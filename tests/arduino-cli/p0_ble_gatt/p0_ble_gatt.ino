/**
 * @file p0_ble_gatt.ino
 * @brief P0 adaptive BLE 역할의 저수준 설정 없는 build fixture입니다.
 */

#include <NUCODE_BLE.h>

const nucode::ble::BLEUuid serviceUuid("9f3c1001-8b7a-4d64-a1b2-001122334455");
const nucode::ble::BLEUuid valueUuid("9f3c1002-8b7a-4d64-a1b2-001122334455");
nucode::ble::BLEService fixtureService(serviceUuid);
nucode::ble::BLECharacteristic fixtureValue(
    valueUuid, nucode::ble::BLEProperty::read | nucode::ble::BLEProperty::write,
    nucode::ble::BLEPermission::read | nucode::ble::BLEPermission::write, 64U);

/** @brief 실제 server storage가 링크되도록 단일 service schema를 등록합니다. */
void setup()
{
    Serial.begin(115200);
    const std::uint8_t initial[] = {'o', 'k'};
    if (!fixtureValue.setValue(initial, sizeof(initial)) ||
        !fixtureService.addCharacteristic(fixtureValue) ||
        !BLEDevice.addService(fixtureService) || !BLEDevice.begin("P0-GATT"))
    {
        Serial.println("GATT fixture start failed");
    }
}

/** @brief deferred GATT event를 Arduino main thread에서 처리합니다. */
void loop()
{
    BLEDevice.poll();
}
