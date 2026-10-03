/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 2대 — 1) MultipleBleIdentities (advertiser); 2) ExtendedScanner (scanner)
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * prj.conf
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 생성된 identity와 IRK는 settings에 보존됩니다.
 * @par Metadata
 * identity `NUCODE_BLE/MultipleBleIdentities`, sha256 `67beb7ba51545a30a6a04326785fb1e40adda1367992b4c8874d235b319b2503`
 * @nucode_example_setup_end */

/**
 * @file MultipleBleIdentities.ino
 * @brief 세 local identity를 서로 다른 advertising set에 결합합니다.
 */

#include <NUCODE_BLE.h>

nucode::ble::BLEAdvertisingSetHandle advertisingSets[3];

void setup()
{
    Serial.begin(115200);
    if (!BLEDevice.begin("NU54-MULTI-ID"))
    {
        Serial.println("BLE start failed");
        return;
    }
    for (uint8_t identity = 1U; identity < 3U; ++identity)
    {
        nucode::ble::BLEAddress address;
        if (BLEIdentity.address(identity, address))
        {
            continue;
        }
        uint8_t created = 0xffU;
        if (!BLEIdentity.create(created, address) || created != identity)
        {
            Serial.println("identity create failed");
            return;
        }
    }
    for (uint8_t identity = 0U; identity < 3U; ++identity)
    {
        nucode::ble::BLEExtendedAdvertisingParameters parameters;
        parameters.identity = identity;
        parameters.sid = identity;
        if (!BLEExtendedAdvertising.create(parameters, advertisingSets[identity]) ||
            !BLEExtendedAdvertising.start(advertisingSets[identity]))
        {
            Serial.println("identity advertising failed");
            return;
        }
    }
    Serial.println("three identities advertising");
}

void loop()
{
    BLEDevice.poll();
}
