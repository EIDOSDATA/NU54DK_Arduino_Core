/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 2대 — 1) LePowerControlCentral (central/controller); 2) LePowerControlPeripheral (peripheral/device)
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * 없음
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 추가 조건 없음
 * @par Metadata
 * identity `NUCODE_BLE/LePowerControlPeripheral`, sha256 `dabcb667b15ca064a7d23d04e3f6786d3267064044d6e238c02d23e4c0c7fcba`
 * @nucode_example_setup_end */

/**
 * @file LePowerControlPeripheral.ino
 * @brief 표준 LE Power Control report를 제공하는 Peripheral 예제입니다.
 */

#include <NUCODE_BLE.h>

bool restartAdvertising = false;

/** @brief 연결별 송신 전력 reporting을 설정하고 report 복사본을 출력합니다. */
void onBleEvent(const nucode::ble::BLEEventInfo &information, void *context)
{
    static_cast<void>(context);
    if (information.event == nucode::ble::BLEEvent::connected)
    {
        if (!BLEConnection.setTransmitPowerReporting(information.connection, true, true) ||
            !BLEConnection.requestRemoteTransmitPower(
                information.connection, nucode::ble::BLETransmitPowerPhy::le_1m))
        {
            Serial.println("LE power reporting setup failed");
        }
    }
    else if (information.event == nucode::ble::BLEEvent::transmit_power_report)
    {
        Serial.print("Peer TX power: ");
        Serial.print(information.transmit_power.level_dbm);
        Serial.println(" dBm");
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
    if (!BLEDevice.begin("NU54-PWR-P") || !BLEAdvertising.clear() ||
        !BLEAdvertising.setConnectable(true) || !BLEAdvertising.start())
    {
        Serial.println("LE power control advertising failed");
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
