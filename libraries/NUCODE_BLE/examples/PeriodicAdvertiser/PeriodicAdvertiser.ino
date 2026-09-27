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
 * identity `NUCODE_BLE/PeriodicAdvertiser`, sha256 `f48b49e6e0110397dcece70ae264175012421c18b84822ef2a38274d6df28993`
 * @nucode_example_setup_end */

/**
 * @file PeriodicAdvertiser.ino
 * @brief Extended set에 periodic manufacturer data를 결합해 송신합니다.
 */

#include <NUCODE_BLE.h>

nucode::ble::BLEAdvertisingSetHandle advertisingSet;
uint8_t extendedPayload[] = {3U, 0x09U, 'P', 'A'};
uint8_t periodicPayload[] = {4U, 0xffU, 0x59U, 0x00U, 0U};

void setup()
{
    Serial.begin(115200);
    nucode::ble::BLEExtendedAdvertisingParameters extendedParameters{};
    extendedParameters.sid = 2U;
    if (!BLEDevice.begin("NU54-PER-ADV") ||
        !BLEExtendedAdvertising.create(extendedParameters, advertisingSet) ||
        !BLEExtendedAdvertising.setData(advertisingSet, extendedPayload,
                                        sizeof(extendedPayload)) ||
        !BLEPeriodicAdvertising.configure(advertisingSet) ||
        !BLEPeriodicAdvertising.setData(advertisingSet, periodicPayload,
                                        sizeof(periodicPayload)) ||
        !BLEPeriodicAdvertising.start(advertisingSet) ||
        !BLEExtendedAdvertising.start(advertisingSet))
    {
        Serial.println("periodic advertiser failed");
    }
}

void loop()
{
    static uint8_t sequence = 0U;
    BLEDevice.poll();
    periodicPayload[4] = sequence++;
    if (!BLEPeriodicAdvertising.setData(advertisingSet, periodicPayload,
                                        sizeof(periodicPayload)))
    {
        Serial.println("periodic payload update failed");
    }
    delay(1000);
}
