/** @file @brief M32-W05 Nordic SDC vendor HCI 형식의 Host 시험 대역입니다. */
#pragma once

#include <cstdint>

#define SDC_HCI_SUBEVENT_VS_QOS_CONN_EVENT_REPORT 0x80U
#define SDC_HCI_SUBEVENT_VS_QOS_CHANNEL_SURVEY_REPORT 0x81U
#define SDC_HCI_SUBEVENT_VS_CONN_ANCHOR_POINT_UPDATE_REPORT 0x82U

#define SDC_HCI_VS_SET_EVENT_START_TASK_HANDLE_TYPE_SCAN 0x01U
#define SDC_HCI_VS_SET_EVENT_START_TASK_HANDLE_TYPE_INITIATOR 0x02U
#define SDC_HCI_VS_SET_EVENT_START_TASK_HANDLE_TYPE_CONN 0x03U
#define SDC_HCI_VS_SET_EVENT_START_TASK_HANDLE_TYPE_ADV 0x04U

struct sdc_hci_subevent_vs_qos_conn_event_report_t
{
    std::uint16_t conn_handle;
    std::uint16_t event_counter;
    std::uint8_t channel_index;
    std::uint16_t crc_ok_count;
    std::uint16_t crc_error_count;
    std::uint16_t nak_count;
    std::uint8_t rx_timeout;
};

struct sdc_hci_subevent_vs_qos_channel_survey_report_t
{
    std::int8_t channel_energy[40];
};

struct sdc_hci_subevent_vs_conn_anchor_point_update_report_t
{
    std::uint16_t conn_handle;
    std::uint16_t event_counter;
    std::uint64_t anchor_point_us;
};

struct sdc_hci_cmd_vs_llpm_mode_set_t
{
    std::uint8_t enable;
};

struct sdc_hci_cmd_vs_conn_update_t
{
    std::uint16_t conn_handle;
    std::uint32_t conn_interval_us;
    std::uint16_t conn_latency;
    std::uint16_t supervision_timeout;
};

struct sdc_hci_cmd_vs_qos_conn_event_report_enable_t
{
    std::uint8_t enable;
};

struct sdc_hci_cmd_vs_qos_channel_survey_enable_t
{
    std::uint8_t enable;
    std::uint32_t interval_us;
};

struct sdc_hci_cmd_vs_set_event_start_task_t
{
    std::uint8_t handle_type;
    std::uint16_t handle;
    std::uint32_t task_address;
};

struct sdc_hci_cmd_vs_conn_anchor_point_update_event_report_enable_t
{
    std::uint8_t enable;
};
