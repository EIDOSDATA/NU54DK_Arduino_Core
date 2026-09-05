/** @file @brief open/close와 내용을 관측하는 메모리 filesystem fake입니다. */
#pragma once
#include <algorithm>
#include <atomic>
#include <cassert>
#include <cstring>
#include <cerrno>
#include <fstream>
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
inline int mock_open_error = 0, mock_read_error = 0, mock_write_error = 0, mock_sync_error = 0;
inline std::string mock_fs_image;
/** @brief fake filesystem의 내용만 시험용 image에 저장하며 LittleFS on-disk 형식이 아닙니다. */
inline void mockSaveFilesystem()
{
    if (mock_fs_image.empty())
    {
        return;
    }
    std::ofstream output(mock_fs_image, std::ios::binary | std::ios::trunc);
    const auto count = static_cast<std::uint32_t>(mock_files.size());
    output.write(reinterpret_cast<const char *>(&count), sizeof(count));
    for (const auto &entry : mock_files)
    {
        const auto path_size = static_cast<std::uint32_t>(entry.first.size());
        const auto data_size = static_cast<std::uint32_t>(entry.second.size());
        output.write(reinterpret_cast<const char *>(&path_size), sizeof(path_size));
        output.write(reinterpret_cast<const char *>(&data_size), sizeof(data_size));
        output.write(entry.first.data(), path_size);
        output.write(reinterpret_cast<const char *>(entry.second.data()), data_size);
    }
    assert(output.good());
}
/** @brief 새 process의 mount가 이전 fake filesystem 내용을 복원합니다. */
inline void mockLoadFilesystem()
{
    if (mock_fs_image.empty())
    {
        return;
    }
    std::ifstream input(mock_fs_image, std::ios::binary);
    if (!input)
    {
        return;
    }
    std::uint32_t count = 0;
    input.read(reinterpret_cast<char *>(&count), sizeof(count));
    assert(input.good() && count <= 8);
    mock_files.clear();
    for (std::uint32_t i = 0; i < count; ++i)
    {
        std::uint32_t path_size = 0, data_size = 0;
        input.read(reinterpret_cast<char *>(&path_size), sizeof(path_size));
        input.read(reinterpret_cast<char *>(&data_size), sizeof(data_size));
        assert(input.good() && path_size <= 265 && data_size <= 4096);
        std::string path(path_size, '\0');
        std::vector<std::uint8_t> data(data_size);
        input.read(path.data(), path_size);
        input.read(reinterpret_cast<char *>(data.data()), data_size);
        assert(input.good());
        mock_files[path] = std::move(data);
    }
}
inline void fs_file_t_init(fs_file_t *file)
{
    *file = {};
}
inline int fs_open(fs_file_t *file, const char *path, fs_mode_t mode)
{
    if (mock_open_error != 0)
    {
        return mock_open_error;
    }
    if (mock_files.find(path) == mock_files.end() && (mode & FS_O_CREATE) == 0)
    {
        return -ENOENT;
    }
    mock_files.try_emplace(path);
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
    if (mock_close_error == 0)
    {
        mockSaveFilesystem();
    }
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
    if (mock_read_error != 0)
    {
        return mock_read_error;
    }
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
    if (mock_write_error != 0)
    {
        return mock_write_error;
    }
    auto &data = mock_files[file->path];
    data.resize(std::max(data.size(), file->position + size));
    std::memcpy(data.data() + file->position, buffer, size);
    file->position += size;
    return size;
}
inline int fs_stat(const char *path, fs_dirent *entry)
{
    if (mock_files.find(path) == mock_files.end())
    {
        return -ENOENT;
    }
    *entry = {FS_DIR_ENTRY_FILE, mock_files[path].size()};
    return 0;
}
inline int fs_sync(fs_file_t *)
{
    if (mock_sync_error == 0)
    {
        mockSaveFilesystem();
    }
    return mock_sync_error;
}
inline int fs_unlink(const char *path)
{
    mock_files.erase(path);
    mockSaveFilesystem();
    return 0;
}
inline int fs_rename(const char *from, const char *to)
{
    mock_files[to] = std::move(mock_files[from]);
    mock_files.erase(from);
    mockSaveFilesystem();
    return 0;
}
inline int fs_mkdir(const char *)
{
    return 0;
}

enum
{
    FS_LITTLEFS = 1,
    FS_MOUNT_FLAG_NO_FORMAT = 1,
};
struct fs_mount_t
{
    int type;
    const char *mnt_point;
    void *fs_data;
    void *storage_dev;
    unsigned flags;
};
struct fs_statvfs
{
    std::size_t f_frsize, f_blocks, f_bfree;
};
inline int mock_mount_error = 0, mock_unmount_error = 0, mock_format_error = 0;
inline unsigned mock_mounts = 0, mock_unmounts = 0, mock_formats = 0;
inline int fs_mount(fs_mount_t *mount)
{
    assert(mount->type == FS_LITTLEFS && mount->flags == FS_MOUNT_FLAG_NO_FORMAT);
    assert(std::strcmp(mount->mnt_point, "/littlefs") == 0);
    ++mock_mounts;
    if (mock_mount_error == 0)
    {
        mockLoadFilesystem();
    }
    return mock_mount_error;
}
inline int fs_unmount(fs_mount_t *)
{
    ++mock_unmounts;
    return mock_unmount_error;
}
inline int fs_mkfs(int type, std::uintptr_t partition, void *, int flags)
{
    assert(type == FS_LITTLEFS && partition == 1 && flags == 0);
    ++mock_formats;
    if (mock_format_error == 0)
    {
        mock_mount_error = 0;
        mock_files.clear();
        mockSaveFilesystem();
    }
    return mock_format_error;
}
inline int fs_statvfs(const char *, struct fs_statvfs *information)
{
    *information = {4096, 8, 4};
    return 0;
}
