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
    BT_GATT_PERM_PREPARE_WRITE = 64,
    BT_GATT_CCC_NOTIFY = 1,
    BT_GATT_CCC_INDICATE = 2,
    BT_GATT_WRITE_FLAG_PREPARE = 1,
    BT_GATT_WRITE_FLAG_CMD = 2,
    BT_GATT_WRITE_FLAG_EXECUTE = 4,
    BT_GATT_ITER_STOP = 0,
    BT_GATT_ITER_CONTINUE = 1,
    BT_ATT_ERR_NOT_SUPPORTED = 6,
    BT_ATT_ERR_INVALID_OFFSET = 7,
    BT_ATT_ERR_AUTHORIZATION = 8,
    BT_ATT_ERR_PREPARE_QUEUE_FULL = 9,
    BT_ATT_ERR_INVALID_ATTRIBUTE_LEN = 13,
    BT_ATT_ERR_UNLIKELY = 14,
    BT_ATT_FIRST_ATTRIBUTE_HANDLE = 1,
    BT_ATT_LAST_ATTRIBUTE_HANDLE = 65535,
    BT_GATT_DISCOVER_PRIMARY = 0,
    BT_GATT_DISCOVER_CHARACTERISTIC = 3,
    BT_GATT_DISCOVER_DESCRIPTOR = 4,
    BT_GATT_SUBSCRIBE_FLAG_VOLATILE = 0
};
enum bt_att_chan_opt
{
    BT_ATT_CHAN_OPT_NONE = 0,
    BT_ATT_CHAN_OPT_UNENHANCED_ONLY = 1,
    BT_ATT_CHAN_OPT_ENHANCED_ONLY = 2,
};
#define BT_UUID_GATT_DB_HASH_VAL 0x2B2A
#define BT_UUID_GATT_SERVICE_VAL 0x1801
#define BT_UUID_GATT_SC_VAL 0x2A05
#define BT_UUID_GATT_CLIENT_FEATURES_VAL 0x2B29
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
inline const bt_uuid_16 mock_database_hash_uuid{{BT_UUID_TYPE_16}, BT_UUID_GATT_DB_HASH_VAL};
inline const bt_uuid_16 mock_gatt_service_uuid{{BT_UUID_TYPE_16}, BT_UUID_GATT_SERVICE_VAL};
inline const bt_uuid_16 mock_service_changed_uuid{{BT_UUID_TYPE_16}, BT_UUID_GATT_SC_VAL};
inline const bt_uuid_16 mock_client_features_uuid{{BT_UUID_TYPE_16},
                                                  BT_UUID_GATT_CLIENT_FEATURES_VAL};
#define BT_UUID_GATT_PRIMARY (&mock_primary.uuid)
#define BT_UUID_GATT_CHRC (&mock_chrc.uuid)
#define BT_UUID_GATT_CCC (&mock_ccc.uuid)
#define BT_UUID_GATT_DB_HASH (&mock_database_hash_uuid.uuid)
#define BT_UUID_GATT (&mock_gatt_service_uuid.uuid)
#define BT_UUID_GATT_SC (&mock_service_changed_uuid.uuid)
#define BT_UUID_GATT_CLIENT_FEATURES (&mock_client_features_uuid.uuid)
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
    struct
    {
        std::uint16_t *handles;
        bool variable;
    } multiple;
#if defined(CONFIG_BT_EATT)
    int chan_opt;
#endif
};
using bt_gatt_discover_func_t = std::uint8_t (*)(
    bt_conn *, const bt_gatt_attr *, bt_gatt_discover_params *);
struct bt_gatt_write_params
{
    void (*func)(bt_conn *, std::uint8_t, bt_gatt_write_params *);
    std::uint16_t handle, offset;
    const void *data;
    std::uint16_t length;
#if defined(CONFIG_BT_EATT)
    int chan_opt;
#endif
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
inline std::uint8_t mock_database_hash[16] = {
    0x10U, 0x11U, 0x12U, 0x13U, 0x14U, 0x15U, 0x16U, 0x17U,
    0x18U, 0x19U, 0x1aU, 0x1bU, 0x1cU, 0x1dU, 0x1eU, 0x1fU,
};
inline ssize_t mock_database_hash_read(bt_conn *, const bt_gatt_attr *, void *output,
                                       std::uint16_t capacity, std::uint16_t offset)
{
    if (offset > sizeof(mock_database_hash))
    {
        return BT_GATT_ERR(BT_ATT_ERR_INVALID_OFFSET);
    }
    const std::size_t copied =
        std::min<std::size_t>(capacity, sizeof(mock_database_hash) - offset);
    std::memcpy(output, mock_database_hash + offset, copied);
    return static_cast<ssize_t>(copied);
}
inline bt_gatt_attr mock_database_hash_attribute{
    BT_UUID_GATT_DB_HASH, mock_database_hash_read, nullptr, nullptr, 0x0006U, BT_GATT_PERM_READ};
inline void bt_gatt_foreach_attr(std::uint16_t, std::uint16_t,
                                 std::uint8_t (*callback)(const bt_gatt_attr *, std::uint16_t,
                                                          void *),
                                 void *context)
{
    callback(&mock_database_hash_attribute, mock_database_hash_attribute.handle, context);
}
inline int mock_registration_calls = 0, mock_unregister_calls = 0, mock_register_fail_at = 0;
inline bt_gatt_service *mock_revision_service{};
inline int mock_revision_register_error = 0;
inline bt_gatt_service *mock_services[4]{};
inline int bt_gatt_service_register(bt_gatt_service *service)
{
    if (service->attr_count == 1U && service->attrs[0].uuid == BT_UUID_GATT_PRIMARY &&
        service->attrs[0].user_data != nullptr)
    {
        mock_revision_service = service;
        return mock_revision_register_error;
    }
    ++mock_registration_calls;
    if (mock_registration_calls == mock_register_fail_at)
    {
        return -EIO;
    }
    mock_services[mock_registration_calls - 1] = service;
    return 0;
}
inline int bt_gatt_service_unregister(bt_gatt_service *service)
{
    if (service == mock_revision_service)
    {
        mock_revision_service = nullptr;
        return 0;
    }
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
inline bt_conn *mock_notification_connection{};
inline std::uint8_t mock_notification_data[512]{};
inline bt_gatt_indicate_params *mock_indication{};
inline bt_conn *mock_indication_connection{};
inline bt_gatt_discover_params *mock_discovery{};
inline bt_gatt_read_params *mock_read{};
inline bt_gatt_write_params *mock_write{};
inline bt_gatt_subscribe_params *mock_subscription{};
inline bt_gatt_discover_params *mock_discoveries[4]{};
inline bt_gatt_read_params *mock_reads[4]{};
inline bt_gatt_write_params *mock_writes[4]{};
inline bt_gatt_subscribe_params *mock_subscriptions[4]{};
inline void (*mock_command_callback)(bt_conn *, void *){};
inline void *mock_command_user_data{};
inline void (*mock_command_callbacks[4])(bt_conn *, void *){};
inline void *mock_command_user_data_by_connection[4]{};
inline bool mock_command_signed[4]{};
inline std::size_t mock_eatt_channels[4]{};
inline std::size_t mock_eatt_connect_requests[4]{};
inline int bt_gatt_notify_cb(bt_conn *connection, bt_gatt_notify_params *p)
{
    mock_notification_connection = connection;
    mock_notification = *p;
    std::memcpy(mock_notification_data, p->data, p->len);
    return mock_notify_error;
}
inline int bt_gatt_indicate(bt_conn *connection, bt_gatt_indicate_params *p)
{
    mock_indication_connection = connection;
    mock_indication = p;
    return mock_indicate_error;
}
inline int bt_gatt_discover(bt_conn *connection, bt_gatt_discover_params *p)
{
    mock_discovery = p;
    mock_discoveries[static_cast<std::size_t>(connection - mock_connections)] = p;
    return mock_discover_error;
}
inline int bt_gatt_read(bt_conn *connection, bt_gatt_read_params *p)
{
    mock_read = p;
    mock_reads[static_cast<std::size_t>(connection - mock_connections)] = p;
    return mock_read_error;
}
inline int bt_gatt_write(bt_conn *connection, bt_gatt_write_params *p)
{
    mock_write = p;
    mock_writes[static_cast<std::size_t>(connection - mock_connections)] = p;
    return mock_write_error;
}
inline int bt_gatt_write_without_response_cb(bt_conn *connection, std::uint16_t, const void *,
                                             std::uint16_t,
                                             bool sign, void (*callback)(bt_conn *, void *),
                                             void *user_data)
{
    mock_command_callback = callback;
    mock_command_user_data = user_data;
    const std::size_t index = static_cast<std::size_t>(connection - mock_connections);
    mock_command_callbacks[index] = callback;
    mock_command_user_data_by_connection[index] = user_data;
    mock_command_signed[index] = sign;
    return mock_write_error;
}
extern "C" inline int bt_eatt_connect(bt_conn *connection, std::size_t count)
{
    const std::size_t index = static_cast<std::size_t>(connection - mock_connections);
    mock_eatt_connect_requests[index] = count;
    mock_eatt_channels[index] += count;
    return 0;
}
extern "C" inline std::size_t bt_eatt_count(bt_conn *connection)
{
    return mock_eatt_channels[static_cast<std::size_t>(connection - mock_connections)];
}
extern "C" inline int bt_eatt_disconnect(bt_conn *connection)
{
    mock_eatt_channels[static_cast<std::size_t>(connection - mock_connections)] = 0U;
    return 0;
}
inline int bt_gatt_subscribe(bt_conn *connection, bt_gatt_subscribe_params *p)
{
    mock_subscription = p;
    mock_subscriptions[static_cast<std::size_t>(connection - mock_connections)] = p;
    return mock_subscribe_error;
}
inline int bt_gatt_unsubscribe(bt_conn *, bt_gatt_subscribe_params *)
{
    return mock_unsubscribe_error;
}
