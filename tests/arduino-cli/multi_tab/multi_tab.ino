/**
 * @file multi_tab.ino
 * @brief 여러 INO 탭을 하나의 Full Zephyr 애플리케이션으로 빌드하는 계약을 검증합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <Arduino.h>

/** @brief 다른 INO 탭의 계산 결과를 관찰 가능한 상태로 보존합니다. */
volatile unsigned int multiTabResult = 0U;

/** @brief 보조 탭에 정의된 함수를 선언 없이 호출해 prototype 생성을 검증합니다. */
void setup(void)
{
    multiTabResult = combineTabValues(20U);
}

/** @brief Zephyr scheduler에 실행권을 돌려주는 최소 반복 함수입니다. */
void loop(void)
{
    delay(1U);
}
