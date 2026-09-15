/**
 * @file main.cpp
 * @brief Zephyr LL 기본 안테나 IQ 수신 후보의 Kconfig와 API를 분리 판정합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <Arduino.h>
#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/direction.h>
#include <zephyr/bluetooth/hci.h>
#include <zephyr/bluetooth/hci_types.h>
#include <zephyr/net_buf.h>

#include <string.h>

#ifndef CONFIG_BT_LL_SW_SPLIT
#error "Zephyr split LL is not selected"
#endif

#ifndef CONFIG_BT_CTLR_DF_CTE_RX
#error "Controller CTE RX is not selected"
#endif

#ifndef CONFIG_BT_CTLR_DF_SCAN_CTE_RX
#error "Controller connectionless CTE RX is not selected"
#endif

#ifndef CONFIG_BT_DF_CONNECTIONLESS_CTE_RX
#error "Host connectionless CTE RX is not selected"
#endif

namespace
{
    constexpr char probe_command[] = "M31DFIQ|1|PROBE";
    char command[sizeof(probe_command)] = {};
    size_t command_length = 0U;
    bool queried = false;

    /** @brief HCI feature와 안테나 수를 실제 controller에서 읽습니다. */
    void printCandidate()
    {
        Serial.println("M31DFIQ|1|CONFIG|controller=zephyr_ll|cte_rx=1|scan_cte_rx=1|antenna_switch_rx=0");
        const int enabled = bt_enable(nullptr);
        if (enabled != 0)
        {
            Serial.print("M31DFIQ|1|FAIL|stage=bt_enable|code=");
            Serial.println(enabled);
            return;
        }
        struct net_buf *response = nullptr;
        int result = bt_hci_cmd_send_sync(BT_HCI_OP_LE_READ_LOCAL_FEATURES,
                                          nullptr, &response);
        if (result != 0 || response == nullptr ||
            response->len != sizeof(bt_hci_rp_le_read_local_features))
        {
            if (response != nullptr)
            {
                net_buf_unref(response);
            }
            Serial.print("M31DFIQ|1|FAIL|stage=read_features|code=");
            Serial.println(result);
            return;
        }
        bt_hci_rp_le_read_local_features features = {};
        memcpy(&features, response->data, sizeof(features));
        net_buf_unref(response);
        if (features.status != 0U)
        {
            Serial.print("M31DFIQ|1|FAIL|stage=feature_status|code=");
            Serial.println(features.status);
            return;
        }
        response = nullptr;
        result = bt_hci_cmd_send_sync(BT_HCI_OP_LE_READ_ANT_INFO,
                                      nullptr, &response);
        if (result != 0 || response == nullptr ||
            response->len != sizeof(bt_hci_rp_le_read_ant_info))
        {
            if (response != nullptr)
            {
                net_buf_unref(response);
            }
            Serial.print("M31DFIQ|1|FAIL|stage=read_antenna|code=");
            Serial.println(result);
            return;
        }
        bt_hci_rp_le_read_ant_info antenna = {};
        memcpy(&antenna, response->data, sizeof(antenna));
        net_buf_unref(response);
        if (antenna.status != 0U)
        {
            Serial.print("M31DFIQ|1|FAIL|stage=antenna_status|code=");
            Serial.println(antenna.status);
            return;
        }
        constexpr char digits[] = "0123456789abcdef";
        Serial.print("M31DFIQ|1|HCI|features=");
        for (uint8_t value : features.features)
        {
            Serial.print(digits[value >> 4U]);
            Serial.print(digits[value & 0x0fU]);
        }
        Serial.print("|antenna_count=");
        Serial.print(antenna.num_ant);
        Serial.print("|sample_rates=");
        Serial.print(antenna.switch_sample_rates);
        Serial.print("|max_pattern=");
        Serial.println(antenna.max_switch_pattern_len);
    }
}

void setup()
{
    Serial.begin(115200);
    Serial.println("M31DFIQ|1|READY");
}

void loop()
{
    while (Serial.available() > 0)
    {
        const char next = static_cast<char>(Serial.read());
        if (next == '\r')
        {
            continue;
        }
        if (next == '\n')
        {
            if (!queried && strcmp(command, probe_command) == 0)
            {
                queried = true;
                printCandidate();
            }
            command_length = 0U;
            command[0] = '\0';
            continue;
        }
        if (command_length + 1U >= sizeof(command))
        {
            command_length = 0U;
            command[0] = '\0';
            continue;
        }
        command[command_length++] = next;
        command[command_length] = '\0';
    }
}
