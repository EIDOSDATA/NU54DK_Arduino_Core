/**
 * @file runtime_timing.cpp
 * @brief M3 시간 API와 Zephyr scheduler 공존 정책을 실기 계측합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <Arduino.h>

#include <zephyr/kernel.h>
#include <zephyr/sys/atomic.h>
#include <zephyr/sys/printk.h>

#include <cstddef>
#include <cstdint>

namespace
{

	constexpr std::uint32_t trace_signature = 0x4D335254U;
	constexpr std::uint32_t trace_pass = 0x50415353U;
	constexpr std::uint32_t trace_fail = 0x4641494CU;
	constexpr std::uint32_t phase_duration_ms = 400U;
	constexpr std::size_t measured_phase_count = 4U;

	/**
	 * @brief 측정할 Sketch loop 동작 단계를 정의합니다.
	 */
	enum class TimingPhase : std::uint32_t
	{
		Spin = 0U,
		Yield = 1U,
		SleepOneTick = 2U,
		DelayOneMillisecond = 3U,
		Complete = 4U,
	};

	/**
	 * @brief 디버거와 HIL 판정을 위한 M3 시간·공정성 기록입니다.
	 */
	struct RuntimeTimingTrace
	{
		std::uint32_t signature;
		std::uint32_t result;
		std::uint32_t failure;
		std::uint32_t phase;
		std::uint32_t delay_elapsed_ms;
		std::uint32_t delay_elapsed_us;
		std::uint32_t busy_wait_elapsed_us;
		std::uint32_t timer_isr_reads;
		std::uint32_t loop_calls[measured_phase_count];
		std::uint32_t equal_worker_calls[measured_phase_count];
		std::uint32_t low_worker_calls[measured_phase_count];
		std::uint32_t timer_calls[measured_phase_count];
		std::uint32_t workqueue_calls[measured_phase_count];
		std::uint64_t execution_cycles[measured_phase_count];
		std::uint64_t idle_cycles[measured_phase_count];
	};

}

extern "C"
{

	/**
	 * @brief pyOCD가 symbol 이름으로 읽을 수 있는 M3 시간·공정성 기록입니다.
	 */
	volatile RuntimeTimingTrace nu54_m3_runtime_timing_trace = {};
}

namespace
{

	atomic_t equal_worker_counter;
	atomic_t low_worker_counter;
	atomic_t timer_counter;
	atomic_t workqueue_counter;
	atomic_t timer_isr_read_counter;
	atomic_t timer_error_flags;
	atomic_t timer_has_previous_sample;
	atomic_t previous_timer_ms;
	atomic_t previous_timer_us;

	std::uint32_t phase_loop_counter;
	std::uint32_t phase_started_ms;
	std::uint32_t baseline_equal_worker;
	std::uint32_t baseline_low_worker;
	std::uint32_t baseline_timer;
	std::uint32_t baseline_workqueue;
	k_thread_runtime_stats_t baseline_runtime_stats;
	TimingPhase current_phase = TimingPhase::Spin;
	k_work_delayable timing_work;

	/**
	 * @brief 32-bit 순환 counter의 경과값을 계산합니다.
	 *
	 * @param now 현재 counter 값입니다.
	 * @param before 이전 counter 값입니다.
	 * @return modulo-2^32 규칙으로 계산한 경과값입니다.
	 */
	constexpr std::uint32_t elapsed32(std::uint32_t now, std::uint32_t before)
	{
		return now - before;
	}

	static_assert(elapsed32(0x00000010U, 0xFFFFFFF0U) == 0x00000020U,
				  "32-bit wrap-around elapsed calculation failed");

	/**
	 * @brief main과 같은 priority에서 주기적으로 진행 횟수를 기록합니다.
	 *
	 * @param unused1 사용하지 않는 thread 인자입니다.
	 * @param unused2 사용하지 않는 thread 인자입니다.
	 * @param unused3 사용하지 않는 thread 인자입니다.
	 */
	void equalPriorityWorker(void *unused1, void *unused2, void *unused3)
	{
		ARG_UNUSED(unused1);
		ARG_UNUSED(unused2);
		ARG_UNUSED(unused3);

		for (;;)
		{
			atomic_inc(&equal_worker_counter);
			k_msleep(1);
		}
	}

	/**
	 * @brief main보다 낮은 priority에서 주기적으로 진행 횟수를 기록합니다.
	 *
	 * @param unused1 사용하지 않는 thread 인자입니다.
	 * @param unused2 사용하지 않는 thread 인자입니다.
	 * @param unused3 사용하지 않는 thread 인자입니다.
	 */
	void lowPriorityWorker(void *unused1, void *unused2, void *unused3)
	{
		ARG_UNUSED(unused1);
		ARG_UNUSED(unused2);
		ARG_UNUSED(unused3);

		for (;;)
		{
			atomic_inc(&low_worker_counter);
			k_msleep(1);
		}
	}

	/**
	 * @brief system timer ISR에서 시간 API 호출 가능성과 진행 횟수를 기록합니다.
	 *
	 * @param timer 만료된 Zephyr timer입니다.
	 */
	void timingTimerExpiry(k_timer *timer)
	{
		ARG_UNUSED(timer);

		if (!k_is_in_isr())
		{
			atomic_or(&timer_error_flags, 1);
		}

		const std::uint32_t now_ms = static_cast<std::uint32_t>(millis());
		const std::uint32_t now_us = static_cast<std::uint32_t>(micros());

		if (atomic_cas(&timer_has_previous_sample, 0, 1))
		{
			atomic_set(&previous_timer_ms, static_cast<atomic_val_t>(now_ms));
			atomic_set(&previous_timer_us, static_cast<atomic_val_t>(now_us));
		}
		else
		{
			const auto before_ms = static_cast<std::uint32_t>(atomic_get(&previous_timer_ms));
			const auto before_us = static_cast<std::uint32_t>(atomic_get(&previous_timer_us));

			if ((elapsed32(now_ms, before_ms) > 1000U) ||
				(elapsed32(now_us, before_us) > 1000000U))
			{
				atomic_or(&timer_error_flags, 2);
			}

			atomic_set(&previous_timer_ms, static_cast<atomic_val_t>(now_ms));
			atomic_set(&previous_timer_us, static_cast<atomic_val_t>(now_us));
		}

		atomic_inc(&timer_isr_read_counter);
		atomic_inc(&timer_counter);
	}

	K_TIMER_DEFINE(timing_timer, timingTimerExpiry, nullptr);

	/**
	 * @brief system workqueue의 지연 작업 진행 횟수를 기록하고 다시 예약합니다.
	 *
	 * @param work 실행된 delayable work의 공통 header입니다.
	 */
	void timingWorkHandler(k_work *work)
	{
		ARG_UNUSED(work);
		atomic_inc(&workqueue_counter);
		(void)k_work_reschedule(&timing_work, K_MSEC(10));
	}

	/**
	 * @brief 현재 system runtime 통계를 읽고 실패 여부를 반환합니다.
	 *
	 * @param stats 결과를 저장할 구조체입니다.
	 * @return 통계 조회에 성공하면 true입니다.
	 */
	bool readRuntimeStats(k_thread_runtime_stats_t &stats)
	{
		return k_thread_runtime_stats_all_get(&stats) == 0;
	}

	/**
	 * @brief HIL 실패 코드를 가장 먼저 발생한 값으로 기록합니다.
	 *
	 * @param failure_code 실패 원인을 식별하는 번호입니다.
	 */
	void recordFailure(std::uint32_t failure_code)
	{
		if (nu54_m3_runtime_timing_trace.failure == 0U)
		{
			nu54_m3_runtime_timing_trace.failure = failure_code;
		}
	}

	/**
	 * @brief 다음 공정성 측정 단계의 기준값을 저장합니다.
	 */
	void startPhase(void)
	{
		phase_loop_counter = 0U;
		phase_started_ms = static_cast<std::uint32_t>(millis());
		baseline_equal_worker = static_cast<std::uint32_t>(atomic_get(&equal_worker_counter));
		baseline_low_worker = static_cast<std::uint32_t>(atomic_get(&low_worker_counter));
		baseline_timer = static_cast<std::uint32_t>(atomic_get(&timer_counter));
		baseline_workqueue = static_cast<std::uint32_t>(atomic_get(&workqueue_counter));

		if (!readRuntimeStats(baseline_runtime_stats))
		{
			recordFailure(10U);
		}
	}

	/**
	 * @brief 현재 측정 단계를 저장하고 다음 단계로 이동합니다.
	 */
	void finishPhase(void)
	{
		const std::size_t index = static_cast<std::size_t>(current_phase);
		k_thread_runtime_stats_t now_stats = {};

		if (!readRuntimeStats(now_stats))
		{
			recordFailure(11U);
		}

		nu54_m3_runtime_timing_trace.loop_calls[index] = phase_loop_counter;
		nu54_m3_runtime_timing_trace.equal_worker_calls[index] =
			static_cast<std::uint32_t>(atomic_get(&equal_worker_counter)) -
			baseline_equal_worker;
		nu54_m3_runtime_timing_trace.low_worker_calls[index] =
			static_cast<std::uint32_t>(atomic_get(&low_worker_counter)) - baseline_low_worker;
		nu54_m3_runtime_timing_trace.timer_calls[index] =
			static_cast<std::uint32_t>(atomic_get(&timer_counter)) - baseline_timer;
		nu54_m3_runtime_timing_trace.workqueue_calls[index] =
			static_cast<std::uint32_t>(atomic_get(&workqueue_counter)) - baseline_workqueue;
		nu54_m3_runtime_timing_trace.execution_cycles[index] =
			now_stats.execution_cycles - baseline_runtime_stats.execution_cycles;
		nu54_m3_runtime_timing_trace.idle_cycles[index] =
			now_stats.idle_cycles - baseline_runtime_stats.idle_cycles;

		current_phase = static_cast<TimingPhase>(static_cast<std::uint32_t>(current_phase) + 1U);
		nu54_m3_runtime_timing_trace.phase = static_cast<std::uint32_t>(current_phase);

		if (current_phase != TimingPhase::Complete)
		{
			startPhase();
		}
	}

	/**
	 * @brief 모든 공정성 단계의 최소 기대 조건을 판정합니다.
	 */
	void evaluateFairness(void)
	{
		const std::size_t spin = static_cast<std::size_t>(TimingPhase::Spin);
		const std::size_t yielded = static_cast<std::size_t>(TimingPhase::Yield);
		const std::size_t tick_sleep = static_cast<std::size_t>(TimingPhase::SleepOneTick);
		const std::size_t delay_one = static_cast<std::size_t>(TimingPhase::DelayOneMillisecond);

		if ((nu54_m3_runtime_timing_trace.timer_calls[spin] == 0U) ||
			(nu54_m3_runtime_timing_trace.workqueue_calls[spin] == 0U))
		{
			recordFailure(20U);
		}

		if (nu54_m3_runtime_timing_trace.equal_worker_calls[yielded] == 0U)
		{
			recordFailure(21U);
		}

		if ((nu54_m3_runtime_timing_trace.low_worker_calls[tick_sleep] == 0U) ||
			(nu54_m3_runtime_timing_trace.idle_cycles[tick_sleep] == 0U))
		{
			recordFailure(22U);
		}

		if ((nu54_m3_runtime_timing_trace.low_worker_calls[delay_one] == 0U) ||
			(nu54_m3_runtime_timing_trace.idle_cycles[delay_one] == 0U))
		{
			recordFailure(23U);
		}

		if ((atomic_get(&timer_error_flags) != 0) || (atomic_get(&timer_isr_read_counter) == 0))
		{
			recordFailure(24U);
		}
	}

}

K_THREAD_DEFINE(equal_worker, 1024, equalPriorityWorker, nullptr, nullptr, nullptr,
				CONFIG_MAIN_THREAD_PRIORITY, 0, 0);
K_THREAD_DEFINE(low_worker, 1024, lowPriorityWorker, nullptr, nullptr, nullptr,
				CONFIG_MAIN_THREAD_PRIORITY + 1, 0, 0);

/**
 * @brief 시간 API의 기본 정확도와 scheduler 계측기를 초기화합니다.
 */
void setup(void)
{
	nu54_m3_runtime_timing_trace.result = 0U;
	nu54_m3_runtime_timing_trace.failure = 0U;
	nu54_m3_runtime_timing_trace.phase = static_cast<std::uint32_t>(TimingPhase::Spin);
	nu54_m3_runtime_timing_trace.signature = trace_signature;

	pinMode(LED_BUILTIN, OUTPUT);
	digitalWrite(LED_BUILTIN, LOW);

	k_work_init_delayable(&timing_work, timingWorkHandler);
	(void)k_work_schedule(&timing_work, K_MSEC(1));
	k_timer_start(&timing_timer, K_MSEC(1), K_MSEC(1));

	const std::uint32_t worker_before =
		static_cast<std::uint32_t>(atomic_get(&low_worker_counter));
	const std::uint32_t delay_started_ms = static_cast<std::uint32_t>(millis());
	const std::uint32_t delay_started_us = static_cast<std::uint32_t>(micros());
	delay(20U);
	nu54_m3_runtime_timing_trace.delay_elapsed_ms =
		elapsed32(static_cast<std::uint32_t>(millis()), delay_started_ms);
	nu54_m3_runtime_timing_trace.delay_elapsed_us =
		elapsed32(static_cast<std::uint32_t>(micros()), delay_started_us);

	if ((nu54_m3_runtime_timing_trace.delay_elapsed_ms < 20U) ||
		(nu54_m3_runtime_timing_trace.delay_elapsed_us < 20000U) ||
		(static_cast<std::uint32_t>(atomic_get(&low_worker_counter)) == worker_before))
	{
		recordFailure(1U);
	}

	const std::uint32_t busy_started_us = static_cast<std::uint32_t>(micros());
	delayMicroseconds(1000U);
	nu54_m3_runtime_timing_trace.busy_wait_elapsed_us =
		elapsed32(static_cast<std::uint32_t>(micros()), busy_started_us);

	if (nu54_m3_runtime_timing_trace.busy_wait_elapsed_us < 900U)
	{
		recordFailure(2U);
	}

	startPhase();
	printk("M3_RUNTIME_TIMING: measurement started\n");
}

/**
 * @brief 네 scheduler 동작을 순서대로 계측하고 LED로 최종 판정을 표시합니다.
 */
void loop(void)
{
	if (current_phase == TimingPhase::Complete)
	{
		static bool led_state;
		led_state = !led_state;
		digitalWrite(LED_BUILTIN, led_state ? HIGH : LOW);
		delay((nu54_m3_runtime_timing_trace.result == trace_pass) ? 500U : 50U);
		return;
	}

	++phase_loop_counter;

	if (elapsed32(static_cast<std::uint32_t>(millis()), phase_started_ms) >=
		phase_duration_ms)
	{
		finishPhase();

		if (current_phase == TimingPhase::Complete)
		{
			evaluateFairness();
			nu54_m3_runtime_timing_trace.timer_isr_reads =
				static_cast<std::uint32_t>(atomic_get(&timer_isr_read_counter));

			if (nu54_m3_runtime_timing_trace.failure == 0U)
			{
				nu54_m3_runtime_timing_trace.result = trace_pass;
				printk("M3_RUNTIME_TIMING: PASS\n");
			}
			else
			{
				nu54_m3_runtime_timing_trace.result = trace_fail;
				printk("M3_RUNTIME_TIMING: FAIL %u\n",
					   static_cast<unsigned int>(
						   nu54_m3_runtime_timing_trace.failure));
			}
		}

		return;
	}

	switch (current_phase)
	{
	case TimingPhase::Spin:
		break;
	case TimingPhase::Yield:
		yield();
		break;
	case TimingPhase::SleepOneTick:
		(void)k_sleep(K_TICKS(1));
		break;
	case TimingPhase::DelayOneMillisecond:
		delay(1U);
		break;
	case TimingPhase::Complete:
		break;
	}
}
