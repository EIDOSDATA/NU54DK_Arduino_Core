/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par 목적
 * NU54DK PIN_PWM0/P1.10을 8-bit analogWrite로 변화시킵니다.
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
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 추가 조건 없음
 * @par 준비물
 * - NU54DK 보드 1대 — 1) PWMFade 실행 보드
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
 * - `NUCODE_NU54DK/Serial1RuntimePins`
 * - `NUCODE_NU54DK/SerialEcho`
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
 * Recipe `analog_pwm_tone`; 내부 증거 ID는 metadata에서 관리합니다.
 * 직접 upstream 복사 아님; NCS `99553055607b2e9885fbc80ccd11fa9da81c2df0`, Zephyr `bf801e4e3d19e1ffa76164346480cb7734dd2800`
 * build `clean_installed_compile_required`, runtime `procedure_documented_not_physical_pass`
 * @par Metadata
 * identity `NUCODE_NU54DK/PWMFade`, sha256 `a8eac28fc705272117004c7d9e749cad4d2da3246f933eada3856478df452592`
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
