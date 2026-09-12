/** @file @brief W03 extended advertising/scanning의 production lifecycle을 검증합니다. */
#include <NUCODE_BLE_GAP.h>
#include <ble_mock.h>
#include <array>
#include <cstring>
#include <iostream>

using namespace nucode::ble;

std::array<BLEEventInfo, 32> detailed_events{};
std::size_t detailed_event_count = 0U;
BLEScanResult scanned_result{};
unsigned scanned_count = 0U;

/** @brief advertising set generation event를 main-thread에서 보존합니다. */
void observeDetailed(const BLEEventInfo &information, void *)
{
    assert(detailed_event_count < detailed_events.size());
    detailed_events[detailed_event_count++] = information;
}

/** @brief extended scan 결과가 callback 뒤에도 유지되는지 확인하도록 복사합니다. */
void observeScan(const BLEScanResult &result, void *)
{
    scanned_result = result;
    ++scanned_count;
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

int main(int argc, char **argv)
{
    assert(argc == 2);
    const char *const scenario = argv[1];
    BLEDevice.onEventInfo(observeDetailed);
    BLEScan.onResult(observeScan);
    assert(BLEDevice.begin("m28-w03"));
    BLEDevice.poll();

    if (std::strcmp(scenario, "set_lifecycle") == 0)
    {
        BLEExtendedAdvertisingParameters parameters{};
        parameters.sid = 7U;
        parameters.coded = true;
        parameters.include_tx_power = true;
        BLEAdvertisingSetHandle first;
        assert(BLEExtendedAdvertising.create(parameters, first));
        assert(first.valid() && BLEExtendedAdvertising.exists(first));
        assert(mock_ext_advertising_sid == 7U);
        assert((mock_ext_advertising_options & BT_LE_ADV_OPT_EXT_ADV) != 0U);
        assert((mock_ext_advertising_options & BT_LE_ADV_OPT_CODED) != 0U);
        const auto payload = maximumPayload();
        assert(BLEExtendedAdvertising.setData(first, payload.data(), payload.size()));
        assert(mock_ext_advertising_length == payload.size());
        assert(std::memcmp(mock_ext_advertising_data, payload.data(), payload.size()) == 0);
        assert(BLEExtendedAdvertising.start(first, 100U, 10U));
        assert(BLEExtendedAdvertising.running(first));

        bt_le_ext_adv *const first_instance = &mock_ext_advertisers[0];
        bt_le_ext_adv_sent_info sent{};
        mock_ext_advertising_callbacks->sent(first_instance, &sent);
        assert(!BLEExtendedAdvertising.running(first));
        assert(BLEExtendedAdvertising.remove(first));
        assert(!BLEExtendedAdvertising.exists(first));

        BLEAdvertisingSetHandle second;
        assert(BLEExtendedAdvertising.create(parameters, second));
        assert(second.valid() && second != first);
        BLEDevice.poll();
        const std::size_t events_before_stale = detailed_event_count;
        mock_ext_advertising_callbacks->sent(first_instance, &sent);
        BLEDevice.poll();
        assert(detailed_event_count == events_before_stale);
        assert(BLEExtendedAdvertising.exists(second));
    }
    else if (std::strcmp(scenario, "invalid_payload") == 0)
    {
        BLEExtendedAdvertisingParameters invalid{};
        invalid.connectable = true;
        invalid.scannable = true;
        BLEAdvertisingSetHandle handle;
        assert(!BLEExtendedAdvertising.create(invalid, handle));
        assert(!handle.valid());

        BLEExtendedAdvertisingParameters parameters{};
        assert(BLEExtendedAdvertising.create(parameters, handle));
        std::array<std::uint8_t, 256> too_large{};
        assert(!BLEExtendedAdvertising.setData(handle, too_large.data(), too_large.size()));
        assert(BLEDevice.lastError() == BLEError::payload_overflow);
        const std::uint8_t malformed[] = {5U, BT_DATA_FLAGS, 1U};
        assert(!BLEExtendedAdvertising.setData(handle, malformed, sizeof(malformed)));
        assert(BLEDevice.lastError() == BLEError::invalid_argument);
    }
    else if (std::strcmp(scenario, "extended_scan") == 0)
    {
        assert(BLEScan.startExtended(true, true, false));
        assert((mock_scan_options & BT_LE_SCAN_OPT_FILTER_DUPLICATE) == 0U);
        assert((mock_scan_options & BT_LE_SCAN_OPT_CODED) != 0U);
        assert(mock_extended_scan_callbacks != nullptr);
        auto payload = maximumPayload();
        const bt_addr_le_t address{BT_ADDR_LE_RANDOM, {{1, 3, 5, 7, 9, 11}}};
        const bt_le_scan_recv_info information{
            &address,
            9U,
            -42,
            4,
            BT_GAP_ADV_TYPE_ADV_IND,
            static_cast<std::uint16_t>(BT_GAP_ADV_PROP_CONNECTABLE |
                                       BT_GAP_ADV_PROP_EXT_ADV),
            160U,
            BT_GAP_LE_PHY_1M,
            BT_GAP_LE_PHY_CODED,
        };
        net_buf_simple data{payload.data(), payload.size()};
        mock_extended_scan_callbacks->recv(&information, &data);
        payload.fill(0U);
        BLEDevice.poll();
        assert(scanned_count == 1U);
        assert(scanned_result.extended && scanned_result.connectable);
        assert(scanned_result.sid == 9U && scanned_result.rssi == -42);
        assert(scanned_result.tx_power == 4 && scanned_result.periodic_interval == 160U);
        assert(scanned_result.primary_phy == BLEPhy::le_1m);
        assert(scanned_result.secondary_phy == BLEPhy::coded);
        assert(scanned_result.payload_length == 255U && !scanned_result.truncated);
        assert(scanned_result.payload[0] == 254U && scanned_result.payload[254] == 254U);
    }
    else if (std::strcmp(scenario, "connected_scan") == 0)
    {
        mock_next_connection = &mock_connections[0];
        BLEConnectionHandle connection;
        assert(BLEConnection.connect(
            BLEAddress("01:02:03:04:05:06", BLEAddress::Type::public_address), connection));
        mock_conn_callbacks->connected(&mock_connections[0], 0U);
        assert(BLEConnection.connected(connection));
        assert(BLEScan.startExtended(false, false, false));
        assert(BLEScan.running());
        assert(BLEScan.stop());
    }
    else if (std::strcmp(scenario, "end_cleanup") == 0)
    {
        BLEExtendedAdvertisingParameters parameters{};
        BLEAdvertisingSetHandle handle;
        assert(BLEExtendedAdvertising.create(parameters, handle));
        assert(BLEExtendedAdvertising.start(handle));
        bt_le_ext_adv *const instance = &mock_ext_advertisers[0];
        BLEDevice.end();
        assert(instance->deleted && !BLEExtendedAdvertising.exists(handle));
        assert(BLEDevice.begin("after-end"));
        bt_le_ext_adv_sent_info sent{};
        mock_ext_advertising_callbacks->sent(instance, &sent);
        BLEDevice.poll();
        assert(!BLEExtendedAdvertising.exists(handle));
    }
    else
    {
        assert(false);
    }

    BLEDevice.end();
    std::cout << "M28_W03_HOST_PASS=" << scenario << '\n';
}
