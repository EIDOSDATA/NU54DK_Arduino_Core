/**
 * @file main.c
 * @brief SDC 표준 extended scan-request callback을 유한한 세 세션으로 관측한다.
 * SPDX-License-Identifier: MIT
 */
#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/atomic.h>

static atomic_t received;

/** @brief 다른 사용자 데이터를 만들지 않고 controller callback만 집계한다. */
static void scanned(struct bt_le_ext_adv *advertising, struct bt_le_ext_adv_scanned_info *info)
{
    ARG_UNUSED(advertising);
    if (info != NULL && info->addr != NULL)
    {
        atomic_inc(&received);
    }
}

/** @brief 표준 경로의 각 start/stop/delete 결과와 관측 수를 출력한다. */
int nucode_upstream_main(void)
{
    int error = bt_enable(NULL);
    if (error != 0)
    {
        printk("controller enable error=%d\n", error);
        return error;
    }
    static const struct bt_le_ext_adv_cb callbacks = {.scanned = scanned};
    const struct bt_le_adv_param parameters = {
        .id = BT_ID_DEFAULT,
        .options = BT_LE_ADV_OPT_EXT_ADV | BT_LE_ADV_OPT_SCANNABLE | BT_LE_ADV_OPT_NOTIFY_SCAN_REQ,
        .interval_min = 160,
        .interval_max = 240,
    };
    struct bt_le_ext_adv *advertising = NULL;
    error = bt_le_ext_adv_create(&parameters, &callbacks, &advertising);
    if (error != 0)
    {
        printk("advertiser create error=%d\n", error);
        (void)bt_disable();
        return error;
    }
    const struct bt_data data[] = {
        BT_DATA(BT_DATA_NAME_COMPLETE, CONFIG_BT_DEVICE_NAME, sizeof(CONFIG_BT_DEVICE_NAME) - 1)};
    error = bt_le_ext_adv_set_data(advertising, NULL, 0, data, ARRAY_SIZE(data));
    for (unsigned int cycle = 0; cycle < 3 && error == 0; ++cycle)
    {
        atomic_set(&received, 0);
        const struct bt_le_ext_adv_start_param limit = {.timeout = 300};
        error = bt_le_ext_adv_start(advertising, &limit);
        if (error != 0)
        {
            break;
        }
        k_sleep(K_MSEC(2500));
        error = bt_le_ext_adv_stop(advertising);
        printk("scan-request cycle=%u received=%ld stop=%d\n", cycle + 1,
               (long)atomic_get(&received), error);
        k_sleep(K_MSEC(500));
    }
    const int deletion = bt_le_ext_adv_delete(advertising);
    const int disabled = bt_disable();
    printk("scan-request end error=%d delete=%d disable=%d\n", error, deletion, disabled);
    return error != 0 ? error : (deletion != 0 ? deletion : disabled);
}
