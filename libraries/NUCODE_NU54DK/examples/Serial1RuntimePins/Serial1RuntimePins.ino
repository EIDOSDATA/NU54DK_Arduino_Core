/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: Standard peripherals (`standard`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 1대 — 1) Serial1RuntimePins 실행 보드
 * @par Serial Monitor
 * 사용하지 않음
 * @par 필수 sidecar
 * 없음
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 추가 조건 없음
 * @par Metadata
 * identity `NUCODE_NU54DK/Serial1RuntimePins`, sha256 `2a9e6ac5df23f36f5f8a61d24eaa43c194b7346b971b7cfaa11d209619a849af`
 * @nucode_example_setup_end */

/**
 * @file Serial1RuntimePins.ino
 * @brief uart30 Serial1의 핀 선택과 begin/end 재시작 예제입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODEPeripheral.h>

/** @brief P0.1 RX와 P0.0 TX를 선택해 독립 UART를 시작합니다. */
void setup(void)
{
    if (!Serial1.setPins(PIN_P0_01, PIN_P0_00))
    {
        return;
    }
    Serial1.begin(115200U, SERIAL_8N1);
    Serial1.println("NU54 Serial1 ready");
}

/** @brief 수신 byte를 그대로 되돌려 보냅니다. */
void loop(void)
{
    if (Serial1.available() > 0)
    {
        Serial1.write(static_cast<uint8_t>(Serial1.read()));
    }
}
