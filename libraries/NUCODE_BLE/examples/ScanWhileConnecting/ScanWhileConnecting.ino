/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 2대 — 1) connectable peripheral; 2) ScanWhileConnecting (central/scanner)
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * prj.conf
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 이 profile은 controller 제약으로 한 local identity만 사용합니다.
 * @par Metadata
 * identity `NUCODE_BLE/ScanWhileConnecting`, sha256 `793bc64d8adc3e932839b0059a8fb0b7a873e0cac6e948a0cc3f64c0801425f9`
 * @nucode_example_setup_end */

/**
 * @file ScanWhileConnecting.ino
 * @brief explicit scan을 유지한 채 처음 발견한 peer로 initiating을 시작합니다.
 */

#include <NUCODE_BLE.h>

bool peerFound = false;
nucode::ble::BLEAddress peerAddress;

/** @brief 첫 connectable peer의 주소를 main loop로 전달합니다. */
void onScanResult(const nucode::ble::BLEScanResult &result, void *context)
{
    static_cast<void>(context);
    if (!peerFound && result.connectable)
    {
        peerAddress = result.address;
        peerFound = true;
    }
}

void setup()
{
    Serial.begin(115200);
    BLEScan.onResult(onScanResult);
    if (!BLEDevice.begin("NU54-SCAN-CONN") ||
        !BLEScan.startExtended(false, false, false))
    {
        Serial.println("parallel scan start failed");
    }
}

void loop()
{
    BLEDevice.poll();
    if (peerFound && !BLEConnection.connected() && !BLEConnection.connecting())
    {
        peerFound = false;
        if (!BLEConnection.connect(peerAddress))
        {
            Serial.println("parallel initiating failed");
        }
    }
}
