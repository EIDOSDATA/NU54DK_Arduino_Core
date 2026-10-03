/**
 * @file main.cpp
 * @brief 제품 SDC의 modern LE feature page와 compile-time 자원을 분리 보고합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <Arduino.h>

#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/buf.h>
#include <zephyr/bluetooth/hci.h>
#include <zephyr/bluetooth/hci_types.h>
#include <zephyr/net_buf.h>
#include <zephyr/sys/util.h>

#include <errno.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

#ifndef M32_CORE_REVISION
#error "M32_CORE_REVISION is required"
#endif
#ifndef M32_BOARD_REVISION
#error "M32_BOARD_REVISION is required"
#endif
#ifndef M32_NCS_REVISION
#error "M32_NCS_REVISION is required"
#endif
#ifndef M32_ZEPHYR_REVISION
#error "M32_ZEPHYR_REVISION is required"
#endif
#ifndef M32_RESOURCE_PROFILE
#error "M32_RESOURCE_PROFILE is required"
#endif

#ifndef CONFIG_BT_EXT_ADV_MAX_ADV_SET
#define CONFIG_BT_EXT_ADV_MAX_ADV_SET 0
#endif
#ifndef CONFIG_BT_ID_MAX
#define CONFIG_BT_ID_MAX 0
#endif
#ifndef CONFIG_BT_PER_ADV_SYNC_MAX
#define CONFIG_BT_PER_ADV_SYNC_MAX 0
#endif
#ifndef CONFIG_BT_BUF_ACL_TX_COUNT
#define CONFIG_BT_BUF_ACL_TX_COUNT 0
#endif
static_assert(CONFIG_BT_MAX_CONN == 2);
static_assert(CONFIG_BT_CTLR_SDC_PERIPHERAL_COUNT == 1);

namespace
{

    constexpr char probe_command[] = "M32CAP|1|PROBE";
    constexpr char start_prefix[] = "M32CAP|1|START|nonce=";
    constexpr size_t nonce_length = 32U;
    constexpr size_t command_capacity = sizeof(start_prefix) + nonce_length;
    constexpr size_t extended_feature_octets = 16U;

    struct FeatureSnapshot
    {
        uint8_t bytes[extended_feature_octets];
        size_t length;
        uint8_t max_page;
    };

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
        Serial.print("M32CAP|1|FAIL|stage=");
        Serial.print(stage);
        Serial.print("|code=");
        Serial.println(code);
        protocol_finished = true;
    }

    /** @brief Legacy 또는 extended HCI 응답을 정해진 길이로 복사합니다. */
    bool readFeatures(FeatureSnapshot &output)
    {
        struct net_buf *response = nullptr;
        memset(&output, 0, sizeof(output));

        if (IS_ENABLED(CONFIG_BT_LE_EXTENDED_FEAT_SET))
        {
            const int result = bt_hci_cmd_send_sync(
                BT_HCI_OP_LE_READ_ALL_LOCAL_SUPPORTED_FEATURES, nullptr, &response);
            if (result != 0)
            {
                fail("all_local_features", result);
                return false;
            }
            if (response == nullptr ||
                response->len != sizeof(struct bt_hci_rp_le_read_all_local_supported_features))
            {
                if (response != nullptr)
                {
                    net_buf_unref(response);
                }
                fail("all_local_features_size", -EMSGSIZE);
                return false;
            }
            const auto *reply = reinterpret_cast<
                const struct bt_hci_rp_le_read_all_local_supported_features *>(response->data);
            if (reply->status != 0U)
            {
                const int status = reply->status;
                net_buf_unref(response);
                fail("all_local_features_status", status);
                return false;
            }
            memcpy(output.bytes, reply->features, sizeof(output.bytes));
            output.length = sizeof(output.bytes);
            output.max_page = reply->max_page;
            net_buf_unref(response);
            return true;
        }

        const int result = bt_hci_cmd_send_sync(BT_HCI_OP_LE_READ_LOCAL_FEATURES,
                                                nullptr, &response);
        if (result != 0)
        {
            fail("local_features", result);
            return false;
        }
        if (response == nullptr ||
            response->len != sizeof(struct bt_hci_rp_le_read_local_features))
        {
            if (response != nullptr)
            {
                net_buf_unref(response);
            }
            fail("local_features_size", -EMSGSIZE);
            return false;
        }
        const auto *reply = reinterpret_cast<const struct bt_hci_rp_le_read_local_features *>(
            response->data);
        if (reply->status != 0U)
        {
            const int status = reply->status;
            net_buf_unref(response);
            fail("local_features_status", status);
            return false;
        }
        memcpy(output.bytes, reply->features, sizeof(reply->features));
        output.length = sizeof(reply->features);
        output.max_page = 0U;
        net_buf_unref(response);
        return true;
    }

    /** @brief 범위를 벗어난 extended bit를 지원으로 잘못 해석하지 않습니다. */
    bool hasFeature(const FeatureSnapshot &features, size_t bit)
    {
        if (bit / 8U >= features.length)
        {
            return false;
        }
        return (features.bytes[bit / 8U] & BIT(bit % 8U)) != 0U;
    }

    /** @brief raw feature byte를 소문자 hex로 출력해 Host가 독립 재계산하게 합니다. */
    void printHex(const uint8_t *data, size_t length)
    {
        constexpr char digits[] = "0123456789abcdef";
        for (size_t index = 0U; index < length; ++index)
        {
            Serial.print(digits[data[index] >> 4U]);
            Serial.print(digits[data[index] & 0x0fU]);
        }
    }

    /** @brief controller bit와 Host Kconfig를 기능 HIL과 혼동하지 않고 출력합니다. */
    void printCapability(const char *identifier, bool controller_bit, bool host_config)
    {
        Serial.print("M32CAP|1|CAP|nonce=");
        Serial.print(nonce);
        Serial.print("|id=");
        Serial.print(identifier);
        Serial.print("|controller_bit=");
        Serial.print(controller_bit ? 1 : 0);
        Serial.print("|host_config=");
        Serial.println(host_config ? 1 : 0);
    }

    /** @brief 기능 page와 compile-time 자원 상한을 고정 순서로 출력합니다. */
    void printSnapshot(const FeatureSnapshot &features)
    {
        Serial.print("M32CAP|1|IDENTITY|nonce=");
        Serial.print(nonce);
        Serial.print("|core=");
        Serial.print(M32_CORE_REVISION);
        Serial.print("|board=");
        Serial.print(M32_BOARD_REVISION);
        Serial.print("|ncs=");
        Serial.print(M32_NCS_REVISION);
        Serial.print("|zephyr=");
        Serial.print(M32_ZEPHYR_REVISION);
        Serial.print("|controller=product_sdc|profile=");
        Serial.println(M32_RESOURCE_PROFILE);

        Serial.print("M32CAP|1|LE_FEATURES|nonce=");
        Serial.print(nonce);
        Serial.print("|max_page=");
        Serial.print(features.max_page);
        Serial.print("|octets=");
        Serial.print(features.length);
        Serial.print("|features=");
        printHex(features.bytes, features.length);
        Serial.println();

        Serial.print("M32CAP|1|RESOURCES|nonce=");
        Serial.print(nonce);
        Serial.print("|connections=");
        Serial.print(CONFIG_BT_MAX_CONN);
        Serial.print("|peripherals=");
        Serial.print(CONFIG_BT_CTLR_SDC_PERIPHERAL_COUNT);
        Serial.print("|adv_sets=");
        Serial.print(CONFIG_BT_EXT_ADV_MAX_ADV_SET);
        Serial.print("|identities=");
        Serial.print(CONFIG_BT_ID_MAX);
        Serial.print("|syncs=");
        Serial.print(CONFIG_BT_PER_ADV_SYNC_MAX);
        Serial.print("|acl_tx=");
        Serial.print(CONFIG_BT_BUF_ACL_TX_COUNT);
        Serial.print("|acl_rx=");
        Serial.println(BT_BUF_ACL_RX_COUNT);

        printCapability("sca_update", hasFeature(features, BT_LE_FEAT_BIT_SCA_UPDATE),
                        IS_ENABLED(CONFIG_BT_SCA_UPDATE));
        printCapability("power_control_request", hasFeature(features, BT_LE_FEAT_BIT_PWR_CTRL_REQ),
                        IS_ENABLED(CONFIG_BT_TRANSMIT_POWER_CONTROL));
        printCapability("power_change_indication", hasFeature(features, BT_LE_FEAT_BIT_PWR_CHG_IND),
                        IS_ENABLED(CONFIG_BT_TRANSMIT_POWER_CONTROL));
        printCapability("path_loss_monitor", hasFeature(features, BT_LE_FEAT_BIT_PATH_LOSS_MONITOR),
                        IS_ENABLED(CONFIG_BT_PATH_LOSS_MONITORING));
        printCapability("connection_subrating", hasFeature(features, BT_LE_FEAT_BIT_CONN_SUBRATING),
                        IS_ENABLED(CONFIG_BT_SUBRATING));
        printCapability("connection_subrating_host",
                        hasFeature(features, BT_LE_FEAT_BIT_CONN_SUBRATING_HOST_SUPP),
                        IS_ENABLED(CONFIG_BT_SUBRATING));
        printCapability("channel_classification",
                        hasFeature(features, BT_LE_FEAT_BIT_CHANNEL_CLASSIFICATION), true);
        printCapability("advertising_coding_selection",
                        hasFeature(features, BT_LE_FEAT_BIT_ADV_CODING_SEL),
                        IS_ENABLED(CONFIG_BT_EXT_ADV_CODING_SELECTION));
        printCapability("advertising_coding_selection_host",
                        hasFeature(features, BT_LE_FEAT_BIT_ADV_CODING_SEL_HOST),
                        IS_ENABLED(CONFIG_BT_EXT_ADV_CODING_SELECTION));
        printCapability("extended_feature_set",
                        hasFeature(features, BT_LE_FEAT_BIT_EXTENDED_FEAT_SET),
                        IS_ENABLED(CONFIG_BT_LE_EXTENDED_FEAT_SET));
        printCapability("frame_space_update",
                        hasFeature(features, BT_LE_FEAT_BIT_FRAME_SPACE_UPDATE),
                        IS_ENABLED(CONFIG_BT_FRAME_SPACE_UPDATE));
        printCapability("shorter_connection_intervals",
                        hasFeature(features, BT_LE_FEAT_BIT_SHORTER_CONN_INTERVALS),
                        IS_ENABLED(CONFIG_BT_SHORTER_CONNECTION_INTERVALS));
        printCapability("shorter_connection_intervals_host",
                        hasFeature(features, BT_LE_FEAT_BIT_SHORTER_CONN_INTERVALS_HOST_SUPP),
                        IS_ENABLED(CONFIG_BT_SHORTER_CONNECTION_INTERVALS));

        Serial.print("M32CAP|1|END|records=17|capabilities=13|nonce=");
        Serial.println(nonce);
    }

    /** @brief 32자 hex nonce를 확인한 뒤 capability snapshot을 한 번만 생성합니다. */
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
        Serial.print("M32CAP|1|BEGIN|nonce=");
        Serial.print(nonce);
        Serial.print("|controller=product_sdc|profile=");
        Serial.println(M32_RESOURCE_PROFILE);

        FeatureSnapshot features = {};
        if (!readFeatures(features))
        {
            return;
        }
        printSnapshot(features);
        protocol_finished = true;
    }

    /** @brief bounded buffer에서 정확한 PROBE와 START 명령만 허용합니다. */
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
                    Serial.println("M32CAP|1|READY");
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

/** @brief Bluetooth Host를 초기화하고 명시적인 capability 명령을 기다립니다. */
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

/** @brief 한 번 종료된 image는 추가 HCI 명령을 실행하지 않습니다. */
void loop()
{
    if (!protocol_finished)
    {
        pollCommand();
    }
    delay(1);
}
