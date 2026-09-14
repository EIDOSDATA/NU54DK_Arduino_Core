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

        /** @brief connection lock을 보유한 호출자에게 exact link slot을 반환합니다. */
        SecurityLinkState *linkForConnectionLocked(struct bt_conn *connection) noexcept
        {
            for (std::size_t index = 0U; index < maximum_security_links; ++index)
            {
                SecurityLinkState &link = securityState().links[index];
                if (link.connection == connection)
                {
                    return &link;
                }
            }
            return nullptr;
        }

        /** @brief connection lock을 보유한 호출자에게 generation link slot을 반환합니다. */
        SecurityLinkState *linkForHandleLocked(BLEConnectionHandle handle) noexcept
        {
            for (std::size_t index = 0U; index < maximum_security_links; ++index)
            {
                SecurityLinkState &link = securityState().links[index];
                if (link.connection != nullptr && link.handle == handle)
                {
                    return &link;
                }
            }
            return nullptr;
        }

        /** @brief legacy facade가 가리키는 link인지 확인합니다. */
        bool isLegacyConnectionLocked(struct bt_conn *connection) noexcept
        {
            return connection != nullptr && securityState().active_connection == connection;
        }
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
        record.connection = securityHandle(connection);
        record.level =
            connection == nullptr
                ? static_cast<SecurityLevel>(atomic_get(&securityState().current_level_value))
                : static_cast<SecurityLevel>(bt_conn_get_security(connection));
        record.peer = publicAddress(connection == nullptr ? nullptr : bt_conn_get_dst(connection));
        record.passkey = passkey;
        record.reason = reason;
        record.bond_state =
            connection == nullptr ? currentBondState() : currentBondState(connection);
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

    /** @brief identity가 준비된 같은 연결 수준을 security_changed로 한 번만 전달합니다. */
    void queueSecurityChangedIfNew(struct bt_conn *connection, bt_security_t level) noexcept
    {
        if (connection == nullptr)
        {
            return;
        }
        bool legacy = false;
        SecurityLinkState *link = nullptr;
        k_spinlock_key_t key = k_spin_lock(&securityState().connection_lock);
        link = linkForConnectionLocked(connection);
        legacy = isLegacyConnectionLocked(connection);
        k_spin_unlock(&securityState().connection_lock, key);
        if (link == nullptr)
        {
            return;
        }
        if (isResolvablePrivateAddress(bt_conn_get_dst(connection)))
        {
            atomic_set(&link->pending_security_event, 1);
            if (legacy)
            {
                atomic_set(&securityState().pending_security_event, 1);
            }
            return;
        }
        atomic_set(&link->pending_security_event, 0);
        const atomic_val_t published = atomic_set(&link->published_level_value,
                                                  static_cast<atomic_val_t>(level));
        if (legacy)
        {
            atomic_set(&securityState().pending_security_event, 0);
            atomic_set(&securityState().published_level_value,
                       static_cast<atomic_val_t>(level));
        }
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
        setLinkLevel(connection, level);
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

    /** @brief 지정 generation 보안 link에 호출자 수명 동안 reference를 얻습니다. */
    struct bt_conn *referenceConnection(BLEConnectionHandle handle) noexcept
    {
        struct bt_conn *connection = nullptr;
        k_spinlock_key_t key = k_spin_lock(&securityState().connection_lock);
        SecurityLinkState *const link = linkForHandleLocked(handle);
        if (link != nullptr)
        {
            connection = bt_conn_ref(link->connection);
        }
        k_spin_unlock(&securityState().connection_lock, key);
        return connection;
    }

    /** @brief callback connection이 현재 API가 소유한 exact connection인지 확인합니다. */
    bool isActiveConnection(struct bt_conn *connection) noexcept
    {
        bool matches = false;
        k_spinlock_key_t key = k_spin_lock(&securityState().connection_lock);
        matches = linkForConnectionLocked(connection) != nullptr;
        k_spin_unlock(&securityState().connection_lock, key);
        return matches;
    }

    /** @brief generation과 native connection이 같은 active slot인지 확인합니다. */
    bool isActiveConnection(BLEConnectionHandle handle, struct bt_conn *connection) noexcept
    {
        bool matches = false;
        k_spinlock_key_t key = k_spin_lock(&securityState().connection_lock);
        SecurityLinkState *const link = linkForHandleLocked(handle);
        matches = link != nullptr && link->connection == connection;
        k_spin_unlock(&securityState().connection_lock, key);
        return matches;
    }

    /** @brief native connection을 보안 계층이 보존한 generation handle로 변환합니다. */
    BLEConnectionHandle securityHandle(struct bt_conn *connection) noexcept
    {
        BLEConnectionHandle handle;
        k_spinlock_key_t key = k_spin_lock(&securityState().connection_lock);
        SecurityLinkState *const link = linkForConnectionLocked(connection);
        if (link != nullptr)
        {
            handle = link->handle;
        }
        k_spin_unlock(&securityState().connection_lock, key);
        return handle;
    }

    /** @brief generation link의 공개 상태를 한 lock 구간에서 복사합니다. */
    bool copyLinkState(BLEConnectionHandle handle, bool &paired, SecurityLevel &level,
                       BondState &bond_state) noexcept
    {
        bool found = false;
        k_spinlock_key_t key = k_spin_lock(&securityState().connection_lock);
        SecurityLinkState *const link = linkForHandleLocked(handle);
        if (link != nullptr)
        {
            paired = atomic_get(&link->paired_value) != 0;
            level = static_cast<SecurityLevel>(atomic_get(&link->current_level_value));
            bond_state = link->bond_lifecycle.state;
            found = true;
        }
        k_spin_unlock(&securityState().connection_lock, key);
        return found;
    }

    /** @brief exact link의 pairing 결과와 legacy mirror를 함께 갱신합니다. */
    void setLinkPaired(struct bt_conn *connection, bool paired) noexcept
    {
        k_spinlock_key_t key = k_spin_lock(&securityState().connection_lock);
        SecurityLinkState *const link = linkForConnectionLocked(connection);
        if (link != nullptr)
        {
            atomic_set(&link->paired_value, paired ? 1 : 0);
            if (isLegacyConnectionLocked(connection))
            {
                atomic_set(&securityState().paired_value, paired ? 1 : 0);
            }
        }
        k_spin_unlock(&securityState().connection_lock, key);
    }

    /** @brief exact link의 security level과 legacy mirror를 함께 갱신합니다. */
    void setLinkLevel(struct bt_conn *connection, bt_security_t level) noexcept
    {
        k_spinlock_key_t key = k_spin_lock(&securityState().connection_lock);
        SecurityLinkState *const link = linkForConnectionLocked(connection);
        if (link != nullptr)
        {
            atomic_set(&link->current_level_value, static_cast<atomic_val_t>(level));
            if (isLegacyConnectionLocked(connection))
            {
                atomic_set(&securityState().current_level_value,
                           static_cast<atomic_val_t>(level));
            }
        }
        k_spin_unlock(&securityState().connection_lock, key);
    }

    /** @brief active connection이 지정 peer인지 확인하고 제거합니다. */
    bool releaseActiveConnection(struct bt_conn *matching) noexcept
    {
        bool released = false;
        k_spinlock_key_t key = k_spin_lock(&securityState().connection_lock);
        if (securityState().active_connection != nullptr &&
            securityState().active_connection == matching)
        {
            securityState().active_connection = nullptr;
            released = true;
        }
        k_spin_unlock(&securityState().connection_lock, key);
        return released;
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
        atomic_set(&securityState().current_level_value,
                   static_cast<atomic_val_t>(SecurityLevel::none));
        atomic_set(&securityState().published_level_value, 0);
        atomic_set(&securityState().pending_security_event, 0);
        k_spinlock_key_t connection_key = k_spin_lock(&securityState().connection_lock);
        securityState().active_connection = nullptr;
        for (std::size_t index = 0U; index < maximum_security_links; ++index)
        {
            SecurityLinkState &link = securityState().links[index];
            link.handle = {};
            link.connection = nullptr;
            atomic_set(&link.paired_value, 0);
            atomic_set(&link.current_level_value,
                       static_cast<atomic_val_t>(SecurityLevel::none));
            atomic_set(&link.published_level_value, 0);
            atomic_set(&link.pending_security_event, 0);
            link.bond_lifecycle = {};
        }
        k_spin_unlock(&securityState().connection_lock, connection_key);
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

        struct PendingSecuritySnapshot
        {
            struct bt_conn *connection = nullptr;
            bt_security_t level = BT_SECURITY_L1;
        } pending[maximum_security_links] = {};
        std::size_t pending_count = 0U;
        k_spinlock_key_t key = k_spin_lock(&securityState().connection_lock);
        for (std::size_t index = 0U; index < maximum_security_links; ++index)
        {
            SecurityLinkState &link = securityState().links[index];
            if (link.connection != nullptr && atomic_get(&link.pending_security_event) != 0)
            {
                pending[pending_count].connection = bt_conn_ref(link.connection);
                pending[pending_count].level =
                    static_cast<bt_security_t>(atomic_get(&link.current_level_value));
                ++pending_count;
            }
        }
        k_spin_unlock(&securityState().connection_lock, key);
        for (std::size_t index = 0U; index < pending_count; ++index)
        {
            queueSecurityChangedIfNew(pending[index].connection, pending[index].level);
            bt_conn_unref(pending[index].connection);
        }

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

    bool SecurityManager::requestSecurity(BLEConnectionHandle handle) noexcept
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
        struct bt_conn *connection = internal::security::referenceConnection(handle);
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

    bool SecurityManager::paired(BLEConnectionHandle connection) const noexcept
    {
        bool paired_value = false;
        SecurityLevel level = SecurityLevel::none;
        BondState state = BondState::none;
        static_cast<void>(copyLinkState(connection, paired_value, level, state));
        return paired_value;
    }

    bool SecurityManager::bonded() const noexcept
    {
        return currentBondState() == BondState::verified;
    }

    bool SecurityManager::bonded(BLEConnectionHandle connection) const noexcept
    {
        return bondState(connection) == BondState::verified;
    }

    BondState SecurityManager::bondState() const noexcept
    {
        return currentBondState();
    }

    BondState SecurityManager::bondState(BLEConnectionHandle connection) const noexcept
    {
        bool paired_value = false;
        SecurityLevel level = SecurityLevel::none;
        BondState state = BondState::none;
        static_cast<void>(copyLinkState(connection, paired_value, level, state));
        return state;
    }

    SecurityLevel SecurityManager::currentLevel() const noexcept
    {
        return static_cast<SecurityLevel>(atomic_get(&securityState().current_level_value));
    }

    SecurityLevel SecurityManager::currentLevel(BLEConnectionHandle connection) const noexcept
    {
        bool paired_value = false;
        SecurityLevel level = SecurityLevel::none;
        BondState state = BondState::none;
        static_cast<void>(copyLinkState(connection, paired_value, level, state));
        return level;
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
    void securityConnected(struct bt_conn *connection, BLEConnectionHandle handle) noexcept
    {
        if (connection == nullptr || !handle.valid())
        {
            return;
        }
        bool inserted = false;
        bool legacy = false;
        k_spinlock_key_t key = k_spin_lock(&securityState().connection_lock);
        if (linkForConnectionLocked(connection) == nullptr && linkForHandleLocked(handle) == nullptr)
        {
            for (std::size_t index = 0U; index < maximum_security_links; ++index)
            {
                SecurityLinkState &link = securityState().links[index];
                if (link.connection != nullptr)
                {
                    continue;
                }
                link.handle = handle;
                link.connection = bt_conn_ref(connection);
                atomic_set(&link.paired_value, 0);
                atomic_set(&link.current_level_value,
                           static_cast<atomic_val_t>(bt_conn_get_security(connection)));
                atomic_set(&link.published_level_value, 0);
                atomic_set(&link.pending_security_event, 0);
                link.bond_lifecycle = {};
                if (securityState().active_connection == nullptr)
                {
                    securityState().active_connection = connection;
                    legacy = true;
                }
                inserted = true;
                break;
            }
        }
        k_spin_unlock(&securityState().connection_lock, key);
        if (!inserted)
        {
            return;
        }
        const bt_security_t level = bt_conn_get_security(connection);
        setLinkLevel(connection, level);
        if (legacy)
        {
            atomic_set(&securityState().published_level_value, 0);
            atomic_set(&securityState().pending_security_event, 0);
            atomic_set(&securityState().paired_value, 0);
        }
        captureStartupBonds();
        const bt_addr_le_t *const peer = bt_conn_get_dst(connection);
        if (isStartupBond(peer))
        {
            setBondLifecycle(connection, peer, BondState::restored_candidate, false);
            queueEvent(makeEvent(SecurityEvent::bond_restored_candidate, connection));
        }
        else
        {
            setBondLifecycle(connection, nullptr, BondState::none, false);
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

    void securityConnected(struct bt_conn *connection) noexcept
    {
        securityConnected(connection, handleForActiveConnection(connection));
    }

    void securityDisconnected(struct bt_conn *connection, BLEConnectionHandle handle) noexcept
    {
        if (connection == nullptr || !handle.valid())
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
        clearPending(handle);
        struct bt_conn *released = nullptr;
        struct bt_conn *promoted = nullptr;
        BondLifecycleState promoted_bond = {};
        bool was_legacy = false;
        k_spinlock_key_t key = k_spin_lock(&securityState().connection_lock);
        SecurityLinkState *const link = linkForHandleLocked(handle);
        if (link != nullptr && link->connection == connection)
        {
            released = link->connection;
            was_legacy = securityState().active_connection == connection;
            link->handle = {};
            link->connection = nullptr;
            atomic_set(&link->paired_value, 0);
            atomic_set(&link->current_level_value,
                       static_cast<atomic_val_t>(SecurityLevel::none));
            atomic_set(&link->published_level_value, 0);
            atomic_set(&link->pending_security_event, 0);
            link->bond_lifecycle = {};
            if (was_legacy)
            {
                securityState().active_connection = nullptr;
                for (std::size_t index = 0U; index < maximum_security_links; ++index)
                {
                    SecurityLinkState &candidate = securityState().links[index];
                    if (candidate.connection != nullptr)
                    {
                        promoted = candidate.connection;
                        promoted_bond = candidate.bond_lifecycle;
                        securityState().active_connection = promoted;
                        atomic_set(&securityState().paired_value,
                                   atomic_get(&candidate.paired_value));
                        atomic_set(&securityState().current_level_value,
                                   atomic_get(&candidate.current_level_value));
                        atomic_set(&securityState().published_level_value,
                                   atomic_get(&candidate.published_level_value));
                        atomic_set(&securityState().pending_security_event,
                                   atomic_get(&candidate.pending_security_event));
                        break;
                    }
                }
            }
        }
        k_spin_unlock(&securityState().connection_lock, key);
        if (released != nullptr)
        {
            bt_conn_unref(released);
        }
        if (was_legacy)
        {
            if (promoted != nullptr)
            {
                setBondLifecycle(promoted_bond.peer_valid ? &promoted_bond.peer : nullptr,
                                 promoted_bond.state,
                                 promoted_bond.paired_this_connection);
            }
            else if (currentBondState() != BondState::removal_requested)
            {
                setBondLifecycle(nullptr, BondState::none, false);
            }
        }
        if (was_legacy && promoted == nullptr)
        {
            atomic_set(&securityState().paired_value, 0);
            atomic_set(&securityState().current_level_value,
                       static_cast<atomic_val_t>(SecurityLevel::none));
            atomic_set(&securityState().published_level_value, 0);
            atomic_set(&securityState().pending_security_event, 0);
        }
    }

    void securityDisconnected(struct bt_conn *connection) noexcept
    {
        securityDisconnected(connection, securityHandle(connection));
    }

    void securityChanged(struct bt_conn *connection, BLEConnectionHandle handle,
                         bt_security_t level, enum bt_security_err error) noexcept
    {
        if (connection == nullptr || !isActiveConnection(handle, connection))
        {
            return;
        }
        if (error != BT_SECURITY_ERR_SUCCESS)
        {
            if (bondLifecycleMatches(connection, bt_conn_get_dst(connection)))
            {
                setBondLifecycle(connection, nullptr, BondState::none, false);
            }
            setLinkPaired(connection, false);
            recordSecurityError(SecurityError::driver_error, -static_cast<int>(error));
            queueEvent(
                makeEvent(SecurityEvent::error, connection, 0U, static_cast<std::uint8_t>(error)));
            return;
        }
        setLinkLevel(connection, level);
        verifySecureBond(connection, level);
        queueSecurityChangedIfNew(connection, level);
    }

    void securityChanged(struct bt_conn *connection, bt_security_t level,
                         enum bt_security_err error) noexcept
    {
        securityChanged(connection, securityHandle(connection), level, error);
    }

} // namespace nucode::ble::internal
nucode::ble::SecurityManager BLESecurity;
#endif
