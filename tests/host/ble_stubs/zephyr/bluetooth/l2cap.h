/** @file @brief LE CoC callback·credit·buffer ownership을 재현하는 Host stub입니다. */
#pragma once

#include <ble_mock.h>
#include <zephyr/net_buf.h>

#include <array>

enum
{
    BT_L2CAP_CONNECTED = 2,
};

#define BT_L2CAP_SDU_CHAN_SEND_RESERVE 4U
#define BT_L2CAP_SDU_BUF_SIZE(payload_size) ((payload_size) + BT_L2CAP_SDU_CHAN_SEND_RESERVE)

struct bt_l2cap_chan;

struct bt_l2cap_le_endpoint
{
    std::uint16_t cid;
    std::uint16_t mtu;
    std::uint16_t mps;
};

struct bt_l2cap_chan_ops
{
    void (*connected)(bt_l2cap_chan *);
    void (*disconnected)(bt_l2cap_chan *);
    void (*encrypt_change)(bt_l2cap_chan *, std::uint8_t);
    net_buf *(*alloc_seg)(bt_l2cap_chan *);
    net_buf *(*alloc_buf)(bt_l2cap_chan *);
    int (*recv)(bt_l2cap_chan *, net_buf *);
    void (*sent)(bt_l2cap_chan *);
    void (*status)(bt_l2cap_chan *, long *);
    void (*released)(bt_l2cap_chan *);
    void (*reconfigured)(bt_l2cap_chan *);
};

struct bt_l2cap_chan
{
    bt_conn *conn;
    const bt_l2cap_chan_ops *ops;
};

struct bt_l2cap_le_chan
{
    bt_l2cap_chan chan;
    bt_l2cap_le_endpoint rx;
    std::uint16_t pending_rx_mtu;
    bt_l2cap_le_endpoint tx;
    std::uint16_t state;
    std::uint16_t psm;
    std::uint8_t ident;
    std::uint8_t pending_req;
    bt_security_t required_sec_level;
};

struct bt_l2cap_server
{
    std::uint16_t psm;
    bt_security_t sec_level;
    int (*accept)(bt_conn *, bt_l2cap_server *, bt_l2cap_chan **);
};

inline bt_l2cap_server *mock_l2cap_server{};
inline int mock_l2cap_register_error = 0;
inline int mock_l2cap_connect_error = 0;
inline int mock_l2cap_send_error = 0;
inline int mock_l2cap_disconnect_error = 0;
inline std::uint16_t mock_l2cap_remote_mtu = 512U;
inline std::array<bt_l2cap_chan *, 8> mock_l2cap_channels{};
inline std::size_t mock_l2cap_channel_count = 0U;

struct MockL2capTransmit
{
    bt_l2cap_chan *channel{};
    net_buf *buffer{};
};

inline std::array<MockL2capTransmit, 8> mock_l2cap_transmits{};

inline int bt_l2cap_server_register(bt_l2cap_server *server)
{
    if (mock_l2cap_register_error != 0)
    {
        return mock_l2cap_register_error;
    }
    if (server->psm == 0U)
    {
        server->psm = 0x0080U;
    }
    mock_l2cap_server = server;
    return 0;
}

inline int bt_l2cap_chan_connect(bt_conn *connection, bt_l2cap_chan *channel,
                                 std::uint16_t psm)
{
    if (mock_l2cap_connect_error != 0)
    {
        return mock_l2cap_connect_error;
    }
    auto *le = reinterpret_cast<bt_l2cap_le_chan *>(channel);
    channel->conn = connection;
    le->psm = psm;
    le->tx.mtu = mock_l2cap_remote_mtu;
    le->state = BT_L2CAP_CONNECTED;
    mock_l2cap_channels[mock_l2cap_channel_count++] = channel;
    return 0;
}

inline void mock_l2cap_connected(bt_l2cap_chan *channel)
{
    assert(channel != nullptr && channel->ops != nullptr);
    channel->ops->connected(channel);
}

inline int bt_l2cap_chan_send(bt_l2cap_chan *channel, net_buf *buffer)
{
    if (mock_l2cap_send_error != 0)
    {
        return mock_l2cap_send_error;
    }
    for (MockL2capTransmit &transmit : mock_l2cap_transmits)
    {
        if (transmit.buffer == nullptr)
        {
            transmit = {channel, buffer};
            return 0;
        }
    }
    return -ENOMEM;
}

inline bool mock_l2cap_complete_send(bt_l2cap_chan *channel)
{
    for (MockL2capTransmit &transmit : mock_l2cap_transmits)
    {
        if (transmit.channel == channel && transmit.buffer != nullptr)
        {
            net_buf *buffer = transmit.buffer;
            transmit = {};
            channel->ops->sent(channel);
            net_buf_unref(buffer);
            return true;
        }
    }
    return false;
}

inline int mock_l2cap_receive(bt_l2cap_chan *channel, const void *data, std::size_t length)
{
    assert(channel != nullptr && channel->ops != nullptr && channel->ops->alloc_buf != nullptr);
    net_buf *buffer = channel->ops->alloc_buf(channel);
    if (buffer == nullptr)
    {
        return -ENOMEM;
    }
    static_cast<void>(net_buf_add_mem(buffer, data, length));
    const int result = channel->ops->recv(channel, buffer);
    if (result != -EINPROGRESS)
    {
        net_buf_unref(buffer);
    }
    return result;
}

inline int mock_l2cap_accept(bt_conn *connection, bt_l2cap_chan **channel)
{
    if (mock_l2cap_server == nullptr)
    {
        return -ENOENT;
    }
    const int result = mock_l2cap_server->accept(connection, mock_l2cap_server, channel);
    if (result == 0)
    {
        (*channel)->conn = connection;
        auto *le = reinterpret_cast<bt_l2cap_le_chan *>(*channel);
        le->tx.mtu = mock_l2cap_remote_mtu;
        le->state = BT_L2CAP_CONNECTED;
        mock_l2cap_channels[mock_l2cap_channel_count++] = *channel;
        (*channel)->ops->connected(*channel);
    }
    return result;
}

inline int bt_l2cap_chan_disconnect(bt_l2cap_chan *channel)
{
    if (mock_l2cap_disconnect_error != 0)
    {
        return mock_l2cap_disconnect_error;
    }
    channel->ops->disconnected(channel);
    channel->ops->released(channel);
    channel->conn = nullptr;
    return 0;
}
