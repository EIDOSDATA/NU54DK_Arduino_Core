/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 2대 — 1) NordicConnectionEventQos 실행 보드; 2) 연결 가능한 BLE peer
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * prj.conf
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * QoS connection event report는 controller 전역 설정이며 active connection이 필요합니다.
 * @par Metadata
 * identity `NUCODE_BLE/NordicConnectionEventQos`, sha256 `bc108198085949a08703bea9e54ae25865c404b0c6ba02e07afcfa25a465af28`
 * @nucode_example_setup_end */

/**
 * @file NordicConnectionEventQos.ino
 * @brief 연결 event별 channel·CRC·NAK·timeout을 Arduino main thread에서 집계합니다.
 */

#include <NUCODE_BLE.h>

std::uint32_t reportCount = 0U;
std::uint32_t crcErrorCount = 0U;

/** @brief bounded QoS 복사본만 main-thread 집계에 사용합니다. */
void onConnectionEvent(const nucode::ble::BLENordicConnectionEventReport &report,
                       void *context)
{
    static_cast<void>(context);
    ++reportCount;
    crcErrorCount += report.crc_error_count;
    if ((reportCount % 100U) == 0U)
    {
        Serial.print("QoS reports/CRC errors: ");
        Serial.print(reportCount);
        Serial.print('/');
        Serial.println(crcErrorCount);
    }
}

void setup()
{
    Serial.begin(115200);
    BLENordic.onConnectionEvent(onConnectionEvent);
    if (!BLEDevice.begin("NU54-QOS") ||
        !BLENordic.setConnectionEventReports(true) ||
        !BLEAdvertising.start())
    {
        Serial.println("QoS report start failed");
    }
}

void loop()
{
    BLEDevice.poll();
}
