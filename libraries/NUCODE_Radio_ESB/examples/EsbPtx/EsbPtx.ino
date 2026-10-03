/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: Standalone Enhanced ShockBurst radio (`radio_esb`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 2대 — 1) ESB PTX; 2) ESB PRX
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * prj.conf
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 두 보드의 channel, bitrate, pipe를 같게 설정하고 ACK/attempt 통계를 확인합니다.
 * @par Metadata
 * identity `NUCODE_Radio_ESB/EsbPtx`, sha256 `7c28df80a5878dfdf4924bae733f15aaf60da6ddcdf120c2b40d10894560e244`
 * @nucode_example_setup_end */

/**
 * @file EsbPtx.ino
 * @brief ESB hardware ACK와 재전송 횟수를 확인하는 PTX 예제입니다.
 */

#include <NUCODE_Radio_ESB.h>

std::uint32_t sequence = 0U;

void setup()
{
    Serial.begin(115200);
    nucode::esb::Configuration configuration{};
    configuration.channel = 40U;
    configuration.bitrate = nucode::esb::Bitrate::mbps2;
    configuration.retransmit_count = 3U;
    if (!NUCODEEsb.begin(nucode::esb::Role::primary_transmitter, configuration))
    {
        Serial.println("ESB PTX start failed");
        return;
    }
    Serial.println("M32-ESB-01 PTX ready");
}

void loop()
{
    static const std::uint8_t payload[] = {'N', 'U', '5', '4', 'D', 'K'};
    if (!NUCODEEsb.busy())
    {
        if (!NUCODEEsb.send(sequence, payload, sizeof(payload)))
        {
            Serial.println("ESB PTX submit failed");
        }
        ++sequence;
    }
    if (sequence != 0U && sequence % 100U == 0U)
    {
        const nucode::esb::Statistics statistics = NUCODEEsb.statistics();
        Serial.print("requested=");
        Serial.print(statistics.tx_requested);
        Serial.print(" acked=");
        Serial.print(statistics.tx_acknowledged);
        Serial.print(" attempts=");
        Serial.println(statistics.tx_attempts);
    }
    delay(100);
}
