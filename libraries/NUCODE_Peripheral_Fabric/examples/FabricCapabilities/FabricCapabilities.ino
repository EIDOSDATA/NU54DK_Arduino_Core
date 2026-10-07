/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par 목적
 * `NUCODE_Peripheral_Fabric/FabricCapabilities` 공개 API의 기본 사용 흐름을 실행합니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: Peripheral Fabric (DAP UART disconnected) (`fabric`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 1대 — 1) FabricCapabilities 실행 보드
 * @par Serial Monitor
 * 사용하지 않음
 * @par 필수 sidecar
 * 없음
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * DAP UART 공유 핀을 분리하고 예제가 요구하는 외장 I/O 결선을 확인합니다.
 * @par 준비물
 * - NU54DK 보드 1대 — 1) FabricCapabilities 실행 보드
 * - DAP UART 공유 핀을 분리하고 예제가 요구하는 외장 I/O 결선을 확인합니다.
 * @par 설정
 * - Tools → Feature set에서 `fabric` profile을 선택합니다.
 * - 이 예제는 Serial Monitor 출력을 필수 결과로 사용하지 않습니다.
 * @par 실행 순서
 * - 권장 profile로 현재 Sketch와 metadata에 적힌 각 peer 역할 Sketch를 빌드합니다.
 * - probe가 여러 대이면 `NUCODE_PROBE_UID`를 지정하고 Arduino Upload로 역할별 보드를 구분합니다.
 * - peer·외장 조건을 먼저 준비한 뒤 reset 또는 예제에 명시된 입력으로 실행합니다.
 * @par 성공 출력
 * - 목적에 적힌 LED·pin·peer 동작을 직접 확인합니다. Compile PASS만으로 runtime PASS로 처리하지 않습니다.
 * @par 흔한 오류
 * - 권장 profile과 sidecar가 다르면 기능·Kconfig가 빠질 수 있으므로 먼저 설정을 다시 확인합니다.
 * - 여러 probe가 연결된 상태에서 UID를 생략하면 다른 보드에 upload될 수 있습니다.
 * @par 다음 예제
 * - `NUCODE_Peripheral_Fabric/PwmSequencePlayback`
 * - `NUCODE_Peripheral_Fabric/ResourceConflictDemo`
 * @par 종료와 재시작
 * - 예제의 stop/end/disconnect 또는 유한 완료 흐름 뒤 오류와 자원 반환을 확인합니다.
 * - 실패 문구와 driver 상태를 확인한 뒤 명시적 reset 또는 예제의 재시작 흐름을 사용합니다.
 * @par 보안
 * - no_security_property_claimed
 * - 이 예제는 별도의 보안 속성을 주장하지 않습니다.
 * @par 제한
 * - Compile·Host 검사는 실제 보드 runtime 또는 외부 제품 상호운용 PASS를 대신하지 않습니다.
 * - 목적과 metadata 조건 밖의 성능·동시성·정밀도는 이 예제의 보증 범위가 아닙니다.
 * @par Negative
 * - wrong_profile_or_missing_sidecar
 * - missing_or_wrong_role_peer
 * - startup_or_runtime_error_reported
 * @par Traceability
 * Recipe `peripheral_fabric`; 내부 증거 ID는 metadata에서 관리합니다.
 * 직접 upstream 복사 아님; NCS `99553055607b2e9885fbc80ccd11fa9da81c2df0`, Zephyr `bf801e4e3d19e1ffa76164346480cb7734dd2800`
 * build `clean_installed_compile_required`, runtime `procedure_documented_not_physical_pass`
 * @par Metadata
 * identity `NUCODE_Peripheral_Fabric/FabricCapabilities`, sha256 `ef26cd6f3a2a864f631a742bf9afb67fbbd50f0189f67fd064ee2354921913cf`
 * @nucode_example_setup_end */

#include <NUCODE_Peripheral_Fabric.h>

namespace
{
    volatile bool fabric_ready = false;
}

void setup()
{
    using namespace nucode::arduino;
    using namespace nucode::peripheral;

    const bool serial_ready =
        serialFabric().uarte(0U) != nullptr && serialFabric().spim(0U) != nullptr &&
        serialFabric().spis(0U) != nullptr && serialFabric().twim(20U) != nullptr &&
        serialFabric().twis(20U) != nullptr;
    const bool analog_ready = analogFabric().pwm(20U) != nullptr;
    const bool event_ready =
        eventFabric().timer(20U) != nullptr && eventFabric().egu(20U) != nullptr &&
        eventFabric().gpiote(20U) != nullptr && eventFabric().dppi(20U) != nullptr &&
        eventFabric().ppib(20U) != nullptr;
    const bool stream_ready =
        streamFabric().pdm(20U) != nullptr && streamFabric().i2s(20U) != nullptr &&
        streamFabric().qdec(20U) != nullptr && streamFabric().qdec(21U) != nullptr;
    const bool system_ready = systemFabric().watchdog(30U) != nullptr;
    const bool inventory_ready = peripheralInventorySize() == 75U;

    fabric_ready = serial_ready && analog_ready && event_ready && stream_ready && system_ready &&
                   inventory_ready && isSupported(capabilities.serial) &&
                   isSupported(capabilities.analog) && isSupported(capabilities.event) &&
                   isSupported(capabilities.pdm) && isSupported(capabilities.i2s) &&
                   isSupported(capabilities.qdec) && isSupported(capabilities.system);

    pinMode(LED_BUILTIN, OUTPUT);
    digitalWrite(LED_BUILTIN, fabric_ready ? HIGH : LOW);
}

void loop()
{
    delay(1000U);
}
