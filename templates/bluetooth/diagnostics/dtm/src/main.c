/**
 * @file main.c
 * @brief 고정 NCS SDC를 이용한 유한 DTM 두 선식/H4 진단 application.
 * SPDX-License-Identifier: MIT
 */
#include <zephyr/kernel.h>
#include <zephyr/bluetooth/buf.h>
#include <zephyr/bluetooth/hci_raw.h>
#include <zephyr/drivers/uart.h>
#include <zephyr/drivers/watchdog.h>
#include <zephyr/sys/reboot.h>
#include <errno.h>
#include <bluetooth/dtm_twowire/dtm_twowire_to_hci.h>
#include "protocol.h"

#if defined(CONFIG_BT_HCI_HOST) || defined(CONFIG_NUCODE_ARDUINO_CORE)
#error "DTM owns RADIO, controller, buffers and UART exclusively"
#endif
#if defined(CONFIG_UART_CONSOLE) || defined(CONFIG_PRINTK) || defined(CONFIG_LOG)
#error "Binary diagnostic UART must not contain console or debug output"
#endif

/** @brief 3초 RF lease와 1초 controller 응답 제한은 Host 상태에 무관하게 적용한다. */
#define RF_LEASE_MS 3000
#define COMMAND_TIMEOUT_MS 1000

static K_FIFO_DEFINE(controller_events);
static const struct device *const transport = DEVICE_DT_GET(DT_CHOSEN(zephyr_console));
static const struct device *const watchdog = DEVICE_DT_GET(DT_ALIAS(watchdog0));
static int watchdog_channel;
static bool active;
static int64_t deadline;
/** @brief 읽기 전용 vendor identity는 source와 선택한 transport를 실물에서 대조한다. */
static const char source_identity[] = NUCODE_DIAGNOSTIC_REVISION NUCODE_DIAGNOSTIC_SOURCE_HASH;

/** @brief 복구 불가능한 오류에서는 재부팅하여 RADIO를 끄고 명령 대기로 돌아간다. */
static void fail_closed(void)
{
    sys_reboot(SYS_REBOOT_COLD);
}

/** @brief UART에는 오직 선택한 wire protocol byte만 전송한다. */
static void write_bytes(const uint8_t *bytes, size_t length)
{
    for (size_t index = 0; index < length; ++index)
    {
        uart_poll_out(transport, bytes[index]);
    }
}

/** @brief DTM event를 network byte 순서로 전달한다. */
static void write_twowire(uint16_t event)
{
    const uint8_t bytes[2] = {(uint8_t)(event >> 8), (uint8_t)event};
    write_bytes(bytes, sizeof(bytes));
}

/** @brief HCI command complete 오류를 일정한 frame으로 반환한다. */
static void write_hci_error(uint16_t opcode, uint8_t status)
{
    const uint8_t bytes[7] = {0x04,  0x0e, 0x04, 0x01, (uint8_t)opcode, (uint8_t)(opcode >> 8),
                              status};
    write_bytes(bytes, sizeof(bytes));
}

/** @brief 실제 controller의 matching command complete/status만 수신한다. */
static struct net_buf *execute(struct net_buf *command, uint16_t opcode)
{
    if (bt_send(command) != 0)
    {
        net_buf_unref(command);
        fail_closed();
        return NULL;
    }
    const int64_t until = k_uptime_get() + COMMAND_TIMEOUT_MS;
    while (k_uptime_get() < until)
    {
        struct net_buf *event = k_fifo_get(&controller_events, K_MSEC(20));
        if (event == NULL)
        {
            continue;
        }
        const uint8_t *p = event->data;
        bool matches = false;
        if (event->len >= 7 && p[0] == 0x04 && p[2] + 3 == event->len)
        {
            if (p[1] == 0x0e)
            {
                matches = ((uint16_t)p[4] | ((uint16_t)p[5] << 8)) == opcode;
            }
            else if (p[1] == 0x0f)
            {
                matches = ((uint16_t)p[5] | ((uint16_t)p[6] << 8)) == opcode;
            }
        }
        if (matches)
        {
            return event;
        }
        net_buf_unref(event);
    }
    fail_closed();
    return NULL;
}

/** @brief command buffer가 없으면 무기한 기다리지 않고 RADIO를 정지한다. */
static struct net_buf *allocate_command(void)
{
    struct net_buf *command = bt_buf_get_tx(BT_BUF_CMD, K_MSEC(100), NULL, 0);
    if (command == NULL)
    {
        fail_closed();
    }
    return command;
}

/** @brief Test End를 수행해 실제 수신 counter를 wire event로 반환한다. */
static void stop_test(bool report)
{
    struct net_buf *command = allocate_command();
    const uint8_t bytes[3] = {0x1f, 0x20, 0x00};
    net_buf_add_mem(command, bytes, sizeof(bytes));
    struct net_buf *event = execute(command, 0x201f);
    if (event->len != 9 || event->data[1] != 0x0e || event->data[6] != 0)
    {
        net_buf_unref(event);
        fail_closed();
        return;
    }
    active = false;
    if (report)
    {
        if (IS_ENABLED(CONFIG_NUCODE_DIAG_H4))
        {
            write_bytes(event->data, event->len);
        }
        else
        {
            const uint16_t count = (uint16_t)event->data[7] | ((uint16_t)event->data[8] << 8);
            write_twowire(0x8000 | MIN(count, 0x7fff));
        }
    }
    net_buf_unref(event);
}

/** @brief 표준 두 선식 setup과 TX/RX 명령을 고정 SDK 변환기로 처리한다. */
static void process_twowire(uint16_t word)
{
    if ((word & 0xff00) == 0x3f00)
    {
        const uint8_t index = word & 0xff;
        write_twowire(index < sizeof(source_identity) - 1
                          ? ((uint16_t)(uint8_t)source_identity[index] << 1)
                          : 1);
        return;
    }
    const uint8_t kind = word >> 14;
    if (kind == 3 && (word & 0x3ffc) == 0)
    {
        stop_test(true);
        return;
    }
    if (active)
    {
        if (word <= 3)
        {
            stop_test(false);
        }
        else
        {
            write_twowire(1);
            return;
        }
    }
    struct net_buf *command = allocate_command();
    uint16_t response = 1;
    dtm_tw_to_hci_status_t status = dtm_tw_to_hci_process_tw_cmd(word, command, &response);
    if (status == DTM_TW_TO_HCI_STATUS_HCI_CMD)
    {
        uint16_t opcode;
        if (!diagnostic_hci_command_opcode(command->data, command->len, &opcode))
        {
            net_buf_unref(command);
            write_twowire(1);
            return;
        }
        struct net_buf *event = execute(command, opcode);
        status = dtm_tw_to_hci_process_hci_event(word, event, &response);
        net_buf_unref(event);
    }
    else
    {
        net_buf_unref(command);
    }
    if (status != DTM_TW_TO_HCI_STATUS_TW_EVENT)
    {
        response = 1;
    }
    if ((kind == 1 || kind == 2) && response == 0)
    {
        active = true;
        deadline = k_uptime_get() + RF_LEASE_MS;
    }
    write_twowire(response);
}

/** @brief H4 모드는 진단 whitelist를 검사한 뒤 실제 SDC response를 전달한다. */
static void process_h4(const uint8_t *bytes)
{
    const uint16_t opcode = (uint16_t)bytes[1] | ((uint16_t)bytes[2] << 8);
    if (opcode == 0xfc80 && bytes[3] == 0)
    {
        const uint8_t header[7] = {0x04, 0x0e, sizeof(source_identity) + 3, 0x01, 0x80, 0xfc, 0x00};
        write_bytes(header, sizeof(header));
        write_bytes((const uint8_t *)source_identity, sizeof(source_identity) - 1);
        return;
    }
    uint8_t status = diagnostic_hci_status(opcode, &bytes[4], bytes[3]);
    if (active && diagnostic_starts(opcode))
    {
        status = 0x0c;
    }
    if (status != 0)
    {
        write_hci_error(opcode, status);
        return;
    }
    if (opcode == 0x201f)
    {
        stop_test(true);
        return;
    }
    struct net_buf *command = allocate_command();
    net_buf_add_mem(command, &bytes[1], bytes[3] + 3);
    struct net_buf *event = execute(command, opcode);
    const bool success = event->data[1] == 0x0e && event->data[6] == 0;
    if (success && diagnostic_starts(opcode))
    {
        active = true;
        deadline = k_uptime_get() + RF_LEASE_MS;
    }
    if (success && opcode == 0x0c03)
    {
        active = false;
    }
    write_bytes(event->data, event->len);
    net_buf_unref(event);
}

/** @brief raw controller와 전용 UART를 한 번 초기화하고 명령을 기다린다. */
int main(void)
{
    if (!device_is_ready(transport) || !device_is_ready(watchdog))
    {
        return -ENODEV;
    }
    const struct wdt_timeout_cfg timeout = {
        .window = {.min = 0, .max = 8000},
        .flags = WDT_FLAG_RESET_SOC,
    };
    watchdog_channel = wdt_install_timeout(watchdog, &timeout);
    if (watchdog_channel < 0 || wdt_setup(watchdog, WDT_OPT_PAUSE_HALTED_BY_DBG) != 0)
    {
        return -EIO;
    }
    const struct uart_config config = {
        .baudrate = IS_ENABLED(CONFIG_NUCODE_DIAG_H4) ? 115200 : 19200,
        .parity = UART_CFG_PARITY_NONE,
        .stop_bits = UART_CFG_STOP_BITS_1,
        .data_bits = UART_CFG_DATA_BITS_8,
        .flow_ctrl = UART_CFG_FLOW_CTRL_NONE,
    };
    if (uart_configure(transport, &config) != 0 || bt_enable_raw(&controller_events) != 0)
    {
        fail_closed();
    }
    struct diagnostic_parser parser = {0};
    for (;;)
    {
        (void)wdt_feed(watchdog, watchdog_channel);
        if (active && k_uptime_get() >= deadline)
        {
            stop_test(true);
        }
        uint8_t byte;
        if (uart_poll_in(transport, &byte) == 0 &&
            diagnostic_feed(&parser, IS_ENABLED(CONFIG_NUCODE_DIAG_H4), byte, k_uptime_get()))
        {
            if (IS_ENABLED(CONFIG_NUCODE_DIAG_H4))
            {
                process_h4(parser.bytes);
            }
            else
            {
                process_twowire(((uint16_t)parser.bytes[0] << 8) | parser.bytes[1]);
            }
        }
        k_sleep(K_USEC(100));
    }
    return 0;
}
