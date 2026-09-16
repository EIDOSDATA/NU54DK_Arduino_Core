/**
 * @file main.c
 * @brief 고정 SDK의 기본 안테나 CTE 수신 가능성을 분리 진단합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <errno.h>
#include <stdint.h>
#include <string.h>

#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/direction.h>
#include <zephyr/bluetooth/gap.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/printk.h>

#define PEER_NAME "NU54-CTE"
#define PEER_NAME_LENGTH (sizeof(PEER_NAME) - 1U)

static K_SEM_DEFINE(advertisement_found, 0, 1);
static K_SEM_DEFINE(sync_finished, 0, 1);

static bt_addr_le_t peer_address;
static uint8_t peer_sid;
static uint16_t peer_interval;
static bool peer_selected;
static bool sync_established;
static struct bt_le_per_adv_sync *periodic_sync;

/** @brief 광고 이름이 지정한 송신자와 일치하는지 확인합니다. */
static bool inspect_data(struct bt_data *data, void *user_data)
{
    bool *matched = user_data;
    if ((data->type == BT_DATA_NAME_COMPLETE) &&
        (data->data_len == PEER_NAME_LENGTH) &&
        (memcmp(data->data, PEER_NAME, PEER_NAME_LENGTH) == 0))
    {
        *matched = true;
    }
    return true;
}

/** @brief 대상 periodic 광고 하나의 주소와 SID만 고정합니다. */
static void on_scan(const struct bt_le_scan_recv_info *info, struct net_buf_simple *buffer)
{
    bool matched = false;
    if (peer_selected || (info->interval == 0U))
    {
        return;
    }
    bt_data_parse(buffer, inspect_data, &matched);
    if (!matched)
    {
        return;
    }

    bt_addr_le_copy(&peer_address, info->addr);
    peer_sid = info->sid;
    peer_interval = info->interval;
    peer_selected = true;
    printk("M31_RX|1|ADVERTISER|interval=%u|sid=%u|rssi=%d\n",
           peer_interval, peer_sid, info->rssi);
    k_sem_give(&advertisement_found);
}

/** @brief controller가 periodic sync를 수립한 시점을 기록합니다. */
static void on_synced(struct bt_le_per_adv_sync *sync,
                      struct bt_le_per_adv_sync_synced_info *info)
{
    ARG_UNUSED(sync);
    sync_established = true;
    printk("M31_RX|1|SYNCED|interval=%u|phy=%u\n", info->interval, info->phy);
    k_sem_give(&sync_finished);
}

/** @brief controller가 periodic sync를 종료한 시점을 기록합니다. */
static void on_terminated(struct bt_le_per_adv_sync *sync,
                          const struct bt_le_per_adv_sync_term_info *info)
{
    ARG_UNUSED(sync);
    ARG_UNUSED(info);
    printk("M31_RX|1|SYNC_LOST\n");
    k_sem_give(&sync_finished);
}

/** @brief 실제 controller IQ report의 형식과 개수를 기록합니다. */
static void on_iq(struct bt_le_per_adv_sync *sync,
                  const struct bt_df_per_adv_sync_iq_samples_report *report)
{
    ARG_UNUSED(sync);
    printk("M31_RX|1|IQ|count=%u|type=%u|status=%u|rssi=%d\n",
           report->sample_count, report->cte_type, report->packet_status, report->rssi);
}

static struct bt_le_scan_cb scan_callbacks = {
    .recv = on_scan,
};

static struct bt_le_per_adv_sync_cb sync_callbacks = {
    .synced = on_synced,
    .term = on_terminated,
    .cte_report_cb = on_iq,
};

/** @brief 송신 광고, periodic sync, 공개 AoA RX API를 차례로 확인합니다. */
int main(void)
{
    int result = bt_enable(NULL);
    if (result != 0)
    {
        printk("M31_RX|1|ERROR|stage=bluetooth|code=%d\n", result);
        return 0;
    }

    bt_le_scan_cb_register(&scan_callbacks);
    bt_le_per_adv_sync_cb_register(&sync_callbacks);
    const struct bt_le_scan_param scan_parameters = {
        .type = BT_LE_SCAN_TYPE_PASSIVE,
        .options = BT_LE_SCAN_OPT_FILTER_DUPLICATE,
        .interval = BT_GAP_SCAN_FAST_INTERVAL,
        .window = BT_GAP_SCAN_FAST_WINDOW,
    };
    result = bt_le_scan_start(&scan_parameters, NULL);
    if (result != 0)
    {
        printk("M31_RX|1|ERROR|stage=scan|code=%d\n", result);
        return 0;
    }
    printk("M31_RX|1|SCANNING\n");

    if (k_sem_take(&advertisement_found, K_SECONDS(30)) != 0)
    {
        printk("M31_RX|1|ERROR|stage=advertiser_timeout|code=%d\n", -ETIMEDOUT);
        return 0;
    }

    struct bt_le_per_adv_sync_param sync_parameters = {};
    bt_addr_le_copy(&sync_parameters.addr, &peer_address);
    sync_parameters.sid = peer_sid;
    sync_parameters.skip = 0U;
    sync_parameters.timeout = (uint16_t)CLAMP(
        (uint32_t)BT_GAP_PER_ADV_INTERVAL_TO_US(peer_interval) / 10000U * 7U,
        BT_GAP_PER_ADV_MIN_TIMEOUT, BT_GAP_PER_ADV_MAX_TIMEOUT);
    result = bt_le_per_adv_sync_create(&sync_parameters, &periodic_sync);
    printk("M31_RX|1|SYNC_CREATE|code=%d|timeout_10ms=%u\n",
           result, sync_parameters.timeout);
    if (result != 0)
    {
        return 0;
    }
    if ((k_sem_take(&sync_finished, K_MSEC((uint32_t)sync_parameters.timeout * 10U + 2000U)) != 0) ||
        !sync_established)
    {
        printk("M31_RX|1|SYNC_TIMEOUT\n");
        return 0;
    }

    const uint8_t antennas[] = {1U, 2U};
    const struct bt_df_per_adv_sync_cte_rx_param cte_parameters = {
        .max_cte_count = 5U,
        .cte_types = BT_DF_CTE_TYPE_AOA,
        .slot_durations = BT_HCI_LE_ANTENNA_SWITCHING_SLOT_2US,
        .num_ant_ids = ARRAY_SIZE(antennas),
        .ant_ids = antennas,
    };
    result = bt_df_per_adv_sync_cte_rx_enable(periodic_sync, &cte_parameters);
    printk("M31_RX|1|CTE_ENABLE|code=%d\n", result);
    while (true)
    {
        k_sleep(K_SECONDS(1));
    }
    return 0;
}
