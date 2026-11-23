/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par 목적
 * CS를 자동 생성하지 않는 NU54DK SPI transaction 예제입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: Standard peripherals (`standard`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 1대 — 1) SPITransaction 실행 보드
 * @par Serial Monitor
 * 사용하지 않음
 * @par 필수 sidecar
 * 없음
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 추가 조건 없음
 * @par 준비물
 * - NU54DK 보드 1대 — 1) SPITransaction 실행 보드
 * @par 설정
 * - Tools → Feature set에서 `standard` profile을 선택합니다.
 * - 이 예제는 Serial Monitor 출력을 필수 결과로 사용하지 않습니다.
 * @par 실행 순서
 * - 권장 profile로 현재 Sketch와 metadata에 적힌 각 peer 역할 Sketch를 빌드합니다.
 * - probe가 여러 대이면 `NUCODE_PROBE_UID`를 지정하고 Arduino Upload로 역할별 보드를 구분합니다.
 * - peer·외장 조건을 먼저 준비한 뒤 reset 또는 예제에 명시된 입력으로 실행합니다.
 * @par 성공 출력
 * - Serial 문구 `NUCODE_M7_SPI_TRANSACTION_DONE`를 포함한 정상 상태 전이를 확인합니다.
 * @par 흔한 오류
 * - 권장 profile과 sidecar가 다르면 기능·Kconfig가 빠질 수 있으므로 먼저 설정을 다시 확인합니다.
 * - 여러 probe가 연결된 상태에서 UID를 생략하면 다른 보드에 upload될 수 있습니다.
 * @par 다음 예제
 * - `Wire/WirePmicId`
 * - `EEPROM/EEPROMPersistence`
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
 * Recipe `spi`; 내부 증거 ID는 metadata에서 관리합니다.
 * 직접 upstream 복사 아님; NCS `99553055607b2e9885fbc80ccd11fa9da81c2df0`, Zephyr `bf801e4e3d19e1ffa76164346480cb7734dd2800`
 * build `clean_installed_compile_required`, runtime `procedure_documented_not_physical_pass`
 * @par Metadata
 * identity `SPI/SPITransaction`, sha256 `f4a73e24892d8c3c3ab212bc0b2cc05b41cbae55e789274c0b0c65eac7253bef`
 * @nucode_example_setup_end */

/**
 * @file SPITransaction.ino
 * @brief CS를 자동 생성하지 않는 NU54DK SPI transaction 예제입니다.
 * @note SPI library와 함께 배포되는 보드 검증 예제입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <SPI.h>

/**
 * @brief mode 0, MSB-first, 4 MHz transaction에서 두 byte를 전송합니다.
 *
 * @note 실제 target의 CS는 확정된 외부 GPIO를 Sketch가 직접 제어해야 합니다.
 */
void setup(void)
{
    Serial.begin(115200U);
    SPI.begin();
    SPI.beginTransaction(SPISettings(4000000U, MSBFIRST, SPI_MODE0));
    uint8_t frame[] = {0x9FU, 0x00U};
    SPI.transfer(frame, sizeof(frame));
    SPI.endTransaction();
    Serial.println("NUCODE_M7_SPI_TRANSACTION_DONE");
}

/** @brief 단일 transaction 예제이므로 추가 전송은 수행하지 않습니다. */
void loop(void)
{
    delay(1000U);
}
