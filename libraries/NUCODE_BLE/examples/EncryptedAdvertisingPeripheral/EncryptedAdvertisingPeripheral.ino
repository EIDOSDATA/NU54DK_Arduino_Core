/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par 목적
 * EAD payload를 매번 새 randomizer로 암호화해 advertising합니다.
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
 * @par 준비물
 * - NU54DK 보드 2대 — 1) EncryptedAdvertisingPeripheral (advertiser); 2) EncryptedAdvertisingCentral (scanner)
 * - 제품에서는 예제 key와 IV를 고유 보안 절차로 교환해야 합니다.
 * @par 설정
 * - Tools → Feature set에서 `ble` profile을 선택합니다.
 * - Sketch 폴더의 sidecar를 함께 설치합니다: prj.conf
 * - Serial Monitor는 115200 baud로 엽니다.
 * @par 실행 순서
 * - 권장 profile로 현재 Sketch와 metadata에 적힌 각 peer 역할 Sketch를 빌드합니다.
 * - probe가 여러 대이면 `NUCODE_PROBE_UID`를 지정하고 Arduino Upload로 역할별 보드를 구분합니다.
 * - peer·외장 조건을 먼저 준비한 뒤 reset 또는 예제에 명시된 입력으로 실행합니다.
 * @par 성공 출력
 * - Serial Monitor에서 오류 문구 없이 목적 기능의 상태 전이가 완료되는지 확인합니다.
 * @par 흔한 오류
 * - 권장 profile과 sidecar가 다르면 기능·Kconfig가 빠질 수 있으므로 먼저 설정을 다시 확인합니다.
 * - 여러 probe가 연결된 상태에서 UID를 생략하면 다른 보드에 upload될 수 있습니다.
 * - `EAD RPA refresh failed` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * - `EAD encryption failed` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * - `EAD advertising failed` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * @par 다음 예제
 * - `NUCODE_BLE/ExtendedAdvertising`
 * - `NUCODE_BLE/ExtendedLeFeaturePages`
 * @par 종료와 재시작
 * - 예제의 stop/end/disconnect 또는 유한 완료 흐름 뒤 오류와 자원 반환을 확인합니다.
 * - 실패 문구와 driver 상태를 확인한 뒤 명시적 reset 또는 예제의 재시작 흐름을 사용합니다.
 * @par 보안
 * - wireless_example_no_implicit_security_claim
 * - 무선 연결 성공만으로 인증·암호화·상호운용 보안을 주장하지 않습니다.
 * @par 제한
 * - Compile·Host 검사는 실제 보드 runtime 또는 외부 제품 상호운용 PASS를 대신하지 않습니다.
 * - 목적과 metadata 조건 밖의 성능·동시성·정밀도는 이 예제의 보증 범위가 아닙니다.
 * @par Negative
 * - wrong_profile_or_missing_sidecar
 * - missing_or_wrong_role_peer
 * - startup_or_runtime_error_reported
 * @par Traceability
 * Recipe `ble_advertising_scanning`; 내부 증거 ID는 metadata에서 관리합니다.
 * 직접 upstream 복사 아님; NCS `99553055607b2e9885fbc80ccd11fa9da81c2df0`, Zephyr `bf801e4e3d19e1ffa76164346480cb7734dd2800`
 * build `clean_installed_compile_required`, runtime `procedure_documented_not_physical_pass`
 * @par Metadata
 * identity `NUCODE_BLE/EncryptedAdvertisingPeripheral`, sha256 `12ad39d7f0b7536197e1cf14eab9519c2334a0a8d5a33edbed1ac2fb1d3aff6b`
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
