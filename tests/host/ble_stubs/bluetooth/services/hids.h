/** @file @brief 실제 C HIDS bridge에 필요한 고정 Host ABI입니다. */
#pragma once
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
struct bt_conn;
enum bt_hids_pm_evt
{
    BT_HIDS_PM_EVT_BOOT_MODE_ENTERED,
    BT_HIDS_PM_EVT_REPORT_MODE_ENTERED
};
enum
{
    BT_HIDS_REMOTE_WAKE = 1,
    BT_HIDS_NORMALLY_CONNECTABLE = 2
};
struct bt_hids
{
    unsigned reserved;
};
struct bt_hids_init_param
{
    struct
    {
        const uint8_t *data;
        size_t size;
    } rep_map;
    struct
    {
        uint16_t bcd_hid;
        uint8_t b_country_code, flags;
    } info;
    struct
    {
        struct
        {
            uint8_t id;
            size_t size;
        } reports[1];
        size_t cnt;
    } inp_rep_group_init;
    bool is_kb;
    void (*pm_evt_handler)(enum bt_hids_pm_evt, struct bt_conn *);
};

#define BT_HIDS_DEF(name, size) struct bt_hids name
#ifdef __cplusplus
extern "C"
{
#endif
    int bt_hids_init(struct bt_hids *, struct bt_hids_init_param *);
    int bt_hids_connected(struct bt_hids *, struct bt_conn *);
    int bt_hids_disconnected(struct bt_hids *, struct bt_conn *);
    int bt_hids_boot_kb_inp_rep_send(struct bt_hids *, struct bt_conn *, const uint8_t *, size_t,
                                     void *);
    int bt_hids_inp_rep_send(struct bt_hids *, struct bt_conn *, uint8_t, const uint8_t *, size_t,
                             void *);
#ifdef __cplusplus
}
#endif
