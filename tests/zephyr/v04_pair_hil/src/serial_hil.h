// SPDX-License-Identifier: MIT
#pragma once
#include <cstdint>
void initializeOnboardSerialIdle();
void serviceSerial();
std::uint32_t serialOnboard(std::uint32_t opcode, const std::uint32_t *args,
                            std::uint32_t nargs, std::uint32_t *out, std::uint32_t &count);
