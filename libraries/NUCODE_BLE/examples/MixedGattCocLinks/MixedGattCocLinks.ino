/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par 목적
 * 세 NU54DK에서 mixed-role 2-link GATT·LE CoC를 함께 실행하는 예제입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 1대 — 1) MixedGattCocLinks 실행 보드
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * 없음
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 동작에 필요한 compatible BLE peer 또는 mobile/host client를 별도로 준비합니다.
 * @par 준비물
 * - NU54DK 보드 1대 — 1) MixedGattCocLinks 실행 보드
 * - 동작에 필요한 compatible BLE peer 또는 mobile/host client를 별도로 준비합니다.
 * @par 설정
 * - Tools → Feature set에서 `ble` profile을 선택합니다.
 * - Serial Monitor는 115200 baud로 엽니다.
 * @par 실행 순서
 * - 권장 profile로 현재 Sketch와 metadata에 적힌 각 peer 역할 Sketch를 빌드합니다.
 * - probe가 여러 대이면 `NUCODE_PROBE_UID`를 지정하고 Arduino Upload로 역할별 보드를 구분합니다.
 * - peer·외장 조건을 먼저 준비한 뒤 reset 또는 예제에 명시된 입력으로 실행합니다.
 * @par 성공 출력
 * - Serial 문구 `Mixed GATT/CoC example stopped:`를 포함한 정상 상태 전이를 확인합니다.
 * - Serial 문구 `downstream GATT write received`를 포함한 정상 상태 전이를 확인합니다.
 * - Serial 문구 `downstream link connected`를 포함한 정상 상태 전이를 확인합니다.
 * @par 흔한 오류
 * - 권장 profile과 sidecar가 다르면 기능·Kconfig가 빠질 수 있으므로 먼저 설정을 다시 확인합니다.
 * - 여러 probe가 연결된 상태에서 UID를 생략하면 다른 보드에 upload될 수 있습니다.
 * - `, error=` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * @par 다음 예제
 * - `NUCODE_BLE/MixedRoleLinks`
 * - `NUCODE_BLE/MultipleAdvertisingSets`
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
 * identity `NUCODE_BLE/MixedGattCocLinks`, sha256 `d516c890d68989cc7d5271bbab142b60b9ca2e6ab99a58a02ecd3f4ce93d92db`
 * @nucode_example_setup_end */

/**
 * @file MixedGattCocLinks.ino
 * @brief 세 NU54DK에서 mixed-role 2-link GATT·LE CoC를 함께 실행하는 예제입니다.
 *
 * 같은 Sketch의 `nodeRole`만 바꿔 다음 순서로 세 보드에 업로드합니다.
 * 1. `NodeRole::peripheral`: upstream GATT·CoC server
 * 2. `NodeRole::mixed`: upstream에는 central, downstream에는 peripheral
 * 3. `NodeRole::central`: mixed 보드의 downstream client
 *
 * 추가 GPIO 배선은 필요하지 않습니다. 세 보드의 전원을 켜면 mixed 보드가 두 link에서
 * GATT write와 32-byte CoC echo를 1초마다 병렬 실행합니다.
 * 도구 → Feature set → BLE NUS를 선택해야 합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE.h>

#include "MixedGattCocPayload.h"

namespace
{

    /** @brief 한 번에 한 보드에 지정할 예제 role입니다. */
    enum class NodeRole : std::uint8_t
    {
        peripheral,
        mixed,
        central,
    };

    constexpr NodeRole nodeRole = NodeRole::mixed;
    constexpr std::uint16_t cocPsm = 0x0082U;
    constexpr std::uint8_t gattTransport = 0x47U;
    constexpr std::uint8_t cocTransport = 0x43U;
    constexpr std::uint32_t sendIntervalMs = 1000U;

    const nucode::ble::BLEUuid serviceUuid("90bf2a50-14f5-4d3d-92c7-299334932a20");
    const nucode::ble::BLEUuid characteristicUuid("90bf2a51-14f5-4d3d-92c7-299334932a20");
    nucode::ble::BLEService exampleService(serviceUuid);
    nucode::ble::BLECharacteristic exampleCharacteristic(
        characteristicUuid, nucode::ble::BLEProperty::write,
        nucode::ble::BLEPermission::write, mixed_gatt_coc::Payload::length);

    nucode::ble::BLEAddress peerAddress;
    nucode::ble::BLEConnectionHandle clientConnection;
    nucode::ble::BLEConnectionHandle serverConnection;
    nucode::ble::BLEL2capChannelHandle clientChannel;
    nucode::ble::BLEL2capChannelHandle serverChannel;
    std::uint8_t gattPayload[mixed_gatt_coc::Payload::length] = {};
    std::uint8_t cocPayload[mixed_gatt_coc::Payload::length] = {};
    std::uint32_t sequence = 0U;
    std::uint32_t lastSendMs = 0U;
    bool peerFound = false;
    bool scanStarted = false;
    bool clientGattReady = false;
    bool clientCocReady = false;
    bool advertisingStarted = false;
    bool gattPending = false;
    bool cocPending = false;
    bool trafficActive = false;
    bool stopped = false;

    /** @brief 두 transport 완료 뒤에만 같은 sequence의 성공을 확정합니다. */
    void finishTrafficIfComplete();

    /** @brief 현재 image가 client 역할을 갖는지 반환합니다. */
    constexpr bool hasClient()
    {
        return nodeRole != NodeRole::peripheral;
    }

    /** @brief 현재 image가 server 역할을 갖는지 반환합니다. */
    constexpr bool hasServer()
    {
        return nodeRole != NodeRole::central;
    }

    /** @brief 현재 role의 advertising local name을 반환합니다. */
    const char *localName()
    {
        if (nodeRole == NodeRole::peripheral)
        {
            return "NU54-GATT-UP";
        }
        if (nodeRole == NodeRole::mixed)
        {
            return "NU54-GATT-MIX";
        }
        return "NU54-GATT-C";
    }

    /** @brief client role이 검색할 upstream 이름을 반환합니다. */
    const char *peerName()
    {
        return nodeRole == NodeRole::mixed ? "NU54-GATT-UP" : "NU54-GATT-MIX";
    }

    /** @brief payload에 기록할 local role marker를 반환합니다. */
    constexpr std::uint8_t roleMarker()
    {
        return nodeRole == NodeRole::mixed ? 0xb2U : 0xc3U;
    }

    /** @brief 첫 runtime 오류를 출력하고 추가 전송을 중단합니다. */
    void fail(const char *stage)
    {
        if (stopped)
        {
            return;
        }
        stopped = true;
        Serial.print("Mixed GATT/CoC example stopped: ");
        Serial.print(stage);
        Serial.print(", error=");
        Serial.println(BLEDevice.lastDriverError());
    }

    /** @brief server role의 connectable advertising을 한 번 시작합니다. */
    bool startAdvertising()
    {
        if (advertisingStarted)
        {
            return true;
        }
        advertisingStarted = BLEAdvertising.clear() &&
                             BLEAdvertising.setConnectable(true) &&
                             BLEAdvertising.addServiceUuid(serviceUuid) &&
                             BLEAdvertising.setScanResponseName(true) &&
                             BLEAdvertising.start();
        return advertisingStarted;
    }

    /** @brief exact local name으로 upstream active scan을 시작합니다. */
    bool startScan()
    {
        scanStarted = BLEScan.clearFilters() && BLEScan.filterName(peerName()) &&
                      BLEScan.start(true);
        return scanStarted;
    }

    /** @brief mixed role의 두 upstream transport가 준비되면 downstream 광고를 엽니다. */
    void advertiseMixedIfReady()
    {
        if (nodeRole == NodeRole::mixed && clientGattReady && clientCocReady &&
            !startAdvertising())
        {
            fail("mixed advertising");
        }
    }

    /** @brief exact-name scan 결과 하나의 주소를 main loop에 전달합니다. */
    void onScanResult(const nucode::ble::BLEScanResult &result, void *context)
    {
        static_cast<void>(context);
        if (!peerFound && result.connectable)
        {
            peerAddress = result.address;
            peerFound = true;
        }
    }

    /** @brief GATT client 완료를 generation 기반 upstream link와 대조합니다. */
    void onClientEvent(const nucode::ble::BLEGattClientEventInfo &information, void *context)
    {
        static_cast<void>(context);
        if (information.connection != clientConnection)
        {
            fail("cross-link GATT event");
            return;
        }
        if (information.event == nucode::ble::BLEGattClientEvent::discovery_complete)
        {
            clientGattReady = true;
            advertiseMixedIfReady();
        }
        else if (information.event == nucode::ble::BLEGattClientEvent::write_complete)
        {
            gattPending = false;
            finishTrafficIfComplete();
        }
        else if (information.event == nucode::ble::BLEGattClientEvent::operation_failed)
        {
            fail("GATT client operation");
        }
    }

    /** @brief downstream GATT write의 link와 payload 길이를 확인합니다. */
    void onCharacteristic(nucode::ble::BLECharacteristic &characteristic,
                          const nucode::ble::BLECharacteristicEventInfo &information,
                          void *context)
    {
        static_cast<void>(characteristic);
        static_cast<void>(context);
        if (information.event != nucode::ble::BLECharacteristicEvent::written)
        {
            return;
        }
        if (information.connection != serverConnection ||
            information.length != mixed_gatt_coc::Payload::length)
        {
            fail("cross-link or malformed GATT write");
            return;
        }
        Serial.println("downstream GATT write received");
    }

    /** @brief local role을 이용해 두 generation connection handle을 분리합니다. */
    void onBleEvent(const nucode::ble::BLEEventInfo &information, void *context)
    {
        static_cast<void>(context);
        if (information.event == nucode::ble::BLEEvent::connected)
        {
            if (information.role == nucode::ble::BLELinkRole::central && hasClient())
            {
                clientConnection = information.connection;
                if (!BLEL2cap.connect(clientConnection, cocPsm, clientChannel) ||
                    !BLEClient.discover(clientConnection, serviceUuid, characteristicUuid))
                {
                    fail("upstream setup");
                }
            }
            else if (information.role == nucode::ble::BLELinkRole::peripheral && hasServer())
            {
                serverConnection = information.connection;
                Serial.println("downstream link connected");
            }
            else
            {
                fail("unexpected link role");
            }
        }
        else if (information.event == nucode::ble::BLEEvent::disconnected)
        {
            fail("unexpected disconnect");
        }
        else if (information.event == nucode::ble::BLEEvent::error)
        {
            fail("GAP event");
        }
    }

    /** @brief upstream echo와 downstream echo를 channel handle로 분리합니다. */
    void onL2capEvent(const nucode::ble::BLEL2capEventInfo &information, void *context)
    {
        static_cast<void>(context);
        if (information.event == nucode::ble::BLEL2capEvent::connected)
        {
            if (information.connection == clientConnection &&
                information.channel == clientChannel)
            {
                clientCocReady = true;
                advertiseMixedIfReady();
            }
            else if (information.connection == serverConnection && hasServer())
            {
                serverChannel = information.channel;
            }
            else
            {
                fail("cross-link CoC connect");
            }
            return;
        }
        if (information.event == nucode::ble::BLEL2capEvent::disconnected)
        {
            fail("CoC disconnect");
            return;
        }
        if (information.event != nucode::ble::BLEL2capEvent::received)
        {
            return;
        }
        if (information.channel == clientChannel)
        {
            if (!cocPending || !mixed_gatt_coc::Payload::matches(
                                   information.data, information.length, cocPayload))
            {
                fail("upstream CoC echo");
                return;
            }
            cocPending = false;
            finishTrafficIfComplete();
            return;
        }
        if (information.channel != serverChannel ||
            !BLEL2cap.send(serverChannel, information.data, information.length))
        {
            fail("downstream CoC echo");
        }
    }

    /** @brief GATT 응답과 CoC echo가 모두 끝난 sequence만 성공으로 출력합니다. */
    void finishTrafficIfComplete()
    {
        if (!trafficActive || gattPending || cocPending)
        {
            return;
        }
        trafficActive = false;
        Serial.print("GATT+CoC PASS, sequence=");
        Serial.println(sequence);
        ++sequence;
    }

    /** @brief client role에서 GATT write와 CoC echo를 같은 sequence로 함께 시작합니다. */
    void issueTraffic()
    {
        if (!hasClient() || !clientGattReady || !clientCocReady || trafficActive ||
            gattPending || cocPending || BLEClient.busy(clientConnection) ||
            BLEL2cap.availableForWrite() < 2U)
        {
            return;
        }
        const std::uint32_t now = millis();
        if (now - lastSendMs < sendIntervalMs)
        {
            return;
        }
        lastSendMs = now;
        mixed_gatt_coc::Payload::build(gattPayload, roleMarker(), gattTransport, sequence);
        mixed_gatt_coc::Payload::build(cocPayload, roleMarker(), cocTransport, sequence);
        if (!BLEClient.write(clientConnection, gattPayload, sizeof(gattPayload)))
        {
            fail("GATT write start");
            return;
        }
        gattPending = true;
        if (!BLEL2cap.send(clientChannel, cocPayload, sizeof(cocPayload)))
        {
            fail("CoC send start");
            return;
        }
        cocPending = true;
        trafficActive = true;
    }

} // namespace

void setup()
{
    Serial.begin(115200);
    if (hasServer())
    {
        exampleCharacteristic.onEvent(onCharacteristic);
        if (!exampleService.addCharacteristic(exampleCharacteristic) ||
            !BLEDevice.addService(exampleService))
        {
            fail("GATT schema");
            return;
        }
    }
    BLEDevice.onEventInfo(onBleEvent);
    BLEL2cap.onEvent(onL2capEvent);
    if (hasClient())
    {
        BLEScan.onResult(onScanResult);
        BLEClient.onDetailedEvent(onClientEvent);
    }
    if (!BLEDevice.begin(localName()) || (hasServer() && !BLEL2cap.startServer(cocPsm)))
    {
        fail("BLE begin");
        return;
    }
    if ((nodeRole == NodeRole::peripheral && !startAdvertising()) ||
        (hasClient() && !startScan()))
    {
        fail("radio start");
        return;
    }
    Serial.print("Mixed GATT/CoC example ready, role=");
    Serial.println(localName());
}

void loop()
{
    BLEDevice.poll();
    if (stopped)
    {
        delay(10);
        return;
    }
    if (peerFound && scanStarted)
    {
        peerFound = false;
        scanStarted = false;
        if (!BLEScan.stop() || !BLEConnection.connect(peerAddress, clientConnection))
        {
            fail("upstream connect");
            return;
        }
    }
    issueTraffic();
}
