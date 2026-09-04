/**
 * @file NUCODE_NU54DK.cpp
 * @brief NU54DK 보드·시스템·BQ25186 Arduino API를 구현합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include "NUCODE_NU54DK.h"

#include <ctype.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>

#include <zephyr/device.h>
#include <zephyr/devicetree.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/drivers/hwinfo.h>
#include <zephyr/drivers/timer/nrf_grtc_timer.h>
#include <zephyr/drivers/watchdog.h>
#include <zephyr/kernel.h>
#include <zephyr/settings/settings.h>
#include <zephyr/sys/atomic.h>
#include <zephyr/sys/poweroff.h>
#include <zephyr/version.h>

namespace nucode::nu54dk
{
    namespace
    {
        constexpr char settings_prefix[] = "nucode/";
        constexpr std::size_t maximum_settings_key_length = 48U;
        constexpr std::size_t maximum_settings_value_length = 256U;
        constexpr std::uint8_t pmic_address = 0x6AU;
        constexpr std::uint8_t bq25186_device_id = 0x01U;
        constexpr std::uint64_t maximum_alarm_delay_us = 24ULL * 60ULL * 60ULL * 1000000ULL;

        enum class PmicRegister : std::uint8_t
        {
            status0 = 0x00U,
            vbat_control = 0x03U,
            charge_current_control = 0x04U,
            ic_control = 0x07U,
            ship_reset = 0x09U,
            system_regulation = 0x0AU,
            mask_id = 0x0CU,
        };

        K_MUTEX_DEFINE(system_mutex);
        K_MUTEX_DEFINE(storage_mutex);
        K_MUTEX_DEFINE(pmic_mutex);

        atomic_t last_error_value = ATOMIC_INIT(static_cast<atomic_val_t>(Error::none));
        atomic_t last_driver_error_value = ATOMIC_INIT(0);
        atomic_t watchdog_running_value = ATOMIC_INIT(0);
        atomic_t alarm_state = ATOMIC_INIT(0);
        atomic_t pmic_writes_authorized = ATOMIC_INIT(0);
        atomic_t pmic_watchdog_policy_confirmed = ATOMIC_INIT(0);

        bool storage_started = false;
        bool pmic_started = false;
        int32_t alarm_channel = -1;
        std::uint64_t alarm_expiration_ticks = 0U;
        AlarmCallback alarm_callback = nullptr;
        void *alarm_callback_context = nullptr;

#if DT_NODE_HAS_STATUS(DT_ALIAS(watchdog0), okay)
        int watchdog_channel = -1;
        const device *const watchdog_device = DEVICE_DT_GET(DT_ALIAS(watchdog0));
#endif

        const gpio_dt_spec sw0 = GPIO_DT_SPEC_GET(DT_ALIAS(sw0), gpios);
        const gpio_dt_spec sw1 = GPIO_DT_SPEC_GET(DT_ALIAS(sw1), gpios);
        const gpio_dt_spec sw2 = GPIO_DT_SPEC_GET(DT_ALIAS(sw2), gpios);
        const gpio_dt_spec sw3 = GPIO_DT_SPEC_GET(DT_ALIAS(sw3), gpios);

        /** @brief 마지막 공개 오류와 원래 driver 오류를 함께 기록합니다. */
        Error recordError(Error error, int driver_error = 0) noexcept
        {
            atomic_set(&last_error_value, static_cast<atomic_val_t>(error));
            atomic_set(&last_driver_error_value, static_cast<atomic_val_t>(driver_error));
            return error;
        }

        /** @brief errno를 공개 오류 분류로 변환합니다. */
        Error recordDriverError(int result) noexcept
        {
            switch (result)
            {
            case -EINVAL:
                return recordError(Error::invalid_argument, result);
            case -ENOTSUP:
            case -ENOSYS:
            case -EPERM:
                return recordError(Error::unsupported, result);
            case -ENODEV:
                return recordError(Error::device_not_ready, result);
            case -EALREADY:
                return recordError(Error::already_started, result);
            case -EBUSY:
            case -EAGAIN:
            case -ENOMEM:
                return recordError(Error::busy, result);
            case -ENOENT:
                return recordError(Error::not_found, result);
            default:
                return recordError(Error::driver_error, result);
            }
        }

        /** @brief thread 문맥만 허용하는 API의 공통 검증입니다. */
        bool isThreadContext() noexcept
        {
            if (k_is_in_isr())
            {
                recordError(Error::invalid_context, -EWOULDBLOCK);
                return false;
            }
            return true;
        }

        /** @brief Settings key를 한 namespace의 안전한 경로로 만듭니다. */
        Error makeSettingsPath(const char *key, char *path, std::size_t capacity) noexcept
        {
            if ((key == nullptr) || (path == nullptr))
            {
                return recordError(Error::invalid_argument, -EINVAL);
            }

            const std::size_t key_length = strlen(key);
            if ((key_length == 0U) || (key_length > maximum_settings_key_length))
            {
                return recordError(Error::invalid_argument, -EINVAL);
            }
            for (std::size_t index = 0U; index < key_length; ++index)
            {
                const unsigned char character = static_cast<unsigned char>(key[index]);
                if ((isalnum(character) == 0) && (character != '_') && (character != '-') &&
                    (character != '.'))
                {
                    return recordError(Error::invalid_argument, -EINVAL);
                }
            }

            const int written = snprintf(path, capacity, "%s%s", settings_prefix, key);
            if ((written < 0) || (static_cast<std::size_t>(written) >= capacity))
            {
                return recordError(Error::buffer_too_small, -ENOMEM);
            }
            return recordError(Error::none);
        }

        /** @brief alarm ISR에서 Arduino callback을 system work queue로 전달합니다. */
        void alarmWorkHandler(k_work *work);
        K_WORK_DEFINE(alarm_work, alarmWorkHandler);

        /** @brief GRTC ISR에서는 만료 tick 저장과 work 제출만 수행합니다. */
        void alarmInterruptHandler(int32_t channel, std::uint64_t expiration_ticks, void *user_data)
        {
            ARG_UNUSED(channel);
            ARG_UNUSED(user_data);
            if (atomic_cas(&alarm_state, 1, 2))
            {
                alarm_expiration_ticks = expiration_ticks;
                static_cast<void>(k_work_submit(&alarm_work));
            }
        }

        /** @brief 완료된 channel을 반환한 뒤 사용자 callback을 thread에서 실행합니다. */
        void alarmWorkHandler(k_work *work)
        {
            ARG_UNUSED(work);
            AlarmCallback callback = nullptr;
            void *context = nullptr;
            std::uint64_t expiration = 0U;

            static_cast<void>(k_mutex_lock(&system_mutex, K_FOREVER));
            if (atomic_get(&alarm_state) == 2)
            {
                if (alarm_channel >= 0)
                {
                    z_nrf_grtc_timer_chan_free(alarm_channel);
                    alarm_channel = -1;
                }
                callback = alarm_callback;
                context = alarm_callback_context;
                expiration = alarm_expiration_ticks;
                alarm_callback = nullptr;
                alarm_callback_context = nullptr;
                atomic_set(&alarm_state, 0);
            }
            static_cast<void>(k_mutex_unlock(&system_mutex));

            if (callback != nullptr)
            {
                callback(expiration, context);
            }
        }

        /** @brief 선택된 WakeButton에 대응하는 DTS GPIO를 반환합니다. */
        const gpio_dt_spec *wakeButtonSpec(WakeButton button) noexcept
        {
            switch (button)
            {
            case WakeButton::sw0:
                return &sw0;
            case WakeButton::sw1:
                return &sw1;
            case WakeButton::sw2:
                return &sw2;
            case WakeButton::sw3:
                return &sw3;
            default:
                return nullptr;
            }
        }

        /** @brief Wire repeated-start로 BQ25186 register 하나를 읽습니다. */
        int pmicReadRegister(PmicRegister reg, std::uint8_t &value) noexcept
        {
            Wire.beginTransmission(pmic_address);
            if (Wire.write(static_cast<std::uint8_t>(reg)) != 1U)
            {
                return -EIO;
            }
            if (Wire.endTransmission(false) != 0U)
            {
                return -EIO;
            }
            if (Wire.requestFrom(pmic_address, 1U) != 1U)
            {
                return -EIO;
            }
            const int read = Wire.read();
            if (read < 0)
            {
                return -EIO;
            }
            value = static_cast<std::uint8_t>(read);
            return 0;
        }

        /** @brief BQ25186 register 하나를 명시적으로 씁니다. */
        int pmicWriteRegister(PmicRegister reg, std::uint8_t value) noexcept
        {
            Wire.beginTransmission(pmic_address);
            if ((Wire.write(static_cast<std::uint8_t>(reg)) != 1U) || (Wire.write(value) != 1U))
            {
                return -EIO;
            }
            return (Wire.endTransmission(true) == 0U) ? 0 : -EIO;
        }

        /** @brief reserved bit를 보존하는 BQ25186 read-modify-write입니다. */
        int pmicUpdateRegister(PmicRegister reg, std::uint8_t mask, std::uint8_t value) noexcept
        {
            std::uint8_t current = 0U;
            int result = pmicReadRegister(reg, current);
            if (result < 0)
            {
                return result;
            }
            const std::uint8_t updated =
                static_cast<std::uint8_t>((current & ~mask) | (value & mask));
            return pmicWriteRegister(reg, updated);
        }

        /** @brief pmic_mutex를 잡은 상태에서 PMIC 접근 시작 여부를 검사합니다. */
        Error requirePmicStartedLocked() noexcept
        {
            return pmic_started ? Error::none : recordError(Error::not_started, -EACCES);
        }

        /** @brief 승인과 watchdog 정책을 같은 PMIC 임계구역에서 검사하고 RMW합니다. */
        Error mutatePmicRegister(PmicRegister reg, std::uint8_t mask, std::uint8_t value,
                                 bool require_watchdog_policy,
                                 bool confirms_watchdog_policy) noexcept
        {
            if (!isThreadContext())
            {
                return Error::invalid_context;
            }
            static_cast<void>(k_mutex_lock(&pmic_mutex, K_FOREVER));
            if (requirePmicStartedLocked() != Error::none)
            {
                static_cast<void>(k_mutex_unlock(&pmic_mutex));
                return Error::not_started;
            }
            if (atomic_get(&pmic_writes_authorized) == 0)
            {
                static_cast<void>(k_mutex_unlock(&pmic_mutex));
                return recordError(Error::permission_denied, -EACCES);
            }
            if (require_watchdog_policy && (atomic_get(&pmic_watchdog_policy_confirmed) == 0))
            {
                static_cast<void>(k_mutex_unlock(&pmic_mutex));
                return recordError(Error::configuration_required, -EACCES);
            }

            const int result = pmicUpdateRegister(reg, mask, value);
            if ((result == 0) && confirms_watchdog_policy)
            {
                atomic_set(&pmic_watchdog_policy_confirmed, 1);
            }
            static_cast<void>(k_mutex_unlock(&pmic_mutex));
            return (result == 0) ? recordError(Error::none) : recordDriverError(result);
        }
    } // namespace

    const char *BoardSystem::boardModel() const noexcept
    {
        return "NUCODE NU54DK nRF54L15 Application MCU";
    }

    const char *BoardSystem::boardTarget() const noexcept
    {
        return CONFIG_BOARD_TARGET;
    }

    const char *BoardSystem::socName() const noexcept
    {
        return CONFIG_SOC;
    }

    const char *BoardSystem::ncsVersion() const noexcept
    {
        return "3.4.0";
    }

    const char *BoardSystem::zephyrVersion() const noexcept
    {
        return KERNEL_VERSION_STRING;
    }

    const char *BoardSystem::coreVersion() const noexcept
    {
        return "0.2.0-dev";
    }

    Error BoardSystem::deviceId(char *destination, std::size_t destination_size) noexcept
    {
        if (!isThreadContext())
        {
            return Error::invalid_context;
        }
        if (destination == nullptr)
        {
            return recordError(Error::invalid_argument, -EINVAL);
        }
        std::uint8_t identifier[16] = {};
        const ssize_t length = hwinfo_get_device_id(identifier, sizeof(identifier));
        if (length < 0)
        {
            return recordDriverError(static_cast<int>(length));
        }
        const std::size_t required = (static_cast<std::size_t>(length) * 2U) + 1U;
        if (destination_size < required)
        {
            return recordError(Error::buffer_too_small, -ENOMEM);
        }
        constexpr char hexadecimal[] = "0123456789abcdef";
        for (ssize_t index = 0; index < length; ++index)
        {
            destination[index * 2] = hexadecimal[identifier[index] >> 4U];
            destination[(index * 2) + 1] = hexadecimal[identifier[index] & 0x0FU];
        }
        destination[static_cast<std::size_t>(length) * 2U] = '\0';
        return recordError(Error::none);
    }

    Error BoardSystem::resetReport(ResetReport &report) noexcept
    {
        if (!isThreadContext())
        {
            return Error::invalid_context;
        }
        std::uint32_t cause = 0U;
        std::uint32_t supported = 0U;
        int result = hwinfo_get_reset_cause(&cause);
        if (result < 0)
        {
            return recordDriverError(result);
        }
        result = hwinfo_get_supported_reset_cause(&supported);
        if (result < 0)
        {
            return recordDriverError(result);
        }
        report.cause = cause;
        report.supported = supported;
        return recordError(Error::none);
    }

    Error BoardSystem::clearResetCause() noexcept
    {
        if (!isThreadContext())
        {
            return Error::invalid_context;
        }
        const int result = hwinfo_clear_reset_cause();
        return (result == 0) ? recordError(Error::none) : recordDriverError(result);
    }

    std::uint64_t BoardSystem::uptimeMilliseconds() const noexcept
    {
        return static_cast<std::uint64_t>(k_uptime_get());
    }

    Error BoardSystem::lastError() const noexcept
    {
        return static_cast<Error>(atomic_get(&last_error_value));
    }

    int BoardSystem::lastDriverError() const noexcept
    {
        return static_cast<int>(atomic_get(&last_driver_error_value));
    }

    Error BoardSystem::watchdogBegin(std::uint32_t timeout_ms) noexcept
    {
        if (!isThreadContext())
        {
            return Error::invalid_context;
        }
        if (timeout_ms == 0U)
        {
            return recordError(Error::invalid_argument, -EINVAL);
        }
        static_cast<void>(k_mutex_lock(&system_mutex, K_FOREVER));
        if (atomic_get(&watchdog_running_value) != 0)
        {
            static_cast<void>(k_mutex_unlock(&system_mutex));
            return recordError(Error::already_started, -EALREADY);
        }
#if !DT_NODE_HAS_STATUS(DT_ALIAS(watchdog0), okay)
        static_cast<void>(k_mutex_unlock(&system_mutex));
        return recordError(Error::device_not_ready, -ENODEV);
#else
        if (!device_is_ready(watchdog_device))
        {
            static_cast<void>(k_mutex_unlock(&system_mutex));
            return recordError(Error::device_not_ready, -ENODEV);
        }

        wdt_timeout_cfg configuration{};
        configuration.window.min = 0U;
        configuration.window.max = timeout_ms;
        configuration.callback = nullptr;
        configuration.flags = WDT_FLAG_RESET_SOC;
        const int channel = wdt_install_timeout(watchdog_device, &configuration);
        if (channel < 0)
        {
            static_cast<void>(k_mutex_unlock(&system_mutex));
            return recordDriverError(channel);
        }
        const int result = wdt_setup(watchdog_device, 0U);
        if (result < 0)
        {
            static_cast<void>(wdt_disable(watchdog_device));
            static_cast<void>(k_mutex_unlock(&system_mutex));
            return recordDriverError(result);
        }
        watchdog_channel = channel;
        atomic_set(&watchdog_running_value, 1);
        static_cast<void>(k_mutex_unlock(&system_mutex));
        return recordError(Error::none);
#endif
    }

    Error BoardSystem::watchdogFeed() noexcept
    {
        if (!isThreadContext())
        {
            return Error::invalid_context;
        }
        static_cast<void>(k_mutex_lock(&system_mutex, K_FOREVER));
        if (atomic_get(&watchdog_running_value) == 0)
        {
            static_cast<void>(k_mutex_unlock(&system_mutex));
            return recordError(Error::not_started, -EACCES);
        }
#if !DT_NODE_HAS_STATUS(DT_ALIAS(watchdog0), okay)
        static_cast<void>(k_mutex_unlock(&system_mutex));
        return recordError(Error::device_not_ready, -ENODEV);
#else
        const int result = wdt_feed(watchdog_device, watchdog_channel);
        static_cast<void>(k_mutex_unlock(&system_mutex));
        return (result == 0) ? recordError(Error::none) : recordDriverError(result);
#endif
    }

    Error BoardSystem::watchdogStop() noexcept
    {
        if (!isThreadContext())
        {
            return Error::invalid_context;
        }
        static_cast<void>(k_mutex_lock(&system_mutex, K_FOREVER));
        if (atomic_get(&watchdog_running_value) == 0)
        {
            static_cast<void>(k_mutex_unlock(&system_mutex));
            return recordError(Error::not_started, -EACCES);
        }
#if !DT_NODE_HAS_STATUS(DT_ALIAS(watchdog0), okay)
        static_cast<void>(k_mutex_unlock(&system_mutex));
        return recordError(Error::device_not_ready, -ENODEV);
#else
        const int result = wdt_disable(watchdog_device);
        if (result == 0)
        {
            watchdog_channel = -1;
            atomic_set(&watchdog_running_value, 0);
        }
        static_cast<void>(k_mutex_unlock(&system_mutex));
        return (result == 0) ? recordError(Error::none) : recordDriverError(result);
#endif
    }

    bool BoardSystem::watchdogRunning() const noexcept
    {
        return atomic_get(&watchdog_running_value) != 0;
    }

    std::uint64_t BoardSystem::hardwareCounterTicks() const noexcept
    {
        return z_nrf_grtc_timer_read();
    }

    std::uint32_t BoardSystem::hardwareCounterFrequency() const noexcept
    {
        return CONFIG_SYS_CLOCK_HW_CYCLES_PER_SEC;
    }

    Error BoardSystem::alarmAfterMicroseconds(std::uint64_t delay_us, AlarmCallback callback,
                                              void *context) noexcept
    {
        if (!isThreadContext())
        {
            return Error::invalid_context;
        }
        if ((delay_us == 0U) || (delay_us > maximum_alarm_delay_us) || (callback == nullptr))
        {
            return recordError(Error::invalid_argument, -EINVAL);
        }
        static_cast<void>(k_mutex_lock(&system_mutex, K_FOREVER));
        if (atomic_get(&alarm_state) != 0)
        {
            static_cast<void>(k_mutex_unlock(&system_mutex));
            return recordError(Error::busy, -EBUSY);
        }
        const int32_t channel = z_nrf_grtc_timer_chan_alloc();
        if (channel < 0)
        {
            static_cast<void>(k_mutex_unlock(&system_mutex));
            return recordDriverError(channel);
        }
        const std::uint64_t target = z_nrf_grtc_timer_get_ticks(K_USEC(delay_us));
        if (static_cast<std::int64_t>(target) < 0)
        {
            z_nrf_grtc_timer_chan_free(channel);
            static_cast<void>(k_mutex_unlock(&system_mutex));
            return recordDriverError(static_cast<int>(static_cast<std::int64_t>(target)));
        }
        alarm_channel = channel;
        alarm_callback = callback;
        alarm_callback_context = context;
        atomic_set(&alarm_state, 1);
        const int result = z_nrf_grtc_timer_set(channel, target, alarmInterruptHandler, nullptr);
        if (result < 0)
        {
            atomic_set(&alarm_state, 0);
            alarm_channel = -1;
            alarm_callback = nullptr;
            alarm_callback_context = nullptr;
            z_nrf_grtc_timer_chan_free(channel);
            static_cast<void>(k_mutex_unlock(&system_mutex));
            return recordDriverError(result);
        }
        static_cast<void>(k_mutex_unlock(&system_mutex));
        return recordError(Error::none);
    }

    Error BoardSystem::cancelAlarm() noexcept
    {
        if (!isThreadContext())
        {
            return Error::invalid_context;
        }
        static_cast<void>(k_mutex_lock(&system_mutex, K_FOREVER));
        if (!atomic_cas(&alarm_state, 1, 0))
        {
            const bool dispatched = atomic_get(&alarm_state) == 2;
            static_cast<void>(k_mutex_unlock(&system_mutex));
            return recordError(dispatched ? Error::busy : Error::not_found,
                               dispatched ? -EBUSY : -ENOENT);
        }
        z_nrf_grtc_timer_abort(alarm_channel);
        z_nrf_grtc_timer_chan_free(alarm_channel);
        alarm_channel = -1;
        alarm_callback = nullptr;
        alarm_callback_context = nullptr;
        static_cast<void>(k_mutex_unlock(&system_mutex));
        return recordError(Error::none);
    }

    bool BoardSystem::alarmPending() const noexcept
    {
        return atomic_get(&alarm_state) != 0;
    }

    Error BoardSystem::storageBegin() noexcept
    {
        if (!isThreadContext())
        {
            return Error::invalid_context;
        }
        static_cast<void>(k_mutex_lock(&storage_mutex, K_FOREVER));
        if (storage_started)
        {
            static_cast<void>(k_mutex_unlock(&storage_mutex));
            return recordError(Error::none);
        }
        const int result = settings_subsys_init();
        if (result == 0)
        {
            storage_started = true;
        }
        static_cast<void>(k_mutex_unlock(&storage_mutex));
        return (result == 0) ? recordError(Error::none) : recordDriverError(result);
    }

    Error BoardSystem::storagePut(const char *key, const void *value, std::size_t length) noexcept
    {
        if (!isThreadContext())
        {
            return Error::invalid_context;
        }
        if ((value == nullptr) || (length == 0U) || (length > maximum_settings_value_length))
        {
            return recordError(Error::invalid_argument, -EINVAL);
        }
        char path[sizeof(settings_prefix) + maximum_settings_key_length] = {};
        if (makeSettingsPath(key, path, sizeof(path)) != Error::none)
        {
            return lastError();
        }
        static_cast<void>(k_mutex_lock(&storage_mutex, K_FOREVER));
        if (!storage_started)
        {
            static_cast<void>(k_mutex_unlock(&storage_mutex));
            return recordError(Error::not_started, -EACCES);
        }
        const int result = settings_save_one(path, value, length);
        static_cast<void>(k_mutex_unlock(&storage_mutex));
        return (result == 0) ? recordError(Error::none) : recordDriverError(result);
    }

    Error BoardSystem::storageGet(const char *key, void *value, std::size_t capacity,
                                  std::size_t &actual_length) noexcept
    {
        actual_length = 0U;
        if (!isThreadContext())
        {
            return Error::invalid_context;
        }
        if ((value == nullptr) || (capacity == 0U))
        {
            return recordError(Error::invalid_argument, -EINVAL);
        }
        char path[sizeof(settings_prefix) + maximum_settings_key_length] = {};
        if (makeSettingsPath(key, path, sizeof(path)) != Error::none)
        {
            return lastError();
        }
        static_cast<void>(k_mutex_lock(&storage_mutex, K_FOREVER));
        if (!storage_started)
        {
            static_cast<void>(k_mutex_unlock(&storage_mutex));
            return recordError(Error::not_started, -EACCES);
        }
        const ssize_t stored_length = settings_get_val_len(path);
        if (stored_length < 0)
        {
            static_cast<void>(k_mutex_unlock(&storage_mutex));
            return recordDriverError(static_cast<int>(stored_length));
        }
        if (stored_length == 0)
        {
            static_cast<void>(k_mutex_unlock(&storage_mutex));
            return recordError(Error::not_found, -ENOENT);
        }
        actual_length = static_cast<std::size_t>(stored_length);
        if (actual_length > capacity)
        {
            static_cast<void>(k_mutex_unlock(&storage_mutex));
            return recordError(Error::buffer_too_small, -ENOMEM);
        }
        const ssize_t result = settings_load_one(path, value, capacity);
        static_cast<void>(k_mutex_unlock(&storage_mutex));
        if (result < 0)
        {
            return recordDriverError(static_cast<int>(result));
        }
        if (static_cast<std::size_t>(result) != actual_length)
        {
            return recordError(Error::driver_error, -EIO);
        }
        return recordError(Error::none);
    }

    Error BoardSystem::storageRemove(const char *key) noexcept
    {
        if (!isThreadContext())
        {
            return Error::invalid_context;
        }
        char path[sizeof(settings_prefix) + maximum_settings_key_length] = {};
        if (makeSettingsPath(key, path, sizeof(path)) != Error::none)
        {
            return lastError();
        }
        static_cast<void>(k_mutex_lock(&storage_mutex, K_FOREVER));
        if (!storage_started)
        {
            static_cast<void>(k_mutex_unlock(&storage_mutex));
            return recordError(Error::not_started, -EACCES);
        }
        const int result = settings_delete(path);
        static_cast<void>(k_mutex_unlock(&storage_mutex));
        return (result == 0) ? recordError(Error::none) : recordDriverError(result);
    }

    Error BoardSystem::enterSystemOffOnButton(WakeButton button) noexcept
    {
        if (!isThreadContext())
        {
            return Error::invalid_context;
        }
        static_cast<void>(k_mutex_lock(&system_mutex, K_FOREVER));
        if (atomic_get(&alarm_state) != 0)
        {
            static_cast<void>(k_mutex_unlock(&system_mutex));
            return recordError(Error::busy, -EBUSY);
        }
        const gpio_dt_spec *specification = wakeButtonSpec(button);
        if (specification == nullptr)
        {
            static_cast<void>(k_mutex_unlock(&system_mutex));
            return recordError(Error::invalid_argument, -EINVAL);
        }
        if (!gpio_is_ready_dt(specification))
        {
            static_cast<void>(k_mutex_unlock(&system_mutex));
            return recordError(Error::device_not_ready, -ENODEV);
        }
        int result = gpio_pin_configure_dt(specification, GPIO_INPUT);
        if (result == 0)
        {
            result = gpio_pin_interrupt_configure_dt(specification, GPIO_INT_LEVEL_ACTIVE);
        }
        if (result < 0)
        {
            static_cast<void>(k_mutex_unlock(&system_mutex));
            return recordDriverError(result);
        }
        result = hwinfo_clear_reset_cause();
        if (result < 0)
        {
            static_cast<void>(gpio_pin_interrupt_configure_dt(specification, GPIO_INT_DISABLE));
            static_cast<void>(k_mutex_unlock(&system_mutex));
            return recordDriverError(result);
        }
        sys_poweroff();
        __builtin_unreachable();
    }

    Error BoardSystem::enterSystemOffAfter(std::uint64_t wake_after_us) noexcept
    {
        if (!isThreadContext())
        {
            return Error::invalid_context;
        }
        if ((wake_after_us == 0U) || (wake_after_us > maximum_alarm_delay_us))
        {
            return recordError(Error::invalid_argument, -EINVAL);
        }
        static_cast<void>(k_mutex_lock(&system_mutex, K_FOREVER));
        if (atomic_get(&alarm_state) != 0)
        {
            static_cast<void>(k_mutex_unlock(&system_mutex));
            return recordError(Error::busy, -EBUSY);
        }
        int result = hwinfo_clear_reset_cause();
        if (result < 0)
        {
            static_cast<void>(k_mutex_unlock(&system_mutex));
            return recordDriverError(result);
        }
        result = z_nrf_grtc_wakeup_prepare(wake_after_us);
        if (result < 0)
        {
            static_cast<void>(k_mutex_unlock(&system_mutex));
            return recordDriverError(result);
        }
        sys_poweroff();
        __builtin_unreachable();
    }

    Error BoardSystem::pmicBegin() noexcept
    {
        if (!isThreadContext())
        {
            return Error::invalid_context;
        }
        static_cast<void>(k_mutex_lock(&pmic_mutex, K_FOREVER));
        Wire.begin();
        std::uint8_t identifier = 0U;
        const int result = pmicReadRegister(PmicRegister::mask_id, identifier);
        if ((result == 0) && ((identifier & 0x0FU) == bq25186_device_id))
        {
            pmic_started = true;
            atomic_set(&pmic_writes_authorized, 0);
            atomic_set(&pmic_watchdog_policy_confirmed, 0);
            static_cast<void>(k_mutex_unlock(&pmic_mutex));
            return recordError(Error::none);
        }
        pmic_started = false;
        atomic_set(&pmic_writes_authorized, 0);
        atomic_set(&pmic_watchdog_policy_confirmed, 0);
        static_cast<void>(k_mutex_unlock(&pmic_mutex));
        return (result < 0) ? recordDriverError(result) : recordError(Error::not_found, -ENODEV);
    }

    Error BoardSystem::pmicReadStatus(PmicStatus &status) noexcept
    {
        if (!isThreadContext())
        {
            return Error::invalid_context;
        }
        static_cast<void>(k_mutex_lock(&pmic_mutex, K_FOREVER));
        if (requirePmicStartedLocked() != Error::none)
        {
            static_cast<void>(k_mutex_unlock(&pmic_mutex));
            return Error::not_started;
        }
        std::uint8_t status0 = 0U;
        std::uint8_t voltage = 0U;
        std::uint8_t current = 0U;
        int result = pmicReadRegister(PmicRegister::status0, status0);
        if (result == 0)
        {
            result = pmicReadRegister(PmicRegister::vbat_control, voltage);
        }
        if (result == 0)
        {
            result = pmicReadRegister(PmicRegister::charge_current_control, current);
        }
        if (result < 0)
        {
            static_cast<void>(k_mutex_unlock(&pmic_mutex));
            return recordDriverError(result);
        }
        status.input_power_good = (status0 & 0x01U) != 0U;
        status.charging_enabled = (current & 0x80U) == 0U;
        status.charge_state = static_cast<PmicChargeState>((status0 >> 5U) & 0x03U);
        const std::uint16_t decoded_voltage =
            static_cast<std::uint16_t>(3500U + ((voltage & 0x7FU) * 10U));
        status.charge_voltage_mv = (decoded_voltage > 4650U) ? 4650U : decoded_voltage;
        const std::uint8_t current_code = current & 0x7FU;
        status.charge_current_ma = static_cast<std::uint16_t>(
            (current_code <= 30U) ? (current_code + 5U) : (((current_code - 31U) * 10U) + 40U));
        static_cast<void>(k_mutex_unlock(&pmic_mutex));
        return recordError(Error::none);
    }

    Error BoardSystem::pmicReadSystemRegulation(PmicSystemRegulation &regulation) noexcept
    {
        if (!isThreadContext())
        {
            return Error::invalid_context;
        }
        static_cast<void>(k_mutex_lock(&pmic_mutex, K_FOREVER));
        if (requirePmicStartedLocked() != Error::none)
        {
            static_cast<void>(k_mutex_unlock(&pmic_mutex));
            return Error::not_started;
        }
        std::uint8_t value = 0U;
        const int result = pmicReadRegister(PmicRegister::system_regulation, value);
        if (result == 0)
        {
            regulation = static_cast<PmicSystemRegulation>((value >> 5U) & 0x07U);
        }
        static_cast<void>(k_mutex_unlock(&pmic_mutex));
        return (result == 0) ? recordError(Error::none) : recordDriverError(result);
    }

    Error BoardSystem::pmicReadRegisterWatchdog(PmicRegisterWatchdog &watchdog) noexcept
    {
        if (!isThreadContext())
        {
            return Error::invalid_context;
        }
        static_cast<void>(k_mutex_lock(&pmic_mutex, K_FOREVER));
        if (requirePmicStartedLocked() != Error::none)
        {
            static_cast<void>(k_mutex_unlock(&pmic_mutex));
            return Error::not_started;
        }
        std::uint8_t value = 0U;
        const int result = pmicReadRegister(PmicRegister::ic_control, value);
        if (result == 0)
        {
            watchdog = static_cast<PmicRegisterWatchdog>(value & 0x03U);
        }
        static_cast<void>(k_mutex_unlock(&pmic_mutex));
        return (result == 0) ? recordError(Error::none) : recordDriverError(result);
    }

    Error BoardSystem::pmicAuthorizeWrites(PmicWriteAuthorization authorization) noexcept
    {
        if (!isThreadContext())
        {
            return Error::invalid_context;
        }
        if (authorization != PmicWriteAuthorization::acknowledge_unverified_battery_hardware)
        {
            return recordError(Error::permission_denied, -EACCES);
        }
        static_cast<void>(k_mutex_lock(&pmic_mutex, K_FOREVER));
        if (requirePmicStartedLocked() != Error::none)
        {
            static_cast<void>(k_mutex_unlock(&pmic_mutex));
            return Error::not_started;
        }
        atomic_set(&pmic_writes_authorized, 1);
        atomic_set(&pmic_watchdog_policy_confirmed, 0);
        static_cast<void>(k_mutex_unlock(&pmic_mutex));
        return recordError(Error::none);
    }

    Error BoardSystem::pmicRevokeWrites() noexcept
    {
        if (!isThreadContext())
        {
            return Error::invalid_context;
        }
        static_cast<void>(k_mutex_lock(&pmic_mutex, K_FOREVER));
        atomic_set(&pmic_writes_authorized, 0);
        atomic_set(&pmic_watchdog_policy_confirmed, 0);
        static_cast<void>(k_mutex_unlock(&pmic_mutex));
        return recordError(Error::none);
    }

    bool BoardSystem::pmicWritesAuthorized() const noexcept
    {
        return atomic_get(&pmic_writes_authorized) != 0;
    }

    bool BoardSystem::pmicRegisterWatchdogPolicyConfirmed() const noexcept
    {
        return atomic_get(&pmic_watchdog_policy_confirmed) != 0;
    }

    Error BoardSystem::pmicSetChargeVoltage(std::uint16_t millivolts) noexcept
    {
        if ((millivolts < 3500U) || (millivolts > 4650U) || ((millivolts - 3500U) % 10U != 0U))
        {
            return recordError(Error::invalid_argument, -EINVAL);
        }
        const std::uint8_t code = static_cast<std::uint8_t>((millivolts - 3500U) / 10U);
        return mutatePmicRegister(PmicRegister::vbat_control, 0x7FU, code, true, false);
    }

    Error BoardSystem::pmicSetChargeCurrent(std::uint16_t milliamps) noexcept
    {
        std::uint8_t code = 0U;
        if ((milliamps >= 5U) && (milliamps <= 35U))
        {
            code = static_cast<std::uint8_t>(milliamps - 5U);
        }
        else if ((milliamps >= 40U) && (milliamps <= 1000U) && ((milliamps - 40U) % 10U == 0U))
        {
            code = static_cast<std::uint8_t>(((milliamps - 40U) / 10U) + 31U);
        }
        else
        {
            return recordError(Error::invalid_argument, -EINVAL);
        }
        return mutatePmicRegister(PmicRegister::charge_current_control, 0x7FU, code, true, false);
    }

    Error BoardSystem::pmicSetChargingEnabled(bool enabled) noexcept
    {
        return mutatePmicRegister(PmicRegister::charge_current_control, 0x80U,
                                  enabled ? 0x00U : 0x80U, true, false);
    }

    Error BoardSystem::pmicSetRechargeThreshold(std::uint16_t millivolts) noexcept
    {
        if ((millivolts != 100U) && (millivolts != 200U))
        {
            return recordError(Error::invalid_argument, -EINVAL);
        }
        return mutatePmicRegister(PmicRegister::ic_control, 0x20U,
                                  (millivolts == 200U) ? 0x20U : 0x00U, true, false);
    }

    Error BoardSystem::pmicSetSystemRegulation(PmicSystemRegulation regulation) noexcept
    {
        const std::uint8_t raw = static_cast<std::uint8_t>(regulation);
        if (raw > 7U)
        {
            return recordError(Error::invalid_argument, -EINVAL);
        }
        return mutatePmicRegister(PmicRegister::system_regulation, 0xE0U,
                                  static_cast<std::uint8_t>(raw << 5U), true, false);
    }

    Error BoardSystem::pmicSetRegisterWatchdog(PmicRegisterWatchdog watchdog) noexcept
    {
        const std::uint8_t raw = static_cast<std::uint8_t>(watchdog);
        if (raw > 3U)
        {
            return recordError(Error::invalid_argument, -EINVAL);
        }
        return mutatePmicRegister(PmicRegister::ic_control, 0x03U, raw, false, true);
    }

    Error BoardSystem::pmicRequestShutdown() noexcept
    {
        return mutatePmicRegister(PmicRegister::ship_reset, 0x60U, 0x20U, true, false);
    }

    Error BoardSystem::pmicRequestShipMode() noexcept
    {
        return mutatePmicRegister(PmicRegister::ship_reset, 0x60U, 0x40U, true, false);
    }
} // namespace nucode::nu54dk

namespace
{
    nucode::nu54dk::BoardSystem board_system_instance;
}

nucode::nu54dk::BoardSystem &NU54DK = board_system_instance;
