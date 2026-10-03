/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 2대 — 1) DirectedAdvertisingPeripheral (peripheral); 2) DirectedAdvertisingCentral (central)
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * 없음
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * peripheralIdentity를 실제 peripheral identity 주소로 바꿉니다.
 * @par Metadata
 * identity `NUCODE_BLE/DirectedAdvertisingCentral`, sha256 `e4fc14dc8a09f893893d90af807d5b0d83db77c55df83983794873b57a442b58`
 * @nucode_example_setup_end */

/**
 * @file DirectedAdvertisingCentral.ino
 * @brief directed peripheral의 identity 주소로 연결을 시작합니다.
 */

#include <NUCODE_BLE.h>

const nucode::ble::BLEAddress peripheralIdentity(
    "C0:DE:00:00:00:02", nucode::ble::BLEAddress::Type::random_address);
bool reconnectPeer = false;

/** @brief 연결 종료 뒤 저장된 directed peer에 명시적으로 재연결합니다. */
void onBleEvent(nucode::ble::BLEEvent event, void *context)
{
    static_cast<void>(context);
    if (event == nucode::ble::BLEEvent::disconnected)
    {
        reconnectPeer = true;
    }
}

void setup()
{
    Serial.begin(115200);
    BLEDevice.onEvent(onBleEvent);
    if (!BLEDevice.begin("NU54-DIRECT-C") ||
        !BLEConnection.connect(peripheralIdentity))
    {
        Serial.println("directed peer connect failed");
    }
}

void loop()
{
    BLEDevice.poll();
    if (reconnectPeer && !BLEConnection.connected() && !BLEConnection.connecting())
    {
        reconnectPeer = false;
        if (!BLEConnection.reconnect())
        {
            Serial.println("directed peer reconnect failed");
        }
    }
}
