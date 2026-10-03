/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 2대 — 1) Large Composition Data Client; 2) Large Composition Data Server
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * prj.conf
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * server를 먼저 provisioning하고 DevKey 관리 model 접근을 허용합니다.
 * @par Metadata
 * identity `NUCODE_BLE_Mesh_Management/MeshLargeCompositionDataClient`, sha256 `35da969d93c533c647918f4eadf3f8cc0356df8fc851ca8110e081d7c26bd18c`
 * @nucode_example_setup_end */

/**
 * @file MeshLargeCompositionDataClient.ino
 * @brief Composition Data와 Models Metadata를 bounded page 조각으로 읽습니다.
 */

#include <NUCODE_BLE_Mesh_Management.h>

const nucode::mesh::ManagementTarget compositionServer{0x0002U, 0U, 7U};

void setup()
{
    Serial.begin(115200);
    nucode::mesh::Configuration configuration{};
    configuration.role = nucode::mesh::Role::provisioner;
    configuration.uuid[0] = 0x54U;
    configuration.uuid[1] = 0x27U;
    if (!NUCODEMesh.begin(configuration) || !NUCODEMeshManagement.begin())
    {
        Serial.println("Large Composition Data client start failed");
        return;
    }
    if (NUCODEMesh.provisioned())
    {
        nucode::mesh::LargeDataChunk composition{};
        nucode::mesh::LargeDataChunk metadata{};
        if (!NUCODEMeshManagement.readLargeComposition(compositionServer, 0U, 0U,
                                                        composition) ||
            !NUCODEMeshManagement.readModelsMetadata(compositionServer, 0U, 0U,
                                                      metadata))
        {
            Serial.println("Large data read failed");
        }
    }
}

void loop()
{
    NUCODEMesh.poll();
    NUCODEMeshManagement.poll();
}
