/**
 * @file main.cpp
 * @brief M3 GPIO·시간·scheduler 계약을 ztest로 자동 검증합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <Arduino.h>

#include <zephyr/device.h>
#include <zephyr/drivers/gpio/gpio_emul.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/atomic.h>
#include <zephyr/ztest.h>

#include <cstdint>

#include "internal/ArduinoRuntime.h"
#include "internal/TimeMath.h"
#include "internal/pin_description.h"

namespace
{

    using nucode::arduino::internal::elapsedTime32;
    using nucode::arduino::internal::GpioError;
    using nucode::arduino::internal::kMaximumBusyWaitChunkMicroseconds;
    using nucode::arduino::internal::kMaximumSleepChunkMilliseconds;
    using nucode::arduino::internal::lastGpioDriverError;
    using nucode::arduino::internal::lastGpioError;
    using nucode::arduino::internal::nextBusyWaitChunkMicroseconds;
    using nucode::arduino::internal::nextSleepChunkMilliseconds;
    using nucode::arduino::internal::runtimePostLoop;

    /** @brief GPIO emulator 장치입니다. */
    const struct device *const test_gpio = DEVICE_DT_GET(DT_NODELABEL(test_gpio));

    K_THREAD_STACK_DEFINE(worker_stack, 1024);
    struct k_thread worker_thread;
    struct k_sem worker_started;
    struct k_sem worker_finished;
    atomic_t worker_runs;

    /**
	 * @brief scheduler 공정성 시험에서 한 번 실행되는 worker입니다.
	 *
	 * @param first 사용하지 않습니다.
	 * @param second 사용하지 않습니다.
	 * @param third 사용하지 않습니다.
	 */
    void fairnessWorker(void *first, void *second, void *third)
    {
        ARG_UNUSED(first);
        ARG_UNUSED(second);
        ARG_UNUSED(third);

        static_cast<void>(k_sem_take(&worker_started, K_FOREVER));
        atomic_inc(&worker_runs);
        k_sem_give(&worker_finished);
    }

    /** @brief 각 scheduler 시험 전에 동기화 객체를 초기화합니다. */
    void prepareWorker(void)
    {
        k_sem_init(&worker_started, 0, 1);
        k_sem_init(&worker_finished, 0, 1);
        atomic_clear(&worker_runs);
    }

    /**
	 * @brief 현재 ztest thread보다 낮은 우선순위의 worker를 생성합니다.
	 *
	 * @return 생성한 thread 식별자입니다.
	 */
    k_tid_t startLowerPriorityWorker(void)
    {
        const int current_priority = k_thread_priority_get(k_current_get());
        return k_thread_create(&worker_thread, worker_stack, K_THREAD_STACK_SIZEOF(worker_stack),
                               fairnessWorker, nullptr, nullptr, nullptr, current_priority + 1, 0,
                               K_NO_WAIT);
    }

} // namespace

ZTEST(m3_time, test_32bit_rollover_difference)
{
    constexpr std::uint32_t start = 0xFFFFFFF0U;
    constexpr std::uint32_t current = 0x00000020U;

    static_assert(elapsedTime32(start, current) == 0x30U);
    zassert_equal(elapsedTime32(start, current), 48U,
                  "32비트 rollover 경과 계산이 잘못되었습니다.");
}

ZTEST(m3_time, test_long_delay_chunk_boundaries)
{
    constexpr std::int64_t maximum_request = static_cast<std::int64_t>(UINT32_MAX);
    const std::int32_t first_chunk = nextSleepChunkMilliseconds(maximum_request);
    const std::int64_t remaining = maximum_request - first_chunk;
    const std::int32_t second_chunk = nextSleepChunkMilliseconds(remaining);
    const std::int32_t final_chunk = nextSleepChunkMilliseconds(remaining - second_chunk);

    zassert_equal(first_chunk, kMaximumSleepChunkMilliseconds,
                  "첫 sleep 단위가 INT32_MAX로 제한되지 않았습니다.");
    zassert_equal(second_chunk, kMaximumSleepChunkMilliseconds,
                  "두 번째 sleep 단위가 INT32_MAX가 아닙니다.");
    zassert_equal(final_chunk, 1, "UINT32_MAX 밀리초의 마지막 단위가 1이 아닙니다.");
    zassert_equal(nextSleepChunkMilliseconds(0), 0, "완료된 sleep이 0을 반환하지 않습니다.");
    zassert_equal(nextSleepChunkMilliseconds(-1), 0, "지난 deadline이 0을 반환하지 않습니다.");
}

ZTEST(m3_time, test_busy_wait_chunk_boundaries)
{
    constexpr std::uint32_t request = (kMaximumBusyWaitChunkMicroseconds * 2U) + 17U;
    std::uint32_t remaining = request;
    std::uint32_t chunk_count = 0U;

    while (remaining != 0U)
    {
        const std::uint32_t chunk = nextBusyWaitChunkMicroseconds(remaining);
        zassert_true(chunk <= kMaximumBusyWaitChunkMicroseconds,
                     "busy-wait 단위가 1초 제한을 초과했습니다.");
        remaining -= chunk;
        ++chunk_count;
    }

    zassert_equal(chunk_count, 3U, "2,000,017 us 요청이 세 단위로 분할되지 않았습니다.");
}

ZTEST(m3_scheduler, test_default_post_loop_allows_lower_priority_worker)
{
    prepareWorker();
    k_tid_t worker = startLowerPriorityWorker();
    zassert_not_null(worker, "공정성 시험 worker를 생성하지 못했습니다.");

    k_sem_give(&worker_started);
    runtimePostLoop();

    zassert_equal(k_sem_take(&worker_finished, K_MSEC(100)), 0,
                  "한 tick sleep 중 낮은 우선순위 worker가 실행되지 않았습니다.");
    zassert_equal(atomic_get(&worker_runs), 1, "worker 실행 횟수가 1이 아닙니다.");
    k_thread_abort(worker);
}

ZTEST(m3_scheduler, test_post_loop_creates_idle_eligible_interval)
{
    const std::int64_t before = k_uptime_ticks();
    runtimePostLoop();
    const std::int64_t after = k_uptime_ticks();

    zassert_true(after > before,
                 "기본 post-loop 정책이 한 tick 이상 현재 thread를 block하지 않았습니다.");
}

ZTEST(m3_scheduler, test_delay_allows_equal_priority_worker)
{
    prepareWorker();
    const int current_priority = k_thread_priority_get(k_current_get());
    k_tid_t worker =
        k_thread_create(&worker_thread, worker_stack, K_THREAD_STACK_SIZEOF(worker_stack),
                        fairnessWorker, nullptr, nullptr, nullptr, current_priority, 0, K_NO_WAIT);
    zassert_not_null(worker, "delay 공정성 시험 worker를 생성하지 못했습니다.");

    k_sem_give(&worker_started);
    delay(2U);

    zassert_equal(k_sem_take(&worker_finished, K_MSEC(100)), 0,
                  "delay 중 같은 우선순위 worker가 실행되지 않았습니다.");
    zassert_equal(atomic_get(&worker_runs), 1, "delay worker 실행 횟수가 1이 아닙니다.");
    k_thread_abort(worker);
}

ZTEST(m3_gpio, test_emulated_gpio_read_write)
{
    zassert_true(device_is_ready(test_gpio), "GPIO emulator가 준비되지 않았습니다.");

    pinMode(LED_BUILTIN, OUTPUT);
    zassert_equal(lastGpioError(), GpioError::none, "출력 설정에 실패했습니다.");
    digitalWrite(LED_BUILTIN, HIGH);
    zassert_equal(lastGpioError(), GpioError::none, "HIGH 출력에 실패했습니다.");
    zassert_equal(gpio_emul_output_get(test_gpio, 0U), 1, "GPIO raw 출력이 HIGH가 아닙니다.");

    pinMode(LED_BUILTIN, INPUT_PULLUP);
    zassert_equal(gpio_emul_input_set(test_gpio, 0U, 0), 0, "GPIO 입력 주입에 실패했습니다.");
    zassert_equal(digitalRead(LED_BUILTIN), LOW, "주입한 LOW를 읽지 못했습니다.");
    zassert_equal(gpio_emul_input_set(test_gpio, 0U, 1), 0, "GPIO 입력 주입에 실패했습니다.");
    zassert_equal(digitalRead(LED_BUILTIN), HIGH, "주입한 HIGH를 읽지 못했습니다.");
}

ZTEST(m3_gpio, test_gpio_argument_and_state_errors)
{
    pinMode(static_cast<pin_size_t>(NUM_DIGITAL_PINS), OUTPUT);
    zassert_equal(lastGpioError(), GpioError::invalid_pin, "범위 밖 핀 오류가 다릅니다.");

    pinMode(LED_BUILTIN, OUTPUT_OPENDRAIN);
    zassert_equal(lastGpioError(), GpioError::invalid_mode, "미지원 mode 오류가 다릅니다.");

    digitalWrite(LED_BUILTIN, CHANGE);
    zassert_equal(lastGpioError(), GpioError::invalid_value, "미지원 출력값 오류가 다릅니다.");

    pinMode(PIN_INPUT_ONLY, OUTPUT);
    zassert_equal(lastGpioError(), GpioError::unsupported_capability,
                  "입력 전용 핀의 출력 오류가 다릅니다.");

    pinMode(LED_BUILTIN, INPUT);
    digitalWrite(LED_BUILTIN, HIGH);
    zassert_equal(lastGpioError(), GpioError::wrong_mode, "입력 mode의 출력 오류가 다릅니다.");

    zassert_equal(digitalRead(PIN_UNCONFIGURED_INPUT), LOW,
                  "미설정 입력은 안전하게 LOW를 반환해야 합니다.");
    zassert_equal(lastGpioError(), GpioError::pin_not_configured, "미설정 입력 오류가 다릅니다.");
}

ZTEST(m3_gpio, test_gpio_devicetree_flag_error)
{
    pinMode(PIN_UNSUPPORTED_FLAGS, OUTPUT);
    zassert_equal(lastGpioError(), GpioError::unsupported_devicetree_flags,
                  "지원하지 않는 Devicetree flag 오류가 다릅니다.");
    zassert_equal(lastGpioDriverError(), 0,
                  "Core가 거부한 Devicetree flag에 driver 오류를 잘못 기록했습니다.");
}

ZTEST_SUITE(m3_time, nullptr, nullptr, nullptr, nullptr, nullptr);
ZTEST_SUITE(m3_scheduler, nullptr, nullptr, nullptr, nullptr, nullptr);
ZTEST_SUITE(m3_gpio, nullptr, nullptr, nullptr, nullptr, nullptr);
