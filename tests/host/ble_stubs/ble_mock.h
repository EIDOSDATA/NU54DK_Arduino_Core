/** @file @brief 무선 I/O 없이 BLE callback·reference와 driver 오류를 주입합니다. */
#pragma once
#include <cstdint>
#include <cstddef>
#include <cassert>
#include <cerrno>
#include <cstring>
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
    bt_addr_le_t peer{BT_ADDR_LE_PUBLIC, {{1, 2, 3, 4, 5, 6}}};
    std::uint16_t mtu{247};
    std::int8_t tx_power{-4};
    unsigned parameter_updates{0};
    unsigned phy_updates{0};
    unsigned data_length_updates{0};
    std::uint32_t interval_us{30000U};
    std::uint16_t latency{0U};
    std::uint16_t supervision_timeout{400U};
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
struct bt_conn_le_data_len_info
{
    std::uint16_t tx_max_len{27U};
    std::uint16_t tx_max_time{328U};
    std::uint16_t rx_max_len{27U};
    std::uint16_t rx_max_time{328U};
};
struct bt_conn_le_data_len_param
{
    std::uint16_t tx_max_len;
    std::uint16_t tx_max_time;
};
struct bt_conn_info
{
    int type;
    struct
    {
        const bt_addr_le_t *src;
        const bt_addr_le_t *dst;
        const bt_addr_le_t *local;
        const bt_addr_le_t *remote;
        std::uint32_t interval_us;
        std::uint16_t latency;
        std::uint16_t timeout;
        bt_conn_le_phy_info *phy;
        bt_conn_le_data_len_info *data_len;
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
inline int bt_conn_le_create(const bt_addr_le_t *peer, const void *, const bt_le_conn_param *,
                             bt_conn **c)
{
    if (mock_create_error != 0)
    {
        return mock_create_error;
    }
    *c = bt_conn_ref(mock_next_connection);
    (*c)->peer = *peer;
    return 0;
}
inline const bt_addr_le_t *bt_conn_get_dst(const bt_conn *connection)
{
    return &connection->peer;
}
inline bt_conn_le_data_len_info mock_data_lengths[4]{};
inline int bt_conn_get_info(bt_conn *connection, bt_conn_info *info)
{
    static bt_conn_le_phy_info phy{};
    info->type = 1;
    info->le.src = nullptr;
    info->le.dst = &connection->peer;
    info->le.local = nullptr;
    info->le.remote = &connection->peer;
    info->le.interval_us = connection->interval_us;
    info->le.latency = connection->latency;
    info->le.timeout = connection->supervision_timeout;
    info->le.phy = &phy;
    info->le.data_len = &mock_data_lengths[static_cast<std::size_t>(connection - mock_connections)];
    return 0;
}
inline int bt_conn_le_phy_update(bt_conn *connection, const bt_conn_le_phy_param *)
{
    ++connection->phy_updates;
    return 0;
}
inline int mock_data_length_error = 0;
inline int bt_conn_le_data_len_update(bt_conn *connection,
                                      const bt_conn_le_data_len_param *parameters)
{
    ++connection->data_length_updates;
    if (mock_data_length_error == 0)
    {
        bt_conn_le_data_len_info &information =
            mock_data_lengths[static_cast<std::size_t>(connection - mock_connections)];
        information.tx_max_len = parameters->tx_max_len;
        information.tx_max_time = parameters->tx_max_time;
    }
    return mock_data_length_error;
}
struct bt_conn_remote_info
{
    std::uint8_t type;
    std::uint8_t version;
    std::uint16_t manufacturer;
    std::uint16_t subversion;
    struct
    {
        const std::uint8_t *features;
    } le;
};
inline std::uint8_t mock_remote_features[4][8]{};
inline bt_conn_remote_info mock_remote_information[4]{};
inline int mock_remote_information_error = 0;
inline int bt_conn_get_remote_info(const bt_conn *connection, bt_conn_remote_info *information)
{
    if (mock_remote_information_error != 0)
    {
        return mock_remote_information_error;
    }
    *information = mock_remote_information[
        static_cast<std::size_t>(connection - mock_connections)];
    return 0;
}
inline int bt_conn_le_get_tx_power_level(bt_conn *connection, bt_conn_le_tx_power *power)
{
    power->current_level = connection->tx_power;
    return 0;
}
inline int bt_conn_le_param_update(bt_conn *connection, const bt_le_conn_param *)
{
    ++connection->parameter_updates;
    return 0;
}
struct bt_conn_cb;
inline bt_conn_cb *mock_conn_callbacks{};
struct bt_conn_cb
{
    void (*connected)(bt_conn *, std::uint8_t){};
    void (*disconnected)(bt_conn *, std::uint8_t){};
    void (*le_param_updated)(bt_conn *, std::uint16_t, std::uint16_t, std::uint16_t){};
    void (*identity_resolved)(bt_conn *, const bt_addr_le_t *, const bt_addr_le_t *){};
    void (*security_changed)(bt_conn *, bt_security_t, bt_security_err){};
    void (*remote_info_available)(bt_conn *, bt_conn_remote_info *){};
    void (*le_phy_updated)(bt_conn *, bt_conn_le_phy_info *){};
    void (*le_data_len_updated)(bt_conn *, bt_conn_le_data_len_info *){};
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
inline bt_gatt_exchange_params *mock_mtu_parameter_history[8]{};
inline std::size_t mock_mtu_call_count = 0U;
inline void bt_gatt_cb_register(bt_gatt_cb *callbacks)
{
    mock_gatt_callbacks = callbacks;
}
inline std::uint16_t bt_gatt_get_mtu(bt_conn *connection)
{
    return connection->mtu;
}
inline int bt_gatt_exchange_mtu(bt_conn *, bt_gatt_exchange_params *params)
{
    mock_mtu_parameters = params;
    assert(mock_mtu_call_count < 8U);
    mock_mtu_parameter_history[mock_mtu_call_count++] = params;
    return mock_mtu_error;
}
struct net_buf_simple
{
    std::uint8_t *data;
    std::size_t len;
};
inline void net_buf_simple_init_with_data(net_buf_simple *buffer, void *data,
                                          std::size_t length)
{
    buffer->data = static_cast<std::uint8_t *>(data);
    buffer->len = length;
}
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
struct bt_le_ext_adv
{
    unsigned index{0U};
    bool active{false};
    bool deleted{false};
};
struct bt_le_per_adv_sync;
struct bt_le_ext_adv_sent_info
{
    std::uint8_t num_sent{0U};
};
struct bt_le_ext_adv_connected_info
{
    bt_conn *conn{};
};
struct bt_le_ext_adv_scanned_info
{
    const bt_addr_le_t *addr{};
};
struct bt_le_per_adv_data_request
{
    std::uint8_t start;
    std::uint8_t count;
};
struct bt_le_per_adv_response_info
{
    std::uint8_t subevent;
    std::uint8_t tx_status;
    std::int8_t tx_power;
    std::int8_t rssi;
    std::uint8_t cte_type;
    std::uint8_t response_slot;
};
struct bt_le_ext_adv_start_param
{
    std::uint16_t timeout;
    std::uint8_t num_events;
};
struct bt_le_ext_adv_cb
{
    void (*sent)(bt_le_ext_adv *, bt_le_ext_adv_sent_info *){};
    void (*connected)(bt_le_ext_adv *, bt_le_ext_adv_connected_info *){};
    void (*scanned)(bt_le_ext_adv *, bt_le_ext_adv_scanned_info *){};
#if defined(CONFIG_BT_PRIVACY)
    bool (*rpa_expired)(bt_le_ext_adv *){};
#endif
#if defined(CONFIG_BT_PER_ADV_RSP)
    void (*pawr_data_request)(bt_le_ext_adv *, const bt_le_per_adv_data_request *){};
    void (*pawr_response)(bt_le_ext_adv *, bt_le_per_adv_response_info *,
                          net_buf_simple *){};
#endif
};
inline bt_le_ext_adv mock_ext_advertisers[4];
inline std::size_t mock_ext_advertiser_count = 0U;
inline bt_le_ext_adv_cb *mock_ext_advertising_callbacks{};
inline std::uint32_t mock_ext_advertising_options = 0U;
inline std::uint8_t mock_ext_advertising_sid = 0U;
inline std::uint8_t mock_ext_advertising_data[255]{};
inline std::size_t mock_ext_advertising_length = 0U;
inline std::uint8_t mock_ext_scan_response_data[255]{};
inline std::size_t mock_ext_scan_response_length = 0U;
inline int mock_ext_create_error = 0;
inline int mock_ext_data_error = 0;
inline int mock_ext_start_error = 0;
inline int mock_ext_stop_error = 0;
inline int mock_ext_delete_error = 0;
inline int mock_rpa_timeout_error = 0;
inline std::uint16_t mock_rpa_timeout = 900U;
inline int bt_le_set_rpa_timeout(std::uint16_t seconds)
{
    if (mock_rpa_timeout_error == 0)
    {
        mock_rpa_timeout = seconds;
    }
    return mock_rpa_timeout_error;
}
inline int bt_le_ext_adv_create(const bt_le_adv_param *parameters, bt_le_ext_adv_cb *callbacks,
                                bt_le_ext_adv **advertiser)
{
    if (mock_ext_create_error != 0)
    {
        return mock_ext_create_error;
    }
    assert(mock_ext_advertiser_count < 4U);
    bt_le_ext_adv &instance = mock_ext_advertisers[mock_ext_advertiser_count];
    instance.index = static_cast<unsigned>(mock_ext_advertiser_count++);
    instance.active = false;
    instance.deleted = false;
    mock_ext_advertising_callbacks = callbacks;
    mock_ext_advertising_options = parameters->options;
    mock_ext_advertising_sid = parameters->sid;
    *advertiser = &instance;
    return 0;
}
inline void mock_encode_advertising_fields(const bt_data *fields, std::size_t count,
                                           std::uint8_t *output, std::size_t &length)
{
    length = 0U;
    for (std::size_t index = 0U; index < count; ++index)
    {
        const std::size_t field_length = static_cast<std::size_t>(fields[index].data_len) + 1U;
        assert(length + field_length + 1U <= 255U);
        output[length++] = static_cast<std::uint8_t>(field_length);
        output[length++] = fields[index].type;
        for (std::size_t offset = 0U; offset < fields[index].data_len; ++offset)
        {
            output[length++] = fields[index].data[offset];
        }
    }
}
inline int bt_le_ext_adv_set_data(bt_le_ext_adv *, const bt_data *advertising,
                                  std::size_t advertising_count, const bt_data *scan_response,
                                  std::size_t scan_response_count)
{
    if (mock_ext_data_error != 0)
    {
        return mock_ext_data_error;
    }
    mock_encode_advertising_fields(advertising, advertising_count, mock_ext_advertising_data,
                                   mock_ext_advertising_length);
    mock_encode_advertising_fields(scan_response, scan_response_count,
                                   mock_ext_scan_response_data, mock_ext_scan_response_length);
    return 0;
}
inline int bt_le_ext_adv_start(bt_le_ext_adv *advertiser,
                               const bt_le_ext_adv_start_param *)
{
    if (mock_ext_start_error != 0)
    {
        return mock_ext_start_error;
    }
    advertiser->active = true;
    return 0;
}
inline int bt_le_ext_adv_stop(bt_le_ext_adv *advertiser)
{
    if (mock_ext_stop_error != 0)
    {
        return mock_ext_stop_error;
    }
    advertiser->active = false;
    return 0;
}
inline int bt_le_ext_adv_delete(bt_le_ext_adv *advertiser)
{
    if (mock_ext_delete_error != 0)
    {
        return mock_ext_delete_error;
    }
    advertiser->deleted = true;
    return 0;
}
struct bt_le_per_adv_param
{
    std::uint16_t interval_min;
    std::uint16_t interval_max;
    std::uint32_t options;
#if defined(CONFIG_BT_PER_ADV_RSP)
    std::uint8_t num_subevents;
    std::uint8_t subevent_interval;
    std::uint8_t response_slot_delay;
    std::uint8_t response_slot_spacing;
    std::uint8_t num_response_slots;
#endif
};
struct bt_le_per_adv_sync
{
    unsigned index{0U};
    bool deleted{false};
};
struct bt_le_per_adv_sync_param
{
    bt_addr_le_t addr;
    std::uint8_t sid;
    std::uint32_t options;
    std::uint16_t skip;
    std::uint16_t timeout;
};
struct bt_le_per_adv_sync_synced_info
{
    const bt_addr_le_t *addr;
    std::uint8_t sid;
    std::uint16_t interval;
    std::uint8_t phy;
    bool recv_enabled;
    std::uint16_t service_data;
    bt_conn *conn;
#if defined(CONFIG_BT_PER_ADV_SYNC_RSP)
    std::uint8_t num_subevents;
    std::uint8_t subevent_interval;
    std::uint8_t response_slot_delay;
    std::uint8_t response_slot_spacing;
#endif
};
struct bt_le_per_adv_sync_term_info
{
    const bt_addr_le_t *addr;
    std::uint8_t sid;
    std::uint8_t reason;
};
struct bt_le_per_adv_sync_recv_info
{
    const bt_addr_le_t *addr;
    std::uint8_t sid;
    std::int8_t tx_power;
    std::int8_t rssi;
    std::uint8_t cte_type;
#if defined(CONFIG_BT_PER_ADV_SYNC_RSP)
    std::uint16_t periodic_event_counter;
    std::uint8_t subevent;
#endif
};
struct bt_le_per_adv_sync_state_info
{
    bool recv_enabled;
};
struct bt_le_per_adv_sync_cb
{
    void (*synced)(bt_le_per_adv_sync *, bt_le_per_adv_sync_synced_info *){};
    void (*term)(bt_le_per_adv_sync *, const bt_le_per_adv_sync_term_info *){};
    void (*recv)(bt_le_per_adv_sync *, const bt_le_per_adv_sync_recv_info *,
                 net_buf_simple *){};
    void (*state_changed)(bt_le_per_adv_sync *, const bt_le_per_adv_sync_state_info *){};
    void (*biginfo)(bt_le_per_adv_sync *, const void *){};
    void (*cte_report_cb)(bt_le_per_adv_sync *, const void *){};
};
struct bt_le_per_adv_sync_transfer_param
{
    std::uint16_t skip;
    std::uint16_t timeout;
    std::uint32_t options;
};
struct bt_le_per_adv_subevent_data_params
{
    std::uint8_t subevent;
    std::uint8_t response_slot_start;
    std::uint8_t response_slot_count;
    const net_buf_simple *data;
};
struct bt_le_per_adv_sync_subevent_params
{
    std::uint16_t properties;
    std::uint8_t num_subevents;
    std::uint8_t *subevents;
};
struct bt_le_per_adv_response_params
{
    std::uint16_t request_event;
    std::uint8_t request_subevent;
    std::uint8_t response_subevent;
    std::uint8_t response_slot;
};
inline bt_le_per_adv_sync mock_periodic_syncs[4];
inline std::size_t mock_periodic_sync_count = 0U;
inline bt_le_per_adv_sync_cb *mock_periodic_sync_callbacks{};
inline bt_le_per_adv_sync_param mock_periodic_sync_parameters{};
inline bt_le_per_adv_param mock_periodic_parameters{};
inline std::uint8_t mock_periodic_data[255]{};
inline std::size_t mock_periodic_data_length = 0U;
inline bool mock_periodic_advertising_active = false;
inline int mock_periodic_configure_error = 0;
inline int mock_periodic_data_error = 0;
inline int mock_periodic_start_error = 0;
inline int mock_periodic_stop_error = 0;
inline int mock_periodic_sync_create_error = 0;
inline int mock_periodic_sync_delete_error = 0;
inline int mock_past_error = 0;
inline unsigned mock_past_transfer_count = 0U;
inline unsigned mock_past_subscribe_count = 0U;
inline unsigned mock_past_unsubscribe_count = 0U;
inline unsigned mock_pawr_subevent_data_count = 0U;
inline unsigned mock_pawr_scanner_config_count = 0U;
inline unsigned mock_pawr_response_data_count = 0U;
inline bt_le_per_adv_response_params mock_pawr_response_parameters{};
inline std::uint8_t mock_pawr_response_data[249]{};
inline std::size_t mock_pawr_response_length = 0U;
inline int mock_pawr_error = 0;
inline int bt_le_per_adv_set_param(bt_le_ext_adv *, const bt_le_per_adv_param *parameters)
{
    mock_periodic_parameters = *parameters;
    return mock_periodic_configure_error;
}
inline int bt_le_per_adv_set_data(const bt_le_ext_adv *, const bt_data *fields,
                                  std::size_t count)
{
    if (mock_periodic_data_error != 0)
    {
        return mock_periodic_data_error;
    }
    mock_encode_advertising_fields(fields, count, mock_periodic_data,
                                   mock_periodic_data_length);
    return 0;
}
inline int bt_le_per_adv_start(bt_le_ext_adv *)
{
    if (mock_periodic_start_error != 0)
    {
        return mock_periodic_start_error;
    }
    mock_periodic_advertising_active = true;
    return 0;
}
inline int bt_le_per_adv_stop(bt_le_ext_adv *)
{
    if (mock_periodic_stop_error != 0)
    {
        return mock_periodic_stop_error;
    }
    mock_periodic_advertising_active = false;
    return 0;
}
inline int bt_le_per_adv_sync_cb_register(bt_le_per_adv_sync_cb *callbacks)
{
    mock_periodic_sync_callbacks = callbacks;
    return 0;
}
inline int bt_le_per_adv_sync_create(const bt_le_per_adv_sync_param *parameters,
                                     bt_le_per_adv_sync **sync)
{
    if (mock_periodic_sync_create_error != 0)
    {
        return mock_periodic_sync_create_error;
    }
    assert(mock_periodic_sync_count < 4U);
    bt_le_per_adv_sync &instance = mock_periodic_syncs[mock_periodic_sync_count];
    instance.index = static_cast<unsigned>(mock_periodic_sync_count++);
    instance.deleted = false;
    mock_periodic_sync_parameters = *parameters;
    *sync = &instance;
    return 0;
}
inline int bt_le_per_adv_sync_delete(bt_le_per_adv_sync *sync)
{
    if (mock_periodic_sync_delete_error != 0)
    {
        return mock_periodic_sync_delete_error;
    }
    sync->deleted = true;
    return 0;
}
inline int bt_le_per_adv_sync_transfer(const bt_le_per_adv_sync *, const bt_conn *,
                                       std::uint16_t)
{
    ++mock_past_transfer_count;
    return mock_past_error;
}
inline int bt_le_per_adv_set_info_transfer(const bt_le_ext_adv *, const bt_conn *,
                                           std::uint16_t)
{
    ++mock_past_transfer_count;
    return mock_past_error;
}
inline int bt_le_per_adv_sync_transfer_subscribe(
    const bt_conn *, const bt_le_per_adv_sync_transfer_param *)
{
    ++mock_past_subscribe_count;
    return mock_past_error;
}
inline int bt_le_per_adv_sync_transfer_unsubscribe(const bt_conn *)
{
    ++mock_past_unsubscribe_count;
    return mock_past_error;
}
inline int bt_le_per_adv_set_subevent_data(
    const bt_le_ext_adv *, std::uint8_t count,
    const bt_le_per_adv_subevent_data_params *)
{
    mock_pawr_subevent_data_count += count;
    return mock_pawr_error;
}
inline int bt_le_per_adv_sync_subevent(bt_le_per_adv_sync *,
                                       bt_le_per_adv_sync_subevent_params *)
{
    ++mock_pawr_scanner_config_count;
    return mock_pawr_error;
}
inline int bt_le_per_adv_set_response_data(bt_le_per_adv_sync *,
                                           const bt_le_per_adv_response_params *parameters,
                                           const net_buf_simple *data)
{
    ++mock_pawr_response_data_count;
    mock_pawr_response_parameters = *parameters;
    mock_pawr_response_length = data->len;
    if (data->len != 0U)
    {
        std::memcpy(mock_pawr_response_data, data->data, data->len);
    }
    return mock_pawr_error;
}
struct bt_le_scan_param
{
    std::uint8_t type;
    std::uint32_t options;
    std::uint16_t interval, window, timeout, interval_coded, window_coded;
};
struct bt_le_scan_recv_info
{
    const bt_addr_le_t *addr;
    std::uint8_t sid;
    std::int8_t rssi;
    std::int8_t tx_power;
    std::uint8_t adv_type;
    std::uint16_t adv_props;
    std::uint16_t interval;
    std::uint8_t primary_phy;
    std::uint8_t secondary_phy;
};
struct bt_le_scan_cb
{
    void (*recv)(const bt_le_scan_recv_info *, net_buf_simple *){};
    void (*timeout)(){};
};
inline bt_le_scan_cb *mock_extended_scan_callbacks{};
inline int bt_le_scan_cb_register(bt_le_scan_cb *callbacks)
{
    mock_extended_scan_callbacks = callbacks;
    return 0;
}
inline void bt_le_scan_cb_unregister(bt_le_scan_cb *callbacks)
{
    if (mock_extended_scan_callbacks == callbacks)
    {
        mock_extended_scan_callbacks = nullptr;
    }
}
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
    BT_LE_SCAN_OPT_CODED = 2,
    BT_GAP_SCAN_FAST_INTERVAL = 96,
    BT_GAP_SCAN_FAST_WINDOW = 48,
    BT_GAP_ADV_TYPE_ADV_IND = 0,
    BT_GAP_ADV_TYPE_ADV_DIRECT_IND = 1,
    BT_GAP_ADV_TYPE_SCAN_RSP = 4,
    BT_GAP_ADV_PROP_CONNECTABLE = 1,
    BT_GAP_ADV_PROP_SCANNABLE = 2,
    BT_GAP_ADV_PROP_SCAN_RESPONSE = 8,
    BT_GAP_ADV_PROP_EXT_ADV = 16,
    BT_GAP_SID_MAX = 15,
    BT_GAP_LE_PHY_1M = 1,
    BT_GAP_LE_PHY_2M = 2,
    BT_GAP_LE_PHY_CODED = 4,
    BT_GAP_DATA_LEN_DEFAULT = 27,
    BT_GAP_DATA_LEN_MAX = 251,
    BT_GAP_DATA_TIME_DEFAULT = 328,
    BT_GAP_DATA_TIME_MAX = 17040,
    BT_LE_PER_ADV_OPT_NONE = 0,
    BT_LE_PER_ADV_OPT_USE_TX_POWER = 2,
    BT_LE_PER_ADV_OPT_INCLUDE_ADI = 4,
    BT_LE_PER_ADV_SYNC_OPT_NONE = 0,
    BT_LE_PER_ADV_SYNC_OPT_FILTER_DUPLICATE = 2,
    BT_LE_PER_ADV_SYNC_TRANSFER_OPT_NONE = 0,
    BT_LE_PER_ADV_SYNC_TRANSFER_OPT_FILTER_DUPLICATES = 32,
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
    BT_LE_ADV_OPT_EXT_ADV = 1024,
    BT_LE_ADV_OPT_NO_2M = 2048,
    BT_LE_ADV_OPT_CODED = 4096,
    BT_LE_ADV_OPT_ANONYMOUS = 8192,
    BT_LE_ADV_OPT_USE_TX_POWER = 16384,
};
