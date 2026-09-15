/**
 * @file main.cpp
 * @brief 기본 SDC image의 ISO·DF·CS HCI bit와 Host 구성만 분리 보고합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <Arduino.h>

#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/hci.h>
#include <zephyr/bluetooth/hci_types.h>
#include <zephyr/net_buf.h>
#include <zephyr/sys/util.h>

#include <errno.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

#ifndef M31_CORE_REVISION
#error "M31_CORE_REVISION is required"
#endif
#ifndef M31_BOARD_REVISION
#error "M31_BOARD_REVISION is required"
#endif
#ifndef M31_NCS_REVISION
#error "M31_NCS_REVISION is required"
#endif
#ifndef M31_ZEPHYR_REVISION
#error "M31_ZEPHYR_REVISION is required"
#endif
#ifndef M31_CONTROLLER_VARIANT
#error "M31_CONTROLLER_VARIANT is required"
#endif

static_assert(CONFIG_BT_MAX_CONN == 2);
#ifndef CONFIG_BT_LL_SW_SPLIT
static_assert(CONFIG_BT_CTLR_SDC_PERIPHERAL_COUNT == 1);
#endif

namespace
{

    constexpr char probe_command[] = "M31CAP|1|PROBE";
    constexpr char start_prefix[] = "M31CAP|1|START|nonce=";
    constexpr size_t nonce_length = 32U;
    constexpr size_t command_capacity = sizeof(start_prefix) + nonce_length;

    char command[command_capacity] = {};
    char nonce[nonce_length + 1U] = {};
    size_t command_length = 0U;
    bool protocol_ready = false;
    bool protocol_finished = false;

    /** @brief 실행 중 첫 오류를 한 번만 출력하고 뒤의 결과 출력을 막습니다. */
    void fail(const char *stage, int code)
    {
        if (protocol_finished)
        {
            return;
        }
        Serial.print("M31CAP|1|FAIL|stage=");
        Serial.print(stage);
        Serial.print("|code=");
        Serial.println(code);
        protocol_finished = true;
    }

    /** @brief HCI 응답의 길이·상태·소유권을 확인합니다. */
    bool readFeatures(bt_hci_rp_le_read_local_features &output)
    {
        struct net_buf *response = nullptr;
        const int result = bt_hci_cmd_send_sync(BT_HCI_OP_LE_READ_LOCAL_FEATURES,
                                                nullptr, &response);
        if (result != 0)
        {
            fail("le_features", result);
            return false;
        }
        if (response == nullptr || response->len != sizeof(output))
        {
            if (response != nullptr)
            {
                net_buf_unref(response);
            }
            fail("le_features_size", -EMSGSIZE);
            return false;
        }
        memcpy(&output, response->data, sizeof(output));
        net_buf_unref(response);
        if (output.status != 0U)
        {
            fail("le_features_status", output.status);
            return false;
        }
        return true;
    }

    /** @brief LE feature bit를 첫 8 byte의 정확한 위치에서 읽습니다. */
    bool hasFeature(const uint8_t *features, size_t length, size_t bit)
    {
        if (bit / 8U >= length)
        {
            return false;
        }
        return (features[bit / 8U] & BIT(bit % 8U)) != 0U;
    }

    /** @brief raw HCI byte를 소문자 hex로 출력해 parser에서 재계산합니다. */
    void printHex(const uint8_t *data, size_t length)
    {
        constexpr char digits[] = "0123456789abcdef";
        for (size_t index = 0U; index < length; ++index)
        {
            Serial.print(digits[data[index] >> 4U]);
            Serial.print(digits[data[index] & 0x0fU]);
        }
    }

    /** @brief controller bit와 Host Kconfig를 실행 PASS와 혼동하지 않고 기록합니다. */
    void printCapability(const char *identifier, bool controller_bit, bool host_config)
    {
        Serial.print("M31CAP|1|CAP|nonce=");
        Serial.print(nonce);
        Serial.print("|id=");
        Serial.print(identifier);
        Serial.print("|controller_bit=");
        Serial.print(controller_bit ? 1 : 0);
        Serial.print("|host_config=");
        Serial.println(host_config ? 1 : 0);
    }

    /** @brief 고정 순서의 7개 기능을 source/build/runtime과 별도 출력합니다. */
    void printSnapshot(const bt_hci_rp_le_read_local_features &response)
    {
        const uint8_t *features = response.features;
        const size_t length = sizeof(response.features);

        Serial.print("M31CAP|1|IDENTITY|nonce=");
        Serial.print(nonce);
        Serial.print("|core=");
        Serial.print(M31_CORE_REVISION);
        Serial.print("|board=");
        Serial.print(M31_BOARD_REVISION);
        Serial.print("|ncs=");
        Serial.print(M31_NCS_REVISION);
        Serial.print("|zephyr=");
        Serial.print(M31_ZEPHYR_REVISION);
        Serial.print("|controller=");
        Serial.println(M31_CONTROLLER_VARIANT);

        Serial.print("M31CAP|1|LE_FEATURES|nonce=");
        Serial.print(nonce);
        Serial.print("|features=");
        printHex(features, length);
        Serial.println();

        printCapability("cis_central", hasFeature(features, length, BT_LE_FEAT_BIT_CIS_CENTRAL),
                        IS_ENABLED(CONFIG_BT_ISO_CENTRAL));
        printCapability("cis_peripheral", hasFeature(features, length, BT_LE_FEAT_BIT_CIS_PERIPHERAL),
                        IS_ENABLED(CONFIG_BT_ISO_PERIPHERAL));
        printCapability("bis_broadcaster", hasFeature(features, length, BT_LE_FEAT_BIT_ISO_BROADCASTER),
                        IS_ENABLED(CONFIG_BT_ISO_BROADCASTER));
        printCapability("bis_receiver", hasFeature(features, length, BT_LE_FEAT_BIT_SYNC_RECEIVER),
                        IS_ENABLED(CONFIG_BT_ISO_SYNC_RECEIVER));
        printCapability("cte_tx", hasFeature(features, length, BT_LE_FEAT_BIT_CONNECTIONLESS_CTE_TX),
                        IS_ENABLED(CONFIG_BT_DF_CONNECTIONLESS_CTE_TX));
        printCapability("raw_iq_rx",
                        hasFeature(features, length, BT_LE_FEAT_BIT_CONNECTIONLESS_CTE_RX),
                        IS_ENABLED(CONFIG_BT_DF_CONNECTIONLESS_CTE_RX));
        printCapability("channel_sounding",
                        hasFeature(features, length, BT_LE_FEAT_BIT_CHANNEL_SOUNDING),
                        IS_ENABLED(CONFIG_BT_CHANNEL_SOUNDING));

        Serial.print("M31CAP|1|END|records=10|capabilities=7|nonce=");
        Serial.println(nonce);
    }

    /** @brief 32자 hex nonce를 확인하고 HCI를 한 번만 조회합니다. */
    void startProtocol()
    {
        const size_t prefix_length = strlen(start_prefix);
        if (command_length != prefix_length + nonce_length ||
            memcmp(command, start_prefix, prefix_length) != 0)
        {
            fail("start_command", -EINVAL);
            return;
        }
        for (size_t index = 0U; index < nonce_length; ++index)
        {
            const char value = command[prefix_length + index];
            if (!((value >= '0' && value <= '9') || (value >= 'a' && value <= 'f')))
            {
                fail("nonce", -EINVAL);
                return;
            }
        }
        memcpy(nonce, command + prefix_length, nonce_length);
        nonce[nonce_length] = '\0';
        Serial.print("M31CAP|1|BEGIN|nonce=");
        Serial.print(nonce);
        Serial.print("|controller=");
        Serial.println(M31_CONTROLLER_VARIANT);

        bt_hci_rp_le_read_local_features response = {};
        if (!readFeatures(response))
        {
            return;
        }
        printSnapshot(response);
        protocol_finished = true;
    }

    /** @brief UART 명령을 bounded buffer에 모으고 정확한 PROBE/START만 허용합니다. */
    void pollCommand()
    {
        while (Serial.available() > 0 && !protocol_finished)
        {
            const int incoming = Serial.read();
            if (incoming < 0)
            {
                return;
            }
            const char value = static_cast<char>(incoming);
            if (value == '\r')
            {
                continue;
            }
            if (value == '\n')
            {
                command[command_length] = '\0';
                if (protocol_ready)
                {
                    startProtocol();
                }
                else if (command_length == strlen(probe_command) &&
                         memcmp(command, probe_command, command_length) == 0)
                {
                    Serial.println("M31CAP|1|READY");
                    protocol_ready = true;
                }
                else
                {
                    fail("probe_command", -EINVAL);
                }
                command_length = 0U;
                return;
            }
            if (command_length + 1U >= sizeof(command))
            {
                fail("command_length", -EMSGSIZE);
                return;
            }
            command[command_length++] = value;
        }
    }

} // namespace

/** @brief Bluetooth Host를 초기화하고 명시적 capability 명령을 기다립니다. */
void setup()
{
    Serial.begin(115200);
    delay(20);
    const int result = bt_enable(nullptr);
    if (result != 0)
    {
        fail("bt_enable", result);
    }
}

/** @brief 한 번 종료된 capability image는 추가 HCI 실행을 하지 않습니다. */
void loop()
{
    if (!protocol_finished)
    {
        pollCommand();
    }
    delay(1);
}
