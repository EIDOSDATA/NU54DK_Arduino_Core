/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 2대 — 1) NUSCentral (central/client); 2) NUSPeripheral (peripheral/server)
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * 없음
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI `--upload-field probe_id=<UID>`로 명시 선택합니다.
 * @par 추가 조건
 * 추가 조건 없음
 * @par Metadata
 * identity `NUCODE_BLE/NUSPeripheral`, sha256 `2f11bc195734f0991fbcb1a59c7bf2cf658d373bcecf275aa740cf6ba94f0ad0`
 * @nucode_example_setup_end */

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
    switch (event)
    {
    case nucode::ble::Event::advertising_started:
        Serial.println("BLE advertising started");
        break;
    case nucode::ble::Event::connected:
        Serial.println("BLE connected");
        break;
    case nucode::ble::Event::ready:
        Serial.println("BLE NUS ready");
        break;
    case nucode::ble::Event::disconnected:
        Serial.println("BLE disconnected");
        break;
    case nucode::ble::Event::error:
        /** @brief Event queue에 오류 snapshot이 없으므로 오래된 전역 오류값을 출력하지 않습니다. */
        Serial.println("BLE error");
        break;
    case nucode::ble::Event::received:
        /** @brief 수신 데이터는 아래 Stream 경로에서 원문 그대로 출력합니다. */
        break;
    case nucode::ble::Event::scan_started:
        /** @brief Peripheral 역할에서는 발생하지 않습니다. */
        break;
    }
}

void setup()
{
    Serial.begin(115200);
    BLESerial.onEvent(onBleEvent);
    if (!BLESerial.beginPeripheral("NU54-NUS") || !BLESerial.startAdvertising())
    {
        Serial.println("BLE NUS Peripheral start failed");
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
