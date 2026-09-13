/** @file @brief 실제 GAP/GATT의 등록·전송·session과 지연 callback을 검증합니다. */
#include <NUCODE_BLE_GATT.h>
#include <internal/NUCODE_BLE_Internal.h>
#include <internal/gatt/GattInternal.h>
#include <gatt_mock.h>
#include <zephyr/settings/settings.h>
#include <array>
#include <cstring>
#include <iostream>
using namespace nucode::ble;

static_assert(static_cast<std::uint8_t>(BLECharacteristicEvent::subscribed) == 1U,
              "기존 server event ordinal을 유지해야 합니다.");
static_assert(static_cast<std::uint8_t>(BLECharacteristicEvent::indication_failed) == 5U,
              "기존 server event ordinal을 유지해야 합니다.");
static_assert(static_cast<std::uint8_t>(BLEGattClientEvent::read_complete) == 1U,
              "기존 client event ordinal을 유지해야 합니다.");
static_assert(static_cast<std::uint8_t>(BLEGattClientEvent::operation_failed) == 9U,
              "기존 client event ordinal을 유지해야 합니다.");
static_assert(static_cast<std::uint8_t>(BLEGattClientEvent::read_multiple_complete) == 11U,
              "W04 client event ordinal을 유지해야 합니다.");

namespace nucode::ble::internal
{
    /** @brief GATT 단독 호스트 시험에는 LE CoC main-thread 작업이 없습니다. */
    void pollL2cap() noexcept
    {
    }

    /** @brief GATT 단독 호스트 시험에는 LE CoC 종료 작업이 없습니다. */
    void l2capEnded() noexcept
    {
    }

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
                                 BLEPermission::read | BLEPermission::write, 512);
BLECharacteristic alternate_characteristic(BLEUuid(std::uint16_t{0x2A24}), BLEProperty::write,
                                           BLEPermission::write, 512);
BLECharacteristic second_characteristic(BLEUuid(std::uint16_t{0x2A19}), BLEProperty::read,
                                         BLEPermission::read, 20);
BLEDescriptor descriptors[] = {
    BLEDescriptor(BLEUuid(std::uint16_t{0x2901}), BLEPermission::read | BLEPermission::write, 4U),
    BLEDescriptor(BLEUuid(std::uint16_t{0x2904}), BLEPermission::read | BLEPermission::write, 4U),
    BLEDescriptor(BLEUuid(std::uint16_t{0x2905}), BLEPermission::read | BLEPermission::write, 4U),
    BLEDescriptor(BLEUuid(std::uint16_t{0x2906}), BLEPermission::read | BLEPermission::write, 4U),
};
std::array<unsigned, 20> server_events{}, client_events{};
BLEConnectionHandle observed_server_connection;
std::array<std::uint8_t, 512> observed_data{};
std::size_t observed_length = 0;
std::array<BLEConnectionHandle, 2> observed_handles{};
std::array<std::array<unsigned, 20>, 2> detailed_events{};
std::array<std::array<std::uint8_t, 512>, 2> detailed_data{};
std::array<std::size_t, 2> detailed_lengths{};
bool reenter = false;
BLEDescriptor *observed_descriptor = nullptr;
BLEGattAuthorizationOperation observed_authorization_operation =
    BLEGattAuthorizationOperation::read;
unsigned authorization_calls = 0U;
bool descriptor_access_allowed = true;

bool authorizeAccess(const BLEGattAuthorizationRequest &request, void *context)
{
    ++authorization_calls;
    assert(request.connection.valid());
    if (context != nullptr && !*static_cast<bool *>(context))
    {
        return false;
    }
    return request.operation != BLEGattAuthorizationOperation::write || request.length == 0U ||
           request.data[0] != 0xDEU;
}

void serverObserved(BLECharacteristic &, const BLECharacteristicEventInfo &event, void *)
{
    ++server_events[static_cast<unsigned>(event.event)];
    observed_server_connection = event.connection;
    observed_descriptor = event.descriptor;
    observed_authorization_operation = event.authorization_operation;
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

/** @brief cache miss 후 target service·characteristic·CCC discovery를 완료합니다. */
void completeCachedTarget(bt_conn *connection, std::uint16_t first_handle)
{
    bt_gatt_service_val service_value{
        BT_UUID_GATT_PRIMARY, static_cast<std::uint16_t>(first_handle + 11U)};
    bt_gatt_attr attribute{};
    attribute.user_data = &service_value;
    attribute.handle = first_handle;
    assert(mock_discovery->type == BT_GATT_DISCOVER_PRIMARY);
    mock_discovery->func(connection, &attribute, mock_discovery);
    BLEDevice.poll();

    bt_gatt_chrc characteristic_value{
        BT_UUID_GATT_CHRC, static_cast<std::uint16_t>(first_handle + 2U), 0x3eU};
    attribute.user_data = &characteristic_value;
    attribute.handle = static_cast<std::uint16_t>(first_handle + 1U);
    assert(mock_discovery->type == BT_GATT_DISCOVER_CHARACTERISTIC);
    mock_discovery->func(connection, &attribute, mock_discovery);
    BLEDevice.poll();

    attribute.user_data = nullptr;
    attribute.handle = static_cast<std::uint16_t>(first_handle + 3U);
    assert(mock_discovery->type == BT_GATT_DISCOVER_DESCRIPTOR);
    mock_discovery->func(connection, &attribute, mock_discovery);
    BLEDevice.poll();
    BLEDevice.poll();
}

/** @brief CCC가 없는 read/write target을 service 마지막 handle에서 완료합니다. */
void completeCachedTargetWithoutCcc(bt_conn *connection, std::uint16_t first_handle)
{
    bt_gatt_service_val service_value{
        BT_UUID_GATT_PRIMARY, static_cast<std::uint16_t>(first_handle + 2U)};
    bt_gatt_attr attribute{};
    attribute.user_data = &service_value;
    attribute.handle = first_handle;
    assert(mock_discovery->type == BT_GATT_DISCOVER_PRIMARY);
    mock_discovery->func(connection, &attribute, mock_discovery);
    BLEDevice.poll();

    bt_gatt_chrc characteristic_value{
        BT_UUID_GATT_CHRC, static_cast<std::uint16_t>(first_handle + 2U),
        static_cast<std::uint8_t>(BT_GATT_CHRC_READ | BT_GATT_CHRC_WRITE)};
    attribute.user_data = &characteristic_value;
    attribute.handle = static_cast<std::uint16_t>(first_handle + 1U);
    assert(mock_discovery->type == BT_GATT_DISCOVER_CHARACTERISTIC);
    mock_discovery->func(connection, &attribute, mock_discovery);
    BLEDevice.poll();
    BLEDevice.poll();
}

/** @brief standard Service Changed·Client Features·Database Hash 동기화를 주입합니다. */
void synchronizeCachedDiscovery(BLEConnectionHandle handle, bt_conn *connection,
                                bool expect_target, std::uint16_t first_handle = 20U,
                                bool target_without_ccc = false)
{
    assert(BLEClient.discoverCached(handle, BLEUuid(std::uint16_t{0x180A}),
                                    BLEUuid(std::uint16_t{0x2A29}), 7U));
    bt_gatt_service_val gatt_service{BT_UUID_GATT, 8U};
    bt_gatt_attr attribute{};
    attribute.user_data = &gatt_service;
    attribute.handle = 1U;
    assert(mock_discovery->uuid == BT_UUID_GATT);
    mock_discovery->func(connection, &attribute, mock_discovery);
    BLEDevice.poll();

    bt_gatt_chrc standard_characteristic{BT_UUID_GATT_SC, 3U, BT_GATT_CHRC_INDICATE};
    attribute.user_data = &standard_characteristic;
    attribute.handle = 2U;
    assert(mock_discovery->uuid == BT_UUID_GATT_SC);
    mock_discovery->func(connection, &attribute, mock_discovery);
    BLEDevice.poll();

    attribute.user_data = nullptr;
    attribute.handle = 4U;
    assert(mock_discovery->uuid == BT_UUID_GATT_CCC);
    mock_discovery->func(connection, &attribute, mock_discovery);
    BLEDevice.poll();
    assert(mock_subscription->value_handle == 3U && mock_subscription->ccc_handle == 4U);
    mock_subscription->subscribe(connection, 0U, mock_subscription);
    BLEDevice.poll();

    standard_characteristic = {BT_UUID_GATT_CLIENT_FEATURES, 6U, BT_GATT_CHRC_WRITE};
    attribute.user_data = &standard_characteristic;
    attribute.handle = 5U;
    assert(mock_discovery->uuid == BT_UUID_GATT_CLIENT_FEATURES);
    mock_discovery->func(connection, &attribute, mock_discovery);
    BLEDevice.poll();
    assert(mock_write->handle == 6U && mock_write->length == 1U);
    assert(*static_cast<const std::uint8_t *>(mock_write->data) == 1U);
    mock_write->func(connection, 0U, mock_write);
    BLEDevice.poll();

    standard_characteristic = {BT_UUID_GATT_DB_HASH, 8U, BT_GATT_CHRC_READ};
    attribute.user_data = &standard_characteristic;
    attribute.handle = 7U;
    assert(mock_discovery->uuid == BT_UUID_GATT_DB_HASH);
    mock_discovery->func(connection, &attribute, mock_discovery);
    BLEDevice.poll();
    assert(mock_read->single.handle == 8U && mock_read->handle_count == 1U);
    assert(mock_read->func(connection, 0U, mock_read, mock_database_hash,
                           sizeof(mock_database_hash)) == BT_GATT_ITER_CONTINUE);
    assert(mock_read->func(connection, 0U, mock_read, nullptr, 0U) == BT_GATT_ITER_STOP);
    BLEDevice.poll();
    if (expect_target)
    {
        if (target_without_ccc)
        {
            completeCachedTargetWithoutCcc(connection, first_handle);
        }
        else
        {
            completeCachedTarget(connection, first_handle);
        }
    }
    else
    {
        BLEDevice.poll();
        assert(!BLEClient.busy(handle));
    }
}
int main(int argc, char **argv)
{
    assert(argc == 2);
    const char *scenario = argv[1];
    if (std::strcmp(scenario, "m29_descriptor_authorization") == 0)
    {
        const std::uint8_t descriptor_values[][4] = {
            {0x11U, 0x12U, 0x13U, 0x14U},
            {0x21U, 0x22U, 0x23U, 0x24U},
            {0x31U, 0x32U, 0x33U, 0x34U},
            {0x41U, 0x42U, 0x43U, 0x44U},
        };
        for (std::size_t index = 0U; index < std::size(descriptors); ++index)
        {
            assert(descriptors[index].setValue(descriptor_values[index],
                                               sizeof(descriptor_values[index])));
            assert(characteristic.addDescriptor(descriptors[index]));
        }
        BLEDescriptor fifth_descriptor(BLEUuid(std::uint16_t{0x2907}), BLEPermission::read, 4U);
        assert(!characteristic.addDescriptor(fifth_descriptor));
        characteristic.onAuthorize(authorizeAccess, nullptr);
        descriptors[0].onAuthorize(authorizeAccess, &descriptor_access_allowed);
    }
    else if (std::strcmp(scenario, "m29_descriptor_reuse") == 0)
    {
        assert(characteristic.addDescriptor(descriptors[0]));
        assert(alternate_characteristic.addDescriptor(descriptors[0]));
    }
    assert(service.addCharacteristic(characteristic));
    assert(service.addCharacteristic(alternate_characteristic));
    assert(BLEDevice.addService(service));
    const bool cache_scenario = std::strncmp(scenario, "m29_cache_", 10U) == 0;
    if (cache_scenario)
    {
        assert(BLEGattDatabase.setRevision(0x10203040U));
        assert(BLEGattDatabase.revision() == 0x10203040U);
    }
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
    if (std::strcmp(scenario, "m29_descriptor_reuse") == 0)
    {
        assert(!BLEDevice.begin("descriptor-reuse"));
        assert(BLEDevice.lastDriverError() == -EEXIST);
        return 0;
    }
    characteristic.onEvent(serverObserved, nullptr);
    BLEClient.onEvent(clientObserved, nullptr);
    if (std::strcmp(scenario, "m29_long_parallel") == 0 ||
        std::strcmp(scenario, "m29_long_write") == 0 ||
        std::strcmp(scenario, "client_reentrant_end") == 0)
    {
        BLEClient.onDetailedEvent(detailedClientObserved, nullptr);
    }
    assert(BLEDevice.begin("gatt"));
    if (cache_scenario)
    {
        std::uint8_t local_hash[GattDatabase::hash_length]{};
        assert(BLEGattDatabase.hash(local_hash));
        assert(std::memcmp(local_hash, mock_database_hash, sizeof(local_hash)) == 0);
        assert(std::strcmp(mock_settings_saved_key, "nucode/gatt/database_identity") == 0);
        assert(mock_settings_saved_length == 28U);
        assert(mock_settings_saved_value[8] == 0x40U &&
               mock_settings_saved_value[9] == 0x30U &&
               mock_settings_saved_value[10] == 0x20U &&
               mock_settings_saved_value[11] == 0x10U);
    }
    assert(!service.addCharacteristic(second_characteristic));
    connect();
    auto *connection = &mock_connections[0];
    const auto *attribute = &mock_services[0]->attrs[2];
    std::uint8_t payload[]{1, 2, 3, 4};
    if (std::strcmp(scenario, "m29_cache_restore") == 0)
    {
        BLEConnectionHandle handle = BLEConnection.handle(BLELinkRole::central);
        synchronizeCachedDiscovery(handle, connection, true, 20U);
        assert(BLEClient.cacheState(handle) == BLEGattCacheState::discovered);
        assert(BLEClient.remoteCharacteristic(handle).valueHandle() == 22U);
        assert(client_events[static_cast<unsigned>(BLEGattClientEvent::cache_saved)] == 1U);
        mock_conn_callbacks->disconnected(connection, 0x13U);
        BLEDevice.poll();
        connect(1U);
        connection = &mock_connections[1];
        handle = BLEConnection.handle(BLELinkRole::central);
        synchronizeCachedDiscovery(handle, connection, false);
        assert(BLEClient.cacheState(handle) == BLEGattCacheState::restored);
        assert(BLEClient.remoteCharacteristic(handle).valueHandle() == 22U);
        assert(client_events[static_cast<unsigned>(BLEGattClientEvent::cache_restored)] == 1U);
        const BLEGattCacheStatistics statistics = BLEClient.cacheStatistics();
        assert(statistics.saved == 1U && statistics.restored == 1U);
    }
    else if (std::strcmp(scenario, "m29_cache_service_changed") == 0)
    {
        const BLEConnectionHandle handle = BLEConnection.handle(BLELinkRole::central);
        synchronizeCachedDiscovery(handle, connection, true, 20U);
        const std::uint16_t old_handle = BLEClient.remoteCharacteristic(handle).valueHandle();
        for (std::size_t index = 0U; index < sizeof(mock_database_hash); ++index)
        {
            mock_database_hash[index] ^= 0x5aU;
        }
        const std::uint8_t changed_range[]{0x01U, 0x00U, 0xffU, 0xffU};
        assert(mock_subscription->notify(connection, mock_subscription, changed_range,
                                         sizeof(changed_range)) == BT_GATT_ITER_CONTINUE);
        BLEDevice.poll();
        assert(!BLEClient.discovered(handle));
        assert(mock_read->func(connection, 0U, mock_read, mock_database_hash,
                               sizeof(mock_database_hash)) == BT_GATT_ITER_CONTINUE);
        assert(mock_read->func(connection, 0U, mock_read, nullptr, 0U) ==
               BT_GATT_ITER_STOP);
        BLEDevice.poll();
        completeCachedTarget(connection, 40U);
        assert(BLEClient.cacheState(handle) == BLEGattCacheState::discovered);
        assert(BLEClient.remoteCharacteristic(handle).valueHandle() == 42U);
        assert(BLEClient.remoteCharacteristic(handle).valueHandle() != old_handle);
        assert(client_events[static_cast<unsigned>(BLEGattClientEvent::service_changed)] == 1U);
        assert(client_events[static_cast<unsigned>(BLEGattClientEvent::cache_invalidated)] == 1U);
        assert(BLEClient.cacheStatistics().invalidated == 1U);
    }
    else if (std::strcmp(scenario, "m29_cache_corrupt") == 0)
    {
        std::uint8_t corrupt_record[84]{};
        std::memset(corrupt_record, 0xa5, sizeof(corrupt_record));
        assert(settings_save_one("nucode/gatt/cache/0", corrupt_record,
                                 sizeof(corrupt_record)) == 0);
        const BLEConnectionHandle handle = BLEConnection.handle(BLELinkRole::central);
        synchronizeCachedDiscovery(handle, connection, true, 20U);
        assert(BLEClient.cacheState(handle) == BLEGattCacheState::discovered);
        assert(BLEClient.cacheStatistics().corrupt_rejected == 1U);
        assert(client_events[static_cast<unsigned>(BLEGattClientEvent::cache_restored)] == 0U);
    }
    else if (std::strcmp(scenario, "m29_cache_no_ccc") == 0)
    {
        const BLEConnectionHandle handle = BLEConnection.handle(BLELinkRole::central);
        synchronizeCachedDiscovery(handle, connection, true, 20U, true);
        assert(BLEClient.cacheState(handle) == BLEGattCacheState::discovered);
        assert(BLEClient.remoteCharacteristic(handle).valueHandle() == 22U);
        assert(BLEClient.remoteCharacteristic(handle).cccHandle() == 0U);
        assert(BLEClient.remoteCharacteristic(handle).properties() ==
               (BLEProperty::read | BLEProperty::write));
        assert(BLEDevice.lastError() != BLEError::not_connected);
    }
    else if (std::strcmp(scenario, "m29_descriptor_authorization") == 0)
    {
        const BLEConnectionHandle handle = BLEConnection.handle(BLELinkRole::central);
        assert(handle.valid());
        assert(characteristic.setValue(payload, sizeof(payload)));
        std::uint8_t output[4]{};
        assert(attribute->read(connection, attribute, output, sizeof(output), 0U) == 4);
        assert(std::memcmp(output, payload, sizeof(payload)) == 0);

        const std::uint8_t rejected[]{0xDEU, 0xADU};
        assert(attribute->write(connection, attribute, rejected, sizeof(rejected), 0U, 0U) ==
               BT_GATT_ERR(BT_ATT_ERR_AUTHORIZATION));
        assert(characteristic.readValue(output, sizeof(output)) == sizeof(payload));
        assert(std::memcmp(output, payload, sizeof(payload)) == 0);

        const auto *descriptor_attribute = &mock_services[0]->attrs[3];
        assert(descriptor_attribute->read(connection, descriptor_attribute, output,
                                          sizeof(output), 0U) == 4);
        const std::uint8_t changed[]{0x51U, 0x52U, 0x53U, 0x54U};
        assert(descriptor_attribute->write(connection, descriptor_attribute, changed,
                                           sizeof(changed), 0U, 0U) == 4);
        descriptor_access_allowed = false;
        assert(descriptor_attribute->read(connection, descriptor_attribute, output,
                                          sizeof(output), 0U) ==
               BT_GATT_ERR(BT_ATT_ERR_AUTHORIZATION));
        BLEDevice.poll();
        assert(authorization_calls == 5U);
        assert(server_events[static_cast<unsigned>(BLECharacteristicEvent::authorization_allowed)] ==
               3U);
        assert(server_events[static_cast<unsigned>(BLECharacteristicEvent::authorization_denied)] ==
               2U);
        assert(server_events[static_cast<unsigned>(BLECharacteristicEvent::descriptor_written)] ==
               1U);
        assert(observed_descriptor == &descriptors[0]);
        assert(observed_authorization_operation == BLEGattAuthorizationOperation::read);

        assert(characteristic.notify(handle));
        assert(mock_notification_connection == connection);
        mock_notification.func(connection, mock_notification.user_data);
        BLEDevice.poll();
        assert(characteristic.indicate(handle));
        assert(mock_indication_connection == connection);
        mock_indication->func(connection, mock_indication, 0U);
        mock_indication->destroy(mock_indication);
        BLEDevice.poll();

        discover();
        for (std::size_t index = 0U; index < std::size(descriptors); ++index)
        {
            assert(BLEClient.discoverDescriptor(descriptors[index].uuid()));
            bt_gatt_attr next_characteristic{};
            next_characteristic.handle = 10U;
            assert(mock_discovery->func(connection, &next_characteristic, mock_discovery) ==
                   BT_GATT_ITER_STOP);
            BLEDevice.poll();
            bt_gatt_attr descriptor_discovery{};
            descriptor_discovery.handle = static_cast<std::uint16_t>(5U + index);
            mock_discovery->func(connection, &descriptor_discovery, mock_discovery);
            BLEDevice.poll();
        }
        assert(BLEClient.descriptorCount() == 4U);
        std::uint16_t handles[4]{};
        for (std::size_t index = 0U; index < std::size(handles); ++index)
        {
            const BLERemoteDescriptor remote = BLEClient.remoteDescriptor(index);
            assert(remote.valid() && remote.uuid() == descriptors[index].uuid());
            handles[index] = remote.handle();
        }
        assert(BLEClient.readMultiple(handles, std::size(handles)));
        assert(mock_read->handle_count == 4U && !mock_read->multiple.variable);
        assert(std::memcmp(mock_read->multiple.handles, handles, sizeof(handles)) == 0);
        const std::uint8_t values[]{0x11U, 0x12U, 0x13U, 0x14U, 0x21U, 0x22U, 0x23U, 0x24U,
                                    0x31U, 0x32U, 0x33U, 0x34U, 0x41U, 0x42U, 0x43U, 0x44U};
        assert(mock_read->func(connection, 0U, mock_read, values, sizeof(values)) ==
               BT_GATT_ITER_CONTINUE);
        assert(mock_read->func(connection, 0U, mock_read, nullptr, 0U) == BT_GATT_ITER_STOP);
        BLEDevice.poll();
        assert(client_events[static_cast<unsigned>(BLEGattClientEvent::descriptor_discovery_complete)] ==
               4U);
        assert(client_events[static_cast<unsigned>(BLEGattClientEvent::read_multiple_complete)] ==
               1U);
        assert(observed_length == sizeof(values));
        assert(std::memcmp(observed_data.data(), values, sizeof(values)) == 0);
        assert(!BLEClient.readMultiple(nullptr, std::size(handles)));
        assert(!BLEClient.readMultiple(handles, 1U));
        std::uint16_t five_handles[]{5U, 6U, 7U, 8U, 9U};
        assert(!BLEClient.readMultiple(five_handles, std::size(five_handles)));
        std::uint16_t duplicate_handles[]{handles[0], handles[0]};
        assert(!BLEClient.readMultiple(duplicate_handles, std::size(duplicate_handles)));
        std::uint16_t outside_handles[]{BLEClient.remoteService().startHandle(), handles[1]};
        assert(!BLEClient.readMultiple(outside_handles, std::size(outside_handles)));
        const BLEUuid fifth_descriptor(std::uint16_t{0x2907});
        assert(!BLEClient.discoverDescriptor(fifth_descriptor));
    }
    else if (std::strcmp(scenario, "server_copy") == 0)
    {
        assert(attribute->write(connection, attribute, payload, 4, 0, 0) == 4);
        payload[0] = 99;
        assert(server_events[0] == 0);
        BLEDevice.poll();
        assert(server_events[0] == 1 && observed_length == 4 && observed_data[0] == 1);
        std::uint8_t output[4]{};
        assert(attribute->read(connection, attribute, output, 4, 1) == 3);
        assert(output[0] == 2);
        assert(attribute->write(connection, attribute, payload, 4, 0,
                                BT_GATT_WRITE_FLAG_PREPARE) == 0);
        assert(attribute->write(connection, attribute, payload, 4, 0,
                                BT_GATT_WRITE_FLAG_EXECUTE) == 4);
        assert(attribute->write(connection, attribute, payload, 4, 510, 0) == -13);
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
    else if (std::strcmp(scenario, "m29_long_write") == 0)
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
            first[index] = static_cast<std::uint8_t>((index * 3U) & 0xffU);
            second[index] = static_cast<std::uint8_t>((index * 5U + 0x31U) & 0xffU);
        }
        assert(BLEClient.write(observed_handles[0], first.data(), first.size()));
        assert(BLEClient.write(observed_handles[1], second.data(), second.size()));
        auto *first_write = mock_writes[0];
        auto *second_write = mock_writes[1];
        assert(first_write != nullptr && second_write != nullptr && first_write != second_write);
        assert(first_write->length == 512U && second_write->length == 512U);
        first[0] ^= 0xffU;
        second[0] ^= 0xffU;
        assert(static_cast<const std::uint8_t *>(first_write->data)[0] != first[0]);
        assert(static_cast<const std::uint8_t *>(second_write->data)[0] != second[0]);
        second_write->func(&mock_connections[1], 0U, second_write);
        first_write->func(&mock_connections[0], 0U, first_write);
        BLEDevice.poll();
        assert(detailed_events[0][static_cast<unsigned>(BLEGattClientEvent::write_complete)] == 1U);
        assert(detailed_events[1][static_cast<unsigned>(BLEGattClientEvent::write_complete)] == 1U);
        std::array<std::uint8_t, 513> oversized{};
        assert(!BLEClient.write(observed_handles[0], oversized.data(), oversized.size()));
        assert(BLEDevice.lastError() == BLEError::value_overflow);
        assert(!BLEClient.writeWithoutResponse(observed_handles[0], first.data(), first.size()));

        const auto *alternate_attribute = &mock_services[0]->attrs[5];
        assert((attribute->perm & BT_GATT_PERM_PREPARE_WRITE) != 0U);
        assert((alternate_attribute->perm & BT_GATT_PERM_PREPARE_WRITE) != 0U);
        const std::array<std::uint8_t, 4> seed{9U, 8U, 7U, 6U};
        assert(characteristic.setValue(seed.data(), seed.size()));
        std::array<std::uint8_t, 512> before{};
        assert(characteristic.readValue(before.data(), before.size()) == seed.size());

        first[0] ^= 0xffU;
        second[0] ^= 0xffU;
        assert(attribute->write(&mock_connections[0], attribute, first.data(), 242U, 0U,
                                BT_GATT_WRITE_FLAG_PREPARE) == 0);
        assert(attribute->write(&mock_connections[1], attribute, second.data(), 242U, 0U,
                                BT_GATT_WRITE_FLAG_PREPARE) == 0);
        assert(attribute->write(&mock_connections[0], attribute, first.data() + 242U, 242U, 242U,
                                BT_GATT_WRITE_FLAG_PREPARE) == 0);
        assert(attribute->write(&mock_connections[1], attribute, second.data() + 242U, 242U, 242U,
                                BT_GATT_WRITE_FLAG_PREPARE) == 0);
        assert(attribute->write(&mock_connections[0], attribute, first.data() + 484U, 28U, 484U,
                                BT_GATT_WRITE_FLAG_PREPARE) == 0);
        assert(attribute->write(&mock_connections[1], attribute, second.data() + 484U, 28U, 484U,
                                BT_GATT_WRITE_FLAG_PREPARE) == 0);
        assert(characteristic.readValue(before.data(), before.size()) == seed.size());
        assert(std::memcmp(before.data(), seed.data(), seed.size()) == 0);
        assert(attribute->write(&mock_connections[0], attribute, first.data(), 512U, 0U,
                                BT_GATT_WRITE_FLAG_EXECUTE) == 512);
        assert(attribute->write(&mock_connections[1], attribute, second.data(), 512U, 0U,
                                BT_GATT_WRITE_FLAG_EXECUTE) == 512);
        BLEDevice.poll();
        assert(server_events[static_cast<unsigned>(BLECharacteristicEvent::written)] == 2U);
        assert(observed_server_connection == observed_handles[1]);
        assert(characteristic.readValue(before.data(), before.size()) == second.size());
        assert(before == second);

        assert(attribute->write(&mock_connections[0], attribute, first.data(), 242U, 0U,
                                BT_GATT_WRITE_FLAG_PREPARE) == 0);
        assert(attribute->write(&mock_connections[0], attribute, first.data() + 243U, 20U, 243U,
                                BT_GATT_WRITE_FLAG_PREPARE) ==
               BT_GATT_ERR(BT_ATT_ERR_INVALID_OFFSET));
        assert(attribute->write(&mock_connections[0], attribute, first.data(), 512U, 0U,
                                BT_GATT_WRITE_FLAG_EXECUTE) ==
               BT_GATT_ERR(BT_ATT_ERR_INVALID_OFFSET));
        assert(characteristic.readValue(before.data(), before.size()) == second.size());
        assert(before == second);

        assert(attribute->write(&mock_connections[0], attribute, first.data(), 242U, 0U,
                                BT_GATT_WRITE_FLAG_PREPARE) == 0);
        assert(attribute->write(&mock_connections[0], attribute, first.data() + 484U, 29U, 484U,
                                BT_GATT_WRITE_FLAG_PREPARE) ==
               BT_GATT_ERR(BT_ATT_ERR_INVALID_ATTRIBUTE_LEN));
        assert(attribute->write(&mock_connections[0], alternate_attribute, first.data(), 10U, 0U,
                                BT_GATT_WRITE_FLAG_PREPARE) == 0);
        assert(attribute->write(&mock_connections[0], attribute, first.data(), 10U, 0U,
                                BT_GATT_WRITE_FLAG_PREPARE) ==
               BT_GATT_ERR(BT_ATT_ERR_PREPARE_QUEUE_FULL));
        assert(characteristic.readValue(before.data(), before.size()) == second.size());
        assert(before == second);

        assert(attribute->write(&mock_connections[0], attribute, first.data(), 10U, 0U,
                                BT_GATT_WRITE_FLAG_PREPARE) == 0);
        assert(attribute->write(&mock_connections[0], attribute, first.data(), 11U, 0U,
                                BT_GATT_WRITE_FLAG_EXECUTE) ==
               BT_GATT_ERR(BT_ATT_ERR_INVALID_ATTRIBUTE_LEN));
        assert(characteristic.readValue(before.data(), before.size()) == second.size());
        assert(before == second);

        assert(attribute->write(&mock_connections[0], attribute, first.data(), 10U, 0U,
                                BT_GATT_WRITE_FLAG_PREPARE) == 0);
        nucode::ble::internal::gatt::clearServerTransaction(&mock_connections[0]);
        assert(attribute->write(&mock_connections[0], attribute, first.data(), 10U, 0U,
                                BT_GATT_WRITE_FLAG_EXECUTE) ==
               BT_GATT_ERR(BT_ATT_ERR_INVALID_OFFSET));
        assert(characteristic.readValue(before.data(), before.size()) == second.size());
        assert(before == second);

        assert(attribute->write(&mock_connections[0], attribute, first.data(), 512U, 0U,
                                BT_GATT_WRITE_FLAG_PREPARE) == 0);
        assert(attribute->write(&mock_connections[0], attribute, first.data(), 512U, 0U,
                                BT_GATT_WRITE_FLAG_EXECUTE) == 512);
        assert(characteristic.readValue(before.data(), before.size()) == first.size());
        assert(before == first);
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
