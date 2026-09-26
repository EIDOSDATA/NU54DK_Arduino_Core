/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: Standard peripherals (`standard`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 1대 — 1) EEPROMPersistence 실행 보드
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * 없음
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI `--upload-field probe_id=<UID>`로 명시 선택합니다.
 * @par 추가 조건
 * 추가 조건 없음
 * @par Metadata
 * identity `EEPROM/EEPROMPersistence`, sha256 `571428d2e0bd03400f64a9b56c0160260ac551534ae388e57c3407fbbad81126`
 * @nucode_example_setup_end */

/**
 * @file EEPROMPersistence.ino
 * @brief reset 뒤에도 유지되는 EEPROM counter와 명시적 commit을 보여 줍니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <EEPROM.h>

void setup()
{
    Serial.begin(115200);
    while (!Serial && millis() < 3000)
    {
    }

    if (!EEPROM.begin(EEPROMClass::maximum_size))
    {
        Serial.println("EEPROM open failed; call EEPROM.reset() only for explicit recovery.");
        return;
    }

    uint32_t boots = 0;
    EEPROM.get(0, boots);
    if (boots == 0xffffffffUL)
    {
        boots = 0;
    }
    ++boots;
    EEPROM.put(0, boots);
    if (!EEPROM.commit())
    {
        Serial.println("EEPROM commit failed.");
        return;
    }
    Serial.print("Persistent boot count: ");
    Serial.println(boots);
}

void loop()
{
}
