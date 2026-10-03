/**
 * @file main.cpp
 * @brief M32-W09 IEEE 802.15.4 공개 API target compile 계약입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_Radio_IEEE802154.h>

/** @brief 공개 구조와 bounded lifecycle signature를 target compiler로 확인합니다. */
int main()
{
    nucode::radio154::Configuration configuration{};
    nucode::radio154::Packet packet{};
    const std::uint8_t payload[] = {0x4EU, 0x55U};
    volatile bool execute_contract = false;
    if (execute_contract)
    {
        static_cast<void>(NUCODERadio154.begin(nucode::radio154::Role::transmitter,
                                               configuration));
        static_cast<void>(NUCODERadio154.send(1U, payload, sizeof(payload)));
        static_cast<void>(NUCODERadio154.available());
        static_cast<void>(NUCODERadio154.read(packet));
        static_cast<void>(NUCODERadio154.cancel());
        static_cast<void>(NUCODERadio154.busy());
        static_cast<void>(NUCODERadio154.statistics());
        static_cast<void>(NUCODERadio154.lastError());
        static_cast<void>(NUCODERadio154.lastDriverError());
        static_cast<void>(NUCODERadio154.stop());
    }
    return 0;
}
