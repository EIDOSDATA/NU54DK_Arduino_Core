/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: Standard peripherals (`standard`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 1대 — 1) LittleFSPersistence 실행 보드
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * 없음
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI `--upload-field probe_id=<UID>`로 명시 선택합니다.
 * @par 추가 조건
 * 추가 조건 없음
 * @par Metadata
 * identity `LittleFS/LittleFSPersistence`, sha256 `deb7adae344381de00b84a4a2644a50c4a94067623b13d5461f7641605c9816c`
 * @nucode_example_setup_end */

/**
 * @file LittleFSPersistence.ino
 * @brief 비파괴 mount와 명시적 LittleFS 복구 사용법을 보여 줍니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <LittleFS.h>

void setup()
{
    Serial.begin(115200);
    while (!Serial && millis() < 3000)
    {
    }

    /** @brief 기본 begin은 손상되었거나 빈 partition을 자동으로 포맷하지 않습니다. */
    if (!LittleFS.begin(false))
    {
        Serial.println("LittleFS mount failed. Run LittleFS.format() only after approval.");
        return;
    }

    uint32_t boots = 0;
    File input = LittleFS.open("/boot-count.bin", FILE_READ);
    if (input &&
        input.readBytes(reinterpret_cast<uint8_t *>(&boots), sizeof(boots)) != sizeof(boots))
    {
        boots = 0;
    }
    input.close();

    ++boots;
    File output = LittleFS.open("/boot-count.bin", FILE_WRITE);
    if (!output ||
        output.write(reinterpret_cast<const uint8_t *>(&boots), sizeof(boots)) != sizeof(boots))
    {
        Serial.println("LittleFS write failed.");
        return;
    }
    output.close();
    Serial.print("Persistent LittleFS boot count: ");
    Serial.println(boots);
}

void loop()
{
}
