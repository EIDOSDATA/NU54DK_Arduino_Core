/**
 * @file SystemFabric.cpp
 * @brief TEMP와 WDT30/31 v0.4 후보 system API 구현입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <nucode/SystemFabric.h>

#include <zephyr/device.h>
#include <zephyr/devicetree.h>
#include <zephyr/drivers/sensor.h>
#include <zephyr/drivers/watchdog.h>
#include <zephyr/kernel.h>

#include <cstdint>

namespace nucode::arduino
{
    namespace
    {

        struct WatchdogContext
        {
            const device *driver{nullptr};
            int channel{-1};
            int last_error{0};
            std::uint8_t options{0U};
            bool configured{false};
            bool active{false};
        };

        K_MUTEX_DEFINE(system_fabric_mutex);

        int temperature_last_error = 0;
        WatchdogContext watchdog_contexts[] = {
            {DEVICE_DT_GET(DT_NODELABEL(wdt30))},
            {DEVICE_DT_GET(DT_NODELABEL(wdt31))},
        };

        [[nodiscard]] WatchdogContext *watchdogContext(std::uint8_t instance) noexcept
        {
            if (instance == 30U)
            {
                return &watchdog_contexts[0];
            }
            if (instance == 31U)
            {
                return &watchdog_contexts[1];
            }
            return nullptr;
        }

        [[nodiscard]] SystemFabricResult driverResult(int result) noexcept
        {
            if (result == 0)
            {
                return SystemFabricResult::success;
            }
            if (result == -ENOMEM)
            {
                return SystemFabricResult::resource_exhausted;
            }
            if (result == -EBUSY || result == -EALREADY)
            {
                return SystemFabricResult::wrong_state;
            }
            if (result == -EINVAL || result == -ENOTSUP)
            {
                return SystemFabricResult::invalid_argument;
            }
            return SystemFabricResult::driver_error;
        }

    } // namespace

    SystemFabricResult TemperatureFabric::readCentiCelsius(std::int32_t &temperature) noexcept
    {
        if (k_is_in_isr())
        {
            return SystemFabricResult::invalid_context;
        }

        const device *const driver = DEVICE_DT_GET(DT_NODELABEL(temp));
        if (!device_is_ready(driver))
        {
            temperature_last_error = -ENODEV;
            return SystemFabricResult::driver_unavailable;
        }

        k_mutex_lock(&system_fabric_mutex, K_FOREVER);
        sensor_value value{};
        int result = sensor_sample_fetch(driver);
        if (result == 0)
        {
            result = sensor_channel_get(driver, SENSOR_CHAN_DIE_TEMP, &value);
        }
        temperature_last_error = result;
        if (result == 0)
        {
            const std::int64_t micro_celsius =
                static_cast<std::int64_t>(value.val1) * 1000000LL + value.val2;
            temperature = static_cast<std::int32_t>(micro_celsius / 10000LL);
        }
        k_mutex_unlock(&system_fabric_mutex);
        return driverResult(result);
    }

    int TemperatureFabric::lastDriverError() const noexcept
    {
        k_mutex_lock(&system_fabric_mutex, K_FOREVER);
        const int result = temperature_last_error;
        k_mutex_unlock(&system_fabric_mutex);
        return result;
    }

    std::uint8_t WatchdogFabric::instance() const noexcept
    {
        return instance_;
    }

    bool WatchdogFabric::configured() const noexcept
    {
        k_mutex_lock(&system_fabric_mutex, K_FOREVER);
        const auto *const context = watchdogContext(instance_);
        const bool result = context != nullptr && context->configured;
        k_mutex_unlock(&system_fabric_mutex);
        return result;
    }

    bool WatchdogFabric::active() const noexcept
    {
        k_mutex_lock(&system_fabric_mutex, K_FOREVER);
        const auto *const context = watchdogContext(instance_);
        const bool result = context != nullptr && context->active;
        k_mutex_unlock(&system_fabric_mutex);
        return result;
    }

    int WatchdogFabric::lastDriverError() const noexcept
    {
        k_mutex_lock(&system_fabric_mutex, K_FOREVER);
        const auto *const context = watchdogContext(instance_);
        const int result = context != nullptr ? context->last_error : -ENODEV;
        k_mutex_unlock(&system_fabric_mutex);
        return result;
    }

    SystemFabricResult WatchdogFabric::configure(std::uint32_t timeout_ms, bool run_in_sleep,
                                                 bool run_in_halt) noexcept
    {
        if (k_is_in_isr())
        {
            return SystemFabricResult::invalid_context;
        }
        if (timeout_ms == 0U)
        {
            return SystemFabricResult::invalid_argument;
        }

        k_mutex_lock(&system_fabric_mutex, K_FOREVER);
        auto *const context = watchdogContext(instance_);
        if (context == nullptr)
        {
            k_mutex_unlock(&system_fabric_mutex);
            return SystemFabricResult::unsupported_instance;
        }
        if (!device_is_ready(context->driver))
        {
            context->last_error = -ENODEV;
            k_mutex_unlock(&system_fabric_mutex);
            return SystemFabricResult::driver_unavailable;
        }
        if (context->configured || context->active)
        {
            k_mutex_unlock(&system_fabric_mutex);
            return SystemFabricResult::wrong_state;
        }

        wdt_timeout_cfg timeout{};
        timeout.window.min = 0U;
        timeout.window.max = timeout_ms;
        timeout.callback = nullptr;
        timeout.flags = WDT_FLAG_RESET_SOC;
        const int channel = wdt_install_timeout(context->driver, &timeout);
        context->last_error = channel < 0 ? channel : 0;
        if (channel < 0)
        {
            k_mutex_unlock(&system_fabric_mutex);
            return driverResult(channel);
        }

        context->channel = channel;
        context->configured = true;
        context->active = false;
        std::uint8_t options = 0U;
        if (!run_in_sleep)
        {
            options |= WDT_OPT_PAUSE_IN_SLEEP;
        }
        if (!run_in_halt)
        {
            options |= WDT_OPT_PAUSE_HALTED_BY_DBG;
        }
        context->options = options;
        context->last_error = 0;
        k_mutex_unlock(&system_fabric_mutex);
        return SystemFabricResult::success;
    }

    SystemFabricResult WatchdogFabric::start() noexcept
    {
        if (k_is_in_isr())
        {
            return SystemFabricResult::invalid_context;
        }
        k_mutex_lock(&system_fabric_mutex, K_FOREVER);
        auto *const context = watchdogContext(instance_);
        if (context == nullptr)
        {
            k_mutex_unlock(&system_fabric_mutex);
            return SystemFabricResult::unsupported_instance;
        }
        if (!context->configured || context->active)
        {
            k_mutex_unlock(&system_fabric_mutex);
            return SystemFabricResult::wrong_state;
        }
        const int result = wdt_setup(context->driver, context->options);
        context->last_error = result;
        if (result == 0)
        {
            context->active = true;
        }
        k_mutex_unlock(&system_fabric_mutex);
        return driverResult(result);
    }

    SystemFabricResult WatchdogFabric::feed() noexcept
    {
        if (k_is_in_isr())
        {
            return SystemFabricResult::invalid_context;
        }
        k_mutex_lock(&system_fabric_mutex, K_FOREVER);
        auto *const context = watchdogContext(instance_);
        if (context == nullptr)
        {
            k_mutex_unlock(&system_fabric_mutex);
            return SystemFabricResult::unsupported_instance;
        }
        if (!context->active)
        {
            k_mutex_unlock(&system_fabric_mutex);
            return SystemFabricResult::wrong_state;
        }
        const int result = wdt_feed(context->driver, context->channel);
        context->last_error = result;
        k_mutex_unlock(&system_fabric_mutex);
        return driverResult(result);
    }

    SystemFabricResult WatchdogFabric::stop() noexcept
    {
        if (k_is_in_isr())
        {
            return SystemFabricResult::invalid_context;
        }
        k_mutex_lock(&system_fabric_mutex, K_FOREVER);
        auto *const context = watchdogContext(instance_);
        if (context == nullptr)
        {
            k_mutex_unlock(&system_fabric_mutex);
            return SystemFabricResult::unsupported_instance;
        }
        if (!context->configured)
        {
            k_mutex_unlock(&system_fabric_mutex);
            return SystemFabricResult::wrong_state;
        }
        const int result = context->active ? wdt_disable(context->driver) : 0;
        context->last_error = result;
        if (result == 0)
        {
            context->channel = -1;
            context->options = 0U;
            context->configured = false;
            context->active = false;
        }
        k_mutex_unlock(&system_fabric_mutex);
        return driverResult(result);
    }

    TemperatureFabric &SystemFabric::temperature() noexcept
    {
        static TemperatureFabric handle;
        return handle;
    }

    WatchdogFabric *SystemFabric::watchdog(std::uint8_t instance) noexcept
    {
        static WatchdogFabric handles[] = {WatchdogFabric(30U), WatchdogFabric(31U)};
        if (instance == 30U)
        {
            return &handles[0];
        }
        if (instance == 31U)
        {
            return &handles[1];
        }
        return nullptr;
    }

    SystemFabric &systemFabric() noexcept
    {
        static SystemFabric fabric;
        return fabric;
    }

} // namespace nucode::arduino
