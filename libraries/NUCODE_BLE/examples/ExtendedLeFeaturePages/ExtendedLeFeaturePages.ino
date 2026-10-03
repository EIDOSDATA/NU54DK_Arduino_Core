/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 1대 — 1) ExtendedLeFeaturePages (local controller query)
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * 없음
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 추가 조건 없음
 * @par Metadata
 * identity `NUCODE_BLE/ExtendedLeFeaturePages`, sha256 `daa243f2ef8caa70d2580d6967416c7283800c8e1df8cb9832e57745f6fd1a1a`
 * @nucode_example_setup_end */

/**
 * @file ExtendedLeFeaturePages.ino
 * @brief local controller의 확장 LE feature page를 복사해 분류합니다.
 */

#include <NUCODE_BLE.h>

void setup()
{
    Serial.begin(115200);
    if (!BLEDevice.begin("NU54-FEAT"))
    {
        Serial.println("BLE start failed");
        return;
    }
    nucode::ble::BLEExtendedFeatureSet features;
    if (!BLEConnection.localExtendedFeatures(features))
    {
        Serial.println("Local feature query failed");
        return;
    }
    Serial.print("Highest local LE feature page: ");
    Serial.println(features.maximum_valid_page);
    for (std::uint8_t page = 0U; page <= features.maximum_valid_page; ++page)
    {
        Serial.print("Page ");
        Serial.print(page);
        Serial.print(" first bit: ");
        Serial.println(features.supported(page, 0U) ? "supported" : "clear");
    }
}

void loop()
{
    BLEDevice.poll();
}
