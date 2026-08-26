/**
 * @file local_library.ino
 * @brief 직접 library와 depends library source 전달을 검증합니다.
 */

#include <LocalAccumulator.h>

/** @brief library 반환값으로 LED 초기 상태를 결정합니다. */
void setup()
{
  pinMode(LED_BUILTIN, OUTPUT);
  digitalWrite(LED_BUILTIN, localAccumulate(1) == 5 ? HIGH : LOW);
}

/** @brief fixture는 scheduler에 실행 기회를 반복해서 양보합니다. */
void loop()
{
  delay(10);
}
