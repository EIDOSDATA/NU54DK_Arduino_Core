/**
 * @file NUCODE_BLE_ISO_RawCis.cpp
 * @brief Arduino 사용자 SDU를 CIS HCI 경로로 송수신합니다.
 * SPDX-License-Identifier: MIT
 */

#include "NUCODE_BLE_ISO.h"

#if !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE) && \
    (defined(CONFIG_NUCODE_BLE_ISO_MODE_CIS_CENTRAL) || \
     defined(CONFIG_NUCODE_BLE_ISO_MODE_CIS_PERIPHERAL))

#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/conn.h>
#include <zephyr/bluetooth/gap.h>
#include <zephyr/bluetooth/iso.h>
#include <zephyr/kernel.h>
#include <zephyr/net_buf.h>
#include <zephyr/sys/atomic.h>

#include <errno.h>
#include <string.h>

namespace
{
    using nucode::ble::iso::CisFrame;
    using nucode::ble::iso::Error;
    using nucode::ble::iso::RawCis;

#if defined(CONFIG_NUCODE_BLE_ISO_MODE_CIS_CENTRAL)
    constexpr bool central_role = true;
#else
    constexpr bool central_role = false;
#endif

    constexpr std::size_t session_length = 16U;
    constexpr std::size_t frame_capacity = 16U;
    RawCis *owner = nullptr;
    std::uint8_t session_id[session_length] = {};
    struct bt_conn *acl = nullptr;
    struct bt_iso_cig *cig = nullptr;
    struct bt_iso_chan channel = {};
    bool started = false;
    bool stopping = false;
    bool scan_active = false;
    bool advertising_active = false;
    bool server_registered = false;
    bool bluetooth_enabled = false;
    std::int64_t stop_started_ms = 0;
    std::uint16_t next_sequence = 0U;
    atomic_t channel_ready = ATOMIC_INIT(0);
    atomic_t native_error = ATOMIC_INIT(0);

    K_MSGQ_DEFINE(receive_queue, sizeof(CisFrame), 8U, 4U);
    NET_BUF_POOL_FIXED_DEFINE(transmit_pool, 4U,
                              BT_ISO_SDU_BUF_SIZE(CONFIG_BT_ISO_TX_MTU),
                              CONFIG_BT_CONN_TX_USER_DATA_SIZE, nullptr);

    /** @brief 콜백의 첫 native 오류를 보존합니다. */
    void recordError(int result)
    {
        if (result != 0 && atomic_get(&native_error) == 0)
        {
            atomic_set(&native_error, result);
        }
    }

    /** @brief 유효 SDU를 소유권이 분리된 bounded queue에 복사합니다. */
    void received(struct bt_iso_chan *received_channel,
                  const struct bt_iso_recv_info *information, struct net_buf *buffer)
    {
        if (!started || stopping || received_channel != &channel ||
            information == nullptr || buffer == nullptr ||
            (information->flags & BT_ISO_FLAGS_VALID) == 0U)
        {
            return;
        }
        if (buffer->len == 0U || buffer->len > frame_capacity)
        {
            recordError(-EMSGSIZE);
            return;
        }
        CisFrame frame = {};
        frame.length = static_cast<std::uint8_t>(buffer->len);
        frame.sequence = information->seq_num;
        frame.timestamp_valid = (information->flags & BT_ISO_FLAGS_TS) != 0U;
        frame.timestamp_us = information->ts;
        memcpy(frame.data, buffer->data, buffer->len);
        if (k_msgq_put(&receive_queue, &frame, K_NO_WAIT) != 0)
        {
            recordError(-ENOBUFS);
        }
    }

    /** @brief 현재 role의 HCI data path를 연결합니다. */
    void connected(struct bt_iso_chan *connected_channel)
    {
        if (!started || stopping || connected_channel != &channel)
        {
            return;
        }
        const struct bt_iso_chan_path path = {
            .pid = BT_ISO_DATA_PATH_HCI,
            .format = BT_HCI_CODING_FORMAT_TRANSPARENT,
        };
        const std::uint8_t direction = central_role ?
            BT_HCI_DATAPATH_DIR_HOST_TO_CTLR : BT_HCI_DATAPATH_DIR_CTLR_TO_HOST;
        const int result = bt_iso_setup_data_path(connected_channel, direction, &path);
        if (result != 0)
        {
            recordError(result);
            return;
        }
        atomic_set(&channel_ready, 1);
    }

    /** @brief 해제 이후 전송 가능 상태를 즉시 지웁니다. */
    void disconnected(struct bt_iso_chan *disconnected_channel, std::uint8_t reason)
    {
        static_cast<void>(reason);
        if (disconnected_channel == &channel)
        {
            atomic_set(&channel_ready, 0);
        }
    }

    struct bt_iso_chan_ops operations = {
        .connected = connected,
        .disconnected = disconnected,
        .recv = received,
    };
    struct bt_iso_chan_io_qos transmit_qos = {
        .sdu = CONFIG_BT_ISO_TX_MTU,
        .phy = BT_GAP_LE_PHY_2M,
        .rtn = 2U,
    };
    struct bt_iso_chan_io_qos receive_qos = {
        .sdu = CONFIG_BT_ISO_RX_MTU,
        .phy = BT_GAP_LE_PHY_2M,
    };
    struct bt_iso_chan_qos qos = {
        .rx = &receive_qos,
        .tx = &transmit_qos,
    };

    /** @brief 이 객체가 소유한 ACL에서만 ISO channel을 수락합니다. */
    int acceptIso(const struct bt_iso_accept_info *information,
                  struct bt_iso_chan **accepted_channel)
    {
        if (!started || stopping || information == nullptr ||
            accepted_channel == nullptr || information->acl != acl ||
            channel.iso != nullptr)
        {
            return -ENOMEM;
        }
        *accepted_channel = &channel;
        return 0;
    }

    struct bt_iso_server server = {
        .accept = acceptIso,
    };

    /** @brief 정확한 16-byte 사용자 session ID의 광고만 선택합니다. */
    bool matchingAdvertisement(struct bt_data *data, void *context)
    {
        bool *matched = static_cast<bool *>(context);
        if (data->type == BT_DATA_MANUFACTURER_DATA &&
            data->data_len == session_length &&
            memcmp(data->data, session_id, session_length) == 0)
        {
            *matched = true;
            return false;
        }
        return true;
    }

    /** @brief session ID가 일치하는 peripheral에만 ACL을 요청합니다. */
    void found(const bt_addr_le_t *address, std::int8_t rssi, std::uint8_t type,
               struct net_buf_simple *advertisement)
    {
        static_cast<void>(rssi);
        if (!started || stopping || !scan_active || acl != nullptr ||
            type != BT_GAP_ADV_TYPE_ADV_IND)
        {
            return;
        }
        bool matched = false;
        bt_data_parse(advertisement, matchingAdvertisement, &matched);
        if (!matched)
        {
            return;
        }
        const int stop_result = bt_le_scan_stop();
        if (stop_result != 0)
        {
            recordError(stop_result);
            return;
        }
        scan_active = false;
        const struct bt_le_conn_param parameters =
            BT_LE_CONN_PARAM_INIT(BT_GAP_MS_TO_CONN_INTERVAL(30),
                                  BT_GAP_MS_TO_CONN_INTERVAL(30), 0U,
                                  BT_GAP_MS_TO_CONN_TIMEOUT(4000));
        recordError(bt_conn_le_create(address, BT_CONN_LE_CREATE_CONN,
                                      &parameters, &acl));
    }

    /** @brief 같은 ACL이 연결되면 central에서 CIS를 엽니다. */
    void aclConnected(struct bt_conn *connection, std::uint8_t error)
    {
        if (!started || stopping)
        {
            return;
        }
        if (error != 0U)
        {
            recordError(-static_cast<int>(error));
            return;
        }
        if (!central_role && acl == nullptr)
        {
            acl = bt_conn_ref(connection);
        }
        if (connection != acl)
        {
            recordError(-EINVAL);
            return;
        }
        if (central_role)
        {
            const struct bt_iso_connect_param parameter = {
                .iso_chan = &channel,
                .acl = connection,
            };
            recordError(bt_iso_chan_connect(&parameter, 1U));
        }
    }

    /** @brief 끊어진 ACL 참조를 한 번만 반환합니다. */
    void aclDisconnected(struct bt_conn *connection, std::uint8_t reason)
    {
        if (connection == acl)
        {
            bt_conn_unref(acl);
            acl = nullptr;
            if (central_role && started && !stopping)
            {
                recordError(-static_cast<int>(reason));
            }
        }
        atomic_set(&channel_ready, 0);
    }

    BT_CONN_CB_DEFINE(acl_callbacks) = {
        .connected = aclConnected,
        .disconnected = aclDisconnected,
    };

    /** @brief 이전 callback이 끝난 뒤 CIG/server와 queue를 반환합니다. */
    Error finishStop()
    {
        if (!stopping)
        {
            return Error::none;
        }
        if (acl != nullptr || channel.state == BT_ISO_STATE_CONNECTED ||
            channel.state == BT_ISO_STATE_CONNECTING)
        {
            if (k_uptime_get() - stop_started_ms > 30000)
            {
                recordError(-ETIMEDOUT);
                return Error::transport_failure;
            }
            return Error::busy;
        }
        if (cig != nullptr)
        {
            const int result = bt_iso_cig_terminate(cig);
            if (result != 0)
            {
                recordError(result);
                return Error::transport_failure;
            }
            cig = nullptr;
        }
        if (server_registered)
        {
            const int result = bt_iso_server_unregister(&server);
            if (result != 0)
            {
                recordError(result);
                return Error::transport_failure;
            }
            server_registered = false;
        }
        k_msgq_purge(&receive_queue);
        memset(&channel, 0, sizeof(channel));
        started = false;
        stopping = false;
        owner = nullptr;
        atomic_set(&channel_ready, 0);
        return Error::none;
    }
}

namespace nucode::ble::iso
{
    /** @brief CIS 자원을 한 객체에 예약하고 정확한 session peer를 찾습니다. */
    Error RawCis::begin(Role role, const std::uint8_t requested_id[16]) noexcept
    {
        const Role configured = central_role ? Role::cis_central : Role::cis_peripheral;
        if (role != configured)
        {
            return Error::configuration_mismatch;
        }
        if (requested_id == nullptr)
        {
            return Error::invalid_argument;
        }
        if (owner != nullptr || started || stopping)
        {
            return Error::busy;
        }
        owner = this;
        memcpy(session_id, requested_id, session_length);
        atomic_set(&native_error, 0);
        atomic_set(&channel_ready, 0);
        next_sequence = 0U;
        k_msgq_purge(&receive_queue);
        memset(&channel, 0, sizeof(channel));
        channel.ops = &operations;
        channel.qos = &qos;
        if (!bluetooth_enabled)
        {
            const int result = bt_enable(nullptr);
            if (result != 0 && result != -EALREADY)
            {
                recordError(result);
                owner = nullptr;
                return Error::transport_failure;
            }
            bluetooth_enabled = true;
        }
        started = true;
        if (central_role)
        {
            struct bt_iso_chan *channels[] = {&channel};
            const struct bt_iso_cig_param parameter = {
                .cis_channels = channels,
                .num_cis = 1U,
                .c_to_p_interval = 10000U,
                .p_to_c_interval = 10000U,
                .c_to_p_latency = 20U,
                .p_to_c_latency = 20U,
                .sca = BT_GAP_SCA_UNKNOWN,
                .packing = BT_ISO_PACKING_SEQUENTIAL,
                .framing = BT_ISO_FRAMING_UNFRAMED,
            };
            const int result = bt_iso_cig_create(&parameter, &cig);
            if (result != 0)
            {
                recordError(result);
                started = false;
                owner = nullptr;
                return Error::transport_failure;
            }
            const int scan_result = bt_le_scan_start(BT_LE_SCAN_PASSIVE, found);
            if (scan_result != 0)
            {
                recordError(scan_result);
                (void)bt_iso_cig_terminate(cig);
                cig = nullptr;
                started = false;
                owner = nullptr;
                return Error::transport_failure;
            }
            scan_active = true;
        }
        else
        {
            const int register_result = bt_iso_server_register(&server);
            if (register_result != 0)
            {
                recordError(register_result);
                started = false;
                owner = nullptr;
                return Error::transport_failure;
            }
            server_registered = true;
            const struct bt_data data[] = {
                BT_DATA_BYTES(BT_DATA_FLAGS, (BT_LE_AD_GENERAL | BT_LE_AD_NO_BREDR)),
                BT_DATA(BT_DATA_MANUFACTURER_DATA, session_id, sizeof(session_id)),
            };
            const int result = bt_le_adv_start(BT_LE_ADV_CONN_FAST_1, data,
                                               ARRAY_SIZE(data), nullptr, 0U);
            if (result != 0)
            {
                recordError(result);
                (void)bt_iso_server_unregister(&server);
                server_registered = false;
                started = false;
                owner = nullptr;
                return Error::transport_failure;
            }
            advertising_active = true;
        }
        return Error::none;
    }

    /** @brief callback 해제 중이면 반환 완료까지 상태를 진행합니다. */
    Error RawCis::poll() noexcept
    {
        if (owner != this)
        {
            return Error::not_started;
        }
        const Error cleanup = finishStop();
        if (cleanup == Error::transport_failure)
        {
            return cleanup;
        }
        return atomic_get(&native_error) == 0 ? Error::none : Error::transport_failure;
    }

    /** @brief 사용자가 만든 SDU를 전송 pool에서 복사해 HCI로 전달합니다. */
    Error RawCis::sendFrame(const std::uint8_t *data, std::size_t length) noexcept
    {
        if (data == nullptr || length == 0U || length > frame_capacity)
        {
            return Error::invalid_argument;
        }
        if (owner != this || !started || stopping || !central_role ||
            atomic_get(&channel_ready) == 0)
        {
            return Error::not_ready;
        }
        struct net_buf *buffer = net_buf_alloc(&transmit_pool, K_NO_WAIT);
        if (buffer == nullptr)
        {
            return Error::busy;
        }
        net_buf_reserve(buffer, BT_ISO_CHAN_SEND_RESERVE);
        net_buf_add_mem(buffer, data, length);
        const int result = bt_iso_chan_send(&channel, buffer, next_sequence);
        if (result != 0)
        {
            net_buf_unref(buffer);
            recordError(result);
            return Error::transport_failure;
        }
        ++next_sequence;
        return Error::none;
    }

    /** @brief 수신 queue에서 frame 하나를 사용자 소유 구조체로 옮깁니다. */
    bool RawCis::readFrame(CisFrame &frame) noexcept
    {
        if (owner != this || !started || stopping)
        {
            return false;
        }
        return k_msgq_get(&receive_queue, &frame, K_NO_WAIT) == 0;
    }

    /** @brief ACL과 ISO 연결을 비동기 해제하고 main thread 복귀를 보장합니다. */
    Error RawCis::stop() noexcept
    {
        if (owner != this || !started)
        {
            return Error::not_started;
        }
        if (stopping)
        {
            return Error::busy;
        }
        stopping = true;
        stop_started_ms = k_uptime_get();
        atomic_set(&channel_ready, 0);
        if (scan_active)
        {
            (void)bt_le_scan_stop();
            scan_active = false;
        }
        if (advertising_active)
        {
            (void)bt_le_adv_stop();
            advertising_active = false;
        }
        if (central_role && channel.state == BT_ISO_STATE_CONNECTED)
        {
            (void)bt_iso_chan_disconnect(&channel);
        }
        if (acl != nullptr)
        {
            (void)bt_conn_disconnect(acl, BT_HCI_ERR_REMOTE_USER_TERM_CONN);
        }
        return Error::none;
    }

    /** @brief HCI path setup이 끝난 연결만 참으로 반환합니다. */
    bool RawCis::connected() const noexcept
    {
        return owner == this && started && !stopping &&
               atomic_get(&channel_ready) != 0;
    }

    /** @brief 모든 connection과 ISO 자원이 반환되었는지 확인합니다. */
    bool RawCis::stopped() const noexcept
    {
        return owner != this;
    }

    /** @brief 최근 Zephyr 오류를 공개 enum과 분리해 진단합니다. */
    int RawCis::nativeError() const noexcept
    {
        return owner == this ? atomic_get(&native_error) : 0;
    }

    /** @brief 빌드 시각의 Core revision을 검증 가능한 값으로 노출합니다. */
    const char *RawCis::buildRevision() noexcept
    {
        return NUCODE_CORE_REVISION;
    }
}

#endif
