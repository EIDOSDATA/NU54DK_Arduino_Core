/** @file @brief GATT session·link별 queue·deferred callback 수명주기입니다.
 * SPDX-License-Identifier: MIT
 */
#if !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE)
#include "internal/gatt/GattInternal.h"

/** @brief legacy signing library가 제공하지 않으면 영속화를 fail-closed로 거부합니다. */
extern "C" __weak int nucode_ble_signing_persist(struct bt_conn *connection)
{
    ARG_UNUSED(connection);
    return -ENOTSUP;
}

namespace nucode::ble::internal::gatt
{
    namespace
    {
        SessionState state{};
        K_MSGQ_DEFINE(gatt_event_queue, sizeof(GattEventRecord),
                      CONFIG_NUCODE_BLE_GATT_EVENT_QUEUE_SIZE, alignof(GattEventRecord));

        /** @brief link context의 remote handle과 operation 상태를 고정 초기화합니다. */
        bool clearClientState(ClientState &client) noexcept
        {
            k_spinlock_key_t state_key = k_spin_lock(&client.client_state_lock);
            const bool had_handles = client.remote_service.valid() ||
                                     client.remote_characteristic.valid() ||
                                     atomic_get(&client.client_subscribed) != 0 ||
                                     atomic_get(&client.client_busy_value) != 0;
            GattAccess::clear(client.remote_service);
            GattAccess::clear(client.remote_characteristic);
            for (BLERemoteDescriptor &descriptor : client.remote_descriptors)
            {
                GattAccess::clear(descriptor);
            }
            client.remote_descriptor_count = 0U;
            k_spin_unlock(&client.client_state_lock, state_key);
            atomic_set(&client.client_stage, static_cast<atomic_val_t>(ClientStage::idle));
            atomic_set(&client.client_busy_value, 0);
            atomic_set(&client.client_subscribed, 0);
            atomic_set(&client.client_subscription_value, 0);
            atomic_set(&client.client_last_att_error, 0);
            atomic_set(&client.client_operation_bearer,
                       static_cast<atomic_val_t>(BLEGattBearer::unenhanced));
            atomic_set(&client.client_signed_write, 0);
            atomic_set(&client.descriptor_boundary_ready, 0);
            client.descriptor_end_handle = 0U;
            client.read_length = 0U;
            client.read_multiple = false;
            clearClientOperationToken(client);
            clearClientSubscriptionToken(client);
            clearClientCacheState(client);
            return had_handles;
        }

    } // namespace

    BLEConnectionHandle handleForConnection(struct bt_conn *connection) noexcept
    {
        return nucode::ble::internal::handleForActiveConnection(connection);
    }

    SessionState &sessionState() noexcept
    {
        return state;
    }

    k_msgq &gattEventQueue() noexcept
    {
        return gatt_event_queue;
    }

    bool queueGattEvent(const GattEventRecord &record) noexcept
    {
        const bool active = record.owner_kind == GattEventRecord::Owner::server
                                ? nucode::ble::internal::hasActiveConnection()
                                : findClientState(record.connection) != nullptr;
        const bool invalidation = record.owner_kind == GattEventRecord::Owner::client &&
                                  record.client_event ==
                                      BLEGattClientEvent::handles_invalidated;
        if (!active && !invalidation)
        {
            return false;
        }
        if (k_msgq_put(&gattEventQueue(), &record, K_NO_WAIT) == 0)
        {
            return true;
        }
        nucode::ble::internal::recordError(BLEError::event_overflow, -ENOBUFS, true);
        return false;
    }

    void queueServerEvent(BLECharacteristic &characteristic, BLECharacteristicEvent event,
                          const void *data, std::size_t length, std::size_t offset,
                          bool without_response, int status, struct bt_conn *connection,
                          BLEDescriptor *descriptor,
                          BLEGattAuthorizationOperation authorization_operation) noexcept
    {
        if (length > maximum_event_payload_length)
        {
            nucode::ble::internal::recordError(BLEError::value_overflow, -EMSGSIZE, true);
            return;
        }
        GattEventRecord record = {};
        record.owner_kind = GattEventRecord::Owner::server;
        record.generation =
            static_cast<std::uint32_t>(atomic_get(&sessionState().gatt_session_generation));
        record.connection = handleForConnection(connection);
        record.characteristic = &characteristic;
        record.descriptor = descriptor;
        record.server_event = event;
        record.authorization_operation = authorization_operation;
        record.length = static_cast<std::uint16_t>(length);
        record.offset = static_cast<std::uint16_t>(offset);
        record.without_response = without_response;
        record.persist_signing =
            event == BLECharacteristicEvent::written && without_response &&
            connection != nullptr && bt_conn_get_security(connection) == BT_SECURITY_L1 &&
            hasProperty(GattAccess::properties(characteristic),
                        BLEProperty::authenticated_signed_write);
        record.status = status;
        if (data != nullptr && length != 0U)
        {
            ::memcpy(record.data, data, length);
        }
        if (!queueGattEvent(record) && record.persist_signing && connection != nullptr)
        {
            /* queue 포화 시에도 수신 counter를 되돌릴 수 없도록 즉시 저장합니다. */
            const int persist_result = nucode_ble_signing_persist(connection);
            if (persist_result < 0)
            {
                nucode::ble::internal::recordError(BLEError::driver_error,
                                                   persist_result, true);
                static_cast<void>(bt_conn_disconnect(
                    connection, BT_HCI_ERR_REMOTE_USER_TERM_CONN));
            }
        }
    }

    bool queueClientEvent(ClientState &client, BLEGattClientEvent event, const void *data,
                          std::size_t length, std::size_t offset, int status,
                          std::uint8_t att_error) noexcept
    {
        if (length > maximum_event_payload_length)
        {
            nucode::ble::internal::recordError(BLEError::value_overflow, -EMSGSIZE, true);
            return false;
        }
        GattEventRecord record = {};
        record.owner_kind = GattEventRecord::Owner::client;
        record.generation =
            static_cast<std::uint32_t>(atomic_get(&sessionState().gatt_session_generation));
        record.connection = client.connection_handle;
        record.client_event = event;
        record.length = static_cast<std::uint16_t>(length);
        record.offset = static_cast<std::uint16_t>(offset);
        record.att_error = att_error;
        record.bearer = static_cast<BLEGattBearer>(
            atomic_get(&client.client_operation_bearer));
        record.status = status;
        if (data != nullptr && length != 0U)
        {
            ::memcpy(record.data, data, length);
        }
        return queueGattEvent(record);
    }

    void queueInvalidatedEvent(BLEConnectionHandle connection) noexcept
    {
        GattEventRecord record = {};
        record.owner_kind = GattEventRecord::Owner::client;
        record.generation =
            static_cast<std::uint32_t>(atomic_get(&sessionState().gatt_session_generation));
        record.connection = connection;
        record.client_event = BLEGattClientEvent::handles_invalidated;
        static_cast<void>(queueGattEvent(record));
    }

    bool currentGattConnection(ClientState &client, struct bt_conn *connection) noexcept
    {
        if (connection == nullptr)
        {
            return false;
        }
        BLEConnectionHandle handle;
        k_spinlock_key_t key = k_spin_lock(&client.client_token_lock);
        const bool token_matches = client.gatt_connection == connection &&
                                   client.connection_handle.valid();
        handle = client.connection_handle;
        k_spin_unlock(&client.client_token_lock, key);
        if (!token_matches)
        {
            return false;
        }
        struct bt_conn *current = nucode::ble::internal::referenceConnection(handle);
        if (current == nullptr)
        {
            return false;
        }
        const bool matches = current == connection;
        bt_conn_unref(current);
        return matches;
    }

} // namespace nucode::ble::internal::gatt

namespace nucode::ble::internal
{
    using namespace gatt;

    void pollGatt() noexcept
    {
        GattEventRecord record = {};
        while (k_msgq_get(&gattEventQueue(), &record, K_NO_WAIT) == 0)
        {
            if (record.generation !=
                static_cast<std::uint32_t>(atomic_get(&sessionState().gatt_session_generation)))
            {
                continue;
            }
            if (record.owner_kind == GattEventRecord::Owner::server &&
                record.characteristic != nullptr)
            {
                if (record.connection.valid())
                {
                    struct bt_conn *connection = referenceConnection(record.connection);
                    if (connection == nullptr)
                    {
                        continue;
                    }
                    if (record.persist_signing)
                    {
                        const int persist_result = nucode_ble_signing_persist(connection);
                        if (persist_result < 0)
                        {
                            record.status = persist_result;
                            recordError(BLEError::driver_error, persist_result, true);
                            static_cast<void>(bt_conn_disconnect(
                                connection, BT_HCI_ERR_REMOTE_USER_TERM_CONN));
                        }
                    }
                    bt_conn_unref(connection);
                }
                const BLECharacteristicEventInfo event = {
                    .event = record.server_event,
                    .connection = record.connection,
                    .data = record.length == 0U ? nullptr : record.data,
                    .length = record.length,
                    .offset = record.offset,
                    .without_response = record.without_response,
                    .status = record.status,
                    .descriptor = record.descriptor,
                    .authorization_operation = record.authorization_operation,
                };
                GattAccess::dispatch(*record.characteristic, event);
                continue;
            }
            if (record.owner_kind != GattEventRecord::Owner::client)
            {
                continue;
            }
            const bool invalidation =
                record.client_event == BLEGattClientEvent::handles_invalidated;
            if (!invalidation && findClientState(record.connection) == nullptr)
            {
                continue;
            }
            if (record.client_event == BLEGattClientEvent::signed_write_complete)
            {
                ClientState *client = findClientState(record.connection);
                struct bt_conn *connection = referenceConnection(record.connection);
                int persist_result = -ENOTCONN;
                if (client != nullptr && connection != nullptr &&
                    currentGattConnection(*client, connection))
                {
                    persist_result = nucode_ble_signing_persist(connection);
                }
                if (connection != nullptr && persist_result < 0)
                {
                    static_cast<void>(bt_conn_disconnect(
                        connection, BT_HCI_ERR_REMOTE_USER_TERM_CONN));
                }
                if (connection != nullptr)
                {
                    bt_conn_unref(connection);
                }
                if (client != nullptr && persist_result >= 0)
                {
                    clearClientOperationToken(*client);
                    atomic_set(&client->client_busy_value, 0);
                    atomic_set(&client->client_signed_write, 0);
                    atomic_set(&client->client_operation_bearer,
                               static_cast<atomic_val_t>(BLEGattBearer::unenhanced));
                }
                if (persist_result < 0)
                {
                    /* disconnect 전까지 busy를 유지해 counter rollback 가능성을 닫습니다. */
                    record.client_event = BLEGattClientEvent::operation_failed;
                    record.status = persist_result;
                    recordError(BLEError::driver_error, persist_result, true);
                }
            }
            ClientCallbacks &callbacks = clientCallbacks();
            if (callbacks.legacy != nullptr)
            {
                callbacks.legacy(record.client_event,
                                 record.length == 0U ? nullptr : record.data,
                                 record.length, callbacks.legacy_context);
            }
            if (record.generation !=
                static_cast<std::uint32_t>(atomic_get(&sessionState().gatt_session_generation)))
            {
                continue;
            }
            if (callbacks.detailed != nullptr)
            {
                const BLEGattClientEventInfo information = {
                    .event = record.client_event,
                    .connection = record.connection,
                    .data = record.length == 0U ? nullptr : record.data,
                    .length = record.length,
                    .offset = record.offset,
                    .att_error = record.att_error,
                    .status = record.status,
                    .bearer = record.bearer,
                };
                callbacks.detailed(information, callbacks.detailed_context);
            }
        }
        progressClientDiscovery();
        progressGattCache();
    }

    void gattConnected(struct bt_conn *connection, BLEConnectionHandle handle) noexcept
    {
        if (connection == nullptr || !handle.valid())
        {
            return;
        }
        ClientState *available = nullptr;
        for (ClientState &client : clientStates())
        {
            k_spinlock_key_t key = k_spin_lock(&client.client_token_lock);
            const bool same = client.gatt_connection == connection &&
                              client.connection_handle == handle;
            const bool empty = client.gatt_connection == nullptr;
            k_spin_unlock(&client.client_token_lock, key);
            if (same)
            {
                return;
            }
            if (empty && available == nullptr)
            {
                available = &client;
            }
        }
        if (available == nullptr)
        {
            recordError(BLEError::schema_full, -ENOSPC, true);
            return;
        }
        static_cast<void>(clearClientState(*available));
        k_spinlock_key_t key = k_spin_lock(&available->client_token_lock);
        available->connection_handle = handle;
        available->gatt_connection = connection;
        k_spin_unlock(&available->client_token_lock, key);
    }

    void gattDisconnected(struct bt_conn *connection, BLEConnectionHandle handle) noexcept
    {
        clearServerTransaction(connection);
        ClientState *matched = nullptr;
        for (ClientState &client : clientStates())
        {
            k_spinlock_key_t key = k_spin_lock(&client.client_token_lock);
            const bool matches = client.gatt_connection == connection &&
                                 client.connection_handle == handle;
            if (matches)
            {
                client.gatt_connection = nullptr;
            }
            k_spin_unlock(&client.client_token_lock, key);
            if (matches)
            {
                matched = &client;
                break;
            }
        }
        if (matched == nullptr)
        {
            return;
        }
        const bool had_handles = clearClientState(*matched);
        k_spinlock_key_t key = k_spin_lock(&matched->client_token_lock);
        matched->connection_handle = BLEConnectionHandle{};
        k_spin_unlock(&matched->client_token_lock, key);
        if (had_handles)
        {
            queueInvalidatedEvent(handle);
        }
    }

    void gattEnded() noexcept
    {
        atomic_inc(&sessionState().gatt_session_generation);
        k_msgq_purge(&gattEventQueue());
        clearServerTransactions();
        for (ClientState &client : clientStates())
        {
            static_cast<void>(clearClientState(client));
            k_spinlock_key_t key = k_spin_lock(&client.client_token_lock);
            client.connection_handle = BLEConnectionHandle{};
            client.gatt_connection = nullptr;
            k_spin_unlock(&client.client_token_lock, key);
        }
    }

} // namespace nucode::ble::internal
#endif
