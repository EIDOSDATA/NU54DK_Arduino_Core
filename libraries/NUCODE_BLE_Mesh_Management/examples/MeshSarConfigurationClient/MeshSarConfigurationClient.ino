/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 2대 — 1) SAR Configuration Client; 2) SAR Configuration Server
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * prj.conf
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 모든 bit-field가 Mesh Profile 허용 범위 안인지 확인한 뒤 설정합니다.
 * @par Metadata
 * identity `NUCODE_BLE_Mesh_Management/MeshSarConfigurationClient`, sha256 `12626d85c9cf79ded5cf4e7fa6d98cfb88d65e106e501a1612f45860e9a38199`
 * @nucode_example_setup_end */

/**
 * @file MeshSarConfigurationClient.ino
 * @brief 원격 SAR TX/RX 설정을 읽고 유효 범위에서 갱신합니다.
 */

#include <NUCODE_BLE_Mesh_Management.h>

const nucode::mesh::ManagementTarget sarServer{0x0002U, 0U, 7U};

void setup()
{
    Serial.begin(115200);
    nucode::mesh::Configuration configuration{};
    configuration.role = nucode::mesh::Role::provisioner;
    configuration.uuid[0] = 0x54U;
    configuration.uuid[1] = 0x23U;
    if (!NUCODEMesh.begin(configuration) || !NUCODEMeshManagement.begin())
    {
        Serial.println("SAR client start failed");
        return;
    }
    if (NUCODEMesh.provisioned())
    {
        nucode::mesh::SarTransmitter transmitter{};
        nucode::mesh::SarReceiver receiver{};
        if (!NUCODEMeshManagement.getSarTransmitter(sarServer, transmitter) ||
            !NUCODEMeshManagement.getSarReceiver(sarServer, receiver))
        {
            Serial.println("SAR read failed");
            return;
        }
        transmitter.segment_interval_step = 1U;
        receiver.segments_threshold = 3U;
        if (!NUCODEMeshManagement.setSarTransmitter(sarServer, transmitter) ||
            !NUCODEMeshManagement.setSarReceiver(sarServer, receiver))
        {
            Serial.println("SAR update failed");
        }
    }
}

void loop()
{
    NUCODEMesh.poll();
    NUCODEMeshManagement.poll();
}
