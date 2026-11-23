/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par 목적
 * 한 NU54DK가 central 1-link와 peripheral 1-link를 동시에 유지하는 예제입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 1대 — 1) MixedRoleLinks 실행 보드
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * 없음
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 동작에 필요한 compatible BLE peer 또는 mobile/host client를 별도로 준비합니다.
 * @par 준비물
 * - NU54DK 보드 1대 — 1) MixedRoleLinks 실행 보드
 * - 동작에 필요한 compatible BLE peer 또는 mobile/host client를 별도로 준비합니다.
 * @par 설정
 * - Tools → Feature set에서 `ble` profile을 선택합니다.
 * - Serial Monitor는 115200 baud로 엽니다.
 * @par 실행 순서
 * - 권장 profile로 현재 Sketch와 metadata에 적힌 각 peer 역할 Sketch를 빌드합니다.
 * - probe가 여러 대이면 `NUCODE_PROBE_UID`를 지정하고 Arduino Upload로 역할별 보드를 구분합니다.
 * - peer·외장 조건을 먼저 준비한 뒤 reset 또는 예제에 명시된 입력으로 실행합니다.
 * @par 성공 출력
 * - Serial Monitor에서 오류 문구 없이 목적 기능의 상태 전이가 완료되는지 확인합니다.
 * @par 흔한 오류
 * - 권장 profile과 sidecar가 다르면 기능·Kconfig가 빠질 수 있으므로 먼저 설정을 다시 확인합니다.
 * - 여러 probe가 연결된 상태에서 UID를 생략하면 다른 보드에 upload될 수 있습니다.
 * - `mixed-role setup failed` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * - `central connect failed` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * - `peripheral advertising failed` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * @par 다음 예제
 * - `NUCODE_BLE/MultipleAdvertisingSets`
 * - `NUCODE_BLE/MultipleBleIdentities`
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
 * identity `NUCODE_BLE/MixedRoleLinks`, sha256 `5861e4602eff466bfa34060ec974be7147fbbc1ef42f7c334cc52b9704b1119a`
 * @nucode_example_setup_end */

/**
 * @file MixedRoleLinks.ino
 * @brief 한 NU54DK가 central 1-link와 peripheral 1-link를 동시에 유지하는 예제입니다.
 *
 * Central peer는 `NU54-GAP-P`로 광고해야 하며, 세 번째 peer는 `NU54-MIXED`에 연결합니다.
 * 도구 → Feature set → BLE NUS를 선택해야 합니다.
 */

#include <NUCODE_BLE.h>

nucode::ble::BLEAddress centralPeerAddress;
nucode::ble::BLEConnectionHandle centralLink;
nucode::ble::BLEConnectionHandle peripheralLink;
bool centralPeerFound = false;
bool startPeripheralAdvertising = false;

/** @brief exact-name scan 결과에서 central 역할로 연결할 주소를 보존합니다. */
void onScanResult(const nucode::ble::BLEScanResult &result, void *context)
{
    static_cast<void>(context);
    if (!centralPeerFound)
    {
        centralPeerAddress = result.address;
        centralPeerFound = true;
    }
}

/** @brief link별 generation handle과 local 역할을 main thread에서 보존합니다. */
void onBleEvent(const nucode::ble::BLEEventInfo &information, void *context)
{
    static_cast<void>(context);
    if (information.event == nucode::ble::BLEEvent::connected)
    {
        if (information.role == nucode::ble::BLELinkRole::central)
        {
            centralLink = information.connection;
            startPeripheralAdvertising = true;
        }
        else if (information.role == nucode::ble::BLELinkRole::peripheral)
        {
            peripheralLink = information.connection;
        }
    }
    else if (information.event == nucode::ble::BLEEvent::disconnected)
    {
        if (information.connection == centralLink)
        {
            centralLink = nucode::ble::BLEConnectionHandle{};
        }
        if (information.connection == peripheralLink)
        {
            peripheralLink = nucode::ble::BLEConnectionHandle{};
        }
    }
}

void setup()
{
    Serial.begin(115200);
    BLEDevice.onEventInfo(onBleEvent);
    BLEScan.onResult(onScanResult);
    if (!BLEDevice.begin("NU54-MIXED") || !BLEAdvertising.clear() ||
        !BLEAdvertising.setConnectable(true) || !BLEScan.clearFilters() ||
        !BLEScan.filterName("NU54-GAP-P") || !BLEScan.start(true))
    {
        Serial.println("mixed-role setup failed");
    }
}

void loop()
{
    BLEDevice.poll();
    if (centralPeerFound && !centralLink.valid())
    {
        centralPeerFound = false;
        if (!BLEConnection.connect(centralPeerAddress, centralLink))
        {
            Serial.println("central connect failed");
        }
    }
    if (startPeripheralAdvertising && BLEConnection.connected(centralLink))
    {
        startPeripheralAdvertising = false;
        if (!BLEAdvertising.start())
        {
            Serial.println("peripheral advertising failed");
        }
    }
}
