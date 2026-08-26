/**
 * @file config_overlay.ino
 * @brief sketch 옆 prj.conf와 app.overlay 전달을 검증합니다.
 */

/** @brief 최소 Arduino GPIO 초기화를 수행합니다. */
void setup()
{
  pinMode(LED_BUILTIN, OUTPUT);
}

/** @brief Zephyr scheduler를 사용하는 최소 loop입니다. */
void loop()
{
  delay(25);
}
