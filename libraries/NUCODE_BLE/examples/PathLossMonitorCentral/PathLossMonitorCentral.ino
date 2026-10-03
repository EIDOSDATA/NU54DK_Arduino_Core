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
 * identity `NUCODE_BLE/PathLossMonitorCentral`, sha256 `88a83a99fdb8ec04d88bdc2e8f6465c094e0cd00fc702650013d086dbb11b198`
 * @nucode_example_setup_end */

/**
 * @file PathLossMonitorCentral.ino
 * @brief 표준 Path Loss threshold 구간 변화를 수신하는 Central 예제입니다.
 */

#include <NUCODE_BLE.h>

bool peerFound = false;
nucode::ble::BLEAddress peerAddress;

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

/** @brief link에 threshold를 적용하고 복사된 zone event를 출력합니다. */
void onBleEvent(const nucode::ble::BLEEventInfo &information, void *context)
{
    static_cast<void>(context);
    if (information.event == nucode::ble::BLEEvent::connected)
    {
        const nucode::ble::BLEPathLossParameters parameters = {
            .high_threshold_db = 60U,
            .high_hysteresis_db = 5U,
            .low_threshold_db = 40U,
            .low_hysteresis_db = 5U,
            .minimum_connection_events = 5U,
        };
        if (!BLEConnection.configurePathLossMonitoring(information.connection,
                                                       parameters) ||
            !BLEConnection.setPathLossMonitoring(information.connection, true))
        {
            Serial.println("Path Loss monitoring setup failed");
        }
    }
    else if (information.event == nucode::ble::BLEEvent::path_loss_changed)
    {
        Serial.print("Path Loss zone: ");
        Serial.print(static_cast<unsigned int>(information.path_loss.zone));
        Serial.print(", loss: ");
        Serial.print(information.path_loss.path_loss_db);
        Serial.println(" dB");
    }
}

void setup()
{
    Serial.begin(115200);
    BLEDevice.onEventInfo(onBleEvent);
    BLEScan.onResult(onScanResult);
    if (!BLEDevice.begin("NU54-PATH-C") || !BLEScan.clearFilters() ||
        !BLEScan.filterName("NU54-PATH-P") || !BLEScan.start(true))
    {
        Serial.println("Path Loss scan failed");
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
