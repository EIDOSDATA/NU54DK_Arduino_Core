/**
 * @file NUCODE_BLE_HidsBackend.h
 * @brief NCS HIDS 저장소를 C++ 구현에 안전하게 제공합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#ifndef NUCODE_BLE_SECURITY_INTERNAL_HIDS_BACKEND_H_
#define NUCODE_BLE_SECURITY_INTERNAL_HIDS_BACKEND_H_

#ifdef __cplusplus
extern "C"
{
#endif

    struct bt_hids;

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
