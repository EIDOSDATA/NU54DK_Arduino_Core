/**
 * @file Diagnostics.h
 * @brief NU54DK Arduino Core의 최소 공개 진단 값과 포맷 계약입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#ifndef NUCODE_ARDUINO_CORE_NUCODE_DIAGNOSTICS_H_
#define NUCODE_ARDUINO_CORE_NUCODE_DIAGNOSTICS_H_

#include <cstddef>
#include <cstdint>

namespace nucode::arduino
{

	/** @brief 진단을 생성한 Core 하위 시스템입니다. */
	enum class DiagnosticSubsystem : std::uint8_t
	{
		core = 0U,
		gpio,
		time,
		serial,
		wire,
		spi,
		analog,
	};

	/** @brief 하위 시스템에 독립적인 최소 공개 진단 분류입니다. */
	enum class DiagnosticCode : std::uint8_t
	{
		none = 0U,
		invalid_context,
		invalid_argument,
		invalid_pin,
		unsupported,
		device_not_ready,
		not_started,
		overflow,
		ownership_conflict,
		driver_error,
	};

	/**
	 * @brief 할당과 logging 없이 전달할 수 있는 공개 진단 값입니다.
	 *
	 * 기존 backend의 비공개 진단 상태를 강제로 변경하지 않으며, 공개 projection과
	 * 순수 포맷 함수가 공유하는 공통 값 계약입니다.
	 */
	struct Diagnostic
	{
		DiagnosticSubsystem subsystem{DiagnosticSubsystem::core};
		DiagnosticCode code{DiagnosticCode::none};
		int driver_error{0};
		std::uint32_t detail{0U};
	};

	/**
	 * @brief 하위 시스템의 안정된 영문 token을 반환합니다.
	 *
	 * @param subsystem 변환할 하위 시스템입니다.
	 * @return 알려진 값의 영문 token이며, 알 수 없는 값이면 "unknown"입니다.
	 */
	[[nodiscard]] const char *diagnosticSubsystemToken(DiagnosticSubsystem subsystem) noexcept;

	/**
	 * @brief 진단 코드의 안정된 영문 token을 반환합니다.
	 *
	 * @param code 변환할 진단 코드입니다.
	 * @return 알려진 값의 영문 token이며, 알 수 없는 값이면 "unknown"입니다.
	 */
	[[nodiscard]] const char *diagnosticCodeToken(DiagnosticCode code) noexcept;

	/**
	 * @brief 선택한 backend의 마지막 내부 오류를 공개 진단 값으로 투영합니다.
	 *
	 * 조회는 기존 backend 상태를 지우지 않습니다. 활성화된 GPIO, Serial, Wire,
	 * SPI와 Analog backend는 원자적으로 보관한 마지막 오류를 읽습니다. 별도 오류
	 * 저장소가 없는 Core/Time 또는 build에서 비활성화된 backend는 각각 `none` 또는
	 * `unsupported`를 반환합니다.
	 *
	 * 여러 thread나 ISR이 같은 backend 상태를 동시에 갱신하면 호출 시점에 관측한
	 * 최신 원자 값이 반환됩니다. 이 값은 이벤트 queue나 오류 이력의 대체물이 아닙니다.
	 *
	 * @param subsystem 조회할 backend 하위 시스템입니다.
	 * @return 공개 코드, 원본 driver 오류와 필요한 보조 detail을 담은 값입니다.
	 */
	[[nodiscard]] Diagnostic lastDiagnostic(DiagnosticSubsystem subsystem) noexcept;

	/**
	 * @brief 진단을 한 줄 ASCII 형식으로 포맷합니다.
	 *
	 * 형식은 `NU54:<subsystem>:<code>:driver=<signed>:detail=<unsigned>`입니다.
	 * buffer가 nullptr이거나 capacity가 0이면 필요한 길이만 계산하며 출력 memory를
	 * 변경하지 않습니다. capacity가 1 이상인데 공간이 부족하면 가능한 부분까지 쓰고
	 * 마지막 byte를 NUL로 끝냅니다.
	 *
	 * @param diagnostic 포맷할 진단 값입니다.
	 * @param buffer 출력 buffer 또는 nullptr입니다.
	 * @param capacity NUL 문자를 포함한 buffer 크기입니다.
	 * @return NUL 문자를 제외한 전체 필요 길이입니다.
	 */
	[[nodiscard]] std::size_t formatDiagnostic(const Diagnostic &diagnostic,
										  char *buffer,
										  std::size_t capacity) noexcept;

}

#endif
