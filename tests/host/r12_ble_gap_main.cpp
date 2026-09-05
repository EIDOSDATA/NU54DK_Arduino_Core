/** @file @brief 실제 GAP public API의 callback/reference/session 경계를 검증합니다. */
#include <NUCODE_BLE_GAP.h>
#include <internal/NUCODE_BLE_Internal.h>
#include <ble_mock.h>
#include <array>
#include <cstring>
#include <iostream>
using namespace nucode::ble;
std::array<unsigned, 32> events{};
bool reenter = false;
unsigned scan_results = 0;
void observed(BLEEvent event, void *)
{
    ++events[static_cast<unsigned>(event)];
    if (reenter && event == BLEEvent::connected)
    {
        reenter = false;
        BLEDevice.end();
        assert(BLEDevice.begin("reentered"));
    }
}
void scanned(const BLEScanResult &result, void *)
{
    ++scan_results;
    assert(std::strcmp(result.name, "abc") == 0);
    BLEDevice.end();
}
void connect(unsigned index = 0)
{
    mock_next_connection = &mock_connections[index];
    assert(
        BLEConnection.connect(BLEAddress("01:02:03:04:05:06", BLEAddress::Type::public_address)));
    assert(mock_connections[index].refs == 1);
    mock_conn_callbacks->connected(&mock_connections[index], 0);
    assert(BLEConnection.connected());
}
int main(int argc, char **argv)
{
    assert(argc == 2);
    const char *const scenario = argv[1];
    if (std::strcmp(scenario, "settings_failure") == 0)
    {
        mock_settings_error = -EIO;
        assert(!BLEDevice.begin("failed"));
        assert(BLEDevice.lastDriverError() == -EIO);
        assert(!internal::settingsReady() && internal::settingsResult() == -EIO);
        assert(!BLEDevice.begin("retry"));
        assert(mock_enable_calls == 1 && mock_settings_calls == 1);
        return 0;
    }
    BLEDevice.onEvent(observed, nullptr);
    assert(BLEDevice.begin("host"));
    BLEDevice.poll();
    assert(events[static_cast<unsigned>(BLEEvent::initialized)] == 1);
    if (std::strcmp(scenario, "lifecycle") == 0)
    {
        connect();
        assert(mock_connections[0].refs == 1);
        assert(BLEConnection.mtu() == 247 && mock_connections[0].refs == 1);
        std::int8_t power = 0;
        assert(BLEConnection.txPower(power) && power == -4 && mock_connections[0].refs == 1);
        assert(BLEConnection.requestParameters(24, 40, 0, 400));
        BLEDevice.poll();
        assert(events[static_cast<unsigned>(BLEEvent::connected)] == 1);
        assert(BLEConnection.disconnect());
        mock_conn_callbacks->disconnected(&mock_connections[0], 0x13);
        assert(!BLEConnection.connected() && mock_connections[0].refs == 0);
    }
    else if (std::strcmp(scenario, "late_callback") == 0)
    {
        connect();
        BLEDevice.poll();
        assert(BLEConnection.requestMtu());
        mock_conn_callbacks->disconnected(&mock_connections[0], 0x13);
        BLEDevice.poll();
        mock_mtu_parameters->func(&mock_connections[0], 0, mock_mtu_parameters);
        mock_gatt_callbacks->att_mtu_updated(&mock_connections[0], 247, 247);
        mock_conn_callbacks->le_param_updated(&mock_connections[0], 24, 0, 400);
        BLEDevice.poll();
        assert(events[static_cast<unsigned>(BLEEvent::mtu_changed)] == 0);
        assert(events[static_cast<unsigned>(BLEEvent::parameters_changed)] == 0);
        assert(mock_connections[0].refs == 0);
    }
    else if (std::strcmp(scenario, "reconnect") == 0)
    {
        connect();
        mock_conn_callbacks->disconnected(&mock_connections[0], 0x13);
        mock_next_connection = &mock_connections[1];
        assert(BLEConnection.reconnect());
        mock_conn_callbacks->connected(&mock_connections[1], 0);
        mock_conn_callbacks->disconnected(&mock_connections[0], 0x13);
        mock_gatt_callbacks->att_mtu_updated(&mock_connections[0], 247, 247);
        BLEDevice.poll();
        assert(BLEConnection.connected() && mock_connections[1].refs == 1);
        assert(events[static_cast<unsigned>(BLEEvent::mtu_changed)] == 0);
    }
    else if (std::strcmp(scenario, "queue_overflow") == 0)
    {
        connect();
        BLEDevice.poll();
        for (unsigned index = 0; index < 40; ++index)
        {
            mock_gatt_callbacks->att_mtu_updated(&mock_connections[0], 247, 247);
        }
        assert(BLEDevice.droppedEvents() == 16);
        assert(BLEDevice.lastError() == BLEError::event_overflow);
        BLEDevice.poll();
        assert(events[static_cast<unsigned>(BLEEvent::mtu_changed)] == 24);
    }
    else if (std::strcmp(scenario, "reentrant") == 0)
    {
        reenter = true;
        connect();
        mock_conn_callbacks->le_param_updated(&mock_connections[0], 24, 0, 400);
        BLEDevice.poll();
        assert(!reenter && BLEDevice.initialized() && !BLEConnection.connected());
        assert(mock_connections[0].refs == 0);
        assert(events[static_cast<unsigned>(BLEEvent::parameters_changed)] == 0);
        assert(mock_enable_calls == 1 && mock_settings_calls == 1);
    }
    else if (std::strcmp(scenario, "pending_end") == 0)
    {
        assert(BLEConnection.connect(
            BLEAddress("01:02:03:04:05:06", BLEAddress::Type::public_address)));
        BLEDevice.end();
        assert(mock_connections[0].refs == 0);
        assert(BLEDevice.begin("new-session"));
        mock_conn_callbacks->connected(&mock_connections[0], 0);
        BLEDevice.poll();
        assert(!BLEConnection.connected() && mock_connections[0].refs == 0);
        assert(events[static_cast<unsigned>(BLEEvent::connected)] == 0);
    }
    else if (std::strcmp(scenario, "scan_copy") == 0)
    {
        assert(BLEScan.start(true));
        std::uint8_t payload[]{4, BT_DATA_NAME_COMPLETE, 'a', 'b', 'c'};
        net_buf_simple data{payload, sizeof(payload)};
        const bt_addr_le_t address{BT_ADDR_LE_PUBLIC, {{1, 2, 3, 4, 5, 6}}};
        mock_scan_callback(&address, -50, BT_GAP_ADV_TYPE_ADV_IND, &data);
        std::memset(payload, 0, sizeof(payload));
        BLEScan.onResult(scanned, nullptr);
        BLEDevice.poll();
        assert(scan_results == 1 && !BLEDevice.initialized());
        mock_scan_callback(&address, -50, BT_GAP_ADV_TYPE_ADV_IND, &data);
        assert(BLEScan.available() == 0);
    }
    else if (std::strcmp(scenario, "advertising") == 0)
    {
        assert(BLEAdvertising.clear());
        assert(BLEAdvertising.start() && mock_advertising_options == 3U);
        mock_conn_callbacks->connected(&mock_connections[0], 0);
        assert(BLEConnection.connected() && mock_connections[0].refs == 1);
        mock_conn_callbacks->disconnected(&mock_connections[0], 0x13);
        assert(BLEAdvertising.clear());
        assert(BLEAdvertising.setConnectable(false));
        assert(BLEAdvertising.start() && mock_advertising_options == 512U);
        assert(BLEAdvertising.stop());
        const std::uint8_t payload[25]{};
        assert(BLEAdvertising.setManufacturerData(0x1234, payload, sizeof(payload)));
        const auto calls = mock_advertising_calls;
        assert(!BLEAdvertising.start());
        assert(BLEDevice.lastError() == BLEError::payload_overflow &&
               mock_advertising_calls == calls);
    }
    else if (std::strcmp(scenario, "driver_failure") == 0)
    {
        mock_create_error = -ENOMEM;
        assert(!BLEConnection.connect(
            BLEAddress("01:02:03:04:05:06", BLEAddress::Type::public_address)));
        assert(!BLEConnection.connecting() && mock_connections[0].refs == 0);
        mock_create_error = 0;
        connect();
        mock_mtu_error = -EIO;
        assert(!BLEConnection.requestMtu() && mock_connections[0].refs == 1);
        mock_mtu_error = 0;
        assert(BLEConnection.requestMtu());
        mock_mtu_parameters->func(&mock_connections[0], 0, mock_mtu_parameters);
    }
    else
    {
        assert(false);
    }
    BLEDevice.end();
    for (const auto &connection : mock_connections)
    {
        assert(connection.refs == 0);
    }
    std::cout << "R12_GAP_PASS=" << scenario << '\n';
}
