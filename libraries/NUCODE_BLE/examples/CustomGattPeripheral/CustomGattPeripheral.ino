/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: Adaptive capabilities (experimental) (adaptive, 실험적 대안)
 * @par 보드와 역할
 * 2대 — 1) CustomGattCentral (central/client); 2) CustomGattPeripheral (peripheral/server)
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * nucode-build.json
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI `--upload-field probe_id=<UID>`로 명시 선택합니다.
 * @par 추가 조건
 * 추가 조건 없음
 * @par Metadata
 * identity `NUCODE_BLE/CustomGattPeripheral`, sha256 `e44c8bc00c2611000a8630992c90e0470a3f3f65d7d441b7a203a18f81ef8f3b`
 * @nucode_example_setup_end */

/**
 * @file CustomGattPeripheral.ino
 * @brief cached value, write, notify와 indicate를 제공하는 custom GATT 예제입니다.
 */

#include <NUCODE_BLE.h>

const nucode::ble::BLEUuid serviceUuid("9f3c0001-8b7a-4d64-a1b2-001122334455");
const nucode::ble::BLEUuid valueUuid("9f3c0002-8b7a-4d64-a1b2-001122334455");
nucode::ble::BLEService customService(serviceUuid);
nucode::ble::BLECharacteristic
    customValue(valueUuid,
                nucode::ble::BLEProperty::read | nucode::ble::BLEProperty::write |
                    nucode::ble::BLEProperty::write_without_response |
                    nucode::ble::BLEProperty::notify | nucode::ble::BLEProperty::indicate,
                nucode::ble::BLEPermission::read | nucode::ble::BLEPermission::write, 64U);

/** @brief peer write를 main thread에서 cached echo와 notification으로 처리합니다. */
void onCharacteristic(nucode::ble::BLECharacteristic &characteristic,
                      const nucode::ble::BLECharacteristicEventInfo &event, void *context)
{
    static_cast<void>(context);
    if (event.event == nucode::ble::BLECharacteristicEvent::written)
    {
        if (characteristic.notificationSubscribed())
        {
            static_cast<void>(characteristic.notify());
        }
        else if (characteristic.indicationSubscribed())
        {
            static_cast<void>(characteristic.indicate());
        }
    }
}

void setup()
{
    Serial.begin(115200);
    const uint8_t initial[] = {'r', 'e', 'a', 'd', 'y'};
    customValue.onEvent(onCharacteristic);
    if (!customValue.setValue(initial, sizeof(initial)) ||
        !customService.addCharacteristic(customValue) || !BLEDevice.addService(customService) ||
        !BLEDevice.begin("NU54-GATT-P") || !BLEAdvertising.clear() ||
        !BLEAdvertising.addServiceUuid(serviceUuid) || !BLEAdvertising.start())
    {
        Serial.println("custom GATT start failed");
    }
}

void loop()
{
    BLEDevice.poll();
}
