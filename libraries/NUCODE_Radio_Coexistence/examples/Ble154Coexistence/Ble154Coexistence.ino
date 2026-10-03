/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE + IEEE 802.15.4 coexistence (`coexistence_ble_154`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 3대 — 1) BLE + IEEE 802.15.4 coexistence receiver; 2) IEEE 802.15.4 transmitter 0x0001; 3) BLE NUS central
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * prj.conf
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * coexistence 보드의 IEEE 802.15.4 주소는 0x0002이며 transmitter와 PAN ID/channel을 같게 설정합니다.
 * @par Metadata
 * identity `NUCODE_Radio_Coexistence/Ble154Coexistence`, sha256 `18201e6de5482ae1ebfa2de825d011e050da64780849aafb752093c0c9f04692`
 * @nucode_example_setup_end */

/**
 * @file Ble154Coexistence.ino
 * @brief BLE NUS peripheral과 IEEE 802.15.4 receiver를 MPSL에서 함께 실행합니다.
 */

#include <NUCODE_BLE.h>
#include <NUCODE_Radio_Coexistence.h>
#include <NUCODE_Radio_IEEE802154.h>

using nucode::coexistence::Protocol;

uint32_t bleSequence = 0U;
uint32_t lastBleServiceMs = 0U;
uint32_t lastReportMs = 0U;

/** @brief 한 protocol의 공존 통계를 사람이 읽을 수 있는 고정 형식으로 출력합니다. */
void printCoexistenceStatistics(const char *name, Protocol protocol)
{
    const nucode::coexistence::ServiceStatistics statistics =
        NUCODECoexistence.statistics(protocol);
    Serial.print("coex protocol=");
    Serial.print(name);
    Serial.print(" requested=");
    Serial.print(statistics.requested);
    Serial.print(" delivered=");
    Serial.print(statistics.delivered);
    Serial.print(" dropped=");
    Serial.print(statistics.dropped);
    Serial.print(" sequence_errors=");
    Serial.print(statistics.sequence_errors);
    Serial.print(" hash_errors=");
    Serial.print(statistics.hash_errors);
    Serial.print(" starvation_events=");
    Serial.print(statistics.starvation_events);
    Serial.print(" maximum_service_gap_ms=");
    Serial.println(statistics.maximum_service_gap_ms);
}

void setup()
{
    Serial.begin(115200);
    static_cast<void>(NUCODECoexistence.begin(500U));

    if (!BLESerial.beginPeripheral("NU54-COEX-154") || !BLESerial.startAdvertising())
    {
        Serial.println("BLE start failed");
    }
    else
    {
        NUCODECoexistence.setActive(Protocol::ble, true);
    }

    nucode::radio154::Configuration configuration{};
    configuration.local_address = 0x0002U;
    configuration.peer_address = 0x0001U;
    if (!NUCODERadio154.begin(nucode::radio154::Role::receiver, configuration))
    {
        Serial.println("IEEE 802.15.4 start failed");
    }
    else
    {
        NUCODECoexistence.setActive(Protocol::ieee802154, true);
    }
}

void loop()
{
    BLESerial.poll();
    nucode::radio154::Packet packet{};
    while (NUCODERadio154.read(packet))
    {
        NUCODECoexistence.recordRequested(Protocol::ieee802154);
        NUCODECoexistence.recordDelivered(Protocol::ieee802154, packet.sequence,
                                          packet.sequence ^ 0x1540U, packet.hash_valid);
    }

    const uint32_t now = millis();
    if (BLESerial.connected() && now - lastBleServiceMs >= 100U)
    {
        lastBleServiceMs = now;
        ++bleSequence;
        NUCODECoexistence.recordRequested(Protocol::ble);
        NUCODECoexistence.recordDelivered(Protocol::ble, bleSequence, bleSequence ^ 0xB1E0U);
    }
    if (now - lastReportMs >= 1000U)
    {
        lastReportMs = now;
        printCoexistenceStatistics("ble", Protocol::ble);
        printCoexistenceStatistics("ieee802154", Protocol::ieee802154);
    }
}
