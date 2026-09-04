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

/** @brief Zephyr 초기화 뒤 실행하는 Arduino Core 기본 초기화 hook입니다. */
extern "C" __weak void init(void)
{
}

/** @brief Variant별 초기화의 기본 구현입니다. */
extern "C" __weak void initVariant(void)
{
}

/**
 * @brief Arduino Sketch 런타임을 시작합니다.
 *
 * Zephyr가 C++ 전역 생성자를 실행한 뒤 main thread에서 이 함수를 호출합니다.
 * `setup()`은 정확히 한 번, `loop()`는 반환할 때마다 반복 호출합니다.
 *
 * @note 기본 정책은 Zephyr main thread에서 각 `loop()` 반환 뒤 한 kernel
 * tick을 대기하는 것입니다.
 *
 * @return 정상 동작 중에는 반환하지 않습니다.
 */
int main(void)
{
    init();
    initVariant();
    setup();

    for (;;)
    {
        loop();
        if (arduino::serialEventRun != nullptr)
        {
            arduino::serialEventRun();
        }
        nucode::arduino::internal::runtimePostLoop();
    }
}
