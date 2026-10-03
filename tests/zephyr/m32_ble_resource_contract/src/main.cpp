/**
 * @file main.cpp
 * @brief M32 ARF-01 BLE 역할별 자원 profile의 target link 계약입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE_GAP.h>

int main()
{
    nucode::ble::BLEAdvertisingSetHandle advertising_set;
    nucode::ble::BLEPeriodicSyncHandle periodic_sync;
    nucode::ble::BLEExtendedAdvertisingParameters parameters;
    static_cast<void>(BLEExtendedAdvertising.create(parameters, advertising_set));
    static_cast<void>(BLEPeriodicAdvertising.exists(periodic_sync));
    static_cast<void>(BLEIdentity.count());
    static_cast<void>(BLEAdvertisingLists.filterAcceptCapacity());
    return 0;
}
