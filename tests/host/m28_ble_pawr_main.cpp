/** @file @brief W05 PAwR advertiser·scanner production lifecycle을 검증합니다. */
#include <NUCODE_BLE_GAP.h>
#include <ble_mock.h>
#include <array>
#include <cstring>
#include <iostream>

using namespace nucode::ble;

BLEPawrResponse observed_response{};
unsigned observed_response_count = 0U;

/** @brief PAwR response가 callback buffer와 독립적인지 확인하도록 복사합니다. */
void observeResponse(const BLEPawrResponse &response, void *)
{
    observed_response = response;
    ++observed_response_count;
}

/** @brief PAwR용 non-connectable extended set을 생성합니다. */
BLEAdvertisingSetHandle createAdvertisingSet()
{
    BLEExtendedAdvertisingParameters parameters{};
    parameters.sid = 5U;
    BLEAdvertisingSetHandle advertising_set;
    assert(BLEExtendedAdvertising.create(parameters, advertising_set));
    return advertising_set;
}

/** @brief PAwR metadata가 있는 synchronized periodic sync를 만듭니다. */
BLEPeriodicSyncHandle createSynchronizedSync()
{
    const BLEAddress address("11:22:33:44:55:66", BLEAddress::Type::random_address);
    BLEPeriodicSyncHandle sync;
    assert(BLEPeriodicAdvertising.createSync(address, 5U, sync));
    const bt_addr_le_t zephyr_address{BT_ADDR_LE_RANDOM, {{0x66, 0x55, 0x44, 0x33, 0x22, 0x11}}};
    bt_le_per_adv_sync_synced_info information{
        &zephyr_address, 5U, 160U, BT_GAP_LE_PHY_1M, true, 0U, nullptr,
        4U, 8U, 1U, 2U};
    mock_periodic_sync_callbacks->synced(&mock_periodic_syncs[0], &information);
    assert(BLEPeriodicAdvertising.synchronized(sync));
    return sync;
}

int main(int argc, char **argv)
{
    assert(argc == 2);
    const char *const scenario = argv[1];
    BLEPawr.onResponse(observeResponse);
    assert(BLEDevice.begin("m28-w05"));
    BLEDevice.poll();

    if (std::strcmp(scenario, "advertiser_request") == 0)
    {
        const BLEAdvertisingSetHandle advertising_set = createAdvertisingSet();
        assert(BLEPawr.configureAdvertiser(advertising_set));
        assert(mock_periodic_parameters.num_subevents == 4U);
        assert(mock_periodic_parameters.num_response_slots == 4U);
        assert(mock_periodic_parameters.interval_min == 0x0100U);
        assert(mock_periodic_parameters.interval_max == 0x0100U);
        assert(mock_periodic_parameters.subevent_interval == 64U);
        assert(mock_periodic_parameters.response_slot_delay == 8U);
        assert(mock_periodic_parameters.response_slot_spacing == 80U);
        for (std::uint8_t subevent = 0U; subevent < 4U; ++subevent)
        {
            const std::uint8_t payload[] = {subevent, 0xa5U};
            assert(BLEPawr.setSubeventData(advertising_set, subevent, payload,
                                          sizeof(payload)));
        }
        bt_le_per_adv_data_request request{0U, 4U};
        mock_ext_advertising_callbacks->pawr_data_request(&mock_ext_advertisers[0], &request);
        assert(mock_pawr_subevent_data_count == 4U);
    }
    else if (std::strcmp(scenario, "advertiser_wrapped_request") == 0)
    {
        const BLEAdvertisingSetHandle advertising_set = createAdvertisingSet();
        assert(BLEPawr.configureAdvertiser(advertising_set));
        for (std::uint8_t subevent = 0U; subevent < 4U; ++subevent)
        {
            const std::uint8_t payload[] = {subevent, 0x5aU};
            assert(BLEPawr.setSubeventData(advertising_set, subevent, payload,
                                          sizeof(payload)));
        }
        bt_le_per_adv_data_request request{3U, 4U};
        mock_ext_advertising_callbacks->pawr_data_request(&mock_ext_advertisers[0], &request);
        assert(mock_pawr_subevent_data_count == 4U);
        assert(BLEDevice.lastError() == BLEError::none);
    }
    else if (std::strcmp(scenario, "advertiser_response") == 0)
    {
        const BLEAdvertisingSetHandle advertising_set = createAdvertisingSet();
        assert(BLEPawr.configureAdvertiser(advertising_set));
        std::array<std::uint8_t, 249> payload{};
        payload.fill(0x5aU);
        bt_le_per_adv_response_info information{2U, 0U, 3, -51, 0U, 1U};
        net_buf_simple buffer{payload.data(), payload.size()};
        mock_ext_advertising_callbacks->pawr_response(&mock_ext_advertisers[0],
                                                      &information, &buffer);
        payload.fill(0U);
        BLEDevice.poll();
        assert(observed_response_count == 1U);
        assert(observed_response.advertising_set == advertising_set);
        assert(observed_response.subevent == 2U && observed_response.response_slot == 1U);
        assert(observed_response.received && !observed_response.truncated);
        assert(observed_response.payload_length == 249U);
        assert(observed_response.payload[248] == 0x5aU);
    }
    else if (std::strcmp(scenario, "scanner_response") == 0)
    {
        const BLEPeriodicSyncHandle sync = createSynchronizedSync();
        const std::uint8_t subevents[] = {0U, 1U, 2U, 3U};
        assert(BLEPawr.configureScanner(sync, subevents, sizeof(subevents)));
        std::array<std::uint8_t, 249> payload{};
        payload.fill(0x3cU);
        assert(BLEPawr.sendResponse(sync, 123U, 1U, 2U, 3U,
                                    payload.data(), payload.size()));
        assert(mock_pawr_scanner_config_count == 1U);
        assert(mock_pawr_response_data_count == 1U);
        assert(mock_pawr_response_parameters.request_event == 123U);
        assert(mock_pawr_response_parameters.response_slot == 3U);
        assert(mock_pawr_response_length == 249U);
        assert(mock_pawr_response_data[248] == 0x3cU);
    }
    else if (std::strcmp(scenario, "invalid_window_end") == 0)
    {
        const BLEAdvertisingSetHandle advertising_set = createAdvertisingSet();
        BLEPawrAdvertisingParameters invalid_geometry{};
        invalid_geometry.subevent_interval = 20U;
        assert(!BLEPawr.configureAdvertiser(advertising_set, invalid_geometry));
        assert(BLEDevice.lastError() == BLEError::invalid_argument);
        assert(BLEPawr.configureAdvertiser(advertising_set));
        std::array<std::uint8_t, 250> too_large{};
        assert(!BLEPawr.setSubeventData(advertising_set, 0U, too_large.data(),
                                       too_large.size()));
        assert(BLEDevice.lastError() == BLEError::payload_overflow);

        const BLEPeriodicSyncHandle sync = createSynchronizedSync();
        const std::uint8_t duplicate_subevents[] = {0U, 0U};
        assert(!BLEPawr.configureScanner(sync, duplicate_subevents,
                                        sizeof(duplicate_subevents)));
        assert(!BLEPawr.sendResponse(sync, 1U, 0U, 0U, 4U, nullptr, 0U));

        bt_le_ext_adv *const old_advertiser = &mock_ext_advertisers[0];
        BLEDevice.end();
        assert(BLEDevice.begin("after-end"));
        const unsigned responses_before_stale = observed_response_count;
        bt_le_per_adv_response_info information{0U, 0U, 0, -40, 0U, 0U};
        mock_ext_advertising_callbacks->pawr_response(old_advertiser, &information, nullptr);
        BLEDevice.poll();
        assert(observed_response_count == responses_before_stale);
    }
    else
    {
        assert(false);
    }

    BLEDevice.end();
    std::cout << "M28_W05_HOST_PASS=" << scenario << '\n';
}
