/**
 * @file SPIBackend.h
 * @brief Zephyr SPI controller backend의 비공개 진단 계약입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#ifndef NUCODE_ARDUINO_CORE_INTERNAL_SPI_BACKEND_H_
#define NUCODE_ARDUINO_CORE_INTERNAL_SPI_BACKEND_H_

#include <cstdint>

namespace nucode::arduino::internal
{

	/** @brief SPI controller에서 마지막으로 관측한 상태입니다. */
	enum class SpiError : std::uint8_t
	{
		none = 0U,
		invalid_context,
		device_not_ready,
		not_started,
		transaction_already_active,
		transaction_not_active,
		transaction_owner_mismatch,
		invalid_frequency,
		invalid_bit_order,
		invalid_data_mode,
		unsupported_bus_mode,
		unsupported_operation,
		invalid_pin_route,
		route_busy,
		route_error,
		interrupt_mask_error,
		invalid_buffer,
		driver_error,
	};

	/** @brief 마지막 SPI 상태를 반환합니다. */
	[[nodiscard]] SpiError lastSpiError() noexcept;

	/** @brief 마지막 Zephyr SPI 오류 번호를 반환합니다. */
	[[nodiscard]] int lastSpiDriverError() noexcept;

	/** @brief SPI transaction이 열려 있는지 반환합니다. */
	[[nodiscard]] bool spiTransactionActive() noexcept;

	/** @brief 현재 transaction의 SCK 속도를 반환합니다. */
	[[nodiscard]] std::uint32_t spiTransactionFrequency() noexcept;

	/** @brief SPI 오류 상태를 초기화합니다. */
	void clearSpiDiagnostics() noexcept;

}

#endif
