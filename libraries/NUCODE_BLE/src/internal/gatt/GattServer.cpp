/** @file @brief GATT cached value·CCC·notification/indication 수명주기입니다.
 * SPDX-License-Identifier: MIT
 */
#if !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE)
#include "GattInternal.h"
namespace nucode::ble::internal::gatt
{
    namespace
    {
        ServerState state{};
    }
    ServerState &serverState() noexcept
    {
        return state;
    }

    namespace
    {
        /** @brief lock을 잡은 상태에서 transaction slot을 초기화합니다. */
        void resetPrepareTransaction(PrepareTransaction &transaction) noexcept
        {
            transaction.connection = nullptr;
            transaction.characteristic = nullptr;
            transaction.generation = 0U;
            transaction.length = 0U;
        }

        /** @brief exact native link의 transaction을 찾습니다. */
        PrepareTransaction *findPrepareTransaction(struct bt_conn *connection) noexcept
        {
            for (PrepareTransaction &transaction : serverState().prepare_transactions)
            {
                if (transaction.connection == connection)
                {
                    return &transaction;
                }
            }
            return nullptr;
        }

        /** @brief 빈 prepare transaction slot을 찾습니다. */
        PrepareTransaction *findAvailablePrepareTransaction() noexcept
        {
            for (PrepareTransaction &transaction : serverState().prepare_transactions)
            {
                if (transaction.connection == nullptr)
                {
                    return &transaction;
                }
            }
            return nullptr;
        }
    } // namespace

    void clearServerTransaction(struct bt_conn *connection) noexcept
    {
        if (connection == nullptr)
        {
            return;
        }
        k_spinlock_key_t key = k_spin_lock(&serverState().characteristic_value_lock);
        PrepareTransaction *transaction = findPrepareTransaction(connection);
        if (transaction != nullptr)
        {
            resetPrepareTransaction(*transaction);
        }
        k_spin_unlock(&serverState().characteristic_value_lock, key);
    }

    void clearServerTransactions() noexcept
    {
        k_spinlock_key_t key = k_spin_lock(&serverState().characteristic_value_lock);
        for (PrepareTransaction &transaction : serverState().prepare_transactions)
        {
            resetPrepareTransaction(transaction);
        }
        k_spin_unlock(&serverState().characteristic_value_lock, key);
    }
    /** @brief cached characteristic 값을 spinlock 아래 bounded snapshot으로 복사합니다. */
    std::size_t copyCachedValue(const BLECharacteristic &characteristic, void *output,
                                std::size_t capacity) noexcept
    {
        k_spinlock_key_t key = k_spin_lock(&serverState().characteristic_value_lock);
        const std::size_t length = GattAccess::length(characteristic);
        const std::size_t copy_length = length < capacity ? length : capacity;
        if (copy_length != 0U && output != nullptr)
        {
            ::memcpy(output, GattAccess::value(characteristic), copy_length);
        }
        k_spin_unlock(&serverState().characteristic_value_lock, key);
        return copy_length;
    }

    /** @brief cached characteristic 값이 전송 buffer에 맞을 때만 온전히 복사합니다. */
    bool copyCachedValueForTransmission(const BLECharacteristic &characteristic, void *output,
                                        std::size_t capacity,
                                        std::size_t &length) noexcept
    {
        k_spinlock_key_t key = k_spin_lock(&serverState().characteristic_value_lock);
        length = GattAccess::length(characteristic);
        if (length > capacity)
        {
            k_spin_unlock(&serverState().characteristic_value_lock, key);
            return false;
        }
        if (length != 0U && output != nullptr)
        {
            ::memcpy(output, GattAccess::value(characteristic), length);
        }
        k_spin_unlock(&serverState().characteristic_value_lock, key);
        return true;
    }

    std::size_t copyDescriptorValue(const BLEDescriptor &descriptor, void *output,
                                    std::size_t capacity) noexcept
    {
        k_spinlock_key_t key = k_spin_lock(&serverState().characteristic_value_lock);
        const std::size_t length = GattAccess::length(descriptor);
        const std::size_t copy_length = length < capacity ? length : capacity;
        if (copy_length != 0U && output != nullptr)
        {
            ::memcpy(output, GattAccess::value(descriptor), copy_length);
        }
        k_spin_unlock(&serverState().characteristic_value_lock, key);
        return copy_length;
    }

    /** @brief descriptor가 속한 characteristic을 고정 schema에서 찾습니다. */
    BLECharacteristic *findDescriptorOwner(BLEDescriptor &descriptor) noexcept
    {
        for (std::size_t service_index = 0U;
             service_index < databaseState().registered_service_count; ++service_index)
        {
            ServiceSlot &slot = serviceSlots()[service_index];
            for (std::size_t characteristic_index = 0U;
                 characteristic_index < slot.characteristic_count; ++characteristic_index)
            {
                for (std::size_t descriptor_index = 0U;
                     descriptor_index < slot.descriptor_count[characteristic_index];
                     ++descriptor_index)
                {
                    if (slot.descriptors[characteristic_index][descriptor_index] == &descriptor)
                    {
                        return slot.characteristics[characteristic_index];
                    }
                }
            }
        }
        return nullptr;
    }

    /** @brief 동기 authorization을 수행하고 결과를 main-thread event로 복사합니다. */
    bool authorizeServerAccess(BLECharacteristic &characteristic, BLEDescriptor *descriptor,
                               BLEGattAuthorizationOperation operation, const void *data,
                               std::size_t length, std::size_t offset, std::uint8_t flags,
                               struct bt_conn *connection) noexcept
    {
        const bool configured = descriptor == nullptr
                                    ? GattAccess::hasAuthorization(characteristic)
                                    : GattAccess::hasAuthorization(*descriptor);
        if (!configured)
        {
            return true;
        }
        const BLEGattAuthorizationRequest request = {
            .connection = handleForConnection(connection),
            .characteristic = &characteristic,
            .descriptor = descriptor,
            .operation = operation,
            .data = static_cast<const std::uint8_t *>(data),
            .length = length,
            .offset = offset,
            .prepare = (flags & BT_GATT_WRITE_FLAG_PREPARE) != 0U,
            .execute = (flags & BT_GATT_WRITE_FLAG_EXECUTE) != 0U,
            .without_response = (flags & BT_GATT_WRITE_FLAG_CMD) != 0U,
        };
        const bool allowed = descriptor == nullptr ? GattAccess::authorize(characteristic, request)
                                                   : GattAccess::authorize(*descriptor, request);
        queueServerEvent(characteristic,
                         allowed ? BLECharacteristicEvent::authorization_allowed
                                 : BLECharacteristicEvent::authorization_denied,
                         data, length, offset, request.without_response,
                         allowed ? 0 : -BT_ATT_ERR_AUTHORIZATION, connection, descriptor,
                         operation);
        return allowed;
    }

    /** @brief CCC attribute가 소유한 characteristic을 찾습니다. */
    BLECharacteristic *findCccOwner(const struct bt_gatt_attr *attribute) noexcept
    {
        for (std::size_t service_index = 0U;
             service_index < databaseState().registered_service_count; ++service_index)
        {
            ServiceSlot &slot = serviceSlots()[service_index];
            for (std::size_t index = 0U; index < slot.characteristic_count; ++index)
            {
                if (slot.ccc_attribute_index[index] != 0U &&
                    &slot.attributes[slot.ccc_attribute_index[index]] == attribute)
                {
                    return slot.characteristics[index];
                }
            }
        }
        return nullptr;
    }

    /** @brief CCC를 실제로 설정한 active link를 peripheral 우선으로 참조합니다. */
    struct bt_conn *referenceSubscribedConnection(const struct bt_gatt_attr *attribute,
                                                  std::uint16_t value) noexcept
    {
        constexpr BLELinkRole roles[] = {
            BLELinkRole::peripheral,
            BLELinkRole::central,
        };
        for (BLELinkRole role : roles)
        {
            struct bt_conn *connection = internal::referenceConnection(role);
            if (connection == nullptr)
            {
                continue;
            }
            if (bt_gatt_is_subscribed(connection, attribute, value))
            {
                return connection;
            }
            bt_conn_unref(connection);
        }
        return nullptr;
    }

    /** @brief cached characteristic value를 stack read deadline 안에서 반환합니다. */
    ssize_t serverRead(struct bt_conn *connection, const struct bt_gatt_attr *attribute,
                       void *buffer, std::uint16_t length, std::uint16_t offset) noexcept
    {
        BLECharacteristic *characteristic = static_cast<BLECharacteristic *>(attribute->user_data);
        if (characteristic == nullptr)
        {
            return BT_GATT_ERR(BT_ATT_ERR_UNLIKELY);
        }
        if (!internal::activeConnection(connection))
        {
            return BT_GATT_ERR(BT_ATT_ERR_UNLIKELY);
        }
        if (!authorizeServerAccess(*characteristic, nullptr,
                                   BLEGattAuthorizationOperation::read, nullptr, 0U, offset, 0U,
                                   connection))
        {
            return BT_GATT_ERR(BT_ATT_ERR_AUTHORIZATION);
        }
        std::uint8_t snapshot[maximum_value_length] = {};
        const std::size_t snapshot_length =
            copyCachedValue(*characteristic, snapshot, sizeof(snapshot));
        return bt_gatt_attr_read(connection, attribute, buffer, length, offset, snapshot,
                                 snapshot_length);
    }

    /** @brief peer write를 link별 prepare 검증 뒤 atomic cached value로 commit합니다. */
    ssize_t serverWrite(struct bt_conn *connection, const struct bt_gatt_attr *attribute,
                        const void *buffer, std::uint16_t length, std::uint16_t offset,
                        std::uint8_t flags) noexcept
    {
        BLECharacteristic *characteristic = static_cast<BLECharacteristic *>(attribute->user_data);
        if (characteristic == nullptr || (buffer == nullptr && length != 0U))
        {
            return BT_GATT_ERR(BT_ATT_ERR_UNLIKELY);
        }
        if (length > maximum_event_payload_length)
        {
            clearServerTransaction(connection);
            return BT_GATT_ERR(BT_ATT_ERR_INVALID_ATTRIBUTE_LEN);
        }
        if (!internal::activeConnection(connection))
        {
            return BT_GATT_ERR(BT_ATT_ERR_UNLIKELY);
        }

        const std::size_t capacity = GattAccess::capacity(*characteristic);
        if (length == 0U &&
            (flags & (BT_GATT_WRITE_FLAG_PREPARE | BT_GATT_WRITE_FLAG_EXECUTE)) != 0U)
        {
            clearServerTransaction(connection);
            return BT_GATT_ERR(BT_ATT_ERR_INVALID_ATTRIBUTE_LEN);
        }
        if (offset > capacity)
        {
            clearServerTransaction(connection);
            return BT_GATT_ERR(BT_ATT_ERR_INVALID_OFFSET);
        }
        if (static_cast<std::size_t>(offset) + length > capacity)
        {
            clearServerTransaction(connection);
            return BT_GATT_ERR(BT_ATT_ERR_INVALID_ATTRIBUTE_LEN);
        }
        if (!authorizeServerAccess(*characteristic, nullptr,
                                   BLEGattAuthorizationOperation::write, buffer, length, offset,
                                   flags, connection))
        {
            clearServerTransaction(connection);
            return BT_GATT_ERR(BT_ATT_ERR_AUTHORIZATION);
        }

        if ((flags & BT_GATT_WRITE_FLAG_PREPARE) != 0U)
        {
            if ((flags & (BT_GATT_WRITE_FLAG_CMD | BT_GATT_WRITE_FLAG_EXECUTE)) != 0U)
            {
                clearServerTransaction(connection);
                return BT_GATT_ERR(BT_ATT_ERR_NOT_SUPPORTED);
            }
            const std::uint32_t generation =
                static_cast<std::uint32_t>(atomic_get(&sessionState().gatt_session_generation));
            k_spinlock_key_t key = k_spin_lock(&serverState().characteristic_value_lock);
            PrepareTransaction *transaction = findPrepareTransaction(connection);
            if (transaction != nullptr && transaction->generation != generation)
            {
                resetPrepareTransaction(*transaction);
                transaction = nullptr;
            }
            if (transaction != nullptr && transaction->characteristic != characteristic)
            {
                resetPrepareTransaction(*transaction);
                k_spin_unlock(&serverState().characteristic_value_lock, key);
                return BT_GATT_ERR(BT_ATT_ERR_PREPARE_QUEUE_FULL);
            }
            if (transaction != nullptr && offset == 0U)
            {
                resetPrepareTransaction(*transaction);
                transaction = nullptr;
            }
            if (transaction == nullptr)
            {
                if (offset != 0U)
                {
                    k_spin_unlock(&serverState().characteristic_value_lock, key);
                    return BT_GATT_ERR(BT_ATT_ERR_INVALID_OFFSET);
                }
                transaction = findAvailablePrepareTransaction();
                if (transaction == nullptr)
                {
                    k_spin_unlock(&serverState().characteristic_value_lock, key);
                    return BT_GATT_ERR(BT_ATT_ERR_PREPARE_QUEUE_FULL);
                }
                transaction->connection = connection;
                transaction->characteristic = characteristic;
                transaction->generation = generation;
            }
            if (offset != transaction->length)
            {
                resetPrepareTransaction(*transaction);
                k_spin_unlock(&serverState().characteristic_value_lock, key);
                return BT_GATT_ERR(BT_ATT_ERR_INVALID_OFFSET);
            }
            transaction->length = static_cast<std::uint16_t>(offset + length);
            k_spin_unlock(&serverState().characteristic_value_lock, key);
            return 0;
        }

        if ((flags & BT_GATT_WRITE_FLAG_EXECUTE) != 0U)
        {
            if ((flags & BT_GATT_WRITE_FLAG_CMD) != 0U)
            {
                clearServerTransaction(connection);
                return BT_GATT_ERR(BT_ATT_ERR_NOT_SUPPORTED);
            }
            const std::uint32_t generation =
                static_cast<std::uint32_t>(atomic_get(&sessionState().gatt_session_generation));
            k_spinlock_key_t key = k_spin_lock(&serverState().characteristic_value_lock);
            PrepareTransaction *transaction = findPrepareTransaction(connection);
            if (transaction == nullptr || transaction->characteristic != characteristic ||
                transaction->generation != generation || offset != 0U)
            {
                if (transaction != nullptr)
                {
                    resetPrepareTransaction(*transaction);
                }
                k_spin_unlock(&serverState().characteristic_value_lock, key);
                return BT_GATT_ERR(BT_ATT_ERR_INVALID_OFFSET);
            }
            if (transaction->length != length)
            {
                resetPrepareTransaction(*transaction);
                k_spin_unlock(&serverState().characteristic_value_lock, key);
                return BT_GATT_ERR(BT_ATT_ERR_INVALID_ATTRIBUTE_LEN);
            }
            ::memcpy(GattAccess::value(*characteristic), buffer, length);
            GattAccess::setLength(*characteristic, length);
            resetPrepareTransaction(*transaction);
            k_spin_unlock(&serverState().characteristic_value_lock, key);
            queueServerEvent(*characteristic, BLECharacteristicEvent::written, buffer, length, 0U,
                             false, 0, connection);
            return length;
        }

        k_spinlock_key_t key = k_spin_lock(&serverState().characteristic_value_lock);
        if (findPrepareTransaction(connection) != nullptr)
        {
            k_spin_unlock(&serverState().characteristic_value_lock, key);
            return BT_GATT_ERR(BT_ATT_ERR_PREPARE_QUEUE_FULL);
        }
        if (length != 0U)
        {
            ::memcpy(GattAccess::value(*characteristic) + offset, buffer, length);
        }
        const std::size_t new_length = offset == 0U
                                           ? length
                                           : MAX(GattAccess::length(*characteristic),
                                                 static_cast<std::size_t>(offset) + length);
        GattAccess::setLength(*characteristic, new_length);
        k_spin_unlock(&serverState().characteristic_value_lock, key);
        queueServerEvent(*characteristic, BLECharacteristicEvent::written, buffer, length, offset,
                         (flags & BT_GATT_WRITE_FLAG_CMD) != 0U, 0, connection);
        return length;
    }

    ssize_t descriptorRead(struct bt_conn *connection, const struct bt_gatt_attr *attribute,
                           void *buffer, std::uint16_t length, std::uint16_t offset) noexcept
    {
        BLEDescriptor *descriptor = static_cast<BLEDescriptor *>(attribute->user_data);
        if (descriptor == nullptr || !internal::activeConnection(connection))
        {
            return BT_GATT_ERR(BT_ATT_ERR_UNLIKELY);
        }
        BLECharacteristic *characteristic = findDescriptorOwner(*descriptor);
        if (characteristic == nullptr)
        {
            return BT_GATT_ERR(BT_ATT_ERR_UNLIKELY);
        }
        if (!authorizeServerAccess(*characteristic, descriptor,
                                   BLEGattAuthorizationOperation::read, nullptr, 0U, offset, 0U,
                                   connection))
        {
            return BT_GATT_ERR(BT_ATT_ERR_AUTHORIZATION);
        }
        std::uint8_t snapshot[BLEDescriptor::maximum_value_length] = {};
        const std::size_t snapshot_length =
            copyDescriptorValue(*descriptor, snapshot, sizeof(snapshot));
        return bt_gatt_attr_read(connection, attribute, buffer, length, offset, snapshot,
                                 snapshot_length);
    }

    ssize_t descriptorWrite(struct bt_conn *connection, const struct bt_gatt_attr *attribute,
                            const void *buffer, std::uint16_t length, std::uint16_t offset,
                            std::uint8_t flags) noexcept
    {
        BLEDescriptor *descriptor = static_cast<BLEDescriptor *>(attribute->user_data);
        if (descriptor == nullptr || (buffer == nullptr && length != 0U) ||
            !internal::activeConnection(connection))
        {
            return BT_GATT_ERR(BT_ATT_ERR_UNLIKELY);
        }
        if (length > maximum_event_payload_length)
        {
            return BT_GATT_ERR(BT_ATT_ERR_INVALID_ATTRIBUTE_LEN);
        }
        if ((flags & (BT_GATT_WRITE_FLAG_PREPARE | BT_GATT_WRITE_FLAG_EXECUTE)) != 0U)
        {
            return BT_GATT_ERR(BT_ATT_ERR_NOT_SUPPORTED);
        }
        const std::size_t capacity = GattAccess::capacity(*descriptor);
        if (offset > capacity)
        {
            return BT_GATT_ERR(BT_ATT_ERR_INVALID_OFFSET);
        }
        if (static_cast<std::size_t>(offset) + length > capacity)
        {
            return BT_GATT_ERR(BT_ATT_ERR_INVALID_ATTRIBUTE_LEN);
        }
        BLECharacteristic *characteristic = findDescriptorOwner(*descriptor);
        if (characteristic == nullptr)
        {
            return BT_GATT_ERR(BT_ATT_ERR_UNLIKELY);
        }
        if (!authorizeServerAccess(*characteristic, descriptor,
                                   BLEGattAuthorizationOperation::write, buffer, length, offset,
                                   flags, connection))
        {
            return BT_GATT_ERR(BT_ATT_ERR_AUTHORIZATION);
        }
        k_spinlock_key_t key = k_spin_lock(&serverState().characteristic_value_lock);
        if (length != 0U)
        {
            ::memcpy(GattAccess::value(*descriptor) + offset, buffer, length);
        }
        const std::size_t new_length = offset == 0U
                                           ? length
                                           : MAX(GattAccess::length(*descriptor),
                                                 static_cast<std::size_t>(offset) + length);
        GattAccess::setLength(*descriptor, new_length);
        k_spin_unlock(&serverState().characteristic_value_lock, key);
        queueServerEvent(*characteristic, BLECharacteristicEvent::descriptor_written, buffer,
                         length, offset, (flags & BT_GATT_WRITE_FLAG_CMD) != 0U, 0, connection,
                         descriptor, BLEGattAuthorizationOperation::write);
        return length;
    }

    /** @brief connection별 CCC 변경을 main-thread event로 변환합니다. */
    void cccChanged(const struct bt_gatt_attr *attribute, std::uint16_t value) noexcept
    {
        if (!internal::hasActiveConnection())
        {
            return;
        }
        BLECharacteristic *characteristic = findCccOwner(attribute);
        if (characteristic == nullptr)
        {
            return;
        }
        queueServerEvent(*characteristic,
                         value == 0U ? BLECharacteristicEvent::unsubscribed
                                     : BLECharacteristicEvent::subscribed,
                         nullptr, 0U, 0U, false, value);
    }

    /** @brief notification local TX 완료를 main-thread event로 변환합니다. */
    void notificationCompleted(struct bt_conn *connection, void *user_data) noexcept
    {
        NotificationContext *notification = static_cast<NotificationContext *>(user_data);
        if (notification == nullptr || notification->characteristic == nullptr)
        {
            return;
        }
        ServiceSlot *slot = nullptr;
        std::size_t index = 0U;
        if (!findCharacteristic(*notification->characteristic, slot, index))
        {
            return;
        }
        struct bt_conn *token_connection = notification->connection;
        const std::uint32_t token_generation = notification->generation;
        atomic_set(&slot->notification_active[index], 0);
        notification->connection = nullptr;
        notification->generation = 0U;
        if (token_connection == connection &&
            token_generation ==
                static_cast<std::uint32_t>(atomic_get(&sessionState().gatt_session_generation)) &&
            internal::activeConnection(connection))
        {
            queueServerEvent(*notification->characteristic,
                             BLECharacteristicEvent::notification_sent, nullptr, 0U, 0U, false, 0,
                             connection);
        }
    }

    /** @brief indication params가 소유한 characteristic 위치를 찾습니다. */
    bool findIndication(struct bt_gatt_indicate_params *parameters, ServiceSlot *&slot,
                        std::size_t &index) noexcept
    {
        for (std::size_t service_index = 0U;
             service_index < databaseState().registered_service_count; ++service_index)
        {
            ServiceSlot &candidate = serviceSlots()[service_index];
            for (std::size_t characteristic_index = 0U;
                 characteristic_index < candidate.characteristic_count; ++characteristic_index)
            {
                if (&candidate.indications[characteristic_index] == parameters)
                {
                    slot = &candidate;
                    index = characteristic_index;
                    return true;
                }
            }
        }
        return false;
    }

    /** @brief indication confirmation 또는 ATT 오류를 main thread에 전달합니다. */
    void indicationCompleted(struct bt_conn *connection, struct bt_gatt_indicate_params *parameters,
                             std::uint8_t error) noexcept
    {
        ARG_UNUSED(connection);
        ServiceSlot *slot = nullptr;
        std::size_t index = 0U;
        if (!findIndication(parameters, slot, index))
        {
            return;
        }
        if (slot->indication_connections[index] != connection ||
            slot->indication_generations[index] !=
                static_cast<std::uint32_t>(atomic_get(&sessionState().gatt_session_generation)) ||
            !internal::activeConnection(connection))
        {
            return;
        }
        queueServerEvent(*slot->characteristics[index],
                          error == 0U ? BLECharacteristicEvent::indication_confirmed
                                      : BLECharacteristicEvent::indication_failed,
                          nullptr, 0U, 0U, false, -static_cast<int>(error), connection);
    }

    /** @brief stack이 indication 수명을 해제한 뒤 slot 재사용을 허용합니다. */
    void indicationDestroyed(struct bt_gatt_indicate_params *parameters) noexcept
    {
        ServiceSlot *slot = nullptr;
        std::size_t index = 0U;
        if (findIndication(parameters, slot, index))
        {
            atomic_set(&slot->indication_active[index], 0);
            slot->indication_connections[index] = nullptr;
            slot->indication_generations[index] = 0U;
        }
    }

} // namespace nucode::ble::internal::gatt
namespace nucode::ble
{
    using namespace internal::gatt;

    BLEDescriptor::BLEDescriptor(const BLEUuid &uuid, BLEPermission permissions,
                                 std::size_t capacity) noexcept
        : uuid_(uuid), permissions_(permissions),
          value_(capacity <= maximum_inline_value_length ? internal_value_ : nullptr),
          capacity_(capacity <= maximum_inline_value_length ? capacity : 0U)
    {
    }

    BLEDescriptor::BLEDescriptor(const BLEUuid &uuid, BLEPermission permissions,
                                 std::uint8_t *buffer, std::size_t capacity) noexcept
        : uuid_(uuid), permissions_(permissions),
          value_(buffer != nullptr && capacity <= maximum_value_length ? buffer : nullptr),
          capacity_(buffer != nullptr && capacity <= maximum_value_length ? capacity : 0U)
    {
    }

    const BLEUuid &BLEDescriptor::uuid() const noexcept
    {
        return uuid_;
    }

    BLEPermission BLEDescriptor::permissions() const noexcept
    {
        return permissions_;
    }

    std::size_t BLEDescriptor::capacity() const noexcept
    {
        return capacity_;
    }

    std::size_t BLEDescriptor::valueLength() const noexcept
    {
        k_spinlock_key_t key = k_spin_lock(&serverState().characteristic_value_lock);
        const std::size_t length = value_length_;
        k_spin_unlock(&serverState().characteristic_value_lock, key);
        return length;
    }

    std::size_t BLEDescriptor::readValue(void *output, std::size_t capacity) const noexcept
    {
        if (output == nullptr || capacity == 0U || value_ == nullptr)
        {
            return 0U;
        }
        return copyDescriptorValue(*this, output, capacity);
    }

    bool BLEDescriptor::setValue(const void *data, std::size_t length) noexcept
    {
        if (!internal::requireThreadContext())
        {
            return false;
        }
        if ((data == nullptr && length != 0U) || value_ == nullptr || length > capacity_)
        {
            internal::recordError(BLEError::value_overflow, -EMSGSIZE, true);
            return false;
        }
        k_spinlock_key_t key = k_spin_lock(&serverState().characteristic_value_lock);
        if (length != 0U)
        {
            ::memcpy(value_, data, length);
        }
        value_length_ = length;
        k_spin_unlock(&serverState().characteristic_value_lock, key);
        return true;
    }

    void BLEDescriptor::onAuthorize(BLEGattAuthorizationCallback callback,
                                    void *context) noexcept
    {
        if (!internal::requireThreadContext())
        {
            return;
        }
        authorization_callback_ = callback;
        authorization_context_ = context;
    }

    BLECharacteristic::BLECharacteristic(const BLEUuid &uuid, BLEProperty properties,
                                         BLEPermission permissions, std::size_t capacity) noexcept
        : uuid_(uuid), properties_(properties), permissions_(permissions),
          value_(capacity <= maximum_inline_value_length ? internal_value_ : nullptr),
          capacity_(capacity <= maximum_inline_value_length ? capacity : 0U)
    {
    }

    BLECharacteristic::BLECharacteristic(const BLEUuid &uuid, BLEProperty properties,
                                         BLEPermission permissions, std::uint8_t *buffer,
                                         std::size_t capacity) noexcept
        : uuid_(uuid), properties_(properties), permissions_(permissions),
          value_(buffer != nullptr && capacity <= maximum_value_length ? buffer : nullptr),
          capacity_(buffer != nullptr && capacity <= maximum_value_length ? capacity : 0U)
    {
    }

    const BLEUuid &BLECharacteristic::uuid() const noexcept
    {
        return uuid_;
    }

    BLEProperty BLECharacteristic::properties() const noexcept
    {
        return properties_;
    }

    BLEPermission BLECharacteristic::permissions() const noexcept
    {
        return permissions_;
    }

    std::size_t BLECharacteristic::capacity() const noexcept
    {
        return capacity_;
    }

    std::size_t BLECharacteristic::valueLength() const noexcept
    {
        k_spinlock_key_t key = k_spin_lock(&serverState().characteristic_value_lock);
        const std::size_t length = value_length_;
        k_spin_unlock(&serverState().characteristic_value_lock, key);
        return length;
    }

    std::size_t BLECharacteristic::readValue(void *output, std::size_t capacity) const noexcept
    {
        if (output == nullptr || capacity == 0U || value_ == nullptr)
        {
            return 0U;
        }
        return copyCachedValue(*this, output, capacity);
    }

    bool BLECharacteristic::setValue(const void *data, std::size_t length) noexcept
    {
        if (!internal::requireThreadContext())
        {
            return false;
        }
        if ((data == nullptr && length != 0U) || value_ == nullptr || length > capacity_)
        {
            internal::recordError(BLEError::value_overflow, -EMSGSIZE, true);
            return false;
        }
        k_spinlock_key_t key = k_spin_lock(&serverState().characteristic_value_lock);
        if (length != 0U)
        {
            ::memcpy(value_, data, length);
        }
        value_length_ = length;
        k_spin_unlock(&serverState().characteristic_value_lock, key);
        return true;
    }

    void BLECharacteristic::onAuthorize(BLEGattAuthorizationCallback callback,
                                        void *context) noexcept
    {
        if (!internal::requireThreadContext())
        {
            return;
        }
        authorization_callback_ = callback;
        authorization_context_ = context;
    }

    bool BLECharacteristic::notificationSubscribed() const noexcept
    {
        if (!internal::requireThreadContext())
        {
            return false;
        }
        ServiceSlot *slot = nullptr;
        std::size_t index = 0U;
        if (!findCharacteristic(const_cast<BLECharacteristic &>(*this), slot, index))
        {
            return false;
        }
        const struct bt_gatt_attr *attribute =
            &slot->attributes[slot->value_attribute_index[index]];
        struct bt_conn *connection =
            referenceSubscribedConnection(attribute, BT_GATT_CCC_NOTIFY);
        if (connection == nullptr)
        {
            return false;
        }
        bt_conn_unref(connection);
        return true;
    }

    bool BLECharacteristic::indicationSubscribed() const noexcept
    {
        if (!internal::requireThreadContext())
        {
            return false;
        }
        ServiceSlot *slot = nullptr;
        std::size_t index = 0U;
        if (!findCharacteristic(const_cast<BLECharacteristic &>(*this), slot, index))
        {
            return false;
        }
        const struct bt_gatt_attr *attribute =
            &slot->attributes[slot->value_attribute_index[index]];
        struct bt_conn *connection =
            referenceSubscribedConnection(attribute, BT_GATT_CCC_INDICATE);
        if (connection == nullptr)
        {
            return false;
        }
        bt_conn_unref(connection);
        return true;
    }

    bool BLECharacteristic::notify() noexcept
    {
        if (!internal::requireThreadContext())
        {
            return false;
        }
        ServiceSlot *slot = nullptr;
        std::size_t index = 0U;
        if (!findCharacteristic(*this, slot, index))
        {
            internal::recordError(BLEError::wrong_state, -EPERM, true);
            return false;
        }
        const struct bt_gatt_attr *attribute =
            &slot->attributes[slot->value_attribute_index[index]];
        struct bt_conn *connection =
            referenceSubscribedConnection(attribute, BT_GATT_CCC_NOTIFY);
        if (connection == nullptr)
        {
            internal::recordError(BLEError::not_connected, -ENOTCONN, true);
            return false;
        }
        const BLEConnectionHandle handle = handleForConnection(connection);
        bt_conn_unref(connection);
        if (!handle.valid())
        {
            internal::recordError(BLEError::not_connected, -ENOTCONN, true);
            return false;
        }
        return notify(handle);
    }

    bool BLECharacteristic::notify(BLEConnectionHandle connection_handle) noexcept
    {
        if (!internal::requireThreadContext())
        {
            return false;
        }
        if (!hasProperty(properties_, BLEProperty::notify))
        {
            internal::recordError(BLEError::unsupported, -ENOTSUP, true);
            return false;
        }
        ServiceSlot *slot = nullptr;
        std::size_t index = 0U;
        if (!findCharacteristic(*this, slot, index))
        {
            internal::recordError(BLEError::wrong_state, -EPERM, true);
            return false;
        }
        if (!atomic_cas(&slot->notification_active[index], 0, 1))
        {
            internal::recordError(BLEError::busy, -EBUSY, true);
            return false;
        }
        const struct bt_gatt_attr *attribute =
            &slot->attributes[slot->value_attribute_index[index]];
        struct bt_conn *connection = internal::referenceConnection(connection_handle);
        if (connection == nullptr ||
            !bt_gatt_is_subscribed(connection, attribute, BT_GATT_CCC_NOTIFY))
        {
            if (connection != nullptr)
            {
                bt_conn_unref(connection);
            }
            atomic_set(&slot->notification_active[index], 0);
            internal::recordError(BLEError::not_connected, -ENOTCONN, true);
            return false;
        }
        const std::size_t mtu = bt_gatt_get_mtu(connection);
        std::size_t snapshot_length = 0U;
        if (!copyCachedValueForTransmission(*this, slot->notification_data[index],
                                            maximum_tx_payload_length, snapshot_length))
        {
            bt_conn_unref(connection);
            atomic_set(&slot->notification_active[index], 0);
            internal::recordError(BLEError::value_overflow, -EMSGSIZE, true);
            return false;
        }
        if (mtu < 3U || snapshot_length > mtu - 3U)
        {
            bt_conn_unref(connection);
            atomic_set(&slot->notification_active[index], 0);
            internal::recordError(BLEError::value_overflow, -EMSGSIZE, true);
            return false;
        }
        NotificationContext &notification = slot->notifications[index];
        notification.characteristic = this;
        notification.connection = connection;
        notification.generation =
            static_cast<std::uint32_t>(atomic_get(&sessionState().gatt_session_generation));
        struct bt_gatt_notify_params parameters = {
            .uuid = nullptr,
            .attr = attribute,
            .data = slot->notification_data[index],
            .len = static_cast<std::uint16_t>(snapshot_length),
            .func = notificationCompleted,
            .user_data = &notification,
        };
        const int result = bt_gatt_notify_cb(connection, &parameters);
        bt_conn_unref(connection);
        if (result < 0)
        {
            atomic_set(&slot->notification_active[index], 0);
            notification.connection = nullptr;
            notification.generation = 0U;
            internal::recordError(BLEError::driver_error, result, true);
            return false;
        }
        return true;
    }

    bool BLECharacteristic::indicate() noexcept
    {
        if (!internal::requireThreadContext())
        {
            return false;
        }
        ServiceSlot *slot = nullptr;
        std::size_t index = 0U;
        if (!findCharacteristic(*this, slot, index))
        {
            internal::recordError(BLEError::wrong_state, -EPERM, true);
            return false;
        }
        const struct bt_gatt_attr *attribute =
            &slot->attributes[slot->value_attribute_index[index]];
        struct bt_conn *connection =
            referenceSubscribedConnection(attribute, BT_GATT_CCC_INDICATE);
        if (connection == nullptr)
        {
            internal::recordError(BLEError::not_connected, -ENOTCONN, true);
            return false;
        }
        const BLEConnectionHandle handle = handleForConnection(connection);
        bt_conn_unref(connection);
        if (!handle.valid())
        {
            internal::recordError(BLEError::not_connected, -ENOTCONN, true);
            return false;
        }
        return indicate(handle);
    }

    bool BLECharacteristic::indicate(BLEConnectionHandle connection_handle) noexcept
    {
        if (!internal::requireThreadContext())
        {
            return false;
        }
        if (!hasProperty(properties_, BLEProperty::indicate))
        {
            internal::recordError(BLEError::unsupported, -ENOTSUP, true);
            return false;
        }
        ServiceSlot *slot = nullptr;
        std::size_t index = 0U;
        if (!findCharacteristic(*this, slot, index))
        {
            internal::recordError(BLEError::wrong_state, -EPERM, true);
            return false;
        }
        if (!atomic_cas(&slot->indication_active[index], 0, 1))
        {
            internal::recordError(BLEError::busy, -EBUSY, true);
            return false;
        }
        const struct bt_gatt_attr *attribute =
            &slot->attributes[slot->value_attribute_index[index]];
        struct bt_conn *connection = internal::referenceConnection(connection_handle);
        if (connection == nullptr ||
            !bt_gatt_is_subscribed(connection, attribute, BT_GATT_CCC_INDICATE))
        {
            if (connection != nullptr)
            {
                bt_conn_unref(connection);
            }
            atomic_set(&slot->indication_active[index], 0);
            internal::recordError(BLEError::not_connected, -ENOTCONN, true);
            return false;
        }
        const std::size_t mtu = bt_gatt_get_mtu(connection);
        std::size_t snapshot_length = 0U;
        if (!copyCachedValueForTransmission(*this, slot->indication_data[index],
                                            maximum_tx_payload_length, snapshot_length))
        {
            bt_conn_unref(connection);
            atomic_set(&slot->indication_active[index], 0);
            internal::recordError(BLEError::value_overflow, -EMSGSIZE, true);
            return false;
        }
        if (mtu < 3U || snapshot_length > mtu - 3U)
        {
            bt_conn_unref(connection);
            atomic_set(&slot->indication_active[index], 0);
            internal::recordError(BLEError::value_overflow, -EMSGSIZE, true);
            return false;
        }
        struct bt_gatt_indicate_params &parameters = slot->indications[index];
        ::memset(&parameters, 0, sizeof(parameters));
        parameters.attr = attribute;
        parameters.func = indicationCompleted;
        parameters.destroy = indicationDestroyed;
        parameters.data = slot->indication_data[index];
        parameters.len = static_cast<std::uint16_t>(snapshot_length);
        slot->indication_connections[index] = connection;
        slot->indication_generations[index] =
            static_cast<std::uint32_t>(atomic_get(&sessionState().gatt_session_generation));
        const int result = bt_gatt_indicate(connection, &parameters);
        bt_conn_unref(connection);
        if (result < 0)
        {
            atomic_set(&slot->indication_active[index], 0);
            slot->indication_connections[index] = nullptr;
            slot->indication_generations[index] = 0U;
            internal::recordError(BLEError::driver_error, result, true);
            return false;
        }
        return true;
    }

    void BLECharacteristic::onEvent(BLECharacteristicCallback callback, void *context) noexcept
    {
        if (!internal::requireThreadContext())
        {
            return;
        }
        callback_ = callback;
        callback_context_ = context;
    }

} // namespace nucode::ble
#endif
