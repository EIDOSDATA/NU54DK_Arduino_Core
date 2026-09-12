/**
 * @file main.cpp
 * @brief M28 controller HCI와 host 구성을 고정 프로토콜로 보고합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <Arduino.h>

#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/hci.h>
#include <zephyr/bluetooth/hci_types.h>
#include <zephyr/net_buf.h>
#include <zephyr/sys/byteorder.h>
#include <zephyr/sys/util.h>

#include <errno.h>
#include <cstddef>
#include <cstdint>
#include <string.h>

#ifndef M28_CORE_REVISION
#error "M28_CORE_REVISION is required"
#endif
#ifndef M28_BOARD_REVISION
#error "M28_BOARD_REVISION is required"
#endif
#ifndef M28_NCS_REVISION
#error "M28_NCS_REVISION is required"
#endif
#ifndef M28_ZEPHYR_REVISION
#error "M28_ZEPHYR_REVISION is required"
#endif

/** @brief Host capability profile이 약화되면 target build에서 즉시 거부합니다. */
static_assert(CONFIG_BT_MAX_CONN == 2);
static_assert(CONFIG_BT_CTLR_SDC_PERIPHERAL_COUNT == 1);
static_assert(IS_ENABLED(CONFIG_BT_EXT_ADV));
static_assert(CONFIG_BT_CTLR_ADV_DATA_LEN_MAX >= 255);
static_assert(IS_ENABLED(CONFIG_BT_PER_ADV));
static_assert(IS_ENABLED(CONFIG_BT_PER_ADV_SYNC));
static_assert(CONFIG_BT_CTLR_SYNC_PERIODIC_ADV_LIST_SIZE >= 1);
static_assert(IS_ENABLED(CONFIG_BT_PER_ADV_SYNC_TRANSFER_SENDER));
static_assert(IS_ENABLED(CONFIG_BT_PER_ADV_SYNC_TRANSFER_RECEIVER));
static_assert(IS_ENABLED(CONFIG_BT_PER_ADV_RSP));
static_assert(IS_ENABLED(CONFIG_BT_PER_ADV_SYNC_RSP));
static_assert(IS_ENABLED(CONFIG_BT_CTLR_SDC_PAWR_ADV));
static_assert(IS_ENABLED(CONFIG_BT_CTLR_SDC_PAWR_SYNC));
static_assert(IS_ENABLED(CONFIG_BT_PRIVACY));
static_assert(IS_ENABLED(CONFIG_BT_SETTINGS));
static_assert(IS_ENABLED(CONFIG_BT_DATA_LEN_UPDATE));
static_assert(IS_ENABLED(CONFIG_BT_REMOTE_INFO));
static_assert(IS_ENABLED(CONFIG_BT_USER_PHY_UPDATE));
static_assert(!IS_ENABLED(CONFIG_NCS_BOOT_BANNER));

namespace
{

    constexpr char probe_command[] = "M28CAP|1|PROBE";
    constexpr char start_prefix[] = "M28CAP|1|START|nonce=";
    constexpr std::size_t nonce_length = 32U;
    constexpr std::size_t command_capacity = sizeof(start_prefix) + nonce_length;

    char command[command_capacity] = {};
    char nonce[nonce_length + 1U] = {};
    std::size_t command_length = 0U;
    bool protocol_ready = false;
    bool protocol_finished = false;

    struct CapabilitySnapshot
    {
        bt_hci_rp_read_local_version_info version = {};
        bt_hci_rp_read_supported_commands commands = {};
        bt_hci_rp_le_read_local_features features = {};
        bt_hci_rp_le_read_max_adv_data_len maximum_advertising_data = {};
        bt_hci_rp_le_read_rl_size resolving_list = {};
        std::uint8_t advertising_sets = 0U;
        std::uint8_t periodic_advertiser_list = 0U;
    };

    /** @brief 정해진 stage와 오류 코드를 한 번 출력하고 실행을 닫습니다. */
    void fail(const char *stage, int code)
    {
        if (protocol_finished)
        {
            return;
        }
        Serial.print("M28CAP|1|FAIL|stage=");
        Serial.print(stage);
        Serial.print("|code=");
        Serial.println(code);
        protocol_finished = true;
    }

    /** @brief byte 배열을 소문자 고정 폭 hex로 출력합니다. */
    void printHex(const std::uint8_t *data, std::size_t length)
    {
        constexpr char digits[] = "0123456789abcdef";
        for (std::size_t index = 0U; index < length; ++index)
        {
            Serial.print(digits[data[index] >> 4U]);
            Serial.print(digits[data[index] & 0x0fU]);
        }
    }

    /** @brief HCI command 응답 크기와 status를 확인한 뒤 고정 구조체에 복사합니다. */
    template <typename Response>
    bool readHci(std::uint16_t opcode, const char *stage, Response &output)
    {
        struct net_buf *response = nullptr;
        const int result = bt_hci_cmd_send_sync(opcode, nullptr, &response);
        if (result != 0)
        {
            fail(stage, result);
            return false;
        }
        if (response == nullptr || response->len != sizeof(Response))
        {
            if (response != nullptr)
            {
                net_buf_unref(response);
            }
            fail(stage, -EMSGSIZE);
            return false;
        }
        memcpy(&output, response->data, sizeof(output));
        net_buf_unref(response);
        if (output.status != 0U)
        {
            fail(stage, static_cast<int>(output.status));
            return false;
        }
        return true;
    }

    /** @brief Read Supported Commands의 한 bit를 검사합니다. */
    bool commandSupported(const std::uint8_t *commands, std::size_t octet, std::uint8_t bit)
    {
        return (commands[octet] & BIT(bit)) != 0U;
    }

    /** @brief 지정한 command bit가 모두 있는지 검사합니다. */
    bool commandsSupported(const std::uint8_t *commands, const std::uint8_t (*requirements)[2],
                           std::size_t count)
    {
        for (std::size_t index = 0U; index < count; ++index)
        {
            if (!commandSupported(commands, requirements[index][0], requirements[index][1]))
            {
                return false;
            }
        }
        return true;
    }

    /** @brief LE Local Supported Features의 한 bit를 검사합니다. */
    bool featureSupported(const std::uint8_t *features, std::uint8_t bit)
    {
        return (features[bit >> 3U] & BIT(bit & 0x07U)) != 0U;
    }

    /** @brief Host API를 통해 controller advertising set 한 개의 생성과 회수를 확인합니다. */
    bool probeAdvertisingSet(CapabilitySnapshot &snapshot)
    {
        const bt_le_adv_param parameters = BT_LE_ADV_PARAM_INIT(
            BT_LE_ADV_OPT_EXT_ADV, BT_GAP_ADV_FAST_INT_MIN_2, BT_GAP_ADV_FAST_INT_MAX_2, nullptr);
        bt_le_ext_adv *advertising = nullptr;
        int result = bt_le_ext_adv_create(&parameters, nullptr, &advertising);
        if (result != 0)
        {
            fail("adv_set_create", result);
            return false;
        }
        snapshot.advertising_sets = 1U;
        result = bt_le_ext_adv_delete(advertising);
        if (result != 0)
        {
            fail("adv_set_delete", result);
            return false;
        }
        return true;
    }

    /** @brief Host API로 controller periodic advertiser list 한 slot을 왕복 확인합니다. */
    bool probePeriodicAdvertiserList(CapabilitySnapshot &snapshot)
    {
        bt_addr_le_t address = {};
        address.type = BT_ADDR_LE_RANDOM;
        address.a.val[5] = 0xc0U;
        int result = bt_le_per_adv_list_add(&address, 0U);
        if (result != 0)
        {
            fail("per_adv_list_add", result);
            return false;
        }
        snapshot.periodic_advertiser_list = 1U;
        result = bt_le_per_adv_list_remove(&address, 0U);
        if (result != 0)
        {
            fail("per_adv_list_remove", result);
            return false;
        }
        return true;
    }

    /** @brief 고정 capability 판정 한 줄을 출력합니다. */
    void printCapability(const char *identifier, bool host, bool controller, const char *evidence)
    {
        Serial.print("M28CAP|1|CAP|nonce=");
        Serial.print(nonce);
        Serial.print("|id=");
        Serial.print(identifier);
        Serial.print("|host=");
        Serial.print(host ? "pass" : "fail");
        Serial.print("|controller=");
        Serial.print(controller ? "pass" : "fail");
        Serial.print("|evidence=");
        Serial.println(evidence);
    }

    /** @brief Host Kconfig와 실제 HCI 응답을 고정 순서로 출력합니다. */
    void printSnapshot(const CapabilitySnapshot &snapshot)
    {
        const std::uint8_t multi_role_commands[][2] = {{26U, 4U}, {36U, 2U}};
        const std::uint8_t extended_commands[][2] = {
            {36U, 1U}, {36U, 2U}, {36U, 3U}, {36U, 4U}, {36U, 5U}, {36U, 6U},
            {36U, 7U}, {37U, 0U}, {37U, 1U}, {37U, 5U}, {37U, 6U},
        };
        const std::uint8_t periodic_commands[][2] = {
            {37U, 2U}, {37U, 3U}, {37U, 4U}, {38U, 0U}, {38U, 1U}, {38U, 2U}, {38U, 3U},
            {38U, 4U}, {38U, 5U}, {38U, 6U}, {40U, 6U}, {40U, 7U}, {41U, 0U}, {41U, 1U},
        };
        const std::uint8_t privacy_commands[][2] = {
            {34U, 3U}, {34U, 4U}, {34U, 5U}, {34U, 6U}, {34U, 7U},
            {35U, 0U}, {35U, 1U}, {35U, 2U}, {39U, 2U},
        };
        const std::uint8_t link_control_commands[][2] = {
            {0U, 5U}, {27U, 2U}, {27U, 5U}, {33U, 6U}, {35U, 3U}, {35U, 4U}, {35U, 6U},
        };

        const bool multi_role_host =
            CONFIG_BT_MAX_CONN == 2 && CONFIG_BT_CTLR_SDC_PERIPHERAL_COUNT == 1;
        const bool extended_host = IS_ENABLED(CONFIG_BT_EXT_ADV);
        const bool periodic_host = IS_ENABLED(CONFIG_BT_PER_ADV) &&
                                   IS_ENABLED(CONFIG_BT_PER_ADV_SYNC) &&
                                   IS_ENABLED(CONFIG_BT_PER_ADV_SYNC_TRANSFER_SENDER) &&
                                   IS_ENABLED(CONFIG_BT_PER_ADV_SYNC_TRANSFER_RECEIVER);
        const bool pawr_host =
            IS_ENABLED(CONFIG_BT_PER_ADV_RSP) && IS_ENABLED(CONFIG_BT_PER_ADV_SYNC_RSP);
        const bool privacy_host = IS_ENABLED(CONFIG_BT_PRIVACY) && IS_ENABLED(CONFIG_BT_SETTINGS);
        const bool link_control_host = IS_ENABLED(CONFIG_BT_DATA_LEN_UPDATE) &&
                                       IS_ENABLED(CONFIG_BT_REMOTE_INFO) &&
                                       IS_ENABLED(CONFIG_BT_USER_PHY_UPDATE);

        const bool multi_role_controller = commandsSupported(
            snapshot.commands.commands, multi_role_commands, ARRAY_SIZE(multi_role_commands));
        const bool extended_controller =
            featureSupported(snapshot.features.features, BT_LE_FEAT_BIT_EXT_ADV) &&
            commandsSupported(snapshot.commands.commands, extended_commands,
                              ARRAY_SIZE(extended_commands)) &&
            sys_le16_to_cpu(snapshot.maximum_advertising_data.max_adv_data_len) >= 255U &&
            snapshot.advertising_sets >= 1U;
        const bool periodic_controller =
            featureSupported(snapshot.features.features, BT_LE_FEAT_BIT_PER_ADV) &&
            featureSupported(snapshot.features.features, BT_LE_FEAT_BIT_PAST_SEND) &&
            featureSupported(snapshot.features.features, BT_LE_FEAT_BIT_PAST_RECV) &&
            commandsSupported(snapshot.commands.commands, periodic_commands,
                              ARRAY_SIZE(periodic_commands)) &&
            snapshot.periodic_advertiser_list >= 1U;
        const bool pawr_controller =
            featureSupported(snapshot.features.features, BT_LE_FEAT_BIT_PAWR_ADVERTISER) &&
            featureSupported(snapshot.features.features, BT_LE_FEAT_BIT_PAWR_SCANNER);
        const bool privacy_controller =
            featureSupported(snapshot.features.features, BT_LE_FEAT_BIT_PRIVACY) &&
            commandsSupported(snapshot.commands.commands, privacy_commands,
                              ARRAY_SIZE(privacy_commands)) &&
            snapshot.resolving_list.rl_size >= 1U;
        const bool link_control_controller =
            featureSupported(snapshot.features.features, BT_LE_FEAT_BIT_DLE) &&
            commandsSupported(snapshot.commands.commands, link_control_commands,
                              ARRAY_SIZE(link_control_commands));

        Serial.print("M28CAP|1|IDENTITY|nonce=");
        Serial.print(nonce);
        Serial.print("|core=");
        Serial.print(M28_CORE_REVISION);
        Serial.print("|board=");
        Serial.print(M28_BOARD_REVISION);
        Serial.print("|ncs=");
        Serial.print(M28_NCS_REVISION);
        Serial.print("|zephyr=");
        Serial.println(M28_ZEPHYR_REVISION);

        Serial.print("M28CAP|1|HOST|nonce=");
        Serial.print(nonce);
        Serial.print("|bt_max_conn=");
        Serial.print(CONFIG_BT_MAX_CONN);
        Serial.print("|peripheral_count=");
        Serial.print(CONFIG_BT_CTLR_SDC_PERIPHERAL_COUNT);
        Serial.print("|central_count=");
        Serial.print(CONFIG_BT_MAX_CONN - CONFIG_BT_CTLR_SDC_PERIPHERAL_COUNT);
        Serial.print("|ext_adv=");
        Serial.print(IS_ENABLED(CONFIG_BT_EXT_ADV));
        Serial.print("|per_adv=");
        Serial.print(IS_ENABLED(CONFIG_BT_PER_ADV));
        Serial.print("|per_adv_sync=");
        Serial.print(IS_ENABLED(CONFIG_BT_PER_ADV_SYNC));
        Serial.print("|past_sender=");
        Serial.print(IS_ENABLED(CONFIG_BT_PER_ADV_SYNC_TRANSFER_SENDER));
        Serial.print("|past_receiver=");
        Serial.print(IS_ENABLED(CONFIG_BT_PER_ADV_SYNC_TRANSFER_RECEIVER));
        Serial.print("|pawr_adv=");
        Serial.print(IS_ENABLED(CONFIG_BT_PER_ADV_RSP));
        Serial.print("|pawr_sync=");
        Serial.print(IS_ENABLED(CONFIG_BT_PER_ADV_SYNC_RSP));
        Serial.print("|privacy=");
        Serial.print(IS_ENABLED(CONFIG_BT_PRIVACY));
        Serial.print("|settings=");
        Serial.print(IS_ENABLED(CONFIG_BT_SETTINGS));
        Serial.print("|data_len_update=");
        Serial.print(IS_ENABLED(CONFIG_BT_DATA_LEN_UPDATE));
        Serial.print("|remote_info=");
        Serial.print(IS_ENABLED(CONFIG_BT_REMOTE_INFO));
        Serial.print("|user_phy_update=");
        Serial.println(IS_ENABLED(CONFIG_BT_USER_PHY_UPDATE));

        Serial.print("M28CAP|1|HCI_VERSION|nonce=");
        Serial.print(nonce);
        Serial.print("|hci_version=");
        Serial.print(snapshot.version.hci_version);
        Serial.print("|hci_revision=");
        Serial.print(sys_le16_to_cpu(snapshot.version.hci_revision));
        Serial.print("|manufacturer=");
        Serial.print(sys_le16_to_cpu(snapshot.version.manufacturer));
        Serial.print("|lmp_subversion=");
        Serial.println(sys_le16_to_cpu(snapshot.version.lmp_subversion));

        Serial.print("M28CAP|1|HCI_COMMANDS|nonce=");
        Serial.print(nonce);
        Serial.print("|commands=");
        printHex(snapshot.commands.commands, sizeof(snapshot.commands.commands));
        Serial.println();

        Serial.print("M28CAP|1|LE_FEATURES|nonce=");
        Serial.print(nonce);
        Serial.print("|features=");
        printHex(snapshot.features.features, sizeof(snapshot.features.features));
        Serial.println();

        Serial.print("M28CAP|1|RESOURCES|nonce=");
        Serial.print(nonce);
        Serial.print("|max_adv_data_len=");
        Serial.print(sys_le16_to_cpu(snapshot.maximum_advertising_data.max_adv_data_len));
        Serial.print("|adv_sets=");
        Serial.print(snapshot.advertising_sets);
        Serial.print("|per_adv_list=");
        Serial.print(snapshot.periodic_advertiser_list);
        Serial.print("|resolving_list=");
        Serial.println(snapshot.resolving_list.rl_size);

        printCapability("multi_role_multi_link", multi_role_host, multi_role_controller,
                        "config+commands");
        printCapability("extended_advertising_scanning", extended_host, extended_controller,
                        "le_feature+commands+resource");
        printCapability("periodic_advertising_sync_past", periodic_host, periodic_controller,
                        "le_feature+commands+resource");
        printCapability("pawr_advertiser_scanner", pawr_host, pawr_controller, "le_feature");
        printCapability("privacy_rpa", privacy_host, privacy_controller,
                        "le_feature+commands+resource");
        printCapability("per_link_control", link_control_host, link_control_controller,
                        "le_feature+commands");

        Serial.print("M28CAP|1|END|records=12|capabilities=6|nonce=");
        Serial.println(nonce);
    }

    /** @brief 모든 필수 HCI command를 한 번씩 실행합니다. */
    bool readSnapshot(CapabilitySnapshot &snapshot)
    {
        return readHci(BT_HCI_OP_READ_LOCAL_VERSION_INFO, "hci_version", snapshot.version) &&
               readHci(BT_HCI_OP_READ_SUPPORTED_COMMANDS, "hci_commands", snapshot.commands) &&
               readHci(BT_HCI_OP_LE_READ_LOCAL_FEATURES, "le_features", snapshot.features) &&
               readHci(BT_HCI_OP_LE_READ_MAX_ADV_DATA_LEN, "max_adv_data_len",
                       snapshot.maximum_advertising_data) &&
               readHci(BT_HCI_OP_LE_READ_RL_SIZE, "resolving_list", snapshot.resolving_list) &&
               probeAdvertisingSet(snapshot) && probePeriodicAdvertiserList(snapshot);
    }

    /** @brief flash reset 잡음 뒤 exact PROBE command에 READY로 응답합니다. */
    void probeProtocol()
    {
        if (command_length != strlen(probe_command) ||
            memcmp(command, probe_command, strlen(probe_command)) != 0)
        {
            fail("probe_command", -EINVAL);
            return;
        }
        Serial.println("M28CAP|1|READY");
        protocol_ready = true;
        command_length = 0U;
    }

    /** @brief exact nonce command를 검증하고 capability 수집을 한 번 수행합니다. */
    void startProtocol()
    {
        const std::size_t prefix_length = strlen(start_prefix);
        if (command_length != prefix_length + nonce_length ||
            memcmp(command, start_prefix, prefix_length) != 0)
        {
            fail("start_command", -EINVAL);
            return;
        }
        for (std::size_t index = 0U; index < nonce_length; ++index)
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
        Serial.print("M28CAP|1|BEGIN|nonce=");
        Serial.println(nonce);

        CapabilitySnapshot snapshot;
        if (!readSnapshot(snapshot))
        {
            return;
        }
        printSnapshot(snapshot);
        protocol_finished = true;
    }

    /** @brief bounded UART command를 수집하고 CRLF/LF 하나만 허용합니다. */
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
                else
                {
                    probeProtocol();
                }
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

/** @brief Bluetooth controller를 초기화하고 Host의 PROBE를 기다립니다. */
void setup()
{
    Serial.begin(115200);
    delay(20);
    const int result = bt_enable(nullptr);
    if (result != 0)
    {
        fail("bt_enable", result);
        return;
    }
}

/** @brief Host의 exact START command가 올 때까지만 UART를 확인합니다. */
void loop()
{
    if (!protocol_finished)
    {
        pollCommand();
    }
    delay(1);
}
