/**
 * @file main.cpp
 * @brief Arduino runtime에서 고정 100-SDU CIS 송수신의 양 역할을 검증합니다.
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
#include <string.h>

#ifndef NUCODE_BLE_ISO_CIS_ROLE
#error "NUCODE_BLE_ISO_CIS_ROLE is required"
#endif

namespace
{
    constexpr uint16_t sdu_count = 100U;
    constexpr size_t sdu_length = 8U;
    constexpr size_t nonce_length = 32U;
    constexpr char start_prefix[] = "M31ISO|1|START|nonce=";
    constexpr char risk_start_prefix[] = "M31ISO|1|START_RISK|nonce=";
    constexpr char start_suffix[] = "|count=100";
    constexpr char stop_prefix[] = "M31ISO|1|STOP|nonce=";
    constexpr char risk_stop_prefix[] = "M31ISO|1|ABORT_ACL|nonce=";
#if defined(NUCODE_BLE_ISO_CIS_TO_BIS_PEER)
    constexpr char send_prefix[] = "M31ISO|1|SEND|nonce=";
    constexpr uint32_t send_period_ms = 18U;
#else
    constexpr uint32_t send_period_ms = 10U;
#endif
    constexpr char role_name[] = NUCODE_BLE_ISO_CIS_ROLE;
    const bool central_role = strcmp(role_name, "central") == 0;
#if defined(NUCODE_BLE_ISO_CIS_TO_BIS_PEER)
    atomic_t send_armed = ATOMIC_INIT(0);
#endif
    char command[128] = {};
    size_t command_length = 0U;
    char nonce[nonce_length + 1U] = {};
    uint8_t nonce_bytes[nonce_length / 2U] = {};
    atomic_t started = ATOMIC_INIT(0);
    atomic_t finished = ATOMIC_INIT(0);
    atomic_t stopping = ATOMIC_INIT(0);
    bool bluetooth_enabled = false;
    bool server_registered = false;
    atomic_t stop_start_ms = ATOMIC_INIT(0);
    atomic_t rx_end_printed = ATOMIC_INIT(0);
    atomic_t tx_end_printed = ATOMIC_INIT(0);
    atomic_t risk_mode = ATOMIC_INIT(0);
    atomic_t risk_ready_printed = ATOMIC_INIT(0);
    atomic_t acl_first_teardown = ATOMIC_INIT(0);
    atomic_t negotiated_nse = ATOMIC_INIT(0);
    atomic_t transmitted = ATOMIC_INIT(0);
    atomic_t received = ATOMIC_INIT(0);
    atomic_t invalid_or_lost = ATOMIC_INIT(0);
    atomic_t corrupt = ATOMIC_INIT(0);
    atomic_t duplicate = ATOMIC_INIT(0);
    atomic_t risk_load_ticks = ATOMIC_INIT(0);
    uint32_t seen[(sdu_count + 31U) / 32U] = {};
    struct bt_conn *acl = nullptr;
    struct bt_iso_cig *cig = nullptr;
    struct bt_iso_chan iso_channel = {};
    struct k_work_delayable send_work;
    struct k_work_delayable risk_load_work;

    NET_BUF_POOL_FIXED_DEFINE(iso_tx_pool, 4U, BT_ISO_SDU_BUF_SIZE(CONFIG_BT_ISO_TX_MTU),
                              CONFIG_BT_CONN_TX_USER_DATA_SIZE, nullptr);

    /** @brief 첫 오류를 제한된 stage/code로 남기고 성공 출력을 중단합니다. */
    void fail(const char *stage, int code)
    {
        if (!atomic_cas(&finished, 0, 1))
        {
            return;
        }
        Serial.print("M31ISO|1|FAIL|nonce=");
        Serial.print(nonce);
        Serial.print("|role=");
        Serial.print(role_name);
        Serial.print("|stage=");
        Serial.print(stage);
        Serial.print("|code=");
        Serial.println(code);
    }

    /** @brief 16-byte nonce를 제조사 광고 데이터의 전부로 비교합니다. */
    bool parseNonce()
    {
        for (size_t index = 0U; index < nonce_length / 2U; ++index)
        {
            const char upper = nonce[index * 2U];
            const char lower = nonce[index * 2U + 1U];
            const auto hex = [](char value) -> int
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
            const int hi = hex(upper);
            const int lo = hex(lower);
            if (hi < 0 || lo < 0)
            {
                return false;
            }
            nonce_bytes[index] = static_cast<uint8_t>((hi << 4U) | lo);
        }
        return true;
    }

    /** @brief SDU sequence와 session marker에서 재현 가능한 무결성 값을 만듭니다. */
    uint32_t payloadChecksum(uint16_t sequence)
    {
        const uint32_t marker = static_cast<uint32_t>(nonce_bytes[0]) |
                                (static_cast<uint32_t>(nonce_bytes[1]) << 8U);
#if defined(NUCODE_BLE_ISO_CIS_TO_BIS_PEER)
        return 0x31b15000U ^ (static_cast<uint32_t>(sequence) * 0x9e3779b1U) ^ marker;
#else
        return 0x31a50000U ^ (static_cast<uint32_t>(sequence) * 0x9e3779b1U) ^ marker;
#endif
    }

    /** @brief 같은 session의 순서·길이·flags·payload를 확인합니다. */
    void isoReceived(struct bt_iso_chan *channel, const struct bt_iso_recv_info *information,
                     struct net_buf *buffer)
    {
        (void)channel;
        if (atomic_get(&finished) != 0 || atomic_get(&started) == 0)
        {
            return;
        }
        if (information == nullptr || buffer == nullptr)
        {
            atomic_inc(&corrupt);
            fail("missing_sdu_record", -EBADMSG);
            return;
        }
        if ((information->flags & BT_ISO_FLAGS_VALID) == 0U)
        {
            if (atomic_get(&rx_end_printed) == 0)
            {
                const atomic_val_t prior = atomic_inc(&invalid_or_lost);
                if (prior < 4)
                {
                    Serial.print("M31ISO|1|RX_INVALID|nonce=");
                    Serial.print(nonce);
                    Serial.print("|seq=");
                    Serial.print(information->seq_num);
                    Serial.print("|flags=");
                    Serial.print(information->flags);
                    Serial.print("|len=");
                    Serial.println(buffer->len);
                }
            }
            return;
        }
        if (buffer->len != sdu_length)
        {
            Serial.print("M31ISO|1|RX_BAD_LENGTH|nonce=");
            Serial.print(nonce);
            Serial.print("|seq=");
            Serial.print(information->seq_num);
            Serial.print("|flags=");
            Serial.print(information->flags);
            Serial.print("|len=");
            Serial.println(buffer->len);
            atomic_inc(&corrupt);
            fail("sdu_length", -EBADMSG);
            return;
        }
        const uint16_t sequence = sys_get_le16(buffer->data);
        const uint16_t marker = sys_get_le16(buffer->data + 2U);
        const uint16_t expected_marker = static_cast<uint16_t>(nonce_bytes[0]) |
                                         (static_cast<uint16_t>(nonce_bytes[1]) << 8U);
        if (sequence >= sdu_count || marker != expected_marker ||
            sys_get_le32(buffer->data + 4U) != payloadChecksum(sequence))
        {
            atomic_inc(&corrupt);
            fail("payload", -EBADMSG);
            return;
        }
        const uint32_t bit = 1U << (sequence % 32U);
        uint32_t &word = seen[sequence / 32U];
        if ((word & bit) != 0U)
        {
            atomic_inc(&duplicate);
            fail("duplicate", -EALREADY);
            return;
        }
        word |= bit;
        atomic_inc(&received);
        if (sequence == sdu_count - 1U && atomic_cas(&rx_end_printed, 0, 1))
        {
            Serial.print("M31ISO|1|RX_END|nonce=");
            Serial.print(nonce);
            Serial.print("|received=");
            Serial.print(atomic_get(&received));
            Serial.print("|corrupt=");
            Serial.print(atomic_get(&corrupt));
            Serial.print("|duplicate=");
            Serial.print(atomic_get(&duplicate));
            Serial.print("|invalid_or_lost=");
            Serial.println(atomic_get(&invalid_or_lost));
        }
    }

    /** @brief risk session 동안 system workqueue에 20%의 유한 CPU 부하를 가합니다. */
    void runRiskLoad(struct k_work *work)
    {
        (void)work;
        if (atomic_get(&risk_mode) == 0 || atomic_get(&started) == 0 ||
            atomic_get(&finished) != 0 ||
            iso_channel.state != BT_ISO_STATE_CONNECTED)
        {
            return;
        }
        k_busy_wait(2000U);
        atomic_inc(&risk_load_ticks);
        k_work_schedule(&risk_load_work, K_MSEC(8));
    }

    /** @brief 한 개의 HCI transparent path를 role 방향에 따라 선택합니다. */
    void isoConnected(struct bt_iso_chan *channel)
    {
#if defined(NUCODE_BLE_ISO_CIS_TO_BIS_PEER)
        struct bt_iso_info information = {};
        const int information_result = bt_iso_chan_get_info(channel, &information);
        if (information_result != 0)
        {
            fail("iso_info", information_result);
            return;
        }
        Serial.print("M31ISO|1|ISO_INFO|nonce=");
        Serial.print(nonce);
        Serial.print("|can_send=");
        Serial.print(information.can_send ? 1 : 0);
        Serial.print("|p_bn=");
        Serial.print(information.unicast.peripheral.bn);
        Serial.print("|max_sdu=");
        Serial.println(information.unicast.peripheral.max_sdu);
        if (!information.can_send)
        {
            fail("iso_tx_unavailable", -ENOTSUP);
            return;
        }
#endif
        if (atomic_get(&risk_mode) != 0)
        {
            struct bt_iso_info risk_information = {};
            const int risk_information_result =
                bt_iso_chan_get_info(channel, &risk_information);
            if (risk_information_result != 0 ||
                risk_information.max_subevent <= 1U)
            {
                fail("risk_nse", risk_information_result != 0 ?
                     risk_information_result : -ERANGE);
                return;
            }
            atomic_set(&negotiated_nse, risk_information.max_subevent);
            k_work_schedule(&risk_load_work, K_NO_WAIT);
        }
        const struct bt_iso_chan_path path = {
            .pid = BT_ISO_DATA_PATH_HCI,
            .format = BT_HCI_CODING_FORMAT_TRANSPARENT,
        };
        const uint8_t direction = central_role ? BT_HCI_DATAPATH_DIR_HOST_TO_CTLR :
#if defined(NUCODE_BLE_ISO_CIS_TO_BIS_PEER)
                                                 BT_HCI_DATAPATH_DIR_HOST_TO_CTLR;
#else
                                                 BT_HCI_DATAPATH_DIR_CTLR_TO_HOST;
#endif
        const int result = bt_iso_setup_data_path(channel, direction, &path);
        if (result != 0)
        {
            fail("iso_data_path", result);
            return;
        }
        Serial.print("M31ISO|1|ISO_CONNECTED|nonce=");
        Serial.println(nonce);
        if (central_role)
        {
            k_work_schedule(&send_work, K_MSEC(send_period_ms));
        }
    }

    /** @brief disconnect reason을 성공으로 숨기지 않고 work를 중단합니다. */
    void isoDisconnected(struct bt_iso_chan *channel, uint8_t reason)
    {
        (void)channel;
        k_work_cancel_delayable(&send_work);
        k_work_cancel_delayable(&risk_load_work);
        Serial.print("M31ISO|1|ISO_DISCONNECTED|nonce=");
        Serial.print(nonce);
        Serial.print("|reason=");
        Serial.println(reason);
    }

    struct bt_iso_chan_ops iso_operations = {
        .connected = isoConnected,
        .disconnected = isoDisconnected,
        .recv = isoReceived,
    };
    struct bt_iso_chan_io_qos transmit_qos = {
#if defined(NUCODE_BLE_ISO_CIS_TO_BIS_PEER)
        .sdu = sdu_length,
#else
        .sdu = CONFIG_BT_ISO_TX_MTU,
#endif
        .phy = BT_GAP_LE_PHY_2M,
#if defined(NUCODE_BLE_ISO_CIS_TO_BIS_PEER)
        .rtn = 10U,
#else
        .rtn = 2U,
#endif
    };
#if !defined(NUCODE_BLE_ISO_CIS_TO_BIS_PEER)
    struct bt_iso_chan_io_qos receive_qos = {
        .sdu = CONFIG_BT_ISO_RX_MTU,
        .phy = BT_GAP_LE_PHY_2M,
    };
#endif
    struct bt_iso_chan_qos qos = {
#if !defined(NUCODE_BLE_ISO_CIS_TO_BIS_PEER)
        .rx = &receive_qos,
#endif
        .tx = &transmit_qos,
    };

    /** @brief CIG 한 개의 HCI SDU를 고정 pool에서 전송합니다. */
    void sendNext(struct k_work *work)
    {
        (void)work;
        if (atomic_get(&finished) != 0 ||
            iso_channel.state != BT_ISO_STATE_CONNECTED)
        {
            return;
        }
#if defined(NUCODE_BLE_ISO_CIS_TO_BIS_PEER)
        if (atomic_get(&send_armed) == 0)
        {
            return;
        }
#endif
        const uint16_t sequence = static_cast<uint16_t>(atomic_get(&transmitted));
        if (sequence >= sdu_count)
        {
            return;
        }
        struct net_buf *buffer = net_buf_alloc(&iso_tx_pool, K_NO_WAIT);
        if (buffer == nullptr)
        {
            k_work_schedule(&send_work, K_MSEC(send_period_ms));
            return;
        }
        net_buf_reserve(buffer, BT_ISO_CHAN_SEND_RESERVE);
        uint8_t payload[sdu_length] = {};
        sys_put_le16(sequence, payload);
        payload[2] = nonce_bytes[0];
        payload[3] = nonce_bytes[1];
        sys_put_le32(payloadChecksum(sequence), payload + 4U);
        net_buf_add_mem(buffer, payload, sizeof(payload));
        const int result = bt_iso_chan_send(&iso_channel, buffer, sequence);
        if (result != 0)
        {
            net_buf_unref(buffer);
            fail("iso_send", result);
            return;
        }
        atomic_inc(&transmitted);
        if (sequence == sdu_count - 1U)
        {
            atomic_set(&tx_end_printed, 1);
            Serial.print("M31ISO|1|TX_END|nonce=");
            Serial.print(nonce);
            Serial.print("|sent=");
            Serial.println(atomic_get(&transmitted));
            return;
        }
        k_work_schedule(&send_work, K_MSEC(send_period_ms));
    }

    /** @brief 이미 사용 중인 ISO slot은 수락하지 않습니다. */
    int acceptIso(const struct bt_iso_accept_info *information,
                  struct bt_iso_chan **channel)
    {
        if (information == nullptr || channel == nullptr ||
            information->acl != acl || iso_channel.iso != nullptr)
        {
            return -ENOMEM;
        }
        *channel = &iso_channel;
        return 0;
    }

    struct bt_iso_server iso_server = {
        .accept = acceptIso,
    };

    /** @brief 광고 제조사 데이터에서 nonce 16 byte가 모두 맞는지 확인합니다. */
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

    /** @brief 다른 광고/세션은 연결하지 않습니다. */
    void found(const bt_addr_le_t *address, int8_t rssi, uint8_t type,
               struct net_buf_simple *advertisement)
    {
        (void)rssi;
        if (atomic_get(&started) == 0 || atomic_get(&finished) != 0 ||
            acl != nullptr ||
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
        const struct bt_le_conn_param parameters =
            BT_LE_CONN_PARAM_INIT(BT_GAP_MS_TO_CONN_INTERVAL(30),
                                  BT_GAP_MS_TO_CONN_INTERVAL(30), 0U,
                                  BT_GAP_MS_TO_CONN_TIMEOUT(4000));
        const int result = bt_conn_le_create(address, BT_CONN_LE_CREATE_CONN,
                                             &parameters, &acl);
        if (result != 0)
        {
            fail("acl_create", result);
        }
    }

    /** @brief ACL 세션이 맞을 때만 CIS를 요청합니다. */
    void aclConnected(struct bt_conn *connection, uint8_t error)
    {
        if (error != 0U)
        {
            fail("acl_connected", error);
            return;
        }
        if (!central_role)
        {
            if (acl == nullptr)
            {
                acl = bt_conn_ref(connection);
            }
        }
        if (connection != acl)
        {
            fail("wrong_acl", -EINVAL);
            return;
        }
        Serial.print("M31ISO|1|ACL_CONNECTED|nonce=");
        Serial.println(nonce);
        if (central_role)
        {
            const struct bt_iso_connect_param parameter = {
                .iso_chan = &iso_channel,
                .acl = connection,
            };
            const int result = bt_iso_chan_connect(&parameter, 1U);
            if (result != 0)
            {
                fail("cis_connect", result);
            }
        }
    }

    /** @brief 끊어진 ACL pointer를 같은 세션으로 재사용하지 않습니다. */
    void aclDisconnected(struct bt_conn *connection, uint8_t reason)
    {
        const bool peer_acl_first_teardown =
            connection == acl && atomic_get(&risk_mode) != 0 &&
            atomic_get(&risk_ready_printed) != 0 &&
            atomic_get(&stopping) == 0;
        if (connection == acl)
        {
            bt_conn_unref(acl);
            acl = nullptr;
        }
        Serial.print("M31ISO|1|ACL_DISCONNECTED|nonce=");
        Serial.print(nonce);
        Serial.print("|reason=");
        Serial.println(reason);
        if (peer_acl_first_teardown)
        {
            atomic_set(&finished, 1);
            atomic_set(&stopping, 1);
            atomic_set(&acl_first_teardown, 1);
            atomic_set(&stop_start_ms, k_uptime_get_32());
            k_work_cancel_delayable(&send_work);
            k_work_cancel_delayable(&risk_load_work);
        }
    }

    BT_CONN_CB_DEFINE(iso_acl_callbacks) = {
        .connected = aclConnected,
        .disconnected = aclDisconnected,
    };

    /** @brief 128-bit session nonce를 가진 상대 광고 또는 검색만 시작합니다. */
    void startRadio()
    {
        if (central_role)
        {
            iso_channel.ops = &iso_operations;
            iso_channel.qos = &qos;
            struct bt_iso_chan *channels[] = {&iso_channel};
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
                fail("cig_create", result);
                return;
            }
            k_work_init_delayable(&send_work, sendNext);
            const int scan_result = bt_le_scan_start(BT_LE_SCAN_PASSIVE, found);
            if (scan_result != 0)
            {
                fail("scan_start", scan_result);
            }
        }
        else
        {
            iso_channel.ops = &iso_operations;
            iso_channel.qos = &qos;
            k_work_init_delayable(&send_work, sendNext);
            if (!server_registered)
            {
                const int register_result = bt_iso_server_register(&iso_server);
                if (register_result != 0)
                {
                    fail("iso_server", register_result);
                    return;
                }
                server_registered = true;
            }
            const struct bt_data data[] = {
                BT_DATA_BYTES(BT_DATA_FLAGS, (BT_LE_AD_GENERAL | BT_LE_AD_NO_BREDR)),
                BT_DATA(BT_DATA_MANUFACTURER_DATA, nonce_bytes, sizeof(nonce_bytes)),
            };
            const int result = bt_le_adv_start(BT_LE_ADV_CONN_FAST_1, data,
                                               ARRAY_SIZE(data), nullptr, 0U);
            if (result != 0)
            {
                fail("advertise", result);
            }
        }
    }

    /** @brief exact revision과 bounded session 조건을 보고합니다. */
    void startProtocol(const char *prefix, bool enable_risk_mode)
    {
        const size_t prefix_length = strlen(prefix);
        const size_t suffix_length = strlen(start_suffix);
        if (atomic_get(&started) != 0 || atomic_get(&stopping) != 0 ||
            acl != nullptr || cig != nullptr ||
            command_length != prefix_length + nonce_length + suffix_length ||
            memcmp(command, prefix, prefix_length) != 0 ||
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
        atomic_set(&started, 1);
        atomic_set(&finished, 0);
        atomic_set(&rx_end_printed, 0);
        atomic_set(&tx_end_printed, 0);
        atomic_set(&risk_mode, enable_risk_mode ? 1 : 0);
        atomic_set(&risk_ready_printed, 0);
        atomic_set(&acl_first_teardown, 0);
        atomic_set(&negotiated_nse, 0);
        atomic_set(&stop_start_ms, 0);
#if defined(NUCODE_BLE_ISO_CIS_TO_BIS_PEER)
        atomic_set(&send_armed, 0);
#endif
        atomic_set(&transmitted, 0);
        atomic_set(&received, 0);
        atomic_set(&invalid_or_lost, 0);
        atomic_set(&corrupt, 0);
        atomic_set(&duplicate, 0);
        atomic_set(&risk_load_ticks, 0);
        memset(seen, 0, sizeof(seen));
        memset(&iso_channel, 0, sizeof(iso_channel));
        k_work_init_delayable(&risk_load_work, runRiskLoad);
        Serial.print("M31ISO|1|BEGIN|nonce=");
        Serial.print(nonce);
        Serial.print("|role=");
        Serial.println(role_name);
        Serial.print("M31ISO|1|IDENTITY|nonce=");
        Serial.print(nonce);
        Serial.print("|core=");
        Serial.print(NUCODE_CORE_REVISION);
        Serial.print("|board=");
        Serial.print(NUCODE_BOARD_REVISION);
        Serial.print("|ncs=");
        Serial.print(NUCODE_NCS_REVISION);
        Serial.print("|zephyr=");
        Serial.println(NUCODE_ZEPHYR_REVISION);
        if (!bluetooth_enabled)
        {
            const int enabled = bt_enable(nullptr);
            if (enabled != 0)
            {
                fail("bt_enable", enabled);
                return;
            }
            bluetooth_enabled = true;
        }
        startRadio();
    }

#if defined(NUCODE_BLE_ISO_CIS_TO_BIS_PEER)
    /** @brief BIS receiver가 BIG에 붙은 뒤 peer CIS 송신을 시작합니다. */
    void startSending()
    {
        const size_t prefix_length = strlen(send_prefix);
        if (central_role || atomic_get(&started) == 0 ||
            atomic_get(&finished) != 0 || atomic_get(&stopping) != 0 ||
            atomic_get(&send_armed) != 0 ||
            iso_channel.state != BT_ISO_STATE_CONNECTED ||
            command_length != prefix_length + nonce_length ||
            memcmp(command, send_prefix, prefix_length) != 0 ||
            memcmp(command + prefix_length, nonce, nonce_length) != 0)
        {
            fail("send_command", -EINVAL);
            return;
        }
        atomic_set(&send_armed, 1);
        Serial.print("M31ISO|1|SEND_ARMED|nonce=");
        Serial.println(nonce);
        k_work_schedule(&send_work, K_MSEC(send_period_ms));
    }
#endif

    /** @brief STOP 또는 active-CIS ACL 우선 종료로 무선 자원을 해제합니다. */
    void stopProtocol(const char *prefix, bool acl_first)
    {
        const size_t prefix_length = strlen(prefix);
        if (atomic_get(&started) == 0 || atomic_get(&stopping) != 0 ||
            command_length != prefix_length + nonce_length ||
            memcmp(command, prefix, prefix_length) != 0 ||
            memcmp(command + prefix_length, nonce, nonce_length) != 0)
        {
            fail("stop_command", -EINVAL);
            return;
        }
        if (acl_first && (atomic_get(&risk_mode) == 0 ||
                          atomic_get(&risk_ready_printed) == 0 ||
                          iso_channel.state != BT_ISO_STATE_CONNECTED))
        {
            fail("risk_abort_state", -EINVAL);
            return;
        }
        atomic_set(&finished, 1);
        atomic_set(&stopping, 1);
        atomic_set(&acl_first_teardown, acl_first ? 1 : 0);
        atomic_set(&stop_start_ms, k_uptime_get_32());
        k_work_cancel_delayable(&send_work);
        k_work_cancel_delayable(&risk_load_work);
        if (!acl_first && central_role &&
            iso_channel.state == BT_ISO_STATE_CONNECTED)
        {
            (void)bt_iso_chan_disconnect(&iso_channel);
        }
        if (acl != nullptr)
        {
            (void)bt_conn_disconnect(acl, BT_HCI_ERR_REMOTE_USER_TERM_CONN);
        }
        if (central_role && acl == nullptr)
        {
            (void)bt_le_scan_stop();
        }
        if (!central_role)
        {
            (void)bt_le_adv_stop();
        }
    }

    /** @brief 무선 callback의 종료를 확인한 뒤 CIG/server 자원을 실제 반환합니다. */
    void finishStop()
    {
        if (atomic_get(&stopping) == 0)
        {
            return;
        }
        if (acl != nullptr || iso_channel.state == BT_ISO_STATE_CONNECTED ||
            iso_channel.state == BT_ISO_STATE_CONNECTING)
        {
            const uint32_t stop_elapsed = k_uptime_get_32() -
                                          static_cast<uint32_t>(
                                              atomic_get(&stop_start_ms));
            if (stop_elapsed > 30000U)
            {
                Serial.print("M31ISO|1|FAIL|nonce=");
                Serial.print(nonce);
                Serial.print("|role=");
                Serial.print(role_name);
                Serial.println("|stage=stop_timeout|code=-110");
                atomic_set(&stopping, 0);
            }
            return;
        }
        if (cig != nullptr)
        {
            const int result = bt_iso_cig_terminate(cig);
            if (result != 0)
            {
                Serial.print("M31ISO|1|FAIL|nonce=");
                Serial.print(nonce);
                Serial.print("|role=");
                Serial.print(role_name);
                Serial.print("|stage=cig_terminate|code=");
                Serial.println(result);
                atomic_set(&stopping, 0);
                return;
            }
            cig = nullptr;
        }
        if (server_registered)
        {
            const int result = bt_iso_server_unregister(&iso_server);
            if (result != 0)
            {
                Serial.print("M31ISO|1|FAIL|nonce=");
                Serial.print(nonce);
                Serial.print("|role=");
                Serial.print(role_name);
                Serial.print("|stage=server_unregister|code=");
                Serial.println(result);
                atomic_set(&stopping, 0);
                return;
            }
            server_registered = false;
        }
        Serial.print(atomic_get(&risk_mode) != 0 ?
                         "M31ISO|1|RISK_STOPPED|nonce=" :
                         "M31ISO|1|STOPPED|nonce=");
        Serial.print(nonce);
        Serial.print("|role=");
        Serial.print(role_name);
        Serial.print("|tx=");
        Serial.print(atomic_get(&transmitted));
        Serial.print("|rx=");
        Serial.print(atomic_get(&received));
        if (atomic_get(&risk_mode) != 0)
        {
            Serial.print("|nse=");
            Serial.print(atomic_get(&negotiated_nse));
            Serial.print("|load_ticks=");
            Serial.print(atomic_get(&risk_load_ticks));
            Serial.print("|acl_first=");
            Serial.print(atomic_get(&acl_first_teardown) != 0 ? 1 : 0);
        }
        Serial.println();
        atomic_set(&started, 0);
        atomic_set(&stopping, 0);
        atomic_set(&finished, 0);
        atomic_set(&risk_mode, 0);
        atomic_set(&risk_ready_printed, 0);
        atomic_set(&acl_first_teardown, 0);
        atomic_set(&negotiated_nse, 0);
        memset(&iso_channel, 0, sizeof(iso_channel));
        memset(nonce, 0, sizeof(nonce));
        memset(nonce_bytes, 0, sizeof(nonce_bytes));
    }

    /** @brief active CIS·NSE>1·실제 CPU 부하가 함께 성립한 종료 시점을 보고합니다. */
    void reportRiskReady()
    {
        const atomic_val_t payload_count = central_role ?
                                               atomic_get(&transmitted) :
                                               atomic_get(&received);
        if (atomic_get(&risk_mode) == 0 ||
            atomic_get(&risk_ready_printed) != 0 ||
            atomic_get(&finished) != 0 ||
            iso_channel.state != BT_ISO_STATE_CONNECTED ||
            atomic_get(&negotiated_nse) <= 1 ||
            atomic_get(&risk_load_ticks) < 10 ||
            payload_count < 25)
        {
            return;
        }
        Serial.print("M31ISO|1|RISK_ACTIVE|nonce=");
        Serial.print(nonce);
        Serial.print("|role=");
        Serial.print(role_name);
        Serial.print("|nse=");
        Serial.print(atomic_get(&negotiated_nse));
        Serial.print("|load_ticks=");
        Serial.print(atomic_get(&risk_load_ticks));
        Serial.print("|payloads=");
        Serial.println(payload_count);
        atomic_set(&risk_ready_printed, 1);
    }

    /** @brief PROBE, START, START_RISK, STOP, ABORT_ACL만 bounded 입력으로 수락합니다. */
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
                if (strcmp(command, "M31ISO|1|PROBE") == 0)
                {
                    Serial.print("M31ISO|1|READY|role=");
                    Serial.println(role_name);
                }
                else if (strncmp(command, risk_start_prefix,
                                 strlen(risk_start_prefix)) == 0)
                {
                    startProtocol(risk_start_prefix, true);
                }
                else if (strncmp(command, start_prefix, strlen(start_prefix)) == 0)
                {
                    startProtocol(start_prefix, false);
                }
                else if (strncmp(command, risk_stop_prefix,
                                 strlen(risk_stop_prefix)) == 0)
                {
                    stopProtocol(risk_stop_prefix, true);
                }
                else if (strncmp(command, stop_prefix, strlen(stop_prefix)) == 0)
                {
                    stopProtocol(stop_prefix, false);
                }
#if defined(NUCODE_BLE_ISO_CIS_TO_BIS_PEER)
                else if (strncmp(command, send_prefix, strlen(send_prefix)) == 0)
                {
                    startSending();
                }
#endif
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

/** @brief Arduino sketch에서 호출하는 CIS 프로그램 API입니다. */
namespace nucode::ble::iso::internal
{
    /** @brief UART PROBE 뒤 역할별 무선 시작을 기다립니다. */
    void begin()
    {
        Serial.begin(115200);
    }

    /** @brief 무선 callback이 진행하는 동안 bounded serial command를 처리합니다. */
    void poll()
    {
        pollSerial();
        reportRiskReady();
        finishStop();
    }
}

#if !defined(NUCODE_BLE_ISO_LIBRARY_BACKEND)
/** @brief native HIL 앱의 Arduino 진입점을 제공합니다. */
void setup()
{
    nucode::ble::iso::internal::begin();
}

/** @brief native HIL 앱에서 CIS 프로그램을 계속 실행합니다. */
void loop()
{
    nucode::ble::iso::internal::poll();
    delay(1);
}
#endif
