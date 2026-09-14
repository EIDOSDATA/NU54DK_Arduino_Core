/** @file @brief boot bond snapshot·검증·삭제 rollback입니다.
 * SPDX-License-Identifier: MIT
 */
#if !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE)
#include "SecurityInternal.h"
namespace nucode::ble::internal::security
{
    namespace
    {
        BondStorage state{};
    }
    BondStorage &bondStorage() noexcept
    {
        return state;
    }
    namespace
    {
        bt_addr_le_t startup_bonds[CONFIG_BT_MAX_PAIRED] = {};
    }
    /** @brief 공개 가능한 현재 bond 상태 snapshot을 반환합니다. */
    BondState currentBondState() noexcept
    {
        return static_cast<BondState>(atomic_get(&bondStorage().bond_state_value));
    }

    /** @brief exact link의 bond 상태를 generation slot에서 반환합니다. */
    BondState currentBondState(struct bt_conn *connection) noexcept
    {
        if (connection == nullptr)
        {
            return BondState::none;
        }
        BondState result = BondState::none;
        k_spinlock_key_t key = k_spin_lock(&securityState().connection_lock);
        for (std::size_t index = 0U; index < maximum_security_links; ++index)
        {
            const SecurityLinkState &link = securityState().links[index];
            if (link.connection == connection)
            {
                result = link.bond_lifecycle.state;
                break;
            }
        }
        k_spin_unlock(&securityState().connection_lock, key);
        return result;
    }

    /** @brief 현재 peer의 bond 상태를 원자적으로 교체합니다. */
    void setBondLifecycle(const bt_addr_le_t *peer, BondState state,
                          bool paired_this_connection) noexcept
    {
        k_spinlock_key_t key = k_spin_lock(&bondStorage().bond_lock);
        bondStorage().bond_lifecycle = {};
        if (peer != nullptr)
        {
            bt_addr_le_copy(&bondStorage().bond_lifecycle.peer, peer);
            bondStorage().bond_lifecycle.peer_valid = true;
        }
        bondStorage().bond_lifecycle.state = state;
        bondStorage().bond_lifecycle.paired_this_connection = paired_this_connection;
        k_spin_unlock(&bondStorage().bond_lock, key);
        atomic_set(&bondStorage().bond_state_value, static_cast<atomic_val_t>(state));
    }

    /** @brief exact link의 bond 상태와 필요 시 legacy mirror를 교체합니다. */
    void setBondLifecycle(struct bt_conn *connection, const bt_addr_le_t *peer, BondState state,
                          bool paired_this_connection) noexcept
    {
        bool found = false;
        bool legacy = false;
        k_spinlock_key_t key = k_spin_lock(&securityState().connection_lock);
        for (std::size_t index = 0U; index < maximum_security_links; ++index)
        {
            SecurityLinkState &link = securityState().links[index];
            if (link.connection != connection)
            {
                continue;
            }
            link.bond_lifecycle = {};
            if (peer != nullptr)
            {
                bt_addr_le_copy(&link.bond_lifecycle.peer, peer);
                link.bond_lifecycle.peer_valid = true;
            }
            link.bond_lifecycle.state = state;
            link.bond_lifecycle.paired_this_connection = paired_this_connection;
            found = true;
            legacy = securityState().active_connection == connection;
            break;
        }
        k_spin_unlock(&securityState().connection_lock, key);
        if (found && legacy)
        {
            setBondLifecycle(peer, state, paired_this_connection);
        }
    }

    /** @brief 지정 peer와 현재 bond 후보가 같은지 확인합니다. */
    bool bondLifecycleMatches(const bt_addr_le_t *peer) noexcept
    {
        if (peer == nullptr)
        {
            return false;
        }
        bool matches = false;
        k_spinlock_key_t key = k_spin_lock(&bondStorage().bond_lock);
        matches = bondStorage().bond_lifecycle.peer_valid &&
                  bt_addr_le_eq(&bondStorage().bond_lifecycle.peer, peer);
        k_spin_unlock(&bondStorage().bond_lock, key);
        return matches;
    }

    /** @brief 지정 connection의 bond 후보와 peer가 같은지 확인합니다. */
    bool bondLifecycleMatches(struct bt_conn *connection, const bt_addr_le_t *peer) noexcept
    {
        if (connection == nullptr || peer == nullptr)
        {
            return false;
        }
        bool matches = false;
        k_spinlock_key_t key = k_spin_lock(&securityState().connection_lock);
        for (std::size_t index = 0U; index < maximum_security_links; ++index)
        {
            const SecurityLinkState &link = securityState().links[index];
            if (link.connection == connection)
            {
                matches = link.bond_lifecycle.peer_valid &&
                          bt_addr_le_eq(&link.bond_lifecycle.peer, peer);
                break;
            }
        }
        k_spin_unlock(&securityState().connection_lock, key);
        return matches;
    }

    /** @brief 오류 rollback에 사용할 bond 상태 snapshot을 복사합니다. */
    BondLifecycleState copyBondLifecycle() noexcept
    {
        BondLifecycleState snapshot = {};
        k_spinlock_key_t key = k_spin_lock(&bondStorage().bond_lock);
        snapshot = bondStorage().bond_lifecycle;
        k_spin_unlock(&bondStorage().bond_lock, key);
        return snapshot;
    }

    /** @brief exact link의 bond 상태 snapshot을 복사합니다. */
    BondLifecycleState copyBondLifecycle(struct bt_conn *connection) noexcept
    {
        BondLifecycleState snapshot = {};
        if (connection == nullptr)
        {
            return snapshot;
        }
        k_spinlock_key_t key = k_spin_lock(&securityState().connection_lock);
        for (std::size_t index = 0U; index < maximum_security_links; ++index)
        {
            const SecurityLinkState &link = securityState().links[index];
            if (link.connection == connection)
            {
                snapshot = link.bond_lifecycle;
                break;
            }
        }
        k_spin_unlock(&securityState().connection_lock, key);
        return snapshot;
    }

    /** @brief 이전 bond 상태 snapshot을 복원합니다. */
    void restoreBondLifecycle(const BondLifecycleState &snapshot) noexcept
    {
        setBondLifecycle(snapshot.peer_valid ? &snapshot.peer : nullptr, snapshot.state,
                         snapshot.paired_this_connection);
    }

    /** @brief boot 때 로드된 bond 목록에 peer가 있었는지 확인합니다. */
    bool isStartupBond(const bt_addr_le_t *peer) noexcept
    {
        if (peer == nullptr)
        {
            return false;
        }
        bool found = false;
        k_spinlock_key_t key = k_spin_lock(&bondStorage().startup_bond_lock);
        for (std::size_t index = 0U; index < bondStorage().startup_bond_count; ++index)
        {
            if (bt_addr_le_eq(&startup_bonds[index], peer))
            {
                found = true;
                break;
            }
        }
        k_spin_unlock(&bondStorage().startup_bond_lock, key);
        return found;
    }

    /** @brief 실제 삭제 callback을 받은 peer를 boot bond snapshot에서 제거합니다. */
    void removeStartupBond(const bt_addr_le_t *peer) noexcept
    {
        if (peer == nullptr)
        {
            return;
        }
        k_spinlock_key_t key = k_spin_lock(&bondStorage().startup_bond_lock);
        for (std::size_t index = 0U; index < bondStorage().startup_bond_count; ++index)
        {
            if (!bt_addr_le_eq(&startup_bonds[index], peer))
            {
                continue;
            }
            for (std::size_t move = index + 1U; move < bondStorage().startup_bond_count; ++move)
            {
                bt_addr_le_copy(&startup_bonds[move - 1U], &startup_bonds[move]);
            }
            --bondStorage().startup_bond_count;
            break;
        }
        k_spin_unlock(&bondStorage().startup_bond_lock, key);
    }

    /** @brief L2 이상으로 확인된 저장 bond 후보를 검증 완료 상태로 승격합니다. */
    void verifySecureBond(struct bt_conn *connection, bt_security_t level) noexcept
    {
        if (connection == nullptr || level < BT_SECURITY_L2)
        {
            return;
        }
        const bt_addr_le_t *const peer = bt_conn_get_dst(connection);
        if (bondLifecycleMatches(connection, peer) &&
            currentBondState(connection) == BondState::restored_candidate)
        {
            setBondLifecycle(connection, peer, BondState::verified, false);
            setLinkPaired(connection, true);
            queueEvent(makeEvent(SecurityEvent::bond_verified, connection));
        }
        else if (currentBondState(connection) != BondState::removal_requested)
        {
            setLinkPaired(connection, true);
        }
    }

    /** @brief 첫 연결에서 boot 시작 bond 목록을 최초 한 번만 고정합니다. */
    void captureStartupBonds() noexcept
    {
        if (!atomic_cas(&bondStorage().startup_bond_snapshot_ready, 0, 1))
        {
            return;
        }

        struct Snapshot
        {
            bt_addr_le_t bonds[ARRAY_SIZE(startup_bonds)] = {};
            std::size_t count = 0U;
        } snapshot;
        if (nucode::ble::internal::settingsReady())
        {
            bt_foreach_bond(
                BT_ID_DEFAULT,
                [](const struct bt_bond_info *information, void *context)
                {
                    Snapshot *output = static_cast<Snapshot *>(context);
                    if (information != nullptr && output != nullptr &&
                        output->count < ARRAY_SIZE(output->bonds))
                    {
                        bt_addr_le_copy(&output->bonds[output->count], &information->addr);
                        ++output->count;
                    }
                },
                &snapshot);
        }

        k_spinlock_key_t key = k_spin_lock(&bondStorage().startup_bond_lock);
        bondStorage().startup_bond_count = snapshot.count;
        for (std::size_t index = 0U; index < snapshot.count; ++index)
        {
            bt_addr_le_copy(&startup_bonds[index], &snapshot.bonds[index]);
        }
        k_spin_unlock(&bondStorage().startup_bond_lock, key);
    }

} // namespace nucode::ble::internal::security
namespace nucode::ble
{
    using namespace internal::security;
    std::size_t SecurityManager::bondCount() const noexcept
    {
        std::size_t count = 0U;
        bt_foreach_bond(
            BT_ID_DEFAULT,
            [](const struct bt_bond_info *information, void *context)
            {
                ARG_UNUSED(information);
                std::size_t *value = static_cast<std::size_t *>(context);
                if (value != nullptr)
                {
                    ++(*value);
                }
            },
            &count);
        return count;
    }

    std::size_t SecurityManager::copyBonds(PeerAddress *buffer, std::size_t capacity) const noexcept
    {
        if (buffer == nullptr || capacity == 0U)
        {
            return 0U;
        }
        struct Context
        {
            PeerAddress *buffer;
            std::size_t capacity;
            std::size_t count;
        } context = {buffer, capacity, 0U};
        bt_foreach_bond(
            BT_ID_DEFAULT,
            [](const struct bt_bond_info *information, void *opaque)
            {
                Context *output = static_cast<Context *>(opaque);
                if (output != nullptr && output->count < output->capacity)
                {
                    output->buffer[output->count++] = publicAddress(&information->addr);
                }
            },
            &context);
        return context.count;
    }

    bool SecurityManager::eraseBond(const PeerAddress &peer) noexcept
    {
        if (!requireThreadContext())
        {
            return false;
        }
        const bt_addr_le_t address = nativeAddress(peer);
        const BondLifecycleState previous = copyBondLifecycle();
        struct bt_conn *connection = referenceActiveConnection();
        const BondLifecycleState link_previous = copyBondLifecycle(connection);
        if (bondLifecycleMatches(&address))
        {
            setBondLifecycle(&address, BondState::removal_requested, false);
        }
        if (connection != nullptr && bondLifecycleMatches(connection, &address))
        {
            setBondLifecycle(connection, &address, BondState::removal_requested, false);
        }
        const int result = bt_unpair(BT_ID_DEFAULT, &address);
        if (result < 0)
        {
            restoreBondLifecycle(previous);
            if (connection != nullptr)
            {
                setBondLifecycle(connection,
                                 link_previous.peer_valid ? &link_previous.peer : nullptr,
                                 link_previous.state, link_previous.paired_this_connection);
            }
            if (connection != nullptr)
            {
                bt_conn_unref(connection);
            }
            recordSecurityError(SecurityError::driver_error, result);
            return false;
        }
        if (connection != nullptr)
        {
            bt_conn_unref(connection);
        }
        queueEvent(makePeerEvent(SecurityEvent::bond_removal_requested, &address,
                                 BondState::removal_requested));
        recordSecurityError(SecurityError::none);
        return true;
    }

    bool SecurityManager::eraseAllBonds() noexcept
    {
        if (!requireThreadContext())
        {
            return false;
        }
        const BondLifecycleState previous = copyBondLifecycle();
        struct bt_conn *connection = referenceActiveConnection();
        const BondLifecycleState link_previous = copyBondLifecycle(connection);
        setBondLifecycle(previous.peer_valid ? &previous.peer : nullptr,
                         BondState::removal_requested, false);
        if (connection != nullptr)
        {
            setBondLifecycle(connection,
                             link_previous.peer_valid ? &link_previous.peer : nullptr,
                             BondState::removal_requested, false);
        }
        const int result = bt_unpair(BT_ID_DEFAULT, BT_ADDR_LE_ANY);
        if (result < 0)
        {
            restoreBondLifecycle(previous);
            if (connection != nullptr)
            {
                setBondLifecycle(connection,
                                 link_previous.peer_valid ? &link_previous.peer : nullptr,
                                 link_previous.state, link_previous.paired_this_connection);
                bt_conn_unref(connection);
            }
            recordSecurityError(SecurityError::driver_error, result);
            return false;
        }
        if (connection != nullptr)
        {
            bt_conn_unref(connection);
        }
        queueEvent(makePeerEvent(SecurityEvent::all_bonds_removal_requested, nullptr,
                                 BondState::removal_requested));
        recordSecurityError(SecurityError::none);
        return true;
    }

} // namespace nucode::ble
#endif
