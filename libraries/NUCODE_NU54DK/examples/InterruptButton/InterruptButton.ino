/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par 목적
 * NU54DK 버튼 edge interrupt로 내장 LED를 갱신하는 예제입니다.
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
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 추가 조건 없음
 * @par 준비물
 * - NU54DK 보드 1대 — 1) InterruptButton 실행 보드
 * @par 설정
 * - Tools → Feature set에서 `standard` profile을 선택합니다.
 * - 이 예제는 Serial Monitor 출력을 필수 결과로 사용하지 않습니다.
 * @par 실행 순서
 * - 권장 profile로 현재 Sketch와 metadata에 적힌 각 peer 역할 Sketch를 빌드합니다.
 * - probe가 여러 대이면 `NUCODE_PROBE_UID`를 지정하고 Arduino Upload로 역할별 보드를 구분합니다.
 * - peer·외장 조건을 먼저 준비한 뒤 reset 또는 예제에 명시된 입력으로 실행합니다.
 * @par 성공 출력
 * - 목적에 적힌 LED·pin·peer 동작을 직접 확인합니다. Compile PASS만으로 runtime PASS로 처리하지 않습니다.
 * @par 흔한 오류
 * - 권장 profile과 sidecar가 다르면 기능·Kconfig가 빠질 수 있으므로 먼저 설정을 다시 확인합니다.
 * - 여러 probe가 연결된 상태에서 UID를 생략하면 다른 보드에 upload될 수 있습니다.
 * @par 다음 예제
 * - `NUCODE_NU54DK/PWMFade`
 * - `NUCODE_NU54DK/Serial1RuntimePins`
 * @par 종료와 재시작
 * - 예제의 stop/end/disconnect 또는 유한 완료 흐름 뒤 오류와 자원 반환을 확인합니다.
 * - 실패 문구와 driver 상태를 확인한 뒤 명시적 reset 또는 예제의 재시작 흐름을 사용합니다.
 * @par 보안
 * - no_security_property_claimed
 * - 이 예제는 별도의 보안 속성을 주장하지 않습니다.
 * @par 제한
 * - Compile·Host 검사는 실제 보드 runtime 또는 외부 제품 상호운용 PASS를 대신하지 않습니다.
 * - 목적과 metadata 조건 밖의 성능·동시성·정밀도는 이 예제의 보증 범위가 아닙니다.
 * @par Negative
 * - wrong_profile_or_missing_sidecar
 * - missing_or_wrong_role_peer
 * - startup_or_runtime_error_reported
 * @par Traceability
 * Recipe `gpio_interrupt`; 내부 증거 ID는 metadata에서 관리합니다.
 * 직접 upstream 복사 아님; NCS `99553055607b2e9885fbc80ccd11fa9da81c2df0`, Zephyr `bf801e4e3d19e1ffa76164346480cb7734dd2800`
 * build `clean_installed_compile_required`, runtime `procedure_documented_not_physical_pass`
 * @par Metadata
 * identity `NUCODE_NU54DK/InterruptButton`, sha256 `5ee2415d8fed97122291c40596b0b3384a95d486303fba729141504630e2c217`
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
