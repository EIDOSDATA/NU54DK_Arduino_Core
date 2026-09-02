/**
 * @file main.cpp
 * @brief NU54DK board/system과 M21 BLE security의 ZMS 동시 link 계약을 검증합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE_Security.h>
#include <NUCODE_NU54DK.h>

#include <cstdint>
#include <string.h>

int main()
{
    const char *const model = NU54DK.boardModel();
    if (model == nullptr || ::strcmp(model, "NU54DK") != 0)
    {
        return 1;
    }

    nucode::ble::SecurityConfig security = {};
    security.minimum_level = nucode::ble::SecurityLevel::encrypted;
    static_cast<void>(BLESecurity.begin(security));
    static_cast<void>(BLESecurity.bondCount());
    static_cast<void>(BLESecurity.bondState());
    static_cast<void>(NU54DK.storageBegin());
    return 0;
}
