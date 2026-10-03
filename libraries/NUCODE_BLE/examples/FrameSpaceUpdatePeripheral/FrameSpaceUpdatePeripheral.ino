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
 * identity `NUCODE_BLE/FrameSpaceUpdatePeripheral`, sha256 `b3d1256f8375609716f18fa025764db26488dfc8645958778ae84244a7356c5b`
 * @nucode_example_setup_end */

/**
 * @file FrameSpaceUpdatePeripheral.ino
 * @brief controller 또는 peer가 적용한 Frame Space Update를 관측합니다.
 */

#include <NUCODE_BLE.h>

bool restartAdvertising = false;

/** @brief Frame Space 결과와 연결 종료를 처리합니다. */
void onBleEvent(const nucode::ble::BLEEventInfo &information, void *context)
{
    static_cast<void>(context);
    if (information.event == nucode::ble::BLEEvent::frame_space_changed)
    {
        nucode::ble::BLEFrameSpaceInfo result;
        if (BLEConnection.frameSpace(information.connection, result))
        {
            Serial.print("Frame spacing: ");
            Serial.print(result.frame_space_us);
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
    if (!BLEDevice.begin("NU54-FSU-P") || !BLEAdvertising.clear() ||
        !BLEAdvertising.setConnectable(true) || !BLEAdvertising.start())
    {
        Serial.println("Frame Space peripheral start failed");
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
