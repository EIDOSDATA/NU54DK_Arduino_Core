/** @file @brief BAS battery 값과 오류를 소유합니다.
 * SPDX-License-Identifier: MIT
 */
#if !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE)
#include "SecurityInternal.h"
#include <zephyr/bluetooth/services/bas.h>
namespace nucode::ble::internal::security
{
    namespace
    {
        atomic_t battery_error_value = ATOMIC_INIT(static_cast<atomic_val_t>(SecurityError::none));
    }
} // namespace nucode::ble::internal::security
namespace nucode::ble
{
    using namespace internal::security;
    bool BatteryService::setLevel(std::uint8_t percent) noexcept
    {
        if (k_is_in_isr())
        {
            atomic_set(&battery_error_value,
                       static_cast<atomic_val_t>(SecurityError::invalid_context));
            return false;
        }
        if (percent > 100U)
        {
            atomic_set(&battery_error_value,
                       static_cast<atomic_val_t>(SecurityError::invalid_argument));
            return false;
        }
        const int result = bt_bas_set_battery_level(percent);
        atomic_set(&battery_error_value,
                   static_cast<atomic_val_t>(result < 0 ? SecurityError::driver_error
                                                        : SecurityError::none));
        return result >= 0;
    }

    std::uint8_t BatteryService::level() const noexcept
    {
        return bt_bas_get_battery_level();
    }

    SecurityError BatteryService::lastError() const noexcept
    {
        return static_cast<SecurityError>(atomic_get(&battery_error_value));
    }

} // namespace nucode::ble
nucode::ble::BatteryService BLEBattery;
#endif
