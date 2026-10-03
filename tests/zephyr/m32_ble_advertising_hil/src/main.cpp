/**
 * @file main.cpp
 * @brief 세 NU54DK에서 6개 광고 set과 SID 수신 계약을 검증합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <Arduino.h>
#include <NUCODE_BLE.h>

#include <zephyr/kernel.h>

#include <cstddef>
#include <cstdint>
#include <string.h>

#ifndef M32_ADV_CORE_REVISION
#error "M32_ADV_CORE_REVISION is required"
#endif

namespace
{

    constexpr char protocol[] = "M32ADV|1";
    constexpr char start_prefix[] = "M32ADV|1|START|nonce=";
    constexpr char stop_prefix[] = "M32ADV|1|STOP|nonce=";
    constexpr std::size_t nonce_length = 32U;
    constexpr std::size_t nonce_fragment_length = 8U;
    constexpr std::uint32_t iteration_target = 20U;
    constexpr std::uint32_t packet_target = 600U;
    constexpr std::uint32_t unique_target = 120U;
    constexpr std::uint8_t set_count = 3U;
    constexpr std::uint8_t manufacturer_type = 0xffU;
    constexpr std::int64_t update_interval_ms = 1600;
    constexpr std::int64_t session_timeout_ms = 240000;
    constexpr std::uint8_t payload_magic[] = {
        0x4dU, 0x33U, 0x32U, 0x41U, 0x44U, 0x56U,
    };

    char command[128] = {};
    char nonce[nonce_length + 1U] = {};
    std::size_t command_length = 0U;
    bool started = false;
    bool finished = false;
    bool stop_requested = false;
    bool callback_context_valid = true;
    std::int64_t deadline_ms = 0;
    struct k_thread *main_thread = nullptr;

#if defined(NUCODE_M32_ADV_ADVERTISER)
    nucode::ble::BLEAdvertisingSetHandle advertising_sets[set_count];
    std::uint32_t updates = 0U;
    std::int64_t next_update_ms = 0;
    bool over_capacity_rejected = false;
    bool stale_set_rejected = false;
#else
    bool seen[2U][set_count][iteration_target] = {};
    std::uint32_t raw_reports = 0U;
    std::uint32_t unique_reports = 0U;
    std::uint32_t corrupt_reports = 0U;
    bool scan_initiate_conflict_rejected = false;
#endif

    /** @brief 현재 image의 고정 역할 이름을 반환합니다. */
    const char *roleName()
    {
#if defined(NUCODE_M32_ADV_ADVERTISER)
#if NUCODE_M32_ADV_INDEX == 0
        return "advertiser_a";
#else
        return "advertiser_b";
#endif
#else
        return "scanner";
#endif
    }

    /** @brief 모든 결과 record에 nonce와 exact Core revision을 결합합니다. */
    void printSuffix()
    {
        Serial.print("|nonce=");
        Serial.print(nonce);
        Serial.print("|core=");
        Serial.print(M32_ADV_CORE_REVISION);
    }

    /** @brief 첫 오류만 bounded protocol로 출력합니다. */
    void fail(const char *stage, int code = 0)
    {
        if (finished)
        {
            return;
        }
        Serial.print(protocol);
        Serial.print("|FAIL|role=");
        Serial.print(roleName());
        Serial.print("|stage=");
        Serial.print(stage);
        Serial.print("|code=");
        Serial.print(code);
        printSuffix();
        Serial.println();
        finished = true;
    }

    /** @brief callback이 Arduino main thread에서 dispatch됐는지 확인합니다. */
    [[maybe_unused]] void checkCallbackContext()
    {
        if (k_current_get() != main_thread)
        {
            callback_context_valid = false;
            fail("callback_context");
        }
    }

    /** @brief START record의 nonce와 exact revision을 검증합니다. */
    bool acceptStart()
    {
        const std::size_t prefix_length = ::strlen(start_prefix);
        if (::strncmp(command, start_prefix, prefix_length) != 0)
        {
            return false;
        }
        const char *cursor = command + prefix_length;
        for (std::size_t index = 0U; index < nonce_length; ++index)
        {
            const char value = cursor[index];
            if (!((value >= '0' && value <= '9') ||
                  (value >= 'a' && value <= 'f')))
            {
                return false;
            }
        }
        constexpr char core_prefix[] = "|core=";
        if (::strncmp(cursor + nonce_length, core_prefix,
                      sizeof(core_prefix) - 1U) != 0 ||
            ::strcmp(cursor + nonce_length + sizeof(core_prefix) - 1U,
                     M32_ADV_CORE_REVISION) != 0)
        {
            return false;
        }
        ::memcpy(nonce, cursor, nonce_length);
        nonce[nonce_length] = '\0';
        return true;
    }

#if defined(NUCODE_M32_ADV_ADVERTISER)
    /** @brief 한 set의 sequence와 실행 nonce를 AD payload에 기록합니다. */
    bool updatePayload(std::uint8_t local_set, std::uint8_t sequence)
    {
        std::uint8_t payload[21] = {};
        payload[0] = static_cast<std::uint8_t>(sizeof(payload) - 1U);
        payload[1] = manufacturer_type;
        ::memcpy(&payload[2], payload_magic, sizeof(payload_magic));
        payload[8] = static_cast<std::uint8_t>(NUCODE_M32_ADV_INDEX);
        payload[9] = local_set;
        payload[10] = sequence;
        payload[11] = static_cast<std::uint8_t>(~sequence);
        ::memcpy(&payload[12], nonce, nonce_fragment_length);
        payload[20] = static_cast<std::uint8_t>(payload[8] ^ payload[9] ^
                                                payload[10] ^ payload[11]);
        return BLEExtendedAdvertising.setData(advertising_sets[local_set],
                                              payload, sizeof(payload));
    }

    /** @brief 삭제한 handle과 네 번째 set이 모두 거부되는지 먼저 확인합니다. */
    bool validateNegativePaths()
    {
        nucode::ble::BLEExtendedAdvertisingParameters parameters{};
        parameters.sid = 0x0eU;
        nucode::ble::BLEAdvertisingSetHandle stale;
        if (!BLEExtendedAdvertising.create(parameters, stale) ||
            !BLEExtendedAdvertising.remove(stale))
        {
            return false;
        }
        stale_set_rejected = !BLEExtendedAdvertising.start(stale);
        return stale_set_rejected;
    }

    /** @brief 세 production set을 만들고 controller 상한 초과를 검증합니다. */
    bool startRadio()
    {
        if (!validateNegativePaths())
        {
            return false;
        }
        for (std::uint8_t index = 0U; index < set_count; ++index)
        {
            nucode::ble::BLEExtendedAdvertisingParameters parameters{};
            parameters.sid = static_cast<std::uint8_t>(
                (NUCODE_M32_ADV_INDEX * set_count) + index);
            parameters.interval_min = 0x0050U;
            parameters.interval_max = 0x0050U;
            if (!BLEExtendedAdvertising.create(parameters, advertising_sets[index]) ||
                !updatePayload(index, 0U) ||
                !BLEExtendedAdvertising.start(advertising_sets[index]))
            {
                return false;
            }
        }
        nucode::ble::BLEExtendedAdvertisingParameters excess_parameters{};
        excess_parameters.sid = 0x0fU;
        nucode::ble::BLEAdvertisingSetHandle excess;
        over_capacity_rejected = !BLEExtendedAdvertising.create(excess_parameters, excess);
        if (!over_capacity_rejected)
        {
            static_cast<void>(BLEExtendedAdvertising.remove(excess));
            return false;
        }
        updates = 1U;
        next_update_ms = k_uptime_get() + update_interval_ms;
        return true;
    }

    /** @brief 20회 × 3 set 갱신 결과를 출력하고 마지막 payload를 유지합니다. */
    void finishAdvertiser()
    {
        Serial.print(protocol);
        Serial.print("|RESULT|role=");
        Serial.print(roleName());
        Serial.print("|updates=");
        Serial.print(updates);
        Serial.print("|sets=3|over_capacity_rejected=");
        Serial.print(over_capacity_rejected ? 1 : 0);
        Serial.print("|stale_set_rejected=");
        Serial.print(stale_set_rejected ? 1 : 0);
        Serial.print("|callback_context=");
        Serial.print(callback_context_valid ? "pass" : "fail");
        printSuffix();
        Serial.println();
        Serial.print(protocol);
        Serial.print("|END|role=");
        Serial.print(roleName());
        Serial.print("|status=pass");
        printSuffix();
        Serial.println();
        finished = true;
    }
#else
    /** @brief AD stream에서 시험 payload를 찾아 advertiser/set/sequence를 반환합니다. */
    bool parsePayload(const nucode::ble::BLEScanResult &result,
                      std::uint8_t &advertiser, std::uint8_t &local_set,
                      std::uint8_t &sequence)
    {
        std::size_t offset = 0U;
        while (offset < result.payload_length)
        {
            const std::uint8_t length = result.payload[offset];
            if (length == 0U || offset + length >= result.payload_length)
            {
                return false;
            }
            if (length == 20U && result.payload[offset + 1U] == manufacturer_type &&
                ::memcmp(&result.payload[offset + 2U], payload_magic,
                         sizeof(payload_magic)) == 0)
            {
                const std::uint8_t *data = &result.payload[offset + 2U];
                advertiser = data[6];
                local_set = data[7];
                sequence = data[8];
                const std::uint8_t complement = data[9];
                const std::uint8_t checksum = data[18];
                return advertiser < 2U && local_set < set_count &&
                       sequence < iteration_target &&
                       complement == static_cast<std::uint8_t>(~sequence) &&
                       ::memcmp(&data[10], nonce, nonce_fragment_length) == 0 &&
                       checksum == static_cast<std::uint8_t>(advertiser ^ local_set ^
                                                             sequence ^ complement);
            }
            offset += static_cast<std::size_t>(length) + 1U;
        }
        return false;
    }

    /** @brief 유효한 6 set 광고의 raw/unique 분모와 SID 귀속을 누적합니다. */
    void onScanResult(const nucode::ble::BLEScanResult &result, void *)
    {
        checkCallbackContext();
        if (!started || finished)
        {
            return;
        }
        std::uint8_t advertiser = 0U;
        std::uint8_t local_set = 0U;
        std::uint8_t sequence = 0U;
        if (!parsePayload(result, advertiser, local_set, sequence))
        {
            return;
        }
        ++raw_reports;
        const std::uint8_t expected_sid = static_cast<std::uint8_t>(
            (advertiser * set_count) + local_set);
        if (!result.extended || result.sid != expected_sid)
        {
            ++corrupt_reports;
            fail("sid_mismatch");
            return;
        }
        if (!seen[advertiser][local_set][sequence])
        {
            seen[advertiser][local_set][sequence] = true;
            ++unique_reports;
        }
    }

    /** @brief scan 중 중복 시작을 거부하고 6-set 수신을 시작합니다. */
    bool startRadio()
    {
        if (!BLEScan.clearFilters() ||
            !BLEScan.startExtended(false, false, false))
        {
            return false;
        }
        scan_initiate_conflict_rejected =
            !BLEScan.startExtended(false, false, false);
        return scan_initiate_conflict_rejected;
    }

    /** @brief 600 raw 및 120 unique 수신 결과를 출력합니다. */
    void finishScanner()
    {
        Serial.print(protocol);
        Serial.print("|RESULT|role=scanner|raw=");
        Serial.print(raw_reports);
        Serial.print("|unique=");
        Serial.print(unique_reports);
        Serial.print("|corrupt=");
        Serial.print(corrupt_reports);
        Serial.print("|dropped=");
        Serial.print(BLEScan.droppedResults());
        Serial.print("|scan_initiate_conflict_rejected=");
        Serial.print(scan_initiate_conflict_rejected ? 1 : 0);
        Serial.print("|callback_context=");
        Serial.print(callback_context_valid ? "pass" : "fail");
        printSuffix();
        Serial.println();
        Serial.print(protocol);
        Serial.print("|END|role=scanner|status=pass");
        printSuffix();
        Serial.println();
        finished = true;
    }
#endif

    /** @brief 검증된 START 뒤 image 역할의 radio 시험을 시작합니다. */
    void beginProtocol()
    {
        if (!acceptStart())
        {
            fail("start_record");
            return;
        }
        started = true;
        deadline_ms = k_uptime_get() + session_timeout_ms;
        Serial.print(protocol);
        Serial.print("|BEGIN|role=");
        Serial.print(roleName());
        printSuffix();
        Serial.println();
        if (!startRadio())
        {
            fail("radio_start", BLEDevice.lastDriverError());
        }
    }

    /** @brief STOP 때 광고·검색과 library 자원을 bounded하게 회수합니다. */
    void stopProtocol()
    {
#if defined(NUCODE_M32_ADV_ADVERTISER)
        for (std::uint8_t index = 0U; index < set_count; ++index)
        {
            if (BLEExtendedAdvertising.running(advertising_sets[index]))
            {
                static_cast<void>(BLEExtendedAdvertising.stop(advertising_sets[index]));
            }
            if (BLEExtendedAdvertising.exists(advertising_sets[index]))
            {
                static_cast<void>(BLEExtendedAdvertising.remove(advertising_sets[index]));
            }
        }
#else
        if (BLEScan.running())
        {
            static_cast<void>(BLEScan.stop());
        }
#endif
        BLEDevice.end();
        Serial.print(protocol);
        Serial.print("|STOPPED|role=");
        Serial.print(roleName());
        printSuffix();
        Serial.println();
        stop_requested = false;
    }

    /** @brief CR/LF 명령을 고정 buffer로 읽어 PROBE·START·STOP만 처리합니다. */
    void pollCommand()
    {
        while (Serial.available() > 0)
        {
            const int input = Serial.read();
            if (input == '\r')
            {
                continue;
            }
            if (input != '\n')
            {
                if (command_length + 1U >= sizeof(command))
                {
                    command_length = 0U;
                    fail("command_overflow");
                    return;
                }
                command[command_length++] = static_cast<char>(input);
                command[command_length] = '\0';
                continue;
            }
            if (::strcmp(command, "M32ADV|1|PROBE") == 0)
            {
                Serial.print(protocol);
                Serial.print("|READY|role=");
                Serial.print(roleName());
                Serial.print("|core=");
                Serial.println(M32_ADV_CORE_REVISION);
            }
            else if (!started && ::strncmp(command, start_prefix,
                                           ::strlen(start_prefix)) == 0)
            {
                beginProtocol();
            }
            else if (started && ::strncmp(command, stop_prefix,
                                          ::strlen(stop_prefix)) == 0)
            {
                const char *requested_nonce = command + ::strlen(stop_prefix);
                if (::strcmp(requested_nonce, nonce) == 0)
                {
                    stop_requested = true;
                }
            }
            command_length = 0U;
            command[0] = '\0';
        }
    }

} // namespace

void setup()
{
    main_thread = k_current_get();
    Serial.begin(115200);
    const std::int64_t serial_deadline = k_uptime_get() + 5000;
    while (!Serial && k_uptime_get() < serial_deadline)
    {
        delay(10);
    }
#if !defined(NUCODE_M32_ADV_ADVERTISER)
    BLEScan.onResult(onScanResult);
#endif
    if (!BLEDevice.begin(roleName()))
    {
        fail("device_begin", BLEDevice.lastDriverError());
    }
}

void loop()
{
    pollCommand();
    if (BLEDevice.initialized())
    {
        BLEDevice.poll();
    }
    if (started && !finished && k_uptime_get() >= deadline_ms)
    {
        fail("session_timeout");
    }
#if defined(NUCODE_M32_ADV_ADVERTISER)
    if (started && !finished && k_uptime_get() >= next_update_ms)
    {
        if (updates >= iteration_target)
        {
            finishAdvertiser();
        }
        else
        {
            for (std::uint8_t index = 0U; index < set_count; ++index)
            {
                if (!updatePayload(index, static_cast<std::uint8_t>(updates)))
                {
                    fail("payload_update", BLEDevice.lastDriverError());
                    break;
                }
            }
            ++updates;
            next_update_ms += update_interval_ms;
        }
    }
#else
    if (started && !finished && raw_reports >= packet_target &&
        unique_reports == unique_target)
    {
        finishScanner();
    }
#endif
    if (stop_requested)
    {
        stopProtocol();
    }
    delay(1);
}
