/**
 * @file NUCODE_BLE_Audio_UnicastServer.cpp
 * @brief PACS/ASCS unicast sink와 고정 LC3 frame queue를 구현합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include "NUCODE_BLE_Audio.h"

#if !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE) && defined(CONFIG_BT_BAP_UNICAST_SERVER)

#include <NUCODE_BLE.h>

#include <zephyr/bluetooth/audio/bap.h>
#include <zephyr/bluetooth/audio/lc3.h>
#include <zephyr/bluetooth/audio/pacs.h>
#include <zephyr/bluetooth/conn.h>
#include <zephyr/bluetooth/hci.h>
#include <zephyr/bluetooth/iso.h>
#include <zephyr/kernel.h>
#include <zephyr/net_buf.h>
#include <zephyr/sys/atomic.h>

#include <string.h>

namespace nucode::ble::audio
{
    namespace
    {
        constexpr std::uint16_t frame_octets = 40U;
        constexpr bt_audio_context contexts = static_cast<bt_audio_context>(
            BT_AUDIO_CONTEXT_TYPE_UNSPECIFIED | BT_AUDIO_CONTEXT_TYPE_MEDIA);

        K_MSGQ_DEFINE(frame_queue, frame_octets, 8, 4);

#if defined(CONFIG_BT_AUDIO_TX)
        NET_BUF_POOL_FIXED_DEFINE(source_tx_pool, 4, BT_ISO_SDU_BUF_SIZE(CONFIG_BT_ISO_TX_MTU),
                                  CONFIG_BT_CONN_TX_USER_DATA_SIZE, nullptr);
#endif

        /** @brief 단일 sink ASE와 callback이 공유하는 고정 상태입니다. */
        struct ServerState
        {
            UnicastServer *owner = nullptr;
            bt_bap_stream stream = {};
            bt_bap_stream source_stream = {};
            bool source_enabled = false;
            bool source_capability_registered = false;
            atomic_t streaming = 0;
            atomic_t source_streaming = 0;
            atomic_t received = 0;
            atomic_t sent = 0;
            atomic_t sequence = 0;
            atomic_t dropped = 0;
            atomic_t error = 0;
        };

        ServerState server;

        /** @brief peer의 재플래시로 보안 정보가 어긋나면 해당 bond만 제거합니다. */
        void securityChanged(bt_conn *connection, bt_security_t level, bt_security_err error)
        {
            static_cast<void>(level);
            if ((server.owner != nullptr) &&
                ((error == BT_SECURITY_ERR_PIN_OR_KEY_MISSING) ||
                 (error == BT_SECURITY_ERR_AUTH_REQUIREMENT)))
            {
                static_cast<void>(bt_unpair(BT_ID_DEFAULT, bt_conn_get_dst(connection)));
            }
        }

        BT_CONN_CB_DEFINE(nucode_audio_server_connection_callbacks) = {
            .security_changed = securityChanged,
        };

        const bt_audio_codec_cap codec_cap = BT_AUDIO_CODEC_CAP_LC3(
            BT_AUDIO_CODEC_CAP_FREQ_16KHZ, BT_AUDIO_CODEC_CAP_DURATION_10,
            BT_AUDIO_CODEC_CAP_CHAN_COUNT_SUPPORT(1), frame_octets, frame_octets, 1U, contexts);

        bt_pacs_cap pac_sink = {
            .codec_cap = &codec_cap,
        };
        bt_pacs_cap pac_source = {
            .codec_cap = &codec_cap,
        };

        /** @brief 광고할 codec 설정이 고정 frame 계약과 일치하는지 확인합니다. */
        bool validCodec(const bt_audio_codec_cfg *config)
        {
            if ((config == nullptr) || (config->id != BT_HCI_CODING_FORMAT_LC3))
            {
                return false;
            }
            const int frequency = bt_audio_codec_cfg_get_freq(config);
            const int duration = bt_audio_codec_cfg_get_frame_dur(config);
            return (frequency > 0) && (duration > 0) &&
                   (bt_audio_codec_cfg_freq_to_freq_hz(
                        static_cast<bt_audio_codec_cfg_freq>(frequency)) == 16000) &&
                   (bt_audio_codec_cfg_frame_dur_to_frame_dur_us(
                        static_cast<bt_audio_codec_cfg_frame_dur>(duration)) == 10000) &&
                   (bt_audio_codec_cfg_get_octets_per_frame(config) == frame_octets) &&
                   (bt_audio_codec_cfg_get_frame_blocks_per_sdu(config, true) == 1);
        }

        /** @brief 유효하지 않은 ASE 요청을 명시적으로 거부합니다. */
        int reject(bt_bap_ascs_rsp *response, int native_error)
        {
            *response = BT_BAP_ASCS_RSP(BT_BAP_ASCS_RSP_CODE_CONF_UNSUPPORTED,
                                        BT_BAP_ASCS_REASON_CODEC_DATA);
            return native_error;
        }

        /** @brief PACS로 광고한 LC3 ASE 하나를 해당 방향의 고정 stream에 할당합니다. */
        int configure(bt_conn *connection, const bt_bap_ep *endpoint, bt_audio_dir direction,
                      const bt_audio_codec_cfg *config, bt_bap_stream **stream,
                      bt_bap_qos_cfg_pref *preference, bt_bap_ascs_rsp *response)
        {
            static_cast<void>(connection);
            static_cast<void>(endpoint);
            if ((server.owner == nullptr) || !validCodec(config))
            {
                return reject(response, -EINVAL);
            }
            if (direction == BT_AUDIO_DIR_SINK)
            {
                if (server.stream.conn != nullptr)
                {
                    return reject(response, -EBUSY);
                }
                *stream = &server.stream;
                atomic_set(&server.streaming, 0);
                k_msgq_purge(&frame_queue);
            }
            else if ((direction == BT_AUDIO_DIR_SOURCE) && server.source_enabled)
            {
                if (server.source_stream.conn != nullptr)
                {
                    return reject(response, -EBUSY);
                }
                *stream = &server.source_stream;
                atomic_set(&server.source_streaming, 0);
                atomic_set(&server.sequence, 0);
            }
            else
            {
                return reject(response, -EINVAL);
            }
            *preference =
                BT_BAP_QOS_CFG_PREF(true, BT_GAP_LE_PHY_2M, 0x02, 10, 40000, 40000, 40000, 40000);
            return 0;
        }

        /** @brief 연결 중 codec 변경은 고정 자원 계약상 거부합니다. */
        int reconfigure(bt_bap_stream *stream, bt_audio_dir direction,
                        const bt_audio_codec_cfg *config, bt_bap_qos_cfg_pref *preference,
                        bt_bap_ascs_rsp *response)
        {
            static_cast<void>(stream);
            static_cast<void>(direction);
            static_cast<void>(config);
            static_cast<void>(preference);
            return reject(response, -ENOTSUP);
        }

        /** @brief 요청한 QoS가 고정 ISO 전송 크기와 일치하는지 검사합니다. */
        int setQos(bt_bap_stream *stream, const bt_bap_qos_cfg *qos, bt_bap_ascs_rsp *response)
        {
            static_cast<void>(stream);
            if ((qos == nullptr) || (qos->sdu != frame_octets))
            {
                *response =
                    BT_BAP_ASCS_RSP(BT_BAP_ASCS_RSP_CODE_CONF_UNSUPPORTED, BT_BAP_ASCS_REASON_SDU);
                return -EINVAL;
            }
            if (qos->interval != 10000U)
            {
                *response = BT_BAP_ASCS_RSP(BT_BAP_ASCS_RSP_CODE_CONF_UNSUPPORTED,
                                            BT_BAP_ASCS_REASON_INTERVAL);
                return -EINVAL;
            }
            return 0;
        }

        /** @brief 유효한 codec 설정이 남아 있는 경우에만 ASE를 활성화합니다. */
        int enable(bt_bap_stream *stream, const std::uint8_t *metadata, std::size_t metadata_length,
                   bt_bap_ascs_rsp *response)
        {
            static_cast<void>(metadata);
            static_cast<void>(metadata_length);
            if (((stream != &server.stream) && (stream != &server.source_stream)) ||
                !validCodec(stream->codec_cfg))
            {
                return reject(response, -EINVAL);
            }
            return 0;
        }

        /** @brief sink가 준비되면 client의 CIS 연결을 기다립니다. */
        int start(bt_bap_stream *stream, bt_bap_ascs_rsp *response)
        {
            static_cast<void>(response);
            return ((stream == &server.stream) || (stream == &server.source_stream)) ? 0 : -EINVAL;
        }

        /** @brief 알려진 metadata만 허용합니다. */
        int metadata(bt_bap_stream *stream, const std::uint8_t *data, std::size_t length,
                     bt_bap_ascs_rsp *response)
        {
            static_cast<void>(data);
            static_cast<void>(length);
            if ((stream != &server.stream) && (stream != &server.source_stream))
            {
                return reject(response, -EINVAL);
            }
            return 0;
        }

        /** @brief ASE 중단 요청 후 streaming flag를 낮춥니다. */
        int disable(bt_bap_stream *stream, bt_bap_ascs_rsp *response)
        {
            static_cast<void>(response);
            if ((stream != &server.stream) && (stream != &server.source_stream))
            {
                return -EINVAL;
            }
            if (stream == &server.stream)
            {
                atomic_set(&server.streaming, 0);
            }
            else
            {
                atomic_set(&server.source_streaming, 0);
            }
            return 0;
        }

        /** @brief transport 정지에 성공하면 수신 queue를 비웁니다. */
        int stop(bt_bap_stream *stream, bt_bap_ascs_rsp *response)
        {
            const int result = disable(stream, response);
            if ((result == 0) && (stream == &server.stream))
            {
                k_msgq_purge(&frame_queue);
            }
            return result;
        }

        /** @brief client의 ASE release를 수락합니다. */
        int release(bt_bap_stream *stream, bt_bap_ascs_rsp *response)
        {
            return stop(stream, response);
        }

        bt_bap_unicast_server_cb server_callbacks = {
            .config = configure,
            .reconfig = reconfigure,
            .qos = setQos,
            .enable = enable,
            .start = start,
            .metadata = metadata,
            .disable = disable,
            .stop = stop,
            .release = release,
        };

        /** @brief 유효한 ISO payload만 고정 queue에 복사합니다. */
        void receive(bt_bap_stream *stream, const bt_iso_recv_info *info, net_buf *buffer)
        {
            if ((stream != &server.stream) || ((info->flags & BT_ISO_FLAGS_VALID) == 0U) ||
                (buffer->len != frame_octets))
            {
                return;
            }
            atomic_inc(&server.received);
            if (k_msgq_put(&frame_queue, buffer->data, K_NO_WAIT) != 0)
            {
                atomic_inc(&server.dropped);
            }
        }

        /** @brief ISO transport가 시작되면 수신 가능 상태로 표시합니다. */
        void streamStarted(bt_bap_stream *stream)
        {
            if (stream == &server.stream)
            {
                atomic_set(&server.streaming, 1);
            }
            else if (stream == &server.source_stream)
            {
                atomic_set(&server.source_streaming, 1);
            }
        }

        /** @brief ISO transport 중단 시 공개 상태를 정리합니다. */
        void streamStopped(bt_bap_stream *stream, std::uint8_t reason)
        {
            static_cast<void>(reason);
            if (stream == &server.stream)
            {
                atomic_set(&server.streaming, 0);
                k_msgq_purge(&frame_queue);
            }
            else if (stream == &server.source_stream)
            {
                atomic_set(&server.source_streaming, 0);
            }
        }

        /** @brief sink ASE enable 후 HCI CIS를 시작합니다. */
        void streamEnabled(bt_bap_stream *stream)
        {
            if (stream == &server.stream)
            {
                const int result = bt_bap_stream_start(stream);
                if (result != 0)
                {
                    atomic_set(&server.error, result);
                }
            }
        }

        bt_bap_stream_ops stream_callbacks = {
            .enabled = streamEnabled,
            .started = streamStarted,
            .stopped = streamStopped,
            .recv = receive,
        };

        /** @brief 등록 실패 시 역순으로 서비스를 반환합니다. */
        void unregisterServices(bool capability, bool callbacks, bool server_registered, bool pacs)
        {
            if (capability)
            {
                if (server.source_capability_registered)
                {
                    (void)bt_pacs_cap_unregister(BT_AUDIO_DIR_SOURCE, &pac_source);
                    server.source_capability_registered = false;
                }
                (void)bt_pacs_cap_unregister(BT_AUDIO_DIR_SINK, &pac_sink);
            }
            if (callbacks)
            {
                (void)bt_bap_unicast_server_unregister_cb(&server_callbacks);
            }
            if (server_registered)
            {
                (void)bt_bap_unicast_server_unregister();
            }
            if (pacs)
            {
                (void)bt_pacs_unregister();
            }
        }
    } // namespace

    /** @brief 마지막 API 오류를 기록합니다. */
    Error UnicastServer::record(Error error, int native_code) noexcept
    {
        last_error_ = error;
        native_code_ = native_code;
        return error;
    }

    /** @brief 기존 단방향 sink 시작 경로를 유지합니다. */
    Error UnicastServer::begin() noexcept
    {
        return begin(UnicastServerMode::sink_only);
    }

    /** @brief Bluetooth 시작 뒤 요청한 PACS·ASCS 방향을 등록합니다. */
    Error UnicastServer::begin(UnicastServerMode mode) noexcept
    {
        if (started_)
        {
            return record(Error::already_started);
        }
        if (!BLEDevice.initialized())
        {
            return record(Error::not_ready);
        }
        if (server.owner != nullptr)
        {
            return record(Error::busy);
        }
        if ((mode != UnicastServerMode::sink_only) && (mode != UnicastServerMode::duplex))
        {
            return record(Error::invalid_argument);
        }
        if ((mode == UnicastServerMode::duplex) &&
            (!IS_ENABLED(CONFIG_BT_PAC_SRC) || !IS_ENABLED(CONFIG_BT_PAC_SRC_LOC) ||
             !IS_ENABLED(CONFIG_BT_AUDIO_TX) ||
             (CONFIG_BT_ASCS_MAX_ASE_SRC_COUNT < 1)))
        {
            return record(Error::unsupported);
        }
        server.owner = this;
        server.source_enabled = mode == UnicastServerMode::duplex;
        server.source_capability_registered = false;
        memset(&server.stream, 0, sizeof(server.stream));
        memset(&server.source_stream, 0, sizeof(server.source_stream));
        bt_bap_stream_cb_register(&server.stream, &stream_callbacks);
        if (server.source_enabled)
        {
            bt_bap_stream_cb_register(&server.source_stream, &stream_callbacks);
        }
        atomic_set(&server.streaming, 0);
        atomic_set(&server.source_streaming, 0);
        atomic_set(&server.received, 0);
        atomic_set(&server.sent, 0);
        atomic_set(&server.sequence, 0);
        atomic_set(&server.dropped, 0);
        atomic_set(&server.error, 0);
        k_msgq_purge(&frame_queue);

        const bt_pacs_register_param pacs_config = {
            .snk_pac = true,
            .snk_loc = true,
#if defined(CONFIG_BT_PAC_SRC)
            .src_pac = server.source_enabled,
#endif
#if defined(CONFIG_BT_PAC_SRC_LOC)
            .src_loc = server.source_enabled,
#endif
        };
        int result = bt_pacs_register(&pacs_config);
        if (result != 0)
        {
            server.owner = nullptr;
            return record(Error::stack_error, result);
        }
        const bt_bap_unicast_server_register_param server_config = {
            .snk_cnt = 1U,
            .src_cnt = server.source_enabled ? 1U : 0U,
        };
        result = bt_bap_unicast_server_register(&server_config);
        if (result != 0)
        {
            unregisterServices(false, false, false, true);
            server.owner = nullptr;
            return record(Error::stack_error, result);
        }
        result = bt_bap_unicast_server_register_cb(&server_callbacks);
        if (result != 0)
        {
            unregisterServices(false, false, true, true);
            server.owner = nullptr;
            return record(Error::stack_error, result);
        }
        result = bt_pacs_cap_register(BT_AUDIO_DIR_SINK, &pac_sink);
        if (result != 0)
        {
            unregisterServices(false, true, true, true);
            server.owner = nullptr;
            return record(Error::stack_error, result);
        }
        if (server.source_enabled)
        {
            result = bt_pacs_cap_register(BT_AUDIO_DIR_SOURCE, &pac_source);
            if (result != 0)
            {
                unregisterServices(true, true, true, true);
                server.owner = nullptr;
                return record(Error::stack_error, result);
            }
            server.source_capability_registered = true;
        }
        result = bt_pacs_set_location(BT_AUDIO_DIR_SINK, BT_AUDIO_LOCATION_FRONT_LEFT);
        if (result == 0)
        {
            result = bt_pacs_set_supported_contexts(BT_AUDIO_DIR_SINK, contexts);
        }
        if (result == 0)
        {
            result = bt_pacs_set_available_contexts(BT_AUDIO_DIR_SINK, contexts);
        }
        if ((result == 0) && server.source_enabled)
        {
            result = bt_pacs_set_location(BT_AUDIO_DIR_SOURCE, BT_AUDIO_LOCATION_FRONT_RIGHT);
        }
        if ((result == 0) && server.source_enabled)
        {
            result = bt_pacs_set_supported_contexts(BT_AUDIO_DIR_SOURCE, contexts);
        }
        if ((result == 0) && server.source_enabled)
        {
            result = bt_pacs_set_available_contexts(BT_AUDIO_DIR_SOURCE, contexts);
        }
        if (result != 0)
        {
            unregisterServices(true, true, true, true);
            server.owner = nullptr;
            return record(Error::stack_error, result);
        }
        started_ = true;
        return record(Error::none);
    }

    /** @brief 연결이 없는 상태에서 서비스 등록을 해제합니다. */
    Error UnicastServer::end() noexcept
    {
        if (!started_)
        {
            return record(Error::not_started);
        }
        if ((server.stream.conn != nullptr) || (server.source_stream.conn != nullptr))
        {
            return record(Error::busy);
        }
        unregisterServices(true, true, true, true);
        k_msgq_purge(&frame_queue);
        server.owner = nullptr;
        started_ = false;
        return record(Error::none);
    }

    /** @brief ASE stream 상태를 반환합니다. */
    bool UnicastServer::streaming() const noexcept
    {
        return started_ && (atomic_get(&server.streaming) != 0);
    }

    /** @brief 수신 frame 한 개를 Arduino 문맥으로 전달합니다. */
    bool UnicastServer::readFrame(std::uint8_t (&frame)[40]) noexcept
    {
        return started_ && (k_msgq_get(&frame_queue, frame, K_NO_WAIT) == 0);
    }

    /** @brief duplex source ASE의 ISO 송신 가능 상태를 반환합니다. */
    bool UnicastServer::sourceStreaming() const noexcept
    {
        return started_ && server.source_enabled &&
               (atomic_get(&server.source_streaming) != 0);
    }

    /** @brief Arduino의 LC3 frame을 서버 source ASE의 CIS에 보냅니다. */
    Error UnicastServer::sendFrame(const std::uint8_t (&frame)[40]) noexcept
    {
#if defined(CONFIG_BT_AUDIO_TX)
        if (!sourceStreaming())
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
        const std::uint16_t sequence = static_cast<std::uint16_t>(atomic_get(&server.sequence));
        const int result = bt_bap_stream_send(&server.source_stream, buffer, sequence);
        if (result != 0)
        {
            net_buf_unref(buffer);
            return record(Error::stack_error, result);
        }
        atomic_inc(&server.sequence);
        atomic_inc(&server.sent);
        return record(Error::none);
#else
        static_cast<void>(frame);
        return record(Error::not_ready);
#endif
    }

    /** @brief 서버 source ASE에서 controller가 수락한 frame 수를 반환합니다. */
    std::uint32_t UnicastServer::sentFrames() const noexcept
    {
        return started_ ? static_cast<std::uint32_t>(atomic_get(&server.sent)) : 0U;
    }

    /** @brief 유효 수신 수를 반환합니다. */
    std::uint32_t UnicastServer::receivedFrames() const noexcept
    {
        return started_ ? static_cast<std::uint32_t>(atomic_get(&server.received)) : 0U;
    }

    /** @brief queue 포화로 버린 frame 수를 반환합니다. */
    std::uint32_t UnicastServer::droppedFrames() const noexcept
    {
        return started_ ? static_cast<std::uint32_t>(atomic_get(&server.dropped)) : 0U;
    }

    /** @brief callback 오류가 있으면 stack 오류를 우선 반환합니다. */
    Error UnicastServer::lastError() const noexcept
    {
        return (started_ && (atomic_get(&server.error) != 0)) ? Error::stack_error : last_error_;
    }

    /** @brief callback 또는 API의 원본 오류를 반환합니다. */
    int UnicastServer::nativeCode() const noexcept
    {
        const int callback_error = atomic_get(&server.error);
        return (callback_error != 0) ? callback_error : native_code_;
    }
} // namespace nucode::ble::audio

#else

namespace nucode::ble::audio
{
    /** @brief BAP server 기능이 없는 image는 기존 sink 시작도 거부합니다. */
    Error UnicastServer::begin() noexcept
    {
        last_error_ = Error::not_ready;
        return last_error_;
    }

    /** @brief BAP server 기능이 없는 image는 명시적으로 거부합니다. */
    Error UnicastServer::begin(UnicastServerMode) noexcept
    {
        last_error_ = Error::not_ready;
        return last_error_;
    }

    /** @brief 시작하지 않은 BAP server의 해제를 거부합니다. */
    Error UnicastServer::end() noexcept
    {
        last_error_ = Error::not_started;
        return last_error_;
    }

    /** @brief 기능이 없는 image에서 streaming은 항상 거짓입니다. */
    bool UnicastServer::streaming() const noexcept
    {
        return false;
    }

    /** @brief 기능이 없는 image에서 수신 frame은 없습니다. */
    bool UnicastServer::readFrame(std::uint8_t (&frame)[40]) noexcept
    {
        static_cast<void>(frame);
        return false;
    }

    /** @brief 기능이 없는 image의 서버 source는 송신하지 않습니다. */
    bool UnicastServer::sourceStreaming() const noexcept
    {
        return false;
    }

    /** @brief 기능이 없는 image의 서버 source 전송을 거부합니다. */
    Error UnicastServer::sendFrame(const std::uint8_t (&frame)[40]) noexcept
    {
        static_cast<void>(frame);
        return record(Error::not_ready);
    }

    /** @brief 기능이 없는 image의 전송 수는 0입니다. */
    std::uint32_t UnicastServer::sentFrames() const noexcept
    {
        return 0U;
    }

    /** @brief 기능이 없는 image의 수신 수는 0입니다. */
    std::uint32_t UnicastServer::receivedFrames() const noexcept
    {
        return 0U;
    }

    /** @brief 기능이 없는 image의 폐기 수는 0입니다. */
    std::uint32_t UnicastServer::droppedFrames() const noexcept
    {
        return 0U;
    }

    /** @brief 마지막 공개 오류를 반환합니다. */
    Error UnicastServer::lastError() const noexcept
    {
        return last_error_;
    }

    /** @brief 기능이 없는 image에서 stack 오류는 없습니다. */
    int UnicastServer::nativeCode() const noexcept
    {
        return 0;
    }

    /** @brief 마지막 공개 오류를 기록합니다. */
    Error UnicastServer::record(Error error, int native_code) noexcept
    {
        static_cast<void>(native_code);
        last_error_ = error;
        return error;
    }
} // namespace nucode::ble::audio

#endif
