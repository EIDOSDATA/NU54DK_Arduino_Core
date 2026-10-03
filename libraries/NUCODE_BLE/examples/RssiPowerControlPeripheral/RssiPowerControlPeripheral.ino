/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 2대 — 1) RssiPowerControlCentral (central/controller); 2) RssiPowerControlPeripheral (peripheral/device)
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * 없음
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 추가 조건 없음
 * @par Metadata
 * identity `NUCODE_BLE/RssiPowerControlPeripheral`, sha256 `bb15a1f29a21cb0bc61bff63dc5f8c1c9351bfe48a3b2f4f7ac0d6e2736e8207`
 * @nucode_example_setup_end */

/**
 * @file RssiPowerControlPeripheral.ino
 * @brief RSSI 기반 Central의 표준 송신 전력 변경 요청을 받는 Peripheral 예제입니다.
 */

#include <NUCODE_BLE.h>

bool restartAdvertising = false;

/** @brief 송신 전력 reporting과 연결 종료 후 광고 재시작을 관리합니다. */
void onBleEvent(const nucode::ble::BLEEventInfo &information, void *context)
{
    static_cast<void>(context);
    if (information.event == nucode::ble::BLEEvent::connected)
    {
        if (!BLEConnection.setTransmitPowerReporting(information.connection, true, false))
        {
            Serial.println("TX power reporting setup failed");
        }
    }
    else if (information.event == nucode::ble::BLEEvent::transmit_power_report)
    {
        Serial.print("Local TX power: ");
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
    if (!BLEDevice.begin("NU54-RSSI-P") || !BLEAdvertising.clear() ||
        !BLEAdvertising.setConnectable(true) || !BLEAdvertising.start())
    {
        Serial.println("RSSI power-control advertising failed");
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
