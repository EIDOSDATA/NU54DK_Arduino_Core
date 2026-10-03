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
 * centralIdentity를 실제 central identity 주소로 바꿉니다.
 * @par Metadata
 * identity `NUCODE_BLE/DirectedAdvertisingPeripheral`, sha256 `8f0aab6166c64e31a28b568d8c0e9a02e6097fe2ed04030bdbfec4264d36973d`
 * @nucode_example_setup_end */

/**
 * @file DirectedAdvertisingPeripheral.ino
 * @brief 지정 central identity에 low-duty directed advertising을 실행합니다.
 */

#include <NUCODE_BLE.h>

nucode::ble::BLEAdvertisingSetHandle advertisingSet;
bool restartAdvertising = false;
const nucode::ble::BLEAddress centralIdentity(
    "C0:DE:00:00:00:01", nucode::ble::BLEAddress::Type::random_address);

/** @brief 연결 종료 뒤 같은 directed peer를 대상으로 advertising을 재개합니다. */
void onBleEvent(nucode::ble::BLEEvent event, void *context)
{
    static_cast<void>(context);
    if (event == nucode::ble::BLEEvent::disconnected)
    {
        restartAdvertising = true;
    }
}

void setup()
{
    Serial.begin(115200);
    BLEDevice.onEvent(onBleEvent);
    nucode::ble::BLEExtendedAdvertisingParameters parameters;
    parameters.connectable = true;
    parameters.directed_low_duty = true;
    parameters.directed_peer_uses_rpa = true;
    parameters.directed_peer = centralIdentity;
    if (!BLEDevice.begin("NU54-DIRECT-P") ||
        !BLEExtendedAdvertising.create(parameters, advertisingSet) ||
        !BLEExtendedAdvertising.start(advertisingSet))
    {
        Serial.println("directed advertising failed");
    }
}

void loop()
{
    BLEDevice.poll();
    if (restartAdvertising && !BLEConnection.connected())
    {
        restartAdvertising = false;
        if (!BLEExtendedAdvertising.start(advertisingSet))
        {
            Serial.println("directed advertising restart failed");
        }
    }
}
