/** @file @brief GATT session·queue·deferred callback 수명주기입니다.
 * SPDX-License-Identifier: MIT
 */
#if !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE)
#include "internal/gatt/GattInternal.h"
namespace nucode::ble::internal::gatt
{
    namespace
    {
        SessionState state{};
    }
    SessionState &sessionState() noexcept
    {
        return state;
    }
    namespace
    {
        K_MSGQ_DEFINE(gatt_event_queue, sizeof(GattEventRecord),
                      CONFIG_NUCODE_BLE_GATT_EVENT_QUEUE_SIZE, alignof(GattEventRecord));
    }
    k_msgq &gattEventQueue() noexcept
    {
        return gatt_event_queue;
    }
    /** @brief GATT callback record를 bounded queue에 복사합니다. */
    bool queueGattEvent(const GattEventRecord &record) noexcept
    {
        if (atomic_get(&sessionState().gatt_link_active) == 0 &&
            !(record.owner_kind == GattEventRecord::Owner::client &&
              record.client_event == BLEGattClientEvent::handles_invalidated))
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

    /** @brief server event와 payload chunk를 main-thread queue로 복사합니다. */
    void queueServerEvent(BLECharacteristic &characteristic, BLECharacteristicEvent event,
                          const void *data, std::size_t length, std::size_t offset,
                          bool without_response, int status) noexcept
    {
        if (length > maximum_value_length)
        {
            nucode::ble::internal::recordError(BLEError::value_overflow, -EMSGSIZE, true);
            return;
        }
        GattEventRecord record = {};
        record.owner_kind = GattEventRecord::Owner::server;
        record.generation =
            static_cast<std::uint32_t>(atomic_get(&sessionState().gatt_session_generation));
        record.characteristic = &characteristic;
        record.server_event = event;
        record.length = static_cast<std::uint16_t>(length);
        record.offset = static_cast<std::uint16_t>(offset);
        record.without_response = without_response;
        record.status = status;
        if (data != nullptr && length != 0U)
        {
            ::memcpy(record.data, data, length);
        }
        static_cast<void>(queueGattEvent(record));
    }

    /** @brief client event와 payload를 main-thread queue로 복사합니다. */
    void queueClientEvent(BLEGattClientEvent event, const void *data, std::size_t length,
                          int status) noexcept
    {
        if (length > maximum_value_length)
        {
            nucode::ble::internal::recordError(BLEError::value_overflow, -EMSGSIZE, true);
            return;
        }
        GattEventRecord record = {};
        record.owner_kind = GattEventRecord::Owner::client;
        record.generation =
            static_cast<std::uint32_t>(atomic_get(&sessionState().gatt_session_generation));
        record.client_event = event;
        record.length = static_cast<std::uint16_t>(length);
        record.status = status;
        if (data != nullptr && length != 0U)
        {
            ::memcpy(record.data, data, length);
        }
        static_cast<void>(queueGattEvent(record));
    }

    /** @brief callback connection이 현재 generic link인지 reference로 검사합니다. */
    bool currentGattConnection(struct bt_conn *connection) noexcept
    {
        if (connection == nullptr || atomic_get(&sessionState().gatt_link_active) == 0)
        {
            return false;
        }
        k_spinlock_key_t key = k_spin_lock(&clientState().client_token_lock);
        const bool token_matches = clientState().gatt_connection == connection &&
                                   clientState().gatt_connection_generation != 0U;
        k_spin_unlock(&clientState().client_token_lock, key);
        if (!token_matches)
        {
            return false;
        }
        struct bt_conn *current = nucode::ble::internal::referenceConnection();
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
                const BLECharacteristicEventInfo event = {
                    .event = record.server_event,
                    .data = record.length == 0U ? nullptr : record.data,
                    .length = record.length,
                    .offset = record.offset,
                    .without_response = record.without_response,
                    .status = record.status,
                };
                GattAccess::dispatch(*record.characteristic, event);
            }
            else if (record.owner_kind == GattEventRecord::Owner::client &&
                     clientState().client_callback != nullptr)
            {
                clientState().client_callback(record.client_event,
                                              record.length == 0U ? nullptr : record.data,
                                              record.length, clientState().client_context);
            }
        }
        progressClientDiscovery();
    }

    void gattConnected(struct bt_conn *connection, std::uint32_t generation) noexcept
    {
        k_spinlock_key_t key = k_spin_lock(&clientState().client_token_lock);
        clientState().gatt_connection = connection;
        clientState().gatt_connection_generation = generation;
        k_spin_unlock(&clientState().client_token_lock, key);
        atomic_set(&sessionState().gatt_link_active, 1);
    }

    void gattDisconnected(struct bt_conn *connection, std::uint32_t generation) noexcept
    {
        k_spinlock_key_t token_key = k_spin_lock(&clientState().client_token_lock);
        const bool matches = clientState().gatt_connection == connection &&
                             clientState().gatt_connection_generation == generation;
        if (matches)
        {
            clientState().gatt_connection = nullptr;
            clientState().gatt_connection_generation = 0U;
        }
        k_spin_unlock(&clientState().client_token_lock, token_key);
        if (!matches)
        {
            return;
        }
        atomic_set(&clientState().client_stage, static_cast<atomic_val_t>(ClientStage::idle));
        atomic_set(&sessionState().gatt_link_active, 0);
        atomic_inc(&sessionState().gatt_session_generation);
        k_msgq_purge(&gattEventQueue());
        k_spinlock_key_t key = k_spin_lock(&clientState().client_state_lock);
        const bool had_handles = clientState().remote_service.valid() ||
                                 clientState().remote_characteristic.valid() ||
                                 atomic_get(&clientState().client_subscribed) != 0 ||
                                 atomic_get(&clientState().client_busy_value) != 0;
        GattAccess::clear(clientState().remote_service);
        GattAccess::clear(clientState().remote_characteristic);
        k_spin_unlock(&clientState().client_state_lock, key);
        atomic_set(&clientState().client_busy_value, 0);
        atomic_set(&clientState().client_subscribed, 0);
        atomic_set(&clientState().client_subscription_value, 0);
        clearClientOperationToken();
        clearClientSubscriptionToken();
        if (had_handles)
        {
            queueClientEvent(BLEGattClientEvent::handles_invalidated);
        }
    }

    void gattEnded() noexcept
    {
        atomic_set(&clientState().client_stage, static_cast<atomic_val_t>(ClientStage::idle));
        atomic_set(&sessionState().gatt_link_active, 0);
        atomic_inc(&sessionState().gatt_session_generation);
        k_msgq_purge(&gattEventQueue());
        k_spinlock_key_t key = k_spin_lock(&clientState().client_state_lock);
        GattAccess::clear(clientState().remote_service);
        GattAccess::clear(clientState().remote_characteristic);
        k_spin_unlock(&clientState().client_state_lock, key);
        atomic_set(&clientState().client_busy_value, 0);
        atomic_set(&clientState().client_subscribed, 0);
        atomic_set(&clientState().client_subscription_value, 0);
        clearClientOperationToken();
        clearClientSubscriptionToken();
        k_spinlock_key_t token_key = k_spin_lock(&clientState().client_token_lock);
        clientState().gatt_connection = nullptr;
        clientState().gatt_connection_generation = 0U;
        k_spin_unlock(&clientState().client_token_lock, token_key);
    }

} // namespace nucode::ble::internal
#endif
