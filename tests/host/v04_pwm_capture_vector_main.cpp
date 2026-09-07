/**
 * @file v04_pwm_capture_vector_main.cpp
 * @brief 독립 상수 배열과 constexpr 계약으로 실제 HIL DMA 배치를 검증합니다.
 * SPDX-License-Identifier: MIT
 */
#include "pwm_capture_vector.h"

namespace
{
    /** @brief 네 load의 알려진 word 배치를 세 DMA 길이에서 대조합니다. */
    constexpr bool layouts()
    {
        v04::PwmCaptureVector cases[]{{20U, 3U, 1000U, 25U, 1U, 0U, 4U},
                                      {21U, 2U, 1000U, 75U, 0U, 1U, 4U},
                                      {22U, 1U, 1000U, 50U, 1U, 2U, 4U},
                                      {20U, 2U, 4000U, 25U, 0U, 3U, 4U}};
        constexpr std::uint16_t expected[][4]{{0x80FAU, 0x80FAU, 0x80FAU, 0x80FAU},
                                              {750U, 250U, 750U, 250U},
                                              {0x80FAU, 0x81F4U, 0x80FAU, 0x80FAU},
                                              {1000U, 1000U, 3000U, 4000U}};
        constexpr std::uint32_t counts[]{4U, 32U, 256U};
        for (unsigned scenario = 0U; scenario < 4U; ++scenario)
        {
            for (const auto count : counts)
            {
                cases[scenario].values = count;
                std::uint16_t output[257]{};
                output[count] = 0xCAFEU;
                if (!v04::fillPwmCaptureValues(cases[scenario], output, count))
                {
                    return false;
                }
                for (unsigned index = 0U; index < count; ++index)
                {
                    if (output[index] != expected[scenario][index % 4U])
                    {
                        return false;
                    }
                }
                if (output[count] != 0xCAFEU || cases[scenario].registerTop() != 1000U)
                {
                    return false;
                }
            }
        }
        return true;
    }

    /** @brief WaveForm slot 3·미지원 길이·부족한 출력 용량은 원자적으로 거부합니다. */
    constexpr bool rejection()
    {
        v04::PwmCaptureVector vector{20U, 0U, 1000U, 25U, 0U, 3U, 4U};
        std::uint16_t output[4]{1U, 2U, 3U, 4U};
        if (v04::fillPwmCaptureValues(vector, output, 3U) ||
            v04::fillPwmCaptureValues(vector, nullptr, 4U))
        {
            return false;
        }
        vector.slot = 3U;
        if (vector.valid() || v04::fillPwmCaptureValues(vector, output, 4U))
        {
            return false;
        }
        vector.slot = 0U;
        vector.values = 8U;
        if (vector.valid() || v04::fillPwmCaptureValues(vector, output, 4U))
        {
            return false;
        }
        return output[0] == 1U && output[1] == 2U && output[2] == 3U && output[3] == 4U;
    }

    static_assert(layouts());
    static_assert(rejection());
} // namespace
