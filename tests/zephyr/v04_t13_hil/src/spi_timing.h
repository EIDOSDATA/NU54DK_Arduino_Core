/** @file @brief S 역할 전환의 제한된 SPI 타이밍 진단 선택을 정의합니다. */
#pragma once
#include "model.h"

namespace t13
{
    bool spiTimingPolicy(unsigned mode);
    bool spiTimingCase(Case &test);
    bool spiTimingConfigured(const Endpoint &endpoint);
    void spiTimingSnapshot(const Endpoint &endpoint, std::uint32_t *out);
} // namespace t13
