/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 2대 — 1) Relay node; 2) 같은 subnet의 source 또는 destination node
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * prj.conf
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * Relay를 거치도록 direct radio 경로를 감쇠하고 TTL을 2 이상으로 설정합니다.
 * @par Metadata
 * identity `NUCODE_BLE_Mesh/MeshRelay`, sha256 `faacca59e772af9b932dfb4c936c3d58091e314cb2c1533ceed4c64e8fef7bec`
 * @nucode_example_setup_end */

/**
 * @file MeshRelay.ino
 * @brief provisioning 뒤 Relay와 network retransmit을 활성화합니다.
 */

#include <NUCODE_BLE_Mesh.h>

void setup()
{
    Serial.begin(115200);
    nucode::mesh::Configuration configuration{};
    configuration.uuid[0] = 0x54U;
    configuration.uuid[1] = 0x11U;
    if (!NUCODEMesh.begin(configuration))
    {
        Serial.println("Relay start failed");
        return;
    }
    if (NUCODEMesh.provisioned() && !NUCODEMesh.setFeature(nucode::mesh::Feature::relay, true))
    {
        Serial.println("Relay enable failed");
    }
}

void loop()
{
    NUCODEMesh.poll();
}
