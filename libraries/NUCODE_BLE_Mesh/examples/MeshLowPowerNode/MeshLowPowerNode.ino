/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 2대 — 1) Mesh Low Power Node; 2) 같은 subnet의 Mesh Friend
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * prj.conf
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 두 node를 provisioning한 뒤 Friend feature를 먼저 활성화합니다.
 * @par Metadata
 * identity `NUCODE_BLE_Mesh/MeshLowPowerNode`, sha256 `74723b19d7c4d812ec546cf977f102b07d7f3dfc14a82edfbe3437597601c8f7`
 * @nucode_example_setup_end */

/**
 * @file MeshLowPowerNode.ino
 * @brief Friend와 맺는 Low Power Node를 실행하고 명시적으로 poll합니다.
 */

#include <NUCODE_BLE_Mesh.h>

unsigned long lastPoll = 0UL;

void setup()
{
    Serial.begin(115200);
    nucode::mesh::Configuration configuration{};
    configuration.uuid[0] = 0x54U;
    configuration.uuid[1] = 0x13U;
    if (!NUCODEMesh.begin(configuration))
    {
        Serial.println("LPN start failed");
        return;
    }
    if (NUCODEMesh.provisioned() &&
        !NUCODEMesh.setFeature(nucode::mesh::Feature::low_power_node, true))
    {
        Serial.println("LPN enable failed");
    }
}

void loop()
{
    NUCODEMesh.poll();
    if (NUCODEMesh.provisioned() && millis() - lastPoll >= 10000UL)
    {
        lastPoll = millis();
        static_cast<void>(NUCODEMesh.pollFriend());
    }
}
