/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 2대 — 1) ConnectionSubratingCentral (central/requester); 2) ConnectionSubratingPeripheral (peripheral/responder)
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * 없음
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 추가 조건 없음
 * @par Metadata
 * identity `NUCODE_BLE/ConnectionSubratingCentral`, sha256 `dde340b1c6627d8158fd34b98bcc4075a5d3a6f6a1a2b0feaac8b9fa30e91f81`
 * @nucode_example_setup_end */

/**
 * @file ConnectionSubratingCentral.ino
 * @brief 연결 후 표준 Connection Subrating을 요청하고 협상 결과를 출력합니다.
 */

#include <NUCODE_BLE.h>

bool peerFound = false;
nucode::ble::BLEAddress peerAddress;

/** @brief 이름이 일치한 peripheral 주소를 보존합니다. */
void onScanResult(const nucode::ble::BLEScanResult &result, void *context)
{
    static_cast<void>(context);
    if (!peerFound)
    {
        peerAddress = result.address;
        peerFound = true;
    }
}

/** @brief link별 Subrating 요청과 결과 조회를 처리합니다. */
void onBleEvent(const nucode::ble::BLEEventInfo &information, void *context)
{
    static_cast<void>(context);
    if (information.event == nucode::ble::BLEEvent::connected)
    {
        nucode::ble::BLESubrateParameters parameters;
        parameters.minimum_factor = 2U;
        parameters.maximum_factor = 8U;
        parameters.continuation_number = 1U;
        if (!BLEConnection.requestSubrate(information.connection, parameters))
        {
            Serial.println("Subrating request failed");
        }
    }
    else if (information.event == nucode::ble::BLEEvent::subrate_changed)
    {
        nucode::ble::BLESubrateInfo result;
        if (BLEConnection.subrate(information.connection, result))
        {
            Serial.print("Subrate factor: ");
            Serial.println(result.factor);
        }
    }
}

void setup()
{
    Serial.begin(115200);
    BLEDevice.onEventInfo(onBleEvent);
    BLEScan.onResult(onScanResult);
    nucode::ble::BLESubrateParameters defaults;
    if (!BLEDevice.begin("NU54-SUB-C") ||
        !BLEConnection.setDefaultSubrate(defaults) ||
        !BLEScan.clearFilters() || !BLEScan.filterName("NU54-SUB-P") ||
        !BLEScan.start(true))
    {
        Serial.println("Subrating central start failed");
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
