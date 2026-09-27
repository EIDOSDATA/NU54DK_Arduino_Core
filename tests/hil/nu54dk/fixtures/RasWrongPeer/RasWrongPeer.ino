/**
 * @file RasWrongPeer.ino
 * @brief 같은 이름으로 다른 서비스를 광고하는 CS negative 시험 peer입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE.h>

using nucode::ble::BLEEvent;
using nucode::ble::BLEEventInfo;
using nucode::ble::BLEUuid;

namespace
{
    bool restartAdvertising = false;

    /** @brief 잘못된 peer에 대한 연결 시도를 Serial로 감시합니다. */
    void onBleEvent(const BLEEventInfo &event, void *context)
    {
        static_cast<void>(context);
        if (event.event == BLEEvent::connected)
        {
            Serial.println("CS wrong peer connected");
        }
        else if (event.event == BLEEvent::disconnected)
        {
            restartAdvertising = true;
            Serial.println("CS wrong peer disconnected");
        }
    }
}

/** @brief Ranging Service 없이 동일한 이름과 다른 UUID를 광고합니다. */
void setup()
{
    Serial.begin(115200);
    BLEDevice.onEventInfo(onBleEvent);
    if (!BLEDevice.begin("NU54-CS-RSP") || !BLEAdvertising.clear() ||
        !BLEAdvertising.setConnectable(true) ||
        !BLEAdvertising.addServiceUuid(BLEUuid(0x180DU)) ||
        !BLEAdvertising.start())
    {
        Serial.println("CS wrong peer advertising failed");
        return;
    }
    Serial.println("CS wrong peer advertising");
}

/** @brief 광고를 유지하고 잘못된 연결 시도를 관찰합니다. */
void loop()
{
    BLEDevice.poll();
    if (restartAdvertising && !BLEConnection.connected())
    {
        restartAdvertising = false;
        if (!BLEAdvertising.start())
        {
            Serial.println("CS wrong peer restart failed");
        }
    }
    delay(1);
}
