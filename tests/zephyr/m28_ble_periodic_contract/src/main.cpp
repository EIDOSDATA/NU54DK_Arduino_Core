/**
 * @file main.cpp
 * @brief M28-W04 periodic advertising·sync·PAST 공개 API의 target 계약입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE_GAP.h>

static_assert(CONFIG_BT_PER_ADV == 1);
static_assert(CONFIG_BT_PER_ADV_SYNC == 1);
static_assert(CONFIG_BT_PER_ADV_SYNC_MAX == 1);
static_assert(CONFIG_BT_PER_ADV_SYNC_TRANSFER_RECEIVER == 1);
static_assert(CONFIG_BT_PER_ADV_SYNC_TRANSFER_SENDER == 1);
static_assert(nucode::ble::PeriodicAdvertising::maximum_payload_length == 255U);
static_assert(nucode::ble::BLEPeriodicReport::maximum_payload_length == 255U);

int main()
{
    nucode::ble::BLEAdvertisingSetHandle advertising_set;
    nucode::ble::BLEPeriodicSyncHandle sync;
    nucode::ble::BLEConnectionHandle connection;
    nucode::ble::BLEPeriodicAdvertisingParameters parameters{};
    nucode::ble::BLEPeriodicReport report{};
    const nucode::ble::BLEAddress address(
        "01:02:03:04:05:06", nucode::ble::BLEAddress::Type::public_address);
    std::uint8_t payload[255]{};
    payload[0] = 254U;
    payload[1] = 0xffU;

    static_cast<void>(BLEPeriodicAdvertising.configure(advertising_set, parameters));
    static_cast<void>(BLEPeriodicAdvertising.setData(advertising_set, payload,
                                                     sizeof(payload)));
    static_cast<void>(BLEPeriodicAdvertising.start(advertising_set));
    static_cast<void>(BLEPeriodicAdvertising.running(advertising_set));
    static_cast<void>(BLEPeriodicAdvertising.stop(advertising_set));
    static_cast<void>(BLEPeriodicAdvertising.createSync(address, 1U, sync));
    static_cast<void>(BLEPeriodicAdvertising.exists(sync));
    static_cast<void>(BLEPeriodicAdvertising.synchronized(sync));
    static_cast<void>(BLEPeriodicAdvertising.available());
    static_cast<void>(BLEPeriodicAdvertising.read(report));
    static_cast<void>(BLEPeriodicAdvertising.transferSync(sync, connection));
    static_cast<void>(BLEPeriodicAdvertising.transferSet(advertising_set, connection));
    static_cast<void>(BLEPeriodicAdvertising.subscribeTransfers(connection));
    static_cast<void>(BLEPeriodicAdvertising.unsubscribeTransfers(connection));
    static_cast<void>(BLEPeriodicAdvertising.deleteSync(sync));
    return 0;
}
