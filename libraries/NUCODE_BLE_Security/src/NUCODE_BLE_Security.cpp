/** @file @brief Security facade·event·connection lifecycle입니다.
 * SPDX-License-Identifier: MIT
 */
#include <NUCODE_BLE_Security.h>
#if !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE)
#include "internal/security/SecurityInternal.h"
namespace nucode::ble::internal::security
{
    namespace
    {
        SecurityState state{};
    }
    SecurityState &securityState() noexcept
    {
        return state;
    }
    namespace
    {
        constexpr std::size_t security_event_capacity = 24U;
        K_MSGQ_DEFINE(security_event_queue, sizeof(SecurityEventRecord), security_event_capacity,
                      alignof(SecurityEventRecord));
    } // namespace
    k_msgq &securityEventQueue() noexcept
    {
        return security_event_queue;
    }
    /** @brief thread 문맥 전용 공개 API인지 확인합니다. */
    bool requireThreadContext() noexcept
    {
        if (k_is_in_isr())
        {
            atomic_set(&securityState().security_error_value,
                       static_cast<atomic_val_t>(SecurityError::invalid_context));
            atomic_set(&securityState().security_driver_error_value, -EWOULDBLOCK);
            return false;
        }
        return true;
    }

    /** @brief 마지막 security 오류와 원본 driver 오류를 함께 기록합니다. */
    void recordSecurityError(SecurityError error, int driver_error) noexcept
    {
        atomic_set(&securityState().security_error_value, static_cast<atomic_val_t>(error));
        atomic_set(&securityState().security_driver_error_value, driver_error);
    }

    /** @brief connection의 security snapshot event를 만듭니다. */
    SecurityEventRecord makeEvent(SecurityEvent event, struct bt_conn *connection,
                                  std::uint32_t passkey, std::uint8_t reason) noexcept
    {
        SecurityEventRecord record = {};
        record.event = event;
        record.level =
            connection == nullptr
                ? static_cast<SecurityLevel>(atomic_get(&securityState().current_level_value))
                : static_cast<SecurityLevel>(bt_conn_get_security(connection));
        record.peer = publicAddress(connection == nullptr ? nullptr : bt_conn_get_dst(connection));
        record.passkey = passkey;
        record.reason = reason;
        record.bond_state = currentBondState();
        record.bonded = record.bond_state == BondState::verified;
        return record;
    }

    /** @brief 주소만 가진 bond event를 만듭니다. */
    SecurityEventRecord makePeerEvent(SecurityEvent event, const bt_addr_le_t *peer,
                                      BondState state) noexcept
    {
        SecurityEventRecord record = {};
        record.event = event;
        record.level = static_cast<SecurityLevel>(atomic_get(&securityState().current_level_value));
        record.peer = publicAddress(peer);
        record.bond_state = state;
        record.bonded = state == BondState::verified;
        return record;
    }

    /** @brief bounded event queue overflow를 공개 오류로 보존합니다. */
    void queueEvent(const SecurityEventRecord &record) noexcept
    {
        if (k_msgq_put(&securityEventQueue(), &record, K_NO_WAIT) != 0)
        {
            recordSecurityError(SecurityError::busy, -ENOBUFS);
        }
    }

    /** @brief 같은 연결 수준의 중복 callback을 제거해 security_changed를 한 번만 전달합니다. */
    void queueSecurityChangedIfNew(struct bt_conn *connection, bt_security_t level) noexcept
    {
        const atomic_val_t published =
            atomic_set(&securityState().published_level_value, static_cast<atomic_val_t>(level));
        if (published != static_cast<atomic_val_t>(level))
        {
            queueEvent(makeEvent(SecurityEvent::security_changed, connection));
        }
    }

    /** @brief 실제 link가 요구 level을 충족하면 bond와 event snapshot을 즉시 동기화합니다. */
    bool synchronizeSatisfiedSecurity(struct bt_conn *connection,
                                      bt_security_t required_level) noexcept
    {
        if (connection == nullptr)
        {
            return false;
        }
        const bt_security_t level = bt_conn_get_security(connection);
        if (level < required_level)
        {
            return false;
        }
        atomic_set(&securityState().current_level_value, static_cast<atomic_val_t>(level));
        verifySecureBond(connection, level);
        queueSecurityChangedIfNew(connection, level);
        return true;
    }

    /** @brief active connection에 호출자 수명 동안 reference를 얻습니다. */
    struct bt_conn *referenceActiveConnection() noexcept
    {
        k_spinlock_key_t key = k_spin_lock(&securityState().connection_lock);
        struct bt_conn *connection = securityState().active_connection;
        if (connection != nullptr)
        {
            bt_conn_ref(connection);
        }
        k_spin_unlock(&securityState().connection_lock, key);
        return connection;
    }

    /** @brief callback connection이 현재 API가 소유한 exact connection인지 확인합니다. */
    bool isActiveConnection(struct bt_conn *connection) noexcept
    {
        struct bt_conn *active = referenceActiveConnection();
        const bool matches = active != nullptr && active == connection;
        if (active != nullptr)
        {
            bt_conn_unref(active);
        }
        return matches;
    }

    /** @brief active connection이 지정 peer인지 확인하고 제거합니다. */
    bool releaseActiveConnection(struct bt_conn *matching) noexcept
    {
        struct bt_conn *released = nullptr;
        k_spinlock_key_t key = k_spin_lock(&securityState().connection_lock);
        if (securityState().active_connection != nullptr &&
            securityState().active_connection == matching)
        {
            released = securityState().active_connection;
            securityState().active_connection = nullptr;
        }
        k_spin_unlock(&securityState().connection_lock, key);
        if (released != nullptr)
        {
            bt_conn_unref(released);
            return true;
        }
        return false;
    }

} // namespace nucode::ble::internal::security
namespace nucode::ble
{
    using namespace internal::security;
    bool SecurityManager::begin(const SecurityConfig &config) noexcept
    {
        if (!requireThreadContext())
        {
            return false;
        }
        const unsigned int level = static_cast<unsigned int>(config.minimum_level);
        const unsigned int io_capability = static_cast<unsigned int>(config.io_capability);
        if (level < static_cast<unsigned int>(SecurityLevel::encrypted) ||
            level > static_cast<unsigned int>(SecurityLevel::secure_connections) ||
            io_capability > static_cast<unsigned int>(SecurityIoCapability::keyboard_display) ||
            config.response_timeout_ms < 1000U || config.response_timeout_ms > 300000U)
        {
            recordSecurityError(SecurityError::invalid_argument, -EINVAL);
            return false;
        }
        if (!atomic_cas(&securityState().security_initialized, 0, 1))
        {
            recordSecurityError(SecurityError::busy, -EALREADY);
            return false;
        }

        securityState().security_config = config;
        k_msgq_purge(&securityEventQueue());
        k_spinlock_key_t startup_key = k_spin_lock(&bondStorage().startup_bond_lock);
        bondStorage().startup_bond_count = 0U;
        k_spin_unlock(&bondStorage().startup_bond_lock, startup_key);
        atomic_set(&bondStorage().startup_bond_snapshot_ready, 0);
        atomic_set(&securityState().paired_value, 0);
        setBondLifecycle(nullptr, BondState::none, false);
        prepareAuthenticationCallbacks(config.io_capability);
        int result = bt_conn_auth_cb_register(&pairingState().authentication_callbacks);
        if (result == 0)
        {
            result = bt_conn_auth_info_cb_register(&pairingState().authentication_info_callbacks);
        }
        if (result < 0)
        {
            atomic_set(&securityState().security_initialized, 0);
            recordSecurityError(SecurityError::driver_error, result);
            return false;
        }
        bt_set_bondable(config.bonding);
        recordSecurityError(SecurityError::none);
        return true;
    }

    void SecurityManager::poll() noexcept
    {
        if (!requireThreadContext())
        {
            return;
        }
        if (atomic_get(&securityState().security_initialized) == 0)
        {
            recordSecurityError(SecurityError::not_initialized, -EACCES);
            return;
        }
        processPendingTimeout();

        SecurityEventRecord event = {};
        while (k_msgq_get(&securityEventQueue(), &event, K_NO_WAIT) == 0)
        {
            SecurityEventCallback callback = securityState().security_event_callback;
            if (callback != nullptr)
            {
                callback(event, securityState().security_event_context);
            }
        }
    }

    bool SecurityManager::requestSecurity() noexcept
    {
        if (!requireThreadContext())
        {
            return false;
        }
        if (atomic_get(&securityState().security_initialized) == 0)
        {
            recordSecurityError(SecurityError::not_initialized, -EACCES);
            return false;
        }
        struct bt_conn *connection = referenceActiveConnection();
        if (connection == nullptr)
        {
            recordSecurityError(SecurityError::not_connected, -ENOTCONN);
            return false;
        }
        const bt_security_t required_level =
            static_cast<bt_security_t>(securityState().security_config.minimum_level);
        if (synchronizeSatisfiedSecurity(connection, required_level))
        {
            bt_conn_unref(connection);
            recordSecurityError(SecurityError::none);
            return true;
        }
        const int result = bt_conn_set_security(connection, required_level);
        if (result >= 0)
        {
            static_cast<void>(synchronizeSatisfiedSecurity(connection, required_level));
        }
        bt_conn_unref(connection);
        if (result < 0)
        {
            recordSecurityError(
                result == -EBUSY ? SecurityError::busy : SecurityError::driver_error, result);
            return false;
        }
        recordSecurityError(SecurityError::none);
        return true;
    }

    bool SecurityManager::paired() const noexcept
    {
        return atomic_get(&securityState().paired_value) != 0;
    }

    bool SecurityManager::bonded() const noexcept
    {
        return currentBondState() == BondState::verified;
    }

    BondState SecurityManager::bondState() const noexcept
    {
        return currentBondState();
    }

    SecurityLevel SecurityManager::currentLevel() const noexcept
    {
        return static_cast<SecurityLevel>(atomic_get(&securityState().current_level_value));
    }

    void SecurityManager::onEvent(SecurityEventCallback callback, void *context) noexcept
    {
        if (!requireThreadContext())
        {
            return;
        }
        securityState().security_event_callback = callback;
        securityState().security_event_context = context;
    }

    SecurityError SecurityManager::lastError() const noexcept
    {
        return static_cast<SecurityError>(atomic_get(&securityState().security_error_value));
    }

    int SecurityManager::lastDriverError() const noexcept
    {
        return static_cast<int>(atomic_get(&securityState().security_driver_error_value));
    }

} // namespace nucode::ble
namespace nucode::ble::internal
{
    using namespace security;
    void securityConnected(struct bt_conn *connection) noexcept
    {
        if (connection == nullptr)
        {
            return;
        }
        bool inserted = false;
        k_spinlock_key_t key = k_spin_lock(&securityState().connection_lock);
        if (securityState().active_connection == nullptr)
        {
            securityState().active_connection = bt_conn_ref(connection);
            inserted = true;
        }
        k_spin_unlock(&securityState().connection_lock, key);
        if (!inserted)
        {
            return;
        }
        const bt_security_t level = bt_conn_get_security(connection);
        atomic_set(&securityState().current_level_value, static_cast<atomic_val_t>(level));
        atomic_set(&securityState().published_level_value, 0);
        atomic_set(&securityState().paired_value, 0);
        captureStartupBonds();
        const bt_addr_le_t *const peer = bt_conn_get_dst(connection);
        if (isStartupBond(peer))
        {
            setBondLifecycle(peer, BondState::restored_candidate, false);
            queueEvent(makePeerEvent(SecurityEvent::bond_restored_candidate, peer,
                                     BondState::restored_candidate));
        }
        else
        {
            setBondLifecycle(nullptr, BondState::none, false);
        }
        verifySecureBond(connection, level);
        if (level >= BT_SECURITY_L2)
        {
            queueSecurityChangedIfNew(connection, level);
        }
        if (atomic_get(&hidState().hid_initialized) != 0)
        {
            lockHidApi();
            const int result = attachHidsLocked(connection);
            unlockHidApi();
            if (result < 0)
            {
                recordHidError(SecurityError::driver_error, result);
            }
        }
    }

    void securityDisconnected(struct bt_conn *connection) noexcept
    {
        if (connection == nullptr)
        {
            return;
        }
        if (atomic_get(&hidState().hid_initialized) != 0)
        {
            lockHidApi();
            const int result = detachHidsLocked(connection);
            unlockHidApi();
            if (result < 0)
            {
                recordHidError(SecurityError::driver_error, result);
            }
        }
        clearPending(connection);
        if (releaseActiveConnection(connection))
        {
            if (bondLifecycleMatches(bt_conn_get_dst(connection)) &&
                currentBondState() != BondState::removal_requested)
            {
                setBondLifecycle(nullptr, BondState::none, false);
            }
            atomic_set(&securityState().paired_value, 0);
            atomic_set(&securityState().current_level_value,
                       static_cast<atomic_val_t>(SecurityLevel::none));
            atomic_set(&securityState().published_level_value, 0);
        }
    }

    void securityChanged(struct bt_conn *connection, bt_security_t level,
                         enum bt_security_err error) noexcept
    {
        if (connection == nullptr)
        {
            return;
        }
        struct bt_conn *active = referenceActiveConnection();
        const bool is_active = active == connection;
        if (active != nullptr)
        {
            bt_conn_unref(active);
        }
        if (!is_active)
        {
            return;
        }
        if (error != BT_SECURITY_ERR_SUCCESS)
        {
            if (bondLifecycleMatches(bt_conn_get_dst(connection)))
            {
                setBondLifecycle(nullptr, BondState::none, false);
            }
            atomic_set(&securityState().paired_value, 0);
            recordSecurityError(SecurityError::driver_error, -static_cast<int>(error));
            queueEvent(
                makeEvent(SecurityEvent::error, connection, 0U, static_cast<std::uint8_t>(error)));
            return;
        }
        atomic_set(&securityState().current_level_value, static_cast<atomic_val_t>(level));
        verifySecureBond(connection, level);
        queueSecurityChangedIfNew(connection, level);
    }

} // namespace nucode::ble::internal
nucode::ble::SecurityManager BLESecurity;
#endif
