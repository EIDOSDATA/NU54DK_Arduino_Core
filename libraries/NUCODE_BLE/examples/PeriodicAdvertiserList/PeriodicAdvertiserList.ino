/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 3대 — 1) PeriodicAdvertiser 첫 번째 송신기; 2) PeriodicAdvertiser 두 번째 송신기; 3) PeriodicAdvertiserList 실행 보드
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * prj.conf
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 예제의 두 주소와 SID를 실제 advertiser 값으로 바꿉니다.
 * @par Metadata
 * identity `NUCODE_BLE/PeriodicAdvertiserList`, sha256 `4adabc3b3a2a456d134e73a93a493c08fd33a6da35760d07c4d91eb80c584379`
 * @nucode_example_setup_end */

/**
 * @file PeriodicAdvertiserList.ino
 * @brief 두 주소·SID를 controller Periodic Advertiser List에 등록합니다.
 */

#include <NUCODE_BLE.h>

const nucode::ble::BLEAddress advertisers[2] = {
    nucode::ble::BLEAddress("C0:DE:00:00:00:01",
                            nucode::ble::BLEAddress::Type::random_address),
    nucode::ble::BLEAddress("C0:DE:00:00:00:02",
                            nucode::ble::BLEAddress::Type::random_address),
};

void setup()
{
    Serial.begin(115200);
    if (!BLEDevice.begin("NU54-PAL") ||
        !BLEAdvertisingLists.clearPeriodicAdvertisers() ||
        !BLEAdvertisingLists.addPeriodicAdvertiser(advertisers[0], 1U) ||
        !BLEAdvertisingLists.addPeriodicAdvertiser(advertisers[1], 2U))
    {
        Serial.println("periodic advertiser list failed");
        return;
    }
    Serial.print("periodic list capacity: ");
    Serial.println(BLEAdvertisingLists.periodicAdvertiserCapacity());
}

void loop()
{
    BLEDevice.poll();
}
