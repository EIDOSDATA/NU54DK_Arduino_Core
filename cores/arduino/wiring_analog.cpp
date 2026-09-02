/**
 * @file wiring_analog.cpp
 * @brief NU54DK의 다중 SAADC, 동적 PWM과 tone Arduino API를 구현합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <Arduino.h>

#include <zephyr/device.h>
#include <zephyr/devicetree.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/atomic.h>
#include <zephyr/sys/util.h>

#if defined(CONFIG_NUCODE_ARDUINO_ADC)
#include <zephyr/drivers/adc.h>
#endif

#include <cstddef>
#include <cstdint>
#include <errno.h>

#include "internal/AnalogBackend.h"
#include "internal/AnalogRuntimeMath.h"
#include "internal/IoResourceManager.h"
#include "internal/PinHandover.h"
#include "internal/PwmRuntime.h"
#include "internal/pin_description.h"

#if defined(CONFIG_NUCODE_ARDUINO_ADC)

#if !DT_HAS_CHOSEN(nucode_arduino_adc)
#error "analogRead에는 io-channels를 가진 nucode,arduino-adc chosen node가 필요합니다."
#endif

#define NUCODE_ARDUINO_ADC_NODE DT_CHOSEN(nucode_arduino_adc)

#if !DT_NODE_HAS_PROP(NUCODE_ARDUINO_ADC_NODE, io_channels)
#error "nucode,arduino-adc chosen node에는 io-channels 속성이 필요합니다."
#endif

#define NUCODE_ADC_SPEC_AND_COMMA(node_id, prop, index) \
	ADC_DT_SPEC_GET_BY_IDX(node_id, index),

#endif

namespace
{
	using nucode::arduino::internal::AnalogError;
	using nucode::arduino::internal::GpioPinHandover;
	using nucode::arduino::internal::IoAcquirePolicy;
	using nucode::arduino::internal::IoOwnerKind;
	using nucode::arduino::internal::IoResourceKind;
	using nucode::arduino::internal::IoResourceLease;
	using nucode::arduino::internal::IoResourceResult;
	using nucode::arduino::internal::PinCapability;
	using nucode::arduino::internal::PinHandoverResult;
	using nucode::arduino::internal::PinOwnership;
	using nucode::arduino::internal::PinPolicy;
	using nucode::arduino::internal::PinRoute;
	using nucode::arduino::internal::PwmRuntimeClient;
	using nucode::arduino::internal::PwmRuntimeResult;

	K_MUTEX_DEFINE(analog_mutex);

	atomic_t last_analog_error = ATOMIC_INIT(static_cast<atomic_val_t>(AnalogError::none));
	atomic_t last_analog_driver_error = ATOMIC_INIT(0);

#if defined(CONFIG_NUCODE_ARDUINO_ADC)
	/** @brief profile chosen node가 공개한 SAADC channel 전체입니다. */
	const struct adc_dt_spec adc_inputs[] = {
		DT_FOREACH_PROP_ELEM(NUCODE_ARDUINO_ADC_NODE, io_channels,
							 NUCODE_ADC_SPEC_AND_COMMA)};

	std::uint32_t configured_adc_channels = 0U;
	std::uint8_t analog_read_resolution =
		nucode::arduino::internal::analog_read_resolution_bits;
#endif

#if defined(CONFIG_NUCODE_ARDUINO_PWM)
	/** @brief 기존 PIN_PWM0의 v0.1~v0.2 호환 기본 주파수입니다. */
	constexpr std::uint32_t default_analog_write_frequency_hz = 50U;

	std::uint8_t analog_write_resolution =
		nucode::arduino::internal::analog_write_resolution_bits;
	std::uint32_t analog_write_frequencies[NUM_PIN_ROLES]{};

	K_MUTEX_DEFINE(tone_api_mutex);
	K_MUTEX_DEFINE(tone_state_mutex);

	struct ToneState
	{
		pin_size_t pin{};
		std::uint32_t generation{0U};
		std::uint32_t scheduled_generation{0U};
		bool active{false};
	};

	ToneState tone_state{};

	void toneStopWorkHandler(struct k_work *work);
	K_WORK_DELAYABLE_DEFINE(tone_stop_work, toneStopWorkHandler);
#endif

	/** @brief analog 진단 상태를 원자적으로 기록합니다. */
	void recordAnalogError(AnalogError error, int driver_error = 0) noexcept
	{
		atomic_set(&last_analog_driver_error, static_cast<atomic_val_t>(driver_error));
		atomic_set(&last_analog_error, static_cast<atomic_val_t>(error));
	}

	/** @brief 성공한 analog API 뒤 이전 오류를 제거합니다. */
	void recordAnalogSuccess() noexcept
	{
		recordAnalogError(AnalogError::none);
	}

	/** @brief ownership 결과를 보존 가능한 음수 진단 값으로 변환합니다. */
	[[nodiscard]] int ownershipError(IoResourceResult result) noexcept
	{
		switch (result)
		{
		case IoResourceResult::conflict:
			return -EBUSY;
		case IoResourceResult::capacity_exhausted:
			return -ENOSPC;
		case IoResourceResult::invalid_context:
			return -EWOULDBLOCK;
		case IoResourceResult::invalid_argument:
			return -EINVAL;
		default:
			return -EIO;
		}
	}

	/** @brief GPIO handover 결과를 analog 진단용 errno로 변환합니다. */
	[[nodiscard]] int handoverError(PinHandoverResult result) noexcept
	{
		switch (result)
		{
		case PinHandoverResult::ownership_conflict:
			return -EBUSY;
		case PinHandoverResult::unsupported:
			return -ENOTSUP;
		case PinHandoverResult::device_not_ready:
			return -ENODEV;
		case PinHandoverResult::invalid_context:
			return -EWOULDBLOCK;
		case PinHandoverResult::invalid_argument:
		case PinHandoverResult::invalid_pin:
			return -EINVAL;
		default:
			return -EIO;
		}
	}

	/** @brief PWM runtime 결과를 기존 Analog 진단 계약에 투영합니다. */
	void recordPwmResult(PwmRuntimeResult result) noexcept
	{
		switch (result)
		{
		case PwmRuntimeResult::success:
			recordAnalogSuccess();
			break;
		case PwmRuntimeResult::invalid_context:
			recordAnalogError(AnalogError::invalid_context);
			break;
		case PwmRuntimeResult::invalid_pin:
			recordAnalogError(AnalogError::invalid_pin);
			break;
		case PwmRuntimeResult::invalid_argument:
			recordAnalogError(AnalogError::invalid_value);
			break;
		case PwmRuntimeResult::unsupported_route:
			recordAnalogError(AnalogError::unsupported_devicetree);
			break;
		case PwmRuntimeResult::device_not_ready:
			recordAnalogError(AnalogError::device_not_ready);
			break;
		case PwmRuntimeResult::ownership_conflict:
		case PwmRuntimeResult::period_conflict:
			recordAnalogError(AnalogError::driver_error, -EBUSY);
			break;
		case PwmRuntimeResult::channel_exhausted:
			recordAnalogError(AnalogError::driver_error, -ENOSPC);
			break;
		case PwmRuntimeResult::not_active:
			recordAnalogError(AnalogError::driver_error, -ENOENT);
			break;
		case PwmRuntimeResult::route_error:
		case PwmRuntimeResult::driver_error:
		{
			const int driver_error =
				nucode::arduino::internal::lastPwmRuntimeDriverError();
			recordAnalogError(AnalogError::driver_error,
							  driver_error != 0 ? driver_error : -EIO);
			break;
		}
		default:
			recordAnalogError(AnalogError::unsupported_devicetree);
			break;
		}
	}

#if defined(CONFIG_NUCODE_ARDUINO_ADC)
	/** @brief 논리 핀의 analog metadata와 profile ADC spec을 함께 조회합니다. */
	[[nodiscard]] const struct adc_dt_spec *adcInputForPin(pin_size_t pin) noexcept
	{
		const auto *const description =
			nucode::arduino::internal::pinDescription(pin);
		if (description == nullptr || description->analog_channel < 0 ||
			!nucode::arduino::internal::hasPinCapability(
				description->capabilities, PinCapability::analog_input) ||
			!nucode::arduino::internal::hasPinRoute(description->routes, PinRoute::adc) ||
			description->policy == PinPolicy::system_reserved ||
			description->ownership == PinOwnership::system)
		{
			return nullptr;
		}

		for (const auto &input : adc_inputs)
		{
			if (input.channel_id ==
				static_cast<std::uint8_t>(description->analog_channel))
			{
				return &input;
			}
		}
		return nullptr;
	}

	/** @brief ADC channel의 profile 계약이 runtime resolution 변경과 호환되는지 확인합니다. */
	[[nodiscard]] bool adcDevicetreeContractMatches(
		const struct adc_dt_spec &input) noexcept
	{
		return input.channel_cfg_dt_node_exists && input.channel_id < 32U &&
			   input.channel_cfg.reference == ADC_REF_INTERNAL;
	}

	/** @brief ADC block과 GPIO pad의 transient 예약을 역순으로 복구합니다. */
	void rollbackAnalogRead(GpioPinHandover *handover,
							IoResourceLease &block_lease) noexcept
	{
		if (handover != nullptr)
		{
			static_cast<void>(
				nucode::arduino::internal::rollbackGpioPinHandover(*handover));
		}
		static_cast<void>(nucode::arduino::internal::rollbackIoResources(block_lease));
	}
#endif

#if defined(CONFIG_NUCODE_ARDUINO_PWM)
	/** @brief canonical 핀의 저장 주파수 또는 기본값을 반환합니다. */
	[[nodiscard]] std::uint32_t analogWriteFrequencyForPin(
		std::size_t canonical_pin) noexcept
	{
		return analog_write_frequencies[canonical_pin] != 0U
				   ? analog_write_frequencies[canonical_pin]
				   : default_analog_write_frequency_hz;
	}

	/** @brief tone 출력과 상태를 tone_state_mutex를 잡은 상태에서 중지합니다. */
	void stopToneLocked() noexcept
	{
		if (!tone_state.active)
		{
			return;
		}
		const PwmRuntimeResult result = nucode::arduino::internal::pwmRuntimeStop(
			PwmRuntimeClient::tone, tone_state.pin);
		if (result != PwmRuntimeResult::success &&
			result != PwmRuntimeResult::not_active)
		{
			recordPwmResult(result);
			return;
		}
		tone_state.active = false;
		recordAnalogSuccess();
	}

	/** @brief 유한 duration tone의 현재 generation만 중지합니다. */
	void toneStopWorkHandler(struct k_work *work)
	{
		ARG_UNUSED(work);
		static_cast<void>(k_mutex_lock(&tone_state_mutex, K_FOREVER));
		if (tone_state.active &&
			tone_state.scheduled_generation == tone_state.generation)
		{
			stopToneLocked();
		}
		static_cast<void>(k_mutex_unlock(&tone_state_mutex));
	}
#endif
}

#if defined(CONFIG_NUCODE_ARDUINO_ADC)

extern "C" void analogReference(std::uint8_t mode)
{
	if (k_is_in_isr())
	{
		recordAnalogError(AnalogError::invalid_context);
		return;
	}
	if (mode != AR_DEFAULT)
	{
		recordAnalogError(AnalogError::unsupported_reference);
		return;
	}
	recordAnalogSuccess();
}

extern "C" void analogReadResolution(std::uint8_t bits)
{
	if (k_is_in_isr())
	{
		recordAnalogError(AnalogError::invalid_context);
		return;
	}
	if (!nucode::arduino::internal::isSupportedAnalogReadResolution(bits))
	{
		recordAnalogError(AnalogError::invalid_value);
		return;
	}

	static_cast<void>(k_mutex_lock(&analog_mutex, K_FOREVER));
	analog_read_resolution = bits;
	recordAnalogSuccess();
	static_cast<void>(k_mutex_unlock(&analog_mutex));
}

extern "C" int analogRead(pin_size_t pin)
{
	if (k_is_in_isr())
	{
		recordAnalogError(AnalogError::invalid_context);
		return -1;
	}

	static_cast<void>(k_mutex_lock(&analog_mutex, K_FOREVER));
	const std::size_t canonical = nucode::arduino::internal::canonicalPinId(pin);
	if (canonical == static_cast<std::size_t>(-1))
	{
		recordAnalogError(AnalogError::invalid_pin);
		static_cast<void>(k_mutex_unlock(&analog_mutex));
		return -1;
	}
	const auto *const input = adcInputForPin(static_cast<pin_size_t>(canonical));
	if (input == nullptr)
	{
		recordAnalogError(AnalogError::unsupported_devicetree);
		static_cast<void>(k_mutex_unlock(&analog_mutex));
		return -1;
	}
	if (nucode::arduino::internal::isPinConfiguredForOutput(canonical))
	{
		recordAnalogError(AnalogError::driver_error, -EBUSY);
		static_cast<void>(k_mutex_unlock(&analog_mutex));
		return -1;
	}
	if (!adc_is_ready_dt(input))
	{
		recordAnalogError(AnalogError::device_not_ready);
		static_cast<void>(k_mutex_unlock(&analog_mutex));
		return -1;
	}
	if (!adcDevicetreeContractMatches(*input))
	{
		recordAnalogError(AnalogError::unsupported_devicetree);
		static_cast<void>(k_mutex_unlock(&analog_mutex));
		return -1;
	}

	IoResourceLease block_lease{};
	const auto block_resource = nucode::arduino::internal::peripheralIoResource(
		IoResourceKind::adc_block, 0U, input->dev);
	const IoResourceResult reserve_result =
		nucode::arduino::internal::reserveIoResources(
			{IoOwnerKind::adc, 0U}, &block_resource, 1U,
			IoAcquirePolicy::exclusive, block_lease);
	if (reserve_result != IoResourceResult::success)
	{
		recordAnalogError(AnalogError::driver_error,
						  ownershipError(reserve_result));
		static_cast<void>(k_mutex_unlock(&analog_mutex));
		return -1;
	}

	GpioPinHandover handover{};
	const PinHandoverResult begin_result =
		nucode::arduino::internal::beginGpioPinHandover(
			canonical, {IoOwnerKind::adc, 0U}, handover);
	if (begin_result != PinHandoverResult::success)
	{
		static_cast<void>(
			nucode::arduino::internal::rollbackIoResources(block_lease));
		recordAnalogError(AnalogError::driver_error,
						  handoverError(begin_result));
		static_cast<void>(k_mutex_unlock(&analog_mutex));
		return -1;
	}

	const std::uint32_t channel_mask =
		static_cast<std::uint32_t>(1UL) << input->channel_id;
	if ((configured_adc_channels & channel_mask) == 0U)
	{
		const int setup_result = adc_channel_setup_dt(input);
		if (setup_result < 0)
		{
			rollbackAnalogRead(&handover, block_lease);
			recordAnalogError(AnalogError::driver_error, setup_result);
			static_cast<void>(k_mutex_unlock(&analog_mutex));
			return -1;
		}
		configured_adc_channels |= channel_mask;
	}

	std::int16_t sample = 0;
	struct adc_sequence sequence = {};
	const int sequence_result = adc_sequence_init_dt(input, &sequence);
	if (sequence_result < 0)
	{
		rollbackAnalogRead(&handover, block_lease);
		recordAnalogError(AnalogError::driver_error, sequence_result);
		static_cast<void>(k_mutex_unlock(&analog_mutex));
		return -1;
	}
	sequence.resolution = analog_read_resolution;
	sequence.buffer = &sample;
	sequence.buffer_size = sizeof(sample);

	const int read_result = adc_read_dt(input, &sequence);
	const PinHandoverResult rollback_pin_result =
		nucode::arduino::internal::rollbackGpioPinHandover(handover);
	const IoResourceResult rollback_block_result =
		nucode::arduino::internal::rollbackIoResources(block_lease);
	if (read_result < 0)
	{
		recordAnalogError(AnalogError::driver_error, read_result);
		static_cast<void>(k_mutex_unlock(&analog_mutex));
		return -1;
	}
	if (rollback_pin_result != PinHandoverResult::success ||
		rollback_block_result != IoResourceResult::success)
	{
		recordAnalogError(
			AnalogError::driver_error,
			rollback_pin_result != PinHandoverResult::success
				? handoverError(rollback_pin_result)
				: ownershipError(rollback_block_result));
		static_cast<void>(k_mutex_unlock(&analog_mutex));
		return -1;
	}

	const int maximum = static_cast<int>(
		nucode::arduino::internal::analogResolutionMaximum(analog_read_resolution));
	int result = static_cast<int>(sample);
	if (result < 0)
	{
		result = 0;
	}
	else if (result > maximum)
	{
		result = maximum;
	}

	recordAnalogSuccess();
	static_cast<void>(k_mutex_unlock(&analog_mutex));
	return result;
}

#endif

#if defined(CONFIG_NUCODE_ARDUINO_PWM)

extern "C" void analogWriteResolution(std::uint8_t bits)
{
	if (k_is_in_isr())
	{
		recordAnalogError(AnalogError::invalid_context);
		return;
	}
	if (!nucode::arduino::internal::isSupportedAnalogWriteResolution(bits))
	{
		recordAnalogError(AnalogError::invalid_value);
		return;
	}

	static_cast<void>(k_mutex_lock(&analog_mutex, K_FOREVER));
	analog_write_resolution = bits;
	recordAnalogSuccess();
	static_cast<void>(k_mutex_unlock(&analog_mutex));
}

extern "C" bool analogWriteFrequency(pin_size_t pin, std::uint32_t frequency_hz)
{
	if (k_is_in_isr())
	{
		recordAnalogError(AnalogError::invalid_context);
		return false;
	}
	std::uint32_t period_ns = 0U;
	if (!nucode::arduino::internal::frequencyToPeriodNanoseconds(
			frequency_hz, period_ns))
	{
		recordAnalogError(AnalogError::invalid_value);
		return false;
	}

	const std::size_t canonical = nucode::arduino::internal::canonicalPinId(pin);
	if (canonical >= NUM_PIN_ROLES ||
		!nucode::arduino::internal::pwmRuntimePinSupported(
			PwmRuntimeClient::analog_write, static_cast<pin_size_t>(canonical)))
	{
		recordAnalogError(AnalogError::invalid_pin);
		return false;
	}

	static_cast<void>(k_mutex_lock(&analog_mutex, K_FOREVER));
	if (nucode::arduino::internal::pwmRuntimeActive(
			PwmRuntimeClient::analog_write, static_cast<pin_size_t>(canonical)))
	{
		const PwmRuntimeResult result =
			nucode::arduino::internal::pwmRuntimeRetune(
				PwmRuntimeClient::analog_write,
				static_cast<pin_size_t>(canonical), period_ns);
		if (result != PwmRuntimeResult::success)
		{
			recordPwmResult(result);
			static_cast<void>(k_mutex_unlock(&analog_mutex));
			return false;
		}
	}
	analog_write_frequencies[canonical] = frequency_hz;
	recordAnalogSuccess();
	static_cast<void>(k_mutex_unlock(&analog_mutex));
	return true;
}

extern "C" void analogWrite(pin_size_t pin, int value)
{
	if (k_is_in_isr())
	{
		recordAnalogError(AnalogError::invalid_context);
		return;
	}

	static_cast<void>(k_mutex_lock(&analog_mutex, K_FOREVER));
	const std::uint32_t maximum =
		nucode::arduino::internal::analogResolutionMaximum(analog_write_resolution);
	if (value < 0 || static_cast<std::uint32_t>(value) > maximum)
	{
		recordAnalogError(AnalogError::invalid_value);
		static_cast<void>(k_mutex_unlock(&analog_mutex));
		return;
	}
	const std::size_t canonical = nucode::arduino::internal::canonicalPinId(pin);
	if (canonical >= NUM_PIN_ROLES)
	{
		recordAnalogError(AnalogError::invalid_pin);
		static_cast<void>(k_mutex_unlock(&analog_mutex));
		return;
	}

	std::uint32_t period_ns = 0U;
	const std::uint32_t frequency_hz = analogWriteFrequencyForPin(canonical);
	if (!nucode::arduino::internal::frequencyToPeriodNanoseconds(
			frequency_hz, period_ns))
	{
		recordAnalogError(AnalogError::invalid_value);
		static_cast<void>(k_mutex_unlock(&analog_mutex));
		return;
	}
	const std::uint32_t pulse_ns =
		nucode::arduino::internal::scaleAnalogDutyToPulse(
			period_ns, static_cast<std::uint32_t>(value),
			analog_write_resolution);
	const PwmRuntimeResult result = nucode::arduino::internal::pwmRuntimeWrite(
		PwmRuntimeClient::analog_write, static_cast<pin_size_t>(canonical),
		period_ns, pulse_ns);
	recordPwmResult(result);
	static_cast<void>(k_mutex_unlock(&analog_mutex));
}

void tone(std::uint8_t pin, unsigned int frequency, unsigned long duration)
{
	if (k_is_in_isr())
	{
		recordAnalogError(AnalogError::invalid_context);
		return;
	}
	if (frequency == 0U)
	{
		noTone(pin);
		return;
	}

	std::uint32_t period_ns = 0U;
	if (!nucode::arduino::internal::frequencyToPeriodNanoseconds(
			static_cast<std::uint32_t>(frequency), period_ns))
	{
		recordAnalogError(AnalogError::invalid_value);
		return;
	}
	const std::size_t canonical = nucode::arduino::internal::canonicalPinId(pin);
	if (canonical >= NUM_PIN_ROLES)
	{
		recordAnalogError(AnalogError::invalid_pin);
		return;
	}

	static_cast<void>(k_mutex_lock(&tone_api_mutex, K_FOREVER));
	struct k_work_sync sync{};
	static_cast<void>(k_work_cancel_delayable_sync(&tone_stop_work, &sync));
	static_cast<void>(k_mutex_lock(&tone_state_mutex, K_FOREVER));
	++tone_state.generation;
	stopToneLocked();
	if (tone_state.active)
	{
		static_cast<void>(k_mutex_unlock(&tone_state_mutex));
		static_cast<void>(k_mutex_unlock(&tone_api_mutex));
		return;
	}

	const PwmRuntimeResult result = nucode::arduino::internal::pwmRuntimeWrite(
		PwmRuntimeClient::tone, static_cast<pin_size_t>(canonical), period_ns,
		period_ns / 2U);
	if (result == PwmRuntimeResult::success)
	{
		tone_state.pin = static_cast<pin_size_t>(canonical);
		tone_state.active = true;
		tone_state.scheduled_generation = tone_state.generation;
		recordAnalogSuccess();
		if (duration != 0UL)
		{
			static_cast<void>(k_work_reschedule(
				&tone_stop_work,
				K_MSEC(static_cast<std::int64_t>(duration))));
		}
	}
	else
	{
		recordPwmResult(result);
	}
	static_cast<void>(k_mutex_unlock(&tone_state_mutex));
	static_cast<void>(k_mutex_unlock(&tone_api_mutex));
}

void noTone(std::uint8_t pin)
{
	if (k_is_in_isr())
	{
		recordAnalogError(AnalogError::invalid_context);
		return;
	}
	const std::size_t canonical = nucode::arduino::internal::canonicalPinId(pin);
	if (canonical >= NUM_PIN_ROLES)
	{
		recordAnalogError(AnalogError::invalid_pin);
		return;
	}

	static_cast<void>(k_mutex_lock(&tone_api_mutex, K_FOREVER));
	struct k_work_sync sync{};
	static_cast<void>(k_work_cancel_delayable_sync(&tone_stop_work, &sync));
	static_cast<void>(k_mutex_lock(&tone_state_mutex, K_FOREVER));
	++tone_state.generation;
	if (tone_state.active &&
		tone_state.pin == static_cast<pin_size_t>(canonical))
	{
		stopToneLocked();
	}
	else
	{
		recordAnalogSuccess();
	}
	static_cast<void>(k_mutex_unlock(&tone_state_mutex));
	static_cast<void>(k_mutex_unlock(&tone_api_mutex));
}

#endif

namespace nucode::arduino::internal
{
	AnalogError lastAnalogError() noexcept
	{
		return static_cast<AnalogError>(atomic_get(&last_analog_error));
	}

	int lastAnalogDriverError() noexcept
	{
		return static_cast<int>(atomic_get(&last_analog_driver_error));
	}

	void clearAnalogDiagnostics() noexcept
	{
		recordAnalogSuccess();
	}
}

#if defined(CONFIG_NUCODE_ARDUINO_ADC)
#undef NUCODE_ADC_SPEC_AND_COMMA
#undef NUCODE_ARDUINO_ADC_NODE
#endif
