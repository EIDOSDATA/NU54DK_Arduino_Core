/**
 * @file NUCODE_BLE_GATT.cpp
 * @brief 고정 자원 범용 GATT server/client를 구현합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE_GATT.h>

#if !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE)
#include <internal/NUCODE_BLE_Internal.h>

#include <zephyr/bluetooth/att.h>
#include <zephyr/bluetooth/gatt.h>
#include <zephyr/bluetooth/uuid.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/atomic.h>
#include <zephyr/sys/util.h>

#include <errno.h>
#include <string.h>

namespace nucode::ble::internal
{

    /** @brief 공개 GATT 객체의 private 고정 자원에 구현만 접근합니다. */
    struct GattAccess
    {
        static BLEUuid &uuid(BLECharacteristic &characteristic) noexcept
        {
            return characteristic.uuid_;
        }

        static BLEProperty properties(const BLECharacteristic &characteristic) noexcept
        {
            return characteristic.properties_;
        }

        static BLEPermission permissions(const BLECharacteristic &characteristic) noexcept
        {
            return characteristic.permissions_;
        }

        static std::uint8_t *value(BLECharacteristic &characteristic) noexcept
        {
            return characteristic.value_;
        }

        static const std::uint8_t *value(const BLECharacteristic &characteristic) noexcept
        {
            return characteristic.value_;
        }

        static std::size_t capacity(const BLECharacteristic &characteristic) noexcept
        {
            return characteristic.capacity_;
        }

        static std::size_t length(const BLECharacteristic &characteristic) noexcept
        {
            return characteristic.value_length_;
        }

        static void setLength(BLECharacteristic &characteristic, std::size_t length) noexcept
        {
            characteristic.value_length_ = length;
        }

        static bool registered(const BLECharacteristic &characteristic) noexcept
        {
            return characteristic.registered_;
        }

        static void setRegistered(BLECharacteristic &characteristic, bool registered) noexcept
        {
            characteristic.registered_ = registered;
        }

        static void dispatch(BLECharacteristic &characteristic,
                             const BLECharacteristicEventInfo &event) noexcept
        {
            if (characteristic.callback_ != nullptr)
            {
                characteristic.callback_(characteristic, event, characteristic.callback_context_);
            }
        }

        static BLEUuid &uuid(BLEService &service) noexcept
        {
            return service.uuid_;
        }

        static std::size_t characteristicCount(const BLEService &service) noexcept
        {
            return service.characteristic_count_;
        }

        static BLECharacteristic *characteristic(BLEService &service, std::size_t index) noexcept
        {
            return service.characteristics_[index];
        }

        static bool registered(const BLEService &service) noexcept
        {
            return service.registered_;
        }

        static void setRegistered(BLEService &service, bool registered) noexcept
        {
            service.registered_ = registered;
        }

        static void clear(BLERemoteService &service) noexcept
        {
            service.uuid_ = BLEUuid{};
            service.start_handle_ = 0U;
            service.end_handle_ = 0U;
            service.valid_ = false;
        }

        static void set(BLERemoteService &service, const BLEUuid &uuid, std::uint16_t start,
                        std::uint16_t end) noexcept
        {
            service.uuid_ = uuid;
            service.start_handle_ = start;
            service.end_handle_ = end;
            service.valid_ = true;
        }

        static void clear(BLERemoteCharacteristic &characteristic) noexcept
        {
            characteristic.uuid_ = BLEUuid{};
            characteristic.declaration_handle_ = 0U;
            characteristic.value_handle_ = 0U;
            characteristic.ccc_handle_ = 0U;
            characteristic.properties_ = BLEProperty::none;
            characteristic.valid_ = false;
        }

        static void set(BLERemoteCharacteristic &characteristic, const BLEUuid &uuid,
                        std::uint16_t declaration_handle, std::uint16_t value_handle,
                        BLEProperty properties) noexcept
        {
            characteristic.uuid_ = uuid;
            characteristic.declaration_handle_ = declaration_handle;
            characteristic.value_handle_ = value_handle;
            characteristic.ccc_handle_ = 0U;
            characteristic.properties_ = properties;
            characteristic.valid_ = true;
        }

        static void setCcc(BLERemoteCharacteristic &characteristic, std::uint16_t handle) noexcept
        {
            characteristic.ccc_handle_ = handle;
        }
    };

} // namespace nucode::ble::internal

namespace
{

    using nucode::ble::BLECharacteristic;
    using nucode::ble::BLECharacteristicEvent;
    using nucode::ble::BLECharacteristicEventInfo;
    using nucode::ble::BLEError;
    using nucode::ble::BLEGattClientCallback;
    using nucode::ble::BLEGattClientEvent;
    using nucode::ble::BLEPermission;
    using nucode::ble::BLEProperty;
    using nucode::ble::BLERemoteCharacteristic;
    using nucode::ble::BLERemoteService;
    using nucode::ble::BLEService;
    using nucode::ble::BLEUuid;
    using nucode::ble::internal::GattAccess;

    constexpr std::size_t maximum_services = CONFIG_NUCODE_BLE_GATT_MAX_SERVICES;
    constexpr std::size_t maximum_characteristics = BLEService::maximum_characteristics;
    constexpr std::size_t maximum_attributes = 1U + maximum_characteristics * 3U;
    constexpr std::size_t maximum_value_length = BLECharacteristic::maximum_value_length;

    static_assert(maximum_services > 0U, "GATT service slot이 하나 이상 필요합니다.");
    static_assert(CONFIG_NUCODE_BLE_GATT_MAX_CHARACTERISTICS_PER_SERVICE <=
                      BLEService::maximum_characteristics,
                  "Kconfig characteristic 한도가 공개 객체 한도를 넘습니다.");

    /** @brief BLEUuid를 Zephyr public UUID 구조에 고정 저장합니다. */
    struct ZephyrUuid
    {
        struct bt_uuid_16 uuid16 = {};
        struct bt_uuid_128 uuid128 = {};

        const struct bt_uuid *assign(const BLEUuid &source) noexcept
        {
            if (source.type() == BLEUuid::Type::uuid16)
            {
                uuid16.uuid.type = BT_UUID_TYPE_16;
                uuid16.val = static_cast<std::uint16_t>(source.data()[0]) |
                             (static_cast<std::uint16_t>(source.data()[1]) << 8U);
                return &uuid16.uuid;
            }
            if (source.type() == BLEUuid::Type::uuid128)
            {
                uuid128.uuid.type = BT_UUID_TYPE_128;
                ::memcpy(uuid128.val, source.data(), sizeof(uuid128.val));
                return &uuid128.uuid;
            }
            return nullptr;
        }
    };

    /** @brief 등록 service 하나의 attribute와 async 전송 수명을 보존합니다. */
    struct NotificationContext
    {
        BLECharacteristic *characteristic = nullptr;
        struct bt_conn *connection = nullptr;
        std::uint32_t generation = 0U;
    };

    /** @brief 등록 service 하나의 attribute와 async 전송 수명을 보존합니다. */
    struct ServiceSlot
    {
        BLEService *owner = nullptr;
        ZephyrUuid service_uuid;
        ZephyrUuid characteristic_uuids[maximum_characteristics] = {};
        struct bt_gatt_service service = {};
        struct bt_gatt_attr attributes[maximum_attributes] = {};
        struct bt_gatt_chrc declarations[maximum_characteristics] = {};
        struct bt_gatt_ccc_managed_user_data ccc[maximum_characteristics] = {};
        BLECharacteristic *characteristics[maximum_characteristics] = {};
        NotificationContext notifications[maximum_characteristics] = {};
        atomic_t notification_active[maximum_characteristics] = {};
        struct bt_gatt_indicate_params indications[maximum_characteristics] = {};
        std::uint8_t indication_data[maximum_characteristics][maximum_value_length] = {};
        atomic_t indication_active[maximum_characteristics] = {};
        struct bt_conn *indication_connections[maximum_characteristics] = {};
        std::uint32_t indication_generations[maximum_characteristics] = {};
        std::size_t value_attribute_index[maximum_characteristics] = {};
        std::size_t ccc_attribute_index[maximum_characteristics] = {};
        std::size_t characteristic_count = 0U;
    };

    /** @brief server 또는 client callback data를 main thread로 복사합니다. */
    struct GattEventRecord
    {
        enum class Owner : std::uint8_t
        {
            server,
            client,
        } owner_kind;
        std::uint32_t generation;
        BLECharacteristic *characteristic;
        BLECharacteristicEvent server_event;
        BLEGattClientEvent client_event;
        std::uint16_t length;
        std::uint16_t offset;
        bool without_response;
        int status;
        std::uint8_t data[maximum_value_length];
    };

    /** @brief generic client discovery의 bounded 비동기 단계입니다. */
    enum class ClientStage : atomic_val_t
    {
        idle,
        discovering_service,
        service_found,
        discovering_characteristic,
        characteristic_found,
        discovering_ccc,
        ccc_found,
        ready,
    };

    K_MSGQ_DEFINE(gatt_event_queue, sizeof(GattEventRecord),
                  CONFIG_NUCODE_BLE_GATT_EVENT_QUEUE_SIZE, alignof(GattEventRecord));
    K_MUTEX_DEFINE(gatt_schema_mutex);
    struct k_spinlock characteristic_value_lock;
    struct k_spinlock client_state_lock;
    struct k_spinlock client_token_lock;

    ServiceSlot service_slots[maximum_services] = {};
    BLEService *registered_services[maximum_services] = {};
    std::size_t registered_service_count = 0U;
    atomic_t database_registered = ATOMIC_INIT(0);
    atomic_t gatt_session_generation = ATOMIC_INIT(1);
    atomic_t gatt_link_active = ATOMIC_INIT(0);

    atomic_t client_stage = ATOMIC_INIT(static_cast<atomic_val_t>(ClientStage::idle));
    atomic_t client_busy_value = ATOMIC_INIT(0);
    atomic_t client_subscribed = ATOMIC_INIT(0);
    atomic_t client_subscription_value = ATOMIC_INIT(0);
    atomic_t client_last_att_error = ATOMIC_INIT(0);
    BLEUuid target_service_uuid;
    BLEUuid target_characteristic_uuid;
    ZephyrUuid target_service_zephyr_uuid;
    ZephyrUuid target_characteristic_zephyr_uuid;
    BLERemoteService remote_service;
    BLERemoteCharacteristic remote_characteristic;
    struct bt_gatt_discover_params discovery_parameters = {};
    struct bt_gatt_read_params read_parameters = {};
    struct bt_gatt_write_params write_parameters = {};
    struct bt_gatt_subscribe_params subscribe_parameters = {};
    std::uint8_t client_write_data[maximum_value_length] = {};
    BLEGattClientCallback client_callback = nullptr;
    void *client_context = nullptr;
    struct bt_conn *client_operation_connection = nullptr;
    struct bt_conn *client_subscription_connection = nullptr;
    struct bt_conn *gatt_connection = nullptr;
    std::uint32_t client_operation_generation = 0U;
    std::uint32_t client_subscription_generation = 0U;
    std::uint32_t gatt_connection_generation = 0U;

    /** @brief enum bit가 설정되었는지 검사합니다. */
    bool hasProperty(BLEProperty value, BLEProperty bit) noexcept
    {
        return (static_cast<std::uint8_t>(value) & static_cast<std::uint8_t>(bit)) != 0U;
    }

    /** @brief permission bit가 설정되었는지 검사합니다. */
    bool hasPermission(BLEPermission value, BLEPermission bit) noexcept
    {
        return (static_cast<std::uint8_t>(value) & static_cast<std::uint8_t>(bit)) != 0U;
    }

    /** @brief public property를 Zephyr characteristic bit로 변환합니다. */
    std::uint8_t zephyrProperties(BLEProperty properties) noexcept
    {
        std::uint8_t result = 0U;
        if (hasProperty(properties, BLEProperty::read))
        {
            result |= BT_GATT_CHRC_READ;
        }
        if (hasProperty(properties, BLEProperty::write))
        {
            result |= BT_GATT_CHRC_WRITE;
        }
        if (hasProperty(properties, BLEProperty::write_without_response))
        {
            result |= BT_GATT_CHRC_WRITE_WITHOUT_RESP;
        }
        if (hasProperty(properties, BLEProperty::notify))
        {
            result |= BT_GATT_CHRC_NOTIFY;
        }
        if (hasProperty(properties, BLEProperty::indicate))
        {
            result |= BT_GATT_CHRC_INDICATE;
        }
        return result;
    }

    /** @brief Zephyr characteristic bit를 public property로 변환합니다. */
    BLEProperty publicProperties(std::uint8_t properties) noexcept
    {
        BLEProperty result = BLEProperty::none;
        if ((properties & BT_GATT_CHRC_READ) != 0U)
        {
            result = result | BLEProperty::read;
        }
        if ((properties & BT_GATT_CHRC_WRITE) != 0U)
        {
            result = result | BLEProperty::write;
        }
        if ((properties & BT_GATT_CHRC_WRITE_WITHOUT_RESP) != 0U)
        {
            result = result | BLEProperty::write_without_response;
        }
        if ((properties & BT_GATT_CHRC_NOTIFY) != 0U)
        {
            result = result | BLEProperty::notify;
        }
        if ((properties & BT_GATT_CHRC_INDICATE) != 0U)
        {
            result = result | BLEProperty::indicate;
        }
        return result;
    }

    /** @brief 공개 permission을 Zephyr attribute permission으로 변환합니다. */
    std::uint16_t zephyrPermissions(BLEPermission permissions) noexcept
    {
        std::uint16_t result = BT_GATT_PERM_NONE;
        if (hasPermission(permissions, BLEPermission::read))
        {
            result |= BT_GATT_PERM_READ;
        }
        if (hasPermission(permissions, BLEPermission::write))
        {
            result |= BT_GATT_PERM_WRITE;
        }
        return result;
    }

    /** @brief characteristic schema의 property/permission/buffer 일관성을 검사합니다. */
    bool validCharacteristic(const BLECharacteristic &characteristic) noexcept
    {
        const BLEProperty properties = GattAccess::properties(characteristic);
        const BLEPermission permissions = GattAccess::permissions(characteristic);
        if (!GattAccess::uuid(const_cast<BLECharacteristic &>(characteristic)).valid() ||
            GattAccess::uuid(const_cast<BLECharacteristic &>(characteristic)).type() ==
                BLEUuid::Type::uuid32 ||
            GattAccess::value(const_cast<BLECharacteristic &>(characteristic)) == nullptr ||
            GattAccess::capacity(characteristic) == 0U ||
            GattAccess::capacity(characteristic) > maximum_value_length ||
            properties == BLEProperty::none)
        {
            return false;
        }
        const bool readable = hasProperty(properties, BLEProperty::read);
        const bool writable = hasProperty(properties, BLEProperty::write) ||
                              hasProperty(properties, BLEProperty::write_without_response);
        return readable == hasPermission(permissions, BLEPermission::read) &&
               writable == hasPermission(permissions, BLEPermission::write);
    }

    /** @brief GATT callback record를 bounded queue에 복사합니다. */
    bool queueGattEvent(const GattEventRecord &record) noexcept
    {
        if (atomic_get(&gatt_link_active) == 0 &&
            !(record.owner_kind == GattEventRecord::Owner::client &&
              record.client_event == BLEGattClientEvent::handles_invalidated))
        {
            return false;
        }
        if (k_msgq_put(&gatt_event_queue, &record, K_NO_WAIT) == 0)
        {
            return true;
        }
        nucode::ble::internal::recordError(BLEError::event_overflow, -ENOBUFS, true);
        return false;
    }

    /** @brief server event와 payload chunk를 main-thread queue로 복사합니다. */
    void queueServerEvent(BLECharacteristic &characteristic, BLECharacteristicEvent event,
                          const void *data = nullptr, std::size_t length = 0U,
                          std::size_t offset = 0U, bool without_response = false,
                          int status = 0) noexcept
    {
        if (length > maximum_value_length)
        {
            nucode::ble::internal::recordError(BLEError::value_overflow, -EMSGSIZE, true);
            return;
        }
        GattEventRecord record = {};
        record.owner_kind = GattEventRecord::Owner::server;
        record.generation = static_cast<std::uint32_t>(atomic_get(&gatt_session_generation));
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
    void queueClientEvent(BLEGattClientEvent event, const void *data = nullptr,
                          std::size_t length = 0U, int status = 0) noexcept
    {
        if (length > maximum_value_length)
        {
            nucode::ble::internal::recordError(BLEError::value_overflow, -EMSGSIZE, true);
            return;
        }
        GattEventRecord record = {};
        record.owner_kind = GattEventRecord::Owner::client;
        record.generation = static_cast<std::uint32_t>(atomic_get(&gatt_session_generation));
        record.client_event = event;
        record.length = static_cast<std::uint16_t>(length);
        record.status = status;
        if (data != nullptr && length != 0U)
        {
            ::memcpy(record.data, data, length);
        }
        static_cast<void>(queueGattEvent(record));
    }

    /** @brief owner characteristic의 등록 attribute 위치를 찾습니다. */
    bool findCharacteristic(BLECharacteristic &owner, ServiceSlot *&slot,
                            std::size_t &characteristic_index) noexcept
    {
        for (std::size_t service_index = 0U; service_index < registered_service_count;
             ++service_index)
        {
            ServiceSlot &candidate = service_slots[service_index];
            for (std::size_t index = 0U; index < candidate.characteristic_count; ++index)
            {
                if (candidate.characteristics[index] == &owner)
                {
                    slot = &candidate;
                    characteristic_index = index;
                    return true;
                }
            }
        }
        return false;
    }

    /** @brief cached characteristic 값을 spinlock 아래 bounded snapshot으로 복사합니다. */
    std::size_t copyCachedValue(const BLECharacteristic &characteristic, void *output,
                                std::size_t capacity) noexcept
    {
        k_spinlock_key_t key = k_spin_lock(&characteristic_value_lock);
        const std::size_t length = GattAccess::length(characteristic);
        const std::size_t copy_length = length < capacity ? length : capacity;
        if (copy_length != 0U && output != nullptr)
        {
            ::memcpy(output, GattAccess::value(characteristic), copy_length);
        }
        k_spin_unlock(&characteristic_value_lock, key);
        return copy_length;
    }

    /** @brief remote handle 두 개를 하나의 spinlock 아래 값으로 복사합니다. */
    void copyRemoteHandles(BLERemoteService &service,
                           BLERemoteCharacteristic &characteristic) noexcept
    {
        k_spinlock_key_t key = k_spin_lock(&client_state_lock);
        service = remote_service;
        characteristic = remote_characteristic;
        k_spin_unlock(&client_state_lock, key);
    }

    /** @brief remote service handle을 spinlock 아래 값으로 복사합니다. */
    BLERemoteService copyRemoteService() noexcept
    {
        k_spinlock_key_t key = k_spin_lock(&client_state_lock);
        const BLERemoteService service = remote_service;
        k_spin_unlock(&client_state_lock, key);
        return service;
    }

    /** @brief remote characteristic handle을 spinlock 아래 값으로 복사합니다. */
    BLERemoteCharacteristic copyRemoteCharacteristic() noexcept
    {
        k_spinlock_key_t key = k_spin_lock(&client_state_lock);
        const BLERemoteCharacteristic characteristic = remote_characteristic;
        k_spin_unlock(&client_state_lock, key);
        return characteristic;
    }

    /** @brief callback connection이 현재 generic link인지 reference로 검사합니다. */
    bool currentGattConnection(struct bt_conn *connection) noexcept
    {
        if (connection == nullptr || atomic_get(&gatt_link_active) == 0)
        {
            return false;
        }
        k_spinlock_key_t key = k_spin_lock(&client_token_lock);
        const bool token_matches =
            gatt_connection == connection && gatt_connection_generation != 0U;
        k_spin_unlock(&client_token_lock, key);
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

    /** @brief 새 client operation의 connection/session token을 저장합니다. */
    void setClientOperationToken(struct bt_conn *connection) noexcept
    {
        k_spinlock_key_t key = k_spin_lock(&client_token_lock);
        client_operation_connection = connection;
        client_operation_generation =
            static_cast<std::uint32_t>(atomic_get(&gatt_session_generation));
        k_spin_unlock(&client_token_lock, key);
    }

    /** @brief callback이 현재 client operation에 속하는지 검사합니다. */
    bool validClientOperation(struct bt_conn *connection) noexcept
    {
        k_spinlock_key_t key = k_spin_lock(&client_token_lock);
        const bool matches = client_operation_connection == connection &&
                             client_operation_generation ==
                                 static_cast<std::uint32_t>(atomic_get(&gatt_session_generation));
        k_spin_unlock(&client_token_lock, key);
        return matches && currentGattConnection(connection);
    }

    /** @brief 현재 client operation token을 회수합니다. */
    void clearClientOperationToken() noexcept
    {
        k_spinlock_key_t key = k_spin_lock(&client_token_lock);
        client_operation_connection = nullptr;
        client_operation_generation = 0U;
        k_spin_unlock(&client_token_lock, key);
    }

    /** @brief 새 subscription의 connection/session token을 저장합니다. */
    void setClientSubscriptionToken(struct bt_conn *connection) noexcept
    {
        k_spinlock_key_t key = k_spin_lock(&client_token_lock);
        client_subscription_connection = connection;
        client_subscription_generation =
            static_cast<std::uint32_t>(atomic_get(&gatt_session_generation));
        k_spin_unlock(&client_token_lock, key);
    }

    /** @brief callback이 현재 subscription에 속하는지 검사합니다. */
    bool validClientSubscription(struct bt_conn *connection) noexcept
    {
        k_spinlock_key_t key = k_spin_lock(&client_token_lock);
        const bool matches = client_subscription_connection == connection &&
                             client_subscription_generation ==
                                 static_cast<std::uint32_t>(atomic_get(&gatt_session_generation));
        k_spin_unlock(&client_token_lock, key);
        return matches && currentGattConnection(connection);
    }

    /** @brief 현재 subscription token을 회수합니다. */
    void clearClientSubscriptionToken() noexcept
    {
        k_spinlock_key_t key = k_spin_lock(&client_token_lock);
        client_subscription_connection = nullptr;
        client_subscription_generation = 0U;
        k_spin_unlock(&client_token_lock, key);
    }

    /** @brief CCC attribute가 소유한 characteristic을 찾습니다. */
    BLECharacteristic *findCccOwner(const struct bt_gatt_attr *attribute) noexcept
    {
        for (std::size_t service_index = 0U; service_index < registered_service_count;
             ++service_index)
        {
            ServiceSlot &slot = service_slots[service_index];
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

    /** @brief cached characteristic value를 stack read deadline 안에서 반환합니다. */
    ssize_t serverRead(struct bt_conn *connection, const struct bt_gatt_attr *attribute,
                       void *buffer, std::uint16_t length, std::uint16_t offset) noexcept
    {
        BLECharacteristic *characteristic = static_cast<BLECharacteristic *>(attribute->user_data);
        if (characteristic == nullptr)
        {
            return BT_GATT_ERR(BT_ATT_ERR_UNLIKELY);
        }
        if (!currentGattConnection(connection))
        {
            return BT_GATT_ERR(BT_ATT_ERR_UNLIKELY);
        }
        std::uint8_t snapshot[maximum_value_length] = {};
        const std::size_t snapshot_length =
            copyCachedValue(*characteristic, snapshot, sizeof(snapshot));
        return bt_gatt_attr_read(connection, attribute, buffer, length, offset, snapshot,
                                 snapshot_length);
    }

    /** @brief peer write를 cached buffer와 bounded main-thread event로 복사합니다. */
    ssize_t serverWrite(struct bt_conn *connection, const struct bt_gatt_attr *attribute,
                        const void *buffer, std::uint16_t length, std::uint16_t offset,
                        std::uint8_t flags) noexcept
    {
        ARG_UNUSED(connection);
        BLECharacteristic *characteristic = static_cast<BLECharacteristic *>(attribute->user_data);
        if (characteristic == nullptr || (buffer == nullptr && length != 0U))
        {
            return BT_GATT_ERR(BT_ATT_ERR_UNLIKELY);
        }
        if (!currentGattConnection(connection))
        {
            return BT_GATT_ERR(BT_ATT_ERR_UNLIKELY);
        }
        if ((flags & (BT_GATT_WRITE_FLAG_PREPARE | BT_GATT_WRITE_FLAG_EXECUTE)) != 0U)
        {
            return BT_GATT_ERR(BT_ATT_ERR_NOT_SUPPORTED);
        }
        if (offset > GattAccess::capacity(*characteristic))
        {
            return BT_GATT_ERR(BT_ATT_ERR_INVALID_OFFSET);
        }
        if (static_cast<std::size_t>(offset) + length > GattAccess::capacity(*characteristic))
        {
            return BT_GATT_ERR(BT_ATT_ERR_INVALID_ATTRIBUTE_LEN);
        }
        k_spinlock_key_t key = k_spin_lock(&characteristic_value_lock);
        if (length != 0U)
        {
            ::memcpy(GattAccess::value(*characteristic) + offset, buffer, length);
        }
        const std::size_t new_length = offset == 0U
                                           ? length
                                           : MAX(GattAccess::length(*characteristic),
                                                 static_cast<std::size_t>(offset) + length);
        GattAccess::setLength(*characteristic, new_length);
        k_spin_unlock(&characteristic_value_lock, key);
        queueServerEvent(*characteristic, BLECharacteristicEvent::written, buffer, length, offset,
                         (flags & BT_GATT_WRITE_FLAG_CMD) != 0U);
        return length;
    }

    /** @brief connection별 CCC 변경을 main-thread event로 변환합니다. */
    void cccChanged(const struct bt_gatt_attr *attribute, std::uint16_t value) noexcept
    {
        if (atomic_get(&gatt_link_active) == 0)
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
            token_generation == static_cast<std::uint32_t>(atomic_get(&gatt_session_generation)) &&
            currentGattConnection(connection))
        {
            queueServerEvent(*notification->characteristic,
                             BLECharacteristicEvent::notification_sent);
        }
    }

    /** @brief indication params가 소유한 characteristic 위치를 찾습니다. */
    bool findIndication(struct bt_gatt_indicate_params *parameters, ServiceSlot *&slot,
                        std::size_t &index) noexcept
    {
        for (std::size_t service_index = 0U; service_index < registered_service_count;
             ++service_index)
        {
            ServiceSlot &candidate = service_slots[service_index];
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
                static_cast<std::uint32_t>(atomic_get(&gatt_session_generation)) ||
            !currentGattConnection(connection))
        {
            return;
        }
        queueServerEvent(*slot->characteristics[index],
                         error == 0U ? BLECharacteristicEvent::indication_confirmed
                                     : BLECharacteristicEvent::indication_failed,
                         nullptr, 0U, 0U, false, -static_cast<int>(error));
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

    /** @brief client operation 실패 상태와 main-thread event를 함께 기록합니다. */
    void failClient(int driver_error, std::uint8_t att_error = 0U) noexcept
    {
        clearClientOperationToken();
        atomic_set(&client_last_att_error, att_error);
        atomic_set(&client_busy_value, 0);
        atomic_set(&client_stage, static_cast<atomic_val_t>(ClientStage::idle));
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
        k_spinlock_key_t key = k_spin_lock(&client_state_lock);
        GattAccess::set(remote_service, target_service_uuid, attribute->handle, value->end_handle);
        k_spin_unlock(&client_state_lock, key);
        atomic_set(&client_stage, static_cast<atomic_val_t>(ClientStage::service_found));
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
        k_spinlock_key_t key = k_spin_lock(&client_state_lock);
        GattAccess::set(remote_characteristic, target_characteristic_uuid, attribute->handle,
                        value->value_handle, publicProperties(value->properties));
        k_spin_unlock(&client_state_lock, key);
        atomic_set(&client_stage, static_cast<atomic_val_t>(ClientStage::characteristic_found));
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
        k_spinlock_key_t key = k_spin_lock(&client_state_lock);
        GattAccess::setCcc(remote_characteristic, attribute->handle);
        k_spin_unlock(&client_state_lock, key);
        atomic_set(&client_stage, static_cast<atomic_val_t>(ClientStage::ccc_found));
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
            atomic_set(&client_busy_value, 0);
            queueClientEvent(BLEGattClientEvent::read_complete, data, length);
            return BT_GATT_ITER_STOP;
        }
        clearClientOperationToken();
        atomic_set(&client_busy_value, 0);
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
        atomic_set(&client_busy_value, 0);
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
        atomic_set(&client_busy_value, 0);
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
            atomic_set(&client_subscribed, 0);
            atomic_set(&client_subscription_value, 0);
            clearClientSubscriptionToken();
            failClient(-EIO, error);
            return;
        }
        if (parameters == nullptr)
        {
            atomic_set(&client_subscribed, 0);
            atomic_set(&client_subscription_value, 0);
            clearClientSubscriptionToken();
            failClient(-EINVAL);
            return;
        }
        if (parameters->value == 0U)
        {
            atomic_set(&client_subscribed, 0);
            atomic_set(&client_busy_value, 0);
            return;
        }
        atomic_set(&client_subscribed, 1);
        atomic_set(&client_subscription_value, parameters->value);
        atomic_set(&client_busy_value, 0);
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
            atomic_set(&client_subscribed, 0);
            atomic_set(&client_subscription_value, 0);
            clearClientSubscriptionToken();
            atomic_set(&client_busy_value, 0);
            queueClientEvent(BLEGattClientEvent::unsubscribed);
            return BT_GATT_ITER_STOP;
        }
        queueClientEvent(atomic_get(&client_subscription_value) == BT_GATT_CCC_INDICATE
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
        atomic_set(&client_stage,
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
            atomic_set(&client_stage, static_cast<atomic_val_t>(ClientStage::ready));
            clearClientOperationToken();
            atomic_set(&client_busy_value, 0);
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
        atomic_set(&client_stage, static_cast<atomic_val_t>(ClientStage::discovering_ccc));
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
        if (atomic_cas(&client_stage, static_cast<atomic_val_t>(ClientStage::service_found),
                       static_cast<atomic_val_t>(ClientStage::discovering_characteristic)))
        {
            continueCharacteristicDiscovery();
            return;
        }
        if (atomic_cas(&client_stage, static_cast<atomic_val_t>(ClientStage::characteristic_found),
                       static_cast<atomic_val_t>(ClientStage::discovering_ccc)))
        {
            continueCccDiscovery();
            return;
        }
        if (atomic_cas(&client_stage, static_cast<atomic_val_t>(ClientStage::ccc_found),
                       static_cast<atomic_val_t>(ClientStage::ready)))
        {
            clearClientOperationToken();
            atomic_set(&client_busy_value, 0);
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
        if (atomic_get(&client_stage) != static_cast<atomic_val_t>(ClientStage::ready) ||
            !characteristic.valid() || characteristic.cccHandle() == 0U)
        {
            nucode::ble::internal::recordError(BLEError::wrong_state, -EPERM, true);
            return false;
        }
        if (!atomic_cas(&client_busy_value, 0, 1))
        {
            nucode::ble::internal::recordError(BLEError::busy, -EBUSY, true);
            return false;
        }
        if (atomic_get(&client_subscribed) != 0)
        {
            atomic_set(&client_busy_value, 0);
            nucode::ble::internal::recordError(BLEError::already_started, -EALREADY, true);
            return false;
        }
        struct bt_conn *connection = nucode::ble::internal::referenceConnection();
        if (connection == nullptr)
        {
            atomic_set(&client_busy_value, 0);
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
        atomic_set(&client_subscription_value, value);
        setClientSubscriptionToken(connection);
        const int result = bt_gatt_subscribe(connection, &subscribe_parameters);
        bt_conn_unref(connection);
        if (result < 0)
        {
            atomic_set(&client_busy_value, 0);
            atomic_set(&client_subscription_value, 0);
            clearClientSubscriptionToken();
            nucode::ble::internal::recordError(BLEError::driver_error, result, true);
            return false;
        }
        return true;
    }

} // namespace

namespace nucode::ble::internal
{

    bool addGattService(BLEService &service) noexcept
    {
        k_mutex_lock(&gatt_schema_mutex, K_FOREVER);
        if (stackReady() || atomic_get(&database_registered) != 0 ||
            GattAccess::registered(service))
        {
            k_mutex_unlock(&gatt_schema_mutex);
            recordError(BLEError::wrong_state, -EPERM, true);
            return false;
        }
        BLEUuid &uuid = GattAccess::uuid(service);
        if (!uuid.valid() || uuid.type() == BLEUuid::Type::uuid32)
        {
            k_mutex_unlock(&gatt_schema_mutex);
            recordError(BLEError::invalid_argument, -EINVAL, true);
            return false;
        }
        for (std::size_t index = 0U; index < registered_service_count; ++index)
        {
            if (registered_services[index] == &service ||
                GattAccess::uuid(*registered_services[index]) == uuid)
            {
                k_mutex_unlock(&gatt_schema_mutex);
                recordError(BLEError::duplicate, -EEXIST, true);
                return false;
            }
        }
        if (registered_service_count >= maximum_services)
        {
            k_mutex_unlock(&gatt_schema_mutex);
            recordError(BLEError::schema_full, -ENOSPC, true);
            return false;
        }
        registered_services[registered_service_count++] = &service;
        k_mutex_unlock(&gatt_schema_mutex);
        return true;
    }

    bool hasGattSchema() noexcept
    {
        return registered_service_count != 0U;
    }

    int prepareGattDatabase() noexcept
    {
        k_mutex_lock(&gatt_schema_mutex, K_FOREVER);
        if (atomic_get(&database_registered) != 0)
        {
            k_mutex_unlock(&gatt_schema_mutex);
            return 0;
        }
        if (stackReady() && registered_service_count != 0U)
        {
            k_mutex_unlock(&gatt_schema_mutex);
            return -EPERM;
        }

        /** @brief 모든 schema를 먼저 검증·구성한 뒤에만 stack에 노출합니다. */
        for (std::size_t service_index = 0U; service_index < registered_service_count;
             ++service_index)
        {
            BLEService &owner = *registered_services[service_index];
            ServiceSlot &slot = service_slots[service_index];
            slot.owner = &owner;
            slot.characteristic_count = GattAccess::characteristicCount(owner);
            if (slot.characteristic_count > CONFIG_NUCODE_BLE_GATT_MAX_CHARACTERISTICS_PER_SERVICE)
            {
                k_mutex_unlock(&gatt_schema_mutex);
                return -ENOSPC;
            }
            const struct bt_uuid *service_uuid = slot.service_uuid.assign(GattAccess::uuid(owner));
            if (service_uuid == nullptr)
            {
                k_mutex_unlock(&gatt_schema_mutex);
                return -EINVAL;
            }

            std::size_t attribute_index = 0U;
            struct bt_gatt_attr &service_attribute = slot.attributes[attribute_index++];
            service_attribute.uuid = BT_UUID_GATT_PRIMARY;
            service_attribute.perm = BT_GATT_PERM_READ;
            service_attribute.read = bt_gatt_attr_read_service;
            service_attribute.write = nullptr;
            service_attribute.user_data = const_cast<struct bt_uuid *>(service_uuid);

            for (std::size_t index = 0U; index < slot.characteristic_count; ++index)
            {
                BLECharacteristic *characteristic = GattAccess::characteristic(owner, index);
                if (characteristic == nullptr || !validCharacteristic(*characteristic))
                {
                    k_mutex_unlock(&gatt_schema_mutex);
                    return -EINVAL;
                }
                for (std::size_t previous = 0U; previous < index; ++previous)
                {
                    if (GattAccess::uuid(*slot.characteristics[previous]) ==
                        GattAccess::uuid(*characteristic))
                    {
                        k_mutex_unlock(&gatt_schema_mutex);
                        return -EEXIST;
                    }
                }
                slot.characteristics[index] = characteristic;
                const struct bt_uuid *characteristic_uuid =
                    slot.characteristic_uuids[index].assign(GattAccess::uuid(*characteristic));
                if (characteristic_uuid == nullptr)
                {
                    k_mutex_unlock(&gatt_schema_mutex);
                    return -EINVAL;
                }

                slot.declarations[index].uuid = characteristic_uuid;
                slot.declarations[index].value_handle = 0U;
                slot.declarations[index].properties =
                    zephyrProperties(GattAccess::properties(*characteristic));

                struct bt_gatt_attr &declaration = slot.attributes[attribute_index++];
                declaration.uuid = BT_UUID_GATT_CHRC;
                declaration.perm = BT_GATT_PERM_READ;
                declaration.read = bt_gatt_attr_read_chrc;
                declaration.write = nullptr;
                declaration.user_data = &slot.declarations[index];

                slot.value_attribute_index[index] = attribute_index;
                struct bt_gatt_attr &value_attribute = slot.attributes[attribute_index++];
                value_attribute.uuid = characteristic_uuid;
                value_attribute.perm = zephyrPermissions(GattAccess::permissions(*characteristic));
                value_attribute.read =
                    hasProperty(GattAccess::properties(*characteristic), BLEProperty::read)
                        ? serverRead
                        : nullptr;
                value_attribute.write =
                    hasProperty(GattAccess::properties(*characteristic), BLEProperty::write) ||
                            hasProperty(GattAccess::properties(*characteristic),
                                        BLEProperty::write_without_response)
                        ? serverWrite
                        : nullptr;
                value_attribute.user_data = characteristic;

                if (hasProperty(GattAccess::properties(*characteristic), BLEProperty::notify) ||
                    hasProperty(GattAccess::properties(*characteristic), BLEProperty::indicate))
                {
                    slot.ccc[index].cfg_changed = cccChanged;
                    slot.ccc[index].cfg_write = nullptr;
                    slot.ccc[index].cfg_match = nullptr;
                    slot.ccc_attribute_index[index] = attribute_index;
                    struct bt_gatt_attr &ccc_attribute = slot.attributes[attribute_index++];
                    ccc_attribute.uuid = BT_UUID_GATT_CCC;
                    ccc_attribute.perm = BT_GATT_PERM_READ | BT_GATT_PERM_WRITE;
                    ccc_attribute.read = bt_gatt_attr_read_ccc;
                    ccc_attribute.write = bt_gatt_attr_write_ccc;
                    ccc_attribute.user_data = &slot.ccc[index];
                }
                else
                {
                    slot.ccc_attribute_index[index] = 0U;
                }
            }

            slot.service.attrs = slot.attributes;
            slot.service.attr_count = attribute_index;
        }

        std::size_t registered_count = 0U;
        for (std::size_t service_index = 0U; service_index < registered_service_count;
             ++service_index)
        {
            ServiceSlot &slot = service_slots[service_index];
            const int result = bt_gatt_service_register(&slot.service);
            if (result < 0)
            {
                for (std::size_t rollback = 0U; rollback < registered_count; ++rollback)
                {
                    static_cast<void>(bt_gatt_service_unregister(&service_slots[rollback].service));
                    GattAccess::setRegistered(*service_slots[rollback].owner, false);
                    for (std::size_t index = 0U;
                         index < service_slots[rollback].characteristic_count; ++index)
                    {
                        GattAccess::setRegistered(*service_slots[rollback].characteristics[index],
                                                  false);
                    }
                }
                k_mutex_unlock(&gatt_schema_mutex);
                return result;
            }
            ++registered_count;
            GattAccess::setRegistered(*slot.owner, true);
            for (std::size_t index = 0U; index < slot.characteristic_count; ++index)
            {
                GattAccess::setRegistered(*slot.characteristics[index], true);
            }
        }
        atomic_set(&database_registered, 1);
        k_mutex_unlock(&gatt_schema_mutex);
        return 0;
    }

    void pollGatt() noexcept
    {
        GattEventRecord record = {};
        while (k_msgq_get(&gatt_event_queue, &record, K_NO_WAIT) == 0)
        {
            if (record.generation !=
                static_cast<std::uint32_t>(atomic_get(&gatt_session_generation)))
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
                     client_callback != nullptr)
            {
                client_callback(record.client_event, record.length == 0U ? nullptr : record.data,
                                record.length, client_context);
            }
        }
        progressClientDiscovery();
    }

    void gattConnected(struct bt_conn *connection, std::uint32_t generation) noexcept
    {
        k_spinlock_key_t key = k_spin_lock(&client_token_lock);
        gatt_connection = connection;
        gatt_connection_generation = generation;
        k_spin_unlock(&client_token_lock, key);
        atomic_set(&gatt_link_active, 1);
    }

    void gattDisconnected(struct bt_conn *connection, std::uint32_t generation) noexcept
    {
        k_spinlock_key_t token_key = k_spin_lock(&client_token_lock);
        const bool matches =
            gatt_connection == connection && gatt_connection_generation == generation;
        if (matches)
        {
            gatt_connection = nullptr;
            gatt_connection_generation = 0U;
        }
        k_spin_unlock(&client_token_lock, token_key);
        if (!matches)
        {
            return;
        }
        atomic_set(&client_stage, static_cast<atomic_val_t>(ClientStage::idle));
        atomic_set(&gatt_link_active, 0);
        atomic_inc(&gatt_session_generation);
        k_msgq_purge(&gatt_event_queue);
        k_spinlock_key_t key = k_spin_lock(&client_state_lock);
        const bool had_handles = remote_service.valid() || remote_characteristic.valid() ||
                                 atomic_get(&client_subscribed) != 0 ||
                                 atomic_get(&client_busy_value) != 0;
        GattAccess::clear(remote_service);
        GattAccess::clear(remote_characteristic);
        k_spin_unlock(&client_state_lock, key);
        atomic_set(&client_busy_value, 0);
        atomic_set(&client_subscribed, 0);
        atomic_set(&client_subscription_value, 0);
        clearClientOperationToken();
        clearClientSubscriptionToken();
        if (had_handles)
        {
            queueClientEvent(BLEGattClientEvent::handles_invalidated);
        }
    }

    void gattEnded() noexcept
    {
        atomic_set(&client_stage, static_cast<atomic_val_t>(ClientStage::idle));
        atomic_set(&gatt_link_active, 0);
        atomic_inc(&gatt_session_generation);
        k_msgq_purge(&gatt_event_queue);
        k_spinlock_key_t key = k_spin_lock(&client_state_lock);
        GattAccess::clear(remote_service);
        GattAccess::clear(remote_characteristic);
        k_spin_unlock(&client_state_lock, key);
        atomic_set(&client_busy_value, 0);
        atomic_set(&client_subscribed, 0);
        atomic_set(&client_subscription_value, 0);
        clearClientOperationToken();
        clearClientSubscriptionToken();
        k_spinlock_key_t token_key = k_spin_lock(&client_token_lock);
        gatt_connection = nullptr;
        gatt_connection_generation = 0U;
        k_spin_unlock(&client_token_lock, token_key);
    }

} // namespace nucode::ble::internal

namespace nucode::ble
{

    BLECharacteristic::BLECharacteristic(const BLEUuid &uuid, BLEProperty properties,
                                         BLEPermission permissions, std::size_t capacity) noexcept
        : uuid_(uuid), properties_(properties), permissions_(permissions),
          value_(capacity <= maximum_value_length ? internal_value_ : nullptr),
          capacity_(capacity <= maximum_value_length ? capacity : 0U)
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
        k_spinlock_key_t key = k_spin_lock(&characteristic_value_lock);
        const std::size_t length = value_length_;
        k_spin_unlock(&characteristic_value_lock, key);
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
        k_spinlock_key_t key = k_spin_lock(&characteristic_value_lock);
        if (length != 0U)
        {
            ::memcpy(value_, data, length);
        }
        value_length_ = length;
        k_spin_unlock(&characteristic_value_lock, key);
        return true;
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
        struct bt_conn *connection = internal::referenceConnection();
        if (connection == nullptr)
        {
            return false;
        }
        const bool subscribed = bt_gatt_is_subscribed(
            connection, &slot->attributes[slot->value_attribute_index[index]], BT_GATT_CCC_NOTIFY);
        bt_conn_unref(connection);
        return subscribed;
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
        struct bt_conn *connection = internal::referenceConnection();
        if (connection == nullptr)
        {
            return false;
        }
        const bool subscribed =
            bt_gatt_is_subscribed(connection, &slot->attributes[slot->value_attribute_index[index]],
                                  BT_GATT_CCC_INDICATE);
        bt_conn_unref(connection);
        return subscribed;
    }

    bool BLECharacteristic::notify() noexcept
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
        struct bt_conn *connection = internal::referenceConnection();
        if (connection == nullptr)
        {
            atomic_set(&slot->notification_active[index], 0);
            internal::recordError(BLEError::not_connected, -ENOTCONN, true);
            return false;
        }
        const struct bt_gatt_attr *attribute =
            &slot->attributes[slot->value_attribute_index[index]];
        const bool subscribed = bt_gatt_is_subscribed(connection, attribute, BT_GATT_CCC_NOTIFY);
        const std::size_t mtu = bt_gatt_get_mtu(connection);
        std::uint8_t snapshot[maximum_value_length] = {};
        const std::size_t snapshot_length = copyCachedValue(*this, snapshot, sizeof(snapshot));
        if (!subscribed || mtu < 3U || snapshot_length > mtu - 3U)
        {
            bt_conn_unref(connection);
            atomic_set(&slot->notification_active[index], 0);
            internal::recordError(subscribed ? BLEError::value_overflow : BLEError::wrong_state,
                                  subscribed ? -EMSGSIZE : -EPERM, true);
            return false;
        }
        NotificationContext &notification = slot->notifications[index];
        notification.characteristic = this;
        notification.connection = connection;
        notification.generation = static_cast<std::uint32_t>(atomic_get(&gatt_session_generation));
        struct bt_gatt_notify_params parameters = {
            .uuid = nullptr,
            .attr = attribute,
            .data = snapshot,
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
        struct bt_conn *connection = internal::referenceConnection();
        if (connection == nullptr)
        {
            atomic_set(&slot->indication_active[index], 0);
            internal::recordError(BLEError::not_connected, -ENOTCONN, true);
            return false;
        }
        const struct bt_gatt_attr *attribute =
            &slot->attributes[slot->value_attribute_index[index]];
        const bool subscribed = bt_gatt_is_subscribed(connection, attribute, BT_GATT_CCC_INDICATE);
        const std::size_t mtu = bt_gatt_get_mtu(connection);
        const std::size_t snapshot_length =
            copyCachedValue(*this, slot->indication_data[index], maximum_value_length);
        if (!subscribed || mtu < 3U || snapshot_length > mtu - 3U)
        {
            bt_conn_unref(connection);
            atomic_set(&slot->indication_active[index], 0);
            internal::recordError(subscribed ? BLEError::value_overflow : BLEError::wrong_state,
                                  subscribed ? -EMSGSIZE : -EPERM, true);
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
            static_cast<std::uint32_t>(atomic_get(&gatt_session_generation));
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

    BLEService::BLEService(const BLEUuid &uuid) noexcept : uuid_(uuid)
    {
    }

    const BLEUuid &BLEService::uuid() const noexcept
    {
        return uuid_;
    }

    bool BLEService::addCharacteristic(BLECharacteristic &characteristic) noexcept
    {
        if (!internal::requireThreadContext())
        {
            return false;
        }
        if (registered_ || internal::stackReady())
        {
            internal::recordError(BLEError::wrong_state, -EPERM, true);
            return false;
        }
        if (!validCharacteristic(characteristic))
        {
            internal::recordError(BLEError::invalid_argument, -EINVAL, true);
            return false;
        }
        for (std::size_t index = 0U; index < characteristic_count_; ++index)
        {
            if (characteristics_[index] == &characteristic ||
                characteristics_[index]->uuid() == characteristic.uuid())
            {
                internal::recordError(BLEError::duplicate, -EEXIST, true);
                return false;
            }
        }
        if (characteristic_count_ >= maximum_characteristics)
        {
            internal::recordError(BLEError::schema_full, -ENOSPC, true);
            return false;
        }
        characteristics_[characteristic_count_++] = &characteristic;
        return true;
    }

    std::size_t BLEService::characteristicCount() const noexcept
    {
        return characteristic_count_;
    }

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
        if (!atomic_cas(&client_busy_value, 0, 1))
        {
            internal::recordError(BLEError::busy, -EBUSY, true);
            return false;
        }
        struct bt_conn *connection = internal::referenceConnection();
        if (connection == nullptr)
        {
            atomic_set(&client_busy_value, 0);
            internal::recordError(BLEError::not_connected, -ENOTCONN, true);
            return false;
        }

        target_service_uuid = service_uuid;
        target_characteristic_uuid = characteristic_uuid;
        k_spinlock_key_t key = k_spin_lock(&client_state_lock);
        GattAccess::clear(remote_service);
        GattAccess::clear(remote_characteristic);
        k_spin_unlock(&client_state_lock, key);
        atomic_set(&client_subscribed, 0);
        atomic_set(&client_subscription_value, 0);
        atomic_set(&client_last_att_error, 0);
        ::memset(&discovery_parameters, 0, sizeof(discovery_parameters));
        discovery_parameters.uuid = target_service_zephyr_uuid.assign(service_uuid);
        discovery_parameters.func = serviceDiscovered;
        discovery_parameters.start_handle = BT_ATT_FIRST_ATTRIBUTE_HANDLE;
        discovery_parameters.end_handle = BT_ATT_LAST_ATTRIBUTE_HANDLE;
        discovery_parameters.type = BT_GATT_DISCOVER_PRIMARY;
        atomic_set(&client_stage, static_cast<atomic_val_t>(ClientStage::discovering_service));
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
        if (atomic_get(&client_stage) != static_cast<atomic_val_t>(ClientStage::ready))
        {
            return false;
        }
        BLERemoteService service;
        BLERemoteCharacteristic characteristic;
        copyRemoteHandles(service, characteristic);
        return atomic_get(&client_stage) == static_cast<atomic_val_t>(ClientStage::ready) &&
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
        if (!atomic_cas(&client_busy_value, 0, 1))
        {
            internal::recordError(BLEError::busy, -EBUSY, true);
            return false;
        }
        struct bt_conn *connection = internal::referenceConnection();
        if (connection == nullptr)
        {
            atomic_set(&client_busy_value, 0);
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
            atomic_set(&client_busy_value, 0);
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
        if (!atomic_cas(&client_busy_value, 0, 1))
        {
            internal::recordError(BLEError::busy, -EBUSY, true);
            return false;
        }
        struct bt_conn *connection = internal::referenceConnection();
        if (connection == nullptr)
        {
            atomic_set(&client_busy_value, 0);
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
            atomic_set(&client_busy_value, 0);
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
        if (!atomic_cas(&client_busy_value, 0, 1))
        {
            internal::recordError(BLEError::busy, -EBUSY, true);
            return false;
        }
        struct bt_conn *connection = internal::referenceConnection();
        if (connection == nullptr)
        {
            atomic_set(&client_busy_value, 0);
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
            atomic_set(&client_busy_value, 0);
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
        if (atomic_get(&client_subscribed) == 0)
        {
            internal::recordError(BLEError::wrong_state, -EPERM, true);
            return false;
        }
        if (!atomic_cas(&client_busy_value, 0, 1))
        {
            internal::recordError(BLEError::busy, -EBUSY, true);
            return false;
        }
        struct bt_conn *connection = internal::referenceConnection();
        if (connection == nullptr)
        {
            atomic_set(&client_busy_value, 0);
            internal::recordError(BLEError::not_connected, -ENOTCONN, true);
            return false;
        }
        const int result = bt_gatt_unsubscribe(connection, &subscribe_parameters);
        bt_conn_unref(connection);
        if (result < 0)
        {
            atomic_set(&client_busy_value, 0);
            internal::recordError(BLEError::driver_error, result, true);
            return false;
        }
        return true;
    }

    bool GattClient::busy() const noexcept
    {
        return atomic_get(&client_busy_value) != 0;
    }

    std::uint8_t GattClient::lastAttError() const noexcept
    {
        return static_cast<std::uint8_t>(atomic_get(&client_last_att_error));
    }

    void GattClient::onEvent(BLEGattClientCallback callback, void *context) noexcept
    {
        if (!internal::requireThreadContext())
        {
            return;
        }
        client_callback = callback;
        client_context = context;
    }

} // namespace nucode::ble

nucode::ble::GattClient BLEClient;

#endif
