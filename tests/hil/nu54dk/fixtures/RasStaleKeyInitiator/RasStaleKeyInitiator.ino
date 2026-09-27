/**
 * @file RasStaleKeyInitiator.ino
 * @brief 한쪽만 삭제된 bond의 재연결을 CS initiator에서 거부하는 내부 HIL fixture입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE.h>
#include <NUCODE_BLE_ChannelSounding.h>
#include <NUCODE_BLE_Security.h>

using nucode::ble::BLEAddress;
using nucode::ble::BLEConnectionHandle;
using nucode::ble::BLEEvent;
using nucode::ble::BLEEventInfo;
using nucode::ble::BLEScanResult;
using nucode::ble::BLEUuid;
using nucode::ble::SecurityEvent;
using nucode::ble::SecurityEventRecord;
using nucode::ble::SecurityLevel;
using nucode::ble::cs::Error;
using nucode::ble::cs::InitiatorStage;
using nucode::ble::cs::RasInitiator;
using nucode::ble::cs::RasReading;

namespace
{
    enum class Phase : unsigned char
    {
        idle,
        prime,
        negative,
        stopping,
        stopped,
    };

    constexpr unsigned long watchdogMilliseconds = 90000UL;
    RasInitiator initiator;
    BLEAddress peerAddress;
    BLEConnectionHandle peer;
    Phase phase = Phase::idle;
    bool peerFound = false;
    bool disconnectSeen = false;
    bool primeReported = false;
    bool stopReported = false;
    unsigned int negativePairingRequests = 0U;
    unsigned int negativePairingRejected = 0U;
    unsigned int negativeSecurityErrors = 0U;
    unsigned int negativeDisconnects = 0U;
    unsigned int negativeSecurityReason = 0U;
    unsigned int negativeDisconnectReason = 0U;
    unsigned int negativeSecurityL2 = 0U;
    unsigned int negativeReady = 0U;
    unsigned int negativeRaw = 0U;
    unsigned int primeRaw = 0U;
    unsigned long phaseDeadline = 0UL;

    /** @brief 현재 phase의 bounded watchdog를 갱신합니다. */
    void armWatchdog()
    {
        phaseDeadline = millis() + watchdogMilliseconds;
    }

    /** @brief Ranging Service 광고만 선택하고 scan을 중단합니다. */
    void onScanResult(const BLEScanResult &result, void *context)
    {
        static_cast<void>(context);
        if (!peerFound && result.connectable)
        {
            peerAddress = result.address;
            peerFound = true;
            (void)BLEScan.stop();
        }
    }

    /** @brief 연결마다 CS initiator를 결합하고 disconnect 원본을 보존합니다. */
    void onBleEvent(const BLEEventInfo &event, void *context)
    {
        static_cast<void>(context);
        if ((event.event == BLEEvent::connected) &&
            (event.role == nucode::ble::BLELinkRole::central))
        {
            peer = event.connection;
            const Error result = initiator.begin(peer);
            Serial.print("CSKEY initiator connected phase=");
            Serial.print(phase == Phase::prime ? "prime" : "negative");
            Serial.print(" begin=");
            Serial.println(static_cast<unsigned int>(result));
        }
        else if ((event.event == BLEEvent::disconnected) &&
                 (event.connection == peer))
        {
            if (phase == Phase::negative)
            {
                ++negativeDisconnects;
                negativeDisconnectReason = event.reason;
                Serial.print("CSKEY initiator negative disconnected reason=");
                Serial.println(negativeDisconnectReason);
            }
            initiator.end();
            peer = BLEConnectionHandle();
            peerFound = false;
            disconnectSeen = true;
            Serial.println("CSKEY initiator disconnected");
        }
    }

    /** @brief prime pairing만 승인하고 stale-key repair pairing은 명시적으로 거부합니다. */
    void onSecurityEvent(const SecurityEventRecord &record, void *context)
    {
        static_cast<void>(context);
        if (record.event == SecurityEvent::pairing_requested)
        {
            const bool accept = phase == Phase::prime;
            if (!accept)
            {
                ++negativePairingRequests;
            }
            if (!BLESecurity.acceptPairing(record.connection, accept))
            {
                Serial.println("CSKEY initiator pairing response failed");
                return;
            }
            if (!accept)
            {
                ++negativePairingRejected;
                Serial.println("CSKEY initiator repair pairing rejected");
            }
        }
        else if (record.event == SecurityEvent::paired)
        {
            Serial.print("CSKEY initiator paired bonds=");
            Serial.println(BLESecurity.bondCount());
        }
        else if (record.event == SecurityEvent::security_changed)
        {
            if ((phase == Phase::negative) &&
                (record.level >= SecurityLevel::encrypted))
            {
                ++negativeSecurityL2;
                Serial.println("CSKEY initiator negative L2 UNEXPECTED");
            }
        }
        else if ((phase == Phase::negative) &&
                 ((record.event == SecurityEvent::pairing_failed) ||
                  (record.event == SecurityEvent::pairing_cancelled)))
        {
            Serial.print("CSKEY initiator security rejected reason=");
            Serial.println(record.reason);
        }
        else if ((phase == Phase::negative) &&
                 (record.event == SecurityEvent::error))
        {
            ++negativeSecurityErrors;
            negativeSecurityReason = record.reason;
            Serial.print("CSKEY initiator security error reason=");
            Serial.println(negativeSecurityReason);
        }
    }

    /** @brief RAS service 대상 scan을 시작합니다. */
    bool startScan()
    {
        peerFound = false;
        return BLEScan.clearFilters() &&
               BLEScan.filterServiceUuid(BLEUuid(0x185BU)) && BLEScan.start(true);
    }

    /** @brief 현재 negative 관측값을 key material 없이 출력합니다. */
    void printStatus()
    {
        Serial.print("CSKEY initiator status bonds=");
        Serial.print(BLESecurity.bondCount());
        Serial.print(" pairing_requests=");
        Serial.print(negativePairingRequests);
        Serial.print(" pairing_rejected=");
        Serial.print(negativePairingRejected);
        Serial.print(" security_errors=");
        Serial.print(negativeSecurityErrors);
        Serial.print(" security_reason=");
        Serial.print(negativeSecurityReason);
        Serial.print(" disconnects=");
        Serial.print(negativeDisconnects);
        Serial.print(" disconnect_reason=");
        Serial.print(negativeDisconnectReason);
        Serial.print(" l2=");
        Serial.print(negativeSecurityL2);
        Serial.print(" ready=");
        Serial.print(negativeReady);
        Serial.print(" raw=");
        Serial.print(negativeRaw);
        Serial.print(" connected=");
        Serial.println(BLEConnection.connected(peer) ? 1 : 0);
    }

    /** @brief STOP은 scan·CS·ACL을 순서대로 닫습니다. */
    void requestStop()
    {
        phase = Phase::stopping;
        (void)BLEScan.stop();
        if (initiator.stage() == InitiatorStage::ranging)
        {
            (void)initiator.stop();
        }
        initiator.end();
        if (peer.valid() && BLEConnection.connected(peer))
        {
            (void)BLEConnection.disconnect(peer);
        }
    }

    /** @brief 단일 byte 명령으로 clean·prime·negative·STOP 수명을 구동합니다. */
    void handleCommand(int command)
    {
        if ((command == 'c') && !BLEConnection.connected() &&
            !BLEConnection.connecting())
        {
            (void)BLEScan.stop();
            if (!BLESecurity.eraseAllBonds())
            {
                Serial.println("CSKEY initiator clean failed");
                return;
            }
            phase = Phase::idle;
            Serial.print("CSKEY initiator clean bonds=");
            Serial.println(BLESecurity.bondCount());
        }
        else if ((command == 'p') && (phase == Phase::idle))
        {
            phase = Phase::prime;
            disconnectSeen = false;
            armWatchdog();
            Serial.println(startScan() ? "CSKEY initiator prime scan" :
                                         "CSKEY initiator prime scan failed");
        }
        else if ((command == 'd') && peer.valid() && BLEConnection.connected(peer))
        {
            (void)BLEConnection.disconnect(peer);
            Serial.println("CSKEY initiator disconnect requested");
        }
        else if ((command == 'n') && disconnectSeen &&
                 !BLEConnection.connected() && !BLEConnection.connecting())
        {
            phase = Phase::negative;
            negativePairingRequests = 0U;
            negativePairingRejected = 0U;
            negativeSecurityErrors = 0U;
            negativeDisconnects = 0U;
            negativeSecurityReason = 0U;
            negativeDisconnectReason = 0U;
            negativeSecurityL2 = 0U;
            negativeReady = 0U;
            negativeRaw = 0U;
            armWatchdog();
            Serial.println(startScan() ? "CSKEY initiator negative scan" :
                                         "CSKEY initiator negative scan failed");
        }
        else if (command == 'q')
        {
            printStatus();
        }
        else if (command == 's')
        {
            requestStop();
        }
        else
        {
            Serial.println("CSKEY initiator command rejected");
        }
    }
}

/** @brief 공개 BLE·Security facade를 초기화하되 자동 연결은 시작하지 않습니다. */
void setup()
{
    Serial.begin(115200);
    nucode::ble::SecurityConfig security{};
    security.minimum_level = SecurityLevel::encrypted;
    security.bonding = true;
    security.io_capability = nucode::ble::SecurityIoCapability::no_input_output;
    security.response_timeout_ms = 30000U;
    BLESecurity.onEvent(onSecurityEvent);
    BLEDevice.onEventInfo(onBleEvent);
    BLEScan.onResult(onScanResult);
    if (!BLESecurity.begin(security) || !BLEDevice.begin("NU54-CS-KEY-I"))
    {
        Serial.println("CSKEY initiator setup failed");
        return;
    }
    Serial.print("CSKEY initiator boot bonds=");
    Serial.println(BLESecurity.bondCount());
}

/** @brief prime raw RAS와 stale-key 이후 무진행 경계를 관찰합니다. */
void loop()
{
    BLEDevice.poll();
    BLESecurity.poll();
    initiator.poll();

    if (peerFound && !BLEConnection.connected() && !BLEConnection.connecting())
    {
        peerFound = false;
        if (!BLEConnection.connect(peerAddress))
        {
            Serial.println("CSKEY initiator connect failed");
        }
    }

    if ((phase == Phase::prime) &&
        (initiator.stage() == InitiatorStage::ready))
    {
        (void)initiator.start();
    }
    if ((phase == Phase::negative) &&
        (initiator.stage() == InitiatorStage::ready))
    {
        ++negativeReady;
        Serial.println("CSKEY initiator negative ready UNEXPECTED");
        (void)initiator.start();
    }

    RasReading reading{};
    while (initiator.read(reading))
    {
        if (phase == Phase::prime)
        {
            ++primeRaw;
            if (!primeReported && (BLESecurity.bondCount() == 1U))
            {
                primeReported = true;
                Serial.print("CSKEY initiator prime ready raw=");
                Serial.print(primeRaw);
                Serial.print(" bonds=");
                Serial.println(BLESecurity.bondCount());
            }
        }
        else if (phase == Phase::negative)
        {
            ++negativeRaw;
            Serial.println("CSKEY initiator negative raw UNEXPECTED");
        }
    }

    while (Serial.available() > 0)
    {
        handleCommand(Serial.read());
    }

    if (((phase == Phase::prime) || (phase == Phase::negative)) &&
        (static_cast<long>(millis() - phaseDeadline) >= 0L))
    {
        Serial.println("CSKEY initiator watchdog STOP");
        requestStop();
    }
    if ((phase == Phase::stopping) && !BLEConnection.connected() &&
        !BLEConnection.connecting() && !BLEScan.running() && !stopReported)
    {
        stopReported = true;
        phase = Phase::stopped;
        Serial.println("CSKEY initiator STOPPED");
    }
    delay(1U);
}
