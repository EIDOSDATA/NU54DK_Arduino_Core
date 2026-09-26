/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: Standard peripherals (`standard`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 1대 — 1) Blink 실행 보드
 * @par Serial Monitor
 * 사용하지 않음
 * @par 필수 sidecar
 * 없음
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 추가 조건 없음
 * @par Metadata
 * identity `NUCODE_NU54DK/Blink`, sha256 `0bf27910efb97c51d1983b21a48d3dcca99822affe690e48afd703a60f305323`
 * @nucode_example_setup_end */

/**
 * @file Blink.ino
 * @brief NU54DK 내장 LED를 250 ms 간격으로 점멸합니다.
 *
 * SPDX-License-Identifier: MIT
 */

/** @brief 내장 LED를 출력으로 초기화합니다. */
void setup()
{
    pinMode(LED_BUILTIN, OUTPUT);
}

/** @brief 내장 LED의 논리 상태를 반복해서 전환합니다. */
void loop()
{
    writeBuiltinLed(true);
    delay(250);
    writeBuiltinLed(false);
    delay(250);
}

/**
 * @brief 내장 LED 상태를 기록합니다.
 * @note loop보다 아래에 두어 Arduino prototype 생성도 함께 검증합니다.
 */
void writeBuiltinLed(bool high)
{
    digitalWrite(LED_BUILTIN, high ? HIGH : LOW);
}
