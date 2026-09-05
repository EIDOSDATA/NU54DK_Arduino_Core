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
    void lockGapLifecycle() noexcept
    {
        k_mutex_lock(&gap_lifecycle_mutex, K_FOREVER);
    }
    void unlockGapLifecycle() noexcept
    {
        k_mutex_unlock(&gap_lifecycle_mutex);
    }
    /** @brief event queue에 사용자 callback 대신 작은 record만 저장합니다. */
    void queueEvent(BLEEvent event, std::uint32_t generation) noexcept
    {
        const std::uint32_t current_generation =
            static_cast<std::uint32_t>(atomic_get(&gapState().device_session_generation));
        const GapEventRecord record = {
            .event = event,
            .generation = generation == 0U ? current_generation : generation,
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
        return referenceActiveConnection();
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
        atomic_set(&gapState().advertising_active, 0);
        atomic_set(&gapState().scanning_active, 0);
        atomic_set(&gapState().connection_connecting, 0);
        atomic_set(&gapState().connection_active, 0);
        atomic_set(&gapState().mtu_exchange_active, 0);
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
            if (record.generation !=
                static_cast<std::uint32_t>(atomic_get(&gapState().device_session_generation)))
            {
                continue;
            }
            BLEEventCallback callback = gapState().event_callback;
            if (callback != nullptr)
            {
                callback(record.event, gapState().event_context);
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

        struct bt_conn *active = nullptr;
        struct bt_conn *pending = nullptr;
        k_spinlock_key_t key = k_spin_lock(&gapState().connection_lock);
        active = gapState().active_connection;
        pending = gapState().pending_connection;
        gapState().active_connection = nullptr;
        gapState().pending_connection = nullptr;
        gapState().active_connection_generation = 0U;
        gapState().pending_connection_generation = 0U;
        gapState().last_peer_address = BLEAddress{};
        k_spin_unlock(&gapState().connection_lock, key);

        atomic_set(&gapState().connection_connecting, 0);
        atomic_set(&gapState().connection_active, 0);
        atomic_set(&gapState().mtu_exchange_active, 0);
        k_msgq_purge(&gapEventQueue());
        k_msgq_purge(&scanResultQueue());

        if (pending != nullptr)
        {
            static_cast<void>(bt_conn_disconnect(pending, BT_HCI_ERR_REMOTE_USER_TERM_CONN));
            bt_conn_unref(pending);
        }
        if (active != nullptr)
        {
            nucode::ble::internal::securityDisconnected(active);
            static_cast<void>(bt_conn_disconnect(active, BT_HCI_ERR_REMOTE_USER_TERM_CONN));
            bt_conn_unref(active);
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
nucode::ble::Connection BLEConnection;

#endif
