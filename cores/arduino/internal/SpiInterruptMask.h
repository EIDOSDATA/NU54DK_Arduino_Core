/**
 * @file SpiInterruptMask.h
 * @brief SPI transaction과 Arduino GPIO interrupt의 선택적 마스킹 adapter입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#ifndef NUCODE_ARDUINO_CORE_INTERNAL_SPI_INTERRUPT_MASK_H_
#define NUCODE_ARDUINO_CORE_INTERNAL_SPI_INTERRUPT_MASK_H_

#include <cstddef>
#include <cstdint>

namespace nucode::arduino::internal
{
	/** @brief wiring_interrupt 구현이 보존할 고정 크기 opaque token입니다. */
	struct SpiInterruptMaskToken
	{
		std::uintptr_t words[4]{};
		bool active{false};
	};

	/** @brief 특정 Arduino interrupt의 suspend/restore adapter 계약입니다. */
	struct SpiInterruptMaskAdapter
	{
		bool (*valid)(int interrupt_number) noexcept {nullptr};
		int (*suspend)(int interrupt_number, SpiInterruptMaskToken &token) noexcept {nullptr};
		int (*restore)(SpiInterruptMaskToken &token) noexcept {nullptr};
	};

	/** @brief wiring_interrupt 계층의 adapter를 한 번 등록합니다. */
	[[nodiscard]] bool registerSpiInterruptMaskAdapter(
		const SpiInterruptMaskAdapter &adapter) noexcept;

	/** @brief 선택적 interrupt 마스킹 adapter가 준비되었는지 반환합니다. */
	[[nodiscard]] bool spiInterruptMaskAvailable() noexcept;
}

#endif
