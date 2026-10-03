/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 2대 — 1) Opcodes Aggregator Client; 2) Opcodes Aggregator Server
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * prj.conf
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * AppKey 0을 관리 client와 대상 SIG model에 bind합니다.
 * @par Metadata
 * identity `NUCODE_BLE_Mesh_Management/MeshOpcodeAggregatorClient`, sha256 `6b456aaa72b57cc0cc969ec35620104f2c442ec545edf0b2303dfb80194648d8`
 * @nucode_example_setup_end */

/**
 * @file MeshOpcodeAggregatorClient.ino
 * @brief 여러 SIG model 요청을 한 Opcodes Aggregator sequence로 전송합니다.
 */

#include <NUCODE_BLE_Mesh_Management.h>

const nucode::mesh::ManagementTarget aggregatorServer{0x0002U, 0U, 7U};

void setup()
{
    Serial.begin(115200);
    nucode::mesh::Configuration configuration{};
    configuration.role = nucode::mesh::Role::provisioner;
    configuration.uuid[0] = 0x54U;
    configuration.uuid[1] = 0x25U;
    if (!NUCODEMesh.begin(configuration) || !NUCODEMeshManagement.begin())
    {
        Serial.println("Opcode Aggregator client start failed");
        return;
    }
    if (NUCODEMesh.provisioned())
    {
        nucode::mesh::Destination destination{};
        destination.address = aggregatorServer.address;
        if (!NUCODEMeshManagement.beginOpcodeSequence(aggregatorServer, 0U,
                                                       aggregatorServer.address) ||
            !NUCODEMesh.sendOnOff(destination, true) ||
            !NUCODEMesh.requestTime(destination) ||
            !NUCODEMeshManagement.sendOpcodeSequence())
        {
            NUCODEMeshManagement.abortOpcodeSequence();
            Serial.println("Opcode sequence failed");
        }
    }
}

void loop()
{
    NUCODEMesh.poll();
    NUCODEMeshManagement.poll();
}
