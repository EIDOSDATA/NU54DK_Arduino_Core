/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 2대 — 1) LongGattCentral (central/client); 2) LongGattPeripheral (peripheral/server)
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * 없음
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 추가 조건 없음
 * @par Metadata
 * identity `NUCODE_BLE/LongGattPeripheral`, sha256 `dfaf96f2ffa355ca642a41e7a3981f226a9d9222481104482c1f00ea61f77f7d`
 * @nucode_example_setup_end */

/**
 * @file LongGattPeripheral.ino
 * @brief 512-byte characteristic를 광고하는 long read peripheral 예제입니다.
 */

#include <NUCODE_BLE.h>

const nucode::ble::BLEUuid serviceUuid("8e7e2901-7d8c-4c1a-9d2d-8b6519f77410");
const nucode::ble::BLEUuid valueUuid("8e7e2902-7d8c-4c1a-9d2d-8b6519f77410");
nucode::ble::BLEService longService(serviceUuid);
nucode::ble::BLECharacteristic longValue(
    valueUuid, nucode::ble::BLEProperty::read, nucode::ble::BLEPermission::read, 512U);
uint8_t payload[512] = {};
bool running = false;

/** @brief index만으로 재현 가능한 512-byte 값을 만듭니다. */
void buildPayload()
{
    for (size_t index = 0U; index < sizeof(payload); ++index)
    {
        payload[index] = static_cast<uint8_t>(0xa5U ^ static_cast<uint8_t>(index) ^
                                              static_cast<uint8_t>(index >> 8U));
    }
}

/** @brief BLE 오류와 연결 수명 이벤트를 main thread에서 보고합니다. */
void onBleEvent(const nucode::ble::BLEEventInfo &information, void *context)
{
    static_cast<void>(context);
    if (information.event == nucode::ble::BLEEvent::error)
    {
        Serial.print("BLE error: ");
        Serial.println(BLEDevice.lastDriverError());
    }
    else if (information.event == nucode::ble::BLEEvent::connected)
    {
        Serial.println("long-read central connected");
    }
    else if (information.event == nucode::ble::BLEEvent::disconnected)
    {
        Serial.println("long-read central disconnected");
    }
}

void setup()
{
    Serial.begin(115200);
    buildPayload();
    BLEDevice.onEventInfo(onBleEvent);
    running = longValue.setValue(payload, sizeof(payload)) &&
              longService.addCharacteristic(longValue) && BLEDevice.addService(longService) &&
              BLEDevice.begin("NU54-LONG-P") && BLEAdvertising.clear() &&
              BLEAdvertising.setConnectable(true) && BLEAdvertising.addServiceUuid(serviceUuid) &&
              BLEAdvertising.setScanResponseName(true) && BLEAdvertising.start();
    if (!running)
    {
        Serial.print("long GATT peripheral start failed: ");
        Serial.println(BLEDevice.lastDriverError());
    }
}

void loop()
{
    if (running)
    {
        BLEDevice.poll();
    }
}
