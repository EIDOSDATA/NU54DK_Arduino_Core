/**
 * @file runtime_smoke.cpp
 * @brief M2 Arduino 런타임의 호출 순서와 반복 동작을 검증합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <Arduino.h>

#include <zephyr/device.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/printk.h>

#include <cstdint>

/**
 * @brief 디버거와 HIL 판정을 위한 M2 런타임 추적 구조체입니다.
 */
struct RuntimeSmokeTrace
{
    std::uint32_t signature;
    std::uint32_t constructor_calls;
    std::uint32_t setup_calls;
    std::uint32_t loop_calls;
    std::uint32_t result;
    std::uint32_t failure;
    std::uint32_t serial_event_calls;
};

extern "C"
{

    /**
	 * @brief pyOCD가 symbol 이름으로 읽는 M2 HIL 추적값입니다.
	 */
    volatile RuntimeSmokeTrace nu54_m2_runtime_trace = {};
}

namespace
{

    constexpr std::uint32_t trace_signature = 0x4D325254U;
    constexpr std::uint32_t trace_pass = 0x50415353U;
    constexpr std::uint32_t trace_fail = 0x4641494CU;

    /**
	 * @brief M2 HIL 통과 상태를 표시하는 Zephyr 전용 시험 LED입니다.
	 *
	 * Arduino GPIO API나 Variant 핀 매핑을 구현하지 않으며 `led0` Devicetree alias를
	 * 직접 사용합니다.
	 */
    const gpio_dt_spec runtime_led = GPIO_DT_SPEC_GET(DT_ALIAS(led0), gpios);

    /**
	 * @brief 전역 C++ 생성자 실행 여부를 기록하는 시험용 객체입니다.
	 */
    class ConstructorProbe final
    {
      public:
        /**
		 * @brief `setup()`보다 앞선 정적 초기화 단계의 실행 흔적을 남깁니다.
		 */
        ConstructorProbe() noexcept
        {
            nu54_m2_runtime_trace.signature = 0U;
            ++nu54_m2_runtime_trace.constructor_calls;
            nu54_m2_runtime_trace.setup_calls = 0U;
            nu54_m2_runtime_trace.loop_calls = 0U;
            nu54_m2_runtime_trace.result = 0U;
            nu54_m2_runtime_trace.failure = 0U;
            nu54_m2_runtime_trace.serial_event_calls = 0U;
            nu54_m2_runtime_trace.signature = trace_signature;
        }
    };

    ConstructorProbe constructor_probe;

    /**
	 * @brief smoke 조건 위반을 출력하고 시스템을 중단합니다.
	 *
	 * @param reason 위반한 조건을 설명하는 문자열입니다.
	 * @param failure_code HIL에서 식별할 실패 번호입니다.
	 */
    [[noreturn]] void fail(const char *reason, std::uint32_t failure_code)
    {
        nu54_m2_runtime_trace.failure = failure_code;
        nu54_m2_runtime_trace.result = trace_fail;
        printk("M2_RUNTIME_SMOKE: FAIL: %s\n", reason);
        k_panic();

        for (;;)
        {
        }
    }

} // namespace

/**
 * @brief 강한 serialEventRun symbol이 호출할 순서 검증 본체입니다.
 */
extern "C" void nu54M2SerialEventProbe(void)
{
    if (nu54_m2_runtime_trace.loop_calls != (nu54_m2_runtime_trace.serial_event_calls + 1U))
    {
        fail("serialEventRun did not follow exactly one loop", 8U);
    }

    ++nu54_m2_runtime_trace.serial_event_calls;
    if (nu54_m2_runtime_trace.serial_event_calls == 3U)
    {
        nu54_m2_runtime_trace.result = trace_pass;
        printk("M2_RUNTIME_SMOKE: serial_event=3 PASS\n");
    }
}

/**
 * @brief 생성자 선행 실행과 단일 초기화 호출을 확인합니다.
 */
void setup(void)
{
    ++nu54_m2_runtime_trace.setup_calls;

    if ((nu54_m2_runtime_trace.signature != trace_signature) ||
        (nu54_m2_runtime_trace.constructor_calls != 1U))
    {
        fail("global constructor did not run before setup", 1U);
    }

    if (nu54_m2_runtime_trace.setup_calls != 1U)
    {
        fail("setup was called more than once", 2U);
    }

    if (!device_is_ready(runtime_led.port))
    {
        fail("led0 GPIO device is not ready", 4U);
    }

    if (gpio_pin_configure_dt(&runtime_led, GPIO_OUTPUT_INACTIVE) != 0)
    {
        fail("led0 GPIO configuration failed", 5U);
    }

    printk("M2_RUNTIME_SMOKE: setup=1 constructor=before_setup\n");
}

/**
 * @brief 반복 호출을 계수하고 직전 serialEventRun 순서를 검증합니다.
 */
void loop(void)
{
    if (nu54_m2_runtime_trace.setup_calls != 1U)
    {
        fail("loop observed an invalid setup count", 3U);
    }
    if (nu54_m2_runtime_trace.serial_event_calls != nu54_m2_runtime_trace.loop_calls)
    {
        fail("previous loop did not run serialEventRun", 7U);
    }

    ++nu54_m2_runtime_trace.loop_calls;

    if (gpio_pin_toggle_dt(&runtime_led) != 0)
    {
        fail("led0 GPIO toggle failed", 6U);
    }

    if (nu54_m2_runtime_trace.loop_calls <= 3U)
    {
        printk("M2_RUNTIME_SMOKE: loop=%u\n",
               static_cast<unsigned int>(nu54_m2_runtime_trace.loop_calls));
    }

    k_msleep(250);
}
