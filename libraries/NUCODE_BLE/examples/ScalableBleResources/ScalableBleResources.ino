/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 1대 — 1) ScalableBleResources 실행 보드
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * prj.conf
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 확장 preset의 실제 RAM/RRAM 값은 M32 build evidence를 확인합니다.
 * @par Metadata
 * identity `NUCODE_BLE/ScalableBleResources`, sha256 `4c0e34881ab19f1598a8a9628a82a64fa0d3956c0df02bf4acba8bbeceefbace`
 * @nucode_example_setup_end */

/**
 * @file ScalableBleResources.ino
 * @brief 확장 BLE resource preset의 advertising·identity·sync 상한을 표시합니다.
 */

#include <NUCODE_BLE.h>

void setup()
{
    Serial.begin(115200);
    if (!BLEDevice.begin("NU54-BLE-SCALE"))
    {
        Serial.println("BLE start failed");
        return;
    }
    Serial.print("advertising sets: ");
    Serial.println(nucode::ble::ExtendedAdvertising::product_maximum_sets);
    Serial.print("identities: ");
    Serial.println(nucode::ble::Identity::product_maximum_identities);
    Serial.print("filter accept capacity: ");
    Serial.println(BLEAdvertisingLists.filterAcceptCapacity());
    Serial.print("periodic advertiser capacity: ");
    Serial.println(BLEAdvertisingLists.periodicAdvertiserCapacity());
}

void loop()
{
    BLEDevice.poll();
}
