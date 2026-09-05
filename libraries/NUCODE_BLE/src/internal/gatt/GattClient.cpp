/** @file @brief GATT discovery·client operation·subscription 수명주기입니다.
 * SPDX-License-Identifier: MIT
 */
#if !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE)
#include "GattInternal.h"
namespace nucode::ble::internal::gatt
{
    namespace
    {
        ClientState state{};
        BLEUuid target_service_uuid;
        BLEUuid target_characteristic_uuid;
        ZephyrUuid target_service_zephyr_uuid;
        ZephyrUuid target_characteristic_zephyr_uuid;
        struct bt_gatt_discover_params discovery_parameters = {};
        struct bt_gatt_read_params read_parameters = {};
        struct bt_gatt_write_params write_parameters = {};
        struct bt_gatt_subscribe_params subscribe_parameters = {};
        std::uint8_t client_write_data[maximum_value_length] = {};
    } // namespace
    ClientState &clientState() noexcept
    {
        return state;
    }
    /** @brief remote handle 두 개를 하나의 spinlock 아래 값으로 복사합니다. */
    void copyRemoteHandles(BLERemoteService &service,
                           BLERemoteCharacteristic &characteristic) noexcept
    {
        k_spinlock_key_t key = k_spin_lock(&clientState().client_state_lock);
        service = clientState().remote_service;
        characteristic = clientState().remote_characteristic;
        k_spin_unlock(&clientState().client_state_lock, key);
    }

    /** @brief remote service handle을 spinlock 아래 값으로 복사합니다. */
    BLERemoteService copyRemoteService() noexcept
    {
        k_spinlock_key_t key = k_spin_lock(&clientState().client_state_lock);
        const BLERemoteService service = clientState().remote_service;
        k_spin_unlock(&clientState().client_state_lock, key);
        return service;
    }

    /** @brief remote characteristic handle을 spinlock 아래 값으로 복사합니다. */
    BLERemoteCharacteristic copyRemoteCharacteristic() noexcept
    {
        k_spinlock_key_t key = k_spin_lock(&clientState().client_state_lock);
        const BLERemoteCharacteristic characteristic = clientState().remote_characteristic;
        k_spin_unlock(&clientState().client_state_lock, key);
        return characteristic;
    }

    /** @brief 새 client operation의 connection/session token을 저장합니다. */
    void setClientOperationToken(struct bt_conn *connection) noexcept
    {
        k_spinlock_key_t key = k_spin_lock(&clientState().client_token_lock);
        clientState().client_operation_connection = connection;
        clientState().client_operation_generation =
            static_cast<std::uint32_t>(atomic_get(&sessionState().gatt_session_generation));
        k_spin_unlock(&clientState().client_token_lock, key);
    }

    /** @brief callback이 현재 client operation에 속하는지 검사합니다. */
    bool validClientOperation(struct bt_conn *connection) noexcept
    {
        k_spinlock_key_t key = k_spin_lock(&clientState().client_token_lock);
        const bool matches =
            clientState().client_operation_connection == connection &&
            clientState().client_operation_generation ==
                static_cast<std::uint32_t>(atomic_get(&sessionState().gatt_session_generation));
        k_spin_unlock(&clientState().client_token_lock, key);
        return matches && currentGattConnection(connection);
    }

    /** @brief 현재 client operation token을 회수합니다. */
    void clearClientOperationToken() noexcept
    {
        k_spinlock_key_t key = k_spin_lock(&clientState().client_token_lock);
        clientState().client_operation_connection = nullptr;
        clientState().client_operation_generation = 0U;
        k_spin_unlock(&clientState().client_token_lock, key);
    }

    /** @brief 새 subscription의 connection/session token을 저장합니다. */
    void setClientSubscriptionToken(struct bt_conn *connection) noexcept
    {
        k_spinlock_key_t key = k_spin_lock(&clientState().client_token_lock);
        clientState().client_subscription_connection = connection;
        clientState().client_subscription_generation =
            static_cast<std::uint32_t>(atomic_get(&sessionState().gatt_session_generation));
        k_spin_unlock(&clientState().client_token_lock, key);
    }

    /** @brief callback이 현재 subscription에 속하는지 검사합니다. */
    bool validClientSubscription(struct bt_conn *connection) noexcept
    {
        k_spinlock_key_t key = k_spin_lock(&clientState().client_token_lock);
        const bool matches =
            clientState().client_subscription_connection == connection &&
            clientState().client_subscription_generation ==
                static_cast<std::uint32_t>(atomic_get(&sessionState().gatt_session_generation));
        k_spin_unlock(&clientState().client_token_lock, key);
        return matches && currentGattConnection(connection);
    }

    /** @brief 현재 subscription token을 회수합니다. */
    void clearClientSubscriptionToken() noexcept
    {
        k_spinlock_key_t key = k_spin_lock(&clientState().client_token_lock);
        clientState().client_subscription_connection = nullptr;
        clientState().client_subscription_generation = 0U;
        k_spin_unlock(&clientState().client_token_lock, key);
    }

    /** @brief client operation 실패 상태와 main-thread event를 함께 기록합니다. */
    void failClient(int driver_error, std::uint8_t att_error) noexcept
    {
        clearClientOperationToken();
        atomic_set(&clientState().client_last_att_error, att_error);
        atomic_set(&clientState().client_busy_value, 0);
        atomic_set(&clientState().client_stage, static_cast<atomic_val_t>(ClientStage::idle));
        nucode::ble::internal::recordError(driver_error == -ENOENT ? BLEError::not_found
                                                                   : BLEError::driver_error,
                                           driver_error, true);
        queueClientEvent(BLEGattClientEvent::operation_failed, nullptr, 0U,
                         att_error != 0U ? -static_cast<int>(att_error) : driver_error);
    }

    /** @brief service discovery callback에서 handle 복사본만 보존합니다. */
    std::uint8_t serviceDiscovered(struct bt_conn *connection, const struct bt_gatt_attr *attribute,
                                   struct bt_gatt_discover_params *parameters) noexcept
    {
        ARG_UNUSED(parameters);
        if (!validClientOperation(connection))
        {
            return BT_GATT_ITER_STOP;
        }
        if (attribute == nullptr)
        {
            failClient(-ENOENT);
            return BT_GATT_ITER_STOP;
        }
        const auto *value = static_cast<const struct bt_gatt_service_val *>(attribute->user_data);
        if (value == nullptr || value->end_handle <= attribute->handle)
        {
            failClient(-EINVAL);
            return BT_GATT_ITER_STOP;
        }
        k_spinlock_key_t key = k_spin_lock(&clientState().client_state_lock);
        GattAccess::set(clientState().remote_service, target_service_uuid, attribute->handle,
                        value->end_handle);
        k_spin_unlock(&clientState().client_state_lock, key);
        atomic_set(&clientState().client_stage,
                   static_cast<atomic_val_t>(ClientStage::service_found));
        return BT_GATT_ITER_STOP;
    }

    /** @brief characteristic discovery callback에서 portable handle만 보존합니다. */
    std::uint8_t characteristicDiscovered(struct bt_conn *connection,
                                          const struct bt_gatt_attr *attribute,
                                          struct bt_gatt_discover_params *parameters) noexcept
    {
        ARG_UNUSED(parameters);
        if (!validClientOperation(connection))
        {
            return BT_GATT_ITER_STOP;
        }
        if (attribute == nullptr)
        {
            failClient(-ENOENT);
            return BT_GATT_ITER_STOP;
        }
        const auto *value = static_cast<const struct bt_gatt_chrc *>(attribute->user_data);
        if (value == nullptr || value->value_handle == 0U)
        {
            failClient(-EINVAL);
            return BT_GATT_ITER_STOP;
        }
        k_spinlock_key_t key = k_spin_lock(&clientState().client_state_lock);
        GattAccess::set(clientState().remote_characteristic, target_characteristic_uuid,
                        attribute->handle, value->value_handle,
                        publicProperties(value->properties));
        k_spin_unlock(&clientState().client_state_lock, key);
        atomic_set(&clientState().client_stage,
                   static_cast<atomic_val_t>(ClientStage::characteristic_found));
        return BT_GATT_ITER_STOP;
    }

    /** @brief CCC discovery callback에서 descriptor handle만 보존합니다. */
    std::uint8_t cccDiscovered(struct bt_conn *connection, const struct bt_gatt_attr *attribute,
                               struct bt_gatt_discover_params *parameters) noexcept
    {
        ARG_UNUSED(parameters);
        if (!validClientOperation(connection))
        {
            return BT_GATT_ITER_STOP;
        }
        if (attribute == nullptr)
        {
            failClient(-ENOENT);
            return BT_GATT_ITER_STOP;
        }
        k_spinlock_key_t key = k_spin_lock(&clientState().client_state_lock);
        GattAccess::setCcc(clientState().remote_characteristic, attribute->handle);
        k_spin_unlock(&clientState().client_state_lock, key);
        atomic_set(&clientState().client_stage, static_cast<atomic_val_t>(ClientStage::ccc_found));
        return BT_GATT_ITER_STOP;
    }

    /** @brief remote read의 첫 bounded fragment를 main-thread queue로 복사합니다. */
    std::uint8_t clientReadCompleted(struct bt_conn *connection, std::uint8_t error,
                                     struct bt_gatt_read_params *parameters, const void *data,
                                     std::uint16_t length) noexcept
    {
        ARG_UNUSED(parameters);
        if (!validClientOperation(connection))
        {
            return BT_GATT_ITER_STOP;
        }
        if (error != 0U)
        {
            failClient(-EIO, error);
            return BT_GATT_ITER_STOP;
        }
        if (data != nullptr)
        {
            clearClientOperationToken();
            atomic_set(&clientState().client_busy_value, 0);
            queueClientEvent(BLEGattClientEvent::read_complete, data, length);
            return BT_GATT_ITER_STOP;
        }
        clearClientOperationToken();
        atomic_set(&clientState().client_busy_value, 0);
        queueClientEvent(BLEGattClientEvent::read_complete);
        return BT_GATT_ITER_STOP;
    }

    /** @brief response write 완료를 main-thread event로 변환합니다. */
    void clientWriteCompleted(struct bt_conn *connection, std::uint8_t error,
                              struct bt_gatt_write_params *parameters) noexcept
    {
        ARG_UNUSED(parameters);
        if (!validClientOperation(connection))
        {
            return;
        }
        if (error != 0U)
        {
            failClient(-EIO, error);
            return;
        }
        clearClientOperationToken();
        atomic_set(&clientState().client_busy_value, 0);
        queueClientEvent(BLEGattClientEvent::write_complete);
    }

    /** @brief write command의 local TX 완료를 main-thread event로 변환합니다. */
    void clientWriteCommandCompleted(struct bt_conn *connection, void *user_data) noexcept
    {
        ARG_UNUSED(user_data);
        if (!validClientOperation(connection))
        {
            return;
        }
        clearClientOperationToken();
        atomic_set(&clientState().client_busy_value, 0);
        queueClientEvent(BLEGattClientEvent::write_without_response_complete);
    }

    /** @brief CCC write response를 main-thread event로 변환합니다. */
    void clientSubscribeCompleted(struct bt_conn *connection, std::uint8_t error,
                                  struct bt_gatt_subscribe_params *parameters) noexcept
    {
        if (!validClientSubscription(connection))
        {
            return;
        }
        if (error != 0U)
        {
            atomic_set(&clientState().client_subscribed, 0);
            atomic_set(&clientState().client_subscription_value, 0);
            clearClientSubscriptionToken();
            failClient(-EIO, error);
            return;
        }
        if (parameters == nullptr)
        {
            atomic_set(&clientState().client_subscribed, 0);
            atomic_set(&clientState().client_subscription_value, 0);
            clearClientSubscriptionToken();
            failClient(-EINVAL);
            return;
        }
        if (parameters->value == 0U)
        {
            atomic_set(&clientState().client_subscribed, 0);
            atomic_set(&clientState().client_busy_value, 0);
            return;
        }
        atomic_set(&clientState().client_subscribed, 1);
        atomic_set(&clientState().client_subscription_value, parameters->value);
        atomic_set(&clientState().client_busy_value, 0);
        queueClientEvent(BLEGattClientEvent::subscribed);
    }

    /** @brief notify/indicate payload와 unsubscribe를 bounded queue로 복사합니다. */
    std::uint8_t clientNotification(struct bt_conn *connection,
                                    struct bt_gatt_subscribe_params *parameters, const void *data,
                                    std::uint16_t length) noexcept
    {
        ARG_UNUSED(parameters);
        if (!validClientSubscription(connection))
        {
            return BT_GATT_ITER_STOP;
        }
        if (data == nullptr)
        {
            atomic_set(&clientState().client_subscribed, 0);
            atomic_set(&clientState().client_subscription_value, 0);
            clearClientSubscriptionToken();
            atomic_set(&clientState().client_busy_value, 0);
            queueClientEvent(BLEGattClientEvent::unsubscribed);
            return BT_GATT_ITER_STOP;
        }
        queueClientEvent(atomic_get(&clientState().client_subscription_value) ==
                                 BT_GATT_CCC_INDICATE
                             ? BLEGattClientEvent::indication_received
                             : BLEGattClientEvent::notification_received,
                         data, length);
        return BT_GATT_ITER_CONTINUE;
    }

    /** @brief service 발견 뒤 characteristic discovery를 main thread에서 시작합니다. */
    void continueCharacteristicDiscovery() noexcept
    {
        struct bt_conn *connection = nucode::ble::internal::referenceConnection();
        if (connection == nullptr)
        {
            failClient(-ENOTCONN);
            return;
        }
        if (!validClientOperation(connection))
        {
            bt_conn_unref(connection);
            failClient(-ENOTCONN);
            return;
        }
        const BLERemoteService service = copyRemoteService();
        ::memset(&discovery_parameters, 0, sizeof(discovery_parameters));
        discovery_parameters.uuid =
            target_characteristic_zephyr_uuid.assign(target_characteristic_uuid);
        discovery_parameters.func = characteristicDiscovered;
        discovery_parameters.start_handle = service.startHandle() + 1U;
        discovery_parameters.end_handle = service.endHandle();
        discovery_parameters.type = BT_GATT_DISCOVER_CHARACTERISTIC;
        atomic_set(&clientState().client_stage,
                   static_cast<atomic_val_t>(ClientStage::discovering_characteristic));
        const int result = bt_gatt_discover(connection, &discovery_parameters);
        bt_conn_unref(connection);
        if (result < 0)
        {
            failClient(result);
        }
    }

    /** @brief characteristic 발견 뒤 CCC descriptor discovery를 시작합니다. */
    void continueCccDiscovery() noexcept
    {
        BLERemoteService service;
        BLERemoteCharacteristic characteristic;
        copyRemoteHandles(service, characteristic);
        const BLEProperty properties = characteristic.properties();
        if (!hasProperty(properties, BLEProperty::notify) &&
            !hasProperty(properties, BLEProperty::indicate))
        {
            atomic_set(&clientState().client_stage, static_cast<atomic_val_t>(ClientStage::ready));
            clearClientOperationToken();
            atomic_set(&clientState().client_busy_value, 0);
            queueClientEvent(BLEGattClientEvent::discovery_complete);
            return;
        }

        struct bt_conn *connection = nucode::ble::internal::referenceConnection();
        if (connection == nullptr)
        {
            failClient(-ENOTCONN);
            return;
        }
        if (!validClientOperation(connection))
        {
            bt_conn_unref(connection);
            failClient(-ENOTCONN);
            return;
        }
        if (characteristic.valueHandle() >= service.endHandle())
        {
            bt_conn_unref(connection);
            failClient(-ENOENT);
            return;
        }
        ::memset(&discovery_parameters, 0, sizeof(discovery_parameters));
        discovery_parameters.uuid = BT_UUID_GATT_CCC;
        discovery_parameters.func = cccDiscovered;
        discovery_parameters.start_handle = characteristic.valueHandle() + 1U;
        discovery_parameters.end_handle = service.endHandle();
        discovery_parameters.type = BT_GATT_DISCOVER_DESCRIPTOR;
        atomic_set(&clientState().client_stage,
                   static_cast<atomic_val_t>(ClientStage::discovering_ccc));
        const int result = bt_gatt_discover(connection, &discovery_parameters);
        bt_conn_unref(connection);
        if (result < 0)
        {
            failClient(result);
        }
    }

    /** @brief callback 결과 단계에 따라 다음 client discovery를 진행합니다. */
    void progressClientDiscovery() noexcept
    {
        if (atomic_cas(&clientState().client_stage,
                       static_cast<atomic_val_t>(ClientStage::service_found),
                       static_cast<atomic_val_t>(ClientStage::discovering_characteristic)))
        {
            continueCharacteristicDiscovery();
            return;
        }
        if (atomic_cas(&clientState().client_stage,
                       static_cast<atomic_val_t>(ClientStage::characteristic_found),
                       static_cast<atomic_val_t>(ClientStage::discovering_ccc)))
        {
            continueCccDiscovery();
            return;
        }
        if (atomic_cas(&clientState().client_stage,
                       static_cast<atomic_val_t>(ClientStage::ccc_found),
                       static_cast<atomic_val_t>(ClientStage::ready)))
        {
            clearClientOperationToken();
            atomic_set(&clientState().client_busy_value, 0);
            queueClientEvent(BLEGattClientEvent::discovery_complete);
        }
    }

    /** @brief client payload가 현재 ATT MTU의 단일 PDU에 들어가는지 검사합니다. */
    bool validClientPayload(std::size_t length) noexcept
    {
        struct bt_conn *connection = nucode::ble::internal::referenceConnection();
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

    /** @brief notify/indicate 공통 subscription 요청을 시작합니다. */
    bool startSubscription(std::uint16_t value) noexcept
    {
        BLERemoteService service;
        BLERemoteCharacteristic characteristic;
        copyRemoteHandles(service, characteristic);
        if (atomic_get(&clientState().client_stage) !=
                static_cast<atomic_val_t>(ClientStage::ready) ||
            !characteristic.valid() || characteristic.cccHandle() == 0U)
        {
            nucode::ble::internal::recordError(BLEError::wrong_state, -EPERM, true);
            return false;
        }
        if (!atomic_cas(&clientState().client_busy_value, 0, 1))
        {
            nucode::ble::internal::recordError(BLEError::busy, -EBUSY, true);
            return false;
        }
        if (atomic_get(&clientState().client_subscribed) != 0)
        {
            atomic_set(&clientState().client_busy_value, 0);
            nucode::ble::internal::recordError(BLEError::already_started, -EALREADY, true);
            return false;
        }
        struct bt_conn *connection = nucode::ble::internal::referenceConnection();
        if (connection == nullptr)
        {
            atomic_set(&clientState().client_busy_value, 0);
            nucode::ble::internal::recordError(BLEError::not_connected, -ENOTCONN, true);
            return false;
        }
        ::memset(&subscribe_parameters, 0, sizeof(subscribe_parameters));
        subscribe_parameters.notify = clientNotification;
        subscribe_parameters.subscribe = clientSubscribeCompleted;
        subscribe_parameters.value_handle = characteristic.valueHandle();
        subscribe_parameters.ccc_handle = characteristic.cccHandle();
        subscribe_parameters.value = value;
        atomic_set_bit(subscribe_parameters.flags, BT_GATT_SUBSCRIBE_FLAG_VOLATILE);
        atomic_set(&clientState().client_subscription_value, value);
        setClientSubscriptionToken(connection);
        const int result = bt_gatt_subscribe(connection, &subscribe_parameters);
        bt_conn_unref(connection);
        if (result < 0)
        {
            atomic_set(&clientState().client_busy_value, 0);
            atomic_set(&clientState().client_subscription_value, 0);
            clearClientSubscriptionToken();
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
        if (!atomic_cas(&clientState().client_busy_value, 0, 1))
        {
            internal::recordError(BLEError::busy, -EBUSY, true);
            return false;
        }
        struct bt_conn *connection = internal::referenceConnection();
        if (connection == nullptr)
        {
            atomic_set(&clientState().client_busy_value, 0);
            internal::recordError(BLEError::not_connected, -ENOTCONN, true);
            return false;
        }

        target_service_uuid = service_uuid;
        target_characteristic_uuid = characteristic_uuid;
        k_spinlock_key_t key = k_spin_lock(&clientState().client_state_lock);
        GattAccess::clear(clientState().remote_service);
        GattAccess::clear(clientState().remote_characteristic);
        k_spin_unlock(&clientState().client_state_lock, key);
        atomic_set(&clientState().client_subscribed, 0);
        atomic_set(&clientState().client_subscription_value, 0);
        atomic_set(&clientState().client_last_att_error, 0);
        ::memset(&discovery_parameters, 0, sizeof(discovery_parameters));
        discovery_parameters.uuid = target_service_zephyr_uuid.assign(service_uuid);
        discovery_parameters.func = serviceDiscovered;
        discovery_parameters.start_handle = BT_ATT_FIRST_ATTRIBUTE_HANDLE;
        discovery_parameters.end_handle = BT_ATT_LAST_ATTRIBUTE_HANDLE;
        discovery_parameters.type = BT_GATT_DISCOVER_PRIMARY;
        atomic_set(&clientState().client_stage,
                   static_cast<atomic_val_t>(ClientStage::discovering_service));
        setClientOperationToken(connection);
        const int result = bt_gatt_discover(connection, &discovery_parameters);
        bt_conn_unref(connection);
        if (result < 0)
        {
            clearClientOperationToken();
            failClient(result);
            return false;
        }
        return true;
    }

    bool GattClient::discovered() const noexcept
    {
        if (atomic_get(&clientState().client_stage) !=
            static_cast<atomic_val_t>(ClientStage::ready))
        {
            return false;
        }
        BLERemoteService service;
        BLERemoteCharacteristic characteristic;
        copyRemoteHandles(service, characteristic);
        return atomic_get(&clientState().client_stage) ==
                   static_cast<atomic_val_t>(ClientStage::ready) &&
               service.valid() && characteristic.valid();
    }

    BLERemoteService GattClient::remoteService() const noexcept
    {
        return copyRemoteService();
    }

    BLERemoteCharacteristic GattClient::remoteCharacteristic() const noexcept
    {
        return copyRemoteCharacteristic();
    }

    bool GattClient::read() noexcept
    {
        if (!internal::requireThreadContext())
        {
            return false;
        }
        const BLERemoteCharacteristic characteristic = remoteCharacteristic();
        if (!discovered() || !characteristic.valid())
        {
            internal::recordError(BLEError::wrong_state, -EPERM, true);
            return false;
        }
        if (!hasProperty(characteristic.properties(), BLEProperty::read))
        {
            internal::recordError(BLEError::unsupported, -ENOTSUP, true);
            return false;
        }
        if (!atomic_cas(&clientState().client_busy_value, 0, 1))
        {
            internal::recordError(BLEError::busy, -EBUSY, true);
            return false;
        }
        struct bt_conn *connection = internal::referenceConnection();
        if (connection == nullptr)
        {
            atomic_set(&clientState().client_busy_value, 0);
            internal::recordError(BLEError::not_connected, -ENOTCONN, true);
            return false;
        }
        ::memset(&read_parameters, 0, sizeof(read_parameters));
        read_parameters.func = clientReadCompleted;
        read_parameters.handle_count = 1U;
        read_parameters.single.handle = characteristic.valueHandle();
        read_parameters.single.offset = 0U;
        setClientOperationToken(connection);
        const int result = bt_gatt_read(connection, &read_parameters);
        bt_conn_unref(connection);
        if (result < 0)
        {
            clearClientOperationToken();
            atomic_set(&clientState().client_busy_value, 0);
            internal::recordError(BLEError::driver_error, result, true);
            return false;
        }
        return true;
    }

    bool GattClient::write(const void *data, std::size_t length) noexcept
    {
        if (!internal::requireThreadContext())
        {
            return false;
        }
        const BLERemoteCharacteristic characteristic = remoteCharacteristic();
        if (!discovered() || !characteristic.valid() ||
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
        if (!validClientPayload(length))
        {
            return false;
        }
        if (!atomic_cas(&clientState().client_busy_value, 0, 1))
        {
            internal::recordError(BLEError::busy, -EBUSY, true);
            return false;
        }
        struct bt_conn *connection = internal::referenceConnection();
        if (connection == nullptr)
        {
            atomic_set(&clientState().client_busy_value, 0);
            internal::recordError(BLEError::not_connected, -ENOTCONN, true);
            return false;
        }
        if (length != 0U)
        {
            ::memcpy(client_write_data, data, length);
        }
        ::memset(&write_parameters, 0, sizeof(write_parameters));
        write_parameters.func = clientWriteCompleted;
        write_parameters.handle = characteristic.valueHandle();
        write_parameters.offset = 0U;
        write_parameters.data = client_write_data;
        write_parameters.length = static_cast<std::uint16_t>(length);
        setClientOperationToken(connection);
        const int result = bt_gatt_write(connection, &write_parameters);
        bt_conn_unref(connection);
        if (result < 0)
        {
            clearClientOperationToken();
            atomic_set(&clientState().client_busy_value, 0);
            internal::recordError(BLEError::driver_error, result, true);
            return false;
        }
        return true;
    }

    bool GattClient::writeWithoutResponse(const void *data, std::size_t length) noexcept
    {
        if (!internal::requireThreadContext())
        {
            return false;
        }
        const BLERemoteCharacteristic characteristic = remoteCharacteristic();
        if (!discovered() || !characteristic.valid() ||
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
        if (!validClientPayload(length))
        {
            return false;
        }
        if (!atomic_cas(&clientState().client_busy_value, 0, 1))
        {
            internal::recordError(BLEError::busy, -EBUSY, true);
            return false;
        }
        struct bt_conn *connection = internal::referenceConnection();
        if (connection == nullptr)
        {
            atomic_set(&clientState().client_busy_value, 0);
            internal::recordError(BLEError::not_connected, -ENOTCONN, true);
            return false;
        }
        if (length != 0U)
        {
            ::memcpy(client_write_data, data, length);
        }
        setClientOperationToken(connection);
        const int result = bt_gatt_write_without_response_cb(
            connection, characteristic.valueHandle(), client_write_data,
            static_cast<std::uint16_t>(length), false, clientWriteCommandCompleted, nullptr);
        bt_conn_unref(connection);
        if (result < 0)
        {
            clearClientOperationToken();
            atomic_set(&clientState().client_busy_value, 0);
            internal::recordError(BLEError::driver_error, result, true);
            return false;
        }
        return true;
    }

    bool GattClient::subscribeNotifications() noexcept
    {
        if (!internal::requireThreadContext())
        {
            return false;
        }
        const BLERemoteCharacteristic characteristic = remoteCharacteristic();
        if (!characteristic.valid() ||
            !hasProperty(characteristic.properties(), BLEProperty::notify))
        {
            internal::recordError(BLEError::unsupported, -ENOTSUP, true);
            return false;
        }
        return startSubscription(BT_GATT_CCC_NOTIFY);
    }

    bool GattClient::subscribeIndications() noexcept
    {
        if (!internal::requireThreadContext())
        {
            return false;
        }
        const BLERemoteCharacteristic characteristic = remoteCharacteristic();
        if (!characteristic.valid() ||
            !hasProperty(characteristic.properties(), BLEProperty::indicate))
        {
            internal::recordError(BLEError::unsupported, -ENOTSUP, true);
            return false;
        }
        return startSubscription(BT_GATT_CCC_INDICATE);
    }

    bool GattClient::unsubscribe() noexcept
    {
        if (!internal::requireThreadContext())
        {
            return false;
        }
        if (atomic_get(&clientState().client_subscribed) == 0)
        {
            internal::recordError(BLEError::wrong_state, -EPERM, true);
            return false;
        }
        if (!atomic_cas(&clientState().client_busy_value, 0, 1))
        {
            internal::recordError(BLEError::busy, -EBUSY, true);
            return false;
        }
        struct bt_conn *connection = internal::referenceConnection();
        if (connection == nullptr)
        {
            atomic_set(&clientState().client_busy_value, 0);
            internal::recordError(BLEError::not_connected, -ENOTCONN, true);
            return false;
        }
        const int result = bt_gatt_unsubscribe(connection, &subscribe_parameters);
        bt_conn_unref(connection);
        if (result < 0)
        {
            atomic_set(&clientState().client_busy_value, 0);
            internal::recordError(BLEError::driver_error, result, true);
            return false;
        }
        return true;
    }

    bool GattClient::busy() const noexcept
    {
        return atomic_get(&clientState().client_busy_value) != 0;
    }

    std::uint8_t GattClient::lastAttError() const noexcept
    {
        return static_cast<std::uint8_t>(atomic_get(&clientState().client_last_att_error));
    }

    void GattClient::onEvent(BLEGattClientCallback callback, void *context) noexcept
    {
        if (!internal::requireThreadContext())
        {
            return;
        }
        clientState().client_callback = callback;
        clientState().client_context = context;
    }

} // namespace nucode::ble
nucode::ble::GattClient BLEClient;
#endif
