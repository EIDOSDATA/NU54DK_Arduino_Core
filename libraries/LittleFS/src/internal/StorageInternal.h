/** @file @brief LittleFS path·slot·mount의 고정 상태와 잠금 경계입니다.
 * SPDX-License-Identifier: MIT
 */
#pragma once
#include <FS.h>
#include <zephyr/fs/fs.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/atomic.h>
#include <errno.h>
#include <limits.h>
#include <stdio.h>
#include <string.h>
namespace nucode::littlefs::internal
{
    inline constexpr std::uint8_t maximum_open_files = 4U;
    inline constexpr std::uint8_t invalid_slot = 0xffU;
    inline constexpr std::size_t maximum_path_length = 255U;
    inline constexpr char mount_point[] = "/littlefs";

    /** @brief 한 Arduino File이 소유하는 고정 Zephyr handle slot입니다. */
    struct FileSlot
    {
        fs_file_t file{};
        std::uint32_t generation{0U};
        std::uint16_t references{0U};
        bool active{false};
        char path[maximum_path_length + 1U]{};
    };

    /** @brief slot 배열과 별개로 filesystem 상태·오류를 보존합니다. */
    struct FileSystemState
    {
        bool filesystem_mounted = false;
        atomic_t last_error_value = ATOMIC_INIT(static_cast<atomic_val_t>(FSError::none));
        atomic_t last_driver_error_value = ATOMIC_INIT(0);
    };
    using FileSlots = FileSlot[maximum_open_files];
    FileSystemState &filesystemState() noexcept;
    FileSlots &fileSlots() noexcept;
    k_mutex &filesystemMutex() noexcept;
    FSError recordError(FSError error, int driver_error = 0) noexcept;
    FSError recordDriverError(int result) noexcept;
    bool isThreadContext() noexcept;
    bool normalizePath(const char *path, char *destination, std::size_t capacity) noexcept;
    bool parseMode(const char *mode, fs_mode_t &flags) noexcept;
    FileSlot *validSlot(std::uint8_t slot, std::uint32_t generation) noexcept;
    bool retainSlotLocked(std::uint8_t index, std::uint32_t generation) noexcept;
    void releaseSlotLocked(std::uint8_t index, std::uint32_t generation) noexcept;
    bool hasOpenFiles() noexcept;
} // namespace nucode::littlefs::internal
