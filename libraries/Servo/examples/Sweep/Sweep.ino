/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: Standard peripherals (`standard`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 1대 — 1) Sweep 실행 보드
 * @par Serial Monitor
 * 사용하지 않음
 * @par 필수 sidecar
 * 없음
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI `--upload-field probe_id=<UID>`로 명시 선택합니다.
 * @par 추가 조건
 * 추가 조건 없음
 * @par Metadata
 * identity `Servo/Sweep`, sha256 `0cd140ea849bc8852eda185f113be00b99e4ca0aaa052512cfaf8d028cdb856b`
 * @nucode_example_setup_end */

/**
 * @file Sweep.ino
 * @brief NU54DK PWM22 Servo 출력의 기본 각도 sweep 예제입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <Servo.h>

Servo servo;

void setup()
{
    if (servo.attach(PIN_PWM0) == INVALID_SERVO)
    {
        while (true)
        {
            delay(1000);
        }
    }
}

void loop()
{
    for (int angle = 0; angle <= 180; ++angle)
    {
        servo.write(angle);
        delay(15);
    }
    for (int angle = 180; angle >= 0; --angle)
    {
        servo.write(angle);
        delay(15);
    }
}
