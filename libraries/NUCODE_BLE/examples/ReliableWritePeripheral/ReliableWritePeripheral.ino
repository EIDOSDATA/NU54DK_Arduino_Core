/**
 * @file ReliableWritePeripheral.ino
 * @brief 512-byte prepare/execute write를 원자적으로 받는 peripheral 예제입니다.
 */

#include <NUCODE_BLE.h>

const nucode::ble::BLEUuid serviceUuid("8e7e2903-7d8c-4c1a-9d2d-8b6519f77410");
const nucode::ble::BLEUuid valueUuid("8e7e2904-7d8c-4c1a-9d2d-8b6519f77410");
nucode::ble::BLEService writeService(serviceUuid);
nucode::ble::BLECharacteristic
    writeValue(valueUuid, nucode::ble::BLEProperty::read | nucode::ble::BLEProperty::write,
               nucode::ble::BLEPermission::read | nucode::ble::BLEPermission::write, 512U);
bool running = false;

/** @brief 완전히 execute된 값 하나와 그 값을 보낸 link를 main thread에서 보고합니다. */
void onValueEvent(nucode::ble::BLECharacteristic &characteristic,
                  const nucode::ble::BLECharacteristicEventInfo &information, void *context)
{
    static_cast<void>(context);
    if (information.event != nucode::ble::BLECharacteristicEvent::written)
    {
        return;
    }
    Serial.print("reliable write bytes: ");
    Serial.print(information.length);
    Serial.print(", exact link: ");
    Serial.println(information.connection.valid() ? "valid" : "invalid");
    if (!information.connection.valid() || information.offset != 0U ||
        information.without_response || characteristic.valueLength() != 512U)
    {
        Serial.println("unexpected partial write event");
    }
}

/** @brief BLE 오류와 연결 수명 이벤트를 main thread에서 보고합니다. */
void onBleEvent(const nucode::ble::BLEEventInfo &information, void *context)
{
    static_cast<void>(context);
    if (information.event == nucode::ble::BLEEvent::error)
    {
        Serial.print("BLE error: ");
        Serial.println(BLEDevice.lastDriverError());
    }
    else if (information.event == nucode::ble::BLEEvent::connected)
    {
        Serial.println("reliable-write central connected");
    }
    else if (information.event == nucode::ble::BLEEvent::disconnected)
    {
        Serial.println("reliable-write central disconnected");
    }
}

void setup()
{
    Serial.begin(115200);
    writeValue.onEvent(onValueEvent);
    BLEDevice.onEventInfo(onBleEvent);
    running = writeService.addCharacteristic(writeValue) && BLEDevice.addService(writeService) &&
              BLEDevice.begin("NU54-WRITE-P") && BLEAdvertising.clear() &&
              BLEAdvertising.setConnectable(true) && BLEAdvertising.addServiceUuid(serviceUuid) &&
              BLEAdvertising.setScanResponseName(true) && BLEAdvertising.start();
    if (!running)
    {
        Serial.print("reliable write peripheral start failed: ");
        Serial.println(BLEDevice.lastDriverError());
    }
}

void loop()
{
    if (running)
    {
        BLEDevice.poll();
    }
}
