/**
 * @file CustomGattPeripheral.ino
 * @brief cached value, write, notify와 indicate를 제공하는 custom GATT 예제입니다.
 */

#include <NUCODE_BLE.h>

const nucode::ble::BLEUuid serviceUuid("9f3c0001-8b7a-4d64-a1b2-001122334455");
const nucode::ble::BLEUuid valueUuid("9f3c0002-8b7a-4d64-a1b2-001122334455");
nucode::ble::BLEService customService(serviceUuid);
nucode::ble::BLECharacteristic
    customValue(valueUuid,
                nucode::ble::BLEProperty::read | nucode::ble::BLEProperty::write |
                    nucode::ble::BLEProperty::write_without_response |
                    nucode::ble::BLEProperty::notify | nucode::ble::BLEProperty::indicate,
                nucode::ble::BLEPermission::read | nucode::ble::BLEPermission::write, 64U);

/** @brief peer write를 main thread에서 cached echo와 notification으로 처리합니다. */
void onCharacteristic(nucode::ble::BLECharacteristic &characteristic,
                      const nucode::ble::BLECharacteristicEventInfo &event, void *context)
{
    static_cast<void>(context);
    if (event.event == nucode::ble::BLECharacteristicEvent::written)
    {
        if (characteristic.notificationSubscribed())
        {
            static_cast<void>(characteristic.notify());
        }
        else if (characteristic.indicationSubscribed())
        {
            static_cast<void>(characteristic.indicate());
        }
    }
}

void setup()
{
    Serial.begin(115200);
    const uint8_t initial[] = {'r', 'e', 'a', 'd', 'y'};
    customValue.onEvent(onCharacteristic);
    if (!customValue.setValue(initial, sizeof(initial)) ||
        !customService.addCharacteristic(customValue) || !BLEDevice.addService(customService) ||
        !BLEDevice.begin("NU54-GATT-P") || !BLEAdvertising.clear() ||
        !BLEAdvertising.addServiceUuid(serviceUuid) || !BLEAdvertising.start())
    {
        Serial.println("custom GATT start failed");
    }
}

void loop()
{
    BLEDevice.poll();
}
