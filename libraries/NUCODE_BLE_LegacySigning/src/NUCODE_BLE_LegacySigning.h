/**
 * @file NUCODE_BLE_LegacySigning.h
 * @brief Authenticated Signed Write의 deprecated legacy opt-in을 선택합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#ifndef NUCODE_BLE_LEGACY_SIGNING_H_
#define NUCODE_BLE_LEGACY_SIGNING_H_

#include <NUCODE_BLE_Security.h>

namespace nucode::ble
{

    /** @brief build가 deprecated Signed Write profile을 명시적으로 선택했음을 표시합니다. */
    struct BLELegacySigningProfile final
    {
        static constexpr bool deprecated = true;
        static constexpr bool default_enabled = false;
    };

} // namespace nucode::ble

#endif // NUCODE_BLE_LEGACY_SIGNING_H_
