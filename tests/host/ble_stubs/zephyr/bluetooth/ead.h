/** @file @brief Host EAD 암호화·인증 동작을 결정적으로 모의합니다. */
#pragma once

#include <ble_mock.h>

/** @brief 시험용 randomizer를 증가시켜 payload와 인증 값을 생성합니다. */
inline int bt_ead_encrypt(const std::uint8_t session_key[16],
                          const std::uint8_t iv[8],
                          const std::uint8_t *payload,
                          std::size_t payload_size,
                          std::uint8_t *encrypted_payload)
{
    static std::uint64_t randomizer = 1U;
    if (session_key == nullptr || iv == nullptr || payload == nullptr ||
        encrypted_payload == nullptr)
    {
        return -EINVAL;
    }
    for (std::size_t index = 0U; index < 5U; ++index)
    {
        encrypted_payload[index] =
            static_cast<std::uint8_t>(randomizer >> (index * 8U));
    }
    std::uint32_t mic = 0x32ead001U;
    for (std::size_t index = 0U; index < 16U; ++index)
    {
        mic = (mic << 5U) ^ (mic >> 2U) ^ session_key[index];
    }
    for (std::size_t index = 0U; index < 8U; ++index)
    {
        mic = (mic << 5U) ^ (mic >> 2U) ^ iv[index];
    }
    for (std::size_t index = 0U; index < payload_size; ++index)
    {
        const std::uint8_t cipher = static_cast<std::uint8_t>(
            payload[index] ^ session_key[index % 16U] ^ iv[index % 8U]);
        encrypted_payload[5U + index] = cipher;
        mic = (mic << 5U) ^ (mic >> 2U) ^ cipher;
    }
    for (std::size_t index = 0U; index < 4U; ++index)
    {
        encrypted_payload[5U + payload_size + index] =
            static_cast<std::uint8_t>(mic >> (index * 8U));
    }
    ++randomizer;
    return 0;
}

/** @brief 시험용 MIC를 검사한 뒤 원문을 복원합니다. */
inline int bt_ead_decrypt(const std::uint8_t session_key[16],
                          const std::uint8_t iv[8],
                          const std::uint8_t *encrypted_payload,
                          std::size_t encrypted_payload_size,
                          std::uint8_t *payload)
{
    if (session_key == nullptr || iv == nullptr || encrypted_payload == nullptr ||
        payload == nullptr || encrypted_payload_size < 9U)
    {
        return -EINVAL;
    }
    const std::size_t payload_size = encrypted_payload_size - 9U;
    std::uint32_t mic = 0x32ead001U;
    for (std::size_t index = 0U; index < 16U; ++index)
    {
        mic = (mic << 5U) ^ (mic >> 2U) ^ session_key[index];
    }
    for (std::size_t index = 0U; index < 8U; ++index)
    {
        mic = (mic << 5U) ^ (mic >> 2U) ^ iv[index];
    }
    for (std::size_t index = 0U; index < payload_size; ++index)
    {
        const std::uint8_t cipher = encrypted_payload[5U + index];
        mic = (mic << 5U) ^ (mic >> 2U) ^ cipher;
        payload[index] = static_cast<std::uint8_t>(
            cipher ^ session_key[index % 16U] ^ iv[index % 8U]);
    }
    for (std::size_t index = 0U; index < 4U; ++index)
    {
        if (encrypted_payload[5U + payload_size + index] !=
            static_cast<std::uint8_t>(mic >> (index * 8U)))
        {
            return -EIO;
        }
    }
    return 0;
}
