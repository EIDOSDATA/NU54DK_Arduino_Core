/**
 * @file RasReflector.ino
 * @brief 보안 BLE 연결에서 Ranging Service와 CS reflector를 실행합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE.h>
#include <NUCODE_BLE_ChannelSounding.h>
#include <P2MemoryTelemetry.h>

using nucode::ble::BLEConnectionHandle;
using nucode::ble::BLEEvent;
using nucode::ble::BLEEventInfo;
using nucode::ble::BLEUuid;
using nucode::ble::cs::Error;
using nucode::ble::cs::RasReflector;

bool p2Stopped = false;

namespace
{
    RasReflector reflector;
    BLEConnectionHandle peer;
    bool restartAdvertising = false;
    bool wasSecure = false;
    bool wasReady = false;
    bool wasActive = false;
    bool quiesceRequested = false;
    bool quiesceDisconnectRequested = false;
    bool quiesceReported = false;

    /** @brief 연결 상태 변화를 공개 API로 reflector에 전달합니다. */
    void onBleEvent(const BLEEventInfo &event, void *context)
    {
        static_cast<void>(context);
        if (event.event == BLEEvent::connected)
        {
            peer = event.connection;
            if (quiesceRequested)
            {
                quiesceDisconnectRequested = false;
                return;
            }
            const Error result = reflector.begin(peer);
            if (result == Error::none)
            {
                Serial.println("CS reflector connected");
            }
            else
            {
                Serial.print("CS reflector begin failed: ");
                Serial.println(reflector.nativeCode());
            }
        }
        else if ((event.event == BLEEvent::disconnected) &&
                 (event.connection == peer))
        {
            reflector.end();
            peer = BLEConnectionHandle();
            restartAdvertising = !quiesceRequested;
            wasSecure = false;
            wasReady = false;
            wasActive = false;
            Serial.println("CS reflector disconnected");
        }
    }

    /** @brief advertising·CS·ACL을 끝내고 재광고를 금지합니다. */
    void requestQuiesce()
    {
        quiesceRequested = true;
        quiesceDisconnectRequested = false;
        quiesceReported = false;
        restartAdvertising = false;
        reflector.end();
        if (BLEAdvertising.running() && !BLEAdvertising.stop())
        {
            Serial.println("CS quiesce advertising stop failed");
        }
        Serial.println("CS quiesce requested role=reflector");
    }

    /** @brief quiesce 뒤 active ACL·pending 연결·advertising·CS가 모두 0인지 공개합니다. */
    void pollQuiesce()
    {
        if (!quiesceRequested)
        {
            return;
        }
        if (BLEAdvertising.running())
        {
            if (!BLEAdvertising.stop())
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
            !BLEConnection.connecting() && !BLEAdvertising.running() &&
            !quiesceReported)
        {
            quiesceReported = true;
            Serial.println(
                "CS_QUIESCED role=reflector active_acl=0 pending=0 advertising=0 cs=0");
        }
    }
}

/** @brief Ranging Service UUID와 연결 가능한 광고를 시작합니다. */
void setup()
{
    Serial.begin(115200);
    Serial.println("P2_READY role=cs-reflector");
    nucode::test::reportMemory("ready");
    BLEDevice.onEventInfo(onBleEvent);
    if (!BLEDevice.begin("NU54-CS-RSP") || !BLEAdvertising.clear() ||
        !BLEAdvertising.setConnectable(true) ||
        !BLEAdvertising.addServiceUuid(BLEUuid(0x185BU)) ||
        !BLEAdvertising.start())
    {
        Serial.println("CS reflector advertising failed");
        return;
    }
    Serial.println("CS reflector advertising");
}

/** @brief CS 설정 완료와 보안·절차 상태를 Arduino 문맥에서 관찰합니다. */
void loop()
{
    BLEDevice.poll();
    if (p2Stopped)
    {
        if (Serial.available() > 0)
        {
            const int command = Serial.read();
            if (command == 'q')
            {
                requestQuiesce();
            }
        }
        pollQuiesce();
        delay(1);
        return;
    }
    reflector.poll();
    pollQuiesce();

    if (!quiesceRequested && restartAdvertising && !BLEConnection.connected())
    {
        restartAdvertising = false;
        if (!BLEAdvertising.start())
        {
            Serial.println("CS reflector advertising restart failed");
        }
    }

    if (peer.valid())
    {
        const bool secure = reflector.secure();
        const bool ready = reflector.ready();
        const bool active = reflector.active();
        if (secure && !wasSecure)
        {
            Serial.println("CS reflector secure L2");
        }
        if (ready && !wasReady)
        {
            Serial.println("CS reflector config ready");
        }
        if (active != wasActive)
        {
            Serial.println(active ? "CS procedures enabled" :
                                   "CS procedures disabled");
        }
        wasSecure = secure;
        wasReady = ready;
        wasActive = active;
    }

    if (reflector.lastError() == Error::controller_error)
    {
        Serial.print("CS reflector controller error: ");
        Serial.println(reflector.nativeCode());
        reflector.end();
    }
    if (Serial.available() > 0)
    {
        const int command = Serial.read();
        if (command == 'q')
        {
            requestQuiesce();
        }
        else if (command == 's')
        {
            reflector.end();
            if (BLEAdvertising.running() && !BLEAdvertising.stop())
            {
                Serial.println("P2_FAIL stage=cs-reflector-stop");
            }
            nucode::test::reportMemory("stopped");
            Serial.println("P2_STOP role=cs-reflector");
            p2Stopped = true;
            return;
        }
    }
    delay(1);
}
