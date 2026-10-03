/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 3대 — 1) Remote Provisioning Server; 2) Remote Provisioning Client; 3) unprovisioned node
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * prj.conf
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * server와 unprovisioned node가 PB-ADV 통신 가능한 위치에 있어야 합니다.
 * @par Metadata
 * identity `NUCODE_BLE_Mesh_Management/MeshRemoteProvisioningServer`, sha256 `0450096de68cc3458420da57e8b4d9d0451f1eeed8a92c9d5d49ae44c9ba3a1d`
 * @nucode_example_setup_end */

/**
 * @file MeshRemoteProvisioningServer.ino
 * @brief provisioned node에서 Remote Provisioning Server model을 제공합니다.
 */

#include <NUCODE_BLE_Mesh_Management.h>

void setup()
{
    Serial.begin(115200);
    nucode::mesh::Configuration configuration{};
    configuration.uuid[0] = 0x54U;
    configuration.uuid[1] = 0x22U;
    if (!NUCODEMesh.begin(configuration) || !NUCODEMeshManagement.begin())
    {
        Serial.println("Remote provisioning server start failed");
        return;
    }
    Serial.println("Remote Provisioning Server ready");
}

void loop()
{
    NUCODEMesh.poll();
    NUCODEMeshManagement.poll();
}
