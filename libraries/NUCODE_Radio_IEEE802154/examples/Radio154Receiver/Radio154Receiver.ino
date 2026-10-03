/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: Standalone IEEE 802.15.4 radio (`radio_ieee802154`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 2대 — 1) IEEE 802.15.4 receiver 0x0002; 2) IEEE 802.15.4 transmitter 0x0001
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * prj.conf
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 두 보드의 PAN ID와 channel을 같게 설정하고 receiver를 먼저 시작합니다.
 * @par Metadata
 * identity `NUCODE_Radio_IEEE802154/Radio154Receiver`, sha256 `b7e0197ce3ed5ace5d042d129671b74c462dbf68a41c9263dd8a7fa3677a1e4b`
 * @nucode_example_setup_end */

/**
 * @file Radio154Receiver.ino
 * @brief IEEE 802.15.4 수신 sequence/hash/중복을 확인하는 예제입니다.
 */

#include <NUCODE_Radio_IEEE802154.h>

void setup()
{
    Serial.begin(115200);
    nucode::radio154::Configuration configuration{};
    configuration.local_address = 0x0002U;
    configuration.peer_address = 0x0001U;
    configuration.channel = 20U;
    if (!NUCODERadio154.begin(nucode::radio154::Role::receiver, configuration))
    {
        Serial.println("IEEE 802.15.4 RX start failed");
        return;
    }
    Serial.println("M32-154-01 RX ready");
}

void loop()
{
    nucode::radio154::Packet packet{};
    while (NUCODERadio154.read(packet))
    {
        Serial.print("sequence=");
        Serial.print(packet.sequence);
        Serial.print(" hash=");
        Serial.print(packet.hash_valid ? "ok" : "bad");
        Serial.print(" duplicate=");
        Serial.println(packet.duplicate ? "yes" : "no");
    }
    delay(5);
}
