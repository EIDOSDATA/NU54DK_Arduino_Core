/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: Standard peripherals (`standard`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 1대 — 1) AnalogReadA0 실행 보드
 * @par Serial Monitor
 * 사용하지 않음
 * @par 필수 sidecar
 * 없음
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 추가 조건 없음
 * @par Metadata
 * identity `NUCODE_NU54DK/AnalogReadA0`, sha256 `7d8f147af20698e5e6b72167e47b31caafa3c4f7d27badda9fdbec96415c696f`
 * @nucode_example_setup_end */

/**
 * @file AnalogReadA0.ino
 * @brief NU54DK A0/P1.12의 고정 12-bit raw ADC 값을 출력합니다.
 * @note NU54DK 보드 전용 ADC 역할을 사용합니다.
 *
 * SPDX-License-Identifier: MIT
 */

/** @brief Serial과 DTS 고정 reference 계약을 시작합니다. */
void setup(void)
{
    Serial.begin(115200U);
    analogReference(AR_DEFAULT);
}

/** @brief A0 raw 값 0..4095 또는 오류 -1을 출력합니다. */
void loop(void)
{
    const int raw = analogRead(A0);
    Serial.print("NUCODE_M7_A0_RAW:");
    Serial.println(raw);
    delay(250U);
}
