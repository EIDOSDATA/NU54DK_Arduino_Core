/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par 목적
 * NU54DK 모델, target, device ID와 reset 원인을 출력합니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: Standard peripherals (`standard`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 1대 — 1) BoardInfo 실행 보드
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * 없음
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 추가 조건 없음
 * @par 준비물
 * - NU54DK 보드 1대 — 1) BoardInfo 실행 보드
 * @par 설정
 * - Tools → Feature set에서 `standard` profile을 선택합니다.
 * - Serial Monitor는 115200 baud로 엽니다.
 * @par 실행 순서
 * - 권장 profile로 현재 Sketch와 metadata에 적힌 각 peer 역할 Sketch를 빌드합니다.
 * - probe가 여러 대이면 `NUCODE_PROBE_UID`를 지정하고 Arduino Upload로 역할별 보드를 구분합니다.
 * - peer·외장 조건을 먼저 준비한 뒤 reset 또는 예제에 명시된 입력으로 실행합니다.
 * @par 성공 출력
 * - Serial 문구 `NU54DK board information`를 포함한 정상 상태 전이를 확인합니다.
 * - Serial 문구 `model:`를 포함한 정상 상태 전이를 확인합니다.
 * - Serial 문구 `target:`를 포함한 정상 상태 전이를 확인합니다.
 * @par 흔한 오류
 * - 권장 profile과 sidecar가 다르면 기능·Kconfig가 빠질 수 있으므로 먼저 설정을 다시 확인합니다.
 * - 여러 probe가 연결된 상태에서 UID를 생략하면 다른 보드에 upload될 수 있습니다.
 * @par 다음 예제
 * - `NUCODE_NU54DK/CounterAlarm`
 * - `NUCODE_NU54DK/DynamicPWM`
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
 * identity `NUCODE_NU54DK/BoardInfo`, sha256 `f97221c21512d0ad04e7a06f177a37c5ed1b7727178b63bb0ea4554b52aa4341`
 * @nucode_example_setup_end */

/**
 * @file BoardInfo.ino
 * @brief NU54DK 모델, target, device ID와 reset 원인을 출력합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_NU54DK.h>

#include <stdio.h>

using nucode::nu54dk::Error;
using nucode::nu54dk::ResetReport;

void setup()
{
    Serial.begin(115200);
    delay(200);

    char device_id[33] = {};
    ResetReport reset{};

    Serial.println("NU54DK board information");
    Serial.print("model: ");
    Serial.println(NU54DK.boardModel());
    Serial.print("target: ");
    Serial.println(NU54DK.boardTarget());
    Serial.print("soc: ");
    Serial.println(NU54DK.socName());
    Serial.print("NCS: ");
    Serial.println(NU54DK.ncsVersion());
    Serial.print("Zephyr: ");
    Serial.println(NU54DK.zephyrVersion());
    Serial.print("Core source: ");
    Serial.println(NU54DK.coreVersion());

    if (NU54DK.deviceId(device_id, sizeof(device_id)) == Error::none)
    {
        Serial.print("raw device ID: ");
        Serial.println(device_id);
    }
    if (NU54DK.resetReport(reset) == Error::none)
    {
        char report[80] = {};
        snprintf(report, sizeof(report), "reset cause=0x%08lx supported=0x%08lx",
                 static_cast<unsigned long>(reset.cause),
                 static_cast<unsigned long>(reset.supported));
        Serial.println(report);
    }
}

void loop()
{
    delay(1000);
}
