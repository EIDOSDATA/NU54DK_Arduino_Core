/**
 * @file NUCODE_BLE_ISO_RawBis.cpp
 * @brief 일반·암호화·시각동기 BIG/BIS 사용자 SDU를 Arduino API로 연결합니다.
 * SPDX-License-Identifier: MIT
 */

#include "NUCODE_BLE_ISO.h"

#if !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE) && \
    (defined(CONFIG_NUCODE_BLE_ISO_MODE_BIS_SOURCE) || \
     defined(CONFIG_NUCODE_BLE_ISO_MODE_BIS_RECEIVER) || \
     defined(CONFIG_NUCODE_BLE_ISO_MODE_BIS_ENCRYPTED_SOURCE) || \
     defined(CONFIG_NUCODE_BLE_ISO_MODE_BIS_ENCRYPTED_RECEIVER) || \
     defined(CONFIG_NUCODE_BLE_ISO_MODE_BIS_TIME_SOURCE) || \
     defined(CONFIG_NUCODE_BLE_ISO_MODE_BIS_TIME_RECEIVER) || \
     defined(CONFIG_NUCODE_BLE_ISO_MODE_CIS_TO_BIS_BRIDGE) || \
     defined(CONFIG_NUCODE_BLE_ISO_MODE_CIS_TO_BIS_RECEIVER))

#include "../../../cores/arduino/internal/BLEPeriodicSyncLease.h"

#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/gap.h>
#include <zephyr/bluetooth/hci_types.h>
#include <zephyr/bluetooth/iso.h>
#include <zephyr/kernel.h>
#include <zephyr/net_buf.h>
#include <zephyr/sys/atomic.h>

#include <errno.h>
#include <string.h>

namespace
{
    using nucode::ble::iso::BisFrame;
    using nucode::ble::iso::BisTxSync;
    using nucode::ble::iso::Error;
    using nucode::ble::iso::RawBis;

#if defined(CONFIG_NUCODE_BLE_ISO_MODE_BIS_SOURCE) || \
    defined(CONFIG_NUCODE_BLE_ISO_MODE_BIS_ENCRYPTED_SOURCE) || \
    defined(CONFIG_NUCODE_BLE_ISO_MODE_BIS_TIME_SOURCE) || \
    defined(CONFIG_NUCODE_BLE_ISO_MODE_CIS_TO_BIS_BRIDGE)
    constexpr bool source_role = true;
#else
    constexpr bool source_role = false;
#endif

#if defined(CONFIG_NUCODE_BLE_ISO_MODE_CIS_TO_BIS_BRIDGE) || \
    defined(CONFIG_NUCODE_BLE_ISO_MODE_CIS_TO_BIS_RECEIVER)
    constexpr bool relay_role = true;
#else
    constexpr bool relay_role = false;
#endif

#if defined(CONFIG_NUCODE_BLE_ISO_MODE_BIS_TIME_SOURCE) || \
    defined(CONFIG_NUCODE_BLE_ISO_MODE_BIS_TIME_RECEIVER)
    constexpr bool time_role = true;
#else
    constexpr bool time_role = false;
#endif

#if defined(CONFIG_NUCODE_BLE_ISO_MODE_BIS_ENCRYPTED_SOURCE) || \
    defined(CONFIG_NUCODE_BLE_ISO_MODE_BIS_ENCRYPTED_RECEIVER)
    constexpr bool encrypted_role = true;
#else
    constexpr bool encrypted_role = false;
#endif

    constexpr std::size_t session_length = 16U;
    constexpr std::size_t frame_capacity = 16U;
    RawBis *owner = nullptr;
    std::uint8_t session_id[session_length] = {};
    std::uint8_t broadcast_code[session_length] = {};
    struct bt_le_ext_adv *advertiser = nullptr;
    struct bt_le_per_adv_sync *periodic_sync = nullptr;
#if defined(CONFIG_BT_ISO_SYNC_RECEIVER)
    std::uint8_t periodic_sync_owner_token = 0U;
#endif
    struct bt_iso_big *big = nullptr;
    struct bt_iso_chan channel = {};
    struct bt_iso_chan_io_qos transmit_qos = {};
    struct bt_iso_chan_io_qos receive_qos = {};
    struct bt_iso_chan_qos qos = {};
    bool started = false;
    bool stopping = false;
    bool bluetooth_enabled = false;
    bool callbacks_registered = false;
    bool scan_active = false;
    bool sync_requested = false;
    bool big_requested = false;
    bool big_disconnected = true;
#if defined(CONFIG_BT_ISO_SYNC_RECEIVER)
    bool periodic_delete_pending = false;
#endif
    std::int64_t stop_started_ms = 0;
    std::uint16_t next_sequence = 0U;
    atomic_t channel_ready = ATOMIC_INIT(0);
    atomic_t native_error = ATOMIC_INIT(0);
    atomic_t peer_ended = ATOMIC_INIT(0);
#if defined(CONFIG_NUCODE_BLE_ISO_MODE_BIS_TIME_SOURCE)
    BisTxSync tx_sync = {};
    atomic_t tx_sync_available = ATOMIC_INIT(0);
    bool tx_sync_seen = false;
#endif
    K_MSGQ_DEFINE(receive_queue, sizeof(BisFrame), 8U, 4U);

#if defined(CONFIG_BT_ISO_BROADCASTER)
    NET_BUF_POOL_FIXED_DEFINE(transmit_pool, 4U,
                              BT_ISO_SDU_BUF_SIZE(CONFIG_BT_ISO_TX_MTU),
                              CONFIG_BT_CONN_TX_USER_DATA_SIZE, nullptr);
#endif
#if defined(CONFIG_BT_ISO_SYNC_RECEIVER)
    struct k_work sync_work;
    struct k_work big_work;
    bt_addr_le_t candidate_address = {};
    std::uint8_t candidate_sid = 0U;
#endif

    /** @brief 첫 native 오류를 보존해 poll()에서 전달합니다. */
    void recordError(int result)
    {
        if (result != 0 && atomic_get(&native_error) == 0)
        {
            atomic_set(&native_error, result);
        }
    }

    /** @brief 유효한 SDU를 Arduino main thread 소유 queue에 복사합니다. */
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
        BisFrame frame = {};
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

    /** @brief source/receiver 방향의 HCI ISO data path를 연결합니다. */
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
        const std::uint8_t direction = source_role ?
            BT_HCI_DATAPATH_DIR_HOST_TO_CTLR : BT_HCI_DATAPATH_DIR_CTLR_TO_HOST;
        const int result = bt_iso_setup_data_path(connected_channel, direction, &path);
        if (result != 0)
        {
            recordError(result);
            return;
        }
        atomic_set(&channel_ready, 1);
    }

    /** @brief BIG 해제를 stop()과 link loss 양쪽에 알립니다. */
    void disconnected(struct bt_iso_chan *disconnected_channel, std::uint8_t reason)
    {
        if (disconnected_channel != &channel)
        {
            return;
        }
        big_disconnected = true;
        atomic_set(&channel_ready, 0);
        if (started && !stopping)
        {
            if (!source_role && reason == BT_HCI_ERR_REMOTE_USER_TERM_CONN)
            {
                atomic_set(&peer_ended, 1);
            }
            else
            {
                recordError(-static_cast<int>(reason));
            }
        }
    }

#if defined(CONFIG_NUCODE_BLE_ISO_MODE_BIS_TIME_SOURCE)
    /** @brief 완료된 SDU의 HCI 기준시각을 Arduino thread에 전달합니다. */
    void sent(struct bt_iso_chan *sent_channel)
    {
        if (!started || stopping || sent_channel != &channel)
        {
            return;
        }
        struct bt_iso_tx_info information = {};
        const int result = bt_iso_chan_get_tx_sync(sent_channel, &information);
        if (result != 0)
        {
            recordError(result);
            return;
        }
        if (tx_sync_seen &&
            (static_cast<std::int16_t>(information.seq_num - tx_sync.sequence) <= 0 ||
             static_cast<std::int32_t>(information.ts - tx_sync.timestamp_us) <= 0))
        {
            recordError(-EBADMSG);
            return;
        }
        tx_sync.sequence = information.seq_num;
        tx_sync.timestamp_us = information.ts;
        tx_sync_seen = true;
        atomic_set(&tx_sync_available, 1);
    }
#endif

    struct bt_iso_chan_ops operations = {
        .connected = connected,
        .disconnected = disconnected,
        .recv = received,
#if defined(CONFIG_NUCODE_BLE_ISO_MODE_BIS_TIME_SOURCE)
        .sent = sent,
#endif
    };

#if defined(CONFIG_BT_ISO_SYNC_RECEIVER)
    /** @brief session ID가 일치하는 periodic advertising만 고릅니다. */
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

    /** @brief scanner callback에서 peer 정보를 복사하고 sync work를 예약합니다. */
    void advertisementReceived(const struct bt_le_scan_recv_info *information,
                               struct net_buf_simple *buffer)
    {
        if (!started || stopping || sync_requested || information == nullptr ||
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

    /** @brief scanner callback 밖에서 periodic sync를 만듭니다. */
    void createPeriodicSync(struct k_work *work)
    {
        static_cast<void>(work);
        if (!started || stopping)
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
        const struct bt_le_per_adv_sync_param parameter = {
            .addr = candidate_address,
            .sid = candidate_sid,
            .options = 0U,
            .skip = 0U,
            .timeout = 100U,
        };
        struct bt_le_per_adv_sync *created = nullptr;
        const int result = bt_le_per_adv_sync_create(&parameter, &created);
        if (result != 0)
        {
            recordError(result);
            return;
        }
        if ((created == nullptr) ||
            (bt_le_per_adv_sync_lookup_addr(&parameter.addr, parameter.sid) != created))
        {
            recordError(-ECONNRESET);
            return;
        }
        periodic_sync = created;
        periodic_delete_pending = false;
    }

    /** @brief peer의 BIG 정보가 기존 periodic sync에 속하는지 검사합니다. */
    void bigInfo(struct bt_le_per_adv_sync *sync,
                 const struct bt_iso_biginfo *information)
    {
        if (!started || stopping || sync != periodic_sync || big_requested)
        {
            return;
        }
        if (information == nullptr || information->num_bis != 1U ||
            information->encryption != encrypted_role)
        {
            recordError(-ENOTSUP);
            return;
        }
        big_requested = true;
        k_work_submit(&big_work);
    }

    /** @brief 예상 밖 periodic sync 해제를 오류로 전달합니다. */
    void periodicTerminated(struct bt_le_per_adv_sync *sync,
                            const struct bt_le_per_adv_sync_term_info *information)
    {
        static_cast<void>(information);
        if (sync != periodic_sync)
        {
            return;
        }
        periodic_sync = nullptr;
        periodic_delete_pending = false;
        if (started && !stopping && atomic_get(&peer_ended) == 0)
        {
            recordError(-ENOLINK);
        }
    }

    struct bt_le_per_adv_sync_cb periodic_callbacks = {
        .term = periodicTerminated,
        .biginfo = bigInfo,
    };

    /** @brief callback thread 밖에서 첫 BIS를 HCI 수신 path에 동기화합니다. */
    void createBigSync(struct k_work *work)
    {
        static_cast<void>(work);
        if (!started || stopping || periodic_sync == nullptr)
        {
            return;
        }
        struct bt_iso_chan *channels[] = {&channel};
        struct bt_iso_big_sync_param parameter = {
            .bis_channels = channels,
            .num_bis = 1U,
            .bis_bitfield = BT_ISO_BIS_INDEX_BIT(1),
            .mse = BT_ISO_SYNC_MSE_ANY,
            .sync_timeout = 100U,
            .encryption = encrypted_role,
        };
        if (encrypted_role)
        {
            memcpy(parameter.bcode, broadcast_code, sizeof(parameter.bcode));
        }
        big_disconnected = false;
        const int result = bt_iso_big_sync(periodic_sync, &parameter, &big);
        if (result != 0)
        {
            big_disconnected = true;
            recordError(result);
        }
    }
#endif

    /** @brief 시작 도중 실패한 advertiser 또는 sync를 되돌립니다. */
    void releaseFailedStart()
    {
#if defined(CONFIG_BT_ISO_SYNC_RECEIVER)
        if (scan_active)
        {
            (void)bt_le_scan_stop();
            scan_active = false;
        }
        if (periodic_sync != nullptr)
        {
            if (!periodic_delete_pending)
            {
                const int result = bt_le_per_adv_sync_delete(periodic_sync);
                if (result == 0)
                {
                    periodic_delete_pending = true;
                }
                else
                {
                    recordError(result);
                }
            }
        }
        if (periodic_sync == nullptr)
        {
            periodic_delete_pending = false;
            nucode::arduino::internal::releaseBLEPeriodicSyncLease(
                &periodic_sync_owner_token);
        }
#endif
#if defined(CONFIG_BT_ISO_BROADCASTER)
        if (advertiser != nullptr)
        {
            (void)bt_le_per_adv_stop(advertiser);
            (void)bt_le_ext_adv_stop(advertiser);
            (void)bt_le_ext_adv_delete(advertiser);
            advertiser = nullptr;
        }
#endif
#if defined(CONFIG_BT_ISO_SYNC_RECEIVER)
        if (periodic_sync != nullptr)
        {
            return;
        }
#endif
        started = false;
        owner = nullptr;
        memset(broadcast_code, 0, sizeof(broadcast_code));
    }

    /** @brief BIG callback이 닫힌 뒤 광고 또는 sync 자원을 반환합니다. */
    Error finishStop()
    {
        if (!stopping)
        {
            return Error::none;
        }
        if ((big != nullptr && !big_disconnected) ||
            channel.state == BT_ISO_STATE_CONNECTED ||
            channel.state == BT_ISO_STATE_CONNECTING ||
            channel.state == BT_ISO_STATE_DISCONNECTING)
        {
            if (k_uptime_get() - stop_started_ms > 30000)
            {
                recordError(-ETIMEDOUT);
                return Error::transport_failure;
            }
            return Error::busy;
        }
        big = nullptr;
#if defined(CONFIG_BT_ISO_BROADCASTER)
        if (advertiser != nullptr)
        {
            const int periodic_result = bt_le_per_adv_stop(advertiser);
            const int advertising_result = bt_le_ext_adv_stop(advertiser);
            const int delete_result = bt_le_ext_adv_delete(advertiser);
            if (periodic_result != 0 || advertising_result != 0 || delete_result != 0)
            {
                recordError(-EIO);
                return Error::transport_failure;
            }
            advertiser = nullptr;
        }
#endif
#if defined(CONFIG_BT_ISO_SYNC_RECEIVER)
        if (periodic_sync != nullptr)
        {
            if (!periodic_delete_pending)
            {
                const int result = bt_le_per_adv_sync_delete(periodic_sync);
                if (result != 0)
                {
                    recordError(result);
                    return Error::transport_failure;
                }
                periodic_delete_pending = true;
            }
            if (periodic_sync != nullptr)
            {
                if (k_uptime_get() - stop_started_ms > 30000)
                {
                    recordError(-ETIMEDOUT);
                    return Error::transport_failure;
                }
                return Error::busy;
            }
        }
#endif
        k_msgq_purge(&receive_queue);
        memset(&channel, 0, sizeof(channel));
        started = false;
        stopping = false;
        owner = nullptr;
        memset(broadcast_code, 0, sizeof(broadcast_code));
        atomic_set(&channel_ready, 0);
        atomic_set(&peer_ended, 0);
#if defined(CONFIG_NUCODE_BLE_ISO_MODE_BIS_TIME_SOURCE)
        atomic_set(&tx_sync_available, 0);
#endif
#if defined(CONFIG_BT_ISO_SYNC_RECEIVER)
        nucode::arduino::internal::releaseBLEPeriodicSyncLease(
            &periodic_sync_owner_token);
#endif
        return Error::none;
    }
}

namespace nucode::ble::iso
{
    /** @brief 16-byte session ID로 한 BIG/BIS source 또는 receiver를 시작합니다. */
    Error RawBis::begin(Role role, const std::uint8_t requested_id[16],
                        const std::uint8_t requested_code[16]) noexcept
    {
        const Role configured = relay_role ?
            (source_role ? Role::cis_to_bis_bridge : Role::cis_to_bis_receiver) :
            (time_role ?
                (source_role ? Role::bis_time_source : Role::bis_time_receiver) :
                (encrypted_role ?
                    (source_role ? Role::bis_encrypted_source : Role::bis_encrypted_receiver) :
                    (source_role ? Role::bis_source : Role::bis_receiver)));
        if (role != configured)
        {
            return Error::configuration_mismatch;
        }
        if (requested_id == nullptr)
        {
            return Error::invalid_argument;
        }
        if (encrypted_role == (requested_code == nullptr))
        {
            return Error::invalid_argument;
        }
        if (owner != nullptr || started || stopping)
        {
            return Error::busy;
        }
#if defined(CONFIG_BT_ISO_SYNC_RECEIVER)
        if (!nucode::arduino::internal::claimBLEPeriodicSyncLease(
                &periodic_sync_owner_token))
        {
            return Error::busy;
        }
#endif
        owner = this;
        memcpy(session_id, requested_id, session_length);
        if (encrypted_role)
        {
            memcpy(broadcast_code, requested_code, sizeof(broadcast_code));
        }
        atomic_set(&native_error, 0);
        atomic_set(&channel_ready, 0);
        atomic_set(&peer_ended, 0);
#if defined(CONFIG_NUCODE_BLE_ISO_MODE_BIS_TIME_SOURCE)
        tx_sync = {};
        tx_sync_seen = false;
        atomic_set(&tx_sync_available, 0);
#endif
        k_msgq_purge(&receive_queue);
        next_sequence = 0U;
        sync_requested = false;
        big_requested = false;
        big_disconnected = true;
#if defined(CONFIG_BT_ISO_SYNC_RECEIVER)
        periodic_delete_pending = false;
#endif
        memset(&channel, 0, sizeof(channel));
        memset(&qos, 0, sizeof(qos));
        channel.ops = &operations;
        channel.qos = &qos;
        if (!bluetooth_enabled)
        {
            const int result = bt_enable(nullptr);
            if (result != 0 && result != -EALREADY)
            {
                recordError(result);
                owner = nullptr;
                memset(broadcast_code, 0, sizeof(broadcast_code));
#if defined(CONFIG_BT_ISO_SYNC_RECEIVER)
                nucode::arduino::internal::releaseBLEPeriodicSyncLease(
                    &periodic_sync_owner_token);
#endif
                return Error::transport_failure;
            }
            bluetooth_enabled = true;
        }
        started = true;
#if defined(CONFIG_BT_ISO_BROADCASTER)
        transmit_qos.sdu = CONFIG_BT_ISO_TX_MTU;
        transmit_qos.phy = BT_GAP_LE_PHY_2M;
        transmit_qos.rtn = relay_role ? 10U : (time_role ? 2U : 1U);
        qos.tx = &transmit_qos;
        const struct bt_le_adv_param advertising_parameter =
            BT_LE_ADV_PARAM_INIT(BT_LE_ADV_OPT_EXT_ADV,
                                 BT_GAP_MS_TO_ADV_INTERVAL(50),
                                 BT_GAP_MS_TO_ADV_INTERVAL(50), nullptr);
        int result = bt_le_ext_adv_create(&advertising_parameter, nullptr, &advertiser);
        if (result == 0)
        {
            const struct bt_data data[] = {
                BT_DATA(BT_DATA_MANUFACTURER_DATA, session_id, sizeof(session_id)),
            };
            result = bt_le_ext_adv_set_data(advertiser, data, ARRAY_SIZE(data), nullptr, 0U);
        }
        if (result == 0)
        {
            const struct bt_le_per_adv_param periodic_parameter =
                BT_LE_PER_ADV_PARAM_INIT(BT_GAP_MS_TO_PER_ADV_INTERVAL(
                                             relay_role ? 20 : 60),
                                         BT_GAP_MS_TO_PER_ADV_INTERVAL(
                                             relay_role ? 20 : 60),
                                         BT_LE_PER_ADV_OPT_NONE);
            result = bt_le_per_adv_set_param(advertiser, &periodic_parameter);
        }
        if (result == 0)
        {
            result = bt_le_per_adv_start(advertiser);
        }
        if (result == 0)
        {
            result = bt_le_ext_adv_start(advertiser, BT_LE_EXT_ADV_START_DEFAULT);
        }
        if (result == 0)
        {
            struct bt_iso_chan *channels[] = {&channel};
            struct bt_iso_big_create_param parameter = {
                .bis_channels = channels,
                .num_bis = 1U,
                .interval = relay_role ? 20000U : 10000U,
                .latency = relay_role ? 40U : 20U,
                .packing = BT_ISO_PACKING_SEQUENTIAL,
                .framing = BT_ISO_FRAMING_UNFRAMED,
                .encryption = encrypted_role,
            };
            if (encrypted_role)
            {
                memcpy(parameter.bcode, broadcast_code, sizeof(parameter.bcode));
            }
            big_disconnected = false;
            result = bt_iso_big_create(advertiser, &parameter, &big);
        }
        if (result != 0)
        {
            recordError(result);
            releaseFailedStart();
            return Error::transport_failure;
        }
#else
        receive_qos.sdu = CONFIG_BT_ISO_RX_MTU;
        receive_qos.phy = BT_GAP_LE_PHY_2M;
        qos.rx = &receive_qos;
        k_work_init(&sync_work, createPeriodicSync);
        k_work_init(&big_work, createBigSync);
        if (!callbacks_registered)
        {
            bt_le_scan_cb_register(&scan_callbacks);
            bt_le_per_adv_sync_cb_register(&periodic_callbacks);
            callbacks_registered = true;
        }
        const int result = bt_le_scan_start(BT_LE_SCAN_PASSIVE, nullptr);
        if (result != 0)
        {
            recordError(result);
            releaseFailedStart();
            return Error::transport_failure;
        }
        scan_active = true;
#endif
        return Error::none;
    }

    /** @brief 비동기 BIG 종료와 native 오류를 Arduino loop에 반영합니다. */
    Error RawBis::poll() noexcept
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
        const int failure = atomic_get(&native_error);
        if (failure != 0 &&
            !(failure == -ENOLINK && atomic_get(&peer_ended) != 0))
        {
            return Error::transport_failure;
        }
        return atomic_get(&peer_ended) != 0 ? Error::peer_stopped : Error::none;
    }

    /** @brief 사용자 SDU를 Zephyr net_buf에 복사해 한 BIS로 보냅니다. */
    Error RawBis::sendFrame(const std::uint8_t *data, std::size_t length) noexcept
    {
        if (data == nullptr || length == 0U || length > frame_capacity)
        {
            return Error::invalid_argument;
        }
        if (!source_role || owner != this || !started || stopping ||
            atomic_get(&channel_ready) == 0)
        {
            return Error::not_ready;
        }
        if (time_role && next_sequence > 0U)
        {
            return Error::invalid_argument;
        }
#if defined(CONFIG_BT_ISO_BROADCASTER)
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
#else
        return Error::not_ready;
#endif
    }

    /** @brief time source의 사용자 SDU를 명시적 HCI 시각으로 보냅니다. */
    Error RawBis::sendFrameAt(const std::uint8_t *data, std::size_t length,
                              std::uint32_t timestamp_us) noexcept
    {
        if (data == nullptr || length == 0U || length > frame_capacity)
        {
            return Error::invalid_argument;
        }
        if (!time_role || !source_role || owner != this || !started || stopping ||
            atomic_get(&channel_ready) == 0 || next_sequence == 0U)
        {
            return Error::not_ready;
        }
#if defined(CONFIG_NUCODE_BLE_ISO_MODE_BIS_TIME_SOURCE)
        struct net_buf *buffer = net_buf_alloc(&transmit_pool, K_NO_WAIT);
        if (buffer == nullptr)
        {
            return Error::busy;
        }
        net_buf_reserve(buffer, BT_ISO_CHAN_SEND_RESERVE);
        net_buf_add_mem(buffer, data, length);
        const int result = bt_iso_chan_send_ts(&channel, buffer, next_sequence,
                                                timestamp_us);
        if (result != 0)
        {
            net_buf_unref(buffer);
            recordError(result);
            return Error::transport_failure;
        }
        ++next_sequence;
        return Error::none;
#else
        return Error::not_ready;
#endif
    }

    /** @brief 완료된 SDU의 HCI sequence·시각을 Arduino loop에서 한 번 읽습니다. */
    bool RawBis::takeTxSync(BisTxSync &sync) noexcept
    {
#if defined(CONFIG_NUCODE_BLE_ISO_MODE_BIS_TIME_SOURCE)
        if (owner != this || !started || stopping ||
            atomic_get(&tx_sync_available) == 0)
        {
            return false;
        }
        sync = tx_sync;
        atomic_set(&tx_sync_available, 0);
        return true;
#else
        static_cast<void>(sync);
        return false;
#endif
    }

    /** @brief 수신 queue에서 다음 사용자 frame을 복사합니다. */
    bool RawBis::readFrame(BisFrame &frame) noexcept
    {
        if (owner != this || !started || stopping)
        {
            return false;
        }
        return k_msgq_get(&receive_queue, &frame, K_NO_WAIT) == 0;
    }

    /** @brief BIG과 scan/광고의 해제를 예약합니다. */
    Error RawBis::stop() noexcept
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
        if (big != nullptr && !big_disconnected)
        {
            const int result = bt_iso_big_terminate(big);
            if (result != 0)
            {
                recordError(result);
                return Error::transport_failure;
            }
        }
        return Error::none;
    }

    /** @brief HCI ISO path 준비를 확인합니다. */
    bool RawBis::connected() const noexcept
    {
        return owner == this && started && !stopping &&
               atomic_get(&channel_ready) != 0;
    }

    /** @brief BIG과 광고 또는 periodic sync 해제를 확인합니다. */
    bool RawBis::stopped() const noexcept
    {
        return owner != this;
    }

    /** @brief 최근 Zephyr native 실패 코드를 반환합니다. */
    int RawBis::nativeError() const noexcept
    {
        return owner == this ? atomic_get(&native_error) : 0;
    }

    /** @brief 이미지에 컴파일된 Core revision을 반환합니다. */
    const char *RawBis::buildRevision() noexcept
    {
        return NUCODE_CORE_REVISION;
    }
}

#endif
