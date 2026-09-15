/**
 * @file main.cpp
 * @brief 두 NU54DK 사이의 인증 BLE SMP packet relay와 MCUboot 상태를 검증합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <Arduino.h>
#include <NUCODE_BLE_Security.h>
#include <internal/NUCODE_BLE_Internal.h>

#if defined(NUCODE_M30_DFU_PERIPHERAL)
#include <NUCODE_BLE_DFU.h>
#endif

#include <zephyr/bluetooth/att.h>
#include <zephyr/bluetooth/conn.h>
#include <zephyr/bluetooth/gatt.h>
#include <zephyr/bluetooth/uuid.h>
#include <zephyr/kernel.h>
#if defined(NUCODE_M30_DFU_POWER_HIL)
#include <zephyr/mgmt/mcumgr/mgmt/callbacks.h>
#endif
#include <zephyr/mgmt/mcumgr/transport/smp_bt.h>
#include <zephyr/sys/atomic.h>
#include <zephyr/sys/byteorder.h>
#include <zephyr/sys/util.h>

#include <cstddef>
#include <cstdint>
#include <errno.h>
#include <string.h>

namespace
{

    constexpr char protocol[] = "M30DFU|1";
    constexpr std::size_t nonce_characters = 32U;
    constexpr std::size_t nonce_bytes = 16U;
    constexpr std::uint16_t company_id = 0x054dU;
    constexpr std::size_t command_capacity = 640U;
    constexpr std::int64_t security_delay_ms = 300;
    constexpr std::int64_t scan_retry_ms = 100;
    constexpr std::int64_t scan_retry_timeout_ms = 30000;
    constexpr std::int64_t protocol_timeout_ms = 2400000;

    char nonce[nonce_characters + 1U] = {};
    std::uint8_t nonce_binary[nonce_bytes] = {};
    char command[command_capacity] = {};
    std::size_t command_length = 0U;
    bool started = false;
    bool failed = false;
    bool secured = false;
    bool link_reported = false;
    nucode::ble::BLEConnectionHandle connection_handle = {};
    std::int64_t security_due_ms = 0;
    std::int64_t deadline_ms = 0;

    /** @brief compile-time image 역할을 반환합니다. */
    const char *roleName()
    {
#if defined(NUCODE_M30_DFU_PERIPHERAL)
        return "peripheral";
#else
        return "central";
#endif
    }

    /** @brief nonce와 exact Core revision을 protocol 뒤에 붙입니다. */
    void printSuffix()
    {
        Serial.print("|nonce=");
        Serial.print(nonce);
        Serial.print("|core=");
        Serial.print(M30_DFU_CORE_REVISION);
    }

    /** @brief 첫 protocol 실패만 민감 정보 없이 보고합니다. */
    void fail(const char *reason)
    {
        if (!failed)
        {
            Serial.print(protocol);
            Serial.print("|FAIL|role=");
            Serial.print(roleName());
            Serial.print("|reason=");
            Serial.print(reason == nullptr ? "unknown" : reason);
            Serial.print("|security_error=");
            Serial.print(static_cast<unsigned int>(BLESecurity.lastError()));
            Serial.print("|security_driver=");
            Serial.print(BLESecurity.lastDriverError());
            Serial.print("|gap_error=");
            Serial.print(static_cast<unsigned int>(BLEDevice.lastError()));
            Serial.print("|gap_driver=");
            Serial.print(BLEDevice.lastDriverError());
            printSuffix();
            Serial.println();
        }
        failed = true;
    }

    /** @brief 소문자 128-bit nonce를 검증하고 binary로 변환합니다. */
    bool decodeNonce(const char *text)
    {
        if (text == nullptr || ::strlen(text) != nonce_characters)
        {
            return false;
        }
        for (std::size_t index = 0U; index < nonce_characters; ++index)
        {
            const char value = text[index];
            if (!((value >= '0' && value <= '9') || (value >= 'a' && value <= 'f')))
            {
                return false;
            }
        }
        for (std::size_t index = 0U; index < nonce_bytes; ++index)
        {
            const char high = text[index * 2U];
            const char low = text[index * 2U + 1U];
            const std::uint8_t high_value = static_cast<std::uint8_t>(
                high <= '9' ? high - '0' : high - 'a' + 10);
            const std::uint8_t low_value = static_cast<std::uint8_t>(
                low <= '9' ? low - '0' : low - 'a' + 10);
            nonce_binary[index] = static_cast<std::uint8_t>((high_value << 4U) | low_value);
        }
        ::memcpy(nonce, text, nonce_characters + 1U);
        return true;
    }

    /** @brief START가 nonce와 exact revision을 모두 포함하는지 확인합니다. */
    bool parseStart(const char *line)
    {
        constexpr char prefix[] = "M30DFU|1|START|nonce=";
        constexpr char core_marker[] = "|core=";
        const std::size_t prefix_length = sizeof(prefix) - 1U;
        if (line == nullptr || ::strncmp(line, prefix, prefix_length) != 0)
        {
            return false;
        }
        const char *value = line + prefix_length;
        if (::strlen(value) != nonce_characters + sizeof(core_marker) - 1U + 40U ||
            ::strncmp(value + nonce_characters, core_marker,
                      sizeof(core_marker) - 1U) != 0 ||
            ::strcmp(value + nonce_characters + sizeof(core_marker) - 1U,
                     M30_DFU_CORE_REVISION) != 0)
        {
            return false;
        }
        char parsed[nonce_characters + 1U] = {};
        ::memcpy(parsed, value, nonce_characters);
        return decodeNonce(parsed);
    }

#if !defined(NUCODE_M30_DFU_PERIPHERAL)
    /** @brief RESCAN command가 현재 nonce와 exact revision에 결합됐는지 확인합니다. */
    bool parseRescan(const char *line)
    {
        constexpr char prefix[] = "M30DFU|1|RESCAN|nonce=";
        constexpr char core_marker[] = "|core=";
        const std::size_t prefix_length = sizeof(prefix) - 1U;
        if (line == nullptr || ::strncmp(line, prefix, prefix_length) != 0)
        {
            return false;
        }
        const char *value = line + prefix_length;
        return ::strlen(value) ==
                   nonce_characters + sizeof(core_marker) - 1U + 40U &&
               ::strncmp(value, nonce, nonce_characters) == 0 &&
               ::strncmp(value + nonce_characters, core_marker,
                         sizeof(core_marker) - 1U) == 0 &&
               ::strcmp(value + nonce_characters + sizeof(core_marker) - 1U,
                        M30_DFU_CORE_REVISION) == 0;
    }
#endif

    /** @brief 실제 연결의 encryption key 크기를 반환합니다. */
    std::uint8_t encryptionKeySize()
    {
        struct bt_conn *connection =
            nucode::ble::internal::referenceConnection(connection_handle);
        if (connection == nullptr)
        {
            return 0U;
        }
        const std::uint8_t result = bt_conn_enc_key_size(connection);
        bt_conn_unref(connection);
        return result;
    }

#if defined(NUCODE_M30_DFU_PERIPHERAL)

#if defined(NUCODE_M30_DFU_POWER_HIL)
    struct mgmt_callback image_management_callback = {};

    /** @brief DFU 최종 검증 직후 실제 전원 차단을 위한 유한 관찰 창을 엽니다. */
    enum mgmt_cb_return onImageManagementEvent(
        std::uint32_t event, enum mgmt_cb_return previous_status,
        std::int32_t *return_code, std::uint16_t *group, bool *abort_more,
        void *data, std::size_t data_size)
    {
        ARG_UNUSED(return_code);
        ARG_UNUSED(group);
        ARG_UNUSED(abort_more);
        ARG_UNUSED(data);
        ARG_UNUSED(data_size);
        if (previous_status != MGMT_CB_OK)
        {
            return previous_status;
        }
        if (event == MGMT_EVT_OP_IMG_MGMT_DFU_PENDING)
        {
            Serial.println("M30POWER|1|WINDOW|point=image_validation_write");
            k_msleep(15000);
        }
        return MGMT_CB_OK;
    }
#endif

    /** @brief 실행 image와 explicit confirm 결과를 UART로 보고합니다. */
    void reportBoot()
    {
        const nucode::ble::SecureDfuImageVersion version = BLESecureDfu.version();
        Serial.print(protocol);
        Serial.print("|BOOT|role=peripheral|active_area_id=");
        Serial.print(BLESecureDfu.activeSlot());
        Serial.print("|confirmed=");
        Serial.print(BLESecureDfu.confirmed() ? 1 : 0);
        Serial.print("|auto_confirm=");
        Serial.print(NUCODE_M30_DFU_AUTO_CONFIRM);
        Serial.print("|version=");
        Serial.print(version.major);
        Serial.print('.');
        Serial.print(version.minor);
        Serial.print('.');
        Serial.print(version.revision);
        Serial.print('+');
        Serial.print(static_cast<unsigned long>(version.build));
        printSuffix();
        Serial.println();
    }

#if defined(NUCODE_M30_DFU_POWER_HIL)
    /** @brief settings load 결과와 bond 구조 상태를 민감 정보 없이 보고합니다. */
    void reportPowerState()
    {
        Serial.print("M30POWER|1|STATE|bond_count=");
        Serial.print(static_cast<unsigned long>(BLESecurity.bondCount()));
        Serial.print("|rejected_bonds=");
        Serial.print(static_cast<unsigned long>(BLESecurity.rejectedBondCount()));
        Serial.print("|bonded=");
        Serial.print(BLESecurity.bonded() ? 1 : 0);
        Serial.print("|settings_valid=");
        Serial.println(BLESecurity.rejectedBondCount() == 0U ? 1 : 0);
    }
#endif

    /** @brief nonce로 묶은 connectable advertising을 시작합니다. */
    bool startAdvertising()
    {
        return BLEAdvertising.clear() && BLEAdvertising.setConnectable(true) &&
               BLEAdvertising.setFlags(BT_LE_AD_GENERAL | BT_LE_AD_NO_BREDR) &&
               BLEAdvertising.setManufacturerData(company_id, nonce_binary,
                                                    sizeof(nonce_binary)) &&
               BLEAdvertising.setScanResponseName(true) && BLEAdvertising.start();
    }

#else

    constexpr std::size_t response_capacity = 1200U;
    std::uint8_t response[response_capacity] = {};
    std::size_t response_length = 0U;
    std::size_t response_expected = 0U;
    std::uint16_t smp_value_handle = 0U;
    struct bt_gatt_discover_params discovery_parameters = {};
    struct bt_gatt_discover_params ccc_discovery = {};
    struct bt_gatt_subscribe_params subscription = {};
    atomic_t discovery_complete = ATOMIC_INIT(0);
    atomic_t subscription_complete = ATOMIC_INIT(0);
    atomic_t subscription_error = ATOMIC_INIT(0);
    atomic_t response_ready = ATOMIC_INIT(0);
    atomic_t response_error = ATOMIC_INIT(0);
    bool discovery_started = false;
    bool subscription_started = false;
    bool mtu_ready = false;
    bool restart_scan_pending = false;
    std::int64_t restart_scan_due_ms = 0;
    std::int64_t restart_scan_deadline_ms = 0;

    /** @brief 현재 Central L4·MTU·SMP 준비 상태를 protocol로 다시 보고합니다. */
    void reportCentralLink()
    {
        Serial.print(protocol);
        Serial.print("|LINK|role=central|level=4|key_size=16|mtu=247|smp=1");
        printSuffix();
        Serial.println();
    }

    /** @brief hard power loss 뒤 scan 재시작을 bounded retry 상태로 예약합니다. */
    void scheduleCentralScan()
    {
        const std::int64_t now = k_uptime_get();
        restart_scan_pending = true;
        restart_scan_due_ms = now;
        restart_scan_deadline_ms = now + scan_retry_timeout_ms;
    }

    /** @brief 연결 또는 scan 시작이 확인되면 남은 재시작 예약을 해제합니다. */
    void clearScheduledCentralScan()
    {
        restart_scan_pending = false;
        restart_scan_due_ms = 0;
        restart_scan_deadline_ms = 0;
    }

    /** @brief scan 재시작 중 발생 가능한 controller busy 상태만 재시도 대상으로 판별합니다. */
    bool isTransientScanRestartError()
    {
        const nucode::ble::BLEError error = BLEDevice.lastError();
        const int driver_error = BLEDevice.lastDriverError();
        return restart_scan_pending &&
               ((error == nucode::ble::BLEError::busy && driver_error == -EBUSY) ||
                ((error == nucode::ble::BLEError::already_started ||
                  error == nucode::ble::BLEError::wrong_state) &&
                 driver_error == -EALREADY));
    }

    /** @brief scan 결과의 manufacturer field를 exact nonce와 비교합니다. */
    bool validPayload(const nucode::ble::BLEScanResult &result)
    {
        std::size_t cursor = 0U;
        while (cursor < result.payload_length)
        {
            const std::uint8_t field_length = result.payload[cursor];
            if (field_length == 0U || cursor + field_length >= result.payload_length)
            {
                return false;
            }
            if (result.payload[cursor + 1U] == BT_DATA_MANUFACTURER_DATA &&
                field_length == nonce_bytes + 3U)
            {
                const std::uint8_t *value = &result.payload[cursor + 2U];
                return value[0] == static_cast<std::uint8_t>(company_id & 0xffU) &&
                       value[1] == static_cast<std::uint8_t>(company_id >> 8U) &&
                       ::memcmp(&value[2], nonce_binary, sizeof(nonce_binary)) == 0;
            }
            cursor += field_length + 1U;
        }
        return false;
    }

    /** @brief nonce가 일치하는 connectable DUT에 한 번만 연결합니다. */
    void onScanResult(const nucode::ble::BLEScanResult &result, void *context)
    {
        ARG_UNUSED(context);
        if (!started || failed || connection_handle.valid() || !result.connectable ||
            result.scan_response || !validPayload(result))
        {
            return;
        }
        static_cast<void>(BLEScan.stop());
        if (!BLEConnection.connect(result.address))
        {
            fail("connect-start");
        }
    }

    /** @brief SMP characteristic handle을 full discovery에서 찾습니다. */
    std::uint8_t onDiscovery(struct bt_conn *connection,
                             const struct bt_gatt_attr *attribute,
                             struct bt_gatt_discover_params *parameters)
    {
        ARG_UNUSED(connection);
        if (attribute == nullptr)
        {
            ::memset(parameters, 0, sizeof(*parameters));
            atomic_set(&discovery_complete, 1);
            return BT_GATT_ITER_STOP;
        }
        const auto *characteristic =
            static_cast<const struct bt_gatt_chrc *>(attribute->user_data);
        if (characteristic != nullptr && characteristic->uuid != nullptr &&
            bt_uuid_cmp(characteristic->uuid, SMP_BT_CHR_UUID) == 0)
        {
            smp_value_handle = characteristic->value_handle;
        }
        return BT_GATT_ITER_CONTINUE;
    }

    /** @brief 원격 SMP characteristic discovery를 시작합니다. */
    void beginDiscovery()
    {
        struct bt_conn *connection =
            nucode::ble::internal::referenceConnection(connection_handle);
        if (connection == nullptr)
        {
            fail("discover-connection");
            return;
        }
        smp_value_handle = 0U;
        discovery_parameters = {};
        discovery_parameters.func = onDiscovery;
        discovery_parameters.start_handle = BT_ATT_FIRST_ATTRIBUTE_HANDLE;
        discovery_parameters.end_handle = BT_ATT_LAST_ATTRIBUTE_HANDLE;
        discovery_parameters.type = BT_GATT_DISCOVER_CHARACTERISTIC;
        atomic_set(&discovery_complete, 0);
        discovery_started = true;
        const int result = bt_gatt_discover(connection, &discovery_parameters);
        bt_conn_unref(connection);
        if (result < 0)
        {
            fail("discover-start");
        }
    }

    /** @brief SMP response notification fragment를 bounded buffer에 모읍니다. */
    std::uint8_t onNotification(struct bt_conn *connection,
                                struct bt_gatt_subscribe_params *parameters,
                                const void *data, std::uint16_t length)
    {
        ARG_UNUSED(connection);
        ARG_UNUSED(parameters);
        if (data == nullptr)
        {
            return BT_GATT_ITER_STOP;
        }
        if (atomic_get(&response_ready) != 0 || length == 0U ||
            response_length + length > sizeof(response))
        {
            atomic_set(&response_error, 1);
            return BT_GATT_ITER_CONTINUE;
        }
        ::memcpy(&response[response_length], data, length);
        response_length += length;
        if (response_expected == 0U && response_length >= 8U)
        {
            response_expected = 8U + sys_get_be16(&response[2]);
            if (response_expected > sizeof(response))
            {
                atomic_set(&response_error, 1);
                return BT_GATT_ITER_CONTINUE;
            }
        }
        if (response_expected != 0U && response_length == response_expected)
        {
            atomic_set(&response_ready, 1);
        }
        else if (response_expected != 0U && response_length > response_expected)
        {
            atomic_set(&response_error, 1);
        }
        return BT_GATT_ITER_CONTINUE;
    }

    /** @brief CCC write 결과를 main loop에 전달합니다. */
    void onSubscribed(struct bt_conn *connection, std::uint8_t error,
                      struct bt_gatt_subscribe_params *parameters)
    {
        ARG_UNUSED(connection);
        ARG_UNUSED(parameters);
        atomic_set(&subscription_error, error);
        atomic_set(&subscription_complete, 1);
    }

    /** @brief authenticated SMP notification 구독을 시작합니다. */
    void beginSubscription()
    {
        struct bt_conn *connection =
            nucode::ble::internal::referenceConnection(connection_handle);
        if (connection == nullptr || smp_value_handle == 0U)
        {
            if (connection != nullptr)
            {
                bt_conn_unref(connection);
            }
            fail("subscribe-handle");
            return;
        }
        subscription = {};
        ccc_discovery = {};
        subscription.notify = onNotification;
        subscription.subscribe = onSubscribed;
        subscription.value_handle = smp_value_handle;
        subscription.ccc_handle = BT_GATT_AUTO_DISCOVER_CCC_HANDLE;
        subscription.end_handle = BT_ATT_LAST_ATTRIBUTE_HANDLE;
        subscription.disc_params = &ccc_discovery;
        subscription.value = BT_GATT_CCC_NOTIFY;
        subscription.min_security = BT_SECURITY_L4;
        atomic_set_bit(subscription.flags, BT_GATT_SUBSCRIBE_FLAG_VOLATILE);
        atomic_set(&subscription_complete, 0);
        atomic_set(&subscription_error, 0);
        subscription_started = true;
        const int result = bt_gatt_subscribe(connection, &subscription);
        bt_conn_unref(connection);
        if (result < 0)
        {
            fail("subscribe-start");
        }
    }

    /** @brief 한 hex 문자를 nibble로 변환합니다. */
    int hexNibble(char value)
    {
        if (value >= '0' && value <= '9')
        {
            return value - '0';
        }
        if (value >= 'a' && value <= 'f')
        {
            return value - 'a' + 10;
        }
        return -1;
    }

    /** @brief hex SMP request를 실제 authenticated GATT write로 전송합니다. */
    void sendSmp(const char *hex)
    {
        std::uint8_t packet[256] = {};
        if (!link_reported || hex == nullptr || atomic_get(&response_ready) != 0 ||
            response_length != 0U)
        {
            fail("tx-state");
            return;
        }
        const std::size_t characters = ::strlen(hex);
        if (characters < 16U || characters > sizeof(packet) * 2U ||
            (characters % 2U) != 0U)
        {
            fail("tx-length");
            return;
        }
        const std::size_t packet_length = characters / 2U;
        for (std::size_t index = 0U; index < packet_length; ++index)
        {
            const int high = hexNibble(hex[index * 2U]);
            const int low = hexNibble(hex[index * 2U + 1U]);
            if (high < 0 || low < 0)
            {
                fail("tx-hex");
                return;
            }
            packet[index] = static_cast<std::uint8_t>((high << 4U) | low);
        }
        if (8U + sys_get_be16(&packet[2]) != packet_length)
        {
            fail("tx-header-length");
            return;
        }
        struct bt_conn *connection =
            nucode::ble::internal::referenceConnection(connection_handle);
        if (connection == nullptr || packet_length > bt_gatt_get_mtu(connection) - 3U)
        {
            if (connection != nullptr)
            {
                bt_conn_unref(connection);
            }
            fail("tx-mtu");
            return;
        }
        response_length = 0U;
        response_expected = 0U;
        atomic_set(&response_error, 0);
        const int result = bt_gatt_write_without_response(
            connection, smp_value_handle, packet, packet_length, false);
        bt_conn_unref(connection);
        if (result < 0)
        {
            fail("tx-write");
        }
    }

    /** @brief 완성된 SMP response를 ASCII hex로 Host에 전달합니다. */
    void reportResponse()
    {
        if (atomic_get(&response_error) != 0)
        {
            fail("rx-frame");
            return;
        }
        if (atomic_cas(&response_ready, 1, 0) == 0)
        {
            return;
        }
        constexpr char digits[] = "0123456789abcdef";
        Serial.print(protocol);
        Serial.print("|RX|role=central|data=");
        for (std::size_t index = 0U; index < response_length; ++index)
        {
            Serial.print(digits[response[index] >> 4U]);
            Serial.print(digits[response[index] & 0x0fU]);
        }
        printSuffix();
        Serial.println();
        response_length = 0U;
        response_expected = 0U;
    }

    /** @brief security·discovery·CCC 상태 기계를 진행합니다. */
    void driveCentral()
    {
        if (connection_handle.valid() && !secured && security_due_ms != 0 &&
            k_uptime_get() >= security_due_ms)
        {
            security_due_ms = 0;
            if (!BLESecurity.requestSecurity(connection_handle) &&
                BLESecurity.lastError() != nucode::ble::SecurityError::busy)
            {
                fail("security-request");
                return;
            }
        }
        if (secured && mtu_ready && !discovery_started)
        {
            beginDiscovery();
        }
        if (atomic_cas(&discovery_complete, 1, 0) != 0)
        {
            if (smp_value_handle == 0U)
            {
                fail("smp-not-found");
                return;
            }
            beginSubscription();
        }
        if (atomic_cas(&subscription_complete, 1, 0) != 0)
        {
            if (atomic_get(&subscription_error) != 0)
            {
                fail("subscribe-result");
                return;
            }
            if (BLESecurity.currentLevel(connection_handle) !=
                    nucode::ble::SecurityLevel::secure_connections ||
                encryptionKeySize() != 16U)
            {
                fail("link-security");
                return;
            }
            link_reported = true;
            reportCentralLink();
        }
        reportResponse();
        if (restart_scan_pending)
        {
            const std::int64_t now = k_uptime_get();
            if (now >= restart_scan_due_ms)
            {
                if (!connection_handle.valid())
                {
                    if (BLEScan.running() || BLEScan.start(false))
                    {
                        clearScheduledCentralScan();
                    }
                    else
                    {
                        restart_scan_due_ms = now + scan_retry_ms;
                    }
                }
                else
                {
                    clearScheduledCentralScan();
                }
                if (restart_scan_pending && now >= restart_scan_deadline_ms)
                {
                    fail("scan-restart-timeout");
                }
            }
        }
    }

#endif

    /** @brief GAP event를 연결·재연결 상태로 전달합니다. */
    void onBleEvent(const nucode::ble::BLEEventInfo &information, void *context)
    {
        ARG_UNUSED(context);
        if (!started || failed)
        {
            return;
        }
        if (information.event == nucode::ble::BLEEvent::connected)
        {
            connection_handle = information.connection;
            security_due_ms = k_uptime_get() + security_delay_ms;
#if !defined(NUCODE_M30_DFU_PERIPHERAL)
            clearScheduledCentralScan();
            if (!BLEConnection.requestMtu(connection_handle))
            {
                fail("mtu-request");
            }
#endif
        }
#if !defined(NUCODE_M30_DFU_PERIPHERAL)
        else if (information.event == nucode::ble::BLEEvent::mtu_changed &&
                 information.connection == connection_handle)
        {
            if (BLEConnection.mtu(connection_handle) != 247U)
            {
                fail("mtu-value");
                return;
            }
            mtu_ready = true;
        }
#endif
        else if (information.event == nucode::ble::BLEEvent::disconnected)
        {
#if !defined(NUCODE_M30_DFU_PERIPHERAL)
            Serial.print(protocol);
            Serial.print("|UNLINK|role=central");
            printSuffix();
            Serial.println();
#endif
            connection_handle = {};
            secured = false;
            link_reported = false;
#if !defined(NUCODE_M30_DFU_PERIPHERAL)
            discovery_started = false;
            subscription_started = false;
            mtu_ready = false;
            smp_value_handle = 0U;
            response_length = 0U;
            response_expected = 0U;
            atomic_set(&response_ready, 0);
#endif
        }
        else if (information.event == nucode::ble::BLEEvent::connection_recycled)
        {
#if !defined(NUCODE_M30_DFU_PERIPHERAL)
            if (started && !connection_handle.valid())
            {
                scheduleCentralScan();
            }
#endif
        }
        else if (information.event == nucode::ble::BLEEvent::error)
        {
#if !defined(NUCODE_M30_DFU_PERIPHERAL)
            if (isTransientScanRestartError())
            {
                restart_scan_due_ms = k_uptime_get() + scan_retry_ms;
                return;
            }
#endif
            fail("gap-error");
        }
    }

    /** @brief numeric comparison을 승인하고 L4 도달만 secured로 인정합니다. */
    void onSecurityEvent(const nucode::ble::SecurityEventRecord &event, void *context)
    {
        ARG_UNUSED(context);
        if (failed)
        {
            return;
        }
        if (event.event == nucode::ble::SecurityEvent::pairing_requested)
        {
            if (!BLESecurity.acceptPairing(event.connection, true))
            {
                fail("pairing-accept");
            }
        }
        else if (event.event ==
                 nucode::ble::SecurityEvent::passkey_confirmation_requested)
        {
            if (!BLESecurity.confirmPasskey(event.connection, true))
            {
                fail("numeric-confirm");
            }
        }
        else if (event.event == nucode::ble::SecurityEvent::security_changed &&
                 event.level >= nucode::ble::SecurityLevel::secure_connections)
        {
            secured = true;
#if defined(NUCODE_M30_DFU_PERIPHERAL)
            if (!link_reported && encryptionKeySize() == 16U)
            {
                link_reported = true;
                Serial.print(protocol);
                Serial.print("|LINK|role=peripheral|level=4|key_size=16|smp=1");
                printSuffix();
                Serial.println();
            }
#endif
        }
        else if (event.event == nucode::ble::SecurityEvent::pairing_failed ||
                 event.event == nucode::ble::SecurityEvent::pairing_cancelled ||
                 event.event == nucode::ble::SecurityEvent::timeout ||
                 event.event == nucode::ble::SecurityEvent::error)
        {
            fail("security-event");
        }
    }

    /** @brief Host UART 명령을 현재 role 상태에 적용합니다. */
    void executeCommand(char *line)
    {
        if (::strcmp(line, "M30DFU|1|READY?") == 0)
        {
            Serial.print(protocol);
            Serial.print("|READY|role=");
            Serial.print(roleName());
            Serial.print("|core=");
            Serial.print(M30_DFU_CORE_REVISION);
            Serial.println();
            return;
        }
        if (::strcmp(line, "M30DFU|1|BOOT?") == 0)
        {
#if defined(NUCODE_M30_DFU_PERIPHERAL)
            reportBoot();
#else
            Serial.print(protocol);
            Serial.print("|BOOT|role=central");
            printSuffix();
            Serial.println();
#endif
            return;
        }
#if defined(NUCODE_M30_DFU_PERIPHERAL) && defined(NUCODE_M30_DFU_POWER_HIL)
        if (::strcmp(line, "M30POWER|1|STATE?") == 0)
        {
            reportPowerState();
            return;
        }
#endif
        constexpr char rescan_marker[] = "M30DFU|1|RESCAN|";
#if !defined(NUCODE_M30_DFU_PERIPHERAL)
        if (::strncmp(line, rescan_marker, sizeof(rescan_marker) - 1U) == 0)
        {
            if (!started || !parseRescan(line))
            {
                fail("rescan-command");
                return;
            }
            if (!connection_handle.valid())
            {
                scheduleCentralScan();
            }
            Serial.print(protocol);
            Serial.print("|RESCAN|role=central");
            printSuffix();
            Serial.println();
            if (link_reported)
            {
                reportCentralLink();
            }
            return;
        }
#else
        ARG_UNUSED(rescan_marker);
#endif
        constexpr char start_marker[] = "M30DFU|1|START|";
        if (::strncmp(line, start_marker, sizeof(start_marker) - 1U) == 0 && !started)
        {
            if (!parseStart(line))
            {
                fail("start-command");
                return;
            }
            started = true;
            deadline_ms = k_uptime_get() + protocol_timeout_ms;
#if defined(NUCODE_M30_DFU_PERIPHERAL)
            if (!startAdvertising())
            {
                fail("advertising-start");
                return;
            }
#else
            if (!BLEScan.clearFilters() || !BLEScan.start(false))
            {
                fail("scan-start");
                return;
            }
#endif
            Serial.print(protocol);
            Serial.print("|BEGIN|role=");
            Serial.print(roleName());
            printSuffix();
            Serial.println();
#if defined(NUCODE_M30_DFU_PERIPHERAL)
            reportBoot();
#endif
            return;
        }
#if !defined(NUCODE_M30_DFU_PERIPHERAL)
        constexpr char transmit_marker[] = "M30DFU|1|TX|";
        if (::strncmp(line, transmit_marker, sizeof(transmit_marker) - 1U) == 0)
        {
            sendSmp(line + sizeof(transmit_marker) - 1U);
            return;
        }
#endif
        fail("command-state");
    }

    /** @brief newline으로 끝나는 bounded VCOM command를 조립합니다. */
    void pollCommand()
    {
        while (Serial.available() > 0)
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
                executeCommand(command);
                command_length = 0U;
                return;
            }
            if (command_length + 1U >= sizeof(command))
            {
                command_length = 0U;
                fail("command-overflow");
                return;
            }
            command[command_length++] = value;
        }
    }

} // namespace

/** @brief DFU image·보안·BLE role을 초기화합니다. */
void setup()
{
    Serial.begin(115200);
#if defined(NUCODE_M30_DFU_PERIPHERAL)
#if defined(NUCODE_M30_DFU_POWER_HIL)
    image_management_callback.callback = onImageManagementEvent;
    image_management_callback.event_id = MGMT_EVT_OP_IMG_MGMT_DFU_PENDING;
    mgmt_callback_register(&image_management_callback);
#endif
    if (!BLESecureDfu.begin())
    {
        fail("dfu-begin");
        return;
    }
#endif
    nucode::ble::SecurityConfig security = {};
    security.minimum_level = nucode::ble::SecurityLevel::secure_connections;
    security.bonding = true;
    security.response_timeout_ms = 30000U;
    security.io_capability = nucode::ble::SecurityIoCapability::display_yes_no;
    BLESecurity.onEvent(onSecurityEvent);
    if (!BLESecurity.begin(security))
    {
        fail("security-begin");
        return;
    }
    BLEDevice.onEventInfo(onBleEvent);
    if (!BLEDevice.begin(
#if defined(NUCODE_M30_DFU_PERIPHERAL)
            "NU54-M30-DFU-P"
#else
            "NU54-M30-DFU-C"
#endif
            ))
    {
        fail("device-begin");
        return;
    }
#if defined(NUCODE_M30_DFU_PERIPHERAL) && NUCODE_M30_DFU_AUTO_CONFIRM
    if (!BLESecureDfu.confirm())
    {
        fail("dfu-confirm");
        return;
    }
#endif
#if !defined(NUCODE_M30_DFU_PERIPHERAL)
    BLEScan.onResult(onScanResult);
#endif
}

/** @brief UART·BLE·security·SMP relay 상태 기계를 진행합니다. */
void loop()
{
    pollCommand();
    BLEDevice.poll();
    BLESecurity.poll();
#if !defined(NUCODE_M30_DFU_PERIPHERAL)
    if (started && !failed)
    {
        driveCentral();
    }
#endif
    if (started && !failed && k_uptime_get() > deadline_ms)
    {
        fail("protocol-timeout");
    }
    k_msleep(1);
}
