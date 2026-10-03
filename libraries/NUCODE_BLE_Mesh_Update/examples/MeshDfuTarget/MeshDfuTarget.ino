/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: Secure BLE DFU (MCUboot) (`secure_ble_dfu`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 2대 — 1) Mesh DFU Target; 2) Mesh DFU Initiator 또는 Distributor
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * prj.conf
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * production signing key의 public key를 MCUboot에 고정하고 test boot 정상 동작 뒤에만 c로 confirm합니다.
 * @par Metadata
 * identity `NUCODE_BLE_Mesh_Update/MeshDfuTarget`, sha256 `895b2a709563eba065817cc9d96a729ba44e065381875fd8a9afbf383a8a6877`
 * @nucode_example_setup_end */

/**
 * @file MeshDfuTarget.ino
 * @brief signed Mesh DFU image의 test boot와 명시적 confirm 경계를 제공합니다.
 */

#include <NUCODE_BLE_Mesh_Update.h>

void setup()
{
    Serial.begin(115200);
    nucode::mesh::Configuration configuration{};
    configuration.role = nucode::mesh::Role::node;
    configuration.uuid[0] = 0x54U;
    configuration.uuid[1] = 0x30U;
    if (!NUCODEMesh.begin(configuration) || !NUCODEMeshUpdate.begin())
    {
        Serial.println("Mesh DFU Target start failed");
        return;
    }
    Serial.println("type c only after the test image passes application checks");
}

void loop()
{
    NUCODEMesh.poll();
    if (Serial.available() > 0 && Serial.read() == 'c')
    {
        if (!NUCODEMeshUpdate.confirmRunningImage())
        {
            Serial.println("image confirmation failed");
        }
    }
}
