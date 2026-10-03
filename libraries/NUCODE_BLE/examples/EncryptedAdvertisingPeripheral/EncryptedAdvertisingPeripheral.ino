/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 2대 — 1) EncryptedAdvertisingPeripheral (advertiser); 2) EncryptedAdvertisingCentral (scanner)
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * prj.conf
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 제품에서는 예제 key와 IV를 고유 보안 절차로 교환해야 합니다.
 * @par Metadata
 * identity `NUCODE_BLE/EncryptedAdvertisingPeripheral`, sha256 `eadd85208f45aceee098e7299dcb6590b36615138df2a38197fbc813d56ef4cf`
 * @nucode_example_setup_end */

/**
 * @file EncryptedAdvertisingPeripheral.ino
 * @brief EAD payload를 매번 새 randomizer로 암호화해 advertising합니다.
 */

#include <NUCODE_BLE.h>

#include <string.h>

nucode::ble::EncryptedAdvertisingData ead;
nucode::ble::BLEAdvertisingSetHandle advertisingSet;
uint8_t key[nucode::ble::EncryptedAdvertisingData::session_key_length] = {
    0x10U, 0x11U, 0x12U, 0x13U, 0x14U, 0x15U, 0x16U, 0x17U,
    0x18U, 0x19U, 0x1aU, 0x1bU, 0x1cU, 0x1dU, 0x1eU, 0x1fU,
};
uint8_t iv[nucode::ble::EncryptedAdvertisingData::initialization_vector_length] = {
    0xa0U, 0xa1U, 0xa2U, 0xa3U, 0xa4U, 0xa5U, 0xa6U, 0xa7U,
};
uint8_t encryptedAd[32] = {};
uint8_t advertisingPayload[34] = {};
const uint8_t plaintext[] = {3U, 0xffU, 0x54U, 0x01U};

/** @brief 새 randomizer로 EAD를 만들고 실행 중 set의 payload를 갱신합니다. */
bool refreshEncryptedAdvertising()
{
    size_t encryptedLength = 0U;
    if (!ead.encrypt(plaintext, sizeof(plaintext), encryptedAd,
                     sizeof(encryptedAd), encryptedLength))
    {
        return false;
    }
    advertisingPayload[0] = static_cast<uint8_t>(encryptedLength + 1U);
    advertisingPayload[1] = 0x31U;
    ::memcpy(&advertisingPayload[2], encryptedAd, encryptedLength);
    return BLEExtendedAdvertising.setData(advertisingSet, advertisingPayload,
                                          encryptedLength + 2U);
}

/** @brief RPA 만료 뒤 EAD randomizer를 교체해 nonce 재사용을 막습니다. */
void onBleEvent(const nucode::ble::BLEEventInfo &information, void *context)
{
    static_cast<void>(context);
    if (information.event == nucode::ble::BLEEvent::rpa_expired &&
        information.advertising_set == advertisingSet &&
        !refreshEncryptedAdvertising())
    {
        Serial.println("EAD RPA refresh failed");
    }
}

void setup()
{
    Serial.begin(115200);
    BLEDevice.onEventInfo(onBleEvent);
    nucode::ble::BLEExtendedAdvertisingParameters parameters;
    parameters.sid = 4U;
    if (!BLEDevice.begin("NU54-EAD-P") || !ead.configure(key, iv) ||
        !BLEExtendedAdvertising.create(parameters, advertisingSet) ||
        !refreshEncryptedAdvertising())
    {
        Serial.println("EAD encryption failed");
        return;
    }
    if (!BLEExtendedAdvertising.start(advertisingSet))
    {
        Serial.println("EAD advertising failed");
    }
}

void loop()
{
    BLEDevice.poll();
}
