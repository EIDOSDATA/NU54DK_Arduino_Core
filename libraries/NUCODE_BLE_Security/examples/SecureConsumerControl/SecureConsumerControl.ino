/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 1대 — 1) SecureConsumerControl 실행 보드
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * 없음
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 동작에 필요한 compatible BLE peer 또는 mobile/host client를 별도로 준비합니다.
 * @par Metadata
 * identity `NUCODE_BLE_Security/SecureConsumerControl`, sha256 `db37b86fce1a2f9428f6e8d6fca3b6cd6014e5d5e255e82ecbe88accaff00654`
 * @nucode_example_setup_end */

/**
 * @file SecureConsumerControl.ino
 * @brief 암호화된 표준 BLE HID consumer-control report를 보냅니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE_Security.h>

namespace
{

    constexpr std::uint16_t volume_increment_usage = 0x00e9U;

    /** @brief 실패 단계를 출력하고 안전하게 정지합니다. */
    void require(bool condition, const char *stage)
    {
        if (condition)
        {
            return;
        }
        Serial.print("SecureConsumerControl start failed: ");
        Serial.println(stage);
        while (true)
        {
            delay(1000);
        }
    }

} // namespace

void setup()
{
    Serial.begin(115200);
    const nucode::ble::SecurityConfig security = {nucode::ble::SecurityLevel::encrypted, true,
                                                  30000U};
    require(BLESecurity.begin(security), "security");
    require(BLEConsumerControl.begin(), "consumer-control");
    require(BLEDevice.begin("NU54-Consumer-Control"), "device");
    require(BLEAdvertising.clear(), "advertising-clear");
    require(BLEAdvertising.setConnectable(true), "advertising-connectable");
    require(BLEAdvertising.addServiceUuid(nucode::ble::BLEUuid(0x1812U)), "advertising-hids");
    require(BLEAdvertising.setScanResponseName(true), "advertising-name");
    require(BLEAdvertising.start(), "advertising-start");
}

void loop()
{
    BLEDevice.poll();
    BLESecurity.poll();
    if (BLEConsumerControl.connected())
    {
        static_cast<void>(BLEConsumerControl.press(volume_increment_usage));
        delay(20);
        static_cast<void>(BLEConsumerControl.release());
        delay(980);
    }
    else
    {
        delay(10);
    }
}
