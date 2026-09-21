/** @file @brief BLE Host driver 경계를 공유합니다. */
#pragma once
#include <ble_mock.h>
#include <algorithm>
#include <sys/types.h>

inline int mock_settings_save_error = 0;
inline char mock_settings_saved_key[64]{};
inline std::uint8_t mock_settings_saved_value[128]{};
inline std::size_t mock_settings_saved_length = 0U;
inline char mock_settings_keys[8][64]{};
inline std::uint8_t mock_settings_values[8][128]{};
inline std::size_t mock_settings_lengths[8]{};

/** @brief 저장 key와 bounded value를 Host test에 복사합니다. */
inline int settings_save_one(const char *name, const void *value, std::size_t length)
{
    if (mock_settings_save_error != 0)
    {
        return mock_settings_save_error;
    }
    assert(name != nullptr && value != nullptr);
    assert(std::strlen(name) < sizeof(mock_settings_saved_key));
    assert(length <= sizeof(mock_settings_saved_value));
    std::strcpy(mock_settings_saved_key, name);
    std::memcpy(mock_settings_saved_value, value, length);
    mock_settings_saved_length = length;
    std::size_t slot = 8U;
    for (std::size_t index = 0U; index < 8U; ++index)
    {
        if (mock_settings_keys[index][0] == '\0' ||
            std::strcmp(mock_settings_keys[index], name) == 0)
        {
            slot = index;
            break;
        }
    }
    assert(slot < 8U);
    std::strcpy(mock_settings_keys[slot], name);
    std::memcpy(mock_settings_values[slot], value, length);
    mock_settings_lengths[slot] = length;
    return 0;
}

/** @brief exact key의 저장 value를 caller buffer로 복사합니다. */
inline ssize_t settings_load_one(const char *name, void *output, std::size_t capacity)
{
    for (std::size_t index = 0U; index < 8U; ++index)
    {
        if (std::strcmp(mock_settings_keys[index], name) != 0)
        {
            continue;
        }
        const std::size_t copied = std::min(capacity, mock_settings_lengths[index]);
        std::memcpy(output, mock_settings_values[index], copied);
        return static_cast<ssize_t>(mock_settings_lengths[index]);
    }
    return -ENOENT;
}

/** @brief exact key의 Host test value를 폐기합니다. */
inline int settings_delete(const char *name)
{
    for (std::size_t index = 0U; index < 8U; ++index)
    {
        if (std::strcmp(mock_settings_keys[index], name) == 0)
        {
            mock_settings_keys[index][0] = '\0';
            mock_settings_lengths[index] = 0U;
            std::memset(mock_settings_values[index], 0, sizeof(mock_settings_values[index]));
            return 0;
        }
    }
    return 0;
}
