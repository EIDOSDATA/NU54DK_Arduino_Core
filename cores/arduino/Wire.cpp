/**
 * @file Wire.cpp
 * @brief Zephyr I2C controller 위에 Arduino Wire API를 구현합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <Arduino.h>
#include <NUCODEPeripheral.h>

#include <zephyr/device.h>
#include <zephyr/devicetree.h>
#include <zephyr/drivers/i2c.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/atomic.h>

#include <cstddef>
#include <cstdint>
#include <errno.h>

#include "internal/WireBackend.h"
#include "internal/RuntimePeripheralRoute.h"
#include <peripheral_routes.h>

#if !DT_HAS_CHOSEN(nucode_arduino_wire)
#error "NUCODE_M7_WIRE_CHOSEN_REQUIRED: Wire에는 app overlay의 nucode,arduino-wire chosen I2C controller가 필요합니다."
#endif

#define NUCODE_ARDUINO_WIRE_NODE DT_CHOSEN(nucode_arduino_wire)

#if !DT_NODE_HAS_STATUS_OKAY(NUCODE_ARDUINO_WIRE_NODE)
#error "nucode,arduino-wire chosen I2C controller가 활성화되어 있지 않습니다."
#endif

namespace
{

	using nucode::arduino::internal::WireError;

	/** @brief Arduino Wire가 허용하는 가장 큰 7-bit 주소입니다. */
	constexpr std::uint8_t maximum_7bit_address = 0x7FU;

	/** @brief Arduino 표준 속도입니다. */
	constexpr std::uint32_t standard_clock_hz = 100000U;

	/** @brief Arduino fast-mode 속도입니다. */
	constexpr std::uint32_t fast_clock_hz = 400000U;

	/** @brief 보드 DTS가 선택한 Wire controller입니다. */
	const struct device *const wire_device = DEVICE_DT_GET(NUCODE_ARDUINO_WIRE_NODE);
	const nucode::arduino::internal::PeripheralRouteBinding wire_binding =
		nucode::arduino::internal::wireRouteBinding();
	nucode::arduino::internal::RuntimePeripheralRoute wire_route(
		wire_binding.device, wire_binding.pinctrl_config, wire_binding.owner,
		wire_binding.block_kind, wire_binding.block_index);
	bool wire_route_staged = false;

	/** @brief 보드 DTS가 선언한 초기 I2C 속도입니다. */
	constexpr std::uint32_t devicetree_clock_hz =
		DT_PROP_OR(NUCODE_ARDUINO_WIRE_NODE, clock_frequency, standard_clock_hz);

	K_MUTEX_DEFINE(wire_mutex);

	atomic_t last_wire_error = ATOMIC_INIT(static_cast<atomic_val_t>(WireError::none));
	atomic_t last_wire_driver_error = ATOMIC_INIT(0);
	atomic_t wire_pending_restart = ATOMIC_INIT(0);
	atomic_t wire_clock_hz = ATOMIC_INIT(static_cast<atomic_val_t>(devicetree_clock_hz));

	bool wire_started = false;
	bool transmission_active = false;
	bool tx_overflow = false;
	std::uint8_t tx_address = 0U;
	std::uint8_t tx_buffer[CONFIG_NUCODE_ARDUINO_WIRE_BUFFER_SIZE] = {};
	std::size_t tx_length = 0U;
	std::uint8_t rx_buffer[CONFIG_NUCODE_ARDUINO_WIRE_BUFFER_SIZE] = {};
	std::size_t rx_length = 0U;
	std::size_t rx_position = 0U;
	k_tid_t wire_transaction_owner = nullptr;

	/**
	 * @brief Wire 진단 상태를 원자적으로 기록합니다.
	 *
	 * @param error Core 내부 오류입니다.
	 * @param driver_error Zephyr I2C가 반환한 오류입니다.
	 */
	void recordWireError(WireError error, int driver_error = 0) noexcept
	{
		atomic_set(&last_wire_driver_error, static_cast<atomic_val_t>(driver_error));
		atomic_set(&last_wire_error, static_cast<atomic_val_t>(error));
	}

	/** @brief 성공한 Wire API 뒤 이전 오류를 제거합니다. */
	void recordWireSuccess() noexcept
	{
		recordWireError(WireError::none);
	}

	/** @brief RX cursor와 길이를 초기화합니다. */
	void clearReceiveBuffer() noexcept
	{
		rx_length = 0U;
		rx_position = 0U;
	}

	/** @brief 현재 TX 상태와 보류된 repeated-start 계약을 초기화합니다. */
	void clearTransmitState() noexcept
	{
		transmission_active = false;
		tx_overflow = false;
		tx_length = 0U;
		atomic_clear(&wire_pending_restart);
		wire_transaction_owner = nullptr;
	}

	/**
	 * @brief Arduino Wire의 7-bit 주소 범위를 확인합니다.
	 *
	 * @param address 검사할 controller target 주소입니다.
	 * @return 접근할 수 있으면 true입니다.
	 */
	[[nodiscard]] bool validateAddress(std::uint8_t address) noexcept
	{
		if (address > maximum_7bit_address)
		{
			recordWireError(WireError::invalid_address);
			return false;
		}
		return true;
	}

	/**
	 * @brief Arduino clock 값을 Zephyr controller 설정으로 변환합니다.
	 *
	 * @param clock_hz 요청한 SCL 속도입니다.
	 * @param configuration 변환 결과를 받을 주소입니다.
	 * @return v0.1이 지원하는 100 kHz 또는 400 kHz이면 true입니다.
	 */
	[[nodiscard]] bool wireConfiguration(std::uint32_t clock_hz,
										 std::uint32_t &configuration) noexcept
	{
		if (clock_hz == standard_clock_hz)
		{
			configuration = I2C_MODE_CONTROLLER | I2C_SPEED_SET(I2C_SPEED_STANDARD);
			return true;
		}
		if (clock_hz == fast_clock_hz)
		{
			configuration = I2C_MODE_CONTROLLER | I2C_SPEED_SET(I2C_SPEED_FAST);
			return true;
		}
		return false;
	}

	/**
	 * @brief Wire controller 속도를 안전한 두 값 중 하나로 설정합니다.
	 *
	 * @param clock_hz 요청한 SCL 속도입니다.
	 * @return 성공하면 true입니다.
	 */
	[[nodiscard]] bool configureWireClock(std::uint32_t clock_hz) noexcept
	{
		std::uint32_t configuration = 0U;
		if (!wireConfiguration(clock_hz, configuration))
		{
			recordWireError(WireError::unsupported_clock);
			return false;
		}

		const int result = i2c_configure(wire_device, configuration);
		if (result < 0)
		{
			recordWireError(WireError::driver_error, result);
			return false;
		}

		atomic_set(&wire_clock_hz, static_cast<atomic_val_t>(clock_hz));
		recordWireSuccess();
		return true;
	}

	/**
	 * @brief Zephyr I2C 오류를 Arduino endTransmission 상태로 변환합니다.
	 *
	 * @param driver_error Zephyr I2C 오류 번호입니다.
	 * @return Arduino Wire 상태 번호입니다.
	 */
	[[nodiscard]] std::uint8_t transmissionStatus(int driver_error) noexcept
	{
		if (driver_error == -ETIMEDOUT)
		{
			return 5U;
		}
		return 4U;
	}

	/** @brief ArduinoCore-API HardwareI2C의 NU54DK controller 구현입니다. */
	class ZephyrWire final : public nucode::arduino::Nu54TwoWire
	{
	public:
		/** @brief 종료 상태에서 다음 begin()의 TWIM22 SDA/SCL route를 선택합니다. */
		bool setPins(pin_size_t sda_pin, pin_size_t scl_pin) noexcept override
		{
			if (k_is_in_isr())
			{
				recordWireError(WireError::invalid_context);
				return false;
			}
			static_cast<void>(k_mutex_lock(&wire_mutex, K_FOREVER));
			if (wire_started)
			{
				recordWireError(WireError::route_busy);
				static_cast<void>(k_mutex_unlock(&wire_mutex));
				return false;
			}
			const pin_size_t pins[]{sda_pin, scl_pin};
			const nucode::arduino::internal::PeripheralSignal signals[]{
				nucode::arduino::internal::PeripheralSignal::i2c_sda,
				nucode::arduino::internal::PeripheralSignal::i2c_scl,
			};
			nucode::arduino::internal::PeripheralRouteConfiguration configuration{};
			const auto result = nucode::arduino::internal::buildPeripheralRoute(
				nucode::arduino::internal::PinRoute::i2c22, pins, signals, 2U,
				configuration);
			const bool staged =
				(result == nucode::arduino::internal::PeripheralRouteBuildError::none) &&
				wire_route.stage(configuration);
			if (staged)
			{
				wire_route_staged = true;
			}
			recordWireError(staged ? WireError::none : WireError::invalid_pin_route,
							staged ? 0 : static_cast<int>(result));
			static_cast<void>(k_mutex_unlock(&wire_mutex));
			return staged;
		}

		/** @brief controller와 종료 상태 pin remap capability를 반환합니다. */
		nucode::arduino::PeripheralCapability capabilities() const noexcept override
		{
			return nucode::arduino::PeripheralCapability::controller |
				   nucode::arduino::PeripheralCapability::pin_remap;
		}

		/** @brief DTS 속도로 controller lifecycle을 시작합니다. */
		void begin() override
		{
			if (k_is_in_isr())
			{
				recordWireError(WireError::invalid_context);
				return;
			}

			static_cast<void>(k_mutex_lock(&wire_mutex, K_FOREVER));
			if (!wire_binding.available)
			{
				recordWireError(WireError::route_error);
				static_cast<void>(k_mutex_unlock(&wire_mutex));
				return;
			}
			if (!wire_started && !wire_route_staged)
			{
				nucode::arduino::internal::PeripheralRouteConfiguration route{};
				wire_route_staged =
					nucode::arduino::internal::defaultWireRoute(route) ==
						nucode::arduino::internal::PeripheralRouteBuildError::none &&
					wire_route.stage(route);
			}
			if (!wire_started && (!wire_route_staged || !wire_route.activate()))
			{
				recordWireError(WireError::route_error, wire_route.lastDriverError());
				static_cast<void>(k_mutex_unlock(&wire_mutex));
				return;
			}
			if (!device_is_ready(wire_device))
			{
				recordWireError(WireError::device_not_ready);
				if (!wire_started)
				{
					static_cast<void>(wire_route.deactivate());
				}
				static_cast<void>(k_mutex_unlock(&wire_mutex));
				return;
			}

			if (!wire_started)
			{
				clearTransmitState();
				clearReceiveBuffer();
				wire_started = configureWireClock(devicetree_clock_hz);
				if (!wire_started)
				{
					static_cast<void>(wire_route.deactivate());
				}
			}
			else
			{
				recordWireSuccess();
			}
			static_cast<void>(k_mutex_unlock(&wire_mutex));
		}

		/**
		 * @brief peripheral 주소 방식은 v0.1에서 지원하지 않습니다.
		 *
		 * @param address 사용하지 않는 local 주소입니다.
		 */
		void begin(std::uint8_t address) override
		{
			ARG_UNUSED(address);
			recordWireError(k_is_in_isr() ? WireError::invalid_context
										  : WireError::unsupported_peripheral_mode);
		}

		/** @brief Core 상태만 닫고 Zephyr가 소유한 I2C 장치는 유지합니다. */
		void end() override
		{
			if (k_is_in_isr())
			{
				recordWireError(WireError::invalid_context);
				return;
			}

			static_cast<void>(k_mutex_lock(&wire_mutex, K_FOREVER));
			if ((transmission_active || (atomic_get(&wire_pending_restart) != 0)) &&
				(wire_transaction_owner != k_current_get()))
			{
				recordWireError(WireError::transaction_owner_mismatch);
				static_cast<void>(k_mutex_unlock(&wire_mutex));
				return;
			}
			const bool discarded_restart = atomic_get(&wire_pending_restart) != 0;
			clearTransmitState();
			clearReceiveBuffer();
			const bool was_started = wire_started;
			const bool route_present =
				was_started || wire_route.active() || wire_route.faulted();
			const bool route_ok = !route_present || wire_route.deactivate();
			/** @brief 복구 가능한 route 해제 실패는 end() 재시도를 위해 active 상태를 보존합니다. */
			wire_started = !route_ok && wire_route.active();
			if (!route_ok)
			{
				recordWireError(WireError::route_error, wire_route.lastDriverError());
			}
			else
			{
				recordWireError(discarded_restart ? WireError::pending_restart_conflict
												  : WireError::none);
			}
			static_cast<void>(k_mutex_unlock(&wire_mutex));
		}

		/** @brief controller를 100 kHz 또는 400 kHz로 설정합니다. */
		void setClock(std::uint32_t frequency) override
		{
			if (k_is_in_isr())
			{
				recordWireError(WireError::invalid_context);
				return;
			}

			static_cast<void>(k_mutex_lock(&wire_mutex, K_FOREVER));
			if (!wire_started)
			{
				recordWireError(WireError::not_started);
			}
			else if (transmission_active || (atomic_get(&wire_pending_restart) != 0))
			{
				if (wire_transaction_owner != k_current_get())
				{
					recordWireError(WireError::transaction_owner_mismatch);
				}
				else
				{
					clearTransmitState();
					recordWireError(WireError::pending_restart_conflict);
				}
			}
			else
			{
				static_cast<void>(configureWireClock(frequency));
			}
			static_cast<void>(k_mutex_unlock(&wire_mutex));
		}

		/** @brief 한 target에 보낼 고정 TX buffer를 엽니다. */
		void beginTransmission(std::uint8_t address) override
		{
			if (k_is_in_isr())
			{
				recordWireError(WireError::invalid_context);
				return;
			}

			static_cast<void>(k_mutex_lock(&wire_mutex, K_FOREVER));
			if (!wire_started)
			{
				recordWireError(WireError::not_started);
			}
			else if (transmission_active || (atomic_get(&wire_pending_restart) != 0))
			{
				if (wire_transaction_owner != k_current_get())
				{
					recordWireError(WireError::transaction_owner_mismatch);
				}
				else
				{
					clearTransmitState();
					recordWireError(WireError::pending_restart_conflict);
				}
			}
			else if (validateAddress(address))
			{
				transmission_active = true;
				wire_transaction_owner = k_current_get();
				tx_overflow = false;
				tx_address = address;
				tx_length = 0U;
				recordWireSuccess();
			}
			static_cast<void>(k_mutex_unlock(&wire_mutex));
		}

		/** @brief STOP을 포함해 현재 TX를 완료합니다. */
		std::uint8_t endTransmission() override
		{
			return endTransmission(true);
		}

		/**
		 * @brief TX를 전송하거나 다음 repeated-start read까지 보류합니다.
		 *
		 * @param stop_bit true이면 즉시 STOP write, false이면 같은 주소의 다음
		 * requestFrom까지 write를 보류합니다.
		 * @return Arduino Wire 상태 번호입니다.
		 */
		std::uint8_t endTransmission(bool stop_bit) override
		{
			if (k_is_in_isr())
			{
				recordWireError(WireError::invalid_context);
				return 4U;
			}

			static_cast<void>(k_mutex_lock(&wire_mutex, K_FOREVER));
			if (!wire_started)
			{
				recordWireError(WireError::not_started);
				static_cast<void>(k_mutex_unlock(&wire_mutex));
				return 4U;
			}
			if (!transmission_active)
			{
				recordWireError(WireError::transmission_not_active);
				static_cast<void>(k_mutex_unlock(&wire_mutex));
				return 4U;
			}
			if (wire_transaction_owner != k_current_get())
			{
				recordWireError(WireError::transaction_owner_mismatch);
				static_cast<void>(k_mutex_unlock(&wire_mutex));
				return 4U;
			}

			transmission_active = false;
			if (tx_overflow)
			{
				clearTransmitState();
				recordWireError(WireError::tx_buffer_overflow);
				static_cast<void>(k_mutex_unlock(&wire_mutex));
				return 1U;
			}
			if (!stop_bit)
			{
				atomic_set(&wire_pending_restart, 1);
				recordWireSuccess();
				static_cast<void>(k_mutex_unlock(&wire_mutex));
				return 0U;
			}

			const int result = i2c_write(wire_device, tx_buffer, tx_length, tx_address);
			clearTransmitState();
			if (result < 0)
			{
				recordWireError(WireError::driver_error, result);
				static_cast<void>(k_mutex_unlock(&wire_mutex));
				return transmissionStatus(result);
			}

			recordWireSuccess();
			static_cast<void>(k_mutex_unlock(&wire_mutex));
			return 0U;
		}

		/** @brief STOP read를 요청합니다. */
		std::size_t requestFrom(std::uint8_t address, std::size_t length) override
		{
			return requestFrom(address, length, true);
		}

		/**
		 * @brief target에서 고정 RX buffer로 읽습니다.
		 *
		 * 보류된 같은 주소의 write가 있으면 i2c_write_read 한 호출로 결합합니다.
		 *
		 * @param address 읽을 7-bit 주소입니다.
		 * @param length 읽을 byte 수입니다.
		 * @param stop_bit v0.1에서는 true만 지원합니다.
		 * @return 성공적으로 읽은 byte 수입니다.
		 */
		std::size_t requestFrom(std::uint8_t address, std::size_t length,
								bool stop_bit) override
		{
			if (k_is_in_isr())
			{
				recordWireError(WireError::invalid_context);
				return 0U;
			}

			static_cast<void>(k_mutex_lock(&wire_mutex, K_FOREVER));
			clearReceiveBuffer();
			if (!wire_started)
			{
				recordWireError(WireError::not_started);
				static_cast<void>(k_mutex_unlock(&wire_mutex));
				return 0U;
			}
			const bool has_transmit_state =
				transmission_active || (atomic_get(&wire_pending_restart) != 0);
			if (has_transmit_state && (wire_transaction_owner != k_current_get()))
			{
				recordWireError(WireError::transaction_owner_mismatch);
				static_cast<void>(k_mutex_unlock(&wire_mutex));
				return 0U;
			}
			if (!stop_bit)
			{
				clearTransmitState();
				recordWireError(WireError::unsupported_no_stop_read);
				static_cast<void>(k_mutex_unlock(&wire_mutex));
				return 0U;
			}
			if (length == 0U)
			{
				if (has_transmit_state)
				{
					clearTransmitState();
					recordWireError(WireError::pending_restart_conflict);
				}
				else
				{
					recordWireSuccess();
				}
				static_cast<void>(k_mutex_unlock(&wire_mutex));
				return 0U;
			}
			if (length > sizeof(rx_buffer))
			{
				clearTransmitState();
				recordWireError(WireError::rx_buffer_overflow);
				static_cast<void>(k_mutex_unlock(&wire_mutex));
				return 0U;
			}
			if (!validateAddress(address))
			{
				clearTransmitState();
				static_cast<void>(k_mutex_unlock(&wire_mutex));
				return 0U;
			}
			if (transmission_active)
			{
				clearTransmitState();
				recordWireError(WireError::pending_restart_conflict);
				static_cast<void>(k_mutex_unlock(&wire_mutex));
				return 0U;
			}

			int result = 0;
			if (atomic_get(&wire_pending_restart) != 0)
			{
				if (address != tx_address)
				{
					clearTransmitState();
					recordWireError(WireError::pending_restart_address_mismatch);
					static_cast<void>(k_mutex_unlock(&wire_mutex));
					return 0U;
				}

				result = i2c_write_read(wire_device, address, tx_buffer, tx_length,
										rx_buffer, length);
				clearTransmitState();
			}
			else
			{
				result = i2c_read(wire_device, rx_buffer, length, address);
			}

			if (result < 0)
			{
				recordWireError(WireError::driver_error, result);
				static_cast<void>(k_mutex_unlock(&wire_mutex));
				return 0U;
			}

			rx_length = length;
			recordWireSuccess();
			static_cast<void>(k_mutex_unlock(&wire_mutex));
			return length;
		}

		/** @brief 다음 TX buffer에 한 byte를 추가합니다. */
		std::size_t write(std::uint8_t value) override
		{
			if (k_is_in_isr())
			{
				setWriteError();
				recordWireError(WireError::invalid_context);
				return 0U;
			}

			static_cast<void>(k_mutex_lock(&wire_mutex, K_FOREVER));
			if (!wire_started)
			{
				setWriteError();
				recordWireError(WireError::not_started);
				static_cast<void>(k_mutex_unlock(&wire_mutex));
				return 0U;
			}
			if (!transmission_active)
			{
				setWriteError();
				recordWireError(WireError::transmission_not_active);
				static_cast<void>(k_mutex_unlock(&wire_mutex));
				return 0U;
			}
			if (wire_transaction_owner != k_current_get())
			{
				setWriteError();
				recordWireError(WireError::transaction_owner_mismatch);
				static_cast<void>(k_mutex_unlock(&wire_mutex));
				return 0U;
			}
			if (tx_length >= sizeof(tx_buffer))
			{
				tx_overflow = true;
				setWriteError();
				recordWireError(WireError::tx_buffer_overflow);
				static_cast<void>(k_mutex_unlock(&wire_mutex));
				return 0U;
			}

			tx_buffer[tx_length++] = value;
			recordWireSuccess();
			static_cast<void>(k_mutex_unlock(&wire_mutex));
			return 1U;
		}

		/** @brief TX buffer에 남은 byte 수를 반환합니다. */
		int availableForWrite() override
		{
			if (k_is_in_isr())
			{
				recordWireError(WireError::invalid_context);
				return 0;
			}
			static_cast<void>(k_mutex_lock(&wire_mutex, K_FOREVER));
			int result = 0;
			if (!wire_started)
			{
				recordWireError(WireError::not_started);
			}
			else if (atomic_get(&wire_pending_restart) != 0)
			{
				recordWireError((wire_transaction_owner == k_current_get())
									? WireError::pending_restart_conflict
									: WireError::transaction_owner_mismatch);
			}
			else if (!transmission_active)
			{
				recordWireError(WireError::transmission_not_active);
			}
			else if (wire_transaction_owner != k_current_get())
			{
				recordWireError(WireError::transaction_owner_mismatch);
			}
			else
			{
				result = static_cast<int>(sizeof(tx_buffer) - tx_length);
				recordWireSuccess();
			}
			static_cast<void>(k_mutex_unlock(&wire_mutex));
			return result;
		}

		/** @brief RX buffer에서 읽을 수 있는 byte 수를 반환합니다. */
		int available() override
		{
			if (k_is_in_isr())
			{
				recordWireError(WireError::invalid_context);
				return 0;
			}
			static_cast<void>(k_mutex_lock(&wire_mutex, K_FOREVER));
			const int count = wire_started
								  ? static_cast<int>(rx_length - rx_position)
								  : 0;
			recordWireError(wire_started ? WireError::none : WireError::not_started);
			static_cast<void>(k_mutex_unlock(&wire_mutex));
			return count;
		}

		/** @brief 다음 RX byte를 소비하지 않고 반환합니다. */
		int peek() override
		{
			if (k_is_in_isr())
			{
				recordWireError(WireError::invalid_context);
				return -1;
			}
			static_cast<void>(k_mutex_lock(&wire_mutex, K_FOREVER));
			if (!wire_started)
			{
				recordWireError(WireError::not_started);
				static_cast<void>(k_mutex_unlock(&wire_mutex));
				return -1;
			}
			const int value = (rx_position < rx_length) ? rx_buffer[rx_position] : -1;
			recordWireSuccess();
			static_cast<void>(k_mutex_unlock(&wire_mutex));
			return value;
		}

		/** @brief 다음 RX byte를 소비하여 반환합니다. */
		int read() override
		{
			if (k_is_in_isr())
			{
				recordWireError(WireError::invalid_context);
				return -1;
			}
			static_cast<void>(k_mutex_lock(&wire_mutex, K_FOREVER));
			if (!wire_started)
			{
				recordWireError(WireError::not_started);
				static_cast<void>(k_mutex_unlock(&wire_mutex));
				return -1;
			}
			const int value = (rx_position < rx_length) ? rx_buffer[rx_position++] : -1;
			recordWireSuccess();
			static_cast<void>(k_mutex_unlock(&wire_mutex));
			return value;
		}

		/** @brief 동기 전송 특성상 no-op이며 보류 write는 안전하게 취소합니다. */
		void flush() override
		{
			if (k_is_in_isr())
			{
				recordWireError(WireError::invalid_context);
				return;
			}

			static_cast<void>(k_mutex_lock(&wire_mutex, K_FOREVER));
			if (!wire_started)
			{
				recordWireError(WireError::not_started);
			}
			else if (transmission_active || (atomic_get(&wire_pending_restart) != 0))
			{
				if (wire_transaction_owner != k_current_get())
				{
					recordWireError(WireError::transaction_owner_mismatch);
				}
				else
				{
					clearTransmitState();
					recordWireError(WireError::pending_restart_conflict);
				}
			}
			else
			{
				recordWireSuccess();
			}
			static_cast<void>(k_mutex_unlock(&wire_mutex));
		}

		/** @brief peripheral 수신 callback은 지원하지 않습니다. */
		void onReceive(void (*callback)(int)) override
		{
			ARG_UNUSED(callback);
			recordWireError(k_is_in_isr() ? WireError::invalid_context
										  : WireError::unsupported_peripheral_mode);
		}

		/** @brief peripheral 요청 callback은 지원하지 않습니다. */
		void onRequest(void (*callback)(void)) override
		{
			ARG_UNUSED(callback);
			recordWireError(k_is_in_isr() ? WireError::invalid_context
										  : WireError::unsupported_peripheral_mode);
		}
	};

	ZephyrWire wire_backend;

}

TwoWire &Wire = wire_backend;

namespace nucode::arduino::internal
{

	WireError lastWireError() noexcept
	{
		return static_cast<WireError>(atomic_get(&last_wire_error));
	}

	int lastWireDriverError() noexcept
	{
		return static_cast<int>(atomic_get(&last_wire_driver_error));
	}

	bool wireHasPendingRestart() noexcept
	{
		return atomic_get(&wire_pending_restart) != 0;
	}

	std::uint32_t wireClockFrequency() noexcept
	{
		return static_cast<std::uint32_t>(atomic_get(&wire_clock_hz));
	}

	void clearWireDiagnostics() noexcept
	{
		recordWireSuccess();
	}

}

#undef NUCODE_ARDUINO_WIRE_NODE
