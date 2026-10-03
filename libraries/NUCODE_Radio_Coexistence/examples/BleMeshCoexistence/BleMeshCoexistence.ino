/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE + Bluetooth Mesh coexistence (`coexistence_ble_mesh`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 3대 — 1) BLE NUS + Mesh coexistence node; 2) Mesh provisioner/peer; 3) BLE NUS central
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * prj.conf
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 저장된 Mesh 상태가 없거나 의도한 topology와 일치해야 하며 Mesh와 BLE event를 개별 판정합니다.
 * @par Metadata
 * identity `NUCODE_Radio_Coexistence/BleMeshCoexistence`, sha256 `52cf802b98e9c6d383f6b63041cc585e93b931e9604a2024c2f7f7d0af61e5af`
 * @nucode_example_setup_end */

/**
 * @file BleMeshCoexistence.ino
 * @brief 한 image에서 BLE NUS peripheral과 Bluetooth Mesh node를 함께 관측합니다.
 */

#include <NUCODE_BLE.h>
#include <NUCODE_BLE_Mesh.h>
#include <NUCODE_Radio_Coexistence.h>

using nucode::coexistence::Protocol;

uint32_t bleSequence = 0U;
uint32_t meshSequence = 0U;
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

/** @brief Mesh event를 sequence/hash 형태의 공존 통계로 기록합니다. */
void onMeshCoexistenceEvent(const nucode::mesh::EventRecord &record, void *context)
{
    static_cast<void>(context);
    ++meshSequence;
    NUCODECoexistence.recordRequested(Protocol::mesh);
    NUCODECoexistence.recordDelivered(Protocol::mesh, meshSequence,
                                      static_cast<uint32_t>(record.address));
}

void setup()
{
    Serial.begin(115200);
    if (!NUCODECoexistence.begin(500U))
    {
        Serial.println("coexistence monitor failed");
        return;
    }

    if (!BLESerial.beginPeripheral("NU54-COEX-MESH") || !BLESerial.startAdvertising())
    {
        Serial.println("BLE start failed");
    }
    else
    {
        NUCODECoexistence.setActive(Protocol::ble, true);
    }

    nucode::mesh::Configuration configuration{};
    configuration.uuid[0] = 0x54U;
    configuration.uuid[1] = 0xC0U;
    configuration.uuid[2] = 0x10U;
    NUCODEMesh.onEvent(onMeshCoexistenceEvent);
    if (!NUCODEMesh.begin(configuration))
    {
        Serial.println("Mesh start failed");
    }
    else
    {
        NUCODECoexistence.setActive(Protocol::mesh, true);
    }
}

void loop()
{
    BLESerial.poll();
    NUCODEMesh.poll();

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
        printCoexistenceStatistics("mesh", Protocol::mesh);
    }
}
