/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 2대 — 1) BleThroughputCentral (central/sender); 2) BleThroughputPeripheral (peripheral/receiver)
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * 없음
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 표시값은 1초 application payload window이며 RF PHY bit rate가 아닙니다.
 * @par Metadata
 * identity `NUCODE_BLE/BleThroughputPeripheral`, sha256 `46ab2ac37b98b9720e27f2a287b4ea0961965803a086091f40f736df4ef42fc0`
 * @nucode_example_setup_end */

/**
 * @file BleThroughputPeripheral.ino
 * @brief NUS 수신 byte를 1초 window로 집계해 throughput을 출력합니다.
 */

#include <NUCODE_BLE.h>

std::uint32_t receivedBytes = 0U;
unsigned long windowStartedAt = 0UL;

/** @brief 연결 직후 throughput용 PHY·DLE·MTU 교환을 요청합니다. */
void onNusEvent(nucode::ble::Event event, void *context)
{
    static_cast<void>(context);
    if (event == nucode::ble::Event::connected)
    {
        const nucode::ble::BLEConnectionHandle connection =
            BLEConnection.handle(nucode::ble::BLELinkRole::peripheral);
        static_cast<void>(BLEConnection.requestPhy(connection, true));
        static_cast<void>(BLEConnection.requestDataLength(connection));
        static_cast<void>(BLEConnection.requestMtu(connection));
    }
    else if (event == nucode::ble::Event::ready)
    {
        windowStartedAt = millis();
    }
}

void setup()
{
    Serial.begin(115200);
    BLESerial.onEvent(onNusEvent);
    if (!BLESerial.beginPeripheral("NU54-THR") || !BLESerial.startAdvertising())
    {
        Serial.println("Throughput peripheral start failed");
    }
}

void loop()
{
    BLESerial.poll();
    while (BLESerial.available() > 0)
    {
        static_cast<void>(BLESerial.read());
        ++receivedBytes;
    }
    const unsigned long now = millis();
    if (windowStartedAt != 0UL && now - windowStartedAt >= 1000UL)
    {
        Serial.print("RX bytes/s: ");
        Serial.println(receivedBytes);
        receivedBytes = 0U;
        windowStartedAt = now;
    }
}
