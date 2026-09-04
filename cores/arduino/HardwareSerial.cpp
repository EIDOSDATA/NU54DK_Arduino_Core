/**
 * @file HardwareSerial.cpp
 * @brief Zephyr console Serial과 독립 uart30 Serial1을 구현합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <Arduino.h>
#include <NUCODEPeripheral.h>

#if defined(CONFIG_NUCODE_ARDUINO_SERIAL1)
#include "internal/RuntimePeripheralRoute.h"
#endif
#include "internal/SerialBackend.h"
#if defined(CONFIG_NUCODE_ARDUINO_SERIAL1)
#include <peripheral_routes.h>
#endif

#include <zephyr/device.h>
#include <zephyr/devicetree.h>
#include <zephyr/drivers/uart.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/atomic.h>

#include <cstddef>
#include <cstdint>
#include <errno.h>

#if DT_HAS_CHOSEN(nucode_arduino_serial)
#define NUCODE_ARDUINO_SERIAL_NODE DT_CHOSEN(nucode_arduino_serial)
#elif DT_HAS_CHOSEN(zephyr_console)
#define NUCODE_ARDUINO_SERIAL_NODE DT_CHOSEN(zephyr_console)
#else
#error "기본 Serial에는 nucode,arduino-serial 또는 zephyr,console chosen이 필요합니다."
#endif

#if !DT_NODE_HAS_STATUS_OKAY(NUCODE_ARDUINO_SERIAL_NODE)
#error "기본 Serial chosen UART가 활성화되어 있지 않습니다."
#endif

namespace
{
	using nucode::arduino::PeripheralCapability;
#if defined(CONFIG_NUCODE_ARDUINO_SERIAL1)
	using nucode::arduino::internal::PeripheralRouteBuildError;
	using nucode::arduino::internal::PeripheralRouteConfiguration;
	using nucode::arduino::internal::PeripheralSignal;
	using nucode::arduino::internal::RuntimePeripheralRoute;
#endif
	using nucode::arduino::internal::SerialError;

	constexpr unsigned long console_baud =
		DT_PROP(NUCODE_ARDUINO_SERIAL_NODE, current_speed);
	constexpr std::uint32_t serial_frame_bits = 10U;
	/** @brief 기본 Serial의 마지막 8N1 frame이 선로를 떠날 때까지 기다릴 여유입니다. */
	constexpr std::uint32_t serial_flush_guard_us = static_cast<std::uint32_t>(
		((2ULL * serial_frame_bits * 1000000ULL) + console_baud - 1ULL) / console_baud);

	K_MSGQ_DEFINE(console_rx_queue, sizeof(std::uint8_t),
				  CONFIG_NUCODE_ARDUINO_SERIAL_RX_BUFFER_SIZE, alignof(std::uint8_t));
#if defined(CONFIG_NUCODE_ARDUINO_SERIAL1)
	K_MSGQ_DEFINE(serial1_rx_queue, sizeof(std::uint8_t),
				  CONFIG_NUCODE_ARDUINO_SERIAL_RX_BUFFER_SIZE, alignof(std::uint8_t));
#endif
	K_MUTEX_DEFINE(console_lifecycle_mutex);
	K_MUTEX_DEFINE(serial_tx_mutex);
#if defined(CONFIG_NUCODE_ARDUINO_SERIAL1)
	K_MUTEX_DEFINE(serial1_lifecycle_mutex);
	K_MUTEX_DEFINE(serial1_tx_mutex);
#endif

	struct SerialDiagnostics
	{
		atomic_t started{ATOMIC_INIT(0)};
		atomic_t error{ATOMIC_INIT(static_cast<atomic_val_t>(SerialError::none))};
		atomic_t driver_error{ATOMIC_INIT(0)};
		atomic_t dropped{ATOMIC_INIT(0)};
	};

	SerialDiagnostics console_diagnostics;
#if defined(CONFIG_NUCODE_ARDUINO_SERIAL1)
	SerialDiagnostics serial1_diagnostics;
#endif

	/** @brief Serial backend 하나의 고정 상태입니다. */
	struct SerialPortState
	{
		const struct device *device{nullptr};
		struct k_msgq *rx_queue{nullptr};
		struct k_mutex *lifecycle_mutex{nullptr};
		struct k_mutex *tx_mutex{nullptr};
		SerialDiagnostics *diagnostics{nullptr};
		unsigned long baud{0UL};
		std::uint16_t config{0U};
	};

	const struct device *const console_device = DEVICE_DT_GET(NUCODE_ARDUINO_SERIAL_NODE);
	SerialPortState console_state{console_device, &console_rx_queue,
								  &console_lifecycle_mutex, &serial_tx_mutex, &console_diagnostics,
								  console_baud, static_cast<std::uint16_t>(SERIAL_8N1)};

#if defined(CONFIG_NUCODE_ARDUINO_SERIAL1)
	const nucode::arduino::internal::PeripheralRouteBinding serial1_binding =
		nucode::arduino::internal::serial1RouteBinding();
	RuntimePeripheralRoute serial1_route(serial1_binding.device,
										 serial1_binding.pinctrl_config, serial1_binding.owner,
										 serial1_binding.block_kind, serial1_binding.block_index);
	SerialPortState serial1_state{serial1_binding.device, &serial1_rx_queue,
								  &serial1_lifecycle_mutex, &serial1_tx_mutex, &serial1_diagnostics};
	bool serial1_route_staged = false;
#endif

	/** @brief backend 진단을 기록합니다. */
	void record(SerialPortState &state, SerialError error, int driver_error = 0) noexcept
	{
		atomic_set(&state.diagnostics->driver_error,
				   static_cast<atomic_val_t>(driver_error));
		atomic_set(&state.diagnostics->error, static_cast<atomic_val_t>(error));
	}

	/** @brief UART IRQ 수신 byte를 instance별 queue로 옮깁니다. */
	void serialIrqHandler(const struct device *device, void *user_data)
	{
		auto *const state = static_cast<SerialPortState *>(user_data);
		if ((state == nullptr) || (atomic_get(&state->diagnostics->started) == 0) ||
			(uart_irq_update(device) == 0))
		{
			return;
		}
		while (uart_irq_rx_ready(device) != 0)
		{
			std::uint8_t bytes[16]{};
			const int received = uart_fifo_read(device, bytes, sizeof(bytes));
			if (received <= 0)
			{
				break;
			}
			for (int index = 0; index < received; ++index)
			{
				if (k_msgq_put(state->rx_queue, &bytes[index], K_NO_WAIT) != 0)
				{
					atomic_inc(&state->diagnostics->dropped);
					record(*state, SerialError::rx_overflow);
				}
			}
		}
	}

	/** @brief Arduino UART config를 Zephyr 설정으로 변환합니다. */
	[[nodiscard]] bool buildConfig(unsigned long baud, std::uint16_t request,
								   struct uart_config &configuration) noexcept
	{
		if (baud == 0UL)
		{
			return false;
		}
		configuration = {};
		configuration.baudrate = static_cast<std::uint32_t>(baud);
		configuration.flow_ctrl = UART_CFG_FLOW_CTRL_NONE;
		switch (request & SERIAL_PARITY_MASK)
		{
		case SERIAL_PARITY_NONE:
			configuration.parity = UART_CFG_PARITY_NONE;
			break;
		case SERIAL_PARITY_EVEN:
			configuration.parity = UART_CFG_PARITY_EVEN;
			break;
		case SERIAL_PARITY_ODD:
			configuration.parity = UART_CFG_PARITY_ODD;
			break;
		default:
			return false;
		}
		switch (request & SERIAL_STOP_BIT_MASK)
		{
		case SERIAL_STOP_BIT_1:
			configuration.stop_bits = UART_CFG_STOP_BITS_1;
			break;
		case SERIAL_STOP_BIT_2:
			configuration.stop_bits = UART_CFG_STOP_BITS_2;
			break;
		default:
			return false;
		}
		switch (request & SERIAL_DATA_MASK)
		{
		case SERIAL_DATA_5:
			configuration.data_bits = UART_CFG_DATA_BITS_5;
			break;
		case SERIAL_DATA_6:
			configuration.data_bits = UART_CFG_DATA_BITS_6;
			break;
		case SERIAL_DATA_7:
			configuration.data_bits = UART_CFG_DATA_BITS_7;
			break;
		case SERIAL_DATA_8:
			configuration.data_bits = UART_CFG_DATA_BITS_8;
			break;
		default:
			return false;
		}
		return true;
	}

	/** @brief Zephyr 설정 두 개가 동일한지 비교합니다. */
	[[nodiscard]] bool sameConfig(const struct uart_config &lhs,
								  const struct uart_config &rhs) noexcept
	{
		return (lhs.baudrate == rhs.baudrate) && (lhs.parity == rhs.parity) &&
			   (lhs.stop_bits == rhs.stop_bits) && (lhs.data_bits == rhs.data_bits) &&
			   (lhs.flow_ctrl == rhs.flow_ctrl);
	}

	/** @brief RX IRQ와 queue를 시작합니다. 호출자는 lifecycle mutex를 보유합니다. */
	[[nodiscard]] bool startRx(SerialPortState &state) noexcept
	{
		k_msgq_purge(state.rx_queue);
		const int result = uart_irq_callback_user_data_set(
			state.device, serialIrqHandler, &state);
		if (result < 0)
		{
			record(state, SerialError::driver_error, result);
			return false;
		}
		atomic_set(&state.diagnostics->started, 1);
		uart_irq_rx_enable(state.device);
		record(state, SerialError::none);
		return true;
	}

	/** @brief RX IRQ와 queue를 종료합니다. 호출자는 lifecycle mutex를 보유합니다. */
	[[nodiscard]] bool stopRx(SerialPortState &state) noexcept
	{
		uart_irq_rx_disable(state.device);
		const int result = uart_irq_callback_user_data_set(state.device, nullptr, nullptr);
		if (result < 0)
		{
			/** @brief callback 해제 실패 시 active RX 상태를 보존해 end() 재시도를 허용합니다. */
			uart_irq_rx_enable(state.device);
			record(state, SerialError::driver_error, result);
			return false;
		}
		atomic_clear(&state.diagnostics->started);
		k_msgq_purge(state.rx_queue);
		return true;
	}

	/** @brief 공통 RX available 구현입니다. */
	int available(SerialPortState &state) noexcept
	{
		if (k_is_in_isr())
		{
			record(state, SerialError::invalid_context);
			return 0;
		}
		if (atomic_get(&state.diagnostics->started) == 0)
		{
			record(state, SerialError::not_started);
			return 0;
		}
		record(state, SerialError::none);
		return static_cast<int>(k_msgq_num_used_get(state.rx_queue));
	}

	/** @brief 공통 RX peek/read 구현입니다. */
	int readByte(SerialPortState &state, bool consume) noexcept
	{
		if (k_is_in_isr())
		{
			record(state, SerialError::invalid_context);
			return -1;
		}
		if (atomic_get(&state.diagnostics->started) == 0)
		{
			record(state, SerialError::not_started);
			return -1;
		}
		std::uint8_t value = 0U;
		const int result = consume ? k_msgq_get(state.rx_queue, &value, K_NO_WAIT)
								   : k_msgq_peek(state.rx_queue, &value);
		record(state, SerialError::none);
		return (result == 0) ? static_cast<int>(value) : -1;
	}

#if defined(CONFIG_NUCODE_ARDUINO_SERIAL1)
	/** @brief Serial1의 마지막 frame 전송 완료를 기다리는 flush 구현입니다. */
	void flush(SerialPortState &state) noexcept
	{
		if (k_is_in_isr())
		{
			record(state, SerialError::invalid_context);
			return;
		}
		if (atomic_get(&state.diagnostics->started) == 0)
		{
			record(state, SerialError::not_started);
			return;
		}
		const unsigned long baud = (state.baud == 0UL) ? 1UL : state.baud;
		const std::uint32_t guard = static_cast<std::uint32_t>(
			((2ULL * serial_frame_bits * 1000000ULL) + baud - 1ULL) / baud);
		static_cast<void>(k_mutex_lock(state.tx_mutex, K_FOREVER));
		k_busy_wait(guard);
		static_cast<void>(k_mutex_unlock(state.tx_mutex));
		record(state, SerialError::none);
	}
#endif

	/** @brief 공통 polling TX 구현입니다. */
	std::size_t writeByte(SerialPortState &state, std::uint8_t value) noexcept
	{
		if (k_is_in_isr())
		{
			record(state, SerialError::invalid_context);
			return 0U;
		}
		if (atomic_get(&state.diagnostics->started) == 0)
		{
			record(state, SerialError::not_started);
			return 0U;
		}
		static_cast<void>(k_mutex_lock(state.tx_mutex, K_FOREVER));
		uart_poll_out(state.device, value);
		static_cast<void>(k_mutex_unlock(state.tx_mutex));
		record(state, SerialError::none);
		return 1U;
	}

	/** @brief Zephyr 소유 console를 차용하는 고정 Serial입니다. */
	class ConsoleSerial final : public arduino::HardwareSerial
	{
	public:
		void begin(unsigned long baud) override { begin(baud, SERIAL_8N1); }
		void begin(unsigned long baud, std::uint16_t config) override
		{
			if (k_is_in_isr())
			{
				record(console_state, SerialError::invalid_context);
				return;
			}
			struct uart_config requested{};
			if ((baud != console_baud) || (config != SERIAL_8N1) ||
				!buildConfig(baud, config, requested))
			{
				record(console_state, SerialError::unsupported_config);
				return;
			}
			if (!device_is_ready(console_state.device))
			{
				record(console_state, SerialError::device_not_ready);
				return;
			}
			struct uart_config actual{};
			const int get_result = uart_config_get(console_state.device, &actual);
			if ((get_result < 0) || !sameConfig(actual, requested))
			{
				record(console_state, (get_result < 0) ? SerialError::driver_error : SerialError::unsupported_config, get_result);
				return;
			}
			static_cast<void>(k_mutex_lock(console_state.lifecycle_mutex, K_FOREVER));
			if (atomic_get(&console_state.diagnostics->started) == 0)
			{
				static_cast<void>(startRx(console_state));
			}
			else
			{
				record(console_state, SerialError::none);
			}
			static_cast<void>(k_mutex_unlock(console_state.lifecycle_mutex));
		}
		void end() override
		{
			if (k_is_in_isr())
			{
				record(console_state, SerialError::invalid_context);
				return;
			}
			static_cast<void>(k_mutex_lock(console_state.lifecycle_mutex, K_FOREVER));
			if (atomic_get(&console_state.diagnostics->started) != 0)
			{
				static_cast<void>(stopRx(console_state));
			}
			else
			{
				record(console_state, SerialError::none);
			}
			static_cast<void>(k_mutex_unlock(console_state.lifecycle_mutex));
		}
		int available() override { return ::available(console_state); }
		int peek() override { return readByte(console_state, false); }
		int read() override { return readByte(console_state, true); }
		void flush() override
		{
			if (k_is_in_isr())
			{
				record(console_state, SerialError::invalid_context);
				return;
			}
			if (atomic_get(&console_state.diagnostics->started) == 0)
			{
				record(console_state, SerialError::not_started);
				return;
			}
			static_cast<void>(k_mutex_lock(&serial_tx_mutex, K_FOREVER));
			k_busy_wait(serial_flush_guard_us);
			static_cast<void>(k_mutex_unlock(&serial_tx_mutex));
			record(console_state, SerialError::none);
		}
		std::size_t write(std::uint8_t value) override
		{
			const std::size_t result = writeByte(console_state, value);
			if (result == 0U)
			{
				setWriteError();
			}
			return result;
		}
		int availableForWrite() override
		{
			return (!k_is_in_isr() && atomic_get(&console_state.diagnostics->started)) ? 1 : 0;
		}
		operator bool() override
		{
			return atomic_get(&console_state.diagnostics->started) && device_is_ready(console_state.device);
		}
	};

#if defined(CONFIG_NUCODE_ARDUINO_SERIAL1)
	/** @brief uart30 runtime PM과 핀 handover를 소유하는 독립 Serial1입니다. */
	class Uart30Serial final : public nucode::arduino::Nu54HardwareSerial
	{
	public:
		bool setPins(pin_size_t rx_pin, pin_size_t tx_pin) noexcept override
		{
			if (k_is_in_isr())
			{
				record(serial1_state, SerialError::invalid_context);
				return false;
			}
			static_cast<void>(k_mutex_lock(serial1_state.lifecycle_mutex, K_FOREVER));
			if (atomic_get(&serial1_state.diagnostics->started) != 0)
			{
				record(serial1_state, SerialError::route_busy);
				static_cast<void>(k_mutex_unlock(serial1_state.lifecycle_mutex));
				return false;
			}
			const pin_size_t pins[]{rx_pin, tx_pin};
			const PeripheralSignal signals[]{PeripheralSignal::uart_rx,
											 PeripheralSignal::uart_tx};
			PeripheralRouteConfiguration configuration{};
			const PeripheralRouteBuildError result =
				nucode::arduino::internal::buildPeripheralRoute(
					nucode::arduino::internal::PinRoute::uart30, pins, signals, 2U,
					configuration);
			const bool staged = (result == PeripheralRouteBuildError::none) &&
								serial1_route.stage(configuration);
			if (staged)
			{
				serial1_route_staged = true;
			}
			record(serial1_state, staged ? SerialError::none : SerialError::invalid_pin_route,
				   staged ? 0 : static_cast<int>(result));
			static_cast<void>(k_mutex_unlock(serial1_state.lifecycle_mutex));
			return staged;
		}

		PeripheralCapability capabilities() const noexcept override
		{
			return PeripheralCapability::pin_remap;
		}

		void begin(unsigned long baud) override { begin(baud, SERIAL_8N1); }
		void begin(unsigned long baud, std::uint16_t config) override
		{
			if (k_is_in_isr())
			{
				record(serial1_state, SerialError::invalid_context);
				return;
			}
			struct uart_config requested{};
			if (!buildConfig(baud, config, requested))
			{
				record(serial1_state, SerialError::unsupported_config);
				return;
			}
			static_cast<void>(k_mutex_lock(serial1_state.lifecycle_mutex, K_FOREVER));
			if (atomic_get(&serial1_state.diagnostics->started) != 0)
			{
				struct uart_config previous{};
				const int get_result = uart_config_get(serial1_state.device, &previous);
				if (get_result < 0)
				{
					record(serial1_state, SerialError::driver_error, get_result);
				}
				else if (sameConfig(previous, requested))
				{
					serial1_state.baud = baud;
					serial1_state.config = config;
					record(serial1_state, SerialError::none);
				}
				else
				{
					const bool stopped = stopRx(serial1_state);
					const int configure_result = stopped ? uart_configure(serial1_state.device, &requested) : -EIO;
					if ((configure_result < 0) || !startRx(serial1_state))
					{
						static_cast<void>(uart_configure(serial1_state.device, &previous));
						if (atomic_get(&serial1_state.diagnostics->started) == 0)
						{
							static_cast<void>(startRx(serial1_state));
						}
						record(serial1_state, SerialError::driver_error,
							   configure_result < 0 ? configure_result : -EIO);
					}
					else
					{
						serial1_state.baud = baud;
						serial1_state.config = config;
						record(serial1_state, SerialError::none);
					}
				}
				static_cast<void>(k_mutex_unlock(serial1_state.lifecycle_mutex));
				return;
			}
			if (!serial1_binding.available)
			{
				record(serial1_state, SerialError::route_error);
				static_cast<void>(k_mutex_unlock(serial1_state.lifecycle_mutex));
				return;
			}
			if (!serial1_route_staged)
			{
				PeripheralRouteConfiguration route{};
				serial1_route_staged =
					nucode::arduino::internal::defaultSerial1Route(route) ==
						PeripheralRouteBuildError::none &&
					serial1_route.stage(route);
			}
			if (!serial1_route_staged || !serial1_route.activate())
			{
				record(serial1_state, SerialError::route_error,
					   serial1_route.lastDriverError());
				static_cast<void>(k_mutex_unlock(serial1_state.lifecycle_mutex));
				return;
			}
			const int configure_result = uart_configure(serial1_state.device, &requested);
			if (configure_result < 0)
			{
				static_cast<void>(serial1_route.deactivate());
				record(serial1_state, SerialError::driver_error, configure_result);
				static_cast<void>(k_mutex_unlock(serial1_state.lifecycle_mutex));
				return;
			}
			serial1_state.baud = baud;
			serial1_state.config = config;
			if (!startRx(serial1_state))
			{
				static_cast<void>(serial1_route.deactivate());
			}
			static_cast<void>(k_mutex_unlock(serial1_state.lifecycle_mutex));
		}

		void end() override
		{
			if (k_is_in_isr())
			{
				record(serial1_state, SerialError::invalid_context);
				return;
			}
			static_cast<void>(k_mutex_lock(serial1_state.lifecycle_mutex, K_FOREVER));
			const bool was_started =
				atomic_get(&serial1_state.diagnostics->started) != 0;
			const bool route_present =
				serial1_route.active() || serial1_route.faulted();
			if (was_started || route_present)
			{
				const bool rx_ok = !was_started || stopRx(serial1_state);
				const bool route_ok = rx_ok &&
									  (!route_present || serial1_route.deactivate());
				if (rx_ok && route_ok)
				{
					record(serial1_state, SerialError::none);
				}
				else if (!route_ok)
				{
					if (rx_ok)
					{
						record(serial1_state, SerialError::route_error,
							   serial1_route.lastDriverError());
					}
				}
			}
			else
			{
				record(serial1_state, SerialError::none);
			}
			static_cast<void>(k_mutex_unlock(serial1_state.lifecycle_mutex));
		}
		int available() override { return ::available(serial1_state); }
		int peek() override { return readByte(serial1_state, false); }
		int read() override { return readByte(serial1_state, true); }
		void flush() override { ::flush(serial1_state); }
		std::size_t write(std::uint8_t value) override
		{
			const std::size_t result = writeByte(serial1_state, value);
			if (result == 0U)
			{
				setWriteError();
			}
			return result;
		}
		int availableForWrite() override
		{
			return (!k_is_in_isr() && atomic_get(&serial1_state.diagnostics->started)) ? 1 : 0;
		}
		operator bool() override
		{
			return atomic_get(&serial1_state.diagnostics->started) && serial1_state.device != nullptr && device_is_ready(serial1_state.device);
		}
	};
#endif

	ConsoleSerial console_backend;
#if defined(CONFIG_NUCODE_ARDUINO_SERIAL1)
	Uart30Serial serial1_backend;
#endif
}

HardwareSerial &Serial = console_backend;
#if defined(CONFIG_NUCODE_ARDUINO_SERIAL1)
nucode::arduino::Nu54HardwareSerial &Serial1 = serial1_backend;
#endif

namespace nucode::arduino::internal
{
	SerialError lastSerialError() noexcept
	{
		return static_cast<SerialError>(atomic_get(&console_diagnostics.error));
	}
	int lastSerialDriverError() noexcept
	{
		return static_cast<int>(atomic_get(&console_diagnostics.driver_error));
	}
	std::uint32_t serialDroppedRxBytes() noexcept
	{
		return static_cast<std::uint32_t>(atomic_get(&console_diagnostics.dropped));
	}
	void clearSerialDiagnostics() noexcept
	{
		atomic_clear(&console_diagnostics.dropped);
		record(console_state, SerialError::none);
	}
#if defined(CONFIG_NUCODE_ARDUINO_SERIAL1)
	SerialError lastSerial1Error() noexcept
	{
		return static_cast<SerialError>(atomic_get(&serial1_diagnostics.error));
	}
	int lastSerial1DriverError() noexcept
	{
		return static_cast<int>(atomic_get(&serial1_diagnostics.driver_error));
	}
	std::uint32_t serial1DroppedRxBytes() noexcept
	{
		return static_cast<std::uint32_t>(atomic_get(&serial1_diagnostics.dropped));
	}
	void clearSerial1Diagnostics() noexcept
	{
		atomic_clear(&serial1_diagnostics.dropped);
		record(serial1_state, SerialError::none);
	}
#endif
}

#undef NUCODE_ARDUINO_SERIAL_NODE
