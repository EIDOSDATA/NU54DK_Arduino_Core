/**
 * @file m31_csip_member_lifecycle_main.cpp
 * @brief CSIP Member lease, 파괴 격리와 연결 세대 승인을 실행 검증합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE.h>
#include <NUCODE_BLE_Audio.h>
#include <internal/NUCODE_BLE_Internal.h>
#include <zephyr/bluetooth/audio/csip.h>

#include <atomic>
#include <cassert>
#include <cerrno>
#include <condition_variable>
#include <cstdint>
#include <mutex>
#include <thread>

namespace
{
    bt_csip_set_member_svc_inst native_instance{};
    bt_csip_set_member_cb *registered_callbacks = nullptr;
    bt_csip_set_member_set_info native_information = {
        {}, 2U, 1U, true, false,
    };
    std::atomic<unsigned> register_calls{0U};
    std::atomic<unsigned> unregister_calls{0U};
    std::atomic<unsigned> setter_calls{0U};
    std::atomic<bool> block_rsi{false};
    std::atomic<bool> rsi_entered{false};
    int unregister_error = 0;
    std::mutex rsi_mutex;
    std::condition_variable rsi_condition;
    nucode::ble::BLEConnectionHandle active_handle;
    bt_conn *active_connection = &mock_connections[0];
    nucode::ble::BLEConnectionHandle coordinator_handles[2];
    bool coordinator_connections_active[2] = {false, false};
    bt_csip_set_coordinator_set_member coordinator_members[2] = {};
    bt_csip_set_coordinator_cb *coordinator_callbacks = nullptr;
    bt_csip_set_coordinator_ordered_access_t coordinator_ordered_predicate = nullptr;
    bt_csip_set_coordinator_set_info coordinator_ordered_info = {};
    bt_csip_set_coordinator_set_member *coordinator_ordered_members[2] = {};
    std::uint8_t coordinator_ordered_count = 0U;
    std::atomic<unsigned> coordinator_ordered_calls{0U};
    std::atomic<unsigned> coordinator_lock_calls{0U};
    std::atomic<unsigned> coordinator_release_calls{0U};
    int coordinator_release_error = 0;
}

nucode::ble::Connection BLEConnection;

namespace nucode::ble::internal
{
    /** @brief 시험에서 서로 다른 공개 연결 세대를 만듭니다. */
    struct BLEConnectionHandleAccess
    {
        static constexpr BLEConnectionHandle make(std::size_t slot,
                                                  std::uint32_t generation) noexcept
        {
            return BLEConnectionHandle((static_cast<std::uint64_t>(generation) << 8U) |
                                       static_cast<std::uint64_t>(slot + 1U));
        }
    };

    bool stackReady() noexcept
    {
        return true;
    }

    void recordError(BLEError, int, bool) noexcept
    {
    }

    bt_conn *referenceConnection(BLEConnectionHandle connection) noexcept
    {
        if (active_connection != nullptr && connection == active_handle)
        {
            return bt_conn_ref(active_connection);
        }
        for (std::size_t index = 0U; index < 2U; ++index)
        {
            if (coordinator_connections_active[index] &&
                connection == coordinator_handles[index])
            {
                return bt_conn_ref(&mock_connections[index + 1U]);
            }
        }
        return nullptr;
    }

    BLEConnectionHandle handleForActiveConnection(bt_conn *connection) noexcept
    {
        if (connection == active_connection)
        {
            return active_handle;
        }
        for (std::size_t index = 0U; index < 2U; ++index)
        {
            if (coordinator_connections_active[index] &&
                connection == &mock_connections[index + 1U])
            {
                return coordinator_handles[index];
            }
        }
        return BLEConnectionHandle{};
    }
} // namespace nucode::ble::internal

namespace nucode::ble
{
    bool Connection::connected(BLEConnectionHandle connection) const noexcept
    {
        for (std::size_t index = 0U; index < 2U; ++index)
        {
            if (coordinator_connections_active[index] &&
                coordinator_handles[index] == connection)
            {
                return true;
            }
        }
        return connection == active_handle && active_connection != nullptr;
    }
} // namespace nucode::ble

int bt_csip_set_member_register(const bt_csip_set_member_register_param *parameters,
                                bt_csip_set_member_svc_inst **instance)
{
    ++register_calls;
    registered_callbacks = parameters->cb;
    native_information.set_size = parameters->set_size;
    native_information.rank = parameters->rank;
    native_information.lockable = parameters->lockable;
    *instance = &native_instance;
    return 0;
}

int bt_csip_set_member_unregister(bt_csip_set_member_svc_inst *instance)
{
    assert(instance == &native_instance);
    ++unregister_calls;
    return unregister_error;
}

int bt_csip_set_member_generate_rsi(bt_csip_set_member_svc_inst *instance,
                                    std::uint8_t rsi[BT_CSIP_RSI_SIZE])
{
    assert(instance == &native_instance);
    rsi_entered = true;
    std::unique_lock<std::mutex> lock(rsi_mutex);
    rsi_condition.notify_all();
    rsi_condition.wait(lock, [] { return !block_rsi.load(); });
    rsi[0] = 1U;
    return 0;
}

int bt_csip_set_member_sirk(bt_csip_set_member_svc_inst *, const std::uint8_t *)
{
    return 0;
}

int bt_csip_set_member_set_size_and_rank(bt_csip_set_member_svc_inst *, std::uint8_t size,
                                         std::uint8_t rank)
{
    if ((!native_information.lockable && rank != 0U) ||
        (native_information.lockable && (rank == 0U || rank > size)))
    {
        return -EINVAL;
    }
    if (native_information.set_size == size)
    {
        return -EALREADY;
    }
    ++setter_calls;
    native_information.set_size = size;
    native_information.rank = native_information.lockable ? rank : 0U;
    return 0;
}

int bt_csip_set_member_get_info(const bt_csip_set_member_svc_inst *,
                                bt_csip_set_member_set_info *information)
{
    *information = native_information;
    return 0;
}

int bt_csip_set_member_lock(bt_csip_set_member_svc_inst *, bool, bool)
{
    return 0;
}

int bt_csip_set_coordinator_register_cb(bt_csip_set_coordinator_cb *callbacks)
{
    coordinator_callbacks = callbacks;
    return 0;
}

bool bt_csip_set_coordinator_is_set_member(const std::uint8_t *, const bt_data *)
{
    return true;
}

int bt_csip_set_coordinator_discover(bt_conn *)
{
    return 0;
}

bt_csip_set_coordinator_set_member *
bt_csip_set_coordinator_set_member_by_conn(const bt_conn *connection)
{
    for (std::size_t index = 0U; index < 2U; ++index)
    {
        if (coordinator_connections_active[index] &&
            connection == &mock_connections[index + 1U])
        {
            return &coordinator_members[index];
        }
    }
    return nullptr;
}

int bt_csip_set_coordinator_ordered_access(
    const bt_csip_set_coordinator_set_member *members[], std::uint8_t count,
    const bt_csip_set_coordinator_set_info *set_info,
    bt_csip_set_coordinator_ordered_access_t predicate)
{
    ++coordinator_ordered_calls;
    coordinator_ordered_info = *set_info;
    coordinator_ordered_count = count;
    coordinator_ordered_predicate = predicate;
    for (std::size_t index = 0U; index < count; ++index)
    {
        coordinator_ordered_members[index] =
            const_cast<bt_csip_set_coordinator_set_member *>(members[index]);
    }
    if (count == 2U && coordinator_ordered_members[0]->insts[0].info.rank >
                           coordinator_ordered_members[1]->insts[0].info.rank)
    {
        bt_csip_set_coordinator_set_member *const first = coordinator_ordered_members[0];
        coordinator_ordered_members[0] = coordinator_ordered_members[1];
        coordinator_ordered_members[1] = first;
    }
    return 0;
}

int bt_csip_set_coordinator_lock(const bt_csip_set_coordinator_set_member *[], std::uint8_t,
                                 const bt_csip_set_coordinator_set_info *)
{
    ++coordinator_lock_calls;
    return 0;
}

int bt_csip_set_coordinator_release(const bt_csip_set_coordinator_set_member *[], std::uint8_t,
                                    const bt_csip_set_coordinator_set_info *)
{
    ++coordinator_release_calls;
    return coordinator_release_error;
}

int main()
{
    using namespace nucode::ble;
    using namespace nucode::ble::audio;
    using AudioError = nucode::ble::audio::Error;

    CsipMemberConfig configuration{};
    configuration.set_size = 2U;
    configuration.rank = 1U;
    configuration.lockable = true;

    CsipSetMember member;
    assert(member.begin(configuration) == AudioError::none);
    block_rsi = true;
    std::uint8_t rsi[6] = {};
    std::thread caller([&] { assert(member.generateRsi(rsi) == AudioError::none); });
    {
        std::unique_lock<std::mutex> lock(rsi_mutex);
        rsi_condition.wait(lock, [] { return rsi_entered.load(); });
    }
    std::atomic<bool> end_finished{false};
    std::thread ending([&] {
        assert(member.end() == AudioError::none);
        end_finished = true;
    });
    std::this_thread::yield();
    assert(unregister_calls == 0U);
    assert(!end_finished);
    block_rsi = false;
    rsi_condition.notify_all();
    caller.join();
    ending.join();
    assert(unregister_calls == 1U);

    unregister_error = -EBUSY;
    {
        CsipSetMember abandoned;
        assert(abandoned.begin(configuration) == AudioError::none);
    }
    assert(unregister_calls == 2U);
    unregister_error = 0;
    CsipSetMember replacement;
    assert(replacement.begin(configuration) == AudioError::none);
    assert(unregister_calls == 3U);

    native_information.set_size = 2U;
    native_information.rank = 1U;
    assert(replacement.setSizeAndRank(2U, 2U) == AudioError::unsupported);
    assert(setter_calls == 0U);
    assert(replacement.setSizeAndRank(3U, 2U) == AudioError::none);
    assert(setter_calls == 1U);

    active_connection->security = BT_SECURITY_L2;
    active_handle = internal::BLEConnectionHandleAccess::make(0U, 1U);
    assert(replacement.authorizeSirkRead(active_handle) == AudioError::none);
    assert(registered_callbacks->sirk_read_req(active_connection, &native_instance) ==
           BT_CSIP_READ_SIRK_REQ_RSP_ACCEPT_ENC);
    mock_bond_exists = false;
    assert(registered_callbacks->sirk_read_req(active_connection, &native_instance) ==
           BT_CSIP_READ_SIRK_REQ_RSP_REJECT);
    mock_bond_exists = true;
    active_handle = internal::BLEConnectionHandleAccess::make(0U, 2U);
    assert(registered_callbacks->sirk_read_req(active_connection, &native_instance) ==
           BT_CSIP_READ_SIRK_REQ_RSP_REJECT);
    const BLEConnectionHandle disconnected =
        internal::BLEConnectionHandleAccess::make(0U, 1U);
    assert(replacement.authorizeSirkRead(disconnected, false) == AudioError::none);
    assert(replacement.end() == AudioError::none);

    configuration.lockable = false;
    configuration.rank = 0U;
    CsipSetMember non_lockable;
    assert(non_lockable.begin(configuration) == AudioError::none);
    CsipMemberInfo non_lockable_information{};
    assert(non_lockable.info(non_lockable_information) == AudioError::none);
    assert(!non_lockable_information.lockable && non_lockable_information.rank == 0U);
    assert(non_lockable.setSizeAndRank(3U, 0U) == AudioError::none);
    assert(non_lockable.setSizeAndRank(4U, 1U) == AudioError::invalid_argument);
    assert(non_lockable.end() == AudioError::none);

    CsipSetKey coordinator_key{};
    for (std::size_t index = 0U; index < 2U; ++index)
    {
        coordinator_members[index].insts[0].info.set_size = 2U;
        coordinator_members[index].insts[0].info.rank =
            static_cast<std::uint8_t>(2U - index);
        coordinator_members[index].insts[0].info.lockable = true;
        coordinator_connections_active[index] = true;
        coordinator_handles[index] =
            internal::BLEConnectionHandleAccess::make(index, 10U);
    }
    CsipSetCoordinator coordinator;
    assert(coordinator.begin(coordinator_key, 2U) == AudioError::none);
    for (std::size_t index = 0U; index < 2U; ++index)
    {
        assert(coordinator.discover(coordinator_handles[index]) == AudioError::none);
        coordinator_callbacks->discover(&mock_connections[index + 1U],
                                        &coordinator_members[index], 0, 1U);
    }
    assert(coordinator.ready());
    assert(coordinator.prepareOrderedAccess() == AudioError::none);
    assert(coordinator_ordered_calls == 1U && coordinator_ordered_count == 2U);
    assert(coordinator_ordered_predicate != nullptr);
    bt_csip_set_coordinator_set_info wrong_set = coordinator_ordered_info;
    wrong_set.sirk[0] ^= 0x01U;
    assert(!coordinator_ordered_predicate(&wrong_set, coordinator_ordered_members, 2U));
    wrong_set = coordinator_ordered_info;
    ++wrong_set.set_size;
    assert(!coordinator_ordered_predicate(&wrong_set, coordinator_ordered_members, 2U));
    wrong_set = coordinator_ordered_info;
    wrong_set.rank = 1U;
    assert(!coordinator_ordered_predicate(&wrong_set, coordinator_ordered_members, 2U));
    wrong_set = coordinator_ordered_info;
    wrong_set.lockable = !wrong_set.lockable;
    assert(!coordinator_ordered_predicate(&wrong_set, coordinator_ordered_members, 2U));
    bt_csip_set_coordinator_set_member *duplicate_members[2] = {
        coordinator_ordered_members[0], coordinator_ordered_members[0],
    };
    assert(!coordinator_ordered_predicate(&coordinator_ordered_info,
                                          duplicate_members, 2U));
    assert(coordinator_ordered_predicate(&coordinator_ordered_info,
                                         coordinator_ordered_members, 2U));
    assert(coordinator.orderedMember(0U) == coordinator_handles[1]);
    assert(coordinator.orderedMember(1U) == coordinator_handles[0]);
    coordinator_callbacks->ordered_access(&wrong_set, 0, false, nullptr);
    assert(coordinator.stage() == CsipStage::operating);
    coordinator_callbacks->ordered_access(&coordinator_ordered_info, 0, false, nullptr);
    assert(coordinator.ready());
    coordinator_callbacks->ordered_access(&coordinator_ordered_info, -EIO, true,
                                          coordinator_ordered_members[0]);
    assert(coordinator.ready() && coordinator.lastError() == AudioError::none);
    assert(coordinator.lock() == AudioError::none);
    coordinator_connections_active[1] = false;
    coordinator.poll();
    assert(coordinator.memberCount() == 1U);
    coordinator_callbacks->lock_set(0);
    assert(!coordinator.locked());
    assert(coordinator_release_calls == 0U);
    mock_uptime_offset_ms += 36000U;
    coordinator_release_error = -EBUSY;
    coordinator.poll();
    assert(coordinator_release_calls == 1U);
    coordinator_release_error = 0;
    mock_uptime_offset_ms += 300U;
    coordinator.poll();
    assert(coordinator_release_calls == 2U);
    coordinator_callbacks->release_set(0);
    assert(coordinator.memberCount() == 1U && !coordinator.locked());

    coordinator_connections_active[1] = true;
    coordinator_handles[1] = internal::BLEConnectionHandleAccess::make(1U, 11U);
    assert(coordinator.discover(coordinator_handles[1]) == AudioError::none);
    coordinator_callbacks->discover(&mock_connections[2], &coordinator_members[1], 0, 1U);
    assert(coordinator.ready());
    assert(coordinator.lock() == AudioError::none);
    coordinator_callbacks->lock_set(0);
    assert(coordinator.locked());
    coordinator_callbacks->size_changed(&mock_connections[2],
                                        &coordinator_members[1].insts[0]);
    assert(coordinator.memberCount() == 1U);
    coordinator.poll();
    assert(coordinator_release_calls == 3U);
    coordinator_callbacks->release_set(0);

    coordinator_handles[1] = internal::BLEConnectionHandleAccess::make(1U, 12U);
    assert(coordinator.discover(coordinator_handles[1]) == AudioError::none);
    coordinator_callbacks->discover(&mock_connections[2], &coordinator_members[1], 0, 1U);
    assert(coordinator.lock() == AudioError::none);
    coordinator_callbacks->lock_set(0);
    assert(coordinator.locked());
    coordinator_callbacks->sirk_changed(&coordinator_members[1].insts[0]);
    assert(coordinator.memberCount() == 1U);
    coordinator.poll();
    assert(coordinator_release_calls == 4U);
    coordinator_callbacks->release_set(0);

    coordinator_handles[1] = internal::BLEConnectionHandleAccess::make(1U, 13U);
    assert(coordinator.discover(coordinator_handles[1]) == AudioError::none);
    coordinator_callbacks->discover(&mock_connections[2], &coordinator_members[1], 0, 1U);
    assert(coordinator.lock() == AudioError::none);
    mock_uptime_offset_ms += 16000U;
    coordinator.poll();
    coordinator_callbacks->lock_set(0);
    assert(!coordinator.locked());
    mock_uptime_offset_ms += 36000U;
    coordinator.poll();
    assert(coordinator_release_calls == 5U);
    coordinator_callbacks->release_set(0);
    assert(coordinator.ready());

    coordinator_connections_active[1] = false;
    coordinator.poll();
    assert(coordinator.memberCount() == 1U);
    coordinator_connections_active[1] = true;
    coordinator_handles[1] = internal::BLEConnectionHandleAccess::make(1U, 14U);
    assert(coordinator.discover(coordinator_handles[1]) == AudioError::none);
    coordinator_callbacks->discover(&mock_connections[2], &coordinator_members[1], 0, 1U);
    assert(coordinator.ready());
    assert(coordinator.end() == AudioError::none);
    assert(coordinator.begin(coordinator_key, 2U) == AudioError::none);
    coordinator_callbacks->ordered_access(&coordinator_ordered_info, -EIO, true,
                                          coordinator_ordered_members[0]);
    assert(coordinator.stage() == CsipStage::discovering);
    assert(coordinator.lastError() == AudioError::none);
    assert(coordinator.end() == AudioError::none);
    return 0;
}
