/** @file @brief 공유 고정 slot을 참조하는 Arduino File 값 API입니다.
 * SPDX-License-Identifier: MIT
 */
#if !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE)
#include "StorageInternal.h"
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
    static_cast<void>(k_mutex_lock(&filesystemMutex(), K_FOREVER));
    if (retainSlotLocked(other.slot_, other.generation_))
    {
        slot_ = other.slot_;
        generation_ = other.generation_;
    }
    static_cast<void>(k_mutex_unlock(&filesystemMutex()));
}

File &File::operator=(const File &other) noexcept
{
    if (this != &other && isThreadContext())
    {
        static_cast<void>(k_mutex_lock(&filesystemMutex(), K_FOREVER));
        releaseSlotLocked(slot_, generation_);
        slot_ = invalid_slot;
        generation_ = 0U;
        if (retainSlotLocked(other.slot_, other.generation_))
        {
            slot_ = other.slot_;
            generation_ = other.generation_;
        }
        static_cast<void>(k_mutex_unlock(&filesystemMutex()));
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
        static_cast<void>(k_mutex_lock(&filesystemMutex(), K_FOREVER));
        releaseSlotLocked(slot_, generation_);
        slot_ = other.slot_;
        generation_ = other.generation_;
        other.slot_ = invalid_slot;
        other.generation_ = 0U;
        static_cast<void>(k_mutex_unlock(&filesystemMutex()));
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
    static_cast<void>(k_mutex_lock(&filesystemMutex(), K_FOREVER));
    FileSlot *slot = validSlot(slot_, generation_);
    if (slot == nullptr)
    {
        recordError(FSError::not_found, -EBADF);
        static_cast<void>(k_mutex_unlock(&filesystemMutex()));
        return 0;
    }
    const off_t current = fs_tell(&slot->file);
    struct fs_dirent information{};
    const int result = current < 0 ? static_cast<int>(current) : fs_stat(slot->path, &information);
    if (result < 0)
    {
        recordDriverError(result);
        static_cast<void>(k_mutex_unlock(&filesystemMutex()));
        return 0;
    }
    const std::size_t remaining = information.size > static_cast<std::size_t>(current)
                                      ? information.size - static_cast<std::size_t>(current)
                                      : 0U;
    recordError(FSError::none);
    static_cast<void>(k_mutex_unlock(&filesystemMutex()));
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
    static_cast<void>(k_mutex_lock(&filesystemMutex(), K_FOREVER));
    FileSlot *slot = validSlot(slot_, generation_);
    if (slot == nullptr)
    {
        recordError(FSError::not_found, -EBADF);
        static_cast<void>(k_mutex_unlock(&filesystemMutex()));
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
    static_cast<void>(k_mutex_unlock(&filesystemMutex()));
    return result < 0 ? -1 : (result > INT_MAX ? INT_MAX : static_cast<int>(result));
}

int File::peek()
{
    if (!isThreadContext())
    {
        return -1;
    }
    static_cast<void>(k_mutex_lock(&filesystemMutex(), K_FOREVER));
    FileSlot *slot = validSlot(slot_, generation_);
    if (slot == nullptr)
    {
        recordError(FSError::not_found, -EBADF);
        static_cast<void>(k_mutex_unlock(&filesystemMutex()));
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
    static_cast<void>(k_mutex_unlock(&filesystemMutex()));
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
    static_cast<void>(k_mutex_lock(&filesystemMutex(), K_FOREVER));
    FileSlot *slot = validSlot(slot_, generation_);
    if (slot == nullptr)
    {
        recordError(FSError::not_found, -EBADF);
        static_cast<void>(k_mutex_unlock(&filesystemMutex()));
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
    static_cast<void>(k_mutex_unlock(&filesystemMutex()));
    return result > 0 ? static_cast<std::size_t>(result) : 0U;
}

bool File::seek(std::uint32_t position)
{
    if (!isThreadContext())
    {
        return false;
    }
    static_cast<void>(k_mutex_lock(&filesystemMutex(), K_FOREVER));
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
    static_cast<void>(k_mutex_unlock(&filesystemMutex()));
    return result == 0;
}

std::size_t File::position() const
{
    if (!isThreadContext())
    {
        return 0U;
    }
    static_cast<void>(k_mutex_lock(&filesystemMutex(), K_FOREVER));
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
    static_cast<void>(k_mutex_unlock(&filesystemMutex()));
    return result < 0 ? 0U : static_cast<std::size_t>(result);
}

std::size_t File::size() const
{
    if (!isThreadContext())
    {
        return 0U;
    }
    static_cast<void>(k_mutex_lock(&filesystemMutex(), K_FOREVER));
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
    static_cast<void>(k_mutex_unlock(&filesystemMutex()));
    return result < 0 ? 0U : information.size;
}

void File::flush()
{
    if (!isThreadContext())
    {
        return;
    }
    static_cast<void>(k_mutex_lock(&filesystemMutex(), K_FOREVER));
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
    static_cast<void>(k_mutex_unlock(&filesystemMutex()));
}

void File::close()
{
    if (slot_ == invalid_slot || !isThreadContext())
    {
        return;
    }
    static_cast<void>(k_mutex_lock(&filesystemMutex(), K_FOREVER));
    releaseSlotLocked(slot_, generation_);
    slot_ = invalid_slot;
    generation_ = 0U;
    static_cast<void>(k_mutex_unlock(&filesystemMutex()));
}

const char *File::name() const noexcept
{
    if (!isThreadContext())
    {
        return "";
    }
    static_cast<void>(k_mutex_lock(&filesystemMutex(), K_FOREVER));
    const FileSlot *slot = validSlot(slot_, generation_);
    const char *path = slot == nullptr ? "" : slot->path + (sizeof(mount_point) - 1U);
    static_cast<void>(k_mutex_unlock(&filesystemMutex()));
    return path;
}

File::operator bool() const noexcept
{
    if (!isThreadContext())
    {
        return false;
    }
    static_cast<void>(k_mutex_lock(&filesystemMutex(), K_FOREVER));
    const bool valid = validSlot(slot_, generation_) != nullptr;
    static_cast<void>(k_mutex_unlock(&filesystemMutex()));
    return valid;
}

#endif
