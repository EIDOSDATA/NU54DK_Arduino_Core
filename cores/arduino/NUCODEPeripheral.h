/**
 * @file NUCODEPeripheral.h
 * @brief NU54DK 주변장치의 ArduinoCore-API 확장 계약을 정의합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#ifndef NUCODE_ARDUINO_CORE_NUCODE_PERIPHERAL_H_
#define NUCODE_ARDUINO_CORE_NUCODE_PERIPHERAL_H_

#include <api/Common.h>
#include <api/HardwareI2C.h>
#include <api/HardwareSPI.h>
#include <api/HardwareSerial.h>

#include "nucode/PeripheralInventory.h"

#include <cstdint>

namespace nucode::arduino
{
	/** @brief NU54DK 주변장치 backend가 공개하는 고정 capability 비트입니다. */
	enum class PeripheralCapability : std::uint32_t
	{
		none = 0U,
		pin_remap = 1U << 0U,
		controller = 1U << 1U,
		target = 1U << 2U,
		no_stop_read = 1U << 3U,
		interrupt_mask = 1U << 4U,
	};

	/** @brief 두 주변장치 capability를 하나의 비트 마스크로 결합합니다. */
	[[nodiscard]] constexpr PeripheralCapability operator|(PeripheralCapability lhs,
														   PeripheralCapability rhs) noexcept
	{
		return static_cast<PeripheralCapability>(static_cast<std::uint32_t>(lhs) |
												 static_cast<std::uint32_t>(rhs));
	}

	/** @brief capability 비트 마스크에 요청 기능이 포함되는지 확인합니다. */
	[[nodiscard]] constexpr bool hasPeripheralCapability(PeripheralCapability capabilities,
														 PeripheralCapability requested) noexcept
	{
		return (static_cast<std::uint32_t>(capabilities) &
				static_cast<std::uint32_t>(requested)) != 0U;
	}

	/**
	 * @brief 독립 UARTE를 사용하는 NU54DK HardwareSerial 확장 형식입니다.
	 *
	 * @details setPins()는 end() 상태에서 다음 begin()에 사용할 route만 예약합니다.
	 * 기본 console Serial은 이 형식을 사용하지 않으며 핀을 바꿀 수 없습니다.
	 */
	class Nu54HardwareSerial : public ::arduino::HardwareSerial
	{
	public:
		/**
		 * @brief 다음 begin()에 사용할 RX와 TX 논리 핀을 선택합니다.
		 *
		 * @param rx_pin RX 기능을 부여할 Arduino 논리 핀입니다.
		 * @param tx_pin TX 기능을 부여할 Arduino 논리 핀입니다.
		 * @return stage에 성공하면 true, 실행 중이거나 route가 유효하지 않으면 false입니다.
		 */
		virtual bool setPins(pin_size_t rx_pin, pin_size_t tx_pin) noexcept = 0;

		/** @brief 이 instance가 제공하는 고정 capability를 반환합니다. */
		[[nodiscard]] virtual PeripheralCapability capabilities() const noexcept = 0;
	};

	/**
	 * @brief NU54DK I2C controller의 핀 선택 기능을 추가한 Wire 형식입니다.
	 *
	 * @details 현재 stock NCS backend는 controller 전용입니다. target mode와
	 * requestFrom(..., false)의 read no-STOP은 capability에 포함되지 않습니다.
	 */
	class Nu54TwoWire : public ::arduino::HardwareI2C
	{
	public:
		/**
		 * @brief 다음 begin()에 사용할 SDA와 SCL 논리 핀을 선택합니다.
		 *
		 * @param sda_pin SDA 기능을 부여할 Arduino 논리 핀입니다.
		 * @param scl_pin SCL 기능을 부여할 Arduino 논리 핀입니다.
		 * @return stage에 성공하면 true, 실행 중이거나 route가 유효하지 않으면 false입니다.
		 */
		virtual bool setPins(pin_size_t sda_pin, pin_size_t scl_pin) noexcept = 0;

		/** @brief 이 instance가 제공하는 고정 capability를 반환합니다. */
		[[nodiscard]] virtual PeripheralCapability capabilities() const noexcept = 0;
	};

	/**
	 * @brief NU54DK SPI controller의 핀 선택 기능을 추가한 SPI 형식입니다.
	 *
	 * @details usingInterrupt()는 Arduino GPIO interrupt를 transaction 동안
	 * 선택적으로 마스킹합니다. attachInterrupt()는 SPIM controller에서 지원하지 않습니다.
	 */
	class Nu54SPIClass : public ::arduino::HardwareSPI
	{
	public:
		/**
		 * @brief 다음 begin()에 사용할 SCK, MISO와 MOSI 논리 핀을 선택합니다.
		 *
		 * @param sck_pin SCK 기능을 부여할 Arduino 논리 핀입니다.
		 * @param miso_pin MISO 기능을 부여할 Arduino 논리 핀입니다.
		 * @param mosi_pin MOSI 기능을 부여할 Arduino 논리 핀입니다.
		 * @return stage에 성공하면 true, 실행 중이거나 route가 유효하지 않으면 false입니다.
		 */
		virtual bool setPins(pin_size_t sck_pin, pin_size_t miso_pin,
							 pin_size_t mosi_pin) noexcept = 0;

		/** @brief 이 instance가 제공하는 고정 capability를 반환합니다. */
		[[nodiscard]] virtual PeripheralCapability capabilities() const noexcept = 0;
	};

}

/** @brief uart30을 소유하는 독립 NU54DK Arduino serial instance입니다. */
#if !defined(__ZEPHYR__) || defined(CONFIG_NUCODE_ARDUINO_SERIAL1)
extern nucode::arduino::Nu54HardwareSerial &Serial1;
#endif

/** @brief i2c22 controller와 runtime 핀 route를 소유하는 Wire instance입니다. */
extern nucode::arduino::Nu54TwoWire &Wire;

/** @brief spi00 controller와 고정 signal route를 소유하는 SPI instance입니다. */
extern nucode::arduino::Nu54SPIClass &SPI;

#endif
