/**
 * @file NUCODE_BLE_Audio_UnicastClient.cpp
 * @brief PACS/ASCS discovery와 LC3 unicast CIS 송신을 구현합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include "NUCODE_BLE_Audio.h"

#if !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE) && defined(CONFIG_BT_BAP_UNICAST_CLIENT)

#include <NUCODE_BLE.h>
#include <internal/NUCODE_BLE_Internal.h>

#include <zephyr/bluetooth/audio/bap.h>
#include <zephyr/bluetooth/audio/bap_lc3_preset.h>
#include <zephyr/bluetooth/conn.h>
#include <zephyr/bluetooth/gatt.h>
#include <zephyr/bluetooth/hci.h>
#include <zephyr/bluetooth/iso.h>
#include <zephyr/kernel.h>
#include <zephyr/net_buf.h>
#include <zephyr/sys/atomic.h>

#include <errno.h>
#include <string.h>

namespace nucode::ble::audio
{
    namespace
    {
        constexpr std::size_t frame_octets = 40U;

        NET_BUF_POOL_FIXED_DEFINE(tx_pool, 4, BT_ISO_SDU_BUF_SIZE(CONFIG_BT_ISO_TX_MTU),
                                  CONFIG_BT_CONN_TX_USER_DATA_SIZE, nullptr);

        /** @brief 순차적 Host callback 단계를 나타냅니다. */
        enum class Event : int
        {
            none = 0,
            secured,
            discovered,
            configured,
            qos_set,
            enabled,
            connected,
            streaming,
            disabled,
            released,
        };

        /** @brief 한 Arduino client만 소유하는 고정 BAP 상태입니다. */
        struct ClientState
        {
            UnicastClient *owner = nullptr;
            bt_conn *connection = nullptr;
            bt_bap_ep *sink = nullptr;
            bt_bap_unicast_group *group = nullptr;
            bt_bap_stream stream = {};
            atomic_t event = 0;
            atomic_t error = 0;
            atomic_t sent = 0;
            atomic_t sequence = 0;
            atomic_t codec_found = 0;
            atomic_t stopping = 0;
            atomic_t expected_disconnect = 0;
            std::uint32_t security_wait_started = 0U;
            std::uint32_t stop_wait_started = 0U;
            bool security_requested = false;
        };

        ClientState client;

        bt_bap_lc3_preset preset = {
            .codec_cfg = BT_AUDIO_CODEC_LC3_CONFIG(
                BT_AUDIO_CODEC_CFG_FREQ_16KHZ, BT_AUDIO_CODEC_CFG_DURATION_10,
                BT_AUDIO_LOCATION_FRONT_LEFT, 40U, 1U, BT_AUDIO_CONTEXT_TYPE_UNSPECIFIED),
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

        /** @brief 현재 연결의 성공 callback만 다음 단계로 전달합니다. */
        void acceptResponse(bt_bap_stream *stream, bt_bap_ascs_rsp_code code)
        {
            if ((client.owner == nullptr) || (stream != &client.stream))
            {
                return;
            }
            if (code != BT_BAP_ASCS_RSP_CODE_SUCCESS)
            {
                atomic_set(&client.error, -static_cast<int>(code));
                return;
            }
        }

        /** @brief codec configuration 응답을 검사합니다. */
        void configured(bt_bap_stream *stream, bt_bap_ascs_rsp_code code, bt_bap_ascs_reason reason)
        {
            static_cast<void>(reason);
            acceptResponse(stream, code);
        }

        /** @brief QoS configuration 응답을 검사합니다. */
        void qosSet(bt_bap_stream *stream, bt_bap_ascs_rsp_code code, bt_bap_ascs_reason reason)
        {
            static_cast<void>(reason);
            acceptResponse(stream, code);
        }

        /** @brief ASE enable 응답을 검사합니다. */
        void enabled(bt_bap_stream *stream, bt_bap_ascs_rsp_code code, bt_bap_ascs_reason reason)
        {
            static_cast<void>(reason);
            acceptResponse(stream, code);
        }

        /** @brief disable control point 응답 실패를 비동기 오류로 전달합니다. */
        void disabledResponse(bt_bap_stream *stream, bt_bap_ascs_rsp_code code,
                              bt_bap_ascs_reason reason)
        {
            static_cast<void>(reason);
            acceptResponse(stream, code);
        }

        /** @brief release control point 응답 실패를 비동기 오류로 전달합니다. */
        void releasedResponse(bt_bap_stream *stream, bt_bap_ascs_rsp_code code,
                              bt_bap_ascs_reason reason)
        {
            static_cast<void>(reason);
            acceptResponse(stream, code);
        }

        /** @brief 상대 PACS가 LC3를 광고하는지 기록합니다. */
        void pacRecord(bt_conn *connection, bt_audio_dir direction,
                       const bt_audio_codec_cap *capability)
        {
            if ((client.owner == nullptr) || (connection != client.connection) ||
                (direction != BT_AUDIO_DIR_SINK) || (capability == nullptr))
            {
                return;
            }
            if (capability->id == BT_HCI_CODING_FORMAT_LC3)
            {
                atomic_set(&client.codec_found, 1);
            }
        }

        /** @brief 발견한 첫 sink ASE를 선택합니다. */
        void endpoint(bt_conn *connection, bt_audio_dir direction, bt_bap_ep *ep)
        {
            if ((client.owner == nullptr) || (connection != client.connection) ||
                (direction != BT_AUDIO_DIR_SINK) || (ep == nullptr))
            {
                return;
            }
            if (client.sink == nullptr)
            {
                client.sink = ep;
            }
        }

        /** @brief PACS/ASCS 검색 완료를 Arduino poll()에 알립니다. */
        void discovered(bt_conn *connection, int error, bt_audio_dir direction)
        {
            if ((client.owner == nullptr) || (connection != client.connection) ||
                (direction != BT_AUDIO_DIR_SINK))
            {
                return;
            }
            if (error != 0)
            {
                atomic_set(&client.error, error);
            }
            else
            {
                atomic_set(&client.event, static_cast<int>(Event::discovered));
            }
        }

        bt_bap_unicast_client_cb client_callbacks = {
            .config = configured,
            .qos = qosSet,
            .enable = enabled,
            .disable = disabledResponse,
            .release = releasedResponse,
            .pac_record = pacRecord,
            .endpoint = endpoint,
            .discover = discovered,
        };

        /** @brief ASE 상태가 codec configured로 바뀐 뒤에만 QoS로 진행합니다. */
        void streamConfigured(bt_bap_stream *stream, const bt_bap_qos_cfg_pref *preference)
        {
            static_cast<void>(preference);
            if ((client.owner != nullptr) && (stream == &client.stream) &&
                (atomic_get(&client.stopping) == 0))
            {
                atomic_set(&client.event, static_cast<int>(Event::configured));
            }
        }

        /** @brief ASE 상태가 QoS configured로 바뀐 뒤에만 enable로 진행합니다. */
        void streamQosSet(bt_bap_stream *stream)
        {
            if ((client.owner != nullptr) && (stream == &client.stream) &&
                (atomic_get(&client.stopping) == 0))
            {
                atomic_set(&client.event, static_cast<int>(Event::qos_set));
            }
        }

        /** @brief ASE 상태가 enabled로 바뀐 뒤에만 CIS로 진행합니다. */
        void streamEnabled(bt_bap_stream *stream)
        {
            if ((client.owner != nullptr) && (stream == &client.stream) &&
                (atomic_get(&client.stopping) == 0))
            {
                atomic_set(&client.event, static_cast<int>(Event::enabled));
            }
        }

        /** @brief CIS 연결 완료를 다음 단계로 전달합니다. */
        void streamConnected(bt_bap_stream *stream)
        {
            if ((client.owner != nullptr) && (stream == &client.stream) &&
                (atomic_get(&client.stopping) == 0))
            {
                atomic_set(&client.event, static_cast<int>(Event::connected));
            }
        }

        /** @brief peer가 sink stream을 시작했음을 알립니다. */
        void streamStarted(bt_bap_stream *stream)
        {
            if ((client.owner != nullptr) && (stream == &client.stream) &&
                (atomic_get(&client.stopping) == 0))
            {
                atomic_set(&client.event, static_cast<int>(Event::streaming));
            }
        }

        /** @brief sink ASE가 QoS configured로 돌아오면 release를 예약합니다. */
        void streamDisabled(bt_bap_stream *stream)
        {
            if ((client.owner != nullptr) && (stream == &client.stream) &&
                (atomic_get(&client.stopping) != 0))
            {
                atomic_set(&client.event, static_cast<int>(Event::disabled));
            }
        }

        /** @brief ASE 자원 반환 완료를 Arduino poll()에 알립니다. */
        void streamReleased(bt_bap_stream *stream)
        {
            if ((client.owner != nullptr) && (stream == &client.stream) &&
                (atomic_get(&client.stopping) != 0))
            {
                atomic_set(&client.event, static_cast<int>(Event::released));
            }
        }

        /** @brief stream 중단을 전송 거부 상태로 반영합니다. */
        void streamStopped(bt_bap_stream *stream, std::uint8_t reason)
        {
            if ((client.owner != nullptr) && (stream == &client.stream))
            {
                if (atomic_get(&client.stopping) == 0)
                {
                    atomic_set(&client.error, -(0x100 + static_cast<int>(reason)));
                }
            }
        }

        bt_bap_stream_ops stream_callbacks = {
            .configured = streamConfigured,
            .qos_set = streamQosSet,
            .enabled = streamEnabled,
            .disabled = streamDisabled,
            .released = streamReleased,
            .started = streamStarted,
            .stopped = streamStopped,
            .connected = streamConnected,
        };

        /** @brief 요청한 연결의 L2 보안 완료를 수신합니다. */
        void securityChanged(bt_conn *connection, bt_security_t level, bt_security_err error)
        {
            if ((client.owner == nullptr) || (connection != client.connection))
            {
                return;
            }
            if (error != BT_SECURITY_ERR_SUCCESS)
            {
                if ((error == BT_SECURITY_ERR_PIN_OR_KEY_MISSING) ||
                    (error == BT_SECURITY_ERR_AUTH_REQUIREMENT))
                {
                    /** @brief 상대의 재시작·재플래시 뒤 불일치한 bond를 지워 다시 페어링합니다. */
                    static_cast<void>(bt_unpair(BT_ID_DEFAULT, bt_conn_get_dst(connection)));
                }
                atomic_set(&client.error, -static_cast<int>(error));
            }
            else if (level >= BT_SECURITY_L2)
            {
                atomic_set(&client.event, static_cast<int>(Event::secured));
            }
        }

        /** @brief 연결 해제 뒤 진행 중인 상태를 실패로 돌립니다. */
        void disconnected(bt_conn *connection, std::uint8_t reason)
        {
            if ((client.owner != nullptr) && (connection == client.connection) &&
                (atomic_get(&client.expected_disconnect) == 0))
            {
                atomic_set(&client.error, -(0x200 + static_cast<int>(reason)));
            }
        }

        BT_CONN_CB_DEFINE(nucode_audio_client_connection_callbacks) = {
            .disconnected = disconnected,
            .security_changed = securityChanged,
        };

        /** @brief 하나의 TX ASE에 대한 고정 unicast group을 구성합니다. */
        int createGroup()
        {
            bt_bap_unicast_group_stream_param tx = {
                .stream = &client.stream,
                .qos = &preset.qos,
            };
            bt_bap_unicast_group_stream_pair_param pair = {
                .rx_param = nullptr,
                .tx_param = &tx,
            };
            bt_bap_unicast_group_param parameters = {
                .params_count = 1U,
                .params = &pair,
                .packing = BT_ISO_PACKING_SEQUENTIAL,
            };
            return bt_bap_unicast_group_create(&parameters, &client.group);
        }
    } // namespace

    /** @brief 공개 오류와 원본 코드를 기록합니다. */
    Error UnicastClient::record(Error error, int native_code) noexcept
    {
        last_error_ = error;
        native_code_ = native_code;
        if ((error == Error::stack_error) || (error == Error::unsupported) ||
            (error == Error::not_connected))
        {
            failure_stage_ = stage_;
            stage_ = UnicastClientStage::failed;
        }
        return error;
    }

    /** @brief 공개 연결을 참조하고 L2 보안을 요청합니다. */
    Error UnicastClient::begin(const BLEConnectionHandle &connection) noexcept
    {
        if (!connection.valid())
        {
            return record(Error::invalid_argument);
        }
        if (started_)
        {
            return record(Error::already_started);
        }
        if (client.owner != nullptr)
        {
            return record(Error::busy);
        }
        bt_conn *native = internal::referenceConnection(connection);
        if (native == nullptr)
        {
            return record(Error::not_connected);
        }
        client.owner = this;
        client.connection = native;
        client.sink = nullptr;
        client.group = nullptr;
        memset(&client.stream, 0, sizeof(client.stream));
        bt_bap_stream_cb_register(&client.stream, &stream_callbacks);
        atomic_set(&client.event, 0);
        atomic_set(&client.error, 0);
        atomic_set(&client.sent, 0);
        atomic_set(&client.sequence, 0);
        atomic_set(&client.codec_found, 0);
        atomic_set(&client.stopping, 0);
        atomic_set(&client.expected_disconnect, 0);
        client.security_wait_started = k_uptime_get_32();
        client.security_requested = false;
        int result = bt_bap_unicast_client_register_cb(&client_callbacks);
        if (result != 0)
        {
            bt_conn_unref(native);
            client = {};
            return record(Error::stack_error, result);
        }
        started_ = true;
        stage_ = UnicastClientStage::securing;
        failure_stage_ = UnicastClientStage::idle;
        last_step_ = UnicastClientStep::security;
        if (bt_conn_get_security(native) >= BT_SECURITY_L2)
        {
            atomic_set(&client.event, static_cast<int>(Event::secured));
        }
        return record(Error::none);
    }

    /** @brief callback 단계마다 정확히 한 다음 Host 요청을 실행합니다. */
    void UnicastClient::poll() noexcept
    {
        if (!started_ || (stage_ == UnicastClientStage::failed))
        {
            return;
        }
        const int callback_error = atomic_set(&client.error, 0);
        if (callback_error != 0)
        {
            (void)record(Error::stack_error, callback_error);
            return;
        }
        if ((stage_ == UnicastClientStage::stopping) &&
            ((k_uptime_get_32() - client.stop_wait_started) > 10000U))
        {
            (void)record(Error::stack_error, -ETIMEDOUT);
            return;
        }
        if ((stage_ == UnicastClientStage::securing) && (atomic_get(&client.event) == 0))
        {
            if (bt_conn_get_security(client.connection) >= BT_SECURITY_L2)
            {
                atomic_set(&client.event, static_cast<int>(Event::secured));
            }
            else if (!client.security_requested && (bt_gatt_get_mtu(client.connection) > 23U))
            {
                client.security_requested = true;
                last_step_ = UnicastClientStep::security;
                const int security_result = bt_conn_set_security(client.connection, BT_SECURITY_L2);
                /** @brief 재연결 시 bond의 자동 암호화가 진행 중이면 완료 callback을 기다립니다. */
                if ((security_result != 0) && (security_result != -EBUSY))
                {
                    (void)record(Error::stack_error, security_result);
                    return;
                }
            }
            if ((atomic_get(&client.event) == 0) &&
                ((k_uptime_get_32() - client.security_wait_started) > 10000U))
            {
                (void)record(Error::stack_error, -ETIMEDOUT);
                return;
            }
            if (atomic_get(&client.event) == 0)
            {
                return;
            }
        }
        const Event event = static_cast<Event>(atomic_set(&client.event, 0));
        if (event == Event::none)
        {
            return;
        }
        if ((stage_ == UnicastClientStage::stopping) && (event != Event::disabled) &&
            (event != Event::released))
        {
            return;
        }
        int result = 0;
        if (event == Event::secured)
        {
            stage_ = UnicastClientStage::discovering;
            last_step_ = UnicastClientStep::discover;
            result = bt_bap_unicast_client_discover(client.connection, BT_AUDIO_DIR_SINK);
        }
        else if (event == Event::discovered)
        {
            if ((client.sink == nullptr) || (atomic_get(&client.codec_found) == 0))
            {
                (void)record(Error::unsupported);
                return;
            }
            stage_ = UnicastClientStage::configuring;
            last_step_ = UnicastClientStep::configure;
            result = bt_bap_stream_config(client.connection, &client.stream, client.sink,
                                          &preset.codec_cfg);
        }
        else if (event == Event::configured)
        {
            last_step_ = UnicastClientStep::group;
            result = createGroup();
            if (result == 0)
            {
                last_step_ = UnicastClientStep::qos;
                result = bt_bap_stream_qos(client.connection, client.group);
            }
        }
        else if (event == Event::qos_set)
        {
            last_step_ = UnicastClientStep::enable;
            result = bt_bap_stream_enable(&client.stream, preset.codec_cfg.meta,
                                          preset.codec_cfg.meta_len);
        }
        else if (event == Event::enabled)
        {
            last_step_ = UnicastClientStep::connect;
            result = bt_bap_stream_connect(&client.stream);
        }
        else if (event == Event::streaming)
        {
            if (stage_ == UnicastClientStage::configuring)
            {
                stage_ = UnicastClientStage::streaming;
            }
        }
        else if (event == Event::disabled)
        {
            last_step_ = UnicastClientStep::release;
            result = bt_bap_stream_release(&client.stream);
        }
        else if (event == Event::released)
        {
            atomic_set(&client.expected_disconnect, 1);
            stage_ = UnicastClientStage::released;
        }
        if (result != 0)
        {
            (void)record(Error::stack_error, result);
        }
    }

    /** @brief 고정 buffer 하나에 LC3 frame을 넣고 ISO로 전송합니다. */
    Error UnicastClient::sendFrame(const std::uint8_t (&frame)[40]) noexcept
    {
        if (!started_ || (stage_ != UnicastClientStage::streaming))
        {
            return record(Error::not_ready);
        }
        last_step_ = UnicastClientStep::send;
        net_buf *buffer = net_buf_alloc(&tx_pool, K_NO_WAIT);
        if (buffer == nullptr)
        {
            return record(Error::busy, -ENOMEM);
        }
        net_buf_reserve(buffer, BT_ISO_CHAN_SEND_RESERVE);
        net_buf_add_mem(buffer, frame, frame_octets);
        const std::uint16_t sequence = static_cast<std::uint16_t>(atomic_get(&client.sequence));
        const int result = bt_bap_stream_send(&client.stream, buffer, sequence);
        if (result != 0)
        {
            net_buf_unref(buffer);
            return record(Error::stack_error, result);
        }
        atomic_inc(&client.sequence);
        atomic_inc(&client.sent);
        return record(Error::none);
    }

    /** @brief sink ASE를 disable하고 QoS 상태 callback에서 release합니다. */
    Error UnicastClient::stop() noexcept
    {
        if (!started_ || (stage_ != UnicastClientStage::streaming))
        {
            return record(Error::not_ready);
        }
        last_step_ = UnicastClientStep::disable;
        atomic_set(&client.stopping, 1);
        stage_ = UnicastClientStage::stopping;
        client.stop_wait_started = k_uptime_get_32();
        const int result = bt_bap_stream_disable(&client.stream);
        if (result != 0)
        {
            atomic_set(&client.stopping, 0);
            return record(Error::stack_error, result);
        }
        return record(Error::none);
    }

    /** @brief ACL 해제 뒤 group과 callback 참조를 반환합니다. */
    Error UnicastClient::end() noexcept
    {
        if (!started_)
        {
            return record(Error::not_started);
        }
        if (client.stream.conn != nullptr)
        {
            return record(Error::busy);
        }
        if (client.group != nullptr)
        {
            last_step_ = UnicastClientStep::cleanup;
            const int result = bt_bap_unicast_group_delete(client.group);
            if (result != 0)
            {
                return record(Error::stack_error, result);
            }
        }
        const int result = bt_bap_unicast_client_unregister_cb(&client_callbacks);
        if (result != 0)
        {
            return record(Error::stack_error, result);
        }
        bt_conn_unref(client.connection);
        client = {};
        started_ = false;
        stage_ = UnicastClientStage::idle;
        return record(Error::none);
    }

    /** @brief 현재 비동기 단계를 반환합니다. */
    UnicastClientStage UnicastClient::stage() const noexcept
    {
        return stage_;
    }

    /** @brief 마지막 실패 지점을 반환합니다. */
    UnicastClientStage UnicastClient::failedAt() const noexcept
    {
        return failure_stage_;
    }

    /** @brief 마지막 요청 단계를 반환합니다. */
    UnicastClientStep UnicastClient::lastStep() const noexcept
    {
        return last_step_;
    }

    /** @brief Host가 수락한 frame 수를 반환합니다. */
    std::uint32_t UnicastClient::sentFrames() const noexcept
    {
        return started_ ? static_cast<std::uint32_t>(atomic_get(&client.sent)) : 0U;
    }

    /** @brief 마지막 공개 오류를 반환합니다. */
    Error UnicastClient::lastError() const noexcept
    {
        return last_error_;
    }

    /** @brief 마지막 Host/controller 오류를 반환합니다. */
    int UnicastClient::nativeCode() const noexcept
    {
        return native_code_;
    }
} // namespace nucode::ble::audio

#else

namespace nucode::ble::audio
{
    /** @brief client 기능이 없는 image에서는 시작을 거부합니다. */
    Error UnicastClient::begin(const BLEConnectionHandle &) noexcept
    {
        return record(Error::not_ready);
    }

    /** @brief 기능이 없는 image에서는 다음 단계가 없습니다. */
    void UnicastClient::poll() noexcept
    {
    }

    /** @brief 기능이 없는 image에서는 frame을 전송하지 않습니다. */
    Error UnicastClient::sendFrame(const std::uint8_t (&frame)[40]) noexcept
    {
        static_cast<void>(frame);
        return record(Error::not_ready);
    }

    /** @brief 기능이 없는 image에서는 stream을 중단하지 않습니다. */
    Error UnicastClient::stop() noexcept
    {
        return record(Error::not_ready);
    }

    /** @brief 시작하지 않은 client는 해제할 자원이 없습니다. */
    Error UnicastClient::end() noexcept
    {
        return record(Error::not_started);
    }

    /** @brief 기능이 없는 image는 idle 상태입니다. */
    UnicastClientStage UnicastClient::stage() const noexcept
    {
        return stage_;
    }

    /** @brief 기능이 없는 image는 실패 단계가 없습니다. */
    UnicastClientStage UnicastClient::failedAt() const noexcept
    {
        return failure_stage_;
    }

    /** @brief 기능이 없는 image는 요청한 작업이 없습니다. */
    UnicastClientStep UnicastClient::lastStep() const noexcept
    {
        return last_step_;
    }

    /** @brief 기능이 없는 image는 전송 수가 0입니다. */
    std::uint32_t UnicastClient::sentFrames() const noexcept
    {
        return 0U;
    }

    /** @brief 마지막 공개 오류를 반환합니다. */
    Error UnicastClient::lastError() const noexcept
    {
        return last_error_;
    }

    /** @brief 기능이 없는 image는 원본 오류가 없습니다. */
    int UnicastClient::nativeCode() const noexcept
    {
        return 0;
    }

    /** @brief 마지막 공개 오류를 기록합니다. */
    Error UnicastClient::record(Error error, int native_code) noexcept
    {
        static_cast<void>(native_code);
        last_error_ = error;
        return error;
    }
} // namespace nucode::ble::audio

#endif
