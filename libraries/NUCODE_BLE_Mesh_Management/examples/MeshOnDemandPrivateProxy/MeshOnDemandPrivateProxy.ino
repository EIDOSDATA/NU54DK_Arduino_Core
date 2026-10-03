/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 2대 — 1) On-Demand Private Proxy Client; 2) On-Demand Private Proxy Server
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * prj.conf
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * Private Beacon Server를 먼저 구성하고 광고 lifetime을 초 단위로 확인합니다.
 * @par Metadata
 * identity `NUCODE_BLE_Mesh_Management/MeshOnDemandPrivateProxy`, sha256 `77fe42dca3bb33135f2211aa0869636950b7fb04d26bf4c99d2e3558d2f2b92c`
 * @nucode_example_setup_end */

/**
 * @file MeshOnDemandPrivateProxy.ino
 * @brief On-Demand Private Proxy 광고 수명을 원격 설정합니다.
 */

#include <NUCODE_BLE_Mesh_Management.h>

const nucode::mesh::ManagementTarget proxyServer{0x0002U, 0U, 7U};

void setup()
{
    Serial.begin(115200);
    nucode::mesh::Configuration configuration{};
    configuration.role = nucode::mesh::Role::provisioner;
    configuration.uuid[0] = 0x54U;
    configuration.uuid[1] = 0x2BU;
    if (!NUCODEMesh.begin(configuration) || !NUCODEMeshManagement.begin())
    {
        Serial.println("On-Demand Private Proxy client start failed");
        return;
    }
    if (NUCODEMesh.provisioned() &&
        !NUCODEMeshManagement.setOnDemandPrivateProxy(proxyServer, 30U))
    {
        Serial.println("On-Demand Private Proxy update failed");
    }
}

void loop()
{
    NUCODEMesh.poll();
    NUCODEMeshManagement.poll();
}
