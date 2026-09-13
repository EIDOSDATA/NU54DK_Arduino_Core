/**
 * @file main.cpp
 * @brief M29 ATT/GATT·L2CAP Host capability를 고정 프로토콜로 보고합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <Arduino.h>

#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/gatt.h>
#include <zephyr/bluetooth/l2cap.h>
#include <zephyr/settings/settings.h>
#include <zephyr/sys/util.h>

#include <errno.h>
#include <cstddef>
#include <cstdint>
#include <string.h>

#ifndef M29_CORE_REVISION
#error "M29_CORE_REVISION is required"
#endif
#ifndef M29_BOARD_REVISION
#error "M29_BOARD_REVISION is required"
#endif
#ifndef M29_NCS_REVISION
#error "M29_NCS_REVISION is required"
#endif
#ifndef M29_ZEPHYR_REVISION
#error "M29_ZEPHYR_REVISION is required"
#endif

static_assert(CONFIG_BT_MAX_CONN == 2);
static_assert(CONFIG_BT_CTLR_SDC_PERIPHERAL_COUNT == 1);
static_assert(IS_ENABLED(CONFIG_BT_GATT_CLIENT));
static_assert(IS_ENABLED(CONFIG_BT_GATT_SERVICE_CHANGED));
static_assert(IS_ENABLED(CONFIG_BT_GATT_DYNAMIC_DB));
static_assert(IS_ENABLED(CONFIG_BT_GATT_CACHING));
static_assert(IS_ENABLED(CONFIG_BT_GATT_READ_MULTIPLE));
static_assert(IS_ENABLED(CONFIG_BT_GATT_READ_MULT_VAR_LEN));
static_assert(CONFIG_BT_ATT_TX_COUNT >= 8);
static_assert(CONFIG_BT_ATT_PREPARE_COUNT >= 8);
static_assert(IS_ENABLED(CONFIG_BT_L2CAP_DYNAMIC_CHANNEL));
static_assert(CONFIG_BT_L2CAP_TX_MTU >= 512);
static_assert(CONFIG_BT_L2CAP_TX_BUF_COUNT >= 4);
static_assert(IS_ENABLED(CONFIG_BT_SIGNING));
static_assert(IS_ENABLED(CONFIG_BT_EATT));
static_assert(CONFIG_BT_EATT_MAX == 2);
static_assert(!IS_ENABLED(CONFIG_BT_EATT_AUTO_CONNECT));
static_assert(!IS_ENABLED(CONFIG_NCS_BOOT_BANNER));

namespace
{

    constexpr char probe_command[] = "M29CAP|1|PROBE";
    constexpr char start_prefix[] = "M29CAP|1|START|nonce=";
    constexpr std::size_t nonce_length = 32U;
    constexpr std::size_t command_capacity = sizeof(start_prefix) + nonce_length;
    constexpr std::size_t maximum_value_bytes = 512U;
    constexpr std::size_t maximum_client_contexts = 2U;
    constexpr std::size_t maximum_descriptors = 4U;
    constexpr std::size_t maximum_read_multiple_handles = 4U;
    constexpr std::size_t maximum_coc_channels = 2U;

    char command[command_capacity] = {};
    char nonce[nonce_length + 1U] = {};
    std::size_t command_length = 0U;
    bool protocol_ready = false;
    bool protocol_finished = false;
    bool gatt_registered = false;
    bool l2cap_registered = false;

    std::uint8_t probe_value[maximum_value_bytes] = {};
    struct bt_uuid_16 probe_service_uuid = BT_UUID_INIT_16(0xffe0U);
    struct bt_uuid_16 probe_characteristic_uuid = BT_UUID_INIT_16(0xffe1U);
    struct bt_gatt_cep probe_extended_properties = {
        .properties = BT_GATT_CEP_RELIABLE_WRITE,
    };

    /** @brief capability probe characteristic의 bounded read를 처리합니다. */
    ssize_t probeRead(struct bt_conn *connection, const struct bt_gatt_attr *attribute,
                      void *buffer, std::uint16_t length, std::uint16_t offset)
    {
        return bt_gatt_attr_read(connection, attribute, buffer, length, offset, probe_value,
                                 sizeof(probe_value));
    }

    /** @brief capability probe의 prepare/execute flag와 offset 경로를 수락합니다. */
    ssize_t probeWrite(struct bt_conn *connection, const struct bt_gatt_attr *attribute,
                       const void *buffer, std::uint16_t length, std::uint16_t offset,
                       std::uint8_t flags)
    {
        ARG_UNUSED(connection);
        ARG_UNUSED(attribute);
        ARG_UNUSED(flags);
        if ((buffer == nullptr && length != 0U) ||
            static_cast<std::size_t>(offset) + length > sizeof(probe_value))
        {
            return BT_GATT_ERR(BT_ATT_ERR_INVALID_ATTRIBUTE_LEN);
        }
        if (length != 0U)
        {
            memcpy(probe_value + offset, buffer, length);
        }
        return length;
    }

    struct bt_gatt_attr probe_attributes[] = {
        BT_GATT_PRIMARY_SERVICE(&probe_service_uuid),
        BT_GATT_CHARACTERISTIC(&probe_characteristic_uuid.uuid,
                               BT_GATT_CHRC_READ | BT_GATT_CHRC_WRITE |
                                   BT_GATT_CHRC_EXT_PROP,
                               BT_GATT_PERM_READ | BT_GATT_PERM_WRITE |
                                   BT_GATT_PERM_PREPARE_WRITE,
                               probeRead, probeWrite, probe_value),
        BT_GATT_CEP(&probe_extended_properties),
    };
    struct bt_gatt_service probe_service = BT_GATT_SERVICE(probe_attributes);

    /** @brief capability probe는 실제 peer channel을 받지 않고 자원 없음으로 닫습니다. */
    int rejectL2cap(struct bt_conn *connection, struct bt_l2cap_server *server,
                    struct bt_l2cap_chan **channel)
    {
        ARG_UNUSED(connection);
        ARG_UNUSED(server);
        ARG_UNUSED(channel);
        return -ENOMEM;
    }

    struct bt_l2cap_server probe_l2cap_server = {
        .psm = 0U,
        .sec_level = BT_SECURITY_L2,
        .accept = rejectL2cap,
    };

    /** @brief 정해진 stage와 오류 코드를 한 번 출력하고 실행을 닫습니다. */
    void fail(const char *stage, int code)
    {
        if (protocol_finished)
        {
            return;
        }
        Serial.print("M29CAP|1|FAIL|stage=");
        Serial.print(stage);
        Serial.print("|code=");
        Serial.println(code);
        protocol_finished = true;
    }

    /** @brief Host API 등록을 실행해 compile-only 후보와 runtime 초기화를 구분합니다. */
    bool probeHostApis()
    {
        int result = bt_gatt_service_register(&probe_service);
        if (result != 0)
        {
            fail("gatt_register", result);
            return false;
        }
        gatt_registered = true;
        result = bt_l2cap_server_register(&probe_l2cap_server);
        if (result != 0)
        {
            fail("l2cap_register", result);
            return false;
        }
        l2cap_registered = true;
        return true;
    }

    /** @brief 정적 SDK 분류와 실제 W01 probe 경계를 한 줄로 출력합니다. */
    void printCapability(const char *identifier, const char *sdk_status,
                         const char *probe_status)
    {
        Serial.print("M29CAP|1|CAP|nonce=");
        Serial.print(nonce);
        Serial.print("|id=");
        Serial.print(identifier);
        Serial.print("|sdk=");
        Serial.print(sdk_status);
        Serial.print("|config=pass|probe=");
        Serial.println(probe_status);
    }

    /** @brief exact identity·Host 구성·계약 상한·capability를 고정 순서로 출력합니다. */
    void printSnapshot()
    {
        Serial.print("M29CAP|1|IDENTITY|nonce=");
        Serial.print(nonce);
        Serial.print("|core=");
        Serial.print(M29_CORE_REVISION);
        Serial.print("|board=");
        Serial.print(M29_BOARD_REVISION);
        Serial.print("|ncs=");
        Serial.print(M29_NCS_REVISION);
        Serial.print("|zephyr=");
        Serial.println(M29_ZEPHYR_REVISION);

        Serial.print("M29CAP|1|HOST|nonce=");
        Serial.print(nonce);
        Serial.print("|bt_max_conn=");
        Serial.print(CONFIG_BT_MAX_CONN);
        Serial.print("|gatt_client=");
        Serial.print(IS_ENABLED(CONFIG_BT_GATT_CLIENT));
        Serial.print("|dynamic_db=");
        Serial.print(IS_ENABLED(CONFIG_BT_GATT_DYNAMIC_DB));
        Serial.print("|read_multiple=");
        Serial.print(IS_ENABLED(CONFIG_BT_GATT_READ_MULTIPLE));
        Serial.print("|service_changed=");
        Serial.print(IS_ENABLED(CONFIG_BT_GATT_SERVICE_CHANGED));
        Serial.print("|caching=");
        Serial.print(IS_ENABLED(CONFIG_BT_GATT_CACHING));
        Serial.print("|l2cap_dynamic=");
        Serial.print(IS_ENABLED(CONFIG_BT_L2CAP_DYNAMIC_CHANNEL));
        Serial.print("|signing=");
        Serial.print(IS_ENABLED(CONFIG_BT_SIGNING));
        Serial.print("|eatt=");
        Serial.print(IS_ENABLED(CONFIG_BT_EATT));
        Serial.print("|eatt_max=");
        Serial.print(CONFIG_BT_EATT_MAX);
        Serial.print("|att_tx_count=");
        Serial.print(CONFIG_BT_ATT_TX_COUNT);
        Serial.print("|prepare_count=");
        Serial.print(CONFIG_BT_ATT_PREPARE_COUNT);
        Serial.print("|l2cap_tx_mtu=");
        Serial.print(CONFIG_BT_L2CAP_TX_MTU);
        Serial.print("|l2cap_tx_buffers=");
        Serial.println(CONFIG_BT_L2CAP_TX_BUF_COUNT);

        Serial.print("M29CAP|1|PROBE|nonce=");
        Serial.print(nonce);
        Serial.print("|gatt_service=");
        Serial.print(gatt_registered ? 1 : 0);
        Serial.print("|l2cap_server=");
        Serial.print(l2cap_registered ? 1 : 0);
        Serial.print("|l2cap_psm=");
        Serial.println(probe_l2cap_server.psm);

        Serial.print("M29CAP|1|CONTRACT|nonce=");
        Serial.print(nonce);
        Serial.print("|client_contexts=");
        Serial.print(maximum_client_contexts);
        Serial.print("|value_bytes=");
        Serial.print(maximum_value_bytes);
        Serial.print("|prepare_per_link=1|descriptors=");
        Serial.print(maximum_descriptors);
        Serial.print("|read_multiple_handles=");
        Serial.print(maximum_read_multiple_handles);
        Serial.print("|coc_channels=");
        Serial.print(maximum_coc_channels);
        Serial.print("|coc_sdu_bytes=");
        Serial.print(maximum_value_bytes);
        Serial.print("|eatt_bearers=");
        Serial.println(CONFIG_BT_EATT_MAX);

        printCapability("gatt_long_reliable", "stable", "gatt_registered");
        printCapability("gatt_read_multiple", "stable", "gatt_registered");
        printCapability("service_changed", "stable", "gatt_registered");
        printCapability("robust_caching", "stable", "gatt_registered");
        printCapability("le_coc", "stable", "server_registered");
        printCapability("signed_write_legacy", "deprecated", "peer_required");
        printCapability("eatt_experimental", "experimental", "peer_required");

        Serial.print("M29CAP|1|END|records=11|capabilities=7|nonce=");
        Serial.println(nonce);
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
        Serial.println("M29CAP|1|READY");
        protocol_ready = true;
        command_length = 0U;
    }

    /** @brief exact nonce command를 검증하고 Host capability를 한 번 보고합니다. */
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
        Serial.print("M29CAP|1|BEGIN|nonce=");
        Serial.println(nonce);
        printSnapshot();
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

/** @brief Bluetooth Host를 초기화하고 GATT·L2CAP API 등록을 실제 실행합니다. */
void setup()
{
    Serial.begin(115200);
    delay(20);
    int result = bt_enable(nullptr);
    if (result != 0)
    {
        fail("bt_enable", result);
        return;
    }
    result = settings_load();
    if (result != 0)
    {
        fail("settings_load", result);
        return;
    }
    if (!probeHostApis())
    {
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
