/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: Standard peripherals (`standard`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 1대 — 1) AnalogChannels 실행 보드
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * 없음
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI `--upload-field probe_id=<UID>`로 명시 선택합니다.
 * @par 추가 조건
 * 추가 조건 없음
 * @par Metadata
 * identity `NUCODE_NU54DK/AnalogChannels`, sha256 `0b5b40e1aade2eb46e71d1b22afcb3df362170b73ff352f96ef8898577c83303`
 * @nucode_example_setup_end */

/**
 * @file AnalogChannels.ino
 * @brief 기본 profile에서 강제 탈취 없이 읽을 수 있는 SAADC 별칭을 순회합니다.
 *
 * @details A1~A4는 UART20, A5는 PMIC INT 소유권을 유지하므로 기본 profile에서
 * analogRead()가 -1을 반환합니다. 해당 기능을 종료하고 route를 명시적으로 넘기는
 * 전용 profile을 사용하기 전에는 Core가 이 핀들을 암묵적으로 탈취하지 않습니다.
 *
 * SPDX-License-Identifier: MIT
 */

void setup()
{
    Serial.begin(115200);
    analogReadResolution(12);
}

void loop()
{
    const pin_size_t pins[] = {A0, A6, A7};
    const char *const labels[] = {"AIN5/A0", "AIN6/A6", "AIN7/A7"};
    for (size_t index = 0; index < 3; ++index)
    {
        Serial.print(labels[index]);
        Serial.print(": ");
        Serial.println(analogRead(pins[index]));
    }
    delay(1000);
}
