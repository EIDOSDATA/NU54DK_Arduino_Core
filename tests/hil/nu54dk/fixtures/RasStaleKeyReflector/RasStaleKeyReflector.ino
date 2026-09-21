/**
 * @file RasStaleKeyReflector.ino
 * @brief bond를 한쪽에서만 삭제해 stale-key repair pairing을 거부하는 내부 HIL fixture입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE.h>
#include <NUCODE_BLE_ChannelSounding.h>
#include <NUCODE_BLE_Security.h>

using nucode::ble::BLEConnectionHandle;
using nucode::ble::BLEEvent;
using nucode::ble::BLEEventInfo;
using nucode::ble::BLEUuid;
using nucode::ble::SecurityEvent;
using nucode::ble::SecurityEventRecord;
using nucode::ble::SecurityLevel;
using nucode::ble::cs::Error;
using nucode::ble::cs::RasReflector;

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
    RasReflector reflector;
    BLEConnectionHandle peer;
    Phase phase = Phase::idle;
    bool disconnectSeen = false;
    bool primeReported = false;
    bool stopReported = false;
    unsigned int negativePairingRejected = 0U;
    unsigned int negativeSecurityL2 = 0U;
    unsigned int negativeReady = 0U;
    unsigned int negativeActive = 0U;
    unsigned long phaseDeadline = 0UL;

    /** @brief 현재 phase의 bounded watchdog를 갱신합니다. */
    void armWatchdog()
    {
        phaseDeadline = millis() + watchdogMilliseconds;
    }

    /** @brief Ranging Service UUID를 포함한 연결 가능 광고를 시작합니다. */
    bool startAdvertising()
    {
        return BLEAdvertising.clear() && BLEAdvertising.setConnectable(true) &&
               BLEAdvertising.addServiceUuid(BLEUuid(0x185BU)) &&
               BLEAdvertising.start();
    }

    /** @brief 연결 수명에 reflector를 결합하고 disconnect를 보존합니다. */
    void onBleEvent(const BLEEventInfo &event, void *context)
    {
        static_cast<void>(context);
        if ((event.event == BLEEvent::connected) &&
            (event.role == nucode::ble::BLELinkRole::peripheral))
        {
            peer = event.connection;
            const Error result = reflector.begin(peer);
            Serial.print("CSKEY reflector connected phase=");
            Serial.print(phase == Phase::prime ? "prime" : "negative");
            Serial.print(" begin=");
            Serial.println(static_cast<unsigned int>(result));
        }
        else if ((event.event == BLEEvent::disconnected) &&
                 (event.connection == peer))
        {
            reflector.end();
            peer = BLEConnectionHandle();
            disconnectSeen = true;
            Serial.println("CSKEY reflector disconnected");
        }
    }

    /** @brief prime pairing만 승인하고 bond 삭제 뒤 repair pairing은 거부합니다. */
    void onSecurityEvent(const SecurityEventRecord &record, void *context)
    {
        static_cast<void>(context);
        if (record.event == SecurityEvent::pairing_requested)
        {
            const bool accept = phase == Phase::prime;
            if (!BLESecurity.acceptPairing(record.connection, accept))
            {
                Serial.println("CSKEY reflector pairing response failed");
                return;
            }
            if (!accept)
            {
                ++negativePairingRejected;
                Serial.println("CSKEY reflector repair pairing rejected");
            }
        }
        else if (record.event == SecurityEvent::paired)
        {
            Serial.print("CSKEY reflector paired bonds=");
            Serial.println(BLESecurity.bondCount());
        }
        else if (record.event == SecurityEvent::security_changed)
        {
            if ((phase == Phase::negative) &&
                (record.level >= SecurityLevel::encrypted))
            {
                ++negativeSecurityL2;
                Serial.println("CSKEY reflector negative L2 UNEXPECTED");
            }
        }
        else if ((phase == Phase::negative) &&
                 ((record.event == SecurityEvent::pairing_failed) ||
                  (record.event == SecurityEvent::pairing_cancelled)))
        {
            Serial.print("CSKEY reflector security rejected reason=");
            Serial.println(record.reason);
        }
    }

    /** @brief 현재 negative 관측값을 key material 없이 출력합니다. */
    void printStatus()
    {
        Serial.print("CSKEY reflector status bonds=");
        Serial.print(BLESecurity.bondCount());
        Serial.print(" pairing_rejected=");
        Serial.print(negativePairingRejected);
        Serial.print(" l2=");
        Serial.print(negativeSecurityL2);
        Serial.print(" ready=");
        Serial.print(negativeReady);
        Serial.print(" active=");
        Serial.print(negativeActive);
        Serial.print(" connected=");
        Serial.println(BLEConnection.connected(peer) ? 1 : 0);
    }

    /** @brief STOP은 광고·reflector·ACL을 순서대로 닫습니다. */
    void requestStop()
    {
        phase = Phase::stopping;
        (void)BLEAdvertising.stop();
        reflector.end();
        if (peer.valid() && BLEConnection.connected(peer))
        {
            (void)BLEConnection.disconnect(peer);
        }
    }

    /** @brief single-byte 명령으로 clean·prime·한쪽 erase·negative·STOP을 구동합니다. */
    void handleCommand(int command)
    {
        if ((command == 'c') && !BLEConnection.connected())
        {
            (void)BLEAdvertising.stop();
            if (!BLESecurity.eraseAllBonds())
            {
                Serial.println("CSKEY reflector clean failed");
                return;
            }
            phase = Phase::idle;
            Serial.print("CSKEY reflector clean bonds=");
            Serial.println(BLESecurity.bondCount());
        }
        else if ((command == 'p') && (phase == Phase::idle))
        {
            phase = Phase::prime;
            disconnectSeen = false;
            armWatchdog();
            Serial.println(startAdvertising() ? "CSKEY reflector prime advertising" :
                                                "CSKEY reflector prime advertising failed");
        }
        else if ((command == 'e') && disconnectSeen &&
                 !BLEConnection.connected())
        {
            if (!BLESecurity.eraseAllBonds())
            {
                Serial.println("CSKEY reflector stale erase failed");
                return;
            }
            Serial.print("CSKEY reflector stale erased bonds=");
            Serial.println(BLESecurity.bondCount());
        }
        else if ((command == 'n') && disconnectSeen &&
                 !BLEConnection.connected())
        {
            phase = Phase::negative;
            negativePairingRejected = 0U;
            negativeSecurityL2 = 0U;
            negativeReady = 0U;
            negativeActive = 0U;
            armWatchdog();
            Serial.println(startAdvertising() ? "CSKEY reflector negative advertising" :
                                                "CSKEY reflector negative advertising failed");
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
            Serial.println("CSKEY reflector command rejected");
        }
    }
}

/** @brief 공개 BLE·Security facade를 초기화하되 명령 전 광고하지 않습니다. */
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
    if (!BLESecurity.begin(security) || !BLEDevice.begin("NU54-CS-KEY-R"))
    {
        Serial.println("CSKEY reflector setup failed");
        return;
    }
    Serial.print("CSKEY reflector boot bonds=");
    Serial.println(BLESecurity.bondCount());
}

/** @brief prime CS 준비와 stale-key 이후 보안·ready 무진행을 관찰합니다. */
void loop()
{
    BLEDevice.poll();
    BLESecurity.poll();
    reflector.poll();

    if ((phase == Phase::prime) && reflector.secure() && reflector.ready() &&
        !primeReported && (BLESecurity.bondCount() == 1U))
    {
        primeReported = true;
        Serial.print("CSKEY reflector prime ready bonds=");
        Serial.println(BLESecurity.bondCount());
    }
    if (phase == Phase::negative)
    {
        if (reflector.ready())
        {
            ++negativeReady;
            Serial.println("CSKEY reflector negative ready UNEXPECTED");
        }
        if (reflector.active())
        {
            ++negativeActive;
            Serial.println("CSKEY reflector negative active UNEXPECTED");
        }
    }

    while (Serial.available() > 0)
    {
        handleCommand(Serial.read());
    }

    if (((phase == Phase::prime) || (phase == Phase::negative)) &&
        (static_cast<long>(millis() - phaseDeadline) >= 0L))
    {
        Serial.println("CSKEY reflector watchdog STOP");
        requestStop();
    }
    if ((phase == Phase::stopping) && !BLEConnection.connected() &&
        !BLEAdvertising.running() && !stopReported)
    {
        stopReported = true;
        phase = Phase::stopped;
        Serial.println("CSKEY reflector STOPPED");
    }
    delay(1U);
}
