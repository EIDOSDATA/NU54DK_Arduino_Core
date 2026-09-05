/** @file @brief open/close와 내용을 관측하는 메모리 filesystem fake입니다. */
#pragma once
#include <algorithm>
#include <atomic>
#include <cassert>
#include <cstring>
#include <map>
#include <string>
#include <sys/types.h>
#include <vector>
using fs_mode_t = unsigned;
enum
{
    FS_O_READ = 1,
    FS_O_WRITE = 2,
    FS_O_RDWR = 3,
    FS_O_CREATE = 4,
    FS_O_TRUNC = 8,
    FS_O_APPEND = 16,
    FS_SEEK_SET = 0,
    FS_DIR_ENTRY_FILE = 1,
    FS_DIR_ENTRY_DIR = 2
};
struct fs_file_t
{
    std::string path;
    std::size_t position{0};
    bool open{false};
};
struct fs_dirent
{
    int type;
    std::size_t size;
};
inline std::map<std::string, std::vector<std::uint8_t>> mock_files;
inline std::atomic<unsigned> mock_opens{0}, mock_closes{0};
inline int mock_close_error = 0;
inline void fs_file_t_init(fs_file_t *file)
{
    *file = {};
}
inline int fs_open(fs_file_t *file, const char *path, fs_mode_t mode)
{
    file->path = path;
    if ((mode & FS_O_TRUNC) != 0)
    {
        mock_files[path].clear();
    }
    file->position = (mode & FS_O_APPEND) != 0 ? mock_files[path].size() : 0;
    file->open = true;
    ++mock_opens;
    return 0;
}
inline int fs_close(fs_file_t *file)
{
    assert(file->open);
    file->open = false;
    ++mock_closes;
    return mock_close_error;
}
inline off_t fs_tell(fs_file_t *file)
{
    assert(file->open);
    return static_cast<off_t>(file->position);
}
inline int fs_seek(fs_file_t *file, off_t position, int)
{
    assert(file->open);
    file->position = position;
    return 0;
}
inline ssize_t fs_read(fs_file_t *file, void *buffer, std::size_t size)
{
    assert(file->open);
    auto &data = mock_files[file->path];
    const auto count = std::min(size, data.size() - std::min(file->position, data.size()));
    if (count != 0)
    {
        std::memcpy(buffer, data.data() + file->position, count);
    }
    file->position += count;
    return count;
}
inline ssize_t fs_write(fs_file_t *file, const void *buffer, std::size_t size)
{
    assert(file->open);
    auto &data = mock_files[file->path];
    data.resize(std::max(data.size(), file->position + size));
    std::memcpy(data.data() + file->position, buffer, size);
    file->position += size;
    return size;
}
inline int fs_stat(const char *path, fs_dirent *entry)
{
    *entry = {FS_DIR_ENTRY_FILE, mock_files[path].size()};
    return 0;
}
inline int fs_sync(fs_file_t *)
{
    return 0;
}
inline int fs_unlink(const char *path)
{
    mock_files.erase(path);
    return 0;
}
inline int fs_rename(const char *from, const char *to)
{
    mock_files[to] = std::move(mock_files[from]);
    mock_files.erase(from);
    return 0;
}
inline int fs_mkdir(const char *)
{
    return 0;
}
