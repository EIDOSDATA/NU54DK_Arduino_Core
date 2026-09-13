/** @file @brief GATT private 상태 소유와 database/server/client 경계입니다.
 * SPDX-License-Identifier: MIT
 */
#pragma once
#include <NUCODE_BLE_GATT.h>

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

        static bool authorize(BLECharacteristic &characteristic,
                              const BLEGattAuthorizationRequest &request) noexcept
        {
            return characteristic.authorization_callback_ == nullptr ||
                   characteristic.authorization_callback_(
                       request, characteristic.authorization_context_);
        }

        static bool hasAuthorization(const BLECharacteristic &characteristic) noexcept
        {
            return characteristic.authorization_callback_ != nullptr;
        }

        static std::size_t descriptorCount(const BLECharacteristic &characteristic) noexcept
        {
            return characteristic.descriptor_count_;
        }

        static BLEDescriptor *descriptor(BLECharacteristic &characteristic,
                                         std::size_t index) noexcept
        {
            return characteristic.descriptors_[index];
        }

        static BLEUuid &uuid(BLEDescriptor &descriptor) noexcept
        {
            return descriptor.uuid_;
        }

        static BLEPermission permissions(const BLEDescriptor &descriptor) noexcept
        {
            return descriptor.permissions_;
        }

        static std::uint8_t *value(BLEDescriptor &descriptor) noexcept
        {
            return descriptor.value_;
        }

        static const std::uint8_t *value(const BLEDescriptor &descriptor) noexcept
        {
            return descriptor.value_;
        }

        static std::size_t capacity(const BLEDescriptor &descriptor) noexcept
        {
            return descriptor.capacity_;
        }

        static std::size_t length(const BLEDescriptor &descriptor) noexcept
        {
            return descriptor.value_length_;
        }

        static void setLength(BLEDescriptor &descriptor, std::size_t length) noexcept
        {
            descriptor.value_length_ = length;
        }

        static bool registered(const BLEDescriptor &descriptor) noexcept
        {
            return descriptor.registered_;
        }

        static void setRegistered(BLEDescriptor &descriptor, bool registered) noexcept
        {
            descriptor.registered_ = registered;
        }

        static bool authorize(BLEDescriptor &descriptor,
                              const BLEGattAuthorizationRequest &request) noexcept
        {
            return descriptor.authorization_callback_ == nullptr ||
                   descriptor.authorization_callback_(request,
                                                       descriptor.authorization_context_);
        }

        static bool hasAuthorization(const BLEDescriptor &descriptor) noexcept
        {
            return descriptor.authorization_callback_ != nullptr;
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

        static void clear(BLERemoteDescriptor &descriptor) noexcept
        {
            descriptor.uuid_ = BLEUuid{};
            descriptor.handle_ = 0U;
            descriptor.valid_ = false;
        }

        static void set(BLERemoteDescriptor &descriptor, const BLEUuid &uuid,
                        std::uint16_t handle) noexcept
        {
            descriptor.uuid_ = uuid;
            descriptor.handle_ = handle;
            descriptor.valid_ = true;
        }
    };

} // namespace nucode::ble::internal

namespace nucode::ble::internal::gatt
{
    using nucode::ble::BLECharacteristic;
    using nucode::ble::BLECharacteristicEvent;
    using nucode::ble::BLECharacteristicEventInfo;
    using nucode::ble::BLEDescriptor;
    using nucode::ble::BLEError;
    using nucode::ble::BLEGattAuthorizationOperation;
    using nucode::ble::BLEGattAuthorizationRequest;
    using nucode::ble::BLEGattClientCallback;
    using nucode::ble::BLEGattClientEvent;
    using nucode::ble::BLEGattClientInfoCallback;
    using nucode::ble::BLEPermission;
    using nucode::ble::BLEProperty;
    using nucode::ble::BLERemoteCharacteristic;
    using nucode::ble::BLERemoteDescriptor;
    using nucode::ble::BLERemoteService;
    using nucode::ble::BLEService;
    using nucode::ble::BLEUuid;
    using nucode::ble::internal::GattAccess;

    inline constexpr std::size_t maximum_services = CONFIG_NUCODE_BLE_GATT_MAX_SERVICES;
    inline constexpr std::size_t maximum_characteristics = BLEService::maximum_characteristics;
    inline constexpr std::size_t maximum_descriptors = BLECharacteristic::maximum_descriptors;
    inline constexpr std::size_t maximum_attributes =
        1U + maximum_characteristics * (3U + maximum_descriptors);
    inline constexpr std::size_t maximum_value_length = BLECharacteristic::maximum_value_length;

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
        ZephyrUuid descriptor_uuids[maximum_characteristics][maximum_descriptors] = {};
        struct bt_gatt_service service = {};
        struct bt_gatt_attr attributes[maximum_attributes] = {};
        struct bt_gatt_chrc declarations[maximum_characteristics] = {};
        struct bt_gatt_ccc_managed_user_data ccc[maximum_characteristics] = {};
        BLECharacteristic *characteristics[maximum_characteristics] = {};
        BLEDescriptor *descriptors[maximum_characteristics][maximum_descriptors] = {};
        NotificationContext notifications[maximum_characteristics] = {};
        std::uint8_t notification_data[maximum_characteristics][maximum_value_length] = {};
        atomic_t notification_active[maximum_characteristics] = {};
        struct bt_gatt_indicate_params indications[maximum_characteristics] = {};
        std::uint8_t indication_data[maximum_characteristics][maximum_value_length] = {};
        atomic_t indication_active[maximum_characteristics] = {};
        struct bt_conn *indication_connections[maximum_characteristics] = {};
        std::uint32_t indication_generations[maximum_characteristics] = {};
        std::size_t value_attribute_index[maximum_characteristics] = {};
        std::size_t ccc_attribute_index[maximum_characteristics] = {};
        std::size_t descriptor_attribute_index[maximum_characteristics][maximum_descriptors] = {};
        std::size_t descriptor_count[maximum_characteristics] = {};
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
        BLEConnectionHandle connection;
        BLECharacteristic *characteristic;
        BLEDescriptor *descriptor;
        BLECharacteristicEvent server_event;
        BLEGattAuthorizationOperation authorization_operation;
        BLEGattClientEvent client_event;
        std::uint16_t length;
        std::uint16_t offset;
        bool without_response;
        std::uint8_t att_error;
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

    /** @brief database의 고정 schema·slot 상태입니다. */
    struct DatabaseState
    {
        BLEService *registered_services[maximum_services] = {};
        std::size_t registered_service_count = 0U;
        atomic_t database_registered = ATOMIC_INIT(0);
    };
    DatabaseState &databaseState() noexcept;
    /** @brief 사용된 server 경로만 slot 저장소를 참조하도록 별도로 소유합니다. */
    using ServiceSlots = ServiceSlot[maximum_services];
    ServiceSlots &serviceSlots() noexcept;
    inline constexpr std::size_t maximum_prepare_transactions = 2U;

    /** @brief link 하나의 long write prepare 범위를 고정 상태로 소유합니다. */
    struct PrepareTransaction
    {
        struct bt_conn *connection = nullptr;
        BLECharacteristic *characteristic = nullptr;
        std::uint32_t generation = 0U;
        std::uint16_t length = 0U;
    };

    /** @brief server 값 snapshot lock 상태입니다. */
    struct ServerState
    {
        struct k_spinlock characteristic_value_lock;
        PrepareTransaction prepare_transactions[maximum_prepare_transactions] = {};
    };
    ServerState &serverState() noexcept;

    /** @brief 해제된 link의 prepare transaction을 상수 시간에 폐기합니다. */
    void clearServerTransaction(struct bt_conn *connection) noexcept;

    /** @brief image session의 모든 prepare transaction을 폐기합니다. */
    void clearServerTransactions() noexcept;
    /** @brief GATT image session generation 상태입니다. */
    struct SessionState
    {
        atomic_t gatt_session_generation = ATOMIC_INIT(1);
    };
    SessionState &sessionState() noexcept;
    inline constexpr std::size_t maximum_client_contexts = 2U;

    /** @brief 공개 client callback은 두 link가 공유하고 event가 link를 식별합니다. */
    struct ClientCallbacks
    {
        BLEGattClientCallback legacy = nullptr;
        void *legacy_context = nullptr;
        BLEGattClientInfoCallback detailed = nullptr;
        void *detailed_context = nullptr;
    };

    /** @brief link 하나의 handle·operation·subscription 고정 상태입니다. */
    struct ClientState
    {
        struct k_spinlock client_state_lock;
        struct k_spinlock client_token_lock;
        atomic_t client_stage = ATOMIC_INIT(static_cast<atomic_val_t>(ClientStage::idle));
        atomic_t client_busy_value = ATOMIC_INIT(0);
        atomic_t client_subscribed = ATOMIC_INIT(0);
        atomic_t client_subscription_value = ATOMIC_INIT(0);
        atomic_t client_last_att_error = ATOMIC_INIT(0);
        atomic_t descriptor_boundary_ready = ATOMIC_INIT(0);
        BLERemoteService remote_service;
        BLERemoteCharacteristic remote_characteristic;
        BLERemoteDescriptor remote_descriptors[maximum_descriptors] = {};
        std::size_t remote_descriptor_count = 0U;
        BLEConnectionHandle connection_handle;
        BLEUuid target_service_uuid;
        BLEUuid target_characteristic_uuid;
        ZephyrUuid target_service_zephyr_uuid;
        ZephyrUuid target_characteristic_zephyr_uuid;
        BLEUuid target_descriptor_uuid;
        ZephyrUuid target_descriptor_zephyr_uuid;
        struct bt_gatt_discover_params discovery_parameters = {};
        struct bt_gatt_read_params read_parameters = {};
        struct bt_gatt_write_params write_parameters = {};
        struct bt_gatt_subscribe_params subscribe_parameters = {};
        std::uint8_t read_data[maximum_value_length] = {};
        std::uint16_t read_handles[maximum_descriptors] = {};
        std::uint16_t descriptor_end_handle = 0U;
        std::uint8_t write_data[maximum_value_length] = {};
        std::size_t read_length = 0U;
        bool read_multiple = false;
        struct bt_conn *client_operation_connection = nullptr;
        struct bt_conn *client_subscription_connection = nullptr;
        struct bt_conn *gatt_connection = nullptr;
    };
    using ClientStates = ClientState[maximum_client_contexts];
    ClientStates &clientStates() noexcept;
    ClientCallbacks &clientCallbacks() noexcept;
    /** @brief enum bit가 설정되었는지 검사합니다. */
    inline bool hasProperty(BLEProperty value, BLEProperty bit) noexcept
    {
        return (static_cast<std::uint8_t>(value) & static_cast<std::uint8_t>(bit)) != 0U;
    }

    /** @brief permission bit가 설정되었는지 검사합니다. */
    inline bool hasPermission(BLEPermission value, BLEPermission bit) noexcept
    {
        return (static_cast<std::uint8_t>(value) & static_cast<std::uint8_t>(bit)) != 0U;
    }

    /** @brief public property를 Zephyr characteristic bit로 변환합니다. */
    inline std::uint8_t zephyrProperties(BLEProperty properties) noexcept
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
    inline BLEProperty publicProperties(std::uint8_t properties) noexcept
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
    inline std::uint16_t zephyrPermissions(BLEPermission permissions) noexcept
    {
        std::uint16_t result = BT_GATT_PERM_NONE;
        if (hasPermission(permissions, BLEPermission::read))
        {
            result |= BT_GATT_PERM_READ;
        }
        if (hasPermission(permissions, BLEPermission::write))
        {
            result |= BT_GATT_PERM_WRITE | BT_GATT_PERM_PREPARE_WRITE;
        }
        return result;
    }

    /** @brief characteristic schema의 property/permission/buffer 일관성을 검사합니다. */
    inline bool validCharacteristic(const BLECharacteristic &characteristic) noexcept
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

    /** @brief descriptor schema의 UUID·permission·buffer 일관성을 검사합니다. */
    inline bool validDescriptor(const BLEDescriptor &descriptor) noexcept
    {
        const BLEPermission permissions = GattAccess::permissions(descriptor);
        return GattAccess::uuid(const_cast<BLEDescriptor &>(descriptor)).valid() &&
               GattAccess::uuid(const_cast<BLEDescriptor &>(descriptor)).type() !=
                   BLEUuid::Type::uuid32 &&
               GattAccess::value(const_cast<BLEDescriptor &>(descriptor)) != nullptr &&
               GattAccess::capacity(descriptor) != 0U &&
               GattAccess::capacity(descriptor) <= BLEDescriptor::maximum_value_length &&
               permissions != BLEPermission::none;
    }

    /** @brief 내부 module 간 호출이며 공개 Arduino API가 아닙니다. */
    bool queueGattEvent(const GattEventRecord &record) noexcept;
    void queueServerEvent(BLECharacteristic &characteristic, BLECharacteristicEvent event,
                          const void *data = nullptr, std::size_t length = 0U,
                          std::size_t offset = 0U, bool without_response = false,
                          int status = 0, struct bt_conn *connection = nullptr,
                          BLEDescriptor *descriptor = nullptr,
                          BLEGattAuthorizationOperation authorization_operation =
                              BLEGattAuthorizationOperation::read) noexcept;
    void queueClientEvent(ClientState &state, BLEGattClientEvent event,
                          const void *data = nullptr, std::size_t length = 0U,
                          std::size_t offset = 0U, int status = 0,
                          std::uint8_t att_error = 0U) noexcept;
    void queueInvalidatedEvent(BLEConnectionHandle connection) noexcept;
    BLEConnectionHandle handleForConnection(struct bt_conn *connection) noexcept;
    bool findCharacteristic(BLECharacteristic &owner, ServiceSlot *&slot,
                            std::size_t &characteristic_index) noexcept;
    std::size_t copyCachedValue(const BLECharacteristic &characteristic, void *output,
                                std::size_t capacity) noexcept;
    std::size_t copyDescriptorValue(const BLEDescriptor &descriptor, void *output,
                                    std::size_t capacity) noexcept;
    void copyRemoteHandles(ClientState &state, BLERemoteService &service,
                            BLERemoteCharacteristic &characteristic) noexcept;
    BLERemoteService copyRemoteService(ClientState &state) noexcept;
    BLERemoteCharacteristic copyRemoteCharacteristic(ClientState &state) noexcept;
    BLERemoteDescriptor copyRemoteDescriptor(ClientState &state, std::size_t index) noexcept;
    ClientState *findClientState(BLEConnectionHandle connection) noexcept;
    ClientState *legacyClientState() noexcept;
    ClientState *findDiscoveryState(struct bt_gatt_discover_params *parameters) noexcept;
    ClientState *findReadState(struct bt_gatt_read_params *parameters) noexcept;
    ClientState *findWriteState(struct bt_gatt_write_params *parameters) noexcept;
    ClientState *findSubscriptionState(struct bt_gatt_subscribe_params *parameters) noexcept;
    bool currentGattConnection(ClientState &state, struct bt_conn *connection) noexcept;
    void setClientOperationToken(ClientState &state, struct bt_conn *connection) noexcept;
    bool validClientOperation(ClientState &state, struct bt_conn *connection) noexcept;
    void clearClientOperationToken(ClientState &state) noexcept;
    void setClientSubscriptionToken(ClientState &state, struct bt_conn *connection) noexcept;
    bool validClientSubscription(ClientState &state, struct bt_conn *connection) noexcept;
    void clearClientSubscriptionToken(ClientState &state) noexcept;
    BLECharacteristic *findCccOwner(const struct bt_gatt_attr *attribute) noexcept;
    ssize_t serverRead(struct bt_conn *connection, const struct bt_gatt_attr *attribute,
                       void *buffer, std::uint16_t length, std::uint16_t offset) noexcept;
    ssize_t serverWrite(struct bt_conn *connection, const struct bt_gatt_attr *attribute,
                        const void *buffer, std::uint16_t length, std::uint16_t offset,
                        std::uint8_t flags) noexcept;
    ssize_t descriptorRead(struct bt_conn *connection, const struct bt_gatt_attr *attribute,
                           void *buffer, std::uint16_t length, std::uint16_t offset) noexcept;
    ssize_t descriptorWrite(struct bt_conn *connection, const struct bt_gatt_attr *attribute,
                            const void *buffer, std::uint16_t length, std::uint16_t offset,
                            std::uint8_t flags) noexcept;
    void cccChanged(const struct bt_gatt_attr *attribute, std::uint16_t value) noexcept;
    void notificationCompleted(struct bt_conn *connection, void *user_data) noexcept;
    bool findIndication(struct bt_gatt_indicate_params *parameters, ServiceSlot *&slot,
                        std::size_t &index) noexcept;
    void indicationCompleted(struct bt_conn *connection, struct bt_gatt_indicate_params *parameters,
                             std::uint8_t error) noexcept;
    void indicationDestroyed(struct bt_gatt_indicate_params *parameters) noexcept;
    void failClient(ClientState &state, int driver_error, std::uint8_t att_error = 0U) noexcept;
    std::uint8_t serviceDiscovered(struct bt_conn *connection, const struct bt_gatt_attr *attribute,
                                   struct bt_gatt_discover_params *parameters) noexcept;
    std::uint8_t characteristicDiscovered(struct bt_conn *connection,
                                          const struct bt_gatt_attr *attribute,
                                          struct bt_gatt_discover_params *parameters) noexcept;
    std::uint8_t cccDiscovered(struct bt_conn *connection, const struct bt_gatt_attr *attribute,
                               struct bt_gatt_discover_params *parameters) noexcept;
    std::uint8_t descriptorBoundaryDiscovered(
        struct bt_conn *connection, const struct bt_gatt_attr *attribute,
        struct bt_gatt_discover_params *parameters) noexcept;
    std::uint8_t descriptorDiscovered(struct bt_conn *connection,
                                      const struct bt_gatt_attr *attribute,
                                      struct bt_gatt_discover_params *parameters) noexcept;
    std::uint8_t clientReadCompleted(struct bt_conn *connection, std::uint8_t error,
                                     struct bt_gatt_read_params *parameters, const void *data,
                                     std::uint16_t length) noexcept;
    void clientWriteCompleted(struct bt_conn *connection, std::uint8_t error,
                              struct bt_gatt_write_params *parameters) noexcept;
    void clientWriteCommandCompleted(struct bt_conn *connection, void *user_data) noexcept;
    void clientSubscribeCompleted(struct bt_conn *connection, std::uint8_t error,
                                  struct bt_gatt_subscribe_params *parameters) noexcept;
    std::uint8_t clientNotification(struct bt_conn *connection,
                                    struct bt_gatt_subscribe_params *parameters, const void *data,
                                    std::uint16_t length) noexcept;
    void continueCharacteristicDiscovery(ClientState &state) noexcept;
    void continueCccDiscovery(ClientState &state) noexcept;
    void continueDescriptorDiscovery(ClientState &state) noexcept;
    void progressClientDiscovery() noexcept;
    bool validClientPayload(ClientState &state, std::size_t length) noexcept;
    bool startSubscription(ClientState &state, std::uint16_t value) noexcept;
    k_msgq &gattEventQueue() noexcept;
    void lockGattSchema() noexcept;
    void unlockGattSchema() noexcept;
} // namespace nucode::ble::internal::gatt
