/**
 * @file main.cpp
 * @brief M28-W06 privacy·RPA와 link별 제어 공개 API의 target 계약입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE_GAP.h>

static_assert(CONFIG_BT_MAX_CONN == 2);
static_assert(CONFIG_BT_PRIVACY == 1);
static_assert(CONFIG_BT_RPA_TIMEOUT_DYNAMIC == 1);
static_assert(CONFIG_BT_USER_DATA_LEN_UPDATE == 1);
static_assert(CONFIG_BT_REMOTE_INFO == 1);
static_assert(CONFIG_BT_REMOTE_VERSION == 1);

int main()
{
    nucode::ble::BLEConnectionHandle connection;
    nucode::ble::BLEConnectionParameters parameters{};
    nucode::ble::BLEDataLengthInfo data_length{};
    nucode::ble::BLERemoteInformation remote{};

    static_cast<void>(BLEPrivacy.supported());
    static_cast<void>(BLEPrivacy.setRotationTimeout(900U));
    static_cast<void>(BLEPrivacy.rotationTimeout());
    static_cast<void>(BLEPrivacy.expirationCount());
    static_cast<void>(BLEConnection.connectionAddress(connection));
    static_cast<void>(BLEConnection.identityResolved(connection));
    static_cast<void>(BLEConnection.parameters(connection, parameters));
    static_cast<void>(BLEConnection.requestDataLength(connection));
    static_cast<void>(BLEConnection.dataLength(connection, data_length));
    static_cast<void>(BLEConnection.remoteInformation(connection, remote));
    return 0;
}
