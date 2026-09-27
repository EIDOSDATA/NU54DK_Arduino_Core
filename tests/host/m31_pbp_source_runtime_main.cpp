/**
 * @file m31_pbp_source_runtime_main.cpp
 * @brief 실제 PBP CAP source callback과 teardown 경계를 실행합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#define private public
#include "../../libraries/NUCODE_BLE_Audio/src/NUCODE_BLE_Audio_CapInitiator.cpp"
#undef private

#include <atomic>
#include <cassert>
#include <chrono>
#include <thread>

using namespace nucode::ble::audio;

namespace
{
    bt_cap_broadcast_source shared_source = {};

    /** @brief source callback 시험용 새 세대를 같은 주소에 결합합니다. */
    void beginGeneration(bool with_source)
    {
        cap_source_state = {};
        atomic_set(&cap_source_state.active, 1);
        if (with_source)
        {
            cap_source_state.source = &shared_source;
            atomic_ptr_set(&cap_source_state.callback_source, &shared_source);
            atomic_set(&cap_source_state.source_started, 1);
        }
    }

    /** @brief 예상하지 않은 BIS/source 중단이 recovery 오류를 남기는지 검사합니다. */
    void testUnexpectedStops()
    {
        beginGeneration(true);
        atomic_set(&cap_source_state.streaming, 1);
        constexpr std::uint8_t stream_reason = 0x08U;
        streamStopped(&cap_source_state.stream.bap_stream, stream_reason);
        assert(atomic_get(&cap_source_state.streaming) == 0);
        assert(atomic_get(&cap_source_state.error) == -stream_reason);

        atomic_set(&cap_source_state.error, 0);
        constexpr std::uint8_t source_reason = 0x3eU;
        broadcastStopped(&shared_source, source_reason);
        assert(atomic_get(&cap_source_state.source_started) == 0);
        assert(atomic_get(&cap_source_state.error) == -source_reason);
        assert(releaseCapSource() == 0);
        assert(cap_source_state.source == nullptr);
        assert(atomic_get(&cap_source_state.active) == 0);
    }

    /** @brief callback/end 경쟁 뒤 같은 stream pointer의 ABA 재사용을 반복합니다. */
    void testCallbackDrainAndRebegin()
    {
        CapInitiator public_source;
        const PublicBroadcastSourceConfig config = {};
        for (unsigned int cycle = 0U; cycle < 8U; cycle++)
        {
            assert(public_source.startPublic(config, nullptr) == Error::none);
            {
                const std::lock_guard<std::mutex> lock(pbp_stub::atomic_mutex);
                pbp_stub::blocked_atomic = &cap_source_state.active;
                pbp_stub::atomic_entered = false;
                pbp_stub::release_atomic = false;
            }
            std::thread callback([]()
            {
                streamStarted(&cap_source_state.stream.bap_stream);
            });
            {
                std::unique_lock<std::mutex> lock(pbp_stub::atomic_mutex);
                pbp_stub::atomic_changed.wait(lock, []()
                {
                    return pbp_stub::atomic_entered;
                });
            }

            std::atomic<bool> teardown_done = false;
            int teardown_result = -1;
            std::thread teardown([&]()
            {
                teardown_result = static_cast<int>(public_source.end());
                teardown_done.store(true);
            });
            std::this_thread::sleep_for(std::chrono::milliseconds(20));
            assert(!teardown_done.load());
            {
                const std::lock_guard<std::mutex> lock(pbp_stub::atomic_mutex);
                pbp_stub::release_atomic = true;
            }
            pbp_stub::atomic_changed.notify_all();
            callback.join();
            teardown.join();
            assert(teardown_result == static_cast<int>(Error::none));
            assert(atomic_get(&cap_source_state.streaming) == 0);
            assert(atomic_get(&cap_source_state.active) == 0);

            pbp_stub::blocked_atomic = nullptr;
            assert(public_source.startPublic(config, nullptr) == Error::none);
            streamStarted(&cap_source_state.stream.bap_stream);
            assert(atomic_get(&cap_source_state.streaming) == 1);
            assert(public_source.end() == Error::none);
        }
    }
} // namespace

/** @brief 모든 실제 CAP source callback 회귀 시나리오를 실행합니다. */
int main()
{
    testUnexpectedStops();
    testCallbackDrainAndRebegin();
    return 0;
}
