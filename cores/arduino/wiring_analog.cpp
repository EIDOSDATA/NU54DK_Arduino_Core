/**
 * @file wiring_analog.cpp
 * @brief NU54DK Devicetree 역할 위에 Arduino analog API를 구현합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <Arduino.h>

#include <zephyr/device.h>
#include <zephyr/devicetree.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/atomic.h>

#if defined(CONFIG_NUCODE_ARDUINO_ADC)
#include <zephyr/drivers/adc.h>
#endif

#if defined(CONFIG_NUCODE_ARDUINO_PWM)
#include <zephyr/drivers/pwm.h>
#endif

#include <cstdint>

#include "internal/AnalogBackend.h"

#if defined(CONFIG_NUCODE_ARDUINO_ADC)

#if !DT_HAS_CHOSEN(nucode_arduino_adc)
#error "analogRead에는 io-channels를 가진 nucode,arduino-adc chosen node가 필요합니다."
#endif

#define NUCODE_ARDUINO_ADC_NODE DT_CHOSEN(nucode_arduino_adc)

#if !DT_NODE_HAS_PROP(NUCODE_ARDUINO_ADC_NODE, io_channels)
#error "nucode,arduino-adc chosen node에는 io-channels 속성이 필요합니다."
#endif

#endif

#if defined(CONFIG_NUCODE_ARDUINO_PWM)

#if !DT_HAS_CHOSEN(nucode_arduino_pwm)
#error "analogWrite에는 pwms 역할을 가진 nucode,arduino-pwm chosen node가 필요합니다."
#endif

#define NUCODE_ARDUINO_PWM_NODE DT_CHOSEN(nucode_arduino_pwm)

#if !DT_NODE_HAS_STATUS_OKAY(NUCODE_ARDUINO_PWM_NODE)
#error "nucode,arduino-pwm chosen 대상이 활성화되어 있지 않습니다."
#elif !DT_NODE_HAS_PROP(NUCODE_ARDUINO_PWM_NODE, pwms)
#error "nucode,arduino-pwm chosen 대상에는 pwms 속성이 필요합니다."
#endif

#endif

namespace
{

	using nucode::arduino::internal::AnalogError;

	K_MUTEX_DEFINE(analog_mutex);

	atomic_t last_analog_error = ATOMIC_INIT(static_cast<atomic_val_t>(AnalogError::none));
	atomic_t last_analog_driver_error = ATOMIC_INIT(0);

#if defined(CONFIG_NUCODE_ARDUINO_ADC)
	/** @brief app overlay가 channel 5/P1.12 역할로 선택한 ADC spec입니다. */
	const struct adc_dt_spec adc_input = ADC_DT_SPEC_GET(NUCODE_ARDUINO_ADC_NODE);

	bool adc_channel_configured = false;
#endif

#if defined(CONFIG_NUCODE_ARDUINO_PWM)
	/** @brief board pwm_led1/P1.10 chosen이 가리키는 PWM 역할입니다. */
	const struct pwm_dt_spec pwm_output = PWM_DT_SPEC_GET(NUCODE_ARDUINO_PWM_NODE);

	/** @brief NU54DK pwm_led1 DTS가 선언해야 하는 고정 20 ms 주기입니다. */
	constexpr std::uint32_t required_pwm_period = PWM_MSEC(20U);
#endif

	/**
	 * @brief analog 진단 상태를 원자적으로 기록합니다.
	 *
	 * @param error Core 내부 오류입니다.
	 * @param driver_error Zephyr ADC/PWM가 반환한 오류입니다.
	 */
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

#if defined(CONFIG_NUCODE_ARDUINO_ADC)
	/**
	 * @brief chosen io-channel이 NU54DK A0 고정 계약과 같은지 확인합니다.
	 *
	 * @return channel 5, 12-bit, internal reference, 1/4 gain이면 true입니다.
	 */
	[[nodiscard]] bool adcDevicetreeContractMatches() noexcept
	{
		return adc_input.channel_cfg_dt_node_exists &&
			   (adc_input.channel_id == 5U) &&
			   (adc_input.resolution ==
				static_cast<std::uint8_t>(nucode::arduino::internal::analog_read_resolution_bits)) &&
			   (adc_input.channel_cfg.reference == ADC_REF_INTERNAL) &&
			   (adc_input.channel_cfg.gain == ADC_GAIN_1_4);
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

extern "C" int analogRead(pin_size_t pin)
{
	if (k_is_in_isr())
	{
		recordAnalogError(AnalogError::invalid_context);
		return -1;
	}
	if (pin != PIN_A0)
	{
		recordAnalogError(AnalogError::invalid_pin);
		return -1;
	}

	static_cast<void>(k_mutex_lock(&analog_mutex, K_FOREVER));
	if (!adc_is_ready_dt(&adc_input))
	{
		recordAnalogError(AnalogError::device_not_ready);
		static_cast<void>(k_mutex_unlock(&analog_mutex));
		return -1;
	}
	if (!adcDevicetreeContractMatches())
	{
		recordAnalogError(AnalogError::unsupported_devicetree);
		static_cast<void>(k_mutex_unlock(&analog_mutex));
		return -1;
	}

	if (!adc_channel_configured)
	{
		const int setup_result = adc_channel_setup_dt(&adc_input);
		if (setup_result < 0)
		{
			recordAnalogError(AnalogError::driver_error, setup_result);
			static_cast<void>(k_mutex_unlock(&analog_mutex));
			return -1;
		}
		adc_channel_configured = true;
	}

	std::int16_t sample = 0;
	struct adc_sequence sequence = {};
	const int sequence_result = adc_sequence_init_dt(&adc_input, &sequence);
	if (sequence_result < 0)
	{
		recordAnalogError(AnalogError::driver_error, sequence_result);
		static_cast<void>(k_mutex_unlock(&analog_mutex));
		return -1;
	}
	sequence.buffer = &sample;
	sequence.buffer_size = sizeof(sample);

	const int read_result = adc_read_dt(&adc_input, &sequence);
	if (read_result < 0)
	{
		recordAnalogError(AnalogError::driver_error, read_result);
		static_cast<void>(k_mutex_unlock(&analog_mutex));
		return -1;
	}

	constexpr int maximum_raw_value =
		(1 << nucode::arduino::internal::analog_read_resolution_bits) - 1;
	int result = static_cast<int>(sample);
	if (result < 0)
	{
		result = 0;
	}
	else if (result > maximum_raw_value)
	{
		result = maximum_raw_value;
	}

	recordAnalogSuccess();
	static_cast<void>(k_mutex_unlock(&analog_mutex));
	return result;
}

#endif

#if defined(CONFIG_NUCODE_ARDUINO_PWM)

extern "C" void analogWrite(pin_size_t pin, int value)
{
	if (k_is_in_isr())
	{
		recordAnalogError(AnalogError::invalid_context);
		return;
	}
	if (pin != PIN_PWM0)
	{
		recordAnalogError(AnalogError::invalid_pin);
		return;
	}
	if ((value < 0) || (value > 255))
	{
		recordAnalogError(AnalogError::invalid_value);
		return;
	}

	static_cast<void>(k_mutex_lock(&analog_mutex, K_FOREVER));
	if (!pwm_is_ready_dt(&pwm_output))
	{
		recordAnalogError(AnalogError::device_not_ready);
		static_cast<void>(k_mutex_unlock(&analog_mutex));
		return;
	}
	if (pwm_output.period != required_pwm_period)
	{
		recordAnalogError(AnalogError::unsupported_devicetree);
		static_cast<void>(k_mutex_unlock(&analog_mutex));
		return;
	}

	std::uint32_t pulse = 0U;
	if (value == 255)
	{
		pulse = pwm_output.period;
	}
	else if (value != 0)
	{
		const std::uint64_t scaled =
			(static_cast<std::uint64_t>(pwm_output.period) *
			 static_cast<std::uint32_t>(value)) +
			127U;
		pulse = static_cast<std::uint32_t>(scaled / 255U);
	}

	const int result = pwm_set_pulse_dt(&pwm_output, pulse);
	if (result < 0)
	{
		recordAnalogError(AnalogError::driver_error, result);
	}
	else
	{
		recordAnalogSuccess();
	}
	static_cast<void>(k_mutex_unlock(&analog_mutex));
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
#undef NUCODE_ARDUINO_ADC_NODE
#endif

#if defined(CONFIG_NUCODE_ARDUINO_PWM)
#undef NUCODE_ARDUINO_PWM_NODE
#endif
