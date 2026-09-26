/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: Standard peripherals (`standard`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 1대 — 1) WatchdogBasic 실행 보드
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * 없음
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * watchdog reset이 의도된 예제이므로 Serial 종료 메시지와 재부팅을 함께 확인합니다.
 * @par Metadata
 * identity `NUCODE_NU54DK/WatchdogBasic`, sha256 `6d3b851ab15e81ef827f3351da6c7294f958677eb41e477d8b3b40daf9beb32a`
 * @nucode_example_setup_end */

/**
 * @file WatchdogBasic.ino
 * @brief NU54DK WDT31을 시작하고 주기적으로 feed합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_NU54DK.h>

using nucode::nu54dk::Error;

namespace
{
    constexpr std::uint32_t watchdog_timeout_ms = 5000U;
    constexpr std::uint32_t feed_interval_ms = 1000U;
    std::uint32_t previous_feed_ms = 0U;
} // namespace

void setup()
{
    Serial.begin(115200);
    delay(200);
    const Error result = NU54DK.watchdogBegin(watchdog_timeout_ms);
    Serial.println((result == Error::none) ? "watchdog started" : "watchdog start failed");
}

void loop()
{
    const std::uint32_t now = millis();
    if ((now - previous_feed_ms) >= feed_interval_ms)
    {
        previous_feed_ms = now;
        Serial.println((NU54DK.watchdogFeed() == Error::none) ? "watchdog fed"
                                                              : "watchdog feed failed");
    }
}
