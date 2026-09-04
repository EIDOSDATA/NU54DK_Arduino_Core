/**
 * @file main.cpp
 * @brief M21 BLE security·BAS·DIS·HID 공개 표면과 NCS backend link를 검증합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE_Security.h>
#include <internal/NUCODE_BLE_Internal.h>

#include <cstdint>

/** @brief callback 형식과 event snapshot을 build graph에 고정합니다. */
void onSecurityEvent(const nucode::ble::SecurityEventRecord &event, void *context)
{
    volatile std::uint8_t *observed = static_cast<volatile std::uint8_t *>(context);
    if (observed != nullptr)
    {
        *observed = static_cast<std::uint8_t>(event.event);
    }
}

int main()
{
    volatile std::uint8_t observed = 0U;
    BLESecurity.onEvent(onSecurityEvent, const_cast<std::uint8_t *>(&observed));

    nucode::ble::SecurityConfig config = {};
    config.minimum_level = nucode::ble::SecurityLevel::encrypted;
    static_cast<void>(BLESecurity.begin(config));
    static_cast<void>(BLESecurity.requestSecurity());
    static_cast<void>(BLESecurity.bondCount());
    static_cast<void>(BLESecurity.bondState());
    static_cast<void>(BLESecurity.currentLevel());
    static_cast<void>(BLESecurity.lastError());
    static_cast<void>(BLESecurity.lastDriverError());

    const nucode::ble::DeviceInformation information = {"NUCODE", "NU54DK-M21", "TEST",
                                                        "0.3.0",  "NU54DK",     "0.3.0"};
    static_cast<void>(BLEDeviceInformation.configure(information));
    static_cast<void>(BLEBattery.setLevel(73U));
    static_cast<void>(BLEKeyboard.begin());
    static_cast<void>(BLEKeyboard.press(0x04U));
    static_cast<void>(BLEKeyboard.press(0x66U));
    static_cast<void>(BLEKeyboard.releaseAll());
    return 0;
}
