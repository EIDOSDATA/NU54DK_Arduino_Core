/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: Standard peripherals (`standard`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 1대 — 1) InterruptButton 실행 보드
 * @par Serial Monitor
 * 사용하지 않음
 * @par 필수 sidecar
 * 없음
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI `--upload-field probe_id=<UID>`로 명시 선택합니다.
 * @par 추가 조건
 * 추가 조건 없음
 * @par Metadata
 * identity `NUCODE_NU54DK/InterruptButton`, sha256 `c6fce0df4d351ffab27300ab33bb54dd4d06ad164de664be73497d157afc6707`
 * @nucode_example_setup_end */

/**
 * @file InterruptButton.ino
 * @brief NU54DK 버튼 edge interrupt로 내장 LED를 갱신하는 예제입니다.
 * @note ISR에서는 flag만 기록하고 실제 GPIO 처리는 loop에서 수행합니다.
 *
 * SPDX-License-Identifier: MIT
 */

/** @brief ISR에서 loop로 버튼 변화만 전달하는 최소 flag입니다. */
static volatile bool button_changed = false;

/** @brief GPIO ISR에서 blocking 작업 없이 변화 flag만 설정합니다. */
static void on_button_change(void)
{
    button_changed = true;
}

/** @brief 버튼 입력, LED 출력과 raw CHANGE interrupt를 구성합니다. */
void setup(void)
{
    pinMode(LED_BUILTIN, OUTPUT);
    pinMode(PIN_BUTTON0, INPUT_PULLUP);
    attachInterrupt(digitalPinToInterrupt(PIN_BUTTON0), on_button_change, CHANGE);
    button_changed = true;
}

/** @brief 버튼 변화가 있을 때 thread 문맥에서 입력을 읽고 LED를 갱신합니다. */
void loop(void)
{
    if (button_changed)
    {
        button_changed = false;
        const PinStatus button_raw = digitalRead(PIN_BUTTON0);
        digitalWrite(LED_BUILTIN, (button_raw == LOW) ? LOW : HIGH);
    }

    delay(1UL);
}
