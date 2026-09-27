/**
 * @file NUCODE_BLE_ProfilesBackend.h
 * @brief C++ profile facade가 사용하는 표준 ESS 정적 backend입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#ifndef NUCODE_BLE_SECURITY_INTERNAL_PROFILES_BACKEND_H_
#define NUCODE_BLE_SECURITY_INTERNAL_PROFILES_BACKEND_H_

#include <stdint.h>

#ifdef __cplusplus
extern "C"
{
#endif

    /** @brief 0.01 °C 온도를 저장하고 ESS 구독자에게 알립니다. */
    int nucode_ble_ess_set_temperature(int16_t hundredths_celsius);

    /** @brief 마지막 ESS 온도를 0.01 °C 단위로 반환합니다. */
    int16_t nucode_ble_ess_get_temperature(void);

    /** @brief 0.01 % 습도를 저장하고 ESS 구독자에게 알립니다. */
    int nucode_ble_ess_set_humidity(uint16_t hundredths_percent);

    /** @brief 마지막 ESS 습도를 0.01 % 단위로 반환합니다. */
    uint16_t nucode_ble_ess_get_humidity(void);

#ifdef __cplusplus
}
#endif

#endif
