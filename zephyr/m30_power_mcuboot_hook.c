/**
 * @file m30_power_mcuboot_hook.c
 * @brief M30 전원 손실 HIL에서 MCUboot test swap 직전 관찰 창을 제공합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <bootutil/mcuboot_status.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/printk.h>

/** @brief test upgrade가 실제 swap에 진입하기 직전에 유한 관찰 창을 엽니다. */
void mcuboot_status_change(mcuboot_status_type_t status)
{
    if (status == MCUBOOT_STATUS_UPGRADING)
    {
        printk("M30POWER|1|WINDOW|point=mcuboot_test_swap\n");
        k_sleep(K_SECONDS(60));
    }
}
