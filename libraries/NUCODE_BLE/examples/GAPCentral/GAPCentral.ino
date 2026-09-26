/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 2대 — 1) GAPCentral (central/client); 2) GAPPeripheral (peripheral/server)
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * 없음
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 추가 조건 없음
 * @par Metadata
 * identity `NUCODE_BLE/GAPCentral`, sha256 `7e25c56c6fcdc9ac37d5a192e46a5b26178774a0e36653e086935ceb91834f05`
 * @nucode_example_setup_end */

/**
 * @file GAPCentral.ino
 * @brief exact local-name scan 결과에 한 번 연결하는 GAP central 예제입니다.
 */

#include <NUCODE_BLE.h>

bool peerFound = false;
nucode::ble::BLEAddress peerAddress;

/** @brief bounded scan 결과를 main thread에서 보존합니다. */
void onScanResult(const nucode::ble::BLEScanResult &result, void *context)
{
    static_cast<void>(context);
    /** @note exact name은 scan response에서 올 수 있어 같은 peer 주소를 사용합니다. */
    if (!peerFound)
    {
        peerAddress = result.address;
        peerFound = true;
    }
}

void setup()
{
    Serial.begin(115200);
    BLEScan.onResult(onScanResult);
    if (!BLEDevice.begin("NU54-GAP-C") || !BLEScan.clearFilters() ||
        !BLEScan.filterName("NU54-GAP-P") || !BLEScan.start(true))
    {
        Serial.println("BLE GAP scan failed");
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
}
