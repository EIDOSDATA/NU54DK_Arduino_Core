/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 2대 — 1) PawrAdvertiser (advertiser); 2) PawrScanner (scanner)
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * 없음
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI `--upload-field probe_id=<UID>`로 명시 선택합니다.
 * @par 추가 조건
 * 추가 조건 없음
 * @par Metadata
 * identity `NUCODE_BLE/PawrAdvertiser`, sha256 `c4c94960878b69e6b1bb0a86424079e4e6d4f066293fe32d890d3cedb5d330c6`
 * @nucode_example_setup_end */

/**
 * @file PawrAdvertiser.ino
 * @brief 4 subevent × 4 response slot PAwR train을 송신하고 response를 읽습니다.
 */

#include <NUCODE_BLE.h>

nucode::ble::BLEAdvertisingSetHandle advertisingSet;
uint8_t extendedPayload[] = {3U, 0x09U, 'P', 'R'};

/** @brief main-thread로 전달된 PAwR response의 위치와 길이를 출력합니다. */
void onResponse(const nucode::ble::BLEPawrResponse &response, void *)
{
    Serial.print("response subevent=");
    Serial.print(response.subevent);
    Serial.print(" slot=");
    Serial.print(response.response_slot);
    Serial.print(" bytes=");
    Serial.println(response.payload_length);
}

void setup()
{
    Serial.begin(115200);
    nucode::ble::BLEExtendedAdvertisingParameters extendedParameters{};
    extendedParameters.sid = 3U;
    if (!BLEDevice.begin("NU54-PAWR-ADV") ||
        !BLEExtendedAdvertising.create(extendedParameters, advertisingSet) ||
        !BLEExtendedAdvertising.setData(advertisingSet, extendedPayload,
                                        sizeof(extendedPayload)) ||
        !BLEPawr.configureAdvertiser(advertisingSet))
    {
        return;
    }
    for (uint8_t subevent = 0U; subevent < 4U; ++subevent)
    {
        const uint8_t payload[] = {subevent, 0xa5U};
        if (!BLEPawr.setSubeventData(advertisingSet, subevent, payload,
                                    sizeof(payload)))
        {
            return;
        }
    }
    BLEPawr.onResponse(onResponse);
    if (!BLEPeriodicAdvertising.start(advertisingSet) ||
        !BLEExtendedAdvertising.start(advertisingSet))
    {
        Serial.println("PAwR advertiser start failed");
    }
}

void loop()
{
    BLEDevice.poll();
}
