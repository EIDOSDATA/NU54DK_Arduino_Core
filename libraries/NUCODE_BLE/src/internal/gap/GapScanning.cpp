/** @file @brief GAP Scanning의 callback과 public API 구현입니다.
 * SPDX-License-Identifier: MIT
 */
#if !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE)
#include "GapInternal.h"
namespace nucode::ble::internal::gap
{
    namespace
    {
        /** @brief 모듈 설정은 해당 구현에서만 소유합니다. */
        ScanConfiguration scan_configuration;
        /** @brief raw AD payload에서 완전·축약 local name을 복사합니다. */
        void copyAdvertisedName(BLEScanResult &result) noexcept
        {
            std::size_t index = 0U;
            while (index < result.payload_length)
            {
                const std::size_t field_length = result.payload[index];
                if (field_length == 0U)
                {
                    break;
                }
                if (index + field_length + 1U > result.payload_length)
                {
                    result.truncated = true;
                    return;
                }
                const std::uint8_t type = result.payload[index + 1U];
                if (type == BT_DATA_NAME_COMPLETE || type == BT_DATA_NAME_SHORTENED)
                {
                    const std::size_t available = field_length - 1U;
                    const std::size_t copy_length = available < BLEScanResult::maximum_name_length
                                                        ? available
                                                        : BLEScanResult::maximum_name_length;
                    ::memcpy(result.name, &result.payload[index + 2U], copy_length);
                    result.name[copy_length] = '\0';
                    if (copy_length != available)
                    {
                        result.truncated = true;
                    }
                    return;
                }
                index += field_length + 1U;
            }
        }
        /** @brief AD service UUID list에서 exact UUID를 찾습니다. */
        bool payloadContainsUuid(const BLEScanResult &result, const BLEUuid &uuid) noexcept
        {
            std::uint8_t incomplete_type = 0U;
            std::uint8_t complete_type = 0U;
            switch (uuid.type())
            {
            case BLEUuid::Type::uuid16:
                incomplete_type = BT_DATA_UUID16_SOME;
                complete_type = BT_DATA_UUID16_ALL;
                break;
            case BLEUuid::Type::uuid32:
                incomplete_type = BT_DATA_UUID32_SOME;
                complete_type = BT_DATA_UUID32_ALL;
                break;
            case BLEUuid::Type::uuid128:
                incomplete_type = BT_DATA_UUID128_SOME;
                complete_type = BT_DATA_UUID128_ALL;
                break;
            default:
                return false;
            }

            std::size_t index = 0U;
            while (index < result.payload_length)
            {
                const std::size_t field_length = result.payload[index];
                if (field_length == 0U || index + field_length + 1U > result.payload_length)
                {
                    break;
                }
                const std::uint8_t type = result.payload[index + 1U];
                if (type == incomplete_type || type == complete_type)
                {
                    const std::size_t data_length = field_length - 1U;
                    for (std::size_t offset = 0U; offset + uuid.size() <= data_length;
                         offset += uuid.size())
                    {
                        if (::memcmp(&result.payload[index + 2U + offset], uuid.data(),
                                     uuid.size()) == 0)
                        {
                            return true;
                        }
                    }
                }
                index += field_length + 1U;
            }
            return false;
        }
        /** @brief 현재 software filter가 모두 scan 결과와 일치하는지 검사합니다. */
        bool scanResultMatches(const BLEScanResult &result) noexcept
        {
            k_spinlock_key_t key = k_spin_lock(&gapState().configuration_lock);
            const ScanConfiguration filters = scan_configuration;
            k_spin_unlock(&gapState().configuration_lock, key);

            if (filters.has_address && result.address != filters.address)
            {
                return false;
            }
            if (filters.has_name && ::strcmp(result.name, filters.name) != 0)
            {
                return false;
            }
            if (filters.has_uuid && !payloadContainsUuid(result, filters.uuid))
            {
                return false;
            }
            return true;
        }
        /** @brief stack scan callback에서 bounded 결과만 queue로 복사합니다. */
        void scanReceived(const bt_addr_le_t *address, std::int8_t rssi,
                          std::uint8_t advertising_type, struct net_buf_simple *data) noexcept
        {
            if (atomic_get(&gapState().scanning_active) == 0 || address == nullptr ||
                data == nullptr)
            {
                return;
            }
            const std::uint32_t generation =
                static_cast<std::uint32_t>(atomic_get(&gapState().device_session_generation));

            BLEScanResult result = {};
            result.address = fromZephyrAddress(*address);
            result.rssi = rssi;
            result.connectable = advertising_type == BT_GAP_ADV_TYPE_ADV_IND ||
                                 advertising_type == BT_GAP_ADV_TYPE_ADV_DIRECT_IND;
            result.scan_response = advertising_type == BT_GAP_ADV_TYPE_SCAN_RSP;
            const std::size_t copy_length = data->len < BLEScanResult::maximum_payload_length
                                                ? data->len
                                                : BLEScanResult::maximum_payload_length;
            result.payload_length = static_cast<std::uint8_t>(copy_length);
            result.truncated = data->len > BLEScanResult::maximum_payload_length;
            if (copy_length != 0U)
            {
                ::memcpy(result.payload, data->data, copy_length);
            }
            copyAdvertisedName(result);

            if (!scanResultMatches(result))
            {
                return;
            }
            if (atomic_get(&gapState().scanning_active) == 0 ||
                generation !=
                    static_cast<std::uint32_t>(atomic_get(&gapState().device_session_generation)))
            {
                return;
            }
            const ScanResultRecord record = {
                .result = result,
                .generation = generation,
            };
            if (k_msgq_put(&scanResultQueue(), &record, K_NO_WAIT) != 0)
            {
                atomic_inc(&gapState().dropped_scan_value);
                nucode::ble::internal::recordError(BLEError::scan_result_overflow, -ENOBUFS, true);
                return;
            }
            queueEvent(BLEEvent::scan_result, generation);
        }
    } // namespace
} // namespace nucode::ble::internal::gap
namespace nucode::ble
{
    using namespace internal::gap;
    bool Scan::clearFilters() noexcept
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
        scan_configuration = ScanConfiguration{};
        k_spin_unlock(&gapState().configuration_lock, key);
        k_msgq_purge(&scanResultQueue());
        return true;
    }

    bool Scan::filterName(const char *exact_name) noexcept
    {
        if (!requireThreadContext() || running())
        {
            if (running())
            {
                internal::recordError(BLEError::busy, -EBUSY, true);
            }
            return false;
        }
        if (exact_name == nullptr)
        {
            internal::recordError(BLEError::invalid_argument, -EINVAL, true);
            return false;
        }
        const std::size_t length = ::strlen(exact_name);
        if (length == 0U || length > CONFIG_BT_DEVICE_NAME_MAX || !validUtf8(exact_name, length))
        {
            internal::recordError(BLEError::invalid_argument, -EINVAL, true);
            return false;
        }
        k_spinlock_key_t key = k_spin_lock(&gapState().configuration_lock);
        ::memcpy(scan_configuration.name, exact_name, length + 1U);
        scan_configuration.has_name = true;
        k_spin_unlock(&gapState().configuration_lock, key);
        return true;
    }

    bool Scan::filterServiceUuid(const BLEUuid &uuid) noexcept
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
        k_spinlock_key_t key = k_spin_lock(&gapState().configuration_lock);
        scan_configuration.uuid = uuid;
        scan_configuration.has_uuid = true;
        k_spin_unlock(&gapState().configuration_lock, key);
        return true;
    }

    bool Scan::filterAddress(const BLEAddress &address) noexcept
    {
        if (!requireThreadContext() || running())
        {
            if (running())
            {
                internal::recordError(BLEError::busy, -EBUSY, true);
            }
            return false;
        }
        if (!address.valid())
        {
            internal::recordError(BLEError::invalid_argument, -EINVAL, true);
            return false;
        }
        k_spinlock_key_t key = k_spin_lock(&gapState().configuration_lock);
        scan_configuration.address = address;
        scan_configuration.has_address = true;
        k_spin_unlock(&gapState().configuration_lock, key);
        return true;
    }

    bool Scan::start(bool active) noexcept
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
        if (atomic_get(&gapState().advertising_active) != 0 ||
            atomic_get(&gapState().connection_connecting) != 0 ||
            atomic_get(&gapState().connection_active) != 0)
        {
            internal::recordError(BLEError::busy, -EBUSY, true);
            return false;
        }
        k_msgq_purge(&scanResultQueue());
        const struct bt_le_scan_param parameters = {
            .type = active ? BT_LE_SCAN_TYPE_ACTIVE : BT_LE_SCAN_TYPE_PASSIVE,
            .options = BT_LE_SCAN_OPT_FILTER_DUPLICATE,
            .interval = BT_GAP_SCAN_FAST_INTERVAL,
            .window = BT_GAP_SCAN_FAST_WINDOW,
            .timeout = 0U,
            .interval_coded = 0U,
            .window_coded = 0U,
        };
        const int result = bt_le_scan_start(&parameters, scanReceived);
        if (result < 0)
        {
            internal::recordError(BLEError::driver_error, result, true);
            return false;
        }
        atomic_set(&gapState().scanning_active, 1);
        queueEvent(BLEEvent::scan_started);
        return true;
    }

    bool Scan::stop() noexcept
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
        const int result = bt_le_scan_stop();
        if (result < 0)
        {
            internal::recordError(BLEError::driver_error, result, true);
            return false;
        }
        atomic_set(&gapState().scanning_active, 0);
        queueEvent(BLEEvent::scan_stopped);
        return true;
    }

    bool Scan::running() const noexcept
    {
        return atomic_get(&gapState().scanning_active) != 0;
    }

    int Scan::available() const noexcept
    {
        return static_cast<int>(k_msgq_num_used_get(&scanResultQueue()));
    }

    bool Scan::read(BLEScanResult &result) noexcept
    {
        ScanResultRecord record = {};
        while (k_msgq_get(&scanResultQueue(), &record, K_NO_WAIT) == 0)
        {
            if (record.generation ==
                static_cast<std::uint32_t>(atomic_get(&gapState().device_session_generation)))
            {
                result = record.result;
                return true;
            }
        }
        return false;
    }

    void Scan::onResult(BLEScanCallback callback, void *context) noexcept
    {
        gapState().scan_callback = callback;
        gapState().scan_context = context;
    }

    std::uint32_t Scan::droppedResults() const noexcept
    {
        return static_cast<std::uint32_t>(atomic_get(&gapState().dropped_scan_value));
    }

} // namespace nucode::ble
#endif
