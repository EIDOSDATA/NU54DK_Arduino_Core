/**
 * @file NUCODE_BLE_HidsBackend.h
 * @brief NCS HIDS 저장소를 C++ 구현에 안전하게 제공합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#ifndef NUCODE_BLE_SECURITY_INTERNAL_HIDS_BACKEND_H_
#define NUCODE_BLE_SECURITY_INTERNAL_HIDS_BACKEND_H_

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C"
{
#endif

    struct bt_hids;
    struct bt_conn;

    /** @brief SDK enum을 C++에 노출하지 않는 protocol mode callback입니다. */
    typedef void (*nucode_ble_hids_protocol_callback)(bool boot_mode, struct bt_conn *connection);

    /** @brief 기존 keyboard descriptor와 protocol callback으로 정적 HIDS를 초기화합니다. */
    int nucode_ble_hids_initialize(const uint8_t *report_map, size_t report_map_size,
                                   uint8_t report_id, uint8_t report_index,
                                   nucode_ble_hids_protocol_callback callback);

    /** @brief exact connection을 정적 HIDS에 등록합니다. */
    int nucode_ble_hids_connected(struct bt_conn *connection);

    /** @brief exact connection의 HIDS 등록을 회수합니다. */
    int nucode_ble_hids_disconnected(struct bt_conn *connection);

    /** @brief 선택한 protocol mode로 기존 keyboard input report를 전송합니다. */
    int nucode_ble_hids_send(struct bt_conn *connection, bool boot_mode, uint8_t report_index,
                             const uint8_t *data, size_t length);

    /**
     * @brief 정적으로 할당된 keyboard HIDS 인스턴스를 반환합니다.
     *
     * @return 애플리케이션 수명 동안 유효한 HIDS 인스턴스 포인터입니다.
     */
    struct bt_hids *nucode_ble_hids_backend(void);

#ifdef __cplusplus
}
#endif

#endif
