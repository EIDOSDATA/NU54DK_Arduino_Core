/** @file @brief bounded multiple extended advertising set lifecycle을 구현합니다.
 * SPDX-License-Identifier: MIT
 */
#if !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE)
#include "GapInternal.h"
#if defined(CONFIG_BT_EAD)
#include <zephyr/bluetooth/ead.h>
#endif
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
                                  std::uint32_t &device_generation,
                                  ExtendedAdvertisingContext **matched_context = nullptr) noexcept
        {
            if (!handle.valid())
            {
                return false;
            }
            k_spinlock_key_t key = k_spin_lock(&gapState().configuration_lock);
            ExtendedAdvertisingContext *match = nullptr;
            for (ExtendedAdvertisingContext &context : gapState().extended_advertising)
            {
                if (context.instance != nullptr &&
                    context.generation == BLEConnectionHandleAccess::generation(handle))
                {
                    match = &context;
                    break;
                }
            }
            const bool matches = match != nullptr;
            instance = matches ? match->instance : nullptr;
            device_generation = matches ? match->device_generation : 0U;
            if (matched_context != nullptr)
            {
                *matched_context = match;
            }
            k_spin_unlock(&gapState().configuration_lock, key);
            return matches;
        }

        /** @brief stack advertising set pointer를 현재 generation handle로 변환합니다. */
        bool currentAdvertisingHandle(struct bt_le_ext_adv *instance,
                                      BLEAdvertisingSetHandle &handle,
                                      std::uint32_t &device_generation,
                                      bool mark_inactive = false) noexcept
        {
            bool matches = false;
            k_spinlock_key_t key = k_spin_lock(&gapState().configuration_lock);
            for (ExtendedAdvertisingContext &context : gapState().extended_advertising)
            {
                if (context.instance == instance && context.generation != 0U)
                {
                    handle = BLEConnectionHandleAccess::makeAdvertisingSet(context.generation);
                    device_generation = context.device_generation;
                    if (mark_inactive)
                    {
                        atomic_set(&context.active, 0);
                    }
                    matches = true;
                    break;
                }
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
            if (!currentAdvertisingHandle(instance, handle, device_generation, true))
            {
                return;
            }
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
            if (!currentAdvertisingHandle(instance, handle, device_generation, true))
            {
                return;
            }
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

        /** @brief controller list·identity 오류를 공개 오류 분류로 변환합니다. */
        [[maybe_unused]] void recordResourceError(int result) noexcept
        {
            BLEError error = BLEError::driver_error;
            if (result == -ENOMEM)
            {
                error = BLEError::schema_full;
            }
            else if (result == -EBUSY)
            {
                error = BLEError::busy;
            }
            else if (result == -EALREADY || result == -EEXIST)
            {
                error = BLEError::duplicate;
            }
            else if (result == -EINVAL || result == -ENOENT)
            {
                error = BLEError::invalid_argument;
            }
            internal::recordError(error, result, true);
        }

        /** @brief compiler가 제거할 수 없는 byte 쓰기로 key material을 지웁니다. */
        void secureClear(void *memory, std::size_t length) noexcept
        {
            volatile std::uint8_t *bytes =
                static_cast<volatile std::uint8_t *>(memory);
            for (std::size_t index = 0U; index < length; ++index)
            {
                bytes[index] = 0U;
            }
        }

#if defined(CONFIG_BT_EXT_ADV)
        /** @brief 생성된 advertising set이 identity slot을 계속 참조하는지 확인합니다. */
        [[maybe_unused]] bool advertisingIdentityInUse(std::uint8_t identity) noexcept
        {
            bool in_use = false;
            k_spinlock_key_t key = k_spin_lock(&gapState().configuration_lock);
            for (const ExtendedAdvertisingContext &context :
                 gapState().extended_advertising)
            {
                if (context.instance != nullptr && context.identity == identity)
                {
                    in_use = true;
                    break;
                }
            }
            k_spin_unlock(&gapState().configuration_lock, key);
            return in_use;
        }
#endif
    } // namespace

    bool extendedAdvertisingExists() noexcept
    {
#if defined(CONFIG_BT_EXT_ADV)
        k_spinlock_key_t key = k_spin_lock(&gapState().configuration_lock);
        bool exists = false;
        for (const ExtendedAdvertisingContext &context : gapState().extended_advertising)
        {
            if (context.instance != nullptr)
            {
                exists = true;
                break;
            }
        }
        k_spin_unlock(&gapState().configuration_lock, key);
        return exists;
#else
        return false;
#endif
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
        struct bt_le_ext_adv *instances[CONFIG_BT_EXT_ADV_MAX_ADV_SET] = {};
        k_spinlock_key_t key = k_spin_lock(&gapState().configuration_lock);
        std::size_t instance_count = 0U;
        for (ExtendedAdvertisingContext &context : gapState().extended_advertising)
        {
            if (context.instance != nullptr)
            {
                instances[instance_count++] = context.instance;
            }
            context.instance = nullptr;
            context.generation = 0U;
            context.device_generation = 0U;
            context.connectable = false;
            context.scannable = false;
            context.identity = 0U;
            context.advertising_length = 0U;
            context.scan_response_length = 0U;
            atomic_set(&context.active, 0);
        }
        k_spin_unlock(&gapState().configuration_lock, key);
        for (std::size_t index = 0U; index < instance_count; ++index)
        {
            static_cast<void>(bt_le_ext_adv_stop(instances[index]));
            static_cast<void>(bt_le_ext_adv_delete(instances[index]));
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
        const bool directed = parameters.directed_peer.valid();
        if (parameters.identity >= CONFIG_BT_ID_MAX ||
            parameters.sid > BT_GAP_SID_MAX || parameters.interval_min < 0x0020U ||
            parameters.interval_max > 0x4000U ||
            parameters.interval_min > parameters.interval_max ||
            (parameters.connectable && parameters.scannable) ||
            (parameters.connectable && parameters.anonymous) ||
            (parameters.secondary_1m && parameters.coded) ||
            (parameters.coding != BLEAdvertisingCoding::automatic && !parameters.coded) ||
            (directed && (!parameters.connectable || parameters.scannable ||
                          parameters.anonymous || !parameters.directed_low_duty)) ||
            (parameters.use_identity_address && parameters.directed_peer_uses_rpa) ||
            (!directed && (parameters.directed_low_duty ||
                           parameters.directed_peer_uses_rpa)))
        {
            internal::recordError(BLEError::invalid_argument, -EINVAL, true);
            return false;
        }
        ExtendedAdvertisingContext *free_context = nullptr;
        k_spinlock_key_t key = k_spin_lock(&gapState().configuration_lock);
        for (ExtendedAdvertisingContext &context : gapState().extended_advertising)
        {
            if (context.instance == nullptr)
            {
                free_context = &context;
                break;
            }
        }
        k_spin_unlock(&gapState().configuration_lock, key);
        if (BLEAdvertising.running())
        {
            internal::recordError(BLEError::already_started, -EALREADY, true);
            return false;
        }
        if (free_context == nullptr)
        {
            internal::recordError(BLEError::schema_full, -ENOMEM, true);
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
        if (parameters.secondary_1m)
        {
            options |= BT_LE_ADV_OPT_NO_2M;
        }
        if (parameters.anonymous)
        {
            options |= BT_LE_ADV_OPT_ANONYMOUS;
        }
        if (parameters.include_tx_power)
        {
            options |= BT_LE_ADV_OPT_USE_TX_POWER;
        }
        if (parameters.use_identity_address)
        {
            options |= BT_LE_ADV_OPT_USE_IDENTITY;
        }
        if (parameters.filter_scan_requests)
        {
            options |= BT_LE_ADV_OPT_FILTER_SCAN_REQ;
        }
        if (parameters.filter_connections)
        {
            options |= BT_LE_ADV_OPT_FILTER_CONN;
        }
        if (parameters.directed_low_duty)
        {
            options |= BT_LE_ADV_OPT_DIR_MODE_LOW_DUTY;
        }
        if (parameters.directed_peer_uses_rpa)
        {
            options |= BT_LE_ADV_OPT_DIR_ADDR_RPA;
        }
#if defined(CONFIG_BT_EXT_ADV_CODING_SELECTION)
        if (parameters.coding == BLEAdvertisingCoding::s2)
        {
            options |= BT_LE_ADV_OPT_REQUIRE_S2_CODING;
        }
        else if (parameters.coding == BLEAdvertisingCoding::s8)
        {
            options |= BT_LE_ADV_OPT_REQUIRE_S8_CODING;
        }
#else
        if (parameters.coding != BLEAdvertisingCoding::automatic)
        {
            internal::recordError(BLEError::unsupported, -ENOTSUP, true);
            return false;
        }
#endif
        bt_addr_le_t peer = {};
        const bt_addr_le_t *peer_pointer = nullptr;
        if (directed)
        {
            if (!toZephyrAddress(parameters.directed_peer, peer))
            {
                internal::recordError(BLEError::invalid_argument, -EINVAL, true);
                return false;
            }
            peer_pointer = &peer;
        }
        const struct bt_le_adv_param zephyr_parameters = {
            .id = parameters.identity,
            .sid = parameters.sid,
            .secondary_max_skip = 0U,
            .options = options,
            .interval_min = parameters.interval_min,
            .interval_max = parameters.interval_max,
            .peer = peer_pointer,
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
        key = k_spin_lock(&gapState().configuration_lock);
        free_context->instance = instance;
        free_context->generation = generation;
        free_context->device_generation = device_generation;
        free_context->connectable = parameters.connectable;
        free_context->scannable = parameters.scannable;
        free_context->identity = parameters.identity;
        free_context->advertising_length = 0U;
        free_context->scan_response_length = 0U;
        atomic_set(&free_context->active, 0);
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
        ExtendedAdvertisingContext *context = nullptr;
        if (!lookupAdvertisingSet(advertising_set, instance, device_generation, &context))
        {
            internal::recordError(BLEError::wrong_state, -ENOENT, true);
            return false;
        }
        if ((context->scannable && advertising_length != 0U) ||
            (!context->scannable && scan_response_length != 0U))
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
            ::memcpy(context->advertising_data, advertising_data, advertising_length);
            static_cast<void>(decodeAdvertisingData(context->advertising_data, advertising_length,
                                                    advertising_fields, advertising_count));
        }
        if (scan_response_length != 0U)
        {
            ::memcpy(context->scan_response_data, scan_response_data, scan_response_length);
            static_cast<void>(decodeAdvertisingData(context->scan_response_data,
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
        context->advertising_length = advertising_length;
        context->scan_response_length = scan_response_length;
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
        ExtendedAdvertisingContext *context = nullptr;
        if (!lookupAdvertisingSet(advertising_set, instance, device_generation, &context))
        {
            internal::recordError(BLEError::wrong_state, -ENOENT, true);
            return false;
        }
        if (!atomic_cas(&context->active, 0, 1))
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
            atomic_set(&context->active, 0);
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
        ExtendedAdvertisingContext *context = nullptr;
        if (!lookupAdvertisingSet(advertising_set, instance, device_generation, &context) ||
            atomic_get(&context->active) == 0)
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
        atomic_set(&context->active, 0);
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
        ExtendedAdvertisingContext *context = nullptr;
        if (!lookupAdvertisingSet(advertising_set, instance, device_generation, &context))
        {
            internal::recordError(BLEError::wrong_state, -ENOENT, true);
            return false;
        }
        bool busy = atomic_get(&context->active) != 0;
#if defined(CONFIG_BT_PER_ADV)
        busy = busy || (periodicAdvertisingUsesSet(advertising_set) &&
                        atomic_get(&gapState().periodic_advertising.active) != 0);
#endif
        if (busy)
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
        context->instance = nullptr;
        context->generation = 0U;
        context->device_generation = 0U;
        context->connectable = false;
        context->scannable = false;
        context->identity = 0U;
        context->advertising_length = 0U;
        context->scan_response_length = 0U;
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
#if defined(CONFIG_BT_EXT_ADV)
        struct bt_le_ext_adv *instance = nullptr;
        std::uint32_t device_generation = 0U;
        ExtendedAdvertisingContext *context = nullptr;
        return lookupAdvertisingSet(advertising_set, instance, device_generation, &context) &&
               atomic_get(&context->active) != 0;
#else
        ARG_UNUSED(advertising_set);
        return false;
#endif
    }

    std::size_t Identity::count() const noexcept
    {
#if defined(CONFIG_BT)
        bt_addr_le_t addresses[CONFIG_BT_ID_MAX] = {};
        std::size_t address_count = CONFIG_BT_ID_MAX;
        bt_id_get(addresses, &address_count);
        std::size_t valid_count = 0U;
        for (std::size_t index = 0U; index < address_count; ++index)
        {
            if (!bt_addr_le_eq(&addresses[index], BT_ADDR_LE_ANY))
            {
                ++valid_count;
            }
        }
        return valid_count;
#else
        return 0U;
#endif
    }

    bool Identity::address(std::uint8_t identity, BLEAddress &address) const noexcept
    {
        address = BLEAddress{};
#if defined(CONFIG_BT)
        if (identity >= CONFIG_BT_ID_MAX)
        {
            return false;
        }
        bt_addr_le_t addresses[CONFIG_BT_ID_MAX] = {};
        std::size_t address_count = CONFIG_BT_ID_MAX;
        bt_id_get(addresses, &address_count);
        if (identity >= address_count || bt_addr_le_eq(&addresses[identity], BT_ADDR_LE_ANY))
        {
            return false;
        }
        address = fromZephyrAddress(addresses[identity]);
        return true;
#else
        ARG_UNUSED(identity);
        return false;
#endif
    }

    bool Identity::create(std::uint8_t &identity, BLEAddress &address) noexcept
    {
        identity = 0xffU;
        address = BLEAddress{};
        if (!requireThreadContext())
        {
            return false;
        }
#if defined(CONFIG_BT)
        if (atomic_get(&gapState().device_initialized) == 0)
        {
            internal::recordError(BLEError::not_initialized, -EPERM, true);
            return false;
        }
        bt_addr_le_t generated = {};
        bt_addr_le_copy(&generated, BT_ADDR_LE_ANY);
        const int result = bt_id_create(&generated, nullptr);
        if (result < 0)
        {
            recordResourceError(result);
            return false;
        }
        identity = static_cast<std::uint8_t>(result);
        address = fromZephyrAddress(generated);
        return true;
#else
        internal::recordError(BLEError::unsupported, -ENOTSUP, true);
        return false;
#endif
    }

    bool Identity::reset(std::uint8_t identity, BLEAddress &address) noexcept
    {
        address = BLEAddress{};
        if (!requireThreadContext())
        {
            return false;
        }
#if defined(CONFIG_BT)
        if (identity == BT_ID_DEFAULT || identity >= CONFIG_BT_ID_MAX)
        {
            internal::recordError(BLEError::invalid_argument, -EINVAL, true);
            return false;
        }
#if defined(CONFIG_BT_EXT_ADV)
        if (advertisingIdentityInUse(identity))
        {
            internal::recordError(BLEError::busy, -EBUSY, true);
            return false;
        }
#endif
        bt_addr_le_t generated = {};
        bt_addr_le_copy(&generated, BT_ADDR_LE_ANY);
        const int result = bt_id_reset(identity, &generated, nullptr);
        if (result < 0)
        {
            recordResourceError(result);
            return false;
        }
        address = fromZephyrAddress(generated);
        return true;
#else
        ARG_UNUSED(identity);
        internal::recordError(BLEError::unsupported, -ENOTSUP, true);
        return false;
#endif
    }

    bool Identity::remove(std::uint8_t identity) noexcept
    {
        if (!requireThreadContext())
        {
            return false;
        }
#if defined(CONFIG_BT)
        if (identity == BT_ID_DEFAULT || identity >= CONFIG_BT_ID_MAX)
        {
            internal::recordError(BLEError::invalid_argument, -EINVAL, true);
            return false;
        }
#if defined(CONFIG_BT_EXT_ADV)
        if (advertisingIdentityInUse(identity))
        {
            internal::recordError(BLEError::busy, -EBUSY, true);
            return false;
        }
#endif
        const int result = bt_id_delete(identity);
        if (result < 0)
        {
            recordResourceError(result);
            return false;
        }
        return true;
#else
        ARG_UNUSED(identity);
        internal::recordError(BLEError::unsupported, -ENOTSUP, true);
        return false;
#endif
    }

    std::size_t AdvertisingLists::filterAcceptCapacity() const noexcept
    {
#if defined(CONFIG_BT_CTLR_FAL_SIZE)
        return CONFIG_BT_CTLR_FAL_SIZE;
#else
        return 0U;
#endif
    }

    std::size_t AdvertisingLists::resolvingCapacity() const noexcept
    {
#if defined(CONFIG_BT_CTLR_RL_SIZE)
        return CONFIG_BT_CTLR_RL_SIZE;
#else
        return 0U;
#endif
    }

    std::size_t AdvertisingLists::periodicAdvertiserCapacity() const noexcept
    {
#if defined(CONFIG_BT_CTLR_SYNC_PERIODIC_ADV_LIST_SIZE)
        return CONFIG_BT_CTLR_SYNC_PERIODIC_ADV_LIST_SIZE;
#else
        return 0U;
#endif
    }

    bool AdvertisingLists::addFilterAccept(const BLEAddress &address) noexcept
    {
        if (!requireThreadContext())
        {
            return false;
        }
#if defined(CONFIG_BT_FILTER_ACCEPT_LIST)
        bt_addr_le_t converted = {};
        if (!toZephyrAddress(address, converted))
        {
            internal::recordError(BLEError::invalid_argument, -EINVAL, true);
            return false;
        }
        const int result = bt_le_filter_accept_list_add(&converted);
        if (result != 0)
        {
            recordResourceError(result);
            return false;
        }
        return true;
#else
        ARG_UNUSED(address);
        internal::recordError(BLEError::unsupported, -ENOTSUP, true);
        return false;
#endif
    }

    bool AdvertisingLists::removeFilterAccept(const BLEAddress &address) noexcept
    {
        if (!requireThreadContext())
        {
            return false;
        }
#if defined(CONFIG_BT_FILTER_ACCEPT_LIST)
        bt_addr_le_t converted = {};
        if (!toZephyrAddress(address, converted))
        {
            internal::recordError(BLEError::invalid_argument, -EINVAL, true);
            return false;
        }
        const int result = bt_le_filter_accept_list_remove(&converted);
        if (result != 0)
        {
            recordResourceError(result);
            return false;
        }
        return true;
#else
        ARG_UNUSED(address);
        internal::recordError(BLEError::unsupported, -ENOTSUP, true);
        return false;
#endif
    }

    bool AdvertisingLists::clearFilterAccept() noexcept
    {
        if (!requireThreadContext())
        {
            return false;
        }
#if defined(CONFIG_BT_FILTER_ACCEPT_LIST)
        const int result = bt_le_filter_accept_list_clear();
        if (result != 0)
        {
            recordResourceError(result);
            return false;
        }
        return true;
#else
        internal::recordError(BLEError::unsupported, -ENOTSUP, true);
        return false;
#endif
    }

    bool AdvertisingLists::addPeriodicAdvertiser(const BLEAddress &address,
                                                  std::uint8_t sid) noexcept
    {
        if (!requireThreadContext())
        {
            return false;
        }
#if defined(CONFIG_BT_PER_ADV_SYNC)
        bt_addr_le_t converted = {};
        if (sid > BT_GAP_SID_MAX || !toZephyrAddress(address, converted))
        {
            internal::recordError(BLEError::invalid_argument, -EINVAL, true);
            return false;
        }
        const int result = bt_le_per_adv_list_add(&converted, sid);
        if (result != 0)
        {
            recordResourceError(result);
            return false;
        }
        return true;
#else
        ARG_UNUSED(address);
        ARG_UNUSED(sid);
        internal::recordError(BLEError::unsupported, -ENOTSUP, true);
        return false;
#endif
    }

    bool AdvertisingLists::removePeriodicAdvertiser(const BLEAddress &address,
                                                     std::uint8_t sid) noexcept
    {
        if (!requireThreadContext())
        {
            return false;
        }
#if defined(CONFIG_BT_PER_ADV_SYNC)
        bt_addr_le_t converted = {};
        if (sid > BT_GAP_SID_MAX || !toZephyrAddress(address, converted))
        {
            internal::recordError(BLEError::invalid_argument, -EINVAL, true);
            return false;
        }
        const int result = bt_le_per_adv_list_remove(&converted, sid);
        if (result != 0)
        {
            recordResourceError(result);
            return false;
        }
        return true;
#else
        ARG_UNUSED(address);
        ARG_UNUSED(sid);
        internal::recordError(BLEError::unsupported, -ENOTSUP, true);
        return false;
#endif
    }

    bool AdvertisingLists::clearPeriodicAdvertisers() noexcept
    {
        if (!requireThreadContext())
        {
            return false;
        }
#if defined(CONFIG_BT_PER_ADV_SYNC)
        const int result = bt_le_per_adv_list_clear();
        if (result != 0)
        {
            recordResourceError(result);
            return false;
        }
        return true;
#else
        internal::recordError(BLEError::unsupported, -ENOTSUP, true);
        return false;
#endif
    }

    EncryptedAdvertisingData::~EncryptedAdvertisingData() noexcept
    {
        clear();
    }

    bool EncryptedAdvertisingData::configure(
        const std::uint8_t session_key[session_key_length],
        const std::uint8_t iv[initialization_vector_length]) noexcept
    {
        if (!requireThreadContext())
        {
            return false;
        }
        if (session_key == nullptr || iv == nullptr)
        {
            internal::recordError(BLEError::invalid_argument, -EINVAL, true);
            return false;
        }
        clear();
        ::memcpy(session_key_, session_key, session_key_length);
        ::memcpy(iv_, iv, initialization_vector_length);
        configured_ = true;
        return true;
    }

    bool EncryptedAdvertisingData::encrypt(const void *plaintext,
                                           std::size_t plaintext_length,
                                           void *encrypted,
                                           std::size_t encrypted_capacity,
                                           std::size_t &encrypted_length) noexcept
    {
        encrypted_length = 0U;
        if (!requireThreadContext())
        {
            return false;
        }
        const std::size_t required = plaintext_length + randomizer_length + mic_length;
        if (!configured_ || plaintext == nullptr || encrypted == nullptr ||
            plaintext_length == 0U || plaintext_length > maximum_plaintext_length ||
            encrypted_capacity < required)
        {
            internal::recordError(BLEError::invalid_argument, -EINVAL, true);
            return false;
        }
#if defined(CONFIG_BT_EAD)
        const int result = bt_ead_encrypt(
            session_key_, iv_, static_cast<const std::uint8_t *>(plaintext),
            plaintext_length, static_cast<std::uint8_t *>(encrypted));
        if (result != 0)
        {
            internal::recordError(BLEError::driver_error, result, true);
            return false;
        }
        encrypted_length = required;
        return true;
#else
        internal::recordError(BLEError::unsupported, -ENOTSUP, true);
        return false;
#endif
    }

    bool EncryptedAdvertisingData::decrypt(const void *encrypted,
                                           std::size_t encrypted_length,
                                           void *plaintext,
                                           std::size_t plaintext_capacity,
                                           std::size_t &plaintext_length) noexcept
    {
        plaintext_length = 0U;
        if (!requireThreadContext())
        {
            return false;
        }
        if (!configured_ || encrypted == nullptr || plaintext == nullptr ||
            encrypted_length < randomizer_length + mic_length ||
            encrypted_length > maximum_encrypted_length ||
            plaintext_capacity < encrypted_length - randomizer_length - mic_length)
        {
            internal::recordError(BLEError::invalid_argument, -EINVAL, true);
            return false;
        }
        const std::uint8_t *const bytes = static_cast<const std::uint8_t *>(encrypted);
        for (std::size_t index = 0U; index < replay_count_; ++index)
        {
            if (::memcmp(replay_cache_[index], bytes, randomizer_length) == 0)
            {
                internal::recordError(BLEError::duplicate, -EALREADY, true);
                return false;
            }
        }
#if defined(CONFIG_BT_EAD)
        const int result = bt_ead_decrypt(
            session_key_, iv_, bytes, encrypted_length,
            static_cast<std::uint8_t *>(plaintext));
        if (result != 0)
        {
            internal::recordError(BLEError::driver_error, result, true);
            return false;
        }
        ::memcpy(replay_cache_[replay_cursor_], bytes, randomizer_length);
        replay_cursor_ = (replay_cursor_ + 1U) % replay_cache_entries;
        if (replay_count_ < replay_cache_entries)
        {
            ++replay_count_;
        }
        plaintext_length = encrypted_length - randomizer_length - mic_length;
        return true;
#else
        internal::recordError(BLEError::unsupported, -ENOTSUP, true);
        return false;
#endif
    }

    void EncryptedAdvertisingData::clear() noexcept
    {
        secureClear(session_key_, sizeof(session_key_));
        secureClear(iv_, sizeof(iv_));
        secureClear(replay_cache_, sizeof(replay_cache_));
        replay_count_ = 0U;
        replay_cursor_ = 0U;
        configured_ = false;
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
