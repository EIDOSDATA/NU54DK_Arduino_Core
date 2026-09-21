/** @file @brief W04 periodic advertising·sync·PAST production lifecycle을 검증합니다. */
#include <NUCODE_BLE_GAP.h>
#include <ble_mock.h>
#include <array>
#include <cstring>
#include <iostream>

using namespace nucode::ble;

std::array<BLEEventInfo, 48> detailed_events{};
std::size_t detailed_event_count = 0U;
BLEPeriodicReport observed_report{};
unsigned observed_report_count = 0U;

/** @brief periodic handle event를 main-thread에서 보존합니다. */
void observeDetailed(const BLEEventInfo &information, void *)
{
    assert(detailed_event_count < detailed_events.size());
    detailed_events[detailed_event_count++] = information;
}

/** @brief periodic report가 callback buffer와 독립적인지 확인하도록 복사합니다. */
void observeReport(const BLEPeriodicReport &report, void *)
{
    observed_report = report;
    ++observed_report_count;
}

/** @brief 전체 255-byte 길이의 올바른 단일 AD structure를 만듭니다. */
std::array<std::uint8_t, 255> maximumPayload()
{
    std::array<std::uint8_t, 255> payload{};
    payload[0] = 254U;
    payload[1] = BT_DATA_MANUFACTURER_DATA;
    for (std::size_t index = 2U; index < payload.size(); ++index)
    {
        payload[index] = static_cast<std::uint8_t>(index);
    }
    return payload;
}

/** @brief non-connectable extended set을 생성합니다. */
BLEAdvertisingSetHandle createAdvertisingSet()
{
    BLEExtendedAdvertisingParameters parameters{};
    parameters.sid = 4U;
    BLEAdvertisingSetHandle advertising_set;
    assert(BLEExtendedAdvertising.create(parameters, advertising_set));
    return advertising_set;
}

/** @brief central connection을 만들고 연결 callback까지 완료합니다. */
BLEConnectionHandle connectPeer()
{
    mock_next_connection = &mock_connections[0];
    BLEConnectionHandle connection;
    assert(BLEConnection.connect(
        BLEAddress("01:02:03:04:05:06", BLEAddress::Type::public_address), connection));
    mock_conn_callbacks->connected(&mock_connections[0], 0U);
    assert(BLEConnection.connected(connection));
    return connection;
}

int main(int argc, char **argv)
{
    assert(argc == 2);
    const char *const scenario = argv[1];
    BLEDevice.onEventInfo(observeDetailed);
    assert(BLEDevice.begin("m28-w04"));
    BLEDevice.poll();

    if (std::strcmp(scenario, "advertiser") == 0)
    {
        const BLEAdvertisingSetHandle advertising_set = createAdvertisingSet();
        BLEPeriodicAdvertisingParameters parameters{};
        parameters.interval_min = 80U;
        parameters.interval_max = 96U;
        parameters.include_tx_power = true;
        parameters.include_adi = true;
        assert(BLEPeriodicAdvertising.configure(advertising_set, parameters));
        assert(mock_periodic_parameters.interval_min == 80U);
        assert((mock_periodic_parameters.options & BT_LE_PER_ADV_OPT_USE_TX_POWER) != 0U);
        const auto payload = maximumPayload();
        assert(BLEPeriodicAdvertising.setData(advertising_set, payload.data(), payload.size()));
        assert(mock_periodic_data_length == payload.size());
        assert(std::memcmp(mock_periodic_data, payload.data(), payload.size()) == 0);
        assert(BLEPeriodicAdvertising.start(advertising_set));
        assert(BLEPeriodicAdvertising.running(advertising_set));
        assert(!BLEExtendedAdvertising.remove(advertising_set));
        assert(BLEPeriodicAdvertising.stop(advertising_set));
        assert(!BLEPeriodicAdvertising.running(advertising_set));
        assert(BLEExtendedAdvertising.remove(advertising_set));
    }
    else if (std::strcmp(scenario, "sync_report") == 0)
    {
        BLEPeriodicAdvertising.onReport(observeReport);
        const BLEAddress address("11:22:33:44:55:66", BLEAddress::Type::random_address);
        BLEPeriodicSyncHandle first;
        assert(BLEPeriodicAdvertising.createSync(address, 7U, first, 2U, 100U));
        assert(first.valid() && BLEPeriodicAdvertising.exists(first));
        bt_le_per_adv_sync *const first_instance = &mock_periodic_syncs[0];
        const bt_addr_le_t zephyr_address{BT_ADDR_LE_RANDOM, {{0x66, 0x55, 0x44, 0x33, 0x22, 0x11}}};
        bt_le_per_adv_sync_synced_info synced_information{
            &zephyr_address, 7U, 80U, BT_GAP_LE_PHY_1M, true, 0U, nullptr};
        mock_periodic_sync_callbacks->synced(first_instance, &synced_information);
        assert(BLEPeriodicAdvertising.synchronized(first));

        auto payload = maximumPayload();
        bt_le_per_adv_sync_recv_info report_information{
            &zephyr_address, 7U, 3, -47, 0U};
        net_buf_simple buffer{payload.data(), payload.size()};
        mock_periodic_sync_callbacks->recv(first_instance, &report_information, &buffer);
        payload.fill(0U);
        BLEDevice.poll();
        assert(observed_report_count == 1U);
        assert(observed_report.sync == first && observed_report.sid == 7U);
        assert(observed_report.tx_power == 3 && observed_report.rssi == -47);
        assert(observed_report.payload_length == 255U && !observed_report.truncated);
        assert(observed_report.payload[254] == 254U);

        assert(BLEPeriodicAdvertising.deleteSync(first));
        BLEPeriodicSyncHandle second;
        assert(BLEPeriodicAdvertising.createSync(address, 7U, second));
        assert(second != first);
        const unsigned reports_before_stale = observed_report_count;
        mock_periodic_sync_callbacks->recv(first_instance, &report_information, &buffer);
        BLEDevice.poll();
        assert(observed_report_count == reports_before_stale);
    }
    else if (std::strcmp(scenario, "past") == 0)
    {
        const BLEConnectionHandle connection = connectPeer();
        const BLEAddress address("11:22:33:44:55:66", BLEAddress::Type::random_address);
        BLEPeriodicSyncHandle sync;
        assert(BLEPeriodicAdvertising.createSync(address, 7U, sync));
        const bt_addr_le_t zephyr_address{BT_ADDR_LE_RANDOM, {{0x66, 0x55, 0x44, 0x33, 0x22, 0x11}}};
        bt_le_per_adv_sync_synced_info synced_information{
            &zephyr_address, 7U, 80U, BT_GAP_LE_PHY_1M, true, 0U, nullptr};
        mock_periodic_sync_callbacks->synced(&mock_periodic_syncs[0], &synced_information);
        assert(BLEPeriodicAdvertising.transferSync(sync, connection, 0x1234U));
        assert(BLEPeriodicAdvertising.deleteSync(sync));

        const BLEAdvertisingSetHandle advertising_set = createAdvertisingSet();
        assert(BLEPeriodicAdvertising.configure(advertising_set));
        assert(BLEPeriodicAdvertising.transferSet(advertising_set, connection, 0x5678U));
        assert(BLEPeriodicAdvertising.subscribeTransfers(connection, 1U, 100U));
        bt_le_per_adv_sync_synced_info transferred_information{
            &zephyr_address, 7U, 80U, BT_GAP_LE_PHY_1M, true, 0x9999U,
            &mock_connections[0]};
        mock_periodic_sync_callbacks->synced(&mock_periodic_syncs[1],
                                             &transferred_information);
        BLEDevice.poll();
        bool received_transferred_handle = false;
        for (std::size_t index = 0U; index < detailed_event_count; ++index)
        {
            if (detailed_events[index].event == BLEEvent::periodic_sync_synchronized &&
                detailed_events[index].periodic_sync.valid())
            {
                received_transferred_handle = true;
            }
        }
        assert(received_transferred_handle);
        assert(BLEPeriodicAdvertising.unsubscribeTransfers(connection));
        assert(mock_past_transfer_count == 2U);
        assert(mock_past_subscribe_count == 1U);
        assert(mock_past_unsubscribe_count == 1U);
        assert(mock_connections[0].refs == 1);
    }
    else if (std::strcmp(scenario, "end_cleanup") == 0)
    {
        const BLEAdvertisingSetHandle advertising_set = createAdvertisingSet();
        assert(BLEPeriodicAdvertising.configure(advertising_set));
        assert(BLEPeriodicAdvertising.start(advertising_set));
        const BLEAddress address("11:22:33:44:55:66", BLEAddress::Type::random_address);
        BLEPeriodicSyncHandle sync;
        assert(BLEPeriodicAdvertising.createSync(address, 2U, sync));
        bt_le_per_adv_sync *const sync_instance = &mock_periodic_syncs[0];
        bt_le_ext_adv *const advertising_instance = &mock_ext_advertisers[0];
        BLEDevice.end();
        assert(sync_instance->deleted && advertising_instance->deleted);
        assert(!BLEPeriodicAdvertising.exists(sync));
        assert(!BLEPeriodicAdvertising.running(advertising_set));
        assert(BLEDevice.begin("after-end"));
        BLEDevice.poll();
        const std::size_t events_before_stale = detailed_event_count;
        const bt_addr_le_t zephyr_address{BT_ADDR_LE_RANDOM, {{1, 2, 3, 4, 5, 6}}};
        bt_le_per_adv_sync_synced_info synced_information{
            &zephyr_address, 2U, 80U, BT_GAP_LE_PHY_1M, true, 0U, nullptr};
        mock_periodic_sync_callbacks->synced(sync_instance, &synced_information);
        BLEDevice.poll();
        assert(detailed_event_count == events_before_stale);
        assert(!BLEPeriodicAdvertising.exists(sync));
    }
    else
    {
        assert(false);
    }

    BLEDevice.end();
    std::cout << "M28_W04_HOST_PASS=" << scenario << '\n';
}
