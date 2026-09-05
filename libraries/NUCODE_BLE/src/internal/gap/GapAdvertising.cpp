/** @file @brief GAP Advertising의 callback과 public API 구현입니다.
 * SPDX-License-Identifier: MIT
 */
#if !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE)
#include "GapInternal.h"
namespace nucode::ble::internal::gap
{
    namespace
    {
        /** @brief 모듈 설정은 해당 구현에서만 소유합니다. */
        AdvertisingConfiguration advertising_configuration;
        /** @brief AD field를 payload budget을 검사하며 배열에 추가합니다. */
        bool appendAdvertisingField(struct bt_data *fields, std::size_t &field_count,
                                    std::size_t maximum_fields, std::size_t &serialized,
                                    std::uint8_t type, const std::uint8_t *data,
                                    std::size_t length) noexcept
        {
            if (field_count >= maximum_fields || length > UINT8_MAX ||
                serialized + length + 2U > nucode::ble::Advertising::maximum_payload_length)
            {
                return false;
            }
            fields[field_count] = {
                .type = type,
                .data_len = static_cast<std::uint8_t>(length),
                .data = data,
            };
            ++field_count;
            serialized += length + 2U;
            return true;
        }
    } // namespace
} // namespace nucode::ble::internal::gap
namespace nucode::ble
{
    using namespace internal::gap;
    bool Advertising::clear() noexcept
    {
        if (!requireThreadContext() || running())
        {
            if (running())
            {
                internal::recordError(BLEError::busy, -EBUSY, true);
            }
            return false;
        }
        k_spinlock_key_t key = k_spin_lock(&gapState().configuration_lock);
        advertising_configuration = AdvertisingConfiguration{};
        k_spin_unlock(&gapState().configuration_lock, key);
        return true;
    }

    bool Advertising::setConnectable(bool connectable) noexcept
    {
        if (!requireThreadContext() || running())
        {
            if (running())
            {
                internal::recordError(BLEError::busy, -EBUSY, true);
            }
            return false;
        }
        advertising_configuration.connectable = connectable;
        return true;
    }

    bool Advertising::setFlags(std::uint8_t flags) noexcept
    {
        if (!requireThreadContext() || running())
        {
            if (running())
            {
                internal::recordError(BLEError::busy, -EBUSY, true);
            }
            return false;
        }
        advertising_configuration.flags = flags;
        return true;
    }

    bool Advertising::setInterval(std::uint16_t minimum, std::uint16_t maximum) noexcept
    {
        if (!requireThreadContext() || running())
        {
            if (running())
            {
                internal::recordError(BLEError::busy, -EBUSY, true);
            }
            return false;
        }
        if (minimum < minimum_advertising_interval || maximum > maximum_advertising_interval ||
            minimum > maximum)
        {
            internal::recordError(BLEError::invalid_argument, -EINVAL, true);
            return false;
        }
        advertising_configuration.interval_min = minimum;
        advertising_configuration.interval_max = maximum;
        return true;
    }

    bool Advertising::addServiceUuid(const BLEUuid &uuid) noexcept
    {
        if (!requireThreadContext() || running())
        {
            if (running())
            {
                internal::recordError(BLEError::busy, -EBUSY, true);
            }
            return false;
        }
        if (!uuid.valid())
        {
            internal::recordError(BLEError::invalid_argument, -EINVAL, true);
            return false;
        }
        for (std::size_t index = 0U; index < advertising_configuration.service_uuid_count; ++index)
        {
            if (advertising_configuration.service_uuids[index] == uuid)
            {
                internal::recordError(BLEError::duplicate, -EEXIST, true);
                return false;
            }
        }
        if (advertising_configuration.service_uuid_count >= maximum_service_uuids)
        {
            internal::recordError(BLEError::payload_overflow, -ENOSPC, true);
            return false;
        }
        advertising_configuration.service_uuids[advertising_configuration.service_uuid_count++] =
            uuid;
        return true;
    }

    bool Advertising::setManufacturerData(std::uint16_t company_id, const void *data,
                                          std::size_t length) noexcept
    {
        if (!requireThreadContext() || running())
        {
            if (running())
            {
                internal::recordError(BLEError::busy, -EBUSY, true);
            }
            return false;
        }
        if ((data == nullptr && length != 0U) || length + 2U > maximum_ad_field_data)
        {
            internal::recordError(BLEError::payload_overflow, -EMSGSIZE, true);
            return false;
        }
        advertising_configuration.company_id = company_id;
        advertising_configuration.manufacturer_length = length;
        advertising_configuration.has_manufacturer_data = true;
        if (length != 0U)
        {
            ::memcpy(advertising_configuration.manufacturer_data, data, length);
        }
        return true;
    }

    bool Advertising::setServiceData(const BLEUuid &uuid, const void *data,
                                     std::size_t length) noexcept
    {
        if (!requireThreadContext() || running())
        {
            if (running())
            {
                internal::recordError(BLEError::busy, -EBUSY, true);
            }
            return false;
        }
        if (!uuid.valid() || (data == nullptr && length != 0U) ||
            uuid.size() + length > maximum_ad_field_data)
        {
            internal::recordError(uuid.valid() ? BLEError::payload_overflow
                                               : BLEError::invalid_argument,
                                  uuid.valid() ? -EMSGSIZE : -EINVAL, true);
            return false;
        }
        advertising_configuration.service_data_uuid = uuid;
        advertising_configuration.service_data_length = length;
        advertising_configuration.has_service_data = true;
        if (length != 0U)
        {
            ::memcpy(advertising_configuration.service_data, data, length);
        }
        return true;
    }

    bool Advertising::setScanResponseName(bool enabled) noexcept
    {
        if (!requireThreadContext() || running())
        {
            if (running())
            {
                internal::recordError(BLEError::busy, -EBUSY, true);
            }
            return false;
        }
        advertising_configuration.scan_response_name = enabled;
        return true;
    }

    bool Advertising::start() noexcept
    {
        if (!requireThreadContext())
        {
            return false;
        }
        if (atomic_get(&gapState().device_initialized) == 0)
        {
            internal::recordError(BLEError::not_initialized, -EPERM, true);
            return false;
        }
        if (running())
        {
            internal::recordError(BLEError::already_started, -EALREADY, true);
            return false;
        }
        if (atomic_get(&gapState().scanning_active) != 0 ||
            atomic_get(&gapState().connection_connecting) != 0 ||
            atomic_get(&gapState().connection_active) != 0)
        {
            internal::recordError(BLEError::busy, -EBUSY, true);
            return false;
        }

        const AdvertisingConfiguration configuration = advertising_configuration;
        struct bt_data advertising_fields[8] = {};
        struct bt_data scan_response_fields[1] = {};
        std::uint8_t manufacturer_field[maximum_ad_field_data] = {};
        std::uint8_t service_data_field[maximum_ad_field_data] = {};
        std::uint8_t uuid16_field[maximum_ad_field_data] = {};
        std::uint8_t uuid32_field[maximum_ad_field_data] = {};
        std::uint8_t uuid128_field[maximum_ad_field_data] = {};
        std::size_t uuid16_length = 0U;
        std::size_t uuid32_length = 0U;
        std::size_t uuid128_length = 0U;
        std::size_t advertising_count = 0U;
        std::size_t advertising_size = 0U;
        std::size_t scan_response_count = 0U;
        std::size_t scan_response_size = 0U;

        if (!appendAdvertisingField(advertising_fields, advertising_count,
                                    ARRAY_SIZE(advertising_fields), advertising_size, BT_DATA_FLAGS,
                                    &configuration.flags, 1U))
        {
            internal::recordError(BLEError::payload_overflow, -EMSGSIZE, true);
            return false;
        }
        for (std::size_t index = 0U; index < configuration.service_uuid_count; ++index)
        {
            const BLEUuid &uuid = configuration.service_uuids[index];
            std::uint8_t *field = uuid128_field;
            std::size_t *field_length = &uuid128_length;
            if (uuid.type() == BLEUuid::Type::uuid16)
            {
                field = uuid16_field;
                field_length = &uuid16_length;
            }
            else if (uuid.type() == BLEUuid::Type::uuid32)
            {
                field = uuid32_field;
                field_length = &uuid32_length;
            }
            if (*field_length + uuid.size() > maximum_ad_field_data)
            {
                internal::recordError(BLEError::payload_overflow, -EMSGSIZE, true);
                return false;
            }
            ::memcpy(&field[*field_length], uuid.data(), uuid.size());
            *field_length += uuid.size();
        }
        const struct
        {
            std::uint8_t type;
            const std::uint8_t *data;
            std::size_t length;
        } uuid_fields[] = {
            {BT_DATA_UUID16_ALL, uuid16_field, uuid16_length},
            {BT_DATA_UUID32_ALL, uuid32_field, uuid32_length},
            {BT_DATA_UUID128_ALL, uuid128_field, uuid128_length},
        };
        for (const auto &field : uuid_fields)
        {
            if (field.length != 0U &&
                !appendAdvertisingField(advertising_fields, advertising_count,
                                        ARRAY_SIZE(advertising_fields), advertising_size,
                                        field.type, field.data, field.length))
            {
                internal::recordError(BLEError::payload_overflow, -EMSGSIZE, true);
                return false;
            }
        }
        if (configuration.has_manufacturer_data)
        {
            manufacturer_field[0] = static_cast<std::uint8_t>(configuration.company_id & 0xffU);
            manufacturer_field[1] =
                static_cast<std::uint8_t>((configuration.company_id >> 8U) & 0xffU);
            ::memcpy(&manufacturer_field[2], configuration.manufacturer_data,
                     configuration.manufacturer_length);
            if (!appendAdvertisingField(advertising_fields, advertising_count,
                                        ARRAY_SIZE(advertising_fields), advertising_size,
                                        BT_DATA_MANUFACTURER_DATA, manufacturer_field,
                                        configuration.manufacturer_length + 2U))
            {
                internal::recordError(BLEError::payload_overflow, -EMSGSIZE, true);
                return false;
            }
        }
        if (configuration.has_service_data)
        {
            const BLEUuid &uuid = configuration.service_data_uuid;
            ::memcpy(service_data_field, uuid.data(), uuid.size());
            ::memcpy(&service_data_field[uuid.size()], configuration.service_data,
                     configuration.service_data_length);
            const std::uint8_t type =
                uuid.type() == BLEUuid::Type::uuid16
                    ? BT_DATA_SVC_DATA16
                    : (uuid.type() == BLEUuid::Type::uuid32 ? BT_DATA_SVC_DATA32
                                                            : BT_DATA_SVC_DATA128);
            if (!appendAdvertisingField(advertising_fields, advertising_count,
                                        ARRAY_SIZE(advertising_fields), advertising_size, type,
                                        service_data_field,
                                        uuid.size() + configuration.service_data_length))
            {
                internal::recordError(BLEError::payload_overflow, -EMSGSIZE, true);
                return false;
            }
        }
        if (configuration.scan_response_name)
        {
            const std::size_t name_length = ::strlen(gapState().local_name);
            if (!appendAdvertisingField(
                    scan_response_fields, scan_response_count, ARRAY_SIZE(scan_response_fields),
                    scan_response_size, BT_DATA_NAME_COMPLETE,
                    reinterpret_cast<const std::uint8_t *>(gapState().local_name), name_length))
            {
                internal::recordError(BLEError::payload_overflow, -EMSGSIZE, true);
                return false;
            }
        }

        std::uint32_t options = configuration.connectable ? BT_LE_ADV_OPT_CONN : BT_LE_ADV_OPT_NONE;
        if (!configuration.connectable && scan_response_count != 0U)
        {
            options |= BT_LE_ADV_OPT_SCANNABLE;
        }
        const struct bt_le_adv_param parameters = {
            .id = BT_ID_DEFAULT,
            .sid = 0U,
            .secondary_max_skip = 0U,
            .options = options,
            .interval_min = configuration.interval_min,
            .interval_max = configuration.interval_max,
            .peer = nullptr,
        };
        const int result = bt_le_adv_start(&parameters, advertising_fields, advertising_count,
                                           scan_response_fields, scan_response_count);
        if (result < 0)
        {
            internal::recordError(BLEError::driver_error, result, true);
            return false;
        }
        atomic_set(&gapState().advertising_active, 1);
        internal::recordError(BLEError::none, 0, false);
        queueEvent(BLEEvent::advertising_started);
        return true;
    }

    bool Advertising::stop() noexcept
    {
        if (!requireThreadContext())
        {
            return false;
        }
        if (!running())
        {
            internal::recordError(BLEError::wrong_state, -EALREADY, true);
            return false;
        }
        const int result = bt_le_adv_stop();
        if (result < 0)
        {
            internal::recordError(BLEError::driver_error, result, true);
            return false;
        }
        atomic_set(&gapState().advertising_active, 0);
        queueEvent(BLEEvent::advertising_stopped);
        return true;
    }

    bool Advertising::running() const noexcept
    {
        return atomic_get(&gapState().advertising_active) != 0;
    }

} // namespace nucode::ble
#endif
