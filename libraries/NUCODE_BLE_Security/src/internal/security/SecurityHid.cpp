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
        K_MUTEX_DEFINE(hid_api_mutex);
        static_assert(sizeof(KeyboardReport) == 8U,
                      "BLE HID keyboard report는 정확히 8 byte여야 합니다.");

        /** @brief 표준 keyboard input report descriptor입니다. */
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
        if (!requireThreadContext())
        {
            recordHidError(SecurityError::invalid_context, -EWOULDBLOCK);
            return false;
        }
        lockHidApi();
        if (atomic_get(&hidState().hid_initialized) != 0)
        {
            unlockHidApi();
            recordHidError(SecurityError::busy, -EALREADY);
            return false;
        }
        int result = nucode_ble_hids_initialize(keyboard_report_map, sizeof(keyboard_report_map),
                                                keyboard_report_id, keyboard_report_index,
                                                hidsProtocolModeChanged);
        if (result == 0)
        {
            atomic_set(&hidState().hid_initialized, 1);
            struct bt_conn *connection = referenceActiveConnection();
            if (connection != nullptr)
            {
                result = attachHidsLocked(connection);
                bt_conn_unref(connection);
            }
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
        if (atomic_get(&hidState().hid_initialized) == 0)
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
        if (bt_conn_get_security(connection) < BT_SECURITY_L2)
        {
            bt_conn_unref(connection);
            unlockHidApi();
            recordHidError(SecurityError::invalid_state, -EACCES);
            return false;
        }
        const auto *const bytes = reinterpret_cast<const std::uint8_t *>(&report);
        const int result = nucode_ble_hids_send(connection, boot_mode, keyboard_report_index, bytes,
                                                sizeof(report));
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
        bool boot_mode = false;
        struct bt_conn *connection = referenceHidConnection(&boot_mode);
        ARG_UNUSED(boot_mode);
        if (connection == nullptr)
        {
            return false;
        }
        bt_conn_unref(connection);
        return atomic_get(&hidState().hid_initialized) != 0;
    }

    SecurityError HidKeyboard::lastError() const noexcept
    {
        return static_cast<SecurityError>(atomic_get(&hidState().hid_error_value));
    }

    int HidKeyboard::lastDriverError() const noexcept
    {
        return static_cast<int>(atomic_get(&hidState().hid_driver_error_value));
    }

} // namespace nucode::ble
nucode::ble::HidKeyboard BLEKeyboard;
#endif
