/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 2대 — 1) MeshHealth foundation node; 2) Configuration/Health Client를 가진 provisioner
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * prj.conf
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * provisioner에서 Composition Data와 Health Fault 상태를 조회합니다.
 * @par Metadata
 * identity `NUCODE_BLE_Mesh/MeshHealth`, sha256 `fb6afc6c99f4b242edd3b83834c269b7e711a21343b61c6095e1ee038295298a`
 * @nucode_example_setup_end */

/**
 * @file MeshHealth.ino
 * @brief Configuration Server와 Health Server를 포함한 foundation node를 실행합니다.
 */

#include <NUCODE_BLE_Mesh.h>

/** @brief lifecycle error를 main 문맥에서 보고합니다. */
void onMeshEvent(const nucode::mesh::EventRecord &record, void *context)
{
    static_cast<void>(context);
    if (record.event == nucode::mesh::Event::error)
    {
        Serial.print("Mesh driver error: ");
        Serial.println(record.driver_error);
    }
}

void setup()
{
    Serial.begin(115200);
    nucode::mesh::Configuration configuration{};
    configuration.uuid[0] = 0x54U;
    configuration.uuid[1] = 0x03U;
    NUCODEMesh.onEvent(onMeshEvent);
    if (!NUCODEMesh.begin(configuration))
    {
        Serial.println("Health node start failed");
    }
}

void loop()
{
    NUCODEMesh.poll();
}
