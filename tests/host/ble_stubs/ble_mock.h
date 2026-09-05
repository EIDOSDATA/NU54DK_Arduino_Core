/** @file @brief 무선 I/O 없이 BLE callback·reference와 driver 오류를 주입합니다. */
#pragma once
#include <cstdint>
#include <cstddef>
#include <cassert>
#include <cerrno>
struct bt_addr_t
{
    std::uint8_t val[6];
};
struct bt_addr_le_t
{
    std::uint8_t type;
    bt_addr_t a;
};
enum
{
    BT_ADDR_LE_PUBLIC = 0,
    BT_ADDR_LE_RANDOM = 1,
    BT_ADDR_LE_PUBLIC_ID = 2
};
using bt_security_t = std::uint8_t;
enum bt_security_err
{
    BT_SECURITY_ERR_SUCCESS = 0,
    BT_SECURITY_ERR_AUTH_FAIL = 1
};
struct bt_conn
{
    int refs{0};
    int disconnects{0};
    std::uint8_t security{1};
};
inline bt_conn mock_connections[4];
inline bt_conn *mock_next_connection = &mock_connections[0];
inline int mock_create_error = 0, mock_disconnect_error = 0, mock_mtu_error = 0;
inline int mock_start_error = 0, mock_name_error = 0, mock_settings_error = 0;
inline int mock_enable_calls = 0, mock_settings_calls = 0;
inline bool mock_stack_ready = false;
inline bt_conn *bt_conn_ref(bt_conn *c)
{
    ++c->refs;
    return c;
}
inline void bt_conn_unref(bt_conn *c)
{
    assert(c->refs > 0);
    --c->refs;
}
inline int bt_conn_disconnect(bt_conn *c, std::uint8_t)
{
    ++c->disconnects;
    return mock_disconnect_error;
}
struct bt_conn_le_phy_info
{
    std::uint8_t tx_phy{1};
};
struct bt_conn_info
{
    int type;
    struct
    {
        bt_conn_le_phy_info *phy;
    } le;
};
struct bt_conn_le_phy_param
{
    std::uint16_t options;
    std::uint8_t pref_tx_phy;
    std::uint8_t pref_rx_phy;
};
struct bt_conn_le_tx_power
{
    std::uint8_t phy;
    std::int8_t current_level;
    std::int8_t max_level;
};
struct bt_le_conn_param
{
    std::uint16_t interval_min, interval_max, latency, timeout;
};
inline const bt_le_conn_param mock_default_parameters{24, 40, 0, 400};
#define BT_LE_CONN_PARAM_DEFAULT (&mock_default_parameters)
#define BT_CONN_LE_CREATE_CONN nullptr
inline int bt_conn_le_create(const bt_addr_le_t *, const void *, const bt_le_conn_param *,
                             bt_conn **c)
{
    if (mock_create_error != 0)
    {
        return mock_create_error;
    }
    *c = bt_conn_ref(mock_next_connection);
    return 0;
}
inline int bt_conn_get_info(bt_conn *, bt_conn_info *info)
{
    static bt_conn_le_phy_info phy{};
    info->type = 1;
    info->le.phy = &phy;
    return 0;
}
inline int bt_conn_le_phy_update(bt_conn *, const bt_conn_le_phy_param *)
{
    return 0;
}
inline int bt_conn_le_get_tx_power_level(bt_conn *, bt_conn_le_tx_power *power)
{
    power->current_level = -4;
    return 0;
}
inline int bt_conn_le_param_update(bt_conn *, const bt_le_conn_param *)
{
    return 0;
}
struct bt_conn_cb;
inline bt_conn_cb *mock_conn_callbacks{};
struct bt_conn_cb
{
    void (*connected)(bt_conn *, std::uint8_t){};
    void (*disconnected)(bt_conn *, std::uint8_t){};
    void (*le_param_updated)(bt_conn *, std::uint16_t, std::uint16_t, std::uint16_t){};
    void (*security_changed)(bt_conn *, bt_security_t, bt_security_err){};
    void (*le_phy_updated)(bt_conn *, bt_conn_le_phy_info *){};
    int registered{(mock_conn_callbacks = this, 0)};
};
#define BT_CONN_CB_DEFINE(name) bt_conn_cb name
struct bt_gatt_exchange_params
{
    void (*func)(bt_conn *, std::uint8_t, bt_gatt_exchange_params *);
};
struct bt_gatt_cb
{
    void (*att_mtu_updated)(bt_conn *, std::uint16_t, std::uint16_t);
};
inline bt_gatt_cb *mock_gatt_callbacks{};
inline bt_gatt_exchange_params *mock_mtu_parameters{};
inline void bt_gatt_cb_register(bt_gatt_cb *callbacks)
{
    mock_gatt_callbacks = callbacks;
}
inline std::uint16_t bt_gatt_get_mtu(bt_conn *)
{
    return 247;
}
inline int bt_gatt_exchange_mtu(bt_conn *, bt_gatt_exchange_params *params)
{
    mock_mtu_parameters = params;
    return mock_mtu_error;
}
struct net_buf_simple
{
    std::uint8_t *data;
    std::size_t len;
};
struct bt_data
{
    std::uint8_t type;
    std::uint8_t data_len;
    const std::uint8_t *data;
};
struct bt_le_adv_param
{
    std::uint8_t id, sid, secondary_max_skip;
    std::uint32_t options;
    std::uint32_t interval_min, interval_max;
    const bt_addr_le_t *peer;
};
struct bt_le_scan_param
{
    std::uint8_t type;
    std::uint32_t options;
    std::uint16_t interval, window, timeout, interval_coded, window_coded;
};
using MockScanCallback = void (*)(const bt_addr_le_t *, std::int8_t, std::uint8_t,
                                  net_buf_simple *);
inline MockScanCallback mock_scan_callback{};
inline int bt_le_scan_start(const bt_le_scan_param *, MockScanCallback callback)
{
    mock_scan_callback = callback;
    return mock_start_error;
}
inline int bt_le_scan_stop()
{
    return 0;
}
inline unsigned mock_advertising_calls = 0;
inline std::uint32_t mock_advertising_options = 0;
inline int bt_le_adv_start(const bt_le_adv_param *parameters, const bt_data *, std::size_t,
                           const bt_data *, std::size_t)
{
    ++mock_advertising_calls;
    mock_advertising_options = parameters->options;
    return mock_start_error;
}
inline int bt_le_adv_stop()
{
    return 0;
}
inline int bt_set_name(const char *)
{
    return mock_name_error;
}
inline bool bt_is_ready()
{
    return mock_stack_ready;
}
inline int bt_enable(void *)
{
    ++mock_enable_calls;
    mock_stack_ready = true;
    return 0;
}
inline int settings_load()
{
    ++mock_settings_calls;
    return mock_settings_error;
}
enum
{
    BT_ID_DEFAULT = 0,
    BT_LE_AD_GENERAL = 2,
    BT_LE_AD_NO_BREDR = 4,
    BT_LE_SCAN_TYPE_ACTIVE = 1,
    BT_LE_SCAN_TYPE_PASSIVE = 0,
    BT_LE_SCAN_OPT_FILTER_DUPLICATE = 1,
    BT_GAP_SCAN_FAST_INTERVAL = 96,
    BT_GAP_SCAN_FAST_WINDOW = 48,
    BT_GAP_ADV_TYPE_ADV_IND = 0,
    BT_GAP_ADV_TYPE_ADV_DIRECT_IND = 1,
    BT_GAP_ADV_TYPE_SCAN_RSP = 4,
    BT_GAP_LE_PHY_1M = 1,
    BT_GAP_LE_PHY_2M = 2,
    BT_GAP_LE_PHY_CODED = 4,
    BT_CONN_TYPE_LE = 1,
    BT_CONN_LE_PHY_OPT_NONE = 0,
    BT_HCI_ERR_REMOTE_USER_TERM_CONN = 0x13,
    BT_DATA_FLAGS = 1,
    BT_DATA_UUID16_SOME = 2,
    BT_DATA_UUID16_ALL = 3,
    BT_DATA_UUID32_SOME = 4,
    BT_DATA_UUID32_ALL = 5,
    BT_DATA_UUID128_SOME = 6,
    BT_DATA_UUID128_ALL = 7,
    BT_DATA_NAME_SHORTENED = 8,
    BT_DATA_NAME_COMPLETE = 9,
    BT_DATA_SVC_DATA16 = 0x16,
    BT_DATA_SVC_DATA32 = 0x20,
    BT_DATA_SVC_DATA128 = 0x21,
    BT_DATA_MANUFACTURER_DATA = 0xFF
};
/** @brief 고정 NCS header의 advertising option bit와 별도 enum 범위를 유지합니다. */
enum
{
    BT_LE_ADV_OPT_NONE = 0,
    BT_LE_ADV_OPT_CONN = 3,
    BT_LE_ADV_OPT_SCANNABLE = 512,
};
