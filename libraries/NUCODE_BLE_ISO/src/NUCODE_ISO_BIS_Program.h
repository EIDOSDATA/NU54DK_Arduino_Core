#pragma once
#if !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE)
/**
 * @file main.cpp
 * @brief Arduino runtime에서 한 BIS의 source/receiver 역할과 유한 재시작을 검증합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <Arduino.h>

#include <zephyr/bluetooth/bluetooth.h>
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

#ifndef M31_BIS_ROLE
#error "M31_BIS_ROLE is required"
#endif

namespace
{
    constexpr uint16_t sdu_count = 100U;
    constexpr size_t sdu_length = 8U;
    constexpr size_t nonce_length = 32U;
    constexpr char start_prefix[] = "M31BIS|1|START|nonce=";
    constexpr char start_suffix[] = "|count=100";
    constexpr char stop_prefix[] = "M31BIS|1|STOP|nonce=";
    constexpr char send_prefix[] = "M31BIS|1|SEND|nonce=";
#if defined(M31_BIS_ENCRYPTED) && defined(CONFIG_BT_ISO_SYNC_RECEIVER)
    constexpr char check_bad_code_prefix[] = "M31BIS|1|CHECK_BAD_CODE|nonce=";
#endif
    constexpr char role_name[] = M31_BIS_ROLE;
    const bool source_role = strcmp(role_name, "source") == 0;
    char command[sizeof(start_prefix) + nonce_length + sizeof(start_suffix)] = {};
    size_t command_length = 0U;
    char nonce[nonce_length + 1U] = {};
    uint8_t nonce_bytes[nonce_length / 2U] = {};
    bool started = false;
#if defined(CONFIG_BT_ISO_BROADCASTER)
    bool send_armed = false;
#endif
    bool finished = false;
    bool stopping = false;
    bool bluetooth_enabled = false;
#if defined(CONFIG_BT_ISO_SYNC_RECEIVER)
    bool callbacks_registered = false;
#endif
    bool rx_end_printed = false;
    bool sync_requested = false;
    bool big_requested = false;
    bool big_disconnected = false;
#if defined(CONFIG_BT_ISO_SYNC_RECEIVER)
    bool expect_sync_loss = false;
#endif
#if defined(M31_BIS_ENCRYPTED) && defined(CONFIG_BT_ISO_SYNC_RECEIVER)
    bool wrong_code_next = false;
    bool wrong_code_active = false;
    bool authentication_rejected = false;
#endif
    int64_t stop_start_ms = 0;
    atomic_t sent = ATOMIC_INIT(0);
    atomic_t received = ATOMIC_INIT(0);
    atomic_t empty_slots = ATOMIC_INIT(0);
    atomic_t corrupt = ATOMIC_INIT(0);
    atomic_t duplicate = ATOMIC_INIT(0);
    atomic_t out_of_order = ATOMIC_INIT(0);
    int last_sequence = -1;
#if defined(M31_BIS_TIME_SYNC)
    atomic_t valid_timestamp = ATOMIC_INIT(0);
    uint32_t first_timestamp = 0U;
    uint32_t last_timestamp = 0U;
#endif
#if defined(M31_BIS_TIME_SYNC) && defined(CONFIG_BT_ISO_BROADCASTER)
    uint32_t next_tx_timestamp = 0U;
    uint32_t first_tx_timestamp = 0U;
    uint32_t last_hci_timestamp = 0U;
    uint16_t last_hci_sequence = 0U;
    bool timestamp_ready = false;
    uint16_t timestamped_sent = 0U;
#endif
    uint32_t seen[(sdu_count + 31U) / 32U] = {};
    struct bt_le_ext_adv *advertiser = nullptr;
    struct bt_le_per_adv_sync *periodic_sync = nullptr;
    struct bt_iso_big *big = nullptr;
    struct bt_iso_chan iso_channel = {};
#if defined(CONFIG_BT_ISO_BROADCASTER)
    struct bt_iso_chan_io_qos transmit_qos = {};
#endif
#if defined(CONFIG_BT_ISO_SYNC_RECEIVER)
    struct bt_iso_chan_io_qos receive_qos = {};
#endif
    struct bt_iso_chan_qos qos = {};
#if defined(CONFIG_BT_ISO_BROADCASTER)
    struct k_work_delayable send_work;
#endif
#if defined(CONFIG_BT_ISO_SYNC_RECEIVER)
    struct k_work sync_work;
    struct k_work big_work;
    bt_addr_le_t candidate_address = {};
    uint8_t candidate_sid = 0U;
#endif

#if defined(CONFIG_BT_ISO_BROADCASTER)
    NET_BUF_POOL_FIXED_DEFINE(iso_tx_pool, 4U, BT_ISO_SDU_BUF_SIZE(CONFIG_BT_ISO_TX_MTU),
                              CONFIG_BT_CONN_TX_USER_DATA_SIZE, nullptr);
#endif

    /** @brief 첫 실패 stage/code를 출력하고 현재 payload 동작을 중지합니다. */
    void fail(const char *stage, int code)
    {
        if (finished)
        {
            return;
        }
        Serial.print("M31BIS|1|FAIL|nonce=");
        Serial.print(nonce);
        Serial.print("|role=");
        Serial.print(role_name);
        Serial.print("|stage=");
        Serial.print(stage);
        Serial.print("|code=");
        Serial.println(code);
        finished = true;
    }

    /** @brief 128-bit session nonce의 ASCII hex를 bounded byte로 바꿉니다. */
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

    /** @brief stream sequence와 session marker로 재현 가능한 payload를 만듭니다. */
    uint32_t checksum(uint16_t sequence)
    {
        const uint32_t marker = static_cast<uint32_t>(nonce_bytes[0]) |
                                (static_cast<uint32_t>(nonce_bytes[1]) << 8U);
        return 0x31b15000U ^ (static_cast<uint32_t>(sequence) * 0x9e3779b1U) ^ marker;
    }

#if defined(CONFIG_BT_ISO_SYNC_RECEIVER)
    /** @brief 마지막 SDU 손실도 포함하도록 현재 receiver 결과를 한 번만 출력합니다. */
    void printReceiveEnd()
    {
        if (rx_end_printed)
        {
            return;
        }
        rx_end_printed = true;
#if defined(M31_BIS_TIME_SYNC)
        Serial.print("M31BIS|1|TIME_END|nonce=");
        Serial.print(nonce);
        Serial.print("|valid=");
        Serial.print(atomic_get(&valid_timestamp));
        Serial.print("|stale=0|first_ts=");
        Serial.print(first_timestamp);
        Serial.print("|last_ts=");
        Serial.println(last_timestamp);
#endif
        Serial.print("M31BIS|1|RX_END|nonce=");
        Serial.print(nonce);
        Serial.print("|received=");
        Serial.print(atomic_get(&received));
        Serial.print("|corrupt=");
        Serial.print(atomic_get(&corrupt));
        Serial.print("|duplicate=");
        Serial.print(atomic_get(&duplicate));
        Serial.print("|out_of_order=");
        Serial.print(atomic_get(&out_of_order));
        Serial.print("|empty_slots=");
        Serial.println(atomic_get(&empty_slots));
    }
#endif

    /** @brief 유효 SDU만 100개 분모에 포함하고 빈 controller slot은 별도 셉니다. */
    void isoReceived(struct bt_iso_chan *channel, const struct bt_iso_recv_info *information,
                     struct net_buf *buffer)
    {
        (void)channel;
        if (!started || finished)
        {
            return;
        }
        if (information == nullptr || buffer == nullptr)
        {
            atomic_inc(&corrupt);
            fail("missing_sdu", -EBADMSG);
            return;
        }
        if ((information->flags & BT_ISO_FLAGS_VALID) == 0U)
        {
            if (!rx_end_printed)
            {
                atomic_inc(&empty_slots);
            }
            return;
        }
#if defined(M31_BIS_ENCRYPTED) && defined(CONFIG_BT_ISO_SYNC_RECEIVER)
        if (wrong_code_active)
        {
            fail("wrong_code_payload_leak", -EBADMSG);
            return;
        }
#endif
        if (buffer->len != sdu_length)
        {
            atomic_inc(&corrupt);
            fail("sdu_length", -EBADMSG);
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
        if (static_cast<int>(sequence) <= last_sequence)
        {
            atomic_inc(&out_of_order);
            fail("out_of_order", -EBADMSG);
            return;
        }
#if defined(M31_BIS_TIME_SYNC)
        if ((information->flags & BT_ISO_FLAGS_TS) == 0U ||
            (atomic_get(&valid_timestamp) > 0 &&
             static_cast<int32_t>(information->ts - last_timestamp) <= 0))
        {
            fail("iso_timestamp", -EBADMSG);
            return;
        }
        if (atomic_get(&valid_timestamp) == 0)
        {
            first_timestamp = information->ts;
        }
        last_timestamp = information->ts;
        atomic_inc(&valid_timestamp);
#endif
        last_sequence = sequence;
        word |= bit;
        atomic_inc(&received);
        if (sequence == sdu_count - 1U && !rx_end_printed)
        {
            printReceiveEnd();
        }
    }

    /** @brief BIG 생성/동기 callback에서 역할 방향 HCI data path를 선택합니다. */
    void isoConnected(struct bt_iso_chan *channel)
    {
        const struct bt_iso_chan_path path = {
            .pid = BT_ISO_DATA_PATH_HCI,
            .format = BT_HCI_CODING_FORMAT_TRANSPARENT,
        };
        const uint8_t direction = source_role ? BT_HCI_DATAPATH_DIR_HOST_TO_CTLR :
                                                BT_HCI_DATAPATH_DIR_CTLR_TO_HOST;
        const int result = bt_iso_setup_data_path(channel, direction, &path);
        if (result != 0)
        {
            fail("iso_data_path", result);
            return;
        }
        Serial.print("M31BIS|1|BIG_SYNCED|nonce=");
        Serial.print(nonce);
        Serial.print("|role=");
        Serial.println(role_name);
    }

    /** @brief BIG 해제 reason을 남기고 pending 전송을 중지합니다. */
    void isoDisconnected(struct bt_iso_chan *channel, uint8_t reason)
    {
        (void)channel;
        big_disconnected = true;
#if defined(M31_BIS_ENCRYPTED) && defined(CONFIG_BT_ISO_SYNC_RECEIVER)
        if (wrong_code_active && !stopping)
        {
            authentication_rejected = reason == BT_HCI_ERR_TERM_DUE_TO_MIC_FAIL;
            Serial.print("M31BIS|1|BAD_CODE_DISCONNECTED|nonce=");
            Serial.print(nonce);
            Serial.print("|reason=");
            Serial.println(reason);
        }
#endif
#if defined(CONFIG_BT_ISO_BROADCASTER)
        k_work_cancel_delayable(&send_work);
#endif
        Serial.print("M31BIS|1|BIG_DISCONNECTED|nonce=");
        Serial.print(nonce);
        Serial.print("|reason=");
        Serial.println(reason);
    }

#if defined(M31_BIS_TIME_SYNC) && defined(CONFIG_BT_ISO_BROADCASTER)
    /** @brief 송신 완료 HCI 기준시각에서 다음 10ms SDU timestamp를 계산합니다. */
    void isoSent(struct bt_iso_chan *channel)
    {
        if (!started || finished || stopping || !send_armed)
        {
            return;
        }
        const int completed = atomic_get(&sent);
        if (completed <= 0 || completed >= sdu_count)
        {
            return;
        }
        struct bt_iso_tx_info information = {};
        const int result = bt_iso_chan_get_tx_sync(channel, &information);
        if (result != 0)
        {
            fail("tx_sync_query", result);
            return;
        }
        if (completed > 1 &&
            (static_cast<int16_t>(information.seq_num - last_hci_sequence) <= 0 ||
             static_cast<int32_t>(information.ts - last_hci_timestamp) <= 0))
        {
            Serial.print("M31BIS|1|TX_SYNC_DIAG|nonce=");
            Serial.print(nonce);
            Serial.print("|completed=");
            Serial.print(completed);
            Serial.print("|hci_seq=");
            Serial.print(information.seq_num);
            Serial.print("|hci_ts=");
            Serial.println(information.ts);
            fail("tx_sync_monotonic", -EBADMSG);
            return;
        }
        if (completed == 1)
        {
            first_tx_timestamp = information.ts;
        }
        next_tx_timestamp = information.ts + 10000U;
        last_hci_sequence = information.seq_num;
        last_hci_timestamp = information.ts;
        timestamp_ready = true;
        k_work_schedule(&send_work, K_NO_WAIT);
    }
#endif

    struct bt_iso_chan_ops iso_operations = {
        .connected = isoConnected,
        .disconnected = isoDisconnected,
        .recv = isoReceived,
#if defined(M31_BIS_TIME_SYNC) && defined(CONFIG_BT_ISO_BROADCASTER)
        .sent = isoSent,
#endif
    };

#if defined(CONFIG_BT_ISO_BROADCASTER)
    /** @brief 10ms 고정 간격으로 100개 BIS SDU를 pool에서 보냅니다. */
    void sendNext(struct k_work *work)
    {
        (void)work;
        if (!started || finished || !send_armed || iso_channel.state != BT_ISO_STATE_CONNECTED)
        {
            return;
        }
        const uint16_t sequence = static_cast<uint16_t>(atomic_get(&sent));
        if (sequence >= sdu_count)
        {
            return;
        }
#if defined(M31_BIS_TIME_SYNC)
        if (sequence > 0U && !timestamp_ready)
        {
            return;
        }
#endif
        struct net_buf *buffer = net_buf_alloc(&iso_tx_pool, K_NO_WAIT);
        if (buffer == nullptr)
        {
            k_work_schedule(&send_work, K_MSEC(10));
            return;
        }
        net_buf_reserve(buffer, BT_ISO_CHAN_SEND_RESERVE);
        uint8_t payload[sdu_length] = {};
        sys_put_le16(sequence, payload);
        payload[2] = nonce_bytes[0];
        payload[3] = nonce_bytes[1];
        sys_put_le32(checksum(sequence), payload + 4U);
        net_buf_add_mem(buffer, payload, sizeof(payload));
#if defined(M31_BIS_TIME_SYNC)
        const int result = sequence == 0U ?
            bt_iso_chan_send(&iso_channel, buffer, sequence) :
            bt_iso_chan_send_ts(&iso_channel, buffer, sequence, next_tx_timestamp);
#else
        const int result = bt_iso_chan_send(&iso_channel, buffer, sequence);
#endif
        if (result != 0)
        {
            net_buf_unref(buffer);
            fail("iso_send", result);
            return;
        }
        atomic_inc(&sent);
#if defined(M31_BIS_TIME_SYNC)
        if (sequence > 0U)
        {
            timestamped_sent++;
        }
        timestamp_ready = false;
#endif
        if (sequence == sdu_count - 1U)
        {
#if defined(M31_BIS_TIME_SYNC)
            Serial.print("M31BIS|1|TIME_TX_END|nonce=");
            Serial.print(nonce);
            Serial.print("|timestamped=");
            Serial.print(timestamped_sent);
            Serial.print("|first_ts=");
            Serial.print(first_tx_timestamp);
            Serial.print("|last_ts=");
            Serial.println(next_tx_timestamp);
#endif
            Serial.print("M31BIS|1|TX_END|nonce=");
            Serial.print(nonce);
            Serial.print("|sent=");
            Serial.println(atomic_get(&sent));
            return;
        }
#if !defined(M31_BIS_TIME_SYNC)
        k_work_schedule(&send_work, K_MSEC(10));
#endif
    }
#endif

#if defined(CONFIG_BT_ISO_SYNC_RECEIVER)
    /** @brief 광고 제조사 nonce가 정확히 맞을 때만 해당 SID를 선택합니다. */
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

    /** @brief 다른 peer·비주기 광고·다른 nonce는 동기화하지 않습니다. */
    void advertisementReceived(const struct bt_le_scan_recv_info *information,
                               struct net_buf_simple *buffer)
    {
        if (!started || finished || stopping || sync_requested || information == nullptr ||
            information->interval == 0U)
        {
            return;
        }
        bool matched = false;
        bt_data_parse(buffer, matchingAdvertisement, &matched);
        if (!matched)
        {
            return;
        }
        sync_requested = true;
        bt_addr_le_copy(&candidate_address, information->addr);
        candidate_sid = information->sid;
        k_work_submit(&sync_work);
    }

    struct bt_le_scan_cb scan_callbacks = {
        .recv = advertisementReceived,
    };

    /** @brief scanner callback 밖에서 periodic sync를 생성합니다. */
    void createPeriodicSync(struct k_work *work)
    {
        (void)work;
        if (!started || finished || stopping)
        {
            return;
        }
        const int stop_result = bt_le_scan_stop();
        if (stop_result != 0)
        {
            fail("scan_stop", stop_result);
            return;
        }
        const struct bt_le_per_adv_sync_param parameter = {
            .addr = candidate_address,
            .sid = candidate_sid,
            .options = 0U,
            .skip = 0U,
            .timeout = 100U,
        };
        const int result = bt_le_per_adv_sync_create(&parameter, &periodic_sync);
        if (result != 0)
        {
            fail("pa_sync_create", result);
        }
    }

    /** @brief periodic advertising이 붙은 동일 peer만 BIG 정보를 받습니다. */
    void periodicSynced(struct bt_le_per_adv_sync *sync,
                        struct bt_le_per_adv_sync_synced_info *information)
    {
        (void)information;
        if (!started || finished || sync != periodic_sync)
        {
            return;
        }
        Serial.print("M31BIS|1|PA_SYNCED|nonce=");
        Serial.println(nonce);
    }

    /** @brief peer loss를 다음 session의 성공으로 재사용하지 않습니다. */
    void periodicTerminated(struct bt_le_per_adv_sync *sync,
                            const struct bt_le_per_adv_sync_term_info *information)
    {
        (void)sync;
        (void)information;
        if (started && !stopping && !finished)
        {
            if (expect_sync_loss && sync == periodic_sync)
            {
                Serial.print("M31BIS|1|SYNC_LOST|nonce=");
                Serial.println(nonce);
                expect_sync_loss = false;
            }
            else
            {
                fail("pa_sync_lost", -ENOLINK);
            }
        }
    }

    /** @brief 고정 1-BIS·비암호화 BIG 정보만 수락해 work에서 동기화합니다. */
    void bigInfo(struct bt_le_per_adv_sync *sync,
                 const struct bt_iso_biginfo *information)
    {
        if (!started || finished || stopping || sync != periodic_sync || big_requested)
        {
            return;
        }
        if (information == nullptr || information->num_bis != 1U ||
#if defined(M31_BIS_ENCRYPTED)
            !information->encryption)
#else
            information->encryption)
#endif
        {
            fail("biginfo", -ENOTSUP);
            return;
        }
        big_requested = true;
        k_work_submit(&big_work);
    }

    struct bt_le_per_adv_sync_cb periodic_callbacks = {
        .synced = periodicSynced,
        .term = periodicTerminated,
        .biginfo = bigInfo,
    };

    /** @brief callback thread 밖에서 1번 BIS를 고정 RX buffer에 연결합니다. */
    void createBigSync(struct k_work *work)
    {
        (void)work;
        if (!started || finished || stopping || periodic_sync == nullptr)
        {
            return;
        }
        struct bt_iso_chan *channels[] = {&iso_channel};
        struct bt_iso_big_sync_param parameter = {
            .bis_channels = channels,
            .num_bis = 1U,
            .bis_bitfield = BT_ISO_BIS_INDEX_BIT(1),
            .mse = BT_ISO_SYNC_MSE_ANY,
            .sync_timeout = 100U,
            .encryption = false,
        };
#if defined(M31_BIS_ENCRYPTED)
        parameter.encryption = true;
        memcpy(parameter.bcode, nonce_bytes, sizeof(parameter.bcode));
        if (wrong_code_active)
        {
            parameter.bcode[0] ^= 0x01U;
        }
#endif
        const int result = bt_iso_big_sync(periodic_sync, &parameter, &big);
        if (result != 0)
        {
            fail("big_sync", result);
        }
    }
#endif

    /** @brief 기본 controller와 역할별 BIG 무선을 한 session만 시작합니다. */
    void startRadio()
    {
        iso_channel.ops = &iso_operations;
        iso_channel.qos = &qos;
#if defined(CONFIG_BT_ISO_BROADCASTER)
        if (source_role)
        {
            transmit_qos.sdu = CONFIG_BT_ISO_TX_MTU;
            transmit_qos.phy = BT_GAP_LE_PHY_2M;
#if defined(M31_BIS_TIME_SYNC)
            transmit_qos.rtn = 2U;
#else
            transmit_qos.rtn = 1U;
#endif
            qos.tx = &transmit_qos;
            const struct bt_le_adv_param advertising_parameter =
                BT_LE_ADV_PARAM_INIT(BT_LE_ADV_OPT_EXT_ADV,
                                     BT_GAP_MS_TO_ADV_INTERVAL(50),
                                     BT_GAP_MS_TO_ADV_INTERVAL(50), nullptr);
            const int create_result = bt_le_ext_adv_create(&advertising_parameter, nullptr,
                                                             &advertiser);
            if (create_result != 0)
            {
                fail("adv_create", create_result);
                return;
            }
            const struct bt_data data[] = {
                BT_DATA(BT_DATA_MANUFACTURER_DATA, nonce_bytes, sizeof(nonce_bytes)),
            };
            const int data_result = bt_le_ext_adv_set_data(advertiser, data,
                                                            ARRAY_SIZE(data), nullptr, 0U);
            if (data_result != 0)
            {
                fail("adv_data", data_result);
                return;
            }
            const struct bt_le_per_adv_param periodic_parameter =
                BT_LE_PER_ADV_PARAM_INIT(BT_GAP_MS_TO_PER_ADV_INTERVAL(60),
                                         BT_GAP_MS_TO_PER_ADV_INTERVAL(60),
                                         BT_LE_PER_ADV_OPT_NONE);
            const int parameter_result = bt_le_per_adv_set_param(advertiser, &periodic_parameter);
            if (parameter_result != 0)
            {
                fail("pa_param", parameter_result);
                return;
            }
            const int periodic_result = bt_le_per_adv_start(advertiser);
            if (periodic_result != 0)
            {
                fail("pa_start", periodic_result);
                return;
            }
            const int advertising_result = bt_le_ext_adv_start(advertiser,
                                                                 BT_LE_EXT_ADV_START_DEFAULT);
            if (advertising_result != 0)
            {
                fail("adv_start", advertising_result);
                return;
            }
            struct bt_iso_chan *channels[] = {&iso_channel};
            struct bt_iso_big_create_param parameter = {
                .bis_channels = channels,
                .num_bis = 1U,
                .interval = 10000U,
                .latency = 20U,
                .packing = BT_ISO_PACKING_SEQUENTIAL,
                .framing = BT_ISO_FRAMING_UNFRAMED,
                .encryption = false,
            };
#if defined(M31_BIS_ENCRYPTED)
            parameter.encryption = true;
            memcpy(parameter.bcode, nonce_bytes, sizeof(parameter.bcode));
#endif
            const int result = bt_iso_big_create(advertiser, &parameter, &big);
            if (result != 0)
            {
                fail("big_create", result);
            }
        }
#endif
#if defined(CONFIG_BT_ISO_SYNC_RECEIVER)
        if (!source_role)
        {
            receive_qos.sdu = CONFIG_BT_ISO_RX_MTU;
            receive_qos.phy = BT_GAP_LE_PHY_2M;
            qos.rx = &receive_qos;
            const int result = bt_le_scan_start(BT_LE_SCAN_PASSIVE, nullptr);
            if (result != 0)
            {
                fail("scan_start", result);
            }
        }
#endif
    }

    /** @brief command nonce와 fixed revision을 무선 동작 전 교차 출력합니다. */
    void startProtocol()
    {
        const size_t prefix_length = strlen(start_prefix);
        const size_t suffix_length = strlen(start_suffix);
        if (started || stopping || advertiser != nullptr || periodic_sync != nullptr || big != nullptr ||
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
        rx_end_printed = false;
        sync_requested = false;
        big_requested = false;
        big_disconnected = false;
#if defined(CONFIG_BT_ISO_SYNC_RECEIVER)
        expect_sync_loss = false;
#endif
#if defined(M31_BIS_ENCRYPTED) && defined(CONFIG_BT_ISO_SYNC_RECEIVER)
        wrong_code_active = wrong_code_next;
        authentication_rejected = false;
#endif
        atomic_set(&sent, 0);
        atomic_set(&received, 0);
        atomic_set(&empty_slots, 0);
        atomic_set(&corrupt, 0);
        atomic_set(&duplicate, 0);
        atomic_set(&out_of_order, 0);
        last_sequence = -1;
#if defined(M31_BIS_TIME_SYNC)
        atomic_set(&valid_timestamp, 0);
        first_timestamp = 0U;
        last_timestamp = 0U;
#endif
#if defined(M31_BIS_TIME_SYNC) && defined(CONFIG_BT_ISO_BROADCASTER)
        next_tx_timestamp = 0U;
        first_tx_timestamp = 0U;
        last_hci_timestamp = 0U;
        last_hci_sequence = 0U;
        timestamp_ready = false;
        timestamped_sent = 0U;
#endif
        memset(seen, 0, sizeof(seen));
#if defined(CONFIG_BT_ISO_BROADCASTER)
        send_armed = false;
#endif
        memset(&iso_channel, 0, sizeof(iso_channel));
        memset(&qos, 0, sizeof(qos));
        Serial.print("M31BIS|1|BEGIN|nonce=");
        Serial.print(nonce);
        Serial.print("|role=");
        Serial.println(role_name);
        Serial.print("M31BIS|1|IDENTITY|nonce=");
        Serial.print(nonce);
        Serial.print("|core=");
        Serial.print(M31_CORE_REVISION);
        Serial.print("|board=");
        Serial.print(M31_BOARD_REVISION);
        Serial.print("|ncs=");
        Serial.print(M31_NCS_REVISION);
        Serial.print("|zephyr=");
        Serial.println(M31_ZEPHYR_REVISION);
        if (!bluetooth_enabled)
        {
            const int result = bt_enable(nullptr);
            if (result != 0)
            {
                fail("bt_enable", result);
                return;
            }
            bluetooth_enabled = true;
        }
#if defined(CONFIG_BT_ISO_SYNC_RECEIVER)
        if (!source_role && !callbacks_registered)
        {
            bt_le_scan_cb_register(&scan_callbacks);
            bt_le_per_adv_sync_cb_register(&periodic_callbacks);
            callbacks_registered = true;
        }
#endif
        startRadio();
    }

#if defined(CONFIG_BT_ISO_BROADCASTER)
    /** @brief receiver BIG 동기 후 동일 nonce의 SEND에서만 전송합니다. */
    void startSending()
    {
        const size_t prefix_length = strlen(send_prefix);
        if (!source_role || !started || finished || stopping || send_armed ||
            iso_channel.state != BT_ISO_STATE_CONNECTED ||
            command_length != prefix_length + nonce_length ||
            memcmp(command, send_prefix, prefix_length) != 0 ||
            memcmp(command + prefix_length, nonce, nonce_length) != 0)
        {
            fail("send_command", -EINVAL);
            return;
        }
        send_armed = true;
        Serial.print("M31BIS|1|SEND_ARMED|nonce=");
        Serial.println(nonce);
        k_work_schedule(&send_work, K_MSEC(10));
    }
#endif

#if defined(CONFIG_BT_ISO_SYNC_RECEIVER)
    /** @brief 동기 해제 negative에서만 peer loss를 기대 상태로 둡니다. */
    void expectSyncLoss()
    {
        if (!started || finished || stopping ||
            command_length != strlen("M31BIS|1|EXPECT_SYNC_LOSS|nonce=") + nonce_length ||
            memcmp(command, "M31BIS|1|EXPECT_SYNC_LOSS|nonce=",
                   strlen("M31BIS|1|EXPECT_SYNC_LOSS|nonce=")) != 0 ||
            memcmp(command + strlen("M31BIS|1|EXPECT_SYNC_LOSS|nonce="), nonce,
                   nonce_length) != 0)
        {
            fail("sync_loss_command", -EINVAL);
            return;
        }
        expect_sync_loss = true;
        Serial.print("M31BIS|1|LOSS_ARMED|nonce=");
        Serial.println(nonce);
    }
#endif

#if defined(M31_BIS_ENCRYPTED) && defined(CONFIG_BT_ISO_SYNC_RECEIVER)
    /** @brief 다음 한 세션에서만 고의로 다른 128-bit broadcast code를 씁니다. */
    void selectWrongCode()
    {
        if (started || stopping || strcmp(command, "M31BIS|1|BAD_CODE") != 0)
        {
            fail("bad_code_command", -EINVAL);
            return;
        }
        wrong_code_next = true;
        Serial.println("M31BIS|1|BAD_CODE_READY");
    }

    /** @brief 송신 뒤 유효 payload 유출 없이 BIG 인증 거부를 확인합니다. */
    void checkWrongCode()
    {
        const size_t prefix_length = strlen(check_bad_code_prefix);
        if (!started || finished || stopping || !wrong_code_active ||
            command_length != prefix_length + nonce_length ||
            memcmp(command, check_bad_code_prefix, prefix_length) != 0 ||
            memcmp(command + prefix_length, nonce, nonce_length) != 0 ||
            atomic_get(&received) != 0 || !authentication_rejected)
        {
            fail("bad_code_not_rejected", -EBADMSG);
            return;
        }
        Serial.print("M31BIS|1|BAD_CODE_REJECTED|nonce=");
        Serial.print(nonce);
        Serial.print("|received=");
        Serial.print(atomic_get(&received));
        Serial.print("|empty_slots=");
        Serial.print(atomic_get(&empty_slots));
        Serial.print("|disconnected=");
        Serial.println(authentication_rejected ? 1 : 0);
    }
#endif

    /** @brief STOP은 동일 session을 보유한 host에게서만 수락합니다. */
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
#if defined(CONFIG_BT_ISO_SYNC_RECEIVER) && !defined(M31_BIS_TIME_SYNC)
        if (!source_role && !rx_end_printed)
        {
            printReceiveEnd();
        }
#endif
        finished = true;
        stopping = true;
        stop_start_ms = k_uptime_get();
#if defined(CONFIG_BT_ISO_BROADCASTER)
        k_work_cancel_delayable(&send_work);
#endif
        if (big != nullptr)
        {
            const int result = big_disconnected ? 0 : bt_iso_big_terminate(big);
            if (result != 0)
            {
                Serial.print("M31BIS|1|FAIL|nonce=");
                Serial.print(nonce);
                Serial.print("|role=");
                Serial.print(role_name);
                Serial.print("|stage=big_terminate|code=");
                Serial.println(result);
                stopping = false;
            }
        }
#if defined(CONFIG_BT_ISO_SYNC_RECEIVER)
        if (!source_role && periodic_sync == nullptr)
        {
            (void)bt_le_scan_stop();
        }
#endif
    }

    /** @brief BIG callback 종료 후 periodic/extended 광고 또는 sync 자원을 반환합니다. */
    void finishStop()
    {
        if (!stopping)
        {
            return;
        }
        if (!big_disconnected || iso_channel.state == BT_ISO_STATE_CONNECTED ||
            iso_channel.state == BT_ISO_STATE_CONNECTING ||
            iso_channel.state == BT_ISO_STATE_DISCONNECTING)
        {
            if (k_uptime_get() - stop_start_ms > 30000)
            {
                Serial.print("M31BIS|1|FAIL|nonce=");
                Serial.print(nonce);
                Serial.print("|role=");
                Serial.print(role_name);
                Serial.println("|stage=stop_timeout|code=-110");
                stopping = false;
            }
            return;
        }
        big = nullptr;
#if defined(CONFIG_BT_ISO_BROADCASTER)
        if (source_role && advertiser != nullptr)
        {
            const int periodic_result = bt_le_per_adv_stop(advertiser);
            const int advertising_result = bt_le_ext_adv_stop(advertiser);
            const int delete_result = bt_le_ext_adv_delete(advertiser);
            if (periodic_result != 0 || advertising_result != 0 || delete_result != 0)
            {
                Serial.print("M31BIS|1|FAIL|nonce=");
                Serial.print(nonce);
                Serial.print("|role=");
                Serial.print(role_name);
                Serial.println("|stage=adv_release|code=-5");
                stopping = false;
                return;
            }
            advertiser = nullptr;
        }
#endif
#if defined(CONFIG_BT_ISO_SYNC_RECEIVER)
        if (!source_role && periodic_sync != nullptr)
        {
            const int result = bt_le_per_adv_sync_delete(periodic_sync);
            if (result != 0)
            {
                Serial.print("M31BIS|1|FAIL|nonce=");
                Serial.print(nonce);
                Serial.print("|role=");
                Serial.print(role_name);
                Serial.print("|stage=pa_release|code=");
                Serial.println(result);
                stopping = false;
                return;
            }
            periodic_sync = nullptr;
        }
#endif
        Serial.print("M31BIS|1|STOPPED|nonce=");
        Serial.print(nonce);
        Serial.print("|role=");
        Serial.print(role_name);
        Serial.print("|tx=");
        Serial.print(atomic_get(&sent));
        Serial.print("|rx=");
        Serial.println(atomic_get(&received));
        started = false;
        finished = false;
        stopping = false;
        memset(&iso_channel, 0, sizeof(iso_channel));
        memset(nonce, 0, sizeof(nonce));
        memset(nonce_bytes, 0, sizeof(nonce_bytes));
#if defined(M31_BIS_ENCRYPTED) && defined(CONFIG_BT_ISO_SYNC_RECEIVER)
        wrong_code_next = false;
        wrong_code_active = false;
        authentication_rejected = false;
#endif
    }

    /** @brief PROBE, START, STOP 외의 UART command를 bounded 실패로 처리합니다. */
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
                if (strcmp(command, "M31BIS|1|PROBE") == 0)
                {
                    Serial.print("M31BIS|1|READY|role=");
                    Serial.println(role_name);
                }
                else if (strncmp(command, start_prefix, strlen(start_prefix)) == 0)
                {
                    startProtocol();
                }
                else if (strncmp(command, stop_prefix, strlen(stop_prefix)) == 0)
                {
                    stopProtocol();
                }
#if defined(CONFIG_BT_ISO_SYNC_RECEIVER)
                else if (strncmp(command, "M31BIS|1|EXPECT_SYNC_LOSS|nonce=",
                                 strlen("M31BIS|1|EXPECT_SYNC_LOSS|nonce=")) == 0)
                {
                    expectSyncLoss();
                }
#endif
#if defined(M31_BIS_ENCRYPTED) && defined(CONFIG_BT_ISO_SYNC_RECEIVER)
                else if (strcmp(command, "M31BIS|1|BAD_CODE") == 0)
                {
                    selectWrongCode();
                }
                else if (strncmp(command, check_bad_code_prefix,
                                 strlen(check_bad_code_prefix)) == 0)
                {
                    checkWrongCode();
                }
#endif
#if defined(CONFIG_BT_ISO_BROADCASTER)
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

/** @brief Serial command 수락 전 모든 work object를 한 번 초기화합니다. */
void setup()
{
    Serial.begin(115200);
#if defined(CONFIG_BT_ISO_BROADCASTER)
    k_work_init_delayable(&send_work, sendNext);
#endif
#if defined(CONFIG_BT_ISO_SYNC_RECEIVER)
    k_work_init(&sync_work, createPeriodicSync);
    k_work_init(&big_work, createBigSync);
#endif
}

/** @brief Arduino loop에서 UART·30초 STOP watchdog을 처리합니다. */
void loop()
{
    pollSerial();
    finishStop();
    delay(1);
}

#endif
