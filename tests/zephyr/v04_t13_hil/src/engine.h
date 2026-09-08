/** @file @brief T13의 실행 허가·지속 측정·종료와 mailbox 제어 경계입니다. */
#pragma once
#include "model.h"
#include <cstdint>

namespace t13
{
    bool claimed();
    bool running();
    void service();
    std::uint32_t command(std::uint32_t opcode, const std::uint32_t *args, std::uint32_t nargs,
                          std::uint32_t *out, std::uint32_t &count);
    bool serialPrepare(const Case &test, std::uint32_t seed);
    bool serialStart();
    void serialService();
    void serialQuiesce();
    bool serialStop();
    bool serialHealthy();
    bool serialDrained();
    void serialSnapshot(unsigned lane, std::uint32_t *out, std::uint32_t &count);
    bool streamPrepare(const Case &test, std::uint32_t seed);
    bool streamStart();
    void streamService();
    bool streamStop();
    bool streamHealthy();
    void streamSnapshot(unsigned stream, std::uint32_t *out, std::uint32_t &count);
    void initializeWiring();
    bool wiringClaimed();
    void wiringService();
    std::uint32_t wiringCommand(std::uint32_t opcode, const std::uint32_t *args,
                                std::uint32_t nargs, std::uint32_t *out, std::uint32_t &count);
    std::uint32_t physicalPin(unsigned role, unsigned net);
    std::uint32_t pinId(std::uint32_t physical);
} // namespace t13
