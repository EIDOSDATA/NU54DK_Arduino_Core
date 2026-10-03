/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: Standalone IEEE 802.15.4 radio (`radio_ieee802154`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 2대 — 1) IEEE 802.15.4 transmitter 0x0001; 2) IEEE 802.15.4 receiver 0x0002
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * prj.conf
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 두 보드의 PAN ID와 channel을 같게 설정하고 ACK/retry 통계를 확인합니다.
 * @par Metadata
 * identity `NUCODE_Radio_IEEE802154/Radio154Transmitter`, sha256 `e7a849509442e00672fdb4ac42cef9703ffd4580ceaa09b00802d00560208a40`
 * @nucode_example_setup_end */

/**
 * @file Radio154Transmitter.ino
 * @brief sequence/hash와 MAC ACK를 확인하는 IEEE 802.15.4 송신 예제입니다.
 */

#include <NUCODE_Radio_IEEE802154.h>

std::uint32_t sequence = 0U;

void setup()
{
    Serial.begin(115200);
    nucode::radio154::Configuration configuration{};
    configuration.local_address = 0x0001U;
    configuration.peer_address = 0x0002U;
    configuration.channel = 20U;
    if (!NUCODERadio154.begin(nucode::radio154::Role::transmitter, configuration))
    {
        Serial.println("IEEE 802.15.4 TX start failed");
        return;
    }
    Serial.println("M32-154-01 TX ready");
}

void loop()
{
    static const std::uint8_t payload[] = {'N', 'U', '5', '4', 'D', 'K'};
    if (!NUCODERadio154.busy())
    {
        if (!NUCODERadio154.send(sequence, payload, sizeof(payload)))
        {
            Serial.println("IEEE 802.15.4 TX submit failed");
        }
        ++sequence;
    }
    if (sequence != 0U && sequence % 100U == 0U)
    {
        const nucode::radio154::Statistics statistics = NUCODERadio154.statistics();
        Serial.print("requested=");
        Serial.print(statistics.tx_requested);
        Serial.print(" acked=");
        Serial.print(statistics.tx_acknowledged);
        Serial.print(" retried=");
        Serial.println(statistics.tx_retried);
    }
    delay(100);
}
