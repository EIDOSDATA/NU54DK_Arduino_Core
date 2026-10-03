/**
 * @file main.cpp
 * @brief M32-W09 ESB 공개 API target compile 계약입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_Radio_ESB.h>

/** @brief 공개 구조와 bounded lifecycle signature를 target compiler로 확인합니다. */
int main()
{
    nucode::esb::Configuration configuration{};
    nucode::esb::Packet packet{};
    const std::uint8_t payload[] = {0x45U, 0x53U};
    volatile bool execute_contract = false;
    if (execute_contract)
    {
        static_cast<void>(NUCODEEsb.begin(nucode::esb::Role::primary_transmitter,
                                          configuration));
        static_cast<void>(NUCODEEsb.send(1U, payload, sizeof(payload)));
        static_cast<void>(NUCODEEsb.available());
        static_cast<void>(NUCODEEsb.read(packet));
        static_cast<void>(NUCODEEsb.cancel());
        static_cast<void>(NUCODEEsb.busy());
        static_cast<void>(NUCODEEsb.statistics());
        static_cast<void>(NUCODEEsb.lastError());
        static_cast<void>(NUCODEEsb.lastDriverError());
        static_cast<void>(NUCODEEsb.stop());
    }
    return 0;
}
