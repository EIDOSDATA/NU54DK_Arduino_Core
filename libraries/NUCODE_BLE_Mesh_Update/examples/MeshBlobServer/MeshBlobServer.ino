/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: Secure BLE DFU (MCUboot) (`secure_ble_dfu`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 2대 — 1) BLOB Server; 2) BLOB Client
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * prj.conf
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 송수신 BLOB ID를 맞추고 push·pull, cancel, peer loss 뒤 resume를 각각 확인합니다.
 * @par Metadata
 * identity `NUCODE_BLE_Mesh_Update/MeshBlobServer`, sha256 `40c0f1b4e190a4ae0ab0829a52f1538c931947f6a9b694170a4ef51b26fcaf83`
 * @nucode_example_setup_end */

/**
 * @file MeshBlobServer.ino
 * @brief push 또는 pull BLOB을 inactive slot에 받아 중단·재개 상태를 보존합니다.
 */

#include <NUCODE_BLE_Mesh_Update.h>

void setup()
{
    Serial.begin(115200);
    nucode::mesh::Configuration configuration{};
    configuration.role = nucode::mesh::Role::node;
    configuration.uuid[0] = 0x54U;
    configuration.uuid[1] = 0x2FU;
    if (!NUCODEMesh.begin(configuration) || !NUCODEMeshUpdate.begin() ||
        !NUCODEMeshUpdate.prepareBlobReceive(0x4E553534424C4F42ULL))
    {
        Serial.println("Mesh BLOB Server start failed");
    }
}

void loop()
{
    NUCODEMesh.poll();
    if (Serial.available() > 0 && Serial.read() == 'x')
    {
        NUCODEMeshUpdate.cancelBlob();
    }
}
