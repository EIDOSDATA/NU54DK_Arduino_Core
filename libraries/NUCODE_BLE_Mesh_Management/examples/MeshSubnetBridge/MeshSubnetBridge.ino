/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 3대 — 1) Bridge Configuration Client; 2) Subnet Bridge node; 3) 두 subnet의 source 또는 destination node
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * prj.conf
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * NetKey 0과 1을 배포하고 허용 table 항목 밖의 forwarding은 거부되는지 확인합니다.
 * @par Metadata
 * identity `NUCODE_BLE_Mesh_Management/MeshSubnetBridge`, sha256 `263df7c3811580ff3e87c6345612a17e5d35f5d656074c1ec41352360151bbf1`
 * @nucode_example_setup_end */

/**
 * @file MeshSubnetBridge.ino
 * @brief Subnet Bridge 상태와 허용 forwarding table 항목을 설정합니다.
 */

#include <NUCODE_BLE_Mesh_Management.h>

const nucode::mesh::ManagementTarget bridgeServer{0x0002U, 0U, 7U};

void setup()
{
    Serial.begin(115200);
    nucode::mesh::Configuration configuration{};
    configuration.role = nucode::mesh::Role::provisioner;
    configuration.uuid[0] = 0x54U;
    configuration.uuid[1] = 0x2DU;
    if (!NUCODEMesh.begin(configuration) || !NUCODEMeshManagement.begin())
    {
        Serial.println("Subnet Bridge client start failed");
        return;
    }
    nucode::mesh::BridgeEntry entry{};
    entry.first_net_key_index = 0U;
    entry.second_net_key_index = 1U;
    entry.first_address = 0x0003U;
    entry.second_address = 0x0004U;
    if (NUCODEMesh.provisioned() &&
        (!NUCODEMeshManagement.setSubnetBridge(bridgeServer, true) ||
         !NUCODEMeshManagement.addBridgeEntry(bridgeServer, entry)))
    {
        Serial.println("Subnet Bridge update failed");
    }
}

void loop()
{
    NUCODEMesh.poll();
    NUCODEMeshManagement.poll();
}
