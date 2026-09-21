/** @file @brief keyboard report와 HIDS connection 수명주기입니다.
 * SPDX-License-Identifier: MIT
 */
#if !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE)
#include "SecurityInternal.h"
namespace nucode::ble::internal::security
{
    namespace
    {
        HidState state{};
    }
    HidState &hidState() noexcept
    {
        return state;
    }
    namespace
    {
        constexpr std::uint8_t keyboard_report_id = 1U;
        constexpr std::uint8_t keyboard_report_index = 0U;
        constexpr std::uint8_t mouse_report_id = 2U;
        constexpr std::uint8_t mouse_report_index = 1U;
        constexpr std::uint8_t consumer_report_id = 3U;
        constexpr std::uint8_t consumer_report_index = 2U;
        constexpr std::uint8_t keyboard_profile_mask = 0x01U;
        constexpr std::uint8_t mouse_profile_mask = 0x02U;
        constexpr std::uint8_t consumer_profile_mask = 0x04U;
        K_MUTEX_DEFINE(hid_api_mutex);
        static_assert(sizeof(KeyboardReport) == 8U,
                      "BLE HID keyboard report는 정확히 8 byte여야 합니다.");
        static_assert(sizeof(MouseReport) == 4U,
                      "BLE HID mouse report는 정확히 4 byte여야 합니다.");
        static_assert(sizeof(ConsumerControlReport) == 2U,
                      "BLE HID consumer report는 정확히 2 byte여야 합니다.");

        /** @brief keyboard·mouse·consumer input을 포함하는 공용 report descriptor입니다. */
        constexpr std::uint8_t keyboard_report_map[] = {
            0x05, 0x01,               /** 일반 데스크톱 사용 페이지입니다. */
            0x09, 0x06,               /** 키보드 사용 항목입니다. */
            0xA1, 0x01,               /** 애플리케이션 collection 시작입니다. */
            0x85, keyboard_report_id, /** 입력 report ID입니다. */
            0x05, 0x07,               /** 키보드 사용 페이지입니다. */
            0x19, 0xE0,               /** 왼쪽 Control 최소 사용 ID입니다. */
            0x29, 0xE7,               /** 오른쪽 GUI 최대 사용 ID입니다. */
            0x15, 0x00,               /** modifier 논리 최소값입니다. */
            0x25, 0x01,               /** modifier 논리 최대값입니다. */
            0x75, 0x01,               /** modifier report 크기입니다. */
            0x95, 0x08,               /** modifier report 개수입니다. */
            0x81, 0x02,               /** 가변 절대 입력입니다. */
            0x95, 0x01,               /** 예약 byte report 개수입니다. */
            0x75, 0x08,               /** 예약 byte report 크기입니다. */
            0x81, 0x01,               /** 예약 상수 입력입니다. */
            0x95, 0x06,               /** 동시 key report 개수입니다. */
            0x75, 0x08,               /** key report 크기입니다. */
            0x15, 0x00,               /** key 논리 최소값입니다. */
            0x25, 0x65,               /** key 논리 최대값입니다. */
            0x05, 0x07,               /** 키보드 사용 페이지입니다. */
            0x19, 0x00,               /** key 사용 ID 최소값입니다. */
            0x29, 0x65,               /** key 사용 ID 최대값입니다. */
            0x81, 0x00,               /** 배열 입력입니다. */
            0xC0,                     /** collection 종료입니다. */
            0x05, 0x01,               /** 일반 데스크톱 사용 페이지입니다. */
            0x09, 0x02,               /** Mouse 사용 항목입니다. */
            0xA1, 0x01,               /** 애플리케이션 collection 시작입니다. */
            0x85, mouse_report_id,    /** Mouse input report ID입니다. */
            0x09, 0x01,               /** Pointer 사용 항목입니다. */
            0xA1, 0x00,               /** Physical collection 시작입니다. */
            0x05, 0x09,               /** Button 사용 페이지입니다. */
            0x19, 0x01,               /** Button 최소 사용 ID입니다. */
            0x29, 0x05,               /** Button 최대 사용 ID입니다. */
            0x15, 0x00,               /** Button 논리 최소값입니다. */
            0x25, 0x01,               /** Button 논리 최대값입니다. */
            0x95, 0x05,               /** Button report 개수입니다. */
            0x75, 0x01,               /** Button report 크기입니다. */
            0x81, 0x02,               /** Button 가변 절대 입력입니다. */
            0x95, 0x01,               /** 예약 report 개수입니다. */
            0x75, 0x03,               /** 예약 bit 크기입니다. */
            0x81, 0x01,               /** 예약 상수 입력입니다. */
            0x05, 0x01,               /** 일반 데스크톱 사용 페이지입니다. */
            0x09, 0x30,               /** X 사용 항목입니다. */
            0x09, 0x31,               /** Y 사용 항목입니다. */
            0x09, 0x38,               /** Wheel 사용 항목입니다. */
            0x15, 0x81,               /** 상대값 논리 최소 -127입니다. */
            0x25, 0x7F,               /** 상대값 논리 최대 127입니다. */
            0x75, 0x08,               /** 상대값 report 크기입니다. */
            0x95, 0x03,               /** X/Y/Wheel report 개수입니다. */
            0x81, 0x06,               /** 가변 상대 입력입니다. */
            0xC0,                     /** Physical collection 종료입니다. */
            0xC0,                     /** Mouse collection 종료입니다. */
            0x05, 0x0C,               /** Consumer 사용 페이지입니다. */
            0x09, 0x01,               /** Consumer Control 사용 항목입니다. */
            0xA1, 0x01,               /** 애플리케이션 collection 시작입니다. */
            0x85, consumer_report_id, /** Consumer input report ID입니다. */
            0x15, 0x00,               /** usage 논리 최소값입니다. */
            0x26, 0xFF, 0x03,         /** usage 논리 최대 0x03ff입니다. */
            0x19, 0x00,               /** usage 최소값입니다. */
            0x2A, 0xFF, 0x03,         /** usage 최대값 0x03ff입니다. */
            0x75, 0x10,               /** usage report 크기입니다. */
            0x95, 0x01,               /** usage report 개수입니다. */
            0x81, 0x00,               /** 배열 입력입니다. */
            0xC0,                     /** Consumer collection 종료입니다. */
        };

        /** @brief keyboard report의 모든 key usage가 descriptor 범위 안인지 확인합니다. */
        bool validKeyboardReport(const KeyboardReport &report) noexcept
        {
            for (const std::uint8_t usage : report.keys)
            {
                if (usage > 0x65U)
                {
                    return false;
                }
            }
            return true;
        }

    } // namespace
    void lockHidApi() noexcept
    {
        k_mutex_lock(&hid_api_mutex, K_FOREVER);
    }
    void unlockHidApi() noexcept
    {
        k_mutex_unlock(&hid_api_mutex);
    }
    /** @brief 마지막 HID 오류와 원본 driver 오류를 함께 기록합니다. */
    void recordHidError(SecurityError error, int driver_error) noexcept
    {
        atomic_set(&hidState().hid_error_value, static_cast<atomic_val_t>(error));
        atomic_set(&hidState().hid_driver_error_value, driver_error);
    }

    /** @brief 공용 HIDS를 한 번 초기화하고 요청 profile bit를 활성화합니다. */
    bool initializeHidProfile(std::uint8_t profile_mask) noexcept
    {
        if (!requireThreadContext())
        {
            recordHidError(SecurityError::invalid_context, -EWOULDBLOCK);
            return false;
        }
        lockHidApi();
        if ((static_cast<std::uint8_t>(atomic_get(&hidState().hid_profile_mask)) &
             profile_mask) != 0U)
        {
            unlockHidApi();
            recordHidError(SecurityError::busy, -EALREADY);
            return false;
        }
        int result = 0;
        if (atomic_get(&hidState().hid_initialized) == 0)
        {
            result = nucode_ble_hids_initialize(keyboard_report_map, sizeof(keyboard_report_map),
                                                hidsProtocolModeChanged);
            if (result == 0)
            {
                atomic_set(&hidState().hid_initialized, 1);
            }
        }
        if (result == 0)
        {
            struct bt_conn *connection = referenceActiveConnection();
            if (connection != nullptr)
            {
                result = attachHidsLocked(connection);
                bt_conn_unref(connection);
            }
        }
        if (result == 0)
        {
            const atomic_val_t active_profiles = atomic_get(&hidState().hid_profile_mask);
            atomic_set(&hidState().hid_profile_mask,
                       active_profiles | static_cast<atomic_val_t>(profile_mask));
        }
        unlockHidApi();
        if (result < 0)
        {
            recordHidError(SecurityError::driver_error, result);
            return false;
        }
        recordHidError(SecurityError::none);
        return true;
    }

    /** @brief 활성 profile의 report를 encrypted HIDS connection으로 전송합니다. */
    bool sendHidReport(std::uint8_t profile_mask, std::uint8_t report_index,
                       const void *data, std::size_t length, bool keyboard_boot) noexcept
    {
        if (!requireThreadContext())
        {
            recordHidError(SecurityError::invalid_context, -EWOULDBLOCK);
            return false;
        }
        if (data == nullptr || length == 0U)
        {
            recordHidError(SecurityError::invalid_argument, -EINVAL);
            return false;
        }
        if (atomic_get(&hidState().hid_initialized) == 0 ||
            (static_cast<std::uint8_t>(atomic_get(&hidState().hid_profile_mask)) &
             profile_mask) == 0U)
        {
            recordHidError(SecurityError::not_initialized, -EACCES);
            return false;
        }
        lockHidApi();
        bool boot_mode = false;
        struct bt_conn *connection = referenceHidConnection(&boot_mode);
        if (connection == nullptr)
        {
            unlockHidApi();
            recordHidError(SecurityError::not_connected, -ENOTCONN);
            return false;
        }
        if (bt_conn_get_security(connection) < BT_SECURITY_L2 ||
            (boot_mode && !keyboard_boot))
        {
            bt_conn_unref(connection);
            unlockHidApi();
            recordHidError(SecurityError::invalid_state, -EACCES);
            return false;
        }
        const int result = nucode_ble_hids_send(
            connection, boot_mode && keyboard_boot, report_index,
            static_cast<const std::uint8_t *>(data), length);
        bt_conn_unref(connection);
        unlockHidApi();
        if (result < 0)
        {
            recordHidError(result == -EACCES ? SecurityError::not_subscribed
                                             : SecurityError::driver_error,
                           result);
            return false;
        }
        recordHidError(SecurityError::none);
        return true;
    }

    /** @brief profile bit·exact connection·L2 이상을 함께 검사합니다. */
    bool hidProfileConnected(std::uint8_t profile_mask) noexcept
    {
        if ((static_cast<std::uint8_t>(atomic_get(&hidState().hid_profile_mask)) &
             profile_mask) == 0U)
        {
            return false;
        }
        bool boot_mode = false;
        struct bt_conn *connection = referenceHidConnection(&boot_mode);
        ARG_UNUSED(boot_mode);
        if (connection == nullptr)
        {
            return false;
        }
        const bool connected = bt_conn_get_security(connection) >= BT_SECURITY_L2;
        bt_conn_unref(connection);
        return connected;
    }

    /** @brief host가 선택한 HIDS protocol mode를 exact connection slot에 반영합니다. */
    void hidsProtocolModeChanged(bool boot_mode, struct bt_conn *connection)
    {
        k_spinlock_key_t key = k_spin_lock(&hidState().hid_state_lock);
        if (hidState().hid_connection_state.registered &&
            hidState().hid_connection_state.connection == connection)
        {
            hidState().hid_connection_state.in_boot_mode = boot_mode;
        }
        k_spin_unlock(&hidState().hid_state_lock, key);
    }

    /** @brief hid_api_mutex를 보유한 상태에서 connection을 HIDS slot에 등록합니다. */
    int attachHidsLocked(struct bt_conn *connection) noexcept
    {
        if (connection == nullptr || atomic_get(&hidState().hid_initialized) == 0)
        {
            return 0;
        }
        k_spinlock_key_t key = k_spin_lock(&hidState().hid_state_lock);
        const bool already_registered = hidState().hid_connection_state.registered &&
                                        hidState().hid_connection_state.connection == connection;
        const bool occupied = hidState().hid_connection_state.registered &&
                              hidState().hid_connection_state.connection != connection;
        k_spin_unlock(&hidState().hid_state_lock, key);
        if (already_registered)
        {
            return 0;
        }
        if (occupied)
        {
            return -ENOMEM;
        }

        const int result = nucode_ble_hids_connected(connection);
        if (result < 0)
        {
            return result;
        }
        key = k_spin_lock(&hidState().hid_state_lock);
        if (!hidState().hid_connection_state.registered)
        {
            hidState().hid_connection_state.connection = bt_conn_ref(connection);
            hidState().hid_connection_state.registered = true;
            hidState().hid_connection_state.in_boot_mode = false;
        }
        else
        {
            k_spin_unlock(&hidState().hid_state_lock, key);
            static_cast<void>(nucode_ble_hids_disconnected(connection));
            return -EALREADY;
        }
        k_spin_unlock(&hidState().hid_state_lock, key);
        return 0;
    }

    /** @brief hid_api_mutex를 보유한 상태에서 exact connection slot을 회수합니다. */
    int detachHidsLocked(struct bt_conn *connection) noexcept
    {
        if (connection == nullptr || atomic_get(&hidState().hid_initialized) == 0)
        {
            return 0;
        }
        k_spinlock_key_t key = k_spin_lock(&hidState().hid_state_lock);
        const bool matches = hidState().hid_connection_state.registered &&
                             hidState().hid_connection_state.connection == connection;
        k_spin_unlock(&hidState().hid_state_lock, key);
        if (!matches)
        {
            return 0;
        }

        const int result = nucode_ble_hids_disconnected(connection);
        struct bt_conn *released = nullptr;
        key = k_spin_lock(&hidState().hid_state_lock);
        if (hidState().hid_connection_state.registered &&
            hidState().hid_connection_state.connection == connection)
        {
            released = hidState().hid_connection_state.connection;
            hidState().hid_connection_state = {};
        }
        k_spin_unlock(&hidState().hid_state_lock, key);
        if (released != nullptr)
        {
            bt_conn_unref(released);
        }
        return result;
    }

    /** @brief 현재 HIDS exact connection과 protocol mode snapshot을 참조합니다. */
    struct bt_conn *referenceHidConnection(bool *boot_mode) noexcept
    {
        struct bt_conn *connection = nullptr;
        k_spinlock_key_t key = k_spin_lock(&hidState().hid_state_lock);
        if (hidState().hid_connection_state.registered &&
            hidState().hid_connection_state.connection != nullptr)
        {
            connection = bt_conn_ref(hidState().hid_connection_state.connection);
            if (boot_mode != nullptr)
            {
                *boot_mode = hidState().hid_connection_state.in_boot_mode;
            }
        }
        k_spin_unlock(&hidState().hid_state_lock, key);
        return connection;
    }

} // namespace nucode::ble::internal::security
namespace nucode::ble
{
    using namespace internal::security;
    bool HidKeyboard::begin() noexcept
    {
        return initializeHidProfile(keyboard_profile_mask);
    }

    bool HidKeyboard::sendReport(const KeyboardReport &report) noexcept
    {
        if (!requireThreadContext())
        {
            recordHidError(SecurityError::invalid_context, -EWOULDBLOCK);
            return false;
        }
        if (!validKeyboardReport(report))
        {
            recordHidError(SecurityError::invalid_argument, -EINVAL);
            return false;
        }
        return sendHidReport(keyboard_profile_mask, keyboard_report_index, &report,
                             sizeof(report), true);
    }

    bool HidKeyboard::press(std::uint8_t usage, std::uint8_t modifiers) noexcept
    {
        if (usage == 0U || usage > 0x65U)
        {
            recordHidError(SecurityError::invalid_argument, -EINVAL);
            return false;
        }
        KeyboardReport report = {};
        report.modifiers = modifiers;
        report.keys[0] = usage;
        return sendReport(report);
    }

    bool HidKeyboard::releaseAll() noexcept
    {
        return sendReport(KeyboardReport{});
    }

    bool HidKeyboard::connected() const noexcept
    {
        return hidProfileConnected(keyboard_profile_mask);
    }

    SecurityError HidKeyboard::lastError() const noexcept
    {
        return static_cast<SecurityError>(atomic_get(&hidState().hid_error_value));
    }

    int HidKeyboard::lastDriverError() const noexcept
    {
        return static_cast<int>(atomic_get(&hidState().hid_driver_error_value));
    }

    bool HidMouse::begin() noexcept
    {
        return initializeHidProfile(mouse_profile_mask);
    }

    bool HidMouse::sendReport(const MouseReport &report) noexcept
    {
        if ((report.buttons & 0xe0U) != 0U)
        {
            recordHidError(SecurityError::invalid_argument, -EINVAL);
            return false;
        }
        return sendHidReport(mouse_profile_mask, mouse_report_index, &report, sizeof(report),
                             false);
    }

    bool HidMouse::move(std::int8_t x, std::int8_t y, std::int8_t wheel,
                        std::uint8_t buttons) noexcept
    {
        MouseReport report = {};
        report.buttons = buttons;
        report.x = x;
        report.y = y;
        report.wheel = wheel;
        return sendReport(report);
    }

    bool HidMouse::releaseAll() noexcept
    {
        return sendReport(MouseReport{});
    }

    bool HidMouse::connected() const noexcept
    {
        return hidProfileConnected(mouse_profile_mask);
    }

    SecurityError HidMouse::lastError() const noexcept
    {
        return static_cast<SecurityError>(atomic_get(&hidState().hid_error_value));
    }

    int HidMouse::lastDriverError() const noexcept
    {
        return static_cast<int>(atomic_get(&hidState().hid_driver_error_value));
    }

    bool HidConsumerControl::begin() noexcept
    {
        return initializeHidProfile(consumer_profile_mask);
    }

    bool HidConsumerControl::sendReport(const ConsumerControlReport &report) noexcept
    {
        if (report.usage > 0x03ffU)
        {
            recordHidError(SecurityError::invalid_argument, -EINVAL);
            return false;
        }
        return sendHidReport(consumer_profile_mask, consumer_report_index, &report,
                             sizeof(report), false);
    }

    bool HidConsumerControl::press(std::uint16_t usage) noexcept
    {
        if (usage == 0U || usage > 0x03ffU)
        {
            recordHidError(SecurityError::invalid_argument, -EINVAL);
            return false;
        }
        ConsumerControlReport report = {};
        report.usage = usage;
        return sendReport(report);
    }

    bool HidConsumerControl::release() noexcept
    {
        return sendReport(ConsumerControlReport{});
    }

    bool HidConsumerControl::connected() const noexcept
    {
        return hidProfileConnected(consumer_profile_mask);
    }

    SecurityError HidConsumerControl::lastError() const noexcept
    {
        return static_cast<SecurityError>(atomic_get(&hidState().hid_error_value));
    }

    int HidConsumerControl::lastDriverError() const noexcept
    {
        return static_cast<int>(atomic_get(&hidState().hid_driver_error_value));
    }

} // namespace nucode::ble
nucode::ble::HidKeyboard BLEKeyboard;
nucode::ble::HidMouse BLEMouse;
nucode::ble::HidConsumerControl BLEConsumerControl;
#endif
