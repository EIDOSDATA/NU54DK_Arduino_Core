/** @file @brief SDK GATT 호출을 완료·오류 주입 가능한 경계로 치환합니다. */
#pragma once
#include <zephyr/bluetooth/bluetooth.h>
#include <cstddef>
#include <cerrno>
struct bt_uuid
{
    std::uint8_t type;
};
struct bt_uuid_16
{
    bt_uuid uuid;
    std::uint16_t val;
};
constexpr int BT_UUID_TYPE_16 = 0;
#define BT_UUID_INIT_16(value) {{BT_UUID_TYPE_16}, value}
#define BT_UUID_16(value) reinterpret_cast<const bt_uuid_16 *>(value)
struct bt_gatt_attr
{
    const bt_uuid *uuid;
    void *user_data;
    std::uint16_t handle;
};
struct bt_gatt_service_val
{
    const bt_uuid *uuid;
    std::uint16_t end_handle;
};
struct bt_gatt_chrc
{
    const bt_uuid *uuid;
    std::uint16_t value_handle;
};
struct bt_gatt_discover_params
{
    const bt_uuid *uuid;
    std::uint8_t (*func)(bt_conn *, const bt_gatt_attr *, bt_gatt_discover_params *);
    std::uint16_t start_handle, end_handle;
    std::uint8_t type;
};
struct bt_gatt_subscribe_params
{
    bt_gatt_discover_params *disc_params;
    std::uint16_t ccc_handle, end_handle, value_handle, value;
    std::uint8_t (*notify)(bt_conn *, bt_gatt_subscribe_params *, const void *, std::uint16_t);
    void (*subscribe)(bt_conn *, std::uint8_t, bt_gatt_subscribe_params *);
    unsigned flags[1];
    bt_gatt_subscribe_params *next;
};
constexpr unsigned BT_GATT_SUBSCRIBE_FLAG_VOLATILE = 0U;
inline void atomic_set_bit(unsigned *flags, unsigned bit)
{
    *flags |= 1U << bit;
}
struct bt_gatt_write_params
{
    std::uint16_t handle, length;
    const void *data;
    void (*func)(bt_conn *, std::uint8_t, bt_gatt_write_params *);
};
struct bt_gatt_authorization_cb
{
    bool (*read_authorize)(bt_conn *, const bt_gatt_attr *);
    bool (*write_authorize)(bt_conn *, const bt_gatt_attr *);
};
constexpr std::uint8_t BT_GATT_ITER_STOP = 0U, BT_GATT_ITER_CONTINUE = 1U;
constexpr std::uint8_t BT_GATT_DISCOVER_PRIMARY = 0U, BT_GATT_DISCOVER_CHARACTERISTIC = 3U;
constexpr std::uint16_t BT_ATT_FIRST_ATTRIBUTE_HANDLE = 1U, BT_ATT_LAST_ATTRIBUTE_HANDLE = 65535U;
constexpr std::uint16_t BT_GATT_CCC_INDICATE = 2U, BT_GATT_AUTO_DISCOVER_CCC_HANDLE = 0U;
inline bt_gatt_discover_params *native_discovery = nullptr;
inline bt_gatt_write_params *native_write = nullptr;
inline bt_gatt_subscribe_params *native_subscriptions[2] = {};
inline unsigned native_subscription_count = 0U;
inline bt_gatt_subscribe_params *native_subscription_head = nullptr;
inline unsigned native_removed_subscriptions = 0U;
inline const bt_gatt_authorization_cb *native_authorization = nullptr;
inline int native_gatt_error = 0;
inline int bt_gatt_discover(bt_conn *, bt_gatt_discover_params *parameters)
{
    native_discovery = parameters;
    return native_gatt_error;
}
inline int bt_gatt_subscribe(bt_conn *, bt_gatt_subscribe_params *parameters)
{
    if (native_gatt_error != 0)
    {
        return native_gatt_error;
    }
    for (auto *current = native_subscription_head; current != nullptr; current = current->next)
    {
        if (current == parameters)
        {
            return -EALREADY;
        }
    }
    parameters->next = native_subscription_head;
    native_subscription_head = parameters;
    native_subscriptions[native_subscription_count++ % 2U] = parameters;
    return 0;
}
/** @brief 고정 SDK처럼 bond된 비휘발 구독은 보관하고 휘발 구독만 제거합니다. */
inline void native_remove_subscriptions(bt_conn *connection, bool bonded)
{
    auto **position = &native_subscription_head;
    while (*position != nullptr)
    {
        auto *parameters = *position;
        if (!bonded || (parameters->flags[0] & (1U << BT_GATT_SUBSCRIBE_FLAG_VOLATILE)) != 0U)
        {
            *position = parameters->next;
            parameters->next = nullptr;
            parameters->value = 0U;
            ++native_removed_subscriptions;
            parameters->notify(connection, parameters, nullptr, 0U);
        }
        else
        {
            position = &parameters->next;
        }
    }
}
inline int bt_gatt_write(bt_conn *, bt_gatt_write_params *parameters)
{
    native_write = parameters;
    return native_gatt_error;
}
inline int bt_gatt_authorization_cb_register(const bt_gatt_authorization_cb *callbacks)
{
    if (callbacks != nullptr && native_authorization != nullptr)
    {
        return -EALREADY;
    }
    native_authorization = callbacks;
    return 0;
}
