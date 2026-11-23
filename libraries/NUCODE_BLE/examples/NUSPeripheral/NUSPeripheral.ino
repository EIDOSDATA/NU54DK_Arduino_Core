/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par 목적
 * NU54DK를 Nordic UART Service Peripheral로 실행합니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 2대 — 1) NUSCentral (central/client); 2) NUSPeripheral (peripheral/server)
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * 없음
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 추가 조건 없음
 * @par 준비물
 * - NU54DK 보드 2대 — 1) NUSCentral (central/client); 2) NUSPeripheral (peripheral/server)
 * @par 설정
 * - Tools → Feature set에서 `ble` profile을 선택합니다.
 * - Serial Monitor는 115200 baud로 엽니다.
 * @par 실행 순서
 * - 권장 profile로 현재 Sketch와 metadata에 적힌 각 peer 역할 Sketch를 빌드합니다.
 * - probe가 여러 대이면 `NUCODE_PROBE_UID`를 지정하고 Arduino Upload로 역할별 보드를 구분합니다.
 * - peer·외장 조건을 먼저 준비한 뒤 reset 또는 예제에 명시된 입력으로 실행합니다.
 * @par 성공 출력
 * - Serial 문구 `BLE advertising started`를 포함한 정상 상태 전이를 확인합니다.
 * - Serial 문구 `BLE connected`를 포함한 정상 상태 전이를 확인합니다.
 * - Serial 문구 `BLE NUS ready`를 포함한 정상 상태 전이를 확인합니다.
 * @par 흔한 오류
 * - 권장 profile과 sidecar가 다르면 기능·Kconfig가 빠질 수 있으므로 먼저 설정을 다시 확인합니다.
 * - 여러 probe가 연결된 상태에서 UID를 생략하면 다른 보드에 upload될 수 있습니다.
 * - `BLE error` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * - `BLE NUS Peripheral start failed` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * @par 다음 예제
 * - `NUCODE_BLE/PastReceiver`
 * - `NUCODE_BLE/PastSender`
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
 * Recipe `ble_uart`; 내부 증거 ID는 metadata에서 관리합니다.
 * 직접 upstream 복사 아님; NCS `99553055607b2e9885fbc80ccd11fa9da81c2df0`, Zephyr `bf801e4e3d19e1ffa76164346480cb7734dd2800`
 * build `clean_installed_compile_required`, runtime `procedure_documented_not_physical_pass`
 * @par Metadata
 * identity `NUCODE_BLE/NUSPeripheral`, sha256 `a225be683413cf8fc2875bc1a7ef25ffa68cc15558f690d0aa1d1fc707bdae18`
 * @nucode_example_setup_end */

/**
 * @file NUSPeripheral.ino
 * @brief NU54DK를 Nordic UART Service Peripheral로 실행합니다.
 *
 * 도구 → Feature set → BLE NUS를 선택해야 합니다.
 */

#include <NUCODE_BLE.h>

/** @brief BLE 상태를 Arduino main 문맥의 Serial에 기록합니다. */
void onBleEvent(nucode::ble::Event event, void *context)
{
    (void)context;
    switch (event)
    {
    case nucode::ble::Event::advertising_started:
        Serial.println("BLE advertising started");
        break;
    case nucode::ble::Event::connected:
        Serial.println("BLE connected");
        break;
    case nucode::ble::Event::ready:
        Serial.println("BLE NUS ready");
        break;
    case nucode::ble::Event::disconnected:
        Serial.println("BLE disconnected");
        break;
    case nucode::ble::Event::error:
        /** @brief Event queue에 오류 snapshot이 없으므로 오래된 전역 오류값을 출력하지 않습니다. */
        Serial.println("BLE error");
        break;
    case nucode::ble::Event::received:
        /** @brief 수신 데이터는 아래 Stream 경로에서 원문 그대로 출력합니다. */
        break;
    case nucode::ble::Event::scan_started:
        /** @brief Peripheral 역할에서는 발생하지 않습니다. */
        break;
    }
}

void setup()
{
    Serial.begin(115200);
    BLESerial.onEvent(onBleEvent);
    if (!BLESerial.beginPeripheral("NU54-NUS") || !BLESerial.startAdvertising())
    {
        Serial.println("BLE NUS Peripheral start failed");
    }
}

void loop()
{
    BLESerial.poll();
    while (BLESerial.available() > 0)
    {
        Serial.write(static_cast<uint8_t>(BLESerial.read()));
    }
    while (Serial.available() > 0 && BLESerial.ready())
    {
        BLESerial.write(static_cast<uint8_t>(Serial.read()));
    }
}
