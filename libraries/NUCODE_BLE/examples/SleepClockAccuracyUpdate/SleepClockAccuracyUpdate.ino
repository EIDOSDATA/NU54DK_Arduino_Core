/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 1대 — 1) SleepClockAccuracyUpdate (support reporter)
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * 없음
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * NCS v3.4.0 고정 Host에는 SCA 요청·완료 report 공개 API가 없어 controller responder 지원만 표시합니다.
 * @par Metadata
 * identity `NUCODE_BLE/SleepClockAccuracyUpdate`, sha256 `e0397c1d75dc82f755e354650db85326ad04dad6cab02183b544ff3c2bc309f1`
 * @nucode_example_setup_end */

/**
 * @file SleepClockAccuracyUpdate.ino
 * @brief 고정 SDK의 controller와 Host SCA Update 지원 경계를 표시합니다.
 */

#include <NUCODE_BLE.h>

void setup()
{
    Serial.begin(115200);
    if (!BLEDevice.begin("NU54-SCA"))
    {
        Serial.println("BLE start failed");
        return;
    }
    const nucode::ble::BLESleepClockAccuracySupport support =
        BLEConnection.sleepClockAccuracySupport();
    Serial.print("Controller SCA procedure: ");
    Serial.println(support.controller_procedure ? "supported" : "unsupported");
    Serial.print("Host request/report API: ");
    Serial.println(support.host_request_and_report ? "supported" : "unavailable");
}

void loop()
{
    BLEDevice.poll();
}
