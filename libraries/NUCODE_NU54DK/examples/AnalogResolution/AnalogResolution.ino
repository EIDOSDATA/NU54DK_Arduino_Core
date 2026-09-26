/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: Standard peripherals (`standard`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 1대 — 1) AnalogResolution 실행 보드
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * 없음
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 추가 조건 없음
 * @par Metadata
 * identity `NUCODE_NU54DK/AnalogResolution`, sha256 `316d29fae7898a7f7b14a4f50f6391a987e2d8af505212a318bbadb65e71bac2`
 * @nucode_example_setup_end */

/**
 * @file AnalogResolution.ino
 * @brief NU54DK SAADC A0를 네 hardware 해상도로 읽습니다.
 *
 * SPDX-License-Identifier: MIT
 */

void setup()
{
    Serial.begin(115200);
}

void loop()
{
    const uint8_t resolutions[] = {8, 10, 12, 14};
    for (const uint8_t bits : resolutions)
    {
        analogReadResolution(bits);
        Serial.print(bits);
        Serial.print(" bit: ");
        Serial.println(analogRead(A0));
    }
    delay(1000);
}
