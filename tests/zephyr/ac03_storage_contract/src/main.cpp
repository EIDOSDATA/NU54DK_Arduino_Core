/**
 * @file main.cpp
 * @brief AC-03 저장소 공개 API와 fixed-partition target 계약을 검증합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <EEPROM.h>
#include <LittleFS.h>

#include <zephyr/devicetree.h>
#include <zephyr/ztest.h>

static_assert(EEPROMClass::maximum_size == 1024U,
			  "EEPROM mirror 크기가 AC-03 계약과 다릅니다.");
static_assert(__is_base_of(Stream, File),
			  "File은 Arduino Stream이어야 합니다.");
static_assert(__is_constructible(File, const File &),
			  "대표 Arduino 라이브러리를 위해 File 참조 복사가 필요합니다.");
static_assert(DT_REG_ADDR(DT_NODELABEL(slot0_partition)) == 0x0,
			  "loaderless image가 reset vector에서 시작하지 않습니다.");
static_assert(DT_REG_SIZE(DT_NODELABEL(slot0_partition)) == 0x16c000,
			  "loaderless image 크기가 1456 KiB가 아닙니다.");
static_assert(DT_SAME_NODE(DT_CHOSEN(zephyr_code_partition),
						   DT_NODELABEL(slot0_partition)),
			  "Zephyr code partition이 loaderless image와 다릅니다.");
static_assert(DT_REG_ADDR(DT_NODELABEL(arduino_fs_partition)) == 0x16c000,
			  "LittleFS 시작 주소가 다릅니다.");
static_assert(DT_REG_SIZE(DT_NODELABEL(arduino_fs_partition)) == 0x8000,
			  "LittleFS 크기가 32 KiB가 아닙니다.");
static_assert(DT_REG_ADDR(DT_NODELABEL(storage_partition)) == 0x174000,
			  "Settings storage 시작 주소가 보존되지 않았습니다.");
static_assert(DT_REG_SIZE(DT_NODELABEL(storage_partition)) == 0x9000,
			  "Settings storage 크기가 보존되지 않았습니다.");

ZTEST(ac03_storage_contract, test_public_bounds_are_fail_closed)
{
	zassert_true(EEPROM.begin(1024U), "EEPROM begin 실패: %d",
				 static_cast<int>(EEPROM.lastError()));
	EEPROM.write(-1, 0x12U);
	zassert_equal(EEPROM.lastError(), EEPROMError::out_of_bounds,
				  "음수 주소가 차단되지 않았습니다.");
	EEPROM.write(1024, 0x34U);
	zassert_equal(EEPROM.lastError(), EEPROMError::out_of_bounds,
				  "끝 주소가 차단되지 않았습니다.");
}

ZTEST(ac03_storage_contract, test_littlefs_requires_mount)
{
	static_cast<void>(LittleFS.end());
	File file = LittleFS.open("/must-not-open.bin", FILE_READ);
	zassert_false(static_cast<bool>(file), "unmount 상태에서 파일이 열렸습니다.");
	zassert_equal(LittleFS.lastError(), FSError::not_mounted,
				  "unmount 오류가 안정 분류로 반환되지 않았습니다.");
}

ZTEST_SUITE(ac03_storage_contract, nullptr, nullptr, nullptr, nullptr, nullptr);
