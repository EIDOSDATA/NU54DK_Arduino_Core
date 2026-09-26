/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: Adaptive capabilities (experimental) (adaptive, 실험적 대안)
 * @par 보드와 역할
 * 2대 — 1) NUSCentral (central/client); 2) NUSPeripheral (peripheral/server)
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * nucode-build.json
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI `--upload-field probe_id=<UID>`로 명시 선택합니다.
 * @par 추가 조건
 * 추가 조건 없음
 * @par Metadata
 * identity `NUCODE_BLE/NUSCentral`, sha256 `19a0df9c54da4170283cbfc3abe30f9a53a40da47d6d5ab5ab1a9c98b112be97`
 * @nucode_example_setup_end */

/**
 * @file NUSCentral.ino
 * @brief 이름과 NUS service로 Peripheral을 찾는 NU54DK Central 예제입니다.
 *
 * 도구 → Feature set → BLE NUS를 선택해야 합니다.
 */

#include <NUCODE_BLE.h>

void setup()
{
    Serial.begin(115200);
    if (!BLESerial.beginCentral() || !BLESerial.scanForNus("NU54-NUS"))
    {
        Serial.println("BLE NUS Central start failed");
    }
}

void loop()
{
    BLESerial.poll();
    while (BLESerial.available() > 0)
    {
        Serial.write(static_cast<uint8_t>(BLESerial.read()));
    }
    while (Serial.available() > 0 && BLESerial.ready())
    {
        BLESerial.write(static_cast<uint8_t>(Serial.read()));
    }
}
