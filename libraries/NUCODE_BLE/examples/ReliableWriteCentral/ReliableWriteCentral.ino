/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par 목적
 * exact generation link로 512-byte reliable write를 수행하는 central 예제입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 2대 — 1) ReliableWriteCentral (central/client); 2) ReliableWritePeripheral (peripheral/server)
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * 없음
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 추가 조건 없음
 * @par 준비물
 * - NU54DK 보드 2대 — 1) ReliableWriteCentral (central/client); 2) ReliableWritePeripheral (peripheral/server)
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
 * - `failed:` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * - `GATT operation failed, ATT=` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * @par 다음 예제
 * - `NUCODE_BLE/ReliableWritePeripheral`
 * - `NUCODE_BLE/RssiPowerControlCentral`
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
 * identity `NUCODE_BLE/ReliableWriteCentral`, sha256 `7dc3ef8b7d71f63fddaeeddaecd78cf0c659938ab7387aeb4e220d163471cad8`
 * @nucode_example_setup_end */

/**
 * @file ReliableWriteCentral.ino
 * @brief exact generation link로 512-byte reliable write를 수행하는 central 예제입니다.
 */

#include <NUCODE_BLE.h>

const nucode::ble::BLEUuid serviceUuid("8e7e2903-7d8c-4c1a-9d2d-8b6519f77410");
const nucode::ble::BLEUuid valueUuid("8e7e2904-7d8c-4c1a-9d2d-8b6519f77410");
nucode::ble::BLEConnectionHandle peer;
uint8_t payload[512] = {};
bool running = false;
bool restartScan = false;

/** @brief index만으로 재현 가능한 512-byte 값을 만듭니다. */
void buildPayload()
{
    for (size_t index = 0U; index < sizeof(payload); ++index)
    {
        payload[index] = static_cast<uint8_t>(0x5aU ^ static_cast<uint8_t>(index) ^
                                              static_cast<uint8_t>(index >> 8U));
    }
}

/** @brief peripheral에서 다시 읽은 512-byte 값을 검증합니다. */
bool validPayload(const uint8_t *data, size_t length)
{
    return data != nullptr && length == sizeof(payload) &&
           memcmp(data, payload, sizeof(payload)) == 0;
}

/** @brief 현재 BLE driver 오류를 Serial에 출력합니다. */
void reportFailure(const char *operation)
{
    Serial.print(operation);
    Serial.print(" failed: ");
    Serial.println(BLEDevice.lastDriverError());
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
        return;
    }
    if (information.event == nucode::ble::BLEEvent::connected && information.connection == peer)
    {
        if (!BLEConnection.requestMtu(peer))
        {
            reportFailure("MTU request");
        }
        return;
    }
    if (information.event == nucode::ble::BLEEvent::mtu_changed && information.connection == peer)
    {
        if (!BLEClient.discover(peer, serviceUuid, valueUuid))
        {
            reportFailure("GATT discovery");
        }
        return;
    }
    if (information.event == nucode::ble::BLEEvent::disconnected && information.connection == peer)
    {
        peer = nucode::ble::BLEConnectionHandle{};
        restartScan = true;
    }
}

/** @brief discovery 뒤 write하고 같은 exact link에서 값을 다시 읽습니다. */
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
        if (!BLEClient.write(peer, payload, sizeof(payload)))
        {
            reportFailure("reliable write");
        }
    }
    else if (information.event == nucode::ble::BLEGattClientEvent::write_complete)
    {
        if (!BLEClient.read(peer))
        {
            reportFailure("read back");
        }
    }
    else if (information.event == nucode::ble::BLEGattClientEvent::read_complete)
    {
        Serial.println(validPayload(information.data, information.length)
                           ? "512-byte reliable write PASS"
                           : "512-byte reliable write mismatch");
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
    buildPayload();
    BLEDevice.onEventInfo(onBleEvent);
    BLEScan.onResult(onScanResult);
    BLEClient.onDetailedEvent(onClientEvent);
    running = BLEDevice.begin("NU54-WRITE-C") && startScan();
    if (!running)
    {
        reportFailure("reliable write central start");
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
