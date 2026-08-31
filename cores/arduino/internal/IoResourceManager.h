/**
 * @file IoResourceManager.h
 * @brief 물리 핀과 주변장치 블록의 런타임 소유권 계약을 정의합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#ifndef NUCODE_ARDUINO_CORE_INTERNAL_IO_RESOURCE_MANAGER_H_
#define NUCODE_ARDUINO_CORE_INTERNAL_IO_RESOURCE_MANAGER_H_

#include <zephyr/drivers/gpio.h>

#include <cstddef>
#include <cstdint>

namespace nucode::arduino::internal
{
	/** @brief 소유권 관리자가 구분하는 물리 자원 종류입니다. */
	enum class IoResourceKind : std::uint8_t
	{
		invalid = 0U,
		gpio_pin,
		serial_block,
		pwm_block,
		adc_block,
		power_domain,
	};

	/**
	 * @brief 하나의 물리 자원을 식별하는 정규화된 키입니다.
	 *
	 * GPIO 핀은 controller device 주소와 controller 내부 pin 번호를 함께
	 * 사용합니다. 따라서 서로 다른 Arduino 논리 별칭도 같은 pad를 가리키면
	 * 반드시 같은 자원으로 충돌합니다.
	 */
	struct IoResourceId
	{
		IoResourceKind kind{IoResourceKind::invalid};
		const void *domain{nullptr};
		std::uint16_t index{0U};
	};

	/** @brief 물리 자원을 사용하는 Core 하위 시스템입니다. */
	enum class IoOwnerKind : std::uint8_t
	{
		none = 0U,
		gpio,
		adc,
		pwm,
		wire,
		spi,
		serial,
		system,
	};

	/** @brief 하위 시스템 종류와 instance를 결합한 소유자 식별자입니다. */
	struct IoResourceOwner
	{
		IoOwnerKind kind{IoOwnerKind::none};
		std::uint8_t instance{0U};
	};

	/** @brief 자원 획득 시 기존 소유권을 처리하는 정책입니다. */
	enum class IoAcquirePolicy : std::uint8_t
	{
		/** 비어 있거나 같은 소유자가 이미 가진 자원만 허용합니다. */
		exclusive = 0U,
	};

	/** @brief 소유권 관리 연산 결과입니다. */
	enum class IoResourceResult : std::uint8_t
	{
		success = 0U,
		invalid_context,
		invalid_argument,
		conflict,
		capacity_exhausted,
		stale_lease,
		wrong_phase,
	};

	/** @brief 자원의 현재 트랜잭션 상태입니다. */
	enum class IoResourceState : std::uint8_t
	{
		free = 0U,
		reserved,
		active,
	};

	/** @brief 하나의 트랜잭션에서 원자적으로 관리할 수 있는 최대 자원 수입니다. */
	inline constexpr std::size_t io_resource_lease_capacity = 8U;

	/** @brief reserve/commit/rollback/release 수명주기를 구분합니다. */
	enum class IoLeasePhase : std::uint8_t
	{
		empty = 0U,
		reserved,
		committed,
		rolled_back,
		released,
	};

	/** @brief lease 내부에서 한 자원의 이전 상태와 세대를 보존합니다. */
	struct IoResourceLeaseEntry
	{
		IoResourceId resource{};
		IoResourceOwner previous_owner{};
		IoResourceState previous_state{IoResourceState::free};
		std::uint64_t generation{0U};
		bool changed{false};
	};

	/**
	 * @brief 여러 자원의 원자적 소유권 변경을 나타내는 고정 크기 lease입니다.
	 *
	 * 호출자는 driver 또는 pinctrl 변경 전에 reserve하고, 성공하면 commit,
	 * 실패하면 rollback해야 합니다. 동적 메모리는 사용하지 않습니다.
	 */
	struct IoResourceLease
	{
		IoResourceOwner owner{};
		IoLeasePhase phase{IoLeasePhase::empty};
		std::uint64_t manager_epoch{0U};
		std::size_t count{0U};
		IoResourceLeaseEntry entries[io_resource_lease_capacity]{};
	};

	/** @brief 진단과 시험에서 읽는 자원 상태 snapshot입니다. */
	struct IoResourceSnapshot
	{
		IoResourceOwner owner{};
		IoResourceState state{IoResourceState::free};
		std::uint64_t generation{0U};
	};

	/**
	 * @brief Zephyr GPIO descriptor를 물리 pad 소유권 키로 변환합니다.
	 *
	 * @param gpio Devicetree에서 생성된 GPIO descriptor입니다.
	 * @return controller와 pin 번호를 보존한 물리 자원 키입니다.
	 */
	[[nodiscard]] constexpr IoResourceId gpioIoResource(const gpio_dt_spec &gpio) noexcept
	{
		return {IoResourceKind::gpio_pin, gpio.port, static_cast<std::uint16_t>(gpio.pin)};
	}

	/**
	 * @brief controller instance와 같은 비 GPIO 자원 키를 생성합니다.
	 *
	 * @param kind 자원 종류입니다.
	 * @param index peripheral 또는 channel instance입니다.
	 * @param domain 동일 번호 공간을 분리할 선택적 domain입니다.
	 * @return 정규화된 물리 자원 키입니다.
	 */
	[[nodiscard]] constexpr IoResourceId peripheralIoResource(IoResourceKind kind,
													 std::uint16_t index,
													 const void *domain = nullptr) noexcept
	{
		return {kind, domain, index};
	}

	/**
	 * @brief 여러 자원을 하나의 소유자에게 원자적으로 예약합니다.
	 *
	 * @param owner 요청 소유자입니다.
	 * @param resources 중복이 없는 자원 키 배열입니다.
	 * @param count 배열 원소 수입니다.
	 * @param policy AC-02A에서는 exclusive만 허용합니다.
	 * @param lease 성공 시 후속 commit/rollback에 사용할 lease입니다.
	 * @param conflict 충돌 시 현재 소유자를 받을 선택적 주소입니다.
	 * @return 예약 결과입니다.
	 */
	[[nodiscard]] IoResourceResult reserveIoResources(
		IoResourceOwner owner, const IoResourceId *resources, std::size_t count,
		IoAcquirePolicy policy, IoResourceLease &lease,
		IoResourceSnapshot *conflict = nullptr) noexcept;

	/** @brief 예약한 자원 변경을 활성 상태로 확정합니다. */
	[[nodiscard]] IoResourceResult commitIoResources(IoResourceLease &lease) noexcept;

	/** @brief driver 전환 실패 후 예약 전 상태를 원자적으로 복구합니다. */
	[[nodiscard]] IoResourceResult rollbackIoResources(IoResourceLease &lease) noexcept;

	/** @brief 확정된 lease가 새로 획득한 자원을 반환합니다. */
	[[nodiscard]] IoResourceResult releaseIoResources(IoResourceLease &lease) noexcept;

	/**
	 * @brief 하나의 자원에 대한 일관된 snapshot을 읽습니다.
	 *
	 * @param resource 조회할 자원입니다.
	 * @param snapshot 조회 결과입니다. 등록되지 않은 자원은 free로 반환됩니다.
	 * @return 조회 결과입니다.
	 */
	[[nodiscard]] IoResourceResult ioResourceSnapshot(const IoResourceId &resource,
												   IoResourceSnapshot &snapshot) noexcept;

#if defined(CONFIG_ZTEST)
	/** @brief ztest 격리용으로 모든 소유권 상태와 lease 세대를 초기화합니다. */
	void resetIoResourceManagerForTest() noexcept;
#endif

}

#endif
