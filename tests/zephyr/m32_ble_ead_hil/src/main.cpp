/**
 * @file main.cpp
 * @brief 두 NU54DK에서 Encrypted Advertising Data 인증과 음수 경로를 검증합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <Arduino.h>
#include <NUCODE_BLE.h>

#include <zephyr/kernel.h>

#include <cstddef>
#include <cstdint>
#include <string.h>

#ifndef M32_EAD_CORE_REVISION
#error "M32_EAD_CORE_REVISION is required"
#endif

namespace
{

    constexpr char protocol[] = "M32EAD|1";
    constexpr char start_prefix[] = "M32EAD|1|START|nonce=";
    constexpr char stop_prefix[] = "M32EAD|1|STOP|nonce=";
    constexpr char peer_name[] = "NU54-M32-EAD";
    constexpr std::size_t nonce_length = 32U;
    constexpr std::size_t nonce_fragment_length = 8U;
    constexpr std::uint32_t iteration_target = 20U;
    constexpr std::uint32_t report_target = 400U;
    constexpr std::int64_t update_interval_ms = 1600;
    constexpr std::int64_t session_timeout_ms = 240000;
    constexpr std::uint8_t ead_type = 0x31U;
    constexpr std::uint8_t ead_sid = 4U;
    constexpr std::uint8_t payload_magic[] = {
        0x4dU, 0x33U, 0x32U, 0x45U, 0x41U, 0x44U,
    };
    constexpr std::size_t plaintext_length =
        sizeof(payload_magic) + 2U + nonce_fragment_length;

    const std::uint8_t session_key[
        nucode::ble::EncryptedAdvertisingData::session_key_length] = {
        0x10U, 0x11U, 0x12U, 0x13U, 0x14U, 0x15U, 0x16U, 0x17U,
        0x18U, 0x19U, 0x1aU, 0x1bU, 0x1cU, 0x1dU, 0x1eU, 0x1fU,
    };
    const std::uint8_t initialization_vector[
        nucode::ble::EncryptedAdvertisingData::initialization_vector_length] = {
        0xa0U, 0xa1U, 0xa2U, 0xa3U, 0xa4U, 0xa5U, 0xa6U, 0xa7U,
    };
    const std::uint8_t wrong_session_key[
        nucode::ble::EncryptedAdvertisingData::session_key_length] = {
        0x90U, 0x91U, 0x92U, 0x93U, 0x94U, 0x95U, 0x96U, 0x97U,
        0x98U, 0x99U, 0x9aU, 0x9bU, 0x9cU, 0x9dU, 0x9eU, 0x9fU,
    };
    const std::uint8_t wrong_initialization_vector[
        nucode::ble::EncryptedAdvertisingData::initialization_vector_length] = {
        0xb0U, 0xb1U, 0xb2U, 0xb3U, 0xb4U, 0xb5U, 0xb6U, 0xb7U,
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

    nucode::ble::EncryptedAdvertisingData ead;
#if defined(NUCODE_M32_EAD_ADVERTISER)
    nucode::ble::BLEAdvertisingSetHandle advertising_set;
    std::uint8_t encrypted_data[32] = {};
    std::uint8_t advertising_payload[34] = {};
    std::uint32_t updates = 0U;
    std::int64_t next_update_ms = 0;
#else
    nucode::ble::EncryptedAdvertisingData tamper_ead;
    nucode::ble::EncryptedAdvertisingData wrong_key_ead;
    nucode::ble::EncryptedAdvertisingData wrong_iv_ead;
    bool seen[iteration_target] = {};
    std::uint32_t raw_reports = 0U;
    std::uint32_t authenticated = 0U;
    std::uint32_t replay_rejected = 0U;
    std::uint32_t tamper_rejected = 0U;
    std::uint32_t wrong_key_rejected = 0U;
    std::uint32_t wrong_iv_rejected = 0U;
#endif

    /** @brief 현재 image의 고정 역할 이름을 반환합니다. */
    const char *roleName()
    {
#if defined(NUCODE_M32_EAD_ADVERTISER)
        return "advertiser";
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
        Serial.print(M32_EAD_CORE_REVISION);
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

#if !defined(NUCODE_M32_EAD_ADVERTISER)
    /** @brief callback이 Arduino main thread에서 dispatch됐는지 확인합니다. */
    void checkCallbackContext()
    {
        if (k_current_get() != main_thread)
        {
            callback_context_valid = false;
            fail("callback_context");
        }
    }
#endif

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
                     M32_EAD_CORE_REVISION) != 0)
        {
            return false;
        }
        ::memcpy(nonce, cursor, nonce_length);
        nonce[nonce_length] = '\0';
        return true;
    }

#if defined(NUCODE_M32_EAD_ADVERTISER)
    /** @brief sequence와 실행 nonce를 새 randomizer로 암호화해 payload를 갱신합니다. */
    bool updateAdvertisingData(std::uint8_t sequence)
    {
        std::uint8_t plaintext[plaintext_length] = {};
        ::memcpy(plaintext, payload_magic, sizeof(payload_magic));
        plaintext[sizeof(payload_magic)] = sequence;
        plaintext[sizeof(payload_magic) + 1U] =
            static_cast<std::uint8_t>(~sequence);
        ::memcpy(&plaintext[sizeof(payload_magic) + 2U], nonce,
                 nonce_fragment_length);

        std::size_t encrypted_length = 0U;
        if (!ead.encrypt(plaintext, sizeof(plaintext), encrypted_data,
                         sizeof(encrypted_data), encrypted_length))
        {
            return false;
        }
        advertising_payload[0] = static_cast<std::uint8_t>(encrypted_length + 1U);
        advertising_payload[1] = ead_type;
        ::memcpy(&advertising_payload[2], encrypted_data, encrypted_length);
        return BLEExtendedAdvertising.setData(
            advertising_set, advertising_payload, encrypted_length + 2U);
    }

    /** @brief 20개 EAD update가 끝나면 결과를 출력하고 마지막 payload를 유지합니다. */
    void finishAdvertiser()
    {
        Serial.print(protocol);
        Serial.print("|RESULT|role=advertiser|updates=");
        Serial.print(updates);
        Serial.print("|callback_context=");
        Serial.print(callback_context_valid ? "pass" : "fail");
        printSuffix();
        Serial.println();
        Serial.print(protocol);
        Serial.print("|END|role=advertiser|status=pass");
        printSuffix();
        Serial.println();
        finished = true;
    }

    /** @brief 고정 SID와 짧은 interval의 non-connectable extended 광고를 시작합니다. */
    bool startRadio()
    {
        nucode::ble::BLEExtendedAdvertisingParameters parameters{};
        parameters.sid = ead_sid;
        parameters.interval_min = 0x0050U;
        parameters.interval_max = 0x0050U;
        if (!ead.configure(session_key, initialization_vector) ||
            !BLEExtendedAdvertising.create(parameters, advertising_set) ||
            !updateAdvertisingData(0U) ||
            !BLEExtendedAdvertising.start(advertising_set))
        {
            return false;
        }
        updates = 1U;
        next_update_ms = k_uptime_get() + update_interval_ms;
        return true;
    }
#else
    /** @brief 복호화된 payload가 exact sequence와 실행 nonce에 귀속되는지 검사합니다. */
    bool validPlaintext(const std::uint8_t *plaintext, std::size_t length,
                        std::uint8_t &sequence)
    {
        if (length != plaintext_length ||
            ::memcmp(plaintext, payload_magic, sizeof(payload_magic)) != 0 ||
            ::memcmp(&plaintext[sizeof(payload_magic) + 2U], nonce,
                     nonce_fragment_length) != 0)
        {
            return false;
        }
        sequence = plaintext[sizeof(payload_magic)];
        return sequence < iteration_target &&
               plaintext[sizeof(payload_magic) + 1U] ==
                   static_cast<std::uint8_t>(~sequence);
    }

    /** @brief 한 unique EAD에 replay·변조·잘못된 key·IV 음수 검사를 적용합니다. */
    bool validateNegativePaths(const std::uint8_t *encrypted,
                               std::size_t encrypted_length)
    {
        std::uint8_t plaintext[plaintext_length] = {};
        std::size_t output_length = 0U;
        if (!ead.decrypt(encrypted, encrypted_length, plaintext,
                         sizeof(plaintext), output_length))
        {
            ++replay_rejected;
        }
        else
        {
            return false;
        }

        std::uint8_t tampered[32] = {};
        if (encrypted_length > sizeof(tampered))
        {
            return false;
        }
        ::memcpy(tampered, encrypted, encrypted_length);
        tampered[encrypted_length - 1U] ^= 0x01U;
        if (!tamper_ead.decrypt(tampered, encrypted_length, plaintext,
                                sizeof(plaintext), output_length))
        {
            ++tamper_rejected;
        }
        else
        {
            return false;
        }
        if (!wrong_key_ead.decrypt(encrypted, encrypted_length, plaintext,
                                   sizeof(plaintext), output_length))
        {
            ++wrong_key_rejected;
        }
        else
        {
            return false;
        }
        if (!wrong_iv_ead.decrypt(encrypted, encrypted_length, plaintext,
                                  sizeof(plaintext), output_length))
        {
            ++wrong_iv_rejected;
        }
        else
        {
            return false;
        }
        return true;
    }

    /** @brief scanner의 packet·인증·음수 경로 분모가 모두 끝나면 결과를 출력합니다. */
    void finishScannerIfComplete()
    {
        if (finished || raw_reports < report_target ||
            authenticated != iteration_target)
        {
            return;
        }
        Serial.print(protocol);
        Serial.print("|RESULT|role=scanner|raw=");
        Serial.print(raw_reports);
        Serial.print("|authenticated=");
        Serial.print(authenticated);
        Serial.print("|replay_rejected=");
        Serial.print(replay_rejected);
        Serial.print("|tamper_rejected=");
        Serial.print(tamper_rejected);
        Serial.print("|wrong_key_rejected=");
        Serial.print(wrong_key_rejected);
        Serial.print("|wrong_iv_rejected=");
        Serial.print(wrong_iv_rejected);
        Serial.print("|dropped=");
        Serial.print(BLEScan.droppedResults());
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

    /** @brief SID 4 EAD report를 인증하고 unique sequence마다 음수 경로를 검증합니다. */
    void onScanResult(const nucode::ble::BLEScanResult &result, void *context)
    {
        static_cast<void>(context);
        checkCallbackContext();
        if (finished || !result.extended || result.sid != ead_sid ||
            result.truncated)
        {
            return;
        }
        std::size_t offset = 0U;
        while (offset < result.payload_length)
        {
            const std::size_t field_length = result.payload[offset];
            if (field_length == 0U ||
                offset + field_length + 1U > result.payload_length)
            {
                return;
            }
            if (result.payload[offset + 1U] == ead_type)
            {
                ++raw_reports;
                const std::uint8_t *encrypted = &result.payload[offset + 2U];
                const std::size_t encrypted_length = field_length - 1U;
                std::uint8_t plaintext[plaintext_length] = {};
                std::size_t output_length = 0U;
                if (ead.decrypt(encrypted, encrypted_length, plaintext,
                                sizeof(plaintext), output_length))
                {
                    std::uint8_t sequence = 0U;
                    if (!validPlaintext(plaintext, output_length, sequence))
                    {
                        fail("plaintext");
                        return;
                    }
                    if (seen[sequence])
                    {
                        fail("randomizer_reuse");
                        return;
                    }
                    seen[sequence] = true;
                    ++authenticated;
                    if (!validateNegativePaths(encrypted, encrypted_length))
                    {
                        fail("negative_path");
                        return;
                    }
                    Serial.print(protocol);
                    Serial.print("|AUTH|role=scanner|sequence=");
                    Serial.print(sequence);
                    printSuffix();
                    Serial.println();
                }
                finishScannerIfComplete();
                return;
            }
            offset += field_length + 1U;
        }
    }

    /** @brief 올바른 key/IV와 두 잘못된 조합을 구성하고 중복 미제거 scan을 시작합니다. */
    bool startRadio()
    {
        if (!ead.configure(session_key, initialization_vector) ||
            !tamper_ead.configure(session_key, initialization_vector) ||
            !wrong_key_ead.configure(wrong_session_key, initialization_vector) ||
            !wrong_iv_ead.configure(session_key, wrong_initialization_vector))
        {
            return false;
        }
        return BLEScan.startExtended(false, false, false);
    }
#endif

    /** @brief PROBE·START·STOP command를 최대 고정 길이로 해석합니다. */
    void processCommand()
    {
        if (::strcmp(command, "M32EAD|1|PROBE") == 0)
        {
            Serial.print(protocol);
            Serial.print("|READY|role=");
            Serial.print(roleName());
            Serial.print("|core=");
            Serial.println(M32_EAD_CORE_REVISION);
            return;
        }
        if (!started && acceptStart())
        {
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
            return;
        }
        if (finished && ::strncmp(command, stop_prefix,
                                  sizeof(stop_prefix) - 1U) == 0 &&
            ::strcmp(command + sizeof(stop_prefix) - 1U, nonce) == 0)
        {
            stop_requested = true;
#if defined(NUCODE_M32_EAD_ADVERTISER)
            if (BLEExtendedAdvertising.running(advertising_set) &&
                !BLEExtendedAdvertising.stop(advertising_set))
#else
            if (BLEScan.running() && !BLEScan.stop())
#endif
            {
                fail("radio_stop", BLEDevice.lastDriverError());
                return;
            }
            Serial.print(protocol);
            Serial.print("|STOPPED|role=");
            Serial.print(roleName());
            printSuffix();
            Serial.println();
            stop_requested = false;
            return;
        }
        fail("command");
    }

    /** @brief 한 줄 command를 overflow 없이 수집합니다. */
    void pollSerial()
    {
        while (Serial.available() > 0)
        {
            const int incoming = Serial.read();
            if (incoming == '\r')
            {
                continue;
            }
            if (incoming == '\n')
            {
                command[command_length] = '\0';
                processCommand();
                command_length = 0U;
                continue;
            }
            if (incoming < 0 || command_length + 1U >= sizeof(command))
            {
                fail("command_length");
                command_length = 0U;
                continue;
            }
            command[command_length++] = static_cast<char>(incoming);
        }
    }

} // namespace

void setup()
{
    Serial.begin(115200);
    main_thread = k_current_get();
#if !defined(NUCODE_M32_EAD_ADVERTISER)
    BLEScan.onResult(onScanResult);
#endif
    if (!BLEDevice.begin(peer_name))
    {
        fail("ble_begin", BLEDevice.lastDriverError());
    }
}

void loop()
{
    BLEDevice.poll();
    pollSerial();
#if defined(NUCODE_M32_EAD_ADVERTISER)
    if (started && !finished && updates < iteration_target &&
        k_uptime_get() >= next_update_ms)
    {
        if (!updateAdvertisingData(static_cast<std::uint8_t>(updates)))
        {
            fail("advertising_update", BLEDevice.lastDriverError());
        }
        else
        {
            ++updates;
            next_update_ms += update_interval_ms;
            if (updates == iteration_target)
            {
                finishAdvertiser();
            }
        }
    }
#endif
    if (started && !finished && k_uptime_get() > deadline_ms)
    {
        fail("timeout");
    }
}
