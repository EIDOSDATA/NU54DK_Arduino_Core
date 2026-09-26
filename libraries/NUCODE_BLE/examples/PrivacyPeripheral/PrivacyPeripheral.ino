/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 1대 — 1) PrivacyPeripheral (peripheral/server)
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * 없음
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI `--upload-field probe_id=<UID>`로 명시 선택합니다.
 * @par 추가 조건
 * 동작에 필요한 compatible BLE peer 또는 mobile/host client를 별도로 준비합니다.
 * @par Metadata
 * identity `NUCODE_BLE/PrivacyPeripheral`, sha256 `58aedc1ab7826560fbe6394e812319c0116e07a88dfac54fa4d5770d4b75bba5`
 * @nucode_example_setup_end */

/**
 * @file PrivacyPeripheral.ino
 * @brief 60초 RPA 회전을 사용하는 extended advertising 예제입니다.
 */

#include <NUCODE_BLE.h>

nucode::ble::BLEAdvertisingSetHandle advertisingSet;

/** @brief RPA 만료 event가 실제 set과 결합되었는지 출력합니다. */
void onBleEvent(const nucode::ble::BLEEventInfo &information, void *context)
{
    static_cast<void>(context);
    if (information.event == nucode::ble::BLEEvent::rpa_expired &&
        information.advertising_set == advertisingSet)
    {
        Serial.print("RPA expiration count: ");
        Serial.println(BLEPrivacy.expirationCount());
    }
}

void setup()
{
    Serial.begin(115200);
    BLEDevice.onEventInfo(onBleEvent);
    nucode::ble::BLEExtendedAdvertisingParameters parameters{};
    parameters.connectable = true;
    parameters.sid = 6U;
    if (!BLEDevice.begin("NU54-PRIVATE") ||
        !BLEPrivacy.setRotationTimeout(60U) ||
        !BLEExtendedAdvertising.create(parameters, advertisingSet) ||
        !BLEExtendedAdvertising.start(advertisingSet))
    {
        Serial.println("privacy advertising failed");
    }
}

void loop()
{
    BLEDevice.poll();
}
