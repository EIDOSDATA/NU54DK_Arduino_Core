/**
 * @file EnvironmentalSensing.ino
 * @brief 표준 BLE Environmental Sensing 온도·습도 값을 갱신합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE_Security.h>

namespace
{

    /** @brief 실패 단계를 출력하고 안전하게 정지합니다. */
    void require(bool condition, const char *stage)
    {
        if (condition)
        {
            return;
        }
        Serial.print("EnvironmentalSensing start failed: ");
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
    const nucode::ble::SecurityConfig security = {
        nucode::ble::SecurityLevel::encrypted, true, 30000U};
    require(BLESecurity.begin(security), "security");
    require(BLEDevice.begin("NU54-Environment"), "device");
    require(BLEAdvertising.clear(), "advertising-clear");
    require(BLEAdvertising.setConnectable(true), "advertising-connectable");
    require(BLEAdvertising.addServiceUuid(nucode::ble::BLEUuid(0x181aU)),
            "advertising-ess");
    require(BLEAdvertising.setScanResponseName(true), "advertising-name");
    require(BLEAdvertising.start(), "advertising-start");
}

void loop()
{
    BLEDevice.poll();
    BLESecurity.poll();
    static std::int16_t temperature = 2200;
    static std::uint16_t humidity = 4500U;
    static_cast<void>(BLEEnvironmentalSensing.setTemperature(temperature));
    static_cast<void>(BLEEnvironmentalSensing.setHumidity(humidity));
    temperature = temperature == 2299 ? 2200 : temperature + 1;
    humidity = humidity == 4599U ? 4500U : humidity + 1U;
    delay(1000);
}
