/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
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
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI `--upload-field probe_id=<UID>`로 명시 선택합니다.
 * @par 추가 조건
 * 추가 조건 없음
 * @par Metadata
 * identity `SPI/SPITransaction`, sha256 `f4f2f332d0be7889cd908e0e9d301d112202144663eb91cbedb029c7779b45a3`
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
