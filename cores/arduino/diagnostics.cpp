/**
 * @file diagnostics.cpp
 * @brief NU54DK Arduino Core의 순수 공개 진단 포맷 구현입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include "nucode/Diagnostics.h"

#if defined(CONFIG_NUCODE_ARDUINO_GPIO)
#include "internal/pin_description.h"
#endif

#if defined(CONFIG_NUCODE_ARDUINO_SERIAL)
#include "internal/SerialBackend.h"
#endif

#if defined(CONFIG_NUCODE_ARDUINO_WIRE)
#include "internal/WireBackend.h"
#endif

#if defined(CONFIG_NUCODE_ARDUINO_SPI)
#include "internal/SPIBackend.h"
#endif

#if defined(CONFIG_NUCODE_ARDUINO_ADC) || defined(CONFIG_NUCODE_ARDUINO_PWM)
#include "internal/AnalogBackend.h"
#endif

#include <stdio.h>

namespace nucode::arduino
{
	namespace
	{

		/** @brief 투영할 수 없는 backend를 명시적인 공개 오류로 만듭니다. */
		[[nodiscard]] constexpr Diagnostic unsupportedDiagnostic(
			DiagnosticSubsystem subsystem) noexcept
		{
			return {subsystem, DiagnosticCode::unsupported, 0, 0U};
		}

#if defined(CONFIG_NUCODE_ARDUINO_GPIO)
		/** @brief GPIO 비공개 오류를 공통 공개 코드로 변환합니다. */
		[[nodiscard]] constexpr DiagnosticCode gpioCode(internal::GpioError error) noexcept
		{
			switch (error)
			{
			case internal::GpioError::none:
				return DiagnosticCode::none;
			case internal::GpioError::invalid_context:
				return DiagnosticCode::invalid_context;
			case internal::GpioError::invalid_pin:
				return DiagnosticCode::invalid_pin;
			case internal::GpioError::invalid_mode:
			case internal::GpioError::invalid_value:
			case internal::GpioError::null_callback:
			case internal::GpioError::invalid_interrupt_mode:
				return DiagnosticCode::invalid_argument;
			case internal::GpioError::unsupported_capability:
			case internal::GpioError::unsupported_devicetree_flags:
				return DiagnosticCode::unsupported;
			case internal::GpioError::device_not_ready:
				return DiagnosticCode::device_not_ready;
			case internal::GpioError::pin_not_configured:
			case internal::GpioError::wrong_mode:
			case internal::GpioError::interrupt_not_configured:
			case internal::GpioError::interrupt_restore_without_disable:
				return DiagnosticCode::not_started;
			case internal::GpioError::ownership_conflict:
				return DiagnosticCode::ownership_conflict;
			case internal::GpioError::resource_exhausted:
			case internal::GpioError::nesting_overflow:
				return DiagnosticCode::overflow;
			case internal::GpioError::driver_error:
				return DiagnosticCode::driver_error;
			default:
				return DiagnosticCode::unsupported;
			}
		}

		/** @brief 현재 GPIO backend 상태를 공개 진단 값으로 투영합니다. */
		[[nodiscard]] Diagnostic gpioDiagnostic() noexcept
		{
			const auto code = gpioCode(internal::lastGpioError());
			const int driver_error = code == DiagnosticCode::driver_error
								 ? internal::lastGpioDriverError()
								 : 0;
			return {DiagnosticSubsystem::gpio, code, driver_error, 0U};
		}
#endif

#if defined(CONFIG_NUCODE_ARDUINO_SERIAL)
		/** @brief Serial 비공개 오류를 공통 공개 코드로 변환합니다. */
		[[nodiscard]] constexpr DiagnosticCode serialCode(internal::SerialError error) noexcept
		{
			switch (error)
			{
			case internal::SerialError::none:
				return DiagnosticCode::none;
			case internal::SerialError::invalid_context:
				return DiagnosticCode::invalid_context;
			case internal::SerialError::unsupported_config:
				return DiagnosticCode::unsupported;
			case internal::SerialError::device_not_ready:
				return DiagnosticCode::device_not_ready;
			case internal::SerialError::not_started:
				return DiagnosticCode::not_started;
			case internal::SerialError::driver_error:
				return DiagnosticCode::driver_error;
			case internal::SerialError::rx_overflow:
				return DiagnosticCode::overflow;
			default:
				return DiagnosticCode::unsupported;
			}
		}

		/** @brief 현재 Serial backend 상태를 공개 진단 값으로 투영합니다. */
		[[nodiscard]] Diagnostic serialDiagnostic() noexcept
		{
			const auto error = internal::lastSerialError();
			const auto code = serialCode(error);
			const int driver_error = code == DiagnosticCode::driver_error
								 ? internal::lastSerialDriverError()
								 : 0;
			const std::uint32_t detail = error == internal::SerialError::rx_overflow
									 ? internal::serialDroppedRxBytes()
									 : 0U;
			return {DiagnosticSubsystem::serial, code, driver_error, detail};
		}
#endif

#if defined(CONFIG_NUCODE_ARDUINO_WIRE)
		/** @brief Wire 비공개 오류를 공통 공개 코드로 변환합니다. */
		[[nodiscard]] constexpr DiagnosticCode wireCode(internal::WireError error) noexcept
		{
			switch (error)
			{
			case internal::WireError::none:
				return DiagnosticCode::none;
			case internal::WireError::invalid_context:
				return DiagnosticCode::invalid_context;
			case internal::WireError::device_not_ready:
				return DiagnosticCode::device_not_ready;
			case internal::WireError::not_started:
			case internal::WireError::transmission_not_active:
				return DiagnosticCode::not_started;
			case internal::WireError::invalid_address:
				return DiagnosticCode::invalid_argument;
			case internal::WireError::unsupported_clock:
			case internal::WireError::unsupported_peripheral_mode:
			case internal::WireError::unsupported_no_stop_read:
				return DiagnosticCode::unsupported;
			case internal::WireError::transaction_owner_mismatch:
			case internal::WireError::pending_restart_conflict:
			case internal::WireError::pending_restart_address_mismatch:
				return DiagnosticCode::ownership_conflict;
			case internal::WireError::tx_buffer_overflow:
			case internal::WireError::rx_buffer_overflow:
				return DiagnosticCode::overflow;
			case internal::WireError::driver_error:
				return DiagnosticCode::driver_error;
			default:
				return DiagnosticCode::unsupported;
			}
		}

		/** @brief 현재 Wire backend 상태를 공개 진단 값으로 투영합니다. */
		[[nodiscard]] Diagnostic wireDiagnostic() noexcept
		{
			const auto code = wireCode(internal::lastWireError());
			const int driver_error = code == DiagnosticCode::driver_error
								 ? internal::lastWireDriverError()
								 : 0;
			return {DiagnosticSubsystem::wire, code, driver_error, 0U};
		}
#endif

#if defined(CONFIG_NUCODE_ARDUINO_SPI)
		/** @brief SPI 비공개 오류를 공통 공개 코드로 변환합니다. */
		[[nodiscard]] constexpr DiagnosticCode spiCode(internal::SpiError error) noexcept
		{
			switch (error)
			{
			case internal::SpiError::none:
				return DiagnosticCode::none;
			case internal::SpiError::invalid_context:
				return DiagnosticCode::invalid_context;
			case internal::SpiError::device_not_ready:
				return DiagnosticCode::device_not_ready;
			case internal::SpiError::not_started:
			case internal::SpiError::transaction_not_active:
				return DiagnosticCode::not_started;
			case internal::SpiError::transaction_already_active:
			case internal::SpiError::transaction_owner_mismatch:
				return DiagnosticCode::ownership_conflict;
			case internal::SpiError::invalid_frequency:
			case internal::SpiError::invalid_bit_order:
			case internal::SpiError::invalid_data_mode:
			case internal::SpiError::invalid_buffer:
				return DiagnosticCode::invalid_argument;
			case internal::SpiError::unsupported_bus_mode:
			case internal::SpiError::unsupported_operation:
				return DiagnosticCode::unsupported;
			case internal::SpiError::driver_error:
				return DiagnosticCode::driver_error;
			default:
				return DiagnosticCode::unsupported;
			}
		}

		/** @brief 현재 SPI backend 상태를 공개 진단 값으로 투영합니다. */
		[[nodiscard]] Diagnostic spiDiagnostic() noexcept
		{
			const auto code = spiCode(internal::lastSpiError());
			const int driver_error = code == DiagnosticCode::driver_error
								 ? internal::lastSpiDriverError()
								 : 0;
			return {DiagnosticSubsystem::spi, code, driver_error, 0U};
		}
#endif

#if defined(CONFIG_NUCODE_ARDUINO_ADC) || defined(CONFIG_NUCODE_ARDUINO_PWM)
		/** @brief Analog 비공개 오류를 공통 공개 코드로 변환합니다. */
		[[nodiscard]] constexpr DiagnosticCode analogCode(internal::AnalogError error) noexcept
		{
			switch (error)
			{
			case internal::AnalogError::none:
				return DiagnosticCode::none;
			case internal::AnalogError::invalid_context:
				return DiagnosticCode::invalid_context;
			case internal::AnalogError::invalid_pin:
				return DiagnosticCode::invalid_pin;
			case internal::AnalogError::invalid_value:
				return DiagnosticCode::invalid_argument;
			case internal::AnalogError::device_not_ready:
				return DiagnosticCode::device_not_ready;
			case internal::AnalogError::unsupported_reference:
			case internal::AnalogError::unsupported_devicetree:
				return DiagnosticCode::unsupported;
			case internal::AnalogError::driver_error:
				return DiagnosticCode::driver_error;
			default:
				return DiagnosticCode::unsupported;
			}
		}

		/** @brief 현재 Analog backend 상태를 공개 진단 값으로 투영합니다. */
		[[nodiscard]] Diagnostic analogDiagnostic() noexcept
		{
			const auto code = analogCode(internal::lastAnalogError());
			const int driver_error = code == DiagnosticCode::driver_error
								 ? internal::lastAnalogDriverError()
								 : 0;
			return {DiagnosticSubsystem::analog, code, driver_error, 0U};
		}
#endif

	}

	const char *diagnosticSubsystemToken(DiagnosticSubsystem subsystem) noexcept
	{
		switch (subsystem)
		{
		case DiagnosticSubsystem::core:
			return "core";
		case DiagnosticSubsystem::gpio:
			return "gpio";
		case DiagnosticSubsystem::time:
			return "time";
		case DiagnosticSubsystem::serial:
			return "serial";
		case DiagnosticSubsystem::wire:
			return "wire";
		case DiagnosticSubsystem::spi:
			return "spi";
		case DiagnosticSubsystem::analog:
			return "analog";
		default:
			return "unknown";
		}
	}

	const char *diagnosticCodeToken(DiagnosticCode code) noexcept
	{
		switch (code)
		{
		case DiagnosticCode::none:
			return "none";
		case DiagnosticCode::invalid_context:
			return "invalid-context";
		case DiagnosticCode::invalid_argument:
			return "invalid-argument";
		case DiagnosticCode::invalid_pin:
			return "invalid-pin";
		case DiagnosticCode::unsupported:
			return "unsupported";
		case DiagnosticCode::device_not_ready:
			return "device-not-ready";
		case DiagnosticCode::not_started:
			return "not-started";
		case DiagnosticCode::overflow:
			return "overflow";
		case DiagnosticCode::ownership_conflict:
			return "ownership-conflict";
		case DiagnosticCode::driver_error:
			return "driver-error";
		default:
			return "unknown";
		}
	}

	Diagnostic lastDiagnostic(DiagnosticSubsystem subsystem) noexcept
	{
		switch (subsystem)
		{
		case DiagnosticSubsystem::core:
			return {DiagnosticSubsystem::core, DiagnosticCode::none, 0, 0U};
		case DiagnosticSubsystem::gpio:
#if defined(CONFIG_NUCODE_ARDUINO_GPIO)
			return gpioDiagnostic();
#else
			return unsupportedDiagnostic(subsystem);
#endif
		case DiagnosticSubsystem::time:
			return unsupportedDiagnostic(subsystem);
		case DiagnosticSubsystem::serial:
#if defined(CONFIG_NUCODE_ARDUINO_SERIAL)
			return serialDiagnostic();
#else
			return unsupportedDiagnostic(subsystem);
#endif
		case DiagnosticSubsystem::wire:
#if defined(CONFIG_NUCODE_ARDUINO_WIRE)
			return wireDiagnostic();
#else
			return unsupportedDiagnostic(subsystem);
#endif
		case DiagnosticSubsystem::spi:
#if defined(CONFIG_NUCODE_ARDUINO_SPI)
			return spiDiagnostic();
#else
			return unsupportedDiagnostic(subsystem);
#endif
		case DiagnosticSubsystem::analog:
#if defined(CONFIG_NUCODE_ARDUINO_ADC) || defined(CONFIG_NUCODE_ARDUINO_PWM)
			return analogDiagnostic();
#else
			return unsupportedDiagnostic(subsystem);
#endif
		default:
			return unsupportedDiagnostic(subsystem);
		}
	}

	std::size_t formatDiagnostic(const Diagnostic &diagnostic,
								 char *buffer,
								 std::size_t capacity) noexcept
	{
		if (buffer == nullptr)
		{
			capacity = 0U;
		}

		const int required = ::snprintf(buffer,
									   capacity,
									   "NU54:%s:%s:driver=%d:detail=%lu",
									   diagnosticSubsystemToken(diagnostic.subsystem),
									   diagnosticCodeToken(diagnostic.code),
									   diagnostic.driver_error,
									   static_cast<unsigned long>(diagnostic.detail));
		return required < 0 ? 0U : static_cast<std::size_t>(required);
	}

}
