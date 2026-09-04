/**
 * @file LittleFS.h
 * @brief 전용 32 KiB partition을 사용하는 NU54DK LittleFS API입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#ifndef NUCODE_ARDUINO_LIBRARY_LITTLEFS_H_
#define NUCODE_ARDUINO_LIBRARY_LITTLEFS_H_

#include <FS.h>

/** @brief 비파괴 mount와 명시적 복구를 제공하는 LittleFS facade입니다. */
class LittleFSClass final : public FS
{
  public:
    /**
	 * @brief 전용 partition을 mount합니다.
	 * @param format_on_fail true일 때만 실패한 partition을 명시적으로 포맷합니다.
	 */
    bool begin(bool format_on_fail = false);

    /** @brief 열린 파일이 없을 때 filesystem을 unmount합니다. */
    bool end();

    /** @brief 전용 partition을 명시적으로 포맷하고 다시 mount합니다. */
    bool format();

    /** @brief filesystem이 보고하는 전체 byte 수를 반환합니다. */
    std::size_t totalBytes();

    /** @brief filesystem이 보고하는 사용 byte 수를 반환합니다. */
    std::size_t usedBytes();

    /** @brief 현재 mount 상태를 반환합니다. */
    bool mounted() const noexcept;

    /** @brief 마지막 안정 오류를 반환합니다. */
    FSError lastError() const noexcept;

    /** @brief 마지막 Zephyr filesystem 오류 번호를 반환합니다. */
    int lastDriverError() const noexcept;
};

/** @brief sketch가 공유하는 전역 LittleFS 객체입니다. */
extern LittleFSClass LittleFS;

#endif
