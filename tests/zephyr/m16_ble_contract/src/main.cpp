/**
 * @file main.cpp
 * @brief M16 NUS Stream 공개 표면이 production backend와 link되는지 검증합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE.h>

#include <cstdint>

/** @brief callback 형식과 event enum을 build graph에 고정합니다. */
void onBleEvent(nucode::ble::Event event, void *context)
{
    volatile std::uint8_t *observed = static_cast<volatile std::uint8_t *>(context);
    if (observed != nullptr)
    {
        *observed = static_cast<std::uint8_t>(event);
    }
}

int main()
{
    volatile std::uint8_t observed = 0U;
    BLESerial.onEvent(onBleEvent, const_cast<std::uint8_t *>(&observed));
    static_cast<void>(BLESerial.connected());
    static_cast<void>(BLESerial.ready());
    static_cast<void>(BLESerial.mtu());
    static_cast<void>(BLESerial.droppedRxBytes());
    static_cast<void>(BLESerial.lastError());
    static_cast<void>(BLESerial.lastDriverError());
    return 0;
}

