/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par 목적
 * CSRK 저장 뒤 암호화하지 않은 재연결에서 signed write를 보내는 예제입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 2대 — 1) LegacySignedWriteCentral (central/client); 2) LegacySignedWritePeripheral (peripheral/server)
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * 없음
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 추가 조건 없음
 * @par 준비물
 * - NU54DK 보드 2대 — 1) LegacySignedWriteCentral (central/client); 2) LegacySignedWritePeripheral (peripheral/server)
 * @par 설정
 * - Tools → Feature set에서 `ble` profile을 선택합니다.
 * - Serial Monitor는 115200 baud로 엽니다.
 * @par 실행 순서
 * - 권장 profile로 현재 Sketch와 metadata에 적힌 각 peer 역할 Sketch를 빌드합니다.
 * - probe가 여러 대이면 `NUCODE_PROBE_UID`를 지정하고 Arduino Upload로 역할별 보드를 구분합니다.
 * - peer·외장 조건을 먼저 준비한 뒤 reset 또는 예제에 명시된 입력으로 실행합니다.
 * @par 성공 출력
 * - Serial 문구 `signed write persisted, sequence=`를 포함한 정상 상태 전이를 확인합니다.
 * - Serial 문구 `WARNING: Authenticated Signed Write is deprecated legacy opt-in`를 포함한 정상 상태 전이를 확인합니다.
 * @par 흔한 오류
 * - 권장 profile과 sidecar가 다르면 기능·Kconfig가 빠질 수 있으므로 먼저 설정을 다시 확인합니다.
 * - 여러 probe가 연결된 상태에서 UID를 생략하면 다른 보드에 upload될 수 있습니다.
 * - `legacy signing scan stop failed` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * - `legacy signing discovery failed` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * - `legacy signing pairing approval failed` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * @par 다음 예제
 * - `NUCODE_BLE_LegacySigning/LegacySignedWritePeripheral`
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
 * Recipe `ble_gatt_extensions`; 내부 증거 ID는 metadata에서 관리합니다.
 * 직접 upstream 복사 아님; NCS `99553055607b2e9885fbc80ccd11fa9da81c2df0`, Zephyr `bf801e4e3d19e1ffa76164346480cb7734dd2800`
 * build `clean_installed_compile_required`, runtime `procedure_documented_not_physical_pass`
 * @par Metadata
 * identity `NUCODE_BLE_LegacySigning/LegacySignedWriteCentral`, sha256 `1fd924798e0c0e06a1e86dc165e6fa4c3a747de08a66a2cfda47c0b27c438549`
 * @nucode_example_setup_end */

/**
 * @file LegacySignedWriteCentral.ino
 * @brief CSRK 저장 뒤 암호화하지 않은 재연결에서 signed write를 보내는 예제입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE_LegacySigning.h>

namespace
{

    const nucode::ble::BLEUuid serviceUuid("8e7e2970-7d8c-4c1a-9d2d-8b6519f77410");
    const nucode::ble::BLEUuid signedValueUuid("8e7e2971-7d8c-4c1a-9d2d-8b6519f77410");
    nucode::ble::BLEConnectionHandle peer;
    nucode::ble::BLEAddress peerAddress;
    bool peerFound = false;
    bool scanPending = false;
    bool securityPending = false;
    bool disconnectAfterPairing = false;
    bool signedWritePending = false;
    std::uint32_t sequence = 0U;

    /** @brief service filter를 통과한 connectable peer를 선택합니다. */
    void onScanResult(const nucode::ble::BLEScanResult &result, void *context)
    {
        static_cast<void>(context);
        if (!peerFound && result.connectable && !result.scan_response)
        {
            peerAddress = result.address;
            peerFound = true;
            if (!BLEScan.stop())
            {
                Serial.println("legacy signing scan stop failed");
            }
        }
    }

    /** @brief 최초 pairing과 이후 unencrypted signed-write 연결을 분리합니다. */
    void onBleEvent(const nucode::ble::BLEEventInfo &information, void *context)
    {
        static_cast<void>(context);
        if (information.event == nucode::ble::BLEEvent::connected &&
            information.role == nucode::ble::BLELinkRole::central)
        {
            peer = information.connection;
            if (BLESecurity.bondCount() == 0U)
            {
                securityPending = true;
            }
            else if (!BLEClient.discover(peer, serviceUuid, signedValueUuid))
            {
                Serial.println("legacy signing discovery failed");
            }
        }
        else if (information.event == nucode::ble::BLEEvent::disconnected &&
                 information.connection == peer)
        {
            peer = nucode::ble::BLEConnectionHandle{};
            peerFound = false;
            scanPending = true;
        }
    }

    /** @brief pairing을 승인하고 CSRK 저장 뒤 L1 재연결을 예약합니다. */
    void onSecurityEvent(const nucode::ble::SecurityEventRecord &record, void *context)
    {
        static_cast<void>(context);
        if (record.event == nucode::ble::SecurityEvent::pairing_requested)
        {
            if (!BLESecurity.acceptPairing(true))
            {
                Serial.println("legacy signing pairing approval failed");
            }
        }
        else if (record.event == nucode::ble::SecurityEvent::paired)
        {
            disconnectAfterPairing = true;
        }
    }

    /** @brief discovery와 counter 영속화 완료를 다음 signed write로 연결합니다. */
    void onClientEvent(const nucode::ble::BLEGattClientEventInfo &information, void *context)
    {
        static_cast<void>(context);
        if (information.connection != peer)
        {
            return;
        }
        if (information.event == nucode::ble::BLEGattClientEvent::discovery_complete ||
            information.event == nucode::ble::BLEGattClientEvent::signed_write_complete)
        {
            if (information.event == nucode::ble::BLEGattClientEvent::signed_write_complete)
            {
                Serial.print("signed write persisted, sequence=");
                Serial.println(sequence);
            }
            signedWritePending = true;
        }
        else if (information.event == nucode::ble::BLEGattClientEvent::operation_failed)
        {
            Serial.print("signed write failed, status=");
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
    Serial.println("WARNING: Authenticated Signed Write is deprecated legacy opt-in");
    nucode::ble::SecurityConfig security{};
    security.minimum_level = nucode::ble::SecurityLevel::encrypted;
    security.bonding = true;
    security.io_capability = nucode::ble::SecurityIoCapability::no_input_output;
    BLESecurity.onEvent(onSecurityEvent);
    BLEDevice.onEventInfo(onBleEvent);
    BLEScan.onResult(onScanResult);
    BLEClient.onDetailedEvent(onClientEvent);
    if (!BLESecurity.begin(security) || !BLEDevice.begin("NU54-SIGN-C") || !startScan())
    {
        Serial.println("LegacySignedWriteCentral start failed");
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
            Serial.println("legacy signing security request failed");
        }
    }
    if (disconnectAfterPairing && peer.valid())
    {
        disconnectAfterPairing = false;
        if (!BLEConnection.disconnect(peer))
        {
            Serial.println("legacy signing reconnect transition failed");
        }
    }
    if (scanPending && !peer.valid() && !BLEScan.running() && !BLEConnection.connecting())
    {
        scanPending = false;
        if (!startScan())
        {
            Serial.println("legacy signing scan restart failed");
        }
    }
    if (signedWritePending && peer.valid() && !BLEClient.busy(peer))
    {
        signedWritePending = false;
        ++sequence;
        if (!BLEClient.writeSigned(peer, &sequence, sizeof(sequence)))
        {
            Serial.println("legacy signed write start failed");
        }
    }
    delay(1U);
}
