/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: Adaptive capabilities (experimental) (adaptive, 실험적 대안)
 * @par 보드와 역할
 * 2대 — 1) CustomGattCentral (central/client); 2) CustomGattPeripheral (peripheral/server)
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * nucode-build.json
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI `--upload-field probe_id=<UID>`로 명시 선택합니다.
 * @par 추가 조건
 * 추가 조건 없음
 * @par Metadata
 * identity `NUCODE_BLE/CustomGattCentral`, sha256 `8dc95108e12d976445a22a44acfaa3f11a1786b9702e9a0d02757c286d600c0a`
 * @nucode_example_setup_end */

/**
 * @file CustomGattCentral.ino
 * @brief 한 번 연결해 custom service discovery와 read/write/subscribe를 실행하는 예제입니다.
 */

#include <NUCODE_BLE.h>

const nucode::ble::BLEUuid serviceUuid("9f3c0001-8b7a-4d64-a1b2-001122334455");
const nucode::ble::BLEUuid valueUuid("9f3c0002-8b7a-4d64-a1b2-001122334455");
nucode::ble::BLEAddress peerAddress;
bool peerFound = false;
bool startDiscovery = false;

/** @brief exact-name scan 결과의 주소 복사본을 보존합니다. */
void onScanResult(const nucode::ble::BLEScanResult &result, void *context)
{
    static_cast<void>(context);
    /** @note exact name은 legacy scan response에 포함될 수 있습니다. */
    if (!peerFound)
    {
        peerAddress = result.address;
        peerFound = true;
    }
}

/** @brief 연결 뒤 discovery 시작을 main loop에 예약합니다. */
void onBleEvent(nucode::ble::BLEEvent event, void *context)
{
    static_cast<void>(context);
    if (event == nucode::ble::BLEEvent::connected)
    {
        startDiscovery = true;
    }
}

/** @brief generic client 결과를 Arduino main thread에서 처리합니다. */
void onClientEvent(nucode::ble::BLEGattClientEvent event, const uint8_t *data, size_t length,
                   void *context)
{
    static_cast<void>(context);
    if (event == nucode::ble::BLEGattClientEvent::discovery_complete)
    {
        static_cast<void>(BLEClient.read());
    }
    else if (event == nucode::ble::BLEGattClientEvent::read_complete)
    {
        Serial.write(data, length);
        const uint8_t command[] = {'p', 'i', 'n', 'g'};
        static_cast<void>(BLEClient.write(command, sizeof(command)));
    }
    else if (event == nucode::ble::BLEGattClientEvent::write_complete)
    {
        static_cast<void>(BLEClient.subscribeNotifications());
    }
}

void setup()
{
    Serial.begin(115200);
    BLEDevice.onEvent(onBleEvent);
    BLEScan.onResult(onScanResult);
    BLEClient.onEvent(onClientEvent);
    if (!BLEDevice.begin("NU54-GATT-C") || !BLEScan.clearFilters() ||
        !BLEScan.filterName("NU54-GATT-P") || !BLEScan.start(true))
    {
        Serial.println("custom GATT scan failed");
    }
}

void loop()
{
    BLEDevice.poll();
    if (peerFound && !BLEConnection.connected() && !BLEConnection.connecting())
    {
        peerFound = false;
        static_cast<void>(BLEConnection.connect(peerAddress));
    }
    if (startDiscovery && BLEConnection.connected())
    {
        startDiscovery = false;
        static_cast<void>(BLEClient.discover(serviceUuid, valueUuid));
    }
}
