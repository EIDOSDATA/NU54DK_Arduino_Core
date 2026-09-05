/** @file @brief 고정 NCS GATT 경계를 대신하여 완료·실패 callback을 주입합니다. */
#pragma once
#include <ble_mock.h>
#include <zephyr/sys/atomic.h>
#include <cstring>
#include <algorithm>
#include <sys/types.h>
enum
{
    BT_UUID_TYPE_16 = 0,
    BT_UUID_TYPE_128 = 2,
    BT_GATT_CHRC_READ = 2,
    BT_GATT_CHRC_WRITE_WITHOUT_RESP = 4,
    BT_GATT_CHRC_WRITE = 8,
    BT_GATT_CHRC_NOTIFY = 16,
    BT_GATT_CHRC_INDICATE = 32,
    BT_GATT_PERM_NONE = 0,
    BT_GATT_PERM_READ = 1,
    BT_GATT_PERM_WRITE = 2,
    BT_GATT_CCC_NOTIFY = 1,
    BT_GATT_CCC_INDICATE = 2,
    BT_GATT_WRITE_FLAG_PREPARE = 1,
    BT_GATT_WRITE_FLAG_CMD = 2,
    BT_GATT_WRITE_FLAG_EXECUTE = 4,
    BT_GATT_ITER_STOP = 0,
    BT_GATT_ITER_CONTINUE = 1,
    BT_ATT_ERR_NOT_SUPPORTED = 6,
    BT_ATT_ERR_INVALID_OFFSET = 7,
    BT_ATT_ERR_INVALID_ATTRIBUTE_LEN = 13,
    BT_ATT_ERR_UNLIKELY = 14,
    BT_ATT_FIRST_ATTRIBUTE_HANDLE = 1,
    BT_ATT_LAST_ATTRIBUTE_HANDLE = 65535,
    BT_GATT_DISCOVER_PRIMARY = 0,
    BT_GATT_DISCOVER_CHARACTERISTIC = 3,
    BT_GATT_DISCOVER_DESCRIPTOR = 4,
    BT_GATT_SUBSCRIBE_FLAG_VOLATILE = 0
};
#define BT_GATT_ERR(value) (-static_cast<int>(value))
#define MAX(a, b) ((a) > (b) ? (a) : (b))
struct bt_uuid
{
    std::uint8_t type;
};
struct bt_uuid_16
{
    bt_uuid uuid;
    std::uint16_t val;
};
struct bt_uuid_128
{
    bt_uuid uuid;
    std::uint8_t val[16];
};
inline const bt_uuid_16 mock_primary{{BT_UUID_TYPE_16}, 0x2800};
inline const bt_uuid_16 mock_chrc{{BT_UUID_TYPE_16}, 0x2803};
inline const bt_uuid_16 mock_ccc{{BT_UUID_TYPE_16}, 0x2902};
#define BT_UUID_GATT_PRIMARY (&mock_primary.uuid)
#define BT_UUID_GATT_CHRC (&mock_chrc.uuid)
#define BT_UUID_GATT_CCC (&mock_ccc.uuid)
struct bt_gatt_attr
{
    const bt_uuid *uuid;
    ssize_t (*read)(bt_conn *, const bt_gatt_attr *, void *, std::uint16_t, std::uint16_t);
    ssize_t (*write)(bt_conn *, const bt_gatt_attr *, const void *, std::uint16_t, std::uint16_t,
                     std::uint8_t);
    void *user_data;
    std::uint16_t handle;
    std::uint16_t perm;
};
struct bt_gatt_service
{
    bt_gatt_attr *attrs;
    std::size_t attr_count;
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
    std::uint8_t properties;
};
struct bt_gatt_ccc_managed_user_data
{
    void (*cfg_changed)(const bt_gatt_attr *, std::uint16_t);
    ssize_t (*cfg_write)(bt_conn *, const bt_gatt_attr *, std::uint16_t);
    bool (*cfg_match)(bt_conn *, const bt_gatt_attr *);
};
struct bt_gatt_notify_params
{
    const bt_uuid *uuid;
    const bt_gatt_attr *attr;
    const void *data;
    std::uint16_t len;
    void (*func)(bt_conn *, void *);
    void *user_data;
};
struct bt_gatt_indicate_params
{
    const bt_uuid *uuid;
    const bt_gatt_attr *attr;
    void (*func)(bt_conn *, bt_gatt_indicate_params *, std::uint8_t);
    void (*destroy)(bt_gatt_indicate_params *);
    const void *data;
    std::uint16_t len;
};
struct bt_gatt_discover_params
{
    const bt_uuid *uuid;
    std::uint8_t (*func)(bt_conn *, const bt_gatt_attr *, bt_gatt_discover_params *);
    std::uint16_t start_handle, end_handle;
    std::uint8_t type;
};
struct bt_gatt_read_params
{
    std::uint8_t (*func)(bt_conn *, std::uint8_t, bt_gatt_read_params *, const void *,
                         std::uint16_t);
    std::uint8_t handle_count;
    struct
    {
        std::uint16_t handle, offset;
    } single;
};
struct bt_gatt_write_params
{
    void (*func)(bt_conn *, std::uint8_t, bt_gatt_write_params *);
    std::uint16_t handle, offset;
    const void *data;
    std::uint16_t length;
};
struct bt_gatt_subscribe_params
{
    std::uint8_t (*notify)(bt_conn *, bt_gatt_subscribe_params *, const void *, std::uint16_t);
    void (*subscribe)(bt_conn *, std::uint8_t, bt_gatt_subscribe_params *);
    std::uint16_t value_handle, ccc_handle, value;
    int flags[1];
};
/** @brief Zephyr의 POD subscription flags만 단일 test thread에서 갱신합니다. */
inline void atomic_set_bit(int *flags, int bit)
{
    *flags |= 1 << bit;
}
inline int mock_registration_calls = 0, mock_unregister_calls = 0, mock_register_fail_at = 0;
inline bt_gatt_service *mock_services[4]{};
inline int bt_gatt_service_register(bt_gatt_service *service)
{
    ++mock_registration_calls;
    if (mock_registration_calls == mock_register_fail_at)
    {
        return -EIO;
    }
    mock_services[mock_registration_calls - 1] = service;
    return 0;
}
inline int bt_gatt_service_unregister(bt_gatt_service *)
{
    ++mock_unregister_calls;
    return 0;
}
inline ssize_t bt_gatt_attr_read(bt_conn *, const bt_gatt_attr *, void *output,
                                 std::uint16_t capacity, std::uint16_t offset, const void *value,
                                 std::uint16_t length)
{
    if (offset > length)
    {
        return BT_GATT_ERR(BT_ATT_ERR_INVALID_OFFSET);
    }
    const auto copied = std::min<unsigned>(capacity, length - offset);
    std::memcpy(output, static_cast<const std::uint8_t *>(value) + offset, copied);
    return copied;
}
inline ssize_t bt_gatt_attr_read_service(bt_conn *, const bt_gatt_attr *, void *, std::uint16_t,
                                         std::uint16_t)
{
    return 0;
}
inline ssize_t bt_gatt_attr_read_chrc(bt_conn *, const bt_gatt_attr *, void *, std::uint16_t,
                                      std::uint16_t)
{
    return 0;
}
inline ssize_t bt_gatt_attr_read_ccc(bt_conn *, const bt_gatt_attr *, void *, std::uint16_t,
                                     std::uint16_t)
{
    return 0;
}
inline ssize_t bt_gatt_attr_write_ccc(bt_conn *, const bt_gatt_attr *, const void *, std::uint16_t,
                                      std::uint16_t, std::uint8_t)
{
    return 0;
}
inline bool mock_server_subscribed = true;
inline bool bt_gatt_is_subscribed(bt_conn *, const bt_gatt_attr *, std::uint16_t)
{
    return mock_server_subscribed;
}
inline int mock_notify_error = 0, mock_indicate_error = 0, mock_discover_error = 0;
inline int mock_read_error = 0, mock_write_error = 0, mock_subscribe_error = 0,
           mock_unsubscribe_error = 0;
inline bt_gatt_notify_params mock_notification{};
inline std::uint8_t mock_notification_data[244]{};
inline bt_gatt_indicate_params *mock_indication{};
inline bt_gatt_discover_params *mock_discovery{};
inline bt_gatt_read_params *mock_read{};
inline bt_gatt_write_params *mock_write{};
inline bt_gatt_subscribe_params *mock_subscription{};
inline void (*mock_command_callback)(bt_conn *, void *){};
inline int bt_gatt_notify_cb(bt_conn *, bt_gatt_notify_params *p)
{
    mock_notification = *p;
    std::memcpy(mock_notification_data, p->data, p->len);
    return mock_notify_error;
}
inline int bt_gatt_indicate(bt_conn *, bt_gatt_indicate_params *p)
{
    mock_indication = p;
    return mock_indicate_error;
}
inline int bt_gatt_discover(bt_conn *, bt_gatt_discover_params *p)
{
    mock_discovery = p;
    return mock_discover_error;
}
inline int bt_gatt_read(bt_conn *, bt_gatt_read_params *p)
{
    mock_read = p;
    return mock_read_error;
}
inline int bt_gatt_write(bt_conn *, bt_gatt_write_params *p)
{
    mock_write = p;
    return mock_write_error;
}
inline int bt_gatt_write_without_response_cb(bt_conn *, std::uint16_t, const void *, std::uint16_t,
                                             bool, void (*callback)(bt_conn *, void *), void *)
{
    mock_command_callback = callback;
    return mock_write_error;
}
inline int bt_gatt_subscribe(bt_conn *, bt_gatt_subscribe_params *p)
{
    mock_subscription = p;
    return mock_subscribe_error;
}
inline int bt_gatt_unsubscribe(bt_conn *, bt_gatt_subscribe_params *)
{
    return mock_unsubscribe_error;
}
