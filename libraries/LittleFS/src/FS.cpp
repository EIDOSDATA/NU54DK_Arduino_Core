/**
 * @file FS.cpp
 * @brief 고정 handle Arduino 파일 facade를 구현합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <FS.h>

#if !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE)

#include <errno.h>
#include <limits.h>
#include <stdio.h>
#include <string.h>

#include <zephyr/fs/fs.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/atomic.h>

namespace nucode::littlefs::internal
{
    constexpr std::uint8_t maximum_open_files = 4U;
    constexpr std::uint8_t invalid_slot = 0xffU;
    constexpr std::size_t maximum_path_length = 255U;
    extern const char mount_point[] = "/littlefs";

    /** @brief 한 Arduino File이 소유하는 고정 Zephyr handle slot입니다. */
    struct FileSlot
    {
        fs_file_t file{};
        std::uint32_t generation{0U};
        std::uint16_t references{0U};
        bool active{false};
        char path[maximum_path_length + 1U]{};
    };

    K_MUTEX_DEFINE(filesystem_mutex);
    FileSlot file_slots[maximum_open_files]{};
    bool filesystem_mounted = false;
    atomic_t last_error_value = ATOMIC_INIT(static_cast<atomic_val_t>(FSError::none));
    atomic_t last_driver_error_value = ATOMIC_INIT(0);

    /** @brief 마지막 공개 오류와 원래 driver 오류를 함께 기록합니다. */
    FSError recordError(FSError error, int driver_error = 0) noexcept
    {
        atomic_set(&last_error_value, static_cast<atomic_val_t>(error));
        atomic_set(&last_driver_error_value, static_cast<atomic_val_t>(driver_error));
        return error;
    }

    /** @brief Zephyr filesystem 오류를 공개 분류로 변환합니다. */
    FSError recordDriverError(int result) noexcept
    {
        switch (result)
        {
        case -EINVAL:
            return recordError(FSError::invalid_argument, result);
        case -ENOENT:
            return recordError(FSError::not_found, result);
        case -EEXIST:
            return recordError(FSError::already_exists, result);
        case -EBUSY:
        case -EAGAIN:
        case -EMFILE:
            return recordError(FSError::busy, result);
        case -ENOSPC:
        case -ENOMEM:
            return recordError(FSError::no_space, result);
        case -EILSEQ:
        case -EBADMSG:
            return recordError(FSError::corrupt, result);
        default:
            return recordError(FSError::driver_error, result);
        }
    }

    /** @brief blocking filesystem API를 thread 문맥으로 제한합니다. */
    bool isThreadContext() noexcept
    {
        if (k_is_in_isr())
        {
            recordError(FSError::invalid_context, -EWOULDBLOCK);
            return false;
        }
        return true;
    }

    /** @brief Arduino 경로를 mount 절대 경로로 검증해 변환합니다. */
    bool normalizePath(const char *path, char *destination, std::size_t capacity) noexcept
    {
        if (path == nullptr || destination == nullptr || path[0] == '\0')
        {
            recordError(FSError::invalid_argument, -EINVAL);
            return false;
        }
        const std::size_t input_length = strlen(path);
        const bool leading_slash = path[0] == '/';
        const std::size_t required =
            sizeof(mount_point) - 1U + (leading_slash ? 0U : 1U) + input_length + 1U;
        if (required > capacity || input_length > maximum_path_length)
        {
            recordError(FSError::invalid_argument, -ENAMETOOLONG);
            return false;
        }

        const char *segment = path + (leading_slash ? 1U : 0U);
        for (const char *cursor = segment;; ++cursor)
        {
            const char character = *cursor;
            if (character == '\\' || character == ':' ||
                (static_cast<unsigned char>(character) < 0x20U && character != '\0'))
            {
                recordError(FSError::invalid_argument, -EINVAL);
                return false;
            }
            if (character == '/' || character == '\0')
            {
                const std::size_t segment_length = static_cast<std::size_t>(cursor - segment);
                if ((segment_length == 1U && segment[0] == '.') ||
                    (segment_length == 2U && segment[0] == '.' && segment[1] == '.'))
                {
                    recordError(FSError::invalid_argument, -EINVAL);
                    return false;
                }
                if (character == '\0')
                {
                    break;
                }
                segment = cursor + 1;
            }
        }

        const int written =
            snprintf(destination, capacity, "%s%s%s", mount_point, leading_slash ? "" : "/", path);
        if (written < 0 || static_cast<std::size_t>(written) >= capacity)
        {
            recordError(FSError::invalid_argument, -ENAMETOOLONG);
            return false;
        }
        return true;
    }

    /** @brief 문자열 mode를 Zephyr open flag로 변환합니다. */
    bool parseMode(const char *mode, fs_mode_t &flags) noexcept
    {
        if (mode == nullptr || strcmp(mode, "r") == 0)
        {
            flags = FS_O_READ;
        }
        else if (strcmp(mode, "w") == 0)
        {
            flags = FS_O_WRITE | FS_O_CREATE | FS_O_TRUNC;
        }
        else if (strcmp(mode, "a") == 0)
        {
            flags = FS_O_WRITE | FS_O_CREATE | FS_O_APPEND;
        }
        else if (strcmp(mode, "r+") == 0)
        {
            flags = FS_O_RDWR;
        }
        else if (strcmp(mode, "w+") == 0)
        {
            flags = FS_O_RDWR | FS_O_CREATE | FS_O_TRUNC;
        }
        else if (strcmp(mode, "a+") == 0)
        {
            flags = FS_O_RDWR | FS_O_CREATE | FS_O_APPEND;
        }
        else
        {
            recordError(FSError::invalid_argument, -EINVAL);
            return false;
        }
        return true;
    }

    /** @brief filesystem_mutex를 보유한 호출자가 slot과 generation의 유효성을 검사합니다. */
    FileSlot *validSlot(std::uint8_t slot, std::uint32_t generation) noexcept
    {
        return slot < maximum_open_files && file_slots[slot].active &&
                       file_slots[slot].generation == generation
                   ? &file_slots[slot]
                   : nullptr;
    }

    /** @brief filesystem_mutex 아래에서 유효한 공유 slot의 참조를 하나 추가합니다. */
    bool retainSlotLocked(std::uint8_t index, std::uint32_t generation) noexcept
    {
        FileSlot *slot = validSlot(index, generation);
        if (slot == nullptr)
        {
            return false;
        }
        if (slot->references == UINT16_MAX)
        {
            recordError(FSError::busy, -EMFILE);
            return false;
        }
        ++slot->references;
        return true;
    }

    /** @brief filesystem_mutex 아래에서 참조를 줄이고 마지막 참조만 backend를 닫습니다. */
    void releaseSlotLocked(std::uint8_t index, std::uint32_t generation) noexcept
    {
        FileSlot *slot = validSlot(index, generation);
        if (slot == nullptr)
        {
            return;
        }
        if (slot->references > 1U)
        {
            --slot->references;
            recordError(FSError::none);
            return;
        }
        const int result = fs_close(&slot->file);
        slot->references = 0U;
        slot->active = false;
        slot->path[0] = '\0';
        if (result < 0)
        {
            recordDriverError(result);
        }
        else
        {
            recordError(FSError::none);
        }
    }

    /** @brief 열린 파일이 하나라도 있는지 반환합니다. */
    bool hasOpenFiles() noexcept
    {
        for (const FileSlot &slot : file_slots)
        {
            if (slot.active)
            {
                return true;
            }
        }
        return false;
    }
} // namespace nucode::littlefs::internal

using namespace nucode::littlefs::internal;

File::File() noexcept : slot_(invalid_slot), generation_(0U)
{
}
File::File(std::uint8_t slot, std::uint32_t generation) noexcept
    : slot_(slot), generation_(generation)
{
}

File::File(const File &other) noexcept : File()
{
    if (!isThreadContext())
    {
        return;
    }
    static_cast<void>(k_mutex_lock(&filesystem_mutex, K_FOREVER));
    if (retainSlotLocked(other.slot_, other.generation_))
    {
        slot_ = other.slot_;
        generation_ = other.generation_;
    }
    static_cast<void>(k_mutex_unlock(&filesystem_mutex));
}

File &File::operator=(const File &other) noexcept
{
    if (this != &other && isThreadContext())
    {
        static_cast<void>(k_mutex_lock(&filesystem_mutex, K_FOREVER));
        releaseSlotLocked(slot_, generation_);
        slot_ = invalid_slot;
        generation_ = 0U;
        if (retainSlotLocked(other.slot_, other.generation_))
        {
            slot_ = other.slot_;
            generation_ = other.generation_;
        }
        static_cast<void>(k_mutex_unlock(&filesystem_mutex));
    }
    return *this;
}

File::File(File &&other) noexcept : File()
{
    if (isThreadContext())
    {
        slot_ = other.slot_;
        generation_ = other.generation_;
        other.slot_ = invalid_slot;
        other.generation_ = 0U;
    }
}

File &File::operator=(File &&other) noexcept
{
    if (this != &other && isThreadContext())
    {
        static_cast<void>(k_mutex_lock(&filesystem_mutex, K_FOREVER));
        releaseSlotLocked(slot_, generation_);
        slot_ = other.slot_;
        generation_ = other.generation_;
        other.slot_ = invalid_slot;
        other.generation_ = 0U;
        static_cast<void>(k_mutex_unlock(&filesystem_mutex));
    }
    return *this;
}

File::~File()
{
    close();
}

int File::available()
{
    if (!isThreadContext())
    {
        return 0;
    }
    static_cast<void>(k_mutex_lock(&filesystem_mutex, K_FOREVER));
    FileSlot *slot = validSlot(slot_, generation_);
    if (slot == nullptr)
    {
        recordError(FSError::not_found, -EBADF);
        static_cast<void>(k_mutex_unlock(&filesystem_mutex));
        return 0;
    }
    const off_t current = fs_tell(&slot->file);
    struct fs_dirent information{};
    const int result = current < 0 ? static_cast<int>(current) : fs_stat(slot->path, &information);
    if (result < 0)
    {
        recordDriverError(result);
        static_cast<void>(k_mutex_unlock(&filesystem_mutex));
        return 0;
    }
    const std::size_t remaining = information.size > static_cast<std::size_t>(current)
                                      ? information.size - static_cast<std::size_t>(current)
                                      : 0U;
    recordError(FSError::none);
    static_cast<void>(k_mutex_unlock(&filesystem_mutex));
    return remaining > static_cast<std::size_t>(INT_MAX) ? INT_MAX : static_cast<int>(remaining);
}

int File::read()
{
    std::uint8_t value = 0U;
    return read(&value, sizeof(value)) == 1 ? value : -1;
}

int File::read(std::uint8_t *buffer, std::size_t size)
{
    if (!isThreadContext())
    {
        return -1;
    }
    if (buffer == nullptr || size == 0U)
    {
        recordError(FSError::invalid_argument, -EINVAL);
        return -1;
    }
    static_cast<void>(k_mutex_lock(&filesystem_mutex, K_FOREVER));
    FileSlot *slot = validSlot(slot_, generation_);
    if (slot == nullptr)
    {
        recordError(FSError::not_found, -EBADF);
        static_cast<void>(k_mutex_unlock(&filesystem_mutex));
        return -1;
    }
    const ssize_t result = fs_read(&slot->file, buffer, size);
    if (result < 0)
    {
        recordDriverError(static_cast<int>(result));
    }
    else
    {
        recordError(FSError::none);
    }
    static_cast<void>(k_mutex_unlock(&filesystem_mutex));
    return result < 0 ? -1 : (result > INT_MAX ? INT_MAX : static_cast<int>(result));
}

int File::peek()
{
    if (!isThreadContext())
    {
        return -1;
    }
    static_cast<void>(k_mutex_lock(&filesystem_mutex, K_FOREVER));
    FileSlot *slot = validSlot(slot_, generation_);
    if (slot == nullptr)
    {
        recordError(FSError::not_found, -EBADF);
        static_cast<void>(k_mutex_unlock(&filesystem_mutex));
        return -1;
    }
    const off_t position = fs_tell(&slot->file);
    std::uint8_t value = 0U;
    const ssize_t read_result =
        position < 0 ? position : fs_read(&slot->file, &value, sizeof(value));
    const int seek_result = read_result == 1 ? fs_seek(&slot->file, position, FS_SEEK_SET) : 0;
    if (read_result < 0 || seek_result < 0)
    {
        recordDriverError(read_result < 0 ? static_cast<int>(read_result) : seek_result);
    }
    else
    {
        recordError(FSError::none);
    }
    static_cast<void>(k_mutex_unlock(&filesystem_mutex));
    return read_result == 1 && seek_result == 0 ? value : -1;
}

std::size_t File::write(std::uint8_t value)
{
    return write(&value, sizeof(value));
}

std::size_t File::write(const std::uint8_t *buffer, std::size_t size)
{
    if (!isThreadContext() || buffer == nullptr || size == 0U)
    {
        if (buffer == nullptr || size == 0U)
        {
            recordError(FSError::invalid_argument, -EINVAL);
        }
        return 0U;
    }
    static_cast<void>(k_mutex_lock(&filesystem_mutex, K_FOREVER));
    FileSlot *slot = validSlot(slot_, generation_);
    if (slot == nullptr)
    {
        recordError(FSError::not_found, -EBADF);
        static_cast<void>(k_mutex_unlock(&filesystem_mutex));
        return 0U;
    }
    const ssize_t result = fs_write(&slot->file, buffer, size);
    if (result < 0)
    {
        recordDriverError(static_cast<int>(result));
    }
    else
    {
        recordError(FSError::none);
    }
    static_cast<void>(k_mutex_unlock(&filesystem_mutex));
    return result > 0 ? static_cast<std::size_t>(result) : 0U;
}

bool File::seek(std::uint32_t position)
{
    if (!isThreadContext())
    {
        return false;
    }
    static_cast<void>(k_mutex_lock(&filesystem_mutex, K_FOREVER));
    FileSlot *slot = validSlot(slot_, generation_);
    const int result = slot == nullptr ? -EBADF : fs_seek(&slot->file, position, FS_SEEK_SET);
    if (result < 0)
    {
        recordDriverError(result);
    }
    else
    {
        recordError(FSError::none);
    }
    static_cast<void>(k_mutex_unlock(&filesystem_mutex));
    return result == 0;
}

std::size_t File::position() const
{
    if (!isThreadContext())
    {
        return 0U;
    }
    static_cast<void>(k_mutex_lock(&filesystem_mutex, K_FOREVER));
    FileSlot *slot = validSlot(slot_, generation_);
    const off_t result = slot == nullptr ? static_cast<off_t>(-EBADF) : fs_tell(&slot->file);
    if (result < 0)
    {
        recordDriverError(static_cast<int>(result));
    }
    else
    {
        recordError(FSError::none);
    }
    static_cast<void>(k_mutex_unlock(&filesystem_mutex));
    return result < 0 ? 0U : static_cast<std::size_t>(result);
}

std::size_t File::size() const
{
    if (!isThreadContext())
    {
        return 0U;
    }
    static_cast<void>(k_mutex_lock(&filesystem_mutex, K_FOREVER));
    FileSlot *slot = validSlot(slot_, generation_);
    struct fs_dirent information{};
    const int result = slot == nullptr ? -EBADF : fs_stat(slot->path, &information);
    if (result < 0)
    {
        recordDriverError(result);
    }
    else
    {
        recordError(FSError::none);
    }
    static_cast<void>(k_mutex_unlock(&filesystem_mutex));
    return result < 0 ? 0U : information.size;
}

void File::flush()
{
    if (!isThreadContext())
    {
        return;
    }
    static_cast<void>(k_mutex_lock(&filesystem_mutex, K_FOREVER));
    FileSlot *slot = validSlot(slot_, generation_);
    const int result = slot == nullptr ? -EBADF : fs_sync(&slot->file);
    if (result < 0)
    {
        recordDriverError(result);
    }
    else
    {
        recordError(FSError::none);
    }
    static_cast<void>(k_mutex_unlock(&filesystem_mutex));
}

void File::close()
{
    if (slot_ == invalid_slot || !isThreadContext())
    {
        return;
    }
    static_cast<void>(k_mutex_lock(&filesystem_mutex, K_FOREVER));
    releaseSlotLocked(slot_, generation_);
    slot_ = invalid_slot;
    generation_ = 0U;
    static_cast<void>(k_mutex_unlock(&filesystem_mutex));
}

const char *File::name() const noexcept
{
    if (!isThreadContext())
    {
        return "";
    }
    static_cast<void>(k_mutex_lock(&filesystem_mutex, K_FOREVER));
    const FileSlot *slot = validSlot(slot_, generation_);
    const char *path = slot == nullptr ? "" : slot->path + (sizeof(mount_point) - 1U);
    static_cast<void>(k_mutex_unlock(&filesystem_mutex));
    return path;
}

File::operator bool() const noexcept
{
    if (!isThreadContext())
    {
        return false;
    }
    static_cast<void>(k_mutex_lock(&filesystem_mutex, K_FOREVER));
    const bool valid = validSlot(slot_, generation_) != nullptr;
    static_cast<void>(k_mutex_unlock(&filesystem_mutex));
    return valid;
}

File FS::open(const char *path, const char *mode)
{
    if (!isThreadContext())
    {
        return {};
    }
    char normalized[maximum_path_length + 1U]{};
    fs_mode_t flags{};
    if (!normalizePath(path, normalized, sizeof(normalized)) || !parseMode(mode, flags))
    {
        return {};
    }
    static_cast<void>(k_mutex_lock(&filesystem_mutex, K_FOREVER));
    if (!filesystem_mounted)
    {
        recordError(FSError::not_mounted, -ENODEV);
        static_cast<void>(k_mutex_unlock(&filesystem_mutex));
        return {};
    }
    std::uint8_t selected = invalid_slot;
    for (std::uint8_t index = 0U; index < maximum_open_files; ++index)
    {
        if (!file_slots[index].active)
        {
            selected = index;
            break;
        }
    }
    if (selected == invalid_slot)
    {
        recordError(FSError::busy, -EMFILE);
        static_cast<void>(k_mutex_unlock(&filesystem_mutex));
        return {};
    }
    FileSlot &slot = file_slots[selected];
    fs_file_t_init(&slot.file);
    const int result = fs_open(&slot.file, normalized, flags);
    if (result < 0)
    {
        recordDriverError(result);
        static_cast<void>(k_mutex_unlock(&filesystem_mutex));
        return {};
    }
    ++slot.generation;
    if (slot.generation == 0U)
    {
        ++slot.generation;
    }
    slot.active = true;
    slot.references = 1U;
    static_cast<void>(snprintf(slot.path, sizeof(slot.path), "%s", normalized));
    recordError(FSError::none);
    const std::uint32_t generation = slot.generation;
    static_cast<void>(k_mutex_unlock(&filesystem_mutex));
    return File(selected, generation);
}

bool FS::exists(const char *path)
{
    if (!isThreadContext())
    {
        return false;
    }
    char normalized[maximum_path_length + 1U]{};
    if (!normalizePath(path, normalized, sizeof(normalized)))
    {
        return false;
    }
    static_cast<void>(k_mutex_lock(&filesystem_mutex, K_FOREVER));
    struct fs_dirent information{};
    const int result = filesystem_mounted ? fs_stat(normalized, &information) : -ENODEV;
    if (result < 0)
    {
        result == -ENODEV ? recordError(FSError::not_mounted, result) : recordDriverError(result);
    }
    else
    {
        recordError(FSError::none);
    }
    static_cast<void>(k_mutex_unlock(&filesystem_mutex));
    return result == 0;
}

bool FS::remove(const char *path)
{
    if (!isThreadContext())
    {
        return false;
    }
    char normalized[maximum_path_length + 1U]{};
    if (!normalizePath(path, normalized, sizeof(normalized)))
    {
        return false;
    }
    static_cast<void>(k_mutex_lock(&filesystem_mutex, K_FOREVER));
    struct fs_dirent information{};
    int result = filesystem_mounted ? fs_stat(normalized, &information) : -ENODEV;
    if (result == 0 && information.type != FS_DIR_ENTRY_FILE)
    {
        result = -EISDIR;
    }
    if (result == 0)
    {
        result = fs_unlink(normalized);
    }
    if (result < 0)
    {
        result == -ENODEV ? recordError(FSError::not_mounted, result) : recordDriverError(result);
    }
    else
    {
        recordError(FSError::none);
    }
    static_cast<void>(k_mutex_unlock(&filesystem_mutex));
    return result == 0;
}

bool FS::rename(const char *from, const char *to)
{
    if (!isThreadContext())
    {
        return false;
    }
    char source[maximum_path_length + 1U]{};
    char destination[maximum_path_length + 1U]{};
    if (!normalizePath(from, source, sizeof(source)) ||
        !normalizePath(to, destination, sizeof(destination)))
    {
        return false;
    }
    static_cast<void>(k_mutex_lock(&filesystem_mutex, K_FOREVER));
    const int result = filesystem_mounted ? fs_rename(source, destination) : -ENODEV;
    if (result < 0)
    {
        result == -ENODEV ? recordError(FSError::not_mounted, result) : recordDriverError(result);
    }
    else
    {
        recordError(FSError::none);
    }
    static_cast<void>(k_mutex_unlock(&filesystem_mutex));
    return result == 0;
}

bool FS::mkdir(const char *path)
{
    if (!isThreadContext())
    {
        return false;
    }
    char normalized[maximum_path_length + 1U]{};
    if (!normalizePath(path, normalized, sizeof(normalized)))
    {
        return false;
    }
    static_cast<void>(k_mutex_lock(&filesystem_mutex, K_FOREVER));
    const int result = filesystem_mounted ? fs_mkdir(normalized) : -ENODEV;
    if (result < 0)
    {
        result == -ENODEV ? recordError(FSError::not_mounted, result) : recordDriverError(result);
    }
    else
    {
        recordError(FSError::none);
    }
    static_cast<void>(k_mutex_unlock(&filesystem_mutex));
    return result == 0;
}

bool FS::rmdir(const char *path)
{
    if (!isThreadContext())
    {
        return false;
    }
    char normalized[maximum_path_length + 1U]{};
    if (!normalizePath(path, normalized, sizeof(normalized)))
    {
        return false;
    }
    static_cast<void>(k_mutex_lock(&filesystem_mutex, K_FOREVER));
    struct fs_dirent information{};
    int result = filesystem_mounted ? fs_stat(normalized, &information) : -ENODEV;
    if (result == 0 && information.type != FS_DIR_ENTRY_DIR)
    {
        result = -ENOTDIR;
    }
    if (result == 0)
    {
        result = fs_unlink(normalized);
    }
    if (result < 0)
    {
        result == -ENODEV ? recordError(FSError::not_mounted, result) : recordDriverError(result);
    }
    else
    {
        recordError(FSError::none);
    }
    static_cast<void>(k_mutex_unlock(&filesystem_mutex));
    return result == 0;
}

#endif
