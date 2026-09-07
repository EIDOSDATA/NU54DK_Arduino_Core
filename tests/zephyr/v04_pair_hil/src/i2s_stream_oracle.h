/**
 * @file i2s_stream_oracle.h
 * @brief 연속 I2S의 sample 위치와 원본 word CRC를 유지합니다.
 * SPDX-License-Identifier: MIT
 */
#pragma once
#include <cstdint>

namespace v04
{
    /** @brief 각 DMA word 위치를 서로 다르게 만드는 기존 stream pattern입니다. */
    constexpr std::uint32_t i2sStreamPattern(std::uint32_t seed, std::uint32_t index)
    {
        return (seed + 0x9E3779B9U * (index + 1U)) ^ ((index << 16U) | (index >> 16U));
    }

    /** @brief little-endian word의 CRC-32/ISO-HDLC 중간 상태를 갱신합니다. */
    constexpr std::uint32_t i2sCrcWord(std::uint32_t crc, std::uint32_t word)
    {
        for (unsigned byte = 0U; byte < 4U; ++byte)
        {
            crc ^= (word >> (8U * byte)) & 0xFFU;
            for (unsigned bit = 0U; bit < 8U; ++bit)
            {
                crc = (crc >> 1U) ^ ((crc & 1U) ? 0xEDB88320U : 0U);
            }
        }
        return crc;
    }

    /** @brief 시작 zero frame을 한번만 허용하고 이후 모든 활성 sample bit를 비교합니다. */
    struct I2sStreamOracle
    {
        std::uint32_t seed = 0U, width = 0U, frame_samples = 0U;
        std::uint32_t padding = 0U, samples = 0U, mismatches = 0U;
        std::uint32_t first_expected = 0U, first_actual = 0U, first_index = UINT32_MAX;
        bool begun = false;

        /** @brief 기대 pattern의 첫 sample은 0이 아닌 seed로 Host가 준비합니다. */
        void reset(std::uint32_t value, std::uint32_t bits, std::uint32_t channels)
        {
            *this = {};
            seed = value;
            width = bits;
            frame_samples = channels == 0U ? 2U : 1U;
            first_index = UINT32_MAX;
        }

        /** @brief 첫 오류 위치를 보존하고 오류 개수는 계속 합산합니다. */
        void mismatch(std::uint32_t expected, std::uint32_t actual)
        {
            if (mismatches == 0U)
            {
                first_index = samples;
                first_expected = expected;
                first_actual = actual;
            }
            ++mismatches;
        }

        /** @brief 한 수신 word를 bit 폭별 sample로 분리합니다. */
        void consume(std::uint32_t word)
        {
            const auto packed = width <= 16U ? 32U / width : 1U;
            const auto mask = width == 32U ? UINT32_MAX : (1U << width) - 1U;
            for (unsigned sample = 0U; sample < packed; ++sample)
            {
                const auto actual = (word >> (sample * width)) & mask;
                if (!begun && actual == 0U)
                {
                    ++padding;
                    if (padding > 8U * frame_samples)
                    {
                        mismatch(1U, 0U);
                    }
                    continue;
                }
                if (!begun)
                {
                    begun = true;
                    if (padding % frame_samples != 0U)
                    {
                        mismatch(0U, padding);
                    }
                }
                const auto expected =
                    (i2sStreamPattern(seed, samples / packed) >> ((samples % packed) * width)) &
                    mask;
                if (actual != expected)
                {
                    mismatch(expected, actual);
                }
                ++samples;
            }
        }
    };
} // namespace v04
