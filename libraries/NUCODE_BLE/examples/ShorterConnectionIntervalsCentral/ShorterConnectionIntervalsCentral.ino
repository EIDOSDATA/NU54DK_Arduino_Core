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
 * identity `NUCODE_BLE/ShorterConnectionIntervalsCentral`, sha256 `0f474db6f290b06898ed91d1aa2ff350e420ddc5e2876a057f2b447b1ed8686f`
 * @nucode_example_setup_end */

/**
 * @file ShorterConnectionIntervalsCentral.ino
 * @brief 125 us 단위의 표준 Shorter Connection Interval을 요청합니다.
 */

#include <NUCODE_BLE.h>

bool peerFound = false;
nucode::ble::BLEAddress peerAddress;

/** @brief 이름이 일치한 peer 주소를 보존합니다. */
void onScanResult(const nucode::ble::BLEScanResult &result, void *context)
{
    static_cast<void>(context);
    if (!peerFound)
    {
        peerAddress = result.address;
        peerFound = true;
    }
}

/** @brief 연결 rate를 요청하고 controller가 보고한 실제 interval을 출력합니다. */
void onBleEvent(const nucode::ble::BLEEventInfo &information, void *context)
{
    static_cast<void>(context);
    if (information.event == nucode::ble::BLEEvent::connected)
    {
        nucode::ble::BLEConnectionRateParameters parameters;
        parameters.interval_minimum_125us = 6U;
        parameters.interval_maximum_125us = 8U;
        if (!BLEConnection.requestConnectionRate(information.connection, parameters))
        {
            Serial.println("Connection Rate request failed");
        }
    }
    else if (information.event == nucode::ble::BLEEvent::connection_rate_changed)
    {
        nucode::ble::BLEConnectionRateInfo result;
        if (BLEConnection.connectionRate(information.connection, result))
        {
            Serial.print("Connection interval: ");
            Serial.print(result.interval_us);
            Serial.println(" us");
        }
    }
}

void setup()
{
    Serial.begin(115200);
    BLEDevice.onEventInfo(onBleEvent);
    BLEScan.onResult(onScanResult);
    nucode::ble::BLEConnectionRateParameters defaults;
    if (!BLEDevice.begin("NU54-SCI-C") ||
        !BLEConnection.setDefaultConnectionRate(defaults) ||
        !BLEScan.clearFilters() || !BLEScan.filterName("NU54-SCI-P") ||
        !BLEScan.start(true))
    {
        Serial.println("Shorter interval central start failed");
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
