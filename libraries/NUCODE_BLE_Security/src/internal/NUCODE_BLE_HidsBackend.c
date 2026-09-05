/**
 * @file NUCODE_BLE_HidsBackend.c
 * @brief NCS HIDS C 매크로가 요구하는 정적 저장소를 정의합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#if !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE)

#include <internal/NUCODE_BLE_HidsBackend.h>

#include <bluetooth/services/hids.h>

/** @brief 표준 boot keyboard input report의 byte 수입니다. */
#define NUCODE_BLE_KEYBOARD_REPORT_SIZE 8U

BT_HIDS_DEF(nucode_ble_keyboard_hids_storage, NUCODE_BLE_KEYBOARD_REPORT_SIZE);

/** @brief SDK callback의 수명 동안 고정된 C++ protocol handler입니다. */
static nucode_ble_hids_protocol_callback protocol_callback;

/** @brief SDK protocol enum을 의미가 같은 bool mode로 변환합니다. */
static void protocol_mode_changed(enum bt_hids_pm_evt event, struct bt_conn *connection)
{
    if (protocol_callback != NULL &&
        (event == BT_HIDS_PM_EVT_BOOT_MODE_ENTERED || event == BT_HIDS_PM_EVT_REPORT_MODE_ENTERED))
    {
        protocol_callback(event == BT_HIDS_PM_EVT_BOOT_MODE_ENTERED, connection);
    }
}

int nucode_ble_hids_initialize(const uint8_t *report_map, size_t report_map_size, uint8_t report_id,
                               uint8_t report_index, nucode_ble_hids_protocol_callback callback)
{
    struct bt_hids_init_param parameters = {0};
    parameters.rep_map.data = report_map;
    parameters.rep_map.size = report_map_size;
    parameters.info.bcd_hid = 0x0111U;
    parameters.info.b_country_code = 0U;
    parameters.info.flags = BT_HIDS_REMOTE_WAKE | BT_HIDS_NORMALLY_CONNECTABLE;
    parameters.inp_rep_group_init.reports[report_index].id = report_id;
    parameters.inp_rep_group_init.reports[report_index].size = NUCODE_BLE_KEYBOARD_REPORT_SIZE;
    parameters.inp_rep_group_init.cnt = 1U;
    parameters.is_kb = true;
    parameters.pm_evt_handler = protocol_mode_changed;
    protocol_callback = callback;
    return bt_hids_init(nucode_ble_hids_backend(), &parameters);
}

int nucode_ble_hids_connected(struct bt_conn *connection)
{
    return bt_hids_connected(nucode_ble_hids_backend(), connection);
}

int nucode_ble_hids_disconnected(struct bt_conn *connection)
{
    return bt_hids_disconnected(nucode_ble_hids_backend(), connection);
}

int nucode_ble_hids_send(struct bt_conn *connection, bool boot_mode, uint8_t report_index,
                         const uint8_t *data, size_t length)
{
    return boot_mode ? bt_hids_boot_kb_inp_rep_send(nucode_ble_hids_backend(), connection, data,
                                                    length, NULL)
                     : bt_hids_inp_rep_send(nucode_ble_hids_backend(), connection, report_index,
                                            data, length, NULL);
}

struct bt_hids *nucode_ble_hids_backend(void)
{
    return &nucode_ble_keyboard_hids_storage;
}

#endif
