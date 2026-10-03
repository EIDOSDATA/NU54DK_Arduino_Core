/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 2대 — 1) ConnectionRadioNotification (peripheral); 2) 연결 가능한 BLE central
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * prj.conf
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * radio prepare callback은 system workqueue에서 실행되므로 짧고 비차단인 작업만 수행합니다.
 * @par Metadata
 * identity `NUCODE_BLE/ConnectionRadioNotification`, sha256 `c01e12a9ee7bcf70e5894d09c45adf6a5c8479f199524f68a608a77390823a6b`
 * @nucode_example_setup_end */

/**
 * @file ConnectionRadioNotification.ino
 * @brief connection event 전에 system-workqueue radio prepare callback을 관측합니다.
 */

#include <NUCODE_BLE.h>

volatile std::uint32_t prepareCount = 0U;

/**
 * @brief system workqueue에서는 counter만 갱신합니다.
 * @warning Serial, heap, blocking API와 BLE 제어 API를 이 callback에서 호출하지 않습니다.
 */
void onRadioPrepare(nucode::ble::BLEConnectionHandle connection, void *context)
{
    static_cast<void>(connection);
    static_cast<void>(context);
    ++prepareCount;
}

void setup()
{
    Serial.begin(115200);
    BLENordic.onRadioPrepare(onRadioPrepare);
    if (!BLEDevice.begin("NU54-RADIO-NOTIFY") ||
        !BLENordic.setRadioNotification(true) || !BLEAdvertising.start())
    {
        Serial.println("Radio notification start failed");
    }
}

void loop()
{
    BLEDevice.poll();
    static std::uint32_t reported = 0U;
    const std::uint32_t current = prepareCount;
    if (current != reported)
    {
        reported = current;
        Serial.print("Radio prepare callbacks: ");
        Serial.println(reported);
    }
}
