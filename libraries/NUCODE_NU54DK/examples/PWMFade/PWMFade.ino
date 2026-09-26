/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: Standard peripherals (`standard`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 1대 — 1) PWMFade 실행 보드
 * @par Serial Monitor
 * 사용하지 않음
 * @par 필수 sidecar
 * 없음
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI `--upload-field probe_id=<UID>`로 명시 선택합니다.
 * @par 추가 조건
 * 추가 조건 없음
 * @par Metadata
 * identity `NUCODE_NU54DK/PWMFade`, sha256 `aa11b9ecd6d592a4bc5a2675e1407d0d3b7bab93c2cb0862e0dd15592d27c4e1`
 * @nucode_example_setup_end */

/**
 * @file PWMFade.ino
 * @brief NU54DK PIN_PWM0/P1.10을 8-bit analogWrite로 변화시킵니다.
 * @note NU54DK 보드 전용 PWM 역할을 사용합니다.
 *
 * SPDX-License-Identifier: MIT
 */

namespace
{
    int duty = 0;
    int step = 1;
} // namespace

/** @brief 0% edge에서 PWM 예제를 시작합니다. */
void setup(void)
{
    analogWrite(PIN_PWM0, 0);
}

/** @brief 고정 20 ms period에서 duty 0..255 edge를 왕복합니다. */
void loop(void)
{
    analogWrite(PIN_PWM0, duty);
    duty += step;
    if ((duty == 255) || (duty == 0))
    {
        step = -step;
    }
    delay(10U);
}
