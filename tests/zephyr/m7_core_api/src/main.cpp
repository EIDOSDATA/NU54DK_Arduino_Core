/**
 * @file main.cpp
 * @brief M7 Wire, SPI, ADC와 PWM 계약을 target emulator로 자동 검증합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <Arduino.h>
#include <SPI.h>
#include <Wire.h>

#include <zephyr/device.h>
#include <zephyr/drivers/adc/adc_emul.h>
#include <zephyr/drivers/emul.h>
#include <zephyr/drivers/i2c.h>
#include <zephyr/drivers/i2c_emul.h>
#include <zephyr/drivers/pwm/pwm_fake.h>
#include <zephyr/drivers/spi.h>
#include <zephyr/drivers/spi_emul.h>
#include <zephyr/fff.h>
#include <zephyr/ztest.h>

#include <cstddef>
#include <cstdint>
#include <errno.h>
#include <string.h>

#include "internal/AnalogBackend.h"
#include "internal/SPIBackend.h"
#include "internal/WireBackend.h"

/** @brief Zephyr fake driver가 공유하는 FFF 전역 상태입니다. */
DEFINE_FFF_GLOBALS;

namespace
{

	using nucode::arduino::internal::AnalogError;
	using nucode::arduino::internal::clearAnalogDiagnostics;
	using nucode::arduino::internal::clearSpiDiagnostics;
	using nucode::arduino::internal::clearWireDiagnostics;
	using nucode::arduino::internal::lastAnalogDriverError;
	using nucode::arduino::internal::lastAnalogError;
	using nucode::arduino::internal::lastSpiDriverError;
	using nucode::arduino::internal::lastSpiError;
	using nucode::arduino::internal::lastWireDriverError;
	using nucode::arduino::internal::lastWireError;
	using nucode::arduino::internal::SpiError;
	using nucode::arduino::internal::spiTransactionActive;
	using nucode::arduino::internal::spiTransactionFrequency;
	using nucode::arduino::internal::WireError;
	using nucode::arduino::internal::wireHasPendingRestart;

	template <typename Left, typename Right>
	inline constexpr bool same_type = false;

	template <typename Value>
	inline constexpr bool same_type<Value, Value> = true;

	/** @brief M7 Wire 시험에 사용하는 고정 target 주소입니다. */
	constexpr std::uint16_t test_i2c_address = 0x5AU;

	/** @brief M7 Wire 시험용 I2C controller emulator입니다. */
	const struct device *const test_i2c = DEVICE_DT_GET(DT_NODELABEL(m7_i2c));

	/** @brief M7 SPI 시험용 controller emulator입니다. */
	const struct device *const test_spi = DEVICE_DT_GET(DT_NODELABEL(m7_spi));

	/** @brief M7 ADC 시험용 ADC emulator입니다. */
	const struct device *const test_adc = DEVICE_DT_GET(DT_NODELABEL(m7_adc));

	/** @brief I2C 전송 한 번에서 보존할 최대 message 수입니다. */
	constexpr std::size_t maximum_i2c_messages = 2U;

	/** @brief I2C message 하나에서 보존할 최대 byte 수입니다. */
	constexpr std::size_t maximum_i2c_bytes = 32U;

	/** @brief I2C emulator가 관측한 전송 계약입니다. */
	struct I2cObservation
	{
		int call_count = 0;
		int forced_result = 0;
		int address = -1;
		int message_count = 0;
		std::uint16_t flags[maximum_i2c_messages] = {};
		std::size_t lengths[maximum_i2c_messages] = {};
		std::uint8_t bytes[maximum_i2c_messages][maximum_i2c_bytes] = {};
		std::uint8_t read_seed = 0x6AU;
	};

	I2cObservation i2c_observation;
	struct emul i2c_target = {};
	struct i2c_emul i2c_backend = {};

	/** @brief SPI emulator가 관측한 설정과 full-duplex byte입니다. */
	struct SpiObservation
	{
		int call_count = 0;
		int forced_result = 0;
		std::uint32_t frequency = 0U;
		spi_operation_t operation = 0U;
		std::uint16_t slave = 0U;
		std::size_t length = 0U;
		std::uint8_t transmitted[96] = {};
	};

	SpiObservation spi_observation;
	struct emul spi_target = {};
	struct spi_emul spi_backend = {};

	/**
	 * @brief I2C message 구조와 데이터를 기록하고 read 결과를 채웁니다.
	 *
	 * @param target 등록된 시험 target입니다.
	 * @param messages Zephyr I2C message 배열입니다.
	 * @param message_count message 개수입니다.
	 * @param address target 주소입니다.
	 * @return 주입된 오류 또는 0입니다.
	 */
	int observeI2cTransfer(const struct emul *target, struct i2c_msg *messages,
						   int message_count, int address)
	{
		ARG_UNUSED(target);
		++i2c_observation.call_count;
		i2c_observation.address = address;
		i2c_observation.message_count = message_count;

		const int recorded_count = MIN(message_count, static_cast<int>(maximum_i2c_messages));
		for (int index = 0; index < recorded_count; ++index)
		{
			i2c_observation.flags[index] = messages[index].flags;
			i2c_observation.lengths[index] = messages[index].len;
			const std::size_t recorded_length =
				MIN(static_cast<std::size_t>(messages[index].len), maximum_i2c_bytes);

			if ((messages[index].flags & I2C_MSG_READ) != 0U)
			{
				for (std::size_t byte_index = 0U; byte_index < messages[index].len;
					 ++byte_index)
				{
					messages[index].buf[byte_index] =
						static_cast<std::uint8_t>(i2c_observation.read_seed + byte_index);
				}
			}
			memcpy(i2c_observation.bytes[index], messages[index].buf, recorded_length);
		}

		return i2c_observation.forced_result;
	}

	const struct i2c_emul_api i2c_api = {
		.transfer = observeI2cTransfer,
	};

	/**
	 * @brief SPI 설정과 TX byte를 기록하고 각 RX byte를 반전해 반환합니다.
	 *
	 * @param target 등록된 시험 target입니다.
	 * @param configuration Zephyr SPI transaction 설정입니다.
	 * @param transmit_buffers 송신 buffer 집합입니다.
	 * @param receive_buffers 수신 buffer 집합입니다.
	 * @return 주입된 오류 또는 0입니다.
	 */
	int observeSpiTransfer(const struct emul *target, const struct spi_config *configuration,
						   const struct spi_buf_set *transmit_buffers,
						   const struct spi_buf_set *receive_buffers)
	{
		ARG_UNUSED(target);
		++spi_observation.call_count;
		spi_observation.frequency = configuration->frequency;
		spi_observation.operation = configuration->operation;
		spi_observation.slave = configuration->slave;

		if (spi_observation.forced_result < 0)
		{
			return spi_observation.forced_result;
		}

		zassert_not_null(transmit_buffers, "SPI TX buffer 집합이 없습니다.");
		zassert_not_null(receive_buffers, "SPI RX buffer 집합이 없습니다.");
		zassert_equal(transmit_buffers->count, 1U, "SPI TX buffer 개수가 다릅니다.");
		zassert_equal(receive_buffers->count, 1U, "SPI RX buffer 개수가 다릅니다.");
		const auto *transmit =
			static_cast<const std::uint8_t *>(transmit_buffers->buffers[0].buf);
		auto *receive = static_cast<std::uint8_t *>(receive_buffers->buffers[0].buf);
		const std::size_t length = transmit_buffers->buffers[0].len;
		zassert_equal(receive_buffers->buffers[0].len, length,
					  "SPI full-duplex TX/RX 길이가 다릅니다.");
		zassert_true((spi_observation.length + length) <= sizeof(spi_observation.transmitted),
					 "SPI 관측 buffer를 초과했습니다.");
		for (std::size_t index = 0U; index < length; ++index)
		{
			spi_observation.transmitted[spi_observation.length + index] = transmit[index];
			receive[index] = static_cast<std::uint8_t>(transmit[index] ^ 0xFFU);
		}
		spi_observation.length += length;
		return 0;
	}

	const struct spi_emul_api spi_api = {
		.io = observeSpiTransfer,
	};

	/** @brief I2C 관측 상태를 기본값으로 되돌립니다. */
	void resetI2cObservation()
	{
		i2c_observation = {};
		i2c_observation.read_seed = 0x6AU;
	}

	/** @brief SPI 관측 상태를 기본값으로 되돌립니다. */
	void resetSpiObservation()
	{
		spi_observation = {};
	}

	/** @brief M7 I2C target emulator를 controller에 한 번 등록합니다. */
	void *wireSuiteSetup()
	{
		zassert_true(device_is_ready(test_i2c), "I2C controller emulator가 준비되지 않았습니다.");
		i2c_target.dev = test_i2c;
		i2c_backend.target = &i2c_target;
		i2c_backend.api = &i2c_api;
		i2c_backend.addr = test_i2c_address;
		zassert_ok(i2c_emul_register(test_i2c, &i2c_backend),
				   "I2C target emulator 등록에 실패했습니다.");
		return nullptr;
	}

	/** @brief M7 SPI target emulator를 controller에 한 번 등록합니다. */
	void *spiSuiteSetup()
	{
		zassert_true(device_is_ready(test_spi), "SPI controller emulator가 준비되지 않았습니다.");
		spi_target.dev = test_spi;
		spi_backend.target = &spi_target;
		spi_backend.api = &spi_api;
		spi_backend.chipsel = 0U;
		zassert_ok(spi_emul_register(test_spi, &spi_backend),
				   "SPI target emulator 등록에 실패했습니다.");
		return nullptr;
	}

	/** @brief 각 Wire 시험 전에 lifecycle과 진단을 초기화합니다. */
	void wireBefore(void *)
	{
		Wire.end();
		clearWireDiagnostics();
		resetI2cObservation();
	}

	/** @brief 각 SPI 시험 전에 lifecycle과 진단을 초기화합니다. */
	void spiBefore(void *)
	{
		SPI.end();
		clearSpiDiagnostics();
		resetSpiObservation();
	}

	/** @brief ADC emulator에 driver 오류를 주입합니다. */
	int failAdcRead(const struct device *device, unsigned int channel, void *data,
					std::uint32_t *result)
	{
		ARG_UNUSED(device);
		ARG_UNUSED(channel);
		ARG_UNUSED(data);
		ARG_UNUSED(result);
		return -EIO;
	}

	/** @brief 각 analog 시험 전에 ADC/PWM fake와 진단을 초기화합니다. */
	void analogBefore(void *)
	{
		clearAnalogDiagnostics();
		RESET_FAKE(fake_pwm_set_cycles);
		zassert_ok(adc_emul_const_raw_value_set(test_adc, 5U, 0U),
				   "ADC emulator 초기화에 실패했습니다.");
	}

}

ZTEST(m7_wire, test_public_header_and_repeated_start_contract)
{
	static_assert(same_type<decltype(Wire), TwoWire &>);

	Wire.begin();
	Wire.beginTransmission(test_i2c_address);
	zassert_equal(Wire.write(static_cast<std::uint8_t>(0x0CU)), 1U,
				  "register pointer를 TX buffer에 넣지 못했습니다.");
	zassert_equal(Wire.endTransmission(false), 0U,
				  "no-STOP write가 repeated-start 대기로 전환되지 않았습니다.");
	zassert_true(wireHasPendingRestart(), "repeated-start 대기 상태가 기록되지 않았습니다.");
	zassert_equal(i2c_observation.call_count, 0,
				  "no-STOP write가 read 전에 물리 전송되었습니다.");

	zassert_equal(Wire.requestFrom(test_i2c_address, 1U, true), 1U,
				  "결합 write/read가 한 byte를 반환하지 않았습니다.");
	zassert_equal(i2c_observation.call_count, 1, "결합 전송 호출 횟수가 다릅니다.");
	zassert_equal(i2c_observation.address, test_i2c_address, "I2C target 주소가 다릅니다.");
	zassert_equal(i2c_observation.message_count, 2, "repeated-start message 수가 다릅니다.");
	zassert_equal(i2c_observation.lengths[0], 1U, "register write 길이가 다릅니다.");
	zassert_equal(i2c_observation.bytes[0][0], 0x0CU, "register pointer 값이 다릅니다.");
	zassert_equal(i2c_observation.flags[0], I2C_MSG_WRITE,
				  "첫 message에 STOP 또는 READ가 잘못 포함되었습니다.");
	zassert_true((i2c_observation.flags[1] & I2C_MSG_RESTART) != 0U,
				 "두 번째 message에 RESTART가 없습니다.");
	zassert_true((i2c_observation.flags[1] & I2C_MSG_READ) != 0U,
				 "두 번째 message가 read가 아닙니다.");
	zassert_true((i2c_observation.flags[1] & I2C_MSG_STOP) != 0U,
				 "두 번째 message가 STOP으로 끝나지 않습니다.");
	zassert_equal(Wire.available(), 1, "Wire RX 길이가 다릅니다.");
	zassert_equal(Wire.peek(), 0x6A, "Wire.peek 결과가 다릅니다.");
	zassert_equal(Wire.read(), 0x6A, "Wire.read 결과가 다릅니다.");
	zassert_equal(Wire.available(), 0, "Wire.read 뒤 RX 길이가 줄지 않았습니다.");
	zassert_equal(lastWireError(), WireError::none, "성공 뒤 Wire 진단이 남았습니다.");
}

ZTEST(m7_wire, test_zero_byte_address_probe_contract)
{
	Wire.begin();
	Wire.beginTransmission(test_i2c_address);
	zassert_equal(Wire.endTransmission(), 0U,
				  "0-byte Wire address probe가 거부되었습니다.");
	zassert_equal(lastWireError(), WireError::none,
				  "0-byte address probe 성공 뒤 오류가 남았습니다.");
	zassert_equal(i2c_observation.call_count, 1,
				  "0-byte address probe가 I2C driver에 전달되지 않았습니다.");
	zassert_equal(i2c_observation.address, test_i2c_address,
				  "0-byte address probe의 target 주소가 다릅니다.");
	zassert_equal(i2c_observation.message_count, 1,
				  "0-byte address probe message 개수가 다릅니다.");
	zassert_equal(i2c_observation.lengths[0], 0U,
				  "address probe가 0-byte write가 아닙니다.");
	zassert_equal(i2c_observation.flags[0], I2C_MSG_WRITE | I2C_MSG_STOP,
				  "0-byte address probe에 STOP write flag가 없습니다.");

	resetI2cObservation();
	i2c_observation.forced_result = -EIO;
	Wire.beginTransmission(test_i2c_address);
	zassert_equal(Wire.endTransmission(), 4U,
				  "0-byte address probe driver 오류가 Arduino 상태 4로 변환되지 않았습니다.");
	zassert_equal(lastWireError(), WireError::driver_error,
				  "0-byte address probe driver 오류가 기록되지 않았습니다.");
	zassert_equal(lastWireDriverError(), -EIO,
				  "0-byte address probe의 원본 driver errno가 보존되지 않았습니다.");
}

ZTEST(m7_wire, test_buffer_address_and_no_stop_read_validation)
{
	Wire.begin();
	Wire.beginTransmission(test_i2c_address);
	for (std::size_t index = 0U; index < 32U; ++index)
	{
		zassert_equal(Wire.write(static_cast<std::uint8_t>(index)), 1U,
					  "Wire TX buffer 정상 범위가 너무 작습니다.");
	}
	zassert_equal(Wire.availableForWrite(), 0, "가득 찬 TX buffer 여유가 0이 아닙니다.");
	zassert_equal(Wire.write(static_cast<std::uint8_t>(0xFFU)), 0U,
				  "Wire TX buffer 초과가 거부되지 않았습니다.");
	zassert_equal(lastWireError(), WireError::tx_buffer_overflow,
				  "TX overflow 진단이 다릅니다.");
	zassert_equal(Wire.endTransmission(), 1U, "TX overflow 상태 번호가 다릅니다.");
	zassert_equal(i2c_observation.call_count, 0, "overflow TX가 controller에 전달되었습니다.");

	zassert_equal(Wire.requestFrom(0x80U, 1U, true), 0U,
				  "7-bit 범위를 벗어난 주소가 거부되지 않았습니다.");
	zassert_equal(lastWireError(), WireError::invalid_address,
				  "범위 밖 주소 진단이 다릅니다.");

	zassert_equal(Wire.requestFrom(test_i2c_address, 1U, false), 0U,
				  "nRF TWIM에서 no-STOP read가 허용되었습니다.");
	zassert_equal(lastWireError(), WireError::unsupported_no_stop_read,
				  "no-STOP read 거부 진단이 다릅니다.");
	zassert_equal(i2c_observation.call_count, 0,
				  "거부된 no-STOP read가 controller에 전달되었습니다.");
}

ZTEST(m7_wire, test_clock_driver_error_and_restart_conflicts)
{
	Wire.begin();
	Wire.setClock(400000U);
	zassert_equal(lastWireError(), WireError::none, "400 kHz 설정에 실패했습니다.");
	std::uint32_t configuration = 0U;
	zassert_ok(i2c_get_config(test_i2c, &configuration), "I2C 설정 조회에 실패했습니다.");
	zassert_equal(I2C_SPEED_GET(configuration), I2C_SPEED_FAST,
				  "400 kHz가 Zephyr fast mode로 반영되지 않았습니다.");
	Wire.setClock(123456U);
	zassert_equal(lastWireError(), WireError::unsupported_clock,
				  "미지원 Wire clock이 거부되지 않았습니다.");

	Wire.beginTransmission(test_i2c_address);
	zassert_equal(Wire.write(static_cast<std::uint8_t>(0x22U)), 1U, "시험 TX 구성에 실패했습니다.");
	zassert_equal(Wire.endTransmission(false), 0U, "repeated-start 준비에 실패했습니다.");
	zassert_equal(Wire.requestFrom(0x6CU, 1U, true), 0U,
				  "다른 주소로 pending repeated-start가 실행되었습니다.");
	zassert_equal(lastWireError(), WireError::pending_restart_address_mismatch,
				  "repeated-start 주소 불일치 진단이 다릅니다.");

	resetI2cObservation();
	i2c_observation.forced_result = -EIO;
	Wire.beginTransmission(test_i2c_address);
	zassert_equal(Wire.write(static_cast<std::uint8_t>(0x55U)), 1U, "오류 주입 TX 구성에 실패했습니다.");
	zassert_equal(Wire.endTransmission(), 4U, "-EIO의 generic Arduino 상태 변환이 다릅니다.");
	zassert_equal(lastWireError(), WireError::driver_error, "I2C driver 오류가 기록되지 않았습니다.");
	zassert_equal(lastWireDriverError(), -EIO, "원본 I2C driver 오류가 보존되지 않았습니다.");
}

ZTEST_SUITE(m7_wire, nullptr, wireSuiteSetup, wireBefore, nullptr, nullptr);

ZTEST(m7_spi, test_public_header_transaction_mode_order_and_frequency)
{
	static_assert(same_type<decltype(SPI), SPIClass &>);

	SPI.begin();
	SPI.beginTransaction(arduino::SPISettings(2000000U, LSBFIRST, arduino::SPI_MODE3));
	zassert_true(spiTransactionActive(), "SPI transaction이 열리지 않았습니다.");
	zassert_equal(spiTransactionFrequency(), 2000000U, "SPI transaction 속도가 다릅니다.");
	zassert_equal(SPI.transfer(static_cast<std::uint8_t>(0x3CU)), 0xC3U,
				  "SPI byte full-duplex 결과가 다릅니다.");
	zassert_equal(spi_observation.call_count, 1, "SPI emulator 호출 횟수가 다릅니다.");
	zassert_equal(spi_observation.frequency, 2000000U, "Zephyr SPI frequency가 다릅니다.");
	zassert_equal(spi_observation.slave, 0U, "CS 없는 SPI controller의 slave 값이 다릅니다.");
	zassert_equal(SPI_WORD_SIZE_GET(spi_observation.operation), 8U, "SPI word 크기가 다릅니다.");
	zassert_true((spi_observation.operation & SPI_MODE_CPOL) != 0U, "SPI MODE3 CPOL이 없습니다.");
	zassert_true((spi_observation.operation & SPI_MODE_CPHA) != 0U, "SPI MODE3 CPHA가 없습니다.");
	zassert_true((spi_observation.operation & SPI_TRANSFER_LSB) != 0U,
				 "SPI LSBFIRST가 Zephyr 설정에 반영되지 않았습니다.");
	zassert_equal(spi_observation.transmitted[0], 0x3CU, "SPI TX byte가 다릅니다.");
	SPI.endTransaction();
	zassert_false(spiTransactionActive(), "endTransaction 뒤 transaction이 남았습니다.");
	zassert_equal(lastSpiError(), SpiError::none, "정상 SPI 뒤 오류가 남았습니다.");
}

ZTEST(m7_spi, test_all_modes_and_bit_orders)
{
	SPI.begin();
	const BitOrder orders[] = {MSBFIRST, LSBFIRST};
	for (int mode = static_cast<int>(arduino::SPI_MODE0);
		 mode <= static_cast<int>(arduino::SPI_MODE3); ++mode)
	{
		for (const BitOrder order : orders)
		{
			resetSpiObservation();
			SPI.beginTransaction(arduino::SPISettings(
				4000000U, order, static_cast<arduino::SPIMode>(mode)));
			zassert_true(spiTransactionActive(), "유효한 SPI mode/order가 거부되었습니다.");
			static_cast<void>(SPI.transfer(static_cast<std::uint8_t>(mode)));
			const bool expected_cpol = (mode == 2) || (mode == 3);
			const bool expected_cpha = (mode == 1) || (mode == 3);
			zassert_equal((spi_observation.operation & SPI_MODE_CPOL) != 0U,
						  expected_cpol, "SPI CPOL 변환이 다릅니다.");
			zassert_equal((spi_observation.operation & SPI_MODE_CPHA) != 0U,
						  expected_cpha, "SPI CPHA 변환이 다릅니다.");
			zassert_equal((spi_observation.operation & SPI_TRANSFER_LSB) != 0U,
						  order == LSBFIRST, "SPI bit order 변환이 다릅니다.");
			SPI.endTransaction();
		}
	}

	const std::uint32_t boundary_frequencies[] = {16000000U, 32000000U};
	for (const std::uint32_t frequency : boundary_frequencies)
	{
		SPI.beginTransaction(
			arduino::SPISettings(frequency, MSBFIRST, arduino::SPI_MODE0));
		zassert_true(spiTransactionActive(), "SPI00 경계 주파수가 거부되었습니다.");
		zassert_equal(spiTransactionFrequency(), frequency,
					  "SPI00 경계 주파수가 transaction에 보존되지 않았습니다.");
		SPI.endTransaction();
	}
}

ZTEST(m7_spi, test_transfer16_buffer_chunking_and_error_paths)
{
	SPI.begin();
	SPI.beginTransaction(arduino::SPISettings(2000000U, MSBFIRST, arduino::SPI_MODE0));
	zassert_equal(SPI.transfer16(0x1234U), 0xEDCBU, "MSBFIRST transfer16 결과가 다릅니다.");
	zassert_equal(spi_observation.length, 2U, "transfer16 byte 수가 다릅니다.");
	zassert_equal(spi_observation.transmitted[0], 0x12U, "MSBFIRST 상위 byte 순서가 다릅니다.");
	zassert_equal(spi_observation.transmitted[1], 0x34U, "MSBFIRST 하위 byte 순서가 다릅니다.");
	SPI.endTransaction();

	resetSpiObservation();
	SPI.beginTransaction(arduino::SPISettings(2000000U, LSBFIRST, arduino::SPI_MODE0));
	zassert_equal(SPI.transfer16(0x1234U), 0xEDCBU, "LSBFIRST transfer16 결과가 다릅니다.");
	zassert_equal(spi_observation.transmitted[0], 0x34U, "LSBFIRST 하위 byte 순서가 다릅니다.");
	zassert_equal(spi_observation.transmitted[1], 0x12U, "LSBFIRST 상위 byte 순서가 다릅니다.");
	SPI.endTransaction();

	resetSpiObservation();
	SPI.beginTransaction(arduino::SPISettings(8000000U, MSBFIRST, arduino::SPI_MODE0));
	std::uint8_t buffer[40] = {};
	for (std::size_t index = 0U; index < sizeof(buffer); ++index)
	{
		buffer[index] = static_cast<std::uint8_t>(index);
	}
	SPI.transfer(buffer, sizeof(buffer));
	zassert_equal(spi_observation.call_count, 2, "32-byte SPI chunk 경계가 적용되지 않았습니다.");
	zassert_equal(spi_observation.length, sizeof(buffer), "SPI buffer 전송 길이가 다릅니다.");
	for (std::size_t index = 0U; index < sizeof(buffer); ++index)
	{
		zassert_equal(buffer[index], static_cast<std::uint8_t>(index ^ 0xFFU),
					  "SPI in-place buffer 결과가 다릅니다.");
	}

	resetSpiObservation();
	spi_observation.forced_result = -EIO;
	zassert_equal(SPI.transfer(static_cast<std::uint8_t>(0x55U)), 0U,
				  "SPI driver 오류에서 byte 성공값이 반환되었습니다.");
	zassert_equal(lastSpiError(), SpiError::driver_error, "SPI driver 오류가 기록되지 않았습니다.");
	zassert_equal(lastSpiDriverError(), -EIO, "원본 SPI driver 오류가 보존되지 않았습니다.");
	SPI.endTransaction();

	SPI.beginTransaction(arduino::SPISettings(0U, MSBFIRST, arduino::SPI_MODE0));
	zassert_equal(lastSpiError(), SpiError::invalid_frequency, "0 Hz SPI 설정이 거부되지 않았습니다.");
	zassert_false(spiTransactionActive(), "잘못된 SPI 설정이 transaction을 열었습니다.");
	SPI.beginTransaction(arduino::SPISettings(1000000U, MSBFIRST, arduino::SPI_MODE0));
	zassert_equal(lastSpiError(), SpiError::invalid_frequency,
				  "SPI00 prescaler 범위 밖의 1 MHz 설정이 선제 거부되지 않았습니다.");
	zassert_false(spiTransactionActive(), "표현할 수 없는 SPI 설정이 transaction을 열었습니다.");
	SPI.transfer(nullptr, 1U);
	zassert_equal(lastSpiError(), SpiError::invalid_buffer, "null SPI buffer가 거부되지 않았습니다.");
}

ZTEST_SUITE(m7_spi, nullptr, spiSuiteSetup, spiBefore, nullptr, nullptr);

ZTEST(m7_adc, test_a0_fixed_12bit_raw_range_and_reference)
{
	static_assert(A0 == PIN_A0);
	static_assert(AR_INTERNAL == AR_DEFAULT);
	static_assert(nucode::arduino::internal::analog_read_resolution_bits == 12U);

	analogReference(AR_DEFAULT);
	zassert_equal(lastAnalogError(), AnalogError::none, "기본 ADC reference가 거부되었습니다.");
	const std::uint32_t raw_values[] = {0U, 2048U, 4095U};
	for (const std::uint32_t raw : raw_values)
	{
		zassert_ok(adc_emul_const_raw_value_set(test_adc, 5U, raw),
				   "ADC raw 값 주입에 실패했습니다.");
		zassert_equal(analogRead(A0), static_cast<int>(raw), "A0 12-bit raw 결과가 다릅니다.");
		zassert_equal(lastAnalogError(), AnalogError::none, "정상 A0 read 뒤 오류가 남았습니다.");
	}

	analogReference(static_cast<std::uint8_t>(AR_DEFAULT + 1U));
	zassert_equal(lastAnalogError(), AnalogError::unsupported_reference,
				  "미지원 ADC reference가 거부되지 않았습니다.");
	zassert_equal(analogRead(LED_BUILTIN), -1, "A0 이외 pin이 ADC 오류값을 반환하지 않았습니다.");
	zassert_equal(lastAnalogError(), AnalogError::invalid_pin, "잘못된 ADC pin 진단이 다릅니다.");
}

ZTEST(m7_adc, test_adc_driver_error_is_preserved)
{
	zassert_ok(adc_emul_raw_value_func_set(test_adc, 5U, failAdcRead, nullptr),
			   "ADC 오류 callback 주입에 실패했습니다.");
	zassert_equal(analogRead(A0), -1, "ADC driver 오류에서 실패값이 반환되지 않았습니다.");
	zassert_equal(lastAnalogError(), AnalogError::driver_error, "ADC driver 오류가 기록되지 않았습니다.");
	zassert_equal(lastAnalogDriverError(), -EIO, "원본 ADC driver 오류가 보존되지 않았습니다.");
}

ZTEST_SUITE(m7_adc, nullptr, nullptr, analogBefore, nullptr, nullptr);

ZTEST(m7_pwm, test_pwm_zero_middle_full_duty)
{
	static_assert(PIN_PWM_LED == PIN_PWM0);
	static_assert(nucode::arduino::internal::analog_write_resolution_bits == 8U);

	const int values[] = {0, 128, 255};
	for (const int value : values)
	{
		RESET_FAKE(fake_pwm_set_cycles);
		analogWrite(PIN_PWM0, value);
		zassert_equal(lastAnalogError(), AnalogError::none, "정상 PWM 값이 거부되었습니다.");
		zassert_equal(fake_pwm_set_cycles_fake.call_count, 1U, "PWM driver 호출 횟수가 다릅니다.");
		zassert_equal(fake_pwm_set_cycles_fake.arg1_val, 0U, "PWM channel이 다릅니다.");
		zassert_equal(fake_pwm_set_cycles_fake.arg2_val, 20000U, "PWM 20 ms period가 다릅니다.");
		const std::uint32_t expected_pulse = (value == 255)
												 ? 20000U
												 : static_cast<std::uint32_t>(((20000000ULL * value + 127ULL) / 255ULL) / 1000ULL);
		zassert_equal(fake_pwm_set_cycles_fake.arg3_val, expected_pulse,
					  "PWM duty cycle 변환이 다릅니다.");
	}
}

ZTEST(m7_pwm, test_pwm_validation_and_driver_error)
{
	analogWrite(PIN_A0, 127);
	zassert_equal(lastAnalogError(), AnalogError::invalid_pin, "잘못된 PWM pin이 거부되지 않았습니다.");
	zassert_equal(fake_pwm_set_cycles_fake.call_count, 0U, "잘못된 PWM pin이 driver에 전달되었습니다.");
	analogWrite(PIN_PWM0, -1);
	zassert_equal(lastAnalogError(), AnalogError::invalid_value, "음수 PWM 값이 거부되지 않았습니다.");
	analogWrite(PIN_PWM0, 256);
	zassert_equal(lastAnalogError(), AnalogError::invalid_value, "8-bit 초과 PWM 값이 거부되지 않았습니다.");

	fake_pwm_set_cycles_fake.return_val = -EIO;
	analogWrite(PIN_PWM0, 64);
	zassert_equal(lastAnalogError(), AnalogError::driver_error, "PWM driver 오류가 기록되지 않았습니다.");
	zassert_equal(lastAnalogDriverError(), -EIO, "원본 PWM driver 오류가 보존되지 않았습니다.");
}

ZTEST_SUITE(m7_pwm, nullptr, nullptr, analogBefore, nullptr, nullptr);
