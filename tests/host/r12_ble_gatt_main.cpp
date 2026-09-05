/** @file @brief 실제 GAP/GATT의 등록·전송·session과 지연 callback을 검증합니다. */
#include <NUCODE_BLE_GATT.h>
#include <internal/NUCODE_BLE_Internal.h>
#include <gatt_mock.h>
#include <array>
#include <cstring>
#include <iostream>
using namespace nucode::ble;
constexpr BLEProperty properties = BLEProperty::read | BLEProperty::write |
                                   BLEProperty::write_without_response | BLEProperty::notify |
                                   BLEProperty::indicate;
BLEService service(BLEUuid(std::uint16_t{0x180A}));
BLEService second_service(BLEUuid(std::uint16_t{0x180F}));
BLECharacteristic characteristic(BLEUuid(std::uint16_t{0x2A29}), properties,
                                 BLEPermission::read | BLEPermission::write, 20);
BLECharacteristic second_characteristic(BLEUuid(std::uint16_t{0x2A19}), BLEProperty::read,
                                        BLEPermission::read, 20);
std::array<unsigned, 16> server_events{}, client_events{};
std::array<std::uint8_t, 244> observed_data{};
std::size_t observed_length = 0;
bool reenter = false;
void serverObserved(BLECharacteristic &, const BLECharacteristicEventInfo &event, void *)
{
    ++server_events[static_cast<unsigned>(event.event)];
    if (event.data != nullptr)
    {
        observed_length = event.length;
        std::memcpy(observed_data.data(), event.data, event.length);
    }
    if (reenter)
    {
        reenter = false;
        BLEDevice.end();
        assert(BLEDevice.begin("reentered"));
    }
}
void clientObserved(BLEGattClientEvent event, const std::uint8_t *data, std::size_t length, void *)
{
    ++client_events[static_cast<unsigned>(event)];
    if (data != nullptr)
    {
        observed_length = length;
        std::memcpy(observed_data.data(), data, length);
    }
}
void connect(unsigned index = 0)
{
    mock_next_connection = &mock_connections[index];
    assert(
        BLEConnection.connect(BLEAddress("01:02:03:04:05:06", BLEAddress::Type::public_address)));
    mock_conn_callbacks->connected(mock_next_connection, 0);
    BLEDevice.poll();
    assert(BLEConnection.connected() && mock_next_connection->refs == 1);
}
void discover(unsigned index = 0)
{
    assert(BLEClient.discover(BLEUuid(std::uint16_t{0x180A}), BLEUuid(std::uint16_t{0x2A29})));
    bt_gatt_service_val value{BT_UUID_GATT_PRIMARY, 12};
    bt_gatt_attr attribute{};
    attribute.user_data = &value;
    attribute.handle = 1;
    auto *connection = &mock_connections[index];
    assert(mock_discovery->type == BT_GATT_DISCOVER_PRIMARY);
    mock_discovery->func(connection, &attribute, mock_discovery);
    BLEDevice.poll();
    bt_gatt_chrc chrc{BT_UUID_GATT_CHRC, 3, 0x3E};
    attribute.user_data = &chrc;
    attribute.handle = 2;
    assert(mock_discovery->type == BT_GATT_DISCOVER_CHARACTERISTIC);
    mock_discovery->func(connection, &attribute, mock_discovery);
    BLEDevice.poll();
    assert(mock_discovery->type == BT_GATT_DISCOVER_DESCRIPTOR);
    attribute.handle = 4;
    mock_discovery->func(connection, &attribute, mock_discovery);
    BLEDevice.poll();
    BLEDevice.poll();
    assert(BLEClient.discovered() && !BLEClient.busy());
    assert(BLEClient.remoteCharacteristic().valueHandle() == 3);
    assert(BLEClient.remoteCharacteristic().cccHandle() == 4);
    assert(connection->refs == 1);
}
int main(int argc, char **argv)
{
    assert(argc == 2);
    const char *scenario = argv[1];
    assert(service.addCharacteristic(characteristic));
    assert(BLEDevice.addService(service));
    if (std::strcmp(scenario, "registration_failure") == 0)
    {
        assert(second_service.addCharacteristic(second_characteristic));
        assert(BLEDevice.addService(second_service));
        mock_register_fail_at = 2;
        assert(!BLEDevice.begin("failed"));
        assert(mock_registration_calls == 2 && mock_unregister_calls == 1);
        assert(mock_enable_calls == 0 && BLEDevice.lastDriverError() == -EIO);
        mock_register_fail_at = 0;
        assert(BLEDevice.begin("retry"));
        assert(mock_registration_calls == 4 && mock_enable_calls == 1);
        BLEDevice.end();
        return 0;
    }
    characteristic.onEvent(serverObserved, nullptr);
    BLEClient.onEvent(clientObserved, nullptr);
    assert(BLEDevice.begin("gatt"));
    assert(!service.addCharacteristic(second_characteristic));
    connect();
    auto *connection = &mock_connections[0];
    const auto *attribute = &mock_services[0]->attrs[2];
    std::uint8_t payload[]{1, 2, 3, 4};
    if (std::strcmp(scenario, "server_copy") == 0)
    {
        assert(attribute->write(connection, attribute, payload, 4, 0, 0) == 4);
        payload[0] = 99;
        assert(server_events[0] == 0);
        BLEDevice.poll();
        assert(server_events[0] == 1 && observed_length == 4 && observed_data[0] == 1);
        std::uint8_t output[4]{};
        assert(attribute->read(connection, attribute, output, 4, 1) == 3);
        assert(output[0] == 2);
        assert(attribute->write(connection, attribute, payload, 4, 0, BT_GATT_WRITE_FLAG_PREPARE) ==
               -6);
        assert(attribute->write(connection, attribute, payload, 4, 19, 0) == -13);
    }
    else if (std::strcmp(scenario, "server_overflow") == 0 ||
             std::strcmp(scenario, "server_reentrant") == 0)
    {
        for (unsigned i = 0; i < 40; ++i)
        {
            assert(attribute->write(connection, attribute, payload, 4, 0, 0) == 4);
        }
        assert(BLEDevice.lastError() == BLEError::event_overflow);
        reenter = std::strcmp(scenario, "server_reentrant") == 0;
        BLEDevice.poll();
        assert(server_events[0] == (std::strcmp(scenario, "server_reentrant") == 0 ? 1U : 24U));
    }
    else if (std::strcmp(scenario, "notification") == 0)
    {
        assert(characteristic.setValue(payload, 4));
        mock_notify_error = -EIO;
        assert(!characteristic.notify());
        mock_notify_error = 0;
        assert(characteristic.notify() && !characteristic.notify());
        assert(mock_notification_data[0] == 1);
        auto completion = mock_notification;
        mock_conn_callbacks->disconnected(connection, 0x13);
        connect(1);
        assert(!characteristic.notify());
        completion.func(connection, completion.user_data);
        BLEDevice.poll();
        assert(server_events[static_cast<unsigned>(BLECharacteristicEvent::notification_sent)] ==
               0);
        assert(characteristic.notify());
        mock_notification.func(&mock_connections[1], mock_notification.user_data);
        BLEDevice.poll();
        assert(server_events[static_cast<unsigned>(BLECharacteristicEvent::notification_sent)] ==
               1);
    }
    else if (std::strcmp(scenario, "indication") == 0)
    {
        assert(characteristic.setValue(payload, 4));
        mock_indicate_error = -EIO;
        assert(!characteristic.indicate());
        mock_indicate_error = 0;
        assert(characteristic.indicate() && !characteristic.indicate());
        payload[0] = 99;
        assert(characteristic.setValue(payload, 4));
        assert(static_cast<const std::uint8_t *>(mock_indication->data)[0] == 1);
        mock_indication->func(connection, mock_indication, 0);
        assert(!characteristic.indicate());
        mock_indication->destroy(mock_indication);
        assert(characteristic.indicate());
        mock_conn_callbacks->disconnected(connection, 0x13);
        connect(1);
        mock_indication->func(connection, mock_indication, 0);
        BLEDevice.poll();
        assert(server_events[static_cast<unsigned>(BLECharacteristicEvent::indication_confirmed)] ==
               0);
        mock_indication->destroy(mock_indication);
        assert(characteristic.indicate());
        mock_indication->func(&mock_connections[1], mock_indication, 0);
        mock_indication->destroy(mock_indication);
        BLEDevice.poll();
        assert(server_events[static_cast<unsigned>(BLECharacteristicEvent::indication_confirmed)] ==
               1);
    }
    else if (std::strcmp(scenario, "discovery_failure") == 0)
    {
        mock_discover_error = -EIO;
        assert(!BLEClient.discover(service.uuid(), characteristic.uuid()));
        assert(!BLEClient.busy());
        mock_discover_error = 0;
        assert(BLEClient.discover(service.uuid(), characteristic.uuid()));
        mock_discovery->func(connection, nullptr, mock_discovery);
        assert(!BLEClient.busy() && !BLEClient.discovered());
        discover();
    }
    else
    {
        discover();
        if (std::strcmp(scenario, "client_io") == 0)
        {
            mock_read_error = -EIO;
            assert(!BLEClient.read() && !BLEClient.busy());
            mock_read_error = 0;
            assert(BLEClient.read() && BLEClient.busy());
            mock_read->func(connection, 0, mock_read, payload, 4);
            payload[0] = 99;
            BLEDevice.poll();
            assert(observed_data[0] == 1 && !BLEClient.busy());
            mock_write_error = -EIO;
            assert(!BLEClient.write(payload, 4) && !BLEClient.busy());
            mock_write_error = 0;
            assert(BLEClient.write(payload, 4));
            payload[0] = 12;
            assert(static_cast<const std::uint8_t *>(mock_write->data)[0] == 99);
            mock_write->func(connection, 0, mock_write);
            assert(!BLEClient.busy());
            assert(BLEClient.writeWithoutResponse(payload, 4));
            mock_command_callback(connection, nullptr);
            assert(!BLEClient.busy());
        }
        else if (std::strcmp(scenario, "client_late") == 0)
        {
            assert(BLEClient.read());
            auto callback = mock_read->func;
            mock_conn_callbacks->disconnected(connection, 0x13);
            connect(1);
            callback(connection, 0, mock_read, payload, 4);
            BLEDevice.poll();
            assert(!BLEClient.discovered() && !BLEClient.remoteService().valid());
            assert(client_events[static_cast<unsigned>(BLEGattClientEvent::read_complete)] == 0);
            discover(1);
            assert(BLEClient.read());
            callback(connection, 0, mock_read, payload, 4);
            assert(BLEClient.busy());
            mock_read->func(&mock_connections[1], 0, mock_read, payload, 4);
            assert(!BLEClient.busy());
        }
        else if (std::strcmp(scenario, "subscription") == 0)
        {
            mock_subscribe_error = -EIO;
            assert(!BLEClient.subscribeNotifications() && !BLEClient.busy());
            mock_subscribe_error = 0;
            assert(BLEClient.subscribeNotifications());
            mock_subscription->subscribe(connection, 0, mock_subscription);
            assert(!BLEClient.busy());
            assert(mock_subscription->notify(connection, mock_subscription, payload, 4) ==
                   BT_GATT_ITER_CONTINUE);
            payload[0] = 99;
            BLEDevice.poll();
            assert(observed_data[0] == 1);
            mock_unsubscribe_error = -EIO;
            assert(!BLEClient.unsubscribe() && !BLEClient.busy());
            mock_unsubscribe_error = 0;
            assert(BLEClient.unsubscribe());
            mock_subscription->notify(connection, mock_subscription, nullptr, 0);
            assert(!BLEClient.busy());
            assert(BLEClient.subscribeIndications());
            mock_subscription->subscribe(connection, 0, mock_subscription);
            mock_conn_callbacks->disconnected(connection, 0x13);
            connect(1);
            assert(mock_subscription->notify(connection, mock_subscription, payload, 4) ==
                   BT_GATT_ITER_STOP);
            BLEDevice.poll();
            assert(client_events[static_cast<unsigned>(BLEGattClientEvent::indication_received)] ==
                   0);
        }
        else if (std::strcmp(scenario, "att_failure") == 0)
        {
            assert(BLEClient.write(payload, 4));
            mock_write->func(connection, BT_ATT_ERR_UNLIKELY, mock_write);
            assert(!BLEClient.busy() && BLEClient.lastAttError() == BT_ATT_ERR_UNLIKELY);
            discover();
            assert(BLEClient.subscribeNotifications());
            mock_subscription->subscribe(connection, BT_ATT_ERR_NOT_SUPPORTED, mock_subscription);
            assert(!BLEClient.busy() && BLEClient.lastAttError() == BT_ATT_ERR_NOT_SUPPORTED);
        }
        else
        {
            assert(false);
        }
    }
    BLEDevice.end();
    for (const auto &c : mock_connections)
    {
        assert(c.refs == 0);
    }
    std::cout << "R12_GATT_PASS=" << scenario << '\n';
}
