/**
 * @file RandomMath.h
 * @brief Arduino random 구현에 사용하는 순수 정수 연산입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#ifndef NUCODE_ARDUINO_CORE_INTERNAL_RANDOM_MATH_H_
#define NUCODE_ARDUINO_CORE_INTERNAL_RANDOM_MATH_H_

#include <cstdint>

namespace nucode::arduino::internal
{

	/** @brief 결정적 기본 PRNG 상태입니다. */
	constexpr std::uint32_t kRandomDefaultState = UINT32_C(0x6d2b79f5);

	/** @brief 2의 거듭제곱 modulus에서 full-period를 만드는 LCG multiplier입니다. */
	constexpr std::uint32_t kRandomMultiplier = UINT32_C(1664525);

	/** @brief 2의 거듭제곱 modulus와 서로소인 LCG increment입니다. */
	constexpr std::uint32_t kRandomIncrement = UINT32_C(1013904223);

	static_assert((kRandomMultiplier % 4U) == 1U,
				  "LCG multiplier는 2^32 full-period 조건을 만족해야 합니다.");
	static_assert((kRandomIncrement % 2U) == 1U,
				  "LCG increment는 2^32와 서로소여야 합니다.");

	/**
	 * @brief 2^32 전체 상태를 순회하는 LCG의 다음 상태를 계산합니다.
	 *
	 * unsigned 32-bit overflow를 modulus 2^32 연산으로 사용합니다. multiplier는
	 * 1 modulo 4이고 increment는 홀수이므로 0을 포함한 모든 uint32 상태를 한
	 * 주기에 정확히 한 번 순회합니다.
	 *
	 * @param state 현재 상태입니다.
	 * @return 다음 32-bit 상태입니다.
	 */
	[[nodiscard]] constexpr std::uint32_t nextLcg32(std::uint32_t state) noexcept
	{
		return state * kRandomMultiplier + kRandomIncrement;
	}

	/**
	 * @brief modulo bias를 제거하기 위한 rejection 경계를 계산합니다.
	 *
	 * @param bound 생성할 반열린 범위의 크기입니다.
	 * @return 이 값보다 작은 PRNG 결과를 버려야 하며, bound가 0이면 0입니다.
	 */
	[[nodiscard]] constexpr std::uint32_t randomRejectionThreshold(std::uint32_t bound) noexcept
	{
		return bound == 0U ? 0U : static_cast<std::uint32_t>(0U - bound) % bound;
	}

}

#endif
