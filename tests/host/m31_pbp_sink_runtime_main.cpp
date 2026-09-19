/**
 * @file m31_pbp_sink_runtime_main.cpp
 * @brief 실제 PBP sink backend의 BASE 선택과 teardown 경계를 실행합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#define private public
#include "../../libraries/NUCODE_BLE_Audio/src/NUCODE_BLE_Audio_BroadcastSink.cpp"
#undef private

#include <atomic>
#include <cassert>
#include <chrono>
#include <thread>

using namespace nucode::ble::audio;

namespace
{
    bt_bap_broadcast_sink shared_sink = {};

    /** @brief 16 kHz Standard Quality codec 설정을 만듭니다. */
    bt_audio_codec_cfg standardCodec()
    {
        return {
            .id = BT_HCI_CODING_FORMAT_LC3,
            .frequency = BT_AUDIO_CODEC_CFG_FREQ_16KHZ,
            .duration = BT_AUDIO_CODEC_CFG_DURATION_10,
            .octets = 40,
            .blocks = 1,
            .location = BT_AUDIO_LOCATION_FRONT_LEFT,
        };
    }

    /** @brief sink callback 시험용 새 세대를 같은 주소에 결합합니다. */
    void beginGeneration()
    {
        sink_state = {};
        atomic_set(&sink_state.active, 1);
        sink_state.sink = &shared_sink;
        atomic_ptr_set(&sink_state.callback_sink, &shared_sink);
    }

    /** @brief malformed BASE와 multi-BIS codec 선택을 실제 callback으로 검사합니다. */
    void testBaseSelection()
    {
        bt_bap_base malformed_size = {
            .encoded_size = 8,
        };
        beginGeneration();
        baseReceived(&shared_sink, &malformed_size, 4U);
        assert(atomic_get(&sink_state.error) == -EBADMSG);

        const std::uint8_t override_frequency[] = {2U, 1U,
                                                    BT_AUDIO_CODEC_CFG_FREQ_16KHZ};
        bt_audio_codec_cfg unsupported = standardCodec();
        unsupported.frequency = 9;
        bt_bap_base multi = {
            .encoded_size = 12,
            .subgroups = {
                {
                    .codec = unsupported,
                    .bis = {{.index = 1U}},
                },
                {
                    .codec = unsupported,
                    .bis = {{.index = 3U,
                             .data = override_frequency,
                             .data_len = sizeof(override_frequency)}},
                },
            },
        };
        beginGeneration();
        baseReceived(&shared_sink, &multi, 12U);
        assert(atomic_get(&sink_state.error) == 0);
        assert(atomic_get(&sink_state.base_received) == 1);
        assert(static_cast<std::uint32_t>(atomic_get(&sink_state.selected_bis)) ==
               BT_ISO_BIS_INDEX_BIT(3U));

        const std::uint8_t malformed_ltv[] = {3U, 1U, 3U};
        bt_bap_base malformed_bis = {
            .encoded_size = 3,
            .subgroups = {{
                .codec = standardCodec(),
                .bis = {{.index = 1U,
                         .data = malformed_ltv,
                         .data_len = sizeof(malformed_ltv)}},
            }},
        };
        beginGeneration();
        baseReceived(&shared_sink, &malformed_bis, 3U);
        assert(atomic_get(&sink_state.base_received) == 0);
        assert(atomic_get(&sink_state.error) == -EBADMSG);
    }

    /** @brief 암호화 불일치, wrong-code와 PA sync-loss 오류를 검사합니다. */
    void testRecoveryErrors()
    {
        beginGeneration();
        sink_state.public_broadcast = true;
        atomic_set(&sink_state.advertised_encrypted, 1);
        atomic_set(&sink_state.has_broadcast_code, 1);
        const bt_iso_biginfo clear_biginfo = {
            .encryption = false,
        };
        sinkSyncable(&shared_sink, &clear_biginfo);
        assert(atomic_get(&sink_state.error) == -EBADMSG);

        beginGeneration();
        atomic_set(&sink_state.sync_requested, 1);
        atomic_set(&sink_state.streaming, 1);
        constexpr std::uint8_t wrong_code_reason = 0x3dU;
        sinkStopped(&shared_sink, wrong_code_reason);
        assert(atomic_get(&sink_state.streaming) == 0);
        assert(atomic_get(&sink_state.error) == -wrong_code_reason);
        assert(releaseSink() == 0);
        assert(atomic_get(&sink_state.active) == 0);

        beginGeneration();
        bt_le_per_adv_sync periodic = {};
        atomic_ptr_set(&sink_state.periodic_sync, &periodic);
        atomic_set(&sink_state.streaming, 1);
        const bt_le_per_adv_sync_term_info lost = {
            .reason = 0x08U,
        };
        periodicTerminated(&periodic, &lost);
        assert(currentPeriodicSync() == nullptr);
        assert(atomic_get(&sink_state.streaming) == 0);
        assert(atomic_get(&sink_state.error) == -8);
        assert(releaseSink() == 0);
    }

    /** @brief BASE callback과 end 경쟁 뒤 같은 pointer 재사용의 ABA를 반복합니다. */
    void testCallbackDrainAndRebegin()
    {
        BroadcastSink public_sink;
        const PublicBroadcastFilter filter = {};
        bt_bap_base base = {
            .encoded_size = 4,
            .subgroups = {{
                .codec = standardCodec(),
                .bis = {{.index = 1U}},
            }},
        };

        for (unsigned int cycle = 0U; cycle < 8U; cycle++)
        {
            assert(public_sink.startPublic(filter, nullptr) == Error::none);
            sink_state.sink = &shared_sink;
            sink_state.sink_created = true;
            atomic_ptr_set(&sink_state.callback_sink, &shared_sink);
            {
                const std::lock_guard<std::mutex> lock(pbp_stub::base_mutex);
                pbp_stub::block_base = true;
                pbp_stub::base_entered = false;
                pbp_stub::release_base = false;
            }
            std::thread callback([&]()
            {
                baseReceived(&shared_sink, &base, 4U);
            });
            {
                std::unique_lock<std::mutex> lock(pbp_stub::base_mutex);
                pbp_stub::base_changed.wait(lock, []()
                {
                    return pbp_stub::base_entered;
                });
            }

            std::atomic<bool> teardown_done = false;
            int teardown_result = -1;
            std::thread teardown([&]()
            {
                teardown_result = static_cast<int>(public_sink.end());
                teardown_done.store(true);
            });
            std::this_thread::sleep_for(std::chrono::milliseconds(20));
            assert(!teardown_done.load());
            {
                const std::lock_guard<std::mutex> lock(pbp_stub::base_mutex);
                pbp_stub::release_base = true;
            }
            pbp_stub::base_changed.notify_all();
            callback.join();
            teardown.join();
            assert(teardown_result == static_cast<int>(Error::none));
            assert(atomic_get(&sink_state.selected_bis) == 0);
            assert(atomic_get(&sink_state.active) == 0);

            pbp_stub::block_base = false;
            assert(public_sink.startPublic(filter, nullptr) == Error::none);
            sink_state.sink = &shared_sink;
            sink_state.sink_created = true;
            atomic_ptr_set(&sink_state.callback_sink, &shared_sink);
            baseReceived(&shared_sink, &base, 4U);
            assert(atomic_get(&sink_state.base_received) == 1);
            assert(atomic_get(&sink_state.selected_bis) ==
                   static_cast<atomic_val_t>(BT_ISO_BIS_INDEX_BIT(1U)));
            assert(public_sink.end() == Error::none);
        }
    }
} // namespace

/** @brief 모든 실제 sink callback 회귀 시나리오를 실행합니다. */
int main()
{
    testBaseSelection();
    testRecoveryErrors();
    testCallbackDrainAndRebegin();
    return 0;
}
