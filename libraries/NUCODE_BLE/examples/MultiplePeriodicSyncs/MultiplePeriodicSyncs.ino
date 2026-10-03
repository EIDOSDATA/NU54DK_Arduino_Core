/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 3대 — 1) PeriodicAdvertiser 첫 번째 송신기; 2) PeriodicAdvertiser 두 번째 송신기; 3) MultiplePeriodicSyncs (scanner)
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * prj.conf
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 두 advertiser는 서로 다른 주소와 SID를 사용해야 합니다.
 * @par Metadata
 * identity `NUCODE_BLE/MultiplePeriodicSyncs`, sha256 `92c15136a8c786c1138475a4b1688bb41d921d7ca90ed74ad623fc50c59906e0`
 * @nucode_example_setup_end */

/**
 * @file MultiplePeriodicSyncs.ino
 * @brief 검색한 서로 다른 두 periodic advertiser에 bounded sync를 생성합니다.
 */

#include <NUCODE_BLE.h>

nucode::ble::BLEScanResult candidates[2];
nucode::ble::BLEPeriodicSyncHandle syncs[2];
size_t candidateCount = 0U;

/** @brief 서로 다른 주소·SID의 periodic advertiser를 두 개까지 보존합니다. */
void onScanResult(const nucode::ble::BLEScanResult &result, void *context)
{
    static_cast<void>(context);
    if (result.periodic_interval == 0U || candidateCount >= 2U)
    {
        return;
    }
    for (size_t index = 0U; index < candidateCount; ++index)
    {
        if (candidates[index].address == result.address &&
            candidates[index].sid == result.sid)
        {
            return;
        }
    }
    candidates[candidateCount++] = result;
}

void setup()
{
    Serial.begin(115200);
    BLEScan.onResult(onScanResult);
    if (!BLEDevice.begin("NU54-MULTI-SYNC") || !BLEScan.startExtended(false))
    {
        Serial.println("periodic scan start failed");
    }
}

void loop()
{
    BLEDevice.poll();
    if (candidateCount == 2U && !syncs[0].valid())
    {
        static_cast<void>(BLEScan.stop());
        for (size_t index = 0U; index < 2U; ++index)
        {
            if (!BLEPeriodicAdvertising.createSync(candidates[index].address,
                                                   candidates[index].sid, syncs[index]))
            {
                Serial.println("periodic sync create failed");
                return;
            }
        }
        Serial.println("two periodic syncs created");
    }
}
