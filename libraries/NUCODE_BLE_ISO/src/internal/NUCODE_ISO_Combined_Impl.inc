#define NUCODE_BLE_ISO_LIBRARY_BACKEND
/**
 * @file main.cpp
 * @brief Arduino runtime에서 CIS 수신 SDU를 한 BIS로 실제 전달하고 재시작을 검증합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <Arduino.h>

#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/conn.h>
#include <zephyr/bluetooth/gap.h>
#include <zephyr/bluetooth/hci_types.h>
#include <zephyr/bluetooth/iso.h>
#include <zephyr/kernel.h>
#include <zephyr/net_buf.h>
#include <zephyr/sys/atomic.h>
#include <zephyr/sys/byteorder.h>

#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

namespace
{
    constexpr uint16_t sdu_count = 100U;
    constexpr size_t sdu_length = 8U;
    constexpr size_t nonce_length = 32U;
    constexpr uint32_t stream_interval_us = 20000U;
    constexpr uint32_t forward_period_ms = 20U;
    constexpr char start_prefix[] = "M31COMB|1|START|nonce=";
    constexpr char start_suffix[] = "|count=100";
    constexpr char stop_prefix[] = "M31COMB|1|STOP|nonce=";
    char command[sizeof(start_prefix) + nonce_length + sizeof(start_suffix)] = {};
    size_t command_length = 0U;
    char nonce[nonce_length + 1U] = {};
    uint8_t nonce_bytes[nonce_length / 2U] = {};
    bool started = false;
    bool finished = false;
    bool stopping = false;
    bool enabled = false;
    bool cis_end = false;
    bool forwarding = false;
    bool big_disconnected = false;
    bool scan_active = false;
    int64_t stop_start_ms = 0;
    int last_sequence = -1;
    uint32_t seen[(sdu_count + 31U) / 32U] = {};
    atomic_t cis_received = ATOMIC_INIT(0);
    atomic_t cis_empty = ATOMIC_INIT(0);
    atomic_t bis_sent = ATOMIC_INIT(0);
    atomic_t corrupt = ATOMIC_INIT(0);
    atomic_t duplicate = ATOMIC_INIT(0);
    atomic_t cross_stream = ATOMIC_INIT(0);
    struct bt_conn *acl = nullptr;
    struct bt_iso_cig *cig = nullptr;
    struct bt_iso_big *big = nullptr;
    struct bt_le_ext_adv *advertiser = nullptr;
    struct bt_iso_chan cis_channel = {};
    struct bt_iso_chan bis_channel = {};
    struct bt_iso_chan_io_qos cis_receive_qos = {};
    struct bt_iso_chan_io_qos bis_transmit_qos = {};
    struct bt_iso_chan_qos cis_qos = {};
    struct bt_iso_chan_qos bis_qos = {};
    struct k_work_delayable forward_work;

    K_MUTEX_DEFINE(output_mutex);
    K_MSGQ_DEFINE(forward_queue, sdu_length, 16U, 4U);
    NET_BUF_POOL_FIXED_DEFINE(bis_tx_pool, 4U, BT_ISO_SDU_BUF_SIZE(CONFIG_BT_ISO_TX_MTU),
                              CONFIG_BT_CONN_TX_USER_DATA_SIZE, nullptr);

    /** @brief 여러 Bluetooth callback의 UART 행을 한 단위로 출력합니다. */
    void emit(const char *line)
    {
        k_mutex_lock(&output_mutex, K_FOREVER);
        Serial.println(line);
        k_mutex_unlock(&output_mutex);
    }

    /** @brief 첫 실패의 stage/code만 유한 행으로 보고하고 전달을 중단합니다. */
    void fail(const char *stage, int code)
    {
        if (finished)
        {
            return;
        }
        char line[160] = {};
        snprintf(line, sizeof(line), "M31COMB|1|FAIL|nonce=%s|stage=%s|code=%d",
                 nonce, stage, code);
        emit(line);
        finished = true;
    }

    /** @brief 128-bit session nonce의 소문자 hex만 byte로 수락합니다. */
    bool parseNonce()
    {
        for (size_t index = 0U; index < sizeof(nonce_bytes); ++index)
        {
            const auto nibble = [](char value) -> int
            {
                if (value >= '0' && value <= '9')
                {
                    return value - '0';
                }
                if (value >= 'a' && value <= 'f')
                {
                    return value - 'a' + 10;
                }
                return -1;
            };
            const int upper = nibble(nonce[index * 2U]);
            const int lower = nibble(nonce[index * 2U + 1U]);
            if (upper < 0 || lower < 0)
            {
                return false;
            }
            nonce_bytes[index] = static_cast<uint8_t>((upper << 4U) | lower);
        }
        return true;
    }

    /** @brief CIS peer와 BIS receiver가 공유할 SDU checksum을 계산합니다. */
    uint32_t checksum(uint16_t sequence)
    {
        const uint32_t marker = static_cast<uint32_t>(nonce_bytes[0]) |
                                (static_cast<uint32_t>(nonce_bytes[1]) << 8U);
        return 0x31b15000U ^ (static_cast<uint32_t>(sequence) * 0x9e3779b1U) ^ marker;
    }

    /** @brief 한 CIS의 유효 payload만 검사해 BIS 전달 queue에 복사합니다. */
    void cisReceived(struct bt_iso_chan *channel, const struct bt_iso_recv_info *information,
                     struct net_buf *buffer)
    {
        (void)channel;
        if (!started || finished || stopping)
        {
            return;
        }
        if (information == nullptr || buffer == nullptr)
        {
            atomic_inc(&corrupt);
            fail("cis_record", -EBADMSG);
            return;
        }
        if ((information->flags & BT_ISO_FLAGS_VALID) == 0U)
        {
            atomic_inc(&cis_empty);
            return;
        }
        if (buffer->len != sdu_length)
        {
            atomic_inc(&corrupt);
            fail("cis_length", -EBADMSG);
            return;
        }
        const uint16_t sequence = sys_get_le16(buffer->data);
        const uint16_t marker = sys_get_le16(buffer->data + 2U);
        const uint16_t expected_marker = static_cast<uint16_t>(nonce_bytes[0]) |
                                         (static_cast<uint16_t>(nonce_bytes[1]) << 8U);
        if (sequence >= sdu_count || marker != expected_marker ||
            sys_get_le32(buffer->data + 4U) != checksum(sequence))
        {
            atomic_inc(&corrupt);
            fail("cis_payload", -EBADMSG);
            return;
        }
        const uint32_t bit = 1U << (sequence % 32U);
        uint32_t &word = seen[sequence / 32U];
        if ((word & bit) != 0U || static_cast<int>(sequence) <= last_sequence)
        {
            atomic_inc(&duplicate);
            fail("cis_sequence", -EALREADY);
            return;
        }
        if (k_msgq_put(&forward_queue, buffer->data, K_NO_WAIT) != 0)
        {
            fail("forward_queue_full", -ENOMEM);
            return;
        }
        word |= bit;
        last_sequence = sequence;
        atomic_inc(&cis_received);
        if (!forwarding && k_msgq_num_used_get(&forward_queue) >= 4U)
        {
            forwarding = true;
            k_work_schedule(&forward_work, K_MSEC(forward_period_ms));
        }
        if (sequence == sdu_count - 1U)
        {
            cis_end = true;
            char line[170] = {};
            snprintf(line, sizeof(line),
                     "M31COMB|1|CIS_RX_END|nonce=%s|received=%ld|corrupt=%ld|duplicate=%ld|cross_stream=%ld|empty_slots=%ld",
                     nonce, atomic_get(&cis_received), atomic_get(&corrupt),
                     atomic_get(&duplicate), atomic_get(&cross_stream), atomic_get(&cis_empty));
            emit(line);
            if (!forwarding)
            {
                forwarding = true;
                k_work_schedule(&forward_work, K_MSEC(forward_period_ms));
            }
        }
    }

    /** @brief 중앙 CIS RX의 transparent HCI path가 설치된 뒤에만 수신합니다. */
    void cisConnected(struct bt_iso_chan *channel)
    {
        const struct bt_iso_chan_path path = {
            .pid = BT_ISO_DATA_PATH_HCI,
            .format = BT_HCI_CODING_FORMAT_TRANSPARENT,
        };
        const int result = bt_iso_setup_data_path(channel, BT_HCI_DATAPATH_DIR_CTLR_TO_HOST,
                                                  &path);
        if (result != 0)
        {
            fail("cis_data_path", result);
            return;
        }
        char line[90] = {};
        snprintf(line, sizeof(line), "M31COMB|1|CIS_CONNECTED|nonce=%s", nonce);
        emit(line);
    }

    /** @brief CIS 해제 reason을 출력하고 현재 queue가 다음 session에 섞이지 않게 합니다. */
    void cisDisconnected(struct bt_iso_chan *channel, uint8_t reason)
    {
        (void)channel;
        k_work_cancel_delayable(&forward_work);
        char line[105] = {};
        snprintf(line, sizeof(line), "M31COMB|1|CIS_DISCONNECTED|nonce=%s|reason=%u",
                 nonce, reason);
        emit(line);
    }

    /** @brief BIS source HCI path와 BIG 연결을 보고합니다. */
    void bisConnected(struct bt_iso_chan *channel)
    {
        const struct bt_iso_chan_path path = {
            .pid = BT_ISO_DATA_PATH_HCI,
            .format = BT_HCI_CODING_FORMAT_TRANSPARENT,
        };
        const int result = bt_iso_setup_data_path(channel, BT_HCI_DATAPATH_DIR_HOST_TO_CTLR,
                                                  &path);
        if (result != 0)
        {
            fail("bis_data_path", result);
            return;
        }
        char line[90] = {};
        snprintf(line, sizeof(line), "M31COMB|1|BIG_SYNCED|nonce=%s", nonce);
        emit(line);
    }

    /** @brief BIG teardown callback을 확정한 후 자원 반환을 허용합니다. */
    void bisDisconnected(struct bt_iso_chan *channel, uint8_t reason)
    {
        (void)channel;
        big_disconnected = true;
        k_work_cancel_delayable(&forward_work);
        char line[105] = {};
        snprintf(line, sizeof(line), "M31COMB|1|BIG_DISCONNECTED|nonce=%s|reason=%u",
                 nonce, reason);
        emit(line);
    }

    struct bt_iso_chan_ops cis_operations = {
        .connected = cisConnected,
        .disconnected = cisDisconnected,
        .recv = cisReceived,
    };
    struct bt_iso_chan_ops bis_operations = {
        .connected = bisConnected,
        .disconnected = bisDisconnected,
    };

    /** @brief CIS에서 확인한 8-byte 원본을 순서대로 한 BIS에 전달합니다. */
    void forwardNext(struct k_work *work)
    {
        (void)work;
        if (!started || finished || stopping ||
            bis_channel.state != BT_ISO_STATE_CONNECTED)
        {
            return;
        }
        uint8_t payload[sdu_length] = {};
        if (k_msgq_peek(&forward_queue, payload) != 0)
        {
            if (!cis_end)
            {
                k_work_schedule(&forward_work, K_MSEC(forward_period_ms));
            }
            return;
        }
        struct net_buf *buffer = net_buf_alloc(&bis_tx_pool, K_NO_WAIT);
        if (buffer == nullptr)
        {
            k_work_schedule(&forward_work, K_MSEC(forward_period_ms));
            return;
        }
        net_buf_reserve(buffer, BT_ISO_CHAN_SEND_RESERVE);
        net_buf_add_mem(buffer, payload, sizeof(payload));
        const uint16_t sequence = sys_get_le16(payload);
        const int result = bt_iso_chan_send(&bis_channel, buffer, sequence);
        if (result != 0)
        {
            net_buf_unref(buffer);
            fail("bis_send", result);
            return;
        }
        uint8_t consumed[sdu_length] = {};
        if (k_msgq_get(&forward_queue, consumed, K_NO_WAIT) != 0 ||
            memcmp(consumed, payload, sizeof(payload)) != 0)
        {
            fail("forward_queue", -EBADMSG);
            return;
        }
        atomic_inc(&bis_sent);
        if (sequence == sdu_count - 1U)
        {
            char line[115] = {};
            snprintf(line, sizeof(line), "M31COMB|1|BIS_TX_END|nonce=%s|sent=%ld|cross_stream=%ld",
                     nonce, atomic_get(&bis_sent), atomic_get(&cross_stream));
            emit(line);
            return;
        }
        k_work_schedule(&forward_work, K_MSEC(forward_period_ms));
    }

    /** @brief CIS peer 광고의 nonce 제조사 데이터만 선택합니다. */
    bool matchingAdvertisement(struct bt_data *data, void *context)
    {
        bool *matched = static_cast<bool *>(context);
        if (data->type == BT_DATA_MANUFACTURER_DATA &&
            data->data_len == sizeof(nonce_bytes) &&
            memcmp(data->data, nonce_bytes, sizeof(nonce_bytes)) == 0)
        {
            *matched = true;
            return false;
        }
        return true;
    }

    /** @brief 해당 nonce의 연결 가능 peer만 ACL 20ms로 요청합니다. */
    void found(const bt_addr_le_t *address, int8_t rssi, uint8_t type,
               struct net_buf_simple *advertisement)
    {
        (void)rssi;
        if (!started || finished || stopping || acl != nullptr ||
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
            fail("scan_stop", stop_result);
            return;
        }
        scan_active = false;
        const struct bt_le_conn_param parameters =
            BT_LE_CONN_PARAM_INIT(BT_GAP_MS_TO_CONN_INTERVAL(20),
                                  BT_GAP_MS_TO_CONN_INTERVAL(20), 0U,
                                  BT_GAP_MS_TO_CONN_TIMEOUT(4000));
        const int result = bt_conn_le_create(address, BT_CONN_LE_CREATE_CONN,
                                             &parameters, &acl);
        if (result != 0)
        {
            fail("acl_create", result);
        }
    }

    /** @brief BIS advertising·periodic advertising·BIG를 같은 nonce로 만듭니다. */
    void startBig()
    {
        bis_channel.ops = &bis_operations;
        bis_channel.qos = &bis_qos;
        bis_transmit_qos.sdu = CONFIG_BT_ISO_TX_MTU;
        bis_transmit_qos.phy = BT_GAP_LE_PHY_2M;
        bis_transmit_qos.rtn = 10U;
        bis_qos.tx = &bis_transmit_qos;
        const struct bt_le_adv_param advertising_parameter =
            BT_LE_ADV_PARAM_INIT(BT_LE_ADV_OPT_EXT_ADV,
                                 BT_GAP_MS_TO_ADV_INTERVAL(50),
                                 BT_GAP_MS_TO_ADV_INTERVAL(50), nullptr);
        int result = bt_le_ext_adv_create(&advertising_parameter, nullptr, &advertiser);
        if (result != 0)
        {
            fail("adv_create", result);
            return;
        }
        const struct bt_data data[] = {
            BT_DATA(BT_DATA_MANUFACTURER_DATA, nonce_bytes, sizeof(nonce_bytes)),
        };
        result = bt_le_ext_adv_set_data(advertiser, data, ARRAY_SIZE(data), nullptr, 0U);
        if (result != 0)
        {
            fail("adv_data", result);
            return;
        }
        const struct bt_le_per_adv_param periodic_parameter =
            BT_LE_PER_ADV_PARAM_INIT(BT_GAP_MS_TO_PER_ADV_INTERVAL(20),
                                     BT_GAP_MS_TO_PER_ADV_INTERVAL(20),
                                     BT_LE_PER_ADV_OPT_NONE);
        result = bt_le_per_adv_set_param(advertiser, &periodic_parameter);
        if (result != 0)
        {
            fail("pa_param", result);
            return;
        }
        result = bt_le_per_adv_start(advertiser);
        if (result != 0)
        {
            fail("pa_start", result);
            return;
        }
        result = bt_le_ext_adv_start(advertiser, BT_LE_EXT_ADV_START_DEFAULT);
        if (result != 0)
        {
            fail("adv_start", result);
            return;
        }
        struct bt_iso_chan *channels[] = {&bis_channel};
        struct bt_iso_big_create_param parameter = {
            .bis_channels = channels,
            .num_bis = 1U,
            .interval = stream_interval_us,
            .latency = 40U,
            .packing = BT_ISO_PACKING_SEQUENTIAL,
            .framing = BT_ISO_FRAMING_UNFRAMED,
            .encryption = false,
        };
        result = bt_iso_big_create(advertiser, &parameter, &big);
        if (result != 0)
        {
            fail("big_create", result);
        }
    }

    /** @brief ACL 연결 직후 CIS RX를 세우고 같은 controller에서 BIG를 시작합니다. */
    void aclConnected(struct bt_conn *connection, uint8_t error)
    {
        if (error != 0U || connection != acl)
        {
            fail("acl_connected", error != 0U ? error : -EINVAL);
            return;
        }
        char line[90] = {};
        snprintf(line, sizeof(line), "M31COMB|1|ACL_CONNECTED|nonce=%s", nonce);
        emit(line);
        const struct bt_iso_connect_param parameter = {
            .iso_chan = &cis_channel,
            .acl = connection,
        };
        const int result = bt_iso_chan_connect(&parameter, 1U);
        if (result != 0)
        {
            fail("cis_connect", result);
            return;
        }
        startBig();
    }

    /** @brief 끊어진 ACL ref를 반환하고 다음 session의 peer와 분리합니다. */
    void aclDisconnected(struct bt_conn *connection, uint8_t reason)
    {
        if (connection == acl)
        {
            bt_conn_unref(acl);
            acl = nullptr;
        }
        char line[105] = {};
        snprintf(line, sizeof(line), "M31COMB|1|ACL_DISCONNECTED|nonce=%s|reason=%u",
                 nonce, reason);
        emit(line);
    }

    BT_CONN_CB_DEFINE(combined_acl_callbacks) = {
        .connected = aclConnected,
        .disconnected = aclDisconnected,
    };

    /** @brief CIG 한 개와 ISO RX path를 만든 뒤 peer 검색을 시작합니다. */
    void startRadio()
    {
        cis_channel.ops = &cis_operations;
        cis_channel.qos = &cis_qos;
        cis_receive_qos.sdu = sdu_length;
        cis_receive_qos.phy = BT_GAP_LE_PHY_2M;
        cis_receive_qos.rtn = 10U;
        cis_qos.rx = &cis_receive_qos;
        struct bt_iso_chan *channels[] = {&cis_channel};
        const struct bt_iso_cig_param parameter = {
            .cis_channels = channels,
            .num_cis = 1U,
            .c_to_p_interval = stream_interval_us,
            .p_to_c_interval = stream_interval_us,
            .c_to_p_latency = 40U,
            .p_to_c_latency = 40U,
            .sca = BT_GAP_SCA_UNKNOWN,
            .packing = BT_ISO_PACKING_SEQUENTIAL,
            .framing = BT_ISO_FRAMING_UNFRAMED,
        };
        const int result = bt_iso_cig_create(&parameter, &cig);
        if (result != 0)
        {
            fail("cig_create", result);
            return;
        }
        const int scan_result = bt_le_scan_start(BT_LE_SCAN_PASSIVE, found);
        if (scan_result != 0)
        {
            fail("scan_start", scan_result);
            return;
        }
        scan_active = true;
    }

    /** @brief 정확한 START·revision·nonce를 무선 동작 앞에서 교차 출력합니다. */
    void startProtocol()
    {
        const size_t prefix_length = strlen(start_prefix);
        const size_t suffix_length = strlen(start_suffix);
        if (started || stopping || acl != nullptr || cig != nullptr || big != nullptr ||
            advertiser != nullptr ||
            command_length != prefix_length + nonce_length + suffix_length ||
            memcmp(command, start_prefix, prefix_length) != 0 ||
            memcmp(command + prefix_length + nonce_length, start_suffix, suffix_length) != 0)
        {
            fail("start_command", -EINVAL);
            return;
        }
        memcpy(nonce, command + prefix_length, nonce_length);
        nonce[nonce_length] = '\0';
        if (!parseNonce())
        {
            fail("nonce", -EINVAL);
            return;
        }
        started = true;
        finished = false;
        cis_end = false;
        forwarding = false;
        big_disconnected = false;
        scan_active = false;
        last_sequence = -1;
        atomic_set(&cis_received, 0);
        atomic_set(&cis_empty, 0);
        atomic_set(&bis_sent, 0);
        atomic_set(&corrupt, 0);
        atomic_set(&duplicate, 0);
        atomic_set(&cross_stream, 0);
        memset(seen, 0, sizeof(seen));
        memset(&cis_channel, 0, sizeof(cis_channel));
        memset(&bis_channel, 0, sizeof(bis_channel));
        memset(&cis_qos, 0, sizeof(cis_qos));
        memset(&bis_qos, 0, sizeof(bis_qos));
        k_msgq_purge(&forward_queue);
        char line[260] = {};
        snprintf(line, sizeof(line), "M31COMB|1|BEGIN|nonce=%s|role=combined", nonce);
        emit(line);
        snprintf(line, sizeof(line),
                 "M31COMB|1|IDENTITY|nonce=%s|core=%s|board=%s|ncs=%s|zephyr=%s",
                 nonce, NUCODE_CORE_REVISION, NUCODE_BOARD_REVISION,
                 NUCODE_NCS_REVISION, NUCODE_ZEPHYR_REVISION);
        emit(line);
        if (!enabled)
        {
            const int result = bt_enable(nullptr);
            if (result != 0)
            {
                fail("bt_enable", result);
                return;
            }
            enabled = true;
        }
        startRadio();
    }

    /** @brief 동일 nonce의 STOP에서 BIG·ACL을 먼저 종료합니다. */
    void stopProtocol()
    {
        const size_t prefix_length = strlen(stop_prefix);
        if (!started || stopping || command_length != prefix_length + nonce_length ||
            memcmp(command, stop_prefix, prefix_length) != 0 ||
            memcmp(command + prefix_length, nonce, nonce_length) != 0)
        {
            fail("stop_command", -EINVAL);
            return;
        }
        finished = true;
        stopping = true;
        stop_start_ms = k_uptime_get();
        k_work_cancel_delayable(&forward_work);
        if (big != nullptr && !big_disconnected)
        {
            const int result = bt_iso_big_terminate(big);
            if (result != 0)
            {
                char line[120] = {};
                snprintf(line, sizeof(line),
                         "M31COMB|1|FAIL|nonce=%s|stage=big_terminate|code=%d",
                         nonce, result);
                emit(line);
                stopping = false;
                return;
            }
        }
        if (acl != nullptr)
        {
            (void)bt_conn_disconnect(acl, BT_HCI_ERR_REMOTE_USER_TERM_CONN);
        }
        if (scan_active)
        {
            (void)bt_le_scan_stop();
            scan_active = false;
        }
    }

    /** @brief callback 종료를 확인한 다음 CIG·광고 자원을 실제 반환합니다. */
    void finishStop()
    {
        if (!stopping)
        {
            return;
        }
        if (acl != nullptr || (big != nullptr && !big_disconnected) ||
            cis_channel.state == BT_ISO_STATE_CONNECTED ||
            cis_channel.state == BT_ISO_STATE_CONNECTING ||
            bis_channel.state == BT_ISO_STATE_CONNECTED ||
            bis_channel.state == BT_ISO_STATE_CONNECTING ||
            bis_channel.state == BT_ISO_STATE_DISCONNECTING)
        {
            if (k_uptime_get() - stop_start_ms > 30000)
            {
                char line[110] = {};
                snprintf(line, sizeof(line),
                         "M31COMB|1|FAIL|nonce=%s|stage=stop_timeout|code=-110", nonce);
                emit(line);
                stopping = false;
            }
            return;
        }
        big = nullptr;
        if (cig != nullptr)
        {
            const int result = bt_iso_cig_terminate(cig);
            if (result != 0)
            {
                char line[120] = {};
                snprintf(line, sizeof(line),
                         "M31COMB|1|FAIL|nonce=%s|stage=cig_terminate|code=%d",
                         nonce, result);
                emit(line);
                stopping = false;
                return;
            }
            cig = nullptr;
        }
        if (advertiser != nullptr)
        {
            const int periodic_result = bt_le_per_adv_stop(advertiser);
            const int advertising_result = bt_le_ext_adv_stop(advertiser);
            const int delete_result = bt_le_ext_adv_delete(advertiser);
            if (periodic_result != 0 || advertising_result != 0 || delete_result != 0)
            {
                char line[110] = {};
                snprintf(line, sizeof(line),
                         "M31COMB|1|FAIL|nonce=%s|stage=adv_release|code=-5", nonce);
                emit(line);
                stopping = false;
                return;
            }
            advertiser = nullptr;
        }
        char line[155] = {};
        snprintf(line, sizeof(line),
                 "M31COMB|1|STOPPED|nonce=%s|role=combined|cis_rx=%ld|bis_tx=%ld|cross_stream=%ld",
                 nonce, atomic_get(&cis_received), atomic_get(&bis_sent),
                 atomic_get(&cross_stream));
        emit(line);
        started = false;
        finished = false;
        stopping = false;
        memset(nonce, 0, sizeof(nonce));
        memset(nonce_bytes, 0, sizeof(nonce_bytes));
        memset(&cis_channel, 0, sizeof(cis_channel));
        memset(&bis_channel, 0, sizeof(bis_channel));
        k_msgq_purge(&forward_queue);
    }

    /** @brief PROBE·START·STOP 외의 입력을 bounded protocol 오류로 닫습니다. */
    void pollSerial()
    {
        while (Serial.available() > 0)
        {
            const int incoming = Serial.read();
            if (incoming < 0)
            {
                return;
            }
            const char value = static_cast<char>(incoming);
            if (value == '\r')
            {
                continue;
            }
            if (value == '\n')
            {
                command[command_length] = '\0';
                if (strcmp(command, "M31COMB|1|PROBE") == 0)
                {
                    emit("M31COMB|1|READY|role=combined");
                }
                else if (strncmp(command, start_prefix, strlen(start_prefix)) == 0)
                {
                    startProtocol();
                }
                else if (strncmp(command, stop_prefix, strlen(stop_prefix)) == 0)
                {
                    stopProtocol();
                }
                else
                {
                    fail("command", -EINVAL);
                }
                command_length = 0U;
                return;
            }
            if (command_length + 1U >= sizeof(command))
            {
                fail("command_length", -EMSGSIZE);
                return;
            }
            command[command_length++] = value;
        }
    }
}

/** @brief Arduino sketch에서 호출하는 CIS→BIS 프로그램 API입니다. */
namespace nucode::ble::iso::internal
{
    /** @brief Serial command 수락 전 BIS 전달 work를 초기화합니다. */
    void begin()
    {
        Serial.begin(115200);
        k_work_init_delayable(&forward_work, forwardNext);
    }

    /** @brief Arduino loop에서 유한 STOP watchdog과 UART를 처리합니다. */
    void poll()
    {
        pollSerial();
        finishStop();
    }
}

#if !defined(NUCODE_BLE_ISO_LIBRARY_BACKEND)
/** @brief native HIL 앱의 Arduino 진입점을 제공합니다. */
void setup()
{
    nucode::ble::iso::internal::begin();
}

/** @brief native HIL 앱에서 CIS→BIS 프로그램을 계속 실행합니다. */
void loop()
{
    nucode::ble::iso::internal::poll();
    delay(1);
}
#endif
