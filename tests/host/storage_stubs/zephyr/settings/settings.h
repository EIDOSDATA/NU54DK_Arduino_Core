/** @file @brief EEPROM record byte와 Settings 실패를 process 사이에서 재현합니다. */
#pragma once
#include <cstdint>
#include <cstring>
#include <cerrno>
#include <fstream>
#include <iterator>
#include <string>
#include <vector>
#include <sys/types.h>
inline std::string mock_settings_file;
inline int mock_settings_init_error = 0, mock_settings_load_error = 0, mock_settings_save_error = 0;
inline bool mock_short_load = false;
inline unsigned mock_settings_saves = 0;
inline std::vector<std::uint8_t> mock_read_record()
{
    std::ifstream input(mock_settings_file, std::ios::binary);
    return {std::istreambuf_iterator<char>(input), std::istreambuf_iterator<char>()};
}
inline int settings_subsys_init()
{
    return mock_settings_init_error;
}
inline ssize_t settings_get_val_len(const char *key)
{
    if (std::strcmp(key, "arduino/eeprom") != 0)
    {
        return -EINVAL;
    }
    if (mock_settings_load_error != 0)
    {
        return mock_settings_load_error;
    }
    std::ifstream input(mock_settings_file, std::ios::binary | std::ios::ate);
    return input ? static_cast<ssize_t>(input.tellg()) : -ENOENT;
}
inline ssize_t settings_load_one(const char *, void *output, std::size_t capacity)
{
    const auto record = mock_read_record();
    if (capacity < record.size())
    {
        return -ENOMEM;
    }
    std::memcpy(output, record.data(), record.size());
    return static_cast<ssize_t>(record.size()) - (mock_short_load ? 1 : 0);
}
inline int settings_save_one(const char *key, const void *record, std::size_t length)
{
    if (std::strcmp(key, "arduino/eeprom") != 0)
    {
        return -EINVAL;
    }
    if (mock_settings_save_error != 0)
    {
        return mock_settings_save_error;
    }
    std::ofstream output(mock_settings_file, std::ios::binary | std::ios::trunc);
    output.write(static_cast<const char *>(record), length);
    if (!output)
    {
        return -EIO;
    }
    ++mock_settings_saves;
    return 0;
}
