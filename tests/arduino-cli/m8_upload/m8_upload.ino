#include <Arduino.h>

/** @brief M8 upload 후 reset과 sketch 실행을 확인하는 UART 표식입니다. */
constexpr const char *upload_ready_token = "NUCODE_M8_UPLOAD_READY";

/** @brief 내장 LED와 Serial 검증 채널을 초기화합니다. */
void setup()
{
  pinMode(LED_BUILTIN, OUTPUT);
  Serial.begin(115200U);
  Serial.println(upload_ready_token);
}

/** @brief LED를 점멸하고 upload HIL이 수집할 생존 표식을 반복 출력합니다. */
void loop()
{
  static bool led_high = false;
  led_high = !led_high;
  digitalWrite(LED_BUILTIN, led_high ? HIGH : LOW);
  Serial.println(upload_ready_token);
  delay(250U);
}
