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
 * identity `NUCODE_BLE/RssiPowerControlCentral`, sha256 `fe8656a7f6d22c10d61523d7f1fa94f76f0bdbfb4190d759f761387a0716d9d5`
 * @nucode_example_setup_end */

/**
 * @file RssiPowerControlCentral.ino
 * @brief RSSI를 읽어 application 정책으로 peer 송신 전력 변경을 요청하는 예제입니다.
 */

#include <NUCODE_BLE.h>

bool peerFound = false;
nucode::ble::BLEAddress peerAddress;
nucode::ble::BLEConnectionHandle peerLink;
unsigned long nextSampleAt = 0UL;

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

/** @brief RSSI 정책에 사용할 현재 generation handle을 관리합니다. */
void onBleEvent(const nucode::ble::BLEEventInfo &information, void *context)
{
    static_cast<void>(context);
    if (information.event == nucode::ble::BLEEvent::connected)
    {
        peerLink = information.connection;
        static_cast<void>(BLEConnection.setTransmitPowerReporting(peerLink, false, true));
    }
    else if (information.event == nucode::ble::BLEEvent::disconnected &&
             information.connection == peerLink)
    {
        peerLink = {};
    }
}

void setup()
{
    Serial.begin(115200);
    BLEDevice.onEventInfo(onBleEvent);
    BLEScan.onResult(onScanResult);
    if (!BLEDevice.begin("NU54-RSSI-C") || !BLEScan.clearFilters() ||
        !BLEScan.filterName("NU54-RSSI-P") || !BLEScan.start(true))
    {
        Serial.println("RSSI power-control scan failed");
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
    const unsigned long now = millis();
    if (peerLink.valid() && now >= nextSampleAt)
    {
        nextSampleAt = now + 1000UL;
        std::int8_t rssi = 0;
        if (BLEConnection.readRssi(peerLink, rssi))
        {
            const std::int8_t delta = rssi < -75 ? 3 : (rssi > -45 ? -3 : 0);
            Serial.print("RSSI: ");
            Serial.print(rssi);
            Serial.println(" dBm");
            if (delta != 0)
            {
                static_cast<void>(BLEConnection.requestRemoteTransmitPowerChange(
                    peerLink, nucode::ble::BLETransmitPowerPhy::le_1m, delta));
            }
        }
    }
}
