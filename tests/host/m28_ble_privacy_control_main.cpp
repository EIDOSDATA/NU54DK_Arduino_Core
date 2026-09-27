/** @file @brief W06 privacy·RPA와 link별 제어 lifecycle을 검증합니다. */
#include <NUCODE_BLE_GAP.h>
#include <ble_mock.h>
#include <array>
#include <cstring>

using namespace nucode::ble;

std::array<BLEEventInfo, 64> observed_events{};
std::size_t observed_event_count = 0U;

/** @brief main-thread에서 전달된 exact handle event를 순서대로 보존합니다. */
void observeEvent(const BLEEventInfo &information, void *)
{
    assert(observed_event_count < observed_events.size());
    observed_events[observed_event_count++] = information;
}

/** @brief 지정 mock connection으로 central link를 연결합니다. */
BLEConnectionHandle connectCentral(unsigned index, const BLEAddress &address)
{
    mock_next_connection = &mock_connections[index];
    BLEConnectionHandle handle;
    assert(BLEConnection.connect(address, handle));
    mock_conn_callbacks->connected(&mock_connections[index], 0U);
    assert(BLEConnection.connected(handle));
    return handle;
}

/** @brief legacy 광고를 통해 두 번째 peripheral link를 수락합니다. */
BLEConnectionHandle connectPeripheral(unsigned index)
{
    assert(BLEAdvertising.clear());
    assert(BLEAdvertising.start());
    mock_connections[index].peer =
        bt_addr_le_t{BT_ADDR_LE_PUBLIC, {{6U, 5U, 4U, 3U, 2U, 1U}}};
    mock_conn_callbacks->connected(&mock_connections[index], 0U);
    BLEConnectionHandle handle = BLEConnection.handle(BLELinkRole::peripheral);
    assert(BLEConnection.connected(handle));
    return handle;
}

/** @brief remote-info mock을 각 link별 값과 feature storage에 결합합니다. */
void prepareRemoteInformation(unsigned index, std::uint8_t feature)
{
    mock_remote_features[index][0] = feature;
    mock_remote_information[index] = {
        BT_CONN_TYPE_LE,
        static_cast<std::uint8_t>(0x0dU + index),
        static_cast<std::uint16_t>(0x0059U + index),
        static_cast<std::uint16_t>(0x1200U + index),
        {mock_remote_features[index]},
    };
}

int main(int argc, char **argv)
{
    assert(argc == 2);
    const char *const scenario = argv[1];
    BLEDevice.onEventInfo(observeEvent);
    assert(BLEDevice.begin("m28-w06"));
    BLEDevice.poll();
    observed_event_count = 0U;

    const BLEAddress public_peer("01:02:03:04:05:06",
                                 BLEAddress::Type::public_address);
    if (std::strcmp(scenario, "per_link_control") == 0)
    {
        const BLEConnectionHandle central = connectCentral(0U, public_peer);
        const BLEConnectionHandle peripheral = connectPeripheral(1U);
        BLEDevice.poll();
        observed_event_count = 0U;
        prepareRemoteInformation(0U, 0xa1U);
        prepareRemoteInformation(1U, 0xb2U);

        assert(BLEConnection.requestDataLength(central, 100U, 1000U));
        assert(BLEConnection.requestDataLength(peripheral, 200U, 2000U));
        assert(mock_connections[0].data_length_updates == 1U);
        assert(mock_connections[1].data_length_updates == 1U);
        mock_data_lengths[0].rx_max_len = 101U;
        mock_data_lengths[1].rx_max_len = 201U;

        BLEDataLengthInfo central_length{};
        BLEDataLengthInfo peripheral_length{};
        assert(BLEConnection.dataLength(central, central_length));
        assert(BLEConnection.dataLength(peripheral, peripheral_length));
        assert(central_length.transmit_octets == 100U &&
               central_length.receive_octets == 101U);
        assert(peripheral_length.transmit_octets == 200U &&
               peripheral_length.receive_octets == 201U);

        BLERemoteInformation central_remote{};
        BLERemoteInformation peripheral_remote{};
        assert(BLEConnection.remoteInformation(central, central_remote));
        assert(BLEConnection.remoteInformation(peripheral, peripheral_remote));
        assert(central_remote.features[0] == 0xa1U &&
               peripheral_remote.features[0] == 0xb2U);

        mock_conn_callbacks->le_data_len_updated(&mock_connections[0], &mock_data_lengths[0]);
        mock_conn_callbacks->le_data_len_updated(&mock_connections[1], &mock_data_lengths[1]);
        mock_conn_callbacks->remote_info_available(&mock_connections[0],
                                                   &mock_remote_information[0]);
        mock_conn_callbacks->remote_info_available(&mock_connections[1],
                                                   &mock_remote_information[1]);
        BLEDevice.poll();
        assert(observed_event_count == 4U);
        assert(observed_events[0].event == BLEEvent::data_length_changed &&
               observed_events[0].connection == central);
        assert(observed_events[1].event == BLEEvent::data_length_changed &&
               observed_events[1].connection == peripheral);
        assert(observed_events[2].event == BLEEvent::remote_information_available &&
               observed_events[2].connection == central);
        assert(observed_events[3].event == BLEEvent::remote_information_available &&
               observed_events[3].connection == peripheral);
    }
    else if (std::strcmp(scenario, "identity_resolution") == 0)
    {
        const BLEAddress rpa("41:22:33:44:55:66", BLEAddress::Type::random_address);
        const BLEConnectionHandle central = connectCentral(0U, rpa);
        BLEDevice.poll();
        observed_event_count = 0U;
        assert(!BLEConnection.identityResolved(central));
        assert(BLEConnection.connectionAddress(central) == rpa);

        const bt_addr_le_t native_rpa{BT_ADDR_LE_RANDOM,
                                      {{0x66U, 0x55U, 0x44U, 0x33U, 0x22U, 0x41U}}};
        const bt_addr_le_t identity{BT_ADDR_LE_PUBLIC,
                                    {{0x06U, 0x05U, 0x04U, 0x03U, 0x02U, 0x01U}}};
        mock_conn_callbacks->identity_resolved(&mock_connections[0], &native_rpa, &identity);
        BLEDevice.poll();
        assert(BLEConnection.identityResolved(central));
        assert(BLEConnection.connectionAddress(central) == rpa);
        assert(BLEConnection.peerAddress(central) == public_peer);
        assert(observed_event_count == 1U &&
               observed_events[0].event == BLEEvent::identity_resolved &&
               observed_events[0].connection == central);
    }
    else if (std::strcmp(scenario, "stale_callback") == 0)
    {
        const BLEConnectionHandle old_handle = connectCentral(0U, public_peer);
        mock_conn_callbacks->disconnected(&mock_connections[0], 0x13U);
        const BLEConnectionHandle current = connectCentral(2U, public_peer);
        BLEDevice.poll();
        observed_event_count = 0U;

        const bt_addr_le_t old_identity{BT_ADDR_LE_PUBLIC,
                                        {{9U, 9U, 9U, 9U, 9U, 9U}}};
        mock_conn_callbacks->identity_resolved(&mock_connections[0],
                                               &mock_connections[0].peer, &old_identity);
        mock_conn_callbacks->le_data_len_updated(&mock_connections[0], &mock_data_lengths[0]);
        mock_conn_callbacks->remote_info_available(&mock_connections[0],
                                                   &mock_remote_information[0]);
        BLEDevice.poll();
        assert(observed_event_count == 0U);
        assert(!BLEConnection.connected(old_handle) && BLEConnection.connected(current));
        assert(BLEConnection.peerAddress(current) == public_peer);
    }
    else if (std::strcmp(scenario, "privacy_rotation") == 0)
    {
        assert(BLEPrivacy.supported());
        assert(!BLEPrivacy.setRotationTimeout(0U));
        assert(BLEDevice.lastError() == BLEError::invalid_argument);
        assert(BLEPrivacy.setRotationTimeout(1U));
        assert(BLEPrivacy.rotationTimeout() == 1U && mock_rpa_timeout == 1U);
        BLEDevice.poll();
        observed_event_count = 0U;

        BLEExtendedAdvertisingParameters parameters{};
        BLEAdvertisingSetHandle advertising_set;
        assert(BLEExtendedAdvertising.create(parameters, advertising_set));
        assert(mock_ext_advertising_callbacks->rpa_expired(&mock_ext_advertisers[0]));
        BLEDevice.poll();
        assert(BLEPrivacy.expirationCount() == 1U);
        assert(observed_events[1].event == BLEEvent::rpa_expired &&
               observed_events[1].advertising_set == advertising_set);

        BLEDevice.end();
        assert(mock_ext_advertising_callbacks->rpa_expired(&mock_ext_advertisers[0]));
        assert(BLEPrivacy.expirationCount() == 0U);
    }
    else if (std::strcmp(scenario, "extended_incoming") == 0)
    {
        BLEExtendedAdvertisingParameters parameters{};
        parameters.connectable = true;
        BLEAdvertisingSetHandle advertising_set;
        assert(BLEExtendedAdvertising.create(parameters, advertising_set));
        assert(BLEExtendedAdvertising.start(advertising_set));

        mock_connections[1].peer =
            bt_addr_le_t{BT_ADDR_LE_PUBLIC, {{6U, 5U, 4U, 3U, 2U, 1U}}};
        mock_conn_callbacks->connected(&mock_connections[1], 0U);
        const BLEConnectionHandle peripheral =
            BLEConnection.handle(BLELinkRole::peripheral);
        assert(peripheral.valid() && BLEConnection.connected(peripheral));

        bt_le_ext_adv_connected_info information{&mock_connections[1]};
        mock_ext_advertising_callbacks->connected(&mock_ext_advertisers[0], &information);
        assert(!BLEExtendedAdvertising.running(advertising_set));
    }
    else
    {
        return 2;
    }
    return 0;
}
