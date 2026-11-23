/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par 목적
 * Zephyr 소유 console UART를 Arduino Serial로 빌려 쓰는 echo 예제입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: Standard peripherals (`standard`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 1대 — 1) SerialEcho 실행 보드
 * @par Serial Monitor
 * 사용하지 않음
 * @par 필수 sidecar
 * 없음
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 추가 조건 없음
 * @par 준비물
 * - NU54DK 보드 1대 — 1) SerialEcho 실행 보드
 * @par 설정
 * - Tools → Feature set에서 `standard` profile을 선택합니다.
 * - 이 예제는 Serial Monitor 출력을 필수 결과로 사용하지 않습니다.
 * @par 실행 순서
 * - 권장 profile로 현재 Sketch와 metadata에 적힌 각 peer 역할 Sketch를 빌드합니다.
 * - probe가 여러 대이면 `NUCODE_PROBE_UID`를 지정하고 Arduino Upload로 역할별 보드를 구분합니다.
 * - peer·외장 조건을 먼저 준비한 뒤 reset 또는 예제에 명시된 입력으로 실행합니다.
 * @par 성공 출력
 * - Serial 문구 `NUCODE_M6_SERIAL_READY`를 포함한 정상 상태 전이를 확인합니다.
 * - Serial 문구 `NUCODE_M6_ECHO:`를 포함한 정상 상태 전이를 확인합니다.
 * @par 흔한 오류
 * - 권장 profile과 sidecar가 다르면 기능·Kconfig가 빠질 수 있으므로 먼저 설정을 다시 확인합니다.
 * - 여러 probe가 연결된 상태에서 UID를 생략하면 다른 보드에 upload될 수 있습니다.
 * - `NUCODE_M6_ERROR:LINE_TOO_LONG` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * @par 다음 예제
 * - `NUCODE_NU54DK/SettingsStorage`
 * - `NUCODE_NU54DK/SPI00RuntimePins`
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
 * Recipe `serial`; 내부 증거 ID는 metadata에서 관리합니다.
 * 직접 upstream 복사 아님; NCS `99553055607b2e9885fbc80ccd11fa9da81c2df0`, Zephyr `bf801e4e3d19e1ffa76164346480cb7734dd2800`
 * build `clean_installed_compile_required`, runtime `procedure_documented_not_physical_pass`
 * @par Metadata
 * identity `NUCODE_NU54DK/SerialEcho`, sha256 `eedf2c89fc57cea56062928fbe1746aa969367dda87c2de85b98e2757e4c87ca`
 * @nucode_example_setup_end */

/**
 * @file SerialEcho.ino
 * @brief Zephyr 소유 console UART를 Arduino Serial로 빌려 쓰는 echo 예제입니다.
 * @note Serial은 보드 Devicetree가 선택한 console UART를 재구성하지 않습니다.
 *
 * SPDX-License-Identifier: MIT
 */

/** @brief 개행과 문자열 종료 문자를 제외한 최대 payload 길이는 127 byte입니다. */
static char line_buffer[128] = {};

/** @brief 현재 line buffer에 저장한 payload 길이입니다. */
static size_t line_length = 0U;

/** @brief 현재 입력 줄이 line buffer 용량을 초과했는지 나타냅니다. */
static bool line_overflow = false;

/** @brief Serial을 Zephyr DTS 속도 그대로 시작하고 HIL 준비 token을 출력합니다. */
void setup(void)
{
    Serial.begin(115200U);
    if (Serial)
    {
        Serial.println("NUCODE_M6_SERIAL_READY");
    }
}

/**
 * @brief 완성된 입력 줄을 echo하거나 길이 초과 오류를 출력합니다.
 */
static void finish_line(void)
{
    if (line_overflow)
    {
        Serial.println("NUCODE_M6_ERROR:LINE_TOO_LONG");
    }
    else
    {
        line_buffer[line_length] = '\0';
        Serial.print("NUCODE_M6_ECHO:");
        Serial.println(line_buffer);
    }

    line_length = 0U;
    line_overflow = false;
}

/**
 * @brief 한 RX byte를 CRLF line protocol에 반영합니다.
 *
 * @param value 수신한 byte입니다.
 */
static void consume_serial_byte(char value)
{
    if (value == '\r')
    {
        return;
    }
    if (value == '\n')
    {
        finish_line();
        return;
    }

    if (!line_overflow && (line_length < (sizeof(line_buffer) - 1U)))
    {
        line_buffer[line_length++] = value;
    }
    else
    {
        line_overflow = true;
    }
}

/** @brief 수신 byte를 비우고 완성된 줄마다 echo 응답을 출력합니다. */
void loop(void)
{
    while (Serial.available() > 0)
    {
        const int value = Serial.read();
        if (value < 0)
        {
            break;
        }
        consume_serial_byte(static_cast<char>(value));
    }

    delay(1UL);
}
