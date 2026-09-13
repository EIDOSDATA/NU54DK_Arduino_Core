/** @file @brief GATT discovery·link별 client operation·subscription 수명주기입니다.
 * SPDX-License-Identifier: MIT
 */
#if !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE)
#include "GattInternal.h"

namespace nucode::ble::internal::gatt
{
    namespace
    {
        ClientStates states{};
        ClientCallbacks callbacks{};

        /** @brief 기존 무인자 API가 사용할 central 우선 handle을 반환합니다. */
        BLEConnectionHandle legacyConnectionHandle() noexcept
        {
            ClientState *state = legacyClientState();
            return state == nullptr ? BLEConnectionHandle{} : state->connection_handle;
        }
    } // namespace

    ClientStates &clientStates() noexcept
    {
        return states;
    }

    ClientCallbacks &clientCallbacks() noexcept
    {
        return callbacks;
    }

    ClientState *findClientState(BLEConnectionHandle connection) noexcept
    {
        if (!connection.valid())
        {
            return nullptr;
        }
        for (ClientState &state : clientStates())
        {
            k_spinlock_key_t key = k_spin_lock(&state.client_token_lock);
            const bool matches = state.connection_handle == connection &&
                                 state.gatt_connection != nullptr;
            k_spin_unlock(&state.client_token_lock, key);
            if (matches)
            {
                return &state;
            }
        }
        return nullptr;
    }

    ClientState *legacyClientState() noexcept
    {
        ClientState *state = findClientState(BLEConnection.handle(BLELinkRole::central));
        if (state == nullptr)
        {
            state = findClientState(BLEConnection.handle(BLELinkRole::peripheral));
        }
        return state;
    }

    ClientState *findDiscoveryState(struct bt_gatt_discover_params *parameters) noexcept
    {
        if (parameters == nullptr)
        {
            return nullptr;
        }
        for (ClientState &state : clientStates())
        {
            if (&state.discovery_parameters == parameters)
            {
                return &state;
            }
        }
        return nullptr;
    }

    ClientState *findReadState(struct bt_gatt_read_params *parameters) noexcept
    {
        if (parameters == nullptr)
        {
            return nullptr;
        }
        for (ClientState &state : clientStates())
        {
            if (&state.read_parameters == parameters)
            {
                return &state;
            }
        }
        return nullptr;
    }

    ClientState *findWriteState(struct bt_gatt_write_params *parameters) noexcept
    {
        if (parameters == nullptr)
        {
            return nullptr;
        }
        for (ClientState &state : clientStates())
        {
            if (&state.write_parameters == parameters)
            {
                return &state;
            }
        }
        return nullptr;
    }

    ClientState *findSubscriptionState(struct bt_gatt_subscribe_params *parameters) noexcept
    {
        if (parameters == nullptr)
        {
            return nullptr;
        }
        for (ClientState &state : clientStates())
        {
            if (&state.subscribe_parameters == parameters)
            {
                return &state;
            }
        }
        return nullptr;
    }

    void copyRemoteHandles(ClientState &state, BLERemoteService &service,
                           BLERemoteCharacteristic &characteristic) noexcept
    {
        k_spinlock_key_t key = k_spin_lock(&state.client_state_lock);
        service = state.remote_service;
        characteristic = state.remote_characteristic;
        k_spin_unlock(&state.client_state_lock, key);
    }

    BLERemoteService copyRemoteService(ClientState &state) noexcept
    {
        k_spinlock_key_t key = k_spin_lock(&state.client_state_lock);
        const BLERemoteService service = state.remote_service;
        k_spin_unlock(&state.client_state_lock, key);
        return service;
    }

    BLERemoteCharacteristic copyRemoteCharacteristic(ClientState &state) noexcept
    {
        k_spinlock_key_t key = k_spin_lock(&state.client_state_lock);
        const BLERemoteCharacteristic characteristic = state.remote_characteristic;
        k_spin_unlock(&state.client_state_lock, key);
        return characteristic;
    }

    void setClientOperationToken(ClientState &state, struct bt_conn *connection) noexcept
    {
        k_spinlock_key_t key = k_spin_lock(&state.client_token_lock);
        state.client_operation_connection = connection;
        k_spin_unlock(&state.client_token_lock, key);
    }

    bool validClientOperation(ClientState &state, struct bt_conn *connection) noexcept
    {
        k_spinlock_key_t key = k_spin_lock(&state.client_token_lock);
        const bool matches = state.client_operation_connection == connection;
        k_spin_unlock(&state.client_token_lock, key);
        return matches && currentGattConnection(state, connection);
    }

    void clearClientOperationToken(ClientState &state) noexcept
    {
        k_spinlock_key_t key = k_spin_lock(&state.client_token_lock);
        state.client_operation_connection = nullptr;
        k_spin_unlock(&state.client_token_lock, key);
    }

    void setClientSubscriptionToken(ClientState &state, struct bt_conn *connection) noexcept
    {
        k_spinlock_key_t key = k_spin_lock(&state.client_token_lock);
        state.client_subscription_connection = connection;
        k_spin_unlock(&state.client_token_lock, key);
    }

    bool validClientSubscription(ClientState &state, struct bt_conn *connection) noexcept
    {
        k_spinlock_key_t key = k_spin_lock(&state.client_token_lock);
        const bool matches = state.client_subscription_connection == connection;
        k_spin_unlock(&state.client_token_lock, key);
        return matches && currentGattConnection(state, connection);
    }

    void clearClientSubscriptionToken(ClientState &state) noexcept
    {
        k_spinlock_key_t key = k_spin_lock(&state.client_token_lock);
        state.client_subscription_connection = nullptr;
        k_spin_unlock(&state.client_token_lock, key);
    }

    void failClient(ClientState &state, int driver_error, std::uint8_t att_error) noexcept
    {
        BLEError error = BLEError::driver_error;
        if (driver_error == -ENOENT)
        {
            error = BLEError::not_found;
        }
        else if (driver_error == -EMSGSIZE)
        {
            error = BLEError::value_overflow;
        }
        else if (driver_error == -ENOTCONN)
        {
            error = BLEError::not_connected;
        }
        clearClientOperationToken(state);
        state.read_length = 0U;
        atomic_set(&state.client_last_att_error, att_error);
        atomic_set(&state.client_busy_value, 0);
        if (atomic_get(&state.client_stage) != static_cast<atomic_val_t>(ClientStage::ready))
        {
            atomic_set(&state.client_stage, static_cast<atomic_val_t>(ClientStage::idle));
        }
        nucode::ble::internal::recordError(error, driver_error, true);
        queueClientEvent(state, BLEGattClientEvent::operation_failed, nullptr, 0U, 0U,
                         att_error != 0U ? -static_cast<int>(att_error) : driver_error, att_error);
    }

    std::uint8_t serviceDiscovered(struct bt_conn *connection, const struct bt_gatt_attr *attribute,
                                   struct bt_gatt_discover_params *parameters) noexcept
    {
        ClientState *state = findDiscoveryState(parameters);
        if (state == nullptr || !validClientOperation(*state, connection))
        {
            return BT_GATT_ITER_STOP;
        }
        if (attribute == nullptr)
        {
            failClient(*state, -ENOENT);
            return BT_GATT_ITER_STOP;
        }
        const auto *value = static_cast<const struct bt_gatt_service_val *>(attribute->user_data);
        if (value == nullptr || value->end_handle <= attribute->handle)
        {
            failClient(*state, -EINVAL);
            return BT_GATT_ITER_STOP;
        }
        k_spinlock_key_t key = k_spin_lock(&state->client_state_lock);
        GattAccess::set(state->remote_service, state->target_service_uuid, attribute->handle,
                        value->end_handle);
        k_spin_unlock(&state->client_state_lock, key);
        atomic_set(&state->client_stage, static_cast<atomic_val_t>(ClientStage::service_found));
        return BT_GATT_ITER_STOP;
    }

    std::uint8_t characteristicDiscovered(struct bt_conn *connection,
                                          const struct bt_gatt_attr *attribute,
                                          struct bt_gatt_discover_params *parameters) noexcept
    {
        ClientState *state = findDiscoveryState(parameters);
        if (state == nullptr || !validClientOperation(*state, connection))
        {
            return BT_GATT_ITER_STOP;
        }
        if (attribute == nullptr)
        {
            failClient(*state, -ENOENT);
            return BT_GATT_ITER_STOP;
        }
        const auto *value = static_cast<const struct bt_gatt_chrc *>(attribute->user_data);
        if (value == nullptr || value->value_handle == 0U)
        {
            failClient(*state, -EINVAL);
            return BT_GATT_ITER_STOP;
        }
        k_spinlock_key_t key = k_spin_lock(&state->client_state_lock);
        GattAccess::set(state->remote_characteristic, state->target_characteristic_uuid,
                        attribute->handle, value->value_handle,
                        publicProperties(value->properties));
        k_spin_unlock(&state->client_state_lock, key);
        atomic_set(&state->client_stage,
                   static_cast<atomic_val_t>(ClientStage::characteristic_found));
        return BT_GATT_ITER_STOP;
    }

    std::uint8_t cccDiscovered(struct bt_conn *connection, const struct bt_gatt_attr *attribute,
                               struct bt_gatt_discover_params *parameters) noexcept
    {
        ClientState *state = findDiscoveryState(parameters);
        if (state == nullptr || !validClientOperation(*state, connection))
        {
            return BT_GATT_ITER_STOP;
        }
        if (attribute == nullptr)
        {
            failClient(*state, -ENOENT);
            return BT_GATT_ITER_STOP;
        }
        k_spinlock_key_t key = k_spin_lock(&state->client_state_lock);
        GattAccess::setCcc(state->remote_characteristic, attribute->handle);
        k_spin_unlock(&state->client_state_lock, key);
        atomic_set(&state->client_stage, static_cast<atomic_val_t>(ClientStage::ccc_found));
        return BT_GATT_ITER_STOP;
    }

    std::uint8_t clientReadCompleted(struct bt_conn *connection, std::uint8_t error,
                                     struct bt_gatt_read_params *parameters, const void *data,
                                     std::uint16_t length) noexcept
    {
        ClientState *state = findReadState(parameters);
        if (state == nullptr || !validClientOperation(*state, connection))
        {
            return BT_GATT_ITER_STOP;
        }
        if (error != 0U)
        {
            failClient(*state, -EIO, error);
            return BT_GATT_ITER_STOP;
        }
        if (data != nullptr)
        {
            if (length == 0U || state->read_length + length > maximum_value_length)
            {
                failClient(*state, -EMSGSIZE);
                return BT_GATT_ITER_STOP;
            }
            ::memcpy(state->read_data + state->read_length, data, length);
            state->read_length += length;
            return BT_GATT_ITER_CONTINUE;
        }
        const std::size_t completed_length = state->read_length;
        state->read_length = 0U;
        clearClientOperationToken(*state);
        atomic_set(&state->client_busy_value, 0);
        queueClientEvent(*state, BLEGattClientEvent::read_complete, state->read_data,
                         completed_length);
        return BT_GATT_ITER_STOP;
    }

    void clientWriteCompleted(struct bt_conn *connection, std::uint8_t error,
                              struct bt_gatt_write_params *parameters) noexcept
    {
        ClientState *state = findWriteState(parameters);
        if (state == nullptr || !validClientOperation(*state, connection))
        {
            return;
        }
        if (error != 0U)
        {
            failClient(*state, -EIO, error);
            return;
        }
        clearClientOperationToken(*state);
        atomic_set(&state->client_busy_value, 0);
        queueClientEvent(*state, BLEGattClientEvent::write_complete);
    }

    void clientWriteCommandCompleted(struct bt_conn *connection, void *user_data) noexcept
    {
        auto *state = static_cast<ClientState *>(user_data);
        if (state == nullptr || !validClientOperation(*state, connection))
        {
            return;
        }
        clearClientOperationToken(*state);
        atomic_set(&state->client_busy_value, 0);
        queueClientEvent(*state, BLEGattClientEvent::write_without_response_complete);
    }

    void clientSubscribeCompleted(struct bt_conn *connection, std::uint8_t error,
                                  struct bt_gatt_subscribe_params *parameters) noexcept
    {
        ClientState *state = findSubscriptionState(parameters);
        if (state == nullptr || !validClientSubscription(*state, connection))
        {
            return;
        }
        if (error != 0U)
        {
            atomic_set(&state->client_subscribed, 0);
            atomic_set(&state->client_subscription_value, 0);
            clearClientSubscriptionToken(*state);
            failClient(*state, -EIO, error);
            return;
        }
        if (parameters->value == 0U)
        {
            atomic_set(&state->client_subscribed, 0);
            atomic_set(&state->client_busy_value, 0);
            return;
        }
        atomic_set(&state->client_subscribed, 1);
        atomic_set(&state->client_subscription_value, parameters->value);
        atomic_set(&state->client_busy_value, 0);
        queueClientEvent(*state, BLEGattClientEvent::subscribed);
    }

    std::uint8_t clientNotification(struct bt_conn *connection,
                                    struct bt_gatt_subscribe_params *parameters, const void *data,
                                    std::uint16_t length) noexcept
    {
        ClientState *state = findSubscriptionState(parameters);
        if (state == nullptr || !validClientSubscription(*state, connection))
        {
            return BT_GATT_ITER_STOP;
        }
        if (data == nullptr)
        {
            atomic_set(&state->client_subscribed, 0);
            atomic_set(&state->client_subscription_value, 0);
            clearClientSubscriptionToken(*state);
            atomic_set(&state->client_busy_value, 0);
            queueClientEvent(*state, BLEGattClientEvent::unsubscribed);
            return BT_GATT_ITER_STOP;
        }
        queueClientEvent(*state,
                         atomic_get(&state->client_subscription_value) == BT_GATT_CCC_INDICATE
                             ? BLEGattClientEvent::indication_received
                             : BLEGattClientEvent::notification_received,
                         data, length);
        return BT_GATT_ITER_CONTINUE;
    }

    void continueCharacteristicDiscovery(ClientState &state) noexcept
    {
        struct bt_conn *connection = nucode::ble::internal::referenceConnection(
            state.connection_handle);
        if (connection == nullptr)
        {
            failClient(state, -ENOTCONN);
            return;
        }
        if (!validClientOperation(state, connection))
        {
            bt_conn_unref(connection);
            failClient(state, -ENOTCONN);
            return;
        }
        const BLERemoteService service = copyRemoteService(state);
        ::memset(&state.discovery_parameters, 0, sizeof(state.discovery_parameters));
        state.discovery_parameters.uuid =
            state.target_characteristic_zephyr_uuid.assign(state.target_characteristic_uuid);
        state.discovery_parameters.func = characteristicDiscovered;
        state.discovery_parameters.start_handle = service.startHandle() + 1U;
        state.discovery_parameters.end_handle = service.endHandle();
        state.discovery_parameters.type = BT_GATT_DISCOVER_CHARACTERISTIC;
        atomic_set(&state.client_stage,
                   static_cast<atomic_val_t>(ClientStage::discovering_characteristic));
        const int result = bt_gatt_discover(connection, &state.discovery_parameters);
        bt_conn_unref(connection);
        if (result < 0)
        {
            failClient(state, result);
        }
    }

    void continueCccDiscovery(ClientState &state) noexcept
    {
        BLERemoteService service;
        BLERemoteCharacteristic characteristic;
        copyRemoteHandles(state, service, characteristic);
        const BLEProperty properties = characteristic.properties();
        if (!hasProperty(properties, BLEProperty::notify) &&
            !hasProperty(properties, BLEProperty::indicate))
        {
            atomic_set(&state.client_stage, static_cast<atomic_val_t>(ClientStage::ready));
            clearClientOperationToken(state);
            atomic_set(&state.client_busy_value, 0);
            queueClientEvent(state, BLEGattClientEvent::discovery_complete);
            return;
        }

        struct bt_conn *connection = nucode::ble::internal::referenceConnection(
            state.connection_handle);
        if (connection == nullptr)
        {
            failClient(state, -ENOTCONN);
            return;
        }
        if (!validClientOperation(state, connection))
        {
            bt_conn_unref(connection);
            failClient(state, -ENOTCONN);
            return;
        }
        if (characteristic.valueHandle() >= service.endHandle())
        {
            bt_conn_unref(connection);
            failClient(state, -ENOENT);
            return;
        }
        ::memset(&state.discovery_parameters, 0, sizeof(state.discovery_parameters));
        state.discovery_parameters.uuid = BT_UUID_GATT_CCC;
        state.discovery_parameters.func = cccDiscovered;
        state.discovery_parameters.start_handle = characteristic.valueHandle() + 1U;
        state.discovery_parameters.end_handle = service.endHandle();
        state.discovery_parameters.type = BT_GATT_DISCOVER_DESCRIPTOR;
        atomic_set(&state.client_stage,
                   static_cast<atomic_val_t>(ClientStage::discovering_ccc));
        const int result = bt_gatt_discover(connection, &state.discovery_parameters);
        bt_conn_unref(connection);
        if (result < 0)
        {
            failClient(state, result);
        }
    }

    void progressClientDiscovery() noexcept
    {
        for (ClientState &state : clientStates())
        {
            if (atomic_cas(&state.client_stage,
                           static_cast<atomic_val_t>(ClientStage::service_found),
                           static_cast<atomic_val_t>(ClientStage::discovering_characteristic)))
            {
                continueCharacteristicDiscovery(state);
                continue;
            }
            if (atomic_cas(&state.client_stage,
                           static_cast<atomic_val_t>(ClientStage::characteristic_found),
                           static_cast<atomic_val_t>(ClientStage::discovering_ccc)))
            {
                continueCccDiscovery(state);
                continue;
            }
            if (atomic_cas(&state.client_stage,
                           static_cast<atomic_val_t>(ClientStage::ccc_found),
                           static_cast<atomic_val_t>(ClientStage::ready)))
            {
                clearClientOperationToken(state);
                atomic_set(&state.client_busy_value, 0);
                queueClientEvent(state, BLEGattClientEvent::discovery_complete);
            }
        }
    }

    bool validWriteCommandPayload(ClientState &state, std::size_t length) noexcept
    {
        struct bt_conn *connection = nucode::ble::internal::referenceConnection(
            state.connection_handle);
        if (connection == nullptr)
        {
            nucode::ble::internal::recordError(BLEError::not_connected, -ENOTCONN, true);
            return false;
        }
        const std::size_t mtu = bt_gatt_get_mtu(connection);
        bt_conn_unref(connection);
        if (length > maximum_value_length || mtu < 3U || length > mtu - 3U)
        {
            nucode::ble::internal::recordError(BLEError::value_overflow, -EMSGSIZE, true);
            return false;
        }
        return true;
    }

    bool startSubscription(ClientState &state, std::uint16_t value) noexcept
    {
        BLERemoteService service;
        BLERemoteCharacteristic characteristic;
        copyRemoteHandles(state, service, characteristic);
        if (atomic_get(&state.client_stage) != static_cast<atomic_val_t>(ClientStage::ready) ||
            !characteristic.valid() || characteristic.cccHandle() == 0U)
        {
            nucode::ble::internal::recordError(BLEError::wrong_state, -EPERM, true);
            return false;
        }
        if (!atomic_cas(&state.client_busy_value, 0, 1))
        {
            nucode::ble::internal::recordError(BLEError::busy, -EBUSY, true);
            return false;
        }
        if (atomic_get(&state.client_subscribed) != 0)
        {
            atomic_set(&state.client_busy_value, 0);
            nucode::ble::internal::recordError(BLEError::already_started, -EALREADY, true);
            return false;
        }
        struct bt_conn *connection = nucode::ble::internal::referenceConnection(
            state.connection_handle);
        if (connection == nullptr)
        {
            atomic_set(&state.client_busy_value, 0);
            nucode::ble::internal::recordError(BLEError::not_connected, -ENOTCONN, true);
            return false;
        }
        ::memset(&state.subscribe_parameters, 0, sizeof(state.subscribe_parameters));
        state.subscribe_parameters.notify = clientNotification;
        state.subscribe_parameters.subscribe = clientSubscribeCompleted;
        state.subscribe_parameters.value_handle = characteristic.valueHandle();
        state.subscribe_parameters.ccc_handle = characteristic.cccHandle();
        state.subscribe_parameters.value = value;
        atomic_set_bit(state.subscribe_parameters.flags, BT_GATT_SUBSCRIBE_FLAG_VOLATILE);
        atomic_set(&state.client_subscription_value, value);
        setClientSubscriptionToken(state, connection);
        const int result = bt_gatt_subscribe(connection, &state.subscribe_parameters);
        bt_conn_unref(connection);
        if (result < 0)
        {
            atomic_set(&state.client_busy_value, 0);
            atomic_set(&state.client_subscription_value, 0);
            clearClientSubscriptionToken(state);
            nucode::ble::internal::recordError(BLEError::driver_error, result, true);
            return false;
        }
        return true;
    }

} // namespace nucode::ble::internal::gatt

namespace nucode::ble
{
    using namespace internal::gatt;

    bool BLERemoteService::valid() const noexcept
    {
        return valid_;
    }

    const BLEUuid &BLERemoteService::uuid() const noexcept
    {
        return uuid_;
    }

    std::uint16_t BLERemoteService::startHandle() const noexcept
    {
        return start_handle_;
    }

    std::uint16_t BLERemoteService::endHandle() const noexcept
    {
        return end_handle_;
    }

    bool BLERemoteCharacteristic::valid() const noexcept
    {
        return valid_;
    }

    const BLEUuid &BLERemoteCharacteristic::uuid() const noexcept
    {
        return uuid_;
    }

    std::uint16_t BLERemoteCharacteristic::valueHandle() const noexcept
    {
        return value_handle_;
    }

    std::uint16_t BLERemoteCharacteristic::cccHandle() const noexcept
    {
        return ccc_handle_;
    }

    BLEProperty BLERemoteCharacteristic::properties() const noexcept
    {
        return properties_;
    }

    bool GattClient::discover(const BLEUuid &service_uuid,
                              const BLEUuid &characteristic_uuid) noexcept
    {
        return discover(legacyConnectionHandle(), service_uuid, characteristic_uuid);
    }

    bool GattClient::discover(BLEConnectionHandle connection_handle,
                              const BLEUuid &service_uuid,
                              const BLEUuid &characteristic_uuid) noexcept
    {
        if (!internal::requireThreadContext())
        {
            return false;
        }
        if (!service_uuid.valid() || !characteristic_uuid.valid() ||
            service_uuid.type() == BLEUuid::Type::uuid32 ||
            characteristic_uuid.type() == BLEUuid::Type::uuid32)
        {
            internal::recordError(BLEError::invalid_argument, -EINVAL, true);
            return false;
        }
        ClientState *state = findClientState(connection_handle);
        if (state == nullptr)
        {
            internal::recordError(BLEError::not_connected, -ENOTCONN, true);
            return false;
        }
        if (!atomic_cas(&state->client_busy_value, 0, 1))
        {
            internal::recordError(BLEError::busy, -EBUSY, true);
            return false;
        }
        struct bt_conn *connection = internal::referenceConnection(connection_handle);
        if (connection == nullptr || !currentGattConnection(*state, connection))
        {
            if (connection != nullptr)
            {
                bt_conn_unref(connection);
            }
            atomic_set(&state->client_busy_value, 0);
            internal::recordError(BLEError::not_connected, -ENOTCONN, true);
            return false;
        }
        state->target_service_uuid = service_uuid;
        state->target_characteristic_uuid = characteristic_uuid;
        k_spinlock_key_t key = k_spin_lock(&state->client_state_lock);
        GattAccess::clear(state->remote_service);
        GattAccess::clear(state->remote_characteristic);
        k_spin_unlock(&state->client_state_lock, key);
        atomic_set(&state->client_subscribed, 0);
        atomic_set(&state->client_subscription_value, 0);
        atomic_set(&state->client_last_att_error, 0);
        state->read_length = 0U;
        ::memset(&state->discovery_parameters, 0, sizeof(state->discovery_parameters));
        state->discovery_parameters.uuid = state->target_service_zephyr_uuid.assign(service_uuid);
        state->discovery_parameters.func = serviceDiscovered;
        state->discovery_parameters.start_handle = BT_ATT_FIRST_ATTRIBUTE_HANDLE;
        state->discovery_parameters.end_handle = BT_ATT_LAST_ATTRIBUTE_HANDLE;
        state->discovery_parameters.type = BT_GATT_DISCOVER_PRIMARY;
        atomic_set(&state->client_stage,
                   static_cast<atomic_val_t>(ClientStage::discovering_service));
        setClientOperationToken(*state, connection);
        const int result = bt_gatt_discover(connection, &state->discovery_parameters);
        bt_conn_unref(connection);
        if (result < 0)
        {
            failClient(*state, result);
            return false;
        }
        return true;
    }

    bool GattClient::discovered() const noexcept
    {
        return discovered(legacyConnectionHandle());
    }

    bool GattClient::discovered(BLEConnectionHandle connection) const noexcept
    {
        ClientState *state = findClientState(connection);
        if (state == nullptr ||
            atomic_get(&state->client_stage) != static_cast<atomic_val_t>(ClientStage::ready))
        {
            return false;
        }
        BLERemoteService service;
        BLERemoteCharacteristic characteristic;
        copyRemoteHandles(*state, service, characteristic);
        return atomic_get(&state->client_stage) == static_cast<atomic_val_t>(ClientStage::ready) &&
               service.valid() && characteristic.valid();
    }

    BLERemoteService GattClient::remoteService() const noexcept
    {
        return remoteService(legacyConnectionHandle());
    }

    BLERemoteService GattClient::remoteService(BLEConnectionHandle connection) const noexcept
    {
        ClientState *state = findClientState(connection);
        return state == nullptr ? BLERemoteService{} : copyRemoteService(*state);
    }

    BLERemoteCharacteristic GattClient::remoteCharacteristic() const noexcept
    {
        return remoteCharacteristic(legacyConnectionHandle());
    }

    BLERemoteCharacteristic GattClient::remoteCharacteristic(
        BLEConnectionHandle connection) const noexcept
    {
        ClientState *state = findClientState(connection);
        return state == nullptr ? BLERemoteCharacteristic{} : copyRemoteCharacteristic(*state);
    }

    bool GattClient::read() noexcept
    {
        return read(legacyConnectionHandle());
    }

    bool GattClient::read(BLEConnectionHandle connection_handle) noexcept
    {
        if (!internal::requireThreadContext())
        {
            return false;
        }
        ClientState *state = findClientState(connection_handle);
        if (state == nullptr)
        {
            internal::recordError(BLEError::not_connected, -ENOTCONN, true);
            return false;
        }
        const BLERemoteCharacteristic characteristic = copyRemoteCharacteristic(*state);
        if (!discovered(connection_handle) || !characteristic.valid())
        {
            internal::recordError(BLEError::wrong_state, -EPERM, true);
            return false;
        }
        if (!hasProperty(characteristic.properties(), BLEProperty::read))
        {
            internal::recordError(BLEError::unsupported, -ENOTSUP, true);
            return false;
        }
        if (!atomic_cas(&state->client_busy_value, 0, 1))
        {
            internal::recordError(BLEError::busy, -EBUSY, true);
            return false;
        }
        struct bt_conn *connection = internal::referenceConnection(connection_handle);
        if (connection == nullptr || !currentGattConnection(*state, connection))
        {
            if (connection != nullptr)
            {
                bt_conn_unref(connection);
            }
            atomic_set(&state->client_busy_value, 0);
            internal::recordError(BLEError::not_connected, -ENOTCONN, true);
            return false;
        }
        state->read_length = 0U;
        ::memset(&state->read_parameters, 0, sizeof(state->read_parameters));
        state->read_parameters.func = clientReadCompleted;
        state->read_parameters.handle_count = 1U;
        state->read_parameters.single.handle = characteristic.valueHandle();
        state->read_parameters.single.offset = 0U;
        setClientOperationToken(*state, connection);
        const int result = bt_gatt_read(connection, &state->read_parameters);
        bt_conn_unref(connection);
        if (result < 0)
        {
            clearClientOperationToken(*state);
            atomic_set(&state->client_busy_value, 0);
            internal::recordError(BLEError::driver_error, result, true);
            return false;
        }
        return true;
    }

    bool GattClient::write(const void *data, std::size_t length) noexcept
    {
        return write(legacyConnectionHandle(), data, length);
    }

    bool GattClient::write(BLEConnectionHandle connection_handle, const void *data,
                           std::size_t length) noexcept
    {
        if (!internal::requireThreadContext())
        {
            return false;
        }
        ClientState *state = findClientState(connection_handle);
        if (state == nullptr)
        {
            internal::recordError(BLEError::not_connected, -ENOTCONN, true);
            return false;
        }
        const BLERemoteCharacteristic characteristic = copyRemoteCharacteristic(*state);
        if (!discovered(connection_handle) || !characteristic.valid() ||
            !hasProperty(characteristic.properties(), BLEProperty::write))
        {
            internal::recordError(BLEError::wrong_state, -EPERM, true);
            return false;
        }
        if (data == nullptr && length != 0U)
        {
            internal::recordError(BLEError::invalid_argument, -EINVAL, true);
            return false;
        }
        if (length > maximum_value_length)
        {
            internal::recordError(BLEError::value_overflow, -EMSGSIZE, true);
            return false;
        }
        if (!atomic_cas(&state->client_busy_value, 0, 1))
        {
            internal::recordError(BLEError::busy, -EBUSY, true);
            return false;
        }
        struct bt_conn *connection = internal::referenceConnection(connection_handle);
        if (connection == nullptr || !currentGattConnection(*state, connection))
        {
            if (connection != nullptr)
            {
                bt_conn_unref(connection);
            }
            atomic_set(&state->client_busy_value, 0);
            internal::recordError(BLEError::not_connected, -ENOTCONN, true);
            return false;
        }
        if (length != 0U)
        {
            ::memcpy(state->write_data, data, length);
        }
        ::memset(&state->write_parameters, 0, sizeof(state->write_parameters));
        state->write_parameters.func = clientWriteCompleted;
        state->write_parameters.handle = characteristic.valueHandle();
        state->write_parameters.offset = 0U;
        state->write_parameters.data = state->write_data;
        state->write_parameters.length = static_cast<std::uint16_t>(length);
        setClientOperationToken(*state, connection);
        const int result = bt_gatt_write(connection, &state->write_parameters);
        bt_conn_unref(connection);
        if (result < 0)
        {
            clearClientOperationToken(*state);
            atomic_set(&state->client_busy_value, 0);
            internal::recordError(BLEError::driver_error, result, true);
            return false;
        }
        return true;
    }

    bool GattClient::writeWithoutResponse(const void *data, std::size_t length) noexcept
    {
        return writeWithoutResponse(legacyConnectionHandle(), data, length);
    }

    bool GattClient::writeWithoutResponse(BLEConnectionHandle connection_handle, const void *data,
                                          std::size_t length) noexcept
    {
        if (!internal::requireThreadContext())
        {
            return false;
        }
        ClientState *state = findClientState(connection_handle);
        if (state == nullptr)
        {
            internal::recordError(BLEError::not_connected, -ENOTCONN, true);
            return false;
        }
        const BLERemoteCharacteristic characteristic = copyRemoteCharacteristic(*state);
        if (!discovered(connection_handle) || !characteristic.valid() ||
            !hasProperty(characteristic.properties(), BLEProperty::write_without_response))
        {
            internal::recordError(BLEError::wrong_state, -EPERM, true);
            return false;
        }
        if (data == nullptr && length != 0U)
        {
            internal::recordError(BLEError::invalid_argument, -EINVAL, true);
            return false;
        }
        if (!validWriteCommandPayload(*state, length))
        {
            return false;
        }
        if (!atomic_cas(&state->client_busy_value, 0, 1))
        {
            internal::recordError(BLEError::busy, -EBUSY, true);
            return false;
        }
        struct bt_conn *connection = internal::referenceConnection(connection_handle);
        if (connection == nullptr || !currentGattConnection(*state, connection))
        {
            if (connection != nullptr)
            {
                bt_conn_unref(connection);
            }
            atomic_set(&state->client_busy_value, 0);
            internal::recordError(BLEError::not_connected, -ENOTCONN, true);
            return false;
        }
        if (length != 0U)
        {
            ::memcpy(state->write_data, data, length);
        }
        setClientOperationToken(*state, connection);
        const int result = bt_gatt_write_without_response_cb(
            connection, characteristic.valueHandle(), state->write_data,
            static_cast<std::uint16_t>(length), false, clientWriteCommandCompleted, state);
        bt_conn_unref(connection);
        if (result < 0)
        {
            clearClientOperationToken(*state);
            atomic_set(&state->client_busy_value, 0);
            internal::recordError(BLEError::driver_error, result, true);
            return false;
        }
        return true;
    }

    bool GattClient::subscribeNotifications() noexcept
    {
        return subscribeNotifications(legacyConnectionHandle());
    }

    bool GattClient::subscribeNotifications(BLEConnectionHandle connection) noexcept
    {
        if (!internal::requireThreadContext())
        {
            return false;
        }
        ClientState *state = findClientState(connection);
        if (state == nullptr)
        {
            internal::recordError(BLEError::not_connected, -ENOTCONN, true);
            return false;
        }
        const BLERemoteCharacteristic characteristic = copyRemoteCharacteristic(*state);
        if (!characteristic.valid() ||
            !hasProperty(characteristic.properties(), BLEProperty::notify))
        {
            internal::recordError(BLEError::unsupported, -ENOTSUP, true);
            return false;
        }
        return startSubscription(*state, BT_GATT_CCC_NOTIFY);
    }

    bool GattClient::subscribeIndications() noexcept
    {
        return subscribeIndications(legacyConnectionHandle());
    }

    bool GattClient::subscribeIndications(BLEConnectionHandle connection) noexcept
    {
        if (!internal::requireThreadContext())
        {
            return false;
        }
        ClientState *state = findClientState(connection);
        if (state == nullptr)
        {
            internal::recordError(BLEError::not_connected, -ENOTCONN, true);
            return false;
        }
        const BLERemoteCharacteristic characteristic = copyRemoteCharacteristic(*state);
        if (!characteristic.valid() ||
            !hasProperty(characteristic.properties(), BLEProperty::indicate))
        {
            internal::recordError(BLEError::unsupported, -ENOTSUP, true);
            return false;
        }
        return startSubscription(*state, BT_GATT_CCC_INDICATE);
    }

    bool GattClient::unsubscribe() noexcept
    {
        return unsubscribe(legacyConnectionHandle());
    }

    bool GattClient::unsubscribe(BLEConnectionHandle connection_handle) noexcept
    {
        if (!internal::requireThreadContext())
        {
            return false;
        }
        ClientState *state = findClientState(connection_handle);
        if (state == nullptr)
        {
            internal::recordError(BLEError::not_connected, -ENOTCONN, true);
            return false;
        }
        if (atomic_get(&state->client_subscribed) == 0)
        {
            internal::recordError(BLEError::wrong_state, -EPERM, true);
            return false;
        }
        if (!atomic_cas(&state->client_busy_value, 0, 1))
        {
            internal::recordError(BLEError::busy, -EBUSY, true);
            return false;
        }
        struct bt_conn *connection = internal::referenceConnection(connection_handle);
        if (connection == nullptr || !currentGattConnection(*state, connection))
        {
            if (connection != nullptr)
            {
                bt_conn_unref(connection);
            }
            atomic_set(&state->client_busy_value, 0);
            internal::recordError(BLEError::not_connected, -ENOTCONN, true);
            return false;
        }
        const int result = bt_gatt_unsubscribe(connection, &state->subscribe_parameters);
        bt_conn_unref(connection);
        if (result < 0)
        {
            atomic_set(&state->client_busy_value, 0);
            internal::recordError(BLEError::driver_error, result, true);
            return false;
        }
        return true;
    }

    bool GattClient::busy() const noexcept
    {
        return busy(legacyConnectionHandle());
    }

    bool GattClient::busy(BLEConnectionHandle connection) const noexcept
    {
        ClientState *state = findClientState(connection);
        return state != nullptr && atomic_get(&state->client_busy_value) != 0;
    }

    std::uint8_t GattClient::lastAttError() const noexcept
    {
        return lastAttError(legacyConnectionHandle());
    }

    std::uint8_t GattClient::lastAttError(BLEConnectionHandle connection) const noexcept
    {
        ClientState *state = findClientState(connection);
        return state == nullptr
                   ? 0U
                   : static_cast<std::uint8_t>(atomic_get(&state->client_last_att_error));
    }

    void GattClient::onEvent(BLEGattClientCallback callback, void *context) noexcept
    {
        if (!internal::requireThreadContext())
        {
            return;
        }
        clientCallbacks().legacy = callback;
        clientCallbacks().legacy_context = context;
    }

    void GattClient::onDetailedEvent(BLEGattClientInfoCallback callback, void *context) noexcept
    {
        if (!internal::requireThreadContext())
        {
            return;
        }
        clientCallbacks().detailed = callback;
        clientCallbacks().detailed_context = context;
    }

} // namespace nucode::ble

nucode::ble::GattClient BLEClient;
#endif
