/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 3대 — 1) Remote Provisioning Client; 2) Remote Provisioning Server; 3) unprovisioned node
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * prj.conf
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * server를 주소 0x0002로 먼저 provisioning한 뒤 scan을 시작합니다.
 * @par Metadata
 * identity `NUCODE_BLE_Mesh_Management/MeshRemoteProvisioner`, sha256 `419784e92d2b0ee29bd7e4f5fab9ca98ebd0514a5391d69c94b4647644f28d59`
 * @nucode_example_setup_end */

/**
 * @file MeshRemoteProvisioner.ino
 * @brief Remote Provisioning Server를 통해 새 node를 scan하고 provisioning합니다.
 */

#include <NUCODE_BLE_Mesh_Management.h>

const nucode::mesh::ManagementTarget remoteServer{0x0002U, 0U, 7U};
bool provisioning = false;

/** @brief scan report를 main loop에서 PB-Remote provisioning으로 연결합니다. */
void onManagementEvent(const nucode::mesh::ManagementEventRecord &record, void *context)
{
    static_cast<void>(context);
    if (record.event == nucode::mesh::ManagementEvent::remote_device && !provisioning)
    {
        provisioning = NUCODEMeshManagement.provisionRemote(
            record.remote.server, record.remote.uuid, 0U);
        Serial.println(provisioning ? "PB-Remote started" : "PB-Remote failed");
    }
}

void setup()
{
    Serial.begin(115200);
    nucode::mesh::Configuration configuration{};
    configuration.role = nucode::mesh::Role::provisioner;
    configuration.uuid[0] = 0x54U;
    configuration.uuid[1] = 0x21U;
    if (!NUCODEMesh.begin(configuration) || !NUCODEMeshManagement.begin())
    {
        Serial.println("Remote provisioner start failed");
        return;
    }
    NUCODEMeshManagement.onEvent(onManagementEvent);
    if (NUCODEMesh.provisioned() && !NUCODEMeshManagement.startRemoteScan(remoteServer, 20U))
    {
        Serial.println("Remote scan start failed");
    }
}

void loop()
{
    NUCODEMesh.poll();
    NUCODEMeshManagement.poll();
}
