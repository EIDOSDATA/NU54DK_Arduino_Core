/**
 * @file NUCODE_BLE_Audio_BroadcastSource.cpp
 * @brief LC3 BAP broadcast source 공개 API를 구현합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include "NUCODE_BLE_Audio.h"

#if !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE) && defined(CONFIG_BT_BAP_BROADCAST_SOURCE)

#include <NUCODE_BLE.h>

#include <zephyr/bluetooth/audio/bap.h>
#include <zephyr/bluetooth/audio/bap_lc3_preset.h>
#include <zephyr/bluetooth/bluetooth.h>
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

        NET_BUF_POOL_FIXED_DEFINE(source_tx_pool, 4,
                                  BT_ISO_SDU_BUF_SIZE(CONFIG_BT_ISO_TX_MTU),
                                  CONFIG_BT_CONN_TX_USER_DATA_SIZE, nullptr);
        K_SEM_DEFINE(source_stopped, 0, 1);

        /** @brief 한 Arduino 객체가 소유하는 broadcast source 상태입니다. */
        struct SourceState
        {
            BroadcastSource *owner = nullptr;
            bt_bap_broadcast_source *source = nullptr;
            bt_le_ext_adv *advertising = nullptr;
            bt_bap_stream stream = {};
            atomic_t streaming = 0;
            atomic_t sent = 0;
            atomic_t sequence = 0;
            atomic_t error = 0;
            bool callbacks_registered = false;
            bool extended_started = false;
            bool periodic_started = false;
            bool source_started = false;
        };

        SourceState source_state;

        bt_bap_lc3_preset preset = {
            .codec_cfg = BT_AUDIO_CODEC_LC3_CONFIG(
                BT_AUDIO_CODEC_CFG_FREQ_16KHZ, BT_AUDIO_CODEC_CFG_DURATION_10,
                BT_AUDIO_LOCATION_FRONT_LEFT, 40U, 1U, BT_AUDIO_CONTEXT_TYPE_MEDIA),
            .qos =
                {
                    .pd = 40000U,
                    .framing = BT_BAP_QOS_CFG_FRAMING_UNFRAMED,
                    .phy = BT_BAP_QOS_CFG_2M,
                    .rtn = 2U,
                    .sdu = 40U,
                    .latency = 10U,
                    .interval = 10000U,
                },
        };

        /** @brief BIS가 시작되면 공개 송신 가능 상태로 표시합니다. */
        void streamStarted(bt_bap_stream *stream)
        {
            if ((source_state.owner != nullptr) && (stream == &source_state.stream))
            {
                atomic_set(&source_state.streaming, 1);
            }
        }

        /** @brief BIS가 중단되면 공개 송신 상태를 내립니다. */
        void streamStopped(bt_bap_stream *stream, std::uint8_t reason)
        {
            static_cast<void>(reason);
            if (stream == &source_state.stream)
            {
                atomic_set(&source_state.streaming, 0);
            }
        }

        bt_bap_stream_ops stream_callbacks = {
            .started = streamStarted,
            .stopped = streamStopped,
        };

        /** @brief source 시작 callback은 stream callback과 함께 상태를 확정합니다. */
        void sourceStarted(bt_bap_broadcast_source *source)
        {
            if (source == source_state.source)
            {
                source_state.source_started = true;
            }
        }

        /** @brief source 중단 완료를 대기 중인 Arduino 문맥에 알립니다. */
        void sourceStopped(bt_bap_broadcast_source *source, std::uint8_t reason)
        {
            static_cast<void>(reason);
            if (source == source_state.source)
            {
                source_state.source_started = false;
                atomic_set(&source_state.streaming, 0);
                k_sem_give(&source_stopped);
            }
        }

        bt_bap_broadcast_source_cb source_callbacks = {
            .started = sourceStarted,
            .stopped = sourceStopped,
        };

        /** @brief 부분 생성된 BAP/advertising 자원을 역순으로 반환합니다. */
        void releaseSource() noexcept
        {
            if ((source_state.source != nullptr) && source_state.source_started)
            {
                if (bt_bap_broadcast_source_stop(source_state.source) == 0)
                {
                    (void)k_sem_take(&source_stopped, K_SECONDS(2));
                }
            }
            if (source_state.source != nullptr)
            {
                (void)bt_bap_broadcast_source_delete(source_state.source);
                source_state.source = nullptr;
            }
            if (source_state.periodic_started && (source_state.advertising != nullptr))
            {
                (void)bt_le_per_adv_stop(source_state.advertising);
                source_state.periodic_started = false;
            }
            if (source_state.extended_started && (source_state.advertising != nullptr))
            {
                (void)bt_le_ext_adv_stop(source_state.advertising);
                source_state.extended_started = false;
            }
            if (source_state.advertising != nullptr)
            {
                (void)bt_le_ext_adv_delete(source_state.advertising);
                source_state.advertising = nullptr;
            }
            if (source_state.callbacks_registered)
            {
                (void)bt_bap_broadcast_source_unregister_cb(&source_callbacks);
                source_state.callbacks_registered = false;
            }
            atomic_set(&source_state.streaming, 0);
        }
    } // namespace

    /** @brief 마지막 공개 오류와 원본 stack 오류를 기록합니다. */
    Error BroadcastSource::record(Error error, int native_code) noexcept
    {
        last_error_ = error;
        native_code_ = native_code;
        return error;
    }

    /** @brief 단일 subgroup/BIS의 BASE와 extended/periodic 광고를 시작합니다. */
    Error BroadcastSource::begin(const char *broadcast_name) noexcept
    {
        return start(broadcast_name, nullptr);
    }

    /** @brief Broadcast Code를 적용한 subgroup/BIS 광고를 시작합니다. */
    Error BroadcastSource::begin(const char *broadcast_name,
                                 const BroadcastCode &broadcast_code) noexcept
    {
        return start(broadcast_name, broadcast_code);
    }

    /** @brief 선택한 암호화 설정으로 source 자원과 광고를 구성합니다. */
    Error BroadcastSource::start(const char *broadcast_name,
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
        if (source_state.owner != nullptr)
        {
            return record(Error::busy);
        }
        if ((broadcast_name == nullptr) || (broadcast_name[0] == '\0') ||
            (strlen(broadcast_name) > maximum_broadcast_name))
        {
            return record(Error::invalid_argument);
        }

        source_state = {};
        source_state.owner = this;
        k_sem_reset(&source_stopped);
        memset(&source_state.stream, 0, sizeof(source_state.stream));
        bt_bap_stream_cb_register(&source_state.stream, &stream_callbacks);

        int result = bt_bap_broadcast_source_register_cb(&source_callbacks);
        if (result != 0)
        {
            source_state.owner = nullptr;
            return record(Error::stack_error, result);
        }
        source_state.callbacks_registered = true;

        bt_bap_broadcast_source_stream_param stream_param = {
            .stream = &source_state.stream,
            .data_len = 0U,
            .data = nullptr,
        };
        bt_bap_broadcast_source_subgroup_param subgroup_param = {
            .params_count = 1U,
            .params = &stream_param,
            .codec_cfg = &preset.codec_cfg,
        };
        bt_bap_broadcast_source_param create_param = {
            .params_count = 1U,
            .params = &subgroup_param,
            .qos = &preset.qos,
            .packing = BT_ISO_PACKING_SEQUENTIAL,
            .encryption = broadcast_code != nullptr,
        };
        if (broadcast_code != nullptr)
        {
            memcpy(create_param.broadcast_code, broadcast_code,
                   sizeof(create_param.broadcast_code));
        }
        result = bt_bap_broadcast_source_create(&create_param, &source_state.source);
        if (result != 0)
        {
            releaseSource();
            source_state.owner = nullptr;
            return record(Error::stack_error, result);
        }

        result = bt_le_ext_adv_create(BT_BAP_ADV_PARAM_BROADCAST_FAST, nullptr,
                                      &source_state.advertising);
        if (result == 0)
        {
            result = bt_le_per_adv_set_param(source_state.advertising,
                                             BT_BAP_PER_ADV_PARAM_BROADCAST_FAST);
        }

        std::uint32_t broadcast_id = 0U;
        if (result == 0)
        {
            result = bt_rand(&broadcast_id, BT_AUDIO_BROADCAST_ID_SIZE);
            broadcast_id &= 0x00FFFFFFU;
        }

        NET_BUF_SIMPLE_DEFINE(announcement, BT_UUID_SIZE_16 + BT_AUDIO_BROADCAST_ID_SIZE);
        if (result == 0)
        {
            net_buf_simple_add_le16(&announcement, BT_UUID_BROADCAST_AUDIO_VAL);
            net_buf_simple_add_le24(&announcement, broadcast_id);
            const bt_data advertising_data[] = {
                {
                    .type = BT_DATA_SVC_DATA16,
                    .data_len = static_cast<std::uint8_t>(announcement.len),
                    .data = announcement.data,
                },
                {
                    .type = BT_DATA_BROADCAST_NAME,
                    .data_len = static_cast<std::uint8_t>(strlen(broadcast_name)),
                    .data = reinterpret_cast<const std::uint8_t *>(broadcast_name),
                },
            };
            result = bt_le_ext_adv_set_data(source_state.advertising, advertising_data,
                                            ARRAY_SIZE(advertising_data), nullptr, 0U);
        }

        NET_BUF_SIMPLE_DEFINE(base, 128U);
        if (result == 0)
        {
            result = bt_bap_broadcast_source_get_base(source_state.source, &base);
        }
        if (result == 0)
        {
            const bt_data periodic_data = {
                .type = BT_DATA_SVC_DATA16,
                .data_len = static_cast<std::uint8_t>(base.len),
                .data = base.data,
            };
            result = bt_le_per_adv_set_data(source_state.advertising, &periodic_data, 1U);
        }
        if (result == 0)
        {
            result = bt_le_ext_adv_start(source_state.advertising,
                                         BT_LE_EXT_ADV_START_DEFAULT);
            source_state.extended_started = result == 0;
        }
        if (result == 0)
        {
            result = bt_le_per_adv_start(source_state.advertising);
            source_state.periodic_started = result == 0;
        }
        if (result == 0)
        {
            result = bt_bap_broadcast_source_start(source_state.source,
                                                   source_state.advertising);
        }
        if (result != 0)
        {
            releaseSource();
            source_state.owner = nullptr;
            return record(Error::stack_error, result);
        }

        source_state.source_started = true;
        atomic_set(&source_state.sent, 0);
        atomic_set(&source_state.sequence, 0);
        atomic_set(&source_state.error, 0);
        started_ = true;
        return record(Error::none);
    }

    /** @brief 방송과 광고를 정지하고 backend 소유권을 반환합니다. */
    Error BroadcastSource::end() noexcept
    {
        if (!started_)
        {
            return record(Error::not_started);
        }

        releaseSource();
        source_state.owner = nullptr;
        started_ = false;
        return record(Error::none);
    }

    /** @brief stream callback이 확정한 BIS 송신 상태를 반환합니다. */
    bool BroadcastSource::streaming() const noexcept
    {
        return started_ && (atomic_get(&source_state.streaming) != 0);
    }

    /** @brief 고정 pool buffer에 LC3 frame을 복사해 BIS로 전송합니다. */
    Error BroadcastSource::sendFrame(const std::uint8_t (&frame)[40]) noexcept
    {
        if (!streaming())
        {
            return record(Error::not_ready);
        }
        net_buf *buffer = net_buf_alloc(&source_tx_pool, K_NO_WAIT);
        if (buffer == nullptr)
        {
            return record(Error::busy, -ENOMEM);
        }
        net_buf_reserve(buffer, BT_ISO_CHAN_SEND_RESERVE);
        net_buf_add_mem(buffer, frame, frame_octets);
        const std::uint16_t sequence =
            static_cast<std::uint16_t>(atomic_get(&source_state.sequence));
        const int result = bt_bap_stream_send(&source_state.stream, buffer, sequence);
        if (result != 0)
        {
            net_buf_unref(buffer);
            return record(Error::stack_error, result);
        }
        atomic_inc(&source_state.sequence);
        atomic_inc(&source_state.sent);
        return record(Error::none);
    }

    /** @brief Host가 수락한 BIS frame 수를 반환합니다. */
    std::uint32_t BroadcastSource::sentFrames() const noexcept
    {
        return started_ ? static_cast<std::uint32_t>(atomic_get(&source_state.sent)) : 0U;
    }

    /** @brief 마지막 공개 오류를 반환합니다. */
    Error BroadcastSource::lastError() const noexcept
    {
        return last_error_;
    }

    /** @brief 마지막 원본 stack 오류를 반환합니다. */
    int BroadcastSource::nativeCode() const noexcept
    {
        const int callback_error = atomic_get(&source_state.error);
        return callback_error != 0 ? callback_error : native_code_;
    }
} // namespace nucode::ble::audio

#else

namespace nucode::ble::audio
{
    /** @brief broadcast source 기능이 없는 image에서는 시작을 거부합니다. */
    Error BroadcastSource::begin(const char *) noexcept
    {
        return record(Error::not_ready);
    }

    /** @brief 기능이 없는 image에서는 암호화 broadcast 시작도 거부합니다. */
    Error BroadcastSource::begin(const char *, const BroadcastCode &) noexcept
    {
        return record(Error::not_ready);
    }

    /** @brief 시작하지 않은 broadcast source는 해제할 자원이 없습니다. */
    Error BroadcastSource::end() noexcept
    {
        return record(Error::not_started);
    }

    /** @brief 기능이 없는 image에서 streaming은 항상 거짓입니다. */
    bool BroadcastSource::streaming() const noexcept
    {
        return false;
    }

    /** @brief 기능이 없는 image에서는 frame을 전송하지 않습니다. */
    Error BroadcastSource::sendFrame(const std::uint8_t (&frame)[40]) noexcept
    {
        static_cast<void>(frame);
        return record(Error::not_ready);
    }

    /** @brief 기능이 없는 image의 전송 수는 0입니다. */
    std::uint32_t BroadcastSource::sentFrames() const noexcept
    {
        return 0U;
    }

    /** @brief 마지막 공개 오류를 반환합니다. */
    Error BroadcastSource::lastError() const noexcept
    {
        return last_error_;
    }

    /** @brief 기능이 없는 image에서 stack 오류는 없습니다. */
    int BroadcastSource::nativeCode() const noexcept
    {
        return 0;
    }

    /** @brief 마지막 공개 오류를 기록합니다. */
    Error BroadcastSource::record(Error error, int native_code) noexcept
    {
        static_cast<void>(native_code);
        last_error_ = error;
        return error;
    }
} // namespace nucode::ble::audio

#endif
