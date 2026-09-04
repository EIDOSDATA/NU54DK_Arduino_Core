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
