/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 2대 — 1) MeshFriend 실행 보드; 2) friendship을 요청하는 provisioned Low Power Node
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * prj.conf
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 외부 provisioner로 AppKey를 배포하고 두 node가 같은 subnet에 속하게 합니다.
 * @par Metadata
 * identity `NUCODE_BLE_Mesh/MeshFriend`, sha256 `e5c7d6fbc5f8e1f5f6e0d166378f7d6b8058f39905668cd477838bbad0630269`
 * @nucode_example_setup_end */

/**
 * @file MeshFriend.ino
 * @brief provisioning 뒤 Friend queue 역할을 활성화합니다.
 */

#include <NUCODE_BLE_Mesh.h>

void setup()
{
    Serial.begin(115200);
    nucode::mesh::Configuration configuration{};
    configuration.uuid[0] = 0x54U;
    configuration.uuid[1] = 0x12U;
    if (!NUCODEMesh.begin(configuration))
    {
        Serial.println("Friend start failed");
        return;
    }
    if (NUCODEMesh.provisioned() &&
        !NUCODEMesh.setFeature(nucode::mesh::Feature::friend_node, true))
    {
        Serial.println("Friend enable failed");
    }
}

void loop()
{
    NUCODEMesh.poll();
}
