/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par 목적
 * inactive slot의 BLOB을 두 target에 push mode로 전송합니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: Secure BLE DFU (MCUboot) (`secure_ble_dfu`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 3대 — 1) BLOB Client; 2) BLOB Server target 0x0002; 3) BLOB Server target 0x0003
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * prj.conf
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 제품이 신뢰하는 signing key로 생성한 inactive-slot image를 staging하고 BLOB ID·크기를 일치시킵니다.
 * @par 준비물
 * - NU54DK 보드 3대 — 1) BLOB Client; 2) BLOB Server target 0x0002; 3) BLOB Server target 0x0003
 * - 제품이 신뢰하는 signing key로 생성한 inactive-slot image를 staging하고 BLOB ID·크기를 일치시킵니다.
 * @par 설정
 * - Tools → Feature set에서 `secure_ble_dfu` profile을 선택합니다.
 * - Sketch 폴더의 sidecar를 함께 설치합니다: prj.conf
 * - Serial Monitor는 115200 baud로 엽니다.
 * @par 실행 순서
 * - 권장 profile로 현재 Sketch와 metadata에 적힌 각 peer 역할 Sketch를 빌드합니다.
 * - probe가 여러 대이면 `NUCODE_PROBE_UID`를 지정하고 Arduino Upload로 역할별 보드를 구분합니다.
 * - peer·외장 조건을 먼저 준비한 뒤 reset 또는 예제에 명시된 입력으로 실행합니다.
 * @par 성공 출력
 * - Serial 문구 `type s after staging a 4096-byte BLOB in slot1`를 포함한 정상 상태 전이를 확인합니다.
 * @par 흔한 오류
 * - 권장 profile과 sidecar가 다르면 기능·Kconfig가 빠질 수 있으므로 먼저 설정을 다시 확인합니다.
 * - 여러 probe가 연결된 상태에서 UID를 생략하면 다른 보드에 upload될 수 있습니다.
 * - `Mesh BLOB Client start failed` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * - `BLOB transfer start failed` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * @par 다음 예제
 * - `NUCODE_BLE_Mesh_Update/MeshBlobServer`
 * - `NUCODE_BLE_Mesh_Update/MeshDfuTarget`
 * @par 종료와 재시작
 * - 예제의 stop/end/disconnect 또는 유한 완료 흐름 뒤 오류와 자원 반환을 확인합니다.
 * - 실패 문구와 driver 상태를 확인한 뒤 명시적 reset 또는 예제의 재시작 흐름을 사용합니다.
 * @par 보안
 * - explicit_security_or_signed_artifact_flow
 * - 예제의 pairing·bond·서명·credential 조건을 생략하지 않고 오류 출력을 확인합니다.
 * @par 제한
 * - Compile·Host 검사는 실제 보드 runtime 또는 외부 제품 상호운용 PASS를 대신하지 않습니다.
 * - 목적과 metadata 조건 밖의 성능·동시성·정밀도는 이 예제의 보증 범위가 아닙니다.
 * @par Negative
 * - wrong_profile_or_missing_sidecar
 * - missing_or_wrong_role_peer
 * - startup_or_runtime_error_reported
 * @par Traceability
 * Recipe `ble_mesh_update`; 내부 증거 ID는 metadata에서 관리합니다.
 * 직접 upstream 복사 아님; NCS `99553055607b2e9885fbc80ccd11fa9da81c2df0`, Zephyr `bf801e4e3d19e1ffa76164346480cb7734dd2800`
 * build `clean_installed_compile_required`, runtime `procedure_documented_not_physical_pass`
 * @par Metadata
 * identity `NUCODE_BLE_Mesh_Update/MeshBlobClient`, sha256 `a268ab471a2ea9af0c16fbe6476ddf86bd6f41ccd909b7d2fc82908a64f32de2`
 * @nucode_example_setup_end */

/**
 * @file MeshBlobClient.ino
 * @brief inactive slot의 BLOB을 두 target에 push mode로 전송합니다.
 */

#include <NUCODE_BLE_Mesh_Update.h>

const nucode::mesh::BlobTarget blobTargets[] = {{0x0002U}, {0x0003U}};

void setup()
{
    Serial.begin(115200);
    nucode::mesh::Configuration configuration{};
    configuration.role = nucode::mesh::Role::provisioner;
    configuration.uuid[0] = 0x54U;
    configuration.uuid[1] = 0x2EU;
    if (!NUCODEMesh.begin(configuration) || !NUCODEMeshUpdate.begin())
    {
        Serial.println("Mesh BLOB Client start failed");
        return;
    }
    Serial.println("type s after staging a 4096-byte BLOB in slot1");
}

void loop()
{
    NUCODEMesh.poll();
    if (Serial.available() > 0 && Serial.read() == 's')
    {
        nucode::mesh::BlobTransfer transfer{};
        transfer.id = 0x4E553534424C4F42ULL;
        transfer.size = 4096U;
        transfer.targets = blobTargets;
        transfer.target_count = sizeof(blobTargets) / sizeof(blobTargets[0]);
        transfer.mode = nucode::mesh::BlobTransferMode::push;
        if (!NUCODEMeshUpdate.sendBlob(transfer))
        {
            Serial.println("BLOB transfer start failed");
        }
    }
}
