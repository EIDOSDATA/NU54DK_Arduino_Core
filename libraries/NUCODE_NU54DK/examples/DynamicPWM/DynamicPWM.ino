/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: Standard peripherals (`standard`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 1대 — 1) DynamicPWM 실행 보드
 * @par Serial Monitor
 * 사용하지 않음
 * @par 필수 sidecar
 * 없음
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI `--upload-field probe_id=<UID>`로 명시 선택합니다.
 * @par 추가 조건
 * 추가 조건 없음
 * @par Metadata
 * identity `NUCODE_NU54DK/DynamicPWM`, sha256 `4f03e0e6bbdf9e5ce5e2c0c6e92477ab939a156023478d2922a6927d0fb7f145`
 * @nucode_example_setup_end */

/**
 * @file DynamicPWM.ino
 * @brief PWM 해상도와 주파수를 바꾸면서 duty를 출력합니다.
 *
 * SPDX-License-Identifier: MIT
 */

void setup()
{
    analogWriteResolution(12);
    if (!analogWriteFrequency(PIN_PWM0, 1000))
    {
        while (true)
        {
            delay(1000);
        }
    }
}

void loop()
{
    for (int duty = 0; duty <= 4095; duty += 16)
    {
        analogWrite(PIN_PWM0, duty);
        delay(2);
    }
}
