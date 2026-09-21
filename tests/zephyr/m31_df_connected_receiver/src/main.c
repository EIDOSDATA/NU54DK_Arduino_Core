/**
 * @file main.c
 * @brief 단일 안테나 NU54DK의 연결 기반 AoA CTE 수신 API를 진단합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>

#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/conn.h>
#include <zephyr/bluetooth/direction.h>
#include <zephyr/bluetooth/hci.h>
#include <zephyr/bluetooth/hci_types.h>
#include <zephyr/kernel.h>
#include <zephyr/net_buf.h>
#include <zephyr/sys/byteorder.h>
#include <zephyr/sys/printk.h>

#define PEER_NAME "NU54-CTE-RSP"
#define PEER_NAME_LENGTH (sizeof(PEER_NAME) - 1U)

static struct bt_conn *selected_connection;
static bool connecting;
static const uint8_t antenna_pattern[] = {0U, 0U};

/** @brief Host 검증과 controller 수락 범위를 분리해 두 HCI 명령을 진단합니다. */
static void diagnose_controller(struct bt_conn *connection)
{
    uint16_t handle = 0U;
    int result = bt_hci_get_conn_handle(connection, &handle);
    if (result != 0)
    {
        printk("DF_CONN|HANDLE|code=%d\n", result);
        return;
    }

    struct net_buf *command = bt_hci_cmd_alloc(K_FOREVER);
    if (command == NULL)
    {
        printk("DF_CONN|RAW_RX_PARAM|code=%d\n", -ENOBUFS);
        return;
    }
    struct bt_hci_cp_le_set_conn_cte_rx_params *receive =
        net_buf_add(command, sizeof(*receive));
    receive->handle = sys_cpu_to_le16(handle);
    receive->sampling_enable = 1U;
    receive->slot_durations = BT_HCI_LE_ANTENNA_SWITCHING_SLOT_2US;
    receive->switch_pattern_len = 0U;
    struct net_buf *response = NULL;
    result = bt_hci_cmd_send_sync(BT_HCI_OP_LE_SET_CONN_CTE_RX_PARAMS,
                                  command, &response);
    printk("DF_CONN|RAW_RX_PARAM|code=%d\n", result);
    if (response != NULL)
    {
        net_buf_unref(response);
    }
    if (result != 0)
    {
        return;
    }

    command = bt_hci_cmd_alloc(K_FOREVER);
    if (command == NULL)
    {
        printk("DF_CONN|RAW_REQUEST|code=%d\n", -ENOBUFS);
        return;
    }
    struct bt_hci_cp_le_conn_cte_req_enable *request =
        net_buf_add(command, sizeof(*request));
    request->handle = sys_cpu_to_le16(handle);
    request->enable = 1U;
    request->cte_request_interval = sys_cpu_to_le16(10U);
    request->requested_cte_length = 0x14U;
    request->requested_cte_type = BT_HCI_LE_AOA_CTE;
    response = NULL;
    result = bt_hci_cmd_send_sync(BT_HCI_OP_LE_CONN_CTE_REQ_ENABLE,
                                  command, &response);
    printk("DF_CONN|RAW_REQUEST|code=%d\n", result);
    if (response != NULL)
    {
        net_buf_unref(response);
    }
}

/** @brief scan 광고에서 CTE 응답자의 이름을 확인합니다. */
static bool inspect_data(struct bt_data *data, void *context)
{
    bool *matched = context;
    if ((data->type == BT_DATA_NAME_COMPLETE) &&
        (data->data_len == PEER_NAME_LENGTH) &&
        (memcmp(data->data, PEER_NAME, PEER_NAME_LENGTH) == 0))
    {
        *matched = true;
    }
    return true;
}

/** @brief 이름이 일치하는 연결 가능 peer 한 대만 선택합니다. */
static void scan_received(const bt_addr_le_t *address, int8_t rssi, uint8_t type,
                          struct net_buf_simple *payload)
{
    ARG_UNUSED(rssi);
    if (connecting || ((type != BT_GAP_ADV_TYPE_ADV_IND) &&
                       (type != BT_GAP_ADV_TYPE_SCAN_RSP)))
    {
        return;
    }
    bool matched = false;
    bt_data_parse(payload, inspect_data, &matched);
    if (!matched)
    {
        return;
    }
    connecting = true;
    int result = bt_le_scan_stop();
    printk("DF_CONN|SCAN_STOP|code=%d\n", result);
    if (result != 0)
    {
        connecting = false;
        return;
    }
    result = bt_conn_le_create(address, BT_CONN_LE_CREATE_CONN,
                               BT_LE_CONN_PARAM_DEFAULT, &selected_connection);
    printk("DF_CONN|CONNECT_REQUEST|code=%d\n", result);
}

/** @brief 연결 후 안테나 정보를 확인하고 AoA RX 설정 결과를 출력합니다. */
static void connected(struct bt_conn *connection, uint8_t error)
{
    if ((error != 0U) || (connection != selected_connection))
    {
        printk("DF_CONN|CONNECTED|error=%u\n", error);
        return;
    }
    printk("DF_CONN|CONNECTED|error=0\n");

    struct bt_df_conn_cte_rx_param receiver = {
        .cte_types = BT_DF_CTE_TYPE_AOA,
        .slot_durations = BT_HCI_LE_ANTENNA_SWITCHING_SLOT_2US,
        .num_ant_ids = sizeof(antenna_pattern),
        .ant_ids = antenna_pattern,
    };
    const int result = bt_df_conn_cte_rx_enable(connection, &receiver);
    printk("DF_CONN|AOA_RX_ENABLE|code=%d\n", result);
    if (result != 0)
    {
        diagnose_controller(connection);
        return;
    }
    const struct bt_df_conn_cte_req_params request = {
        .interval = 10U,
        .cte_length = 0x14U,
        .cte_type = BT_DF_CTE_TYPE_AOA,
    };
    printk("DF_CONN|CTE_REQUEST_ENABLE|code=%d\n",
           bt_df_conn_cte_req_enable(connection, &request));
}

/** @brief 연결 중단 원본 HCI reason을 진단합니다. */
static void disconnected(struct bt_conn *connection, uint8_t reason)
{
    ARG_UNUSED(connection);
    printk("DF_CONN|DISCONNECTED|reason=%u\n", reason);
}

/** @brief 실제 연결 CTE IQ report가 왔을 때만 결과를 기록합니다. */
static void iq_received(struct bt_conn *connection,
                        const struct bt_df_conn_iq_samples_report *report)
{
    ARG_UNUSED(connection);
    printk("DF_CONN|IQ|error=%u|count=%u|type=%u|status=%u|rssi=%d\n",
           report->err, report->sample_count, report->cte_type,
           report->packet_status, report->rssi);
}

BT_CONN_CB_DEFINE(df_connected_callbacks) = {
    .connected = connected,
    .disconnected = disconnected,
    .cte_report_cb = iq_received,
};

/** @brief controller 안테나 수와 연결 기반 AoA 수신 API를 차례로 진단합니다. */
int main(void)
{
    int result = bt_enable(NULL);
    if (result != 0)
    {
        printk("DF_CONN|BT_ENABLE|code=%d\n", result);
        return 0;
    }

    struct net_buf *response = NULL;
    result = bt_hci_cmd_send_sync(BT_HCI_OP_LE_READ_ANT_INFO, NULL, &response);
    if (result == 0)
    {
        const struct bt_hci_rp_le_read_ant_info *information =
            (const void *)response->data;
        printk("DF_CONN|ANT_INFO|count=%u|max_pattern=%u|max_cte=%u\n",
               information->num_ant, information->max_switch_pattern_len,
               information->max_cte_len);
        net_buf_unref(response);
    }
    else
    {
        printk("DF_CONN|ANT_INFO|code=%d\n", result);
    }

    const struct bt_le_scan_param parameters = {
        .type = BT_LE_SCAN_TYPE_ACTIVE,
        .options = BT_LE_SCAN_OPT_NONE,
        .interval = BT_GAP_SCAN_FAST_INTERVAL,
        .window = BT_GAP_SCAN_FAST_WINDOW,
    };
    result = bt_le_scan_start(&parameters, scan_received);
    printk("DF_CONN|SCANNING|code=%d\n", result);
    return 0;
}
