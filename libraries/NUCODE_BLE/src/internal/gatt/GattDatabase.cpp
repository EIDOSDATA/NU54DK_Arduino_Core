/** @file @brief 고정 GATT schema의 구성·검증·등록 rollback입니다.
 * SPDX-License-Identifier: MIT
 */
#if !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE)
#include "GattInternal.h"
namespace nucode::ble::internal::gatt
{
    namespace
    {
        DatabaseState state{};
        ServiceSlots slots{};
    } // namespace
    ServiceSlots &serviceSlots() noexcept
    {
        return slots;
    }
    DatabaseState &databaseState() noexcept
    {
        return state;
    }
    namespace
    {
        K_MUTEX_DEFINE(gatt_schema_mutex);
    }
    void lockGattSchema() noexcept
    {
        k_mutex_lock(&gatt_schema_mutex, K_FOREVER);
    }
    void unlockGattSchema() noexcept
    {
        k_mutex_unlock(&gatt_schema_mutex);
    }
    /** @brief owner characteristic의 등록 attribute 위치를 찾습니다. */
    bool findCharacteristic(BLECharacteristic &owner, ServiceSlot *&slot,
                            std::size_t &characteristic_index) noexcept
    {
        for (std::size_t service_index = 0U;
             service_index < databaseState().registered_service_count; ++service_index)
        {
            ServiceSlot &candidate = serviceSlots()[service_index];
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

} // namespace nucode::ble::internal::gatt
namespace nucode::ble::internal
{
    using namespace gatt;
    bool addGattService(BLEService &service) noexcept
    {
        lockGattSchema();
        if (stackReady() || atomic_get(&databaseState().database_registered) != 0 ||
            GattAccess::registered(service))
        {
            unlockGattSchema();
            recordError(BLEError::wrong_state, -EPERM, true);
            return false;
        }
        BLEUuid &uuid = GattAccess::uuid(service);
        if (!uuid.valid() || uuid.type() == BLEUuid::Type::uuid32)
        {
            unlockGattSchema();
            recordError(BLEError::invalid_argument, -EINVAL, true);
            return false;
        }
        for (std::size_t index = 0U; index < databaseState().registered_service_count; ++index)
        {
            if (databaseState().registered_services[index] == &service ||
                GattAccess::uuid(*databaseState().registered_services[index]) == uuid)
            {
                unlockGattSchema();
                recordError(BLEError::duplicate, -EEXIST, true);
                return false;
            }
        }
        if (databaseState().registered_service_count >= maximum_services)
        {
            unlockGattSchema();
            recordError(BLEError::schema_full, -ENOSPC, true);
            return false;
        }
        databaseState().registered_services[databaseState().registered_service_count++] = &service;
        unlockGattSchema();
        return true;
    }

    bool hasGattSchema() noexcept
    {
        return databaseState().registered_service_count != 0U;
    }

    int prepareGattDatabase() noexcept
    {
        lockGattSchema();
        if (atomic_get(&databaseState().database_registered) != 0)
        {
            unlockGattSchema();
            return 0;
        }
        if (stackReady() && databaseState().registered_service_count != 0U)
        {
            unlockGattSchema();
            return -EPERM;
        }

        /** @brief 모든 schema를 먼저 검증·구성한 뒤에만 stack에 노출합니다. */
        for (std::size_t service_index = 0U;
             service_index < databaseState().registered_service_count; ++service_index)
        {
            BLEService &owner = *databaseState().registered_services[service_index];
            ServiceSlot &slot = serviceSlots()[service_index];
            slot.owner = &owner;
            slot.characteristic_count = GattAccess::characteristicCount(owner);
            if (slot.characteristic_count > CONFIG_NUCODE_BLE_GATT_MAX_CHARACTERISTICS_PER_SERVICE)
            {
                unlockGattSchema();
                return -ENOSPC;
            }
            const struct bt_uuid *service_uuid = slot.service_uuid.assign(GattAccess::uuid(owner));
            if (service_uuid == nullptr)
            {
                unlockGattSchema();
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
                    unlockGattSchema();
                    return -EINVAL;
                }
                for (std::size_t previous = 0U; previous < index; ++previous)
                {
                    if (GattAccess::uuid(*slot.characteristics[previous]) ==
                        GattAccess::uuid(*characteristic))
                    {
                        unlockGattSchema();
                        return -EEXIST;
                    }
                }
                slot.characteristics[index] = characteristic;
                const struct bt_uuid *characteristic_uuid =
                    slot.characteristic_uuids[index].assign(GattAccess::uuid(*characteristic));
                if (characteristic_uuid == nullptr)
                {
                    unlockGattSchema();
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
        for (std::size_t service_index = 0U;
             service_index < databaseState().registered_service_count; ++service_index)
        {
            ServiceSlot &slot = serviceSlots()[service_index];
            const int result = bt_gatt_service_register(&slot.service);
            if (result < 0)
            {
                for (std::size_t rollback = 0U; rollback < registered_count; ++rollback)
                {
                    static_cast<void>(
                        bt_gatt_service_unregister(&serviceSlots()[rollback].service));
                    GattAccess::setRegistered(*serviceSlots()[rollback].owner, false);
                    for (std::size_t index = 0U;
                         index < serviceSlots()[rollback].characteristic_count; ++index)
                    {
                        GattAccess::setRegistered(*serviceSlots()[rollback].characteristics[index],
                                                  false);
                    }
                }
                unlockGattSchema();
                return result;
            }
            ++registered_count;
            GattAccess::setRegistered(*slot.owner, true);
            for (std::size_t index = 0U; index < slot.characteristic_count; ++index)
            {
                GattAccess::setRegistered(*slot.characteristics[index], true);
            }
        }
        atomic_set(&databaseState().database_registered, 1);
        unlockGattSchema();
        return 0;
    }

} // namespace nucode::ble::internal
namespace nucode::ble
{
    using namespace internal::gatt;
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

} // namespace nucode::ble
#endif
