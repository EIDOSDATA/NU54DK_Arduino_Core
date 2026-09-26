/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 2대 — 1) ExtendedAdvertising 실행 보드; 2) ExtendedScanner (scanner)
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * 없음
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI `--upload-field probe_id=<UID>`로 명시 선택합니다.
 * @par 추가 조건
 * 추가 조건 없음
 * @par Metadata
 * identity `NUCODE_BLE/ExtendedScanner`, sha256 `c45cb39e3c9eded4313551134163f866730c02adb66e95296f0b3e11616949fc`
 * @nucode_example_setup_end */

/**
 * @file ExtendedScanner.ino
 * @brief 1M·coded PHY의 extended advertising metadata와 최대 255-byte payload를 수신합니다.
 */

#include <NUCODE_BLE.h>

/** @brief copied extended scan result의 식별 필드를 main thread에서 출력합니다. */
void onScanResult(const nucode::ble::BLEScanResult &result, void *context)
{
    static_cast<void>(context);
    if (result.extended)
    {
        Serial.print("SID=");
        Serial.print(result.sid);
        Serial.print(" PHY=");
        Serial.print(static_cast<unsigned int>(result.secondary_phy));
        Serial.print(" LEN=");
        Serial.println(result.payload_length);
    }
}

void setup()
{
    Serial.begin(115200);
    BLEScan.onResult(onScanResult);
    if (!BLEDevice.begin("NU54-EXT-SCAN") || !BLEScan.clearFilters() ||
        !BLEScan.startExtended(true, true))
    {
        Serial.println("extended scan failed");
    }
}

void loop()
{
    BLEDevice.poll();
}
