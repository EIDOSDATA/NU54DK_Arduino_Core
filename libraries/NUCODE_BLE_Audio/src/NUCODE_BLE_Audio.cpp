/**
 * @file NUCODE_BLE_Audio.cpp
 * @brief NU54DK Bluetooth LE Audio codec 공개 API를 구현합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include "NUCODE_BLE_Audio.h"

#if !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE)

#include <lc3.h>

#include <string.h>

namespace nucode::ble::audio
{
    namespace
    {
        /** @brief 동적 할당 없이 한 LC3 encoder/decoder의 상태를 보관합니다. */
        struct CodecState
        {
            Lc3Codec *owner = nullptr;
            lc3_encoder_mem_16k_t encoder_memory = {};
            lc3_decoder_mem_16k_t decoder_memory = {};
            lc3_encoder_t encoder = nullptr;
            lc3_decoder_t decoder = nullptr;
            Lc3Config config = {};
            std::size_t frame_samples = 0U;
        };

        CodecState codec_state;

        /** @brief 고정 backend가 표현할 수 있는 LC3 구성을 검사합니다. */
        bool validConfig(const Lc3Config &config) noexcept
        {
            if ((config.sample_rate_hz == 0U) || (config.sample_rate_hz > 16000U) ||
                ((config.frame_duration_us != 7500U) &&
                 (config.frame_duration_us != 10000U)) ||
                (config.frame_octets == 0U) || (config.frame_octets > 400U))
            {
                return false;
            }
            return lc3_frame_samples(static_cast<int>(config.frame_duration_us),
                                     static_cast<int>(config.sample_rate_hz)) > 0;
        }
    }

    /** @brief 마지막 오류를 객체에 기록합니다. */
    Error Lc3Codec::record(Error error) noexcept
    {
        last_error_ = error;
        return error;
    }

    /** @brief 실제 liblc3 encoder와 decoder를 고정 메모리에 만듭니다. */
    Error Lc3Codec::begin(const Lc3Config &config) noexcept
    {
        if (!validConfig(config))
        {
            return record(Error::invalid_argument);
        }
        if (state_ != nullptr)
        {
            return record(Error::already_started);
        }
        if ((codec_state.owner != nullptr) && (codec_state.owner != this))
        {
            return record(Error::busy);
        }

        memset(&codec_state.encoder_memory, 0, sizeof(codec_state.encoder_memory));
        memset(&codec_state.decoder_memory, 0, sizeof(codec_state.decoder_memory));
        codec_state.encoder = lc3_setup_encoder(
            static_cast<int>(config.frame_duration_us),
            static_cast<int>(config.sample_rate_hz), 0, &codec_state.encoder_memory);
        codec_state.decoder = lc3_setup_decoder(
            static_cast<int>(config.frame_duration_us),
            static_cast<int>(config.sample_rate_hz), 0, &codec_state.decoder_memory);
        if ((codec_state.encoder == nullptr) || (codec_state.decoder == nullptr))
        {
            codec_state = {};
            return record(Error::codec_error);
        }

        codec_state.owner = this;
        codec_state.config = config;
        codec_state.frame_samples = static_cast<std::size_t>(lc3_frame_samples(
            static_cast<int>(config.frame_duration_us),
            static_cast<int>(config.sample_rate_hz)));
        state_ = &codec_state;
        return record(Error::none);
    }

    /** @brief 이 객체가 소유한 codec 상태만 초기화합니다. */
    void Lc3Codec::end() noexcept
    {
        if ((state_ == &codec_state) && (codec_state.owner == this))
        {
            codec_state = {};
            state_ = nullptr;
        }
        last_error_ = Error::not_started;
    }

    /** @brief PCM sample 수와 출력 buffer를 검증하고 liblc3 encode를 호출합니다. */
    Error Lc3Codec::encode(const std::int16_t *pcm, std::size_t sample_count,
                           std::uint8_t *frame, std::size_t frame_capacity) noexcept
    {
        if ((state_ != &codec_state) || (codec_state.owner != this))
        {
            return record(Error::not_started);
        }
        if ((pcm == nullptr) || (frame == nullptr) ||
            (sample_count != codec_state.frame_samples))
        {
            return record(Error::invalid_argument);
        }
        if (frame_capacity < codec_state.config.frame_octets)
        {
            return record(Error::buffer_too_small);
        }
        const int result = lc3_encode(
            codec_state.encoder, LC3_PCM_FORMAT_S16, pcm, 1,
            static_cast<int>(codec_state.config.frame_octets), frame);
        return record(result == 0 ? Error::none : Error::codec_error);
    }

    /** @brief LC3 frame 크기와 PCM buffer를 검증하고 liblc3 decode를 호출합니다. */
    Error Lc3Codec::decode(const std::uint8_t *frame, std::size_t frame_size,
                           std::int16_t *pcm, std::size_t sample_capacity) noexcept
    {
        if ((state_ != &codec_state) || (codec_state.owner != this))
        {
            return record(Error::not_started);
        }
        if ((frame == nullptr) || (pcm == nullptr) ||
            (frame_size != codec_state.config.frame_octets))
        {
            return record(Error::invalid_argument);
        }
        if (sample_capacity < codec_state.frame_samples)
        {
            return record(Error::buffer_too_small);
        }
        const int result = lc3_decode(
            codec_state.decoder, frame, static_cast<int>(frame_size),
            LC3_PCM_FORMAT_S16, pcm, 1);
        return record(result == 0 ? Error::none : Error::codec_error);
    }

    /** @brief 시작된 codec의 PCM sample/frame 수를 반환합니다. */
    std::size_t Lc3Codec::frameSamples() const noexcept
    {
        return (state_ == &codec_state) && (codec_state.owner == this)
                   ? codec_state.frame_samples
                   : 0U;
    }

    /** @brief 시작된 codec의 LC3 byte/frame 수를 반환합니다. */
    std::size_t Lc3Codec::frameOctets() const noexcept
    {
        return (state_ == &codec_state) && (codec_state.owner == this)
                   ? codec_state.config.frame_octets
                   : 0U;
    }

    /** @brief 마지막 공개 오류를 반환합니다. */
    Error Lc3Codec::lastError() const noexcept
    {
        return last_error_;
    }
}

#endif
