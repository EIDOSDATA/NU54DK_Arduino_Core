/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: Standard peripherals (`standard`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 1대 — 1) WireRuntimePins 실행 보드
 * @par Serial Monitor
 * 사용하지 않음
 * @par 필수 sidecar
 * 없음
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI `--upload-field probe_id=<UID>`로 명시 선택합니다.
 * @par 추가 조건
 * 추가 조건 없음
 * @par Metadata
 * identity `NUCODE_NU54DK/WireRuntimePins`, sha256 `757c4213a0707f98ea1d6632e7b0aaeade2d2a774c3a63d53b2bfd41f0d451ef`
 * @nucode_example_setup_end */

/**
 * @file WireRuntimePins.ino
 * @brief TWIM22 controller의 runtime SDA/SCL 선택 예제입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <Wire.h>

/** @brief P1.2 SDA와 P1.3 SCL을 400 kHz controller로 시작합니다. */
void setup(void)
{
    if (!Wire.setPins(PIN_P1_02, PIN_P1_03))
    {
        return;
    }
    Wire.begin();
    Wire.setClock(400000U);
}

/** @brief 예제는 bus를 점유하지 않고 lifecycle만 유지합니다. */
void loop(void)
{
    delay(1000U);
}
