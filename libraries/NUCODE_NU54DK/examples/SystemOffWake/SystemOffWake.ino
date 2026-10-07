/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par 목적
 * 명령을 받은 뒤 SW0 또는 GRTC wake를 설정하고 System OFF로 진입합니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: Standard peripherals (`standard`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 1대 — 1) SystemOffWake 실행 보드
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * 없음
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * System OFF wake source와 버튼 조건을 확인합니다.
 * @par 준비물
 * - NU54DK 보드 1대 — 1) SystemOffWake 실행 보드
 * - System OFF wake source와 버튼 조건을 확인합니다.
 * @par 설정
 * - Tools → Feature set에서 `standard` profile을 선택합니다.
 * - Serial Monitor는 115200 baud로 엽니다.
 * @par 실행 순서
 * - 권장 profile로 현재 Sketch와 metadata에 적힌 각 peer 역할 Sketch를 빌드합니다.
 * - probe가 여러 대이면 `NUCODE_PROBE_UID`를 지정하고 Arduino Upload로 역할별 보드를 구분합니다.
 * - peer·외장 조건을 먼저 준비한 뒤 reset 또는 예제에 명시된 입력으로 실행합니다.
 * @par 성공 출력
 * - Serial 문구 `press SW0 (P1.13) to wake`를 포함한 정상 상태 전이를 확인합니다.
 * - Serial 문구 `entering System OFF`를 포함한 정상 상태 전이를 확인합니다.
 * - Serial 문구 `GRTC wake in 2 seconds`를 포함한 정상 상태 전이를 확인합니다.
 * @par 흔한 오류
 * - 권장 profile과 sidecar가 다르면 기능·Kconfig가 빠질 수 있으므로 먼저 설정을 다시 확인합니다.
 * - 여러 probe가 연결된 상태에서 UID를 생략하면 다른 보드에 upload될 수 있습니다.
 * @par 다음 예제
 * - `NUCODE_NU54DK/ToneOutput`
 * - `NUCODE_NU54DK/WatchdogBasic`
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
 * Recipe `board_system_power`; 내부 증거 ID는 metadata에서 관리합니다.
 * 직접 upstream 복사 아님; NCS `99553055607b2e9885fbc80ccd11fa9da81c2df0`, Zephyr `bf801e4e3d19e1ffa76164346480cb7734dd2800`
 * build `clean_installed_compile_required`, runtime `procedure_documented_not_physical_pass`
 * @par Metadata
 * identity `NUCODE_NU54DK/SystemOffWake`, sha256 `bdb71c6b2df4a72ab5080f17b1fd388e5482d0a5007287d81a8f3f6b96d472f7`
 * @nucode_example_setup_end */

/**
 * @file SystemOffWake.ino
 * @brief 명령을 받은 뒤 SW0 또는 GRTC wake를 설정하고 System OFF로 진입합니다.
 *
 * Serial Monitor에서 `BUTTON`을 보내면 SW0(P1.13), `TIMER`를 보내면
 * 2초 GRTC wake를 사용합니다. 부팅 직후 자동으로 전원이 꺼지지 않습니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_NU54DK.h>

#include <stdio.h>
#include <string.h>

using nucode::nu54dk::Error;
using nucode::nu54dk::ResetReport;
using nucode::nu54dk::WakeButton;

namespace
{
    char command[16] = {};
    std::size_t command_length = 0U;

    /** @brief System OFF API가 오류로 반환한 경우 결과를 출력합니다. */
    void reportUnexpectedReturn(Error result)
    {
        Serial.println((result == Error::none) ? "unexpected return" : "System OFF rejected");
    }

    /** @brief 한 줄의 대문자 명령을 실행합니다. */
    void executeCommand()
    {
        command[command_length] = '\0';
        if (strcmp(command, "BUTTON") == 0)
        {
            Serial.println("press SW0 (P1.13) to wake");
            Serial.println("entering System OFF");
            Serial.flush();
            delay(50);
            reportUnexpectedReturn(NU54DK.enterSystemOffOnButton(WakeButton::sw0));
        }
        else if (strcmp(command, "TIMER") == 0)
        {
            Serial.println("GRTC wake in 2 seconds");
            Serial.println("entering System OFF");
            Serial.flush();
            delay(50);
            reportUnexpectedReturn(NU54DK.enterSystemOffAfter(2000000ULL));
        }
        else if (command_length != 0U)
        {
            Serial.println("send BUTTON or TIMER");
        }
        command_length = 0U;
    }
} // namespace

void setup()
{
    Serial.begin(115200);
    delay(200);
    ResetReport reset{};
    if (NU54DK.resetReport(reset) == Error::none)
    {
        char message[48] = {};
        snprintf(message, sizeof(message), "boot reset cause=0x%08lx",
                 static_cast<unsigned long>(reset.cause));
        Serial.println(message);
    }
    Serial.println("send BUTTON or TIMER");
}

void loop()
{
    while (Serial.available() > 0)
    {
        const int character = Serial.read();
        if ((character == '\r') || (character == '\n'))
        {
            executeCommand();
        }
        else if ((character >= 0) && (command_length < (sizeof(command) - 1U)))
        {
            command[command_length++] = static_cast<char>(character);
        }
    }
    delay(10);
}
