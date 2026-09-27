/**
 * @file NUCODE_BLE_Audio_CapUnicastInitiator.cpp
 * @brief CAP Initiator unicast group 공개 API를 구현합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include "NUCODE_BLE_Audio.h"

#if !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE) && defined(CONFIG_BT_CAP_INITIATOR) &&               \
    defined(CONFIG_BT_BAP_UNICAST_CLIENT)

#include <NUCODE_BLE.h>
#include <internal/NUCODE_BLE_Internal.h>

#include <zephyr/bluetooth/audio/bap.h>
#include <zephyr/bluetooth/audio/bap_lc3_preset.h>
#include <zephyr/bluetooth/audio/cap.h>
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
        constexpr std::uint32_t procedure_timeout_ms = 10000U;

        NET_BUF_POOL_FIXED_DEFINE(cap_unicast_tx_pool, 4, BT_ISO_SDU_BUF_SIZE(CONFIG_BT_ISO_TX_MTU),
                                  CONFIG_BT_CONN_TX_USER_DATA_SIZE, nullptr);

        /** @brief callback에서 Arduino poll 문맥으로 전달할 사건입니다. */
        enum class Event : int
        {
            none = 0,
            secured,
            common_audio_service_discovered,
            audio_streams_discovered,
            started,
            stopped,
            cancelled,
        };

        /** @brief 한 Arduino 객체가 소유하는 CAP unicast 상태입니다. */
        struct CapUnicastState
        {
            CapUnicastInitiator *owner = nullptr;
            bt_conn *connection = nullptr;
            bt_bap_ep *sink = nullptr;
            bt_cap_unicast_group *group = nullptr;
            bt_cap_stream stream = {};
            bt_cap_unicast_audio_start_stream_param start_stream = {};
            bt_cap_unicast_audio_start_param start_parameters = {};
            bt_cap_stream *stop_streams[1] = {};
            bt_cap_unicast_audio_stop_param stop_parameters = {};
            atomic_t event = 0;
            atomic_t error = 0;
            atomic_t codec_found = 0;
            atomic_t streaming = 0;
            atomic_t sent = 0;
            atomic_t sequence = 0;
            atomic_t cancel_requested = 0;
            atomic_t cancelled = 0;
            atomic_t failed_on_peer = 0;
            atomic_t expected_disconnect = 0;
            bool bap_callbacks_registered = false;
            bool cap_callbacks_registered = false;
            bool security_requested = false;
            std::uint32_t wait_started = 0U;
        };

        CapUnicastState cap_unicast;

        bt_bap_lc3_preset cap_unicast_preset = {
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

        /** @brief 현재 CAP 연결의 LC3 capability를 기록합니다. */
        void pacRecord(bt_conn *connection, bt_audio_dir direction,
                       const bt_audio_codec_cap *capability)
        {
            if ((cap_unicast.owner == nullptr) || (connection != cap_unicast.connection) ||
                (direction != BT_AUDIO_DIR_SINK) || (capability == nullptr))
            {
                return;
            }
            if (capability->id == BT_HCI_CODING_FORMAT_LC3)
            {
                atomic_set(&cap_unicast.codec_found, 1);
            }
        }

        /** @brief 발견한 첫 sink ASE를 CAP stream 대상으로 선택합니다. */
        void endpoint(bt_conn *connection, bt_audio_dir direction, bt_bap_ep *ep)
        {
            if ((cap_unicast.owner != nullptr) && (connection == cap_unicast.connection) &&
                (direction == BT_AUDIO_DIR_SINK) && (ep != nullptr) &&
                (cap_unicast.sink == nullptr))
            {
                cap_unicast.sink = ep;
            }
        }

        /** @brief PACS/ASCS 검색 결과를 Arduino poll 문맥에 전달합니다. */
        void audioStreamsDiscovered(bt_conn *connection, int error, bt_audio_dir direction)
        {
            if ((cap_unicast.owner == nullptr) || (connection != cap_unicast.connection) ||
                (direction != BT_AUDIO_DIR_SINK))
            {
                return;
            }
            if (error != 0)
            {
                atomic_set(&cap_unicast.error, error);
            }
            else
            {
                atomic_set(&cap_unicast.event, static_cast<int>(Event::audio_streams_discovered));
            }
        }

        bt_bap_unicast_client_cb bap_callbacks = {
            .pac_record = pacRecord,
            .endpoint = endpoint,
            .discover = audioStreamsDiscovered,
        };

        /** @brief CAS 검색 완료를 공개 상태기계에 전달합니다. */
        void commonAudioServiceDiscovered(bt_conn *connection, int error,
                                          const bt_csip_set_coordinator_set_member *member,
                                          const bt_csip_set_coordinator_csis_inst *csis_instance)
        {
            static_cast<void>(member);
            static_cast<void>(csis_instance);
            if ((cap_unicast.owner == nullptr) || (connection != cap_unicast.connection))
            {
                return;
            }
            if (error != 0)
            {
                atomic_set(&cap_unicast.error, error);
            }
            else
            {
                atomic_set(&cap_unicast.event,
                           static_cast<int>(Event::common_audio_service_discovered));
            }
        }

        /** @brief CAP 시작 절차의 전체 성공·취소·부분 실패를 구분합니다. */
        void unicastStarted(int error, bt_conn *connection)
        {
            if (cap_unicast.owner == nullptr)
            {
                return;
            }
            if ((error == -ECANCELED) && (atomic_get(&cap_unicast.cancel_requested) != 0))
            {
                atomic_set(&cap_unicast.cancelled, 1);
                atomic_set(&cap_unicast.event, static_cast<int>(Event::cancelled));
                return;
            }
            if (error != 0)
            {
                atomic_set(&cap_unicast.failed_on_peer, connection != nullptr ? 1 : 0);
                atomic_set(&cap_unicast.error, error);
            }
            else
            {
                atomic_set(&cap_unicast.event, static_cast<int>(Event::started));
            }
        }

        /** @brief CAP 중단 절차의 전체 성공·취소·부분 실패를 구분합니다. */
        void unicastStopped(int error, bt_conn *connection)
        {
            if (cap_unicast.owner == nullptr)
            {
                return;
            }
            if ((error == -ECANCELED) && (atomic_get(&cap_unicast.cancel_requested) != 0))
            {
                atomic_set(&cap_unicast.cancelled, 1);
                atomic_set(&cap_unicast.event, static_cast<int>(Event::cancelled));
                return;
            }
            if (error != 0)
            {
                atomic_set(&cap_unicast.failed_on_peer, connection != nullptr ? 1 : 0);
                atomic_set(&cap_unicast.error, error);
            }
            else
            {
                atomic_set(&cap_unicast.event, static_cast<int>(Event::stopped));
            }
        }

        bt_cap_initiator_cb cap_callbacks = {
            .unicast_discovery_complete = commonAudioServiceDiscovered,
            .unicast_start_complete = unicastStarted,
            .unicast_stop_complete = unicastStopped,
        };

        /** @brief CIS가 시작되면 frame 송신 가능 상태로 표시합니다. */
        void streamStarted(bt_bap_stream *stream)
        {
            if ((cap_unicast.owner != nullptr) && (stream == &cap_unicast.stream.bap_stream))
            {
                atomic_set(&cap_unicast.streaming, 1);
            }
        }

        /** @brief CIS 중단을 송신 불가 상태로 즉시 반영합니다. */
        void streamStopped(bt_bap_stream *stream, std::uint8_t reason)
        {
            if (stream != &cap_unicast.stream.bap_stream)
            {
                return;
            }
            atomic_set(&cap_unicast.streaming, 0);
            if ((cap_unicast.owner != nullptr) &&
                (atomic_get(&cap_unicast.cancel_requested) == 0) &&
                (atomic_get(&cap_unicast.expected_disconnect) == 0))
            {
                atomic_cas(&cap_unicast.error, 0, -(0x100 + static_cast<int>(reason)));
            }
        }

        bt_bap_stream_ops stream_callbacks = {
            .started = streamStarted,
            .stopped = streamStopped,
        };

        /** @brief 요청한 연결의 L2 보안 완료를 수신합니다. */
        void securityChanged(bt_conn *connection, bt_security_t level, bt_security_err error)
        {
            if ((cap_unicast.owner == nullptr) || (connection != cap_unicast.connection))
            {
                return;
            }
            if (error != BT_SECURITY_ERR_SUCCESS)
            {
                if ((error == BT_SECURITY_ERR_PIN_OR_KEY_MISSING) ||
                    (error == BT_SECURITY_ERR_AUTH_REQUIREMENT))
                {
                    static_cast<void>(bt_unpair(BT_ID_DEFAULT, bt_conn_get_dst(connection)));
                }
                atomic_set(&cap_unicast.error, -static_cast<int>(error));
            }
            else if (level >= BT_SECURITY_L2)
            {
                atomic_set(&cap_unicast.event, static_cast<int>(Event::secured));
            }
        }

        /** @brief 예기치 않은 ACL 해제를 원본 HCI reason과 함께 보존합니다. */
        void disconnected(bt_conn *connection, std::uint8_t reason)
        {
            if ((cap_unicast.owner != nullptr) && (connection == cap_unicast.connection) &&
                (atomic_get(&cap_unicast.expected_disconnect) == 0))
            {
                atomic_cas(&cap_unicast.error, 0, -(0x200 + static_cast<int>(reason)));
            }
        }

        BT_CONN_CB_DEFINE(nucode_cap_unicast_connection_callbacks) = {
            .disconnected = disconnected,
            .security_changed = securityChanged,
        };

        /** @brief CAP group과 등록 callback을 생성 역순으로 반환합니다. */
        int releaseResources() noexcept
        {
            int first_error = 0;
            if (cap_unicast.group != nullptr)
            {
                const int result = bt_cap_unicast_group_delete(cap_unicast.group);
                if (result == 0)
                {
                    cap_unicast.group = nullptr;
                }
                else
                {
                    first_error = result;
                }
            }
            if (cap_unicast.cap_callbacks_registered)
            {
                const int result = bt_cap_initiator_unregister_cb(&cap_callbacks);
                if ((first_error == 0) && (result != 0))
                {
                    first_error = result;
                }
                if (result == 0)
                {
                    cap_unicast.cap_callbacks_registered = false;
                }
            }
            if (cap_unicast.bap_callbacks_registered)
            {
                const int result = bt_bap_unicast_client_unregister_cb(&bap_callbacks);
                if ((first_error == 0) && (result != 0))
                {
                    first_error = result;
                }
                if (result == 0)
                {
                    cap_unicast.bap_callbacks_registered = false;
                }
            }
            return first_error;
        }
    } // namespace

    /** @brief 마지막 공개 오류와 stack 원본 오류를 기록합니다. */
    Error CapUnicastInitiator::record(Error error, int native_code) noexcept
    {
        last_error_ = error;
        native_code_ = native_code;
        if ((error == Error::stack_error) || (error == Error::not_connected) ||
            (error == Error::unsupported))
        {
            stage_ = CapUnicastStage::failed;
        }
        return error;
    }

    /** @brief 연결을 참조하고 CAP Acceptor 확인 절차를 시작합니다. */
    Error CapUnicastInitiator::begin(const BLEConnectionHandle &connection) noexcept
    {
        if (!connection.valid())
        {
            return record(Error::invalid_argument);
        }
        if (started_)
        {
            return record(Error::already_started);
        }
        if (cap_unicast.owner != nullptr)
        {
            return record(Error::busy);
        }
        bt_conn *native = internal::referenceConnection(connection);
        if (native == nullptr)
        {
            return record(Error::not_connected);
        }

        cap_unicast = {};
        cap_unicast.owner = this;
        cap_unicast.connection = native;
        bt_cap_stream_ops_register(&cap_unicast.stream, &stream_callbacks);

        int result = bt_bap_unicast_client_register_cb(&bap_callbacks);
        if (result != 0)
        {
            bt_conn_unref(native);
            cap_unicast = {};
            return record(Error::stack_error, result);
        }
        cap_unicast.bap_callbacks_registered = true;
        result = bt_cap_initiator_register_cb(&cap_callbacks);
        if (result != 0)
        {
            static_cast<void>(bt_bap_unicast_client_unregister_cb(&bap_callbacks));
            bt_conn_unref(native);
            cap_unicast = {};
            return record(Error::stack_error, result);
        }
        cap_unicast.cap_callbacks_registered = true;
        cap_unicast.wait_started = k_uptime_get_32();
        started_ = true;
        stage_ = CapUnicastStage::securing;
        last_step_ = CapUnicastStep::security;
        if (bt_conn_get_security(native) >= BT_SECURITY_L2)
        {
            atomic_set(&cap_unicast.event, static_cast<int>(Event::secured));
        }
        return record(Error::none);
    }

    /** @brief callback 결과에 따라 CAS, PACS/ASCS와 CAP 완료를 진행합니다. */
    void CapUnicastInitiator::poll() noexcept
    {
        if (!started_ || (stage_ == CapUnicastStage::failed))
        {
            return;
        }
        const int callback_error = atomic_set(&cap_unicast.error, 0);
        if (callback_error != 0)
        {
            static_cast<void>(record(Error::stack_error, callback_error));
            return;
        }
        if ((stage_ == CapUnicastStage::securing) && (atomic_get(&cap_unicast.event) == 0))
        {
            if (bt_conn_get_security(cap_unicast.connection) >= BT_SECURITY_L2)
            {
                atomic_set(&cap_unicast.event, static_cast<int>(Event::secured));
            }
            else if (!cap_unicast.security_requested &&
                     (bt_gatt_get_mtu(cap_unicast.connection) > 23U))
            {
                cap_unicast.security_requested = true;
                const int result = bt_conn_set_security(cap_unicast.connection, BT_SECURITY_L2);
                if ((result != 0) && (result != -EBUSY))
                {
                    static_cast<void>(record(Error::stack_error, result));
                    return;
                }
            }
        }
        if (((stage_ == CapUnicastStage::securing) ||
             (stage_ == CapUnicastStage::discovering_common_audio_service) ||
             (stage_ == CapUnicastStage::discovering_audio_streams) ||
             (stage_ == CapUnicastStage::starting) || (stage_ == CapUnicastStage::stopping)) &&
            ((k_uptime_get_32() - cap_unicast.wait_started) > procedure_timeout_ms))
        {
            static_cast<void>(record(Error::stack_error, -ETIMEDOUT));
            return;
        }

        const Event event = static_cast<Event>(atomic_set(&cap_unicast.event, 0));
        if (event == Event::none)
        {
            return;
        }

        int result = 0;
        if (event == Event::secured)
        {
            stage_ = CapUnicastStage::discovering_common_audio_service;
            last_step_ = CapUnicastStep::common_audio_service;
            cap_unicast.wait_started = k_uptime_get_32();
            result = bt_cap_initiator_unicast_discover(cap_unicast.connection);
        }
        else if (event == Event::common_audio_service_discovered)
        {
            stage_ = CapUnicastStage::discovering_audio_streams;
            last_step_ = CapUnicastStep::audio_streams;
            cap_unicast.wait_started = k_uptime_get_32();
            result = bt_bap_unicast_client_discover(cap_unicast.connection, BT_AUDIO_DIR_SINK);
        }
        else if (event == Event::audio_streams_discovered)
        {
            if ((cap_unicast.sink == nullptr) || (atomic_get(&cap_unicast.codec_found) == 0))
            {
                static_cast<void>(record(Error::unsupported));
                return;
            }
            bt_cap_unicast_group_stream_param transmit = {};
            transmit.stream = &cap_unicast.stream;
            transmit.qos_cfg = &cap_unicast_preset.qos;
            bt_cap_unicast_group_stream_pair_param pair = {};
            pair.tx_param = &transmit;
            bt_cap_unicast_group_param parameters = {};
            parameters.params_count = 1U;
            parameters.params = &pair;
            parameters.packing = BT_ISO_PACKING_SEQUENTIAL;
            last_step_ = CapUnicastStep::group;
            result = bt_cap_unicast_group_create(&parameters, &cap_unicast.group);
            if (result == 0)
            {
                stage_ = CapUnicastStage::ready;
            }
        }
        else if (event == Event::started)
        {
            atomic_set(&cap_unicast.cancel_requested, 0);
            stage_ = CapUnicastStage::streaming;
        }
        else if (event == Event::stopped)
        {
            atomic_set(&cap_unicast.cancel_requested, 0);
            atomic_set(&cap_unicast.streaming, 0);
            atomic_set(&cap_unicast.expected_disconnect, 1);
            stage_ = CapUnicastStage::ready;
        }
        else if (event == Event::cancelled)
        {
            atomic_set(&cap_unicast.streaming, 0);
            atomic_set(&cap_unicast.expected_disconnect, 1);
            stage_ = CapUnicastStage::cancelled;
            last_error_ = Error::none;
            native_code_ = -ECANCELED;
        }
        if (result != 0)
        {
            static_cast<void>(record(Error::stack_error, result));
        }
    }

    /** @brief 준비된 ad-hoc group의 CAP 시작 절차를 실행합니다. */
    Error CapUnicastInitiator::start() noexcept
    {
        if (!started_ || (stage_ != CapUnicastStage::ready) || (cap_unicast.group == nullptr))
        {
            return record(Error::not_ready);
        }
        cap_unicast.start_stream = {};
        cap_unicast.start_stream.member.member = cap_unicast.connection;
        cap_unicast.start_stream.stream = &cap_unicast.stream;
        cap_unicast.start_stream.ep = cap_unicast.sink;
        cap_unicast.start_stream.codec_cfg = &cap_unicast_preset.codec_cfg;
        cap_unicast.start_parameters = {};
        cap_unicast.start_parameters.type = BT_CAP_SET_TYPE_AD_HOC;
        cap_unicast.start_parameters.count = 1U;
        cap_unicast.start_parameters.stream_params = &cap_unicast.start_stream;
        atomic_set(&cap_unicast.cancel_requested, 0);
        atomic_set(&cap_unicast.cancelled, 0);
        atomic_set(&cap_unicast.failed_on_peer, 0);
        atomic_set(&cap_unicast.expected_disconnect, 0);
        last_step_ = CapUnicastStep::start;
        const int result = bt_cap_initiator_unicast_audio_start(&cap_unicast.start_parameters);
        if (result != 0)
        {
            return record(Error::stack_error, result);
        }
        stage_ = CapUnicastStage::starting;
        cap_unicast.wait_started = k_uptime_get_32();
        return record(Error::none);
    }

    /** @brief 진행 중인 CAP 절차를 명시적으로 취소합니다. */
    Error CapUnicastInitiator::cancel() noexcept
    {
        if (!started_ ||
            ((stage_ != CapUnicastStage::starting) && (stage_ != CapUnicastStage::stopping)))
        {
            return record(Error::not_ready);
        }
        atomic_set(&cap_unicast.cancel_requested, 1);
        last_step_ = CapUnicastStep::cancel;
        const int result = bt_cap_initiator_unicast_audio_cancel();
        if (result == -EALREADY)
        {
            atomic_set(&cap_unicast.cancel_requested, 0);
            return record(Error::not_ready, result);
        }
        if (result != 0)
        {
            atomic_set(&cap_unicast.cancel_requested, 0);
            return record(Error::stack_error, result);
        }
        cap_unicast.wait_started = k_uptime_get_32();
        return record(Error::none);
    }

    /** @brief streaming CAP stream을 release까지 포함해 중단합니다. */
    Error CapUnicastInitiator::stop() noexcept
    {
        if (!started_ || (stage_ != CapUnicastStage::streaming))
        {
            return record(Error::not_ready);
        }
        cap_unicast.stop_streams[0] = &cap_unicast.stream;
        cap_unicast.stop_parameters = {};
        cap_unicast.stop_parameters.type = BT_CAP_SET_TYPE_AD_HOC;
        cap_unicast.stop_parameters.count = 1U;
        cap_unicast.stop_parameters.streams = cap_unicast.stop_streams;
        cap_unicast.stop_parameters.release = true;
        atomic_set(&cap_unicast.cancel_requested, 0);
        atomic_set(&cap_unicast.cancelled, 0);
        atomic_set(&cap_unicast.failed_on_peer, 0);
        atomic_set(&cap_unicast.expected_disconnect, 1);
        last_step_ = CapUnicastStep::stop;
        const int result = bt_cap_initiator_unicast_audio_stop(&cap_unicast.stop_parameters);
        if (result != 0)
        {
            atomic_set(&cap_unicast.expected_disconnect, 0);
            return record(Error::stack_error, result);
        }
        stage_ = CapUnicastStage::stopping;
        cap_unicast.wait_started = k_uptime_get_32();
        return record(Error::none);
    }

    /** @brief group과 callback 등록, 연결 참조를 반환합니다. */
    Error CapUnicastInitiator::end() noexcept
    {
        if (!started_)
        {
            return record(Error::not_started);
        }
        if ((stage_ == CapUnicastStage::starting) || (stage_ == CapUnicastStage::stopping) ||
            (stage_ == CapUnicastStage::streaming) ||
            (cap_unicast.stream.bap_stream.conn != nullptr))
        {
            return record(Error::busy);
        }
        last_step_ = CapUnicastStep::cleanup;
        const int result = releaseResources();
        if (result != 0)
        {
            return record(Error::stack_error, result);
        }
        bt_conn_unref(cap_unicast.connection);
        cap_unicast = {};
        started_ = false;
        stage_ = CapUnicastStage::idle;
        return record(Error::none);
    }

    /** @brief CAP start를 요청할 수 있는 상태를 반환합니다. */
    bool CapUnicastInitiator::ready() const noexcept
    {
        return started_ && (stage_ == CapUnicastStage::ready);
    }

    /** @brief callback과 stream 상태가 모두 확정한 송신 상태를 반환합니다. */
    bool CapUnicastInitiator::streaming() const noexcept
    {
        return started_ && (stage_ == CapUnicastStage::streaming) &&
               (atomic_get(&cap_unicast.streaming) != 0);
    }

    /** @brief 명시적 취소 callback 수신 여부를 반환합니다. */
    bool CapUnicastInitiator::cancelled() const noexcept
    {
        return started_ && (atomic_get(&cap_unicast.cancelled) != 0);
    }

    /** @brief CAP 완료 callback이 특정 peer 실패를 보고했는지 반환합니다. */
    bool CapUnicastInitiator::failedOnPeer() const noexcept
    {
        return started_ && (atomic_get(&cap_unicast.failed_on_peer) != 0);
    }

    /** @brief 현재 공개 비동기 단계를 반환합니다. */
    CapUnicastStage CapUnicastInitiator::stage() const noexcept
    {
        return stage_;
    }

    /** @brief 마지막 공개 CAP 작업을 반환합니다. */
    CapUnicastStep CapUnicastInitiator::lastStep() const noexcept
    {
        return last_step_;
    }

    /** @brief CAP CIS로 LC3 frame 하나를 전송합니다. */
    Error CapUnicastInitiator::sendFrame(const std::uint8_t (&frame)[40]) noexcept
    {
        if (!streaming())
        {
            return record(Error::not_ready);
        }
        last_step_ = CapUnicastStep::send;
        net_buf *buffer = net_buf_alloc(&cap_unicast_tx_pool, K_NO_WAIT);
        if (buffer == nullptr)
        {
            return record(Error::busy, -ENOMEM);
        }
        net_buf_reserve(buffer, BT_ISO_CHAN_SEND_RESERVE);
        net_buf_add_mem(buffer, frame, frame_octets);
        const std::uint16_t sequence =
            static_cast<std::uint16_t>(atomic_get(&cap_unicast.sequence));
        const int result = bt_cap_stream_send(&cap_unicast.stream, buffer, sequence);
        if (result != 0)
        {
            net_buf_unref(buffer);
            return record(Error::stack_error, result);
        }
        atomic_inc(&cap_unicast.sequence);
        atomic_inc(&cap_unicast.sent);
        return record(Error::none);
    }

    /** @brief controller가 수락한 CAP CIS frame 수를 반환합니다. */
    std::uint32_t CapUnicastInitiator::sentFrames() const noexcept
    {
        return started_ ? static_cast<std::uint32_t>(atomic_get(&cap_unicast.sent)) : 0U;
    }

    /** @brief 마지막 공개 오류를 반환합니다. */
    Error CapUnicastInitiator::lastError() const noexcept
    {
        return last_error_;
    }

    /** @brief 마지막 CAP/GATT/controller 원본 오류를 반환합니다. */
    int CapUnicastInitiator::nativeCode() const noexcept
    {
        const int callback_error = atomic_get(&cap_unicast.error);
        return callback_error != 0 ? callback_error : native_code_;
    }
} // namespace nucode::ble::audio

#else

namespace nucode::ble::audio
{
    Error CapUnicastInitiator::begin(const BLEConnectionHandle &) noexcept
    {
        return record(Error::not_ready);
    }

    void CapUnicastInitiator::poll() noexcept
    {
    }

    Error CapUnicastInitiator::start() noexcept
    {
        return record(Error::not_ready);
    }

    Error CapUnicastInitiator::cancel() noexcept
    {
        return record(Error::not_ready);
    }

    Error CapUnicastInitiator::stop() noexcept
    {
        return record(Error::not_ready);
    }

    Error CapUnicastInitiator::end() noexcept
    {
        return record(Error::not_started);
    }

    bool CapUnicastInitiator::ready() const noexcept
    {
        return false;
    }

    bool CapUnicastInitiator::streaming() const noexcept
    {
        return false;
    }

    bool CapUnicastInitiator::cancelled() const noexcept
    {
        return false;
    }

    bool CapUnicastInitiator::failedOnPeer() const noexcept
    {
        return false;
    }

    CapUnicastStage CapUnicastInitiator::stage() const noexcept
    {
        return stage_;
    }

    CapUnicastStep CapUnicastInitiator::lastStep() const noexcept
    {
        return last_step_;
    }

    Error CapUnicastInitiator::sendFrame(const std::uint8_t (&)[40]) noexcept
    {
        return record(Error::not_ready);
    }

    std::uint32_t CapUnicastInitiator::sentFrames() const noexcept
    {
        return 0U;
    }

    Error CapUnicastInitiator::lastError() const noexcept
    {
        return last_error_;
    }

    int CapUnicastInitiator::nativeCode() const noexcept
    {
        return native_code_;
    }

    Error CapUnicastInitiator::record(Error error, int native_code) noexcept
    {
        last_error_ = error;
        native_code_ = native_code;
        return error;
    }
} // namespace nucode::ble::audio

#endif
