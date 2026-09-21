/** @file @brief BLE Device session·event·singleton과 GAP 상태의 단일 소유입니다.
 * SPDX-License-Identifier: MIT
 */
#include <NUCODE_BLE_GAP.h>
#if !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE)
#include "internal/gap/GapInternal.h"
namespace nucode::ble::internal::gap
{
    namespace
    {
        K_MSGQ_DEFINE(gap_event_queue, sizeof(GapEventRecord),
                      CONFIG_NUCODE_BLE_CORE_EVENT_QUEUE_SIZE, alignof(GapEventRecord));
        K_MSGQ_DEFINE(scan_result_queue, sizeof(ScanResultRecord),
                      CONFIG_NUCODE_BLE_SCAN_RESULT_QUEUE_SIZE, alignof(BLEScanResult));
        K_MSGQ_DEFINE(periodic_report_queue, sizeof(PeriodicReportRecord),
                      CONFIG_NUCODE_BLE_PERIODIC_REPORT_QUEUE_SIZE,
                      alignof(BLEPeriodicReport));
        K_MSGQ_DEFINE(pawr_response_queue, sizeof(PawrResponseRecord),
                      CONFIG_NUCODE_BLE_PAWR_RESPONSE_QUEUE_SIZE,
                      alignof(BLEPawrResponse));
        K_MUTEX_DEFINE(gap_lifecycle_mutex);

        GapContext context{};
    } // namespace
    GapContext &gapState() noexcept
    {
        return context;
    }
    k_msgq &gapEventQueue() noexcept
    {
        return gap_event_queue;
    }
    k_msgq &scanResultQueue() noexcept
    {
        return scan_result_queue;
    }
    k_msgq &periodicReportQueue() noexcept
    {
        return periodic_report_queue;
    }
    k_msgq &pawrResponseQueue() noexcept
    {
        return pawr_response_queue;
    }
    void lockGapLifecycle() noexcept
    {
        k_mutex_lock(&gap_lifecycle_mutex, K_FOREVER);
    }
    void unlockGapLifecycle() noexcept
    {
        k_mutex_unlock(&gap_lifecycle_mutex);
    }
    /** @brief event queue에 사용자 callback 대신 작은 record만 저장합니다. */
    void queueEvent(BLEEvent event, BLEConnectionHandle connection, BLELinkRole role,
                    std::uint32_t device_generation,
                    BLEAdvertisingSetHandle advertising_set,
                    BLEPeriodicSyncHandle periodic_sync) noexcept
    {
        const std::uint32_t current_generation =
            static_cast<std::uint32_t>(atomic_get(&gapState().device_session_generation));
        const GapEventRecord record = {
            .information =
                {
                    .event = event,
                    .connection = connection,
                    .advertising_set = advertising_set,
                    .periodic_sync = periodic_sync,
                    .role = role,
                },
            .device_generation =
                device_generation == 0U ? current_generation : device_generation,
        };
        if (k_msgq_put(&gapEventQueue(), &record, K_NO_WAIT) != 0)
        {
            atomic_inc(&gapState().dropped_event_value);
            atomic_set(&gapState().last_driver_error_value, -ENOBUFS);
            atomic_set(&gapState().last_error_value,
                       static_cast<atomic_val_t>(BLEError::event_overflow));
        }
    }
} // namespace nucode::ble::internal::gap
namespace nucode::ble::internal
{
    using namespace gap;
    void recordError(BLEError error, int driver_error, bool notify) noexcept
    {
        atomic_set(&gapState().last_error_value, static_cast<atomic_val_t>(error));
        atomic_set(&gapState().last_driver_error_value, driver_error);
        if (notify && error != BLEError::none)
        {
            queueEvent(BLEEvent::error);
        }
    }
    struct bt_conn *referenceConnection() noexcept
    {
        return referenceLegacyConnection();
    }
    struct bt_conn *referenceConnection(BLEConnectionHandle connection) noexcept
    {
        return gap::referenceConnection(connection);
    }
    struct bt_conn *referenceConnection(BLELinkRole role) noexcept
    {
        const std::size_t slot_index =
            role == BLELinkRole::central
                ? central_connection_slot
                : role == BLELinkRole::peripheral ? peripheral_connection_slot
                                                  : maximum_connection_slots;
        struct bt_conn *connection = nullptr;
        k_spinlock_key_t key = k_spin_lock(&gapState().connection_lock);
        if (slot_index < maximum_connection_slots)
        {
            const ConnectionSlot &slot = gapState().connection_slots[slot_index];
            if (slot.active != nullptr && slot.generation != 0U &&
                slot.device_generation == static_cast<std::uint32_t>(
                                              atomic_get(&gapState().device_session_generation)))
            {
                connection = slot.active;
                bt_conn_ref(connection);
            }
        }
        k_spin_unlock(&gapState().connection_lock, key);
        return connection;
    }
    bool activeConnection(struct bt_conn *connection) noexcept
    {
        if (connection == nullptr)
        {
            return false;
        }
        bool active = false;
        k_spinlock_key_t key = k_spin_lock(&gapState().connection_lock);
        for (std::size_t index = 0U; index < maximum_connection_slots; ++index)
        {
            const ConnectionSlot &slot = gapState().connection_slots[index];
            if (slot.active == connection && slot.generation != 0U &&
                slot.device_generation == static_cast<std::uint32_t>(
                                              atomic_get(&gapState().device_session_generation)))
            {
                active = true;
                break;
            }
        }
        k_spin_unlock(&gapState().connection_lock, key);
        return active;
    }
    bool hasActiveConnection() noexcept
    {
        bool active = false;
        k_spinlock_key_t key = k_spin_lock(&gapState().connection_lock);
        for (std::size_t index = 0U; index < maximum_connection_slots; ++index)
        {
            const ConnectionSlot &slot = gapState().connection_slots[index];
            if (slot.active != nullptr && slot.generation != 0U &&
                slot.device_generation == static_cast<std::uint32_t>(
                                              atomic_get(&gapState().device_session_generation)))
            {
                active = true;
                break;
            }
        }
        k_spin_unlock(&gapState().connection_lock, key);
        return active;
    }
} // namespace nucode::ble::internal
namespace nucode::ble
{
    using namespace internal::gap;
    bool Device::begin(const char *name) noexcept
    {
        if (!requireThreadContext() || name == nullptr)
        {
            if (name == nullptr)
            {
                internal::recordError(BLEError::invalid_argument, -EINVAL, true);
            }
            return false;
        }
        const std::size_t length = ::strlen(name);
        if (length == 0U || length > CONFIG_BT_DEVICE_NAME_MAX || !validUtf8(name, length))
        {
            internal::recordError(BLEError::invalid_argument, -EINVAL, true);
            return false;
        }

        lockGapLifecycle();
        if (atomic_get(&gapState().device_initialized) != 0)
        {
            unlockGapLifecycle();
            internal::recordError(BLEError::already_started, -EALREADY, true);
            return false;
        }
        if (!internal::claimFacade(internal::FacadeOwner::generic))
        {
            unlockGapLifecycle();
            internal::recordError(BLEError::already_started, -EALREADY, true);
            return false;
        }

        int result = internal::prepareGattDatabase();
        if (result == 0)
        {
            result = internal::ensureStack();
        }
        if (result == 0)
        {
            result = bt_set_name(name);
        }
        if (result < 0)
        {
            internal::releaseFacade(internal::FacadeOwner::generic);
            unlockGapLifecycle();
            internal::recordError(BLEError::driver_error, result, true);
            return false;
        }

        k_msgq_purge(&gapEventQueue());
        k_msgq_purge(&scanResultQueue());
        k_msgq_purge(&periodicReportQueue());
        k_msgq_purge(&pawrResponseQueue());
        atomic_set(&gapState().advertising_active, 0);
        atomic_set(&gapState().scanning_active, 0);
        atomic_set(&gapState().connection_connecting, 0);
        atomic_set(&gapState().connection_active, 0);
        atomic_set(&gapState().mtu_exchange_active, 0);
        atomic_set(&gapState().rpa_expiration_count, 0);
        ::memcpy(gapState().local_name, name, length + 1U);
        if (atomic_cas(&gapState().gatt_callback_registered, 0, 1))
        {
            bt_gatt_cb_register(&gattCallbacks());
        }
        atomic_set(&gapState().device_initialized, 1);
        internal::recordError(BLEError::none, 0, false);
        unlockGapLifecycle();
        queueEvent(BLEEvent::initialized);
        return true;
    }

    void Device::poll() noexcept
    {
        if (!requireThreadContext())
        {
            return;
        }
        GapEventRecord record = {};
        while (k_msgq_get(&gapEventQueue(), &record, K_NO_WAIT) == 0)
        {
            if (record.device_generation !=
                static_cast<std::uint32_t>(atomic_get(&gapState().device_session_generation)))
            {
                continue;
            }
            BLEEventCallback callback = gapState().event_callback;
            if (callback != nullptr)
            {
                callback(record.information.event, gapState().event_context);
            }
            if (record.device_generation !=
                static_cast<std::uint32_t>(atomic_get(&gapState().device_session_generation)))
            {
                continue;
            }
            BLEEventInfoCallback information_callback = gapState().event_info_callback;
            if (information_callback != nullptr)
            {
                information_callback(record.information, gapState().event_info_context);
            }
        }

        BLEScanCallback result_callback = gapState().scan_callback;
        if (result_callback != nullptr)
        {
            ScanResultRecord record = {};
            while (k_msgq_get(&scanResultQueue(), &record, K_NO_WAIT) == 0)
            {
                if (record.generation ==
                    static_cast<std::uint32_t>(atomic_get(&gapState().device_session_generation)))
                {
                    result_callback(record.result, gapState().scan_context);
                }
            }
        }
        internal::pollGatt();
        BLEPeriodicReportCallback periodic_callback = gapState().periodic_report_callback;
        if (periodic_callback != nullptr)
        {
            PeriodicReportRecord periodic_record = {};
            while (k_msgq_get(&periodicReportQueue(), &periodic_record, K_NO_WAIT) == 0)
            {
                if (periodic_record.device_generation == static_cast<std::uint32_t>(
                                                             atomic_get(&gapState().device_session_generation)))
                {
                    periodic_callback(periodic_record.report,
                                      gapState().periodic_report_context);
                }
            }
        }
        BLEPawrResponseCallback pawr_callback = gapState().pawr_response_callback;
        if (pawr_callback != nullptr)
        {
            PawrResponseRecord pawr_record = {};
            while (k_msgq_get(&pawrResponseQueue(), &pawr_record, K_NO_WAIT) == 0)
            {
                if (pawr_record.device_generation == static_cast<std::uint32_t>(
                                                         atomic_get(&gapState().device_session_generation)))
                {
                    pawr_callback(pawr_record.response, gapState().pawr_response_context);
                }
            }
        }
    }

    void Device::end() noexcept
    {
        if (!requireThreadContext())
        {
            return;
        }
        lockGapLifecycle();
        if (atomic_get(&gapState().device_initialized) == 0)
        {
            unlockGapLifecycle();
            return;
        }
        atomic_set(&gapState().device_initialized, 0);
        atomic_inc(&gapState().device_session_generation);

        const bool stop_scan = atomic_cas(&gapState().scanning_active, 1, 0);
        const bool stop_advertising = atomic_cas(&gapState().advertising_active, 1, 0);
        if (stop_scan)
        {
            static_cast<void>(bt_le_scan_stop());
        }
        if (stop_advertising)
        {
            static_cast<void>(bt_le_adv_stop());
        }
        endPawr();
        endPeriodicAdvertising();
        endExtendedAdvertising();

        struct bt_conn *active[maximum_connection_slots] = {};
        struct bt_conn *pending[maximum_connection_slots] = {};
        k_spinlock_key_t key = k_spin_lock(&gapState().connection_lock);
        for (std::size_t index = 0U; index < maximum_connection_slots; ++index)
        {
            ConnectionSlot &slot = gapState().connection_slots[index];
            active[index] = slot.active;
            pending[index] = slot.pending;
            slot.active = nullptr;
            slot.pending = nullptr;
            slot.generation = 0U;
            slot.device_generation = 0U;
            slot.peer_address = BLEAddress{};
            slot.connection_address = BLEAddress{};
            slot.identity_resolved = false;
        }
        gapState().last_central_address = BLEAddress{};
        k_spin_unlock(&gapState().connection_lock, key);

        atomic_set(&gapState().connection_connecting, 0);
        atomic_set(&gapState().connection_active, 0);
        atomic_set(&gapState().mtu_exchange_active, 0);
        atomic_set(&gapState().rpa_expiration_count, 0);
        k_msgq_purge(&gapEventQueue());
        k_msgq_purge(&scanResultQueue());
        k_msgq_purge(&periodicReportQueue());
        k_msgq_purge(&pawrResponseQueue());

        for (std::size_t index = 0U; index < maximum_connection_slots; ++index)
        {
            if (pending[index] != nullptr)
            {
                static_cast<void>(
                    bt_conn_disconnect(pending[index], BT_HCI_ERR_REMOTE_USER_TERM_CONN));
                bt_conn_unref(pending[index]);
            }
            if (active[index] != nullptr)
            {
                nucode::ble::internal::securityDisconnected(active[index]);
                static_cast<void>(
                    bt_conn_disconnect(active[index], BT_HCI_ERR_REMOTE_USER_TERM_CONN));
                bt_conn_unref(active[index]);
            }
        }
        nucode::ble::internal::gattEnded();
        internal::releaseFacade(internal::FacadeOwner::generic);
        unlockGapLifecycle();
    }

    bool Device::initialized() const noexcept
    {
        return atomic_get(&gapState().device_initialized) != 0;
    }

    const char *Device::localName() const noexcept
    {
        return gapState().local_name;
    }

    void Device::onEvent(BLEEventCallback callback, void *context) noexcept
    {
        gapState().event_callback = callback;
        gapState().event_context = context;
    }

    void Device::onEventInfo(BLEEventInfoCallback callback, void *context) noexcept
    {
        gapState().event_info_callback = callback;
        gapState().event_info_context = context;
    }

    bool Device::addService(BLEService &service) noexcept
    {
        if (!requireThreadContext())
        {
            return false;
        }
        return internal::addGattService(service);
    }

    BLEError Device::lastError() const noexcept
    {
        return static_cast<BLEError>(atomic_get(&gapState().last_error_value));
    }

    int Device::lastDriverError() const noexcept
    {
        return static_cast<int>(atomic_get(&gapState().last_driver_error_value));
    }

    std::uint32_t Device::droppedEvents() const noexcept
    {
        return static_cast<std::uint32_t>(atomic_get(&gapState().dropped_event_value));
    }

} // namespace nucode::ble
nucode::ble::Device BLEDevice;
nucode::ble::Advertising BLEAdvertising;
nucode::ble::Scan BLEScan;
nucode::ble::ExtendedAdvertising BLEExtendedAdvertising;
nucode::ble::PeriodicAdvertising BLEPeriodicAdvertising;
nucode::ble::Pawr BLEPawr;
nucode::ble::Privacy BLEPrivacy;
nucode::ble::Connection BLEConnection;

#endif
