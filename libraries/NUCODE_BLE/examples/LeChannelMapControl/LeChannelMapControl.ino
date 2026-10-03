/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 1대 — 1) LeChannelMapControl (Host classifier)
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * 없음
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 연속 적용 간격은 Bluetooth controller 규칙에 따라 최소 1초입니다.
 * @par Metadata
 * identity `NUCODE_BLE/LeChannelMapControl`, sha256 `e961329539a0d17c61f470ef8f5a621250bf5e629e41faffacc23409aa95114c`
 * @nucode_example_setup_end */

/**
 * @file LeChannelMapControl.ino
 * @brief Host channel classification을 검증해 controller에 적용합니다.
 */

#include <NUCODE_BLE.h>

void setup()
{
    Serial.begin(115200);
    if (!BLEDevice.begin("NU54-CHAN"))
    {
        Serial.println("BLE start failed");
        return;
    }
    const std::uint8_t all_channels[5] = {0xffU, 0xffU, 0xffU, 0xffU, 0x1fU};
    if (BLEConnection.setChannelClassification(all_channels))
    {
        Serial.println("37-channel classification applied");
    }
    else
    {
        Serial.println("Channel classification failed");
    }
}

void loop()
{
    BLEDevice.poll();
}
