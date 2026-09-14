/**
 * @file main.cpp
 * @brief DAPLink VCOM으로 교환한 SC OOB record를 두 NU54DK pairing에 주입합니다.
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
    constexpr char protocol_name[] = "M30OOB";
    constexpr char protocol_revision[] = "1";
    constexpr char peer_name[] = "NU54-M30-OOB";
    constexpr std::size_t nonce_characters = 32U;
    constexpr std::size_t nonce_bytes = 16U;
    constexpr std::size_t frame_hex_characters = nucode::ble::OobFrameCodec::frame_bytes * 2U;
    constexpr std::size_t command_capacity = 256U;
    constexpr std::uint16_t rf_company_id = 0x3054U;
    constexpr std::int64_t security_request_delay_ms = 500;

    char nonce[nonce_characters + 1U] = {};
    std::uint8_t nonce_binary[nonce_bytes] = {};
    char command[command_capacity] = {};
    std::size_t command_length = 0U;
    std::uint8_t current_round = 0U;
    nucode::ble::BLEConnectionHandle connection_handle = {};
    bool protocol_started = false;
    bool protocol_failed = false;
    bool clearing = false;
    bool connection_attempted = false;
    bool security_request_pending = false;
    bool local_ready = false;
    bool remote_ready = false;
    bool oob_applied = false;
    bool paired_seen = false;
    bool persistence_pending_seen = false;
    bool secure_seen = false;
    bool pass_reported = false;
    bool remote_pairing_address_ready = false;
    nucode::ble::PeerAddress remote_pairing_address = {};
    const char *failure_reason = nullptr;
    std::uint8_t authentication_reason = 0U;
    std::int64_t security_request_due_ms = 0;

    /** @brief compile-time image 역할 이름을 반환합니다. */
    const char *roleName()
    {
#if defined(NUCODE_M30_OOB_CENTRAL)
        return "central";
#else
        return "peripheral";
#endif
    }

    /** @brief compile-time image 역할을 공개 OOB enum으로 반환합니다. */
    nucode::ble::OobRole localRole()
    {
#if defined(NUCODE_M30_OOB_CENTRAL)
        return nucode::ble::OobRole::central;
#else
        return nucode::ble::OobRole::peripheral;
#endif
    }

    /** @brief 최초 실패를 보존하고 비밀값 없이 진단합니다. */
    void fail(const char *reason)
    {
        if (!protocol_failed)
        {
            failure_reason = reason;
            Serial.print("M30OOB|1|FAIL|role=");
            Serial.print(roleName());
            Serial.print("|round=");
            Serial.print(current_round);
            Serial.print("|reason=");
            Serial.print(reason == nullptr ? "unknown" : reason);
            Serial.print("|security_error=");
            Serial.print(static_cast<unsigned int>(BLESecurity.lastError()));
            Serial.print("|driver_error=");
            Serial.print(BLESecurity.lastDriverError());
            Serial.print("|authentication_reason=");
            Serial.print(authentication_reason);
            Serial.print("|ble_error=");
            Serial.print(static_cast<unsigned int>(BLEDevice.lastError()));
            Serial.print("|ble_driver_error=");
            Serial.print(BLEDevice.lastDriverError());
            Serial.print("|nonce=");
            Serial.println(nonce);
        }
        protocol_failed = true;
    }

    /** @brief nonce와 image 기능을 결합한 READY를 출력합니다. */
    void reportReady()
    {
        Serial.print("M30OOB|1|READY|role=");
        Serial.print(roleName());
        Serial.print("|round=");
        Serial.print(current_round);
        Serial.print("|frame_bytes=");
        Serial.print(nucode::ble::OobFrameCodec::frame_bytes);
        Serial.print("|ndef_enabled=");
        Serial.print(nucode::ble::OobNdefAdapter::enabled() ? 1 : 0);
        Serial.print("|bond_count=");
        Serial.print(BLESecurity.bondCount());
        Serial.print("|nonce=");
        Serial.println(nonce);
    }

    /** @brief 소문자 hex 문자인지 확인합니다. */
    bool validHex(const char *value, std::size_t length)
    {
        if (value == nullptr || ::strlen(value) != length)
        {
            return false;
        }
        for (std::size_t index = 0U; index < length; ++index)
        {
            if (!((value[index] >= '0' && value[index] <= '9') ||
                  (value[index] >= 'a' && value[index] <= 'f')))
            {
                return false;
            }
        }
        return true;
    }

    /** @brief hex 문자 하나를 nibble로 변환합니다. */
    std::uint8_t hexNibble(char value)
    {
        if (value <= '9')
        {
            return static_cast<std::uint8_t>(value - '0');
        }
        return static_cast<std::uint8_t>(value - 'a' + 10);
    }

    /** @brief 고정 길이 hex를 byte 배열로 변환합니다. */
    bool decodeHex(const char *input, std::size_t characters, std::uint8_t *output,
                   std::size_t capacity)
    {
        if (!validHex(input, characters) || output == nullptr || capacity * 2U != characters)
        {
            return false;
        }
        for (std::size_t index = 0U; index < capacity; ++index)
        {
            output[index] = static_cast<std::uint8_t>(
                (hexNibble(input[index * 2U]) << 4U) | hexNibble(input[index * 2U + 1U]));
        }
        return true;
    }

    /** @brief byte 배열을 소문자 hex로 VCOM에 기록합니다. */
    void printHex(const std::uint8_t *data, std::size_t length)
    {
        constexpr char digits[] = "0123456789abcdef";
        for (std::size_t index = 0U; index < length; ++index)
        {
            Serial.print(digits[data[index] >> 4U]);
            Serial.print(digits[data[index] & 0x0fU]);
        }
    }

    /** @brief 한 round의 volatile 상태를 초기화합니다. */
    void resetRoundState()
    {
        connection_handle = {};
        protocol_started = false;
        protocol_failed = false;
        clearing = false;
        connection_attempted = false;
        security_request_pending = false;
        local_ready = false;
        remote_ready = false;
        oob_applied = false;
        paired_seen = false;
        persistence_pending_seen = false;
        secure_seen = false;
        pass_reported = false;
        remote_pairing_address_ready = false;
        remote_pairing_address = {};
        failure_reason = nullptr;
        authentication_reason = 0U;
        security_request_due_ms = 0;
    }

    /** @brief local OOB 생성과 frame/NDEF round-trip 뒤 raw frame을 Host에 전달합니다. */
    void prepareLocal()
    {
        nucode::ble::SecureConnectionsOobRecord local = {};
        if (!BLESecurity.createLocalOob(localRole(), nonce_binary, sizeof(nonce_binary), local))
        {
            fail("local-oob");
            return;
        }
        std::uint8_t frame[nucode::ble::OobFrameCodec::frame_bytes] = {};
        std::size_t frame_length = 0U;
        if (!nucode::ble::OobFrameCodec::encode(local, frame, sizeof(frame), frame_length))
        {
            fail("frame-encode");
            return;
        }
        std::uint8_t ndef[nucode::ble::OobNdefAdapter::maximum_ndef_bytes] = {};
        std::size_t ndef_length = 0U;
        nucode::ble::SecureConnectionsOobRecord decoded = {};
        if (!nucode::ble::OobNdefAdapter::encode(local, ndef, sizeof(ndef), ndef_length) ||
            !nucode::ble::OobNdefAdapter::decode(ndef, ndef_length, decoded) ||
            ::memcmp(&local, &decoded, sizeof(local)) != 0)
        {
            fail("ndef-roundtrip");
            return;
        }
        local_ready = true;
        Serial.print("M30OOB|1|LOCAL|role=");
        Serial.print(roleName());
        Serial.print("|round=");
        Serial.print(current_round);
        Serial.print("|frame=");
        printHex(frame, frame_length);
        Serial.print("|nonce=");
        Serial.println(nonce);
    }

    /** @brief remote frame을 decode하고 예상 negative 또는 정상 결합을 판정합니다. */
    void acceptRemote(const char *frame_hex, bool expected_rejection)
    {
        std::uint8_t frame[nucode::ble::OobFrameCodec::frame_bytes] = {};
        nucode::ble::SecureConnectionsOobRecord remote = {};
        const bool decoded = decodeHex(frame_hex, frame_hex_characters, frame, sizeof(frame)) &&
                             nucode::ble::OobFrameCodec::decode(frame, sizeof(frame), remote);
        const bool accepted = decoded && BLESecurity.setRemoteOob(localRole(), remote);
        if (expected_rejection)
        {
            if (accepted)
            {
                fail("mismatch-accepted");
                return;
            }
            Serial.print("M30OOB|1|REJECTED|role=");
            Serial.print(roleName());
            Serial.print("|round=");
            Serial.print(current_round);
            Serial.print("|class=crc|nonce=");
            Serial.println(nonce);
            return;
        }
        if (!accepted)
        {
            fail("remote-oob");
            return;
        }
        remote_ready = true;
        remote_pairing_address = remote.pairing_address;
        remote_pairing_address_ready = true;
        Serial.print("M30OOB|1|ARMED|role=");
        Serial.print(roleName());
        Serial.print("|round=");
        Serial.print(current_round);
        Serial.print("|nonce=");
        Serial.println(nonce);
    }

    /** @brief actual link의 key size와 SC/OOB flag를 확인합니다. */
    bool validSecureLink()
    {
        struct bt_conn *connection = nucode::ble::internal::referenceConnection(connection_handle);
        if (connection == nullptr)
        {
            return false;
        }
        struct bt_conn_info information = {};
        const bool valid = bt_conn_get_info(connection, &information) == 0 &&
                           information.security.enc_key_size == 16U &&
                           information.security.level == BT_SECURITY_L4 &&
                           (static_cast<std::uint8_t>(information.security.flags) &
                            BT_SECURITY_FLAG_SC) != 0U &&
                           (static_cast<std::uint8_t>(information.security.flags) &
                            BT_SECURITY_FLAG_OOB) != 0U;
        bt_conn_unref(connection);
        return valid;
    }

    /** @brief 모든 OOB·L4·bond 조건이 충족된 양쪽에 PASS를 출력합니다. */
    void reportPassIfReady()
    {
        if (pass_reported || protocol_failed || !oob_applied || !paired_seen ||
            !persistence_pending_seen || !secure_seen)
        {
            return;
        }
        if (!validSecureLink() || !BLESecurity.paired(connection_handle) ||
            BLESecurity.currentLevel(connection_handle) !=
                nucode::ble::SecurityLevel::secure_connections ||
            BLESecurity.bondState(connection_handle) !=
                nucode::ble::BondState::persistence_pending)
        {
            fail("secure-link");
            return;
        }
        Serial.print("M30OOB|1|PASS|role=");
        Serial.print(roleName());
        Serial.print("|round=");
        Serial.print(current_round);
        Serial.print("|method=oob|level=4|key_size=16|sc=1|oob=1|nonce=");
        Serial.println(nonce);
        pass_reported = true;
    }

    /** @brief exact generation의 security event만 OOB 판정에 반영합니다. */
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
        case nucode::ble::SecurityEvent::oob_data_applied:
            oob_applied = true;
            break;
        case nucode::ble::SecurityEvent::paired:
            paired_seen = true;
            break;
        case nucode::ble::SecurityEvent::bond_persistence_pending:
            persistence_pending_seen = true;
            break;
        case nucode::ble::SecurityEvent::security_changed:
            secure_seen = event.level == nucode::ble::SecurityLevel::secure_connections;
            if (!secure_seen)
            {
                fail("security-level");
            }
            break;
        case nucode::ble::SecurityEvent::oob_data_rejected:
            authentication_reason = event.reason;
            fail("oob-rejected");
            break;
        case nucode::ble::SecurityEvent::pairing_requested:
        case nucode::ble::SecurityEvent::passkey_display:
        case nucode::ble::SecurityEvent::passkey_input_requested:
        case nucode::ble::SecurityEvent::passkey_confirmation_requested:
        case nucode::ble::SecurityEvent::pairing_failed:
        case nucode::ble::SecurityEvent::timeout:
        case nucode::ble::SecurityEvent::error:
            fail("authentication");
            break;
        default:
            break;
        }
        reportPassIfReady();
    }

    /** @brief GAP event를 exact handle과 central security 요청에 연결합니다. */
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
#if defined(NUCODE_M30_OOB_CENTRAL)
            if (information.role != nucode::ble::BLELinkRole::central)
#else
            if (information.role != nucode::ble::BLELinkRole::peripheral)
#endif
            {
                fail("connection-role");
                return;
            }
#if defined(NUCODE_M30_OOB_CENTRAL)
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

#if defined(NUCODE_M30_OOB_CENTRAL)
    /** @brief scan payload가 현재 session nonce를 정확히 포함하는지 검사합니다. */
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
                field_length == nonce_bytes + 3U)
            {
                const std::uint8_t *value = &result.payload[cursor + 2U];
                return value[0] == static_cast<std::uint8_t>(rf_company_id & 0xffU) &&
                       value[1] == static_cast<std::uint8_t>(rf_company_id >> 8U) &&
                       ::memcmp(&value[2], nonce_binary, sizeof(nonce_binary)) == 0;
            }
            cursor += field_length + 1U;
        }
        return false;
    }

    /** @brief nonce가 일치하는 connectable peer에 한 번만 연결합니다. */
    void onScanResult(const nucode::ble::BLEScanResult &result, void *context)
    {
        ARG_UNUSED(context);
        if (!protocol_started || protocol_failed || connection_attempted || !result.connectable ||
            result.scan_response || !validRfBinding(result))
        {
            return;
        }
        const std::uint8_t expected_type =
            result.address.type() == nucode::ble::BLEAddress::Type::public_address
                ? BT_ADDR_LE_PUBLIC
                : BT_ADDR_LE_RANDOM;
        if (!remote_pairing_address_ready || remote_pairing_address.type != expected_type ||
            ::memcmp(remote_pairing_address.value, result.address.data(),
                     sizeof(remote_pairing_address.value)) != 0)
        {
            fail("scan-address-mismatch");
            return;
        }
        connection_attempted = true;
        static_cast<void>(BLEScan.stop());
        if (!BLEConnection.connect(result.address))
        {
            fail("connect-start");
        }
    }
#endif

    /** @brief 현재 역할의 광고 또는 scan을 시작합니다. */
    void startRound()
    {
        if (!local_ready || !remote_ready)
        {
            fail("oob-not-ready");
            return;
        }
        protocol_started = true;
        clearing = false;
#if defined(NUCODE_M30_OOB_CENTRAL)
        if (!BLEScan.clearFilters() || !BLEScan.start(true))
        {
            fail("scan-start");
            return;
        }
#else
        if (!BLEAdvertising.setManufacturerData(rf_company_id, nonce_binary,
                                                  sizeof(nonce_binary)) ||
            !BLEAdvertising.start())
        {
            fail("advertising-start");
            return;
        }
#endif
        Serial.print("M30OOB|1|STARTED|role=");
        Serial.print(roleName());
        Serial.print("|round=");
        Serial.print(current_round);
        Serial.print("|nonce=");
        Serial.println(nonce);
    }

    /** @brief 연결·광고·scan·bond·volatile OOB를 다음 round 전에 정리합니다. */
    void clearRound()
    {
        protocol_started = false;
        clearing = true;
#if defined(NUCODE_M30_OOB_CENTRAL)
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
        if (!BLESecurity.eraseAllBonds() || !BLESecurity.clearOob(localRole()))
        {
            fail("clear");
            return;
        }
        resetRoundState();
        Serial.print("M30OOB|1|CLEARED|role=");
        Serial.print(roleName());
        Serial.print("|round=");
        Serial.print(current_round);
        Serial.print("|bond_count=");
        Serial.print(BLESecurity.bondCount());
        Serial.print("|nonce=");
        Serial.println(nonce);
    }

    /** @brief Host command의 protocol·round·nonce·선택 인자를 분리합니다. */
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
            ::strcmp(revision, protocol_revision) != 0 ||
            !validHex(nonce_text, nonce_characters))
        {
            return false;
        }
        char *end = nullptr;
        const unsigned long round = ::strtoul(round_text, &end, 10);
        if (end == nullptr || *end != '\0' || round < 1UL || round > 20UL ||
            !decodeHex(nonce_text, nonce_characters, nonce_binary, sizeof(nonce_binary)))
        {
            return false;
        }
        current_round = static_cast<std::uint8_t>(round);
        ::memcpy(nonce, nonce_text, sizeof(nonce));
        return true;
    }

    /** @brief 완전한 command 한 줄을 상태 기계에 적용합니다. */
    void executeCommand(char *line)
    {
        char *verb = nullptr;
        char *argument = nullptr;
        if (!parseCommand(line, verb, argument))
        {
            fail("bad-command");
            return;
        }
        if (::strcmp(verb, "IDENTIFY") == 0 && argument == nullptr)
        {
            if (protocol_failed)
            {
                fail(failure_reason);
            }
            else
            {
                reportReady();
            }
        }
        else if (::strcmp(verb, "CLEAR") == 0 && argument == nullptr)
        {
            clearRound();
        }
        else if (::strcmp(verb, "PREPARE") == 0 && argument == nullptr)
        {
            prepareLocal();
        }
        else if (::strcmp(verb, "REJECT") == 0 && argument != nullptr)
        {
            acceptRemote(argument, true);
        }
        else if (::strcmp(verb, "REMOTE") == 0 && argument != nullptr)
        {
            acceptRemote(argument, false);
        }
        else if (::strcmp(verb, "START") == 0 && argument == nullptr)
        {
            startRound();
        }
        else
        {
            fail("command-state");
        }
    }

    /** @brief DAPLink VCOM newline command를 고정 buffer로 조립합니다. */
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

    /** @brief central 연결 정착 뒤 exact handle에 L4를 요청합니다. */
    void driveSecurityRequest()
    {
#if defined(NUCODE_M30_OOB_CENTRAL)
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
    security.io_capability = nucode::ble::SecurityIoCapability::no_input_output;
    security.secure_connections_oob = true;
    BLESecurity.onEvent(onSecurityEvent);
    if (!BLESecurity.begin(security))
    {
        fail("security-begin");
        return;
    }
    BLEDevice.onEventInfo(onBleEvent);
    if (!BLEDevice.begin(
#if defined(NUCODE_M30_OOB_CENTRAL)
            "NU54-M30-OOB-C"
#else
            peer_name
#endif
            ))
    {
        fail("device-begin");
        return;
    }
#if defined(NUCODE_M30_OOB_CENTRAL)
    BLEScan.onResult(onScanResult);
#else
    if (!BLEAdvertising.clear() || !BLEAdvertising.setConnectable(true) ||
        !BLEAdvertising.setFlags(BT_LE_AD_GENERAL | BT_LE_AD_NO_BREDR) ||
        !BLEAdvertising.setScanResponseName(true))
    {
        fail("advertising-config");
    }
#endif
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
