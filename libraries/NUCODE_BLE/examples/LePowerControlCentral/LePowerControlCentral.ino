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
 * identity `NUCODE_BLE/LePowerControlCentral`, sha256 `ee34b9e2a46f71e4eff372c97bce216be25135ea6122d200b1f120af732c3afc`
 * @nucode_example_setup_end */

/**
 * @file LePowerControlCentral.ino
 * @brief 표준 LE Power Control 요청과 송신 전력 report를 확인하는 Central 예제입니다.
 */

#include <NUCODE_BLE.h>

bool peerFound = false;
nucode::ble::BLEAddress peerAddress;
nucode::ble::BLEConnectionHandle peerLink;

/** @brief 이름 filter를 통과한 peer 주소를 main thread에 보존합니다. */
void onScanResult(const nucode::ble::BLEScanResult &result, void *context)
{
    static_cast<void>(context);
    if (!peerFound)
    {
        peerAddress = result.address;
        peerFound = true;
    }
}

/** @brief link별 표준 송신 전력 절차와 복사된 report를 처리합니다. */
void onBleEvent(const nucode::ble::BLEEventInfo &information, void *context)
{
    static_cast<void>(context);
    if (information.event == nucode::ble::BLEEvent::connected)
    {
        peerLink = information.connection;
        nucode::ble::BLETransmitPowerLevel local;
        if (!BLEConnection.setTransmitPowerReporting(peerLink, true, true) ||
            !BLEConnection.localTransmitPower(
                peerLink, nucode::ble::BLETransmitPowerPhy::le_1m, local) ||
            !BLEConnection.requestRemoteTransmitPower(
                peerLink, nucode::ble::BLETransmitPowerPhy::le_1m))
        {
            Serial.println("LE power control setup failed");
        }
        else
        {
            Serial.print("Local TX power: ");
            Serial.print(local.current_dbm);
            Serial.println(" dBm");
        }
    }
    else if (information.event == nucode::ble::BLEEvent::transmit_power_report)
    {
        Serial.print("Reported TX power: ");
        Serial.print(information.transmit_power.level_dbm);
        Serial.print(" dBm, delta: ");
        Serial.println(information.transmit_power.delta_db);
    }
    else if (information.event == nucode::ble::BLEEvent::disconnected)
    {
        peerLink = {};
    }
}

void setup()
{
    Serial.begin(115200);
    BLEDevice.onEventInfo(onBleEvent);
    BLEScan.onResult(onScanResult);
    if (!BLEDevice.begin("NU54-PWR-C") || !BLEScan.clearFilters() ||
        !BLEScan.filterName("NU54-PWR-P") || !BLEScan.start(true))
    {
        Serial.println("LE power control scan failed");
    }
}

void loop()
{
    BLEDevice.poll();
    if (peerFound && !BLEConnection.connected() && !BLEConnection.connecting())
    {
        peerFound = false;
        static_cast<void>(BLEConnection.connect(peerAddress));
    }
}
