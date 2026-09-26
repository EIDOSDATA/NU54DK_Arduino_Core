/**
 * @file main.c
 * @brief 상대 LE CoC credit 고갈과 유한 복구를 직접 관찰합니다.
 *
 * SPDX-License-Identifier: Apache-2.0
 */

#include <errno.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>
#include <sys_malloc.h>

#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/conn.h>
#include <zephyr/bluetooth/l2cap.h>
#include <zephyr/kernel.h>
#include <zephyr/debug/thread_analyzer.h>
#include <zephyr/device.h>
#include <zephyr/drivers/uart.h>
#include <zephyr/net_buf.h>
#include <zephyr/sys/printk.h>

#define P2_COC_PSM 0x0080
#define P2_COC_CHANNEL_COUNT 2
#define P2_COC_SDU_SIZE 512
#define P2_COC_RX_POOL_COUNT 4
#define P2_COC_INITIAL_CREDIT_COUNT 1

struct p2_coc_channel
{
    struct bt_l2cap_le_chan channel;
    bool occupied;
};

static struct p2_coc_channel channels[P2_COC_CHANNEL_COUNT];
static struct net_buf *held[P2_COC_INITIAL_CREDIT_COUNT];
static struct bt_l2cap_chan *held_channels[P2_COC_INITIAL_CREDIT_COUNT];
static size_t held_count;
static bool hold_mode;

NET_BUF_POOL_FIXED_DEFINE(rx_pool, P2_COC_RX_POOL_COUNT,
                          BT_L2CAP_SDU_BUF_SIZE(P2_COC_SDU_SIZE), sizeof(uint16_t), NULL);
NET_BUF_POOL_FIXED_DEFINE(tx_pool, P2_COC_RX_POOL_COUNT,
                          BT_L2CAP_SDU_BUF_SIZE(P2_COC_SDU_SIZE),
                          CONFIG_BT_CONN_TX_USER_DATA_SIZE, NULL);

/** @brief 한 thread의 예약량과 최고 사용량을 P2 공통 형식으로 출력합니다. */
static void report_thread(struct thread_analyzer_info *info)
{
    printk("P2_STACK name=%s reserved=%zu used=%zu\n",
           info->name, info->stack_size, info->stack_used);
}

/** @brief native peer의 stack과 libc/kernel heap 누적 상태를 출력합니다. */
static void report_memory(const char *phase)
{
    struct sys_memory_stats stats = {0};
    struct k_heap *heaps = NULL;
    int count;

    printk("P2_PHASE name=%s\n", phase);
    thread_analyzer_run(report_thread, 0U);
    if (malloc_runtime_stats_get(&stats) == 0)
    {
        printk("P2_MALLOC free=%zu allocated=%zu peak=%zu\n",
               stats.free_bytes, stats.allocated_bytes, stats.max_allocated_bytes);
    }
    count = k_heap_array_get(&heaps);
    for (int index = 0; index < count; ++index)
    {
        if (sys_heap_runtime_stats_get(&heaps[index].heap, &stats) == 0)
        {
            printk("P2_KHEAP index=%d free=%zu allocated=%zu peak=%zu\n",
                   index, stats.free_bytes, stats.allocated_bytes,
                   stats.max_allocated_bytes);
        }
    }
}

/** @brief LE CoC SDU 수신용 고정 buffer를 제공합니다. */
static struct net_buf *allocate_buffer(struct bt_l2cap_chan *channel)
{
    ARG_UNUSED(channel);
    return net_buf_alloc(&rx_pool, K_FOREVER);
}

/** @brief 일반 모드에서는 SDU를 그대로 반향하고 시험 모드에서는 credit을 보류합니다. */
static int received(struct bt_l2cap_chan *channel, struct net_buf *buffer)
{
    if (hold_mode && held_count < ARRAY_SIZE(held))
    {
        held[held_count] = buffer;
        held_channels[held_count] = channel;
        ++held_count;
        printk("P2_COC_PEER_CREDIT_HELD count=%zu\n", held_count);
        if (held_count == ARRAY_SIZE(held))
        {
            printk("P2_COC_PEER_CREDITS_EXHAUSTED held=%zu dwell_ms=2000\n", held_count);
            report_memory("peer-credit-exhausted");
        }
        return -EINPROGRESS;
    }

    struct net_buf *reply = net_buf_alloc(&tx_pool, K_NO_WAIT);
    if (reply == NULL)
    {
        printk("P2_FAIL stage=coc-peer-tx-alloc\n");
        return 0;
    }
    net_buf_reserve(reply, BT_L2CAP_SDU_CHAN_SEND_RESERVE);
    net_buf_add_mem(reply, buffer->data, buffer->len);
    const int result = bt_l2cap_chan_send(channel, reply);
    if (result < 0)
    {
        net_buf_unref(reply);
        printk("P2_FAIL stage=coc-peer-echo native=%d\n", result);
    }
    return 0;
}

/** @brief 연결 종료 시 미반환 buffer를 반환하고 channel slot을 해제합니다. */
static void disconnected(struct bt_l2cap_chan *channel)
{
    for (size_t index = 0U; index < ARRAY_SIZE(channels); ++index)
    {
        if (&channels[index].channel.chan == channel)
        {
            channels[index].occupied = false;
        }
    }
    printk("P2_COC_PEER_DISCONNECTED\n");
}

static const struct bt_l2cap_chan_ops channel_operations = {
    .connected = NULL,
    .disconnected = disconnected,
    .encrypt_change = NULL,
    .alloc_seg = NULL,
    .alloc_buf = allocate_buffer,
    .recv = received,
    .sent = NULL,
    .status = NULL,
    .released = NULL,
    .reconfigured = NULL,
};

/** @brief 최대 두 channel에 고정 slot과 512-byte MTU를 배정합니다. */
static int accept_channel(struct bt_conn *connection, struct bt_l2cap_server *server,
                          struct bt_l2cap_chan **channel)
{
    ARG_UNUSED(connection);
    ARG_UNUSED(server);
    for (size_t index = 0U; index < ARRAY_SIZE(channels); ++index)
    {
        if (!channels[index].occupied)
        {
            memset(&channels[index].channel, 0, sizeof(channels[index].channel));
            channels[index].occupied = true;
            channels[index].channel.chan.ops = &channel_operations;
            channels[index].channel.rx.mtu = P2_COC_SDU_SIZE;
            channels[index].channel.required_sec_level = BT_SECURITY_L1;
            *channel = &channels[index].channel.chan;
            printk("P2_COC_PEER_CHANNEL count=%zu\n", index + 1U);
            return 0;
        }
    }
    return -ENOMEM;
}

static struct bt_l2cap_server server = {
    .psm = P2_COC_PSM,
    .sec_level = BT_SECURITY_L1,
    .accept = accept_channel,
};

/** @brief 보류한 SDU를 모두 완료해 상대 credit을 명시적으로 반환합니다. */
static void release_credits(void)
{
    const size_t release_count = held_count;
    hold_mode = false;
    for (size_t index = 0U; index < release_count; ++index)
    {
        const int result = bt_l2cap_chan_recv_complete(held_channels[index], held[index]);
        if (result < 0)
        {
            printk("P2_FAIL stage=coc-peer-credit-release native=%d\n", result);
        }
        held[index] = NULL;
        held_channels[index] = NULL;
    }
    held_count = 0U;
    printk("P2_COC_PEER_CREDITS_RELEASED count=%zu\n", release_count);
    report_memory("credit-released");
}

/** @brief 광고를 시작하고 UART 명령으로 hold/release/stop을 유한 제어합니다. */
int main(void)
{
    const struct device *console = DEVICE_DT_GET(DT_CHOSEN(zephyr_console));
    const struct bt_data advertising[] = {
        BT_DATA_BYTES(BT_DATA_FLAGS, BT_LE_AD_GENERAL | BT_LE_AD_NO_BREDR),
        BT_DATA(BT_DATA_NAME_COMPLETE, CONFIG_BT_DEVICE_NAME,
                sizeof(CONFIG_BT_DEVICE_NAME) - 1U),
    };
    int result = bt_enable(NULL);
    if (result != 0)
    {
        printk("P2_FAIL stage=coc-peer-bt-enable native=%d\n", result);
        return result;
    }
    result = bt_l2cap_server_register(&server);
    if (result != 0)
    {
        printk("P2_FAIL stage=coc-peer-register native=%d\n", result);
        return result;
    }
    result = bt_le_adv_start(BT_LE_ADV_CONN_FAST_1, advertising,
                             ARRAY_SIZE(advertising), NULL, 0U);
    if (result != 0)
    {
        printk("P2_FAIL stage=coc-peer-advertise native=%d\n", result);
        return result;
    }
    printk("P2_READY role=coc-credit-peer\n");
    report_memory("ready");

    while (true)
    {
        uint8_t command = 0U;
        if (uart_poll_in(console, &command) == 0)
        {
            if (command == 'h')
            {
                hold_mode = true;
                printk("P2_COC_PEER_HOLD_ARMED credits=%d\n",
                       P2_COC_INITIAL_CREDIT_COUNT);
            }
            else if (command == 'r')
            {
                release_credits();
            }
            else if (command == 's')
            {
                if (held_count != 0U)
                {
                    release_credits();
                }
                bt_le_adv_stop();
                const int disable_result = bt_disable();
                report_memory("stopped");
                printk("P2_STOP role=coc-credit-peer bt_disable=%d\n", disable_result);
                break;
            }
        }
        k_sleep(K_MSEC(1));
    }
    return 0;
}
