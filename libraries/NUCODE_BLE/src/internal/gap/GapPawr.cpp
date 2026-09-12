/** @file @brief PAwR advertiser·scanner의 고정 subevent/slot lifecycle을 구현합니다.
 * SPDX-License-Identifier: MIT
 */
#if !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE)
#include "GapInternal.h"
namespace nucode::ble::internal::gap
{
    namespace
    {
#if defined(CONFIG_BT_PER_ADV_RSP)
        /** @brief controller advertiser pointer를 현재 PAwR set으로 대조합니다. */
        bool currentPawrAdvertiser(struct bt_le_ext_adv *advertiser,
                                   BLEAdvertisingSetHandle &handle,
                                   std::uint32_t &device_generation) noexcept
        {
            bool matches = false;
            k_spinlock_key_t key = k_spin_lock(&gapState().configuration_lock);
            const ExtendedAdvertisingContext &extended = gapState().extended_advertising;
            const PawrContext &pawr = gapState().pawr;
            if (pawr.configured && extended.instance == advertiser &&
                extended.generation != 0U &&
                pawr.advertising_set ==
                    BLEConnectionHandleAccess::makeAdvertisingSet(extended.generation))
            {
                handle = pawr.advertising_set;
                device_generation = extended.device_generation;
                matches = true;
            }
            k_spin_unlock(&gapState().configuration_lock, key);
            return matches && device_generation == static_cast<std::uint32_t>(
                                                     atomic_get(&gapState().device_session_generation));
        }
#endif
    } // namespace

    void pawrDataRequested(struct bt_le_ext_adv *advertiser,
                           const struct bt_le_per_adv_data_request *request) noexcept
    {
#if defined(CONFIG_BT_PER_ADV_RSP)
        BLEAdvertisingSetHandle handle;
        std::uint32_t device_generation = 0U;
        if (request == nullptr ||
            !currentPawrAdvertiser(advertiser, handle, device_generation) ||
            request->count == 0U ||
            static_cast<std::size_t>(request->start) + request->count >
                gapState().pawr.subevent_count)
        {
            internal::recordError(BLEError::invalid_argument, -EINVAL, true);
            return;
        }
        struct bt_le_per_adv_subevent_data_params
            parameters[Pawr::maximum_subevents] = {};
        struct net_buf_simple buffers[Pawr::maximum_subevents] = {};
        for (std::size_t offset = 0U; offset < request->count; ++offset)
        {
            const std::size_t subevent = static_cast<std::size_t>(request->start) + offset;
            const PawrSubeventContext &source = gapState().pawr.subevents[subevent];
            if (!source.configured)
            {
                internal::recordError(BLEError::wrong_state, -ENOENT, true);
                return;
            }
            net_buf_simple_init_with_data(&buffers[offset],
                                          const_cast<std::uint8_t *>(source.data),
                                          source.length);
            parameters[offset].subevent = static_cast<std::uint8_t>(subevent);
            parameters[offset].response_slot_start = source.response_slot_start;
            parameters[offset].response_slot_count = source.response_slot_count;
            parameters[offset].data = &buffers[offset];
        }
        const int result = bt_le_per_adv_set_subevent_data(
            advertiser, request->count, parameters);
        if (result < 0)
        {
            internal::recordError(BLEError::driver_error, result, true);
            return;
        }
        queueEvent(BLEEvent::pawr_data_requested, {}, BLELinkRole::none,
                   device_generation, handle);
#else
        ARG_UNUSED(advertiser);
        ARG_UNUSED(request);
#endif
    }

    void pawrResponseReceived(struct bt_le_ext_adv *advertiser,
                              struct bt_le_per_adv_response_info *information,
                              struct net_buf_simple *buffer) noexcept
    {
#if defined(CONFIG_BT_PER_ADV_RSP)
        BLEAdvertisingSetHandle handle;
        std::uint32_t device_generation = 0U;
        if (information == nullptr ||
            !currentPawrAdvertiser(advertiser, handle, device_generation) ||
            information->subevent >= gapState().pawr.subevent_count ||
            information->response_slot >= gapState().pawr.response_slot_count)
        {
            internal::recordError(BLEError::invalid_argument, -ERANGE, true);
            return;
        }
        const std::size_t source_length = buffer == nullptr ? 0U : buffer->len;
        const std::size_t copied = source_length > BLEPawrResponse::maximum_payload_length
                                       ? BLEPawrResponse::maximum_payload_length
                                       : source_length;
        PawrResponseRecord record = {};
        record.response.advertising_set = handle;
        record.response.subevent = information->subevent;
        record.response.response_slot = information->response_slot;
        record.response.transmit_status = information->tx_status;
        record.response.tx_power = information->tx_power;
        record.response.rssi = information->rssi;
        record.response.received = buffer != nullptr;
        record.response.truncated = source_length > copied;
        record.response.payload_length = static_cast<std::uint16_t>(copied);
        if (copied != 0U)
        {
            ::memcpy(record.response.payload, buffer->data, copied);
        }
        record.device_generation = device_generation;
        if (k_msgq_put(&pawrResponseQueue(), &record, K_NO_WAIT) != 0)
        {
            atomic_inc(&gapState().dropped_pawr_response_value);
            atomic_set(&gapState().last_driver_error_value, -ENOBUFS);
            atomic_set(&gapState().last_error_value,
                       static_cast<atomic_val_t>(BLEError::event_overflow));
            return;
        }
        queueEvent(BLEEvent::pawr_response_received, {}, BLELinkRole::none,
                   device_generation, handle);
#else
        ARG_UNUSED(advertiser);
        ARG_UNUSED(information);
        ARG_UNUSED(buffer);
#endif
    }

    void releasePawrSet(BLEAdvertisingSetHandle handle) noexcept
    {
        k_spinlock_key_t key = k_spin_lock(&gapState().configuration_lock);
        if (gapState().pawr.advertising_set == handle)
        {
            gapState().pawr = PawrContext{};
        }
        k_spin_unlock(&gapState().configuration_lock, key);
    }

    void endPawr() noexcept
    {
        k_spinlock_key_t key = k_spin_lock(&gapState().configuration_lock);
        gapState().pawr = PawrContext{};
        k_spin_unlock(&gapState().configuration_lock, key);
        k_msgq_purge(&pawrResponseQueue());
    }
} // namespace nucode::ble::internal::gap

namespace nucode::ble
{
    using namespace internal::gap;

    bool Pawr::configureAdvertiser(
        BLEAdvertisingSetHandle advertising_set,
        const BLEPawrAdvertisingParameters &parameters) noexcept
    {
        if (!requireThreadContext())
        {
            return false;
        }
#if defined(CONFIG_BT_PER_ADV_RSP)
        if (parameters.interval_min < 0x0006U ||
            parameters.interval_min > parameters.interval_max ||
            parameters.subevents == 0U || parameters.subevents > maximum_subevents ||
            parameters.subevent_interval < 6U ||
            parameters.response_slot_delay == 0U ||
            parameters.response_slot_spacing < 2U ||
            parameters.response_slots == 0U ||
            parameters.response_slots > maximum_response_slots)
        {
            internal::recordError(BLEError::invalid_argument, -EINVAL, true);
            return false;
        }
        struct bt_le_ext_adv *advertiser = nullptr;
        std::uint32_t device_generation = 0U;
        if (!currentAdvertisingSet(advertising_set, advertiser, device_generation))
        {
            internal::recordError(BLEError::wrong_state, -ENOENT, true);
            return false;
        }
        BLEPeriodicAdvertisingParameters base_parameters{};
        base_parameters.interval_min = parameters.interval_min;
        base_parameters.interval_max = parameters.interval_max;
        base_parameters.include_tx_power = parameters.include_tx_power;
        base_parameters.include_adi = parameters.include_adi;
        if (!BLEPeriodicAdvertising.configure(advertising_set, base_parameters))
        {
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
        const struct bt_le_per_adv_param pawr_parameters = {
            .interval_min = parameters.interval_min,
            .interval_max = parameters.interval_max,
            .options = options,
            .num_subevents = parameters.subevents,
            .subevent_interval = parameters.subevent_interval,
            .response_slot_delay = parameters.response_slot_delay,
            .response_slot_spacing = parameters.response_slot_spacing,
            .num_response_slots = parameters.response_slots,
        };
        const int result = bt_le_per_adv_set_param(advertiser, &pawr_parameters);
        if (result < 0)
        {
            releasePeriodicAdvertisingSet(advertising_set);
            internal::recordError(BLEError::driver_error, result, true);
            return false;
        }
        k_spinlock_key_t key = k_spin_lock(&gapState().configuration_lock);
        gapState().pawr = PawrContext{};
        gapState().pawr.advertising_set = advertising_set;
        gapState().pawr.subevent_count = parameters.subevents;
        gapState().pawr.response_slot_count = parameters.response_slots;
        gapState().pawr.configured = true;
        k_spin_unlock(&gapState().configuration_lock, key);
        return true;
#else
        ARG_UNUSED(advertising_set);
        ARG_UNUSED(parameters);
        internal::recordError(BLEError::unsupported, -ENOTSUP, true);
        return false;
#endif
    }

    bool Pawr::setSubeventData(BLEAdvertisingSetHandle advertising_set,
                               std::uint8_t subevent, const void *data,
                               std::size_t length, std::uint8_t response_slot_start,
                               std::uint8_t response_slot_count) noexcept
    {
        if (!requireThreadContext())
        {
            return false;
        }
#if defined(CONFIG_BT_PER_ADV_RSP)
        const PawrContext &context = gapState().pawr;
        if (!context.configured || context.advertising_set != advertising_set ||
            subevent >= context.subevent_count || length > maximum_payload_length ||
            (length != 0U && data == nullptr) || response_slot_count == 0U ||
            static_cast<std::size_t>(response_slot_start) + response_slot_count >
                context.response_slot_count)
        {
            internal::recordError(length > maximum_payload_length ? BLEError::payload_overflow
                                                                  : BLEError::invalid_argument,
                                  length > maximum_payload_length ? -EMSGSIZE : -EINVAL, true);
            return false;
        }
        PawrSubeventContext &destination = gapState().pawr.subevents[subevent];
        if (length != 0U)
        {
            ::memcpy(destination.data, data, length);
        }
        destination.length = static_cast<std::uint16_t>(length);
        destination.response_slot_start = response_slot_start;
        destination.response_slot_count = response_slot_count;
        destination.configured = true;
        return true;
#else
        ARG_UNUSED(advertising_set);
        ARG_UNUSED(subevent);
        ARG_UNUSED(data);
        ARG_UNUSED(length);
        ARG_UNUSED(response_slot_start);
        ARG_UNUSED(response_slot_count);
        internal::recordError(BLEError::unsupported, -ENOTSUP, true);
        return false;
#endif
    }

    bool Pawr::configureScanner(BLEPeriodicSyncHandle sync,
                                const std::uint8_t *subevents,
                                std::size_t count) noexcept
    {
        if (!requireThreadContext())
        {
            return false;
        }
#if defined(CONFIG_BT_PER_ADV_SYNC_RSP)
        if (subevents == nullptr || count == 0U || count > maximum_subevents)
        {
            internal::recordError(BLEError::invalid_argument, -EINVAL, true);
            return false;
        }
        std::uint8_t copied[maximum_subevents] = {};
        for (std::size_t index = 0U; index < count; ++index)
        {
            if (subevents[index] >= maximum_subevents ||
                (index != 0U && subevents[index] <= subevents[index - 1U]))
            {
                internal::recordError(BLEError::invalid_argument, -EINVAL, true);
                return false;
            }
            copied[index] = subevents[index];
        }
        struct bt_le_per_adv_sync *instance = nullptr;
        std::uint32_t device_generation = 0U;
        if (!currentPeriodicSync(sync, instance, device_generation) ||
            atomic_get(&gapState().periodic_sync.synchronized) == 0)
        {
            internal::recordError(BLEError::wrong_state, -ENOENT, true);
            return false;
        }
        struct bt_le_per_adv_sync_subevent_params parameters = {
            .properties = 0U,
            .num_subevents = static_cast<std::uint8_t>(count),
            .subevents = copied,
        };
        const int result = bt_le_per_adv_sync_subevent(instance, &parameters);
        if (result < 0)
        {
            internal::recordError(BLEError::driver_error, result, true);
            return false;
        }
        return true;
#else
        ARG_UNUSED(sync);
        ARG_UNUSED(subevents);
        ARG_UNUSED(count);
        internal::recordError(BLEError::unsupported, -ENOTSUP, true);
        return false;
#endif
    }

    bool Pawr::sendResponse(BLEPeriodicSyncHandle sync, std::uint16_t request_event,
                            std::uint8_t request_subevent,
                            std::uint8_t response_subevent,
                            std::uint8_t response_slot, const void *data,
                            std::size_t length) noexcept
    {
        if (!requireThreadContext())
        {
            return false;
        }
#if defined(CONFIG_BT_PER_ADV_SYNC_RSP)
        if (request_subevent >= maximum_subevents ||
            response_subevent >= maximum_subevents ||
            response_slot >= maximum_response_slots ||
            length > maximum_payload_length || (length != 0U && data == nullptr))
        {
            internal::recordError(length > maximum_payload_length ? BLEError::payload_overflow
                                                                  : BLEError::invalid_argument,
                                  length > maximum_payload_length ? -EMSGSIZE : -EINVAL, true);
            return false;
        }
        struct bt_le_per_adv_sync *instance = nullptr;
        std::uint32_t device_generation = 0U;
        if (!currentPeriodicSync(sync, instance, device_generation) ||
            atomic_get(&gapState().periodic_sync.synchronized) == 0)
        {
            internal::recordError(BLEError::wrong_state, -ENOENT, true);
            return false;
        }
        struct net_buf_simple buffer = {};
        net_buf_simple_init_with_data(&buffer, const_cast<void *>(data), length);
        const struct bt_le_per_adv_response_params parameters = {
            .request_event = request_event,
            .request_subevent = request_subevent,
            .response_subevent = response_subevent,
            .response_slot = response_slot,
        };
        const int result = bt_le_per_adv_set_response_data(instance, &parameters, &buffer);
        if (result < 0)
        {
            internal::recordError(BLEError::driver_error, result, true);
            return false;
        }
        return true;
#else
        ARG_UNUSED(sync);
        ARG_UNUSED(request_event);
        ARG_UNUSED(request_subevent);
        ARG_UNUSED(response_subevent);
        ARG_UNUSED(response_slot);
        ARG_UNUSED(data);
        ARG_UNUSED(length);
        internal::recordError(BLEError::unsupported, -ENOTSUP, true);
        return false;
#endif
    }

    int Pawr::available() const noexcept
    {
        return static_cast<int>(k_msgq_num_used_get(&pawrResponseQueue()));
    }

    bool Pawr::read(BLEPawrResponse &response) noexcept
    {
        PawrResponseRecord record = {};
        while (k_msgq_get(&pawrResponseQueue(), &record, K_NO_WAIT) == 0)
        {
            if (record.device_generation == static_cast<std::uint32_t>(
                                                atomic_get(&gapState().device_session_generation)))
            {
                response = record.response;
                return true;
            }
        }
        return false;
    }

    void Pawr::onResponse(BLEPawrResponseCallback callback, void *context) noexcept
    {
        gapState().pawr_response_callback = callback;
        gapState().pawr_response_context = context;
    }

    std::uint32_t Pawr::droppedResponses() const noexcept
    {
        return static_cast<std::uint32_t>(
            atomic_get(&gapState().dropped_pawr_response_value));
    }
} // namespace nucode::ble
#endif
