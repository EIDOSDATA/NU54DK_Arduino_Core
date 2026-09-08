/** @file @brief 별도 power image에서만 활성화하는 S UART 중계·System OFF 경계입니다. */
#pragma once
#include <cstdint>

namespace t13::power
{
    void initialize(std::uint32_t &sequence, std::uint32_t *nonce);
    void service();
    bool claimed();
    bool takeRequest(std::uint32_t *request);
    void remember(std::uint32_t sequence, const std::uint32_t *nonce);
    bool respond(const std::uint32_t *response);
    std::uint32_t command(std::uint32_t opcode, const std::uint32_t *args, std::uint32_t nargs,
                          std::uint32_t *out, std::uint32_t &count, bool from_peer);
} // namespace t13::power
