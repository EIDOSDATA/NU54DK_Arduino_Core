/**
 * @file GAPPeripheral.ino
 * @brief 이름·UUID·manufacturer data를 포함한 connectable 광고 예제입니다.
 */

#include <NUCODE_BLE.h>

const nucode::ble::BLEUuid advertisedService(0x180fU);
bool restartAdvertising = false;

/** @brief BLEDevice.poll()의 Arduino main-thread event를 처리합니다. */
void onBleEvent(nucode::ble::BLEEvent event, void *context)
{
    static_cast<void>(context);
    if (event == nucode::ble::BLEEvent::disconnected)
    {
        restartAdvertising = true;
    }
}

void setup()
{
    Serial.begin(115200);
    BLEDevice.onEvent(onBleEvent);

    const uint8_t productData[] = {0x19U, 0x01U};
    if (!BLEDevice.begin("NU54-GAP-P") || !BLEAdvertising.clear() ||
        !BLEAdvertising.setConnectable(true) || !BLEAdvertising.setInterval(0x00a0U, 0x00f0U) ||
        !BLEAdvertising.addServiceUuid(advertisedService) ||
        !BLEAdvertising.setManufacturerData(0x0059U, productData, sizeof(productData)) ||
        !BLEAdvertising.start())
    {
        Serial.println("BLE GAP start failed");
    }
}

void loop()
{
    BLEDevice.poll();
    if (restartAdvertising && !BLEConnection.connected())
    {
        restartAdvertising = false;
        static_cast<void>(BLEAdvertising.start());
    }
}
