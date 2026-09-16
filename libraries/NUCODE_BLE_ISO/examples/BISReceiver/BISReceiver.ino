/**
 * @file BISReceiver.ino
 * @brief NU54DK BISReceiver 역할을 NUCODE BLE ISO API로 실행합니다.
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE_ISO.h>

using nucode::ble::iso::Error;
using nucode::ble::iso::Program;
using nucode::ble::iso::Role;

Program isoProgram(Role::bis_receiver);
bool isoReady = false;

/** @brief 역할별 ISO 프로그램을 초기화합니다. */
void setup()
{
    isoReady = isoProgram.begin() == Error::none;
    if (!isoReady)
    {
        Serial.println("ISO initialization failed");
    }
}

/** @brief ISO callback 뒤의 main-thread 작업을 계속 처리합니다. */
void loop()
{
    if (isoReady)
    {
        isoProgram.poll();
    }
    delay(1);
}
