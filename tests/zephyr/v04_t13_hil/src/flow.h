/** @file @brief 활성 UART의 PSEL을 바꾸지 않는 peer GPIO CTS 정지 주입 경계입니다. */
#pragma once
#include "model.h"

namespace t13
{
    bool flowPolicy(unsigned mode);
    bool flowPrepare(const Case &test, Endpoint &endpoint);
    bool flowStart();
    void flowService(std::uint32_t completed, bool pending);
    bool flowStop();
    void flowSnapshot(std::uint32_t *out, std::uint32_t &count);
} // namespace t13
