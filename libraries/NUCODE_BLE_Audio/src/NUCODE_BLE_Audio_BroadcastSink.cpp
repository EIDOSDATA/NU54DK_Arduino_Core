/**
 * @file NUCODE_BLE_Audio_BroadcastSink.cpp
 * @brief LC3 BAP broadcast sink 공개 API를 구현합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include "NUCODE_BLE_Audio.h"

#if !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE) && defined(CONFIG_BT_BAP_BROADCAST_SINK)

#include <NUCODE_BLE.h>

#include <zephyr/bluetooth/audio/bap.h>
#include <zephyr/bluetooth/audio/lc3.h>
#include <zephyr/bluetooth/audio/pacs.h>
#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/hci.h>
#include <zephyr/bluetooth/iso.h>
#include <zephyr/kernel.h>
#include <zephyr/net_buf.h>
#include <zephyr/sys/atomic.h>
#include <zephyr/sys/byteorder.h>

#include <errno.h>
#include <string.h>

namespace nucode::ble::audio
{
    namespace
    {
        constexpr std::size_t frame_octets = 40U;
        constexpr std::size_t maximum_broadcast_name = 31U;

        K_MSGQ_DEFINE(receive_queue, frame_octets, 8, 4);
        K_SEM_DEFINE(sink_stopped, 0, 1);

        /** @brief 한 Arduino 객체가 소유하는 broadcast sink 상태입니다. */
        struct SinkState
        {
            BroadcastSink *owner = nullptr;
            bt_bap_broadcast_sink *sink = nullptr;
            bt_le_per_adv_sync *periodic_sync = nullptr;
            bt_bap_stream stream = {};
            bt_addr_le_t broadcaster = {};
            char target_name[maximum_broadcast_name + 1U] = {};
            std::uint32_t broadcast_id = 0U;
            std::uint16_t periodic_interval = 0U;
            std::uint8_t sid = 0U;
            BroadcastCode broadcast_code = {};
            atomic_t found = 0;
            atomic_t periodic_synced = 0;
            atomic_t base_received = 0;
            atomic_t syncable = 0;
            atomic_t streaming = 0;
            atomic_t received = 0;
            atomic_t dropped = 0;
            atomic_t error = 0;
            BroadcastSinkStep cleanup_failure = BroadcastSinkStep::cleanup;
            bool scan_callback_registered = false;
            bool periodic_callback_registered = false;
            bool pacs_registered = false;
            bool capability_registered = false;
            bool scan_delegator_registered = false;
            bool scanning = false;
            bool sink_created = false;
            bool sync_requested = false;
            bool has_broadcast_code = false;
            bool encrypted = false;
        };

        SinkState sink_state;
        bool sink_callback_registered = false;

        constexpr bt_audio_context contexts = BT_AUDIO_CONTEXT_TYPE_MEDIA;
        const bt_audio_codec_cap codec_cap = BT_AUDIO_CODEC_CAP_LC3(
            BT_AUDIO_CODEC_CAP_FREQ_16KHZ, BT_AUDIO_CODEC_CAP_DURATION_10,
            BT_AUDIO_CODEC_CAP_CHAN_COUNT_SUPPORT(1), frame_octets, frame_octets, 1U,
            contexts);
        bt_pacs_cap pac_sink = {
            .codec_cap = &codec_cap,
        };
        bt_bap_scan_delegator_cb scan_delegator_callbacks = {};

        /** @brief 한 광고 packet에서 BAP announcement와 방송 이름을 수집합니다. */
        struct AdvertisementMatch
        {
            bool service = false;
            bool name = false;
            std::uint32_t broadcast_id = 0U;
        };

        /** @brief Service Data와 Broadcast Name AD element를 해석합니다. */
        bool inspectData(bt_data *data, void *user_data)
        {
            auto *match = static_cast<AdvertisementMatch *>(user_data);
            if ((data->type == BT_DATA_SVC_DATA16) &&
                (data->data_len >= BT_UUID_SIZE_16 + BT_AUDIO_BROADCAST_ID_SIZE) &&
                (sys_get_le16(data->data) == BT_UUID_BROADCAST_AUDIO_VAL))
            {
                match->service = true;
                match->broadcast_id = sys_get_le24(data->data + BT_UUID_SIZE_16);
            }
            else if ((data->type == BT_DATA_BROADCAST_NAME) &&
                     (data->data_len == strlen(sink_state.target_name)) &&
                     (memcmp(data->data, sink_state.target_name, data->data_len) == 0))
            {
                match->name = true;
            }
            return true;
        }

        /** @brief 이름과 Broadcast Audio announcement가 함께 있는 source를 선택합니다. */
        void scanReceived(const bt_le_scan_recv_info *info, net_buf_simple *advertising_data)
        {
            if ((sink_state.owner == nullptr) || (atomic_get(&sink_state.found) != 0) ||
                (info->interval == 0U))
            {
                return;
            }

            AdvertisementMatch match;
            net_buf_simple copy;
            net_buf_simple_clone(advertising_data, &copy);
            bt_data_parse(&copy, inspectData, &match);
            if (!match.service || !match.name)
            {
                return;
            }
            if (atomic_cas(&sink_state.found, 0, 1))
            {
                bt_addr_le_copy(&sink_state.broadcaster, info->addr);
                sink_state.sid = info->sid;
                sink_state.periodic_interval = info->interval;
                sink_state.broadcast_id = match.broadcast_id;
            }
        }

        bt_le_scan_cb scan_callbacks = {
            .recv = scanReceived,
        };

        /** @brief periodic advertising 동기화 완료를 poll()에 전달합니다. */
        void periodicSynced(bt_le_per_adv_sync *sync,
                            bt_le_per_adv_sync_synced_info *info)
        {
            static_cast<void>(info);
            if ((sink_state.owner != nullptr) && (sync == sink_state.periodic_sync))
            {
                atomic_set(&sink_state.periodic_synced, 1);
            }
        }

        /** @brief 예상하지 않은 periodic sync 손실을 오류로 기록합니다. */
        void periodicTerminated(bt_le_per_adv_sync *sync,
                                const bt_le_per_adv_sync_term_info *info)
        {
            if (sync == sink_state.periodic_sync)
            {
                sink_state.periodic_sync = nullptr;
                atomic_set(&sink_state.periodic_synced, 0);
                atomic_set(&sink_state.streaming, 0);
                if ((sink_state.owner != nullptr) &&
                    (info->reason != BT_HCI_ERR_LOCALHOST_TERM_CONN))
                {
                    atomic_set(&sink_state.error, -ECONNRESET);
                }
            }
        }

        bt_le_per_adv_sync_cb periodic_callbacks = {
            .synced = periodicSynced,
            .term = periodicTerminated,
        };

        /** @brief BASE 수신을 BIS 동기화 조건으로 기록합니다. */
        void baseReceived(bt_bap_broadcast_sink *sink, const bt_bap_base *base,
                          std::size_t base_size)
        {
            static_cast<void>(base);
            static_cast<void>(base_size);
            if ((sink_state.owner != nullptr) && (sink == sink_state.sink))
            {
                atomic_set(&sink_state.base_received, 1);
            }
        }

        /** @brief BIGInfo와 제공된 Broadcast Code를 동기화 조건으로 확인합니다. */
        void sinkSyncable(bt_bap_broadcast_sink *sink, const bt_iso_biginfo *biginfo)
        {
            if ((sink_state.owner == nullptr) || (sink != sink_state.sink))
            {
                return;
            }
            sink_state.encrypted = biginfo->encryption;
            if (sink_state.encrypted && !sink_state.has_broadcast_code)
            {
                atomic_set(&sink_state.error, -EACCES);
                return;
            }
            atomic_set(&sink_state.syncable, 1);
        }

        /** @brief BIG 동기화 완료를 공개 streaming 상태로 표시합니다. */
        void sinkStarted(bt_bap_broadcast_sink *sink)
        {
            if ((sink_state.owner != nullptr) && (sink == sink_state.sink))
            {
                atomic_set(&sink_state.streaming, 1);
            }
        }

        /** @brief BIG 중단을 공개 상태와 종료 대기에 반영합니다. */
        void sinkStopped(bt_bap_broadcast_sink *sink, std::uint8_t reason)
        {
            if (sink == sink_state.sink)
            {
                atomic_set(&sink_state.streaming, 0);
                if ((sink_state.owner != nullptr) && sink_state.sync_requested &&
                    (reason != BT_HCI_ERR_LOCALHOST_TERM_CONN))
                {
                    atomic_set(&sink_state.error, -static_cast<int>(reason));
                }
                k_sem_give(&sink_stopped);
            }
        }

        bt_bap_broadcast_sink_cb sink_callbacks = {
            .base_recv = baseReceived,
            .syncable = sinkSyncable,
            .started = sinkStarted,
            .stopped = sinkStopped,
        };

        /** @brief 유효한 40-byte LC3 SDU를 고정 queue에 복사합니다. */
        void streamReceived(bt_bap_stream *stream, const bt_iso_recv_info *info,
                            net_buf *buffer)
        {
            if ((sink_state.owner == nullptr) || (stream != &sink_state.stream) ||
                ((info->flags & BT_ISO_FLAGS_VALID) == 0U) ||
                (buffer->len != frame_octets))
            {
                return;
            }
            atomic_inc(&sink_state.received);
            if (k_msgq_put(&receive_queue, buffer->data, K_NO_WAIT) != 0)
            {
                atomic_inc(&sink_state.dropped);
            }
        }

        /** @brief BIS 수신 시작을 공개 상태에 반영합니다. */
        void streamStarted(bt_bap_stream *stream)
        {
            if ((sink_state.owner != nullptr) && (stream == &sink_state.stream))
            {
                atomic_set(&sink_state.streaming, 1);
            }
        }

        /** @brief BIS 수신 중단 시 queue와 공개 상태를 정리합니다. */
        void streamStopped(bt_bap_stream *stream, std::uint8_t reason)
        {
            static_cast<void>(reason);
            if (stream == &sink_state.stream)
            {
                atomic_set(&sink_state.streaming, 0);
            }
        }

        bt_bap_stream_ops stream_callbacks = {
            .started = streamStarted,
            .stopped = streamStopped,
            .recv = streamReceived,
        };

        /** @brief 광고 주기에서 안전한 PA sync timeout을 계산합니다. */
        std::uint16_t periodicTimeout(std::uint16_t interval) noexcept
        {
            if (interval == 0U)
            {
                return 1000U;
            }
            const std::uint32_t timeout = (static_cast<std::uint32_t>(interval) * 125U * 5U) /
                                          1000U;
            return static_cast<std::uint16_t>(CLAMP(timeout, BT_GAP_PER_ADV_MIN_TIMEOUT,
                                                    BT_GAP_PER_ADV_MAX_TIMEOUT));
        }

        /** @brief 진행 중인 검색과 동기화 자원을 역순으로 반환합니다. */
        int releaseSink() noexcept
        {
            int first_error = 0;
            if (sink_state.scanning)
            {
                const int result = bt_le_scan_stop();
                if ((result != 0) && (result != -EALREADY))
                {
                    first_error = result;
                    sink_state.cleanup_failure = BroadcastSinkStep::cleanup_callbacks;
                }
                sink_state.scanning = false;
            }
            if (sink_state.sink_created && sink_state.sync_requested)
            {
                k_sem_reset(&sink_stopped);
                const int result = bt_bap_broadcast_sink_stop(sink_state.sink);
                if (result == 0)
                {
                    (void)k_sem_take(&sink_stopped, K_SECONDS(2));
                }
                else if ((result != -EALREADY) && (first_error == 0))
                {
                    first_error = result;
                    sink_state.cleanup_failure = BroadcastSinkStep::cleanup_sink_stop;
                }
            }
            if (sink_state.sink_created)
            {
                const int result = bt_bap_broadcast_sink_delete(sink_state.sink);
                if ((result != 0) && (first_error == 0))
                {
                    first_error = result;
                    sink_state.cleanup_failure = BroadcastSinkStep::cleanup_sink_delete;
                }
                sink_state.sink = nullptr;
                sink_state.sink_created = false;
            }
            if (sink_state.periodic_sync != nullptr)
            {
                const int result = bt_le_per_adv_sync_delete(sink_state.periodic_sync);
                if ((result != 0) && (first_error == 0))
                {
                    first_error = result;
                    sink_state.cleanup_failure = BroadcastSinkStep::cleanup_periodic_sync;
                }
                sink_state.periodic_sync = nullptr;
            }
            if (sink_state.scan_callback_registered)
            {
                bt_le_scan_cb_unregister(&scan_callbacks);
                sink_state.scan_callback_registered = false;
            }
            if (sink_state.periodic_callback_registered)
            {
                const int result = bt_le_per_adv_sync_cb_unregister(&periodic_callbacks);
                if ((result != 0) && (first_error == 0))
                {
                    first_error = result;
                    sink_state.cleanup_failure = BroadcastSinkStep::cleanup_callbacks;
                }
                sink_state.periodic_callback_registered = false;
            }
            if (sink_state.scan_delegator_registered)
            {
                const int result = bt_bap_scan_delegator_unregister();
                if ((result != 0) && (first_error == 0))
                {
                    first_error = result;
                    sink_state.cleanup_failure = BroadcastSinkStep::cleanup_scan_delegator;
                }
                sink_state.scan_delegator_registered = false;
            }
            if (sink_state.capability_registered)
            {
                const int result = bt_pacs_cap_unregister(BT_AUDIO_DIR_SINK, &pac_sink);
                if ((result != 0) && (first_error == 0))
                {
                    first_error = result;
                    sink_state.cleanup_failure = BroadcastSinkStep::cleanup_capability;
                }
                sink_state.capability_registered = false;
            }
            if (sink_state.pacs_registered)
            {
                const int result = bt_pacs_unregister();
                if ((result != 0) && (first_error == 0))
                {
                    first_error = result;
                    sink_state.cleanup_failure = BroadcastSinkStep::cleanup_pacs;
                }
                sink_state.pacs_registered = false;
            }
            atomic_set(&sink_state.streaming, 0);
            k_msgq_purge(&receive_queue);
            return first_error;
        }
    } // namespace

    /** @brief 마지막 공개 오류와 원본 stack 오류를 기록합니다. */
    Error BroadcastSink::record(Error error, int native_code) noexcept
    {
        last_error_ = error;
        native_code_ = native_code;
        return error;
    }

    /** @brief BAP broadcast source 검색과 callback 집합을 시작합니다. */
    Error BroadcastSink::begin(const char *broadcast_name) noexcept
    {
        return start(broadcast_name, nullptr);
    }

    /** @brief Broadcast Code가 필요한 source 검색을 시작합니다. */
    Error BroadcastSink::begin(const char *broadcast_name,
                               const BroadcastCode &broadcast_code) noexcept
    {
        return start(broadcast_name, broadcast_code);
    }

    /** @brief 선택한 code와 함께 검색·PACS·BASS 자원을 구성합니다. */
    Error BroadcastSink::start(const char *broadcast_name,
                               const std::uint8_t *broadcast_code) noexcept
    {
        if (started_)
        {
            return record(Error::already_started);
        }
        if (!BLEDevice.initialized())
        {
            return record(Error::not_ready);
        }
        if (sink_state.owner != nullptr)
        {
            return record(Error::busy);
        }
        if ((broadcast_name == nullptr) || (broadcast_name[0] == '\0') ||
            (strlen(broadcast_name) > maximum_broadcast_name))
        {
            return record(Error::invalid_argument);
        }

        sink_state = {};
        sink_state.owner = this;
        memcpy(sink_state.target_name, broadcast_name, strlen(broadcast_name) + 1U);
        if (broadcast_code != nullptr)
        {
            memcpy(sink_state.broadcast_code, broadcast_code,
                   sizeof(sink_state.broadcast_code));
            sink_state.has_broadcast_code = true;
        }
        memset(&sink_state.stream, 0, sizeof(sink_state.stream));
        bt_bap_stream_cb_register(&sink_state.stream, &stream_callbacks);
        k_msgq_purge(&receive_queue);
        k_sem_reset(&sink_stopped);

        const bt_pacs_register_param pacs_config = {
            .snk_pac = true,
            .snk_loc = true,
        };
        last_step_ = BroadcastSinkStep::pacs;
        int result = bt_pacs_register(&pacs_config);
        sink_state.pacs_registered = result == 0;
        if (result == 0)
        {
            last_step_ = BroadcastSinkStep::capability;
            result = bt_pacs_cap_register(BT_AUDIO_DIR_SINK, &pac_sink);
            sink_state.capability_registered = result == 0;
        }
        if (result == 0)
        {
            last_step_ = BroadcastSinkStep::location;
            result = bt_pacs_set_location(BT_AUDIO_DIR_SINK,
                                          BT_AUDIO_LOCATION_FRONT_LEFT);
        }
        if (result == 0)
        {
            last_step_ = BroadcastSinkStep::supported_contexts;
            result = bt_pacs_set_supported_contexts(BT_AUDIO_DIR_SINK, contexts);
        }
        if (result == 0)
        {
            last_step_ = BroadcastSinkStep::available_contexts;
            result = bt_pacs_set_available_contexts(BT_AUDIO_DIR_SINK, contexts);
        }
        if (result == 0)
        {
            last_step_ = BroadcastSinkStep::scan_delegator;
            result = bt_bap_scan_delegator_register(&scan_delegator_callbacks);
            sink_state.scan_delegator_registered = result == 0;
        }
        if ((result == 0) && !sink_callback_registered)
        {
            last_step_ = BroadcastSinkStep::callbacks;
            result = bt_bap_broadcast_sink_register_cb(&sink_callbacks);
            if (result == 0)
            {
                sink_callback_registered = true;
            }
        }
        if (result == 0)
        {
            last_step_ = BroadcastSinkStep::callbacks;
            result = bt_le_scan_cb_register(&scan_callbacks);
            sink_state.scan_callback_registered = result == 0;
        }
        if (result == 0)
        {
            last_step_ = BroadcastSinkStep::callbacks;
            result = bt_le_per_adv_sync_cb_register(&periodic_callbacks);
            sink_state.periodic_callback_registered = result == 0;
        }
        if (result == 0)
        {
            last_step_ = BroadcastSinkStep::scan;
            result = bt_le_scan_start(BT_LE_SCAN_ACTIVE, nullptr);
            sink_state.scanning = result == 0;
        }
        if (result != 0)
        {
            (void)releaseSink();
            sink_state.owner = nullptr;
            return record(Error::stack_error, result);
        }

        started_ = true;
        stage_ = BroadcastStage::scanning;
        return record(Error::none);
    }

    /** @brief 검색 결과를 PA/BASE/BIG/BIS 동기화 단계로 진행합니다. */
    void BroadcastSink::poll() noexcept
    {
        if (!started_ || (stage_ == BroadcastStage::failed))
        {
            return;
        }

        const int callback_error = atomic_get(&sink_state.error);
        if (callback_error != 0)
        {
            stage_ = BroadcastStage::failed;
            (void)record(Error::stack_error, callback_error);
            return;
        }

        if ((stage_ == BroadcastStage::scanning) &&
            (atomic_get(&sink_state.found) != 0))
        {
            if (sink_state.scanning)
            {
                const int scan_result = bt_le_scan_stop();
                if ((scan_result != 0) && (scan_result != -EALREADY))
                {
                    stage_ = BroadcastStage::failed;
                    (void)record(Error::stack_error, scan_result);
                    return;
                }
                sink_state.scanning = false;
            }

            const bt_le_per_adv_sync_param sync_param = {
                .addr = sink_state.broadcaster,
                .sid = sink_state.sid,
                .options = BT_LE_PER_ADV_SYNC_OPT_NONE,
                .skip = 5U,
                .timeout = periodicTimeout(sink_state.periodic_interval),
            };
            last_step_ = BroadcastSinkStep::periodic_sync;
            const int result = bt_le_per_adv_sync_create(&sync_param,
                                                         &sink_state.periodic_sync);
            if (result != 0)
            {
                stage_ = BroadcastStage::failed;
                (void)record(Error::stack_error, result);
                return;
            }
            stage_ = BroadcastStage::synchronizing;
        }

        if ((stage_ == BroadcastStage::synchronizing) &&
            (atomic_get(&sink_state.periodic_synced) != 0) &&
            !sink_state.sink_created)
        {
            last_step_ = BroadcastSinkStep::sink_create;
            const int result = bt_bap_broadcast_sink_create(sink_state.periodic_sync,
                                                            sink_state.broadcast_id,
                                                            &sink_state.sink);
            if (result != 0)
            {
                stage_ = BroadcastStage::failed;
                (void)record(Error::stack_error, result);
                return;
            }
            sink_state.sink_created = true;
        }

        if ((stage_ == BroadcastStage::synchronizing) && sink_state.sink_created &&
            !sink_state.sync_requested &&
            (atomic_get(&sink_state.base_received) != 0) &&
            (atomic_get(&sink_state.syncable) != 0))
        {
            bt_bap_stream *streams[] = {&sink_state.stream};
            last_step_ = BroadcastSinkStep::bis_sync;
            const std::uint8_t *broadcast_code =
                sink_state.encrypted ? sink_state.broadcast_code : nullptr;
            const int result = bt_bap_broadcast_sink_sync(
                sink_state.sink, BT_ISO_BIS_INDEX_BIT(1U), streams, broadcast_code);
            if (result != 0)
            {
                stage_ = BroadcastStage::failed;
                (void)record(Error::stack_error, result);
                return;
            }
            sink_state.sync_requested = true;
        }

        if ((stage_ == BroadcastStage::synchronizing) && streaming())
        {
            stage_ = BroadcastStage::streaming;
            (void)record(Error::none);
        }
    }

    /** @brief BIS, PA sync, 검색 callback을 중단하고 backend 소유권을 반환합니다. */
    Error BroadcastSink::end() noexcept
    {
        if (!started_)
        {
            return record(Error::not_started);
        }
        stage_ = BroadcastStage::stopping;
        last_step_ = BroadcastSinkStep::cleanup;
        const int result = releaseSink();
        sink_state.owner = nullptr;
        started_ = false;
        stage_ = BroadcastStage::idle;
        if (result != 0)
        {
            last_step_ = sink_state.cleanup_failure;
            return record(Error::stack_error, result);
        }
        return record(Error::none);
    }

    /** @brief callback이 확정한 BIS 수신 상태를 반환합니다. */
    bool BroadcastSink::streaming() const noexcept
    {
        return started_ && (atomic_get(&sink_state.streaming) != 0);
    }

    /** @brief queue의 LC3 frame 한 개를 Arduino 문맥으로 전달합니다. */
    bool BroadcastSink::readFrame(std::uint8_t (&frame)[40]) noexcept
    {
        return started_ && (k_msgq_get(&receive_queue, frame, K_NO_WAIT) == 0);
    }

    /** @brief 현재 비동기 단계를 반환합니다. */
    BroadcastStage BroadcastSink::stage() const noexcept
    {
        return stage_;
    }

    /** @brief 마지막 Host 요청 또는 오류 작업을 반환합니다. */
    BroadcastSinkStep BroadcastSink::lastStep() const noexcept
    {
        return last_step_;
    }

    /** @brief 유효한 BIS frame 수를 반환합니다. */
    std::uint32_t BroadcastSink::receivedFrames() const noexcept
    {
        return started_ ? static_cast<std::uint32_t>(atomic_get(&sink_state.received)) : 0U;
    }

    /** @brief queue 포화로 폐기한 BIS frame 수를 반환합니다. */
    std::uint32_t BroadcastSink::droppedFrames() const noexcept
    {
        return started_ ? static_cast<std::uint32_t>(atomic_get(&sink_state.dropped)) : 0U;
    }

    /** @brief 마지막 공개 오류를 반환합니다. */
    Error BroadcastSink::lastError() const noexcept
    {
        return last_error_;
    }

    /** @brief 마지막 callback 또는 stack 오류를 반환합니다. */
    int BroadcastSink::nativeCode() const noexcept
    {
        const int callback_error = atomic_get(&sink_state.error);
        return callback_error != 0 ? callback_error : native_code_;
    }
} // namespace nucode::ble::audio

#else

namespace nucode::ble::audio
{
    /** @brief broadcast sink 기능이 없는 image에서는 시작을 거부합니다. */
    Error BroadcastSink::begin(const char *) noexcept
    {
        return record(Error::not_ready);
    }

    /** @brief 기능이 없는 image에서는 암호화 broadcast 검색도 거부합니다. */
    Error BroadcastSink::begin(const char *, const BroadcastCode &) noexcept
    {
        return record(Error::not_ready);
    }

    /** @brief 기능이 없는 image에서는 진행할 동기화 단계가 없습니다. */
    void BroadcastSink::poll() noexcept
    {
    }

    /** @brief 시작하지 않은 broadcast sink는 해제할 자원이 없습니다. */
    Error BroadcastSink::end() noexcept
    {
        return record(Error::not_started);
    }

    /** @brief 기능이 없는 image에서 streaming은 항상 거짓입니다. */
    bool BroadcastSink::streaming() const noexcept
    {
        return false;
    }

    /** @brief 기능이 없는 image에서 수신 frame은 없습니다. */
    bool BroadcastSink::readFrame(std::uint8_t (&frame)[40]) noexcept
    {
        static_cast<void>(frame);
        return false;
    }

    /** @brief 기능이 없는 image는 idle 상태입니다. */
    BroadcastStage BroadcastSink::stage() const noexcept
    {
        return stage_;
    }

    /** @brief 기능이 없는 image는 요청한 작업이 없습니다. */
    BroadcastSinkStep BroadcastSink::lastStep() const noexcept
    {
        return last_step_;
    }

    /** @brief 기능이 없는 image의 수신 수는 0입니다. */
    std::uint32_t BroadcastSink::receivedFrames() const noexcept
    {
        return 0U;
    }

    /** @brief 기능이 없는 image의 폐기 수는 0입니다. */
    std::uint32_t BroadcastSink::droppedFrames() const noexcept
    {
        return 0U;
    }

    /** @brief 마지막 공개 오류를 반환합니다. */
    Error BroadcastSink::lastError() const noexcept
    {
        return last_error_;
    }

    /** @brief 기능이 없는 image에서 stack 오류는 없습니다. */
    int BroadcastSink::nativeCode() const noexcept
    {
        return 0;
    }

    /** @brief 마지막 공개 오류를 기록합니다. */
    Error BroadcastSink::record(Error error, int native_code) noexcept
    {
        static_cast<void>(native_code);
        last_error_ = error;
        return error;
    }
} // namespace nucode::ble::audio

#endif
