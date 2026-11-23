/** @file @brief BLE Host driver 경계를 공유합니다. */
#pragma once
#include <ble_mock.h>
#include <algorithm>
#include <sys/types.h>

inline int mock_settings_save_error = 0;
inline char mock_settings_saved_key[64]{};
inline std::uint8_t mock_settings_saved_value[128]{};
inline std::size_t mock_settings_saved_length = 0U;
inline constexpr std::size_t mock_settings_capacity = 32U;
inline char mock_settings_keys[mock_settings_capacity][64]{};
inline std::uint8_t mock_settings_values[mock_settings_capacity][128]{};
inline std::size_t mock_settings_lengths[mock_settings_capacity]{};
inline int mock_settings_load_error = 0;
inline bool mock_settings_enumerating = false;
using settings_read_cb = ssize_t (*)(void *, void *, std::size_t);
using settings_load_direct_cb = int (*)(const char *, std::size_t, settings_read_cb,
                                        void *, void *);

/** @brief subtree의 실제 저장 이름을 열거하며 callback 중 삭제는 금지합니다. */
inline int settings_load_subtree_direct(const char *subtree, settings_load_direct_cb callback,
                                        void *context)
{
    if (mock_settings_load_error != 0)
    {
        return mock_settings_load_error;
    }
    const std::size_t prefix = std::strlen(subtree);
    mock_settings_enumerating = true;
    for (std::size_t index = 0U; index < mock_settings_capacity; ++index)
    {
        if (std::strncmp(mock_settings_keys[index], subtree, prefix) == 0 &&
            mock_settings_keys[index][prefix] == '/')
        {
            const int result = callback(mock_settings_keys[index] + prefix + 1U,
                                        mock_settings_lengths[index], nullptr, nullptr, context);
            if (result != 0)
            {
                mock_settings_enumerating = false;
                return result;
            }
        }
    }
    mock_settings_enumerating = false;
    return 0;
}

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
    std::size_t slot = mock_settings_capacity;
    for (std::size_t index = 0U; index < mock_settings_capacity; ++index)
    {
        if (mock_settings_keys[index][0] == '\0' ||
            std::strcmp(mock_settings_keys[index], name) == 0)
        {
            slot = index;
            break;
        }
    }
    assert(slot < mock_settings_capacity);
    std::strcpy(mock_settings_keys[slot], name);
    std::memcpy(mock_settings_values[slot], value, length);
    mock_settings_lengths[slot] = length;
    return 0;
}

/** @brief exact key의 저장 value를 caller buffer로 복사합니다. */
inline ssize_t settings_load_one(const char *name, void *output, std::size_t capacity)
{
    for (std::size_t index = 0U; index < mock_settings_capacity; ++index)
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
    assert(!mock_settings_enumerating);
    for (std::size_t index = 0U; index < mock_settings_capacity; ++index)
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
