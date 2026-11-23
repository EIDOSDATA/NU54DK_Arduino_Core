/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par 목적
 * 네 descriptor를 찾고 한 ATT Read Multiple로 읽는 central 예제입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 2대 — 1) GattAuthorization 실행 보드; 2) GattDescriptors 실행 보드
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * 없음
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 추가 조건 없음
 * @par 준비물
 * - NU54DK 보드 2대 — 1) GattAuthorization 실행 보드; 2) GattDescriptors 실행 보드
 * @par 설정
 * - Tools → Feature set에서 `ble` profile을 선택합니다.
 * - Serial Monitor는 115200 baud로 엽니다.
 * @par 실행 순서
 * - 권장 profile로 현재 Sketch와 metadata에 적힌 각 peer 역할 Sketch를 빌드합니다.
 * - probe가 여러 대이면 `NUCODE_PROBE_UID`를 지정하고 Arduino Upload로 역할별 보드를 구분합니다.
 * - peer·외장 조건을 먼저 준비한 뒤 reset 또는 예제에 명시된 입력으로 실행합니다.
 * @par 성공 출력
 * - Serial 문구 `four descriptor bytes:`를 포함한 정상 상태 전이를 확인합니다.
 * @par 흔한 오류
 * - 권장 profile과 sidecar가 다르면 기능·Kconfig가 빠질 수 있으므로 먼저 설정을 다시 확인합니다.
 * - 여러 probe가 연결된 상태에서 UID를 생략하면 다른 보드에 upload될 수 있습니다.
 * - `failed:` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * - `GATT operation failed, ATT=` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * - `descriptor identity mismatch` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * @par 다음 예제
 * - `NUCODE_BLE/L2capCocClient`
 * - `NUCODE_BLE/L2capCocServer`
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
 * Recipe `ble_gatt`; 내부 증거 ID는 metadata에서 관리합니다.
 * 직접 upstream 복사 아님; NCS `99553055607b2e9885fbc80ccd11fa9da81c2df0`, Zephyr `bf801e4e3d19e1ffa76164346480cb7734dd2800`
 * build `clean_installed_compile_required`, runtime `procedure_documented_not_physical_pass`
 * @par Metadata
 * identity `NUCODE_BLE/GattDescriptors`, sha256 `2a18fb1e8f01772b210b99ed316ea29aed89e7a5f61991a75c17ff554e1a3f40`
 * @nucode_example_setup_end */

/**
 * @file GattDescriptors.ino
 * @brief 네 descriptor를 찾고 한 ATT Read Multiple로 읽는 central 예제입니다.
 */

#include <NUCODE_BLE.h>

const nucode::ble::BLEUuid serviceUuid("8e7e2905-7d8c-4c1a-9d2d-8b6519f77410");
const nucode::ble::BLEUuid valueUuid("8e7e2906-7d8c-4c1a-9d2d-8b6519f77410");
const nucode::ble::BLEUuid descriptorUuids[] = {
    nucode::ble::BLEUuid("8e7e2910-7d8c-4c1a-9d2d-8b6519f77410"),
    nucode::ble::BLEUuid("8e7e2911-7d8c-4c1a-9d2d-8b6519f77410"),
    nucode::ble::BLEUuid("8e7e2912-7d8c-4c1a-9d2d-8b6519f77410"),
    nucode::ble::BLEUuid("8e7e2913-7d8c-4c1a-9d2d-8b6519f77410"),
};
const uint8_t unlockToken[] = {0x4eU, 0x55U, 0x35U, 0x34U};
nucode::ble::BLEConnectionHandle peer;
uint16_t descriptorHandles[4] = {};
size_t descriptorIndex = 0U;
bool running = false;
bool restartScan = false;

/** @brief 현재 BLE driver 오류를 Serial에 출력합니다. */
void reportFailure(const char *operation)
{
    Serial.print(operation);
    Serial.print(" failed: ");
    Serial.println(BLEDevice.lastDriverError());
}

/** @brief 다음 exact descriptor를 찾거나 unlock write를 시작합니다. */
void continueDiscovery()
{
    if (descriptorIndex < 4U)
    {
        if (!BLEClient.discoverDescriptor(peer, descriptorUuids[descriptorIndex]))
        {
            reportFailure("descriptor discovery");
        }
        return;
    }
    if (!BLEClient.write(peer, unlockToken, sizeof(unlockToken)))
    {
        reportFailure("unlock write");
    }
}

/** @brief service UUID를 가진 connectable peer 하나에 연결합니다. */
void onScanResult(const nucode::ble::BLEScanResult &result, void *context)
{
    static_cast<void>(context);
    if (peer.valid() || !result.connectable || result.scan_response)
    {
        return;
    }
    if (!BLEScan.stop() || !BLEConnection.connect(result.address, peer))
    {
        reportFailure("connect");
        restartScan = true;
    }
}

/** @brief exact generation link의 연결·MTU·해제 수명을 처리합니다. */
void onBleEvent(const nucode::ble::BLEEventInfo &information, void *context)
{
    static_cast<void>(context);
    if (information.event == nucode::ble::BLEEvent::error)
    {
        reportFailure("BLE");
    }
    else if (information.event == nucode::ble::BLEEvent::connected &&
             information.connection == peer && !BLEConnection.requestMtu(peer))
    {
        reportFailure("MTU request");
    }
    else if (information.event == nucode::ble::BLEEvent::mtu_changed &&
             information.connection == peer && !BLEClient.discover(peer, serviceUuid, valueUuid))
    {
        reportFailure("GATT discovery");
    }
    else if (information.event == nucode::ble::BLEEvent::disconnected &&
             information.connection == peer)
    {
        peer = nucode::ble::BLEConnectionHandle{};
        descriptorIndex = 0U;
        restartScan = true;
    }
}

/** @brief discovery·unlock·Read Multiple 결과를 main thread에서 순서대로 처리합니다. */
void onClientEvent(const nucode::ble::BLEGattClientEventInfo &information, void *context)
{
    static_cast<void>(context);
    if (information.connection != peer)
    {
        return;
    }
    if (information.event == nucode::ble::BLEGattClientEvent::operation_failed)
    {
        Serial.print("GATT operation failed, ATT=");
        Serial.println(information.att_error);
    }
    else if (information.event == nucode::ble::BLEGattClientEvent::discovery_complete)
    {
        continueDiscovery();
    }
    else if (information.event ==
             nucode::ble::BLEGattClientEvent::descriptor_discovery_complete)
    {
        const nucode::ble::BLERemoteDescriptor descriptor =
            BLEClient.remoteDescriptor(peer, descriptorIndex);
        if (!descriptor.valid() || descriptor.uuid() != descriptorUuids[descriptorIndex])
        {
            Serial.println("descriptor identity mismatch");
            return;
        }
        descriptorHandles[descriptorIndex++] = descriptor.handle();
        continueDiscovery();
    }
    else if (information.event == nucode::ble::BLEGattClientEvent::write_complete)
    {
        if (!BLEClient.readMultiple(peer, descriptorHandles, 4U))
        {
            reportFailure("read multiple");
        }
    }
    else if (information.event == nucode::ble::BLEGattClientEvent::read_multiple_complete)
    {
        Serial.print("four descriptor bytes: ");
        Serial.println(information.length);
    }
}

/** @brief service filter를 유지한 active scan을 시작합니다. */
bool startScan()
{
    return BLEScan.clearFilters() && BLEScan.filterServiceUuid(serviceUuid) && BLEScan.start(true);
}

void setup()
{
    Serial.begin(115200);
    BLEDevice.onEventInfo(onBleEvent);
    BLEScan.onResult(onScanResult);
    BLEClient.onDetailedEvent(onClientEvent);
    running = BLEDevice.begin("NU54-DESC") && startScan();
    if (!running)
    {
        reportFailure("descriptor central start");
    }
}

void loop()
{
    if (!running)
    {
        return;
    }
    BLEDevice.poll();
    if (restartScan && !peer.valid())
    {
        restartScan = false;
        if (!startScan())
        {
            reportFailure("scan restart");
        }
    }
}
