/**
 * @file main.cpp
 * @brief M30 보안·OOB·profile·DFU capability를 실제 Host API와 함께 보고합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <Arduino.h>

#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/conn.h>
#include <zephyr/bluetooth/gatt.h>
#include <zephyr/mgmt/mcumgr/transport/smp_bt.h>
#include <zephyr/settings/settings.h>
#include <zephyr/sys/util.h>

#include <errno.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

#ifndef M30_CORE_REVISION
#error "M30_CORE_REVISION is required"
#endif
#ifndef M30_BOARD_REVISION
#error "M30_BOARD_REVISION is required"
#endif
#ifndef M30_NCS_REVISION
#error "M30_NCS_REVISION is required"
#endif
#ifndef M30_ZEPHYR_REVISION
#error "M30_ZEPHYR_REVISION is required"
#endif

static_assert(CONFIG_BT_MAX_CONN == 2);
static_assert(CONFIG_BT_CTLR_SDC_PERIPHERAL_COUNT == 1);
static_assert(IS_ENABLED(CONFIG_BT_SMP));
static_assert(IS_ENABLED(CONFIG_BT_SMP_APP_PAIRING_ACCEPT));
static_assert(IS_ENABLED(CONFIG_BT_SMP_SC_PAIR_ONLY));
static_assert(CONFIG_BT_SMP_MIN_ENC_KEY_SIZE == 16);
static_assert(IS_ENABLED(CONFIG_BT_BONDABLE));
static_assert(CONFIG_BT_MAX_PAIRED == 4);
static_assert(IS_ENABLED(CONFIG_BT_PRIVACY));
static_assert(IS_ENABLED(CONFIG_MCUMGR_TRANSPORT_BT));
static_assert(IS_ENABLED(CONFIG_MCUMGR_TRANSPORT_BT_PERM_RW_AUTHEN));
static_assert(CONFIG_MCUMGR_TRANSPORT_NETBUF_SIZE == 1024);
static_assert(!IS_ENABLED(CONFIG_NCS_BOOT_BANNER));

namespace
{

    constexpr char probe_command[] = "M30CAP|1|PROBE";
    constexpr char start_prefix[] = "M30CAP|1|START|nonce=";
    constexpr size_t nonce_length = 32U;
    constexpr size_t command_capacity = sizeof(start_prefix) + nonce_length;
    constexpr size_t security_contexts = 2U;
    constexpr size_t pairing_slots = 2U;
    constexpr size_t oob_records = 2U;
    constexpr size_t maximum_oob_frame_bytes = 192U;
    constexpr size_t profile_entries = 7U;
    constexpr size_t dfu_slots = 2U;

    char command[command_capacity] = {};
    char nonce[nonce_length + 1U] = {};
    size_t command_length = 0U;
    bool protocol_ready = false;
    bool protocol_finished = false;
    bool auth_callbacks_registered = false;
    bool oob_local_generated = false;
    bool profile_registered = false;
    bool mcumgr_registered = false;

    struct bt_le_oob local_oob = {};
    uint8_t heart_rate_value[2] = {0U, 60U};
    struct bt_uuid_16 heart_rate_service_uuid = BT_UUID_INIT_16(0x180dU);
    struct bt_uuid_16 heart_rate_measurement_uuid = BT_UUID_INIT_16(0x2a37U);

    /** @brief Heart Rate capability probe 값을 bounded read로 제공합니다. */
    ssize_t heartRateRead(struct bt_conn *connection, const struct bt_gatt_attr *attribute,
                          void *buffer, uint16_t length, uint16_t offset)
    {
        return bt_gatt_attr_read(connection, attribute, buffer, length, offset,
                                 heart_rate_value, sizeof(heart_rate_value));
    }

    struct bt_gatt_attr profile_attributes[] = {
        BT_GATT_PRIMARY_SERVICE(&heart_rate_service_uuid),
        BT_GATT_CHARACTERISTIC(&heart_rate_measurement_uuid.uuid, BT_GATT_CHRC_READ,
                               BT_GATT_PERM_READ_ENCRYPT, heartRateRead, nullptr,
                               heart_rate_value),
    };
    struct bt_gatt_service profile_service = BT_GATT_SERVICE(profile_attributes);

    /** @brief 연결별 pairing 요청을 정책 계층이 판정하도록 수락합니다. */
    enum bt_security_err pairingAccept(struct bt_conn *connection,
                                       const struct bt_conn_pairing_feat *features)
    {
        ARG_UNUSED(connection);
        ARG_UNUSED(features);
        return BT_SECURITY_ERR_SUCCESS;
    }

    /** @brief 실제 OOB 요청은 W03 link별 carrier가 채우므로 capability 단계에서는 비웁니다. */
    void oobDataRequest(struct bt_conn *connection, struct bt_conn_oob_info *information)
    {
        ARG_UNUSED(connection);
        ARG_UNUSED(information);
    }

    struct bt_conn_auth_cb authentication_callbacks = {
        .pairing_accept = pairingAccept,
        .oob_data_request = oobDataRequest,
    };

    /** @brief 오류 한 건을 출력하고 protocol을 영구 종료합니다. */
    void fail(const char *stage, int code)
    {
        if (protocol_finished)
        {
            return;
        }
        Serial.print("M30CAP|1|FAIL|stage=");
        Serial.print(stage);
        Serial.print("|code=");
        Serial.println(code);
        protocol_finished = true;
    }

    /** @brief 실제 Host 등록·OOB 생성 경로를 한 번 실행합니다. */
    bool probeHostApis()
    {
        int result = bt_conn_auth_cb_register(&authentication_callbacks);
        if (result != 0)
        {
            fail("auth_register", result);
            return false;
        }
        auth_callbacks_registered = true;

        result = bt_le_oob_get_local(BT_ID_DEFAULT, &local_oob);
        if (result != 0)
        {
            fail("oob_local", result);
            return false;
        }
        oob_local_generated = true;

        result = bt_gatt_service_register(&profile_service);
        if (result != 0)
        {
            fail("profile_register", result);
            return false;
        }
        profile_registered = true;

        result = smp_bt_unregister();
        if (result != 0)
        {
            fail("mcumgr_unregister", result);
            return false;
        }
        result = smp_bt_register();
        if (result != 0)
        {
            fail("mcumgr_register", result);
            return false;
        }
        mcumgr_registered = true;
        return true;
    }

    /** @brief source 후보와 W01 runtime probe의 서로 다른 상태를 출력합니다. */
    void printCapability(const char *identifier, const char *publication,
                         const char *probe)
    {
        Serial.print("M30CAP|1|CAP|nonce=");
        Serial.print(nonce);
        Serial.print("|id=");
        Serial.print(identifier);
        Serial.print("|source=candidate|publication=");
        Serial.print(publication);
        Serial.print("|probe=");
        Serial.println(probe);
    }

    /** @brief exact identity·설정·고정 자원·capability를 순서대로 출력합니다. */
    void printSnapshot()
    {
        Serial.print("M30CAP|1|IDENTITY|nonce=");
        Serial.print(nonce);
        Serial.print("|core=");
        Serial.print(M30_CORE_REVISION);
        Serial.print("|board=");
        Serial.print(M30_BOARD_REVISION);
        Serial.print("|ncs=");
        Serial.print(M30_NCS_REVISION);
        Serial.print("|zephyr=");
        Serial.println(M30_ZEPHYR_REVISION);

        Serial.print("M30CAP|1|HOST|nonce=");
        Serial.print(nonce);
        Serial.print("|bt_max_conn=");
        Serial.print(CONFIG_BT_MAX_CONN);
        Serial.print("|smp=");
        Serial.print(IS_ENABLED(CONFIG_BT_SMP));
        Serial.print("|sc_pair_only=");
        Serial.print(IS_ENABLED(CONFIG_BT_SMP_SC_PAIR_ONLY));
        Serial.print("|min_key_bytes=");
        Serial.print(CONFIG_BT_SMP_MIN_ENC_KEY_SIZE);
        Serial.print("|max_paired=");
        Serial.print(CONFIG_BT_MAX_PAIRED);
        Serial.print("|privacy=");
        Serial.print(IS_ENABLED(CONFIG_BT_PRIVACY));
        Serial.print("|app_pairing=");
        Serial.print(IS_ENABLED(CONFIG_BT_SMP_APP_PAIRING_ACCEPT));
        Serial.print("|mcumgr_bt=");
        Serial.print(IS_ENABLED(CONFIG_MCUMGR_TRANSPORT_BT));
        Serial.print("|mcumgr_authen=");
        Serial.println(IS_ENABLED(CONFIG_MCUMGR_TRANSPORT_BT_PERM_RW_AUTHEN));

        Serial.print("M30CAP|1|PROBE|nonce=");
        Serial.print(nonce);
        Serial.print("|auth_callbacks=");
        Serial.print(auth_callbacks_registered ? 1 : 0);
        Serial.print("|oob_local=");
        Serial.print(oob_local_generated ? 1 : 0);
        Serial.print("|profile_service=");
        Serial.print(profile_registered ? 1 : 0);
        Serial.print("|mcumgr_service=");
        Serial.println(mcumgr_registered ? 1 : 0);

        Serial.print("M30CAP|1|CONTRACT|nonce=");
        Serial.print(nonce);
        Serial.print("|security_contexts=");
        Serial.print(security_contexts);
        Serial.print("|pairing_slots=");
        Serial.print(pairing_slots);
        Serial.print("|oob_records=");
        Serial.print(oob_records);
        Serial.print("|oob_frame_bytes=");
        Serial.print(maximum_oob_frame_bytes);
        Serial.print("|bond_records=");
        Serial.print(CONFIG_BT_MAX_PAIRED);
        Serial.print("|profile_entries=");
        Serial.print(profile_entries);
        Serial.print("|dfu_slots=");
        Serial.println(dfu_slots);

        printCapability("smp_io_capabilities", "stable", "config_pass");
        printCapability("le_secure_connections_oob", "stable_after_hil",
                        "local_generated");
        printCapability("bond_privacy_migration", "stable_after_hil",
                        "settings_loaded");
        printCapability("adopted_profiles", "candidate", "service_registered");
        printCapability("mcuboot_signed_image", "candidate", "source_only");
        printCapability("mcumgr_ble_transport", "candidate", "service_registered");
        printCapability("dfu_rollback_recovery", "candidate", "source_only");

        Serial.print("M30CAP|1|END|records=11|capabilities=7|nonce=");
        Serial.println(nonce);
    }

    /** @brief flash 뒤 exact PROBE command에만 READY를 반환합니다. */
    void probeProtocol()
    {
        if (command_length != strlen(probe_command) ||
            memcmp(command, probe_command, strlen(probe_command)) != 0)
        {
            fail("probe_command", -EINVAL);
            return;
        }
        Serial.println("M30CAP|1|READY");
        protocol_ready = true;
        command_length = 0U;
    }

    /** @brief 128-bit nonce START command를 검증하고 snapshot을 한 번 출력합니다. */
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
        Serial.print("M30CAP|1|BEGIN|nonce=");
        Serial.println(nonce);
        printSnapshot();
        protocol_finished = true;
    }

    /** @brief bounded UART command에서 CR을 버리고 LF 하나로 frame을 닫습니다. */
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

/** @brief Bluetooth Host·settings와 실제 capability probe를 초기화합니다. */
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

/** @brief exact Host command가 올 때까지 UART만 polling합니다. */
void loop()
{
    if (!protocol_finished)
    {
        pollCommand();
    }
    delay(1);
}
