/**
 * @file NUCODE_BLE_LegacySigning.cpp
 * @brief 고정 NCS v3.4.0 CSRK와 sign counter를 bonded key record에 저장합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#if !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE)

#include <NUCODE_BLE_LegacySigning.h>

#include <zephyr/bluetooth/conn.h>

extern "C"
{
#include "keys.h"
}

#include <cstdint>
#include <errno.h>

namespace
{

    /** @brief 연결된 bonded identity의 signing key record를 반환합니다. */
    struct bt_keys *signingKeys(struct bt_conn *connection) noexcept
    {
        if (connection == nullptr)
        {
            return nullptr;
        }
        struct bt_conn_info information = {};
        if (bt_conn_get_info(connection, &information) < 0 ||
            information.type != BT_CONN_TYPE_LE || information.le.dst == nullptr)
        {
            return nullptr;
        }
        return bt_keys_find(
            static_cast<enum bt_keys_type>(BT_KEYS_LOCAL_CSRK | BT_KEYS_REMOTE_CSRK),
            information.id, information.le.dst);
    }

} // namespace

/** @brief 현재 CSRK와 송수신 sign counter를 같은 bonded key record에 동기 저장합니다. */
extern "C" int nucode_ble_signing_persist(struct bt_conn *connection)
{
    struct bt_keys *keys = signingKeys(connection);
    if (keys == nullptr)
    {
        return -ENOENT;
    }
    return bt_keys_store(keys);
}

/** @brief W07 target이 저장 전후 counter를 정량 검증하도록 현재 값을 복사합니다. */
extern "C" int nucode_ble_signing_counters(struct bt_conn *connection,
                                             std::uint32_t *local_counter,
                                             std::uint32_t *remote_counter)
{
    if (local_counter == nullptr || remote_counter == nullptr)
    {
        return -EINVAL;
    }
    struct bt_keys *keys = signingKeys(connection);
    if (keys == nullptr)
    {
        return -ENOENT;
    }
    *local_counter = keys->local_csrk.cnt;
    *remote_counter = keys->remote_csrk.cnt;
    return 0;
}

#endif
