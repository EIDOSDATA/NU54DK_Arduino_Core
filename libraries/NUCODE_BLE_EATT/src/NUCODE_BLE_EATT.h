/**
 * @file NUCODE_BLE_EATT.h
 * @brief Enhanced ATT의 experimental opt-in을 선택합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#ifndef NUCODE_BLE_EATT_H_
#define NUCODE_BLE_EATT_H_

#include <NUCODE_BLE_Security.h>

#include <cstddef>

namespace nucode::ble
{

    /** @brief build가 experimental EATT profile을 명시적으로 선택했음을 표시합니다. */
    struct BLEEattProfile final
    {
        static constexpr bool experimental = true;
        static constexpr bool default_enabled = false;
        static constexpr std::size_t maximum_bearers_per_connection = 2U;
    };

} // namespace nucode::ble

#endif // NUCODE_BLE_EATT_H_
