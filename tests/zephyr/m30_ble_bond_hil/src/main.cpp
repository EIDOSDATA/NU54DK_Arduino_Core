/**
 * @file main.cpp
 * @brief 두 NU54DK에서 bond metadata migration·RPA 회전·stale key 거부를 검증합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <Arduino.h>
#include <NUCODE_BLE_Security.h>
#include <internal/NUCODE_BLE_Internal.h>

#include <zephyr/bluetooth/conn.h>
#include <zephyr/kernel.h>
#include <zephyr/settings/settings.h>
#include <zephyr/sys/byteorder.h>
#include <zephyr/sys/reboot.h>

#include <cstddef>
#include <cstdint>
#include <errno.h>
#include <stdlib.h>
#include <string.h>

#ifndef M30_BOND_CORE_REVISION
#error "M30_BOND_CORE_REVISION is required"
#endif

static_assert(CONFIG_BT_PRIVACY == 1);
static_assert(CONFIG_BT_RPA_TIMEOUT_DYNAMIC == 1);
static_assert(CONFIG_BT_SETTINGS == 1);
static_assert(CONFIG_BT_MAX_PAIRED == 4);

namespace
{
    constexpr char protocol[] = "M30BOND|1";
    constexpr char peer_name[] = "NU54-M30-BOND";
    constexpr char session_key[] = "m30bond/session";
    constexpr char metadata_keys[][24] = {
        "nucode/security/bond/0",
        "nucode/security/bond/1",
        "nucode/security/bond/2",
        "nucode/security/bond/3",
    };
    constexpr std::uint32_t session_magic = 0x4230334dUL;
    constexpr std::uint32_t metadata_magic = 0x32424e4dUL;
    constexpr std::size_t session_bytes = 48U;
    constexpr std::size_t nonce_characters = 32U;
    constexpr std::size_t nonce_bytes = 16U;
    constexpr std::size_t command_capacity = 128U;
    constexpr std::uint16_t company_id = 0x3054U;
    constexpr std::uint8_t required_reconnects = 20U;
    constexpr std::uint8_t required_rpa_addresses = 4U;
    constexpr std::int64_t security_delay_ms = 350;
    constexpr std::int64_t action_delay_ms = 250;
    constexpr std::int64_t protocol_timeout_ms = 900000;

    enum class Phase : std::uint8_t
    {
        idle,
        prime,
        resume,
        await_stale,
        stale,
        finished,
    };

    char nonce[nonce_characters + 1U] = {};
    std::uint8_t nonce_binary[nonce_bytes] = {};
    char command[command_capacity] = {};
    std::size_t command_length = 0U;
    Phase phase = Phase::idle;
    nucode::ble::BLEConnectionHandle connection_handle = {};
    struct k_thread *main_thread = nullptr;
    bool resume_available = false;
    bool protocol_failed = false;
    bool paired_seen = false;
    bool persistence_seen = false;
    bool secure_seen = false;
    bool verified_seen = false;
    bool link_reported = false;
    bool security_pending = false;
    bool disconnect_pending = false;
    bool restart_pending = false;
    bool reboot_pending = false;
    bool stale_rejected = false;
    bool stale_secure = false;
    bool result_reported = false;
    std::uint8_t reconnects = 0U;
    [[maybe_unused]] std::uint8_t rpa_count = 0U;
    [[maybe_unused]] nucode::ble::BLEAddress observed_rpas[required_rpa_addresses] = {};
    std::int64_t action_due_ms = 0;
    std::int64_t protocol_deadline_ms = 0;

    /** @brief compile-time image 역할 이름을 반환합니다. */
    const char *roleName()
    {
#if defined(NUCODE_M30_BOND_CENTRAL)
        return "central";
#else
        return "peripheral";
#endif
    }

    /** @brief 현재 phase 이름을 protocol용 고정 문자열로 반환합니다. */
    const char *phaseName(Phase value)
    {
        switch (value)
        {
        case Phase::prime:
            return "prime";
        case Phase::resume:
            return "resume";
        case Phase::await_stale:
            return "await-stale";
        case Phase::stale:
            return "stale";
        case Phase::finished:
            return "finished";
        default:
            return "idle";
        }
    }

    /** @brief 모든 session record에 exact nonce와 Core revision을 붙입니다. */
    void printSuffix()
    {
        Serial.print("|nonce=");
        Serial.print(nonce);
        Serial.print("|core=");
        Serial.print(M30_BOND_CORE_REVISION);
    }

    /** @brief 첫 실패만 비밀값 없이 출력하고 상태 기계를 닫습니다. */
    void fail(const char *stage, std::uint8_t reason = 0U)
    {
        if (protocol_failed)
        {
            return;
        }
        Serial.print(protocol);
        Serial.print("|FAIL|role=");
        Serial.print(roleName());
        Serial.print("|phase=");
        Serial.print(phaseName(phase));
        Serial.print("|stage=");
        Serial.print(stage == nullptr ? "unknown" : stage);
        Serial.print("|reason=");
        Serial.print(reason);
        Serial.print("|security_error=");
        Serial.print(static_cast<unsigned int>(BLESecurity.lastError()));
        Serial.print("|security_driver=");
        Serial.print(BLESecurity.lastDriverError());
        Serial.print("|ble_error=");
        Serial.print(static_cast<unsigned int>(BLEDevice.lastError()));
        Serial.print("|ble_driver=");
        Serial.print(BLEDevice.lastDriverError());
        printSuffix();
        Serial.println();
        protocol_failed = true;
    }

    /** @brief 공개 callback의 Arduino main-thread 전달 계약을 검사합니다. */
    bool callbackContextValid()
    {
        if (k_current_get() != main_thread)
        {
            fail("callback-context");
            return false;
        }
        return true;
    }

    /** @brief IEEE CRC-32를 고정 buffer에 계산합니다. */
    std::uint32_t crc32(const std::uint8_t *data, std::size_t length)
    {
        std::uint32_t crc = 0xffffffffUL;
        for (std::size_t index = 0U; index < length; ++index)
        {
            crc ^= data[index];
            for (std::uint8_t bit = 0U; bit < 8U; ++bit)
            {
                const std::uint32_t mask = 0U - (crc & 1U);
                crc = (crc >> 1U) ^ (0xedb88320UL & mask);
            }
        }
        return ~crc;
    }

    /** @brief 소문자 128-bit nonce를 binary로 변환합니다. */
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

    /** @brief warm reboot 뒤 재개할 nonce를 CRC 보호 settings record에 저장합니다. */
    bool saveSession()
    {
        std::uint8_t record[session_bytes] = {};
        sys_put_le32(session_magic, &record[0]);
        sys_put_le16(1U, &record[4]);
        sys_put_le16(static_cast<std::uint16_t>(sizeof(record)), &record[6]);
        ::memcpy(&record[8], nonce, nonce_characters);
        record[40] = 2U;
        sys_put_le32(crc32(record, 44U), &record[44]);
        return settings_save_one(session_key, record, sizeof(record)) == 0;
    }

    /** @brief 저장 session을 검사하고 migration 재개 nonce를 복원합니다. */
    bool loadSession()
    {
        std::uint8_t record[session_bytes] = {};
        const ssize_t length = settings_load_one(session_key, record, sizeof(record));
        if (length == -ENOENT)
        {
            return false;
        }
        if (length != static_cast<ssize_t>(sizeof(record)) ||
            sys_get_le32(&record[0]) != session_magic || sys_get_le16(&record[4]) != 1U ||
            sys_get_le16(&record[6]) != sizeof(record) || record[40] != 2U ||
            sys_get_le32(&record[44]) != crc32(record, 44U))
        {
            static_cast<void>(settings_delete(session_key));
            return false;
        }
        char restored[nonce_characters + 1U] = {};
        ::memcpy(restored, &record[8], nonce_characters);
        return decodeNonce(restored);
    }

    /** @brief 현재 schema-2 bond metadata 하나를 유효한 schema-1 record로 낮춥니다. */
    bool rewriteMetadataAsLegacy()
    {
        for (std::size_t index = 0U; index < ARRAY_SIZE(metadata_keys); ++index)
        {
            std::uint8_t current[22] = {};
            const ssize_t length = settings_load_one(metadata_keys[index], current,
                                                     sizeof(current));
            if (length == -ENOENT)
            {
                continue;
            }
            if (length != static_cast<ssize_t>(sizeof(current)) ||
                sys_get_le32(&current[0]) != metadata_magic ||
                sys_get_le16(&current[4]) != 2U ||
                sys_get_le32(&current[18]) != crc32(current, 18U))
            {
                return false;
            }
            std::uint8_t legacy[20] = {};
            ::memcpy(legacy, current, 16U);
            sys_put_le16(1U, &legacy[4]);
            sys_put_le32(crc32(legacy, 16U), &legacy[16]);
            return settings_save_one(metadata_keys[index], legacy, sizeof(legacy)) == 0;
        }
        return false;
    }

    /** @brief nonce가 결합된 manufacturer field인지 검사합니다. */
    [[maybe_unused]] bool validPayload(const nucode::ble::BLEScanResult &result)
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

    /** @brief 현재 nonce의 connectable legacy advertising을 시작합니다. */
    [[maybe_unused]] bool startAdvertising(bool configure)
    {
        if (configure &&
            !BLEAdvertising.setManufacturerData(company_id, nonce_binary,
                                                  sizeof(nonce_binary)))
        {
            return false;
        }
        return BLEAdvertising.start();
    }

#if defined(NUCODE_M30_BOND_CENTRAL)
    /** @brief 현재 nonce를 찾는 passive scan을 시작합니다. */
    bool startScan()
    {
        return BLEScan.clearFilters() && BLEScan.start(false);
    }

    /** @brief 중복 없는 RPA baseline+3회 주소만 고정 배열에 보존합니다. */
    void rememberRpa(const nucode::ble::BLEAddress &address)
    {
        if (address.type() != nucode::ble::BLEAddress::Type::random_address ||
            (address.data()[5] & 0xc0U) != 0x40U)
        {
            fail("non-rpa-advertiser");
            return;
        }
        for (std::uint8_t index = 0U; index < rpa_count; ++index)
        {
            if (observed_rpas[index] == address)
            {
                return;
            }
        }
        if (rpa_count < ARRAY_SIZE(observed_rpas))
        {
            observed_rpas[rpa_count++] = address;
        }
    }

    /** @brief 정확한 nonce·RPA를 가진 peer만 선택해 연결합니다. */
    void onScanResult(const nucode::ble::BLEScanResult &result, void *context)
    {
        ARG_UNUSED(context);
        if (!callbackContextValid() || protocol_failed || !result.connectable ||
            result.scan_response || !validPayload(result) || connection_handle.valid())
        {
            return;
        }
        if (phase == Phase::resume && reconnects == 0U)
        {
            rememberRpa(result.address);
            if (protocol_failed || rpa_count < required_rpa_addresses)
            {
                return;
            }
            Serial.print(protocol);
            Serial.print("|RPA|role=central|rotations=3");
            printSuffix();
            Serial.println();
        }
        if (!BLEScan.stop() || !BLEConnection.connect(result.address, connection_handle))
        {
            fail("connect");
        }
    }
#endif

    /** @brief 현재 연결이 16-byte LE Secure Connections 링크인지 확인합니다. */
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
                           information.security.level >= BT_SECURITY_L2 &&
                           (static_cast<std::uint8_t>(information.security.flags) &
                            BT_SECURITY_FLAG_SC) != 0U;
        bt_conn_unref(connection);
        return valid;
    }

    /** @brief 새 link의 volatile 판정값을 초기화합니다. */
    void resetLinkState()
    {
        connection_handle = {};
        paired_seen = false;
        persistence_seen = false;
        secure_seen = false;
        verified_seen = false;
        link_reported = false;
        security_pending = false;
        disconnect_pending = false;
    }

    /** @brief 초기 pairing 또는 restored bond link의 완료를 한 번만 보고합니다. */
    void reportLinkIfReady()
    {
        if (protocol_failed || link_reported || !secure_seen || !validSecureLink())
        {
            return;
        }
        if (phase == Phase::prime)
        {
            if (!paired_seen || !persistence_seen || !BLESecurity.paired(connection_handle) ||
                BLESecurity.bondState(connection_handle) !=
                    nucode::ble::BondState::persistence_pending)
            {
                return;
            }
            Serial.print(protocol);
            Serial.print("|PAIRED|role=");
            Serial.print(roleName());
            Serial.print("|level=2|key_size=16|sc=1|bonded=1");
            printSuffix();
            Serial.println();
            link_reported = true;
#if defined(NUCODE_M30_BOND_CENTRAL)
            disconnect_pending = true;
            action_due_ms = k_uptime_get() + action_delay_ms;
#endif
            return;
        }
        if (phase == Phase::resume)
        {
            if (!verified_seen || !BLESecurity.paired(connection_handle) ||
                BLESecurity.bondState(connection_handle) != nucode::ble::BondState::verified)
            {
                return;
            }
            ++reconnects;
            Serial.print(protocol);
            Serial.print("|RECONNECT|role=");
            Serial.print(roleName());
            Serial.print("|count=");
            Serial.print(reconnects);
            printSuffix();
            Serial.println();
            link_reported = true;
#if defined(NUCODE_M30_BOND_CENTRAL)
            disconnect_pending = true;
            action_due_ms = k_uptime_get() + action_delay_ms;
#endif
        }
    }

    /** @brief stale key 실패를 한 번 기록하고 중앙 disconnect를 예약합니다. */
    void recordStaleRejection(std::uint8_t reason)
    {
        if (phase != Phase::stale || stale_rejected || stale_secure)
        {
            return;
        }
        stale_rejected = true;
        Serial.print(protocol);
        Serial.print("|STALE_REJECTED|role=");
        Serial.print(roleName());
        Serial.print("|accepted=0|reason=");
        Serial.print(reason);
        printSuffix();
        Serial.println();
#if defined(NUCODE_M30_BOND_CENTRAL)
        disconnect_pending = true;
        action_due_ms = k_uptime_get() + action_delay_ms;
#endif
    }

    /** @brief 최종 정량값을 role별 고정 RESULT로 출력합니다. */
    void reportResult()
    {
        if (result_reported || protocol_failed || stale_secure)
        {
            return;
        }
        Serial.print(protocol);
        Serial.print("|RESULT|role=");
        Serial.print(roleName());
        Serial.print("|bonded_reconnects=");
        Serial.print(reconnects);
#if defined(NUCODE_M30_BOND_CENTRAL)
        Serial.print("|privacy_rotations=");
        Serial.print(static_cast<unsigned int>(rpa_count - 1U));
#endif
        Serial.print("|migration=");
        Serial.print(BLESecurity.bondMigrationCount());
        Serial.print("|stale_key_accepts=0|new_pairings=0|bond_count=");
        Serial.print(BLESecurity.bondCount());
        Serial.print("|callback_context=pass");
        printSuffix();
        Serial.println();
        result_reported = true;
        phase = Phase::finished;
    }

    /** @brief GAP event를 pairing·재연결·재부팅 상태 기계로 전달합니다. */
    void onBleEvent(const nucode::ble::BLEEventInfo &information, void *context)
    {
        ARG_UNUSED(context);
        if (!callbackContextValid() || protocol_failed)
        {
            return;
        }
        if (phase == Phase::finished || phase == Phase::idle || phase == Phase::await_stale)
        {
            return;
        }
        if (information.event == nucode::ble::BLEEvent::connected &&
            (phase == Phase::prime || phase == Phase::resume || phase == Phase::stale))
        {
            connection_handle = information.connection;
            if (!connection_handle.valid())
            {
                fail("connection-handle");
                return;
            }
#if defined(NUCODE_M30_BOND_CENTRAL)
            if (information.role != nucode::ble::BLELinkRole::central)
#else
            if (information.role != nucode::ble::BLELinkRole::peripheral)
#endif
            {
                fail("connection-role");
                return;
            }
#if !defined(NUCODE_M30_BOND_CENTRAL)
            if (phase == Phase::resume && reconnects == 0U &&
                !BLEPrivacy.setRotationTimeout(60U))
            {
                fail("privacy-timeout-restore");
                return;
            }
#endif
#if defined(NUCODE_M30_BOND_CENTRAL)
            security_pending = true;
            action_due_ms = k_uptime_get() + security_delay_ms;
#endif
        }
        else if (information.event == nucode::ble::BLEEvent::disconnected &&
                 connection_handle.valid())
        {
            resetLinkState();
            if (phase == Phase::prime)
            {
                if (!rewriteMetadataAsLegacy() || !saveSession())
                {
                    fail("legacy-session-save");
                    return;
                }
                Serial.print(protocol);
                Serial.print("|MIGRATE_REBOOT|role=");
                Serial.print(roleName());
                Serial.print("|schema=1|warm=1");
                printSuffix();
                Serial.println();
                reboot_pending = true;
                action_due_ms = k_uptime_get() + action_delay_ms;
            }
            else if (phase == Phase::resume)
            {
                if (reconnects < required_reconnects)
                {
                    restart_pending = true;
                    action_due_ms = k_uptime_get() + action_delay_ms;
                }
                else
                {
                    phase = Phase::await_stale;
                    Serial.print(protocol);
                    Serial.print("|RECONNECT_DONE|role=");
                    Serial.print(roleName());
                    Serial.print("|count=20");
                    printSuffix();
                    Serial.println();
                }
            }
            else if (phase == Phase::stale)
            {
                if (!stale_rejected)
                {
                    recordStaleRejection(0U);
                }
                reportResult();
            }
        }
        else if (information.event == nucode::ble::BLEEvent::error &&
                 phase != Phase::stale)
        {
            fail("gap-error");
        }
    }

    /** @brief Security event를 새 pairing·복원·stale 거부 판정으로 변환합니다. */
    void onSecurityEvent(const nucode::ble::SecurityEventRecord &event, void *context)
    {
        ARG_UNUSED(context);
        if (!callbackContextValid() || protocol_failed)
        {
            return;
        }
        if (phase == Phase::finished || phase == Phase::idle || phase == Phase::await_stale)
        {
            return;
        }
        if (event.event == nucode::ble::SecurityEvent::pairing_requested)
        {
            if (phase == Phase::prime)
            {
                if (!BLESecurity.acceptPairing(event.connection, true))
                {
                    fail("pairing-accept");
                }
            }
            else if (phase == Phase::stale)
            {
                if (!BLESecurity.acceptPairing(event.connection, false))
                {
                    fail("pairing-reject");
                    return;
                }
                recordStaleRejection(event.reason);
            }
            else
            {
                fail("unexpected-pairing");
            }
        }
        else if (event.event == nucode::ble::SecurityEvent::paired)
        {
            if (phase != Phase::prime)
            {
                fail("new-pairing");
                return;
            }
            paired_seen = true;
        }
        else if (event.event == nucode::ble::SecurityEvent::bond_persistence_pending)
        {
            persistence_seen = phase == Phase::prime;
        }
        else if (event.event == nucode::ble::SecurityEvent::bond_verified)
        {
            verified_seen = phase == Phase::resume;
        }
        else if (event.event == nucode::ble::SecurityEvent::security_changed)
        {
            if (phase == Phase::stale &&
                event.level >= nucode::ble::SecurityLevel::encrypted)
            {
                stale_secure = true;
                fail("stale-key-accepted");
                return;
            }
            secure_seen = event.level >= nucode::ble::SecurityLevel::encrypted;
        }
        else if (event.event == nucode::ble::SecurityEvent::pairing_cancelled ||
                 event.event == nucode::ble::SecurityEvent::pairing_failed ||
                 event.event == nucode::ble::SecurityEvent::timeout ||
                 event.event == nucode::ble::SecurityEvent::error)
        {
            if (phase == Phase::stale)
            {
                recordStaleRejection(event.reason);
            }
            else
            {
                fail("security-event", event.reason);
            }
        }
        reportLinkIfReady();
    }

    /** @brief central scan 결과를 phase별 privacy/connect 동작으로 전달합니다. */
#if defined(NUCODE_M30_BOND_CENTRAL)
    void handleScanResult(const nucode::ble::BLEScanResult &result, void *context)
    {
        onScanResult(result, context);
    }
#endif

    /** @brief START 명령의 exact nonce와 revision을 검사합니다. */
    bool parseStart(const char *line, char parsed_nonce[nonce_characters + 1U])
    {
        constexpr char prefix[] = "M30BOND|1|START|nonce=";
        const std::size_t prefix_length = sizeof(prefix) - 1U;
        if (::strncmp(line, prefix, prefix_length) != 0)
        {
            return false;
        }
        const char *value = line + prefix_length;
        constexpr char core_marker[] = "|core=";
        if (::strlen(value) != nonce_characters + sizeof(core_marker) - 1U + 40U ||
            ::strncmp(value + nonce_characters, core_marker,
                      sizeof(core_marker) - 1U) != 0 ||
            ::strcmp(value + nonce_characters + sizeof(core_marker) - 1U,
                     M30_BOND_CORE_REVISION) != 0)
        {
            return false;
        }
        ::memcpy(parsed_nonce, value, nonce_characters);
        parsed_nonce[nonce_characters] = '\0';
        return true;
    }

    /** @brief clean 또는 migrated session의 phase를 시작합니다. */
    void startProtocol(const char *line)
    {
        char parsed_nonce[nonce_characters + 1U] = {};
        if (!parseStart(line, parsed_nonce))
        {
            fail("start-command");
            return;
        }
        if (resume_available)
        {
            if (::strcmp(parsed_nonce, nonce) != 0 || BLESecurity.bondCount() != 1U ||
                BLESecurity.bondMigrationCount() != 1U ||
                BLESecurity.rejectedBondCount() != 0U)
            {
                fail("resume-contract");
                return;
            }
            phase = Phase::resume;
        }
        else
        {
            if (!decodeNonce(parsed_nonce) || BLESecurity.bondCount() != 0U)
            {
                fail("clean-contract");
                return;
            }
            phase = Phase::prime;
        }
        protocol_deadline_ms = k_uptime_get() + protocol_timeout_ms;
        Serial.print(protocol);
        Serial.print("|BEGIN|role=");
        Serial.print(roleName());
        Serial.print("|phase=");
        Serial.print(phaseName(phase));
        printSuffix();
        Serial.println();

#if defined(NUCODE_M30_BOND_CENTRAL)
        if (!startScan())
        {
            fail("scan-start");
            return;
        }
        Serial.print(protocol);
        Serial.print("|SCAN|role=central|phase=");
        Serial.print(phaseName(phase));
#else
        if (phase == Phase::resume && !BLEPrivacy.setRotationTimeout(1U))
        {
            fail("privacy-timeout");
            return;
        }
        if (!startAdvertising(true))
        {
            fail("advertising-start");
            return;
        }
        Serial.print(protocol);
        Serial.print("|ADVERTISE|role=peripheral|phase=");
        Serial.print(phaseName(phase));
#endif
        printSuffix();
        Serial.println();
    }

    /** @brief RESET·READY·START·stale 명령을 exact 상태에 적용합니다. */
    void executeCommand(const char *line)
    {
        constexpr char reset[] = "M30BOND|1|RESET|core=" M30_BOND_CORE_REVISION;
        if (::strcmp(line, reset) == 0)
        {
            if (!BLESecurity.eraseAllBonds())
            {
                fail("reset-bonds");
                return;
            }
            static_cast<void>(settings_delete(session_key));
            Serial.print(protocol);
            Serial.print("|RESETTING|role=");
            Serial.print(roleName());
            Serial.print("|warm=1|core=");
            Serial.println(M30_BOND_CORE_REVISION);
            reboot_pending = true;
            action_due_ms = k_uptime_get() + action_delay_ms;
            return;
        }
        if (::strcmp(line, "M30BOND|1|READY?") == 0)
        {
            Serial.print(protocol);
            Serial.print("|READY|role=");
            Serial.print(roleName());
            Serial.print("|stage=");
            Serial.print(resume_available ? "resume" : "clean");
            Serial.print("|bonds=");
            Serial.print(BLESecurity.bondCount());
            Serial.print("|migrations=");
            Serial.print(BLESecurity.bondMigrationCount());
            Serial.print("|rejected=");
            Serial.print(BLESecurity.rejectedBondCount());
            Serial.print("|core=");
            Serial.println(M30_BOND_CORE_REVISION);
            return;
        }
        constexpr char start_marker[] = "M30BOND|1|START|";
        if (::strncmp(line, start_marker, sizeof(start_marker) - 1U) == 0 &&
            phase == Phase::idle)
        {
            startProtocol(line);
            return;
        }
        if (::strcmp(line, "M30BOND|1|ERASE_STALE") == 0 &&
            phase == Phase::await_stale)
        {
#if defined(NUCODE_M30_BOND_CENTRAL)
            fail("erase-role");
#else
            if (!BLESecurity.eraseAllBonds() || BLESecurity.bondCount() != 0U)
            {
                fail("erase-stale");
                return;
            }
            Serial.print(protocol);
            Serial.print("|STALE_ERASED|role=peripheral|bond_count=0");
            printSuffix();
            Serial.println();
#endif
            return;
        }
        if (::strcmp(line, "M30BOND|1|STALE") == 0 && phase == Phase::await_stale)
        {
            phase = Phase::stale;
#if defined(NUCODE_M30_BOND_CENTRAL)
            if (!startScan())
            {
                fail("stale-scan");
                return;
            }
            Serial.print(protocol);
            Serial.print("|SCAN|role=central|phase=stale");
#else
            if (!startAdvertising(false))
            {
                fail("stale-advertising");
                return;
            }
            Serial.print(protocol);
            Serial.print("|ADVERTISE|role=peripheral|phase=stale");
#endif
            printSuffix();
            Serial.println();
            return;
        }
        fail("command-state");
    }

    /** @brief VCOM newline 명령을 고정 buffer로 조립합니다. */
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

    /** @brief main-thread 지연 동작을 우선순위 순서로 실행합니다. */
    void driveActions()
    {
        const std::int64_t now = k_uptime_get();
        if (reboot_pending && now >= action_due_ms)
        {
            sys_reboot(SYS_REBOOT_WARM);
            return;
        }
        if (protocol_deadline_ms != 0 && now >= protocol_deadline_ms)
        {
            fail("protocol-timeout");
            return;
        }
        if (security_pending && now >= action_due_ms)
        {
            security_pending = false;
            if (!BLESecurity.requestSecurity(connection_handle))
            {
                if (phase == Phase::stale)
                {
                    recordStaleRejection(0U);
                    disconnect_pending = true;
                    action_due_ms = now + action_delay_ms;
                }
                else
                {
                    fail("security-request");
                }
            }
            return;
        }
        if (disconnect_pending && now >= action_due_ms)
        {
            disconnect_pending = false;
            if (connection_handle.valid() && !BLEConnection.disconnect(connection_handle))
            {
                fail("disconnect");
            }
            return;
        }
        if (restart_pending && now >= action_due_ms)
        {
            restart_pending = false;
#if defined(NUCODE_M30_BOND_CENTRAL)
            if (!startScan())
            {
                fail("reconnect-scan");
            }
#else
            if (!startAdvertising(false))
            {
                fail("reconnect-advertising");
            }
#endif
        }
    }
} // namespace

void setup()
{
    main_thread = k_current_get();
    Serial.begin(115200);

    nucode::ble::SecurityConfig security = {};
    security.minimum_level = nucode::ble::SecurityLevel::encrypted;
    security.bonding = true;
    security.io_capability = nucode::ble::SecurityIoCapability::no_input_output;
    security.bond_database_revision = 1U;
    BLESecurity.onEvent(onSecurityEvent);
    if (!BLESecurity.begin(security))
    {
        fail("security-begin");
        return;
    }
    BLEDevice.onEventInfo(onBleEvent);
    if (!BLEDevice.begin(
#if defined(NUCODE_M30_BOND_CENTRAL)
            "NU54-M30-BOND-C"
#else
            peer_name
#endif
            ))
    {
        fail("device-begin");
        return;
    }
#if defined(NUCODE_M30_BOND_CENTRAL)
    BLEScan.onResult(handleScanResult);
#else
    if (!BLEAdvertising.clear() || !BLEAdvertising.setConnectable(true) ||
        !BLEAdvertising.setFlags(BT_LE_AD_GENERAL | BT_LE_AD_NO_BREDR) ||
        !BLEAdvertising.setScanResponseName(true))
    {
        fail("advertising-config");
        return;
    }
#endif
    resume_available = loadSession();
}

void loop()
{
    pollCommand();
    BLEDevice.poll();
    BLESecurity.poll();
    reportLinkIfReady();
    driveActions();
}
