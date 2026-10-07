/**
 * @file main.c
 * @brief upstream controller의 독점 소유권과 120초 hardware lease를 보장한다.
 * SPDX-License-Identifier: MIT
 */
#include <zephyr/drivers/hwinfo.h>
#include <zephyr/drivers/watchdog.h>
#include <zephyr/kernel.h>
#include <errno.h>

#if (!defined(NUCODE_DIAGNOSTIC_HOST_APP) && defined(CONFIG_BT_HCI_HOST)) ||                       \
    defined(CONFIG_NUCODE_ARDUINO_CORE)
#error "Raw controller and Arduino/Host stack cannot share RADIO or buffers"
#endif
#if !defined(NUCODE_DIAGNOSTIC_HOST_APP) &&                                                        \
    (defined(CONFIG_UART_CONSOLE) || defined(CONFIG_PRINTK) || defined(CONFIG_LOG))
#error "HCI transport cannot share console or log output"
#endif

int nucode_upstream_main(void);

/** @brief 시작 후 120초가 지나면 reset하며 watchdog reset 뒤에는 RF를 재개하지 않는다. */
int main(void)
{
    uint32_t cause = 0;
    if (hwinfo_get_reset_cause(&cause) != 0)
    {
        return -EPERM;
    }
    (void)hwinfo_clear_reset_cause();
    if ((cause & RESET_WATCHDOG) != 0)
    {
        return -EPERM;
    }
    const struct device *watchdog = DEVICE_DT_GET(DT_ALIAS(watchdog0));
    if (!device_is_ready(watchdog))
    {
        return -ENODEV;
    }
    const struct wdt_timeout_cfg lease = {
        .window = {.min = 0, .max = 120000},
        .flags = WDT_FLAG_RESET_SOC,
    };
    if (wdt_install_timeout(watchdog, &lease) < 0 ||
        wdt_setup(watchdog, WDT_OPT_PAUSE_HALTED_BY_DBG) != 0)
    {
        return -EIO;
    }
    return nucode_upstream_main();
}
