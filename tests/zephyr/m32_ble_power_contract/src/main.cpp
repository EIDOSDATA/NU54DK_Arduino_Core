/**
 * @file main.cpp
 * @brief M32 LE Power Control·RSSI·Path Loss 공개 API의 target link 계약입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE_GAP.h>

#include <cstdint>

static_assert(CONFIG_BT_MAX_CONN == 2);
static_assert(CONFIG_BT_TRANSMIT_POWER_CONTROL == 1);
static_assert(CONFIG_BT_PATH_LOSS_MONITORING == 1);
static_assert(CONFIG_BT_CTLR_CONN_RSSI == 1);

/** @brief Power/Path Loss event payload를 compile-time에 접근합니다. */
void onDetailedEvent(const nucode::ble::BLEEventInfo &information, void *context)
{
    auto *value = static_cast<volatile std::int8_t *>(context);
    if (value == nullptr)
    {
        return;
    }
    if (information.event == nucode::ble::BLEEvent::transmit_power_report)
    {
        *value = information.transmit_power.level_dbm;
    }
    else if (information.event == nucode::ble::BLEEvent::path_loss_changed)
    {
        *value = static_cast<std::int8_t>(information.path_loss.path_loss_db);
    }
}

int main()
{
    volatile std::int8_t observed = 0;
    nucode::ble::BLEConnectionHandle connection;
    nucode::ble::BLETransmitPowerLevel power;
    nucode::ble::BLEPathLossParameters path_loss;
    std::int8_t rssi = 0;

    BLEDevice.onEventInfo(onDetailedEvent, const_cast<std::int8_t *>(&observed));
    static_cast<void>(BLEConnection.localTransmitPower(
        connection, nucode::ble::BLETransmitPowerPhy::le_1m, power));
    static_cast<void>(BLEConnection.requestRemoteTransmitPower(
        connection, nucode::ble::BLETransmitPowerPhy::le_1m));
    static_cast<void>(BLEConnection.requestRemoteTransmitPowerChange(
        connection, nucode::ble::BLETransmitPowerPhy::le_1m, 3));
    static_cast<void>(BLEConnection.setTransmitPowerReporting(connection, true, true));
    static_cast<void>(BLEConnection.readRssi(connection, rssi));
    static_cast<void>(BLEConnection.configurePathLossMonitoring(connection, path_loss));
    static_cast<void>(BLEConnection.setPathLossMonitoring(connection, true));
    static_cast<void>(BLEConnection.setPathLossMonitoring(connection, false));
    return 0;
}
