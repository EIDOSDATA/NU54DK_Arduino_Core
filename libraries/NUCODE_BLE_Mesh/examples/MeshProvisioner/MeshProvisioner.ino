/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 2대 — 1) PB-ADV/PB-GATT provisioner; 2) 초기화되지 않은 Mesh node
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * nucode-build.json, prj.conf
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 한 번에 하나의 unprovisioned beacon만 처리하며 실패 뒤 새 beacon에서 재시도합니다.
 * @par Metadata
 * identity `NUCODE_BLE_Mesh/MeshProvisioner`, sha256 `8fa34d997b666d4760f921055e272e18c7081e9d23b02e04737f9567336f4e34`
 * @nucode_example_setup_end */

/**
 * @file MeshProvisioner.ino
 * @brief PB-ADV와 PB-GATT beacon을 발견해 순차 provisioning합니다.
 */

#include <NUCODE_BLE_Mesh.h>

bool provisioning = false;
const std::uint8_t applicationKey[16] = {
    0x54U, 0x06U, 0x00U, 0x01U, 0x02U, 0x03U, 0x04U, 0x05U,
    0x06U, 0x07U, 0x08U, 0x09U, 0x0AU, 0x0BU, 0x0CU, 0x0DU};

/** @brief 발견과 완료 event를 main loop에서 처리합니다. */
void onMeshEvent(const nucode::mesh::EventRecord &record, void *context)
{
    static_cast<void>(context);
    if (record.event == nucode::mesh::Event::unprovisioned_device && !provisioning)
    {
        provisioning = NUCODEMesh.provision(record.uuid, record.bearer);
        Serial.println(provisioning ? "Provisioning started" : "Provisioning start failed");
    }
    else if (record.event == nucode::mesh::Event::node_added)
    {
        provisioning = false;
        Serial.print("Node added at 0x");
        Serial.println(record.address, HEX);
        if (!NUCODEMesh.configureAppKey(record.address, applicationKey) ||
            !NUCODEMesh.bindModel(record.address, record.address,
                                  nucode::mesh::Model::generic_on_off_server) ||
            !NUCODEMesh.subscribeModel(record.address, record.address,
                                       nucode::mesh::Model::generic_on_off_server, 0xC000U))
        {
            Serial.print("Configuration failed, status: 0x");
            Serial.println(NUCODEMesh.lastConfigurationStatus(), HEX);
        }
        nucode::mesh::Publication publication{};
        publication.address = 0xC000U;
        publication.period_ms = 1000U;
        if (!NUCODEMesh.configurePublication(record.address, record.address,
                                             nucode::mesh::Model::generic_on_off_server,
                                             publication))
        {
            Serial.println("Publication configuration failed");
        }
    }
    else if (record.event == nucode::mesh::Event::provisioning_link_closed)
    {
        provisioning = false;
    }
}

void setup()
{
    Serial.begin(115200);
    nucode::mesh::Configuration configuration{};
    configuration.role = nucode::mesh::Role::provisioner;
    configuration.uuid[0] = 0x54U;
    configuration.uuid[1] = 0x01U;
    NUCODEMesh.onEvent(onMeshEvent);
    if (!NUCODEMesh.begin(configuration))
    {
        Serial.println("Mesh provisioner start failed");
    }
}

void loop()
{
    NUCODEMesh.poll();
}
