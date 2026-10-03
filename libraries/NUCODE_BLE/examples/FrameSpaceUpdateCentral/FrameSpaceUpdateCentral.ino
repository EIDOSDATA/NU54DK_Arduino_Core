/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 2대 — 1) FrameSpaceUpdateCentral (central/requester); 2) FrameSpaceUpdatePeripheral (peripheral/responder)
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * 없음
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 추가 조건 없음
 * @par Metadata
 * identity `NUCODE_BLE/FrameSpaceUpdateCentral`, sha256 `dee8f89554e7645bd269b9bcce15bf1ac4ecc1fad1d9c2efc2aabeb5d96821b1`
 * @nucode_example_setup_end */

/**
 * @file FrameSpaceUpdateCentral.ino
 * @brief LE 2M ACL frame spacing 범위를 요청하고 실제 결과를 출력합니다.
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

/** @brief PHY 전환 뒤 frame spacing 요청과 결과 조회를 처리합니다. */
void onBleEvent(const nucode::ble::BLEEventInfo &information, void *context)
{
    static_cast<void>(context);
    if (information.event == nucode::ble::BLEEvent::connected)
    {
        nucode::ble::BLEFrameSpaceParameters parameters;
        parameters.minimum_us = 0U;
        parameters.maximum_us = 150U;
        if (!BLEConnection.requestPhy(information.connection, true) ||
            !BLEConnection.requestFrameSpace(information.connection, parameters))
        {
            Serial.println("Frame Space request failed");
        }
    }
    else if (information.event == nucode::ble::BLEEvent::frame_space_changed)
    {
        nucode::ble::BLEFrameSpaceInfo result;
        if (BLEConnection.frameSpace(information.connection, result))
        {
            Serial.print("Frame spacing: ");
            Serial.print(result.frame_space_us);
            Serial.println(" us");
        }
    }
}

void setup()
{
    Serial.begin(115200);
    BLEDevice.onEventInfo(onBleEvent);
    BLEScan.onResult(onScanResult);
    if (!BLEDevice.begin("NU54-FSU-C") || !BLEScan.clearFilters() ||
        !BLEScan.filterName("NU54-FSU-P") || !BLEScan.start(true))
    {
        Serial.println("Frame Space central start failed");
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
