/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 2대 — 1) Private Beacon Server; 2) Private Beacon Client
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * prj.conf
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * settings 복원 뒤 privacy 상태와 random refresh interval을 다시 조회합니다.
 * @par Metadata
 * identity `NUCODE_BLE_Mesh_Management/MeshPrivateBeaconServer`, sha256 `37e180d01e90bfe3827bc8bfb72f2d907dc90f6e82a774e43b73bd2fdff8fd07`
 * @nucode_example_setup_end */

/**
 * @file MeshPrivateBeaconServer.ino
 * @brief Private Beacon Server와 privacy 상태 저장을 제공합니다.
 */

#include <NUCODE_BLE_Mesh_Management.h>

void setup()
{
    Serial.begin(115200);
    nucode::mesh::Configuration configuration{};
    configuration.uuid[0] = 0x54U;
    configuration.uuid[1] = 0x2AU;
    if (!NUCODEMesh.begin(configuration) || !NUCODEMeshManagement.begin())
    {
        Serial.println("Private Beacon server start failed");
        return;
    }
    Serial.println("Private Beacon Server ready");
}

void loop()
{
    NUCODEMesh.poll();
    NUCODEMeshManagement.poll();
}
