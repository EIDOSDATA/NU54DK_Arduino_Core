/**
 * @file main.cpp
 * @brief Zephyr main thread에서 Arduino Sketch 수명주기를 실행합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <Arduino.h>

#include <zephyr/kernel.h>
#include <zephyr/toolchain.h>

#include "internal/ArduinoRuntime.h"

/**
 * @brief Variant별 초기화의 기본 구현입니다.
 *
 * @note M2에서는 아무 작업도 하지 않으며 강한 Variant 구현으로 교체할 수
 * 있습니다.
 */
__weak void initVariant(void) {}

namespace
{

    /**
     * @brief 한 번의 Sketch `loop()` 반환 뒤 Zephyr 공존 정책을 적용합니다.
     *
     * 기본 정책은 한 kernel tick 동안 현재 main thread를 재워 낮은 priority
     * thread와 idle thread에도 실행 기회를 제공합니다. Kconfig로 yield 또는 무개입
     * 정책을 선택할 수 있습니다.
     */
    void runtimePostLoop(void)
    {
#if defined(CONFIG_NUCODE_ARDUINO_LOOP_SLEEP_ONE_TICK)
        (void)k_sleep(K_TICKS(1));
#elif defined(CONFIG_NUCODE_ARDUINO_LOOP_YIELD)
        k_yield();
#endif
    }

}

/**
 * @brief Arduino Sketch 런타임을 시작합니다.
 *
 * Zephyr가 C++ 전역 생성자를 실행한 뒤 main thread에서 이 함수를 호출합니다.
 * `setup()`은 정확히 한 번, `loop()`는 반환할 때마다 반복 호출합니다.
 *
 * @note M3 기본 정책은 Zephyr main thread에서 각 `loop()` 반환 뒤 한 kernel
 * tick을 대기하는 것입니다.
 *
 * @return 정상 동작 중에는 반환하지 않습니다.
 */
int main(void)
{
    initVariant();
    setup();

    for (;;)
    {
        loop();
        runtimePostLoop();
    }
}
