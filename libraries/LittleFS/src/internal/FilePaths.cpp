/** @file @brief Arduino 경로와 open mode를 bounded backend 입력으로 검증합니다.
 * SPDX-License-Identifier: MIT
 */
#if !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE)
#include "StorageInternal.h"
namespace nucode::littlefs::internal
{
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

} // namespace nucode::littlefs::internal
#endif
