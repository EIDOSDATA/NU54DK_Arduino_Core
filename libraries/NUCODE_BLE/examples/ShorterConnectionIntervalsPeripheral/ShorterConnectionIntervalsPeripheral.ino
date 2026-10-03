/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 2대 — 1) ShorterConnectionIntervalsCentral (central/requester); 2) ShorterConnectionIntervalsPeripheral (peripheral/responder)
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * 없음
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 추가 조건 없음
 * @par Metadata
 * identity `NUCODE_BLE/ShorterConnectionIntervalsPeripheral`, sha256 `42add0daa8da6a06a2bf81a2c24b92061a162534ba63717863a8a6b349240d51`
 * @nucode_example_setup_end */

/**
 * @file ShorterConnectionIntervalsPeripheral.ino
 * @brief 표준 Connection Rate 변경 결과를 관측하는 Peripheral 예제입니다.
 */

#include <NUCODE_BLE.h>

bool restartAdvertising = false;

/** @brief 실제 rate 결과와 연결 종료를 처리합니다. */
void onBleEvent(const nucode::ble::BLEEventInfo &information, void *context)
{
    static_cast<void>(context);
    if (information.event == nucode::ble::BLEEvent::connection_rate_changed)
    {
        nucode::ble::BLEConnectionRateInfo result;
        if (BLEConnection.connectionRate(information.connection, result))
        {
            Serial.print("Connection interval: ");
            Serial.print(result.interval_us);
            Serial.println(" us");
        }
    }
    else if (information.event == nucode::ble::BLEEvent::disconnected)
    {
        restartAdvertising = true;
    }
}

void setup()
{
    Serial.begin(115200);
    BLEDevice.onEventInfo(onBleEvent);
    if (!BLEDevice.begin("NU54-SCI-P") || !BLEAdvertising.clear() ||
        !BLEAdvertising.setConnectable(true) || !BLEAdvertising.start())
    {
        Serial.println("Shorter interval peripheral start failed");
    }
}

void loop()
{
    BLEDevice.poll();
    if (restartAdvertising && !BLEConnection.connected())
    {
        restartAdvertising = false;
        static_cast<void>(BLEAdvertising.start());
    }
}
