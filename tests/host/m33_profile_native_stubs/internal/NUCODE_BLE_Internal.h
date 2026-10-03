/** @file @brief generation별 reference 획득·반환을 관찰합니다. */
#pragma once
#include <NUCODE_BLE.h>
#include <zephyr/bluetooth/bluetooth.h>
namespace nucode::ble::internal
{
    inline bt_conn *referenceConnection(BLEConnectionHandle peer)
    {
        if (!BLEConnection.connected(peer))
        {
            return nullptr;
        }
        ++native_connection.references;
        return &native_connection;
    }
    inline BLEConnectionHandle handleForActiveConnection(bt_conn *conn)
    {
        return conn == &native_connection ? BLEConnection.peer : BLEConnectionHandle{};
    }
} // namespace nucode::ble::internal
