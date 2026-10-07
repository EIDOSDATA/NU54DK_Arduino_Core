/** @file @brief NCS CGMS의 실제 기록·RACP·session adapter입니다.
 * SPDX-License-Identifier: MIT
 */
#ifndef NUCODE_BLE_GLUCOSE_H_
#define NUCODE_BLE_GLUCOSE_H_
#include <NUCODE_BLE_ProfileCodec.h>
namespace nucode::ble::profiles
{
    /**
     * @brief CGMS native service의 고정 record queue에 사용자 측정값을 제출합니다.
     * @note CONFIG_BT_CGMS=y와 CONFIG_BT_MAX_CONN=1을 요구합니다.
     * Native RACP/session은 단일 owner이며 두 link 설정은 begin에서 거부합니다.
     */
    class GlucoseService final
    {
      public:
        [[nodiscard]] bool begin(std::uint16_t session_hours = 1U,
                                 std::uint16_t notification_minutes = 1U) noexcept;
        /** @brief SFLOAT 농도를 기록합니다. time offset은 native session clock이 소유합니다. */
        [[nodiscard]] bool add(std::int16_t mantissa, std::int8_t exponent = 0) noexcept;
        [[nodiscard]] bool sessionActive() const noexcept;
        [[nodiscard]] int lastError() const noexcept;
    };
} // namespace nucode::ble::profiles
#endif
