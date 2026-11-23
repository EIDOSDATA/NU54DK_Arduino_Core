/**
 * @file RasInitiator.ino
 * @brief 보안 연결의 Ranging Service를 찾아 CS raw step을 수집합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE.h>
#include <NUCODE_BLE_ChannelSounding.h>
#include <P2MemoryTelemetry.h>

#if defined(NUCODE_P2_CS_DIAGNOSTICS) && \
    !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE) && !defined(NUCODE_CAPABILITY_PROBE)
extern "C"
{
#include <bluetooth/services/ras.h>
#include <zephyr/bluetooth/conn.h>
#include <zephyr/sys/atomic.h>
}
#endif

using nucode::ble::BLEAddress;
using nucode::ble::BLEConnectionHandle;
using nucode::ble::BLEEvent;
using nucode::ble::BLEEventInfo;
using nucode::ble::BLEScanResult;
using nucode::ble::BLEUuid;
using nucode::ble::cs::Error;
using nucode::ble::cs::InitiatorStage;
using nucode::ble::cs::RasInitiator;
using nucode::ble::cs::RasReading;

bool p2StopRequested = false;

namespace
{
#if defined(NUCODE_P2_CS_DIAGNOSTICS) && \
    !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE) && !defined(NUCODE_CAPABILITY_PROBE)
    constexpr std::size_t diagnosticCounterLimit = 1024U;
    atomic_t controllerFlags[diagnosticCounterLimit] = {};
    atomic_t controllerCallbacks[diagnosticCounterLimit] = {};
    atomic_t controllerProcedureStatus[diagnosticCounterLimit] = {};
    atomic_t controllerSubeventStatus[diagnosticCounterLimit] = {};
    atomic_t controllerReportedSteps[diagnosticCounterLimit] = {};
    atomic_t controllerProcedureAbortReason[diagnosticCounterLimit] = {};
    atomic_t controllerSubeventAbortReason[diagnosticCounterLimit] = {};
    bool deliveredCounters[diagnosticCounterLimit] = {};
    bool anyDeliveredCounter = false;
    std::uint16_t highestDeliveredCounter = 0U;

    /** @brief Arduino 읽기 queue와 독립적으로 controller CS 상태를 관찰합니다. */
    void observeCsSubevent(bt_conn *connection,
                           bt_conn_le_cs_subevent_result *result)
    {
        static_cast<void>(connection);
        if (result == nullptr)
        {
            return;
        }
        const std::uint16_t counter = bt_ras_rreq_get_ranging_counter(
            result->header.procedure_counter);
        if (counter >= diagnosticCounterLimit)
        {
            return;
        }
        atomic_or(&controllerFlags[counter], 1);
        atomic_inc(&controllerCallbacks[counter]);
        atomic_set(&controllerProcedureStatus[counter],
                   result->header.procedure_done_status);
        atomic_set(&controllerSubeventStatus[counter],
                   result->header.subevent_done_status);
        atomic_set(&controllerReportedSteps[counter],
                   result->header.num_steps_reported);
        if (result->header.procedure_done_status ==
            BT_CONN_LE_CS_PROCEDURE_ABORTED)
        {
            atomic_or(&controllerFlags[counter], 2);
            atomic_set(&controllerProcedureAbortReason[counter],
                       result->header.procedure_abort_reason);
        }
        if (result->header.subevent_done_status ==
            BT_CONN_LE_CS_SUBEVENT_ABORTED)
        {
            atomic_or(&controllerFlags[counter], 4);
            atomic_set(&controllerSubeventAbortReason[counter],
                       result->header.subevent_abort_reason);
        }
        if ((result->step_data_buf == nullptr) ||
            (result->step_data_buf->len == 0U))
        {
            atomic_or(&controllerFlags[counter], 8);
        }
    }

    BT_CONN_CB_DEFINE(p2_cs_controller_observer) = {
        .le_cs_subevent_data_available = observeCsSubevent,
    };

    /** @brief Controller가 보았으나 Arduino 읽기로 전달되지 않은 counter를 출력합니다. */
    void reportMissingCounters()
    {
        if (!anyDeliveredCounter)
        {
            return;
        }
        for (std::uint16_t counter = 0U;
             counter <= highestDeliveredCounter; counter++)
        {
            if (deliveredCounters[counter])
            {
                continue;
            }
            Serial.print("P2_CS_MISSING counter=");
            Serial.print(counter);
            Serial.print(" flags=");
            Serial.print(atomic_get(&controllerFlags[counter]));
            Serial.print(" callbacks=");
            Serial.print(atomic_get(&controllerCallbacks[counter]));
            Serial.print(" procedure_status=");
            Serial.print(atomic_get(&controllerProcedureStatus[counter]));
            Serial.print(" subevent_status=");
            Serial.print(atomic_get(&controllerSubeventStatus[counter]));
            Serial.print(" steps=");
            Serial.print(atomic_get(&controllerReportedSteps[counter]));
            Serial.print(" procedure_abort_reason=");
            Serial.print(atomic_get(&controllerProcedureAbortReason[counter]));
            Serial.print(" subevent_abort_reason=");
            Serial.println(atomic_get(&controllerSubeventAbortReason[counter]));
        }
    }
#endif

    RasInitiator initiator;
    BLEAddress peerAddress;
    BLEConnectionHandle peer;
    bool peerFound = false;
    bool restartScan = false;
    bool started = false;
    bool reportedFailure = false;
    bool riskScanActive = false;
    bool riskDisconnectPending = false;
    bool quiesceRequested = false;
    bool quiesceDisconnectRequested = false;
    bool quiesceReported = false;
    unsigned long riskScanStartedMs = 0UL;
    std::uint32_t riskDisconnectCycles = 0U;
    constexpr unsigned long riskRadioOverlapMs = 100UL;

    /** @brief Ranging Service를 광고하는 연결 가능한 reflector를 선택합니다. */
    void onScanResult(const BLEScanResult &result, void *context)
    {
        static_cast<void>(context);
        if (riskScanActive || quiesceRequested)
        {
            return;
        }
        if (!peerFound && result.connectable)
        {
            peerAddress = result.address;
            peerFound = true;
            if (!BLEScan.stop())
            {
                Serial.println("CS scan stop failed");
            }
        }
    }

    /** @brief BLE 연결 수명을 Ranging Requestor에 전달합니다. */
    void onBleEvent(const BLEEventInfo &event, void *context)
    {
        static_cast<void>(context);
        if ((event.event == BLEEvent::connected) &&
            (event.role == nucode::ble::BLELinkRole::central))
        {
            peer = event.connection;
            if (quiesceRequested)
            {
                quiesceDisconnectRequested = false;
                return;
            }
            const Error result = initiator.begin(peer);
            if (result == Error::none)
            {
                Serial.println("CS initiator connected; securing");
            }
            else
            {
                Serial.print("CS initiator begin failed: ");
                Serial.println(initiator.nativeCode());
            }
        }
        else if ((event.event == BLEEvent::disconnected) &&
                 (event.connection == peer))
        {
            if (riskScanActive)
            {
                riskDisconnectCycles++;
                Serial.print("P2_CS_RISK_DISCONNECTED cycle=");
                Serial.print(riskDisconnectCycles);
                Serial.print(" radio_scan=");
                Serial.println(BLEScan.running() ? 1 : 0);
            }
            initiator.end();
            peer = BLEConnectionHandle();
            peerFound = false;
            restartScan = !p2StopRequested && !quiesceRequested;
            started = false;
            reportedFailure = false;
            riskScanActive = false;
            riskDisconnectPending = false;
            quiesceDisconnectRequested = false;
            Serial.println("CS initiator disconnected");
        }
    }

    /** @brief scan·CS·ACL을 끝내고 재연결을 금지하는 종료 절차를 시작합니다. */
    void requestQuiesce()
    {
        quiesceRequested = true;
        quiesceDisconnectRequested = false;
        quiesceReported = false;
        p2StopRequested = true;
        restartScan = false;
        peerFound = false;
        riskScanActive = false;
        riskDisconnectPending = false;
        if ((initiator.stage() == InitiatorStage::ranging) &&
            (initiator.stop() != Error::none))
        {
            Serial.println("CS quiesce stop failed");
        }
        if (BLEScan.running() && !BLEScan.stop())
        {
            Serial.println("CS quiesce scan stop failed");
        }
        Serial.println("CS quiesce requested role=initiator");
    }

    /** @brief quiesce 뒤 active ACL·pending 연결·scan·CS가 모두 0인지 공개합니다. */
    void pollQuiesce()
    {
        if (!quiesceRequested)
        {
            return;
        }
        if (BLEScan.running())
        {
            if (!BLEScan.stop())
            {
                return;
            }
        }
        if (peer.valid() && BLEConnection.connected() &&
            !quiesceDisconnectRequested)
        {
            if (!BLEConnection.disconnect(peer))
            {
                return;
            }
            quiesceDisconnectRequested = true;
        }
        if (!peer.valid() && !BLEConnection.connected() &&
            !BLEConnection.connecting() && !BLEScan.running() &&
            !quiesceReported)
        {
            initiator.end();
            started = false;
            quiesceReported = true;
            Serial.println(
                "CS_QUIESCED role=initiator active_acl=0 pending=0 scan=0 cs=0");
        }
    }
}

/** @brief 공개 BLE scan과 연결 event를 설정합니다. */
void setup()
{
    Serial.begin(115200);
    Serial.println("P2_READY role=cs-initiator");
    nucode::test::reportMemory("ready");
    BLEScan.onResult(onScanResult);
    BLEDevice.onEventInfo(onBleEvent);
    if (!BLEDevice.begin("NU54-CS-INIT") || !BLEScan.clearFilters() ||
        !BLEScan.filterServiceUuid(BLEUuid(0x185BU)) || !BLEScan.start(true))
    {
        Serial.println("CS initiator scan failed");
    }
}

/** @brief CS 보안·GATT·controller 단계를 진행하고 raw 결과를 출력합니다. */
void loop()
{
    BLEDevice.poll();
    initiator.poll();
    pollQuiesce();

    if (!quiesceRequested && peerFound && !BLEConnection.connected() &&
        !BLEConnection.connecting())
    {
        peerFound = false;
        if (!BLEConnection.connect(peerAddress))
        {
            restartScan = true;
            Serial.println("CS initiator connect failed");
        }
    }
    if (!quiesceRequested && restartScan && !BLEConnection.connected() &&
        !BLEConnection.connecting())
    {
        restartScan = false;
        if (!BLEScan.running() && !BLEScan.start(true))
        {
            Serial.println("CS initiator scan restart failed");
        }
    }

    if (riskDisconnectPending &&
        ((millis() - riskScanStartedMs) >= riskRadioOverlapMs))
    {
        if (!peer.valid() ||
            (initiator.stage() != InitiatorStage::ranging) ||
            !BLEScan.running())
        {
            riskDisconnectPending = false;
            Serial.println("P2_FAIL stage=cs-risk-active-boundary");
        }
        else if (BLEConnection.disconnect(peer))
        {
            riskDisconnectPending = false;
            Serial.print("P2_CS_RISK_ABORT cycle=");
            Serial.print(riskDisconnectCycles + 1U);
            Serial.println(" radio=scan acl=disconnect-requested");
        }
        else
        {
            riskDisconnectPending = false;
            Serial.println("P2_FAIL stage=cs-risk-acl-disconnect");
        }
    }

    if (!quiesceRequested &&
        (initiator.stage() == InitiatorStage::ready) && !started)
    {
        if (initiator.start() == Error::none)
        {
            started = true;
            Serial.println("CS procedures requested");
        }
    }
    if ((initiator.stage() == InitiatorStage::failed) && !reportedFailure)
    {
        reportedFailure = true;
        Serial.print("CS initiator failed: ");
        Serial.println(initiator.nativeCode());
    }

    RasReading reading;
    while (initiator.read(reading))
    {
#if defined(NUCODE_P2_CS_DIAGNOSTICS) && \
    !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE) && !defined(NUCODE_CAPABILITY_PROBE)
        if (reading.ranging_counter < diagnosticCounterLimit)
        {
            deliveredCounters[reading.ranging_counter] = true;
            anyDeliveredCounter = true;
            if (reading.ranging_counter > highestDeliveredCounter)
            {
                highestDeliveredCounter = reading.ranging_counter;
            }
        }
#endif
        Serial.print("CS_RAW counter=");
        Serial.print(reading.ranging_counter);
        Serial.print(" local=");
        Serial.print(reading.local_steps);
        Serial.print(" peer=");
        Serial.print(reading.peer_steps);
        Serial.print(" rtt=");
        Serial.print(reading.mode_1_steps);
        Serial.print(" tone=");
        Serial.print(reading.mode_2_steps);
        Serial.print(" valid_rtt=");
        Serial.print(reading.valid_rtt_samples);
        if (reading.valid_rtt_samples > 0U)
        {
            Serial.print(" distance_m=");
            Serial.print(reading.rtt_distance_meters, 3);
        }
        Serial.println();
    }

    if (Serial.available() > 0)
    {
        const int command = Serial.read();
        if ((command == 's') && (initiator.stage() == InitiatorStage::ranging))
        {
            if (initiator.stop() == Error::none)
            {
                Serial.println("CS procedures stop requested");
                p2StopRequested = true;
                Serial.print("P2_CS_STATS completed=");
                Serial.println(initiator.completed());
                const nucode::ble::cs::RasStatistics causes = initiator.statistics();
                Serial.print("P2_CS_CAUSES busy=");
                Serial.print(causes.local_busy_drops);
                Serial.print(" overflow=");
                Serial.print(causes.local_overflows);
                Serial.print(" procedure_abort=");
                Serial.print(causes.procedure_aborts);
                Serial.print(" subevent_abort=");
                Serial.print(causes.subevent_aborts);
                Serial.print(" mismatch=");
                Serial.print(causes.ras_counter_mismatches);
                Serial.print(" ras_error=");
                Serial.print(causes.ras_errors);
                Serial.print(" local_missing=");
                Serial.print(causes.local_missing);
                Serial.print(" invalid=");
                Serial.print(causes.invalid_readings);
                Serial.print(" queue_full=");
                Serial.println(causes.reading_queue_full);
#if defined(NUCODE_P2_CS_DIAGNOSTICS) && \
    !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE) && !defined(NUCODE_CAPABILITY_PROBE)
                reportMissingCounters();
#endif
                nucode::test::reportMemory("stopped");
                Serial.println("P2_STOP role=cs-initiator");
            }
        }
        else if ((command == 'r') && (initiator.stage() == InitiatorStage::ready))
        {
            if (initiator.start() == Error::none)
            {
                Serial.println("CS procedures restart requested");
            }
        }
        else if ((command == 'd') && peer.valid())
        {
            if (BLEConnection.disconnect(peer))
            {
                Serial.println("CS disconnect requested");
            }
            else
            {
                Serial.println("CS disconnect failed");
            }
        }
        else if ((command == 'x') && peer.valid() &&
                 (initiator.stage() == InitiatorStage::ranging) &&
                 !riskScanActive && !riskDisconnectPending)
        {
            if (!BLEScan.running() && !BLEScan.start(true))
            {
                Serial.println("P2_FAIL stage=cs-risk-radio-start");
            }
            else if (!BLEScan.running())
            {
                Serial.println("P2_FAIL stage=cs-risk-radio-not-running");
            }
            else
            {
                riskScanActive = true;
                riskDisconnectPending = true;
                riskScanStartedMs = millis();
                Serial.print("P2_CS_RISK_ACTIVE cycle=");
                Serial.print(riskDisconnectCycles + 1U);
                Serial.println(" radio=scan acl=connected");
            }
        }
        else if (command == 'q')
        {
            requestQuiesce();
        }
    }
    delay(1);
}
