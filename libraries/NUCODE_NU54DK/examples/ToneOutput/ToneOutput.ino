/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: Standard peripherals (`standard`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 1대 — 1) ToneOutput 실행 보드
 * @par Serial Monitor
 * 사용하지 않음
 * @par 필수 sidecar
 * 없음
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 추가 조건 없음
 * @par Metadata
 * identity `NUCODE_NU54DK/ToneOutput`, sha256 `cd9cfc32f0bd81101888628a995c5251482099149025bde44254b640a699fa6b`
 * @nucode_example_setup_end */

/**
 * @file ToneOutput.ino
 * @brief PWM21의 유한 duration tone과 noTone 동작을 보여줍니다.
 *
 * SPDX-License-Identifier: MIT
 */

void setup()
{
}

void loop()
{
    tone(PIN_PWM0, 440, 250);
    delay(500);
    tone(PIN_PWM0, 880);
    delay(250);
    noTone(PIN_PWM0);
    delay(500);
}
