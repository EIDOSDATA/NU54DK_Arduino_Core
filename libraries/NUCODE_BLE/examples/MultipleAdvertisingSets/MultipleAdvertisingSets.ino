/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 2대 — 1) MultipleAdvertisingSets (advertiser); 2) ExtendedScanner (scanner)
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * prj.conf
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 확장 preset은 3 advertising set을 사용합니다.
 * @par Metadata
 * identity `NUCODE_BLE/MultipleAdvertisingSets`, sha256 `cc12dc12d71bbe72b2ea51a5868762e78db870c058b32f618740b950abf7e2cd`
 * @nucode_example_setup_end */

/**
 * @file MultipleAdvertisingSets.ino
 * @brief 서로 다른 SID·payload·PHY를 가진 세 advertising set을 동시에 실행합니다.
 */

#include <NUCODE_BLE.h>

nucode::ble::BLEAdvertisingSetHandle advertisingSets[3];
const uint8_t payloads[3][4] = {
    {3U, 0xffU, 0x41U, 0U},
    {3U, 0xffU, 0x42U, 1U},
    {3U, 0xffU, 0x43U, 2U},
};

void setup()
{
    Serial.begin(115200);
    if (!BLEDevice.begin("NU54-MULTI-ADV"))
    {
        Serial.println("BLE start failed");
        return;
    }
    for (size_t index = 0U; index < 3U; ++index)
    {
        nucode::ble::BLEExtendedAdvertisingParameters parameters;
        parameters.sid = static_cast<uint8_t>(index);
        parameters.coded = index == 2U;
        parameters.coding = index == 2U ? nucode::ble::BLEAdvertisingCoding::s8
                                        : nucode::ble::BLEAdvertisingCoding::automatic;
        if (!BLEExtendedAdvertising.create(parameters, advertisingSets[index]) ||
            !BLEExtendedAdvertising.setData(advertisingSets[index], payloads[index],
                                             sizeof(payloads[index])) ||
            !BLEExtendedAdvertising.start(advertisingSets[index]))
        {
            Serial.println("advertising set start failed");
            return;
        }
    }
    Serial.println("three advertising sets started");
}

void loop()
{
    BLEDevice.poll();
}
