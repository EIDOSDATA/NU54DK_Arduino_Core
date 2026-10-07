/** @file @brief native connection 수명과 보안 수준을 제어합니다. */
#pragma once
#include <cstdint>
struct bt_conn
{
    unsigned security = 2U;
    unsigned references = 0U;
};
inline bt_conn native_connection;
inline unsigned bt_conn_get_security(bt_conn *conn)
{
    return conn->security;
}
inline void bt_conn_unref(bt_conn *conn)
{
    --conn->references;
}
constexpr unsigned BT_SECURITY_L2 = 2U;
struct bt_conn_cb
{
    void (*disconnected)(bt_conn *, std::uint8_t);
};
inline bt_conn_cb *native_callbacks = nullptr;
#define BT_CONN_CB_DEFINE(name)                                                                    \
    bt_conn_cb name;                                                                               \
    static auto *name##_registration = (native_callbacks = &name);                                 \
    bt_conn_cb &name##_definition = name
