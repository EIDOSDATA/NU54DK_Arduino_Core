/**
 * @file main.cpp
 * @brief M19 BLE Core/GAP 공개 API의 target compile/link 계약을 검증합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE_GAP.h>

#include <cstdint>

/** @brief Core event callback signature를 link graph에 고정합니다. */
void onBleEvent(nucode::ble::BLEEvent event, void *context)
{
    auto *value = static_cast<volatile std::uint8_t *>(context);
    if (value != nullptr)
    {
        *value = static_cast<std::uint8_t>(event);
    }
}

/** @brief bounded scan 결과 callback signature를 고정합니다. */
void onScanResult(const nucode::ble::BLEScanResult &result, void *context)
{
    auto *value = static_cast<volatile std::int8_t *>(context);
    if (value != nullptr)
    {
        *value = result.rssi;
    }
}

int main()
{
    volatile std::uint8_t event = 0U;
    volatile std::int8_t rssi = 0;
    const nucode::ble::BLEUuid uuid16(0x180fU);
    const nucode::ble::BLEUuid second_uuid16(0x180aU);
    const nucode::ble::BLEUuid uuid32 = nucode::ble::BLEUuid::from32(0x12345678U);
    const nucode::ble::BLEUuid uuid128("12345678-1234-5678-1234-56789abcdef0");
    const nucode::ble::BLEAddress address("C0:12:34:56:78:9A",
                                          nucode::ble::BLEAddress::Type::random_address);

    BLEDevice.onEvent(onBleEvent, const_cast<std::uint8_t *>(&event));
    BLEScan.onResult(onScanResult, const_cast<std::int8_t *>(&rssi));
    static_cast<void>(BLEAdvertising.setConnectable(true));
    static_cast<void>(BLEAdvertising.setInterval(0x20U, 0x40U));
    static_cast<void>(BLEAdvertising.addServiceUuid(uuid16));
    static_cast<void>(BLEAdvertising.addServiceUuid(second_uuid16));
    static_cast<void>(BLEAdvertising.setServiceData(uuid32, nullptr, 0U));
    static_cast<void>(BLEScan.filterServiceUuid(uuid128));
    static_cast<void>(BLEScan.filterAddress(address));
    static_cast<void>(BLEConnection.peerAddress());
    static_cast<void>(BLEConnection.phy());
    static_cast<void>(BLEDevice.lastError());
    return 0;
}
