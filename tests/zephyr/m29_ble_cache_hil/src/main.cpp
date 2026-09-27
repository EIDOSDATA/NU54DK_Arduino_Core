/**
 * @file main.cpp
 * @brief 두 NU54DK로 M29-W05 robust GATT cache와 database migration을 검증합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <Arduino.h>
#include <NUCODE_BLE.h>
#include <internal/NUCODE_BLE_Internal.h>

#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/conn.h>
#include <zephyr/bluetooth/gatt.h>
#include <zephyr/kernel.h>
#include <zephyr/settings/settings.h>
#include <zephyr/sys/reboot.h>

#include <cstddef>
#include <cstdint>
#include <errno.h>
#include <string.h>

#ifndef M29_CACHE_CORE_REVISION
#error "M29_CACHE_CORE_REVISION is required"
#endif

static_assert(CONFIG_BT_GATT_SERVICE_CHANGED == 1);
static_assert(CONFIG_BT_GATT_CACHING == 1);
static_assert(CONFIG_BT_SETTINGS == 1);
static_assert(CONFIG_BT_MAX_CONN == 2);

namespace
{

    constexpr char protocol[] = "M29W05|1";
    constexpr char ready_query[] = "M29W05|1|READY?";
    constexpr char reset_command[] = "M29W05|1|RESET|core=" M29_CACHE_CORE_REVISION;
    constexpr char start_prefix[] = "M29W05|1|START|nonce=";
    constexpr char core_field[] = "|core=";
    constexpr char peer_name[] = "NU54-M29-CACHE";
    constexpr char service_text[] = "8e7e2950-7d8c-4c1a-9d2d-8b6519f77410";
    constexpr char characteristic_text[] = "8e7e2951-7d8c-4c1a-9d2d-8b6519f77410";
    constexpr char dummy_text[] = "8e7e2952-7d8c-4c1a-9d2d-8b6519f77410";
    constexpr char stage_key[] = "m29w05/server_stage";
    constexpr char session_key[] = "m29w05/session";
    constexpr char resume_key[] = "m29w05/resume";
    constexpr char cache_keys[][20] = {
        "nucode/gatt/cache/0",
        "nucode/gatt/cache/1",
        "nucode/gatt/cache/2",
        "nucode/gatt/cache/3",
    };
    constexpr std::size_t nonce_text_length = 32U;
    constexpr std::size_t nonce_binary_length = 16U;
    constexpr std::size_t value_length = 16U;
    constexpr std::uint16_t cache_schema_version = 1U;
    constexpr std::uint16_t required_reconnects = 20U;
    constexpr std::int64_t protocol_timeout_ms = 600000;
    constexpr std::int64_t server_action_delay_ms = 500;
    constexpr std::uint32_t session_magic = 0x3530574dU;
    constexpr std::uint32_t resume_magic = 0x3552574dU;
    constexpr std::size_t session_record_length = 48U;
    constexpr std::size_t resume_record_length = 60U;

    const nucode::ble::BLEUuid service_uuid(service_text);
    const nucode::ble::BLEUuid characteristic_uuid(characteristic_text);
    const nucode::ble::BLEUuid dummy_uuid(dummy_text);
    nucode::ble::BLEService test_service(service_uuid);
    nucode::ble::BLECharacteristic dummy_characteristic(
        dummy_uuid, nucode::ble::BLEProperty::read, nucode::ble::BLEPermission::read,
        value_length);
    nucode::ble::BLECharacteristic test_characteristic(
        characteristic_uuid,
        nucode::ble::BLEProperty::read | nucode::ble::BLEProperty::write,
        nucode::ble::BLEPermission::read | nucode::ble::BLEPermission::write,
        value_length);

    char nonce[nonce_text_length + 1U] = {};
    std::uint8_t nonce_binary[nonce_binary_length] = {};
    char command[128] = {};
    std::size_t command_length = 0U;
    bool protocol_started = false;
    bool protocol_finished = false;
    bool callback_context_valid = true;
    std::uint8_t database_stage = 1U;
    std::uint8_t service_changed_requests = 0U;
    std::uint8_t migration_requests = 0U;
    std::int64_t protocol_deadline = 0;
    struct k_thread *setup_thread = nullptr;
    nucode::ble::BLEConnectionHandle connection_handle;

    /** @brief 중앙 role의 cache·재접속·재부팅 진행 단계입니다. */
    enum class CentralStage : std::uint8_t
    {
        idle,
        prime,
        waiting_service_changed,
        service_changed_rediscovery,
        restoring,
        waiting_migration_reboot,
        migration,
        preparing_corrupt_reboot,
        corrupt,
        finishing,
    };

#if defined(NUCODE_M29_CACHE_CENTRAL)
    CentralStage central_stage = CentralStage::idle;
    bool scan_pending = false;
    bool security_requested = false;
    bool cache_started = false;
    std::uint8_t security_attempts = 0U;
    std::uint16_t reconnects = 0U;
    std::uint16_t old_value_handle = 0U;
    std::uint16_t new_value_handle = 0U;
    std::uint16_t hash_reads = 0U;
    std::uint16_t cache_saves = 0U;
    std::uint16_t cache_restores = 0U;
    std::uint16_t cache_invalidations = 0U;
    std::uint16_t service_changed_events = 0U;
#else
    enum class ServerAction : std::uint8_t
    {
        none,
        service_changed,
        migrate,
        finish,
    };

    ServerAction server_action = ServerAction::none;
    std::int64_t server_action_due = 0;
    bool restart_advertising = false;
    bool extra_service_registered = false;
    struct bt_uuid_128 extra_service_uuid = {};
    struct bt_gatt_attr extra_service_attribute = {};
    struct bt_gatt_service extra_service = {};
#endif

    /** @brief little-endian 16-bit 값을 고정 record에 기록합니다. */
    void putLe16(std::uint8_t *output, std::uint16_t value)
    {
        output[0] = static_cast<std::uint8_t>(value & 0xffU);
        output[1] = static_cast<std::uint8_t>((value >> 8U) & 0xffU);
    }

    /** @brief little-endian 32-bit 값을 고정 record에 기록합니다. */
    void putLe32(std::uint8_t *output, std::uint32_t value)
    {
        output[0] = static_cast<std::uint8_t>(value & 0xffU);
        output[1] = static_cast<std::uint8_t>((value >> 8U) & 0xffU);
        output[2] = static_cast<std::uint8_t>((value >> 16U) & 0xffU);
        output[3] = static_cast<std::uint8_t>((value >> 24U) & 0xffU);
    }

    /** @brief 고정 record에서 little-endian 16-bit 값을 읽습니다. */
    std::uint16_t getLe16(const std::uint8_t *input)
    {
        return static_cast<std::uint16_t>(input[0]) |
               (static_cast<std::uint16_t>(input[1]) << 8U);
    }

    /** @brief 고정 record에서 little-endian 32-bit 값을 읽습니다. */
    std::uint32_t getLe32(const std::uint8_t *input)
    {
        return static_cast<std::uint32_t>(input[0]) |
               (static_cast<std::uint32_t>(input[1]) << 8U) |
               (static_cast<std::uint32_t>(input[2]) << 16U) |
               (static_cast<std::uint32_t>(input[3]) << 24U);
    }

    /** @brief settings 시험 record의 IEEE CRC32를 계산합니다. */
    std::uint32_t crc32(const std::uint8_t *data, std::size_t length)
    {
        std::uint32_t value = 0xffffffffU;
        for (std::size_t index = 0U; index < length; ++index)
        {
            value ^= data[index];
            for (std::uint8_t bit = 0U; bit < 8U; ++bit)
            {
                const std::uint32_t mask = 0U - (value & 1U);
                value = (value >> 1U) ^ (0xedb88320U & mask);
            }
        }
        return value ^ 0xffffffffU;
    }

    /** @brief 현재 image의 고정 role 이름을 반환합니다. */
    const char *roleName()
    {
#if defined(NUCODE_M29_CACHE_CENTRAL)
        return "central";
#else
        return "peripheral";
#endif
    }

    /** @brief 모든 검증 record에 nonce와 exact Core revision을 붙입니다. */
    void printSuffix()
    {
        Serial.print("|nonce=");
        Serial.print(nonce);
        Serial.print("|core=");
        Serial.print(M29_CACHE_CORE_REVISION);
    }

    /** @brief 첫 실패를 고정 protocol로 출력하고 추가 동작을 중단합니다. */
    void fail(const char *stage, int code = 0, int ble_error = -1)
    {
        if (protocol_finished)
        {
            return;
        }
        Serial.print(protocol);
        Serial.print("|FAIL|role=");
        Serial.print(roleName());
        Serial.print("|stage=");
        Serial.print(stage == nullptr ? "unknown" : stage);
        if (ble_error >= 0)
        {
            Serial.print("|ble_error=");
            Serial.print(ble_error);
        }
        Serial.print("|code=");
        Serial.print(code);
        printSuffix();
        Serial.println();
        protocol_finished = true;
    }

    /** @brief 공개 callback이 Arduino main thread에서 실행됐는지 확인합니다. */
    void checkCallbackContext()
    {
        if (k_current_get() != setup_thread)
        {
            callback_context_valid = false;
            fail("callback_context");
        }
    }

    /** @brief 소문자 hexadecimal nibble을 binary 값으로 변환합니다. */
    std::uint8_t hexNibble(char value)
    {
        return static_cast<std::uint8_t>(value <= '9' ? value - '0' : value - 'a' + 10);
    }

    /** @brief 현재 nonce를 128-bit binary payload로 변환합니다. */
    void decodeNonce()
    {
        for (std::size_t index = 0U; index < nonce_binary_length; ++index)
        {
            nonce_binary[index] = static_cast<std::uint8_t>(
                (hexNibble(nonce[index * 2U]) << 4U) |
                hexNibble(nonce[index * 2U + 1U]));
        }
    }

    /** @brief START record의 nonce와 exact revision을 엄격히 검증합니다. */
    bool acceptStartCommand()
    {
        const std::size_t prefix_length = ::strlen(start_prefix);
        if (::strncmp(command, start_prefix, prefix_length) != 0)
        {
            return false;
        }
        const char *nonce_text = command + prefix_length;
        for (std::size_t index = 0U; index < nonce_text_length; ++index)
        {
            const char value = nonce_text[index];
            if (!((value >= '0' && value <= '9') || (value >= 'a' && value <= 'f')))
            {
                return false;
            }
        }
        const char *revision = nonce_text + nonce_text_length;
        if (::strncmp(revision, core_field, ::strlen(core_field)) != 0 ||
            ::strcmp(revision + ::strlen(core_field), M29_CACHE_CORE_REVISION) != 0)
        {
            return false;
        }
        ::memcpy(nonce, nonce_text, nonce_text_length);
        nonce[nonce_text_length] = '\0';
        decodeNonce();
        return true;
    }

    /** @brief schema stage와 nonce가 결합된 characteristic value를 갱신합니다. */
    [[maybe_unused]] bool seedCharacteristicValue()
    {
        std::uint8_t value[value_length] = {};
        value[0] = database_stage;
        ::memcpy(&value[1], nonce_binary, value_length - 1U);
        return test_characteristic.setValue(value, sizeof(value));
    }

    /** @brief 현재 session을 CRC 보호 record에 저장합니다. */
    [[maybe_unused]] bool saveSession(bool active)
    {
        std::uint8_t record[session_record_length] = {};
        putLe32(&record[0], session_magic);
        putLe16(&record[4], 1U);
        putLe16(&record[6], static_cast<std::uint16_t>(sizeof(record)));
        ::memcpy(&record[8], nonce, nonce_text_length);
        record[40] = database_stage;
        record[41] = active ? 1U : 0U;
        record[42] = service_changed_requests;
        record[43] = migration_requests;
        putLe32(&record[44], crc32(record, 44U));
        return settings_save_one(session_key, record, sizeof(record)) == 0;
    }

    /** @brief 재부팅 뒤 계속할 peripheral session을 fail-closed로 불러옵니다. */
    [[maybe_unused]] bool loadSession()
    {
        std::uint8_t record[session_record_length] = {};
        const ssize_t length = settings_load_one(session_key, record, sizeof(record));
        if (length != static_cast<ssize_t>(sizeof(record)) ||
            getLe32(&record[0]) != session_magic || getLe16(&record[4]) != 1U ||
            getLe16(&record[6]) != sizeof(record) || record[40] != database_stage ||
            record[41] != 1U || getLe32(&record[44]) != crc32(record, 44U))
        {
            return false;
        }
        for (std::size_t index = 0U; index < nonce_text_length; ++index)
        {
            const char value = static_cast<char>(record[8U + index]);
            if (!((value >= '0' && value <= '9') || (value >= 'a' && value <= 'f')))
            {
                return false;
            }
        }
        ::memcpy(nonce, &record[8], nonce_text_length);
        nonce[nonce_text_length] = '\0';
        service_changed_requests = record[42];
        migration_requests = record[43];
        decodeNonce();
        return true;
    }

#if defined(NUCODE_M29_CACHE_CENTRAL)
    /** @brief 손상 재부팅 전까지의 정량값을 CRC 보호 record에 저장합니다. */
    bool saveResume()
    {
        std::uint8_t record[resume_record_length] = {};
        putLe32(&record[0], resume_magic);
        putLe16(&record[4], 1U);
        putLe16(&record[6], static_cast<std::uint16_t>(sizeof(record)));
        ::memcpy(&record[8], nonce, nonce_text_length);
        putLe16(&record[40], old_value_handle);
        putLe16(&record[42], new_value_handle);
        putLe16(&record[44], reconnects);
        putLe16(&record[46], hash_reads);
        putLe16(&record[48], cache_saves);
        putLe16(&record[50], cache_restores);
        record[52] = static_cast<std::uint8_t>(cache_invalidations);
        record[53] = static_cast<std::uint8_t>(service_changed_events);
        putLe32(&record[56], crc32(record, 56U));
        return settings_save_one(resume_key, record, sizeof(record)) == 0;
    }

    /** @brief 중앙 재부팅 resume record를 검증하고 정량값을 복원합니다. */
    bool loadResume()
    {
        std::uint8_t record[resume_record_length] = {};
        const ssize_t length = settings_load_one(resume_key, record, sizeof(record));
        if (length != static_cast<ssize_t>(sizeof(record)) ||
            getLe32(&record[0]) != resume_magic || getLe16(&record[4]) != 1U ||
            getLe16(&record[6]) != sizeof(record) ||
            getLe32(&record[56]) != crc32(record, 56U))
        {
            return false;
        }
        for (std::size_t index = 0U; index < nonce_text_length; ++index)
        {
            const char value = static_cast<char>(record[8U + index]);
            if (!((value >= '0' && value <= '9') || (value >= 'a' && value <= 'f')))
            {
                return false;
            }
        }
        ::memcpy(nonce, &record[8], nonce_text_length);
        nonce[nonce_text_length] = '\0';
        decodeNonce();
        old_value_handle = getLe16(&record[40]);
        new_value_handle = getLe16(&record[42]);
        reconnects = getLe16(&record[44]);
        hash_reads = getLe16(&record[46]);
        cache_saves = getLe16(&record[48]);
        cache_restores = getLe16(&record[50]);
        cache_invalidations = record[52];
        service_changed_events = record[53];
        return old_value_handle != 0U && new_value_handle != 0U &&
               old_value_handle != new_value_handle && reconnects == required_reconnects;
    }
#endif

    /** @brief bond·application cache·시험 resume를 지우고 stage 1로 재부팅합니다. */
    void resetPersistentState()
    {
        static_cast<void>(bt_unpair(BT_ID_DEFAULT, nullptr));
        for (const auto &key : cache_keys)
        {
            static_cast<void>(settings_delete(key));
        }
        static_cast<void>(settings_delete(stage_key));
        static_cast<void>(settings_delete(session_key));
        static_cast<void>(settings_delete(resume_key));
        Serial.print(protocol);
        Serial.print("|RESET|role=");
        Serial.print(roleName());
        Serial.print("|status=pass|core=");
        Serial.println(M29_CACHE_CORE_REVISION);
        delay(100U);
        sys_reboot(SYS_REBOOT_WARM);
    }

    /** @brief Host 질의에 현재 stage를 포함한 image identity를 응답합니다. */
    void printReady()
    {
        Serial.print(protocol);
        Serial.print("|READY|role=");
        Serial.print(roleName());
        Serial.print("|stage=");
        Serial.print(database_stage);
        Serial.print("|core=");
        Serial.println(M29_CACHE_CORE_REVISION);
    }

    /** @brief session 시작 record를 출력합니다. */
    void printBegin()
    {
        Serial.print(protocol);
        Serial.print("|BEGIN|role=");
        Serial.print(roleName());
        printSuffix();
        Serial.println();
    }

#if defined(NUCODE_M29_CACHE_CENTRAL)
    /** @brief exact service advertisement 한 개만 연결합니다. */
    void onScanResult(const nucode::ble::BLEScanResult &result, void *context)
    {
        static_cast<void>(context);
        checkCallbackContext();
        if (protocol_finished || !result.connectable || result.scan_response ||
            !BLEScan.running())
        {
            return;
        }
        if (!BLEScan.stop())
        {
            fail("scan_stop");
            return;
        }
        if (!BLEConnection.connect(result.address, connection_handle))
        {
            fail("connect_start", BLEDevice.lastDriverError());
        }
    }

    /** @brief 현재 phase에 필요한 active scan을 main thread에서 시작합니다. */
    void startScan()
    {
        scan_pending = false;
        if (!BLEScan.clearFilters() || !BLEScan.filterServiceUuid(service_uuid) ||
            !BLEScan.start(true))
        {
            fail("scan_start", BLEDevice.lastDriverError());
        }
    }

    /** @brief bonded encrypted link에서 robust cache 동기화를 시작합니다. */
    void startCacheDiscovery()
    {
        if (!BLEClient.discoverCached(connection_handle, service_uuid, characteristic_uuid,
                                      cache_schema_version))
        {
            fail("cache_start", BLEDevice.lastDriverError());
        }
    }

    /** @brief current cached characteristic에 한 byte 시험 명령을 기록합니다. */
    void sendServerCommand(char value)
    {
        const std::uint8_t byte = static_cast<std::uint8_t>(value);
        if (!BLEClient.write(connection_handle, &byte, 1U))
        {
            fail("command_write", BLEDevice.lastDriverError());
        }
    }

    /** @brief cache 결과의 target value를 읽습니다. */
    void readCachedValue()
    {
        if (!BLEClient.discovered(connection_handle) || !BLEClient.read(connection_handle))
        {
            fail("cache_read", BLEDevice.lastDriverError());
        }
    }

    /** @brief cache read payload와 현재 migration stage를 검증합니다. */
    bool validRemoteValue(const nucode::ble::BLEGattClientEventInfo &information,
                          std::uint8_t expected_stage)
    {
        return information.data != nullptr && information.length == value_length &&
               information.data[0] == expected_stage &&
               ::memcmp(&information.data[1], nonce_binary, value_length - 1U) == 0;
    }

    /** @brief 20회 restore 뒤 database migration 명령을 보냅니다. */
    void finishRestoreLoop()
    {
        Serial.print(protocol);
        Serial.print("|RESTORES|role=central|count=");
        Serial.print(reconnects);
        Serial.print("|cache_restored=");
        Serial.print(cache_restores);
        Serial.print("|stale=0");
        printSuffix();
        Serial.println();
        central_stage = CentralStage::waiting_migration_reboot;
        sendServerCommand('M');
    }

    /** @brief 중앙의 cache event 순서와 수치를 main thread에서 검증합니다. */
    void onClientEvent(const nucode::ble::BLEGattClientEventInfo &information,
                       void *context)
    {
        static_cast<void>(context);
        checkCallbackContext();
        if (protocol_finished || information.connection != connection_handle)
        {
            return;
        }
        switch (information.event)
        {
            case nucode::ble::BLEGattClientEvent::database_hash_read:
                ++hash_reads;
                return;
            case nucode::ble::BLEGattClientEvent::cache_saved:
                ++cache_saves;
                return;
            case nucode::ble::BLEGattClientEvent::cache_restored:
                ++cache_restores;
                return;
            case nucode::ble::BLEGattClientEvent::service_changed:
                ++service_changed_events;
                central_stage = CentralStage::service_changed_rediscovery;
                return;
            case nucode::ble::BLEGattClientEvent::cache_invalidated:
                ++cache_invalidations;
                return;
            case nucode::ble::BLEGattClientEvent::operation_failed:
                fail("gatt_operation", information.att_error);
                return;
            default:
                break;
        }
        if (information.event == nucode::ble::BLEGattClientEvent::discovery_complete)
        {
            const nucode::ble::BLEGattCacheState state =
                BLEClient.cacheState(connection_handle);
            if ((central_stage == CentralStage::restoring &&
                 state != nucode::ble::BLEGattCacheState::restored) ||
                (central_stage != CentralStage::restoring &&
                 state != nucode::ble::BLEGattCacheState::discovered))
            {
                fail("cache_state", static_cast<int>(state));
                return;
            }
            readCachedValue();
            return;
        }
        if (information.event == nucode::ble::BLEGattClientEvent::write_complete)
        {
            return;
        }
        if (information.event != nucode::ble::BLEGattClientEvent::read_complete)
        {
            return;
        }

        const std::uint8_t expected_stage =
            central_stage == CentralStage::migration ||
                    central_stage == CentralStage::corrupt
                ? 2U
                : 1U;
        if (!validRemoteValue(information, expected_stage))
        {
            fail("cache_payload", expected_stage);
            return;
        }
        const std::uint16_t value_handle =
            BLEClient.remoteCharacteristic(connection_handle).valueHandle();
        if (central_stage == CentralStage::prime)
        {
            old_value_handle = value_handle;
            Serial.print(protocol);
            Serial.print("|PRIME|role=central|cache_saved=1|handle=");
            Serial.print(old_value_handle);
            printSuffix();
            Serial.println();
            central_stage = CentralStage::waiting_service_changed;
            sendServerCommand('S');
            return;
        }
        if (central_stage == CentralStage::service_changed_rediscovery)
        {
            if (service_changed_events != 1U || cache_invalidations != 1U ||
                value_handle != old_value_handle)
            {
                fail("service_changed_totals");
                return;
            }
            Serial.print(protocol);
            Serial.print("|SERVICE_CHANGED|role=central|events=1|invalidated=1");
            printSuffix();
            Serial.println();
            central_stage = CentralStage::restoring;
            if (!BLEConnection.disconnect(connection_handle))
            {
                fail("restore_disconnect");
            }
            return;
        }
        if (central_stage == CentralStage::restoring)
        {
            ++reconnects;
            if (reconnects == required_reconnects)
            {
                finishRestoreLoop();
            }
            else if (!BLEConnection.disconnect(connection_handle))
            {
                fail("restore_disconnect");
            }
            return;
        }
        if (central_stage == CentralStage::migration)
        {
            new_value_handle = value_handle;
            if (new_value_handle == old_value_handle || cache_invalidations != 2U)
            {
                fail("migration_handle");
                return;
            }
            Serial.print(protocol);
            Serial.print("|MIGRATION|role=central|old_handle=");
            Serial.print(old_value_handle);
            Serial.print("|new_handle=");
            Serial.print(new_value_handle);
            Serial.print("|invalidated=2");
            printSuffix();
            Serial.println();
            central_stage = CentralStage::preparing_corrupt_reboot;
            if (!BLEConnection.disconnect(connection_handle))
            {
                fail("corrupt_disconnect");
            }
            return;
        }
        if (central_stage == CentralStage::corrupt)
        {
            const nucode::ble::BLEGattCacheStatistics statistics =
                BLEClient.cacheStatistics();
            if (value_handle != new_value_handle || statistics.corrupt_rejected != 1U ||
                statistics.restored != 0U)
            {
                fail("corrupt_accept", static_cast<int>(statistics.corrupt_rejected));
                return;
            }
            Serial.print(protocol);
            Serial.print("|CORRUPT|role=central|rejected=1|restored=0");
            printSuffix();
            Serial.println();
            central_stage = CentralStage::finishing;
            sendServerCommand('F');
            return;
        }
    }

    /** @brief 손상 cache를 기록하고 resume record를 남긴 뒤 warm reboot합니다. */
    void corruptCacheAndReboot()
    {
        std::uint8_t corrupt_record[84] = {};
        ::memset(corrupt_record, 0xa5, sizeof(corrupt_record));
        if (!saveResume() ||
            settings_save_one(cache_keys[0], corrupt_record, sizeof(corrupt_record)) != 0)
        {
            fail("corrupt_store");
            return;
        }
        Serial.print(protocol);
        Serial.print("|CORRUPT_REBOOT|role=central|status=requested");
        printSuffix();
        Serial.println();
        delay(100U);
        sys_reboot(SYS_REBOOT_WARM);
    }

    /** @brief 최종 합산 결과와 END를 출력합니다. */
    void printCentralResult()
    {
        const nucode::ble::BLEGattCacheStatistics statistics =
            BLEClient.cacheStatistics();
        const std::uint16_t total_hash_reads = hash_reads;
        const std::uint16_t total_saves = cache_saves;
        Serial.print(protocol);
        Serial.print("|RESULT|role=central|bonded=1|reconnects=");
        Serial.print(reconnects);
        Serial.print("|hash_reads=");
        Serial.print(total_hash_reads);
        Serial.print("|cache_saved=");
        Serial.print(total_saves);
        Serial.print("|cache_restored=");
        Serial.print(cache_restores);
        Serial.print("|invalidated=");
        Serial.print(cache_invalidations);
        Serial.print("|service_changed=");
        Serial.print(service_changed_events);
        Serial.print("|corrupt_rejected=");
        Serial.print(statistics.corrupt_rejected);
        Serial.print("|stale=0|callback_context=");
        Serial.print(callback_context_valid ? "pass" : "fail");
        printSuffix();
        Serial.println();
        Serial.print(protocol);
        Serial.print("|END|role=central|status=pass");
        printSuffix();
        Serial.println();
        static_cast<void>(settings_delete(resume_key));
        protocol_finished = true;
    }

#else
    /** @brief 시험 전용 appended service를 등록해 실제 DB hash와 Service Changed를 발생시킵니다. */
    bool registerServiceChangedDelta()
    {
        static constexpr std::uint8_t uuid_value[16] = {
            0x55U, 0x29U, 0x7eU, 0x8eU, 0x8cU, 0x7dU, 0x1aU, 0x4cU,
            0x9dU, 0x2dU, 0x8bU, 0x65U, 0x19U, 0xf7U, 0x74U, 0x10U,
        };
        if (extra_service_registered)
        {
            return false;
        }
        extra_service_uuid.uuid.type = BT_UUID_TYPE_128;
        ::memcpy(extra_service_uuid.val, uuid_value, sizeof(uuid_value));
        extra_service_attribute.uuid = BT_UUID_GATT_PRIMARY;
        extra_service_attribute.perm = BT_GATT_PERM_READ;
        extra_service_attribute.read = bt_gatt_attr_read_service;
        extra_service_attribute.write = nullptr;
        extra_service_attribute.user_data = &extra_service_uuid.uuid;
        extra_service.attrs = &extra_service_attribute;
        extra_service.attr_count = 1U;
        if (bt_gatt_service_register(&extra_service) < 0)
        {
            return false;
        }
        extra_service_registered = true;
        ++service_changed_requests;
        return saveSession(true);
    }

    /** @brief peripheral 결과와 END를 session record 정리 뒤 출력합니다. */
    void printPeripheralResult()
    {
        Serial.print(protocol);
        Serial.print("|RESULT|role=peripheral|stage=");
        Serial.print(database_stage);
        Serial.print("|service_changed_requests=");
        Serial.print(service_changed_requests);
        Serial.print("|migration_requests=");
        Serial.print(migration_requests);
        Serial.print("|callback_context=");
        Serial.print(callback_context_valid ? "pass" : "fail");
        printSuffix();
        Serial.println();
        Serial.print(protocol);
        Serial.print("|END|role=peripheral|status=pass");
        printSuffix();
        Serial.println();
        static_cast<void>(saveSession(false));
        protocol_finished = true;
    }

    /** @brief characteristic command를 지연 실행해 ATT write 완료와 DB 변경을 분리합니다. */
    void driveServerAction()
    {
        if (server_action == ServerAction::none || k_uptime_get() < server_action_due)
        {
            return;
        }
        const ServerAction action = server_action;
        server_action = ServerAction::none;
        if (action == ServerAction::service_changed)
        {
            if (!registerServiceChangedDelta())
            {
                fail("service_changed_register");
                return;
            }
            Serial.print(protocol);
            Serial.print("|SERVICE_CHANGED|role=peripheral|status=requested");
            printSuffix();
            Serial.println();
        }
        else if (action == ServerAction::migrate)
        {
            database_stage = 2U;
            ++migration_requests;
            if (settings_save_one(stage_key, &database_stage, sizeof(database_stage)) != 0 ||
                !saveSession(true))
            {
                fail("migration_store");
                return;
            }
            Serial.print(protocol);
            Serial.print("|MIGRATE_REBOOT|role=peripheral|stage=2");
            printSuffix();
            Serial.println();
            delay(100U);
            sys_reboot(SYS_REBOOT_WARM);
        }
        else
        {
            printPeripheralResult();
        }
    }

    /** @brief written event의 S/M/F 명령만 허용하고 cached value를 즉시 복구합니다. */
    void onCharacteristicEvent(
        nucode::ble::BLECharacteristic &characteristic,
        const nucode::ble::BLECharacteristicEventInfo &information, void *context)
    {
        static_cast<void>(context);
        checkCallbackContext();
        if (protocol_finished || &characteristic != &test_characteristic ||
            information.event != nucode::ble::BLECharacteristicEvent::written ||
            information.connection != connection_handle || information.data == nullptr ||
            information.length != 1U)
        {
            return;
        }
        if (!seedCharacteristicValue())
        {
            fail("value_restore");
            return;
        }
        const char value = static_cast<char>(information.data[0]);
        if (value == 'S' && database_stage == 1U &&
            service_changed_requests == 0U)
        {
            server_action = ServerAction::service_changed;
        }
        else if (value == 'M' && database_stage == 1U && migration_requests == 0U)
        {
            server_action = ServerAction::migrate;
        }
        else if (value == 'F' && database_stage == 2U && migration_requests == 1U)
        {
            server_action = ServerAction::finish;
        }
        else
        {
            fail("server_command", value);
            return;
        }
        server_action_due = k_uptime_get() + server_action_delay_ms;
    }

    /** @brief active session의 connectable advertising을 시작합니다. */
    void startAdvertising(bool resumed, bool report)
    {
        restart_advertising = false;
        if (!seedCharacteristicValue() || !BLEAdvertising.clear() ||
            !BLEAdvertising.setConnectable(true) ||
            !BLEAdvertising.addServiceUuid(service_uuid) ||
            !BLEAdvertising.setScanResponseName(true) || !BLEAdvertising.start())
        {
            fail("advertising_start", BLEDevice.lastDriverError());
            return;
        }
        if (report)
        {
            if (resumed)
            {
                Serial.print(protocol);
                Serial.print("|REBOOT|role=peripheral|stage=2");
                printSuffix();
                Serial.println();
            }
            Serial.print(protocol);
            Serial.print("|ADVERTISE|role=peripheral|stage=");
            Serial.print(database_stage);
            printSuffix();
            Serial.println();
        }
    }
#endif

    /** @brief GAP event에서 exact generation link와 재연결 경계를 추적합니다. */
    void onBleEvent(const nucode::ble::BLEEventInfo &information, void *context)
    {
        static_cast<void>(context);
        checkCallbackContext();
        if (!protocol_started || protocol_finished)
        {
            return;
        }
        if (information.event == nucode::ble::BLEEvent::error)
        {
            fail("gap_error", BLEDevice.lastDriverError(),
                 static_cast<int>(BLEDevice.lastError()));
            return;
        }
        if (information.event == nucode::ble::BLEEvent::connected)
        {
            connection_handle = information.connection;
            if (!connection_handle.valid())
            {
                fail("connection_handle");
                return;
            }
#if defined(NUCODE_M29_CACHE_CENTRAL)
            if (information.role != nucode::ble::BLELinkRole::central)
            {
                fail("connection_role");
                return;
            }
            security_requested = false;
            cache_started = false;
            security_attempts = 0U;
#else
            if (information.role != nucode::ble::BLELinkRole::peripheral)
            {
                fail("connection_role");
            }
#endif
            return;
        }
        if (information.event != nucode::ble::BLEEvent::disconnected ||
            information.connection != connection_handle)
        {
            return;
        }
#if defined(NUCODE_M29_CACHE_CENTRAL)
        if (central_stage == CentralStage::preparing_corrupt_reboot)
        {
            corruptCacheAndReboot();
            return;
        }
        if (central_stage == CentralStage::restoring ||
            central_stage == CentralStage::waiting_migration_reboot ||
            central_stage == CentralStage::migration ||
            central_stage == CentralStage::corrupt)
        {
            if (central_stage == CentralStage::waiting_migration_reboot)
            {
                central_stage = CentralStage::migration;
            }
            scan_pending = true;
        }
#else
        if (!protocol_finished)
        {
            restart_advertising = true;
        }
#endif
    }

#if defined(NUCODE_M29_CACHE_CENTRAL)
    /** @brief 연결을 L2로 올리고 bond가 확인된 뒤 cache 동기화를 시작합니다. */
    void driveSecurity()
    {
        if (!protocol_started || protocol_finished || cache_started ||
            !BLEConnection.connected(connection_handle) || BLEClient.busy(connection_handle))
        {
            return;
        }
        struct bt_conn *connection = nucode::ble::internal::referenceConnection(
            connection_handle);
        if (connection == nullptr)
        {
            fail("security_connection");
            return;
        }
        const bool bonded = bt_le_bond_exists(BT_ID_DEFAULT, bt_conn_get_dst(connection));
        const bt_security_t security = bt_conn_get_security(connection);
        if (security >= BT_SECURITY_L2 && bonded)
        {
            bt_conn_unref(connection);
            cache_started = true;
            startCacheDiscovery();
            return;
        }
        if (!security_requested)
        {
            const int result = bt_conn_set_security(connection, BT_SECURITY_L2);
            ++security_attempts;
            if (result == 0 || result == -EBUSY || result == -EALREADY)
            {
                security_requested = true;
            }
            else
            {
                bt_conn_unref(connection);
                fail("security_request", result);
                return;
            }
        }
        bt_conn_unref(connection);
    }
#endif

    /** @brief 검증된 START record에서 role별 첫 RF 동작을 시작합니다. */
    void startProtocol()
    {
        if (!acceptStartCommand())
        {
            fail("start_record");
            return;
        }
        protocol_started = true;
        protocol_deadline = k_uptime_get() + protocol_timeout_ms;
        printBegin();
#if defined(NUCODE_M29_CACHE_CENTRAL)
        central_stage = CentralStage::prime;
        Serial.print(protocol);
        Serial.print("|SCAN|role=central|stage=1");
        printSuffix();
        Serial.println();
        startScan();
#else
        if (!saveSession(true))
        {
            fail("session_store");
            return;
        }
        startAdvertising(false, true);
#endif
    }

    /** @brief Host의 bounded newline command를 수집합니다. */
    void pollHostCommand()
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
                if (::strcmp(command, ready_query) == 0)
                {
                    printReady();
                }
                else if (::strcmp(command, reset_command) == 0)
                {
                    resetPersistentState();
                }
                else if (!protocol_started)
                {
                    startProtocol();
                }
                else
                {
                    fail("unexpected_command");
                }
                command_length = 0U;
                return;
            }
            if (command_length + 1U >= sizeof(command))
            {
                command_length = 0U;
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
    const std::int64_t serial_deadline = k_uptime_get() + 5000;
    while (!Serial && k_uptime_get() < serial_deadline)
    {
        delay(10U);
    }

    const int settings_result = settings_subsys_init();
    if (settings_result != 0)
    {
        fail("settings_init", settings_result);
        return;
    }

#if !defined(NUCODE_M29_CACHE_CENTRAL)
    const ssize_t stage_length = settings_load_one(stage_key, &database_stage,
                                                   sizeof(database_stage));
    if (stage_length != static_cast<ssize_t>(sizeof(database_stage)) ||
        (database_stage != 1U && database_stage != 2U))
    {
        database_stage = 1U;
    }
#endif
    if (!BLEGattDatabase.setRevision(database_stage))
    {
        fail("database_revision");
        return;
    }

#if !defined(NUCODE_M29_CACHE_CENTRAL)
    const bool resumed = database_stage == 2U && loadSession();
    if (database_stage == 2U && !test_service.addCharacteristic(dummy_characteristic))
    {
        fail("dummy_schema");
        return;
    }
    test_characteristic.onEvent(onCharacteristicEvent);
    if (!test_service.addCharacteristic(test_characteristic) ||
        !BLEDevice.addService(test_service))
    {
        fail("service_schema");
        return;
    }
#else
    const bool resumed = loadResume();
#endif

    BLEDevice.onEventInfo(onBleEvent);
#if defined(NUCODE_M29_CACHE_CENTRAL)
    BLEScan.onResult(onScanResult);
    BLEClient.onDetailedEvent(onClientEvent);
#endif
    if (!BLEDevice.begin(peer_name))
    {
        fail("device_begin", BLEDevice.lastDriverError());
        return;
    }

    if (resumed)
    {
        protocol_started = true;
        protocol_deadline = k_uptime_get() + protocol_timeout_ms;
#if defined(NUCODE_M29_CACHE_CENTRAL)
        central_stage = CentralStage::corrupt;
        Serial.print(protocol);
        Serial.print("|REBOOT|role=central|phase=corrupt");
        printSuffix();
        Serial.println();
        Serial.print(protocol);
        Serial.print("|SCAN|role=central|stage=2");
        printSuffix();
        Serial.println();
        scan_pending = true;
#else
        startAdvertising(true, true);
#endif
    }
    else
    {
        printReady();
    }
}

void loop()
{
    pollHostCommand();
    BLEDevice.poll();
#if defined(NUCODE_M29_CACHE_CENTRAL)
    if (scan_pending && !protocol_finished)
    {
        startScan();
    }
    driveSecurity();
    if (central_stage == CentralStage::finishing && !BLEClient.busy(connection_handle))
    {
        printCentralResult();
    }
#else
    driveServerAction();
    if (restart_advertising && !BLEAdvertising.running() && !protocol_finished)
    {
        startAdvertising(false, false);
    }
#endif
    if (protocol_started && !protocol_finished && k_uptime_get() >= protocol_deadline)
    {
        fail("timeout");
    }
    delay(1U);
}
