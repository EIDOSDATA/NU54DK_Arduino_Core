/**
 * @file wiring_random.cpp
 * @brief Zephyr 동시 실행 환경을 고려한 Arduino random API 구현입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <api/Common.h>

#include <zephyr/sys/atomic.h>

#include <cstdint>

#include "internal/RandomMath.h"

namespace
{

    atomic_t g_random_state =
        ATOMIC_INIT(static_cast<atomic_val_t>(nucode::arduino::internal::kRandomDefaultState));

    /**
	 * @brief 원자적으로 다음 32비트 PRNG 값을 생성합니다.
	 *
	 * @return 2^32 전체 상태를 순회하는 결정적 LCG 출력입니다.
	 */
    [[nodiscard]] std::uint32_t nextRandom32() noexcept
    {
        for (;;)
        {
            const atomic_val_t observed = atomic_get(&g_random_state);
            const auto next =
                nucode::arduino::internal::nextLcg32(static_cast<std::uint32_t>(observed));

            if (atomic_cas(&g_random_state, observed, static_cast<atomic_val_t>(next)))
            {
                return next;
            }
        }
    }

    /**
	 * @brief modulo bias 없이 0 이상 bound 미만 값을 생성합니다.
	 *
	 * @param bound 0보다 큰 반열린 범위 크기입니다.
	 * @return 0 이상 bound 미만의 값입니다.
	 */
    [[nodiscard]] std::uint32_t randomBelow(std::uint32_t bound) noexcept
    {
        const auto threshold = nucode::arduino::internal::randomRejectionThreshold(bound);

        for (;;)
        {
            const auto candidate = nextRandom32();
            if (candidate >= threshold)
            {
                return candidate % bound;
            }
        }
    }

} // namespace

long random(long howbig)
{
    if (howbig <= 0L)
    {
        return 0L;
    }

    return static_cast<long>(randomBelow(static_cast<std::uint32_t>(howbig)));
}

long random(long howsmall, long howbig)
{
    if (howsmall >= howbig)
    {
        return howsmall;
    }

    const auto span = static_cast<std::uint32_t>(static_cast<std::int64_t>(howbig) -
                                                 static_cast<std::int64_t>(howsmall));
    return static_cast<long>(static_cast<std::int64_t>(howsmall) + randomBelow(span));
}

void randomSeed(unsigned long seed)
{
    if (seed != 0UL)
    {
        atomic_set(&g_random_state, static_cast<atomic_val_t>(seed));
    }
}
