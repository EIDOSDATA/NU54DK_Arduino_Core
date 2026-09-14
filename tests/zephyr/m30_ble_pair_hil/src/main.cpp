/**
 * @file main.cpp
 * @brief M30의 SC-only IO capability pairing을 두 NU54DK 사이에서 검증합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <Arduino.h>
#include <NUCODE_BLE_Security.h>
#include <internal/NUCODE_BLE_Internal.h>

#include <zephyr/bluetooth/conn.h>
#include <zephyr/kernel.h>

#include <cstddef>
#include <cstdint>
#include <stdlib.h>
#include <string.h>

namespace
{

    constexpr char protocol_name[] = "M30PAIR";
    constexpr char protocol_revision[] = "1";
    constexpr char peer_name[] = "NU54-M30-PAIR";
    constexpr std::size_t nonce_length = 32U;
    constexpr std::size_t rf_nonce_length = 16U;
    constexpr std::size_t rf_payload_length = rf_nonce_length + 1U;
    constexpr std::uint16_t rf_company_id = 0x3054U;
    constexpr std::size_t command_capacity = 128U;
    constexpr std::int64_t security_request_delay_ms = 500;

    char nonce[nonce_length + 1U] = {};
    std::uint8_t rf_payload[rf_payload_length] = {};
    char command[command_capacity] = {};
    std::size_t command_length = 0U;
    std::uint8_t current_round = 0U;
    nucode::ble::BLEConnectionHandle connection_handle = {};
    bool protocol_started = false;
    bool protocol_failed = false;
    bool clearing = false;
    bool security_request_pending = false;
    bool pairing_requested_seen = false;
    bool passkey_display_seen = false;
    bool passkey_input_seen = false;
    bool passkey_confirmation_seen = false;
    bool paired_seen = false;
    bool persistence_pending_seen = false;
    bool secure_seen = false;
    bool pass_reported = false;
    std::uint8_t encryption_key_size = 0U;
    std::uint32_t unexpected_auth_failures = 0U;
    std::int64_t security_request_due_ms = 0;

    /** @brief compile-time role의 protocol 이름을 반환합니다. */
    const char *roleName()
    {
#if defined(NUCODE_M30_PAIR_CENTRAL)
        return "central";
#else
        return "peripheral";
#endif
    }

    /** @brief 실패를 현재 case·round·nonce와 함께 한 번만 출력합니다. */
    void fail(const char *reason)
    {
        if (!protocol_failed)
        {
            Serial.print("M30PAIR|1|FAIL|role=");
            Serial.print(roleName());
            Serial.print("|case=");
            Serial.print(NUCODE_M30_PAIR_CASE_NAME);
            Serial.print("|round=");
            Serial.print(current_round);
            Serial.print("|reason=");
            Serial.print(reason == nullptr ? "unknown" : reason);
            Serial.print("|nonce=");
            Serial.println(nonce);
        }
        protocol_failed = true;
    }

    /** @brief 소문자 32자리 nonce인지 검사합니다. */
    bool validNonce(const char *value)
    {
        if (value == nullptr || ::strlen(value) != nonce_length)
        {
            return false;
        }
        for (std::size_t index = 0U; index < nonce_length; ++index)
        {
            const char byte = value[index];
            if (!((byte >= '0' && byte <= '9') || (byte >= 'a' && byte <= 'f')))
            {
                return false;
            }
        }
        return true;
    }

    /** @brief 소문자 hex 한 글자를 nibble로 변환합니다. */
    std::uint8_t hexNibble(char value)
    {
        if (value <= '9')
        {
            return static_cast<std::uint8_t>(value - '0');
        }
        return static_cast<std::uint8_t>(value - 'a' + 10);
    }

    /** @brief UART nonce와 case를 RF manufacturer payload로 변환합니다. */
    void decodeRfPayload()
    {
        for (std::size_t index = 0U; index < rf_nonce_length; ++index)
        {
            rf_payload[index] = static_cast<std::uint8_t>(
                (hexNibble(nonce[index * 2U]) << 4U) |
                hexNibble(nonce[index * 2U + 1U]));
        }
        rf_payload[rf_nonce_length] = static_cast<std::uint8_t>(NUCODE_M30_PAIR_CASE);
    }

    /** @brief 현재 case에서 이 role이 관찰해야 하는 인증 event인지 확인합니다. */
    bool expectedMethodObserved()
    {
#if NUCODE_M30_PAIR_CASE == 0
        return pairing_requested_seen;
#elif NUCODE_M30_PAIR_CASE == 1 || NUCODE_M30_PAIR_CASE == 2
        return passkey_display_seen || passkey_input_seen;
#else
        return passkey_confirmation_seen;
#endif
    }

    /** @brief 실제 암호화 key 길이를 exact connection에서 읽습니다. */
    void captureEncryptionKeySize()
    {
        struct bt_conn *connection =
            nucode::ble::internal::referenceConnection(connection_handle);
        if (connection == nullptr)
        {
            fail("key-connection");
            return;
        }
        encryption_key_size = bt_conn_enc_key_size(connection);
        bt_conn_unref(connection);
    }

    /** @brief pairing·bond·L4·16-byte 조건을 모두 충족하면 round PASS를 출력합니다. */
    void reportPassIfReady()
    {
        if (pass_reported || protocol_failed || !paired_seen || !persistence_pending_seen ||
            !secure_seen || !expectedMethodObserved())
        {
            return;
        }
        captureEncryptionKeySize();
        if (protocol_failed)
        {
            return;
        }
        if (encryption_key_size != 16U)
        {
            fail("key-size");
            return;
        }
        if (!BLESecurity.paired(connection_handle) ||
            BLESecurity.currentLevel(connection_handle) !=
                nucode::ble::SecurityLevel::secure_connections ||
            BLESecurity.bondState(connection_handle) !=
                nucode::ble::BondState::persistence_pending)
        {
            fail("link-state");
            return;
        }
        Serial.print("M30PAIR|1|PASS|role=");
        Serial.print(roleName());
        Serial.print("|case=");
        Serial.print(NUCODE_M30_PAIR_CASE_NAME);
        Serial.print("|round=");
        Serial.print(current_round);
        Serial.print("|method=");
        Serial.print(NUCODE_M30_PAIR_METHOD);
        Serial.print("|level=4|key_size=16|paired=1|unexpected_auth_failures=");
        Serial.print(unexpected_auth_failures);
        Serial.print("|nonce=");
        Serial.println(nonce);
        pass_reported = true;
    }

    /** @brief 표시 passkey를 6자리 UART 사용자 I/O로 전달합니다. */
    void reportDisplayedPasskey(std::uint32_t passkey)
    {
        Serial.print("M30PAIR|1|DISPLAY|role=");
        Serial.print(roleName());
        Serial.print("|case=");
        Serial.print(NUCODE_M30_PAIR_CASE_NAME);
        Serial.print("|round=");
        Serial.print(current_round);
        Serial.print("|nonce=");
        Serial.print(nonce);
        Serial.print("|value=");
        std::uint32_t divisor = 100000U;
        while (divisor > 0U)
        {
            Serial.print(static_cast<unsigned int>((passkey / divisor) % 10U));
            divisor /= 10U;
        }
        Serial.println();
    }

    /** @brief SecurityManager event를 exact generation 응답과 판정에 연결합니다. */
    void onSecurityEvent(const nucode::ble::SecurityEventRecord &event, void *context)
    {
        ARG_UNUSED(context);
        if (!protocol_started)
        {
            return;
        }
        if (!event.connection.valid() || event.connection != connection_handle)
        {
            fail("cross-link-event");
            return;
        }
        switch (event.event)
        {
        case nucode::ble::SecurityEvent::pairing_requested:
            pairing_requested_seen = true;
            if (!BLESecurity.acceptPairing(event.connection, true))
            {
                fail("pairing-response");
            }
            break;
        case nucode::ble::SecurityEvent::passkey_display:
            passkey_display_seen = true;
            reportDisplayedPasskey(event.passkey);
            break;
        case nucode::ble::SecurityEvent::passkey_input_requested:
            passkey_input_seen = true;
            Serial.print("M30PAIR|1|INPUT|role=");
            Serial.print(roleName());
            Serial.print("|case=");
            Serial.print(NUCODE_M30_PAIR_CASE_NAME);
            Serial.print("|round=");
            Serial.print(current_round);
            Serial.print("|nonce=");
            Serial.println(nonce);
            break;
        case nucode::ble::SecurityEvent::passkey_confirmation_requested:
            passkey_confirmation_seen = true;
            if (!BLESecurity.confirmPasskey(event.connection, true))
            {
                fail("confirmation-response");
            }
            break;
        case nucode::ble::SecurityEvent::paired:
            paired_seen = true;
            break;
        case nucode::ble::SecurityEvent::bond_persistence_pending:
            persistence_pending_seen = true;
            break;
        case nucode::ble::SecurityEvent::security_changed:
            if (event.level != nucode::ble::SecurityLevel::secure_connections)
            {
                fail("security-level");
            }
            else
            {
                secure_seen = true;
            }
            break;
        case nucode::ble::SecurityEvent::pairing_failed:
        case nucode::ble::SecurityEvent::timeout:
        case nucode::ble::SecurityEvent::error:
            ++unexpected_auth_failures;
            fail("authentication");
            break;
        default:
            break;
        }
        reportPassIfReady();
    }

    /** @brief GAP event에서 exact link handle과 central 보안 요청을 준비합니다. */
    void onBleEvent(const nucode::ble::BLEEventInfo &information, void *context)
    {
        ARG_UNUSED(context);
        if (information.event == nucode::ble::BLEEvent::connected && protocol_started)
        {
            connection_handle = information.connection;
            if (!connection_handle.valid())
            {
                fail("connection-handle");
                return;
            }
#if defined(NUCODE_M30_PAIR_CENTRAL)
            if (information.role != nucode::ble::BLELinkRole::central)
#else
            if (information.role != nucode::ble::BLELinkRole::peripheral)
#endif
            {
                fail("connection-role");
                return;
            }
#if defined(NUCODE_M30_PAIR_CENTRAL)
            security_request_pending = true;
            security_request_due_ms = k_uptime_get() + security_request_delay_ms;
#endif
        }
        else if (information.event == nucode::ble::BLEEvent::disconnected)
        {
            connection_handle = {};
            security_request_pending = false;
            if (protocol_started && !clearing && !pass_reported)
            {
                fail("disconnected");
            }
            clearing = false;
        }
        else if (information.event == nucode::ble::BLEEvent::error && protocol_started &&
                 !clearing)
        {
            fail("gap-error");
        }
    }

#if defined(NUCODE_M30_PAIR_CENTRAL)
    /** @brief scan payload가 현재 128-bit nonce와 case를 정확히 포함하는지 검사합니다. */
    bool validRfBinding(const nucode::ble::BLEScanResult &result)
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
                field_length == rf_payload_length + 3U)
            {
                const std::uint8_t *value = &result.payload[cursor + 2U];
                return value[0] == static_cast<std::uint8_t>(rf_company_id & 0xffU) &&
                       value[1] == static_cast<std::uint8_t>(rf_company_id >> 8U) &&
                       ::memcmp(&value[2], rf_payload, rf_payload_length) == 0;
            }
            cursor += field_length + 1U;
        }
        return false;
    }

    /** @brief 현재 nonce와 case가 일치하는 connectable peer에만 연결합니다. */
    void onScanResult(const nucode::ble::BLEScanResult &result, void *context)
    {
        ARG_UNUSED(context);
        if (!protocol_started || protocol_failed || !result.connectable ||
            result.scan_response || !validRfBinding(result))
        {
            return;
        }
        static_cast<void>(BLEScan.stop());
        if (!BLEConnection.connect(result.address))
        {
            fail("connect-start");
        }
    }
#endif

    /** @brief 새 round의 volatile 판정 상태를 초기화합니다. */
    void resetRoundState()
    {
        connection_handle = {};
        protocol_failed = false;
        security_request_pending = false;
        pairing_requested_seen = false;
        passkey_display_seen = false;
        passkey_input_seen = false;
        passkey_confirmation_seen = false;
        paired_seen = false;
        persistence_pending_seen = false;
        secure_seen = false;
        pass_reported = false;
        encryption_key_size = 0U;
        unexpected_auth_failures = 0U;
        security_request_due_ms = 0;
    }

    /** @brief 두 role의 광고·scan·연결을 멈추고 bond를 삭제합니다. */
    void clearRound()
    {
        protocol_started = false;
        clearing = true;
#if defined(NUCODE_M30_PAIR_CENTRAL)
        if (BLEScan.running())
        {
            static_cast<void>(BLEScan.stop());
        }
#else
        if (BLEAdvertising.running())
        {
            static_cast<void>(BLEAdvertising.stop());
        }
#endif
        if (connection_handle.valid())
        {
            static_cast<void>(BLEConnection.disconnect(connection_handle));
        }
        if (!BLESecurity.eraseAllBonds())
        {
            fail("clear-bonds");
            return;
        }
        Serial.print("M30PAIR|1|CLEARED|role=");
        Serial.print(roleName());
        Serial.print("|case=");
        Serial.print(NUCODE_M30_PAIR_CASE_NAME);
        Serial.print("|round=");
        Serial.print(current_round);
        Serial.print("|bond_count=");
        Serial.print(BLESecurity.bondCount());
        Serial.print("|nonce=");
        Serial.println(nonce);
    }

    /** @brief 현재 case의 광고 또는 scan을 시작합니다. */
    void startRound()
    {
        resetRoundState();
        protocol_started = true;
        clearing = false;
#if defined(NUCODE_M30_PAIR_CENTRAL)
        if (!BLEScan.clearFilters() || !BLEScan.start(true))
        {
            fail("scan-start");
        }
#else
        if (!BLEAdvertising.setManufacturerData(rf_company_id, rf_payload,
                                                  rf_payload_length) ||
            !BLEAdvertising.start())
        {
            fail("advertising-start");
        }
#endif
        Serial.print("M30PAIR|1|STARTED|role=");
        Serial.print(roleName());
        Serial.print("|case=");
        Serial.print(NUCODE_M30_PAIR_CASE_NAME);
        Serial.print("|round=");
        Serial.print(current_round);
        Serial.print("|io=");
        Serial.print(NUCODE_M30_PAIR_IO);
        Serial.print("|nonce=");
        Serial.println(nonce);
    }

    /** @brief Host command token과 현재 image의 round·nonce를 검증합니다. */
    bool parseCommand(char *line, char *&verb, char *&argument)
    {
        char *save = nullptr;
        char *name = ::strtok_r(line, "|", &save);
        char *revision = ::strtok_r(nullptr, "|", &save);
        verb = ::strtok_r(nullptr, "|", &save);
        char *round_text = ::strtok_r(nullptr, "|", &save);
        char *nonce_text = ::strtok_r(nullptr, "|", &save);
        argument = ::strtok_r(nullptr, "|", &save);
        char *extra = ::strtok_r(nullptr, "|", &save);
        if (name == nullptr || revision == nullptr || verb == nullptr || round_text == nullptr ||
            nonce_text == nullptr || extra != nullptr || ::strcmp(name, protocol_name) != 0 ||
            ::strcmp(revision, protocol_revision) != 0 || !validNonce(nonce_text))
        {
            return false;
        }
        char *end = nullptr;
        const unsigned long parsed_round = ::strtoul(round_text, &end, 10);
        if (end == nullptr || *end != '\0' || parsed_round < 1UL || parsed_round > 10UL)
        {
            return false;
        }
        current_round = static_cast<std::uint8_t>(parsed_round);
        ::memcpy(nonce, nonce_text, nonce_length + 1U);
        decodeRfPayload();
        return true;
    }

    /** @brief 완전한 한 줄 command를 CLEAR·START·KEY로 실행합니다. */
    void executeCommand(char *line)
    {
        char *verb = nullptr;
        char *argument = nullptr;
        if (!parseCommand(line, verb, argument))
        {
            fail("bad-command");
            return;
        }
        if (::strcmp(verb, "CLEAR") == 0 && argument == nullptr)
        {
            clearRound();
        }
        else if (::strcmp(verb, "START") == 0 && argument == nullptr)
        {
            startRound();
        }
        else if (::strcmp(verb, "KEY") == 0 && argument != nullptr &&
                 ::strlen(argument) == 6U && connection_handle.valid())
        {
            char *end = nullptr;
            const unsigned long passkey = ::strtoul(argument, &end, 10);
            if (end == nullptr || *end != '\0' || passkey > 999999UL ||
                !BLESecurity.enterPasskey(connection_handle,
                                          static_cast<std::uint32_t>(passkey)))
            {
                fail("passkey-entry");
            }
        }
        else
        {
            fail("command-state");
        }
    }

    /** @brief DAPLink UART의 newline command를 고정 buffer로 조립합니다. */
    void pollHostCommand()
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

    /** @brief central이 연결 정착 뒤 exact handle에 L4를 요청합니다. */
    void driveSecurityRequest()
    {
#if defined(NUCODE_M30_PAIR_CENTRAL)
        if (security_request_pending && k_uptime_get() >= security_request_due_ms)
        {
            security_request_pending = false;
            if (!BLESecurity.requestSecurity(connection_handle))
            {
                fail("security-request");
            }
        }
#endif
    }

} // namespace

void setup()
{
    Serial.begin(115200);
    nucode::ble::SecurityConfig security = {};
    security.minimum_level = nucode::ble::SecurityLevel::secure_connections;
    security.bonding = true;
    security.response_timeout_ms = 30000U;
    security.io_capability =
        static_cast<nucode::ble::SecurityIoCapability>(NUCODE_M30_PAIR_IO);
    BLESecurity.onEvent(onSecurityEvent);
    if (!BLESecurity.begin(security))
    {
        fail("security-begin");
        return;
    }
    BLEDevice.onEventInfo(onBleEvent);
    if (!BLEDevice.begin(
#if defined(NUCODE_M30_PAIR_CENTRAL)
            "NU54-M30-CENTRAL"
#else
            peer_name
#endif
            ))
    {
        fail("device-begin");
        return;
    }
#if defined(NUCODE_M30_PAIR_CENTRAL)
    BLEScan.onResult(onScanResult);
#else
    if (!BLEAdvertising.clear() || !BLEAdvertising.setConnectable(true) ||
        !BLEAdvertising.setFlags(BT_LE_AD_GENERAL | BT_LE_AD_NO_BREDR) ||
        !BLEAdvertising.setScanResponseName(true))
    {
        fail("advertising-config");
        return;
    }
#endif
    Serial.print("M30PAIR|1|READY|role=");
    Serial.print(roleName());
    Serial.print("|case=");
    Serial.print(NUCODE_M30_PAIR_CASE_NAME);
    Serial.print("|io=");
    Serial.print(NUCODE_M30_PAIR_IO);
    Serial.print("|bond_count=");
    Serial.println(BLESecurity.bondCount());
}

void loop()
{
    pollHostCommand();
    BLEDevice.poll();
    BLESecurity.poll();
    if (protocol_started && !protocol_failed)
    {
        driveSecurityRequest();
        reportPassIfReady();
    }
}
