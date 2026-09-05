/** @file @brief 실제 FS/File/mount의 실패·명시적 format·process 복원을 검사합니다. */
#include <LittleFS.h>
#include <zephyr/fs/fs.h>
#include <zephyr/kernel.h>
#include <cassert>
#include <cstring>
#include <iostream>
int main(int argc, char **argv)
{
    assert(argc == 3);
    const char *scenario = argv[1];
    mock_fs_image = argv[2];
    if (std::strcmp(scenario, "mount_failure") == 0)
    {
        mock_mount_error = -EILSEQ;
        assert(!LittleFS.begin() && !LittleFS.mounted() && mock_formats == 0);
        assert(LittleFS.lastError() == FSError::corrupt);
        mock_mount_error = 0;
    }
    if (std::strcmp(scenario, "format_retry") == 0)
    {
        mock_mount_error = -EILSEQ;
        mock_format_error = -EIO;
        assert(!LittleFS.begin(true) && mock_formats == 1);
        assert(LittleFS.lastDriverError() == -EIO && !LittleFS.mounted());
        mock_format_error = 0;
        assert(LittleFS.begin(true) && mock_formats == 2);
        assert(!LittleFS.exists("/persist"));
        assert(LittleFS.end());
        return 0;
    }
    assert(LittleFS.begin() && LittleFS.mounted());
    assert(LittleFS.totalBytes() == 32768 && LittleFS.usedBytes() == 16384);
    if (std::strcmp(scenario, "write") == 0)
    {
        File file = LittleFS.open("/persist", "w+");
        assert(file);
        const std::uint8_t payload[]{1, 3, 5, 7};
        assert(file.write(payload, sizeof(payload)) == sizeof(payload));
        file.flush();
        assert(LittleFS.lastError() == FSError::none);
        file.close();
    }
    else if (std::strcmp(scenario, "read") == 0 || std::strcmp(scenario, "mount_failure") == 0)
    {
        File file = LittleFS.open("/persist", "r");
        assert(file && file.size() == 4);
        std::uint8_t data[4]{};
        assert(file.read(data, 4) == 4 && data[0] == 1 && data[3] == 7);
        file.close();
    }
    else if (std::strcmp(scenario, "open_failure") == 0)
    {
        mock_open_error = -ENOSPC;
        File file = LittleFS.open("/persist", "r");
        assert(!file && LittleFS.lastError() == FSError::no_space);
        mock_open_error = 0;
        File retry = LittleFS.open("/persist", "r");
        assert(retry);
        retry.close();
    }
    else if (std::strcmp(scenario, "io_failure") == 0)
    {
        File file = LittleFS.open("/persist", "r+");
        assert(file);
        mock_read_error = -EIO;
        assert(file.read() == -1 && LittleFS.lastDriverError() == -EIO);
        mock_read_error = 0;
        assert(file.read() == 1);
        mock_write_error = -ENOSPC;
        assert(file.write(9) == 0 && LittleFS.lastError() == FSError::no_space);
        mock_write_error = 0;
        mock_sync_error = -EIO;
        file.flush();
        assert(LittleFS.lastDriverError() == -EIO);
        mock_sync_error = 0;
        file.flush();
        assert(LittleFS.lastError() == FSError::none);
        file.close();
    }
    else if (std::strcmp(scenario, "busy_mount") == 0)
    {
        File file = LittleFS.open("/persist", "r");
        File copy(file);
        assert(!LittleFS.end() && LittleFS.mounted());
        assert(!LittleFS.format() && mock_formats == 0);
        file.close();
        assert(!LittleFS.end());
        copy.close();
        mock_unmount_error = -EIO;
        assert(!LittleFS.end() && LittleFS.mounted());
        mock_unmount_error = 0;
    }
    else if (std::strcmp(scenario, "path_mode") == 0)
    {
        for (const char *path : {"../escape", "a/../b", "C:/drive", "a\\b", "a/./b", ""})
        {
            const auto opens = mock_opens.load();
            assert(!LittleFS.open(path, "w") && mock_opens == opens);
        }
        assert(!LittleFS.open("/persist", "invalid"));
        assert(!LittleFS.open("/missing", "r"));
        mock_in_isr = true;
        assert(!LittleFS.begin() && !LittleFS.format());
        mock_in_isr = false;
    }
    else
    {
        assert(false);
    }
    assert(LittleFS.end() && !LittleFS.mounted());
    assert(mock_opens == mock_closes);
    std::cout << "R12_LITTLEFS_PASS=" << scenario << '\n';
}
