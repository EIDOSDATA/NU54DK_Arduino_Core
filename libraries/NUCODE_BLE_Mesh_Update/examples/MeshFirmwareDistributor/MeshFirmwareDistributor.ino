/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: Secure BLE DFU (MCUboot) (`secure_ble_dfu`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 3대 — 1) Firmware Distributor; 2) Mesh DFU Initiator; 3) Mesh DFU Target
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * prj.conf
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 한 slot을 upload와 distribution이 동시에 사용하지 않도록 절차를 직렬화합니다.
 * @par Metadata
 * identity `NUCODE_BLE_Mesh_Update/MeshFirmwareDistributor`, sha256 `65d36ae441f0f32d1bb117accb4991b80d0a68c96d15adcbd03250cae020724c`
 * @nucode_example_setup_end */

/**
 * @file MeshFirmwareDistributor.ino
 * @brief Mesh Firmware Distributor의 upload·distribution 단계를 관찰합니다.
 */

#include <NUCODE_BLE_Mesh_Update.h>

void setup()
{
    Serial.begin(115200);
    nucode::mesh::Configuration configuration{};
    configuration.role = nucode::mesh::Role::provisioner;
    configuration.uuid[0] = 0x54U;
    configuration.uuid[1] = 0x31U;
    if (!NUCODEMesh.begin(configuration) || !NUCODEMeshUpdate.begin())
    {
        Serial.println("Mesh Firmware Distributor start failed");
        return;
    }
    Serial.println("Distributor models ready; use a Mesh DFU Initiator to upload and start");
}

void loop()
{
    NUCODEMesh.poll();
    if (NUCODEMeshUpdate.distributionPhase() == nucode::mesh::UpdatePhase::failed)
    {
        Serial.println("distribution failed");
        delay(1000U);
    }
}
