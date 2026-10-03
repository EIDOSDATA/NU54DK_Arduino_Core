/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: Standalone Enhanced ShockBurst radio (`radio_esb`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 2대 — 1) ESB PRX; 2) ESB PTX
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * prj.conf
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 두 보드의 channel, bitrate, pipe를 같게 설정하고 PRX를 먼저 시작합니다.
 * @par Metadata
 * identity `NUCODE_Radio_ESB/EsbPrx`, sha256 `fe98b15c75ac5b479daee84f4ffc14ed14808e753e7d8fde7ce1385a98036448`
 * @nucode_example_setup_end */

/**
 * @file EsbPrx.ino
 * @brief ESB PRX 수신 sequence/hash/중복과 ACK payload를 확인하는 예제입니다.
 */

#include <NUCODE_Radio_ESB.h>

void setup()
{
    Serial.begin(115200);
    nucode::esb::Configuration configuration{};
    configuration.channel = 40U;
    configuration.bitrate = nucode::esb::Bitrate::mbps2;
    if (!NUCODEEsb.begin(nucode::esb::Role::primary_receiver, configuration))
    {
        Serial.println("ESB PRX start failed");
        return;
    }
    static const std::uint8_t ack_payload[] = {'A', 'C', 'K'};
    static_cast<void>(NUCODEEsb.send(0U, ack_payload, sizeof(ack_payload)));
    Serial.println("M32-ESB-01 PRX ready");
}

void loop()
{
    nucode::esb::Packet packet{};
    while (NUCODEEsb.read(packet))
    {
        Serial.print("sequence=");
        Serial.print(packet.sequence);
        Serial.print(" hash=");
        Serial.print(packet.hash_valid ? "ok" : "bad");
        Serial.print(" duplicate=");
        Serial.println(packet.duplicate ? "yes" : "no");
        static const std::uint8_t ack_payload[] = {'A', 'C', 'K'};
        static_cast<void>(NUCODEEsb.send(packet.sequence, ack_payload, sizeof(ack_payload)));
    }
    delay(5);
}
