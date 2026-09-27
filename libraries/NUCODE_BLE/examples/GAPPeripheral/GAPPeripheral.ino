/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 2대 — 1) GAPCentral (central/client); 2) GAPPeripheral (peripheral/server)
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * 없음
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 추가 조건 없음
 * @par Metadata
 * identity `NUCODE_BLE/GAPPeripheral`, sha256 `1935a91e9339d58db9c524a45a3a04fe7e2657ca6b0100b5f3d073e9c87ac51b`
 * @nucode_example_setup_end */

/**
 * @file GAPPeripheral.ino
 * @brief 이름·UUID·manufacturer data를 포함한 connectable 광고 예제입니다.
 */

#include <NUCODE_BLE.h>

const nucode::ble::BLEUuid advertisedService(0x180fU);
bool restartAdvertising = false;

/** @brief BLEDevice.poll()의 Arduino main-thread event를 처리합니다. */
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

    const uint8_t productData[] = {0x19U, 0x01U};
    if (!BLEDevice.begin("NU54-GAP-P") || !BLEAdvertising.clear() ||
        !BLEAdvertising.setConnectable(true) || !BLEAdvertising.setInterval(0x00a0U, 0x00f0U) ||
        !BLEAdvertising.addServiceUuid(advertisedService) ||
        !BLEAdvertising.setManufacturerData(0x0059U, productData, sizeof(productData)) ||
        !BLEAdvertising.start())
    {
        Serial.println("BLE GAP start failed");
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
