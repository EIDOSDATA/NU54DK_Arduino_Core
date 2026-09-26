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
#include <zephyr/device.h>
#include <zephyr/debug/thread_analyzer.h>
#include <zephyr/drivers/uart.h>
#include <zephyr/kernel.h>
#include <zephyr/net_buf.h>
#include <zephyr/sys/byteorder.h>
#include <zephyr/sys/printk.h>
#include <sys_malloc.h>

#include "conn_internal.h"

#define PEER_NAME "NU54-CTE-RSP"
#define PEER_NAME_LENGTH (sizeof(PEER_NAME) - 1U)

static struct bt_conn *selected_connection;
static bool connecting;
static const uint8_t antenna_pattern[] = {0U, 0U};
K_MUTEX_DEFINE(connection_mutex);

/** @brief 진단 image의 thread별 stack 예약량과 최대 사용량을 출력합니다. */
static void report_thread(struct thread_analyzer_info *info)
{
    printk("P2_STACK name=%s reserved=%u used=%u\n", info->name,
           (unsigned int)info->stack_size, (unsigned int)info->stack_used);
}

/** @brief 연결 종료 뒤 관찰 가능한 stack·heap 사용량을 출력합니다. */
static void report_memory(void)
{
    printk("P2_PHASE name=stopped\n");
    thread_analyzer_run(report_thread, 0U);

    struct sys_memory_stats stats = {0};
    if (malloc_runtime_stats_get(&stats) == 0)
    {
        printk("P2_MALLOC free=%u allocated=%u peak=%u\n",
               (unsigned int)stats.free_bytes,
               (unsigned int)stats.allocated_bytes,
               (unsigned int)stats.max_allocated_bytes);
    }

    struct k_heap *heaps = NULL;
    const int count = k_heap_array_get(&heaps);
    for (int index = 0; index < count; ++index)
    {
        if (sys_heap_runtime_stats_get(&heaps[index].heap, &stats) == 0)
        {
            printk("P2_KHEAP index=%d free=%u allocated=%u peak=%u\n", index,
                   (unsigned int)stats.free_bytes,
                   (unsigned int)stats.allocated_bytes,
                   (unsigned int)stats.max_allocated_bytes);
        }
    }
}

/**
 * @brief 원시 HCI 수신 설정과 Zephyr Host의 report gate 상태를 동기화합니다.
 *
 * 공개 API가 단일 안테나 capability를 이유로 HCI 전송 전에 거부한 경우에만
 * 사용합니다. controller가 수락한 수신 설정의 수명만 Host 내부 상태에
 * 반영하며, IQ event나 sample을 생성하지 않습니다.
 */
static void set_diagnostic_host_rx_state(struct bt_conn *connection,
                                         bool enable)
{
    if (enable)
    {
        connection->cte_types = BT_DF_CTE_TYPE_AOA;
        atomic_set_bit(connection->flags, BT_CONN_CTE_RX_PARAMS_SET);
        atomic_set_bit(connection->flags, BT_CONN_CTE_RX_ENABLED);
    }
    else
    {
        atomic_clear_bit(connection->flags, BT_CONN_CTE_RX_ENABLED);
        connection->cte_types = BT_DF_CTE_TYPE_NONE;
    }

    printk("DF_CONN|HOST_RX_STATE|enabled=%u|params=%u|cte_types=%u\n",
           atomic_test_bit(connection->flags, BT_CONN_CTE_RX_ENABLED) ? 1U : 0U,
           atomic_test_bit(connection->flags,
                           BT_CONN_CTE_RX_PARAMS_SET) ? 1U : 0U,
           connection->cte_types);
}

/** @brief 직접 HCI CTE 요청을 활성화하거나 중단합니다. */
static int set_raw_cte_request(struct bt_conn *connection, bool enable)
{
    uint16_t handle = 0U;
    int result = bt_hci_get_conn_handle(connection, &handle);
    if (result != 0)
    {
        return result;
    }

    struct net_buf *command = bt_hci_cmd_alloc(K_FOREVER);
    if (command == NULL)
    {
        return -ENOBUFS;
    }
    struct bt_hci_cp_le_conn_cte_req_enable *request =
        net_buf_add(command, sizeof(*request));
    request->handle = sys_cpu_to_le16(handle);
    request->enable = enable ? 1U : 0U;
    request->cte_request_interval = sys_cpu_to_le16(10U);
    request->requested_cte_length = 0x14U;
    request->requested_cte_type = BT_HCI_LE_AOA_CTE;
    struct net_buf *response = NULL;
    result = bt_hci_cmd_send_sync(BT_HCI_OP_LE_CONN_CTE_REQ_ENABLE,
                                  command, &response);
    if (response != NULL)
    {
        net_buf_unref(response);
    }
    return result;
}

/** @brief 직접 HCI IQ sampling 설정을 활성화하거나 반환합니다. */
static int set_raw_cte_reception(struct bt_conn *connection, bool enable)
{
    uint16_t handle = 0U;
    int result = bt_hci_get_conn_handle(connection, &handle);
    if (result != 0)
    {
        return result;
    }

    struct net_buf *command = bt_hci_cmd_alloc(K_FOREVER);
    if (command == NULL)
    {
        return -ENOBUFS;
    }
    struct bt_hci_cp_le_set_conn_cte_rx_params *receive =
        net_buf_add(command, sizeof(*receive));
    receive->handle = sys_cpu_to_le16(handle);
    receive->sampling_enable = enable ? 1U : 0U;
    receive->slot_durations = BT_HCI_LE_ANTENNA_SWITCHING_SLOT_2US;
    receive->switch_pattern_len = 0U;
    struct net_buf *response = NULL;
    result = bt_hci_cmd_send_sync(BT_HCI_OP_LE_SET_CONN_CTE_RX_PARAMS,
                                  command, &response);
    if (response != NULL)
    {
        net_buf_unref(response);
    }
    return result;
}

/** @brief Host 검증과 controller 수락 범위를 분리해 두 HCI 명령을 진단합니다. */
static void diagnose_controller(struct bt_conn *connection)
{
    int result = set_raw_cte_reception(connection, true);
    printk("DF_CONN|RAW_RX_PARAM|code=%d\n", result);
    if (result != 0)
    {
        return;
    }

    set_diagnostic_host_rx_state(connection, true);
    result = set_raw_cte_request(connection, true);
    printk("DF_CONN|RAW_REQUEST|code=%d\n", result);
    if (result != 0)
    {
        set_diagnostic_host_rx_state(connection, false);
        printk("DF_CONN|RAW_RX_ROLLBACK|code=%d\n",
               set_raw_cte_reception(connection, false));
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
    struct bt_conn *connection = NULL;
    result = bt_conn_le_create(address, BT_CONN_LE_CREATE_CONN,
                               BT_LE_CONN_PARAM_DEFAULT, &connection);
    printk("DF_CONN|CONNECT_REQUEST|code=%d\n", result);
    k_mutex_lock(&connection_mutex, K_FOREVER);
    if (result != 0)
    {
        connecting = false;
    }
    else
    {
        selected_connection = connection;
    }
    k_mutex_unlock(&connection_mutex);
}

/** @brief 연결 후 안테나 정보를 확인하고 AoA RX 설정 결과를 출력합니다. */
static void connected(struct bt_conn *connection, uint8_t error)
{
    k_mutex_lock(&connection_mutex, K_FOREVER);
    const bool selected = connection == selected_connection;
    if ((error != 0U) && selected)
    {
        selected_connection = NULL;
        connecting = false;
    }
    k_mutex_unlock(&connection_mutex);
    if ((error != 0U) || !selected)
    {
        printk("DF_CONN|CONNECTED|error=%u\n", error);
        if ((error != 0U) && selected)
        {
            bt_conn_unref(connection);
        }
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
    printk("DF_CONN|DISCONNECTED|reason=%u\n", reason);
    k_mutex_lock(&connection_mutex, K_FOREVER);
    const bool selected = connection == selected_connection;
    if (selected)
    {
        set_diagnostic_host_rx_state(connection, false);
        selected_connection = NULL;
        connecting = false;
    }
    k_mutex_unlock(&connection_mutex);
    if (selected)
    {
        bt_conn_unref(connection);
        printk("DF_CONN|STOPPED\n");
    }
}

/** @brief 요청·sampling·ACL을 순서대로 중단해 controller 자원을 반환합니다. */
static void stop_diagnostic(void)
{
    k_mutex_lock(&connection_mutex, K_FOREVER);
    struct bt_conn *connection = selected_connection;
    if (connection != NULL)
    {
        bt_conn_ref(connection);
    }
    k_mutex_unlock(&connection_mutex);
    if (connection == NULL)
    {
        printk("DF_CONN|STOPPED\n");
        return;
    }
    printk("DF_CONN|RAW_REQUEST_STOP|code=%d\n",
           set_raw_cte_request(connection, false));
    printk("DF_CONN|RAW_RX_STOP|code=%d\n",
           set_raw_cte_reception(connection, false));
    set_diagnostic_host_rx_state(connection, false);
    printk("DF_CONN|DISCONNECT_REQUEST|code=%d\n",
           bt_conn_disconnect(connection,
                              BT_HCI_ERR_REMOTE_USER_TERM_CONN));
    bt_conn_unref(connection);
}

/** @brief 실제 연결 CTE IQ report가 왔을 때만 결과를 기록합니다. */
static void iq_received(struct bt_conn *connection,
                        const struct bt_df_conn_iq_samples_report *report)
{
    ARG_UNUSED(connection);
    int first_i = 0;
    int first_q = 0;
    if ((report->sample_count > 0U) &&
        (report->sample_type == BT_DF_IQ_SAMPLE_8_BITS_INT))
    {
        first_i = report->sample[0].i;
        first_q = report->sample[0].q;
    }
    printk("DF_CONN|IQ|error=%u|count=%u|type=%u|status=%u|sample_type=%u|"
           "slot=%u|event=%u|channel=%u|i0=%d|q0=%d|rssi=%d\n",
           report->err, report->sample_count, report->cte_type,
           report->packet_status, report->sample_type, report->slot_durations,
           report->conn_evt_counter, report->chan_idx, first_i, first_q,
           report->rssi);
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

    const struct device *console = DEVICE_DT_GET(DT_CHOSEN(zephyr_console));
    while (true)
    {
        uint8_t command = 0U;
        if (device_is_ready(console) &&
            (uart_poll_in(console, &command) == 0) && (command == 's'))
        {
            stop_diagnostic();
            k_sleep(K_MSEC(200));
            report_memory();
        }
        k_sleep(K_MSEC(10));
    }
    return 0;
}
