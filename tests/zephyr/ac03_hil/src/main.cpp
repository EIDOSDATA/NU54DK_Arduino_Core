/**
 * @file main.cpp
 * @brief 두 NU54DK에서 EEPROM·LittleFS reset 영속성과 복구를 검증합니다.
 *
 * @note START와 CLEAR는 EEPROM mirror 및 AC-03 전용 LittleFS 시험 파일을
 * 변경하므로 host runner가 명시적 파괴 승인 뒤에만 보냅니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <Arduino.h>
#include <EEPROM.h>
#include <LittleFS.h>

#include <ctype.h>
#include <errno.h>
#include <string.h>

#include <zephyr/devicetree.h>
#include <zephyr/kernel.h>
#include <zephyr/settings/settings.h>
#include <zephyr/storage/flash_map.h>
#include <zephyr/sys/reboot.h>

namespace
{
    constexpr std::uint32_t protocol_schema = 1U;
    constexpr std::uint32_t state_magic = 0x41433033UL;
    constexpr std::size_t nonce_length = 32U;
    constexpr char state_key[] = "ac03/hil/state";
    constexpr char eeprom_key[] = "arduino/eeprom";
    constexpr char filesystem_path[] = "/ac03-persistence.bin";
    constexpr std::uint32_t seeded_value = 0x5aa503e1UL;
    constexpr std::uint32_t recovered_value = 0xc33c03e2UL;
    constexpr std::uint32_t file_value = 0x1f5303a5UL;

    /** @brief reset 경계에서 이어 갈 저장소 HIL 단계입니다. */
    enum class Stage : std::uint32_t
    {
        idle = 0U,
        verify_persistence = 1U,
        verify_corruption = 2U,
        verify_recovery = 3U,
    };

    /** @brief Settings/ZMS에 저장하는 고정 크기 HIL 상태입니다. */
    struct ScenarioState
    {
        std::uint32_t magic{state_magic};
        std::uint32_t schema{protocol_schema};
        Stage stage{Stage::idle};
        char nonce[nonce_length + 1U]{};
        std::uint32_t guard{0U};
    };

    /** @brief HIL state의 단순 회전-XOR guard를 계산합니다. */
    std::uint32_t stateGuard(const ScenarioState &state) noexcept
    {
        std::uint32_t guard =
            state.magic ^ state.schema ^ static_cast<std::uint32_t>(state.stage) ^ 0xa503c33cUL;
        for (std::size_t index = 0U; index < nonce_length; ++index)
        {
            guard = (guard << 5U) | (guard >> 27U);
            guard ^= static_cast<std::uint8_t>(state.nonce[index]);
        }
        return guard;
    }

    /** @brief protocol에 사용할 단계 이름을 반환합니다. */
    const char *stageName(Stage stage) noexcept
    {
        switch (stage)
        {
        case Stage::idle:
            return "idle";
        case Stage::verify_persistence:
            return "verify_persistence";
        case Stage::verify_corruption:
            return "verify_corruption";
        case Stage::verify_recovery:
            return "verify_recovery";
        default:
            return "invalid";
        }
    }

    /** @brief 고정 길이 소문자 16진 nonce인지 검사합니다. */
    bool validNonce(const char *nonce) noexcept
    {
        if (nonce == nullptr || strlen(nonce) != nonce_length)
        {
            return false;
        }
        for (std::size_t index = 0U; index < nonce_length; ++index)
        {
            const unsigned char value = static_cast<unsigned char>(nonce[index]);
            if (isdigit(value) == 0 && (value < 'a' || value > 'f'))
            {
                return false;
            }
        }
        return true;
    }

    /** @brief 저장된 HIL 상태와 guard가 모두 유효한지 반환합니다. */
    bool validState(const ScenarioState &state) noexcept
    {
        const std::uint32_t stage = static_cast<std::uint32_t>(state.stage);
        return state.magic == state_magic && state.schema == protocol_schema &&
               stage >= static_cast<std::uint32_t>(Stage::verify_persistence) &&
               stage <= static_cast<std::uint32_t>(Stage::verify_recovery) &&
               validNonce(state.nonce) && state.guard == stateGuard(state);
    }

    /** @brief UART FAIL token을 남기고 파괴 작업 없이 멈춥니다. */
    [[noreturn]] void fail(const char *phase, int error) noexcept
    {
        Serial.print("NUCODE_AC03_FAIL:phase=");
        Serial.print(phase);
        Serial.print(":error=");
        Serial.println(error);
        Serial.flush();
        for (;;)
        {
            k_sleep(K_SECONDS(1));
        }
    }

    /** @brief 상태를 Settings value 하나로 저장합니다. */
    void saveState(ScenarioState &state, Stage next) noexcept
    {
        state.stage = next;
        state.guard = stateGuard(state);
        const int result = settings_save_one(state_key, &state, sizeof(state));
        if (result != 0)
        {
            fail("STATE_SAVE", result);
        }
    }

    /** @brief 저장된 상태를 읽고 손상 또는 부재를 idle로 처리합니다. */
    bool loadState(ScenarioState &state) noexcept
    {
        const ssize_t length = settings_load_one(state_key, &state, sizeof(state));
        return length == static_cast<ssize_t>(sizeof(state)) && validState(state);
    }

    /** @brief 현재 단계와 nonce를 반복 가능한 boot token으로 출력합니다. */
    void reportBoot(const ScenarioState *state) noexcept
    {
        Serial.print("NUCODE_AC03_BOOT:schema=1:stage=");
        Serial.print(state == nullptr ? "idle" : stageName(state->stage));
        Serial.print(":nonce=");
        Serial.println(state == nullptr ? "none" : state->nonce);
        Serial.flush();
    }

    /** @brief CR/LF 명령 한 줄을 고정 buffer 안에서 읽습니다. */
    bool readCommand(char *destination, std::size_t capacity, const ScenarioState *state) noexcept
    {
        std::size_t length = 0U;
        std::uint32_t idle_ticks = 0U;
        for (;;)
        {
            if (Serial.available() <= 0)
            {
                k_sleep(K_MSEC(5));
                if (++idle_ticks >= 400U)
                {
                    idle_ticks = 0U;
                    reportBoot(state);
                }
                continue;
            }
            const int value = Serial.read();
            if (value < 0)
            {
                continue;
            }
            if (value == '\r' || value == '\n')
            {
                if (length == 0U)
                {
                    continue;
                }
                destination[length] = '\0';
                return true;
            }
            if (length + 1U >= capacity)
            {
                length = 0U;
                continue;
            }
            destination[length++] = static_cast<char>(value);
        }
    }

    /** @brief LittleFS 시험 파일의 정확한 32-bit 값을 검증합니다. */
    bool verifyFilesystemValue(std::uint32_t expected) noexcept
    {
        File file = LittleFS.open(filesystem_path, FILE_READ);
        std::uint32_t actual = 0U;
        const std::size_t read =
            file ? file.readBytes(reinterpret_cast<std::uint8_t *>(&actual), sizeof(actual)) : 0U;
        file.close();
        return read == sizeof(actual) && actual == expected;
    }

    /** @brief 시험 파일에 정확한 32-bit 값을 기록합니다. */
    bool writeFilesystemValue(std::uint32_t value) noexcept
    {
        File file = LittleFS.open(filesystem_path, FILE_WRITE);
        const std::size_t written =
            file ? file.write(reinterpret_cast<const std::uint8_t *>(&value), sizeof(value)) : 0U;
        file.close();
        return written == sizeof(value);
    }

    /** @brief 다음 reset 전에 protocol token을 확실히 전송합니다. */
    [[noreturn]] void rebootAfterToken(const char *token) noexcept
    {
        Serial.println(token);
        Serial.flush();
        k_sleep(K_MSEC(50));
        sys_reboot(SYS_REBOOT_COLD);
        for (;;)
        {
        }
    }

    /** @brief 명시적 CLEAR가 시험 data만 지우고 idle로 되돌립니다. */
    [[noreturn]] void clearScenario() noexcept
    {
        if (!EEPROM.reset(EEPROMClass::maximum_size))
        {
            fail("CLEAR_EEPROM", EEPROM.lastDriverError());
        }
        if (LittleFS.begin(false))
        {
            if (LittleFS.exists(filesystem_path) && !LittleFS.remove(filesystem_path))
            {
                fail("CLEAR_FILE", LittleFS.lastDriverError());
            }
            static_cast<void>(LittleFS.end());
        }
        const int result = settings_delete(state_key);
        if (result != 0 && result != -ENOENT)
        {
            fail("CLEAR_STATE", result);
        }
        rebootAfterToken("NUCODE_AC03_CLEARED:PASS");
    }

    /** @brief idle START에서 전용 FS를 지우고 비파괴 mount와 명시 format을 검증합니다. */
    [[noreturn]] void seedScenario(ScenarioState &state) noexcept
    {
        const flash_area *area = nullptr;
        const int opened =
            flash_area_open(DT_FIXED_PARTITION_ID(DT_NODELABEL(arduino_fs_partition)), &area);
        if (opened != 0 || area == nullptr)
        {
            fail("FS_AREA_OPEN", opened);
        }
        const int erased = flash_area_erase(area, 0U, area->fa_size);
        flash_area_close(area);
        if (erased != 0)
        {
            fail("FS_AREA_ERASE", erased);
        }

        if (LittleFS.begin(false))
        {
            fail("FS_IMPLICIT_FORMAT", 1);
        }
        if (!LittleFS.format())
        {
            fail("FS_EXPLICIT_FORMAT", LittleFS.lastDriverError());
        }
        if (!writeFilesystemValue(file_value))
        {
            fail("FS_SEED", LittleFS.lastDriverError());
        }

        if (!EEPROM.reset(EEPROMClass::maximum_size))
        {
            fail("EEPROM_RESET", EEPROM.lastDriverError());
        }
        EEPROM.put(16, seeded_value);
        if (!EEPROM.commit())
        {
            fail("EEPROM_SEED", EEPROM.lastDriverError());
        }
        saveState(state, Stage::verify_persistence);
        rebootAfterToken(
            "NUCODE_AC03_SEED:PASS:eeprom_commit=1:littlefs_no_format=1:littlefs_format=1");
    }

    /** @brief 첫 reset 뒤 EEPROM과 LittleFS 값을 읽고 EEPROM record를 손상시킵니다. */
    [[noreturn]] void verifyPersistence(ScenarioState &state) noexcept
    {
        std::uint32_t value = 0U;
        if (!EEPROM.begin(EEPROMClass::maximum_size))
        {
            fail("EEPROM_REOPEN", EEPROM.lastDriverError());
        }
        EEPROM.get(16, value);
        if (value != seeded_value)
        {
            fail("EEPROM_PERSISTENCE", static_cast<int>(value));
        }
        if (!LittleFS.begin(false) || !verifyFilesystemValue(file_value))
        {
            fail("FS_PERSISTENCE", LittleFS.lastDriverError());
        }
        Serial.println("NUCODE_AC03_RESET_PERSISTENCE:PASS:eeprom=1:littlefs=1");
        const std::uint8_t malformed[] = {0x41U, 0x43U, 0x30U, 0x33U, 0xffU};
        const int corrupted = settings_save_one(eeprom_key, malformed, sizeof(malformed));
        if (corrupted != 0)
        {
            fail("EEPROM_CORRUPT_INJECT", corrupted);
        }
        saveState(state, Stage::verify_corruption);
        rebootAfterToken("NUCODE_AC03_CORRUPTION_INJECTED:PASS:length=5");
    }

    /** @brief 손상 record를 거부하고 명시적 EEPROM reset으로 복구합니다. */
    [[noreturn]] void verifyCorruption(ScenarioState &state) noexcept
    {
        if (EEPROM.begin(EEPROMClass::maximum_size) || EEPROM.lastError() != EEPROMError::corrupt)
        {
            fail("EEPROM_CORRUPT_ACCEPTED", static_cast<int>(EEPROM.lastError()));
        }
        if (!EEPROM.reset(EEPROMClass::maximum_size))
        {
            fail("EEPROM_RECOVER", EEPROM.lastDriverError());
        }
        EEPROM.put(16, recovered_value);
        if (!EEPROM.commit())
        {
            fail("EEPROM_RECOVER_COMMIT", EEPROM.lastDriverError());
        }
        if (!LittleFS.begin(false) || !verifyFilesystemValue(file_value))
        {
            fail("FS_AFTER_EEPROM_CORRUPTION", LittleFS.lastDriverError());
        }
        File escaped = LittleFS.open("../escape.bin", FILE_WRITE);
        if (escaped || LittleFS.lastError() != FSError::invalid_argument)
        {
            fail("FS_PATH_TRAVERSAL", static_cast<int>(LittleFS.lastError()));
        }
        saveState(state, Stage::verify_recovery);
        rebootAfterToken("NUCODE_AC03_CORRUPTION_RECOVERY:PASS:rejected=1:explicit_reset=1:fs_"
                         "isolated=1:path_bounds=1");
    }

    /** @brief 복구 record의 reset 영속성을 검증하고 시험 data를 정리합니다. */
    [[noreturn]] void verifyRecovery(ScenarioState &state) noexcept
    {
        std::uint32_t value = 0U;
        if (!EEPROM.begin(EEPROMClass::maximum_size))
        {
            fail("RECOVERY_REOPEN", EEPROM.lastDriverError());
        }
        EEPROM.get(16, value);
        if (value != recovered_value)
        {
            fail("RECOVERY_PERSISTENCE", static_cast<int>(value));
        }
        if (!LittleFS.begin(false) || !verifyFilesystemValue(file_value))
        {
            fail("RECOVERY_FS_PERSISTENCE", LittleFS.lastDriverError());
        }
        if (!LittleFS.remove(filesystem_path))
        {
            fail("CLEANUP_FILE", LittleFS.lastDriverError());
        }
        if (!LittleFS.end())
        {
            fail("CLEANUP_UNMOUNT", LittleFS.lastDriverError());
        }
        if (!EEPROM.reset(EEPROMClass::maximum_size))
        {
            fail("CLEANUP_EEPROM", EEPROM.lastDriverError());
        }
        const int deleted = settings_delete(state_key);
        if (deleted != 0)
        {
            fail("CLEANUP_STATE", deleted);
        }
        Serial.print("NUCODE_AC03_FINAL:PASS:nonce=");
        Serial.print(state.nonce);
        Serial.println(":reset_persistence=1:corruption_recovery=1:cleanup=1");
        Serial.flush();
        for (;;)
        {
            k_sleep(K_SECONDS(1));
        }
    }
} // namespace

void setup()
{
    Serial.begin(115200);
    const int initialized = settings_subsys_init();
    if (initialized != 0)
    {
        fail("SETTINGS_INIT", initialized);
    }

    ScenarioState state{};
    const bool has_state = loadState(state);
    reportBoot(has_state ? &state : nullptr);
    char command[96]{};
    if (!readCommand(command, sizeof(command), has_state ? &state : nullptr))
    {
        fail("COMMAND_READ", -EINVAL);
    }
    if (strcmp(command, "NUCODE_AC03_COMMAND:CLEAR") == 0)
    {
        clearScenario();
    }

    constexpr char start_prefix[] = "NUCODE_AC03_COMMAND:START:";
    constexpr char continue_prefix[] = "NUCODE_AC03_COMMAND:CONTINUE:";
    if (!has_state && strncmp(command, start_prefix, sizeof(start_prefix) - 1U) == 0)
    {
        const char *nonce = command + sizeof(start_prefix) - 1U;
        if (!validNonce(nonce))
        {
            fail("START_NONCE", -EINVAL);
        }
        memcpy(state.nonce, nonce, nonce_length + 1U);
        seedScenario(state);
    }
    if (has_state && strncmp(command, continue_prefix, sizeof(continue_prefix) - 1U) == 0)
    {
        const char *nonce = command + sizeof(continue_prefix) - 1U;
        if (!validNonce(nonce) || strcmp(nonce, state.nonce) != 0)
        {
            fail("CONTINUE_NONCE", -EINVAL);
        }
        switch (state.stage)
        {
        case Stage::verify_persistence:
            verifyPersistence(state);
        case Stage::verify_corruption:
            verifyCorruption(state);
        case Stage::verify_recovery:
            verifyRecovery(state);
        default:
            break;
        }
    }
    fail("COMMAND", -EINVAL);
}

void loop()
{
    k_sleep(K_SECONDS(1));
}
