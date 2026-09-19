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
    std::atomic<unsigned> coordinator_lock_calls{0U};
    std::atomic<unsigned> coordinator_release_calls{0U};
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
    ++setter_calls;
    native_information.set_size = size;
    native_information.rank = rank;
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
    const bt_csip_set_coordinator_set_member *[], std::uint8_t,
    const bt_csip_set_coordinator_set_info *, bt_csip_set_coordinator_ordered_access_t)
{
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
    return 0;
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
    active_handle = internal::BLEConnectionHandleAccess::make(0U, 2U);
    assert(registered_callbacks->sirk_read_req(active_connection, &native_instance) ==
           BT_CSIP_READ_SIRK_REQ_RSP_REJECT);
    const BLEConnectionHandle disconnected =
        internal::BLEConnectionHandleAccess::make(0U, 1U);
    assert(replacement.authorizeSirkRead(disconnected, false) == AudioError::none);
    assert(replacement.end() == AudioError::none);

    CsipSetKey coordinator_key{};
    for (std::size_t index = 0U; index < 2U; ++index)
    {
        coordinator_members[index].insts[0].info.set_size = 2U;
        coordinator_members[index].insts[0].info.rank =
            static_cast<std::uint8_t>(index + 1U);
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
    assert(coordinator.lock() == AudioError::none);
    coordinator_connections_active[1] = false;
    coordinator.poll();
    assert(coordinator.memberCount() == 1U);
    coordinator_callbacks->lock_set(0);
    assert(!coordinator.locked());
    assert(coordinator.end() == AudioError::none);

    for (std::size_t index = 0U; index < 2U; ++index)
    {
        coordinator_connections_active[index] = true;
        coordinator_handles[index] =
            internal::BLEConnectionHandleAccess::make(index, 11U);
    }
    assert(coordinator.begin(coordinator_key, 2U) == AudioError::none);
    for (std::size_t index = 0U; index < 2U; ++index)
    {
        assert(coordinator.discover(coordinator_handles[index]) == AudioError::none);
        coordinator_callbacks->discover(&mock_connections[index + 1U],
                                        &coordinator_members[index], 0, 1U);
    }
    assert(coordinator.lock() == AudioError::busy);
    mock_uptime_offset_ms += 36000U;
    assert(coordinator.lock() == AudioError::none);
    assert(coordinator_lock_calls == 2U);
    coordinator_callbacks->lock_set(0);
    assert(coordinator.locked());
    assert(coordinator.release() == AudioError::none);
    assert(coordinator_release_calls == 1U);
    assert(coordinator.end() == AudioError::none);
    coordinator_callbacks->release_set(0);
    assert(coordinator.begin(coordinator_key, 2U) == AudioError::none);
    assert(coordinator.end() == AudioError::none);
    return 0;
}
