/**
 * @file candidate.cpp
 * @brief Mesh 전송 시간을 제한하는 최소 MCUboot candidate oracle입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <Arduino.h>

#include <zephyr/dfu/mcuboot.h>
#include <zephyr/settings/settings.h>
#include <zephyr/storage/flash_map.h>

#include <cstddef>
#include <cstdint>
#include <errno.h>
#include <string.h>

#ifndef M32_MDFU_CORE_REVISION
#error "M32_MDFU_CORE_REVISION is required"
#endif

namespace
{
    constexpr char protocol[] = "M32MDFU|1";
    constexpr char apply_prefix[] = "M32MDFU|1|APPLY|nonce=";
    constexpr char stop_prefix[] = "M32MDFU|1|STOP|nonce=";
    constexpr std::size_t nonce_length = 32U;
    constexpr std::size_t command_capacity = 192U;

    char command[command_capacity] = {};
    char nonce[nonce_length + 1U] = {};
    char role = '\0';
    std::size_t command_length = 0U;
    bool nonce_valid = false;
    bool candidate_applied = false;
    bool failed = false;

    /** @brief MCUboot active image의 semantic version과 confirm 상태입니다. */
    struct ActiveImage
    {
        std::uint8_t major = 0U;
        std::uint8_t minor = 0U;
        std::uint16_t revision = 0U;
        std::uint32_t build = 0U;
        bool confirmed = false;
    };

    /** @brief 설정에서 session nonce와 대상 역할을 복원합니다. */
    int loadSessionEntry(const char *key, std::size_t length,
                         settings_read_cb read_callback, void *callback_argument, void *)
    {
        if ((key != nullptr) && (::strcmp(key, "nonce") == 0) &&
            (length == sizeof(nonce)))
        {
            const ssize_t read = read_callback(callback_argument, nonce, sizeof(nonce));
            nonce_valid = read == static_cast<ssize_t>(sizeof(nonce)) &&
                          nonce[nonce_length] == '\0';
        }
        else if ((key != nullptr) && (::strcmp(key, "role") == 0) &&
                 (length == sizeof(role)))
        {
            static_cast<void>(read_callback(callback_argument, &role, sizeof(role)));
        }
        return 0;
    }

    /** @brief 저장된 역할을 protocol 문자열로 변환합니다. */
    const char *roleName()
    {
        if (role == 'a')
        {
            return "target_a";
        }
        if (role == 'b')
        {
            return "target_b";
        }
        return "candidate_unknown";
    }

    /** @brief protocol record에 session과 exact source를 결합합니다. */
    void printSuffix()
    {
        Serial.print("|nonce=");
        Serial.print(nonce_valid ? nonce : "none");
        Serial.print("|core=");
        Serial.print(M32_MDFU_CORE_REVISION);
    }

    /** @brief 첫 실패만 bounded protocol로 출력합니다. */
    void fail(const char *stage, int code = 0)
    {
        if (failed)
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
        failed = true;
    }

    /** @brief active slot의 MCUboot header를 읽습니다. */
    bool activeImage(ActiveImage &image)
    {
        struct mcuboot_img_header header{};
        const int error =
            boot_read_bank_header(PARTITION_ID(slot0_partition), &header, sizeof(header));
        if ((error != 0) || (header.mcuboot_version != 1U))
        {
            return false;
        }
        image.major = header.h.v1.sem_ver.major;
        image.minor = header.h.v1.sem_ver.minor;
        image.revision = header.h.v1.sem_ver.revision;
        image.build = header.h.v1.sem_ver.build_num;
        image.confirmed = boot_is_img_confirmed();
        return true;
    }

    /** @brief 현재 candidate boot 상태를 출력합니다. */
    void reportBoot()
    {
        ActiveImage image{};
        if (!nonce_valid || ((role != 'a') && (role != 'b')) || !activeImage(image))
        {
            fail("session_restore");
            return;
        }
        Serial.print(protocol);
        Serial.print("|BOOT|role=");
        Serial.print(roleName());
        Serial.print("|version=");
        Serial.print(image.major);
        Serial.print('.');
        Serial.print(image.minor);
        Serial.print('.');
        Serial.print(image.revision);
        Serial.print('+');
        Serial.print(static_cast<unsigned long>(image.build));
        Serial.print("|confirmed=");
        Serial.print(image.confirmed ? 1 : 0);
        Serial.print("|active_slot=");
        Serial.print(static_cast<unsigned int>(boot_fetch_active_slot()));
        printSuffix();
        Serial.println();
    }

    /** @brief 저장된 nonce와 일치하는 명령인지 확인합니다. */
    bool hasSessionPrefix(const char *prefix)
    {
        const std::size_t prefix_length = ::strlen(prefix);
        return nonce_valid && (::strncmp(command, prefix, prefix_length) == 0) &&
               (::strncmp(command + prefix_length, nonce, nonce_length) == 0);
    }

    /** @brief candidate confirm 또는 rollback 대기 상태를 적용합니다. */
    bool applyCandidate()
    {
        if (!hasSessionPrefix(apply_prefix))
        {
            return false;
        }
        const char *cursor = command + ::strlen(apply_prefix) + nonce_length;
        constexpr char iteration_prefix[] = "|iteration=";
        if ((::strncmp(cursor, iteration_prefix, sizeof(iteration_prefix) - 1U) != 0) ||
            (cursor[sizeof(iteration_prefix) - 1U] < '1') ||
            (cursor[sizeof(iteration_prefix) - 1U] > '5'))
        {
            return false;
        }
        const std::uint8_t iteration = static_cast<std::uint8_t>(
            cursor[sizeof(iteration_prefix) - 1U] - '0');
        cursor += sizeof(iteration_prefix);
        constexpr char confirm_prefix[] = "|confirm=";
        if ((::strncmp(cursor, confirm_prefix, sizeof(confirm_prefix) - 1U) != 0) ||
            ((cursor[sizeof(confirm_prefix) - 1U] != '0') &&
             (cursor[sizeof(confirm_prefix) - 1U] != '1')))
        {
            return false;
        }
        const bool confirm = cursor[sizeof(confirm_prefix) - 1U] == '1';
        cursor += sizeof(confirm_prefix);
        if ((::strncmp(cursor, "|core=", 6U) != 0) ||
            (::strcmp(cursor + 6U, M32_MDFU_CORE_REVISION) != 0))
        {
            return false;
        }
        if (candidate_applied)
        {
            fail("duplicate_apply");
            return true;
        }
        if (confirm && (boot_write_img_confirmed() != 0))
        {
            fail("confirm");
            return true;
        }
        candidate_applied = true;
        Serial.print(protocol);
        Serial.print("|APPLIED|role=");
        Serial.print(roleName());
        Serial.print("|iteration=");
        Serial.print(static_cast<unsigned int>(iteration));
        Serial.print("|confirmed=");
        Serial.print(confirm ? 1 : 0);
        printSuffix();
        Serial.println();
        return true;
    }

    /** @brief candidate의 PROBE·APPLY·STOP 명령을 처리합니다. */
    void processCommand()
    {
        if (::strcmp(command, "M32MDFU|1|PROBE") == 0)
        {
            ActiveImage image{};
            if (!activeImage(image))
            {
                fail("probe_header");
                return;
            }
            Serial.print(protocol);
            Serial.print("|READY|role=");
            Serial.print(roleName());
            Serial.print("|version=");
            Serial.print(image.major);
            Serial.print('.');
            Serial.print(image.minor);
            Serial.print('.');
            Serial.print(image.revision);
            Serial.print('+');
            Serial.print(static_cast<unsigned long>(image.build));
            Serial.print("|confirmed=");
            Serial.print(image.confirmed ? 1 : 0);
            Serial.print("|cdb_node_slots=3|cdb_local_slots=1|core=");
            Serial.println(M32_MDFU_CORE_REVISION);
            return;
        }
        if (applyCandidate())
        {
            return;
        }
        if (hasSessionPrefix(stop_prefix) &&
            (::strcmp(command + ::strlen(stop_prefix) + nonce_length, "") == 0))
        {
            Serial.print(protocol);
            Serial.print("|STOPPED|role=");
            Serial.print(roleName());
            Serial.print("|cleanup=pass");
            printSuffix();
            Serial.println();
            return;
        }
        fail("command");
    }

    /** @brief CR/LF serial command를 overflow 없이 수집합니다. */
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
            if ((incoming < 0) || (command_length + 1U >= sizeof(command)))
            {
                command_length = 0U;
                fail("command_length");
                continue;
            }
            command[command_length++] = static_cast<char>(incoming);
        }
    }
} // namespace

/** @brief 최소 candidate 상태와 저장된 session을 준비합니다. */
void setup()
{
    Serial.begin(115200);
    const int settings_error = settings_subsys_init();
    if ((settings_error != 0) && (settings_error != -EALREADY))
    {
        fail("settings_init", settings_error);
        return;
    }
    static_cast<void>(settings_load_subtree_direct("m32mdfu", loadSessionEntry, nullptr));
    ActiveImage image{};
    if (!activeImage(image) || (image.major != 2U))
    {
        fail("candidate_version");
        return;
    }
    reportBoot();
}

/** @brief candidate UART oracle를 bounded polling으로 처리합니다. */
void loop()
{
    pollSerial();
    delay(1);
}
