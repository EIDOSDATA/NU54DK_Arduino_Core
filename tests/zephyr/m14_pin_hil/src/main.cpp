/**
 * @file main.cpp
 * @brief M14 신규 LED와 버튼의 실제 GPIO·edge 동작을 안내형 UART HIL로 검증합니다.
 *
 * @note PIN_LED1은 PIN_PWM0과 같은 물리 자원을 PWM이 소유하므로 digital HIL에서 제외합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <Arduino.h>

#include <zephyr/sys/atomic.h>

#include <cstdint>

#include "internal/pin_description.h"

namespace
{
    using nucode::arduino::internal::GpioError;
    using nucode::arduino::internal::lastGpioDriverError;
    using nucode::arduino::internal::lastGpioError;

    /** @brief 사용자가 한 물리 동작을 완료해야 하는 최대 시간입니다. */
    constexpr unsigned long action_timeout_ms = 30000UL;

    /** @brief 접점이 기대 상태로 유지되어야 하는 debounce 시간입니다. */
    constexpr unsigned long stable_state_ms = 30UL;

    /** @brief 순차적으로 시험할 신규 LED 논리 핀입니다. */
    constexpr pin_size_t output_pins[] = {PIN_LED2, PIN_LED3};

    /** @brief 순차적으로 시험할 신규 버튼 논리 핀입니다. */
    constexpr pin_size_t button_pins[] = {PIN_BUTTON1, PIN_BUTTON2, PIN_BUTTON3};

    /** @brief 현재 시험 중인 단일 버튼의 ISR edge 누적값입니다. */
    atomic_t edge_count = ATOMIC_INIT(0);

    /** @brief GPIO ISR에서 blocking 작업 없이 edge 수만 누적합니다. */
    void countEdge(void)
    {
        atomic_inc(&edge_count);
    }

    /**
	 * @brief 논리 핀 상수 이름을 UART protocol에 기록할 고정 문자열로 변환합니다.
	 *
	 * @param pin 변환할 논리 핀입니다.
	 * @return 고정 protocol 이름입니다.
	 */
    const char *pinName(pin_size_t pin)
    {
        switch (pin)
        {
        case PIN_LED2:
            return "PIN_LED2";
        case PIN_LED3:
            return "PIN_LED3";
        case PIN_BUTTON1:
            return "PIN_BUTTON1";
        case PIN_BUTTON2:
            return "PIN_BUTTON2";
        case PIN_BUTTON3:
            return "PIN_BUTTON3";
        default:
            return "UNKNOWN";
        }
    }

    /**
	 * @brief 마지막 Core GPIO 오류를 포함한 fail-closed token을 출력합니다.
	 *
	 * @param stage 실패한 시험 단계입니다.
	 * @param pin 실패한 논리 핀입니다.
	 */
    void reportFailure(const char *stage, pin_size_t pin)
    {
        Serial.print("NUCODE_M14_PIN_HIL_FAIL:stage=");
        Serial.print(stage);
        Serial.print(":pin=");
        Serial.print(pinName(pin));
        Serial.print(":id=");
        Serial.print(static_cast<unsigned int>(pin));
        Serial.print(":gpio_error=");
        Serial.print(static_cast<unsigned int>(lastGpioError()));
        Serial.print(":driver_error=");
        Serial.println(lastGpioDriverError());
    }

    /**
	 * @brief 지정한 raw 입력이 debounce 시간 동안 유지될 때까지 제한 시간 안에서 기다립니다.
	 *
	 * @param pin 읽을 버튼 논리 핀입니다.
	 * @param expected 기대하는 raw 전기 상태입니다.
	 * @param required_edges 동시에 충족해야 하는 최소 ISR edge 수입니다.
	 * @return 상태와 edge 조건을 모두 만족하면 true입니다.
	 */
    bool waitForStableState(pin_size_t pin, PinStatus expected, std::uint32_t required_edges)
    {
        const unsigned long started = millis();
        unsigned long stable_started = 0UL;
        bool stable = false;

        while ((millis() - started) < action_timeout_ms)
        {
            const bool state_matches = digitalRead(pin) == expected;
            if (lastGpioError() != GpioError::none)
            {
                return false;
            }

            const auto observed_edges = static_cast<std::uint32_t>(atomic_get(&edge_count));
            if (state_matches && (observed_edges >= required_edges))
            {
                if (!stable)
                {
                    stable = true;
                    stable_started = millis();
                }
                else if ((millis() - stable_started) >= stable_state_ms)
                {
                    return true;
                }
            }
            else
            {
                stable = false;
            }
            delay(1UL);
        }

        return false;
    }

    /**
	 * @brief 사용자에게 수행할 단일 버튼 동작을 기계 판독 가능한 token으로 안내합니다.
	 *
	 * @param pin 대상 버튼 논리 핀입니다.
	 * @param mode 검증 단계 이름입니다.
	 * @param expected 기대하는 물리 동작과 raw 상태입니다.
	 */
    void requestAction(pin_size_t pin, const char *mode, const char *expected)
    {
        Serial.print("NUCODE_M14_PIN_HIL_ACTION:pin=");
        Serial.print(pinName(pin));
        Serial.print(":id=");
        Serial.print(static_cast<unsigned int>(pin));
        Serial.print(":mode=");
        Serial.print(mode);
        Serial.print(":expected=");
        Serial.print(expected);
        Serial.print(":timeout_ms=");
        Serial.println(action_timeout_ms);
    }

    /**
	 * @brief 관찰한 interrupt mode, raw 상태와 edge 수를 성공 token으로 기록합니다.
	 *
	 * @param pin 대상 버튼 논리 핀입니다.
	 * @param mode 검증한 interrupt mode와 phase입니다.
	 * @param state 안정화된 raw 상태 이름입니다.
	 * @param observed_edges 관찰한 ISR edge 누적값입니다.
	 */
    void reportEdgePass(pin_size_t pin, const char *mode, const char *state,
                        std::uint32_t observed_edges)
    {
        Serial.print("NUCODE_M14_PIN_HIL_EDGE:PASS:pin=");
        Serial.print(pinName(pin));
        Serial.print(":id=");
        Serial.print(static_cast<unsigned int>(pin));
        Serial.print(":mode=");
        Serial.print(mode);
        Serial.print(":state=");
        Serial.print(state);
        Serial.print(":count=");
        Serial.println(static_cast<unsigned long>(observed_edges));
    }

    /**
	 * @brief 등록된 interrupt를 해제하고 driver 결과를 fail-closed 방식으로 확인합니다.
	 *
	 * @param pin 대상 버튼 논리 핀입니다.
	 * @param stage 해제 실패 시 보고할 단계입니다.
	 * @return 해제가 성공하면 true입니다.
	 */
    bool detachInterruptChecked(pin_size_t pin, const char *stage)
    {
        detachInterrupt(digitalPinToInterrupt(pin));
        if (lastGpioError() != GpioError::none)
        {
            reportFailure(stage, pin);
            return false;
        }
        return true;
    }

    /**
	 * @brief 신규 LED 하나에 LOW/HIGH를 쓰고 output readback이 같은지 검증합니다.
	 *
	 * @param pin 검증할 LED 논리 핀입니다.
	 * @return 두 상태가 모두 일치하면 true입니다.
	 */
    bool testOutputPin(pin_size_t pin)
    {
        pinMode(pin, OUTPUT);
        if (lastGpioError() != GpioError::none)
        {
            reportFailure("LED_PINMODE", pin);
            return false;
        }

        digitalWrite(pin, LOW);
        const PinStatus low_read = digitalRead(pin);
        if ((lastGpioError() != GpioError::none) || (low_read != LOW))
        {
            reportFailure("LED_LOW_READBACK", pin);
            return false;
        }

        digitalWrite(pin, HIGH);
        const PinStatus high_read = digitalRead(pin);
        if ((lastGpioError() != GpioError::none) || (high_read != HIGH))
        {
            reportFailure("LED_HIGH_READBACK", pin);
            return false;
        }

        digitalWrite(pin, LOW);
        if (lastGpioError() != GpioError::none)
        {
            reportFailure("LED_FINAL_LOW", pin);
            return false;
        }
        Serial.print("NUCODE_M14_PIN_HIL_LED:PASS:pin=");
        Serial.print(pinName(pin));
        Serial.print(":id=");
        Serial.print(static_cast<unsigned int>(pin));
        Serial.println(":low_read=LOW:high_read=HIGH:final=LOW");
        return true;
    }

    /**
	 * @brief 버튼 하나의 INPUT_PULLUP raw 상태와 FALLING/RISING/CHANGE를 순차 검증합니다.
	 *
	 * @param pin 검증할 버튼 논리 핀입니다.
	 * @return 모든 사용자 동작과 edge 관찰을 제한 시간 안에 완료하면 true입니다.
	 */
    bool testButtonPin(pin_size_t pin)
    {
        pinMode(pin, INPUT_PULLUP);
        if (lastGpioError() != GpioError::none)
        {
            reportFailure("BUTTON_PINMODE", pin);
            return false;
        }

        atomic_set(&edge_count, 0);
        requestAction(pin, "INPUT_PULLUP", "RELEASE_HIGH");
        if (!waitForStableState(pin, HIGH, 0U))
        {
            reportFailure("BUTTON_IDLE_HIGH_TIMEOUT", pin);
            return false;
        }
        Serial.print("NUCODE_M14_PIN_HIL_INPUT:PASS:pin=");
        Serial.print(pinName(pin));
        Serial.print(":id=");
        Serial.print(static_cast<unsigned int>(pin));
        Serial.println(":mode=INPUT_PULLUP:released=HIGH");

        atomic_set(&edge_count, 0);
        attachInterrupt(digitalPinToInterrupt(pin), countEdge, FALLING);
        if (lastGpioError() != GpioError::none)
        {
            reportFailure("ATTACH_FALLING", pin);
            return false;
        }
        requestAction(pin, "FALLING", "PRESS_LOW");
        if (!waitForStableState(pin, LOW, 1U))
        {
            detachInterrupt(digitalPinToInterrupt(pin));
            reportFailure("FALLING_PRESS_TIMEOUT", pin);
            return false;
        }
        const auto falling_edges = static_cast<std::uint32_t>(atomic_get(&edge_count));
        if (!detachInterruptChecked(pin, "DETACH_FALLING"))
        {
            return false;
        }
        reportEdgePass(pin, "FALLING", "LOW", falling_edges);

        atomic_set(&edge_count, 0);
        attachInterrupt(digitalPinToInterrupt(pin), countEdge, RISING);
        if (lastGpioError() != GpioError::none)
        {
            reportFailure("ATTACH_RISING", pin);
            return false;
        }
        requestAction(pin, "RISING", "RELEASE_HIGH");
        if (!waitForStableState(pin, HIGH, 1U))
        {
            detachInterrupt(digitalPinToInterrupt(pin));
            reportFailure("RISING_RELEASE_TIMEOUT", pin);
            return false;
        }
        const auto rising_edges = static_cast<std::uint32_t>(atomic_get(&edge_count));
        if (!detachInterruptChecked(pin, "DETACH_RISING"))
        {
            return false;
        }
        reportEdgePass(pin, "RISING", "HIGH", rising_edges);

        atomic_set(&edge_count, 0);
        attachInterrupt(digitalPinToInterrupt(pin), countEdge, CHANGE);
        if (lastGpioError() != GpioError::none)
        {
            reportFailure("ATTACH_CHANGE", pin);
            return false;
        }
        requestAction(pin, "CHANGE_PRESS", "PRESS_LOW");
        if (!waitForStableState(pin, LOW, 1U))
        {
            detachInterrupt(digitalPinToInterrupt(pin));
            reportFailure("CHANGE_PRESS_TIMEOUT", pin);
            return false;
        }
        const auto change_press_edges = static_cast<std::uint32_t>(atomic_get(&edge_count));
        reportEdgePass(pin, "CHANGE_PRESS", "LOW", change_press_edges);

        requestAction(pin, "CHANGE_RELEASE", "RELEASE_HIGH");
        if (!waitForStableState(pin, HIGH, change_press_edges + 1U))
        {
            detachInterrupt(digitalPinToInterrupt(pin));
            reportFailure("CHANGE_RELEASE_TIMEOUT", pin);
            return false;
        }
        const auto change_release_edges = static_cast<std::uint32_t>(atomic_get(&edge_count));
        if (!detachInterruptChecked(pin, "DETACH_CHANGE"))
        {
            return false;
        }
        reportEdgePass(pin, "CHANGE_RELEASE", "HIGH", change_release_edges);

        Serial.print("NUCODE_M14_PIN_HIL_BUTTON:PASS:pin=");
        Serial.print(pinName(pin));
        Serial.print(":id=");
        Serial.print(static_cast<unsigned int>(pin));
        Serial.println(":released=HIGH:pressed=LOW:modes=FALLING,RISING,CHANGE");
        return true;
    }
} // namespace

/** @brief 신규 핀 HIL을 단 한 번 실행하고 최종 fail-closed 결과를 UART로 보고합니다. */
void setup(void)
{
    Serial.begin(115200U);
    Serial.println("NUCODE_M14_PIN_HIL_READY:schema=1:action_timeout_ms=30000");
    Serial.println(
        "NUCODE_M14_PIN_HIL_EXCLUDED:pin=PIN_LED1:id=4:owner=PIN_PWM0:evidence=M7_PWM_DRIVER");

    for (const pin_size_t pin : output_pins)
    {
        if (!testOutputPin(pin))
        {
            return;
        }
    }

    for (const pin_size_t pin : button_pins)
    {
        if (!testButtonPin(pin))
        {
            return;
        }
    }

    Serial.println("NUCODE_M14_PIN_HIL_PASS");
}

/** @brief 단발성 HIL 완료 뒤 GPIO 설정을 유지하며 추가 시험 없이 대기합니다. */
void loop(void)
{
    delay(1000UL);
}
