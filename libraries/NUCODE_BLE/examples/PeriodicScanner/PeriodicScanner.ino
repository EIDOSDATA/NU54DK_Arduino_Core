/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 2대 — 1) PeriodicAdvertiser (advertiser); 2) PeriodicScanner (scanner)
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * 없음
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 추가 조건 없음
 * @par Metadata
 * identity `NUCODE_BLE/PeriodicScanner`, sha256 `411d612bc5a3daee4f452a396330c71668233bd113bb408cbe904081204e23a9`
 * @nucode_example_setup_end */

/**
 * @file PeriodicScanner.ino
 * @brief Periodic advertiser를 발견해 한 개 sync를 만들고 bounded report를 읽습니다.
 */

#include <NUCODE_BLE.h>

nucode::ble::BLEPeriodicSyncHandle periodicSync;

/** @brief periodic interval이 있는 첫 extended report에 sync를 요청합니다. */
void onScan(const nucode::ble::BLEScanResult &result, void *)
{
    if (!periodicSync.valid() && result.extended && result.periodic_interval != 0U)
    {
        if (!BLEScan.stop() ||
            !BLEPeriodicAdvertising.createSync(result.address, result.sid, periodicSync))
        {
            Serial.println("periodic sync request failed");
            static_cast<void>(BLEScan.startExtended(false));
        }
    }
}

void setup()
{
    Serial.begin(115200);
    if (!BLEDevice.begin("NU54-PER-SCAN"))
    {
        return;
    }
    BLEScan.onResult(onScan);
    if (!BLEScan.startExtended(false))
    {
        Serial.println("extended scan failed");
    }
}

void loop()
{
    BLEDevice.poll();
    nucode::ble::BLEPeriodicReport report{};
    while (BLEPeriodicAdvertising.read(report))
    {
        Serial.print("periodic bytes=");
        Serial.println(report.payload_length);
    }
}
