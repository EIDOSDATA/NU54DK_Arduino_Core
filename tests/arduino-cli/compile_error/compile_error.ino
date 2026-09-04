/**
 * @file compile_error.ino
 * @brief 원본 .ino diagnostic line 보존을 검증하는 의도적 실패 fixture입니다.
 */

/** @brief 의도적 compile 오류가 있는 setup입니다. */
void setup()
{
    pinMode(LED_BUILTIN, OUTPUT);
    /** @brief 의도한 compile 오류 위치를 검사하는 표식입니다: EXPECT_ERROR_LINE. */
    nucode_intentional_compile_error = 54;
}

/** @brief 도달하지 않는 최소 loop입니다. */
void loop()
{
}
