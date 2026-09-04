/**
 * @file NUCODE_BLE_Internal.h
 * @brief NUS·GAP·GATT 구현이 공유하는 비공개 Bluetooth 경계를 선언합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#ifndef NUCODE_BLE_INTERNAL_H_
#define NUCODE_BLE_INTERNAL_H_

#include <NUCODE_BLE_GAP.h>

#include <zephyr/bluetooth/conn.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/atomic.h>

#include <errno.h>

namespace nucode::ble::internal
{

    /** @brief 한 image에서 동시에 사용할 수 있는 공개 BLE facade 소유자입니다. */
    enum class FacadeOwner : atomic_val_t
    {
        none = 0,
        nus = 1,
        generic = 2,
    };

    /** @brief image 수명 동안 Bluetooth stack을 정확히 한 번 초기화합니다. */
    int ensureStack() noexcept;

    /** @brief Bluetooth stack이 이미 준비되었는지 반환합니다. */
    bool stackReady() noexcept;

    /** @brief CONFIG_BT_SETTINGS의 one-shot settings_load 성공 여부를 반환합니다. */
    bool settingsReady() noexcept;

    /** @brief settings_load 결과를 반환하며 기능 비활성 시 0을 반환합니다. */
    int settingsResult() noexcept;

    /** @brief Core/GATT가 공유하는 마지막 오류를 기록합니다. */
    void recordError(BLEError error, int driver_error = 0, bool notify = false) noexcept;

    /** @brief thread 전용 BLE API의 ISR 호출을 공통 오류로 거부합니다. */
    inline bool requireThreadContext() noexcept
    {
        if (k_is_in_isr())
        {
            recordError(BLEError::invalid_context, -EWOULDBLOCK, true);
            return false;
        }
        return true;
    }

    /** @brief image-wide BLE facade 소유권을 원자적으로 획득합니다. */
    bool claimFacade(FacadeOwner owner) noexcept;

    /** @brief 자신이 보유한 image-wide BLE facade 소유권을 해제합니다. */
    void releaseFacade(FacadeOwner owner) noexcept;

    /** @brief 현재 generic BLE connection의 임시 reference를 반환합니다. */
    struct bt_conn *referenceConnection() noexcept;

    /** @brief GATT database를 stack 시작 전 고정 자원에 등록합니다. */
    int prepareGattDatabase() noexcept;

    /** @brief generic GATT schema가 있는지 반환합니다. */
    bool hasGattSchema() noexcept;

    /** @brief GATT queued event와 client state machine을 main thread에서 진행합니다. */
    void pollGatt() noexcept;

    /** @brief 새 generic connection을 GATT client lifecycle에 전달합니다. */
    void gattConnected(struct bt_conn *connection, std::uint32_t generation) noexcept;

    /** @brief disconnect에서 remote handle과 subscription을 무효화합니다. */
    void gattDisconnected(struct bt_conn *connection, std::uint32_t generation) noexcept;

    /** @brief Device::end에서 GATT session과 queue를 event 없이 폐기합니다. */
    void gattEnded() noexcept;

    /** @brief M21 security 계층에 새 connection reference를 관찰용으로 전달합니다. */
    void securityConnected(struct bt_conn *connection) noexcept;

    /** @brief M21 security 계층에 disconnect를 전달합니다. */
    void securityDisconnected(struct bt_conn *connection) noexcept;

    /** @brief M21 security 계층에 실제 link security 변경 결과를 전달합니다. */
    void securityChanged(struct bt_conn *connection, bt_security_t level,
                         enum bt_security_err error) noexcept;

    /** @brief schema registry를 Device::addService에 연결합니다. */
    bool addGattService(BLEService &service) noexcept;

} // namespace nucode::ble::internal

#endif
