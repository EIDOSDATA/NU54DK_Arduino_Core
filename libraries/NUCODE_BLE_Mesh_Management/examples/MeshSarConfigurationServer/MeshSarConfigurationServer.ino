/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 2대 — 1) SAR Configuration Server; 2) SAR Configuration Client
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * prj.conf
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 분할 message를 전송해 TX/RX 설정 변경 전후 동작을 비교합니다.
 * @par Metadata
 * identity `NUCODE_BLE_Mesh_Management/MeshSarConfigurationServer`, sha256 `e74fcfb4fedb575f8f983f1b3f9651460d9bc8db830f9c332c1ce06bd4bb1540`
 * @nucode_example_setup_end */

/**
 * @file MeshSarConfigurationServer.ino
 * @brief SAR Configuration Server model을 고정 composition으로 제공합니다.
 */

#include <NUCODE_BLE_Mesh_Management.h>

void setup()
{
    Serial.begin(115200);
    nucode::mesh::Configuration configuration{};
    configuration.uuid[0] = 0x54U;
    configuration.uuid[1] = 0x24U;
    if (!NUCODEMesh.begin(configuration) || !NUCODEMeshManagement.begin())
    {
        Serial.println("SAR server start failed");
        return;
    }
    Serial.println("SAR Configuration Server ready");
}

void loop()
{
    NUCODEMesh.poll();
    NUCODEMeshManagement.poll();
}
