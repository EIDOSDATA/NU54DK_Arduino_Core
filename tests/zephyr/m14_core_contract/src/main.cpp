/**
 * @file main.cpp
 * @brief M14 공개 API가 production Zephyr module 경로에서 최종 link되는지 검증합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <Arduino.h>
#include <nucode/Diagnostics.h>

#include <zephyr/ztest.h>

#include <string.h>

ZTEST(m14_core_contract, test_random_and_diagnostics_use_production_module)
{
    long first_sequence[8] = {};
    randomSeed(0x12345678UL);
    for (auto &value : first_sequence)
    {
        value = random(16L);
        zassert_true((value >= 0L) && (value < 16L),
                     "random이 2의 거듭제곱 반열린 범위를 벗어났습니다.");
    }

    randomSeed(0x12345678UL);
    for (const auto expected : first_sequence)
    {
        zassert_equal(random(16L), expected,
                      "같은 seed가 같은 production random 수열을 만들지 못했습니다.");
    }

    const long signed_range_value = random(-50L, 75L);
    zassert_true((signed_range_value >= -50L) && (signed_range_value < 75L),
                 "두 인자 random이 production 반열린 범위를 벗어났습니다.");

    static_cast<void>(digitalRead(static_cast<pin_size_t>(NUM_DIGITAL_PINS)));
    const auto diagnostic =
        nucode::arduino::lastDiagnostic(nucode::arduino::DiagnosticSubsystem::gpio);
    zassert_equal(diagnostic.code, nucode::arduino::DiagnosticCode::invalid_pin,
                  "GPIO 내부 오류가 공개 진단 코드로 투영되지 않았습니다.");
    zassert_equal(diagnostic.driver_error, 0, "driver 오류가 아닌 진단에 errno가 남았습니다.");

    char buffer[80] = {};
    const auto required = nucode::arduino::formatDiagnostic(diagnostic, buffer, sizeof(buffer));
    zassert_equal(required, ::strlen("NU54:gpio:invalid-pin:driver=0:detail=0"),
                  "production 진단 포맷 길이가 다릅니다.");
    zassert_equal(::strcmp(buffer, "NU54:gpio:invalid-pin:driver=0:detail=0"), 0,
                  "production 진단 포맷 결과가 다릅니다.");
}

ZTEST(m14_core_contract, test_disabled_peripheral_api_links_and_fails_closed)
{
    zassert_false(Wire.setPins(0U, 1U), "비활성 Wire stub가 pin route를 허용했습니다.");
    Wire.begin();
    Wire.beginTransmission(0x52U);
    zassert_equal(Wire.write(0xA5U), 0U, "비활성 Wire stub가 byte를 수락했습니다.");
    zassert_equal(Wire.endTransmission(), 4U, "비활성 Wire stub가 성공 상태를 반환했습니다.");
    zassert_equal(Wire.requestFrom(0x52U, 1U), 0U, "비활성 Wire stub가 수신 byte를 만들었습니다.");
    Wire.end();

    zassert_false(SPI.setPins(0U, 1U, 2U), "비활성 SPI stub가 pin route를 허용했습니다.");
    SPI.begin();
    SPI.beginTransaction(SPISettings(4000000U, MSBFIRST, SPI_MODE0));
    zassert_equal(SPI.transfer(0xA5U), 0U,
                  "비활성 SPI stub가 성공처럼 보이는 수신값을 반환했습니다.");
    SPI.endTransaction();
    SPI.end();

    analogReadResolution(12U);
    zassert_equal(analogRead(0U), -1, "비활성 ADC stub가 유효한 sample을 반환했습니다.");
    analogWriteResolution(8U);
    zassert_false(analogWriteFrequency(0U, 1000U), "비활성 PWM stub가 주파수 설정을 허용했습니다.");
    analogWrite(0U, 127);
    tone(0U, 1000U, 1UL);
    noTone(0U);

    zassert_equal(nucode::arduino::lastDiagnostic(nucode::arduino::DiagnosticSubsystem::wire).code,
                  nucode::arduino::DiagnosticCode::unsupported,
                  "비활성 Wire 공개 진단이 unsupported가 아닙니다.");
    zassert_equal(nucode::arduino::lastDiagnostic(nucode::arduino::DiagnosticSubsystem::spi).code,
                  nucode::arduino::DiagnosticCode::unsupported,
                  "비활성 SPI 공개 진단이 unsupported가 아닙니다.");
    zassert_equal(
        nucode::arduino::lastDiagnostic(nucode::arduino::DiagnosticSubsystem::analog).code,
        nucode::arduino::DiagnosticCode::unsupported,
        "비활성 Analog 공개 진단이 unsupported가 아닙니다.");
}

ZTEST_SUITE(m14_core_contract, nullptr, nullptr, nullptr, nullptr, nullptr);
