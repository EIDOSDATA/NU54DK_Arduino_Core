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

struct bt_hids *nucode_ble_hids_backend(void)
{
	return &nucode_ble_keyboard_hids_storage;
}

#endif
