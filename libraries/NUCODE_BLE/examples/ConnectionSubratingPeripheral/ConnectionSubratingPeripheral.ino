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
 * identity `NUCODE_BLE/ConnectionSubratingPeripheral`, sha256 `68121fce24375a3572f26e20350c4cbd8732f4a0ed06dd8553ae669bad757563`
 * @nucode_example_setup_end */

/**
 * @file ConnectionSubratingPeripheral.ino
 * @brief peer의 Connection Subrating 변경을 수신하는 Peripheral 예제입니다.
 */

#include <NUCODE_BLE.h>

bool restartAdvertising = false;

/** @brief Subrating 결과와 연결 종료를 처리합니다. */
void onBleEvent(const nucode::ble::BLEEventInfo &information, void *context)
{
    static_cast<void>(context);
    if (information.event == nucode::ble::BLEEvent::subrate_changed)
    {
        nucode::ble::BLESubrateInfo result;
        if (BLEConnection.subrate(information.connection, result))
        {
            Serial.print("Peer subrate factor: ");
            Serial.println(result.factor);
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
    if (!BLEDevice.begin("NU54-SUB-P") || !BLEAdvertising.clear() ||
        !BLEAdvertising.setConnectable(true) || !BLEAdvertising.start())
    {
        Serial.println("Subrating peripheral start failed");
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
