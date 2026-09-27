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
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 추가 조건 없음
 * @par Metadata
 * identity `NUCODE_BLE/ExtendedAdvertising`, sha256 `fc3048beab88f0bdc27e39ada3aa0caa727f77a39569b5b051e01bfd40cefcd2`
 * @nucode_example_setup_end */

/**
 * @file ExtendedAdvertising.ino
 * @brief SID 3과 255-byte payload로 non-connectable extended advertising을 실행합니다.
 */

#include <NUCODE_BLE.h>

nucode::ble::BLEAdvertisingSetHandle advertisingSet;
uint8_t advertisingPayload[255] = {};

/** @brief 한 개의 최대 길이 manufacturer AD structure를 구성합니다. */
void preparePayload()
{
    advertisingPayload[0] = 254U;
    advertisingPayload[1] = 0xffU;
    for (size_t index = 2U; index < sizeof(advertisingPayload); ++index)
    {
        advertisingPayload[index] = static_cast<uint8_t>(index);
    }
}

void setup()
{
    Serial.begin(115200);
    preparePayload();
    nucode::ble::BLEExtendedAdvertisingParameters parameters{};
    parameters.sid = 3U;
    parameters.include_tx_power = true;
    if (!BLEDevice.begin("NU54-EXT-ADV") ||
        !BLEExtendedAdvertising.create(parameters, advertisingSet) ||
        !BLEExtendedAdvertising.setData(advertisingSet, advertisingPayload,
                                        sizeof(advertisingPayload)) ||
        !BLEExtendedAdvertising.start(advertisingSet))
    {
        Serial.println("extended advertising failed");
    }
}

void loop()
{
    BLEDevice.poll();
}
