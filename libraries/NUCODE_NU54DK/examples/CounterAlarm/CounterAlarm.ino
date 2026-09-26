/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: Standard peripherals (`standard`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 1대 — 1) CounterAlarm 실행 보드
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * 없음
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI `--upload-field probe_id=<UID>`로 명시 선택합니다.
 * @par 추가 조건
 * 추가 조건 없음
 * @par Metadata
 * identity `NUCODE_NU54DK/CounterAlarm`, sha256 `c5d7daae92a4700173389d4659916b6184837f93db899da1b40f528e494d17b4`
 * @nucode_example_setup_end */

/**
 * @file CounterAlarm.ino
 * @brief GRTC absolute counter와 one-shot alarm을 사용합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_NU54DK.h>

#include <stdio.h>

using nucode::nu54dk::Error;

namespace
{
    /** @brief system work queue에서 alarm 완료 시각을 출력합니다. */
    void onAlarm(std::uint64_t scheduled_ticks, void *context)
    {
        (void)context;
        char message[64] = {};
        snprintf(message, sizeof(message), "alarm fired at tick=%llu",
                 static_cast<unsigned long long>(scheduled_ticks));
        Serial.println(message);
    }
} // namespace

void setup()
{
    Serial.begin(115200);
    delay(200);

    char message[96] = {};
    snprintf(message, sizeof(message), "GRTC frequency=%lu Hz current=%llu",
             static_cast<unsigned long>(NU54DK.hardwareCounterFrequency()),
             static_cast<unsigned long long>(NU54DK.hardwareCounterTicks()));
    Serial.println(message);

    const Error result = NU54DK.alarmAfterMicroseconds(2000000ULL, onAlarm);
    Serial.println((result == Error::none) ? "alarm scheduled" : "alarm schedule failed");
}

void loop()
{
    delay(100);
}
