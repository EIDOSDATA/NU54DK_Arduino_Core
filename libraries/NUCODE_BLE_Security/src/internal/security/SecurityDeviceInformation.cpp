/** @file @brief DIS 문자열 검증과 runtime Settings 전달입니다.
 * SPDX-License-Identifier: MIT
 */
#if !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE)
#include "SecurityInternal.h"
namespace nucode::ble::internal::security
{
    namespace
    {
        constexpr std::size_t maximum_dis_string_length = 32U;
        atomic_t dis_error_value = ATOMIC_INIT(static_cast<atomic_val_t>(SecurityError::none));
    } // namespace
    /** @brief DIS 문자열을 caller 수명과 분리된 fixed buffer로 검증·복사합니다. */
    bool copyDisString(const char *source, char (&destination)[maximum_dis_string_length + 1U],
                       bool required) noexcept
    {
        if (source == nullptr)
        {
            destination[0] = '\0';
            return !required;
        }
        const std::size_t length = ::strnlen(source, maximum_dis_string_length + 1U);
        if ((required && length == 0U) || length > maximum_dis_string_length)
        {
            return false;
        }
        ::memcpy(destination, source, length);
        destination[length] = '\0';
        return true;
    }

    /** @brief runtime DIS cache에 null terminator를 포함해 값을 설정합니다. */
    int setDisValue(const char *key, const char *value) noexcept
    {
        return settings_runtime_set(key, value, ::strlen(value) + 1U);
    }

} // namespace nucode::ble::internal::security
namespace nucode::ble
{
    using namespace internal::security;
    bool DeviceInformationService::configure(const DeviceInformation &information) noexcept
    {
        if (!requireThreadContext())
        {
            atomic_set(&dis_error_value, static_cast<atomic_val_t>(SecurityError::invalid_context));
            return false;
        }
        char manufacturer[maximum_dis_string_length + 1U] = {};
        char model[maximum_dis_string_length + 1U] = {};
        char serial[maximum_dis_string_length + 1U] = {};
        char firmware[maximum_dis_string_length + 1U] = {};
        char hardware[maximum_dis_string_length + 1U] = {};
        char software[maximum_dis_string_length + 1U] = {};
        if (!copyDisString(information.manufacturer, manufacturer, true) ||
            !copyDisString(information.model, model, true) ||
            !copyDisString(information.serial_number, serial, false) ||
            !copyDisString(information.firmware_revision, firmware, false) ||
            !copyDisString(information.hardware_revision, hardware, false) ||
            !copyDisString(information.software_revision, software, false))
        {
            atomic_set(&dis_error_value,
                       static_cast<atomic_val_t>(SecurityError::invalid_argument));
            return false;
        }

        const struct
        {
            const char *key;
            const char *value;
        } values[] = {
            {"bt/dis/manuf", manufacturer}, {"bt/dis/model", model}, {"bt/dis/serial", serial},
            {"bt/dis/fw", firmware},        {"bt/dis/hw", hardware}, {"bt/dis/sw", software},
        };
        for (const auto &value : values)
        {
            const int result = setDisValue(value.key, value.value);
            if (result < 0)
            {
                atomic_set(&dis_error_value,
                           static_cast<atomic_val_t>(SecurityError::driver_error));
                return false;
            }
        }
        atomic_set(&dis_error_value, static_cast<atomic_val_t>(SecurityError::none));
        return true;
    }

    SecurityError DeviceInformationService::lastError() const noexcept
    {
        return static_cast<SecurityError>(atomic_get(&dis_error_value));
    }

} // namespace nucode::ble
nucode::ble::DeviceInformationService BLEDeviceInformation;
#endif
