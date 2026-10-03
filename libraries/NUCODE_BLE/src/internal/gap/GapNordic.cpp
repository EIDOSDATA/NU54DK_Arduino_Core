/**
 * @file GapNordic.cpp
 * @brief Nordic SDC LLPM·QoS·시간·event 확장을 bounded lifecycle로 구현합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#if !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE)
#include <internal/gap/GapInternal.h>

#if defined(CONFIG_NUCODE_BLE_NORDIC_EXTENSIONS)
#include <sdc_hci_vs.h>

extern "C"
{
    int hci_vs_sdc_llpm_mode_set(const sdc_hci_cmd_vs_llpm_mode_set_t *parameters);
    int hci_vs_sdc_conn_update(const sdc_hci_cmd_vs_conn_update_t *parameters);
    int hci_vs_sdc_qos_conn_event_report_enable(
        const sdc_hci_cmd_vs_qos_conn_event_report_enable_t *parameters);
    int hci_vs_sdc_qos_channel_survey_enable(
        const sdc_hci_cmd_vs_qos_channel_survey_enable_t *parameters);
    int hci_vs_sdc_set_event_start_task(
        const sdc_hci_cmd_vs_set_event_start_task_t *parameters);
    int hci_vs_sdc_conn_anchor_point_update_event_report_enable(
        const sdc_hci_cmd_vs_conn_anchor_point_update_event_report_enable_t *parameters);
}

#if defined(CONFIG_SOC_SERIES_NRF54L)
#include <zephyr/drivers/timer/nrf_grtc_timer.h>
#endif

#if !defined(CONFIG_NUCODE_BLE_NORDIC_REPORT_QUEUE_SIZE)
#define CONFIG_NUCODE_BLE_NORDIC_REPORT_QUEUE_SIZE 16
#endif

namespace nucode::ble::internal::gap
{
    namespace
    {
        struct ConnectionEventRecord
        {
            BLENordicConnectionEventReport report;
            std::uint32_t device_generation;
        };

        struct ChannelSurveyRecord
        {
            BLENordicChannelSurveyReport report;
            std::uint32_t device_generation;
        };

        struct AnchorPointRecord
        {
            BLENordicAnchorPointReport report;
            std::uint32_t device_generation;
        };

        K_MSGQ_DEFINE(nordic_connection_event_queue, sizeof(ConnectionEventRecord),
                      CONFIG_NUCODE_BLE_NORDIC_REPORT_QUEUE_SIZE, alignof(ConnectionEventRecord));
        K_MSGQ_DEFINE(nordic_channel_survey_queue, sizeof(ChannelSurveyRecord),
                      CONFIG_NUCODE_BLE_NORDIC_REPORT_QUEUE_SIZE, alignof(ChannelSurveyRecord));
        K_MSGQ_DEFINE(nordic_anchor_point_queue, sizeof(AnchorPointRecord),
                      CONFIG_NUCODE_BLE_NORDIC_REPORT_QUEUE_SIZE, alignof(AnchorPointRecord));

        struct NordicContext
        {
            atomic_t vendor_callback_registered = ATOMIC_INIT(0);
            atomic_t connection_event_enabled = ATOMIC_INIT(0);
            atomic_t channel_survey_enabled = ATOMIC_INIT(0);
            atomic_t anchor_point_enabled = ATOMIC_INIT(0);
            atomic_t radio_notification_enabled = ATOMIC_INIT(0);
            atomic_t dropped_report_count = ATOMIC_INIT(0);
            struct k_spinlock callback_lock;
            BLENordicConnectionEventCallback connection_event_callback = nullptr;
            void *connection_event_context = nullptr;
            BLENordicChannelSurveyCallback channel_survey_callback = nullptr;
            void *channel_survey_context = nullptr;
            BLENordicAnchorPointCallback anchor_point_callback = nullptr;
            void *anchor_point_context = nullptr;
            BLENordicRadioPrepareCallback radio_prepare_callback = nullptr;
            void *radio_prepare_context = nullptr;
            std::uint32_t radio_prepare_distance_us =
                NordicExtensions::recommended_radio_prepare_distance_us;
        };

        NordicContext nordic_context{};

        NordicContext &nordicState() noexcept
        {
            return nordic_context;
        }

        std::uint32_t deviceGeneration() noexcept
        {
            return static_cast<std::uint32_t>(
                atomic_get(&gapState().device_session_generation));
        }

        bool initialized() noexcept
        {
            if (atomic_get(&gapState().device_initialized) == 0)
            {
                internal::recordError(BLEError::not_initialized, -EACCES, true);
                return false;
            }
            return true;
        }

        [[maybe_unused]] void recordUnsupported() noexcept
        {
            internal::recordError(BLEError::unsupported, -ENOTSUP, true);
        }

        void recordDriverResult(int result) noexcept
        {
            internal::recordError(result == 0 ? BLEError::none : BLEError::driver_error,
                                  result, result != 0);
        }

        void recordDroppedReport() noexcept
        {
            atomic_inc(&nordicState().dropped_report_count);
            internal::recordError(BLEError::event_overflow, -ENOBUFS, true);
        }

        BLEConnectionHandle connectionHandle(std::uint16_t hci_handle) noexcept
        {
            BLEConnectionHandle handle;
            struct bt_conn *connection = bt_hci_conn_lookup_handle(hci_handle);
            if (connection != nullptr)
            {
                handle = internal::handleForActiveConnection(connection);
                bt_conn_unref(connection);
            }
            return handle;
        }

        bool currentConnection(BLEConnectionHandle handle) noexcept
        {
            struct bt_conn *connection = internal::referenceConnection(handle);
            if (connection == nullptr)
            {
                return false;
            }
            bt_conn_unref(connection);
            return true;
        }

#if defined(CONFIG_SOC_SERIES_NRF54L)
        struct RadioNotificationSlot
        {
            struct k_timer timer;
            struct k_work work;
            BLEConnectionHandle connection;
        };

        RadioNotificationSlot radio_slots[maximum_connection_slots] = {};
        atomic_t radio_slots_initialized = ATOMIC_INIT(0);

        void radioWorkHandler(struct k_work *work) noexcept
        {
            auto *slot = CONTAINER_OF(work, RadioNotificationSlot, work);
            if (atomic_get(&nordicState().radio_notification_enabled) == 0)
            {
                return;
            }
            BLENordicRadioPrepareCallback callback = nullptr;
            void *context = nullptr;
            BLEConnectionHandle connection;
            k_spinlock_key_t key = k_spin_lock(&nordicState().callback_lock);
            callback = nordicState().radio_prepare_callback;
            context = nordicState().radio_prepare_context;
            connection = slot->connection;
            k_spin_unlock(&nordicState().callback_lock, key);
            if (callback != nullptr && currentConnection(connection))
            {
                callback(connection, context);
            }
        }

        void radioTimerHandler(struct k_timer *timer) noexcept
        {
            auto *slot = CONTAINER_OF(timer, RadioNotificationSlot, timer);
            static_cast<void>(k_work_submit(&slot->work));
        }

        void initializeRadioSlots() noexcept
        {
            if (!atomic_cas(&radio_slots_initialized, 0, 1))
            {
                return;
            }
            for (std::size_t index = 0U; index < maximum_connection_slots; ++index)
            {
                k_timer_init(&radio_slots[index].timer, radioTimerHandler, nullptr);
                k_work_init(&radio_slots[index].work, radioWorkHandler);
            }
        }

        void scheduleRadioNotification(const BLENordicAnchorPointReport &report) noexcept
        {
            if (atomic_get(&nordicState().radio_notification_enabled) == 0)
            {
                return;
            }
            const std::size_t slot_index =
                BLEConnectionHandleAccess::slot(report.connection);
            if (slot_index >= maximum_connection_slots)
            {
                return;
            }
            struct bt_conn *connection = internal::referenceConnection(report.connection);
            if (connection == nullptr)
            {
                return;
            }
            struct bt_conn_info information = {};
            const int result = bt_conn_get_info(connection, &information);
            bt_conn_unref(connection);
            if (result != 0 || information.type != BT_CONN_TYPE_LE)
            {
                return;
            }
            const std::uint32_t interval_us = normalizeConnectionIntervalUs(
                information.le.interval_us);
            const std::uint64_t next_anchor_us =
                report.controller_clock_us + interval_us;
            const std::uint32_t distance = nordicState().radio_prepare_distance_us;
            const std::uint64_t startup = z_nrf_grtc_timer_startup_value_get();
            if (next_anchor_us <= static_cast<std::uint64_t>(distance) + startup)
            {
                return;
            }
            radio_slots[slot_index].connection = report.connection;
            const std::uint64_t uptime_target_us = next_anchor_us - distance - startup;
            k_timer_start(&radio_slots[slot_index].timer,
                          K_TIMEOUT_ABS_US(uptime_target_us),
                          K_USEC(interval_us));
        }
#else
        void scheduleRadioNotification(const BLENordicAnchorPointReport &) noexcept
        {
        }
#endif

        bool vendorEventHandler(struct net_buf_simple *buffer) noexcept
        {
            if (buffer == nullptr || buffer->len < 1U)
            {
                return false;
            }
            const std::uint8_t subevent = buffer->data[0];
            ++buffer->data;
            --buffer->len;

#if defined(CONFIG_BT_CTLR_SDC_QOS_CONN_EVENT_REPORT)
            if (subevent == SDC_HCI_SUBEVENT_VS_QOS_CONN_EVENT_REPORT)
            {
                if (buffer->len < sizeof(sdc_hci_subevent_vs_qos_conn_event_report_t))
                {
                    return true;
                }
                sdc_hci_subevent_vs_qos_conn_event_report_t native = {};
                ::memcpy(&native, buffer->data, sizeof(native));
                ConnectionEventRecord record = {
                    .report = {
                        .connection = connectionHandle(native.conn_handle),
                        .event_counter = native.event_counter,
                        .channel_index = native.channel_index,
                        .crc_ok_count = native.crc_ok_count,
                        .crc_error_count = native.crc_error_count,
                        .negative_acknowledgement_count = native.nak_count,
                        .receive_timeout = native.rx_timeout != 0U,
                    },
                    .device_generation = deviceGeneration(),
                };
                if (atomic_get(&nordicState().connection_event_enabled) != 0 &&
                    record.report.connection.valid() &&
                    k_msgq_put(&nordic_connection_event_queue, &record, K_NO_WAIT) != 0)
                {
                    recordDroppedReport();
                }
                return true;
            }
#endif

#if defined(CONFIG_BT_CTLR_SDC_QOS_CHANNEL_SURVEY)
            if (subevent == SDC_HCI_SUBEVENT_VS_QOS_CHANNEL_SURVEY_REPORT)
            {
                if (buffer->len < sizeof(sdc_hci_subevent_vs_qos_channel_survey_report_t))
                {
                    return true;
                }
                sdc_hci_subevent_vs_qos_channel_survey_report_t native = {};
                ::memcpy(&native, buffer->data, sizeof(native));
                ChannelSurveyRecord record = {};
                ::memcpy(record.report.channel_energy_dbm, native.channel_energy,
                         sizeof(record.report.channel_energy_dbm));
                record.device_generation = deviceGeneration();
                if (atomic_get(&nordicState().channel_survey_enabled) != 0 &&
                    k_msgq_put(&nordic_channel_survey_queue, &record, K_NO_WAIT) != 0)
                {
                    recordDroppedReport();
                }
                return true;
            }
#endif

#if defined(CONFIG_BT_CTLR_SDC_CONN_ANCHOR_POINT_REPORT)
            if (subevent == SDC_HCI_SUBEVENT_VS_CONN_ANCHOR_POINT_UPDATE_REPORT)
            {
                if (buffer->len < sizeof(sdc_hci_subevent_vs_conn_anchor_point_update_report_t))
                {
                    return true;
                }
                sdc_hci_subevent_vs_conn_anchor_point_update_report_t native = {};
                ::memcpy(&native, buffer->data, sizeof(native));
                AnchorPointRecord record = {
                    .report = {
                        .connection = connectionHandle(native.conn_handle),
                        .event_counter = native.event_counter,
                        .controller_clock_us = native.anchor_point_us,
                    },
                    .device_generation = deviceGeneration(),
                };
                if (record.report.connection.valid())
                {
                    if (atomic_get(&nordicState().anchor_point_enabled) != 0 &&
                        k_msgq_put(&nordic_anchor_point_queue, &record, K_NO_WAIT) != 0)
                    {
                        recordDroppedReport();
                    }
                    scheduleRadioNotification(record.report);
                }
                return true;
            }
#endif
            return false;
        }

        bool ensureVendorCallback() noexcept
        {
#if defined(CONFIG_BT_HCI_VS_EVT_USER)
            if (atomic_get(&nordicState().vendor_callback_registered) != 0)
            {
                return true;
            }
            if (!atomic_cas(&nordicState().vendor_callback_registered, 0, 1))
            {
                return true;
            }
            const int result = bt_hci_register_vnd_evt_cb(vendorEventHandler);
            if (result != 0)
            {
                atomic_set(&nordicState().vendor_callback_registered, 0);
                recordDriverResult(result);
                return false;
            }
            return true;
#else
            recordUnsupported();
            return false;
#endif
        }

        bool setAnchorControllerState(bool enabled) noexcept
        {
#if defined(CONFIG_BT_CTLR_SDC_CONN_ANCHOR_POINT_REPORT)
            const sdc_hci_cmd_vs_conn_anchor_point_update_event_report_enable_t parameters = {
                .enable = static_cast<std::uint8_t>(enabled ? 1U : 0U),
            };
            const int result =
                hci_vs_sdc_conn_anchor_point_update_event_report_enable(&parameters);
            recordDriverResult(result);
            return result == 0;
#else
            static_cast<void>(enabled);
            recordUnsupported();
            return false;
#endif
        }

        bool setEventStartTask(std::uint8_t handle_type, std::uint16_t handle,
                               std::uint32_t task_address) noexcept
        {
#if defined(CONFIG_BT_CTLR_SDC_EVENT_TRIGGER)
            if (task_address != 0U && (task_address & 0x3U) != 0U)
            {
                internal::recordError(BLEError::invalid_argument, -EINVAL, true);
                return false;
            }
            const sdc_hci_cmd_vs_set_event_start_task_t parameters = {
                .handle_type = handle_type,
                .handle = handle,
                .task_address = task_address,
            };
            const int result = hci_vs_sdc_set_event_start_task(&parameters);
            recordDriverResult(result);
            return result == 0;
#else
            static_cast<void>(handle_type);
            static_cast<void>(handle);
            static_cast<void>(task_address);
            recordUnsupported();
            return false;
#endif
        }
    } // namespace
} // namespace nucode::ble::internal::gap

namespace nucode::ble::internal
{
    void pollNordicExtensions() noexcept
    {
        using namespace gap;
        const std::uint32_t current_generation = deviceGeneration();
        BLENordicConnectionEventCallback connection_callback = nullptr;
        void *connection_context = nullptr;
        BLENordicChannelSurveyCallback survey_callback = nullptr;
        void *survey_context = nullptr;
        BLENordicAnchorPointCallback anchor_callback = nullptr;
        void *anchor_context = nullptr;
        k_spinlock_key_t key = k_spin_lock(&nordicState().callback_lock);
        connection_callback = nordicState().connection_event_callback;
        connection_context = nordicState().connection_event_context;
        survey_callback = nordicState().channel_survey_callback;
        survey_context = nordicState().channel_survey_context;
        anchor_callback = nordicState().anchor_point_callback;
        anchor_context = nordicState().anchor_point_context;
        k_spin_unlock(&nordicState().callback_lock, key);

        if (connection_callback != nullptr)
        {
            ConnectionEventRecord record = {};
            while (k_msgq_get(&nordic_connection_event_queue, &record, K_NO_WAIT) == 0)
            {
                if (record.device_generation == current_generation &&
                    currentConnection(record.report.connection))
                {
                    connection_callback(record.report, connection_context);
                }
            }
        }
        if (survey_callback != nullptr)
        {
            ChannelSurveyRecord record = {};
            while (k_msgq_get(&nordic_channel_survey_queue, &record, K_NO_WAIT) == 0)
            {
                if (record.device_generation == current_generation)
                {
                    survey_callback(record.report, survey_context);
                }
            }
        }
        if (anchor_callback != nullptr)
        {
            AnchorPointRecord record = {};
            while (k_msgq_get(&nordic_anchor_point_queue, &record, K_NO_WAIT) == 0)
            {
                if (record.device_generation == current_generation &&
                    currentConnection(record.report.connection))
                {
                    anchor_callback(record.report, anchor_context);
                }
            }
        }
    }

    void nordicExtensionsEnded() noexcept
    {
        using namespace gap;
#if defined(CONFIG_BT_CTLR_SDC_QOS_CONN_EVENT_REPORT)
        if (atomic_get(&nordicState().connection_event_enabled) != 0)
        {
            const sdc_hci_cmd_vs_qos_conn_event_report_enable_t parameters = {.enable = 0U};
            static_cast<void>(hci_vs_sdc_qos_conn_event_report_enable(&parameters));
        }
#endif
#if defined(CONFIG_BT_CTLR_SDC_QOS_CHANNEL_SURVEY)
        if (atomic_get(&nordicState().channel_survey_enabled) != 0)
        {
            const sdc_hci_cmd_vs_qos_channel_survey_enable_t parameters = {
                .enable = 0U,
                .interval_us = 0U,
            };
            static_cast<void>(hci_vs_sdc_qos_channel_survey_enable(&parameters));
        }
#endif
#if defined(CONFIG_BT_CTLR_SDC_CONN_ANCHOR_POINT_REPORT)
        if (atomic_get(&nordicState().anchor_point_enabled) != 0 ||
            atomic_get(&nordicState().radio_notification_enabled) != 0)
        {
            const sdc_hci_cmd_vs_conn_anchor_point_update_event_report_enable_t parameters = {
                .enable = 0U,
            };
            static_cast<void>(
                hci_vs_sdc_conn_anchor_point_update_event_report_enable(&parameters));
        }
#endif
        atomic_set(&nordicState().connection_event_enabled, 0);
        atomic_set(&gapState().nordic_llpm_mode_enabled, 0);
        atomic_set(&nordicState().channel_survey_enabled, 0);
        atomic_set(&nordicState().anchor_point_enabled, 0);
        atomic_set(&nordicState().radio_notification_enabled, 0);
        k_msgq_purge(&nordic_connection_event_queue);
        k_msgq_purge(&nordic_channel_survey_queue);
        k_msgq_purge(&nordic_anchor_point_queue);
#if defined(CONFIG_SOC_SERIES_NRF54L)
        if (atomic_get(&radio_slots_initialized) != 0)
        {
            for (std::size_t index = 0U; index < maximum_connection_slots; ++index)
            {
                k_timer_stop(&radio_slots[index].timer);
                static_cast<void>(k_work_cancel(&radio_slots[index].work));
                radio_slots[index].connection = BLEConnectionHandle{};
            }
        }
#endif
    }
} // namespace nucode::ble::internal

namespace nucode::ble
{
    using namespace internal::gap;

    bool NordicExtensions::setLlpmMode(bool enabled) noexcept
    {
        if (!requireThreadContext() || !initialized())
        {
            return false;
        }
#if defined(CONFIG_BT_CTLR_SDC_LLPM)
        if (internal::hasActiveConnection())
        {
            internal::recordError(BLEError::wrong_state, -EBUSY, true);
            return false;
        }
        const sdc_hci_cmd_vs_llpm_mode_set_t parameters = {
            .enable = static_cast<std::uint8_t>(enabled ? 1U : 0U),
        };
        const int result = hci_vs_sdc_llpm_mode_set(&parameters);
        if (result == 0)
        {
            atomic_set(&gapState().nordic_llpm_mode_enabled, enabled ? 1 : 0);
        }
        recordDriverResult(result);
        return result == 0;
#else
        static_cast<void>(enabled);
        recordUnsupported();
        return false;
#endif
    }

    bool NordicExtensions::requestLlpmInterval(
        BLEConnectionHandle connection_handle, std::uint32_t interval_us,
        std::uint16_t latency, std::uint16_t supervision_timeout_10ms) noexcept
    {
        if (!requireThreadContext() || !initialized())
        {
            return false;
        }
#if defined(CONFIG_BT_CTLR_SDC_LLPM)
        if (interval_us < minimum_llpm_interval_us || interval_us > maximum_llpm_interval_us ||
            (interval_us % 1000U) != 0U || supervision_timeout_10ms < 10U ||
            supervision_timeout_10ms > 3200U || BLEConnection.phy(connection_handle) != BLEPhy::le_2m)
        {
            internal::recordError(BLEError::invalid_argument, -EINVAL, true);
            return false;
        }
        struct bt_conn *connection = internal::referenceConnection(connection_handle);
        if (connection == nullptr)
        {
            internal::recordError(BLEError::not_connected, -ENOTCONN, true);
            return false;
        }
        std::uint16_t hci_handle = 0U;
        int result = bt_hci_get_conn_handle(connection, &hci_handle);
        bt_conn_unref(connection);
        if (result == 0)
        {
            const sdc_hci_cmd_vs_conn_update_t parameters = {
                .conn_handle = hci_handle,
                .conn_interval_us = interval_us,
                .conn_latency = latency,
                .supervision_timeout = supervision_timeout_10ms,
            };
            result = hci_vs_sdc_conn_update(&parameters);
        }
        recordDriverResult(result);
        return result == 0;
#else
        static_cast<void>(connection_handle);
        static_cast<void>(interval_us);
        static_cast<void>(latency);
        static_cast<void>(supervision_timeout_10ms);
        recordUnsupported();
        return false;
#endif
    }

    bool NordicExtensions::setConnectionEventReports(bool enabled) noexcept
    {
        if (!requireThreadContext() || !initialized())
        {
            return false;
        }
#if defined(CONFIG_BT_CTLR_SDC_QOS_CONN_EVENT_REPORT)
        if (enabled && !ensureVendorCallback())
        {
            return false;
        }
        const sdc_hci_cmd_vs_qos_conn_event_report_enable_t parameters = {
            .enable = static_cast<std::uint8_t>(enabled ? 1U : 0U),
        };
        const int result = hci_vs_sdc_qos_conn_event_report_enable(&parameters);
        if (result == 0)
        {
            atomic_set(&nordicState().connection_event_enabled, enabled ? 1 : 0);
            if (!enabled)
            {
                k_msgq_purge(&nordic_connection_event_queue);
            }
        }
        recordDriverResult(result);
        return result == 0;
#else
        static_cast<void>(enabled);
        recordUnsupported();
        return false;
#endif
    }

    bool NordicExtensions::setChannelSurvey(bool enabled, std::uint32_t interval_us) noexcept
    {
        if (!requireThreadContext() || !initialized())
        {
            return false;
        }
#if defined(CONFIG_BT_CTLR_SDC_QOS_CHANNEL_SURVEY)
        if (enabled && interval_us != 0U &&
            (interval_us < 3000U || interval_us > 4000000U))
        {
            internal::recordError(BLEError::invalid_argument, -EINVAL, true);
            return false;
        }
        if (enabled && !ensureVendorCallback())
        {
            return false;
        }
        const sdc_hci_cmd_vs_qos_channel_survey_enable_t parameters = {
            .enable = static_cast<std::uint8_t>(enabled ? 1U : 0U),
            .interval_us = enabled ? interval_us : 0U,
        };
        const int result = hci_vs_sdc_qos_channel_survey_enable(&parameters);
        if (result == 0)
        {
            atomic_set(&nordicState().channel_survey_enabled, enabled ? 1 : 0);
            if (!enabled)
            {
                k_msgq_purge(&nordic_channel_survey_queue);
            }
        }
        recordDriverResult(result);
        return result == 0;
#else
        static_cast<void>(enabled);
        static_cast<void>(interval_us);
        recordUnsupported();
        return false;
#endif
    }

    bool NordicExtensions::setAnchorPointReports(bool enabled) noexcept
    {
        if (!requireThreadContext() || !initialized())
        {
            return false;
        }
        if (enabled && !ensureVendorCallback())
        {
            return false;
        }
        const bool controller_enabled =
            enabled || atomic_get(&nordicState().radio_notification_enabled) != 0;
        if (!setAnchorControllerState(controller_enabled))
        {
            return false;
        }
        atomic_set(&nordicState().anchor_point_enabled, enabled ? 1 : 0);
        if (!enabled)
        {
            k_msgq_purge(&nordic_anchor_point_queue);
        }
        return true;
    }

    int NordicExtensions::availableConnectionEventReports() const noexcept
    {
        return static_cast<int>(k_msgq_num_used_get(&nordic_connection_event_queue));
    }

    bool NordicExtensions::readConnectionEventReport(
        BLENordicConnectionEventReport &report) noexcept
    {
        ConnectionEventRecord record = {};
        while (k_msgq_get(&nordic_connection_event_queue, &record, K_NO_WAIT) == 0)
        {
            if (record.device_generation == deviceGeneration() &&
                currentConnection(record.report.connection))
            {
                report = record.report;
                return true;
            }
        }
        return false;
    }

    int NordicExtensions::availableChannelSurveyReports() const noexcept
    {
        return static_cast<int>(k_msgq_num_used_get(&nordic_channel_survey_queue));
    }

    bool NordicExtensions::readChannelSurveyReport(
        BLENordicChannelSurveyReport &report) noexcept
    {
        ChannelSurveyRecord record = {};
        while (k_msgq_get(&nordic_channel_survey_queue, &record, K_NO_WAIT) == 0)
        {
            if (record.device_generation == deviceGeneration())
            {
                report = record.report;
                return true;
            }
        }
        return false;
    }

    int NordicExtensions::availableAnchorPointReports() const noexcept
    {
        return static_cast<int>(k_msgq_num_used_get(&nordic_anchor_point_queue));
    }

    bool NordicExtensions::readAnchorPointReport(BLENordicAnchorPointReport &report) noexcept
    {
        AnchorPointRecord record = {};
        while (k_msgq_get(&nordic_anchor_point_queue, &record, K_NO_WAIT) == 0)
        {
            if (record.device_generation == deviceGeneration() &&
                currentConnection(record.report.connection))
            {
                report = record.report;
                return true;
            }
        }
        return false;
    }

    void NordicExtensions::onConnectionEvent(BLENordicConnectionEventCallback callback,
                                              void *context) noexcept
    {
        k_spinlock_key_t key = k_spin_lock(&nordicState().callback_lock);
        nordicState().connection_event_callback = callback;
        nordicState().connection_event_context = context;
        k_spin_unlock(&nordicState().callback_lock, key);
    }

    void NordicExtensions::onChannelSurvey(BLENordicChannelSurveyCallback callback,
                                            void *context) noexcept
    {
        k_spinlock_key_t key = k_spin_lock(&nordicState().callback_lock);
        nordicState().channel_survey_callback = callback;
        nordicState().channel_survey_context = context;
        k_spin_unlock(&nordicState().callback_lock, key);
    }

    void NordicExtensions::onAnchorPoint(BLENordicAnchorPointCallback callback,
                                          void *context) noexcept
    {
        k_spinlock_key_t key = k_spin_lock(&nordicState().callback_lock);
        nordicState().anchor_point_callback = callback;
        nordicState().anchor_point_context = context;
        k_spin_unlock(&nordicState().callback_lock, key);
    }

    bool NordicExtensions::projectAnchorPoint(
        const BLENordicAnchorPointReport &reference,
        std::uint16_t target_event_counter, std::uint32_t connection_interval_us,
        std::uint64_t &controller_clock_us) const noexcept
    {
        if (!reference.connection.valid() || connection_interval_us == 0U)
        {
            internal::recordError(BLEError::invalid_argument, -EINVAL, true);
            return false;
        }
        const auto difference = static_cast<std::int16_t>(
            static_cast<std::uint16_t>(target_event_counter - reference.event_counter));
        const std::int64_t projected =
            static_cast<std::int64_t>(reference.controller_clock_us) +
            static_cast<std::int64_t>(difference) * connection_interval_us;
        if (projected < 0)
        {
            internal::recordError(BLEError::invalid_argument, -ERANGE, true);
            return false;
        }
        controller_clock_us = static_cast<std::uint64_t>(projected);
        internal::recordError(BLEError::none, 0, false);
        return true;
    }

    bool NordicExtensions::setConnectionEventTrigger(BLEConnectionHandle connection_handle,
                                                       std::uint32_t task_address) noexcept
    {
        if (!requireThreadContext() || !initialized())
        {
            return false;
        }
        struct bt_conn *connection = internal::referenceConnection(connection_handle);
        if (connection == nullptr)
        {
            internal::recordError(BLEError::not_connected, -ENOTCONN, true);
            return false;
        }
        std::uint16_t hci_handle = 0U;
        const int result = bt_hci_get_conn_handle(connection, &hci_handle);
        bt_conn_unref(connection);
        if (result != 0)
        {
            recordDriverResult(result);
            return false;
        }
        return setEventStartTask(SDC_HCI_VS_SET_EVENT_START_TASK_HANDLE_TYPE_CONN,
                                 hci_handle, task_address);
    }

    bool NordicExtensions::setAdvertisingEventTrigger(
        BLEAdvertisingSetHandle advertising_set, std::uint32_t task_address) noexcept
    {
        if (!requireThreadContext() || !initialized())
        {
            return false;
        }
#if defined(CONFIG_BT_EXT_ADV)
        struct bt_le_ext_adv *instance = nullptr;
        std::uint32_t generation = 0U;
        if (!currentAdvertisingSet(advertising_set, instance, generation))
        {
            internal::recordError(BLEError::not_found, -ENOENT, true);
            return false;
        }
        std::uint8_t advertising_handle = 0U;
        const int result = bt_hci_get_adv_handle(instance, &advertising_handle);
        if (result != 0)
        {
            recordDriverResult(result);
            return false;
        }
        return setEventStartTask(SDC_HCI_VS_SET_EVENT_START_TASK_HANDLE_TYPE_ADV,
                                 advertising_handle, task_address);
#else
        static_cast<void>(advertising_set);
        static_cast<void>(task_address);
        recordUnsupported();
        return false;
#endif
    }

    bool NordicExtensions::setScannerEventTrigger(std::uint32_t task_address) noexcept
    {
        if (!requireThreadContext() || !initialized())
        {
            return false;
        }
        return setEventStartTask(SDC_HCI_VS_SET_EVENT_START_TASK_HANDLE_TYPE_SCAN,
                                 0U, task_address);
    }

    bool NordicExtensions::setInitiatorEventTrigger(std::uint32_t task_address) noexcept
    {
        if (!requireThreadContext() || !initialized())
        {
            return false;
        }
        return setEventStartTask(SDC_HCI_VS_SET_EVENT_START_TASK_HANDLE_TYPE_INITIATOR,
                                 0U, task_address);
    }

    bool NordicExtensions::setRadioNotification(bool enabled,
                                                 std::uint32_t prepare_distance_us) noexcept
    {
        if (!requireThreadContext() || !initialized())
        {
            return false;
        }
#if defined(CONFIG_BT_CTLR_SDC_CONN_ANCHOR_POINT_REPORT) && \
    defined(CONFIG_SOC_SERIES_NRF54L)
        if (enabled && prepare_distance_us == 0U)
        {
            internal::recordError(BLEError::invalid_argument, -EINVAL, true);
            return false;
        }
        if (enabled && !ensureVendorCallback())
        {
            return false;
        }
        initializeRadioSlots();
        const bool controller_enabled =
            enabled || atomic_get(&nordicState().anchor_point_enabled) != 0;
        if (!setAnchorControllerState(controller_enabled))
        {
            return false;
        }
        nordicState().radio_prepare_distance_us = prepare_distance_us;
        atomic_set(&nordicState().radio_notification_enabled, enabled ? 1 : 0);
        if (!enabled)
        {
            for (std::size_t index = 0U; index < maximum_connection_slots; ++index)
            {
                k_timer_stop(&radio_slots[index].timer);
                static_cast<void>(k_work_cancel(&radio_slots[index].work));
                radio_slots[index].connection = BLEConnectionHandle{};
            }
        }
        return true;
#else
        static_cast<void>(enabled);
        static_cast<void>(prepare_distance_us);
        recordUnsupported();
        return false;
#endif
    }

    void NordicExtensions::onRadioPrepare(BLENordicRadioPrepareCallback callback,
                                           void *context) noexcept
    {
        k_spinlock_key_t key = k_spin_lock(&nordicState().callback_lock);
        nordicState().radio_prepare_callback = callback;
        nordicState().radio_prepare_context = context;
        k_spin_unlock(&nordicState().callback_lock, key);
    }

    std::uint32_t NordicExtensions::droppedReports() const noexcept
    {
        return static_cast<std::uint32_t>(
            atomic_get(&nordicState().dropped_report_count));
    }

    BLEFlushableAclSupport NordicExtensions::flushableAclSupport() const noexcept
    {
        BLEFlushableAclSupport support;
#if defined(CONFIG_BT_CTLR_LE_FLUSHABLE_ACL_DATA)
        support.controller_experimental = true;
#endif
        support.host_transmit_path = false;
        support.usable = support.controller_experimental && support.host_transmit_path;
        return support;
    }
} // namespace nucode::ble

#else

namespace nucode::ble::internal
{
    void pollNordicExtensions() noexcept
    {
    }

    void nordicExtensionsEnded() noexcept
    {
    }
} // namespace nucode::ble::internal

namespace nucode::ble
{
    namespace
    {
        bool unsupported() noexcept
        {
            internal::recordError(BLEError::unsupported, -ENOTSUP, true);
            return false;
        }
    } // namespace

    bool NordicExtensions::setLlpmMode(bool) noexcept
    {
        return unsupported();
    }
    bool NordicExtensions::requestLlpmInterval(BLEConnectionHandle, std::uint32_t,
                                                std::uint16_t, std::uint16_t) noexcept
    {
        return unsupported();
    }
    bool NordicExtensions::setConnectionEventReports(bool) noexcept
    {
        return unsupported();
    }
    bool NordicExtensions::setChannelSurvey(bool, std::uint32_t) noexcept
    {
        return unsupported();
    }
    bool NordicExtensions::setAnchorPointReports(bool) noexcept
    {
        return unsupported();
    }
    int NordicExtensions::availableConnectionEventReports() const noexcept
    {
        return 0;
    }
    bool NordicExtensions::readConnectionEventReport(BLENordicConnectionEventReport &) noexcept
    {
        return false;
    }
    int NordicExtensions::availableChannelSurveyReports() const noexcept
    {
        return 0;
    }
    bool NordicExtensions::readChannelSurveyReport(BLENordicChannelSurveyReport &) noexcept
    {
        return false;
    }
    int NordicExtensions::availableAnchorPointReports() const noexcept
    {
        return 0;
    }
    bool NordicExtensions::readAnchorPointReport(BLENordicAnchorPointReport &) noexcept
    {
        return false;
    }
    void NordicExtensions::onConnectionEvent(BLENordicConnectionEventCallback,
                                               void *) noexcept
    {
    }
    void NordicExtensions::onChannelSurvey(BLENordicChannelSurveyCallback,
                                            void *) noexcept
    {
    }
    void NordicExtensions::onAnchorPoint(BLENordicAnchorPointCallback,
                                          void *) noexcept
    {
    }
    bool NordicExtensions::projectAnchorPoint(const BLENordicAnchorPointReport &,
                                               std::uint16_t, std::uint32_t,
                                               std::uint64_t &) const noexcept
    {
        return unsupported();
    }
    bool NordicExtensions::setConnectionEventTrigger(BLEConnectionHandle,
                                                       std::uint32_t) noexcept
    {
        return unsupported();
    }
    bool NordicExtensions::setAdvertisingEventTrigger(BLEAdvertisingSetHandle,
                                                        std::uint32_t) noexcept
    {
        return unsupported();
    }
    bool NordicExtensions::setScannerEventTrigger(std::uint32_t) noexcept
    {
        return unsupported();
    }
    bool NordicExtensions::setInitiatorEventTrigger(std::uint32_t) noexcept
    {
        return unsupported();
    }
    bool NordicExtensions::setRadioNotification(bool, std::uint32_t) noexcept
    {
        return unsupported();
    }
    void NordicExtensions::onRadioPrepare(BLENordicRadioPrepareCallback, void *) noexcept
    {
    }
    std::uint32_t NordicExtensions::droppedReports() const noexcept
    {
        return 0U;
    }
    BLEFlushableAclSupport NordicExtensions::flushableAclSupport() const noexcept
    {
        return {};
    }
} // namespace nucode::ble

#endif

#endif // !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE)
