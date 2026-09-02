/**
 * @file SPI.cpp
 * @brief Zephyr SPI controller 위에 Arduino SPI API를 구현합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <Arduino.h>
#include <NUCODEPeripheral.h>

#include <zephyr/device.h>
#include <zephyr/devicetree.h>
#include <zephyr/drivers/spi.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/atomic.h>

#include <errno.h>
#include <cstddef>
#include <cstdint>

#include "internal/SPIBackend.h"
#include "internal/RuntimePeripheralRoute.h"
#include "internal/SpiInterruptMask.h"
#include <peripheral_routes.h>

#if !DT_HAS_CHOSEN(nucode_arduino_spi)
#error "SPI에는 app overlay의 nucode,arduino-spi chosen controller가 필요합니다."
#endif

#define NUCODE_ARDUINO_SPI_NODE DT_CHOSEN(nucode_arduino_spi)

#if !DT_NODE_HAS_STATUS_OKAY(NUCODE_ARDUINO_SPI_NODE)
#error "nucode,arduino-spi chosen controller가 활성화되어 있지 않습니다."
#endif

#if !DT_NODE_EXISTS(DT_NODELABEL(spi00))
#error "NU54DK SPI 구현에는 spi00 Devicetree node가 필요합니다."
#elif !DT_SAME_NODE(NUCODE_ARDUINO_SPI_NODE, DT_NODELABEL(spi00)) && \
	!defined(NUCODE_ARDUINO_SPI_TEST_ALLOW_NON_SPI00)
#error "NUCODE_M7_SPI_CHOSEN_MUST_BE_SPI00: NU54DK nucode,arduino-spi chosen은 SPI00을 가리켜야 합니다."
#endif

#if DT_NODE_EXISTS(DT_NODELABEL(spi00)) && DT_NODE_EXISTS(DT_NODELABEL(uart00))
#if DT_SAME_NODE(NUCODE_ARDUINO_SPI_NODE, DT_NODELABEL(spi00)) && \
	DT_NODE_HAS_STATUS_OKAY(DT_NODELABEL(uart00))
#error "NUCODE_M7_SPI_UART00_CONFLICT: NU54DK spi00과 uart00은 같은 하드웨어 자원을 공유하므로 동시에 활성화할 수 없습니다."
#endif
#endif

namespace
{

	using nucode::arduino::internal::SpiError;

	/** @brief NU54DK chosen SPI controller가 선언한 최대 SCK 속도입니다. */
	constexpr std::uint32_t maximum_spi_frequency_hz =
		DT_PROP_OR(NUCODE_ARDUINO_SPI_NODE, max_frequency, 32000000U);

	/** @brief NU54DK SPI00의 고정 SPIM base clock입니다. */
	constexpr std::uint32_t spi_base_frequency_hz = 128000000U;

	/** @brief nRF54L15 SPI00이 허용하는 가장 작은 prescaler입니다. */
	constexpr std::uint32_t minimum_spi_prescaler = 4U;

	/** @brief nRF54L15 SPI00이 허용하는 가장 큰 prescaler입니다. */
	constexpr std::uint32_t maximum_spi_prescaler = 126U;

	/** @brief 보드 overlay가 선택한 SPI controller입니다. */
	const struct device *const spi_device = DEVICE_DT_GET(NUCODE_ARDUINO_SPI_NODE);
	const nucode::arduino::internal::PeripheralRouteBinding spi_binding =
		nucode::arduino::internal::spiRouteBinding();
	nucode::arduino::internal::RuntimePeripheralRoute spi_route(
		spi_binding.device, spi_binding.pinctrl_config, spi_binding.owner,
		spi_binding.block_kind, spi_binding.block_index);
	bool spi_route_staged = false;

	K_MUTEX_DEFINE(spi_mutex);

	atomic_t last_spi_error = ATOMIC_INIT(static_cast<atomic_val_t>(SpiError::none));
	atomic_t last_spi_driver_error = ATOMIC_INIT(0);
	atomic_t spi_transaction_active = ATOMIC_INIT(0);
	atomic_t spi_transaction_frequency = ATOMIC_INIT(0);

	bool spi_started = false;
	struct spi_config spi_configurations[2] = {};
	std::size_t active_configuration_index = 0U;
	const struct spi_config *active_configuration = nullptr;
	BitOrder active_bit_order = MSBFIRST;
	k_tid_t spi_transaction_owner = nullptr;
	constexpr std::size_t interrupt_capacity = 8U;
	int spi_interrupts[interrupt_capacity]{};
	std::size_t spi_interrupt_count = 0U;
	nucode::arduino::internal::SpiInterruptMaskToken
		spi_interrupt_tokens[interrupt_capacity]{};
	nucode::arduino::internal::SpiInterruptMaskAdapter interrupt_adapter_storage{};
	const nucode::arduino::internal::SpiInterruptMaskAdapter *interrupt_adapter = nullptr;
	bool spi_interrupt_mask_faulted = false;

	/** @brief SPI 진단 상태를 원자적으로 기록합니다. */
	void recordSpiError(SpiError error, int driver_error = 0) noexcept;

	/** @brief 복구되지 않은 interrupt token이 하나라도 남아 있는지 확인합니다. */
	[[nodiscard]] bool hasActiveSpiInterruptToken() noexcept
	{
		for (std::size_t index = 0U; index < spi_interrupt_count; ++index)
		{
			if (spi_interrupt_tokens[index].active)
			{
				return true;
			}
		}
		return false;
	}

	/** @brief 등록된 Arduino GPIO interrupt를 순서대로 suspend합니다. */
	[[nodiscard]] bool suspendSpiInterrupts() noexcept
	{
		if (spi_interrupt_mask_faulted || hasActiveSpiInterruptToken())
		{
			recordSpiError(SpiError::interrupt_mask_error, -EIO);
			return false;
		}
		if (spi_interrupt_count == 0U)
		{
			return true;
		}
		if ((interrupt_adapter == nullptr) || (interrupt_adapter->suspend == nullptr) ||
			(interrupt_adapter->restore == nullptr))
		{
			recordSpiError(SpiError::unsupported_operation);
			return false;
		}
		for (std::size_t index = 0U; index < spi_interrupt_count; ++index)
		{
			spi_interrupt_tokens[index] = {};
			const int result = interrupt_adapter->suspend(
				spi_interrupts[index], spi_interrupt_tokens[index]);
			if (result < 0)
			{
				int rollback_error = 0;
				for (std::size_t restore = index; restore > 0U; --restore)
				{
					const int restore_result = interrupt_adapter->restore(
						spi_interrupt_tokens[restore - 1U]);
					if (restore_result == 0)
					{
						spi_interrupt_tokens[restore - 1U].active = false;
					}
					else if (rollback_error == 0)
					{
						rollback_error = restore_result;
					}
				}
				if (spi_interrupt_tokens[index].active && rollback_error == 0)
				{
					rollback_error = -EIO;
				}
				spi_interrupt_mask_faulted = rollback_error < 0;
				recordSpiError(SpiError::interrupt_mask_error,
							   rollback_error < 0 ? rollback_error : result);
				return false;
			}
			spi_interrupt_tokens[index].active = true;
		}
		return true;
	}

	/** @brief suspend된 Arduino GPIO interrupt를 역순으로 복원합니다. */
	[[nodiscard]] bool restoreSpiInterrupts() noexcept
	{
		int first_error = 0;
		if ((interrupt_adapter == nullptr) || (interrupt_adapter->restore == nullptr))
		{
			return spi_interrupt_count == 0U;
		}
		for (std::size_t index = spi_interrupt_count; index > 0U; --index)
		{
			if (!spi_interrupt_tokens[index - 1U].active)
			{
				continue;
			}
			const int result = interrupt_adapter->restore(spi_interrupt_tokens[index - 1U]);
			if (result == 0)
			{
				spi_interrupt_tokens[index - 1U].active = false;
			}
			if ((first_error == 0) && (result < 0))
			{
				first_error = result;
			}
		}
		if (first_error < 0)
		{
			spi_interrupt_mask_faulted = true;
			recordSpiError(SpiError::interrupt_mask_error, first_error);
			return false;
		}
		spi_interrupt_mask_faulted = false;
		return true;
	}

	/**
	 * @brief SPI 진단 상태를 원자적으로 기록합니다.
	 *
	 * @param error Core 내부 오류입니다.
	 * @param driver_error Zephyr SPI가 반환한 오류입니다.
	 */
	void recordSpiError(SpiError error, int driver_error) noexcept
	{
		atomic_set(&last_spi_driver_error, static_cast<atomic_val_t>(driver_error));
		atomic_set(&last_spi_error, static_cast<atomic_val_t>(error));
	}

	/** @brief 성공한 SPI API 뒤 이전 오류를 제거합니다. */
	void recordSpiSuccess() noexcept
	{
		recordSpiError(SpiError::none);
	}

	/**
	 * @brief Arduino SPI mode를 Zephyr operation flag로 변환합니다.
	 *
	 * @param mode Arduino SPI mode입니다.
	 * @param flags 변환 결과를 받을 주소입니다.
	 * @return mode 0~3이면 true입니다.
	 */
	[[nodiscard]] bool modeFlags(arduino::SPIMode mode, spi_operation_t &flags) noexcept
	{
		switch (mode)
		{
		case arduino::SPI_MODE0:
			flags = 0U;
			return true;
		case arduino::SPI_MODE1:
			flags = SPI_MODE_CPHA;
			return true;
		case arduino::SPI_MODE2:
			flags = SPI_MODE_CPOL;
			return true;
		case arduino::SPI_MODE3:
			flags = SPI_MODE_CPOL | SPI_MODE_CPHA;
			return true;
		default:
			return false;
		}
	}

	/**
	 * @brief 요청한 SCK를 SPI00 prescaler 규칙으로 표현할 수 있는지 확인합니다.
	 *
	 * Core가 임의의 근사값을 선택하지 않도록 nRF54L15 nrfx driver와 같은
	 * predicate를 선제 적용합니다. SPI00은 128 MHz base clock과 4~126
	 * 범위의 짝수 prescaler를 사용합니다.
	 *
	 * @param frequency 요청한 SCK 속도입니다.
	 * @return 실제 hardware driver가 허용하는 값이면 true입니다.
	 */
	[[nodiscard]] bool frequencySupported(std::uint32_t frequency) noexcept
	{
		if ((frequency == 0U) || (frequency > maximum_spi_frequency_hz))
		{
			return false;
		}

		const std::uint32_t prescaler = spi_base_frequency_hz / frequency;
		return ((spi_base_frequency_hz % frequency) < prescaler) &&
			   ((prescaler % 2U) == 0U) &&
			   (prescaler >= minimum_spi_prescaler) &&
			   (prescaler <= maximum_spi_prescaler);
	}

	/**
	 * @brief SPISettings를 CS 없는 Zephyr controller 설정으로 변환합니다.
	 *
	 * @param settings Arduino transaction 설정입니다.
	 * @param configuration 변환 결과를 받을 설정입니다.
	 * @return v0.1 controller 계약과 맞으면 true입니다.
	 */
	[[nodiscard]] bool buildSpiConfiguration(const arduino::SPISettings &settings,
											 struct spi_config &configuration) noexcept
	{
		if (settings.getBusMode() != arduino::SPI_CONTROLLER)
		{
			recordSpiError(SpiError::unsupported_bus_mode);
			return false;
		}
		if (!frequencySupported(settings.getClockFreq()))
		{
			recordSpiError(SpiError::invalid_frequency);
			return false;
		}
		if ((settings.getBitOrder() != MSBFIRST) &&
			(settings.getBitOrder() != LSBFIRST))
		{
			recordSpiError(SpiError::invalid_bit_order);
			return false;
		}

		spi_operation_t mode_flags = 0U;
		if (!modeFlags(settings.getDataMode(), mode_flags))
		{
			recordSpiError(SpiError::invalid_data_mode);
			return false;
		}

		configuration = {};
		configuration.frequency = settings.getClockFreq();
		configuration.operation = SPI_OP_MODE_MASTER | SPI_WORD_SET(8) | mode_flags |
								  ((settings.getBitOrder() == LSBFIRST) ? SPI_TRANSFER_LSB : SPI_TRANSFER_MSB);
		configuration.slave = 0U;
		configuration.cs = {};
		configuration.word_delay = 0U;
		return true;
	}

	/**
	 * @brief 현재 transaction 설정으로 full-duplex byte block을 전송합니다.
	 *
	 * @param transmit 송신 buffer입니다.
	 * @param receive 수신 buffer입니다.
	 * @param length buffer 길이입니다.
	 * @return 성공하면 true입니다.
	 */
	[[nodiscard]] bool transferBlock(const std::uint8_t *transmit, std::uint8_t *receive,
									 std::size_t length) noexcept
	{
		if (length == 0U)
		{
			recordSpiSuccess();
			return true;
		}

		struct spi_buf tx_buffer = {};
		tx_buffer.buf = const_cast<std::uint8_t *>(transmit);
		tx_buffer.len = length;
		struct spi_buf_set tx_set = {};
		tx_set.buffers = &tx_buffer;
		tx_set.count = 1U;
		struct spi_buf rx_buffer = {};
		rx_buffer.buf = receive;
		rx_buffer.len = length;
		struct spi_buf_set rx_set = {};
		rx_set.buffers = &rx_buffer;
		rx_set.count = 1U;

		const int result = spi_transceive(spi_device, active_configuration, &tx_set, &rx_set);
		if (result < 0)
		{
			recordSpiError(SpiError::driver_error, result);
			return false;
		}

		recordSpiSuccess();
		return true;
	}

	/** @brief ArduinoCore-API HardwareSPI의 CS 없는 controller 구현입니다. */
	class ZephyrSPI final : public nucode::arduino::Nu54SPIClass
	{
	public:
		/** @brief 종료 상태에서 다음 begin()의 SPI00 고정 route를 검증·선택합니다. */
		bool setPins(pin_size_t sck_pin, pin_size_t miso_pin,
					 pin_size_t mosi_pin) noexcept override
		{
			if (k_is_in_isr())
			{
				recordSpiError(SpiError::invalid_context);
				return false;
			}
			static_cast<void>(k_mutex_lock(&spi_mutex, K_FOREVER));
			if (spi_started)
			{
				recordSpiError(SpiError::route_busy);
				static_cast<void>(k_mutex_unlock(&spi_mutex));
				return false;
			}
			const pin_size_t pins[]{sck_pin, miso_pin, mosi_pin};
			const nucode::arduino::internal::PeripheralSignal signals[]{
				nucode::arduino::internal::PeripheralSignal::spi_sck,
				nucode::arduino::internal::PeripheralSignal::spi_miso,
				nucode::arduino::internal::PeripheralSignal::spi_mosi,
			};
			nucode::arduino::internal::PeripheralRouteConfiguration configuration{};
			const auto result = nucode::arduino::internal::buildPeripheralRoute(
				nucode::arduino::internal::PinRoute::spi00, pins, signals, 3U,
				configuration);
			const bool staged =
				(result == nucode::arduino::internal::PeripheralRouteBuildError::none) &&
				spi_route.stage(configuration);
			if (staged)
			{
				spi_route_staged = true;
			}
			recordSpiError(staged ? SpiError::none : SpiError::invalid_pin_route,
						   staged ? 0 : static_cast<int>(result));
			static_cast<void>(k_mutex_unlock(&spi_mutex));
			return staged;
		}

		/** @brief controller·pin route와 현재 등록된 interrupt adapter capability를 반환합니다. */
		nucode::arduino::PeripheralCapability capabilities() const noexcept override
		{
			auto result = nucode::arduino::PeripheralCapability::controller |
						  nucode::arduino::PeripheralCapability::pin_remap;
			if (nucode::arduino::internal::spiInterruptMaskAvailable())
			{
				result = result | nucode::arduino::PeripheralCapability::interrupt_mask;
			}
			return result;
		}

		/** @brief Zephyr가 pinctrl을 적용한 SPI controller lifecycle을 시작합니다. */
		void begin() override
		{
			if (k_is_in_isr())
			{
				recordSpiError(SpiError::invalid_context);
				return;
			}

			static_cast<void>(k_mutex_lock(&spi_mutex, K_FOREVER));
			if (spi_started)
			{
				recordSpiSuccess();
				static_cast<void>(k_mutex_unlock(&spi_mutex));
				return;
			}
			if (!spi_binding.available)
			{
				recordSpiError(SpiError::route_error);
			}
			else
			{
				if (!spi_route_staged)
				{
					nucode::arduino::internal::PeripheralRouteConfiguration route{};
					spi_route_staged =
						nucode::arduino::internal::defaultSpiRoute(route) ==
							nucode::arduino::internal::PeripheralRouteBuildError::none &&
						spi_route.stage(route);
				}
				if (!spi_route_staged || !spi_route.activate())
				{
					recordSpiError(SpiError::route_error, spi_route.lastDriverError());
				}
				else if (!device_is_ready(spi_device))
				{
					static_cast<void>(spi_route.deactivate());
					recordSpiError(SpiError::device_not_ready);
				}
				else
				{
					spi_started = true;
					recordSpiSuccess();
				}
			}
			static_cast<void>(k_mutex_unlock(&spi_mutex));
		}

		/** @brief Core 상태만 닫고 Zephyr가 소유한 SPI 장치는 유지합니다. */
		void end() override
		{
			if (k_is_in_isr())
			{
				recordSpiError(SpiError::invalid_context);
				return;
			}

			static_cast<void>(k_mutex_lock(&spi_mutex, K_FOREVER));
			const bool discarded_transaction = atomic_get(&spi_transaction_active) != 0;
			if (discarded_transaction && (spi_transaction_owner != k_current_get()))
			{
				recordSpiError(SpiError::transaction_owner_mismatch);
				static_cast<void>(k_mutex_unlock(&spi_mutex));
				return;
			}
			const bool interrupts_ok =
				(!discarded_transaction && !hasActiveSpiInterruptToken()) ||
				restoreSpiInterrupts();
			if (!interrupts_ok)
			{
				/** @brief 복구 token과 transaction 소유권을 보존하여 새 사용을 차단합니다. */
				static_cast<void>(k_mutex_unlock(&spi_mutex));
				return;
			}
			atomic_clear(&spi_transaction_active);
			atomic_clear(&spi_transaction_frequency);
			active_configuration = nullptr;
			spi_transaction_owner = nullptr;
			const bool route_present =
				spi_started || spi_route.active() || spi_route.faulted();
			const bool route_ok = !route_present || spi_route.deactivate();
			spi_started = !route_ok && spi_route.active();
			if (!route_ok)
			{
				recordSpiError(SpiError::route_error, spi_route.lastDriverError());
			}
			else
			{
				recordSpiError(discarded_transaction ? SpiError::transaction_already_active
													 : SpiError::none);
			}
			static_cast<void>(k_mutex_unlock(&spi_mutex));
		}

		/** @brief 새 transaction의 frequency, mode와 bit order를 고정합니다. */
		void beginTransaction(arduino::SPISettings settings) override
		{
			if (k_is_in_isr())
			{
				recordSpiError(SpiError::invalid_context);
				return;
			}

			static_cast<void>(k_mutex_lock(&spi_mutex, K_FOREVER));
			if (!spi_started)
			{
				recordSpiError(SpiError::not_started);
			}
			else if (atomic_get(&spi_transaction_active) != 0)
			{
				recordSpiError((spi_transaction_owner == k_current_get())
								   ? SpiError::transaction_already_active
								   : SpiError::transaction_owner_mismatch);
			}
			else if (spi_interrupt_mask_faulted || hasActiveSpiInterruptToken())
			{
				recordSpiError(SpiError::interrupt_mask_error, -EIO);
			}
			else
			{
				active_configuration_index ^= 1U;
				struct spi_config &configuration =
					spi_configurations[active_configuration_index];
				if (buildSpiConfiguration(settings, configuration) && suspendSpiInterrupts())
				{
					active_configuration = &configuration;
					active_bit_order = settings.getBitOrder();
					atomic_set(&spi_transaction_frequency,
							   static_cast<atomic_val_t>(settings.getClockFreq()));
					atomic_set(&spi_transaction_active, 1);
					spi_transaction_owner = k_current_get();
					recordSpiSuccess();
				}
			}
			static_cast<void>(k_mutex_unlock(&spi_mutex));
		}

		/** @brief 현재 transaction을 닫으며 외부 CS는 변경하지 않습니다. */
		void endTransaction() override
		{
			if (k_is_in_isr())
			{
				recordSpiError(SpiError::invalid_context);
				return;
			}

			static_cast<void>(k_mutex_lock(&spi_mutex, K_FOREVER));
			if (atomic_get(&spi_transaction_active) == 0)
			{
				recordSpiError(SpiError::transaction_not_active);
			}
			else if (spi_transaction_owner != k_current_get())
			{
				recordSpiError(SpiError::transaction_owner_mismatch);
			}
			else
			{
				const bool interrupts_ok = restoreSpiInterrupts();
				if (interrupts_ok)
				{
					atomic_clear(&spi_transaction_active);
					atomic_clear(&spi_transaction_frequency);
					active_configuration = nullptr;
					spi_transaction_owner = nullptr;
					recordSpiSuccess();
				}
			}
			static_cast<void>(k_mutex_unlock(&spi_mutex));
		}

		/** @brief 현재 transaction에서 한 byte를 full-duplex 전송합니다. */
		std::uint8_t transfer(std::uint8_t value) override
		{
			if (k_is_in_isr())
			{
				recordSpiError(SpiError::invalid_context);
				return 0U;
			}

			static_cast<void>(k_mutex_lock(&spi_mutex, K_FOREVER));
			if (!spi_started)
			{
				recordSpiError(SpiError::not_started);
				static_cast<void>(k_mutex_unlock(&spi_mutex));
				return 0U;
			}
			if ((atomic_get(&spi_transaction_active) == 0) ||
				(active_configuration == nullptr))
			{
				recordSpiError(SpiError::transaction_not_active);
				static_cast<void>(k_mutex_unlock(&spi_mutex));
				return 0U;
			}
			if (spi_transaction_owner != k_current_get())
			{
				recordSpiError(SpiError::transaction_owner_mismatch);
				static_cast<void>(k_mutex_unlock(&spi_mutex));
				return 0U;
			}

			std::uint8_t received = 0U;
			static_cast<void>(transferBlock(&value, &received, 1U));
			static_cast<void>(k_mutex_unlock(&spi_mutex));
			return received;
		}

		/** @brief 현재 bit order에 맞춰 16-bit 값을 full-duplex 전송합니다. */
		std::uint16_t transfer16(std::uint16_t value) override
		{
			if (k_is_in_isr())
			{
				recordSpiError(SpiError::invalid_context);
				return 0U;
			}

			static_cast<void>(k_mutex_lock(&spi_mutex, K_FOREVER));
			if (!spi_started || (atomic_get(&spi_transaction_active) == 0) ||
				(active_configuration == nullptr))
			{
				recordSpiError(spi_started ? SpiError::transaction_not_active
										   : SpiError::not_started);
				static_cast<void>(k_mutex_unlock(&spi_mutex));
				return 0U;
			}
			if (spi_transaction_owner != k_current_get())
			{
				recordSpiError(SpiError::transaction_owner_mismatch);
				static_cast<void>(k_mutex_unlock(&spi_mutex));
				return 0U;
			}

			std::uint8_t transmit[2] = {};
			std::uint8_t receive[2] = {};
			if (active_bit_order == LSBFIRST)
			{
				transmit[0] = static_cast<std::uint8_t>(value & 0xFFU);
				transmit[1] = static_cast<std::uint8_t>(value >> 8U);
			}
			else
			{
				transmit[0] = static_cast<std::uint8_t>(value >> 8U);
				transmit[1] = static_cast<std::uint8_t>(value & 0xFFU);
			}

			if (!transferBlock(transmit, receive, sizeof(transmit)))
			{
				static_cast<void>(k_mutex_unlock(&spi_mutex));
				return 0U;
			}

			const std::uint16_t result = (active_bit_order == LSBFIRST)
											 ? static_cast<std::uint16_t>(receive[0] |
																		  (receive[1] << 8U))
											 : static_cast<std::uint16_t>((receive[0] << 8U) |
																		  receive[1]);
			static_cast<void>(k_mutex_unlock(&spi_mutex));
			return result;
		}

		/** @brief caller 소유 buffer를 고정 크기 chunk로 in-place 전송합니다. */
		void transfer(void *buffer, std::size_t count) override
		{
			if (k_is_in_isr())
			{
				recordSpiError(SpiError::invalid_context);
				return;
			}
			if ((buffer == nullptr) && (count != 0U))
			{
				recordSpiError(SpiError::invalid_buffer);
				return;
			}

			static_cast<void>(k_mutex_lock(&spi_mutex, K_FOREVER));
			if (!spi_started || (atomic_get(&spi_transaction_active) == 0) ||
				(active_configuration == nullptr))
			{
				recordSpiError(spi_started ? SpiError::transaction_not_active
										   : SpiError::not_started);
				static_cast<void>(k_mutex_unlock(&spi_mutex));
				return;
			}
			if (spi_transaction_owner != k_current_get())
			{
				recordSpiError(SpiError::transaction_owner_mismatch);
				static_cast<void>(k_mutex_unlock(&spi_mutex));
				return;
			}

			auto *bytes = static_cast<std::uint8_t *>(buffer);
			constexpr std::size_t chunk_capacity = 32U;
			std::uint8_t transmit[chunk_capacity] = {};
			std::uint8_t receive[chunk_capacity] = {};
			std::size_t offset = 0U;
			while (offset < count)
			{
				const std::size_t remaining = count - offset;
				const std::size_t chunk = (remaining < chunk_capacity) ? remaining
																	   : chunk_capacity;
				for (std::size_t index = 0U; index < chunk; ++index)
				{
					transmit[index] = bytes[offset + index];
				}
				if (!transferBlock(transmit, receive, chunk))
				{
					break;
				}
				for (std::size_t index = 0U; index < chunk; ++index)
				{
					bytes[offset + index] = receive[index];
				}
				offset += chunk;
			}
			static_cast<void>(k_mutex_unlock(&spi_mutex));
		}

		/** @brief transaction 동안 마스킹할 Arduino GPIO interrupt를 등록합니다. */
		void usingInterrupt(int interrupt_number) override
		{
			if (k_is_in_isr())
			{
				recordSpiError(SpiError::invalid_context);
				return;
			}
			static_cast<void>(k_mutex_lock(&spi_mutex, K_FOREVER));
			if (atomic_get(&spi_transaction_active) != 0)
			{
				recordSpiError(SpiError::transaction_already_active);
			}
			else if (spi_interrupt_mask_faulted || hasActiveSpiInterruptToken())
			{
				recordSpiError(SpiError::interrupt_mask_error, -EIO);
			}
			else if ((interrupt_adapter == nullptr) || (interrupt_adapter->valid == nullptr) ||
					 !interrupt_adapter->valid(interrupt_number))
			{
				recordSpiError(SpiError::unsupported_operation);
			}
			else
			{
				bool found = false;
				for (std::size_t index = 0U; index < spi_interrupt_count; ++index)
				{
					found = found || (spi_interrupts[index] == interrupt_number);
				}
				if (found)
				{
					recordSpiSuccess();
				}
				else if (spi_interrupt_count >= interrupt_capacity)
				{
					recordSpiError(SpiError::unsupported_operation);
				}
				else
				{
					spi_interrupts[spi_interrupt_count++] = interrupt_number;
					recordSpiSuccess();
				}
			}
			static_cast<void>(k_mutex_unlock(&spi_mutex));
		}

		/** @brief transaction 마스킹 대상에서 Arduino GPIO interrupt를 제거합니다. */
		void notUsingInterrupt(int interrupt_number) override
		{
			if (k_is_in_isr())
			{
				recordSpiError(SpiError::invalid_context);
				return;
			}
			static_cast<void>(k_mutex_lock(&spi_mutex, K_FOREVER));
			if (atomic_get(&spi_transaction_active) != 0)
			{
				recordSpiError(SpiError::transaction_already_active);
			}
			else if (spi_interrupt_mask_faulted || hasActiveSpiInterruptToken())
			{
				recordSpiError(SpiError::interrupt_mask_error, -EIO);
			}
			else
			{
				std::size_t index = 0U;
				while ((index < spi_interrupt_count) &&
					   (spi_interrupts[index] != interrupt_number))
				{
					++index;
				}
				if (index == spi_interrupt_count)
				{
					recordSpiError(SpiError::unsupported_operation);
				}
				else
				{
					for (; index + 1U < spi_interrupt_count; ++index)
					{
						spi_interrupts[index] = spi_interrupts[index + 1U];
					}
					--spi_interrupt_count;
					recordSpiSuccess();
				}
			}
			static_cast<void>(k_mutex_unlock(&spi_mutex));
		}

		/** @brief SPI peripheral interrupt 기능은 제공하지 않습니다. */
		void attachInterrupt() override
		{
			recordSpiError(SpiError::unsupported_operation);
		}

		/** @brief SPI peripheral interrupt 기능은 제공하지 않습니다. */
		void detachInterrupt() override
		{
			recordSpiError(SpiError::unsupported_operation);
		}
	};

	ZephyrSPI spi_backend;

}

SPIClass &SPI = spi_backend;

namespace nucode::arduino::internal
{
	bool registerSpiInterruptMaskAdapter(const SpiInterruptMaskAdapter &adapter) noexcept
	{
		if (k_is_in_isr() || (adapter.valid == nullptr) ||
			(adapter.suspend == nullptr) || (adapter.restore == nullptr))
		{
			return false;
		}
		static_cast<void>(k_mutex_lock(&spi_mutex, K_FOREVER));
		if ((interrupt_adapter != nullptr) ||
			(atomic_get(&spi_transaction_active) != 0))
		{
			static_cast<void>(k_mutex_unlock(&spi_mutex));
			return false;
		}
		interrupt_adapter_storage = adapter;
		interrupt_adapter = &interrupt_adapter_storage;
		static_cast<void>(k_mutex_unlock(&spi_mutex));
		return true;
	}

	bool spiInterruptMaskAvailable() noexcept
	{
		return interrupt_adapter != nullptr;
	}

	SpiError lastSpiError() noexcept
	{
		return static_cast<SpiError>(atomic_get(&last_spi_error));
	}

	int lastSpiDriverError() noexcept
	{
		return static_cast<int>(atomic_get(&last_spi_driver_error));
	}

	bool spiTransactionActive() noexcept
	{
		return atomic_get(&spi_transaction_active) != 0;
	}

	std::uint32_t spiTransactionFrequency() noexcept
	{
		return static_cast<std::uint32_t>(atomic_get(&spi_transaction_frequency));
	}

	void clearSpiDiagnostics() noexcept
	{
		recordSpiSuccess();
	}

}

#undef NUCODE_ARDUINO_SPI_NODE
