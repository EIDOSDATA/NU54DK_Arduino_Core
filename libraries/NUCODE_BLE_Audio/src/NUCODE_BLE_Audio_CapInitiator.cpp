/**
 * @file NUCODE_BLE_Audio_CapInitiator.cpp
 * @brief CAP Initiator broadcast source 공개 API를 구현합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include "NUCODE_BLE_Audio.h"

#if !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE) && defined(CONFIG_BT_CAP_INITIATOR) && \
    defined(CONFIG_BT_BAP_BROADCAST_SOURCE)

#include <NUCODE_BLE.h>

#include <zephyr/bluetooth/audio/bap.h>
#include <zephyr/bluetooth/audio/bap_lc3_preset.h>
#include <zephyr/bluetooth/audio/cap.h>
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

        NET_BUF_POOL_FIXED_DEFINE(cap_source_tx_pool, 4,
                                  BT_ISO_SDU_BUF_SIZE(CONFIG_BT_ISO_TX_MTU),
                                  CONFIG_BT_CONN_TX_USER_DATA_SIZE, nullptr);
        K_SEM_DEFINE(cap_source_stopped, 0, 1);

        /** @brief 한 Arduino 객체가 소유하는 CAP broadcast source 상태입니다. */
        struct CapSourceState
        {
            CapInitiator *owner = nullptr;
            bt_cap_broadcast_source *source = nullptr;
            bt_le_ext_adv *advertising = nullptr;
            bt_cap_stream stream = {};
            atomic_t streaming = 0;
            atomic_t sent = 0;
            atomic_t sequence = 0;
            atomic_t error = 0;
            bool callbacks_registered = false;
            bool extended_started = false;
            bool periodic_started = false;
            bool source_started = false;
        };

        CapSourceState cap_source_state;

        bt_bap_lc3_preset cap_preset = {
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

        /** @brief CAP BIS가 시작되면 공개 송신 가능 상태로 표시합니다. */
        void streamStarted(bt_bap_stream *stream)
        {
            if ((cap_source_state.owner != nullptr) &&
                (stream == &cap_source_state.stream.bap_stream))
            {
                atomic_set(&cap_source_state.streaming, 1);
            }
        }

        /** @brief CAP BIS가 중단되면 공개 송신 상태를 내립니다. */
        void streamStopped(bt_bap_stream *stream, std::uint8_t reason)
        {
            static_cast<void>(reason);
            if (stream == &cap_source_state.stream.bap_stream)
            {
                atomic_set(&cap_source_state.streaming, 0);
            }
        }

        bt_bap_stream_ops cap_stream_callbacks = {
            .started = streamStarted,
            .stopped = streamStopped,
        };

        /** @brief CAP broadcast 시작 완료를 객체 상태에 반영합니다. */
        void broadcastStarted(bt_cap_broadcast_source *source)
        {
            if (source == cap_source_state.source)
            {
                cap_source_state.source_started = true;
            }
        }

        /** @brief CAP broadcast 중단 완료를 대기 중인 Arduino 문맥에 알립니다. */
        void broadcastStopped(bt_cap_broadcast_source *source, std::uint8_t reason)
        {
            static_cast<void>(reason);
            if (source == cap_source_state.source)
            {
                cap_source_state.source_started = false;
                atomic_set(&cap_source_state.streaming, 0);
                k_sem_give(&cap_source_stopped);
            }
        }

        bt_cap_initiator_cb cap_initiator_callbacks = {
            .broadcast_started = broadcastStarted,
            .broadcast_stopped = broadcastStopped,
        };

        /** @brief 부분 생성된 CAP/advertising 자원을 역순으로 반환합니다. */
        void releaseCapSource() noexcept
        {
            if ((cap_source_state.source != nullptr) && cap_source_state.source_started)
            {
                if (bt_cap_initiator_broadcast_audio_stop(cap_source_state.source) == 0)
                {
                    (void)k_sem_take(&cap_source_stopped, K_SECONDS(2));
                }
            }
            if (cap_source_state.source != nullptr)
            {
                (void)bt_cap_initiator_broadcast_audio_delete(cap_source_state.source);
                cap_source_state.source = nullptr;
            }
            if (cap_source_state.periodic_started &&
                (cap_source_state.advertising != nullptr))
            {
                (void)bt_le_per_adv_stop(cap_source_state.advertising);
                cap_source_state.periodic_started = false;
            }
            if (cap_source_state.extended_started &&
                (cap_source_state.advertising != nullptr))
            {
                (void)bt_le_ext_adv_stop(cap_source_state.advertising);
                cap_source_state.extended_started = false;
            }
            if (cap_source_state.advertising != nullptr)
            {
                (void)bt_le_ext_adv_delete(cap_source_state.advertising);
                cap_source_state.advertising = nullptr;
            }
            if (cap_source_state.callbacks_registered)
            {
                (void)bt_cap_initiator_unregister_cb(&cap_initiator_callbacks);
                cap_source_state.callbacks_registered = false;
            }
            atomic_set(&cap_source_state.streaming, 0);
        }
    } // namespace

    /** @brief 마지막 공개 오류와 원본 stack 오류를 기록합니다. */
    Error CapInitiator::record(Error error, int native_code) noexcept
    {
        last_error_ = error;
        native_code_ = native_code;
        return error;
    }

    /** @brief 암호화하지 않은 CAP broadcast를 시작합니다. */
    Error CapInitiator::begin(const char *broadcast_name) noexcept
    {
        return start(broadcast_name, nullptr);
    }

    /** @brief Broadcast Code를 적용한 CAP broadcast를 시작합니다. */
    Error CapInitiator::begin(const char *broadcast_name,
                              const BroadcastCode &broadcast_code) noexcept
    {
        return start(broadcast_name, broadcast_code);
    }

    /** @brief 선택한 암호화 설정으로 CAP source와 광고를 구성합니다. */
    Error CapInitiator::start(const char *broadcast_name,
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
        if (cap_source_state.owner != nullptr)
        {
            return record(Error::busy);
        }
        if ((broadcast_name == nullptr) || (broadcast_name[0] == '\0') ||
            (strlen(broadcast_name) > maximum_broadcast_name))
        {
            return record(Error::invalid_argument);
        }

        cap_source_state = {};
        cap_source_state.owner = this;
        k_sem_reset(&cap_source_stopped);
        memset(&cap_source_state.stream, 0, sizeof(cap_source_state.stream));
        bt_cap_stream_ops_register(&cap_source_state.stream, &cap_stream_callbacks);

        int result = bt_cap_initiator_register_cb(&cap_initiator_callbacks);
        if (result != 0)
        {
            cap_source_state.owner = nullptr;
            stage_ = CapStage::failed;
            return record(Error::stack_error, result);
        }
        cap_source_state.callbacks_registered = true;

        result = bt_le_ext_adv_create(BT_BAP_ADV_PARAM_BROADCAST_FAST, nullptr,
                                      &cap_source_state.advertising);
        if (result == 0)
        {
            result = bt_le_per_adv_set_param(cap_source_state.advertising,
                                             BT_BAP_PER_ADV_PARAM_BROADCAST_FAST);
        }

        bt_cap_initiator_broadcast_stream_param stream_param = {
            .stream = &cap_source_state.stream,
            .data_len = 0U,
            .data = nullptr,
        };
        bt_cap_initiator_broadcast_subgroup_param subgroup_param = {
            .stream_count = 1U,
            .stream_params = &stream_param,
            .codec_cfg = &cap_preset.codec_cfg,
        };
        bt_cap_initiator_broadcast_create_param create_param = {
            .subgroup_count = 1U,
            .subgroup_params = &subgroup_param,
            .qos = &cap_preset.qos,
            .packing = BT_ISO_PACKING_SEQUENTIAL,
            .encryption = broadcast_code != nullptr,
        };
        if ((result == 0) && (broadcast_code != nullptr))
        {
            memcpy(create_param.broadcast_code, broadcast_code,
                   sizeof(create_param.broadcast_code));
        }
        if (result == 0)
        {
            result = bt_cap_initiator_broadcast_audio_create(
                &create_param, &cap_source_state.source);
        }
        if (result == 0)
        {
            result = bt_cap_initiator_broadcast_audio_start(
                cap_source_state.source, cap_source_state.advertising);
            cap_source_state.source_started = result == 0;
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
            result = bt_le_ext_adv_set_data(cap_source_state.advertising,
                                            advertising_data,
                                            ARRAY_SIZE(advertising_data), nullptr, 0U);
        }

        NET_BUF_SIMPLE_DEFINE(base, 128U);
        if (result == 0)
        {
            result = bt_cap_initiator_broadcast_get_base(cap_source_state.source,
                                                         &base);
        }
        if (result == 0)
        {
            const bt_data periodic_data = {
                .type = BT_DATA_SVC_DATA16,
                .data_len = static_cast<std::uint8_t>(base.len),
                .data = base.data,
            };
            result = bt_le_per_adv_set_data(cap_source_state.advertising,
                                            &periodic_data, 1U);
        }
        if (result == 0)
        {
            result = bt_le_ext_adv_start(cap_source_state.advertising,
                                         BT_LE_EXT_ADV_START_DEFAULT);
            cap_source_state.extended_started = result == 0;
        }
        if (result == 0)
        {
            result = bt_le_per_adv_start(cap_source_state.advertising);
            cap_source_state.periodic_started = result == 0;
        }
        if (result != 0)
        {
            releaseCapSource();
            cap_source_state.owner = nullptr;
            stage_ = CapStage::failed;
            return record(Error::stack_error, result);
        }

        atomic_set(&cap_source_state.sent, 0);
        atomic_set(&cap_source_state.sequence, 0);
        atomic_set(&cap_source_state.error, 0);
        started_ = true;
        stage_ = CapStage::ready;
        return record(Error::none);
    }

    /** @brief CAP broadcast와 광고를 정지하고 backend 소유권을 반환합니다. */
    Error CapInitiator::end() noexcept
    {
        if (!started_)
        {
            return record(Error::not_started);
        }

        stage_ = CapStage::stopping;
        releaseCapSource();
        cap_source_state.owner = nullptr;
        started_ = false;
        stage_ = CapStage::idle;
        return record(Error::none);
    }

    /** @brief stream callback이 확정한 CAP BIS 송신 상태를 반환합니다. */
    bool CapInitiator::streaming() const noexcept
    {
        return started_ && (cap_source_state.owner == this) &&
               (atomic_get(&cap_source_state.streaming) != 0);
    }

    /** @brief 고정 pool buffer에 LC3 frame을 복사해 CAP BIS로 전송합니다. */
    Error CapInitiator::sendFrame(const std::uint8_t (&frame)[40]) noexcept
    {
        if (!streaming())
        {
            return record(Error::not_ready);
        }
        net_buf *buffer = net_buf_alloc(&cap_source_tx_pool, K_NO_WAIT);
        if (buffer == nullptr)
        {
            return record(Error::busy, -ENOMEM);
        }
        net_buf_reserve(buffer, BT_ISO_CHAN_SEND_RESERVE);
        net_buf_add_mem(buffer, frame, frame_octets);
        const std::uint16_t sequence =
            static_cast<std::uint16_t>(atomic_get(&cap_source_state.sequence));
        const int result = bt_cap_stream_send(&cap_source_state.stream, buffer, sequence);
        if (result != 0)
        {
            net_buf_unref(buffer);
            return record(Error::stack_error, result);
        }
        atomic_inc(&cap_source_state.sequence);
        atomic_inc(&cap_source_state.sent);
        return record(Error::none);
    }

    /** @brief CAP 절차로 실행 중인 broadcast metadata를 갱신합니다. */
    Error CapInitiator::updateContext(std::uint16_t context) noexcept
    {
        if (!started_)
        {
            return record(Error::not_started);
        }
        if (context == 0U)
        {
            return record(Error::invalid_argument);
        }
        const std::uint8_t metadata[] = {
            3U,
            BT_AUDIO_METADATA_TYPE_STREAM_CONTEXT,
            static_cast<std::uint8_t>(context & 0xffU),
            static_cast<std::uint8_t>((context >> 8U) & 0xffU),
        };
        const int result = bt_cap_initiator_broadcast_audio_update(
            cap_source_state.source, metadata, sizeof(metadata));
        if (result != 0)
        {
            return record(Error::stack_error, result);
        }
        return record(Error::none);
    }

    /** @brief callback을 반영한 CAP Initiator 단계를 반환합니다. */
    CapStage CapInitiator::stage() const noexcept
    {
        if (streaming())
        {
            return CapStage::streaming;
        }
        return stage_;
    }

    /** @brief Host가 수락한 CAP BIS frame 수를 반환합니다. */
    std::uint32_t CapInitiator::sentFrames() const noexcept
    {
        return started_ ? static_cast<std::uint32_t>(
                              atomic_get(&cap_source_state.sent))
                        : 0U;
    }

    /** @brief 마지막 공개 오류를 반환합니다. */
    Error CapInitiator::lastError() const noexcept
    {
        return last_error_;
    }

    /** @brief 마지막 원본 stack 오류를 반환합니다. */
    int CapInitiator::nativeCode() const noexcept
    {
        const int callback_error = atomic_get(&cap_source_state.error);
        return callback_error != 0 ? callback_error : native_code_;
    }
} // namespace nucode::ble::audio

#else

namespace nucode::ble::audio
{
    Error CapInitiator::begin(const char *) noexcept
    {
        return record(Error::not_ready);
    }

    Error CapInitiator::begin(const char *, const BroadcastCode &) noexcept
    {
        return record(Error::not_ready);
    }

    Error CapInitiator::end() noexcept
    {
        return record(Error::not_started);
    }

    bool CapInitiator::streaming() const noexcept
    {
        return false;
    }

    Error CapInitiator::sendFrame(const std::uint8_t (&frame)[40]) noexcept
    {
        static_cast<void>(frame);
        return record(Error::not_ready);
    }

    Error CapInitiator::updateContext(std::uint16_t) noexcept
    {
        return record(Error::not_ready);
    }

    CapStage CapInitiator::stage() const noexcept
    {
        return stage_;
    }

    std::uint32_t CapInitiator::sentFrames() const noexcept
    {
        return 0U;
    }

    Error CapInitiator::lastError() const noexcept
    {
        return last_error_;
    }

    int CapInitiator::nativeCode() const noexcept
    {
        return native_code_;
    }

    Error CapInitiator::start(const char *, const std::uint8_t *) noexcept
    {
        return record(Error::not_ready);
    }

    Error CapInitiator::record(Error error, int native_code) noexcept
    {
        last_error_ = error;
        native_code_ = native_code;
        return error;
    }
} // namespace nucode::ble::audio

#endif
