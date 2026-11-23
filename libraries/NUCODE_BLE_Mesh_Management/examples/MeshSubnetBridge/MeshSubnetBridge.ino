/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par 목적
 * Subnet Bridge 상태와 허용 forwarding table 항목을 설정합니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 3대 — 1) Bridge Configuration Client; 2) Subnet Bridge node; 3) 두 subnet의 source 또는 destination node
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * prj.conf
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * NetKey 0과 1을 배포하고 허용 table 항목 밖의 forwarding은 거부되는지 확인합니다.
 * @par 준비물
 * - NU54DK 보드 3대 — 1) Bridge Configuration Client; 2) Subnet Bridge node; 3) 두 subnet의 source 또는 destination node
 * - NetKey 0과 1을 배포하고 허용 table 항목 밖의 forwarding은 거부되는지 확인합니다.
 * @par 설정
 * - Tools → Feature set에서 `ble` profile을 선택합니다.
 * - Sketch 폴더의 sidecar를 함께 설치합니다: prj.conf
 * - Serial Monitor는 115200 baud로 엽니다.
 * @par 실행 순서
 * - 권장 profile로 현재 Sketch와 metadata에 적힌 각 peer 역할 Sketch를 빌드합니다.
 * - probe가 여러 대이면 `NUCODE_PROBE_UID`를 지정하고 Arduino Upload로 역할별 보드를 구분합니다.
 * - peer·외장 조건을 먼저 준비한 뒤 reset 또는 예제에 명시된 입력으로 실행합니다.
 * @par 성공 출력
 * - Serial Monitor에서 오류 문구 없이 목적 기능의 상태 전이가 완료되는지 확인합니다.
 * @par 흔한 오류
 * - 권장 profile과 sidecar가 다르면 기능·Kconfig가 빠질 수 있으므로 먼저 설정을 다시 확인합니다.
 * - 여러 probe가 연결된 상태에서 UID를 생략하면 다른 보드에 upload될 수 있습니다.
 * - `Subnet Bridge client start failed` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * - `Subnet Bridge update failed` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * @par 다음 예제
 * - `NUCODE_BLE_Mesh_Management/MeshLargeCompositionDataClient`
 * - `NUCODE_BLE_Mesh_Management/MeshLargeCompositionDataServer`
 * @par 종료와 재시작
 * - 예제의 stop/end/disconnect 또는 유한 완료 흐름 뒤 오류와 자원 반환을 확인합니다.
 * - 실패 문구와 driver 상태를 확인한 뒤 명시적 reset 또는 예제의 재시작 흐름을 사용합니다.
 * @par 보안
 * - wireless_example_no_implicit_security_claim
 * - 무선 연결 성공만으로 인증·암호화·상호운용 보안을 주장하지 않습니다.
 * @par 제한
 * - Compile·Host 검사는 실제 보드 runtime 또는 외부 제품 상호운용 PASS를 대신하지 않습니다.
 * - 목적과 metadata 조건 밖의 성능·동시성·정밀도는 이 예제의 보증 범위가 아닙니다.
 * @par Negative
 * - wrong_profile_or_missing_sidecar
 * - missing_or_wrong_role_peer
 * - startup_or_runtime_error_reported
 * @par Traceability
 * Recipe `ble_mesh_management`; 내부 증거 ID는 metadata에서 관리합니다.
 * 직접 upstream 복사 아님; NCS `99553055607b2e9885fbc80ccd11fa9da81c2df0`, Zephyr `bf801e4e3d19e1ffa76164346480cb7734dd2800`
 * build `clean_installed_compile_required`, runtime `procedure_documented_not_physical_pass`
 * @par Metadata
 * identity `NUCODE_BLE_Mesh_Management/MeshSubnetBridge`, sha256 `db4c3056057f521df681b250d55976c9960340f95721c0347a6dc2d1a59ec89a`
 * @nucode_example_setup_end */

/**
 * @file MeshSubnetBridge.ino
 * @brief Subnet Bridge 상태와 허용 forwarding table 항목을 설정합니다.
 */

#include <NUCODE_BLE_Mesh_Management.h>

const nucode::mesh::ManagementTarget bridgeServer{0x0002U, 0U, 7U};

void setup()
{
    Serial.begin(115200);
    nucode::mesh::Configuration configuration{};
    configuration.role = nucode::mesh::Role::provisioner;
    configuration.uuid[0] = 0x54U;
    configuration.uuid[1] = 0x2DU;
    if (!NUCODEMesh.begin(configuration) || !NUCODEMeshManagement.begin())
    {
        Serial.println("Subnet Bridge client start failed");
        return;
    }
    nucode::mesh::BridgeEntry entry{};
    entry.first_net_key_index = 0U;
    entry.second_net_key_index = 1U;
    entry.first_address = 0x0003U;
    entry.second_address = 0x0004U;
    if (NUCODEMesh.provisioned() &&
        (!NUCODEMeshManagement.setSubnetBridge(bridgeServer, true) ||
         !NUCODEMeshManagement.addBridgeEntry(bridgeServer, entry)))
    {
        Serial.println("Subnet Bridge update failed");
    }
}

void loop()
{
    NUCODEMesh.poll();
    NUCODEMeshManagement.poll();
}
