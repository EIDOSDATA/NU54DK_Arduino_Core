/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 2대 — 1) GATT Proxy node; 2) Mesh Proxy Client
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * prj.conf
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * node를 provisioning한 뒤 Proxy feature를 활성화하고 GATT bearer로 연결합니다.
 * @par Metadata
 * identity `NUCODE_BLE_Mesh/MeshProxy`, sha256 `905f137489c2845f676a5da8506b075666b0a030eebee5791509b94b29e01515`
 * @nucode_example_setup_end */

/**
 * @file MeshProxy.ino
 * @brief provisioning 뒤 GATT Proxy bearer를 활성화합니다.
 */

#include <NUCODE_BLE_Mesh.h>

void setup()
{
    Serial.begin(115200);
    nucode::mesh::Configuration configuration{};
    configuration.uuid[0] = 0x54U;
    configuration.uuid[1] = 0x14U;
    if (!NUCODEMesh.begin(configuration))
    {
        Serial.println("Proxy start failed");
        return;
    }
    if (NUCODEMesh.provisioned() &&
        !NUCODEMesh.setFeature(nucode::mesh::Feature::gatt_proxy, true))
    {
        Serial.println("Proxy enable failed");
    }
}

void loop()
{
    NUCODEMesh.poll();
}
