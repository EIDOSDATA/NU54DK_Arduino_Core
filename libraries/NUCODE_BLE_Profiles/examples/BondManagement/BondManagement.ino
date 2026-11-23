/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par 목적
 * 명시적으로 무장한 동안 요청 peer 자신의 LE bond만 삭제합니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 2대 — 1) 사용자 무장 BMS server; 2) 암호화·bond된 BMS 요청 peer
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * 없음
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 기본 미무장입니다. Serial 명령과 예제 authorization을 명시 승인한 한 요청 peer의 bond만 opcode 03으로 삭제하며 전체 삭제를 제공하지 않습니다.
 * @par 준비물
 * - NU54DK 보드 2대 — 1) 사용자 무장 BMS server; 2) 암호화·bond된 BMS 요청 peer
 * - 기본 미무장입니다. Serial 명령과 예제 authorization을 명시 승인한 한 요청 peer의 bond만 opcode 03으로 삭제하며 전체 삭제를 제공하지 않습니다.
 * @par 설정
 * - Tools → Feature set에서 `ble` profile을 선택합니다.
 * - Serial Monitor는 115200 baud로 엽니다.
 * @par 실행 순서
 * - 권장 profile로 현재 Sketch와 metadata에 적힌 각 peer 역할 Sketch를 빌드합니다.
 * - probe가 여러 대이면 `NUCODE_PROBE_UID`를 지정하고 Arduino Upload로 역할별 보드를 구분합니다.
 * - peer·외장 조건을 먼저 준비한 뒤 reset 또는 예제에 명시된 입력으로 실행합니다.
 * @par 성공 출력
 * - Serial 문구 `bond deletion armed`를 포함한 정상 상태 전이를 확인합니다.
 * - Serial 문구 `bond deletion accepted`를 포함한 정상 상태 전이를 확인합니다.
 * @par 흔한 오류
 * - 권장 profile과 sidecar가 다르면 기능·Kconfig가 빠질 수 있으므로 먼저 설정을 다시 확인합니다.
 * - 여러 probe가 연결된 상태에서 UID를 생략하면 다른 보드에 upload될 수 있습니다.
 * @par 다음 예제
 * - `NUCODE_BLE_Profiles/GlucoseSensor`
 * - `NUCODE_BLE_Profiles/ObjectClient`
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
 * Recipe `ble_profiles_and_ecosystems`; 내부 증거 ID는 metadata에서 관리합니다.
 * 직접 upstream 복사 아님; NCS `99553055607b2e9885fbc80ccd11fa9da81c2df0`, Zephyr `bf801e4e3d19e1ffa76164346480cb7734dd2800`
 * build `clean_installed_compile_required`, runtime `procedure_documented_not_physical_pass`
 * @par Metadata
 * identity `NUCODE_BLE_Profiles/BondManagement`, sha256 `2859b61ac6bd000c95df1f20324b2400f29a709a8d8e5818b3f3ee7205c9918e`
 * @nucode_example_setup_end */

/**
 * @file BondManagement.ino
 * @brief 명시적으로 무장한 동안 요청 peer 자신의 LE bond만 삭제합니다.
 * @par 목적
 * 암호화·bond 확인과 application authorization을 함께 사용하는 BMS 예제입니다.
 * @par 준비물
 * NU54DK와 BMS write가 가능한 bonded BLE client.
 * @par 설정
 * Feature set BLE NUS, 115200 baud. 인증코드 "delete-this-bond"는 데모 의사 확인 문구입니다.
 * @par 실행 순서
 * client를 pairing한 뒤 Serial 'a'로 30초 무장합니다. client가 0x2aa4에 opcode 03과
 * 문구 bytes를 Write Request로 보냅니다. 's'를 입력하면 종료합니다.
 * @par 성공 출력
 * bond deletion accepted의 수가 증가합니다. 영속 삭제는 재연결/재부팅으로 별도 확인합니다.
 * @par 흔한 오류
 * 미무장·미암호화·잘못된 문구·다른 opcode는 거부합니다. 전체 bond 삭제는 지원하지 않습니다.
 * @par 다음 예제
 * NUCODE_BLE_Security의 GattCachePeripheral과 pairing 예제를 참고합니다.
 */
#include <NUCODE_BLE_Profiles.h>
#include <NUCODE_BLE_Security.h>
using namespace nucode::ble;
using namespace nucode::ble::profiles;
BondManagementService bonds;
uint32_t armedAt = 0U;
uint32_t lastAccepted = 0U;
bool running = false;

/** @brief callback에서 블로킹 없이 데모 삭제 의도를 확인합니다. */
bool authorizeDelete(const BondDeleteRequest &request, void *)
{
    const char expected[] = "delete-this-bond";
    if (request.length != sizeof(expected) - 1U)
    {
        return false;
    }
    uint8_t difference = 0U;
    for (size_t i = 0U; i < request.length; ++i)
    {
        difference |= request.authorization_code[i] ^ static_cast<uint8_t>(expected[i]);
    }
    return difference == 0U;
}
void onSecurity(const SecurityEventRecord &event, void *)
{
    if (event.event == SecurityEvent::pairing_requested)
    {
        static_cast<void>(BLESecurity.acceptPairing(event.connection, true));
    }
}
void setup()
{
    Serial.begin(115200);
    SecurityConfig security;
    security.io_capability = SecurityIoCapability::no_input_output;
    BLESecurity.onEvent(onSecurity);
    running = BLESecurity.begin(security) && bonds.begin(authorizeDelete) &&
              BLEDevice.begin("NU54-BONDS") && BLEAdvertising.clear() &&
              BLEAdvertising.addServiceUuid(BLEUuid(0x181eU)) && BLEAdvertising.start();
    Serial.println(running ? "bond service ready; Serial a arms 30 seconds"
                           : "bond service failed");
}
void loop()
{
    if (!running)
    {
        return;
    }
    BLEDevice.poll();
    BLESecurity.poll();
    if (Serial.available() > 0)
    {
        const int command = Serial.read();
        if (command == 'a')
        {
            armedAt = millis();
            bonds.setArmed(true);
            Serial.println("bond deletion armed");
        }
        else if (command == 's')
        {
            bonds.setArmed(false);
            BLEDevice.end();
            running = false;
        }
    }
    if (bonds.armed() && millis() - armedAt >= 30000U)
    {
        bonds.setArmed(false);
    }
    if (bonds.acceptedCount() != lastAccepted)
    {
        lastAccepted = bonds.acceptedCount();
        bonds.setArmed(false);
        Serial.println("bond deletion accepted");
    }
}
