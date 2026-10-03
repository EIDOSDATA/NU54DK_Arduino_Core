/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE + ESB coexistence candidate (`coexistence_ble_esb`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 3대 — 1) BLE + ESB coexistence PRX; 2) ESB PTX; 3) BLE NUS central
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * prj.conf
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * ESB standalone HIL PASS 뒤 candidate profile을 사용하고 두 ESB 역할의 channel, bitrate, pipe를 같게 설정합니다.
 * @par Metadata
 * identity `NUCODE_Radio_Coexistence/BleEsbCoexistence`, sha256 `2a5ed8d93244136fb0ddcd9e0ca7454c53f00a288ebe3f7f2eea4764b6524015`
 * @nucode_example_setup_end */

/**
 * @file BleEsbCoexistence.ino
 * @brief BLE NUS peripheral과 ESB PRX를 MPSL timeslot에서 함께 실행합니다.
 */

#include <NUCODE_BLE.h>
#include <NUCODE_Radio_Coexistence.h>
#include <NUCODE_Radio_ESB.h>

using nucode::coexistence::Protocol;

uint32_t bleSequence = 0U;
uint32_t lastBleServiceMs = 0U;
uint32_t lastTimeslotFailures = 0U;
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
    Serial.print(" timeslot_failures=");
    Serial.print(statistics.timeslot_failures);
    Serial.print(" starvation_events=");
    Serial.print(statistics.starvation_events);
    Serial.print(" maximum_service_gap_ms=");
    Serial.println(statistics.maximum_service_gap_ms);
}

void setup()
{
    Serial.begin(115200);
    static_cast<void>(NUCODECoexistence.begin(500U));

    if (!BLESerial.beginPeripheral("NU54-COEX-ESB") || !BLESerial.startAdvertising())
    {
        Serial.println("BLE start failed");
    }
    else
    {
        NUCODECoexistence.setActive(Protocol::ble, true);
    }

    nucode::esb::Configuration configuration{};
    if (!NUCODEEsb.begin(nucode::esb::Role::primary_receiver, configuration))
    {
        Serial.println("ESB start failed");
    }
    else
    {
        NUCODECoexistence.setActive(Protocol::esb, true);
    }
}

void loop()
{
    BLESerial.poll();
    nucode::esb::Packet packet{};
    while (NUCODEEsb.read(packet))
    {
        NUCODECoexistence.recordRequested(Protocol::esb);
        NUCODECoexistence.recordDelivered(Protocol::esb, packet.sequence,
                                          packet.sequence ^ 0xE5B0U, packet.hash_valid);
    }

    const nucode::esb::Statistics esbStatistics = NUCODEEsb.statistics();
    while (lastTimeslotFailures < esbStatistics.timeslot_failures)
    {
        NUCODECoexistence.recordTimeslotFailure(Protocol::esb);
        ++lastTimeslotFailures;
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
        printCoexistenceStatistics("esb", Protocol::esb);
    }
}
