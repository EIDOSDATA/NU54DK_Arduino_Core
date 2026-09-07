/**
 * @file pwm_capture_vector.h
 * @brief PWM load별 DMA word 배치와 첫 capture vector의 유효 범위입니다.
 * SPDX-License-Identifier: MIT
 */
#pragma once

#include <cstddef>
#include <cstdint>

namespace v04
{
    /** @brief 첫 경로의 다섯 필드에 load와 DMA value 수를 더한 내부 시험 설정입니다. */
    struct PwmCaptureVector
    {
        std::uint32_t instance;
        std::uint32_t slot;
        std::uint32_t top;
        std::uint32_t duty;
        std::uint32_t falling;
        std::uint32_t load;
        std::uint32_t values;

        /** @brief WaveForm의 네 번째 word는 TOP이며 slot 3 출력으로 사용하지 않습니다. */
        [[nodiscard]] constexpr bool valid() const noexcept
        {
            return instance >= 20U && instance <= 22U && slot <= 3U &&
                   (top == 1000U || top == 4000U) && duty <= 100U && duty % 25U == 0U &&
                   falling <= 1U && load <= 3U && (load != 3U || slot < 3U) &&
                   (values == 4U || values == 32U || values == 256U);
        }

        /** @brief WaveForm은 RAM TOP을 실제로 읽었는지 구별하도록 register TOP을 다르게 둡니다. */
        [[nodiscard]] constexpr std::uint16_t registerTop() const noexcept
        {
            return static_cast<std::uint16_t>(load == 3U ? (top == 1000U ? 4000U : 1000U) : top);
        }
    };

    /** @brief 선택 slot만 기대 duty로 두고 다른 decoder lane에는 다른 duty를 기록합니다. */
    [[nodiscard]] constexpr bool fillPwmCaptureValues(const PwmCaptureVector &vector,
                                                      std::uint16_t *output,
                                                      std::size_t capacity) noexcept
    {
        if (!vector.valid() || output == nullptr || capacity < vector.values)
        {
            return false;
        }
        const auto stride = vector.load == 0U ? 1U : vector.load == 1U ? 2U : 4U;
        const auto selected = vector.load == 0U   ? 0U
                              : vector.load == 1U ? vector.slot / 2U
                                                  : vector.slot;
        const auto other_duty = vector.duty == 25U ? 75U : 25U;
        for (std::uint32_t index = 0U; index < vector.values; ++index)
        {
            const auto lane = index % stride;
            if (vector.load == 3U && lane == 3U)
            {
                output[index] = static_cast<std::uint16_t>(vector.top);
            }
            else
            {
                const auto duty = lane == selected ? vector.duty : other_duty;
                const auto compare = vector.top * (vector.falling ? duty : 100U - duty) / 100U;
                output[index] = static_cast<std::uint16_t>(compare | (vector.falling << 15U));
            }
        }
        return true;
    }
} // namespace v04
