/**
 * @file PinHandover.h
 * @brief GPIO와 주변장치 사이의 실패 복구 가능한 핀 전환 계약입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#ifndef NUCODE_ARDUINO_CORE_INTERNAL_PIN_HANDOVER_H_
#define NUCODE_ARDUINO_CORE_INTERNAL_PIN_HANDOVER_H_

#include "internal/IoResourceManager.h"

#include <cstddef>
#include <cstdint>

namespace nucode::arduino::internal
{
	/** @brief GPIO 핀 전환의 현재 수명주기 단계입니다. */
	enum class PinHandoverPhase : std::uint8_t
	{
		empty = 0U,
		prepared,
		committed,
		rolled_back,
		faulted,
	};

	/** @brief GPIO 핀 전환 API의 고정 결과입니다. */
	enum class PinHandoverResult : std::uint8_t
	{
		success = 0U,
		invalid_context,
		invalid_argument,
		invalid_pin,
		unsupported,
		ownership_conflict,
		device_not_ready,
		driver_error,
		wrong_phase,
	};

	/**
	 * @brief interrupt callback을 제거하지 않고 일시 정지하는 내부 snapshot입니다.
	 */
	struct PinInterruptHandoverState
	{
		std::size_t canonical_pin{0U};
		bool registered{false};
		bool was_active{false};
		bool was_suspended{false};
	};

	/**
	 * @brief GPIO 상태와 ownership 예약을 함께 보존하는 고정 크기 전환 객체입니다.
	 *
	 * @details begin 성공 뒤 호출자는 주변장치 driver와 pinctrl을 구성하고 commit 또는
	 * rollback을 반드시 호출해야 합니다. begin부터 종료까지 공통 GPIO 전환 mutex를
	 * 호출 thread가 보유하므로 다른 thread로 객체를 넘기면 안 됩니다.
	 */
	struct GpioPinHandover
	{
		PinHandoverPhase phase{PinHandoverPhase::empty};
		std::size_t requested_pin{0U};
		std::size_t canonical_pin{0U};
		IoResourceOwner target_owner{};
		IoResourceLease ownership_lease{};
		PinInterruptHandoverState interrupt{};
		std::uint8_t previous_mode{0U};
		bool previous_output_latch{false};
		bool previous_gpio_owned{false};
		bool lock_held{false};
	};

	/**
	 * @brief free 또는 GPIO 소유 pad를 주변장치 전환용으로 예약하고 GPIO를 분리합니다.
	 */
	[[nodiscard]] PinHandoverResult beginGpioPinHandover(
		std::size_t logical_pin, IoResourceOwner target_owner,
		GpioPinHandover &handover) noexcept;

	/** @brief 성공한 주변장치 구성을 ownership manager에 확정합니다. */
	[[nodiscard]] PinHandoverResult commitGpioPinHandover(
		GpioPinHandover &handover) noexcept;

	/** @brief 실패한 주변장치 구성을 이전 GPIO·interrupt 상태로 되돌립니다. */
	[[nodiscard]] PinHandoverResult rollbackGpioPinHandover(
		GpioPinHandover &handover) noexcept;

	/**
	 * @brief 복구 불가능한 prepared handover의 mutex만 해제하고 자원 상태를 보존합니다.
	 *
	 * @details PM 또는 pinctrl 복구 실패처럼 GPIO를 안전하게 되돌릴 수 없는 경우에만
	 * 사용합니다. ownership lease와 전기적 상태는 변경하지 않고 핀 재사용을 차단합니다.
	 */
	[[nodiscard]] PinHandoverResult abandonGpioPinHandoverFailClosed(
		GpioPinHandover &handover) noexcept;

	/**
	 * @brief commit된 주변장치 사용이 끝난 뒤 저장한 GPIO·interrupt 상태를 복원합니다.
	 *
	 * @details 호출 전에 주변장치 driver가 전송을 끝내고 해당 pad를 disconnect해야 합니다.
	 * 이전에 GPIO가 free였다면 주변장치 lease만 반환하고 free 상태로 복원합니다.
	 */
	[[nodiscard]] PinHandoverResult restoreGpioAfterPeripheral(
		GpioPinHandover &handover) noexcept;

	/**
	 * @brief 이전 GPIO snapshot을 폐기하고 commit된 주변장치 pad를 free로 반환합니다.
	 *
	 * @details GPIO로 복원하지 않을 `end()` 경로에서 사용합니다. 보존한 interrupt callback도
	 * 함께 제거합니다.
	 */
	[[nodiscard]] PinHandoverResult releasePeripheralPinHandover(
		GpioPinHandover &handover) noexcept;

#if defined(CONFIG_NUCODE_ARDUINO_INTERRUPTS)
	/** @brief 특정 canonical 핀의 interrupt를 callback 보존 상태로 정지합니다. */
	[[nodiscard]] int suspendInterruptForPinHandover(
		std::size_t logical_pin, PinInterruptHandoverState &state) noexcept;

	/** @brief 핀 전환 성공 뒤 보존했던 interrupt callback을 제거합니다. */
	[[nodiscard]] int commitInterruptForPinHandover(
		PinInterruptHandoverState &state) noexcept;

	/** @brief 핀 전환 실패 뒤 보존했던 interrupt callback과 trigger를 복원합니다. */
	[[nodiscard]] int rollbackInterruptForPinHandover(
		PinInterruptHandoverState &state) noexcept;
#endif

}

#endif
