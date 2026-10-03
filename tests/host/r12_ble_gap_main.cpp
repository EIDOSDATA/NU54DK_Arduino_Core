/** @file @brief 실제 GAP public API의 callback/reference/session 경계를 검증합니다. */
#include <NUCODE_BLE_GAP.h>
#include <internal/NUCODE_BLE_Internal.h>
#include <ble_mock.h>
#include <array>
#include <cstring>
#include <iostream>
using namespace nucode::ble;
extern "C" void nucode_ble_note_settings_loaded(int result) noexcept;
std::array<unsigned, 64> events{};
std::array<BLEEventInfo, 64> event_information{};
std::size_t event_information_count = 0U;
bool reenter = false;
unsigned scan_results = 0;
void observed(BLEEvent event, void *)
{
    ++events[static_cast<unsigned>(event)];
    if (reenter && event == BLEEvent::connected)
    {
        reenter = false;
        BLEDevice.end();
        assert(BLEDevice.begin("reentered"));
    }
}
void observedInformation(const BLEEventInfo &information, void *)
{
    assert(event_information_count < event_information.size());
    event_information[event_information_count++] = information;
}
void scanned(const BLEScanResult &result, void *)
{
    ++scan_results;
    assert(std::strcmp(result.name, "abc") == 0);
    BLEDevice.end();
}
BLEConnectionHandle connect(unsigned index = 0)
{
    mock_next_connection = &mock_connections[index];
    BLEConnectionHandle handle;
    assert(BLEConnection.connect(
        BLEAddress("01:02:03:04:05:06", BLEAddress::Type::public_address), handle));
    assert(handle.valid() && BLEConnection.connecting(handle));
    assert(mock_connections[index].refs == 1);
    mock_conn_callbacks->connected(&mock_connections[index], 0);
    assert(BLEConnection.connected() && BLEConnection.connected(handle));
    return handle;
}
int main(int argc, char **argv)
{
    assert(argc == 2);
    const char *const scenario = argv[1];
    if (std::strcmp(scenario, "settings_failure") == 0)
    {
        mock_settings_error = -EIO;
        assert(!BLEDevice.begin("failed"));
        assert(BLEDevice.lastDriverError() == -EIO);
        assert(!internal::settingsReady() && internal::settingsResult() == -EIO);
        assert(!BLEDevice.begin("retry"));
        assert(mock_enable_calls == 1 && mock_settings_calls == 1);
        return 0;
    }
    if (std::strcmp(scenario, "settings_preloaded") == 0)
    {
        nucode_ble_note_settings_loaded(0);
        assert(BLEDevice.begin("preloaded"));
        assert(mock_enable_calls == 1 && mock_settings_calls == 0);
        assert(internal::settingsReady() && internal::settingsResult() == 0);
        return 0;
    }
    BLEDevice.onEvent(observed, nullptr);
    BLEDevice.onEventInfo(observedInformation, nullptr);
    assert(BLEDevice.begin("host"));
    BLEDevice.poll();
    assert(events[static_cast<unsigned>(BLEEvent::initialized)] == 1);
    if (std::strcmp(scenario, "lifecycle") == 0)
    {
        connect();
        assert(mock_connections[0].refs == 1);
        assert(BLEConnection.mtu() == 247 && mock_connections[0].refs == 1);
        std::int8_t power = 0;
        assert(BLEConnection.txPower(power) && power == -4 && mock_connections[0].refs == 1);
        assert(BLEConnection.requestParameters(24, 40, 0, 400));
        BLEDevice.poll();
        assert(events[static_cast<unsigned>(BLEEvent::connected)] == 1);
        assert(BLEConnection.disconnect());
        mock_conn_callbacks->disconnected(&mock_connections[0], 0x13);
        assert(!BLEConnection.connected() && mock_connections[0].refs == 0);
    }
    else if (std::strcmp(scenario, "power_control") == 0)
    {
        const BLEConnectionHandle connection = connect();
        BLETransmitPowerLevel level;
        assert(BLEConnection.localTransmitPower(connection, BLETransmitPowerPhy::le_1m,
                                                level));
        assert(level.phy == BLETransmitPowerPhy::le_1m && level.current_dbm == -4 &&
               level.maximum_dbm == 8);
        assert(!BLEConnection.localTransmitPower(connection,
                                                 BLETransmitPowerPhy::unknown, level));
        assert(BLEDevice.lastError() == BLEError::invalid_argument);

        assert(BLEConnection.requestRemoteTransmitPower(connection,
                                                        BLETransmitPowerPhy::le_1m));
        assert(mock_remote_tx_power_calls == 1U &&
               mock_remote_tx_power_phy == BT_CONN_LE_TX_POWER_PHY_1M);
        assert(!BLEConnection.requestRemoteTransmitPower(connection,
                                                         BLETransmitPowerPhy::none));
        assert(mock_remote_tx_power_calls == 1U);
        assert(!BLEConnection.requestRemoteTransmitPowerChange(
            connection, BLETransmitPowerPhy::le_1m, -21));
        assert(BLEConnection.requestRemoteTransmitPowerChange(
            connection, BLETransmitPowerPhy::le_1m, 3));
        assert(mock_remote_tx_power_change_calls == 1U &&
               mock_remote_tx_power_delta == 3);

        assert(BLEConnection.setTransmitPowerReporting(connection, true, true));
        assert(BLEConnection.setTransmitPowerReporting(connection, true, true));
        assert(BLEConnection.setTransmitPowerReporting(connection, false, false));
        assert(BLEConnection.setTransmitPowerReporting(connection, false, false));
        assert(mock_tx_power_reporting_calls == 4U && !mock_local_power_reporting &&
               !mock_remote_power_reporting);

        std::int8_t rssi = 0;
        assert(BLEConnection.readRssi(connection, rssi) && rssi == -55);

        BLEPathLossParameters path_parameters;
        path_parameters.high_threshold_db = 40U;
        path_parameters.low_threshold_db = 40U;
        assert(!BLEConnection.configurePathLossMonitoring(connection,
                                                          path_parameters));
        assert(mock_path_loss_parameter_calls == 0U);
        path_parameters = {};
        path_parameters.high_threshold_db = 250U;
        path_parameters.high_hysteresis_db = 6U;
        assert(!BLEConnection.configurePathLossMonitoring(connection,
                                                          path_parameters));
        path_parameters = {};
        path_parameters.low_threshold_db = 4U;
        path_parameters.low_hysteresis_db = 5U;
        assert(!BLEConnection.configurePathLossMonitoring(connection,
                                                          path_parameters));
        path_parameters = {};
        path_parameters.high_threshold_db = 44U;
        assert(!BLEConnection.configurePathLossMonitoring(connection,
                                                          path_parameters));
        assert(mock_path_loss_parameter_calls == 0U);
        path_parameters = {};
        assert(BLEConnection.configurePathLossMonitoring(connection,
                                                         path_parameters));
        assert(mock_path_loss_parameter_calls == 1U &&
               mock_path_loss_parameters.high_threshold == 60U &&
               mock_path_loss_parameters.low_threshold == 40U &&
               mock_path_loss_parameters.min_time_spent == 5U);
        assert(BLEConnection.setPathLossMonitoring(connection, true));
        assert(BLEConnection.setPathLossMonitoring(connection, true));
        assert(BLEConnection.setPathLossMonitoring(connection, false));
        assert(BLEConnection.setPathLossMonitoring(connection, false));
        assert(mock_path_loss_enable_calls == 4U && !mock_path_loss_enabled);

        bt_conn_le_tx_power_report power_report = {
            .reason = BT_HCI_LE_TX_POWER_REPORT_REASON_READ_REMOTE_COMPLETED,
            .phy = BT_CONN_LE_TX_POWER_PHY_1M,
            .tx_power_level = -7,
            .tx_power_level_flag = 0x01U,
            .delta = -3,
        };
        bt_conn_le_path_loss_threshold_report path_report = {
            .zone = BT_CONN_LE_PATH_LOSS_ZONE_ENTERED_HIGH,
            .path_loss = 72U,
        };
        mock_conn_callbacks->tx_power_report(&mock_connections[0], &power_report);
        mock_conn_callbacks->path_loss_threshold_report(&mock_connections[0], &path_report);
        power_report.tx_power_level = 20;
        path_report.path_loss = 1U;
        BLEDevice.poll();
        assert(event_information_count >= 4U);
        const BLEEventInfo &power_event =
            event_information[event_information_count - 2U];
        const BLEEventInfo &path_event =
            event_information[event_information_count - 1U];
        assert(power_event.event == BLEEvent::transmit_power_report &&
               power_event.connection == connection &&
               power_event.transmit_power.level_dbm == -7 &&
               power_event.transmit_power.at_minimum);
        assert(path_event.event == BLEEvent::path_loss_changed &&
               path_event.connection == connection &&
               path_event.path_loss.zone == BLEPathLossZone::high &&
               path_event.path_loss.path_loss_db == 72U);

        mock_conn_callbacks->disconnected(&mock_connections[0], 0x13);
        BLEDevice.poll();
        const std::size_t count_after_disconnect = event_information_count;
        mock_conn_callbacks->tx_power_report(&mock_connections[0], &power_report);
        mock_conn_callbacks->path_loss_threshold_report(&mock_connections[0], &path_report);
        BLEDevice.poll();
        assert(event_information_count == count_after_disconnect);
        const unsigned request_count = mock_remote_tx_power_calls;
        assert(!BLEConnection.requestRemoteTransmitPower(connection,
                                                         BLETransmitPowerPhy::le_1m));
        assert(mock_remote_tx_power_calls == request_count &&
               BLEDevice.lastError() == BLEError::not_connected);
    }
    else if (std::strcmp(scenario, "timing_features") == 0)
    {
        const BLEConnectionHandle connection = connect();

        BLESubrateParameters subrate;
        subrate.minimum_factor = 0U;
        assert(!BLEConnection.setDefaultSubrate(subrate));
        assert(mock_subrate_default_calls == 0U);
        subrate = {};
        subrate.minimum_factor = 2U;
        subrate.maximum_factor = 5U;
        subrate.maximum_peripheral_latency = 2U;
        subrate.continuation_number = 1U;
        subrate.supervision_timeout_10ms = 500U;
        assert(BLEConnection.setDefaultSubrate(subrate));
        assert(BLEConnection.requestSubrate(connection, subrate));
        assert(mock_subrate_default_calls == 1U &&
               mock_subrate_request_calls == 1U &&
               mock_subrate_parameters.subrate_min == 2U &&
               mock_subrate_parameters.subrate_max == 5U);
        bt_conn_le_subrate_changed subrate_changed = {
            .status = 0U,
            .factor = 4U,
            .continuation_number = 1U,
            .peripheral_latency = 2U,
            .supervision_timeout = 500U,
        };
        mock_conn_callbacks->subrate_changed(&mock_connections[0], &subrate_changed);
        BLESubrateInfo subrate_information;
        assert(BLEConnection.subrate(connection, subrate_information));
        assert(subrate_information.status == 0U &&
               subrate_information.factor == 4U &&
               subrate_information.peripheral_latency == 2U);

        BLEConnectionRateParameters connection_rate;
        connection_rate.interval_minimum_125us = 2U;
        assert(!BLEConnection.setDefaultConnectionRate(connection_rate));
        assert(mock_connection_rate_default_calls == 0U);
        connection_rate = {};
        connection_rate.interval_minimum_125us = 6U;
        connection_rate.interval_maximum_125us = 12U;
        connection_rate.subrate_minimum = 1U;
        connection_rate.subrate_maximum = 2U;
        connection_rate.continuation_number = 0U;
        connection_rate.supervision_timeout_10ms = 300U;
        connection_rate.event_length_minimum_125us = 2U;
        connection_rate.event_length_maximum_125us = 10U;
        assert(BLEConnection.setDefaultConnectionRate(connection_rate));
        assert(BLEConnection.requestConnectionRate(connection, connection_rate));
        assert(mock_connection_rate_default_calls == 1U &&
               mock_connection_rate_request_calls == 1U &&
               mock_connection_rate_parameters.interval_min_125us == 6U);
        bt_conn_le_conn_rate_changed connection_rate_changed = {
            .interval_us = 750U,
            .subrate_factor = 2U,
            .peripheral_latency = 1U,
            .continuation_number = 0U,
            .supervision_timeout_10ms = 300U,
        };
        mock_conn_callbacks->conn_rate_changed(&mock_connections[0], 0U,
                                                &connection_rate_changed);
        BLEConnectionRateInfo connection_rate_information;
        assert(BLEConnection.connectionRate(connection,
                                            connection_rate_information));
        assert(connection_rate_information.interval_us == 750U &&
               connection_rate_information.subrate_factor == 2U);
        std::uint16_t minimum_interval_us = 0U;
        assert(BLEConnection.minimumConnectionInterval(minimum_interval_us));
        assert(minimum_interval_us == 750U);

        BLEFrameSpaceParameters frame_space;
        frame_space.phy_mask = 0U;
        assert(!BLEConnection.requestFrameSpace(connection, frame_space));
        assert(mock_frame_space_calls == 0U);
        frame_space = {};
        frame_space.phy_mask = BLEFrameSpaceParameters::phy_le_2m;
        frame_space.minimum_us = 20U;
        frame_space.maximum_us = 140U;
        assert(BLEConnection.requestFrameSpace(connection, frame_space));
        assert(mock_frame_space_calls == 1U &&
               mock_frame_space_parameters.frame_space_min == 20U);
        bt_conn_le_frame_space_updated frame_space_updated = {
            .status = 0U,
            .initiator = BT_CONN_LE_FRAME_SPACE_UPDATE_INITIATOR_LOCAL_HOST,
            .frame_space = 100U,
            .phys = BLEFrameSpaceParameters::phy_le_2m,
            .spacing_types =
                BLEFrameSpaceParameters::spacing_acl_central_to_peripheral,
        };
        mock_conn_callbacks->frame_space_updated(&mock_connections[0],
                                                  &frame_space_updated);
        BLEFrameSpaceInfo frame_space_information;
        assert(BLEConnection.frameSpace(connection, frame_space_information));
        assert(frame_space_information.status == 0U &&
               frame_space_information.frame_space_us == 100U);

        mock_local_features.features[0] = 0x04U;
        mock_local_features.features[8] = 0x08U;
        BLEExtendedFeatureSet local_features;
        assert(BLEConnection.localExtendedFeatures(local_features));
        assert(local_features.supported(0U, 2U) &&
               local_features.supported(1U, 3U) &&
               !local_features.supported(11U, 0U));
        assert(!BLEConnection.requestRemoteExtendedFeatures(connection, 11U));
        assert(mock_remote_features_calls == 0U);
        assert(BLEConnection.requestRemoteExtendedFeatures(connection, 2U));
        assert(mock_remote_features_calls == 1U && mock_remote_features_page == 2U);
        std::uint8_t remote_bits[BLEExtendedFeatureSet::maximum_size] = {};
        remote_bits[32] = 0x10U;
        bt_conn_le_read_all_remote_feat_complete remote_features = {
            .status = 0U,
            .max_remote_page = 2U,
            .max_valid_page = 2U,
            .features = remote_bits,
        };
        mock_conn_callbacks->read_all_remote_feat_complete(&mock_connections[0],
                                                            &remote_features);
        remote_bits[32] = 0U;
        BLEExtendedFeatureSet copied_features;
        assert(BLEConnection.remoteExtendedFeatures(connection, copied_features));
        assert(copied_features.supported(2U, 4U));

        const BLESleepClockAccuracySupport sca =
            BLEConnection.sleepClockAccuracySupport();
        assert(sca.controller_procedure && !sca.host_request_and_report);
        const std::uint8_t invalid_channel_map[5] = {1U, 0U, 0U, 0U, 0U};
        assert(!BLEConnection.setChannelClassification(invalid_channel_map));
        const std::uint8_t channel_map[5] = {0xffU, 0xffU, 0xffU, 0xffU, 0x1fU};
        assert(BLEConnection.setChannelClassification(channel_map));
        assert(mock_channel_map_calls == 1U && mock_channel_map[4] == 0x1fU);

        BLEDevice.poll();
        assert(events[static_cast<unsigned>(BLEEvent::subrate_changed)] == 1U);
        assert(events[static_cast<unsigned>(BLEEvent::connection_rate_changed)] == 1U);
        assert(events[static_cast<unsigned>(BLEEvent::remote_features_available)] == 1U);
        assert(events[static_cast<unsigned>(BLEEvent::frame_space_changed)] == 1U);

        mock_conn_callbacks->disconnected(&mock_connections[0], 0x13);
        BLEDevice.poll();
        const std::size_t count_after_disconnect = event_information_count;
        mock_conn_callbacks->subrate_changed(&mock_connections[0], &subrate_changed);
        mock_conn_callbacks->conn_rate_changed(&mock_connections[0], 0U,
                                                &connection_rate_changed);
        mock_conn_callbacks->read_all_remote_feat_complete(&mock_connections[0],
                                                            &remote_features);
        mock_conn_callbacks->frame_space_updated(&mock_connections[0],
                                                  &frame_space_updated);
        BLEDevice.poll();
        assert(event_information_count == count_after_disconnect);
        assert(!BLEConnection.subrate(connection, subrate_information));
        assert(!BLEConnection.connectionRate(connection,
                                             connection_rate_information));
        assert(!BLEConnection.remoteExtendedFeatures(connection, copied_features));
        assert(!BLEConnection.frameSpace(connection, frame_space_information));
    }
    else if (std::strcmp(scenario, "late_callback") == 0)
    {
        connect();
        BLEDevice.poll();
        assert(BLEConnection.requestMtu());
        mock_conn_callbacks->disconnected(&mock_connections[0], 0x13);
        BLEDevice.poll();
        mock_mtu_parameters->func(&mock_connections[0], 0, mock_mtu_parameters);
        mock_gatt_callbacks->att_mtu_updated(&mock_connections[0], 247, 247);
        mock_conn_callbacks->le_param_updated(&mock_connections[0], 24, 0, 400);
        BLEDevice.poll();
        assert(events[static_cast<unsigned>(BLEEvent::mtu_changed)] == 0);
        assert(events[static_cast<unsigned>(BLEEvent::parameters_changed)] == 0);
        assert(mock_connections[0].refs == 0);
    }
    else if (std::strcmp(scenario, "reconnect") == 0)
    {
        connect();
        mock_conn_callbacks->disconnected(&mock_connections[0], 0x13);
        mock_next_connection = &mock_connections[1];
        assert(BLEConnection.reconnect());
        mock_conn_callbacks->connected(&mock_connections[1], 0);
        mock_conn_callbacks->disconnected(&mock_connections[0], 0x13);
        mock_gatt_callbacks->att_mtu_updated(&mock_connections[0], 247, 247);
        BLEDevice.poll();
        assert(BLEConnection.connected() && mock_connections[1].refs == 1);
        assert(events[static_cast<unsigned>(BLEEvent::mtu_changed)] == 0);
    }
    else if (std::strcmp(scenario, "recycled") == 0)
    {
        const BLEConnectionHandle connection = connect();
        BLEDevice.poll();
        assert(BLEConnection.disconnect(connection));
        mock_conn_callbacks->disconnected(&mock_connections[0], 0x13);
        mock_conn_callbacks->recycled();
        BLEDevice.poll();
        assert(events[static_cast<unsigned>(BLEEvent::disconnected)] == 1U);
        assert(events[static_cast<unsigned>(BLEEvent::connection_recycled)] == 1U);
    }
    else if (std::strcmp(scenario, "queue_overflow") == 0)
    {
        connect();
        BLEDevice.poll();
        for (unsigned index = 0; index < 40; ++index)
        {
            mock_gatt_callbacks->att_mtu_updated(&mock_connections[0], 247, 247);
        }
        assert(BLEDevice.droppedEvents() == 16);
        assert(BLEDevice.lastError() == BLEError::event_overflow);
        BLEDevice.poll();
        assert(events[static_cast<unsigned>(BLEEvent::mtu_changed)] == 24);
    }
    else if (std::strcmp(scenario, "reentrant") == 0)
    {
        reenter = true;
        connect();
        mock_conn_callbacks->le_param_updated(&mock_connections[0], 24, 0, 400);
        BLEDevice.poll();
        assert(!reenter && BLEDevice.initialized() && !BLEConnection.connected());
        assert(mock_connections[0].refs == 0);
        assert(events[static_cast<unsigned>(BLEEvent::parameters_changed)] == 0);
        assert(mock_enable_calls == 1 && mock_settings_calls == 1);
    }
    else if (std::strcmp(scenario, "pending_end") == 0)
    {
        assert(BLEConnection.connect(
            BLEAddress("01:02:03:04:05:06", BLEAddress::Type::public_address)));
        BLEDevice.end();
        assert(mock_connections[0].refs == 0);
        assert(BLEDevice.begin("new-session"));
        mock_conn_callbacks->connected(&mock_connections[0], 0);
        BLEDevice.poll();
        assert(!BLEConnection.connected() && mock_connections[0].refs == 0);
        assert(events[static_cast<unsigned>(BLEEvent::connected)] == 0);
    }
    else if (std::strcmp(scenario, "scan_copy") == 0)
    {
        assert(BLEScan.start(true));
        std::uint8_t payload[]{4, BT_DATA_NAME_COMPLETE, 'a', 'b', 'c'};
        net_buf_simple data{payload, sizeof(payload)};
        const bt_addr_le_t address{BT_ADDR_LE_PUBLIC, {{1, 2, 3, 4, 5, 6}}};
        mock_scan_callback(&address, -50, BT_GAP_ADV_TYPE_ADV_IND, &data);
        std::memset(payload, 0, sizeof(payload));
        BLEScan.onResult(scanned, nullptr);
        BLEDevice.poll();
        assert(scan_results == 1 && !BLEDevice.initialized());
        mock_scan_callback(&address, -50, BT_GAP_ADV_TYPE_ADV_IND, &data);
        assert(BLEScan.available() == 0);
    }
    else if (std::strcmp(scenario, "advertising") == 0)
    {
        assert(BLEAdvertising.clear());
        assert(BLEAdvertising.start() && mock_advertising_options == 3U);
        mock_conn_callbacks->connected(&mock_connections[0], 0);
        assert(BLEConnection.connected() && mock_connections[0].refs == 1);
        mock_conn_callbacks->disconnected(&mock_connections[0], 0x13);
        assert(BLEAdvertising.clear());
        assert(BLEAdvertising.setConnectable(false));
        assert(BLEAdvertising.start() && mock_advertising_options == 512U);
        assert(BLEAdvertising.stop());
        const std::uint8_t payload[25]{};
        assert(BLEAdvertising.setManufacturerData(0x1234, payload, sizeof(payload)));
        const auto calls = mock_advertising_calls;
        assert(!BLEAdvertising.start());
        assert(BLEDevice.lastError() == BLEError::payload_overflow &&
               mock_advertising_calls == calls);
    }
    else if (std::strcmp(scenario, "driver_failure") == 0)
    {
        mock_create_error = -ENOMEM;
        assert(!BLEConnection.connect(
            BLEAddress("01:02:03:04:05:06", BLEAddress::Type::public_address)));
        assert(!BLEConnection.connecting() && mock_connections[0].refs == 0);
        mock_create_error = 0;
        connect();
        mock_mtu_error = -EIO;
        assert(!BLEConnection.requestMtu() && mock_connections[0].refs == 1);
        mock_mtu_error = 0;
        assert(BLEConnection.requestMtu());
        mock_mtu_parameters->func(&mock_connections[0], 0, mock_mtu_parameters);
    }
    else if (std::strcmp(scenario, "multi_link") == 0)
    {
        static_assert(Device::maximumConnections() == 2U);
        assert(BLEAdvertising.clear() && BLEAdvertising.start());
        mock_connections[0].mtu = 111U;
        mock_connections[0].tx_power = -8;
        const BLEConnectionHandle central = connect(0);
        assert(BLEAdvertising.running());

        mock_connections[1].peer =
            bt_addr_le_t{BT_ADDR_LE_RANDOM, {{6, 5, 4, 3, 2, 1}}};
        mock_connections[1].mtu = 222U;
        mock_connections[1].tx_power = 3;
        mock_conn_callbacks->connected(&mock_connections[1], 0);
        const BLEConnectionHandle peripheral = BLEConnection.handle(BLELinkRole::peripheral);
        assert(peripheral.valid() && peripheral != central);
        assert(BLEConnection.count() == 2U && BLEConnection.connected(peripheral));
        assert(BLEConnection.role(central) == BLELinkRole::central);
        assert(BLEConnection.role(peripheral) == BLELinkRole::peripheral);
        assert(BLEConnection.handle(BLELinkRole::central) == central);
        assert(BLEConnection.mtu() == 111U && BLEConnection.mtu(peripheral) == 222U);
        std::int8_t central_power = 0;
        std::int8_t peripheral_power = 0;
        assert(BLEConnection.txPower(central_power) && central_power == -8);
        assert(BLEConnection.txPower(peripheral, peripheral_power) && peripheral_power == 3);
        assert(BLEConnection.requestParameters(peripheral, 24U, 40U, 0U, 400U));
        assert(mock_connections[0].parameter_updates == 0U);
        assert(mock_connections[1].parameter_updates == 1U);
        BLEDevice.poll();

        unsigned central_connected = 0U;
        unsigned peripheral_connected = 0U;
        for (std::size_t index = 0U; index < event_information_count; ++index)
        {
            const BLEEventInfo &information = event_information[index];
            if (information.event == BLEEvent::connected && information.connection == central &&
                information.role == BLELinkRole::central)
            {
                ++central_connected;
            }
            if (information.event == BLEEvent::connected &&
                information.connection == peripheral &&
                information.role == BLELinkRole::peripheral)
            {
                ++peripheral_connected;
            }
        }
        assert(central_connected == 1U && peripheral_connected == 1U);

        assert(BLEConnection.disconnect(peripheral));
        mock_conn_callbacks->disconnected(&mock_connections[1], 0x13);
        assert(BLEConnection.count() == 1U && BLEConnection.connected(central));
        assert(!BLEConnection.connected(peripheral));
        assert(BLEConnection.role(peripheral) == BLELinkRole::none);
        assert(BLEConnection.mtu(peripheral) == 0U);
        assert(!BLEConnection.disconnect(peripheral));

        mock_conn_callbacks->connected(&mock_connections[2], 0);
        assert(mock_connections[2].disconnects == 1);
        assert(BLEConnection.count() == 1U);
    }
#if CONFIG_NUCODE_BLE_CENTRAL_CONNECTION_SLOTS == 2
    else if (std::strcmp(scenario, "two_central") == 0)
    {
        const BLEConnectionHandle first = connect(0);
        const BLEConnectionHandle second = connect(1);
        assert(first.valid() && second.valid() && first != second);
        assert(BLEConnection.count() == 2U);
        assert(BLEConnection.handle(BLELinkRole::central) == first);
        assert(BLEConnection.role(first) == BLELinkRole::central);
        assert(BLEConnection.role(second) == BLELinkRole::central);

        assert(BLEConnection.disconnect(first));
        mock_conn_callbacks->disconnected(&mock_connections[0], 0x13);
        mock_next_connection = &mock_connections[2];
        BLEConnectionHandle replacement;
        assert(BLEConnection.connect(
            BLEAddress("02:03:04:05:06:07", BLEAddress::Type::public_address), replacement));
        mock_conn_callbacks->connected(&mock_connections[2], 0);
        assert(replacement.valid() && replacement != first && replacement != second);
        assert(BLEConnection.count() == 2U);

        mock_conn_callbacks->disconnected(&mock_connections[0], 0x13);
        assert(BLEConnection.count() == 2U);
        assert(BLEConnection.connected(replacement) && BLEConnection.connected(second));
        assert(!BLEConnection.connected(first));

        assert(BLEConnection.disconnect(second));
        mock_conn_callbacks->disconnected(&mock_connections[1], 0x13);
        assert(BLEConnection.count() == 1U);
        assert(BLEConnection.disconnect(replacement));
        mock_conn_callbacks->disconnected(&mock_connections[2], 0x13);
        assert(BLEConnection.count() == 0U);
    }
#endif
    else if (std::strcmp(scenario, "role_callback_guard") == 0)
    {
        assert(BLEAdvertising.clear() && BLEAdvertising.start());
        const BLEConnectionHandle central = connect(0);

        mock_conn_callbacks->connected(&mock_connections[0], 0);
        assert(mock_connections[0].disconnects == 0);
        assert(BLEConnection.count() == 1U);
        assert(!BLEConnection.handle(BLELinkRole::peripheral).valid());

        mock_connections[1].role = BT_CONN_ROLE_CENTRAL;
        mock_conn_callbacks->connected(&mock_connections[1], 0);
        assert(mock_connections[1].disconnects == 1);
        assert(BLEConnection.count() == 1U && BLEConnection.connected(central));

        mock_conn_callbacks->connected(&mock_connections[2], 0);
        const BLEConnectionHandle peripheral = BLEConnection.handle(BLELinkRole::peripheral);
        assert(peripheral.valid() && BLEConnection.count() == 2U);
        mock_conn_callbacks->connected(&mock_connections[2], 0);
        assert(mock_connections[2].disconnects == 0);
        assert(BLEConnection.count() == 2U);

        BLEDevice.poll();
        assert(events[static_cast<unsigned>(BLEEvent::connected)] == 2U);
    }
    else if (std::strcmp(scenario, "generation") == 0)
    {
        const BLEConnectionHandle first = connect(0);
        BLEDevice.poll();
        assert(BLEConnection.requestMtu(first));
        bt_gatt_exchange_params *const first_request = mock_mtu_parameters;
        assert(BLEConnection.disconnect(first));
        mock_conn_callbacks->disconnected(&mock_connections[0], 0x13);

        mock_next_connection = &mock_connections[1];
        BLEConnectionHandle second;
        assert(BLEConnection.reconnect(second));
        mock_conn_callbacks->connected(&mock_connections[1], 0);
        assert(second.valid() && second != first);
        assert(!BLEConnection.connected(first) && BLEConnection.connected(second));
        assert(!BLEConnection.requestPhy(first, true));

        first_request->func(&mock_connections[0], 0, first_request);
        mock_gatt_callbacks->att_mtu_updated(&mock_connections[0], 247, 247);
        mock_conn_callbacks->le_param_updated(&mock_connections[0], 24, 0, 400);
        BLEDevice.poll();
        assert(events[static_cast<unsigned>(BLEEvent::mtu_changed)] == 0U);
        assert(events[static_cast<unsigned>(BLEEvent::parameters_changed)] == 0U);

        assert(BLEConnection.requestMtu(second));
        bt_gatt_exchange_params *const second_request = mock_mtu_parameters;
        second_request->func(&mock_connections[1], 0, second_request);
        BLEDevice.poll();
        assert(events[static_cast<unsigned>(BLEEvent::mtu_changed)] == 1U);
    }
    else if (std::strcmp(scenario, "end_two_links") == 0)
    {
        assert(BLEAdvertising.clear() && BLEAdvertising.start());
        const BLEConnectionHandle central = connect(0);
        mock_conn_callbacks->connected(&mock_connections[1], 0);
        const BLEConnectionHandle peripheral = BLEConnection.handle(BLELinkRole::peripheral);
        assert(BLEConnection.count() == 2U);
        BLEDevice.end();
        assert(!BLEConnection.connected(central) && !BLEConnection.connected(peripheral));
        assert(mock_connections[0].refs == 0 && mock_connections[1].refs == 0);
        assert(mock_connections[0].disconnects == 1 && mock_connections[1].disconnects == 1);
        assert(BLEDevice.begin("after-two-link-end"));
        mock_conn_callbacks->disconnected(&mock_connections[0], 0x13);
        mock_conn_callbacks->disconnected(&mock_connections[1], 0x13);
        BLEDevice.poll();
        assert(BLEConnection.count() == 0U);
    }
    else
    {
        assert(false);
    }
    BLEDevice.end();
    for (const auto &connection : mock_connections)
    {
        assert(connection.refs == 0);
    }
    std::cout << "R12_GAP_PASS=" << scenario << '\n';
}
