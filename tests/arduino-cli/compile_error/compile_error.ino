/**
 * @file compile_error.ino
 * @brief 원본 .ino diagnostic line 보존을 검증하는 의도적 실패 fixture입니다.
 */

/** @brief 의도적 compile 오류가 있는 setup입니다. */
void setup()
{
  pinMode(LED_BUILTIN, OUTPUT);
  nucode_intentional_compile_error = 54; // EXPECT_ERROR_LINE
}

/** @brief 도달하지 않는 최소 loop입니다. */
void loop()
{
}
