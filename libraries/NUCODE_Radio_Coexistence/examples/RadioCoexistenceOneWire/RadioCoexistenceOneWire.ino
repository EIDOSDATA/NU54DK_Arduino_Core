/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par 목적
 * P1.10 output과 P1.14 grant input을 연결해 1-wire arbitration을 관측합니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE external 1-wire coexistence (`external_coexistence`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 1대 — 1) 1-wire grant simulator와 BLE advertiser
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * prj.conf
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 전원을 끈 상태에서 P1.10(P4-8) output을 P1.14(P4-12) grant input에 연결하고 g/d 명령으로 허용/거부를 확인합니다.
 * @par 준비물
 * - NU54DK 보드 1대 — 1) 1-wire grant simulator와 BLE advertiser
 * - 전원을 끈 상태에서 P1.10(P4-8) output을 P1.14(P4-12) grant input에 연결하고 g/d 명령으로 허용/거부를 확인합니다.
 * @par 설정
 * - Tools → Feature set에서 `external_coexistence` profile을 선택합니다.
 * - Sketch 폴더의 sidecar를 함께 설치합니다: prj.conf
 * - Serial Monitor는 115200 baud로 엽니다.
 * @par 실행 순서
 * - 권장 profile로 현재 Sketch와 metadata에 적힌 각 peer 역할 Sketch를 빌드합니다.
 * - probe가 여러 대이면 `NUCODE_PROBE_UID`를 지정하고 Arduino Upload로 역할별 보드를 구분합니다.
 * - peer·외장 조건을 먼저 준비한 뒤 reset 또는 예제에 명시된 입력으로 실행합니다.
 * @par 성공 출력
 * - Serial 문구 `P1.10을 P1.14에 연결했습니다. g=grant, d=deny`를 포함한 정상 상태 전이를 확인합니다.
 * - Serial 문구 `radio_ready_events=`를 포함한 정상 상태 전이를 확인합니다.
 * - Serial 문구 `delta=`를 포함한 정상 상태 전이를 확인합니다.
 * @par 흔한 오류
 * - 권장 profile과 sidecar가 다르면 기능·Kconfig가 빠질 수 있으므로 먼저 설정을 다시 확인합니다.
 * - 여러 probe가 연결된 상태에서 UID를 생략하면 다른 보드에 upload될 수 있습니다.
 * - `1-wire coexistence start failed` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * - `BLE start failed` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * @par 다음 예제
 * - `NUCODE_Radio_Coexistence/Ble154Coexistence`
 * - `NUCODE_Radio_Coexistence/BleEsbCoexistence`
 * @par 종료와 재시작
 * - 예제의 stop/end/disconnect 또는 유한 완료 흐름 뒤 오류와 자원 반환을 확인합니다.
 * - 실패 문구와 driver 상태를 확인한 뒤 명시적 reset 또는 예제의 재시작 흐름을 사용합니다.
 * @par 보안
 * - wireless_example_no_implicit_security_claim
 * - 무선 연결 성공만으로 인증·암호화·상호운용 보안을 주장하지 않습니다.
 * @par 제한
 * - Compile·Host 검사는 실제 보드 runtime 또는 외부 제품 상호운용 PASS를 대신하지 않습니다.
 * - 목적과 metadata 조건 밖의 성능·동시성·정밀도는 이 예제의 보증 범위가 아닙니다.
 * @par Negative
 * - wrong_profile_or_missing_sidecar
 * - missing_or_wrong_role_peer
 * - startup_or_runtime_error_reported
 * @par Traceability
 * Recipe `radio_coexistence`; 내부 증거 ID는 metadata에서 관리합니다.
 * 직접 upstream 복사 아님; NCS `99553055607b2e9885fbc80ccd11fa9da81c2df0`, Zephyr `bf801e4e3d19e1ffa76164346480cb7734dd2800`
 * build `clean_installed_compile_required`, runtime `procedure_documented_not_physical_pass`
 * @par Metadata
 * identity `NUCODE_Radio_Coexistence/RadioCoexistenceOneWire`, sha256 `c89b2b5d56018e2b2bc86380923db5ad7f8fe15ba24ba542b2e560524e2e59a8`
 * @nucode_example_setup_end */

/**
 * @file RadioCoexistenceOneWire.ino
 * @brief P1.10 output과 P1.14 grant input을 연결해 1-wire arbitration을 관측합니다.
 */

#include <NUCODE_BLE.h>
#include <NUCODE_Radio_Coexistence.h>

using nucode::coexistence::Protocol;

uint32_t lastRadioEvents = 0U;
uint32_t lastReportMs = 0U;

void setup()
{
    Serial.begin(115200);
    static_cast<void>(NUCODECoexistence.begin(500U));
    if (!NUCODECoexistence.beginOneWire())
    {
        Serial.println("1-wire coexistence start failed");
    }
    if (!BLESerial.beginPeripheral("NU54-COEX-1W") || !BLESerial.startAdvertising())
    {
        Serial.println("BLE start failed");
    }
    else
    {
        NUCODECoexistence.setActive(Protocol::ble, true);
    }
    NUCODECoexistence.setActive(Protocol::external_radio, true);
    Serial.println("P1.10을 P1.14에 연결했습니다. g=grant, d=deny");
}

void loop()
{
    BLESerial.poll();
    if (Serial.available() > 0)
    {
        const int command = Serial.read();
        if (command == 'g')
        {
            static_cast<void>(NUCODECoexistence.setExternalGrant(true));
        }
        else if (command == 'd')
        {
            static_cast<void>(NUCODECoexistence.setExternalGrant(false));
        }
    }

    const uint32_t now = millis();
    if (now - lastReportMs >= 1000U)
    {
        lastReportMs = now;
        const uint32_t radioEvents = NUCODECoexistence.radioEventCount();
        NUCODECoexistence.recordRequested(Protocol::external_radio);
        NUCODECoexistence.recordDelivered(Protocol::external_radio, radioEvents,
                                          radioEvents ^ 0xC0E1U);
        Serial.print("radio_ready_events=");
        Serial.print(radioEvents);
        Serial.print(" delta=");
        Serial.println(radioEvents - lastRadioEvents);
        lastRadioEvents = radioEvents;
    }
}
