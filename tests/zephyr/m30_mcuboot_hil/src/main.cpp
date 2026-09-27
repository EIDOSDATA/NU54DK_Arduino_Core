/**
 * @file main.cpp
 * @brief M30 MCUboot 서명·boot·negative image HIL 명령을 제공합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <Arduino.h>

#include <zephyr/dfu/mcuboot.h>
#include <zephyr/kernel.h>
#include <zephyr/storage/flash_map.h>
#include <zephyr/sys/reboot.h>

#include <stddef.h>
#include <string.h>

namespace
{
    /** @brief protocol 입력 한 줄의 최대 크기입니다. */
    constexpr size_t command_capacity = 192U;
    char command[command_capacity] = {};
    size_t command_length = 0U;

    /** @brief exact revision을 포함한 protocol suffix를 출력합니다. */
    void printSuffix()
    {
        Serial.print("|core=");
        Serial.println(M30_BOOT_CORE_REVISION);
    }

    /** @brief 현재 MCUboot 상태를 직렬 protocol로 출력합니다. */
    void printReady(int confirm_result)
    {
        struct mcuboot_img_header header = {};
        const int header_result = boot_read_bank_header(
            PARTITION_ID(slot0_partition), &header, sizeof(header));

        if ((header_result != 0) || (header.mcuboot_version != 1U))
        {
            Serial.print("M30BOOT|1|FAIL|reason=active-header|rc=");
            Serial.print(header_result);
            printSuffix();
            return;
        }
        Serial.print("M30BOOT|1|READY|active_slot=");
        Serial.print(static_cast<unsigned int>(boot_fetch_active_slot()));
        Serial.print("|confirmed=");
        Serial.print(boot_is_img_confirmed() ? 1U : 0U);
        Serial.print("|confirm_rc=");
        Serial.print(confirm_result);
        Serial.print("|version=");
        Serial.print(static_cast<unsigned int>(header.h.v1.sem_ver.major));
        Serial.print('.');
        Serial.print(static_cast<unsigned int>(header.h.v1.sem_ver.minor));
        Serial.print('.');
        Serial.print(static_cast<unsigned int>(header.h.v1.sem_ver.revision));
        Serial.print('+');
        Serial.print(static_cast<unsigned long>(header.h.v1.sem_ver.build_num));
        printSuffix();
    }

    /** @brief 검증 runner가 요청한 warm reboot를 수행합니다. */
    void rebootTarget()
    {
        Serial.print("M30BOOT|1|REBOOTING");
        printSuffix();
        Serial.flush();
        k_msleep(50);
        sys_reboot(SYS_REBOOT_WARM);
    }

    /** @brief 한 줄 command를 fail-closed 방식으로 처리합니다. */
    void processCommand(const char *line)
    {
        if (::strcmp(line, "M30BOOT|1|PING") == 0)
        {
            printReady(0);
        }
        else if (::strcmp(line, "M30BOOT|1|REBOOT") == 0)
        {
            rebootTarget();
        }
        else if (::strcmp(line, "M30BOOT|1|REQUEST_TEST") == 0)
        {
            const int result = boot_request_upgrade(BOOT_UPGRADE_TEST);

            Serial.print("M30BOOT|1|REQUEST_TEST|rc=");
            Serial.print(result);
            printSuffix();
        }
        else
        {
            Serial.print("M30BOOT|1|FAIL|reason=unknown-command");
            printSuffix();
        }
    }

    /** @brief VCOM에서 CR/LF로 끝나는 한 줄을 수신합니다. */
    void pollCommands()
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
                if (command_length != 0U)
                {
                    command[command_length] = '\0';
                    processCommand(command);
                    command_length = 0U;
                }
                continue;
            }
            if (command_length + 1U >= sizeof(command))
            {
                command_length = 0U;
                Serial.print("M30BOOT|1|FAIL|reason=command-too-long");
                printSuffix();
                continue;
            }
            command[command_length] = value;
            command_length++;
        }
    }
} // namespace

/** @brief 실행 image를 confirm하고 boot 검증 protocol을 시작합니다. */
void setup()
{
    Serial.begin(115200);
    const int confirm_result = boot_write_img_confirmed();

    printReady(confirm_result);
}

/** @brief bounded UART command polling을 계속 수행합니다. */
void loop()
{
    pollCommands();
    k_msleep(2);
}
