/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: Standard peripherals (`standard`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 1대 — 1) SystemOffWake 실행 보드
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * 없음
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * System OFF wake source와 버튼 조건을 확인합니다.
 * @par Metadata
 * identity `NUCODE_NU54DK/SystemOffWake`, sha256 `ce969e1e43f26ce50990e28651081295bf9118951dcc3ee1cba838a9583bdc18`
 * @nucode_example_setup_end */

/**
 * @file SystemOffWake.ino
 * @brief 명령을 받은 뒤 SW0 또는 GRTC wake를 설정하고 System OFF로 진입합니다.
 *
 * Serial Monitor에서 `BUTTON`을 보내면 SW0(P1.13), `TIMER`를 보내면
 * 2초 GRTC wake를 사용합니다. 부팅 직후 자동으로 전원이 꺼지지 않습니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_NU54DK.h>

#include <stdio.h>
#include <string.h>

using nucode::nu54dk::Error;
using nucode::nu54dk::ResetReport;
using nucode::nu54dk::WakeButton;

namespace
{
    char command[16] = {};
    std::size_t command_length = 0U;

    /** @brief System OFF API가 오류로 반환한 경우 결과를 출력합니다. */
    void reportUnexpectedReturn(Error result)
    {
        Serial.println((result == Error::none) ? "unexpected return" : "System OFF rejected");
    }

    /** @brief 한 줄의 대문자 명령을 실행합니다. */
    void executeCommand()
    {
        command[command_length] = '\0';
        if (strcmp(command, "BUTTON") == 0)
        {
            Serial.println("press SW0 (P1.13) to wake");
            Serial.println("entering System OFF");
            Serial.flush();
            delay(50);
            reportUnexpectedReturn(NU54DK.enterSystemOffOnButton(WakeButton::sw0));
        }
        else if (strcmp(command, "TIMER") == 0)
        {
            Serial.println("GRTC wake in 2 seconds");
            Serial.println("entering System OFF");
            Serial.flush();
            delay(50);
            reportUnexpectedReturn(NU54DK.enterSystemOffAfter(2000000ULL));
        }
        else if (command_length != 0U)
        {
            Serial.println("send BUTTON or TIMER");
        }
        command_length = 0U;
    }
} // namespace

void setup()
{
    Serial.begin(115200);
    delay(200);
    ResetReport reset{};
    if (NU54DK.resetReport(reset) == Error::none)
    {
        char message[48] = {};
        snprintf(message, sizeof(message), "boot reset cause=0x%08lx",
                 static_cast<unsigned long>(reset.cause));
        Serial.println(message);
    }
    Serial.println("send BUTTON or TIMER");
}

void loop()
{
    while (Serial.available() > 0)
    {
        const int character = Serial.read();
        if ((character == '\r') || (character == '\n'))
        {
            executeCommand();
        }
        else if ((character >= 0) && (command_length < (sizeof(command) - 1U)))
        {
            command[command_length++] = static_cast<char>(character);
        }
    }
    delay(10);
}
