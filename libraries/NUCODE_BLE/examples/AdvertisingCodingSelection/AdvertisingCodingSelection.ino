/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 2대 — 1) AdvertisingCodingSelection (advertiser); 2) ExtendedScanner (coded scanner)
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * prj.conf
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * S=2와 S=8 선택은 controller Advertising Coding Selection 지원이 필요합니다.
 * @par Metadata
 * identity `NUCODE_BLE/AdvertisingCodingSelection`, sha256 `a5d4d00a99f40824bd352405a790a99ed41d989ffe0fb1ccb21329031ea91823`
 * @nucode_example_setup_end */

/**
 * @file AdvertisingCodingSelection.ino
 * @brief LE Coded PHY S=2와 S=8 advertising set을 동시에 실행합니다.
 */

#include <NUCODE_BLE.h>

nucode::ble::BLEAdvertisingSetHandle advertisingSets[2];

void setup()
{
    Serial.begin(115200);
    if (!BLEDevice.begin("NU54-CODING"))
    {
        Serial.println("BLE start failed");
        return;
    }
    for (size_t index = 0U; index < 2U; ++index)
    {
        nucode::ble::BLEExtendedAdvertisingParameters parameters;
        parameters.sid = static_cast<uint8_t>(index + 8U);
        parameters.coded = true;
        parameters.coding = index == 0U ? nucode::ble::BLEAdvertisingCoding::s2
                                        : nucode::ble::BLEAdvertisingCoding::s8;
        if (!BLEExtendedAdvertising.create(parameters, advertisingSets[index]) ||
            !BLEExtendedAdvertising.start(advertisingSets[index]))
        {
            Serial.println("coded advertising failed");
            return;
        }
    }
    Serial.println("S2 and S8 advertising started");
}

void loop()
{
    BLEDevice.poll();
}
