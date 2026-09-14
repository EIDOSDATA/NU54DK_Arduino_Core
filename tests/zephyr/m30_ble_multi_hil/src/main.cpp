/**
 * @file main.cpp
 * @brief 세 NU54DK의 두 generation link 보안 연산을 동시에 검증합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <Arduino.h>
#include <NUCODE_BLE_Security.h>
#include <internal/NUCODE_BLE_Internal.h>

#include <zephyr/bluetooth/conn.h>
#include <zephyr/bluetooth/hci_types.h>
#include <zephyr/kernel.h>

#include <cstddef>
#include <cstdint>
#include <string.h>

#ifndef M30_MULTI_CORE_REVISION
#error "M30_MULTI_CORE_REVISION is required"
#endif

static_assert(CONFIG_BT_MAX_CONN == 2);
static_assert(CONFIG_BT_CTLR_SDC_PERIPHERAL_COUNT == 1);

namespace
{

    constexpr char protocol[] = "M30W07|1";
    constexpr char ready_query[] = "M30W07|1|READY?";
    constexpr char start_prefix[] = "M30W07|1|START|test=M30-MULTI-01|nonce=";
    constexpr char run_prefix[] = "M30W07|1|RUN|nonce=";
    constexpr char core_suffix[] = "|core=" M30_MULTI_CORE_REVISION;
    constexpr std::size_t nonce_text_length = 32U;
    constexpr std::size_t nonce_binary_length = 16U;
    constexpr std::uint16_t company_id = 0x30a7U;
    constexpr std::uint8_t peripheral_marker = 0xa1U;
    constexpr std::uint8_t mixed_marker = 0xb2U;
    constexpr std::uint32_t required_operations = 100U;
    constexpr std::int64_t security_request_delay_ms = 500;
    constexpr std::int64_t session_timeout_ms = 1200000;

    char command[160] = {};
    std::size_t command_length = 0U;
    char nonce[nonce_text_length + 1U] = {};
    std::uint8_t nonce_binary[nonce_binary_length] = {};
    bool session_started = false;
    bool operations_started = false;
    bool session_finished = false;
    bool callback_context_valid = true;
    bool scan_started = false;
    bool peer_found = false;
    bool connection_attempted = false;
    bool client_security_pending = false;
    bool client_secure = false;
    bool server_secure = false;
    bool upstream_reported = false;
    bool advertising_started = false;
    bool link_reported = false;
    std::int64_t security_request_due_ms = 0;
    std::int64_t session_deadline = 0;
    std::uint32_t client_operations = 0U;
    std::uint32_t server_operations = 0U;
    std::uint32_t progress_reported = 0U;
    std::uint32_t cross_link_events = 0U;
    std::uint32_t security_errors = 0U;
    std::uint32_t key_size_errors = 0U;
    nucode::ble::BLEAddress peer_address;
    nucode::ble::BLEConnectionHandle client_connection;
    nucode::ble::BLEConnectionHandle server_connection;
    struct k_thread *setup_thread = nullptr;

    /** @brief 현재 image의 고정 role 이름을 반환합니다. */
    const char *roleName()
    {
#if defined(NUCODE_M30_MULTI_PERIPHERAL)
        return "peripheral";
#elif defined(NUCODE_M30_MULTI_MIXED)
        return "mixed";
#else
        return "central";
#endif
    }

    /** @brief 현재 role이 central link를 가지는지 반환합니다. */
    constexpr bool hasClient()
    {
#if defined(NUCODE_M30_MULTI_PERIPHERAL)
        return false;
#else
        return true;
#endif
    }

    /** @brief 현재 role이 peripheral link를 가지는지 반환합니다. */
    constexpr bool hasServer()
    {
#if defined(NUCODE_M30_MULTI_CENTRAL)
        return false;
#else
        return true;
#endif
    }

    /** @brief 현재 server 광고의 role marker를 반환합니다. */
    constexpr std::uint8_t serverMarker()
    {
#if defined(NUCODE_M30_MULTI_PERIPHERAL)
        return peripheral_marker;
#else
        return mixed_marker;
#endif
    }

    /** @brief 현재 client가 찾을 peer role marker를 반환합니다. */
    constexpr std::uint8_t peerMarker()
    {
#if defined(NUCODE_M30_MULTI_MIXED)
        return peripheral_marker;
#else
        return mixed_marker;
#endif
    }

    /** @brief 모든 session record에 nonce와 exact Core revision을 붙입니다. */
    void printSuffix()
    {
        Serial.print("|nonce=");
        Serial.print(nonce);
        Serial.print("|core=");
        Serial.print(M30_MULTI_CORE_REVISION);
    }

    /** @brief 첫 실패를 출력하고 이후 상태 전진을 막습니다. */
    void fail(const char *stage, int code = 0)
    {
        if (session_finished)
        {
            return;
        }
        Serial.print(protocol);
        Serial.print("|FAIL|role=");
        Serial.print(roleName());
        Serial.print("|stage=");
        Serial.print(stage == nullptr ? "unknown" : stage);
        Serial.print("|code=");
        Serial.print(code);
        printSuffix();
        Serial.println();
        session_finished = true;
    }

    /** @brief 공개 callback이 Arduino main thread에서 실행되는지 확인합니다. */
    void checkCallbackContext()
    {
        if (k_current_get() != setup_thread)
        {
            callback_context_valid = false;
            fail("callback_context");
        }
    }

    /** @brief lowercase 128-bit nonce를 decode합니다. */
    bool decodeNonce(const char *text)
    {
        if (text == nullptr || ::strlen(text) != nonce_text_length)
        {
            return false;
        }
        for (std::size_t index = 0U; index < nonce_binary_length; ++index)
        {
            const char high = text[index * 2U];
            const char low = text[index * 2U + 1U];
            const auto nibble = [](char value, std::uint8_t &output) {
                if (value >= '0' && value <= '9')
                {
                    output = static_cast<std::uint8_t>(value - '0');
                    return true;
                }
                if (value >= 'a' && value <= 'f')
                {
                    output = static_cast<std::uint8_t>(value - 'a' + 10);
                    return true;
                }
                return false;
            };
            std::uint8_t high_value = 0U;
            std::uint8_t low_value = 0U;
            if (!nibble(high, high_value) || !nibble(low, low_value))
            {
                return false;
            }
            nonce_binary[index] = static_cast<std::uint8_t>((high_value << 4U) | low_value);
        }
        ::memcpy(nonce, text, sizeof(nonce));
        return true;
    }

    /** @brief command의 nonce와 exact revision suffix를 검증합니다. */
    bool acceptIdentity(const char *line, const char *prefix)
    {
        const std::size_t prefix_length = ::strlen(prefix);
        if (::strncmp(line, prefix, prefix_length) != 0)
        {
            return false;
        }
        const char *nonce_start = line + prefix_length;
        char candidate[nonce_text_length + 1U] = {};
        ::memcpy(candidate, nonce_start, nonce_text_length);
        if (::strcmp(nonce_start + nonce_text_length, core_suffix) != 0)
        {
            return false;
        }
        if (!session_started)
        {
            return decodeNonce(candidate);
        }
        return ::strcmp(candidate, nonce) == 0;
    }

    /** @brief connection의 실제 암호화 key 길이를 읽습니다. */
    std::uint8_t encryptionKeySize(nucode::ble::BLEConnectionHandle handle)
    {
        struct bt_conn *connection = nucode::ble::internal::referenceConnection(handle);
        if (connection == nullptr)
        {
            return 0U;
        }
        const std::uint8_t size = bt_conn_enc_key_size(connection);
        bt_conn_unref(connection);
        return size;
    }

    /** @brief 현재 nonce와 peer marker가 일치하는 광고만 선택합니다. */
    bool validRfPeer(const nucode::ble::BLEScanResult &result)
    {
        std::size_t cursor = 0U;
        while (cursor < result.payload_length)
        {
            const std::uint8_t length = result.payload[cursor];
            if (length == 0U || cursor + length >= result.payload_length)
            {
                return false;
            }
            if (result.payload[cursor + 1U] == BT_DATA_MANUFACTURER_DATA &&
                length == nonce_binary_length + 4U)
            {
                const std::uint8_t *value = &result.payload[cursor + 2U];
                return value[0] == static_cast<std::uint8_t>(company_id & 0xffU) &&
                       value[1] == static_cast<std::uint8_t>(company_id >> 8U) &&
                       value[2] == peerMarker() &&
                       ::memcmp(value + 3U, nonce_binary, nonce_binary_length) == 0;
            }
            cursor += length + 1U;
        }
        return false;
    }

    /** @brief role marker와 nonce를 넣은 connectable advertising을 시작합니다. */
    bool startAdvertising()
    {
        std::uint8_t manufacturer[nonce_binary_length + 1U] = {};
        manufacturer[0] = serverMarker();
        ::memcpy(manufacturer + 1U, nonce_binary, nonce_binary_length);
        if (!BLEAdvertising.clear() || !BLEAdvertising.setConnectable(true) ||
            !BLEAdvertising.setManufacturerData(company_id, manufacturer,
                                                  sizeof(manufacturer)) ||
            !BLEAdvertising.setScanResponseName(true) || !BLEAdvertising.start())
        {
            return false;
        }
        advertising_started = true;
        Serial.print(protocol);
        Serial.print("|ADVERTISE|role=");
        Serial.print(roleName());
        Serial.print("|marker=");
        Serial.print(serverMarker());
        Serial.print("|status=pass");
        printSuffix();
        Serial.println();
        return true;
    }

    /** @brief exact peer를 찾는 active scan을 시작합니다. */
    bool startScan()
    {
        if (!BLEScan.clearFilters() || !BLEScan.start(true))
        {
            return false;
        }
        scan_started = true;
        Serial.print(protocol);
        Serial.print("|SCAN|role=");
        Serial.print(roleName());
        Serial.print("|status=pass");
        printSuffix();
        Serial.println();
        return true;
    }

    /** @brief local role의 모든 generation link가 L2·16-byte인지 확인합니다. */
    bool allLinksSecure()
    {
        if ((hasClient() && !client_secure) || (hasServer() && !server_secure))
        {
            return false;
        }
        if (hasClient() && encryptionKeySize(client_connection) != 16U)
        {
            return false;
        }
        if (hasServer() && encryptionKeySize(server_connection) != 16U)
        {
            return false;
        }
        return true;
    }

    /** @brief mixed upstream 보안 완료 뒤 downstream advertising을 시작합니다. */
    void startMixedAdvertisingIfReady()
    {
#if defined(NUCODE_M30_MULTI_MIXED)
        if (!client_secure || advertising_started || session_finished)
        {
            return;
        }
        Serial.print(protocol);
        Serial.print("|UPSTREAM|role=mixed|security=ready|key_size=16");
        printSuffix();
        Serial.println();
        upstream_reported = true;
        if (!startAdvertising())
        {
            fail("mixed_advertising", BLEDevice.lastDriverError());
        }
#endif
    }

    /** @brief 모든 local link가 안전한 순간 고정 LINK record를 출력합니다. */
    void printLinkIfReady()
    {
        if (link_reported || !allLinksSecure())
        {
            return;
        }
#if defined(NUCODE_M30_MULTI_MIXED)
        if (!upstream_reported)
        {
            return;
        }
        const unsigned int connections = 2U;
#else
        const unsigned int connections = 1U;
#endif
        link_reported = true;
        Serial.print(protocol);
        Serial.print("|LINK|role=");
        Serial.print(roleName());
        Serial.print("|connections=");
        Serial.print(connections);
        Serial.print("|level=2|key_size=16");
        printSuffix();
        Serial.println();
    }

    /** @brief scan 결과를 main loop의 exact 연결 시도로 넘깁니다. */
    void onScanResult(const nucode::ble::BLEScanResult &result, void *context)
    {
        static_cast<void>(context);
        checkCallbackContext();
        if (!session_started || session_finished || !scan_started || peer_found ||
            connection_attempted || !result.connectable || result.scan_response ||
            !validRfPeer(result))
        {
            return;
        }
        peer_found = true;
        peer_address = result.address;
    }

    /** @brief GAP event를 client/server generation handle에 분리합니다. */
    void onBleEvent(const nucode::ble::BLEEventInfo &information, void *context)
    {
        static_cast<void>(context);
        checkCallbackContext();
        if (!session_started || session_finished)
        {
            return;
        }
        if (information.event == nucode::ble::BLEEvent::error)
        {
            fail("gap_error", BLEDevice.lastDriverError());
            return;
        }
        if (information.event == nucode::ble::BLEEvent::connected)
        {
            if (!information.connection.valid())
            {
                fail("connection_handle");
                return;
            }
            if (information.role == nucode::ble::BLELinkRole::central && hasClient())
            {
                if (client_connection.valid() && client_connection != information.connection)
                {
                    ++cross_link_events;
                    fail("duplicate_client_link");
                    return;
                }
                client_connection = information.connection;
                client_security_pending = true;
                security_request_due_ms = k_uptime_get() + security_request_delay_ms;
                return;
            }
            if (information.role == nucode::ble::BLELinkRole::peripheral && hasServer())
            {
                if (server_connection.valid() && server_connection != information.connection)
                {
                    ++cross_link_events;
                    fail("duplicate_server_link");
                    return;
                }
                server_connection = information.connection;
                return;
            }
            ++cross_link_events;
            fail("unexpected_connection_role");
            return;
        }
        if (information.event == nucode::ble::BLEEvent::disconnected)
        {
            fail("early_disconnect");
        }
    }

    /** @brief security event를 exact generation handle에만 반영합니다. */
    void onSecurityEvent(const nucode::ble::SecurityEventRecord &event, void *context)
    {
        static_cast<void>(context);
        checkCallbackContext();
        if (!session_started || session_finished)
        {
            return;
        }
        const bool client_event = client_connection.valid() &&
                                  event.connection == client_connection;
        const bool server_event = server_connection.valid() &&
                                  event.connection == server_connection;
        if (!client_event && !server_event)
        {
            ++cross_link_events;
            fail("cross_link_security_event");
            return;
        }
        switch (event.event)
        {
        case nucode::ble::SecurityEvent::pairing_requested:
            if (!BLESecurity.acceptPairing(event.connection, true))
            {
                ++security_errors;
                fail("pairing_response", BLESecurity.lastDriverError());
            }
            break;
        case nucode::ble::SecurityEvent::security_changed:
            if (event.level != nucode::ble::SecurityLevel::encrypted ||
                encryptionKeySize(event.connection) != 16U)
            {
                ++security_errors;
                fail("security_level_or_key");
                return;
            }
            if (client_event)
            {
                client_secure = true;
                client_security_pending = false;
            }
            else
            {
                server_secure = true;
            }
            startMixedAdvertisingIfReady();
            printLinkIfReady();
            break;
        case nucode::ble::SecurityEvent::pairing_failed:
        case nucode::ble::SecurityEvent::timeout:
        case nucode::ble::SecurityEvent::error:
            ++security_errors;
            fail("security_event", event.reason);
            break;
        default:
            break;
        }
    }

    /** @brief central role의 보안 요청을 연결 직후가 아닌 main loop에서 실행합니다. */
    void driveInitialSecurity()
    {
        if (!client_security_pending || k_uptime_get() < security_request_due_ms)
        {
            return;
        }
        if (!BLESecurity.requestSecurity(client_connection))
        {
            if (BLESecurity.lastError() == nucode::ble::SecurityError::busy)
            {
                security_request_due_ms = k_uptime_get() + 100;
                return;
            }
            ++security_errors;
            fail("security_request", BLESecurity.lastDriverError());
        }
    }

    /** @brief 한 generation handle에 대한 공개 보안 연산 한 회를 검증합니다. */
    bool performSecurityOperation(nucode::ble::BLEConnectionHandle handle)
    {
        if (!BLESecurity.requestSecurity(handle) ||
            BLESecurity.currentLevel(handle) != nucode::ble::SecurityLevel::encrypted)
        {
            ++security_errors;
            return false;
        }
        if (encryptionKeySize(handle) != 16U)
        {
            ++key_size_errors;
            return false;
        }
        return true;
    }

    /** @brief local link별 보안 연산을 한 loop에 한 회씩 전진시킵니다. */
    void driveOperations()
    {
        if (!operations_started || session_finished)
        {
            return;
        }
        if (hasClient() && client_operations < required_operations)
        {
            if (!performSecurityOperation(client_connection))
            {
                fail("client_security_operation", BLESecurity.lastDriverError());
                return;
            }
            ++client_operations;
        }
        if (hasServer() && server_operations < required_operations)
        {
            if (!performSecurityOperation(server_connection))
            {
                fail("server_security_operation", BLESecurity.lastDriverError());
                return;
            }
            ++server_operations;
        }
        std::uint32_t completed = required_operations;
        if (hasClient() && client_operations < completed)
        {
            completed = client_operations;
        }
        if (hasServer() && server_operations < completed)
        {
            completed = server_operations;
        }
        while (progress_reported + 10U <= completed)
        {
            progress_reported += 10U;
            Serial.print(protocol);
            Serial.print("|PROGRESS|role=");
            Serial.print(roleName());
            Serial.print("|operations_per_link=");
            Serial.print(progress_reported);
            printSuffix();
            Serial.println();
        }
        const bool client_complete = !hasClient() || client_operations == required_operations;
        const bool server_complete = !hasServer() || server_operations == required_operations;
        if (!client_complete || !server_complete)
        {
            return;
        }
#if defined(NUCODE_M30_MULTI_MIXED)
        const unsigned int connections = 2U;
#else
        const unsigned int connections = 1U;
#endif
        Serial.print(protocol);
        Serial.print("|RESULT|role=");
        Serial.print(roleName());
        Serial.print("|connections=");
        Serial.print(connections);
        Serial.print("|client_ops=");
        Serial.print(client_operations);
        Serial.print("|server_ops=");
        Serial.print(server_operations);
        Serial.print("|cross_link=0|security_errors=0|key_size_errors=0");
        Serial.print("|callback_context=pass");
        printSuffix();
        Serial.println();
        Serial.print(protocol);
        Serial.print("|END|role=");
        Serial.print(roleName());
        Serial.print("|status=pass");
        printSuffix();
        Serial.println();
        session_finished = true;
    }

    /** @brief START command 뒤 role별 scan 또는 advertising을 시작합니다. */
    void startProtocol()
    {
        if (!acceptIdentity(command, start_prefix))
        {
            fail("start_record");
            return;
        }
        session_started = true;
        session_deadline = k_uptime_get() + session_timeout_ms;
        Serial.print(protocol);
        Serial.print("|BEGIN|role=");
        Serial.print(roleName());
        Serial.print("|test=M30-MULTI-01");
        printSuffix();
        Serial.println();
#if defined(NUCODE_M30_MULTI_PERIPHERAL)
        if (!startAdvertising())
        {
            fail("peripheral_advertising", BLEDevice.lastDriverError());
        }
#else
        if (!startScan())
        {
            fail("scan_start", BLEDevice.lastDriverError());
        }
#endif
    }

    /** @brief LINK 이후 exact RUN command만 보안 연산 시작으로 수락합니다. */
    void startOperations()
    {
        if (!link_reported || !acceptIdentity(command, run_prefix))
        {
            fail("run_record");
            return;
        }
        operations_started = true;
        Serial.print(protocol);
        Serial.print("|RUNNING|role=");
        Serial.print(roleName());
        Serial.print("|operations_per_link=100");
        printSuffix();
        Serial.println();
    }

    /** @brief Host의 bounded READY·START·RUN 명령을 수집합니다. */
    void pollHostCommand()
    {
        while (Serial.available() > 0 && !session_finished)
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
                command_length = 0U;
                if (!session_started && ::strcmp(command, ready_query) == 0)
                {
                    Serial.print(protocol);
                    Serial.print("|READY|role=");
                    Serial.print(roleName());
                    Serial.print("|core=");
                    Serial.println(M30_MULTI_CORE_REVISION);
                }
                else if (!session_started)
                {
                    startProtocol();
                }
                else if (!operations_started)
                {
                    startOperations();
                }
                else
                {
                    fail("unexpected_command");
                }
                return;
            }
            if (command_length + 1U >= sizeof(command))
            {
                fail("command_overflow");
                return;
            }
            command[command_length++] = value;
        }
    }

} // namespace

void setup()
{
    setup_thread = k_current_get();
    Serial.begin(115200);
    const std::int64_t deadline = k_uptime_get() + 5000;
    while (!Serial && k_uptime_get() < deadline)
    {
        delay(10);
    }
    nucode::ble::SecurityConfig security = {};
    security.minimum_level = nucode::ble::SecurityLevel::encrypted;
    security.bonding = false;
    security.response_timeout_ms = 30000U;
    security.io_capability = nucode::ble::SecurityIoCapability::no_input_output;
    BLESecurity.onEvent(onSecurityEvent);
    if (!BLESecurity.begin(security))
    {
        fail("security_begin", BLESecurity.lastDriverError());
        return;
    }
    BLEDevice.onEventInfo(onBleEvent);
    if (hasClient())
    {
        BLEScan.onResult(onScanResult);
    }
    if (!BLEDevice.begin(roleName()))
    {
        fail("device_begin", BLEDevice.lastDriverError());
        return;
    }
}

void loop()
{
    pollHostCommand();
    BLEDevice.poll();
    BLESecurity.poll();
    if (!session_started || session_finished)
    {
        delay(1);
        return;
    }
    if (peer_found && scan_started && !connection_attempted)
    {
        peer_found = false;
        connection_attempted = true;
        scan_started = false;
        if (!BLEScan.stop() || !BLEConnection.connect(peer_address, client_connection))
        {
            fail("connect_start", BLEDevice.lastDriverError());
        }
    }
    driveInitialSecurity();
    startMixedAdvertisingIfReady();
    printLinkIfReady();
    driveOperations();
    if (!session_finished && k_uptime_get() >= session_deadline)
    {
        fail("timeout");
    }
    delay(1);
}
