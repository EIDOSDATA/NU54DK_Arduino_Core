/** @file @brief BLE Host driver 경계를 공유합니다. */
#pragma once
#include <ble_mock.h>
#include <zephyr/net_buf.h>

#define BT_HCI_OP_READ_RSSI 0x1405U
#define BT_HCI_ERR_SUCCESS 0x00U

struct bt_hci_cp_read_rssi
{
    std::uint16_t handle;
};

struct bt_hci_rp_read_rssi
{
    std::uint8_t status;
    std::uint16_t handle;
    std::int8_t rssi;
};

inline net_buf mock_hci_command_buffers[2]{};
inline net_buf_pool mock_hci_command_pool{mock_hci_command_buffers, 2U,
                                          net_buf::storage_size};
inline net_buf mock_hci_response_buffers[2]{};
inline net_buf_pool mock_hci_response_pool{mock_hci_response_buffers, 2U,
                                           net_buf::storage_size};
inline int mock_hci_handle_error = 0;
inline int mock_hci_command_error = 0;
inline std::uint8_t mock_hci_status = BT_HCI_ERR_SUCCESS;
inline std::int8_t mock_hci_rssi = -55;

using bt_hci_vnd_evt_cb_t = bool(struct net_buf_simple *buffer);
inline bt_hci_vnd_evt_cb_t *mock_hci_vendor_event_callback = nullptr;

inline int bt_hci_get_conn_handle(const bt_conn *connection, std::uint16_t *handle)
{
    if (mock_hci_handle_error != 0)
    {
        return mock_hci_handle_error;
    }
    *handle = static_cast<std::uint16_t>(connection - mock_connections + 1);
    return 0;
}

inline bt_conn *bt_hci_conn_lookup_handle(std::uint16_t handle)
{
    if (handle == 0U || handle > 2U)
    {
        return nullptr;
    }
    return bt_conn_ref(&mock_connections[handle - 1U]);
}

inline int bt_hci_get_adv_handle(const bt_le_ext_adv *advertiser, std::uint8_t *handle)
{
    if (advertiser == nullptr || handle == nullptr)
    {
        return -EINVAL;
    }
    *handle = static_cast<std::uint8_t>(advertiser->index);
    return 0;
}

inline int bt_hci_register_vnd_evt_cb(bt_hci_vnd_evt_cb_t callback)
{
    mock_hci_vendor_event_callback = callback;
    return 0;
}

inline net_buf *bt_hci_cmd_alloc(int timeout)
{
    return net_buf_alloc(&mock_hci_command_pool, timeout);
}

inline int bt_hci_cmd_send_sync(std::uint16_t opcode, net_buf *command,
                                net_buf **response)
{
    assert(opcode == BT_HCI_OP_READ_RSSI);
    assert(command != nullptr && command->len == sizeof(bt_hci_cp_read_rssi));
    const auto *parameters =
        reinterpret_cast<const bt_hci_cp_read_rssi *>(command->data);
    const std::uint16_t handle = parameters->handle;
    net_buf_unref(command);
    if (mock_hci_command_error != 0)
    {
        *response = nullptr;
        return mock_hci_command_error;
    }
    *response = net_buf_alloc(&mock_hci_response_pool, K_NO_WAIT);
    assert(*response != nullptr);
    const bt_hci_rp_read_rssi report = {
        .status = mock_hci_status,
        .handle = handle,
        .rssi = mock_hci_rssi,
    };
    net_buf_add_mem(*response, &report, sizeof(report));
    return 0;
}
