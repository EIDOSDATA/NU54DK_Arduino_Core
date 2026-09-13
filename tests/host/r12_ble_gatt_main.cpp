/** @file @brief 실제 GAP/GATT의 등록·전송·session과 지연 callback을 검증합니다. */
#include <NUCODE_BLE_GATT.h>
#include <internal/NUCODE_BLE_Internal.h>
#include <gatt_mock.h>
#include <array>
#include <cstring>
#include <iostream>
using namespace nucode::ble;

namespace nucode::ble::internal
{
    /** @brief GATT 단독 호스트 시험에서 Security 연결 통지를 소비합니다. */
    void securityConnected(struct bt_conn *) noexcept
    {
    }

    /** @brief GATT 단독 호스트 시험에서 Security 해제 통지를 소비합니다. */
    void securityDisconnected(struct bt_conn *) noexcept
    {
    }

    /** @brief GATT 단독 호스트 시험에서 Security 변경 통지를 소비합니다. */
    void securityChanged(struct bt_conn *, bt_security_t, enum bt_security_err) noexcept
    {
    }
} // namespace nucode::ble::internal

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
std::array<std::uint8_t, 512> observed_data{};
std::size_t observed_length = 0;
std::array<BLEConnectionHandle, 2> observed_handles{};
std::array<std::array<unsigned, 16>, 2> detailed_events{};
std::array<std::array<std::uint8_t, 512>, 2> detailed_data{};
std::array<std::size_t, 2> detailed_lengths{};
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
void clientEndObserved(BLEGattClientEvent event, const std::uint8_t *, std::size_t, void *)
{
    ++client_events[static_cast<unsigned>(event)];
    BLEDevice.end();
}
void detailedClientObserved(const BLEGattClientEventInfo &information, void *)
{
    std::size_t index = 2U;
    for (std::size_t candidate = 0U; candidate < observed_handles.size(); ++candidate)
    {
        if (information.connection == observed_handles[candidate])
        {
            index = candidate;
            break;
        }
    }
    assert(index < observed_handles.size());
    ++detailed_events[index][static_cast<unsigned>(information.event)];
    if (information.data != nullptr)
    {
        detailed_lengths[index] = information.length;
        std::memcpy(detailed_data[index].data(), information.data, information.length);
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
void discoverLink(BLEConnectionHandle handle, unsigned index, std::uint16_t first_handle)
{
    assert(BLEClient.discover(handle, BLEUuid(std::uint16_t{0x180A}),
                              BLEUuid(std::uint16_t{0x2A29})));
    bt_gatt_service_val value{BT_UUID_GATT_PRIMARY,
                              static_cast<std::uint16_t>(first_handle + 11U)};
    bt_gatt_attr attribute{};
    attribute.user_data = &value;
    attribute.handle = first_handle;
    auto *connection = &mock_connections[index];
    auto *parameters = mock_discoveries[index];
    assert(parameters != nullptr && parameters->type == BT_GATT_DISCOVER_PRIMARY);
    parameters->func(connection, &attribute, parameters);
    BLEDevice.poll();
    parameters = mock_discoveries[index];
    bt_gatt_chrc chrc{BT_UUID_GATT_CHRC,
                      static_cast<std::uint16_t>(first_handle + 2U), 0x3E};
    attribute.user_data = &chrc;
    attribute.handle = static_cast<std::uint16_t>(first_handle + 1U);
    assert(parameters->type == BT_GATT_DISCOVER_CHARACTERISTIC);
    parameters->func(connection, &attribute, parameters);
    BLEDevice.poll();
    parameters = mock_discoveries[index];
    attribute.handle = static_cast<std::uint16_t>(first_handle + 3U);
    assert(parameters->type == BT_GATT_DISCOVER_DESCRIPTOR);
    parameters->func(connection, &attribute, parameters);
    BLEDevice.poll();
    assert(BLEClient.discovered(handle) && !BLEClient.busy(handle));
    assert(BLEClient.remoteCharacteristic(handle).valueHandle() == first_handle + 2U);
    assert(BLEClient.remoteCharacteristic(handle).cccHandle() == first_handle + 3U);
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
    if (std::strcmp(scenario, "m29_long_parallel") == 0 ||
        std::strcmp(scenario, "client_reentrant_end") == 0)
    {
        BLEClient.onDetailedEvent(detailedClientObserved, nullptr);
    }
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
    else if (std::strcmp(scenario, "mixed_server_route") == 0)
    {
        assert(BLEAdvertising.clear() && BLEAdvertising.start());
        mock_conn_callbacks->connected(&mock_connections[1], 0);
        BLEDevice.poll();
        assert(BLEConnection.count() == 2U);
        assert(BLEConnection.role(BLEConnection.handle(BLELinkRole::peripheral)) ==
               BLELinkRole::peripheral);
        assert(attribute->write(&mock_connections[1], attribute, payload, 4, 0, 0) == 4);
        assert(attribute->write(&mock_connections[2], attribute, payload, 4, 0, 0) ==
               BT_GATT_ERR(BT_ATT_ERR_UNLIKELY));
        BLEDevice.poll();
        assert(server_events[static_cast<unsigned>(BLECharacteristicEvent::written)] == 1U);
        assert(characteristic.setValue(payload, 4));
        assert(characteristic.notify());
        assert(mock_notification_connection == &mock_connections[1]);
        mock_notification.func(&mock_connections[1], mock_notification.user_data);
        BLEDevice.poll();
        assert(server_events[static_cast<unsigned>(BLECharacteristicEvent::notification_sent)] ==
               1U);
        assert(characteristic.indicate());
        assert(mock_indication_connection == &mock_connections[1]);
        mock_indication->func(&mock_connections[1], mock_indication, 0);
        mock_indication->destroy(mock_indication);
        BLEDevice.poll();
        assert(server_events[static_cast<unsigned>(BLECharacteristicEvent::indication_confirmed)] ==
               1U);
    }
    else if (std::strcmp(scenario, "m29_long_parallel") == 0)
    {
        observed_handles[0] = BLEConnection.handle(BLELinkRole::central);
        assert(observed_handles[0].valid());
        assert(BLEAdvertising.clear() && BLEAdvertising.start());
        mock_conn_callbacks->connected(&mock_connections[1], 0);
        BLEDevice.poll();
        observed_handles[1] = BLEConnection.handle(BLELinkRole::peripheral);
        assert(observed_handles[1].valid() && observed_handles[1] != observed_handles[0]);
        discoverLink(observed_handles[0], 0U, 1U);
        discoverLink(observed_handles[1], 1U, 21U);

        std::array<std::uint8_t, 512> first{};
        std::array<std::uint8_t, 512> second{};
        for (std::size_t index = 0U; index < first.size(); ++index)
        {
            first[index] = static_cast<std::uint8_t>(index & 0xffU);
            second[index] = static_cast<std::uint8_t>((index + 0x5aU) & 0xffU);
        }
        assert(BLEClient.read(observed_handles[0]));
        assert(BLEClient.read(observed_handles[1]));
        assert(BLEClient.busy(observed_handles[0]) && BLEClient.busy(observed_handles[1]));
        auto *first_read = mock_reads[0];
        auto *second_read = mock_reads[1];
        assert(first_read != nullptr && second_read != nullptr && first_read != second_read);
        assert(first_read->func(&mock_connections[0], 0, first_read, first.data(), 246) ==
               BT_GATT_ITER_CONTINUE);
        assert(second_read->func(&mock_connections[1], 0, second_read, second.data(), 246) ==
               BT_GATT_ITER_CONTINUE);
        assert(first_read->func(&mock_connections[0], 0, first_read, first.data() + 246, 246) ==
               BT_GATT_ITER_CONTINUE);
        assert(second_read->func(&mock_connections[1], 0, second_read, second.data() + 246, 246) ==
               BT_GATT_ITER_CONTINUE);
        assert(first_read->func(&mock_connections[0], 0, first_read, first.data() + 492, 20) ==
               BT_GATT_ITER_CONTINUE);
        assert(second_read->func(&mock_connections[1], 0, second_read, second.data() + 492, 20) ==
               BT_GATT_ITER_CONTINUE);
        assert(first_read->func(&mock_connections[0], 0, first_read, nullptr, 0) ==
               BT_GATT_ITER_STOP);
        assert(second_read->func(&mock_connections[1], 0, second_read, nullptr, 0) ==
               BT_GATT_ITER_STOP);
        BLEDevice.poll();
        assert(detailed_lengths[0] == 512U && detailed_lengths[1] == 512U);
        assert(detailed_data[0] == first && detailed_data[1] == second);
        assert(detailed_events[0][static_cast<unsigned>(BLEGattClientEvent::read_complete)] == 1U);
        assert(detailed_events[1][static_cast<unsigned>(BLEGattClientEvent::read_complete)] == 1U);

        assert(BLEClient.read(observed_handles[0]));
        assert(BLEClient.read(observed_handles[1]));
        first_read = mock_reads[0];
        second_read = mock_reads[1];
        mock_conn_callbacks->disconnected(&mock_connections[0], 0x13);
        assert(first_read->func(&mock_connections[0], 0, first_read, first.data(), 20) ==
               BT_GATT_ITER_STOP);
        assert(BLEClient.busy(observed_handles[1]));
        assert(second_read->func(&mock_connections[1], 0, second_read, second.data(), 512) ==
               BT_GATT_ITER_CONTINUE);
        assert(second_read->func(&mock_connections[1], 0, second_read, nullptr, 0) ==
               BT_GATT_ITER_STOP);
        BLEDevice.poll();
        assert(!BLEClient.read(observed_handles[0]));
        assert(detailed_events[0][static_cast<unsigned>(BLEGattClientEvent::read_complete)] == 1U);
        assert(detailed_events[0][static_cast<unsigned>(BLEGattClientEvent::handles_invalidated)] ==
               1U);
        assert(detailed_events[1][static_cast<unsigned>(BLEGattClientEvent::read_complete)] == 2U);

        assert(BLEClient.read(observed_handles[1]));
        second_read = mock_reads[1];
        assert(second_read->func(&mock_connections[1], 0, second_read, second.data(), 500) ==
               BT_GATT_ITER_CONTINUE);
        assert(second_read->func(&mock_connections[1], 0, second_read, second.data() + 500, 13) ==
               BT_GATT_ITER_STOP);
        assert(!BLEClient.busy(observed_handles[1]));
        BLEDevice.poll();
        assert(detailed_events[1][static_cast<unsigned>(BLEGattClientEvent::operation_failed)] ==
               1U);
        assert(BLEDevice.lastError() == BLEError::value_overflow);
    }
    else if (std::strcmp(scenario, "client_reentrant_end") == 0)
    {
        observed_handles[0] = BLEConnection.handle(BLELinkRole::central);
        assert(observed_handles[0].valid());
        discover();
        BLEClient.onEvent(clientEndObserved, nullptr);
        assert(BLEClient.read());
        assert(mock_read->func(connection, 0, mock_read, payload, 4) ==
               BT_GATT_ITER_CONTINUE);
        assert(mock_read->func(connection, 0, mock_read, nullptr, 0) == BT_GATT_ITER_STOP);
        BLEDevice.poll();
        assert(client_events[static_cast<unsigned>(BLEGattClientEvent::read_complete)] == 1U);
        assert(detailed_events[0][static_cast<unsigned>(BLEGattClientEvent::read_complete)] == 0U);
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
            assert(mock_read->func(connection, 0, mock_read, payload, 4) ==
                   BT_GATT_ITER_CONTINUE);
            assert(BLEClient.busy());
            payload[0] = 99;
            assert(mock_read->func(connection, 0, mock_read, nullptr, 0) == BT_GATT_ITER_STOP);
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
            mock_command_callback(connection, mock_command_user_data);
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
            assert(mock_read->func(&mock_connections[1], 0, mock_read, payload, 4) ==
                   BT_GATT_ITER_CONTINUE);
            assert(mock_read->func(&mock_connections[1], 0, mock_read, nullptr, 0) ==
                   BT_GATT_ITER_STOP);
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
