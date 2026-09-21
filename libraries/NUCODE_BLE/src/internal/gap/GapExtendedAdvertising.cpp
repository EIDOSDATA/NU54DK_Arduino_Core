/** @file @brief 한 개 고정 extended advertising set lifecycle을 구현합니다.
 * SPDX-License-Identifier: MIT
 */
#if !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE)
#include "GapInternal.h"
namespace nucode::ble::internal::gap
{
    namespace
    {
#if defined(CONFIG_BT_EXT_ADV)
        inline constexpr std::size_t maximum_ad_structures = 16U;

        /** @brief 0을 건너뛰는 advertising set generation을 발급합니다. */
        std::uint32_t nextAdvertisingGeneration() noexcept
        {
            std::uint32_t generation =
                static_cast<std::uint32_t>(atomic_inc(&gapState().next_advertising_generation)) +
                1U;
            if (generation == 0U)
            {
                generation = static_cast<std::uint32_t>(
                                 atomic_inc(&gapState().next_advertising_generation)) +
                             1U;
            }
            return generation;
        }

        /** @brief raw AD structure stream을 bounded bt_data view로 해석합니다. */
        bool decodeAdvertisingData(const std::uint8_t *payload, std::size_t length,
                                   struct bt_data *fields, std::size_t &field_count) noexcept
        {
            field_count = 0U;
            if (length == 0U)
            {
                return true;
            }
            if (payload == nullptr)
            {
                return false;
            }
            std::size_t offset = 0U;
            while (offset < length)
            {
                const std::size_t encoded_length = payload[offset];
                if (encoded_length == 0U || offset + encoded_length + 1U > length ||
                    field_count >= maximum_ad_structures)
                {
                    return false;
                }
                fields[field_count].type = payload[offset + 1U];
                fields[field_count].data_len = static_cast<std::uint8_t>(encoded_length - 1U);
                fields[field_count].data = &payload[offset + 2U];
                ++field_count;
                offset += encoded_length + 1U;
            }
            return offset == length;
        }

        /** @brief handle이 현재 advertising set generation인지 검사합니다. */
        bool lookupAdvertisingSet(BLEAdvertisingSetHandle handle,
                                  struct bt_le_ext_adv *&instance,
                                  std::uint32_t &device_generation) noexcept
        {
            if (!handle.valid())
            {
                return false;
            }
            k_spinlock_key_t key = k_spin_lock(&gapState().configuration_lock);
            const ExtendedAdvertisingContext &context = gapState().extended_advertising;
            const bool matches = context.instance != nullptr &&
                                 context.generation ==
                                     BLEConnectionHandleAccess::generation(handle);
            instance = matches ? context.instance : nullptr;
            device_generation = matches ? context.device_generation : 0U;
            k_spin_unlock(&gapState().configuration_lock, key);
            return matches;
        }

        /** @brief stack advertising set pointer를 현재 generation handle로 변환합니다. */
        bool currentAdvertisingHandle(struct bt_le_ext_adv *instance,
                                      BLEAdvertisingSetHandle &handle,
                                      std::uint32_t &device_generation) noexcept
        {
            bool matches = false;
            k_spinlock_key_t key = k_spin_lock(&gapState().configuration_lock);
            const ExtendedAdvertisingContext &context = gapState().extended_advertising;
            if (context.instance == instance && context.generation != 0U)
            {
                handle = BLEConnectionHandleAccess::makeAdvertisingSet(context.generation);
                device_generation = context.device_generation;
                matches = true;
            }
            k_spin_unlock(&gapState().configuration_lock, key);
            return matches && device_generation == static_cast<std::uint32_t>(
                                                     atomic_get(&gapState().device_session_generation));
        }

        /** @brief duration/event 상한으로 자동 중지된 set을 main-thread event로 전달합니다. */
        void advertisingSent(struct bt_le_ext_adv *instance,
                             struct bt_le_ext_adv_sent_info *information) noexcept
        {
            ARG_UNUSED(information);
            BLEAdvertisingSetHandle handle;
            std::uint32_t device_generation = 0U;
            if (!currentAdvertisingHandle(instance, handle, device_generation))
            {
                return;
            }
            atomic_set(&gapState().extended_advertising.active, 0);
            queueEvent(BLEEvent::extended_advertising_stopped, {}, BLELinkRole::none,
                       device_generation, handle);
        }

        /** @brief connectable set이 link를 수락하면 set의 active 상태를 내립니다. */
        void advertisingConnected(struct bt_le_ext_adv *instance,
                                  struct bt_le_ext_adv_connected_info *information) noexcept
        {
            ARG_UNUSED(information);
            BLEAdvertisingSetHandle handle;
            std::uint32_t device_generation = 0U;
            if (!currentAdvertisingHandle(instance, handle, device_generation))
            {
                return;
            }
            atomic_set(&gapState().extended_advertising.active, 0);
            queueEvent(BLEEvent::extended_advertising_stopped, {}, BLELinkRole::none,
                       device_generation, handle);
        }

#if defined(CONFIG_BT_PRIVACY)
        /** @brief exact advertising set의 RPA 만료를 기록하고 실제 회전을 허용합니다. */
        bool advertisingRpaExpired(struct bt_le_ext_adv *instance) noexcept
        {
            BLEAdvertisingSetHandle handle;
            std::uint32_t device_generation = 0U;
            if (!currentAdvertisingHandle(instance, handle, device_generation))
            {
                return true;
            }
            atomic_inc(&gapState().rpa_expiration_count);
            queueEvent(BLEEvent::rpa_expired, {}, BLELinkRole::none,
                       device_generation, handle);
            return true;
        }
#endif

        struct bt_le_ext_adv_cb advertising_callbacks = {
            .sent = advertisingSent,
            .connected = advertisingConnected,
#if defined(CONFIG_BT_PRIVACY)
            .rpa_expired = advertisingRpaExpired,
#endif
#if defined(CONFIG_BT_PER_ADV_RSP)
            .pawr_data_request = pawrDataRequested,
            .pawr_response = pawrResponseReceived,
#endif
        };
#endif
    } // namespace

    bool extendedAdvertisingExists() noexcept
    {
        k_spinlock_key_t key = k_spin_lock(&gapState().configuration_lock);
        const bool exists = gapState().extended_advertising.instance != nullptr;
        k_spin_unlock(&gapState().configuration_lock, key);
        return exists;
    }

    bool currentAdvertisingSet(BLEAdvertisingSetHandle handle,
                               struct bt_le_ext_adv *&instance,
                               std::uint32_t &device_generation) noexcept
    {
#if defined(CONFIG_BT_EXT_ADV)
        return lookupAdvertisingSet(handle, instance, device_generation);
#else
        ARG_UNUSED(handle);
        instance = nullptr;
        device_generation = 0U;
        return false;
#endif
    }

    void endExtendedAdvertising() noexcept
    {
#if defined(CONFIG_BT_EXT_ADV)
        struct bt_le_ext_adv *instance = nullptr;
        k_spinlock_key_t key = k_spin_lock(&gapState().configuration_lock);
        ExtendedAdvertisingContext &context = gapState().extended_advertising;
        instance = context.instance;
        context.instance = nullptr;
        context.generation = 0U;
        context.device_generation = 0U;
        context.connectable = false;
        context.scannable = false;
        context.advertising_length = 0U;
        context.scan_response_length = 0U;
        atomic_set(&context.active, 0);
        k_spin_unlock(&gapState().configuration_lock, key);
        if (instance != nullptr)
        {
            static_cast<void>(bt_le_ext_adv_stop(instance));
            static_cast<void>(bt_le_ext_adv_delete(instance));
        }
#endif
    }
} // namespace nucode::ble::internal::gap
namespace nucode::ble
{
    using namespace internal::gap;

    bool ExtendedAdvertising::create(const BLEExtendedAdvertisingParameters &parameters,
                                     BLEAdvertisingSetHandle &advertising_set) noexcept
    {
        advertising_set = BLEAdvertisingSetHandle{};
        if (!requireThreadContext())
        {
            return false;
        }
#if defined(CONFIG_BT_EXT_ADV)
        if (atomic_get(&gapState().device_initialized) == 0)
        {
            internal::recordError(BLEError::not_initialized, -EPERM, true);
            return false;
        }
        if (parameters.sid > BT_GAP_SID_MAX || parameters.interval_min < 0x0020U ||
            parameters.interval_max > 0x4000U ||
            parameters.interval_min > parameters.interval_max ||
            (parameters.connectable && parameters.scannable) ||
            (parameters.connectable && parameters.anonymous))
        {
            internal::recordError(BLEError::invalid_argument, -EINVAL, true);
            return false;
        }
        if (BLEAdvertising.running() || extendedAdvertisingExists())
        {
            internal::recordError(BLEError::already_started, -EALREADY, true);
            return false;
        }
        std::uint32_t options = BT_LE_ADV_OPT_EXT_ADV;
        if (parameters.connectable)
        {
            options |= BT_LE_ADV_OPT_CONN;
        }
        if (parameters.scannable)
        {
            options |= BT_LE_ADV_OPT_SCANNABLE;
        }
        if (parameters.coded)
        {
            options |= BT_LE_ADV_OPT_CODED;
        }
        if (parameters.anonymous)
        {
            options |= BT_LE_ADV_OPT_ANONYMOUS;
        }
        if (parameters.include_tx_power)
        {
            options |= BT_LE_ADV_OPT_USE_TX_POWER;
        }
        const struct bt_le_adv_param zephyr_parameters = {
            .id = BT_ID_DEFAULT,
            .sid = parameters.sid,
            .secondary_max_skip = 0U,
            .options = options,
            .interval_min = parameters.interval_min,
            .interval_max = parameters.interval_max,
            .peer = nullptr,
        };
        struct bt_le_ext_adv *instance = nullptr;
        const int result =
            bt_le_ext_adv_create(&zephyr_parameters, &advertising_callbacks, &instance);
        if (result < 0)
        {
            internal::recordError(BLEError::driver_error, result, true);
            return false;
        }
        const std::uint32_t generation = nextAdvertisingGeneration();
        const std::uint32_t device_generation = static_cast<std::uint32_t>(
            atomic_get(&gapState().device_session_generation));
        k_spinlock_key_t key = k_spin_lock(&gapState().configuration_lock);
        ExtendedAdvertisingContext &context = gapState().extended_advertising;
        context.instance = instance;
        context.generation = generation;
        context.device_generation = device_generation;
        context.connectable = parameters.connectable;
        context.scannable = parameters.scannable;
        context.advertising_length = 0U;
        context.scan_response_length = 0U;
        advertising_set = internal::BLEConnectionHandleAccess::makeAdvertisingSet(generation);
        k_spin_unlock(&gapState().configuration_lock, key);
        queueEvent(BLEEvent::extended_advertising_created, {}, BLELinkRole::none,
                   device_generation, advertising_set);
        return true;
#else
        ARG_UNUSED(parameters);
        internal::recordError(BLEError::unsupported, -ENOTSUP, true);
        return false;
#endif
    }

    bool ExtendedAdvertising::setData(BLEAdvertisingSetHandle advertising_set,
                                      const void *advertising_data,
                                      std::size_t advertising_length,
                                      const void *scan_response_data,
                                      std::size_t scan_response_length) noexcept
    {
        if (!requireThreadContext())
        {
            return false;
        }
#if defined(CONFIG_BT_EXT_ADV)
        if (advertising_length > maximum_payload_length ||
            scan_response_length > maximum_payload_length ||
            (advertising_length != 0U && advertising_data == nullptr) ||
            (scan_response_length != 0U && scan_response_data == nullptr))
        {
            internal::recordError(BLEError::payload_overflow, -EMSGSIZE, true);
            return false;
        }
        struct bt_le_ext_adv *instance = nullptr;
        std::uint32_t device_generation = 0U;
        if (!lookupAdvertisingSet(advertising_set, instance, device_generation))
        {
            internal::recordError(BLEError::wrong_state, -ENOENT, true);
            return false;
        }
        ExtendedAdvertisingContext &context = gapState().extended_advertising;
        if ((context.scannable && advertising_length != 0U) ||
            (!context.scannable && scan_response_length != 0U))
        {
            internal::recordError(BLEError::invalid_argument, -EINVAL, true);
            return false;
        }
        struct bt_data advertising_fields[maximum_ad_structures] = {};
        struct bt_data scan_response_fields[maximum_ad_structures] = {};
        std::size_t advertising_count = 0U;
        std::size_t scan_response_count = 0U;
        if (!decodeAdvertisingData(static_cast<const std::uint8_t *>(advertising_data),
                                   advertising_length, advertising_fields, advertising_count) ||
            !decodeAdvertisingData(static_cast<const std::uint8_t *>(scan_response_data),
                                   scan_response_length, scan_response_fields,
                                   scan_response_count))
        {
            internal::recordError(BLEError::invalid_argument, -EINVAL, true);
            return false;
        }
        if (advertising_length != 0U)
        {
            ::memcpy(context.advertising_data, advertising_data, advertising_length);
            static_cast<void>(decodeAdvertisingData(context.advertising_data, advertising_length,
                                                    advertising_fields, advertising_count));
        }
        if (scan_response_length != 0U)
        {
            ::memcpy(context.scan_response_data, scan_response_data, scan_response_length);
            static_cast<void>(decodeAdvertisingData(context.scan_response_data,
                                                    scan_response_length, scan_response_fields,
                                                    scan_response_count));
        }
        const int result = bt_le_ext_adv_set_data(instance, advertising_fields, advertising_count,
                                                  scan_response_fields, scan_response_count);
        if (result < 0)
        {
            internal::recordError(BLEError::driver_error, result, true);
            return false;
        }
        context.advertising_length = advertising_length;
        context.scan_response_length = scan_response_length;
        return true;
#else
        ARG_UNUSED(advertising_set);
        ARG_UNUSED(advertising_data);
        ARG_UNUSED(advertising_length);
        ARG_UNUSED(scan_response_data);
        ARG_UNUSED(scan_response_length);
        internal::recordError(BLEError::unsupported, -ENOTSUP, true);
        return false;
#endif
    }

    bool ExtendedAdvertising::start(BLEAdvertisingSetHandle advertising_set,
                                    std::uint16_t duration,
                                    std::uint8_t maximum_events) noexcept
    {
        if (!requireThreadContext())
        {
            return false;
        }
#if defined(CONFIG_BT_EXT_ADV)
        struct bt_le_ext_adv *instance = nullptr;
        std::uint32_t device_generation = 0U;
        if (!lookupAdvertisingSet(advertising_set, instance, device_generation))
        {
            internal::recordError(BLEError::wrong_state, -ENOENT, true);
            return false;
        }
        if (!atomic_cas(&gapState().extended_advertising.active, 0, 1))
        {
            internal::recordError(BLEError::already_started, -EALREADY, true);
            return false;
        }
        const struct bt_le_ext_adv_start_param parameters = {
            .timeout = duration,
            .num_events = maximum_events,
        };
        const int result = bt_le_ext_adv_start(instance, &parameters);
        if (result < 0)
        {
            atomic_set(&gapState().extended_advertising.active, 0);
            internal::recordError(BLEError::driver_error, result, true);
            return false;
        }
        queueEvent(BLEEvent::extended_advertising_started, {}, BLELinkRole::none,
                   device_generation, advertising_set);
        return true;
#else
        ARG_UNUSED(advertising_set);
        ARG_UNUSED(duration);
        ARG_UNUSED(maximum_events);
        internal::recordError(BLEError::unsupported, -ENOTSUP, true);
        return false;
#endif
    }

    bool ExtendedAdvertising::stop(BLEAdvertisingSetHandle advertising_set) noexcept
    {
        if (!requireThreadContext())
        {
            return false;
        }
#if defined(CONFIG_BT_EXT_ADV)
        struct bt_le_ext_adv *instance = nullptr;
        std::uint32_t device_generation = 0U;
        if (!lookupAdvertisingSet(advertising_set, instance, device_generation) ||
            atomic_get(&gapState().extended_advertising.active) == 0)
        {
            internal::recordError(BLEError::wrong_state, -EALREADY, true);
            return false;
        }
        const int result = bt_le_ext_adv_stop(instance);
        if (result < 0)
        {
            internal::recordError(BLEError::driver_error, result, true);
            return false;
        }
        atomic_set(&gapState().extended_advertising.active, 0);
        queueEvent(BLEEvent::extended_advertising_stopped, {}, BLELinkRole::none,
                   device_generation, advertising_set);
        return true;
#else
        ARG_UNUSED(advertising_set);
        internal::recordError(BLEError::unsupported, -ENOTSUP, true);
        return false;
#endif
    }

    bool ExtendedAdvertising::remove(BLEAdvertisingSetHandle advertising_set) noexcept
    {
        if (!requireThreadContext())
        {
            return false;
        }
#if defined(CONFIG_BT_EXT_ADV)
        struct bt_le_ext_adv *instance = nullptr;
        std::uint32_t device_generation = 0U;
        if (!lookupAdvertisingSet(advertising_set, instance, device_generation))
        {
            internal::recordError(BLEError::wrong_state, -ENOENT, true);
            return false;
        }
        if (atomic_get(&gapState().extended_advertising.active) != 0 ||
            (periodicAdvertisingUsesSet(advertising_set) &&
             atomic_get(&gapState().periodic_advertising.active) != 0))
        {
            internal::recordError(BLEError::busy, -EBUSY, true);
            return false;
        }
        const int result = bt_le_ext_adv_delete(instance);
        if (result < 0)
        {
            internal::recordError(BLEError::driver_error, result, true);
            return false;
        }
        k_spinlock_key_t key = k_spin_lock(&gapState().configuration_lock);
        ExtendedAdvertisingContext &context = gapState().extended_advertising;
        context.instance = nullptr;
        context.generation = 0U;
        context.device_generation = 0U;
        context.connectable = false;
        context.scannable = false;
        context.advertising_length = 0U;
        context.scan_response_length = 0U;
        k_spin_unlock(&gapState().configuration_lock, key);
        releasePeriodicAdvertisingSet(advertising_set);
        releasePawrSet(advertising_set);
        queueEvent(BLEEvent::extended_advertising_deleted, {}, BLELinkRole::none,
                   device_generation, advertising_set);
        return true;
#else
        ARG_UNUSED(advertising_set);
        internal::recordError(BLEError::unsupported, -ENOTSUP, true);
        return false;
#endif
    }

    bool ExtendedAdvertising::exists(BLEAdvertisingSetHandle advertising_set) const noexcept
    {
#if defined(CONFIG_BT_EXT_ADV)
        struct bt_le_ext_adv *instance = nullptr;
        std::uint32_t device_generation = 0U;
        return lookupAdvertisingSet(advertising_set, instance, device_generation);
#else
        ARG_UNUSED(advertising_set);
        return false;
#endif
    }

    bool ExtendedAdvertising::running(BLEAdvertisingSetHandle advertising_set) const noexcept
    {
        return exists(advertising_set) &&
               atomic_get(&gapState().extended_advertising.active) != 0;
    }

    bool Privacy::supported() const noexcept
    {
#if defined(CONFIG_BT_PRIVACY) && defined(CONFIG_BT_RPA_TIMEOUT_DYNAMIC)
        return true;
#else
        return false;
#endif
    }

    bool Privacy::setRotationTimeout(std::uint16_t seconds) noexcept
    {
        if (!requireThreadContext())
        {
            return false;
        }
        if (seconds < minimum_rotation_timeout_seconds ||
            seconds > maximum_rotation_timeout_seconds)
        {
            internal::recordError(BLEError::invalid_argument, -EINVAL, true);
            return false;
        }
#if defined(CONFIG_BT_PRIVACY) && defined(CONFIG_BT_RPA_TIMEOUT_DYNAMIC)
        if (atomic_get(&gapState().device_initialized) == 0)
        {
            internal::recordError(BLEError::not_initialized, -EPERM, true);
            return false;
        }
        const int result = bt_le_set_rpa_timeout(seconds);
        if (result < 0)
        {
            internal::recordError(BLEError::driver_error, result, true);
            return false;
        }
        atomic_set(&gapState().rpa_rotation_timeout, seconds);
        return true;
#else
        ARG_UNUSED(seconds);
        internal::recordError(BLEError::unsupported, -ENOTSUP, true);
        return false;
#endif
    }

    std::uint16_t Privacy::rotationTimeout() const noexcept
    {
        return static_cast<std::uint16_t>(atomic_get(&gapState().rpa_rotation_timeout));
    }

    std::uint32_t Privacy::expirationCount() const noexcept
    {
        return static_cast<std::uint32_t>(atomic_get(&gapState().rpa_expiration_count));
    }
} // namespace nucode::ble
#endif
