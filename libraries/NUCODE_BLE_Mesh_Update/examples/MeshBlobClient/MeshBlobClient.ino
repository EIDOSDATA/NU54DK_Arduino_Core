/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: Secure BLE DFU (MCUboot) (`secure_ble_dfu`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 3대 — 1) BLOB Client; 2) BLOB Server target 0x0002; 3) BLOB Server target 0x0003
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * prj.conf
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * M30 signing key로 생성한 inactive-slot image를 먼저 staging하고 BLOB ID·크기를 일치시킵니다.
 * @par Metadata
 * identity `NUCODE_BLE_Mesh_Update/MeshBlobClient`, sha256 `1f983422d4a516ea5fb992981e55192befcbe5b71f75b68de28f5f693e42bad6`
 * @nucode_example_setup_end */

/**
 * @file MeshBlobClient.ino
 * @brief inactive slot의 BLOB을 두 target에 push mode로 전송합니다.
 */

#include <NUCODE_BLE_Mesh_Update.h>

const nucode::mesh::BlobTarget blobTargets[] = {{0x0002U}, {0x0003U}};

void setup()
{
    Serial.begin(115200);
    nucode::mesh::Configuration configuration{};
    configuration.role = nucode::mesh::Role::provisioner;
    configuration.uuid[0] = 0x54U;
    configuration.uuid[1] = 0x2EU;
    if (!NUCODEMesh.begin(configuration) || !NUCODEMeshUpdate.begin())
    {
        Serial.println("Mesh BLOB Client start failed");
        return;
    }
    Serial.println("type s after staging a 4096-byte BLOB in slot1");
}

void loop()
{
    NUCODEMesh.poll();
    if (Serial.available() > 0 && Serial.read() == 's')
    {
        nucode::mesh::BlobTransfer transfer{};
        transfer.id = 0x4E553534424C4F42ULL;
        transfer.size = 4096U;
        transfer.targets = blobTargets;
        transfer.target_count = sizeof(blobTargets) / sizeof(blobTargets[0]);
        transfer.mode = nucode::mesh::BlobTransferMode::push;
        if (!NUCODEMeshUpdate.sendBlob(transfer))
        {
            Serial.println("BLOB transfer start failed");
        }
    }
}
