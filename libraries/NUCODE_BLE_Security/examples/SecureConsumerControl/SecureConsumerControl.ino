/**
 * @file SecureConsumerControl.ino
 * @brief 암호화된 표준 BLE HID consumer-control report를 보냅니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE_Security.h>

namespace
{

    constexpr std::uint16_t volume_increment_usage = 0x00e9U;

    /** @brief 실패 단계를 출력하고 안전하게 정지합니다. */
    void require(bool condition, const char *stage)
    {
        if (condition)
        {
            return;
        }
        Serial.print("SecureConsumerControl start failed: ");
        Serial.println(stage);
        while (true)
        {
            delay(1000);
        }
    }

} // namespace

void setup()
{
    Serial.begin(115200);
    const nucode::ble::SecurityConfig security = {nucode::ble::SecurityLevel::encrypted, true,
                                                  30000U};
    require(BLESecurity.begin(security), "security");
    require(BLEConsumerControl.begin(), "consumer-control");
    require(BLEDevice.begin("NU54-Consumer-Control"), "device");
    require(BLEAdvertising.clear(), "advertising-clear");
    require(BLEAdvertising.setConnectable(true), "advertising-connectable");
    require(BLEAdvertising.addServiceUuid(nucode::ble::BLEUuid(0x1812U)), "advertising-hids");
    require(BLEAdvertising.setScanResponseName(true), "advertising-name");
    require(BLEAdvertising.start(), "advertising-start");
}

void loop()
{
    BLEDevice.poll();
    BLESecurity.poll();
    if (BLEConsumerControl.connected())
    {
        static_cast<void>(BLEConsumerControl.press(volume_increment_usage));
        delay(20);
        static_cast<void>(BLEConsumerControl.release());
        delay(980);
    }
    else
    {
        delay(10);
    }
}
