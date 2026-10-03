/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 2대 — 1) Large Composition Data Server; 2) Large Composition Data Client
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * prj.conf
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * client가 page와 offset을 바꾸어 분할 응답과 total size를 확인합니다.
 * @par Metadata
 * identity `NUCODE_BLE_Mesh_Management/MeshLargeCompositionDataServer`, sha256 `ffa0379e6b725b72c0f551e981649c73f2fd43493b24b0cb31299b54ec54fca3`
 * @nucode_example_setup_end */

/**
 * @file MeshLargeCompositionDataServer.ino
 * @brief Large Composition Data Server와 metadata page를 제공합니다.
 */

#include <NUCODE_BLE_Mesh_Management.h>

void setup()
{
    Serial.begin(115200);
    nucode::mesh::Configuration configuration{};
    configuration.uuid[0] = 0x54U;
    configuration.uuid[1] = 0x28U;
    if (!NUCODEMesh.begin(configuration) || !NUCODEMeshManagement.begin())
    {
        Serial.println("Large Composition Data server start failed");
        return;
    }
    Serial.println("Large Composition Data Server ready");
}

void loop()
{
    NUCODEMesh.poll();
    NUCODEMeshManagement.poll();
}
