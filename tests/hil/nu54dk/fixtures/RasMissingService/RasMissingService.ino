/**
 * @file RasMissingService.ino
 * @brief Ranging Service UUID만 광고하고 GATT 서비스는 제공하지 않는 시험 peer입니다.
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

    /** @brief 연결·해제 횟수를 외부 HIL runner에 알립니다. */
    void onBleEvent(const BLEEventInfo &event, void *context)
    {
        static_cast<void>(context);
        if (event.event == BLEEvent::connected)
        {
            Serial.println("CS missing service connected");
        }
        else if (event.event == BLEEvent::disconnected)
        {
            restartAdvertising = true;
            Serial.println("CS missing service disconnected");
        }
    }
}

/** @brief 실제 서비스 없이 Ranging UUID를 광고합니다. */
void setup()
{
    Serial.begin(115200);
    BLEDevice.onEventInfo(onBleEvent);
    if (!BLEDevice.begin("NU54-CS-RSP") || !BLEAdvertising.clear() ||
        !BLEAdvertising.setConnectable(true) ||
        !BLEAdvertising.addServiceUuid(BLEUuid(0x185BU)) ||
        !BLEAdvertising.start())
    {
        Serial.println("CS missing service advertising failed");
        return;
    }
    Serial.println("CS missing service advertising");
}

/** @brief 연결 해제 후 다시 광고해 거부·복구를 반복 시험합니다. */
void loop()
{
    BLEDevice.poll();
    if (restartAdvertising && !BLEConnection.connected())
    {
        restartAdvertising = false;
        if (!BLEAdvertising.start())
        {
            Serial.println("CS missing service restart failed");
        }
    }
    delay(1);
}
