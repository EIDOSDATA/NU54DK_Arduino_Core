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
  if (!BLESerial.beginCentral() || !BLESerial.scanForNus("NU54-NUS")) {
    Serial.println("BLE NUS Central start failed");
  }
}

void loop()
{
  BLESerial.poll();
  while (BLESerial.available() > 0) {
    Serial.write(static_cast<uint8_t>(BLESerial.read()));
  }
  while (Serial.available() > 0 && BLESerial.ready()) {
    BLESerial.write(static_cast<uint8_t>(Serial.read()));
  }
}

