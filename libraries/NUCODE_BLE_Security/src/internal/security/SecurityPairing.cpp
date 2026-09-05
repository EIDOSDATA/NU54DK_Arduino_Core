/** @file @brief SMP 인증 callback과 bounded 사용자 응답 reference입니다.
 * SPDX-License-Identifier: MIT
 */
#if !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE)
#include "SecurityInternal.h"
namespace nucode::ble::internal::security
{
    namespace
    {
        PairingState state{};
    }
    PairingState &pairingState() noexcept
    {
        return state;
    }
    /** @brief pending SMP 사용자 응답 connection을 안전하게 해제합니다. */
    void clearPending(struct bt_conn *matching_connection) noexcept
    {
        struct bt_conn *released = nullptr;
        k_spinlock_key_t key = k_spin_lock(&pairingState().pending_lock);
        if (pairingState().pending_state.connection != nullptr &&
            (matching_connection == nullptr ||
             matching_connection == pairingState().pending_state.connection))
        {
            released = pairingState().pending_state.connection;
            pairingState().pending_state = {};
        }
        k_spin_unlock(&pairingState().pending_lock, key);
        if (released != nullptr)
        {
            bt_conn_unref(released);
        }
    }

    /** @brief 사용자 응답이 필요한 SMP 요청을 하나만 보존합니다. */
    bool setPending(struct bt_conn *connection, PendingResponse response, SecurityEvent event,
                    std::uint32_t passkey) noexcept
    {
        if (connection == nullptr)
        {
            return false;
        }
        if (!isActiveConnection(connection))
        {
            static_cast<void>(bt_conn_auth_cancel(connection));
            return false;
        }
        bool accepted = false;
        k_spinlock_key_t key = k_spin_lock(&pairingState().pending_lock);
        if (pairingState().pending_state.connection == nullptr)
        {
            pairingState().pending_state.connection = bt_conn_ref(connection);
            pairingState().pending_state.response = response;
            pairingState().pending_state.deadline_ms =
                k_uptime_get() +
                static_cast<std::int64_t>(securityState().security_config.response_timeout_ms);
            accepted = true;
        }
        k_spin_unlock(&pairingState().pending_lock, key);
        if (!accepted)
        {
            recordSecurityError(SecurityError::busy, -EBUSY);
            queueEvent(makeEvent(SecurityEvent::error, connection));
            static_cast<void>(bt_conn_auth_cancel(connection));
            return false;
        }
        queueEvent(makeEvent(event, connection, passkey));
        return true;
    }

    /** @brief 예상 종류의 pending connection 소유권을 호출자에게 넘깁니다. */
    struct bt_conn *takePending(PendingResponse expected) noexcept
    {
        struct bt_conn *connection = nullptr;
        k_spinlock_key_t key = k_spin_lock(&pairingState().pending_lock);
        if (pairingState().pending_state.connection != nullptr &&
            pairingState().pending_state.response == expected)
        {
            connection = pairingState().pending_state.connection;
            pairingState().pending_state = {};
        }
        k_spin_unlock(&pairingState().pending_lock, key);
        return connection;
    }

    /** @brief timeout이 지난 pending pairing 요청을 취소합니다. */
    void processPendingTimeout() noexcept
    {
        struct bt_conn *connection = nullptr;
        k_spinlock_key_t key = k_spin_lock(&pairingState().pending_lock);
        if (pairingState().pending_state.connection != nullptr &&
            k_uptime_get() >= pairingState().pending_state.deadline_ms)
        {
            connection = pairingState().pending_state.connection;
            pairingState().pending_state = {};
        }
        k_spin_unlock(&pairingState().pending_lock, key);
        if (connection == nullptr)
        {
            return;
        }
        static_cast<void>(bt_conn_auth_cancel(connection));
        recordSecurityError(SecurityError::timeout, -ETIMEDOUT);
        queueEvent(makeEvent(SecurityEvent::timeout, connection));
        bt_conn_unref(connection);
    }

    /** @brief 새 SMP pairing 시작 시 restored candidate를 즉시 무효화합니다. */
    void markPairingStarted(struct bt_conn *connection) noexcept
    {
        if (!isActiveConnection(connection))
        {
            return;
        }
        const bt_addr_le_t *const peer = bt_conn_get_dst(connection);
        if (bondLifecycleMatches(peer) && currentBondState() == BondState::restored_candidate)
        {
            setBondLifecycle(peer, BondState::none, true);
        }
        atomic_set(&securityState().paired_value, 0);
    }

    /** @brief 모든 SMP pairing req/rsp를 허용하되 새 pairing 여부를 먼저 기록합니다. */
    enum bt_security_err pairingAccept(struct bt_conn *connection,
                                       const struct bt_conn_pairing_feat *features)
    {
        ARG_UNUSED(features);
        markPairingStarted(connection);
        return BT_SECURITY_ERR_SUCCESS;
    }

    /** @brief passkey display 요청을 main-thread event로 전달합니다. */
    void passkeyDisplay(struct bt_conn *connection, unsigned int passkey)
    {
        markPairingStarted(connection);
        if (isActiveConnection(connection))
        {
            queueEvent(makeEvent(SecurityEvent::passkey_display, connection, passkey));
        }
    }

    /** @brief passkey 입력 요청을 main-thread event로 전달합니다. */
    void passkeyEntry(struct bt_conn *connection)
    {
        markPairingStarted(connection);
        static_cast<void>(setPending(connection, PendingResponse::passkey_entry,
                                     SecurityEvent::passkey_input_requested));
    }

    /** @brief numeric comparison 요청을 main-thread event로 전달합니다. */
    void passkeyConfirm(struct bt_conn *connection, unsigned int passkey)
    {
        markPairingStarted(connection);
        static_cast<void>(setPending(connection, PendingResponse::passkey_confirmation,
                                     SecurityEvent::passkey_confirmation_requested, passkey));
    }

    /** @brief Just Works pairing도 명시적 Sketch 승인 뒤에만 진행합니다. */
    void pairingConfirm(struct bt_conn *connection)
    {
        markPairingStarted(connection);
        static_cast<void>(setPending(connection, PendingResponse::pairing_confirmation,
                                     SecurityEvent::pairing_requested));
    }

    /** @brief stack이 사용자 요청을 취소하면 pending reference를 회수합니다. */
    void authenticationCancelled(struct bt_conn *connection)
    {
        clearPending(connection);
        if (isActiveConnection(connection))
        {
            queueEvent(makeEvent(SecurityEvent::pairing_cancelled, connection));
        }
    }

    /** @brief pairing 성공을 기록하되 같은 boot에서 persistence 완료로 승격하지 않습니다. */
    void pairingComplete(struct bt_conn *connection, bool bonded)
    {
        clearPending(connection);
        if (!isActiveConnection(connection))
        {
            return;
        }
        atomic_set(&securityState().paired_value, 1);
        atomic_set(&securityState().current_level_value,
                   static_cast<atomic_val_t>(bt_conn_get_security(connection)));
        const bt_addr_le_t *const peer = bt_conn_get_dst(connection);
        if (bonded && securityState().security_config.bonding)
        {
            setBondLifecycle(peer, BondState::persistence_pending, true);
            queueEvent(makeEvent(SecurityEvent::paired, connection));
            queueEvent(makePeerEvent(SecurityEvent::bond_persistence_pending, peer,
                                     BondState::persistence_pending));
        }
        else
        {
            setBondLifecycle(peer, BondState::none, true);
            queueEvent(makeEvent(SecurityEvent::paired, connection));
        }
    }

    /** @brief pairing 실패 reason을 key material 없이 event로 전달합니다. */
    void pairingFailed(struct bt_conn *connection, enum bt_security_err reason)
    {
        clearPending(connection);
        if (!isActiveConnection(connection))
        {
            return;
        }
        atomic_set(&securityState().paired_value, 0);
        if (bondLifecycleMatches(bt_conn_get_dst(connection)))
        {
            setBondLifecycle(nullptr, BondState::none, false);
        }
        recordSecurityError(SecurityError::rejected, -static_cast<int>(reason));
        queueEvent(makeEvent(SecurityEvent::pairing_failed, connection, 0U,
                             static_cast<std::uint8_t>(reason)));
    }

    /** @brief runtime bond 삭제 callback을 내부 snapshot에만 반영합니다. */
    void bondDeleted(std::uint8_t identity, const bt_addr_le_t *peer)
    {
        ARG_UNUSED(identity);
        removeStartupBond(peer);
        if (bondLifecycleMatches(peer))
        {
            if (currentBondState() != BondState::removal_requested)
            {
                setBondLifecycle(nullptr, BondState::none, false);
            }
            atomic_set(&securityState().paired_value, 0);
        }
    }

    /** @brief 실제 SMP 사용자 입출력 능력만 auth callback으로 공개합니다. */
    void prepareAuthenticationCallbacks(SecurityIoCapability capability) noexcept
    {
        pairingState().authentication_callbacks = {};
        pairingState().authentication_callbacks.pairing_accept = pairingAccept;
        pairingState().authentication_callbacks.cancel = authenticationCancelled;
        pairingState().authentication_callbacks.pairing_confirm = pairingConfirm;

        switch (capability)
        {
        case SecurityIoCapability::no_input_output:
            break;
        case SecurityIoCapability::display_only:
            pairingState().authentication_callbacks.passkey_display = passkeyDisplay;
            break;
        case SecurityIoCapability::keyboard_only:
            pairingState().authentication_callbacks.passkey_entry = passkeyEntry;
            break;
        case SecurityIoCapability::display_yes_no:
            pairingState().authentication_callbacks.passkey_display = passkeyDisplay;
            pairingState().authentication_callbacks.passkey_confirm = passkeyConfirm;
            break;
        case SecurityIoCapability::keyboard_display:
            pairingState().authentication_callbacks.passkey_display = passkeyDisplay;
            pairingState().authentication_callbacks.passkey_entry = passkeyEntry;
            pairingState().authentication_callbacks.passkey_confirm = passkeyConfirm;
            break;
        }

        pairingState().authentication_info_callbacks = {};
        pairingState().authentication_info_callbacks.pairing_complete = pairingComplete;
        pairingState().authentication_info_callbacks.pairing_failed = pairingFailed;
        pairingState().authentication_info_callbacks.bond_deleted = bondDeleted;
    }

} // namespace nucode::ble::internal::security
namespace nucode::ble
{
    using namespace internal::security;
    bool SecurityManager::acceptPairing(bool accept) noexcept
    {
        if (!requireThreadContext())
        {
            return false;
        }
        struct bt_conn *connection = takePending(PendingResponse::pairing_confirmation);
        if (connection == nullptr)
        {
            recordSecurityError(SecurityError::invalid_state, -EALREADY);
            return false;
        }
        const int result =
            accept ? bt_conn_auth_pairing_confirm(connection) : bt_conn_auth_cancel(connection);
        bt_conn_unref(connection);
        if (result < 0)
        {
            recordSecurityError(SecurityError::driver_error, result);
            return false;
        }
        if (!accept)
        {
            recordSecurityError(SecurityError::rejected, -ECANCELED);
        }
        else
        {
            recordSecurityError(SecurityError::none);
        }
        return true;
    }

    bool SecurityManager::enterPasskey(std::uint32_t passkey) noexcept
    {
        if (!requireThreadContext() || passkey > 999999U)
        {
            if (passkey > 999999U)
            {
                recordSecurityError(SecurityError::invalid_argument, -EINVAL);
            }
            return false;
        }
        struct bt_conn *connection = takePending(PendingResponse::passkey_entry);
        if (connection == nullptr)
        {
            recordSecurityError(SecurityError::invalid_state, -EALREADY);
            return false;
        }
        const int result = bt_conn_auth_passkey_entry(connection, passkey);
        bt_conn_unref(connection);
        if (result < 0)
        {
            recordSecurityError(SecurityError::driver_error, result);
            return false;
        }
        recordSecurityError(SecurityError::none);
        return true;
    }

    bool SecurityManager::confirmPasskey(bool accept) noexcept
    {
        if (!requireThreadContext())
        {
            return false;
        }
        struct bt_conn *connection = takePending(PendingResponse::passkey_confirmation);
        if (connection == nullptr)
        {
            recordSecurityError(SecurityError::invalid_state, -EALREADY);
            return false;
        }
        const int result =
            accept ? bt_conn_auth_passkey_confirm(connection) : bt_conn_auth_cancel(connection);
        bt_conn_unref(connection);
        if (result < 0)
        {
            recordSecurityError(SecurityError::driver_error, result);
            return false;
        }
        recordSecurityError(accept ? SecurityError::none : SecurityError::rejected,
                            accept ? 0 : -ECANCELED);
        return true;
    }

    bool SecurityManager::cancelPairing() noexcept
    {
        if (!requireThreadContext())
        {
            return false;
        }
        struct bt_conn *connection = nullptr;
        k_spinlock_key_t key = k_spin_lock(&pairingState().pending_lock);
        if (pairingState().pending_state.connection != nullptr)
        {
            connection = pairingState().pending_state.connection;
            pairingState().pending_state = {};
        }
        k_spin_unlock(&pairingState().pending_lock, key);
        if (connection == nullptr)
        {
            recordSecurityError(SecurityError::invalid_state, -EALREADY);
            return false;
        }
        const int result = bt_conn_auth_cancel(connection);
        bt_conn_unref(connection);
        if (result < 0)
        {
            recordSecurityError(SecurityError::driver_error, result);
            return false;
        }
        recordSecurityError(SecurityError::none);
        return true;
    }

} // namespace nucode::ble
#endif
