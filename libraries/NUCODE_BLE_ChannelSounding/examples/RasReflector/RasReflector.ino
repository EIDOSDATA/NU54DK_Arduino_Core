/**
 * @file RasReflector.ino
 * @brief 보안 BLE 연결에서 Ranging Service와 CS reflector를 실행합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE.h>
#include <NUCODE_BLE_ChannelSounding.h>

using nucode::ble::BLEConnectionHandle;
using nucode::ble::BLEEvent;
using nucode::ble::BLEEventInfo;
using nucode::ble::BLEUuid;
using nucode::ble::cs::Error;
using nucode::ble::cs::RasReflector;

namespace
{
    RasReflector reflector;
    BLEConnectionHandle peer;
    bool restartAdvertising = false;
    bool wasSecure = false;
    bool wasReady = false;
    bool wasActive = false;

    /** @brief 연결 상태 변화를 공개 API로 reflector에 전달합니다. */
    void onBleEvent(const BLEEventInfo &event, void *context)
    {
        static_cast<void>(context);
        if (event.event == BLEEvent::connected)
        {
            peer = event.connection;
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
            restartAdvertising = true;
            wasSecure = false;
            wasReady = false;
            wasActive = false;
            Serial.println("CS reflector disconnected");
        }
    }
}

/** @brief Ranging Service UUID와 연결 가능한 광고를 시작합니다. */
void setup()
{
    Serial.begin(115200);
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
    reflector.poll();

    if (restartAdvertising && !BLEConnection.connected())
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
    delay(1);
}
