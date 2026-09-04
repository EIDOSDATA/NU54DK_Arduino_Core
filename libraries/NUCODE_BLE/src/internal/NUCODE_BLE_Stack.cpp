/**
 * @file NUCODE_BLE_Stack.cpp
 * @brief Bluetooth stack의 image-wide once 초기화를 구현합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#if !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE)

#include <internal/NUCODE_BLE_Internal.h>

#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/atomic.h>
#include <zephyr/sys/util.h>
#if defined(CONFIG_BT_SETTINGS)
#include <zephyr/settings/settings.h>
#endif

#include <errno.h>

namespace
{

    K_MUTEX_DEFINE(nucode_ble_stack_mutex);
    atomic_t stack_ready = ATOMIC_INIT(0);
    atomic_t settings_attempted = ATOMIC_INIT(0);
    atomic_t settings_result = ATOMIC_INIT(0);
    atomic_t facade_owner = ATOMIC_INIT(static_cast<atomic_val_t>(nucode::ble::internal::FacadeOwner::none));

    /** @brief Bluetooth settings를 stack enable 뒤 정확히 한 번 불러옵니다. */
    int loadSettingsOnce() noexcept
    {
#if defined(CONFIG_BT_SETTINGS)
        if (atomic_get(&settings_attempted) == 0)
        {
            const int result = settings_load();
            atomic_set(&settings_result, result);
            atomic_set(&settings_attempted, 1);
        }
        return static_cast<int>(atomic_get(&settings_result));
#else
        atomic_set(&settings_attempted, 1);
        return 0;
#endif
    }

} // namespace

namespace nucode::ble::internal
{

    bool claimFacade(FacadeOwner owner) noexcept
    {
        return owner != FacadeOwner::none &&
               atomic_cas(&facade_owner,
                          static_cast<atomic_val_t>(FacadeOwner::none),
                          static_cast<atomic_val_t>(owner));
    }

    void releaseFacade(FacadeOwner owner) noexcept
    {
        if (owner != FacadeOwner::none)
        {
            static_cast<void>(atomic_cas(
                &facade_owner, static_cast<atomic_val_t>(owner),
                static_cast<atomic_val_t>(FacadeOwner::none)));
        }
    }

    int ensureStack() noexcept
    {
        k_mutex_lock(&nucode_ble_stack_mutex, K_FOREVER);
        if (atomic_get(&stack_ready) != 0 || bt_is_ready())
        {
            atomic_set(&stack_ready, 1);
            const int settings_status = loadSettingsOnce();
            k_mutex_unlock(&nucode_ble_stack_mutex);
            return settings_status;
        }

        const int result = bt_enable(nullptr);
        if (result == 0 || result == -EALREADY)
        {
            atomic_set(&stack_ready, 1);
            const int settings_status = loadSettingsOnce();
            if (settings_status < 0)
            {
                k_mutex_unlock(&nucode_ble_stack_mutex);
                return settings_status;
            }
        }
        k_mutex_unlock(&nucode_ble_stack_mutex);
        return result == -EALREADY ? 0 : result;
    }

    bool stackReady() noexcept
    {
        return atomic_get(&stack_ready) != 0 || bt_is_ready();
    }

    bool settingsReady() noexcept
    {
        return atomic_get(&settings_attempted) != 0 &&
               atomic_get(&settings_result) == 0;
    }

    int settingsResult() noexcept
    {
        return static_cast<int>(atomic_get(&settings_result));
    }

    /** @brief M20이 링크되기 전에는 custom GATT database를 준비하지 않습니다. */
    __weak int prepareGattDatabase() noexcept
    {
        return 0;
    }

    /** @brief M20이 링크되기 전에는 custom GATT schema가 없습니다. */
    __weak bool hasGattSchema() noexcept
    {
        return false;
    }

    /** @brief M20이 링크되기 전에는 GATT main-thread 작업이 없습니다. */
    __weak void pollGatt() noexcept
    {
    }

    /** @brief M20이 링크되기 전에는 generic GATT connection 관찰을 생략합니다. */
    __weak void gattConnected(struct bt_conn *connection, std::uint32_t generation) noexcept
    {
        ARG_UNUSED(connection);
        ARG_UNUSED(generation);
    }

    /** @brief M20이 링크되기 전에는 generic GATT disconnect 관찰을 생략합니다. */
    __weak void gattDisconnected(struct bt_conn *connection, std::uint32_t generation) noexcept
    {
        ARG_UNUSED(connection);
        ARG_UNUSED(generation);
    }

    /** @brief M20이 링크되기 전에는 GATT 종료 정리가 없습니다. */
    __weak void gattEnded() noexcept
    {
    }

    /** @brief M20이 링크되지 않은 M19-only image는 custom schema를 거부합니다. */
    __weak bool addGattService(BLEService &service) noexcept
    {
        ARG_UNUSED(service);
        return false;
    }

    /** @brief M21이 링크되기 전에는 security connection 관찰을 비활성화합니다. */
    __weak void securityConnected(struct bt_conn *connection) noexcept
    {
        ARG_UNUSED(connection);
    }

    /** @brief M21이 링크되기 전에는 security disconnect 관찰을 비활성화합니다. */
    __weak void securityDisconnected(struct bt_conn *connection) noexcept
    {
        ARG_UNUSED(connection);
    }

    /** @brief M21이 링크되기 전에는 security level 변경 관찰을 비활성화합니다. */
    __weak void securityChanged(struct bt_conn *connection, bt_security_t level, enum bt_security_err error) noexcept
    {
        ARG_UNUSED(connection);
        ARG_UNUSED(level);
        ARG_UNUSED(error);
    }

} // namespace nucode::ble::internal

#endif
