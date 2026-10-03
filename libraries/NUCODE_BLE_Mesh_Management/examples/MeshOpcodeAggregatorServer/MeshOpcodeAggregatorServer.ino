/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 2대 — 1) Opcodes Aggregator Server; 2) Opcodes Aggregator Client
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * prj.conf
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * client sequence의 element address와 server primary element를 일치시킵니다.
 * @par Metadata
 * identity `NUCODE_BLE_Mesh_Management/MeshOpcodeAggregatorServer`, sha256 `cf2ec519781b153e459c54d8c4b52cd7b969ff4feec1356dc2e2f91d8cbf081c`
 * @nucode_example_setup_end */

/**
 * @file MeshOpcodeAggregatorServer.ino
 * @brief Opcodes Aggregator Server와 대상 SIG model을 제공합니다.
 */

#include <NUCODE_BLE_Mesh_Management.h>

void setup()
{
    Serial.begin(115200);
    nucode::mesh::Configuration configuration{};
    configuration.uuid[0] = 0x54U;
    configuration.uuid[1] = 0x26U;
    if (!NUCODEMesh.begin(configuration) || !NUCODEMeshManagement.begin())
    {
        Serial.println("Opcode Aggregator server start failed");
        return;
    }
    Serial.println("Opcode Aggregator Server ready");
}

void loop()
{
    NUCODEMesh.poll();
    NUCODEMeshManagement.poll();
}
