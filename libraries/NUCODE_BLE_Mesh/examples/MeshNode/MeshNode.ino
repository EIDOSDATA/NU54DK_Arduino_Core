/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 2대 — 1) PB-ADV/PB-GATT provisionee node; 2) Mesh provisioner
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * prj.conf
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 처음 실행할 때 저장된 Mesh 상태가 없거나 명시적으로 reset되어 있어야 합니다.
 * @par Metadata
 * identity `NUCODE_BLE_Mesh/MeshNode`, sha256 `50ec9bcf721c81224d65b1e7d45227c124bc7bf3147f34b91d155ff593d6d822`
 * @nucode_example_setup_end */

/**
 * @file MeshNode.ino
 * @brief PB-ADV와 PB-GATT를 모두 여는 저장형 Mesh node를 실행합니다.
 */

#include <NUCODE_BLE_Mesh.h>

/** @brief provisioning 완료와 reset을 출력합니다. */
void onMeshEvent(const nucode::mesh::EventRecord &record, void *context)
{
    static_cast<void>(context);
    if (record.event == nucode::mesh::Event::provisioned)
    {
        Serial.print("Provisioned at 0x");
        Serial.println(record.address, HEX);
    }
    else if (record.event == nucode::mesh::Event::reset)
    {
        Serial.println("Mesh state reset");
    }
    else if (record.event == nucode::mesh::Event::model_status &&
             record.model == nucode::mesh::Model::generic_on_off_server)
    {
        Serial.print("Local OnOff state: ");
        Serial.println(NUCODEMesh.localOnOff() ? "on" : "off");
    }
}

void setup()
{
    Serial.begin(115200);
    nucode::mesh::Configuration configuration{};
    configuration.uuid[0] = 0x54U;
    configuration.uuid[1] = 0x02U;
    NUCODEMesh.onEvent(onMeshEvent);
    if (!NUCODEMesh.begin(configuration))
    {
        Serial.println("Mesh node start failed");
    }
}

void loop()
{
    NUCODEMesh.poll();
}
