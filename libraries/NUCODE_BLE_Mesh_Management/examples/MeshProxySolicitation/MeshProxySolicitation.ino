/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 2대 — 1) Solicitation PDU 송신 node; 2) On-Demand Private Proxy Server
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * prj.conf
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * SRPL clear 범위의 unicast address와 재생 SSEQ 거부를 함께 확인합니다.
 * @par Metadata
 * identity `NUCODE_BLE_Mesh_Management/MeshProxySolicitation`, sha256 `8157a90d43b4312bdb74e4e43ad1b6bc99105f0e38c310a6c67475769c34a3a7`
 * @nucode_example_setup_end */

/**
 * @file MeshProxySolicitation.ino
 * @brief Solicitation PDU를 광고하고 원격 SRPL 범위를 정리합니다.
 */

#include <NUCODE_BLE_Mesh_Management.h>

const nucode::mesh::ManagementTarget proxyServer{0x0002U, 0U, 7U};

void setup()
{
    Serial.begin(115200);
    nucode::mesh::Configuration configuration{};
    configuration.role = nucode::mesh::Role::provisioner;
    configuration.uuid[0] = 0x54U;
    configuration.uuid[1] = 0x2CU;
    if (!NUCODEMesh.begin(configuration) || !NUCODEMeshManagement.begin())
    {
        Serial.println("Proxy solicitation start failed");
        return;
    }
    if (NUCODEMesh.provisioned() &&
        (!NUCODEMeshManagement.solicit(0U) ||
         !NUCODEMeshManagement.clearSolicitationReplay(proxyServer, 0x0003U, 2U)))
    {
        Serial.println("Solicitation or SRPL clear failed");
    }
}

void loop()
{
    NUCODEMesh.poll();
    NUCODEMeshManagement.poll();
}
