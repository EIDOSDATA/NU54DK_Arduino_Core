/** @file @brief M32-W05 Nordic SDC 확장의 Host lifecycle·negative를 검증합니다. */
#include <NUCODE_BLE_GAP.h>
#include <ble_mock.h>
#include <sdc_hci_vs.h>
#include <zephyr/kernel.h>
#include <zephyr/bluetooth/hci.h>

#include <array>
#include <cstring>
#include <iostream>

using namespace nucode::ble;

std::uint8_t last_llpm_enable = 0U;
sdc_hci_cmd_vs_conn_update_t last_llpm_update{};
std::uint8_t last_connection_report_enable = 0U;
sdc_hci_cmd_vs_qos_channel_survey_enable_t last_survey{};
sdc_hci_cmd_vs_set_event_start_task_t last_event_trigger{};
std::uint8_t last_anchor_enable = 0U;

extern "C"
{
    int hci_vs_sdc_llpm_mode_set(const sdc_hci_cmd_vs_llpm_mode_set_t *parameters)
    {
        last_llpm_enable = parameters->enable;
        return 0;
    }

    int hci_vs_sdc_conn_update(const sdc_hci_cmd_vs_conn_update_t *parameters)
    {
        last_llpm_update = *parameters;
        return 0;
    }

    int hci_vs_sdc_qos_conn_event_report_enable(
        const sdc_hci_cmd_vs_qos_conn_event_report_enable_t *parameters)
    {
        last_connection_report_enable = parameters->enable;
        return 0;
    }

    int hci_vs_sdc_qos_channel_survey_enable(
        const sdc_hci_cmd_vs_qos_channel_survey_enable_t *parameters)
    {
        last_survey = *parameters;
        return 0;
    }

    int hci_vs_sdc_set_event_start_task(
        const sdc_hci_cmd_vs_set_event_start_task_t *parameters)
    {
        last_event_trigger = *parameters;
        return 0;
    }

    int hci_vs_sdc_conn_anchor_point_update_event_report_enable(
        const sdc_hci_cmd_vs_conn_anchor_point_update_event_report_enable_t *parameters)
    {
        last_anchor_enable = parameters->enable;
        return 0;
    }
}

/** @brief central mock link를 만들고 generation handle을 반환합니다. */
BLEConnectionHandle connectCentral()
{
    const BLEAddress address("C0:DE:00:00:05:01", BLEAddress::Type::random_address);
    BLEConnectionHandle pending;
    assert(BLEConnection.connect(address, pending));
    assert(mock_conn_callbacks != nullptr);
    mock_conn_callbacks->connected(&mock_connections[0], 0U);
    const BLEConnectionHandle connection = BLEConnection.handle(BLELinkRole::central);
    assert(connection.valid());
    return connection;
}

/** @brief 지정 vendor subevent와 payload를 등록 callback에 주입합니다. */
template <typename Payload>
void emitVendorEvent(std::uint8_t subevent, const Payload &payload)
{
    std::array<std::uint8_t, sizeof(Payload) + 1U> bytes{};
    bytes[0] = subevent;
    std::memcpy(bytes.data() + 1U, &payload, sizeof(payload));
    net_buf_simple buffer{};
    net_buf_simple_init_with_data(&buffer, bytes.data(), bytes.size());
    assert(mock_hci_vendor_event_callback != nullptr);
    assert(mock_hci_vendor_event_callback(&buffer));
}

/** @brief LLPM mode·2M PHY·interval validation을 검증합니다. */
void testLlpm()
{
    assert(BLEDevice.begin("m32-w05-llpm"));
    assert(BLENordic.setLlpmMode(true));
    assert(last_llpm_enable == 1U);
    const BLEConnectionHandle connection = connectCentral();
    assert(mock_last_create_parameters.interval_min == 0x0d01U);
    assert(mock_last_create_parameters.interval_max == 0x0d01U);
    mock_connections[0].interval_us = 0x0d01U * 1250U;
    BLEConnectionParameters parameters;
    assert(BLEConnection.parameters(connection, parameters));
    assert(parameters.interval_us == 1000U);
    mock_connection_phy.tx_phy = BT_GAP_LE_PHY_2M;
    assert(BLENordic.requestLlpmInterval(connection, 1000U, 0U, 300U));
    assert(last_llpm_update.conn_handle == 1U);
    assert(last_llpm_update.conn_interval_us == 1000U);
    assert(!BLENordic.requestLlpmInterval(connection, 1500U, 0U, 300U));
    assert(BLEDevice.lastError() == BLEError::invalid_argument);
    assert(!BLENordic.setLlpmMode(false));
    assert(BLEDevice.lastError() == BLEError::wrong_state);
    BLEDevice.end();
}

unsigned connection_callback_count = 0U;
unsigned survey_callback_count = 0U;
unsigned anchor_callback_count = 0U;

/** @brief main-thread connection report callback 값을 검사합니다. */
void onConnectionReport(const BLENordicConnectionEventReport &report, void *)
{
    assert(report.connection.valid());
    assert(report.event_counter == 9U);
    assert(report.channel_index == 17U);
    assert(report.crc_ok_count == 4U);
    assert(report.crc_error_count == 1U);
    ++connection_callback_count;
}

/** @brief main-thread survey callback 값을 검사합니다. */
void onSurveyReport(const BLENordicChannelSurveyReport &report, void *)
{
    assert(report.channel_energy_dbm[0] == -71);
    assert(report.channel_energy_dbm[39] == -32);
    ++survey_callback_count;
}

/** @brief main-thread anchor callback 값을 검사합니다. */
void onAnchorReport(const BLENordicAnchorPointReport &report, void *)
{
    assert(report.connection.valid());
    assert(report.event_counter == 0xfffeU);
    assert(report.controller_clock_us == 1000000U);
    ++anchor_callback_count;
}

/** @brief QoS·survey·anchor queue와 stale disconnect 차단을 검증합니다. */
void testReports()
{
    assert(BLEDevice.begin("m32-w05-reports"));
    const BLEConnectionHandle connection = connectCentral();
    BLENordic.onConnectionEvent(onConnectionReport);
    BLENordic.onChannelSurvey(onSurveyReport);
    BLENordic.onAnchorPoint(onAnchorReport);
    assert(BLENordic.setConnectionEventReports(true));
    assert(BLENordic.setChannelSurvey(true, 100000U));
    assert(BLENordic.setAnchorPointReports(true));
    assert(last_connection_report_enable == 1U);
    assert(last_survey.enable == 1U && last_survey.interval_us == 100000U);
    assert(last_anchor_enable == 1U);

    const sdc_hci_subevent_vs_qos_conn_event_report_t connection_report = {
        .conn_handle = 1U,
        .event_counter = 9U,
        .channel_index = 17U,
        .crc_ok_count = 4U,
        .crc_error_count = 1U,
        .nak_count = 2U,
        .rx_timeout = 0U,
    };
    sdc_hci_subevent_vs_qos_channel_survey_report_t survey{};
    for (std::size_t index = 0U; index < 40U; ++index)
    {
        survey.channel_energy[index] = static_cast<std::int8_t>(-71 + index);
    }
    const sdc_hci_subevent_vs_conn_anchor_point_update_report_t anchor = {
        .conn_handle = 1U,
        .event_counter = 0xfffeU,
        .anchor_point_us = 1000000U,
    };
    emitVendorEvent(SDC_HCI_SUBEVENT_VS_QOS_CONN_EVENT_REPORT, connection_report);
    emitVendorEvent(SDC_HCI_SUBEVENT_VS_QOS_CHANNEL_SURVEY_REPORT, survey);
    emitVendorEvent(SDC_HCI_SUBEVENT_VS_CONN_ANCHOR_POINT_UPDATE_REPORT, anchor);
    BLEDevice.poll();
    assert(connection_callback_count == 1U);
    assert(survey_callback_count == 1U);
    assert(anchor_callback_count == 1U);

    BLENordicAnchorPointReport public_anchor = {
        .connection = connection,
        .event_counter = 0xfffeU,
        .controller_clock_us = 1000000U,
    };
    std::uint64_t projected = 0U;
    assert(BLENordic.projectAnchorPoint(public_anchor, 1U, 1000U, projected));
    assert(projected == 1003000U);

    emitVendorEvent(SDC_HCI_SUBEVENT_VS_QOS_CONN_EVENT_REPORT, connection_report);
    mock_conn_callbacks->disconnected(&mock_connections[0], 0x13U);
    BLEDevice.poll();
    assert(connection_callback_count == 1U);
    BLEDevice.end();
}

/** @brief survey·event task·flushable ACL 적용성의 fail-closed 경계를 검사합니다. */
void testNegativeBoundaries()
{
    assert(BLEDevice.begin("m32-w05-negative"));
    assert(!BLENordic.setChannelSurvey(true, 2999U));
    assert(BLEDevice.lastError() == BLEError::invalid_argument);
    assert(!BLENordic.setScannerEventTrigger(0x1001U));
    assert(BLEDevice.lastError() == BLEError::invalid_argument);
    assert(BLENordic.setScannerEventTrigger(0x1000U));
    assert(last_event_trigger.handle_type ==
           SDC_HCI_VS_SET_EVENT_START_TASK_HANDLE_TYPE_SCAN);
    assert(last_event_trigger.task_address == 0x1000U);
    assert(BLENordic.setScannerEventTrigger(0U));
    const BLEFlushableAclSupport support = BLENordic.flushableAclSupport();
    assert(support.controller_experimental);
    assert(!support.host_transmit_path);
    assert(!support.usable);
    assert(!BLENordic.setRadioNotification(true));
    assert(BLEDevice.lastError() == BLEError::unsupported);
    BLEDevice.end();
}

int main(int argc, char **argv)
{
    assert(argc == 2);
    if (std::strcmp(argv[1], "llpm") == 0)
    {
        testLlpm();
    }
    else if (std::strcmp(argv[1], "reports") == 0)
    {
        testReports();
    }
    else if (std::strcmp(argv[1], "negative") == 0)
    {
        testNegativeBoundaries();
    }
    else
    {
        assert(false);
    }
    std::cout << "M32_W05_HOST_PASS=" << argv[1] << '\n';
}
