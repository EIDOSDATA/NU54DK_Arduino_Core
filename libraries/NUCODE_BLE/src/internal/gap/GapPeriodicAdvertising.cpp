/** @file @brief Periodic advertising·sync·PAST의 고정 자원 lifecycle을 구현합니다.
 * SPDX-License-Identifier: MIT
 */
#if !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE)
#include "GapInternal.h"
namespace nucode::ble::internal::gap
{
    namespace
    {
#if defined(CONFIG_BT_PER_ADV) || defined(CONFIG_BT_PER_ADV_SYNC)
        inline constexpr std::size_t maximum_ad_structures = 16U;

        /** @brief 0을 건너뛰는 periodic sync generation을 발급합니다. */
        std::uint32_t nextPeriodicSyncGeneration() noexcept
        {
            std::uint32_t generation = static_cast<std::uint32_t>(
                                           atomic_inc(&gapState().next_periodic_sync_generation)) +
                                       1U;
            if (generation == 0U)
            {
                generation = static_cast<std::uint32_t>(
                                 atomic_inc(&gapState().next_periodic_sync_generation)) +
                             1U;
            }
            return generation;
        }

        /** @brief raw AD structure stream을 bounded bt_data view로 해석합니다. */
        bool decodePeriodicData(const std::uint8_t *payload, std::size_t length,
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
#endif

#if defined(CONFIG_BT_PER_ADV_SYNC)
        /** @brief callback의 PAST sender link가 명시적으로 구독된 현재 handle인지 확인합니다. */
        bool pastTransferSubscribed(struct bt_conn *connection) noexcept
        {
            if (connection == nullptr)
            {
                return false;
            }
            for (std::size_t index = 0U; index < maximum_connection_slots; ++index)
            {
                const BLEConnectionHandle handle = gapState().past_subscriptions[index];
                struct bt_conn *subscribed = internal::referenceConnection(handle);
                const bool matches = subscribed == connection;
                if (subscribed != nullptr)
                {
                    bt_conn_unref(subscribed);
                }
                if (matches)
                {
                    return true;
                }
            }
            return false;
        }

        /** @brief handle이 현재 periodic sync generation인지 검사합니다. */
        bool lookupPeriodicSync(BLEPeriodicSyncHandle handle,
                                struct bt_le_per_adv_sync *&instance,
                                std::uint32_t &device_generation) noexcept
        {
            if (!handle.valid())
            {
                return false;
            }
            k_spinlock_key_t key = k_spin_lock(&gapState().configuration_lock);
            const PeriodicSyncContext &context = gapState().periodic_sync;
            const bool matches = context.instance != nullptr &&
                                 context.generation ==
                                     BLEConnectionHandleAccess::generation(handle);
            instance = matches ? context.instance : nullptr;
            device_generation = matches ? context.device_generation : 0U;
            k_spin_unlock(&gapState().configuration_lock, key);
            return matches;
        }

        /** @brief stack sync pointer를 현재 generation handle로 변환합니다. */
        bool currentPeriodicHandle(struct bt_le_per_adv_sync *instance,
                                   BLEPeriodicSyncHandle &handle,
                                   std::uint32_t &device_generation) noexcept
        {
            bool matches = false;
            k_spinlock_key_t key = k_spin_lock(&gapState().configuration_lock);
            const PeriodicSyncContext &context = gapState().periodic_sync;
            if (context.instance == instance && context.generation != 0U)
            {
                handle = BLEConnectionHandleAccess::makePeriodicSync(context.generation);
                device_generation = context.device_generation;
                matches = true;
            }
            k_spin_unlock(&gapState().configuration_lock, key);
            return matches && device_generation == static_cast<std::uint32_t>(
                                                     atomic_get(&gapState().device_session_generation));
        }

        /** @brief 직접 sync 또는 PAST 수신 sync를 고정 slot에 결합합니다. */
        void periodicSynced(struct bt_le_per_adv_sync *instance,
                            struct bt_le_per_adv_sync_synced_info *information) noexcept
        {
            BLEPeriodicSyncHandle handle;
            std::uint32_t device_generation = 0U;
            if (!currentPeriodicHandle(instance, handle, device_generation))
            {
                k_spinlock_key_t key = k_spin_lock(&gapState().configuration_lock);
                PeriodicSyncContext &context = gapState().periodic_sync;
                if (context.instance == nullptr &&
                    pastTransferSubscribed(information->conn))
                {
                    context.instance = instance;
                    context.generation = nextPeriodicSyncGeneration();
                    context.device_generation = static_cast<std::uint32_t>(
                        atomic_get(&gapState().device_session_generation));
                    context.address = fromZephyrAddress(*information->addr);
                    context.sid = information->sid;
                    handle = BLEConnectionHandleAccess::makePeriodicSync(context.generation);
                    device_generation = context.device_generation;
                }
                k_spin_unlock(&gapState().configuration_lock, key);
                if (!handle.valid())
                {
                    return;
                }
            }
            atomic_set(&gapState().periodic_sync.synchronized, 1);
            queueEvent(BLEEvent::periodic_sync_synchronized, {}, BLELinkRole::none,
                       device_generation, {}, handle);
        }

        /** @brief 종료된 sync를 먼저 무효화하고 reason event를 전달합니다. */
        void periodicTerminated(struct bt_le_per_adv_sync *instance,
                                const struct bt_le_per_adv_sync_term_info *information) noexcept
        {
            ARG_UNUSED(information);
            BLEPeriodicSyncHandle handle;
            std::uint32_t device_generation = 0U;
            if (!currentPeriodicHandle(instance, handle, device_generation))
            {
                return;
            }
            k_spinlock_key_t key = k_spin_lock(&gapState().configuration_lock);
            PeriodicSyncContext &context = gapState().periodic_sync;
            context.instance = nullptr;
            context.generation = 0U;
            context.device_generation = 0U;
            context.address = BLEAddress{};
            context.sid = 0xffU;
            atomic_set(&context.synchronized, 0);
            k_spin_unlock(&gapState().configuration_lock, key);
            queueEvent(BLEEvent::periodic_sync_terminated, {}, BLELinkRole::none,
                       device_generation, {}, handle);
        }

        /** @brief controller report를 generation이 결합된 고정 queue value로 복사합니다. */
        void periodicReceived(struct bt_le_per_adv_sync *instance,
                              const struct bt_le_per_adv_sync_recv_info *information,
                              struct net_buf_simple *buffer) noexcept
        {
            BLEPeriodicSyncHandle handle;
            std::uint32_t device_generation = 0U;
            if (!currentPeriodicHandle(instance, handle, device_generation) ||
                information == nullptr || buffer == nullptr)
            {
                return;
            }
            const std::size_t copied = buffer->len > BLEPeriodicReport::maximum_payload_length
                                           ? BLEPeriodicReport::maximum_payload_length
                                           : buffer->len;
            PeriodicReportRecord record = {};
            record.report.sync = handle;
            record.report.address = fromZephyrAddress(*information->addr);
            record.report.sid = information->sid;
            record.report.tx_power = information->tx_power;
            record.report.rssi = information->rssi;
#if defined(CONFIG_BT_PER_ADV_SYNC_RSP)
            record.report.periodic_event_counter = information->periodic_event_counter;
            record.report.subevent = information->subevent;
#endif
            record.report.truncated = buffer->len > copied;
            record.report.payload_length = static_cast<std::uint16_t>(copied);
            if (copied != 0U)
            {
                ::memcpy(record.report.payload, buffer->data, copied);
            }
            record.device_generation = device_generation;
            if (k_msgq_put(&periodicReportQueue(), &record, K_NO_WAIT) != 0)
            {
                atomic_inc(&gapState().dropped_periodic_report_value);
                atomic_set(&gapState().last_driver_error_value, -ENOBUFS);
                atomic_set(&gapState().last_error_value,
                           static_cast<atomic_val_t>(BLEError::event_overflow));
                return;
            }
            queueEvent(BLEEvent::periodic_report, {}, BLELinkRole::none,
                       device_generation, {}, handle);
        }

        struct bt_le_per_adv_sync_cb periodic_sync_callbacks = {
            .synced = periodicSynced,
            .term = periodicTerminated,
            .recv = periodicReceived,
        };

        /** @brief periodic sync callback을 image에서 한 번만 등록합니다. */
        bool ensurePeriodicCallbacks() noexcept
        {
            if (atomic_cas(&gapState().periodic_sync_callback_registered, 0, 1))
            {
                const int result = bt_le_per_adv_sync_cb_register(&periodic_sync_callbacks);
                if (result < 0 && result != -EEXIST)
                {
                    atomic_set(&gapState().periodic_sync_callback_registered, 0);
                    internal::recordError(BLEError::driver_error, result, true);
                    return false;
                }
            }
            return true;
        }
#endif
    } // namespace

    bool currentPeriodicSync(BLEPeriodicSyncHandle handle,
                             struct bt_le_per_adv_sync *&instance,
                             std::uint32_t &device_generation) noexcept
    {
#if defined(CONFIG_BT_PER_ADV_SYNC)
        return lookupPeriodicSync(handle, instance, device_generation);
#else
        ARG_UNUSED(handle);
        instance = nullptr;
        device_generation = 0U;
        return false;
#endif
    }

    bool periodicAdvertisingUsesSet(BLEAdvertisingSetHandle handle) noexcept
    {
        k_spinlock_key_t key = k_spin_lock(&gapState().configuration_lock);
        const bool matches = gapState().periodic_advertising.configured != 0 &&
                             gapState().periodic_advertising.advertising_set == handle;
        k_spin_unlock(&gapState().configuration_lock, key);
        return matches;
    }

    void releasePeriodicAdvertisingSet(BLEAdvertisingSetHandle handle) noexcept
    {
        k_spinlock_key_t key = k_spin_lock(&gapState().configuration_lock);
        if (gapState().periodic_advertising.advertising_set == handle &&
            atomic_get(&gapState().periodic_advertising.active) == 0)
        {
            gapState().periodic_advertising.advertising_set = {};
            gapState().periodic_advertising.length = 0U;
            atomic_set(&gapState().periodic_advertising.configured, 0);
        }
        k_spin_unlock(&gapState().configuration_lock, key);
    }

    void endPeriodicAdvertising() noexcept
    {
#if defined(CONFIG_BT_PER_ADV)
        struct bt_le_ext_adv *advertiser = nullptr;
        std::uint32_t unused_generation = 0U;
        const BLEAdvertisingSetHandle advertising_set =
            gapState().periodic_advertising.advertising_set;
        if (currentAdvertisingSet(advertising_set, advertiser, unused_generation) &&
            atomic_get(&gapState().periodic_advertising.active) != 0)
        {
            static_cast<void>(bt_le_per_adv_stop(advertiser));
        }
#endif
#if defined(CONFIG_BT_PER_ADV_SYNC)
        struct bt_le_per_adv_sync *sync = nullptr;
        k_spinlock_key_t sync_key = k_spin_lock(&gapState().configuration_lock);
        sync = gapState().periodic_sync.instance;
        gapState().periodic_sync.instance = nullptr;
        gapState().periodic_sync.generation = 0U;
        gapState().periodic_sync.device_generation = 0U;
        gapState().periodic_sync.address = BLEAddress{};
        gapState().periodic_sync.sid = 0xffU;
        atomic_set(&gapState().periodic_sync.synchronized, 0);
        k_spin_unlock(&gapState().configuration_lock, sync_key);
        if (sync != nullptr)
        {
            static_cast<void>(bt_le_per_adv_sync_delete(sync));
        }
#endif
        k_spinlock_key_t key = k_spin_lock(&gapState().configuration_lock);
        gapState().periodic_advertising.advertising_set = {};
        gapState().periodic_advertising.length = 0U;
        atomic_set(&gapState().periodic_advertising.configured, 0);
        atomic_set(&gapState().periodic_advertising.active, 0);
        for (std::size_t index = 0U; index < maximum_connection_slots; ++index)
        {
            gapState().past_subscriptions[index] = {};
        }
        k_spin_unlock(&gapState().configuration_lock, key);
        k_msgq_purge(&periodicReportQueue());
    }
} // namespace nucode::ble::internal::gap

namespace nucode::ble
{
    using namespace internal::gap;

    bool PeriodicAdvertising::configure(
        BLEAdvertisingSetHandle advertising_set,
        const BLEPeriodicAdvertisingParameters &parameters) noexcept
    {
        if (!requireThreadContext())
        {
            return false;
        }
#if defined(CONFIG_BT_PER_ADV)
        if (parameters.interval_min < 0x0006U ||
            parameters.interval_min > parameters.interval_max)
        {
            internal::recordError(BLEError::invalid_argument, -EINVAL, true);
            return false;
        }
        struct bt_le_ext_adv *instance = nullptr;
        std::uint32_t device_generation = 0U;
        if (!currentAdvertisingSet(advertising_set, instance, device_generation))
        {
            internal::recordError(BLEError::wrong_state, -ENOENT, true);
            return false;
        }
        if (atomic_get(&gapState().periodic_advertising.active) != 0)
        {
            internal::recordError(BLEError::busy, -EBUSY, true);
            return false;
        }
        std::uint32_t options = BT_LE_PER_ADV_OPT_NONE;
        if (parameters.include_tx_power)
        {
            options |= BT_LE_PER_ADV_OPT_USE_TX_POWER;
        }
        if (parameters.include_adi)
        {
            options |= BT_LE_PER_ADV_OPT_INCLUDE_ADI;
        }
        const struct bt_le_per_adv_param periodic_parameters = {
            .interval_min = parameters.interval_min,
            .interval_max = parameters.interval_max,
            .options = options,
#if defined(CONFIG_BT_PER_ADV_RSP)
            .num_subevents = 0U,
            .subevent_interval = 0U,
            .response_slot_delay = 0U,
            .response_slot_spacing = 0U,
            .num_response_slots = 0U,
#endif
        };
        const int result = bt_le_per_adv_set_param(instance, &periodic_parameters);
        if (result < 0)
        {
            internal::recordError(BLEError::driver_error, result, true);
            return false;
        }
        gapState().periodic_advertising.advertising_set = advertising_set;
        atomic_set(&gapState().periodic_advertising.configured, 1);
        return true;
#else
        ARG_UNUSED(advertising_set);
        ARG_UNUSED(parameters);
        internal::recordError(BLEError::unsupported, -ENOTSUP, true);
        return false;
#endif
    }

    bool PeriodicAdvertising::setData(BLEAdvertisingSetHandle advertising_set,
                                      const void *data, std::size_t length) noexcept
    {
        if (!requireThreadContext())
        {
            return false;
        }
#if defined(CONFIG_BT_PER_ADV)
        if (length > maximum_payload_length || (length != 0U && data == nullptr) ||
            !periodicAdvertisingUsesSet(advertising_set))
        {
            internal::recordError(length > maximum_payload_length ? BLEError::payload_overflow
                                                                  : BLEError::invalid_argument,
                                  length > maximum_payload_length ? -EMSGSIZE : -EINVAL, true);
            return false;
        }
        struct bt_data fields[maximum_ad_structures] = {};
        std::size_t field_count = 0U;
        if (!decodePeriodicData(static_cast<const std::uint8_t *>(data), length, fields,
                                field_count))
        {
            internal::recordError(BLEError::invalid_argument, -EINVAL, true);
            return false;
        }
        struct bt_le_ext_adv *instance = nullptr;
        std::uint32_t device_generation = 0U;
        if (!currentAdvertisingSet(advertising_set, instance, device_generation))
        {
            internal::recordError(BLEError::wrong_state, -ENOENT, true);
            return false;
        }
        if (length != 0U)
        {
            ::memcpy(gapState().periodic_advertising.data, data, length);
            static_cast<void>(decodePeriodicData(gapState().periodic_advertising.data,
                                                 length, fields, field_count));
        }
        const int result = bt_le_per_adv_set_data(instance, fields, field_count);
        if (result < 0)
        {
            internal::recordError(BLEError::driver_error, result, true);
            return false;
        }
        gapState().periodic_advertising.length = length;
        return true;
#else
        ARG_UNUSED(advertising_set);
        ARG_UNUSED(data);
        ARG_UNUSED(length);
        internal::recordError(BLEError::unsupported, -ENOTSUP, true);
        return false;
#endif
    }

    bool PeriodicAdvertising::start(BLEAdvertisingSetHandle advertising_set) noexcept
    {
        if (!requireThreadContext())
        {
            return false;
        }
#if defined(CONFIG_BT_PER_ADV)
        struct bt_le_ext_adv *instance = nullptr;
        std::uint32_t device_generation = 0U;
        if (!periodicAdvertisingUsesSet(advertising_set) ||
            !currentAdvertisingSet(advertising_set, instance, device_generation))
        {
            internal::recordError(BLEError::wrong_state, -ENOENT, true);
            return false;
        }
        if (!atomic_cas(&gapState().periodic_advertising.active, 0, 1))
        {
            internal::recordError(BLEError::already_started, -EALREADY, true);
            return false;
        }
        const int result = bt_le_per_adv_start(instance);
        if (result < 0)
        {
            atomic_set(&gapState().periodic_advertising.active, 0);
            internal::recordError(BLEError::driver_error, result, true);
            return false;
        }
        queueEvent(BLEEvent::periodic_advertising_started, {}, BLELinkRole::none,
                   device_generation, advertising_set);
        return true;
#else
        ARG_UNUSED(advertising_set);
        internal::recordError(BLEError::unsupported, -ENOTSUP, true);
        return false;
#endif
    }

    bool PeriodicAdvertising::stop(BLEAdvertisingSetHandle advertising_set) noexcept
    {
        if (!requireThreadContext())
        {
            return false;
        }
#if defined(CONFIG_BT_PER_ADV)
        struct bt_le_ext_adv *instance = nullptr;
        std::uint32_t device_generation = 0U;
        if (!periodicAdvertisingUsesSet(advertising_set) ||
            !currentAdvertisingSet(advertising_set, instance, device_generation) ||
            atomic_get(&gapState().periodic_advertising.active) == 0)
        {
            internal::recordError(BLEError::wrong_state, -EALREADY, true);
            return false;
        }
        const int result = bt_le_per_adv_stop(instance);
        if (result < 0)
        {
            internal::recordError(BLEError::driver_error, result, true);
            return false;
        }
        atomic_set(&gapState().periodic_advertising.active, 0);
        queueEvent(BLEEvent::periodic_advertising_stopped, {}, BLELinkRole::none,
                   device_generation, advertising_set);
        return true;
#else
        ARG_UNUSED(advertising_set);
        internal::recordError(BLEError::unsupported, -ENOTSUP, true);
        return false;
#endif
    }

    bool PeriodicAdvertising::running(BLEAdvertisingSetHandle advertising_set) const noexcept
    {
        return periodicAdvertisingUsesSet(advertising_set) &&
               atomic_get(&gapState().periodic_advertising.active) != 0;
    }

    bool PeriodicAdvertising::createSync(const BLEAddress &address, std::uint8_t sid,
                                         BLEPeriodicSyncHandle &sync, std::uint16_t skip,
                                         std::uint16_t timeout_10ms,
                                         bool filter_duplicates) noexcept
    {
        sync = BLEPeriodicSyncHandle{};
        if (!requireThreadContext())
        {
            return false;
        }
#if defined(CONFIG_BT_PER_ADV_SYNC)
        if (!address.valid() || sid > BT_GAP_SID_MAX || skip > 0x01f3U ||
            timeout_10ms < 0x000aU || timeout_10ms > 0x4000U)
        {
            internal::recordError(BLEError::invalid_argument, -EINVAL, true);
            return false;
        }
        if (!ensurePeriodicCallbacks() || gapState().periodic_sync.instance != nullptr)
        {
            if (gapState().periodic_sync.instance != nullptr)
            {
                internal::recordError(BLEError::busy, -EBUSY, true);
            }
            return false;
        }
        struct bt_le_per_adv_sync_param parameters = {};
        if (!toZephyrAddress(address, parameters.addr))
        {
            internal::recordError(BLEError::invalid_argument, -EINVAL, true);
            return false;
        }
        parameters.sid = sid;
        parameters.skip = skip;
        parameters.timeout = timeout_10ms;
        parameters.options = filter_duplicates ? BT_LE_PER_ADV_SYNC_OPT_FILTER_DUPLICATE
                                               : BT_LE_PER_ADV_SYNC_OPT_NONE;
        struct bt_le_per_adv_sync *instance = nullptr;
        const int result = bt_le_per_adv_sync_create(&parameters, &instance);
        if (result < 0)
        {
            internal::recordError(BLEError::driver_error, result, true);
            return false;
        }
        const std::uint32_t generation = nextPeriodicSyncGeneration();
        const std::uint32_t device_generation = static_cast<std::uint32_t>(
            atomic_get(&gapState().device_session_generation));
        k_spinlock_key_t key = k_spin_lock(&gapState().configuration_lock);
        gapState().periodic_sync.instance = instance;
        gapState().periodic_sync.generation = generation;
        gapState().periodic_sync.device_generation = device_generation;
        gapState().periodic_sync.address = address;
        gapState().periodic_sync.sid = sid;
        atomic_set(&gapState().periodic_sync.synchronized, 0);
        k_spin_unlock(&gapState().configuration_lock, key);
        sync = internal::BLEConnectionHandleAccess::makePeriodicSync(generation);
        queueEvent(BLEEvent::periodic_sync_created, {}, BLELinkRole::none,
                   device_generation, {}, sync);
        return true;
#else
        ARG_UNUSED(address);
        ARG_UNUSED(sid);
        ARG_UNUSED(skip);
        ARG_UNUSED(timeout_10ms);
        ARG_UNUSED(filter_duplicates);
        internal::recordError(BLEError::unsupported, -ENOTSUP, true);
        return false;
#endif
    }

    bool PeriodicAdvertising::deleteSync(BLEPeriodicSyncHandle sync) noexcept
    {
        if (!requireThreadContext())
        {
            return false;
        }
#if defined(CONFIG_BT_PER_ADV_SYNC)
        struct bt_le_per_adv_sync *instance = nullptr;
        std::uint32_t device_generation = 0U;
        if (!lookupPeriodicSync(sync, instance, device_generation))
        {
            internal::recordError(BLEError::wrong_state, -ENOENT, true);
            return false;
        }
        const int result = bt_le_per_adv_sync_delete(instance);
        if (result < 0)
        {
            internal::recordError(BLEError::driver_error, result, true);
            return false;
        }
        k_spinlock_key_t key = k_spin_lock(&gapState().configuration_lock);
        if (gapState().periodic_sync.instance == instance)
        {
            gapState().periodic_sync.instance = nullptr;
            gapState().periodic_sync.generation = 0U;
            gapState().periodic_sync.device_generation = 0U;
            gapState().periodic_sync.address = BLEAddress{};
            gapState().periodic_sync.sid = 0xffU;
            atomic_set(&gapState().periodic_sync.synchronized, 0);
        }
        k_spin_unlock(&gapState().configuration_lock, key);
        queueEvent(BLEEvent::periodic_sync_deleted, {}, BLELinkRole::none,
                   device_generation, {}, sync);
        return true;
#else
        ARG_UNUSED(sync);
        internal::recordError(BLEError::unsupported, -ENOTSUP, true);
        return false;
#endif
    }

    bool PeriodicAdvertising::exists(BLEPeriodicSyncHandle sync) const noexcept
    {
#if defined(CONFIG_BT_PER_ADV_SYNC)
        struct bt_le_per_adv_sync *instance = nullptr;
        std::uint32_t device_generation = 0U;
        return lookupPeriodicSync(sync, instance, device_generation);
#else
        ARG_UNUSED(sync);
        return false;
#endif
    }

    bool PeriodicAdvertising::synchronized(BLEPeriodicSyncHandle sync) const noexcept
    {
        return exists(sync) && atomic_get(&gapState().periodic_sync.synchronized) != 0;
    }

    int PeriodicAdvertising::available() const noexcept
    {
        return static_cast<int>(k_msgq_num_used_get(&periodicReportQueue()));
    }

    bool PeriodicAdvertising::read(BLEPeriodicReport &report) noexcept
    {
        PeriodicReportRecord record = {};
        while (k_msgq_get(&periodicReportQueue(), &record, K_NO_WAIT) == 0)
        {
            if (record.device_generation == static_cast<std::uint32_t>(
                                                atomic_get(&gapState().device_session_generation)))
            {
                report = record.report;
                return true;
            }
        }
        return false;
    }

    void PeriodicAdvertising::onReport(BLEPeriodicReportCallback callback,
                                       void *context) noexcept
    {
        gapState().periodic_report_callback = callback;
        gapState().periodic_report_context = context;
    }

    std::uint32_t PeriodicAdvertising::droppedReports() const noexcept
    {
        return static_cast<std::uint32_t>(
            atomic_get(&gapState().dropped_periodic_report_value));
    }

    bool PeriodicAdvertising::transferSync(BLEPeriodicSyncHandle sync,
                                           BLEConnectionHandle connection,
                                           std::uint16_t service_data) noexcept
    {
        if (!requireThreadContext())
        {
            return false;
        }
#if defined(CONFIG_BT_PER_ADV_SYNC_TRANSFER_SENDER)
        struct bt_le_per_adv_sync *sync_instance = nullptr;
        std::uint32_t sync_generation = 0U;
        if (!lookupPeriodicSync(sync, sync_instance, sync_generation) ||
            atomic_get(&gapState().periodic_sync.synchronized) == 0)
        {
            internal::recordError(BLEError::wrong_state, -ENOENT, true);
            return false;
        }
        struct bt_conn *connection_instance = internal::referenceConnection(connection);
        if (connection_instance == nullptr)
        {
            internal::recordError(BLEError::not_connected, -ENOTCONN, true);
            return false;
        }
        const int result = bt_le_per_adv_sync_transfer(sync_instance, connection_instance,
                                                       service_data);
        bt_conn_unref(connection_instance);
        if (result < 0)
        {
            internal::recordError(BLEError::driver_error, result, true);
            return false;
        }
        queueEvent(BLEEvent::past_transferred, connection, BLELinkRole::none,
                   sync_generation, {}, sync);
        return true;
#else
        ARG_UNUSED(sync);
        ARG_UNUSED(connection);
        ARG_UNUSED(service_data);
        internal::recordError(BLEError::unsupported, -ENOTSUP, true);
        return false;
#endif
    }

    bool PeriodicAdvertising::transferSet(BLEAdvertisingSetHandle advertising_set,
                                          BLEConnectionHandle connection,
                                          std::uint16_t service_data) noexcept
    {
        if (!requireThreadContext())
        {
            return false;
        }
#if defined(CONFIG_BT_PER_ADV_SYNC_TRANSFER_SENDER)
        struct bt_le_ext_adv *advertiser = nullptr;
        std::uint32_t device_generation = 0U;
        if (!periodicAdvertisingUsesSet(advertising_set) ||
            !currentAdvertisingSet(advertising_set, advertiser, device_generation))
        {
            internal::recordError(BLEError::wrong_state, -ENOENT, true);
            return false;
        }
        struct bt_conn *connection_instance = internal::referenceConnection(connection);
        if (connection_instance == nullptr)
        {
            internal::recordError(BLEError::not_connected, -ENOTCONN, true);
            return false;
        }
        const int result = bt_le_per_adv_set_info_transfer(advertiser, connection_instance,
                                                           service_data);
        bt_conn_unref(connection_instance);
        if (result < 0)
        {
            internal::recordError(BLEError::driver_error, result, true);
            return false;
        }
        queueEvent(BLEEvent::past_transferred, connection, BLELinkRole::none,
                   device_generation, advertising_set);
        return true;
#else
        ARG_UNUSED(advertising_set);
        ARG_UNUSED(connection);
        ARG_UNUSED(service_data);
        internal::recordError(BLEError::unsupported, -ENOTSUP, true);
        return false;
#endif
    }

    bool PeriodicAdvertising::subscribeTransfers(BLEConnectionHandle connection,
                                                 std::uint16_t skip,
                                                 std::uint16_t timeout_10ms,
                                                 bool filter_duplicates) noexcept
    {
        if (!requireThreadContext())
        {
            return false;
        }
#if defined(CONFIG_BT_PER_ADV_SYNC_TRANSFER_RECEIVER)
        if (skip > 0x01f3U || timeout_10ms < 0x000aU || timeout_10ms > 0x4000U ||
            !ensurePeriodicCallbacks())
        {
            if (skip > 0x01f3U || timeout_10ms < 0x000aU || timeout_10ms > 0x4000U)
            {
                internal::recordError(BLEError::invalid_argument, -EINVAL, true);
            }
            return false;
        }
        struct bt_conn *instance = internal::referenceConnection(connection);
        if (instance == nullptr)
        {
            internal::recordError(BLEError::not_connected, -ENOTCONN, true);
            return false;
        }
        const struct bt_le_per_adv_sync_transfer_param parameters = {
            .skip = skip,
            .timeout = timeout_10ms,
            .options = filter_duplicates
                           ? BT_LE_PER_ADV_SYNC_TRANSFER_OPT_FILTER_DUPLICATES
                           : BT_LE_PER_ADV_SYNC_TRANSFER_OPT_NONE,
        };
        const int result = bt_le_per_adv_sync_transfer_subscribe(instance, &parameters);
        bt_conn_unref(instance);
        if (result < 0)
        {
            internal::recordError(BLEError::driver_error, result, true);
            return false;
        }
        const std::size_t slot = internal::BLEConnectionHandleAccess::slot(connection);
        if (slot < maximum_connection_slots)
        {
            gapState().past_subscriptions[slot] = connection;
        }
        queueEvent(BLEEvent::past_subscribed, connection);
        return true;
#else
        ARG_UNUSED(connection);
        ARG_UNUSED(skip);
        ARG_UNUSED(timeout_10ms);
        ARG_UNUSED(filter_duplicates);
        internal::recordError(BLEError::unsupported, -ENOTSUP, true);
        return false;
#endif
    }

    bool PeriodicAdvertising::unsubscribeTransfers(BLEConnectionHandle connection) noexcept
    {
        if (!requireThreadContext())
        {
            return false;
        }
#if defined(CONFIG_BT_PER_ADV_SYNC_TRANSFER_RECEIVER)
        struct bt_conn *instance = internal::referenceConnection(connection);
        if (instance == nullptr)
        {
            internal::recordError(BLEError::not_connected, -ENOTCONN, true);
            return false;
        }
        const int result = bt_le_per_adv_sync_transfer_unsubscribe(instance);
        bt_conn_unref(instance);
        if (result < 0)
        {
            internal::recordError(BLEError::driver_error, result, true);
            return false;
        }
        const std::size_t slot = internal::BLEConnectionHandleAccess::slot(connection);
        if (slot < maximum_connection_slots &&
            gapState().past_subscriptions[slot] == connection)
        {
            gapState().past_subscriptions[slot] = {};
        }
        queueEvent(BLEEvent::past_unsubscribed, connection);
        return true;
#else
        ARG_UNUSED(connection);
        internal::recordError(BLEError::unsupported, -ENOTSUP, true);
        return false;
#endif
    }
} // namespace nucode::ble
#endif
