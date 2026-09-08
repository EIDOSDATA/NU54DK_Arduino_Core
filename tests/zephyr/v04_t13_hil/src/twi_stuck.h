/** @file @brief staged TWIM과 별도 SDA open-drain GPIO의 유한 복구 시험입니다. */
#pragma once
#include "model.h"
#include <nucode/SerialFabric.h>

namespace t13
{
    bool twiStuckPolicy(unsigned mode);
    bool twiStuckEnabled();
    bool twiStuckSelection(const Case &test, const Endpoint &endpoint);
    bool twiStuckPrepare(const Endpoint &endpoint, nucode::arduino::SerialFabricHandle &handle,
                         const Buffer *tx, const Buffer *rx);
    bool twiStuckStart();
    bool twiStuckRecover(unsigned attempt);
    void twiStuckService();
    bool twiStuckStop();
    bool twiStuckStaged(const nucode::arduino::SerialFabricHandle &handle);
    void twiStuckSnapshot(unsigned page, std::uint32_t *out, std::uint32_t &count);
} // namespace t13
