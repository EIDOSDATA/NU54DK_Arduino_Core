/**
 * @file ac02b_analog_math.cpp
 * @brief AC-02B 해상도와 PWM 정수 계산을 host compiler로 검증합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include "internal/AnalogRuntimeMath.h"

#include <cstdint>

namespace
{
    /** @brief constexpr reference 출력까지 포함한 주파수 변환을 검사합니다. */
    constexpr bool frequencyContract()
    {
        std::uint32_t period = 0U;
        return nucode::arduino::internal::frequencyToPeriodNanoseconds(50U, period) &&
               period == 20000000U &&
               nucode::arduino::internal::frequencyToPeriodNanoseconds(1000U, period) &&
               period == 1000000U &&
               !nucode::arduino::internal::frequencyToPeriodNanoseconds(0U, period);
    }
} // namespace

int main()
{
    using namespace nucode::arduino::internal;

    static_assert(isSupportedAnalogReadResolution(8U));
    static_assert(isSupportedAnalogReadResolution(10U));
    static_assert(isSupportedAnalogReadResolution(12U));
    static_assert(isSupportedAnalogReadResolution(14U));
    static_assert(!isSupportedAnalogReadResolution(9U));
    static_assert(isSupportedAnalogWriteResolution(1U));
    static_assert(isSupportedAnalogWriteResolution(16U));
    static_assert(!isSupportedAnalogWriteResolution(0U));
    static_assert(!isSupportedAnalogWriteResolution(17U));

    static_assert(analogResolutionMaximum(8U) == 255U);
    static_assert(analogResolutionMaximum(14U) == 16383U);
    static_assert(analogResolutionMaximum(16U) == 65535U);
    static_assert(scaleAnalogDutyToPulse(20000000U, 0U, 8U) == 0U);
    static_assert(scaleAnalogDutyToPulse(20000000U, 255U, 8U) == 20000000U);
    static_assert(scaleAnalogDutyToPulse(20000000U, 128U, 8U) == 10039216U);
    static_assert(scaleAnalogDutyToPulse(1000000U, 32768U, 16U) == 500008U);
    static_assert(frequencyContract());
    static_assert(rescalePulseForPeriod(20000000U, 1500000U, 10000000U) == 750000U);
    static_assert(rescalePulseForPeriod(20000000U, 20000000U, 10000000U) == 10000000U);
    return 0;
}
