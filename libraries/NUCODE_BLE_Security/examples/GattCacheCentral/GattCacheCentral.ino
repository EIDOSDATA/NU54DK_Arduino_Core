/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par 목적
 * bonded peer의 hash를 확인해 GATT handle cache를 복원하거나 재탐색하는 예제입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 2대 — 1) GattCacheCentral (central/client); 2) GattCachePeripheral (peripheral/server)
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * 없음
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 추가 조건 없음
 * @par 준비물
 * - NU54DK 보드 2대 — 1) GattCacheCentral (central/client); 2) GattCachePeripheral (peripheral/server)
 * @par 설정
 * - Tools → Feature set에서 `ble` profile을 선택합니다.
 * - Serial Monitor는 115200 baud로 엽니다.
 * @par 실행 순서
 * - 권장 profile로 현재 Sketch와 metadata에 적힌 각 peer 역할 Sketch를 빌드합니다.
 * - probe가 여러 대이면 `NUCODE_PROBE_UID`를 지정하고 Arduino Upload로 역할별 보드를 구분합니다.
 * - peer·외장 조건을 먼저 준비한 뒤 reset 또는 예제에 명시된 입력으로 실행합니다.
 * @par 성공 출력
 * - Serial 문구 `GATT cache saved after discovery`를 포함한 정상 상태 전이를 확인합니다.
 * - Serial 문구 `GATT cache restored after hash match`를 포함한 정상 상태 전이를 확인합니다.
 * - Serial 문구 `Cached value bytes:`를 포함한 정상 상태 전이를 확인합니다.
 * @par 흔한 오류
 * - 권장 profile과 sidecar가 다르면 기능·Kconfig가 빠질 수 있으므로 먼저 설정을 다시 확인합니다.
 * - 여러 probe가 연결된 상태에서 UID를 생략하면 다른 보드에 upload될 수 있습니다.
 * - `GATT cache scan stop failed` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * - `GATT cache security request failed` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * - `GATT cache pairing approval failed` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * @par 다음 예제
 * - `NUCODE_BLE_Security/GattCachePeripheral`
 * - `NUCODE_BLE_Security/HeartRate`
 * @par 종료와 재시작
 * - 예제의 stop/end/disconnect 또는 유한 완료 흐름 뒤 오류와 자원 반환을 확인합니다.
 * - 실패 문구와 driver 상태를 확인한 뒤 명시적 reset 또는 예제의 재시작 흐름을 사용합니다.
 * @par 보안
 * - explicit_security_or_signed_artifact_flow
 * - 예제의 pairing·bond·서명·credential 조건을 생략하지 않고 오류 출력을 확인합니다.
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
 * identity `NUCODE_BLE_Security/GattCacheCentral`, sha256 `07491c39432e4affb53e402461e31b9cd21d15577a96e667bca4b7c31aa7ee7d`
 * @nucode_example_setup_end */

/**
 * @file GattCacheCentral.ino
 * @brief bonded peer의 hash를 확인해 GATT handle cache를 복원하거나 재탐색하는 예제입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE.h>
#include <NUCODE_BLE_Security.h>

namespace
{

    constexpr std::uint16_t cacheSchemaVersion = 1U;
    const nucode::ble::BLEUuid serviceUuid("8e7e2950-7d8c-4c1a-9d2d-8b6519f77410");
    const nucode::ble::BLEUuid valueUuid("8e7e2951-7d8c-4c1a-9d2d-8b6519f77410");
    nucode::ble::BLEAddress peerAddress;
    nucode::ble::BLEConnectionHandle peerConnection;
    bool peerFound = false;
    bool cachePending = false;
    bool scanPending = false;

    /** @brief service filter를 통과한 connectable peer 주소를 복사합니다. */
    void onScanResult(const nucode::ble::BLEScanResult &result, void *context)
    {
        static_cast<void>(context);
        if (!peerFound && result.connectable && !result.scan_response)
        {
            peerAddress = result.address;
            peerFound = true;
            if (!BLEScan.stop())
            {
                Serial.println("GATT cache scan stop failed");
            }
        }
    }

    /** @brief 연결 수명에 맞춰 security 요청과 재검색을 예약합니다. */
    void onBleEvent(const nucode::ble::BLEEventInfo &information, void *context)
    {
        static_cast<void>(context);
        if (information.event == nucode::ble::BLEEvent::connected &&
            information.role == nucode::ble::BLELinkRole::central)
        {
            peerConnection = information.connection;
            if (!BLESecurity.requestSecurity())
            {
                Serial.println("GATT cache security request failed");
            }
        }
        else if (information.event == nucode::ble::BLEEvent::disconnected &&
                 information.connection == peerConnection)
        {
            cachePending = false;
            peerFound = false;
            scanPending = true;
        }
    }

    /** @brief pairing을 승인하고 bonded encrypted link에서 cache 동기화를 예약합니다. */
    void onSecurityEvent(const nucode::ble::SecurityEventRecord &record, void *context)
    {
        static_cast<void>(context);
        if (record.event == nucode::ble::SecurityEvent::pairing_requested)
        {
            if (!BLESecurity.acceptPairing(true))
            {
                Serial.println("GATT cache pairing approval failed");
            }
        }
        else if (record.event == nucode::ble::SecurityEvent::paired ||
                 record.event == nucode::ble::SecurityEvent::bond_verified)
        {
            cachePending = true;
        }
        else if (record.event == nucode::ble::SecurityEvent::pairing_failed ||
                 record.event == nucode::ble::SecurityEvent::error)
        {
            Serial.println("GATT cache security failed");
        }
    }

    /** @brief cache 저장·복원·무효화와 비동기 GATT 결과를 처리합니다. */
    void onClientEvent(const nucode::ble::BLEGattClientEventInfo &information, void *context)
    {
        static_cast<void>(context);
        if (information.connection != peerConnection)
        {
            return;
        }
        if (information.event == nucode::ble::BLEGattClientEvent::cache_saved)
        {
            Serial.println("GATT cache saved after discovery");
        }
        else if (information.event == nucode::ble::BLEGattClientEvent::cache_restored)
        {
            Serial.println("GATT cache restored after hash match");
        }
        else if (information.event == nucode::ble::BLEGattClientEvent::service_changed)
        {
            Serial.println("Service Changed invalidated cached handles");
        }
        else if (information.event == nucode::ble::BLEGattClientEvent::discovery_complete)
        {
            if (!BLEClient.read(peerConnection))
            {
                Serial.println("GATT cache read start failed");
            }
        }
        else if (information.event == nucode::ble::BLEGattClientEvent::read_complete)
        {
            Serial.print("Cached value bytes: ");
            Serial.println(information.length);
        }
        else if (information.event == nucode::ble::BLEGattClientEvent::operation_failed)
        {
            Serial.println("GATT cache operation failed");
        }
    }

    /** @brief 시작 실패 단계만 출력하고 잘못된 부분 실행을 막습니다. */
    void require(bool condition, const char *stage)
    {
        if (condition)
        {
            return;
        }
        Serial.print("GattCacheCentral start failed: ");
        Serial.println(stage);
        while (true)
        {
            delay(1000U);
        }
    }

} // namespace

void setup()
{
    Serial.begin(115200);

    nucode::ble::SecurityConfig security{};
    security.minimum_level = nucode::ble::SecurityLevel::encrypted;
    security.bonding = true;
    security.io_capability = nucode::ble::SecurityIoCapability::no_input_output;
    BLESecurity.onEvent(onSecurityEvent);
    BLEDevice.onEventInfo(onBleEvent);
    BLEScan.onResult(onScanResult);
    BLEClient.onDetailedEvent(onClientEvent);

    require(BLESecurity.begin(security), "security");
    require(BLEDevice.begin("NU54-GATT-CACHE-C"), "device");
    require(BLEScan.clearFilters(), "scan-clear");
    require(BLEScan.filterServiceUuid(serviceUuid), "scan-service");
    require(BLEScan.start(true), "scan-start");
}

void loop()
{
    BLEDevice.poll();
    BLESecurity.poll();
    if (peerFound && !BLEConnection.connected() && !BLEConnection.connecting())
    {
        peerFound = false;
        if (!BLEConnection.connect(peerAddress, peerConnection))
        {
            Serial.println("GATT cache connection failed");
            scanPending = true;
        }
    }
    if (scanPending && !BLEScan.running() && !BLEConnection.connecting())
    {
        scanPending = false;
        if (!BLEScan.start(true))
        {
            Serial.println("GATT cache scan restart failed");
        }
    }
    if (cachePending && !BLEClient.busy(peerConnection))
    {
        cachePending = false;
        if (!BLEClient.discoverCached(peerConnection, serviceUuid, valueUuid, cacheSchemaVersion))
        {
            Serial.println("GATT cache synchronization failed");
        }
    }
    delay(1U);
}
