/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 2대 — 1) Private Beacon Client; 2) Private Beacon Server
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * prj.conf
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 같은 NetKey를 공유한 뒤 Private Beacon과 Private Node Identity 상태를 관찰합니다.
 * @par Metadata
 * identity `NUCODE_BLE_Mesh_Management/MeshPrivateBeaconClient`, sha256 `244f39feb2230090f2e3fc1ab6ea61006b9348c29eac5a4767544673459f3fef`
 * @nucode_example_setup_end */

/**
 * @file MeshPrivateBeaconClient.ino
 * @brief 원격 Private Beacon·Private Proxy·Private Node Identity를 설정합니다.
 */

#include <NUCODE_BLE_Mesh_Management.h>

const nucode::mesh::ManagementTarget privateServer{0x0002U, 0U, 7U};

void setup()
{
    Serial.begin(115200);
    nucode::mesh::Configuration configuration{};
    configuration.role = nucode::mesh::Role::provisioner;
    configuration.uuid[0] = 0x54U;
    configuration.uuid[1] = 0x29U;
    if (!NUCODEMesh.begin(configuration) || !NUCODEMeshManagement.begin())
    {
        Serial.println("Private Beacon client start failed");
        return;
    }
    if (NUCODEMesh.provisioned() &&
        (!NUCODEMeshManagement.setPrivateBeacon(privateServer, true, 6U) ||
         !NUCODEMeshManagement.setPrivateGattProxy(privateServer, true) ||
         !NUCODEMeshManagement.setPrivateNodeIdentity(privateServer, 0U, true)))
    {
        Serial.println("Private state update failed");
    }
}

void loop()
{
    NUCODEMesh.poll();
    NUCODEMeshManagement.poll();
}
