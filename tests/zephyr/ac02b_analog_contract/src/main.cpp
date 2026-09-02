/**
 * @file main.cpp
 * @brief AC-02B ADC/PWM/tone/Servo runtime 계약을 target에서 자동 검증합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <Arduino.h>
#include <Servo.h>

#include <zephyr/device.h>
#include <zephyr/drivers/adc/adc_emul.h>
#include <zephyr/drivers/pwm/pwm_fake.h>
#include <zephyr/fff.h>
#include <zephyr/kernel.h>
#include <zephyr/ztest.h>

#include <cstddef>
#include <cstdint>
#include <errno.h>

#include "internal/AnalogBackend.h"
#include "internal/PinHandover.h"
#include "internal/PwmRuntime.h"
#include "internal/pin_description.h"

/** @brief Zephyr fake PWM driver가 사용하는 FFF 전역 상태입니다. */
DEFINE_FFF_GLOBALS;

/** @brief Core 공개 header 통합 전에도 구현의 C ABI를 검증합니다. */
extern "C" void analogReadResolution(std::uint8_t bits);
/** @brief Core 공개 header 통합 전에도 구현의 C ABI를 검증합니다. */
extern "C" void analogWriteResolution(std::uint8_t bits);
/** @brief Core 공개 header 통합 전에도 구현의 C ABI를 검증합니다. */
extern "C" bool analogWriteFrequency(pin_size_t pin, std::uint32_t frequency_hz);

namespace
{
	using nucode::arduino::internal::AnalogError;
	using nucode::arduino::internal::PwmRuntimeBlock;
	using nucode::arduino::internal::PwmRuntimeClient;
	using nucode::arduino::internal::PwmRuntimeResult;
	using nucode::arduino::internal::PwmRuntimeRouteBackend;
	using nucode::arduino::internal::PwmRuntimeRouteSet;

	/** @brief ADC emulator 장치입니다. */
	const struct device *const adc_device = DEVICE_DT_GET(DT_NODELABEL(ac02b_adc));
	/** @brief analogWrite용 fake PWM20 장치입니다. */
	const struct device *const pwm20_device = DEVICE_DT_GET(DT_NODELABEL(ac02b_pwm20));
	/** @brief tone용 fake PWM21 장치입니다. */
	const struct device *const pwm21_device = DEVICE_DT_GET(DT_NODELABEL(ac02b_pwm21));
	/** @brief Servo용 fake PWM22 장치입니다. */
	const struct device *const pwm22_device = DEVICE_DT_GET(DT_NODELABEL(ac02b_pwm22));

	/** @brief fake route backend의 block별 관측값입니다. */
	struct RouteObservation
	{
		PwmRuntimeRouteSet active_routes{};
		PwmRuntimeResult next_apply_result{PwmRuntimeResult::success};
		int last_driver_error{0};
		std::uint32_t apply_count{0U};
		std::uint32_t clear_count{0U};
	};

	RouteObservation route_observations[3]{};

#if defined(CONFIG_NUCODE_ARDUINO_INTERRUPTS)
	/** @brief faulted 핀의 interrupt 등록 거부를 확인하는 무동작 callback입니다. */
	void faultedPinCallback()
	{
	}
#endif

	/** @brief PWM instance를 관측 배열 index로 변환합니다. */
	[[nodiscard]] constexpr int blockIndex(std::uint8_t instance) noexcept
	{
		return instance >= 20U && instance <= 22U
				   ? static_cast<int>(instance - 20U)
				   : -1;
	}

	/** @brief allocator 시험에 허용할 고정 논리 핀 집합입니다. */
	[[nodiscard]] bool routeSupports(pin_size_t pin,
									 std::uint8_t instance) noexcept
	{
		if (blockIndex(instance) < 0)
		{
			return false;
		}
		const pin_size_t supported[] = {
			PIN_PWM0,
			PIN_LED3,
			PIN_P1_02,
			PIN_P1_03,
			PIN_P2_00,
		};
		for (const pin_size_t candidate : supported)
		{
			if (candidate == pin)
			{
				return true;
			}
		}
		return false;
	}

	/** @brief instance에 대응하는 fake PWM 장치를 반환합니다. */
	[[nodiscard]] PwmRuntimeResult routeBlock(
		std::uint8_t instance, PwmRuntimeBlock &block) noexcept
	{
		switch (instance)
		{
		case 20U:
			block = {pwm20_device, 0U};
			return PwmRuntimeResult::success;
		case 21U:
			block = {pwm21_device, 0U};
			return PwmRuntimeResult::success;
		case 22U:
			block = {pwm22_device, 0U};
			return PwmRuntimeResult::success;
		default:
			return PwmRuntimeResult::invalid_argument;
		}
	}

	/** @brief 전체 route 적용을 관측하고 한 번의 오류 주입을 지원합니다. */
	[[nodiscard]] PwmRuntimeResult routeApply(
		std::uint8_t instance, const PwmRuntimeRouteSet &routes) noexcept
	{
		const int index = blockIndex(instance);
		if (index < 0 || routes.count == 0U || routes.count > 4U)
		{
			return PwmRuntimeResult::invalid_argument;
		}
		RouteObservation &observation = route_observations[index];
		++observation.apply_count;
		const PwmRuntimeResult result = observation.next_apply_result;
		observation.next_apply_result = PwmRuntimeResult::success;
		if (result == PwmRuntimeResult::success)
		{
			observation.active_routes = routes;
			observation.last_driver_error = 0;
		}
		return result;
	}

	/** @brief block route 전체를 비우고 관측합니다. */
	[[nodiscard]] PwmRuntimeResult routeClear(std::uint8_t instance) noexcept
	{
		const int index = blockIndex(instance);
		if (index < 0)
		{
			return PwmRuntimeResult::invalid_argument;
		}
		RouteObservation &observation = route_observations[index];
		++observation.clear_count;
		observation.active_routes = {};
		observation.last_driver_error = 0;
		return PwmRuntimeResult::success;
	}

	/** @brief 마지막 fake route errno를 반환합니다. */
	[[nodiscard]] int routeDriverError(std::uint8_t instance) noexcept
	{
		const int index = blockIndex(instance);
		return index >= 0 ? route_observations[index].last_driver_error : -EINVAL;
	}

	/** @brief 각 시험 전에 allocator, fake driver와 진단을 초기화합니다. */
	void beforeEach(void *)
	{
		nucode::arduino::internal::resetPwmRuntimeForTest();
		for (auto &observation : route_observations)
		{
			observation = {};
		}
		RESET_FAKE(fake_pwm_set_cycles);
		nucode::arduino::internal::clearAnalogDiagnostics();
		const PwmRuntimeRouteBackend backend = {
			routeSupports,
			routeBlock,
			routeApply,
			routeClear,
			routeDriverError,
		};
		zassert_true(
			nucode::arduino::internal::installPwmRuntimeRouteBackend(backend),
			"fake PWM route backend를 설치하지 못했습니다.");
	}
}

ZTEST(ac02b_analog, test_required_runtime_configuration)
{
	zassert_true(IS_ENABLED(CONFIG_PINCTRL_DYNAMIC),
				 "동적 pinctrl이 활성화되어야 합니다.");
	zassert_true(IS_ENABLED(CONFIG_PINCTRL_KEEP_SLEEP_STATE),
				 "sleep pinctrl state가 보존되어야 합니다.");
	zassert_true(IS_ENABLED(CONFIG_PM_DEVICE),
				 "device PM이 활성화되어야 합니다.");
	zassert_true(IS_ENABLED(CONFIG_PM_DEVICE_RUNTIME),
				 "runtime device PM이 활성화되어야 합니다.");
	zassert_true(device_is_ready(pwm20_device), "PWM20 fake 장치가 준비되지 않았습니다.");
	zassert_true(device_is_ready(pwm21_device), "PWM21 fake 장치가 준비되지 않았습니다.");
	zassert_true(device_is_ready(pwm22_device), "PWM22 fake 장치가 준비되지 않았습니다.");
}

ZTEST(ac02b_analog, test_fail_closed_handover_releases_transition_mutex)
{
	using nucode::arduino::internal::GpioPinHandover;
	using nucode::arduino::internal::IoOwnerKind;
	using nucode::arduino::internal::PinHandoverPhase;
	using nucode::arduino::internal::PinHandoverResult;

	pinMode(PIN_BUTTON2, INPUT_PULLUP);
	GpioPinHandover handover{};
	zassert_equal(nucode::arduino::internal::beginGpioPinHandover(
					  PIN_BUTTON2, {IoOwnerKind::pwm, 99U}, handover),
				  PinHandoverResult::success, "fail-closed 시험 handover 준비에 실패했습니다.");
	zassert_true(handover.lock_held, "prepared handover가 전환 mutex를 보유하지 않습니다.");
	zassert_equal(nucode::arduino::internal::abandonGpioPinHandoverFailClosed(handover),
				  PinHandoverResult::success, "fail-closed handover 전환에 실패했습니다.");
	zassert_equal(handover.phase, PinHandoverPhase::faulted,
				  "복구 불가능한 handover가 faulted로 보존되지 않았습니다.");
	zassert_false(handover.lock_held, "fail-closed handover가 전환 mutex를 남겼습니다.");
	zassert_true(nucode::arduino::internal::isGpioPinHandoverFaulted(PIN_BUTTON2),
				 "faulted 핀이 GPIO data API 차단 상태로 기록되지 않았습니다.");
	zassert_false(nucode::arduino::internal::isPinConfiguredForInput(PIN_BUTTON2),
				  "faulted 핀이 입력 구성 완료 상태로 노출되었습니다.");
	zassert_false(nucode::arduino::internal::isPinConfiguredForOutput(PIN_BUTTON2),
				  "faulted 핀이 출력 구성 완료 상태로 노출되었습니다.");

	nucode::arduino::internal::clearGpioError();
	digitalWrite(PIN_BUTTON2, HIGH);
	zassert_equal(nucode::arduino::internal::lastGpioError(),
				  nucode::arduino::internal::GpioError::ownership_conflict,
				  "faulted 핀의 digitalWrite가 fail-closed로 거부되지 않았습니다.");
	nucode::arduino::internal::clearGpioError();
	zassert_equal(digitalRead(PIN_BUTTON2), LOW,
				  "faulted 핀의 digitalRead 실패 기본값이 LOW가 아닙니다.");
	zassert_equal(nucode::arduino::internal::lastGpioError(),
				  nucode::arduino::internal::GpioError::ownership_conflict,
				  "faulted 핀의 digitalRead가 fail-closed로 거부되지 않았습니다.");
#if defined(CONFIG_NUCODE_ARDUINO_INTERRUPTS)
	nucode::arduino::internal::clearGpioError();
	attachInterrupt(PIN_BUTTON2, faultedPinCallback, RISING);
	zassert_equal(nucode::arduino::internal::lastGpioError(),
				  nucode::arduino::internal::GpioError::ownership_conflict,
				  "faulted 핀의 interrupt 등록이 fail-closed로 거부되지 않았습니다.");
#endif

	/** @brief 같은 thread가 mutex를 다시 얻을 수 있어야 영구 deadlock이 아닙니다. */
	nucode::arduino::internal::lockGpioTransition();
	nucode::arduino::internal::unlockGpioTransition();
}

ZTEST(ac02b_analog, test_adc_alias_resolution_and_ownership_policy)
{
	static_assert(A0 == PIN_AIN5);
	static_assert(A1 == PIN_AIN0);
	static_assert(A7 == PIN_AIN7);
	static_assert(NUM_ANALOG_INPUTS == 8U);
	zassert_true(device_is_ready(adc_device), "ADC emulator가 준비되지 않았습니다.");

	const std::uint8_t channels[] = {5U, 6U, 7U};
	const pin_size_t pins[] = {A0, A6, A7};
	const std::uint8_t resolutions[] = {8U, 10U, 12U, 14U};
	for (const std::uint8_t bits : resolutions)
	{
		const std::uint32_t raw = (static_cast<std::uint32_t>(1U) << bits) - 1U;
		analogReadResolution(bits);
		for (std::size_t index = 0U; index < 3U; ++index)
		{
			zassert_ok(adc_emul_const_raw_value_set(adc_device, channels[index], raw),
					   "ADC emulator 값을 설정하지 못했습니다.");
			zassert_equal(analogRead(pins[index]), static_cast<int>(raw),
						  "공개 ADC 별칭의 해상도 결과가 다릅니다.");
		}
	}

	analogReadResolution(9U);
	zassert_equal(nucode::arduino::internal::lastAnalogError(),
				  AnalogError::invalid_value, "9-bit ADC 요청이 거부되지 않았습니다.");
	zassert_equal(analogRead(A1), -1,
				  "UART20이 소유한 AIN0을 ADC가 강제 탈취했습니다.");
	zassert_equal(analogRead(A5), -1,
				  "PMIC INT가 소유한 AIN4를 ADC가 강제 탈취했습니다.");

	pinMode(A7, OUTPUT);
	zassert_equal(analogRead(A7), -1,
				  "출력으로 구성한 GPIO가 암묵적으로 ADC로 전환되었습니다.");
	zassert_equal(nucode::arduino::internal::lastAnalogDriverError(), -EBUSY,
				  "GPIO output과 ADC 충돌 errno가 다릅니다.");
	pinMode(A7, INPUT);
}

ZTEST(ac02b_analog, test_analog_write_resolution_period_and_capacity)
{
	const pin_size_t pins[] = {
		PIN_PWM0,
		PIN_LED3,
		PIN_P1_02,
		PIN_P1_03,
		PIN_P2_00,
	};
	analogWriteResolution(16U);
	for (const pin_size_t pin : pins)
	{
		zassert_true(analogWriteFrequency(pin, 1000U),
					 "1 kHz analogWrite 주파수 설정에 실패했습니다.");
	}

	analogWrite(pins[0], 32768);
	zassert_equal(nucode::arduino::internal::lastAnalogError(), AnalogError::none,
				  "16-bit analogWrite가 실패했습니다.");
	zassert_equal(route_observations[0].active_routes.count, 1U,
				  "PWM20 첫 route가 적용되지 않았습니다.");
	zassert_equal(fake_pwm_set_cycles_fake.arg2_val, 1000U,
				  "1 kHz period가 fake PWM cycle로 변환되지 않았습니다.");

	for (std::size_t index = 1U; index < 4U; ++index)
	{
		analogWrite(pins[index], 16384);
		zassert_equal(nucode::arduino::internal::lastAnalogError(), AnalogError::none,
					  "PWM20의 네 channel을 채우지 못했습니다.");
	}
	zassert_equal(route_observations[0].active_routes.count, 4U,
				  "PWM20 route 수가 4가 아닙니다.");
	analogWrite(pins[4], 8192);
	zassert_equal(nucode::arduino::internal::lastAnalogDriverError(), -ENOSPC,
				  "PWM20 다섯 번째 channel이 capacity 오류가 아닙니다.");
	zassert_false(analogWriteFrequency(pins[0], 2000U),
				  "공유 block의 활성 주기 충돌이 허용되었습니다.");
	zassert_equal(nucode::arduino::internal::lastAnalogDriverError(), -EBUSY,
				  "공유 주기 충돌 errno가 다릅니다.");

	for (std::size_t index = 0U; index < 4U; ++index)
	{
		zassert_equal(nucode::arduino::internal::pwmRuntimeStop(
						  PwmRuntimeClient::analog_write, pins[index]),
					  PwmRuntimeResult::success,
					  "PWM20 channel을 정리하지 못했습니다.");
	}
}

ZTEST(ac02b_analog, test_allocator_route_failure_is_transactional)
{
	zassert_equal(nucode::arduino::internal::pwmRuntimeWrite(
					  PwmRuntimeClient::analog_write, PIN_PWM0, 1000000U, 500000U),
				  PwmRuntimeResult::success, "기준 PWM route를 만들지 못했습니다.");
	route_observations[0].next_apply_result = PwmRuntimeResult::route_error;
	route_observations[0].last_driver_error = -EIO;
	zassert_equal(nucode::arduino::internal::pwmRuntimeWrite(
					  PwmRuntimeClient::analog_write, PIN_LED3, 1000000U, 250000U),
				  PwmRuntimeResult::route_error, "route 오류 주입 결과가 보존되지 않았습니다.");
	zassert_true(nucode::arduino::internal::pwmRuntimeActive(
					 PwmRuntimeClient::analog_write, PIN_PWM0),
				 "route 실패가 기존 PWM channel을 잃었습니다.");
	zassert_false(nucode::arduino::internal::pwmRuntimeActive(
					  PwmRuntimeClient::analog_write, PIN_LED3),
				  "route 실패가 새 PWM channel을 활성화했습니다.");
	zassert_equal(route_observations[0].active_routes.count, 1U,
				  "route 실패 후 backend의 이전 route가 보존되지 않았습니다.");
}

ZTEST(ac02b_analog, test_output_restore_failure_latches_pwm_block)
{
	zassert_equal(nucode::arduino::internal::pwmRuntimeWrite(
					  PwmRuntimeClient::analog_write, PIN_PWM0, 1000000U, 500000U),
				  PwmRuntimeResult::success, "fatal latch 기준 PWM 출력에 실패했습니다.");

	fake_pwm_set_cycles_fake.return_val = -EIO;
	zassert_equal(nucode::arduino::internal::pwmRuntimeWrite(
					  PwmRuntimeClient::analog_write, PIN_LED3, 1000000U, 250000U),
				  PwmRuntimeResult::route_error,
				  "출력 정지와 복원이 함께 실패했는데 route_error가 아닙니다.");
	fake_pwm_set_cycles_fake.return_val = 0;
	zassert_equal(nucode::arduino::internal::pwmRuntimeWrite(
					  PwmRuntimeClient::analog_write, PIN_LED3, 1000000U, 250000U),
				  PwmRuntimeResult::route_error,
				  "복구 실패한 PWM block이 다시 사용되었습니다.");
	zassert_true(nucode::arduino::internal::pwmRuntimeActive(
					 PwmRuntimeClient::analog_write, PIN_PWM0),
				 "fatal latch가 마지막 논리 slot 상태까지 삭제했습니다.");
}

ZTEST(ac02b_analog, test_pin_mode_reclaims_analog_write_route)
{
	analogWriteResolution(8U);
	analogWrite(PIN_PWM0, 128);
	zassert_true(nucode::arduino::internal::pwmRuntimeActive(
					 PwmRuntimeClient::analog_write, PIN_PWM0),
				 "pinMode 전 analogWrite route가 활성화되지 않았습니다.");

	pinMode(PIN_PWM0, OUTPUT);
	zassert_false(nucode::arduino::internal::pwmRuntimeActive(
					  PwmRuntimeClient::analog_write, PIN_PWM0),
				  "pinMode가 기존 analogWrite route를 종료하지 않았습니다.");
	zassert_equal(route_observations[0].clear_count, 1U,
				  "PWM20 마지막 channel의 route clear가 호출되지 않았습니다.");

	digitalWrite(PIN_PWM0, HIGH);
	zassert_equal(digitalRead(PIN_PWM0), HIGH,
				  "pinMode 후 GPIO output을 사용할 수 없습니다.");
}

ZTEST(ac02b_analog, test_pin_mode_preflight_and_pwm_resume_are_transactional)
{
	analogWriteResolution(8U);
	analogWrite(PIN_PWM0, 96);
	zassert_true(nucode::arduino::internal::pwmRuntimeActive(
					 PwmRuntimeClient::analog_write, PIN_PWM0),
				 "사전 조건용 analogWrite route가 활성화되지 않았습니다.");

	pinMode(PIN_PWM0, static_cast<PinMode>(0x7FU));
	zassert_true(nucode::arduino::internal::pwmRuntimeActive(
					 PwmRuntimeClient::analog_write, PIN_PWM0),
				 "잘못된 pinMode가 사전 검증 전에 PWM를 제거했습니다.");

	nucode::arduino::internal::PwmRuntimeSuspendedOutput snapshot{};
	zassert_equal(nucode::arduino::internal::pwmRuntimeSuspend(
					  PwmRuntimeClient::analog_write, PIN_PWM0, snapshot),
				  PwmRuntimeResult::success, "PWM snapshot 중지에 실패했습니다.");
	zassert_true(snapshot.valid, "중지 snapshot이 보존되지 않았습니다.");
	zassert_false(nucode::arduino::internal::pwmRuntimeActive(
					  PwmRuntimeClient::analog_write, PIN_PWM0),
				  "중지 뒤 allocator slot이 남았습니다.");

	route_observations[0].next_apply_result = PwmRuntimeResult::route_error;
	route_observations[0].last_driver_error = -EIO;
	zassert_equal(nucode::arduino::internal::pwmRuntimeResume(snapshot),
				  PwmRuntimeResult::route_error, "복원 오류 주입 결과가 보존되지 않았습니다.");
	zassert_true(snapshot.valid, "실패한 복원이 snapshot을 폐기했습니다.");
	zassert_equal(nucode::arduino::internal::pwmRuntimeResume(snapshot),
				  PwmRuntimeResult::success, "보존한 snapshot 재시도에 실패했습니다.");
	zassert_false(snapshot.valid, "성공한 복원이 snapshot을 남겼습니다.");
	zassert_true(nucode::arduino::internal::pwmRuntimeActive(
					 PwmRuntimeClient::analog_write, PIN_PWM0),
				 "재시도 뒤 PWM 출력이 복원되지 않았습니다.");
}

ZTEST(ac02b_analog, test_tone_duration_generation_and_single_channel)
{
	tone(PIN_PWM0, 1000U, 20UL);
	zassert_true(nucode::arduino::internal::pwmRuntimeActive(
					 PwmRuntimeClient::tone, PIN_PWM0),
				 "유한 tone이 시작되지 않았습니다.");
	k_sleep(K_MSEC(5));
	tone(PIN_LED3, 2000U, 0UL);
	zassert_false(nucode::arduino::internal::pwmRuntimeActive(
					  PwmRuntimeClient::tone, PIN_PWM0),
				  "재시작 전 tone이 남았습니다.");
	zassert_true(nucode::arduino::internal::pwmRuntimeActive(
					 PwmRuntimeClient::tone, PIN_LED3),
				 "새 무기한 tone이 시작되지 않았습니다.");
	k_sleep(K_MSEC(30));
	zassert_true(nucode::arduino::internal::pwmRuntimeActive(
					 PwmRuntimeClient::tone, PIN_LED3),
				 "이전 duration work가 새 generation tone을 중지했습니다.");
	noTone(PIN_LED3);
	zassert_false(nucode::arduino::internal::pwmRuntimeActive(
					  PwmRuntimeClient::tone, PIN_LED3),
				  "noTone이 출력을 중지하지 못했습니다.");
}

ZTEST(ac02b_analog, test_servo_four_channel_fixed_capacity)
{
	Servo servos[5];
	const int pins[] = {PIN_PWM0, PIN_LED3, PIN_P1_02, PIN_P1_03, PIN_P2_00};
	for (std::size_t index = 0U; index < 4U; ++index)
	{
		zassert_not_equal(servos[index].attach(pins[index]), INVALID_SERVO,
						  "PWM22 Servo channel을 attach하지 못했습니다.");
		servos[index].write(90);
		zassert_equal(servos[index].read(), 90,
					  "Servo 각도와 pulse 변환이 다릅니다.");
	}
	zassert_equal(servos[4].attach(pins[4]), INVALID_SERVO,
				  "PWM22의 다섯 번째 Servo channel이 허용되었습니다.");
	zassert_equal(route_observations[2].active_routes.count, 4U,
				  "PWM22 route 수가 4가 아닙니다.");
	for (std::size_t index = 0U; index < 4U; ++index)
	{
		servos[index].detach();
		zassert_false(servos[index].attached(), "Servo detach가 완료되지 않았습니다.");
	}
}

ZTEST_SUITE(ac02b_analog, nullptr, nullptr, beforeEach, nullptr, nullptr);
