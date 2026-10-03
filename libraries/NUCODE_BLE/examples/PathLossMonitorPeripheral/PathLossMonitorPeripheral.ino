/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 2대 — 1) PathLossMonitorCentral (central/monitor); 2) PathLossMonitorPeripheral (peripheral/monitor)
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * 없음
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 추가 조건 없음
 * @par Metadata
 * identity `NUCODE_BLE/PathLossMonitorPeripheral`, sha256 `af12cca6844e20302d71dfc0bdee50204fd40266738aa8b83b1c7edf60ae80b5`
 * @nucode_example_setup_end */

/**
 * @file PathLossMonitorPeripheral.ino
 * @brief 표준 Path Loss threshold 구간 변화를 수신하는 Peripheral 예제입니다.
 */

#include <NUCODE_BLE.h>

bool restartAdvertising = false;

/** @brief 연결별 threshold monitoring과 광고 재시작을 관리합니다. */
void onBleEvent(const nucode::ble::BLEEventInfo &information, void *context)
{
    static_cast<void>(context);
    if (information.event == nucode::ble::BLEEvent::connected)
    {
        nucode::ble::BLEPathLossParameters parameters;
        if (!BLEConnection.configurePathLossMonitoring(information.connection,
                                                       parameters) ||
            !BLEConnection.setPathLossMonitoring(information.connection, true))
        {
            Serial.println("Path Loss monitoring setup failed");
        }
    }
    else if (information.event == nucode::ble::BLEEvent::path_loss_changed)
    {
        Serial.print("Path Loss: ");
        Serial.print(information.path_loss.path_loss_db);
        Serial.println(" dB");
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
    if (!BLEDevice.begin("NU54-PATH-P") || !BLEAdvertising.clear() ||
        !BLEAdvertising.setConnectable(true) || !BLEAdvertising.start())
    {
        Serial.println("Path Loss advertising failed");
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
