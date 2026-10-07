/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par 목적
 * 두 enhanced bearer pool을 열고 GATT round trip을 반복하는 central 예제입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 2대 — 1) EattCentral (central/client); 2) EattPeripheral (peripheral/server)
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * 없음
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 추가 조건 없음
 * @par 준비물
 * - NU54DK 보드 2대 — 1) EattCentral (central/client); 2) EattPeripheral (peripheral/server)
 * @par 설정
 * - Tools → Feature set에서 `ble` profile을 선택합니다.
 * - Serial Monitor는 115200 baud로 엽니다.
 * @par 실행 순서
 * - 권장 profile로 현재 Sketch와 metadata에 적힌 각 peer 역할 Sketch를 빌드합니다.
 * - probe가 여러 대이면 `NUCODE_PROBE_UID`를 지정하고 Arduino Upload로 역할별 보드를 구분합니다.
 * - peer·외장 조건을 먼저 준비한 뒤 reset 또는 예제에 명시된 입력으로 실행합니다.
 * @par 성공 출력
 * - Serial 문구 `WARNING: EATT is experimental opt-in, maximum two bearers per link`를 포함한 정상 상태 전이를 확인합니다.
 * @par 흔한 오류
 * - 권장 profile과 sidecar가 다르면 기능·Kconfig가 빠질 수 있으므로 먼저 설정을 다시 확인합니다.
 * - 여러 probe가 연결된 상태에서 UID를 생략하면 다른 보드에 upload될 수 있습니다.
 * - `EATT scan stop failed` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * - `EATT pairing approval failed` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * - `EATT discovery failed` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * @par 다음 예제
 * - `NUCODE_BLE_EATT/EattPeripheral`
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
 * Recipe `ble_gatt_extensions`; 내부 증거 ID는 metadata에서 관리합니다.
 * 직접 upstream 복사 아님; NCS `99553055607b2e9885fbc80ccd11fa9da81c2df0`, Zephyr `bf801e4e3d19e1ffa76164346480cb7734dd2800`
 * build `clean_installed_compile_required`, runtime `procedure_documented_not_physical_pass`
 * @par Metadata
 * identity `NUCODE_BLE_EATT/EattCentral`, sha256 `36b11cd1e48873a9a1d34df09ac320a56fd433158d2381d3aaa5a2a7fcfef320`
 * @nucode_example_setup_end */

/**
 * @file EattCentral.ino
 * @brief 두 enhanced bearer pool을 열고 GATT round trip을 반복하는 central 예제입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE_EATT.h>

#include <string.h>

namespace
{

    const nucode::ble::BLEUuid serviceUuid("8e7e2980-7d8c-4c1a-9d2d-8b6519f77410");
    const nucode::ble::BLEUuid valueUuid("8e7e2981-7d8c-4c1a-9d2d-8b6519f77410");
    nucode::ble::BLEConnectionHandle peer;
    nucode::ble::BLEAddress peerAddress;
    bool peerFound = false;
    bool scanPending = false;
    bool securityPending = false;
    bool eattConnectPending = false;
    bool writePending = false;
    bool readPending = false;
    std::uint32_t sequence = 0U;
    nucode::ble::BLEGattBearer selectedBearer = nucode::ble::BLEGattBearer::enhanced;

    /** @brief service UUID를 광고하는 connectable peer를 선택합니다. */
    void onScanResult(const nucode::ble::BLEScanResult &result, void *context)
    {
        static_cast<void>(context);
        if (!peerFound && result.connectable && !result.scan_response)
        {
            peerAddress = result.address;
            peerFound = true;
            if (!BLEScan.stop())
            {
                Serial.println("EATT scan stop failed");
            }
        }
    }

    /** @brief 연결마다 암호화를 요청하고 해제 시 재검색합니다. */
    void onBleEvent(const nucode::ble::BLEEventInfo &information, void *context)
    {
        static_cast<void>(context);
        if (information.event == nucode::ble::BLEEvent::connected &&
            information.role == nucode::ble::BLELinkRole::central)
        {
            peer = information.connection;
            securityPending = true;
        }
        else if (information.event == nucode::ble::BLEEvent::disconnected &&
                 information.connection == peer)
        {
            peer = nucode::ble::BLEConnectionHandle{};
            peerFound = false;
            scanPending = true;
            eattConnectPending = false;
            writePending = false;
            readPending = false;
        }
    }

    /** @brief pairing 승인 뒤 exact characteristic discovery를 시작합니다. */
    void onSecurityEvent(const nucode::ble::SecurityEventRecord &record, void *context)
    {
        static_cast<void>(context);
        if (record.event == nucode::ble::SecurityEvent::pairing_requested)
        {
            if (!BLESecurity.acceptPairing(true))
            {
                Serial.println("EATT pairing approval failed");
            }
        }
        else if ((record.event == nucode::ble::SecurityEvent::paired ||
                  record.event == nucode::ble::SecurityEvent::bond_verified ||
                  record.event == nucode::ble::SecurityEvent::security_changed) &&
                 peer.valid() && !BLEClient.discovered(peer) && !BLEClient.busy(peer))
        {
            if (!BLEClient.discover(peer, serviceUuid, valueUuid))
            {
                Serial.println("EATT discovery failed");
            }
        }
    }

    /** @brief enhanced bearer 결과를 검증하고 write/read sequence를 진행합니다. */
    void onClientEvent(const nucode::ble::BLEGattClientEventInfo &information, void *context)
    {
        static_cast<void>(context);
        if (information.connection != peer)
        {
            return;
        }
        if (information.event == nucode::ble::BLEGattClientEvent::discovery_complete)
        {
            eattConnectPending = true;
        }
        else if (information.event == nucode::ble::BLEGattClientEvent::write_complete)
        {
            if (information.bearer != selectedBearer)
            {
                Serial.println("EATT write bearer mismatch");
            }
            readPending = true;
        }
        else if (information.event == nucode::ble::BLEGattClientEvent::read_complete)
        {
            std::uint32_t observed = 0U;
            if (information.bearer != selectedBearer || information.length != sizeof(observed))
            {
                Serial.println("EATT read bearer or length mismatch");
                return;
            }
            ::memcpy(&observed, information.data, sizeof(observed));
            Serial.println(observed == sequence ? "EATT enhanced round trip PASS"
                                                : "EATT payload mismatch");
            writePending = true;
        }
        else if (information.event == nucode::ble::BLEGattClientEvent::operation_failed)
        {
            Serial.print("EATT operation failed: ");
            Serial.println(information.status);
        }
    }

    /** @brief service UUID active scan을 시작합니다. */
    bool startScan()
    {
        return BLEScan.clearFilters() && BLEScan.filterServiceUuid(serviceUuid) &&
               BLEScan.start(true);
    }

} // namespace

void setup()
{
    Serial.begin(115200);
    Serial.println("WARNING: EATT is experimental opt-in, maximum two bearers per link");
    nucode::ble::SecurityConfig security{};
    security.minimum_level = nucode::ble::SecurityLevel::encrypted;
    security.bonding = true;
    security.io_capability = nucode::ble::SecurityIoCapability::no_input_output;
    BLESecurity.onEvent(onSecurityEvent);
    BLEDevice.onEventInfo(onBleEvent);
    BLEScan.onResult(onScanResult);
    BLEClient.onDetailedEvent(onClientEvent);
    if (!BLESecurity.begin(security) || !BLEDevice.begin("NU54-EATT-C") || !startScan())
    {
        Serial.println("EattCentral start failed");
    }
}

void loop()
{
    BLEDevice.poll();
    BLESecurity.poll();
    if (peerFound && !peer.valid() && !BLEConnection.connecting())
    {
        peerFound = false;
        if (!BLEConnection.connect(peerAddress, peer))
        {
            scanPending = true;
        }
    }
    if (securityPending)
    {
        securityPending = false;
        if (!BLESecurity.requestSecurity())
        {
            Serial.println("EATT security request failed");
        }
    }
    if (scanPending && !peer.valid() && !BLEScan.running() && !BLEConnection.connecting())
    {
        scanPending = false;
        if (!startScan())
        {
            Serial.println("EATT scan restart failed");
        }
    }
    if (eattConnectPending && peer.valid() && !BLEClient.busy(peer))
    {
        eattConnectPending = false;
        if (!BLEEatt.connect(peer, 2U))
        {
            Serial.println("EATT two-bearer connection failed");
        }
    }
    if (BLEEatt.count(peer) == 2U && !writePending && !readPending && !BLEClient.busy(peer))
    {
        writePending = true;
    }
    if (writePending && !BLEClient.busy(peer))
    {
        writePending = false;
        ++sequence;
        if (!BLEClient.write(peer, &sequence, sizeof(sequence), selectedBearer))
        {
            Serial.println("EATT enhanced write start failed");
        }
    }
    if (readPending && !BLEClient.busy(peer))
    {
        readPending = false;
        if (!BLEClient.read(peer, selectedBearer))
        {
            Serial.println("EATT enhanced read start failed");
        }
    }
    delay(1U);
}
