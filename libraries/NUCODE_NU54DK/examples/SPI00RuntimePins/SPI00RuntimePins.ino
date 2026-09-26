/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: Standard peripherals (`standard`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 1대 — 1) SPI00RuntimePins 실행 보드
 * @par Serial Monitor
 * 사용하지 않음
 * @par 필수 sidecar
 * 없음
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 추가 조건 없음
 * @par Metadata
 * identity `NUCODE_NU54DK/SPI00RuntimePins`, sha256 `5ef0196e97d425e17bf15e3c73d2ae06a7dfcb6352613b5c924a7aed9c762269`
 * @nucode_example_setup_end */

/**
 * @file SPI00RuntimePins.ino
 * @brief SPI00 전용 SCK/MISO/MOSI route와 transaction 예제입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <SPI.h>

/** @brief nRF54L15 SPI00 고정 route P2.1/P2.4/P2.2를 시작합니다. */
void setup(void)
{
    if (!SPI.setPins(PIN_P2_01, PIN_P2_04, PIN_P2_02))
    {
        return;
    }
    SPI.begin();
}

/** @brief 외부 CS 없이 한 byte loopback transaction을 실행합니다. */
void loop(void)
{
    SPI.beginTransaction(SPISettings(4000000U, MSBFIRST, SPI_MODE0));
    static_cast<void>(SPI.transfer(0xA5U));
    SPI.endTransaction();
    delay(1000U);
}
