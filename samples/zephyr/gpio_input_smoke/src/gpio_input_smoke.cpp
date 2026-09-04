/**
 * @file gpio_input_smoke.cpp
 * @brief NU54DK 버튼 입력과 유효하지 않은 핀의 no-op 정책을 검증합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <Arduino.h>

#include <cstdint>

/**
 * @brief 디버거와 HIL 판정을 위한 GPIO 입력 시험 추적값입니다.
 */
struct GpioInputSmokeTrace
{
    std::uint32_t signature;
    std::uint32_t result;
    std::uint32_t failure;
    std::uint32_t led_before_invalid;
    std::uint32_t invalid_read;
    std::uint32_t led_after_invalid;
    std::uint32_t button_raw;
    std::uint32_t led_requested;
    std::uint32_t loop_calls;
};

extern "C"
{

    /**
	 * @brief pyOCD나 J-Link가 C symbol 이름으로 읽을 수 있는 추적값입니다.
	 */
    volatile GpioInputSmokeTrace nu54_m3_gpio_input_trace = {};
}

namespace
{

    constexpr std::uint32_t trace_signature = 0x4D334749U;
    constexpr std::uint32_t trace_pass = 0x50415353U;
    constexpr std::uint32_t trace_fail = 0x4641494CU;
    constexpr pin_size_t invalid_pin = NUM_DIGITAL_PINS;

    /**
	 * @brief Arduino 핀 상태를 추적값에 기록할 정수로 변환합니다.
	 *
	 * @param status 변환할 Arduino 핀 상태입니다.
	 * @return `LOW` 또는 `HIGH`의 정수 표현입니다.
	 */
    constexpr std::uint32_t encode_status(PinStatus status)
    {
        return static_cast<std::uint32_t>(status);
    }

    /**
	 * @brief self-check 실패 상태를 기록합니다.
	 *
	 * @param failure_code 실패한 조건을 나타내는 번호입니다.
	 */
    void record_failure(std::uint32_t failure_code)
    {
        nu54_m3_gpio_input_trace.failure = failure_code;
        nu54_m3_gpio_input_trace.result = trace_fail;
    }

} // namespace

/**
 * @brief LED와 버튼을 구성하고 유효하지 않은 핀의 no-op 동작을 검사합니다.
 */
void setup(void)
{
    nu54_m3_gpio_input_trace.signature = 0U;
    nu54_m3_gpio_input_trace.result = 0U;
    nu54_m3_gpio_input_trace.failure = 0U;
    nu54_m3_gpio_input_trace.loop_calls = 0U;

    pinMode(LED_BUILTIN, OUTPUT);
    digitalWrite(LED_BUILTIN, HIGH);

    const PinStatus led_before_invalid = digitalRead(LED_BUILTIN);
    pinMode(invalid_pin, OUTPUT);
    digitalWrite(invalid_pin, LOW);
    const PinStatus invalid_read = digitalRead(invalid_pin);
    const PinStatus led_after_invalid = digitalRead(LED_BUILTIN);

    nu54_m3_gpio_input_trace.led_before_invalid = encode_status(led_before_invalid);
    nu54_m3_gpio_input_trace.invalid_read = encode_status(invalid_read);
    nu54_m3_gpio_input_trace.led_after_invalid = encode_status(led_after_invalid);

    if (led_before_invalid != HIGH)
    {
        record_failure(1U);
    }
    else if (invalid_read != LOW)
    {
        record_failure(2U);
    }
    else if (led_after_invalid != led_before_invalid)
    {
        record_failure(3U);
    }
    else
    {
        nu54_m3_gpio_input_trace.result = trace_pass;
    }

    digitalWrite(LED_BUILTIN, LOW);
    pinMode(PIN_BUTTON0, INPUT_PULLUP);
    nu54_m3_gpio_input_trace.signature = trace_signature;
}

/**
 * @brief 버튼의 raw 상태에 따라 내장 LED를 제어합니다.
 *
 * 버튼은 pull-up 입력이므로 해제 상태가 `HIGH`, 누른 상태가 `LOW`입니다.
 * self-check가 실패하면 버튼 제어 대신 빠른 LED 점멸로 실패를 표시합니다.
 */
void loop(void)
{
    if (nu54_m3_gpio_input_trace.result != trace_pass)
    {
        digitalWrite(LED_BUILTIN, HIGH);
        delay(100UL);
        digitalWrite(LED_BUILTIN, LOW);
        delay(100UL);
        return;
    }

    const PinStatus button_raw = digitalRead(PIN_BUTTON0);
    const PinStatus led_requested = (button_raw == LOW) ? HIGH : LOW;

    nu54_m3_gpio_input_trace.signature = 0U;
    nu54_m3_gpio_input_trace.button_raw = encode_status(button_raw);
    nu54_m3_gpio_input_trace.led_requested = encode_status(led_requested);
    ++nu54_m3_gpio_input_trace.loop_calls;
    digitalWrite(LED_BUILTIN, led_requested);
    nu54_m3_gpio_input_trace.signature = trace_signature;

    delay(10UL);
}
