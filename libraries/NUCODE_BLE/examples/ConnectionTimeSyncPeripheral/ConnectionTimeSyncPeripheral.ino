/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 2대 — 1) ConnectionTimeSyncCentral (central); 2) ConnectionTimeSyncPeripheral (peripheral)
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * prj.conf
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 두 controller clock domain을 직접 동일시하지 말고 application transport로 기준 anchor를 교환합니다.
 * @par Metadata
 * identity `NUCODE_BLE/ConnectionTimeSyncPeripheral`, sha256 `6201b63338d7a1bce82e74869cae14c280bfe8a1c03eb6ba30a191cea193116c`
 * @nucode_example_setup_end */

/**
 * @file ConnectionTimeSyncPeripheral.ino
 * @brief peripheral controller clock의 수신 anchor point를 출력합니다.
 */

#include <NUCODE_BLE.h>

#include <stdio.h>

/** @brief packet이 수신된 peripheral event의 controller timestamp를 출력합니다. */
void onAnchor(const nucode::ble::BLENordicAnchorPointReport &report, void *context)
{
    static_cast<void>(context);
    char message[80] = {};
    snprintf(message, sizeof(message), "Peripheral anchor event/time us: %u/%llu",
             report.event_counter,
             static_cast<unsigned long long>(report.controller_clock_us));
    Serial.println(message);
}

void setup()
{
    Serial.begin(115200);
    BLENordic.onAnchorPoint(onAnchor);
    if (!BLEDevice.begin("NU54-SYNC-P") ||
        !BLENordic.setAnchorPointReports(true) ||
        !BLEAdvertising.setScanResponseName(true) || !BLEAdvertising.start())
    {
        Serial.println("Time sync peripheral start failed");
    }
}

void loop()
{
    BLEDevice.poll();
}
