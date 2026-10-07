/**
 * @file m33_diagnostics_protocol_main.cpp
 * @brief 실제 firmware parser의 조각화·timeout·최대 길이·range 경계 시험.
 * SPDX-License-Identifier: MIT
 */
#include "protocol.h"
#include <cassert>

int main()
{
    diagnostic_parser parser{};
    uint16_t opcode = 0;
    const uint8_t raw_rx_command[] = {0x01, 0x1d, 0x20, 0x01, 19};
    assert(diagnostic_hci_command_opcode(raw_rx_command, sizeof(raw_rx_command), &opcode));
    assert(opcode == 0x201d);
    assert(!diagnostic_hci_command_opcode(raw_rx_command + 1, sizeof(raw_rx_command) - 1, &opcode));
    assert(!diagnostic_hci_command_opcode(raw_rx_command, sizeof(raw_rx_command) - 1, &opcode));
    assert(!diagnostic_feed(&parser, false, 0x40, 0));
    assert(diagnostic_feed(&parser, false, 0x13, 5));
    assert(parser.bytes[0] == 0x40 && parser.bytes[1] == 0x13);
    assert(!diagnostic_feed(&parser, false, 0x99, 10));
    assert(!diagnostic_feed(&parser, false, 0x40, 16));
    assert(diagnostic_feed(&parser, false, 0x13, 17));
    assert(parser.bytes[0] == 0x40);

    assert(!diagnostic_feed(&parser, true, 0x04, 20));
    const uint8_t valid[] = {0x01, 0x34, 0x20, 0x04, 39, 37, 0, 2};
    for (size_t index = 0; index < sizeof(valid); ++index)
    {
        assert(diagnostic_feed(&parser, true, valid[index], 21 + index) ==
               (index == sizeof(valid) - 1));
    }
    assert(diagnostic_hci_status(0x2034, &parser.bytes[4], parser.bytes[3]) == 0);
    assert(!diagnostic_feed(&parser, true, 1, 50));
    assert(!diagnostic_feed(&parser, true, 3, 51));
    for (size_t index = 0; index < sizeof(valid); ++index)
    {
        assert(diagnostic_feed(&parser, true, valid[index], 80 + index) ==
               (index == sizeof(valid) - 1));
    }

    const uint8_t maximum[] = {1, 0xff, 0xff, 255};
    for (uint8_t value : maximum)
    {
        assert(!diagnostic_feed(&parser, true, value, 100));
    }
    for (size_t index = 0; index < 255; ++index)
    {
        assert(diagnostic_feed(&parser, true, 0x7e, 101) == (index == 254));
    }
    assert(parser.used == 0);
    assert(diagnostic_hci_status(0xffff, &parser.bytes[4], 255) == 1);

    const uint8_t parameters[] = {39, 255, 7, 4};
    assert(diagnostic_hci_status(0x201e, parameters, 3) == 0);
    assert(diagnostic_hci_status(0x2034, parameters, 4) == 0);
    assert(diagnostic_hci_status(0x2034, parameters, 3) == 0x12);
    assert(diagnostic_hci_status(0x201f, parameters, 1) == 0x12);
    const uint8_t invalid_channel[] = {40};
    assert(diagnostic_hci_status(0x201d, invalid_channel, 1) == 0x12);
    assert(diagnostic_hci_status(0x201d, nullptr, 0) == 0x12);
    const uint8_t invalid_phy[] = {0, 0, 0, 5};
    assert(diagnostic_hci_status(0x2034, invalid_phy, 4) == 0x12);
    const uint8_t invalid_modulation[] = {0, 1, 2};
    assert(diagnostic_hci_status(0x2033, invalid_modulation, 3) == 0x12);
    assert(diagnostic_hci_status(0x0c03, nullptr, 0) == 0);
    assert(diagnostic_starts(0x2034));
    assert(!diagnostic_starts(0x201f));
    return 0;
}
