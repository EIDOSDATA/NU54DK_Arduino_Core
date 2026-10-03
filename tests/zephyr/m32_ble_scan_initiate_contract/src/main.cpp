/**
 * @file main.cpp
 * @brief M32 scan과 initiating 동시 실행 profile의 target link 계약입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE_GAP.h>

static_assert(CONFIG_BT_SCAN_AND_INITIATE_IN_PARALLEL == 1);
static_assert(CONFIG_BT_ID_MAX == 1);

int main()
{
    nucode::ble::BLEConnectionHandle connection;
    const nucode::ble::BLEAddress peer("C0:DE:00:00:00:01",
                                       nucode::ble::BLEAddress::Type::random_address);

    static_cast<void>(BLEScan.startExtended(false, false, false));
    static_cast<void>(BLEConnection.connect(peer, connection));
    return 0;
}
