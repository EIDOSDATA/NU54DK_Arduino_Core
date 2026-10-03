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
 * identity `NUCODE_BLE/EncryptedAdvertisingCentral`, sha256 `6ef3687a1cd4aa34690dd3278438f94e1d3af06a7a89fdbb45eae22830b800d0`
 * @nucode_example_setup_end */

/**
 * @file EncryptedAdvertisingCentral.ino
 * @brief 수신한 EAD의 MIC와 randomizer replay를 검사해 복호화합니다.
 */

#include <NUCODE_BLE.h>

nucode::ble::EncryptedAdvertisingData ead;
uint8_t key[nucode::ble::EncryptedAdvertisingData::session_key_length] = {
    0x10U, 0x11U, 0x12U, 0x13U, 0x14U, 0x15U, 0x16U, 0x17U,
    0x18U, 0x19U, 0x1aU, 0x1bU, 0x1cU, 0x1dU, 0x1eU, 0x1fU,
};
uint8_t iv[nucode::ble::EncryptedAdvertisingData::initialization_vector_length] = {
    0xa0U, 0xa1U, 0xa2U, 0xa3U, 0xa4U, 0xa5U, 0xa6U, 0xa7U,
};

/** @brief AD stream에서 type 0x31 EAD를 찾아 인증·복호화합니다. */
void onScanResult(const nucode::ble::BLEScanResult &result, void *context)
{
    static_cast<void>(context);
    size_t offset = 0U;
    while (offset < result.payload_length)
    {
        const size_t length = result.payload[offset];
        if (length == 0U || offset + length + 1U > result.payload_length)
        {
            return;
        }
        if (result.payload[offset + 1U] == 0x31U)
        {
            uint8_t plaintext[246] = {};
            size_t plaintextLength = 0U;
            if (ead.decrypt(&result.payload[offset + 2U], length - 1U,
                            plaintext, sizeof(plaintext), plaintextLength))
            {
                Serial.print("authenticated EAD bytes: ");
                Serial.println(plaintextLength);
            }
            return;
        }
        offset += length + 1U;
    }
}

void setup()
{
    Serial.begin(115200);
    BLEScan.onResult(onScanResult);
    if (!BLEDevice.begin("NU54-EAD-C") || !ead.configure(key, iv) ||
        !BLEScan.startExtended(false))
    {
        Serial.println("EAD scanner failed");
    }
}

void loop()
{
    BLEDevice.poll();
}
