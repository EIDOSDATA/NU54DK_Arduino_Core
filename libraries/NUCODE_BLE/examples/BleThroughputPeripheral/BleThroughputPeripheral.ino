/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par 목적
 * NUS 수신 byte를 1초 window로 집계해 throughput을 출력합니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 2대 — 1) BleThroughputCentral (central/sender); 2) BleThroughputPeripheral (peripheral/receiver)
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * 없음
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 표시값은 1초 application payload window이며 RF PHY bit rate가 아닙니다.
 * @par 준비물
 * - NU54DK 보드 2대 — 1) BleThroughputCentral (central/sender); 2) BleThroughputPeripheral (peripheral/receiver)
 * - 표시값은 1초 application payload window이며 RF PHY bit rate가 아닙니다.
 * @par 설정
 * - Tools → Feature set에서 `ble` profile을 선택합니다.
 * - Serial Monitor는 115200 baud로 엽니다.
 * @par 실행 순서
 * - 권장 profile로 현재 Sketch와 metadata에 적힌 각 peer 역할 Sketch를 빌드합니다.
 * - probe가 여러 대이면 `NUCODE_PROBE_UID`를 지정하고 Arduino Upload로 역할별 보드를 구분합니다.
 * - peer·외장 조건을 먼저 준비한 뒤 reset 또는 예제에 명시된 입력으로 실행합니다.
 * @par 성공 출력
 * - Serial 문구 `RX bytes/s:`를 포함한 정상 상태 전이를 확인합니다.
 * @par 흔한 오류
 * - 권장 profile과 sidecar가 다르면 기능·Kconfig가 빠질 수 있으므로 먼저 설정을 다시 확인합니다.
 * - 여러 probe가 연결된 상태에서 UID를 생략하면 다른 보드에 upload될 수 있습니다.
 * - `Throughput peripheral start failed` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * @par 다음 예제
 * - `NUCODE_BLE/ConnectionRadioNotification`
 * - `NUCODE_BLE/ConnectionSubratingCentral`
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
 * Recipe `ble_gap_multilink`; 내부 증거 ID는 metadata에서 관리합니다.
 * 직접 upstream 복사 아님; NCS `99553055607b2e9885fbc80ccd11fa9da81c2df0`, Zephyr `bf801e4e3d19e1ffa76164346480cb7734dd2800`
 * build `clean_installed_compile_required`, runtime `procedure_documented_not_physical_pass`
 * @par Metadata
 * identity `NUCODE_BLE/BleThroughputPeripheral`, sha256 `88b1ea1549417fcc2fb43891ec961dc9500cbc84322f42f62a157612e1d5cfd6`
 * @nucode_example_setup_end */

/**
 * @file BleThroughputPeripheral.ino
 * @brief NUS 수신 byte를 1초 window로 집계해 throughput을 출력합니다.
 */

#include <NUCODE_BLE.h>

std::uint32_t receivedBytes = 0U;
unsigned long windowStartedAt = 0UL;

/** @brief 연결 직후 throughput용 PHY·DLE·MTU 교환을 요청합니다. */
void onNusEvent(nucode::ble::Event event, void *context)
{
    static_cast<void>(context);
    if (event == nucode::ble::Event::connected)
    {
        const nucode::ble::BLEConnectionHandle connection =
            BLEConnection.handle(nucode::ble::BLELinkRole::peripheral);
        static_cast<void>(BLEConnection.requestPhy(connection, true));
        static_cast<void>(BLEConnection.requestDataLength(connection));
        static_cast<void>(BLEConnection.requestMtu(connection));
    }
    else if (event == nucode::ble::Event::ready)
    {
        windowStartedAt = millis();
    }
}

void setup()
{
    Serial.begin(115200);
    BLESerial.onEvent(onNusEvent);
    if (!BLESerial.beginPeripheral("NU54-THR") || !BLESerial.startAdvertising())
    {
        Serial.println("Throughput peripheral start failed");
    }
}

void loop()
{
    BLESerial.poll();
    while (BLESerial.available() > 0)
    {
        static_cast<void>(BLESerial.read());
        ++receivedBytes;
    }
    const unsigned long now = millis();
    if (windowStartedAt != 0UL && now - windowStartedAt >= 1000UL)
    {
        Serial.print("RX bytes/s: ");
        Serial.println(receivedBytes);
        receivedBytes = 0U;
        windowStartedAt = now;
    }
}
