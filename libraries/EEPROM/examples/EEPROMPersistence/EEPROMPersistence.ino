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
  while (!Serial && millis() < 3000) {
  }

  if (!EEPROM.begin(EEPROMClass::maximum_size)) {
    Serial.println("EEPROM open failed; call EEPROM.reset() only for explicit recovery.");
    return;
  }

  uint32_t boots = 0;
  EEPROM.get(0, boots);
  if (boots == 0xffffffffUL) {
    boots = 0;
  }
  ++boots;
  EEPROM.put(0, boots);
  if (!EEPROM.commit()) {
    Serial.println("EEPROM commit failed.");
    return;
  }
  Serial.print("Persistent boot count: ");
  Serial.println(boots);
}

void loop()
{
}
