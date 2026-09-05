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
