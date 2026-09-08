/**
 * @file model.h
 * @brief T13 고정 시험 설정과 독립 데이터·DMA 경계 판정입니다.
 * SPDX-License-Identifier: MIT
 */
#pragma once
#include <cstddef>
#include <cstdint>

namespace t13
{
    constexpr unsigned max_lanes = 5U;
    constexpr std::uint32_t guard_word = 0xA59669A5U;
    constexpr std::uint32_t hash_initial = 2166136261U;

    enum class Kind : std::uint32_t
    {
        none,
        uart,
        spim,
        spis,
        twim,
        twis,
        saadc,
        pwm,
        pdm,
        i2s
    };

    /** @brief 핀은 port*32+pin으로 저장하며 생성 단계에서 생산 route와 대조합니다. */
    struct Endpoint
    {
        Kind kind;
        std::uint32_t instance;
        std::uint32_t bank;
        std::uint32_t profile;
        std::uint32_t pins[4];
        std::uint32_t signals[4];
        std::uint32_t pin_count;
        std::uint32_t rate;
        std::uint32_t length;
    };

    struct Case
    {
        std::uint32_t id;
        std::uint32_t harness;
        std::uint32_t duration;
        std::uint32_t serial_count;
        Endpoint serial[2][max_lanes];
        std::uint32_t adc_channels;
        std::uint32_t pwm_instance;
        std::uint32_t pwm_duty;
        std::uint32_t pdm_instance;
        bool i2s;
    };

    /** @brief 수신 값에 의존하지 않는 seed·전역 byte 위치의 기대 패턴입니다. */
    constexpr std::uint8_t pattern(std::uint32_t seed, std::uint32_t index)
    {
        const auto mixed = seed + index * 0x9E3779B9U;
        return static_cast<std::uint8_t>((mixed ^ (mixed >> 13U) ^ (index >> 8U)) >> 7U);
    }

    constexpr std::uint32_t laneSeed(std::uint32_t seed, unsigned lane, unsigned role)
    {
        return seed ^ (0x13579BDFU * (lane + 1U)) ^ (role * 0x5A5A5A5AU);
    }

    constexpr std::uint32_t hashByte(std::uint32_t hash, std::uint8_t value)
    {
        return (hash ^ value) * 16777619U;
    }

    /** @brief 가드가 실제 요청 길이 바로 뒤에 위치하는 1024-byte DMA slot입니다. */
    struct alignas(4) Buffer
    {
        std::uint32_t storage[264];

        std::uint8_t *data()
        {
            return reinterpret_cast<std::uint8_t *>(storage + 4U);
        }

        const std::uint8_t *data() const
        {
            return reinterpret_cast<const std::uint8_t *>(storage + 4U);
        }

        bool initialize(unsigned length)
        {
            if (length == 0U || length > 1024U || length % 4U != 0U)
            {
                return false;
            }
            for (auto &word : storage)
            {
                word = guard_word;
            }
            for (unsigned index = 0U; index < length; ++index)
            {
                data()[index] = 0xCCU;
            }
            return true;
        }

        bool guards(unsigned length) const
        {
            if (length == 0U || length > 1024U || length % 4U != 0U)
            {
                return false;
            }
            for (unsigned index = 0U; index < 4U; ++index)
            {
                if (storage[index] != guard_word || storage[4U + length / 4U + index] != guard_word)
                {
                    return false;
                }
            }
            return true;
        }
    };

    /** @brief 실제 완료 뒤에만 누적하며 STOP 직후까지 유지하는 방향별 통계입니다. */
    struct Direction
    {
        std::uint32_t completed = 0U;
        std::uint64_t bytes = 0U;
        std::uint32_t hash = hash_initial;
        std::uint32_t first_word = 0U;
        std::uint32_t last_word = 0U;
        std::uint64_t last_completion_ms = 0U;
        std::uint32_t max_completion_gap_ms = 0U;
    };
} // namespace t13
