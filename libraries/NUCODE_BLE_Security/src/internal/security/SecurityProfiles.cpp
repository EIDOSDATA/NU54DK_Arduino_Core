/**
 * @file SecurityProfiles.cpp
 * @brief 표준 HRS와 ESS의 bounded Arduino facade를 구현합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#if !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE)

#include "SecurityInternal.h"

#include <internal/NUCODE_BLE_ProfilesBackend.h>

#include <zephyr/bluetooth/services/hrs.h>

namespace nucode::ble::internal::security
{
    namespace
    {
        atomic_t heart_rate_value = ATOMIC_INIT(0);
        atomic_t heart_rate_error = ATOMIC_INIT(static_cast<atomic_val_t>(SecurityError::none));
        atomic_t environmental_error =
            ATOMIC_INIT(static_cast<atomic_val_t>(SecurityError::none));

        /** @brief ISR·인자·driver 결과를 공통 profile 오류로 변환합니다. */
        bool profileResult(atomic_t &error_value, int result) noexcept
        {
            atomic_set(&error_value,
                       static_cast<atomic_val_t>(result < 0 ? SecurityError::driver_error
                                                            : SecurityError::none));
            return result >= 0;
        }
    } // namespace
} // namespace nucode::ble::internal::security

namespace nucode::ble
{
    using namespace internal::security;

    bool HeartRateService::setRate(std::uint16_t beats_per_minute) noexcept
    {
        if (k_is_in_isr())
        {
            atomic_set(&heart_rate_error,
                       static_cast<atomic_val_t>(SecurityError::invalid_context));
            return false;
        }
        if (beats_per_minute == 0U || beats_per_minute > 240U)
        {
            atomic_set(&heart_rate_error,
                       static_cast<atomic_val_t>(SecurityError::invalid_argument));
            return false;
        }
        const int result = bt_hrs_notify(beats_per_minute);
        if (result >= 0)
        {
            atomic_set(&heart_rate_value, beats_per_minute);
        }
        return profileResult(heart_rate_error, result);
    }

    std::uint16_t HeartRateService::rate() const noexcept
    {
        return static_cast<std::uint16_t>(atomic_get(&heart_rate_value));
    }

    SecurityError HeartRateService::lastError() const noexcept
    {
        return static_cast<SecurityError>(atomic_get(&heart_rate_error));
    }

    bool EnvironmentalSensingService::setTemperature(
        std::int16_t hundredths_celsius) noexcept
    {
        if (k_is_in_isr())
        {
            atomic_set(&environmental_error,
                       static_cast<atomic_val_t>(SecurityError::invalid_context));
            return false;
        }
        return profileResult(environmental_error,
                             nucode_ble_ess_set_temperature(hundredths_celsius));
    }

    std::int16_t EnvironmentalSensingService::temperature() const noexcept
    {
        return nucode_ble_ess_get_temperature();
    }

    bool EnvironmentalSensingService::setHumidity(
        std::uint16_t hundredths_percent) noexcept
    {
        if (k_is_in_isr())
        {
            atomic_set(&environmental_error,
                       static_cast<atomic_val_t>(SecurityError::invalid_context));
            return false;
        }
        if (hundredths_percent > 10000U)
        {
            atomic_set(&environmental_error,
                       static_cast<atomic_val_t>(SecurityError::invalid_argument));
            return false;
        }
        return profileResult(environmental_error,
                             nucode_ble_ess_set_humidity(hundredths_percent));
    }

    std::uint16_t EnvironmentalSensingService::humidity() const noexcept
    {
        return nucode_ble_ess_get_humidity();
    }

    SecurityError EnvironmentalSensingService::lastError() const noexcept
    {
        return static_cast<SecurityError>(atomic_get(&environmental_error));
    }
} // namespace nucode::ble

nucode::ble::HeartRateService BLEHeartRate;
nucode::ble::EnvironmentalSensingService BLEEnvironmentalSensing;

#endif
