/** @file @brief Arduino filesystem 경로 API facade입니다.
 * SPDX-License-Identifier: MIT
 */
#include <FS.h>
#if !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE)
#include "internal/StorageInternal.h"
using namespace nucode::littlefs::internal;
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
    static_cast<void>(k_mutex_lock(&filesystemMutex(), K_FOREVER));
    if (!filesystemState().filesystem_mounted)
    {
        recordError(FSError::not_mounted, -ENODEV);
        static_cast<void>(k_mutex_unlock(&filesystemMutex()));
        return {};
    }
    std::uint8_t selected = invalid_slot;
    for (std::uint8_t index = 0U; index < maximum_open_files; ++index)
    {
        if (!fileSlots()[index].active)
        {
            selected = index;
            break;
        }
    }
    if (selected == invalid_slot)
    {
        recordError(FSError::busy, -EMFILE);
        static_cast<void>(k_mutex_unlock(&filesystemMutex()));
        return {};
    }
    FileSlot &slot = fileSlots()[selected];
    fs_file_t_init(&slot.file);
    const int result = fs_open(&slot.file, normalized, flags);
    if (result < 0)
    {
        recordDriverError(result);
        static_cast<void>(k_mutex_unlock(&filesystemMutex()));
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
    static_cast<void>(k_mutex_unlock(&filesystemMutex()));
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
    static_cast<void>(k_mutex_lock(&filesystemMutex(), K_FOREVER));
    struct fs_dirent information{};
    const int result =
        filesystemState().filesystem_mounted ? fs_stat(normalized, &information) : -ENODEV;
    if (result < 0)
    {
        result == -ENODEV ? recordError(FSError::not_mounted, result) : recordDriverError(result);
    }
    else
    {
        recordError(FSError::none);
    }
    static_cast<void>(k_mutex_unlock(&filesystemMutex()));
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
    static_cast<void>(k_mutex_lock(&filesystemMutex(), K_FOREVER));
    struct fs_dirent information{};
    int result = filesystemState().filesystem_mounted ? fs_stat(normalized, &information) : -ENODEV;
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
    static_cast<void>(k_mutex_unlock(&filesystemMutex()));
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
    static_cast<void>(k_mutex_lock(&filesystemMutex(), K_FOREVER));
    const int result =
        filesystemState().filesystem_mounted ? fs_rename(source, destination) : -ENODEV;
    if (result < 0)
    {
        result == -ENODEV ? recordError(FSError::not_mounted, result) : recordDriverError(result);
    }
    else
    {
        recordError(FSError::none);
    }
    static_cast<void>(k_mutex_unlock(&filesystemMutex()));
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
    static_cast<void>(k_mutex_lock(&filesystemMutex(), K_FOREVER));
    const int result = filesystemState().filesystem_mounted ? fs_mkdir(normalized) : -ENODEV;
    if (result < 0)
    {
        result == -ENODEV ? recordError(FSError::not_mounted, result) : recordDriverError(result);
    }
    else
    {
        recordError(FSError::none);
    }
    static_cast<void>(k_mutex_unlock(&filesystemMutex()));
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
    static_cast<void>(k_mutex_lock(&filesystemMutex(), K_FOREVER));
    struct fs_dirent information{};
    int result = filesystemState().filesystem_mounted ? fs_stat(normalized, &information) : -ENODEV;
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
    static_cast<void>(k_mutex_unlock(&filesystemMutex()));
    return result == 0;
}

#endif
