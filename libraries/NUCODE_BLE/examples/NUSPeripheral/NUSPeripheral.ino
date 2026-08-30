/**
 * @file NUSPeripheral.ino
 * @brief NU54DK를 Nordic UART Service Peripheral로 실행합니다.
 *
 * 도구 → Feature set → BLE NUS를 선택해야 합니다.
 */

#include <NUCODE_BLE.h>

/** @brief BLE 상태를 Arduino main 문맥의 Serial에 기록합니다. */
void onBleEvent(nucode::ble::Event event, void *context)
{
  (void)context;
  Serial.print("BLE event: ");
  Serial.println(static_cast<unsigned int>(event));
}

void setup()
{
  Serial.begin(115200);
  BLESerial.onEvent(onBleEvent);
  if (!BLESerial.beginPeripheral("NU54-NUS") || !BLESerial.startAdvertising()) {
    Serial.println("BLE NUS Peripheral start failed");
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

