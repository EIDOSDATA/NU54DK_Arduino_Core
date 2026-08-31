/**
 * @file main.cpp
 * @brief P2.5/P2.6 loopback과 SW0 자기구동으로 AC-01 GPIO·IRQ 계약을 검증합니다.
 *
 * @note 시험 전에 PIN_GPIO0(P2.5)과 PIN_GPIO1(P2.6)을 점퍼 한 가닥으로 연결해야 합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <Arduino.h>

#include <zephyr/drivers/gpio.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/atomic.h>

#include <errno.h>
#include <cstdint>

#include "internal/pin_description.h"

namespace
{
	static_assert(CONFIG_NUM_COOP_PRIORITIES > 0,
				  "AC-01 pulse generator에는 유효한 cooperative priority가 필요합니다.");

	using nucode::arduino::internal::GpioError;
	using nucode::arduino::internal::lastGpioDriverError;
	using nucode::arduino::internal::lastGpioError;
	using nucode::arduino::internal::PinDescription;
	using nucode::arduino::internal::pinDescription;

	/** @brief 단일 동작과 callback 관찰의 제한 시간입니다. */
	constexpr unsigned long action_timeout_ms = 250UL;

	/** @brief 짧은 pulse 목표 폭입니다. */
	constexpr std::uint32_t short_pulse_width_us = 1500U;

	/** @brief 긴 pulse 목표 폭입니다. */
	constexpr std::uint32_t long_pulse_width_us = 20000U;

	/** @brief pulse 생성 thread가 측정 시작 뒤 기다리는 시간입니다. */
	constexpr std::uint32_t pulse_lead_us = 2000U;

	/** @brief pulse 생성 thread stack입니다. */
	K_THREAD_STACK_DEFINE(pulse_thread_stack, 1024);

	/** @brief pulse 생성 thread 상태입니다. */
	struct k_thread pulse_thread_data;

	/** @brief 현재 pulse 생성 thread가 사용할 폭입니다. */
	std::uint32_t pending_pulse_width_us = 0U;

	/** @brief level interrupt callback 누적값입니다. */
	atomic_t level_callback_count = ATOMIC_INIT(0);

	/** @brief scheduler 생존 확인용 thread 누적값입니다. */
	atomic_t heartbeat_count = ATOMIC_INIT(0);

	/** @brief heartbeat thread stack입니다. */
	K_THREAD_STACK_DEFINE(heartbeat_thread_stack, 768);

	/** @brief heartbeat thread 상태입니다. */
	struct k_thread heartbeat_thread_data;

	/** @brief heartbeat thread 종료 요청입니다. */
	atomic_t heartbeat_stop = ATOMIC_INIT(0);

	/** @brief fail-closed 상태입니다. */
	bool failed = false;

	/** @brief GPIOTE가 연결된 자동 IRQ 시험 핀입니다. */
	constexpr pin_size_t interrupt_test_pin = PIN_BUTTON0;

	/** @brief level callback에서 blocking 없이 누적값만 증가시킵니다. */
	void countLevel(void)
	{
		atomic_inc(&level_callback_count);
	}

	/** @brief pulse 생성 thread에서 P2.5를 HIGH 뒤 LOW로 구동합니다. */
	void pulseThread(void *, void *, void *)
	{
		k_sleep(K_USEC(pulse_lead_us));
		digitalWrite(PIN_GPIO0, HIGH);
		k_sleep(K_USEC(pending_pulse_width_us));
		digitalWrite(PIN_GPIO0, LOW);
	}

	/** @brief Arduino callback mask 중에도 Zephyr scheduler가 진행되는지 기록합니다. */
	void heartbeatThread(void *, void *, void *)
	{
		while (atomic_get(&heartbeat_stop) == 0)
		{
			atomic_inc(&heartbeat_count);
			k_sleep(K_MSEC(1));
		}
	}

	/**
	 * @brief 실패 단계와 Core GPIO 진단을 UART token으로 기록합니다.
	 *
	 * @param stage 실패한 고정 단계 이름입니다.
	 */
	void reportFailure(const char *stage)
	{
		failed = true;
		Serial.print("NUCODE_AC01_GPIO_HIL_FAIL:stage=");
		Serial.print(stage);
		Serial.print(":gpio_error=");
		Serial.print(static_cast<unsigned int>(lastGpioError()));
		Serial.print(":driver_error=");
		Serial.println(lastGpioDriverError());
	}

	/** @brief 마지막 GPIO API가 성공했는지 확인하고 실패 token을 기록합니다. */
	bool requireSuccess(const char *stage)
	{
		if (lastGpioError() == GpioError::none)
		{
			return true;
		}
		reportFailure(stage);
		return false;
	}

	/**
	 * @brief SW0를 입력이 연결된 open-drain 출력으로 안전하게 준비합니다.
	 *
	 * @details P2에는 nRF54L15 CPUAPP GPIOTE가 연결되지 않으므로 P2.6에서
	 * attachInterrupt를 호출하면 Zephyr driver가 -ENOTSUP을 반환합니다. SW0 P1.13은
	 * GPIOTE20에 연결되어 있습니다. HIGH는 high-Z release만 사용하므로 SW0가 우연히
	 * 눌린 상태에서도 VDD와 GND를 push-pull로 단락하지 않습니다.
	 */
	bool configureInterruptFixture(bool released_high, const char *stage)
	{
		pinMode(interrupt_test_pin, INPUT_PULLUP);
		if (!requireSuccess(stage))
		{
			return false;
		}

		const PinDescription *const description = pinDescription(interrupt_test_pin);
		if ((description == nullptr) || !gpio_is_ready_dt(&description->gpio))
		{
			reportFailure(stage);
			return false;
		}

		const gpio_flags_t initial = released_high ? GPIO_OUTPUT_HIGH : GPIO_OUTPUT_LOW;
		const int result = gpio_pin_configure(description->gpio.port,
									 description->gpio.pin,
									 GPIO_INPUT | GPIO_OUTPUT | GPIO_OPEN_DRAIN |
										 GPIO_PULL_UP | initial);
		if (result < 0)
		{
			nucode::arduino::internal::setGpioBackendError(GpioError::driver_error, result);
			reportFailure(stage);
			return false;
		}
		return true;
	}

	/** @brief SW0 open-drain 시험 핀을 LOW 구동하거나 HIGH로 release합니다. */
	bool driveInterruptFixture(int value, const char *stage)
	{
		const PinDescription *const description = pinDescription(interrupt_test_pin);
		if (description == nullptr)
		{
			reportFailure(stage);
			return false;
		}
		const int result = gpio_pin_set_raw(description->gpio.port,
									  description->gpio.pin,
									  (value == HIGH) ? 1 : 0);
		if (result < 0)
		{
			nucode::arduino::internal::setGpioBackendError(GpioError::driver_error, result);
			reportFailure(stage);
			return false;
		}
		return true;
	}

	/** @brief SW0를 원래의 pull-up 입력 상태로 복원합니다. */
	void restoreInterruptFixture(void)
	{
		pinMode(interrupt_test_pin, INPUT_PULLUP);
	}

	/** @brief 실패 경로에서도 IRQ, open-drain 상태와 보조 thread를 정리합니다. */
	class InterruptFixtureGuard
	{
	public:
		/** @brief deassert할 level mode를 저장합니다. */
		explicit InterruptFixtureGuard(PinStatus mode) noexcept : mode_(mode) {}

		/** @brief heartbeat thread가 생성되었음을 기록합니다. */
		void markHeartbeatStarted(void) noexcept
		{
			heartbeat_started_ = true;
		}

		/** @brief 성공한 noInterrupts() 한 번을 cleanup 소유권에 추가합니다. */
		void markMaskAcquired(void) noexcept
		{
			++mask_depth_;
		}

		/** @brief 성공한 interrupts() 한 번을 cleanup 소유권에서 제거합니다. */
		void markMaskReleased(void) noexcept
		{
			if (mask_depth_ > 0U)
			{
				--mask_depth_;
			}
		}

		/** @brief 정상 경로의 오류를 보고하면서 fixture를 닫습니다. */
		bool finish(const char *stage)
		{
			const bool result = cleanup();
			if (!result)
			{
				reportFailure(stage);
			}
			return result;
		}

		/** @brief 조기 반환 때도 fail-closed 정리를 수행합니다. */
		~InterruptFixtureGuard()
		{
			static_cast<void>(cleanup());
		}

		InterruptFixtureGuard(const InterruptFixtureGuard &) = delete;
		InterruptFixtureGuard &operator=(const InterruptFixtureGuard &) = delete;

	private:
		/** @brief level deassert, callback 제거, input-only 복원을 순서대로 수행합니다. */
		bool cleanup()
		{
			if (!active_)
			{
				return true;
			}
			active_ = false;

			if (heartbeat_started_)
			{
				atomic_set(&heartbeat_stop, 1);
				static_cast<void>(k_thread_join(&heartbeat_thread_data, K_MSEC(250)));
				heartbeat_started_ = false;
			}

			const PinDescription *const description = pinDescription(interrupt_test_pin);
			int release_result = -ENODEV;
			if (description != nullptr)
			{
				const int deasserted_value = (mode_ == HIGH) ? 0 : 1;
				release_result = gpio_pin_set_raw(description->gpio.port,
											  description->gpio.pin,
											  deasserted_value);
			}

			while (mask_depth_ > 0U)
			{
				interrupts();
				--mask_depth_;
			}

			detachInterrupt(digitalPinToInterrupt(interrupt_test_pin));
			const GpioError detach_error = lastGpioError();
			const int detach_driver_error = lastGpioDriverError();
			restoreInterruptFixture();

			if (release_result < 0)
			{
				nucode::arduino::internal::setGpioBackendError(
					GpioError::driver_error, release_result);
				return false;
			}
			if (detach_error != GpioError::none)
			{
				nucode::arduino::internal::setGpioBackendError(
					detach_error, detach_driver_error);
				return false;
			}
			return true;
		}

		PinStatus mode_;
		bool heartbeat_started_ = false;
		std::uint8_t mask_depth_ = 0U;
		bool active_ = true;
	};

	/** @brief callback 누적값이 제한 시간 안에 기대값 이상이 되는지 기다립니다. */
	bool waitForCount(atomic_val_t expected)
	{
		const unsigned long started = millis();
		while ((millis() - started) < action_timeout_ms)
		{
			if (atomic_get(&level_callback_count) >= expected)
			{
				return true;
			}
			delay(1UL);
		}
		return false;
	}

	/** @brief P2.6 내부 pull-up을 이용해 P2.5 open-drain low/release를 검증합니다. */
	bool testOpenDrain(void)
	{
		pinMode(PIN_GPIO1, INPUT_PULLUP);
		pinMode(PIN_GPIO0, OUTPUT_OPENDRAIN);
		if (!requireSuccess("OPEN_DRAIN_PINMODE"))
		{
			return false;
		}

		digitalWrite(PIN_GPIO0, LOW);
		delay(2UL);
		if (!requireSuccess("OPEN_DRAIN_LOW_WRITE") || (digitalRead(PIN_GPIO1) != LOW))
		{
			reportFailure("OPEN_DRAIN_LOW_READ");
			return false;
		}

		digitalWrite(PIN_GPIO0, HIGH);
		delay(2UL);
		if (!requireSuccess("OPEN_DRAIN_RELEASE_WRITE") || (digitalRead(PIN_GPIO1) != HIGH))
		{
			reportFailure("OPEN_DRAIN_RELEASE_READ");
			return false;
		}

		Serial.println("NUCODE_AC01_OPEN_DRAIN:PASS:low=LOW:released=HIGH:pullup=PIN_GPIO1_INTERNAL");
		return true;
	}

	/** @brief LOW level callback의 hold one-shot과 deassert 뒤 재무장을 검증합니다. */
	bool testLowLevel(void)
	{
		if (!configureInterruptFixture(true, "LOW_FIXTURE"))
		{
			return false;
		}
		InterruptFixtureGuard fixture(LOW);
		atomic_set(&level_callback_count, 0);
		attachInterrupt(digitalPinToInterrupt(interrupt_test_pin), countLevel, LOW);
		if (!requireSuccess("LOW_ATTACH"))
		{
			return false;
		}

		if (!driveInterruptFixture(LOW, "LOW_FIRST_DRIVE"))
		{
			return false;
		}
		if (!waitForCount(1))
		{
			reportFailure("LOW_FIRST_CALLBACK");
			return false;
		}
		delay(10UL);
		const atomic_val_t held_count = atomic_get(&level_callback_count);
		if (held_count != 1)
		{
			reportFailure("LOW_HOLD_ONE_SHOT");
			return false;
		}

		if (!driveInterruptFixture(HIGH, "LOW_DEASSERT"))
		{
			return false;
		}
		delay(5UL);
		if (!driveInterruptFixture(LOW, "LOW_REASSERT"))
		{
			return false;
		}
		if (!waitForCount(2))
		{
			reportFailure("LOW_REARM_CALLBACK");
			return false;
		}
		if (!fixture.finish("LOW_DETACH"))
		{
			return false;
		}

		Serial.println("NUCODE_AC01_LEVEL_LOW:PASS:first=1:held=1:rearmed=2");
		return true;
	}

	/** @brief HIGH level callback의 hold one-shot과 deassert 뒤 재무장을 검증합니다. */
	bool testHighLevel(void)
	{
		if (!configureInterruptFixture(false, "HIGH_FIXTURE"))
		{
			return false;
		}
		InterruptFixtureGuard fixture(HIGH);
		atomic_set(&level_callback_count, 0);
		attachInterrupt(digitalPinToInterrupt(interrupt_test_pin), countLevel, HIGH);
		if (!requireSuccess("HIGH_ATTACH"))
		{
			return false;
		}

		if (!driveInterruptFixture(HIGH, "HIGH_FIRST_RELEASE"))
		{
			return false;
		}
		if (!waitForCount(1))
		{
			reportFailure("HIGH_FIRST_CALLBACK");
			return false;
		}
		delay(10UL);
		const atomic_val_t held_count = atomic_get(&level_callback_count);
		if (held_count != 1)
		{
			reportFailure("HIGH_HOLD_ONE_SHOT");
			return false;
		}

		if (!driveInterruptFixture(LOW, "HIGH_DEASSERT"))
		{
			return false;
		}
		delay(5UL);
		if (!driveInterruptFixture(HIGH, "HIGH_REASSERT"))
		{
			return false;
		}
		if (!waitForCount(2))
		{
			reportFailure("HIGH_REARM_CALLBACK");
			return false;
		}
		if (!fixture.finish("HIGH_DETACH"))
		{
			return false;
		}

		Serial.println("NUCODE_AC01_LEVEL_HIGH:PASS:first=1:held=1:rearmed=2");
		return true;
	}

	/** @brief pulse generator thread를 시작한 뒤 지정 API로 HIGH pulse를 측정합니다. */
	unsigned long measureGeneratedPulse(std::uint32_t width_us, bool use_long_api)
	{
		pending_pulse_width_us = width_us;
		static_cast<void>(k_thread_create(
			&pulse_thread_data,
			pulse_thread_stack,
			K_THREAD_STACK_SIZEOF(pulse_thread_stack),
			pulseThread,
			nullptr,
			nullptr,
			nullptr,
			K_PRIO_COOP(0),
			0,
			K_NO_WAIT));
		const unsigned long measured = use_long_api
			? pulseInLong(PIN_GPIO1, HIGH, 100000UL)
			: pulseIn(PIN_GPIO1, HIGH, 30000UL);
		static_cast<void>(k_thread_join(&pulse_thread_data, K_MSEC(250)));
		return measured;
	}

	/** @brief pulseIn, pulseInLong과 timeout 결과를 물리 loopback에서 검증합니다. */
	bool testPulse(void)
	{
		pinMode(PIN_GPIO0, OUTPUT);
		digitalWrite(PIN_GPIO0, LOW);
		pinMode(PIN_GPIO1, INPUT_PULLDOWN);
		if (!requireSuccess("PULSE_PINMODE"))
		{
			return false;
		}

		const unsigned long short_measured = measureGeneratedPulse(short_pulse_width_us, false);
		if (!requireSuccess("PULSE_SHORT_API") || (short_measured < 500UL) ||
			(short_measured > 8000UL))
		{
			reportFailure("PULSE_SHORT_RANGE");
			return false;
		}

		const unsigned long long_measured = measureGeneratedPulse(long_pulse_width_us, true);
		if (!requireSuccess("PULSE_LONG_API") || (long_measured < 12000UL) ||
			(long_measured > 40000UL))
		{
			reportFailure("PULSE_LONG_RANGE");
			return false;
		}

		const unsigned long timed_out = pulseIn(PIN_GPIO1, HIGH, 2000UL);
		if (!requireSuccess("PULSE_TIMEOUT_API") || (timed_out != 0UL))
		{
			reportFailure("PULSE_TIMEOUT_VALUE");
			return false;
		}

		Serial.print("NUCODE_AC01_PULSE:PASS:short_us=");
		Serial.print(short_measured);
		Serial.print(":long_us=");
		Serial.print(long_measured);
		Serial.println(":timeout_us=0");
		return true;
	}

	/** @brief shiftOut final bit과 shiftIn 고정 low/high 수신을 loopback에서 검증합니다. */
	bool testShift(void)
	{
		pinMode(PIN_GPIO0, OUTPUT);
		pinMode(LED_BUILTIN, OUTPUT);
		pinMode(PIN_GPIO1, INPUT_PULLDOWN);
		shiftOut(PIN_GPIO0, LED_BUILTIN, MSBFIRST, 0xA5U);
		if (!requireSuccess("SHIFT_OUT_MSB") || (digitalRead(PIN_GPIO1) != HIGH))
		{
			reportFailure("SHIFT_OUT_MSB_FINAL");
			return false;
		}

		shiftOut(PIN_GPIO0, LED_BUILTIN, LSBFIRST, 0x3CU);
		if (!requireSuccess("SHIFT_OUT_LSB") || (digitalRead(PIN_GPIO1) != LOW))
		{
			reportFailure("SHIFT_OUT_LSB_FINAL");
			return false;
		}

		digitalWrite(PIN_GPIO0, LOW);
		const std::uint8_t low_value = shiftIn(PIN_GPIO1, LED_BUILTIN, MSBFIRST);
		digitalWrite(PIN_GPIO0, HIGH);
		const std::uint8_t high_value = shiftIn(PIN_GPIO1, LED_BUILTIN, LSBFIRST);
		if (!requireSuccess("SHIFT_IN_API") || (low_value != 0x00U) ||
			(high_value != 0xFFU))
		{
			reportFailure("SHIFT_IN_VALUES");
			return false;
		}

		Serial.println(
			"NUCODE_AC01_SHIFT:PASS:out_msb_last=HIGH:out_lsb_last=LOW:in_low=0x00:in_high=0xFF");
		return true;
	}

	/** @brief 중첩 mask 중 assert된 LOW level과 scheduler 진행, 마지막 복원을 검증합니다. */
	bool testInterruptMask(void)
	{
		if (!configureInterruptFixture(true, "MASK_FIXTURE"))
		{
			return false;
		}
		InterruptFixtureGuard fixture(LOW);
		atomic_set(&level_callback_count, 0);
		atomic_set(&heartbeat_count, 0);
		atomic_set(&heartbeat_stop, 0);
		static_cast<void>(k_thread_create(
			&heartbeat_thread_data,
			heartbeat_thread_stack,
			K_THREAD_STACK_SIZEOF(heartbeat_thread_stack),
			heartbeatThread,
			nullptr,
			nullptr,
			nullptr,
			K_PRIO_PREEMPT(1),
			0,
			K_NO_WAIT));
		fixture.markHeartbeatStarted();

		attachInterrupt(digitalPinToInterrupt(interrupt_test_pin), countLevel, LOW);
		noInterrupts();
		if (lastGpioError() == GpioError::none)
		{
			fixture.markMaskAcquired();
		}
		noInterrupts();
		if (lastGpioError() == GpioError::none)
		{
			fixture.markMaskAcquired();
		}
		if (!requireSuccess("MASK_NEST"))
		{
			return false;
		}
		const atomic_val_t heartbeat_before = atomic_get(&heartbeat_count);
		if (!driveInterruptFixture(LOW, "MASK_ASSERT"))
		{
			return false;
		}
		delay(10UL);
		const atomic_val_t heartbeat_delta = atomic_get(&heartbeat_count) - heartbeat_before;
		if ((atomic_get(&level_callback_count) != 0) || (heartbeat_delta <= 0))
		{
			reportFailure("MASKED_CALLBACK_OR_SCHEDULER");
			return false;
		}

		interrupts();
		if (lastGpioError() == GpioError::none)
		{
			fixture.markMaskReleased();
		}
		delay(5UL);
		if (!requireSuccess("MASK_FIRST_RESTORE") ||
			(atomic_get(&level_callback_count) != 0))
		{
			reportFailure("MASK_NESTED_RESTORE");
			return false;
		}

		interrupts();
		if (lastGpioError() == GpioError::none)
		{
			fixture.markMaskReleased();
		}
		if (!requireSuccess("MASK_FINAL_RESTORE") || !waitForCount(1))
		{
			reportFailure("MASK_ASSERTED_LEVEL_RESTORE");
			return false;
		}
		delay(10UL);
		if (atomic_get(&level_callback_count) != 1)
		{
			reportFailure("MASK_RESTORED_LEVEL_ONE_SHOT");
			return false;
		}

		if (!fixture.finish("MASK_DETACH"))
		{
			return false;
		}

		Serial.print("NUCODE_AC01_INTERRUPT_MASK:PASS:masked=0:nested=0:restored=1:heartbeat_delta=");
		Serial.println(static_cast<long>(heartbeat_delta));
		return true;
	}
}

/** @brief AC-01 물리 loopback HIL을 한 번 실행하고 최종 결과를 UART로 보고합니다. */
void setup(void)
{
	Serial.begin(115200U);
	Serial.println("NUCODE_AC01_GPIO_HIL_READY:schema=1:gpio0=P2.5:gpio1=P2.6:wiring=P2.5_TO_P2.6:irq=SW0_P1.13_SELF_OPEN_DRAIN");

	const bool passed = testOpenDrain() && testLowLevel() && testHighLevel() &&
						testPulse() && testShift() && testInterruptMask();
	if (passed && !failed)
	{
		Serial.println("NUCODE_AC01_GPIO_HIL_PASS");
	}
}

/** @brief 단발성 HIL 완료 뒤 추가 GPIO 변경 없이 대기합니다. */
void loop(void)
{
	delay(1000UL);
}
