/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: Standard peripherals (`standard`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 1대 — 1) BoardInfo 실행 보드
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * 없음
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI `--upload-field probe_id=<UID>`로 명시 선택합니다.
 * @par 추가 조건
 * 추가 조건 없음
 * @par Metadata
 * identity `NUCODE_NU54DK/BoardInfo`, sha256 `755e0a124515bdb9908640f15469b23bff08d4e4e6f96cf417aa97ec5966465d`
 * @nucode_example_setup_end */

/**
 * @file BoardInfo.ino
 * @brief NU54DK 모델, target, device ID와 reset 원인을 출력합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_NU54DK.h>

#include <stdio.h>

using nucode::nu54dk::Error;
using nucode::nu54dk::ResetReport;

void setup()
{
    Serial.begin(115200);
    delay(200);

    char device_id[33] = {};
    ResetReport reset{};

    Serial.println("NU54DK board information");
    Serial.print("model: ");
    Serial.println(NU54DK.boardModel());
    Serial.print("target: ");
    Serial.println(NU54DK.boardTarget());
    Serial.print("soc: ");
    Serial.println(NU54DK.socName());
    Serial.print("NCS: ");
    Serial.println(NU54DK.ncsVersion());
    Serial.print("Zephyr: ");
    Serial.println(NU54DK.zephyrVersion());
    Serial.print("Core source: ");
    Serial.println(NU54DK.coreVersion());

    if (NU54DK.deviceId(device_id, sizeof(device_id)) == Error::none)
    {
        Serial.print("raw device ID: ");
        Serial.println(device_id);
    }
    if (NU54DK.resetReport(reset) == Error::none)
    {
        char report[80] = {};
        snprintf(report, sizeof(report), "reset cause=0x%08lx supported=0x%08lx",
                 static_cast<unsigned long>(reset.cause),
                 static_cast<unsigned long>(reset.supported));
        Serial.println(report);
    }
}

void loop()
{
    delay(1000);
}
