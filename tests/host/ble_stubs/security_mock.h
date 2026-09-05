/** @file @brief SMP·bond snapshot·profile 실패를 제어하는 Host driver입니다. */
#pragma once
#include <ble_mock.h>
#include <cstring>
#include <string>
#include <map>
enum
{
    BT_SECURITY_L1 = 1,
    BT_SECURITY_L2 = 2,
    BT_SECURITY_L3 = 3,
    BT_SECURITY_L4 = 4
};
inline bt_addr_le_t mock_peer{BT_ADDR_LE_PUBLIC, {{1, 2, 3, 4, 5, 6}}};
inline const bt_addr_le_t mock_any{};
#define BT_ADDR_LE_ANY (&mock_any)
inline void bt_addr_le_copy(bt_addr_le_t *out, const bt_addr_le_t *in)
{
    *out = *in;
}
inline bool bt_addr_le_eq(const bt_addr_le_t *a, const bt_addr_le_t *b)
{
    return std::memcmp(a, b, sizeof(*a)) == 0;
}
inline const bt_addr_le_t *bt_conn_get_dst(bt_conn *)
{
    return &mock_peer;
}
inline bt_security_t bt_conn_get_security(bt_conn *c)
{
    return c->security;
}
inline int mock_security_error = 0, mock_auth_error = 0, mock_auth_register_error = 0;
inline unsigned mock_cancel_calls = 0, mock_confirm_calls = 0, mock_security_calls = 0;
inline int bt_conn_set_security(bt_conn *, bt_security_t)
{
    ++mock_security_calls;
    return mock_security_error;
}
inline int bt_conn_auth_cancel(bt_conn *)
{
    ++mock_cancel_calls;
    return mock_auth_error;
}
inline int bt_conn_auth_pairing_confirm(bt_conn *)
{
    ++mock_confirm_calls;
    return mock_auth_error;
}
inline int bt_conn_auth_passkey_entry(bt_conn *, unsigned int)
{
    return mock_auth_error;
}
inline int bt_conn_auth_passkey_confirm(bt_conn *)
{
    return mock_auth_error;
}
struct bt_conn_pairing_feat
{
};
struct bt_conn_auth_cb
{
    bt_security_err (*pairing_accept)(bt_conn *, const bt_conn_pairing_feat *);
    void (*passkey_display)(bt_conn *, unsigned int);
    void (*passkey_entry)(bt_conn *);
    void (*passkey_confirm)(bt_conn *, unsigned int);
    void (*cancel)(bt_conn *);
    void (*pairing_confirm)(bt_conn *);
};
struct bt_conn_auth_info_cb
{
    void (*pairing_complete)(bt_conn *, bool);
    void (*pairing_failed)(bt_conn *, bt_security_err);
    void (*bond_deleted)(std::uint8_t, const bt_addr_le_t *);
};
inline bt_conn_auth_cb *mock_auth{};
inline bt_conn_auth_info_cb *mock_auth_info{};
inline int bt_conn_auth_cb_register(bt_conn_auth_cb *p)
{
    mock_auth = p;
    return mock_auth_register_error;
}
inline int bt_conn_auth_info_cb_register(bt_conn_auth_info_cb *p)
{
    mock_auth_info = p;
    return mock_auth_register_error;
}
inline bool mock_bondable = false, mock_saved_bond = false;
inline int mock_unpair_error = 0;
struct bt_bond_info
{
    bt_addr_le_t addr;
};
inline void bt_set_bondable(bool value)
{
    mock_bondable = value;
}
inline void bt_foreach_bond(std::uint8_t, void (*callback)(const bt_bond_info *, void *),
                            void *context)
{
    if (mock_saved_bond)
    {
        const bt_bond_info bond{mock_peer};
        callback(&bond, context);
    }
}
inline int bt_unpair(std::uint8_t, const bt_addr_le_t *peer)
{
    if (mock_unpair_error == 0)
    {
        mock_saved_bond = false;
        if (mock_auth_info != nullptr && mock_auth_info->bond_deleted != nullptr)
        {
            mock_auth_info->bond_deleted(0, peer == BT_ADDR_LE_ANY ? &mock_peer : peer);
        }
    }
    return mock_unpair_error;
}
inline int mock_battery_error = 0;
inline std::uint8_t mock_battery_level = 100;
inline int bt_bas_set_battery_level(std::uint8_t value)
{
    if (mock_battery_error == 0)
    {
        mock_battery_level = value;
    }
    return mock_battery_error;
}
inline std::uint8_t bt_bas_get_battery_level()
{
    return mock_battery_level;
}
inline std::map<std::string, std::string> mock_dis_values;
inline int mock_dis_fail_at = 0, mock_dis_calls = 0;
inline int settings_runtime_set(const char *key, const void *value, std::size_t length)
{
    if (++mock_dis_calls == mock_dis_fail_at)
    {
        return -EIO;
    }
    mock_dis_values[key] = std::string(static_cast<const char *>(value), length);
    return 0;
}
#include <bluetooth/services/hids.h>
inline bt_hids mock_hids{};
inline bt_hids_init_param mock_hids_parameters{};
inline int mock_hids_init_error = 0, mock_hids_attach_error = 0, mock_hids_detach_error = 0,
           mock_hids_send_error = 0;
inline unsigned mock_hids_attach_calls = 0, mock_hids_detach_calls = 0, mock_hids_send_calls = 0;
inline bool mock_hids_boot = false;
inline std::uint8_t mock_hids_data[8]{};
