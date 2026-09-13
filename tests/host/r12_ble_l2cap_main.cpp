/** @file @brief 실제 GAP/LE CoC의 generation·credit·buffer 수명을 검증합니다. */

#include <NUCODE_BLE_L2CAP.h>
#include <internal/NUCODE_BLE_Internal.h>

#include <ble_mock.h>
#include <zephyr/bluetooth/l2cap.h>

#include <array>
#include <cassert>
#include <cstring>

using namespace nucode::ble;

namespace nucode::ble::internal
{

    /** @brief LE CoC 단독 시험에는 등록할 GATT database가 없습니다. */
    int prepareGattDatabase() noexcept
    {
        return 0;
    }

    /** @brief LE CoC 단독 시험에는 기록할 GATT database identity가 없습니다. */
    int recordGattDatabaseIdentity() noexcept
    {
        return 0;
    }

    /** @brief LE CoC 단독 시험에는 사용자 GATT schema가 없습니다. */
    bool hasGattSchema() noexcept
    {
        return false;
    }

    /** @brief LE CoC 단독 시험에는 GATT main-thread 작업이 없습니다. */
    void pollGatt() noexcept
    {
    }

    /** @brief LE CoC 단독 시험에는 GATT 연결 관찰이 없습니다. */
    void gattConnected(struct bt_conn *, BLEConnectionHandle) noexcept
    {
    }

    /** @brief LE CoC 단독 시험에는 GATT 해제 관찰이 없습니다. */
    void gattDisconnected(struct bt_conn *, BLEConnectionHandle) noexcept
    {
    }

    /** @brief LE CoC 단독 시험에는 GATT 종료 작업이 없습니다. */
    void gattEnded() noexcept
    {
    }

    /** @brief LE CoC 단독 시험에서는 GATT service 등록을 거부합니다. */
    bool addGattService(BLEService &) noexcept
    {
        return false;
    }

    /** @brief LE CoC 단독 시험에서 Security 연결 통지를 소비합니다. */
    void securityConnected(struct bt_conn *) noexcept
    {
    }

    /** @brief LE CoC 단독 시험에서 Security 해제 통지를 소비합니다. */
    void securityDisconnected(struct bt_conn *) noexcept
    {
    }

    /** @brief LE CoC 단독 시험에서 Security 변경 통지를 소비합니다. */
    void securityChanged(struct bt_conn *, bt_security_t, enum bt_security_err) noexcept
    {
    }

} // namespace nucode::ble::internal

namespace
{

    std::array<unsigned, 5> event_counts{};
    std::array<std::uint8_t, L2capCoc::maximum_sdu_length> received_data{};
    std::size_t received_length = 0U;
    BLEL2capChannelHandle last_channel;
    BLEConnectionHandle last_connection;

    /** @brief main-thread event와 RX payload를 callback 밖 검사용 storage에 복사합니다. */
    void eventObserved(const BLEL2capEventInfo &information, void *)
    {
        ++event_counts[static_cast<std::size_t>(information.event)];
        last_channel = information.channel;
        last_connection = information.connection;
        if (information.data != nullptr)
        {
            received_length = information.length;
            std::memcpy(received_data.data(), information.data, information.length);
        }
    }

    /** @brief generic central link를 만들고 generation handle을 반환합니다. */
    BLEConnectionHandle connectGap(unsigned index = 0U)
    {
        mock_next_connection = &mock_connections[index];
        assert(BLEConnection.connect(
            BLEAddress("01:02:03:04:05:06", BLEAddress::Type::public_address)));
        mock_conn_callbacks->connected(mock_next_connection, 0U);
        BLEDevice.poll();
        const BLEConnectionHandle handle = BLEConnection.handle(BLELinkRole::central);
        assert(handle.valid());
        return handle;
    }

    /** @brief Device와 callback, 한 central link를 공통 초기화합니다. */
    BLEConnectionHandle initialize()
    {
        assert(BLEDevice.begin("m29-coc-host"));
        BLEL2cap.onEvent(eventObserved);
        return connectGap();
    }

    /** @brief outgoing channel을 연결 완료 상태까지 진행합니다. */
    BLEL2capChannelHandle connectChannel(BLEConnectionHandle connection)
    {
        BLEL2capChannelHandle channel;
        assert(BLEL2cap.connect(connection, 0x0080U, channel));
        assert(channel.valid() && !BLEL2cap.connected(channel));
        mock_l2cap_connected(mock_l2cap_channels[mock_l2cap_channel_count - 1U]);
        assert(BLEL2cap.connected(channel));
        return channel;
    }

} // namespace

int main(int argc, char **argv)
{
    assert(argc == 2);
    const char *scenario = argv[1];

    if (std::strcmp(scenario, "lifecycle") == 0)
    {
        const BLEConnectionHandle connection = initialize();
        assert(!BLEL2cap.startServer(0x007fU));
        assert(BLEDevice.lastError() == BLEError::invalid_argument);
        assert(BLEL2cap.startServer());
        assert(BLEL2cap.serverPsm() == 0x0080U);
        assert(BLEL2cap.startServer(0x0080U));
        assert(!BLEL2cap.startServer(0x0081U));

        const BLEL2capChannelHandle first = connectChannel(connection);
        const BLEL2capChannelHandle second = connectChannel(connection);
        BLEL2capChannelHandle third;
        assert(!BLEL2cap.connect(connection, 0x0080U, third));
        assert(!third.valid() && BLEDevice.lastError() == BLEError::busy);
        assert(event_counts[static_cast<std::size_t>(BLEL2capEvent::connected)] == 0U);
        BLEDevice.poll();
        assert(event_counts[static_cast<std::size_t>(BLEL2capEvent::connected)] == 2U);
        assert(first != second && BLEL2cap.connected(first) && BLEL2cap.connected(second));
        assert(BLEL2cap.statistics().connected == 2U);
    }
    else if (std::strcmp(scenario, "backpressure") == 0)
    {
        const BLEConnectionHandle connection = initialize();
        const BLEL2capChannelHandle channel = connectChannel(connection);
        BLEDevice.poll();
        std::array<std::uint8_t, 512> payload{};
        for (std::size_t index = 0U; index < payload.size(); ++index)
        {
            payload[index] = static_cast<std::uint8_t>(index & 0xffU);
        }
        for (std::size_t index = 0U; index < L2capCoc::transmit_buffers; ++index)
        {
            assert(BLEL2cap.send(channel, payload.data(), payload.size()));
        }
        assert(BLEL2cap.availableForWrite() == 0U);
        assert(!BLEL2cap.send(channel, payload.data(), payload.size()));
        assert(BLEDevice.lastError() == BLEError::busy);
        assert(BLEL2cap.statistics().backpressure == 1U);
        for (std::size_t index = 0U; index < L2capCoc::transmit_buffers; ++index)
        {
            assert(mock_l2cap_complete_send(mock_l2cap_channels[0]));
        }
        assert(BLEL2cap.availableForWrite() == L2capCoc::transmit_buffers);
        BLEDevice.poll();
        assert(event_counts[static_cast<std::size_t>(BLEL2capEvent::sent)] == 4U);
        assert(BLEL2cap.statistics().sent == 4U);
    }
    else if (std::strcmp(scenario, "receive_bounds") == 0)
    {
        const BLEConnectionHandle connection = initialize();
        const BLEL2capChannelHandle channel = connectChannel(connection);
        BLEDevice.poll();
        std::array<std::uint8_t, 512> payload{};
        for (std::size_t index = 0U; index < payload.size(); ++index)
        {
            payload[index] = static_cast<std::uint8_t>((index * 7U) & 0xffU);
        }
        for (std::size_t index = 0U; index < L2capCoc::receive_records_per_channel; ++index)
        {
            assert(mock_l2cap_receive(mock_l2cap_channels[0], payload.data(), payload.size()) ==
                   0);
        }
        assert(event_counts[static_cast<std::size_t>(BLEL2capEvent::received)] == 0U);
        assert(mock_l2cap_receive(mock_l2cap_channels[0], payload.data(), payload.size()) == 0);
        assert(BLEDevice.lastError() == BLEError::event_overflow);
        BLEDevice.poll();
        assert(event_counts[static_cast<std::size_t>(BLEL2capEvent::received)] == 4U);
        assert(received_length == payload.size());
        assert(received_data == payload);
        assert(last_channel == channel && last_connection == connection);
        assert(BLEL2cap.statistics().received == 4U);
        assert(BLEL2cap.statistics().dropped_events == 1U);
    }
    else if (std::strcmp(scenario, "stale_reuse") == 0)
    {
        const BLEConnectionHandle connection = initialize();
        const BLEL2capChannelHandle stale = connectChannel(connection);
        BLEDevice.poll();
        assert(BLEL2cap.disconnect(stale));
        BLEDevice.poll();
        assert(!BLEL2cap.connected(stale));
        const BLEL2capChannelHandle current = connectChannel(connection);
        BLEDevice.poll();
        assert(current.valid() && current != stale);
        const std::uint8_t payload = 0x5aU;
        assert(!BLEL2cap.send(stale, &payload, sizeof(payload)));
        assert(BLEDevice.lastError() == BLEError::not_connected);
        assert(BLEL2cap.send(current, &payload, sizeof(payload)));
    }
    else if (std::strcmp(scenario, "server_accept") == 0)
    {
        static_cast<void>(initialize());
        assert(BLEL2cap.startServer());
        assert(BLEAdvertising.clear() && BLEAdvertising.start());
        mock_connections[1].role = BT_CONN_ROLE_PERIPHERAL;
        mock_conn_callbacks->connected(&mock_connections[1], 0U);
        BLEDevice.poll();
        const BLEConnectionHandle peripheral = BLEConnection.handle(BLELinkRole::peripheral);
        assert(peripheral.valid());
        bt_l2cap_chan *incoming = nullptr;
        assert(mock_l2cap_accept(&mock_connections[1], &incoming) == 0);
        BLEDevice.poll();
        assert(last_connection == peripheral && last_channel.valid());
        assert(BLEL2cap.statistics().accepted == 1U);
    }
    else if (std::strcmp(scenario, "driver_failures") == 0)
    {
        const BLEConnectionHandle connection = initialize();
        mock_l2cap_register_error = -EIO;
        assert(!BLEL2cap.startServer());
        assert(BLEDevice.lastError() == BLEError::driver_error);
        mock_l2cap_connect_error = -ECONNREFUSED;
        BLEL2capChannelHandle channel;
        assert(!BLEL2cap.connect(connection, 0x0080U, channel));
        assert(!channel.valid());
        mock_l2cap_connect_error = 0;
        channel = connectChannel(connection);
        BLEDevice.poll();
        std::array<std::uint8_t, 513> too_large{};
        assert(!BLEL2cap.send(channel, nullptr, 1U));
        assert(BLEDevice.lastError() == BLEError::invalid_argument);
        assert(!BLEL2cap.send(channel, too_large.data(), too_large.size()));
        assert(BLEDevice.lastError() == BLEError::value_overflow);
        mock_l2cap_send_error = -EIO;
        assert(!BLEL2cap.send(channel, too_large.data(), 1U));
        assert(BLEDevice.lastError() == BLEError::driver_error);
        assert(BLEL2cap.availableForWrite() == L2capCoc::transmit_buffers);
    }
    else if (std::strcmp(scenario, "end") == 0)
    {
        const BLEConnectionHandle connection = initialize();
        const BLEL2capChannelHandle channel = connectChannel(connection);
        BLEDevice.end();
        assert(!BLEL2cap.connected(channel));
        assert(BLEL2cap.availableForWrite() == L2capCoc::transmit_buffers);
        assert(BLEDevice.begin("m29-coc-new-session"));
        BLEDevice.poll();
        assert(event_counts[static_cast<std::size_t>(BLEL2capEvent::connected)] == 0U);
        assert(event_counts[static_cast<std::size_t>(BLEL2capEvent::disconnected)] == 0U);
        BLEDevice.end();
        assert(!BLEL2cap.startServer());
        assert(BLEDevice.lastError() == BLEError::not_initialized);
    }
    else
    {
        assert(false);
    }
    return 0;
}
