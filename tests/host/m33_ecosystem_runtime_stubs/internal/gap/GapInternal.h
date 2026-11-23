#pragma once
#include <NUCODE_BLE.h>

namespace nucode::ble::internal::gap
{
    inline unsigned companion_stub_advertising_starts;
    inline unsigned companion_stub_advertising_stops;

    inline void legacyAdvertisingStarted() noexcept
    {
        companion_stub_advertising_running = true;
        ++companion_stub_advertising_starts;
    }

    inline void legacyAdvertisingStopped() noexcept
    {
        companion_stub_advertising_running = false;
        ++companion_stub_advertising_stops;
    }
} // namespace nucode::ble::internal::gap
