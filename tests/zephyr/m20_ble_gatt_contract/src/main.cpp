/**
 * @file main.cpp
 * @brief M20 범용 GATT server/client 공개 API의 target 계약을 검증합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE.h>

#include <cstdint>

const nucode::ble::BLEUuid service_uuid("12345678-1234-5678-1234-56789abcdef0");
const nucode::ble::BLEUuid characteristic_uuid("12345678-1234-5678-1234-56789abcdef1");
nucode::ble::BLEService service(service_uuid);
nucode::ble::BLECharacteristic characteristic(
    characteristic_uuid,
    nucode::ble::BLEProperty::read | nucode::ble::BLEProperty::write |
        nucode::ble::BLEProperty::write_without_response |
        nucode::ble::BLEProperty::notify | nucode::ble::BLEProperty::indicate,
    nucode::ble::BLEPermission::read | nucode::ble::BLEPermission::write, 64U);

/** @brief server callback signature를 target compiler에 고정합니다. */
void onCharacteristic(nucode::ble::BLECharacteristic &owner,
                      const nucode::ble::BLECharacteristicEventInfo &event,
                      void *context)
{
    static_cast<void>(owner);
    static_cast<void>(event);
    static_cast<void>(context);
}

/** @brief generic client callback signature를 target compiler에 고정합니다. */
void onClient(nucode::ble::BLEGattClientEvent event, const std::uint8_t *data,
              std::size_t length, void *context)
{
    static_cast<void>(event);
    static_cast<void>(data);
    static_cast<void>(length);
    static_cast<void>(context);
}

int main()
{
    const std::uint8_t initial[] = {0x10U, 0x20U};
    characteristic.onEvent(onCharacteristic);
    BLEClient.onEvent(onClient);
    static_cast<void>(characteristic.setValue(initial, sizeof(initial)));
    static_cast<void>(service.addCharacteristic(characteristic));
    static_cast<void>(BLEDevice.addService(service));
    static_cast<void>(BLEClient.remoteService());
    static_cast<void>(BLEClient.remoteCharacteristic());
    static_cast<void>(BLEClient.lastAttError());
    return 0;
}
