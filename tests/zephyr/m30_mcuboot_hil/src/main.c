/**
 * @file main.c
 * @brief M30 MCUboot 서명·boot·negative image HIL 명령을 제공합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <zephyr/device.h>
#include <zephyr/dfu/mcuboot.h>
#include <zephyr/devicetree.h>
#include <zephyr/drivers/uart.h>
#include <zephyr/kernel.h>
#include <zephyr/storage/flash_map.h>
#include <zephyr/sys/printk.h>
#include <zephyr/sys/reboot.h>

#include <stdbool.h>
#include <stddef.h>
#include <string.h>

/** @brief protocol 입력 한 줄의 최대 크기입니다. */
#define M30_BOOT_COMMAND_CAPACITY 192U

static const struct device *const console = DEVICE_DT_GET(DT_CHOSEN(zephyr_console));

/** @brief exact revision을 포함한 protocol suffix를 출력합니다. */
static void print_suffix(void)
{
	printk("|core=%s\n", M30_BOOT_CORE_REVISION);
}

/** @brief 현재 MCUboot 상태를 직렬 protocol로 출력합니다. */
static void print_ready(int confirm_result)
{
	struct mcuboot_img_header header = {0};
	const int header_result = boot_read_bank_header(
		PARTITION_ID(slot0_partition), &header, sizeof(header));

	if (header_result != 0 || header.mcuboot_version != 1U)
	{
		printk("M30BOOT|1|FAIL|reason=active-header|rc=%d", header_result);
		print_suffix();
		return;
	}
	printk("M30BOOT|1|READY|active_slot=%u|confirmed=%u|confirm_rc=%d"
	       "|version=%u.%u.%u+%u",
	       boot_fetch_active_slot(), boot_is_img_confirmed() ? 1U : 0U,
	       confirm_result, header.h.v1.sem_ver.major, header.h.v1.sem_ver.minor,
	       header.h.v1.sem_ver.revision, header.h.v1.sem_ver.build_num);
	print_suffix();
}

/** @brief 검증 runner가 요청한 warm reboot를 수행합니다. */
static void reboot_target(void)
{
	printk("M30BOOT|1|REBOOTING");
	print_suffix();
	k_msleep(50);
	sys_reboot(SYS_REBOOT_WARM);
}

/** @brief 한 줄 command를 fail-closed 방식으로 처리합니다. */
static void process_command(const char *command)
{
	if (strcmp(command, "M30BOOT|1|PING") == 0)
	{
		print_ready(0);
	}
	else if (strcmp(command, "M30BOOT|1|REBOOT") == 0)
	{
		reboot_target();
	}
	else if (strcmp(command, "M30BOOT|1|REQUEST_TEST") == 0)
	{
		const int result = boot_request_upgrade(BOOT_UPGRADE_TEST);

		printk("M30BOOT|1|REQUEST_TEST|rc=%d", result);
		print_suffix();
	}
	else
	{
		printk("M30BOOT|1|FAIL|reason=unknown-command");
		print_suffix();
	}
}

/** @brief UART에서 CR/LF로 끝나는 한 줄을 수신합니다. */
static void poll_commands(void)
{
	char command[M30_BOOT_COMMAND_CAPACITY] = {0};
	size_t length = 0U;

	while (true)
	{
		unsigned char value = 0U;

		if (uart_poll_in(console, &value) != 0)
		{
			k_msleep(2);
			continue;
		}
		if (value == '\r' || value == '\n')
		{
			if (length != 0U)
			{
				command[length] = '\0';
				process_command(command);
				length = 0U;
			}
			continue;
		}
		if (length + 1U >= sizeof(command))
		{
			length = 0U;
			printk("M30BOOT|1|FAIL|reason=command-too-long");
			print_suffix();
			continue;
		}
		command[length] = (char)value;
		length++;
	}
}

/** @brief 실행 image를 confirm하고 boot 검증 protocol을 시작합니다. */
int main(void)
{
	int confirm_result;

	if (!device_is_ready(console))
	{
		return 1;
	}
	confirm_result = boot_write_img_confirmed();
	print_ready(confirm_result);
	poll_commands();
	return 0;
}
