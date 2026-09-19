/**
 * @file NUCODE_BLE_Audio_ControlDevice.cpp
 * @brief VCP Volume Renderer와 MICP Microphone Device 공개 API를 구현합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include "NUCODE_BLE_Audio.h"

#if !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE) &&                                                   \
    (defined(CONFIG_BT_VCP_VOL_REND) || defined(CONFIG_BT_MICP_MIC_DEV))

#include <NUCODE_BLE.h>

#include <zephyr/bluetooth/audio/aics.h>
#include <zephyr/bluetooth/audio/micp.h>
#include <zephyr/bluetooth/audio/vcp.h>
#include <zephyr/bluetooth/audio/vocs.h>

#include <errno.h>
#include <string.h>

namespace nucode::ble::audio
{
    namespace
    {
        constexpr std::size_t maximumDescriptionLength = 31U;

        /** @brief profile 원본 반환값을 공개 오류로 변환합니다. */
        Error mapNativeError(int error) noexcept
        {
            if (error == 0)
            {
                return Error::none;
            }
            if (error == -EINVAL)
            {
                return Error::invalid_argument;
            }
            if (error == -EALREADY)
            {
                return Error::already_started;
            }
            if (error == -EBUSY)
            {
                return Error::busy;
            }
            if ((error == -ENOTCONN) || (error == -ECONNRESET))
            {
                return Error::not_connected;
            }
            if ((error == -ENOTSUP) || (error == -ENOENT))
            {
                return Error::unsupported;
            }
            return Error::stack_error;
        }

        /** @brief service가 복사할 수 있는 bounded UTF-8 설명인지 확인합니다. */
        bool validDescription(const char *description) noexcept
        {
            return (description != nullptr) &&
                   (strnlen(description, maximumDescriptionLength + 1U) <=
                    maximumDescriptionLength);
        }

        /** @brief AICS 초기 설정의 범위와 enum 값을 확인합니다. */
        bool validInputConfig(const AudioInputConfig &config) noexcept
        {
            const auto mode = static_cast<std::uint8_t>(config.mode);
            const auto type = static_cast<std::uint8_t>(config.type);
            return (config.units != 0U) && (config.minimum_gain <= config.maximum_gain) &&
                   (config.gain >= config.minimum_gain) && (config.gain <= config.maximum_gain) &&
                   (mode <= static_cast<std::uint8_t>(AudioInputMode::automatic)) &&
                   (type <= static_cast<std::uint8_t>(AudioInputType::ambient)) &&
                   validDescription(config.description);
        }

        /** @brief server AICS의 gain mode를 공개 enum 값으로 변경합니다. */
        int setServerInputMode(struct bt_aics *input, AudioInputMode mode) noexcept
        {
            if (input == nullptr)
            {
                return -ENODEV;
            }
            switch (mode)
            {
            case AudioInputMode::manual_only:
                return bt_aics_gain_set_manual_only(input);
            case AudioInputMode::automatic_only:
                return bt_aics_gain_set_auto_only(input);
            case AudioInputMode::manual:
                return bt_aics_manual_gain_set(input);
            case AudioInputMode::automatic:
                return bt_aics_automatic_gain_set(input);
            default:
                return -EINVAL;
            }
        }
    } // namespace

#if defined(CONFIG_BT_VCP_VOL_REND) && (CONFIG_BT_VCP_VOL_REND_VOCS_INSTANCE_COUNT == 1) &&        \
    (CONFIG_BT_VCP_VOL_REND_AICS_INSTANCE_COUNT == 1)

    namespace
    {
        /** @brief image 수명 동안 유지하는 Volume Renderer service 상태입니다. */
        struct RendererBackend
        {
            VolumeRenderer *owner = nullptr;
            std::uint32_t generation = 0U;
            std::uint32_t updates = 0U;
            bool registered = false;
            int error = 0;
            VolumeState volume = {};
            VolumeOffsetState offset = {};
            AudioInputState input = {};
            struct bt_vcp_included included = {};
        };

        RendererBackend rendererBackend;

        /** @brief VCS state read 또는 변경을 bounded 공개 상태에 반영합니다. */
        void rendererVolumeState(struct bt_conn *, int error, std::uint8_t volume,
                                 std::uint8_t mute) noexcept
        {
            if (rendererBackend.owner == nullptr)
            {
                return;
            }
            rendererBackend.error = error;
            if (error == 0)
            {
                rendererBackend.volume.volume = volume;
                rendererBackend.volume.muted = mute == BT_VCP_STATE_MUTED;
                ++rendererBackend.updates;
            }
        }

        /** @brief VCS flags read 또는 변경을 공개 상태에 반영합니다. */
        void rendererFlags(struct bt_conn *, int error, std::uint8_t flags) noexcept
        {
            if (rendererBackend.owner == nullptr)
            {
                return;
            }
            rendererBackend.error = error;
            if (error == 0)
            {
                rendererBackend.volume.flags = flags;
                ++rendererBackend.updates;
            }
        }

        /** @brief 포함 VOCS offset 변경을 공개 상태에 반영합니다. */
        void rendererOffsetState(struct bt_vocs *instance, int error, std::int16_t offset) noexcept
        {
            if ((rendererBackend.owner == nullptr) ||
                ((rendererBackend.included.vocs != nullptr) &&
                 (instance != rendererBackend.included.vocs[0])))
            {
                return;
            }
            rendererBackend.error = error;
            if (error == 0)
            {
                rendererBackend.offset.offset = offset;
                ++rendererBackend.updates;
            }
        }

        /** @brief 포함 VOCS location 변경을 공개 상태에 반영합니다. */
        void rendererOffsetLocation(struct bt_vocs *instance, int error,
                                    std::uint32_t location) noexcept
        {
            if ((rendererBackend.owner == nullptr) ||
                ((rendererBackend.included.vocs != nullptr) &&
                 (instance != rendererBackend.included.vocs[0])))
            {
                return;
            }
            rendererBackend.error = error;
            if (error == 0)
            {
                rendererBackend.offset.location = location;
                ++rendererBackend.updates;
            }
        }

        /** @brief 포함 VOCS 설명 변경 결과를 기록합니다. */
        void rendererOffsetDescription(struct bt_vocs *instance, int error, char *) noexcept
        {
            if ((rendererBackend.owner == nullptr) ||
                ((rendererBackend.included.vocs != nullptr) &&
                 (instance != rendererBackend.included.vocs[0])))
            {
                return;
            }
            rendererBackend.error = error;
            if (error == 0)
            {
                ++rendererBackend.updates;
            }
        }

        /** @brief 포함 AICS state 변경을 공개 상태에 반영합니다. */
        void rendererInputState(struct bt_aics *instance, int error, std::int8_t gain,
                                std::uint8_t mute, std::uint8_t mode) noexcept
        {
            if ((rendererBackend.owner == nullptr) ||
                ((rendererBackend.included.aics != nullptr) &&
                 (instance != rendererBackend.included.aics[0])))
            {
                return;
            }
            rendererBackend.error = error;
            if (error == 0)
            {
                rendererBackend.input.gain = gain;
                rendererBackend.input.muted = mute == BT_AICS_STATE_MUTED;
                rendererBackend.input.mute_disabled = mute == BT_AICS_STATE_MUTE_DISABLED;
                rendererBackend.input.mode = static_cast<AudioInputMode>(mode);
                ++rendererBackend.updates;
            }
        }

        /** @brief 포함 AICS gain 범위를 공개 상태에 반영합니다. */
        void rendererInputGainSetting(struct bt_aics *instance, int error, std::uint8_t units,
                                      std::int8_t minimum, std::int8_t maximum) noexcept
        {
            if ((rendererBackend.owner == nullptr) ||
                ((rendererBackend.included.aics != nullptr) &&
                 (instance != rendererBackend.included.aics[0])))
            {
                return;
            }
            rendererBackend.error = error;
            if (error == 0)
            {
                rendererBackend.input.units = units;
                rendererBackend.input.minimum_gain = minimum;
                rendererBackend.input.maximum_gain = maximum;
                ++rendererBackend.updates;
            }
        }

        /** @brief 포함 AICS 입력 형식을 공개 상태에 반영합니다. */
        void rendererInputType(struct bt_aics *instance, int error, std::uint8_t type) noexcept
        {
            if ((rendererBackend.owner == nullptr) ||
                ((rendererBackend.included.aics != nullptr) &&
                 (instance != rendererBackend.included.aics[0])))
            {
                return;
            }
            rendererBackend.error = error;
            if (error == 0)
            {
                rendererBackend.input.type = static_cast<AudioInputType>(type);
                ++rendererBackend.updates;
            }
        }

        /** @brief 포함 AICS active 상태를 공개 상태에 반영합니다. */
        void rendererInputStatus(struct bt_aics *instance, int error, bool active) noexcept
        {
            if ((rendererBackend.owner == nullptr) ||
                ((rendererBackend.included.aics != nullptr) &&
                 (instance != rendererBackend.included.aics[0])))
            {
                return;
            }
            rendererBackend.error = error;
            if (error == 0)
            {
                rendererBackend.input.active = active;
                ++rendererBackend.updates;
            }
        }

        /** @brief 포함 AICS 설명 변경 결과를 기록합니다. */
        void rendererInputDescription(struct bt_aics *instance, int error, char *) noexcept
        {
            if ((rendererBackend.owner == nullptr) ||
                ((rendererBackend.included.aics != nullptr) &&
                 (instance != rendererBackend.included.aics[0])))
            {
                return;
            }
            rendererBackend.error = error;
            if (error == 0)
            {
                ++rendererBackend.updates;
            }
        }

        struct bt_vcp_vol_rend_cb rendererCallbacks = {
            .state = rendererVolumeState,
            .flags = rendererFlags,
        };

        struct bt_vocs_cb rendererOffsetCallbacks = {
            .state = rendererOffsetState,
            .location = rendererOffsetLocation,
            .description = rendererOffsetDescription,
        };

        struct bt_aics_cb rendererInputCallbacks = {
            .state = rendererInputState,
            .gain_setting = rendererInputGainSetting,
            .type = rendererInputType,
            .status = rendererInputStatus,
            .description = rendererInputDescription,
        };

        /** @brief 현재 facade가 Volume Renderer backend를 소유하는지 확인합니다. */
        bool ownsRenderer(const VolumeRenderer *owner, std::uint32_t generation) noexcept
        {
            return rendererBackend.registered && (rendererBackend.owner == owner) &&
                   (rendererBackend.generation == generation);
        }
    } // namespace

    Error VolumeRenderer::begin(const VolumeRendererConfig &config) noexcept
    {
        if (started_)
        {
            return record(Error::already_started);
        }
        if (!BLEDevice.initialized())
        {
            return record(Error::not_ready);
        }
        if ((rendererBackend.owner != nullptr) || (config.step == 0U) ||
            (config.output.offset < BT_VOCS_MIN_OFFSET) ||
            (config.output.offset > BT_VOCS_MAX_OFFSET) ||
            !validDescription(config.output.description) || !validInputConfig(config.input))
        {
            return record(rendererBackend.owner != nullptr ? Error::busy : Error::invalid_argument);
        }

        ++rendererBackend.generation;
        if (rendererBackend.generation == 0U)
        {
            ++rendererBackend.generation;
        }
        rendererBackend.owner = this;
        rendererBackend.error = 0;
        rendererBackend.updates = 0U;
        rendererBackend.volume = {config.volume, config.muted, 0U};
        rendererBackend.offset = {config.output.offset, config.output.location};
        rendererBackend.input = {
            config.input.gain,         config.input.minimum_gain,
            config.input.maximum_gain, config.input.units,
            config.input.mode,         config.input.type,
            config.input.muted,        false,
            config.input.active,
        };

        int result = 0;
        if (!rendererBackend.registered)
        {
            struct bt_vcp_vol_rend_register_param parameter = {};
            parameter.step = config.step;
            parameter.mute = config.muted ? BT_VCP_STATE_MUTED : BT_VCP_STATE_UNMUTED;
            parameter.volume = config.volume;
            parameter.cb = &rendererCallbacks;
            parameter.vocs_param[0].location = config.output.location;
            parameter.vocs_param[0].location_writable = config.output.location_writable;
            parameter.vocs_param[0].offset = config.output.offset;
            parameter.vocs_param[0].output_desc = const_cast<char *>(config.output.description);
            parameter.vocs_param[0].desc_writable = config.output.description_writable;
            parameter.vocs_param[0].cb = &rendererOffsetCallbacks;
            parameter.aics_param[0].gain = config.input.gain;
            parameter.aics_param[0].mute =
                config.input.muted ? BT_AICS_STATE_MUTED : BT_AICS_STATE_UNMUTED;
            parameter.aics_param[0].gain_mode = static_cast<std::uint8_t>(config.input.mode);
            parameter.aics_param[0].units = config.input.units;
            parameter.aics_param[0].min_gain = config.input.minimum_gain;
            parameter.aics_param[0].max_gain = config.input.maximum_gain;
            parameter.aics_param[0].type = static_cast<std::uint8_t>(config.input.type);
            parameter.aics_param[0].status = config.input.active;
            parameter.aics_param[0].desc_writable = config.input.description_writable;
            parameter.aics_param[0].description = const_cast<char *>(config.input.description);
            parameter.aics_param[0].cb = &rendererInputCallbacks;

            result = bt_vcp_vol_rend_register(&parameter);
            if (result == 0)
            {
                result = bt_vcp_vol_rend_included_get(&rendererBackend.included);
            }
            if ((result == 0) && ((rendererBackend.included.vocs_cnt != 1U) ||
                                  (rendererBackend.included.aics_cnt != 1U) ||
                                  (rendererBackend.included.vocs == nullptr) ||
                                  (rendererBackend.included.aics == nullptr) ||
                                  (rendererBackend.included.vocs[0] == nullptr) ||
                                  (rendererBackend.included.aics[0] == nullptr)))
            {
                result = -ENODEV;
            }
            if (result == 0)
            {
                rendererBackend.registered = true;
            }
        }
        else
        {
            result = bt_vcp_vol_rend_set_step(config.step);
            if (result == 0)
            {
                result = bt_vcp_vol_rend_set_vol(config.volume);
            }
            if (result == 0)
            {
                result = config.muted ? bt_vcp_vol_rend_mute() : bt_vcp_vol_rend_unmute();
            }
            if (result == 0)
            {
                result = bt_vocs_state_set(rendererBackend.included.vocs[0], config.output.offset);
            }
            if (result == 0)
            {
                result = bt_aics_gain_set(rendererBackend.included.aics[0], config.input.gain);
            }
        }
        if (result != 0)
        {
            rendererBackend.owner = nullptr;
            rendererBackend.error = result;
            return record(mapNativeError(result), result);
        }

        started_ = true;
        generation_ = rendererBackend.generation;
        return record(Error::none);
    }

    Error VolumeRenderer::end() noexcept
    {
        if (!started_)
        {
            return record(Error::not_started);
        }
        if (ownsRenderer(this, generation_))
        {
            rendererBackend.owner = nullptr;
            ++rendererBackend.generation;
        }
        started_ = false;
        return record(Error::none);
    }

#define NUCODE_RENDERER_CALL(method, step_error)                                                   \
    do                                                                                             \
    {                                                                                              \
        if (!ownsRenderer(this, generation_))                                                      \
        {                                                                                          \
            return record(Error::not_started);                                                     \
        }                                                                                          \
        const int result = (method);                                                               \
        rendererBackend.error = result;                                                            \
        return record(mapNativeError(result), result == 0 ? 0 : result);                           \
    } while (false)

    Error VolumeRenderer::setVolume(std::uint8_t volume) noexcept
    {
        NUCODE_RENDERER_CALL(bt_vcp_vol_rend_set_vol(volume), set_volume);
    }

    Error VolumeRenderer::volumeUp() noexcept
    {
        NUCODE_RENDERER_CALL(bt_vcp_vol_rend_vol_up(), volume_up);
    }

    Error VolumeRenderer::volumeDown() noexcept
    {
        NUCODE_RENDERER_CALL(bt_vcp_vol_rend_vol_down(), volume_down);
    }

    Error VolumeRenderer::mute() noexcept
    {
        NUCODE_RENDERER_CALL(bt_vcp_vol_rend_mute(), mute_volume);
    }

    Error VolumeRenderer::unmute() noexcept
    {
        NUCODE_RENDERER_CALL(bt_vcp_vol_rend_unmute(), unmute_volume);
    }

    Error VolumeRenderer::setOffset(std::int16_t offset) noexcept
    {
        if ((offset < BT_VOCS_MIN_OFFSET) || (offset > BT_VOCS_MAX_OFFSET))
        {
            return record(Error::invalid_argument);
        }
        NUCODE_RENDERER_CALL(bt_vocs_state_set(rendererBackend.included.vocs[0], offset),
                             set_offset);
    }

    Error VolumeRenderer::setOutputLocation(std::uint32_t location) noexcept
    {
        NUCODE_RENDERER_CALL(bt_vocs_location_set(rendererBackend.included.vocs[0], location),
                             set_output_location);
    }

    Error VolumeRenderer::setOutputDescription(const char *description) noexcept
    {
        if (!validDescription(description))
        {
            return record(Error::invalid_argument);
        }
        NUCODE_RENDERER_CALL(bt_vocs_description_set(rendererBackend.included.vocs[0], description),
                             set_output_description);
    }

    Error VolumeRenderer::setInputGain(std::int8_t gain) noexcept
    {
        if ((gain < rendererBackend.input.minimum_gain) ||
            (gain > rendererBackend.input.maximum_gain))
        {
            return record(Error::invalid_argument);
        }
        NUCODE_RENDERER_CALL(bt_aics_gain_set(rendererBackend.included.aics[0], gain),
                             set_input_gain);
    }

    Error VolumeRenderer::muteInput() noexcept
    {
        NUCODE_RENDERER_CALL(bt_aics_mute(rendererBackend.included.aics[0]), mute_input);
    }

    Error VolumeRenderer::unmuteInput() noexcept
    {
        NUCODE_RENDERER_CALL(bt_aics_unmute(rendererBackend.included.aics[0]), unmute_input);
    }

    Error VolumeRenderer::setInputMode(AudioInputMode mode) noexcept
    {
        NUCODE_RENDERER_CALL(setServerInputMode(rendererBackend.included.aics[0], mode),
                             set_input_mode);
    }

    Error VolumeRenderer::setInputDescription(const char *description) noexcept
    {
        if (!validDescription(description))
        {
            return record(Error::invalid_argument);
        }
        NUCODE_RENDERER_CALL(bt_aics_description_set(rendererBackend.included.aics[0], description),
                             set_input_description);
    }

#undef NUCODE_RENDERER_CALL

    bool VolumeRenderer::ready() const noexcept
    {
        return started_ && ownsRenderer(this, generation_);
    }

    VolumeState VolumeRenderer::state() const noexcept
    {
        return ready() ? rendererBackend.volume : VolumeState{};
    }

    VolumeOffsetState VolumeRenderer::offsetState() const noexcept
    {
        return ready() ? rendererBackend.offset : VolumeOffsetState{};
    }

    AudioInputState VolumeRenderer::inputState() const noexcept
    {
        return ready() ? rendererBackend.input : AudioInputState{};
    }

    std::uint32_t VolumeRenderer::stateUpdates() const noexcept
    {
        return ready() ? rendererBackend.updates : 0U;
    }

    Error VolumeRenderer::lastError() const noexcept
    {
        return (ready() && (rendererBackend.error != 0)) ? mapNativeError(rendererBackend.error)
                                                         : last_error_;
    }

    int VolumeRenderer::nativeCode() const noexcept
    {
        return (ready() && (rendererBackend.error != 0)) ? rendererBackend.error : native_code_;
    }

    Error VolumeRenderer::record(Error error, int native_code) noexcept
    {
        last_error_ = error;
        native_code_ = native_code;
        return error;
    }

#else

    Error VolumeRenderer::begin(const VolumeRendererConfig &) noexcept
    {
        return record(Error::unsupported);
    }

    Error VolumeRenderer::end() noexcept
    {
        return record(Error::not_started);
    }

#define NUCODE_RENDERER_UNSUPPORTED(name, signature)                                               \
    Error VolumeRenderer::name signature noexcept                                                  \
    {                                                                                              \
        return record(Error::unsupported);                                                         \
    }

    NUCODE_RENDERER_UNSUPPORTED(setVolume, (std::uint8_t))
    NUCODE_RENDERER_UNSUPPORTED(volumeUp, ())
    NUCODE_RENDERER_UNSUPPORTED(volumeDown, ())
    NUCODE_RENDERER_UNSUPPORTED(mute, ())
    NUCODE_RENDERER_UNSUPPORTED(unmute, ())
    NUCODE_RENDERER_UNSUPPORTED(setOffset, (std::int16_t))
    NUCODE_RENDERER_UNSUPPORTED(setOutputLocation, (std::uint32_t))
    NUCODE_RENDERER_UNSUPPORTED(setOutputDescription, (const char *))
    NUCODE_RENDERER_UNSUPPORTED(setInputGain, (std::int8_t))
    NUCODE_RENDERER_UNSUPPORTED(muteInput, ())
    NUCODE_RENDERER_UNSUPPORTED(unmuteInput, ())
    NUCODE_RENDERER_UNSUPPORTED(setInputMode, (AudioInputMode))
    NUCODE_RENDERER_UNSUPPORTED(setInputDescription, (const char *))

#undef NUCODE_RENDERER_UNSUPPORTED

    bool VolumeRenderer::ready() const noexcept
    {
        return false;
    }
    VolumeState VolumeRenderer::state() const noexcept
    {
        return {};
    }
    VolumeOffsetState VolumeRenderer::offsetState() const noexcept
    {
        return {};
    }
    AudioInputState VolumeRenderer::inputState() const noexcept
    {
        return {};
    }
    std::uint32_t VolumeRenderer::stateUpdates() const noexcept
    {
        return 0U;
    }
    Error VolumeRenderer::lastError() const noexcept
    {
        return last_error_;
    }
    int VolumeRenderer::nativeCode() const noexcept
    {
        return native_code_;
    }
    Error VolumeRenderer::record(Error error, int native_code) noexcept
    {
        last_error_ = error;
        native_code_ = native_code;
        return error;
    }

#endif

#if defined(CONFIG_BT_MICP_MIC_DEV) && (CONFIG_BT_MICP_MIC_DEV_AICS_INSTANCE_COUNT == 1)

    namespace
    {
        /** @brief image 수명 동안 유지하는 Microphone Device service 상태입니다. */
        struct MicrophoneBackend
        {
            MicrophoneDevice *owner = nullptr;
            std::uint32_t generation = 0U;
            std::uint32_t updates = 0U;
            bool registered = false;
            int error = 0;
            MicrophoneState microphone = {};
            AudioInputState input = {};
            struct bt_micp_included included = {};
        };

        MicrophoneBackend microphoneBackend;

        /** @brief MICS mute 변경을 공개 상태에 반영합니다. */
        void microphoneMuteState(std::uint8_t mute) noexcept
        {
            if (microphoneBackend.owner == nullptr)
            {
                return;
            }
            microphoneBackend.microphone.muted = mute == BT_MICP_MUTE_MUTED;
            microphoneBackend.microphone.mute_disabled = mute == BT_MICP_MUTE_DISABLED;
            microphoneBackend.error = 0;
            ++microphoneBackend.updates;
        }

        /** @brief MICP 포함 AICS state 변경을 공개 상태에 반영합니다. */
        void microphoneInputState(struct bt_aics *instance, int error, std::int8_t gain,
                                  std::uint8_t mute, std::uint8_t mode) noexcept
        {
            if ((microphoneBackend.owner == nullptr) ||
                ((microphoneBackend.included.aics != nullptr) &&
                 (instance != microphoneBackend.included.aics[0])))
            {
                return;
            }
            microphoneBackend.error = error;
            if (error == 0)
            {
                microphoneBackend.input.gain = gain;
                microphoneBackend.input.muted = mute == BT_AICS_STATE_MUTED;
                microphoneBackend.input.mute_disabled = mute == BT_AICS_STATE_MUTE_DISABLED;
                microphoneBackend.input.mode = static_cast<AudioInputMode>(mode);
                ++microphoneBackend.updates;
            }
        }

        /** @brief MICP 포함 AICS gain 범위를 공개 상태에 반영합니다. */
        void microphoneInputGainSetting(struct bt_aics *instance, int error, std::uint8_t units,
                                        std::int8_t minimum, std::int8_t maximum) noexcept
        {
            if ((microphoneBackend.owner == nullptr) ||
                ((microphoneBackend.included.aics != nullptr) &&
                 (instance != microphoneBackend.included.aics[0])))
            {
                return;
            }
            microphoneBackend.error = error;
            if (error == 0)
            {
                microphoneBackend.input.units = units;
                microphoneBackend.input.minimum_gain = minimum;
                microphoneBackend.input.maximum_gain = maximum;
                ++microphoneBackend.updates;
            }
        }

        /** @brief MICP 포함 AICS type을 공개 상태에 반영합니다. */
        void microphoneInputType(struct bt_aics *instance, int error, std::uint8_t type) noexcept
        {
            if ((microphoneBackend.owner == nullptr) ||
                ((microphoneBackend.included.aics != nullptr) &&
                 (instance != microphoneBackend.included.aics[0])))
            {
                return;
            }
            microphoneBackend.error = error;
            if (error == 0)
            {
                microphoneBackend.input.type = static_cast<AudioInputType>(type);
                ++microphoneBackend.updates;
            }
        }

        /** @brief MICP 포함 AICS active 상태를 공개 상태에 반영합니다. */
        void microphoneInputStatus(struct bt_aics *instance, int error, bool active) noexcept
        {
            if ((microphoneBackend.owner == nullptr) ||
                ((microphoneBackend.included.aics != nullptr) &&
                 (instance != microphoneBackend.included.aics[0])))
            {
                return;
            }
            microphoneBackend.error = error;
            if (error == 0)
            {
                microphoneBackend.input.active = active;
                ++microphoneBackend.updates;
            }
        }

        /** @brief MICP 포함 AICS 설명 변경 결과를 기록합니다. */
        void microphoneInputDescription(struct bt_aics *instance, int error, char *) noexcept
        {
            if ((microphoneBackend.owner == nullptr) ||
                ((microphoneBackend.included.aics != nullptr) &&
                 (instance != microphoneBackend.included.aics[0])))
            {
                return;
            }
            microphoneBackend.error = error;
            if (error == 0)
            {
                ++microphoneBackend.updates;
            }
        }

        struct bt_micp_mic_dev_cb microphoneCallbacks = {
            .mute = microphoneMuteState,
        };

        struct bt_aics_cb microphoneInputCallbacks = {
            .state = microphoneInputState,
            .gain_setting = microphoneInputGainSetting,
            .type = microphoneInputType,
            .status = microphoneInputStatus,
            .description = microphoneInputDescription,
        };

        /** @brief 현재 facade가 Microphone Device backend를 소유하는지 확인합니다. */
        bool ownsMicrophone(const MicrophoneDevice *owner, std::uint32_t generation) noexcept
        {
            return microphoneBackend.registered && (microphoneBackend.owner == owner) &&
                   (microphoneBackend.generation == generation);
        }
    } // namespace

    Error MicrophoneDevice::begin(const MicrophoneDeviceConfig &config) noexcept
    {
        if (started_)
        {
            return record(Error::already_started);
        }
        if (!BLEDevice.initialized())
        {
            return record(Error::not_ready);
        }
        if ((microphoneBackend.owner != nullptr) || !validInputConfig(config.input))
        {
            return record(microphoneBackend.owner != nullptr ? Error::busy
                                                             : Error::invalid_argument);
        }

        ++microphoneBackend.generation;
        if (microphoneBackend.generation == 0U)
        {
            ++microphoneBackend.generation;
        }
        microphoneBackend.owner = this;
        microphoneBackend.error = 0;
        microphoneBackend.updates = 0U;
        microphoneBackend.microphone = {config.muted, false};
        microphoneBackend.input = {
            config.input.gain,         config.input.minimum_gain,
            config.input.maximum_gain, config.input.units,
            config.input.mode,         config.input.type,
            config.input.muted,        false,
            config.input.active,
        };

        int result = 0;
        if (!microphoneBackend.registered)
        {
            struct bt_micp_mic_dev_register_param parameter = {};
            parameter.cb = &microphoneCallbacks;
            parameter.aics_param[0].gain = config.input.gain;
            parameter.aics_param[0].mute =
                config.input.muted ? BT_AICS_STATE_MUTED : BT_AICS_STATE_UNMUTED;
            parameter.aics_param[0].gain_mode = static_cast<std::uint8_t>(config.input.mode);
            parameter.aics_param[0].units = config.input.units;
            parameter.aics_param[0].min_gain = config.input.minimum_gain;
            parameter.aics_param[0].max_gain = config.input.maximum_gain;
            parameter.aics_param[0].type = static_cast<std::uint8_t>(config.input.type);
            parameter.aics_param[0].status = config.input.active;
            parameter.aics_param[0].desc_writable = config.input.description_writable;
            parameter.aics_param[0].description = const_cast<char *>(config.input.description);
            parameter.aics_param[0].cb = &microphoneInputCallbacks;

            result = bt_micp_mic_dev_register(&parameter);
            if (result == 0)
            {
                result = bt_micp_mic_dev_included_get(&microphoneBackend.included);
            }
            if ((result == 0) && ((microphoneBackend.included.aics_cnt != 1U) ||
                                  (microphoneBackend.included.aics == nullptr) ||
                                  (microphoneBackend.included.aics[0] == nullptr)))
            {
                result = -ENODEV;
            }
            if (result == 0)
            {
                microphoneBackend.registered = true;
                result = config.muted ? bt_micp_mic_dev_mute() : bt_micp_mic_dev_unmute();
            }
        }
        else
        {
            result = config.muted ? bt_micp_mic_dev_mute() : bt_micp_mic_dev_unmute();
            if (result == 0)
            {
                result = bt_aics_gain_set(microphoneBackend.included.aics[0], config.input.gain);
            }
        }
        if (result != 0)
        {
            microphoneBackend.owner = nullptr;
            microphoneBackend.error = result;
            return record(mapNativeError(result), result);
        }

        started_ = true;
        generation_ = microphoneBackend.generation;
        return record(Error::none);
    }

    Error MicrophoneDevice::end() noexcept
    {
        if (!started_)
        {
            return record(Error::not_started);
        }
        if (ownsMicrophone(this, generation_))
        {
            microphoneBackend.owner = nullptr;
            ++microphoneBackend.generation;
        }
        started_ = false;
        return record(Error::none);
    }

#define NUCODE_MIC_DEVICE_CALL(method)                                                             \
    do                                                                                             \
    {                                                                                              \
        if (!ownsMicrophone(this, generation_))                                                    \
        {                                                                                          \
            return record(Error::not_started);                                                     \
        }                                                                                          \
        const int result = (method);                                                               \
        microphoneBackend.error = result;                                                          \
        return record(mapNativeError(result), result == 0 ? 0 : result);                           \
    } while (false)

    Error MicrophoneDevice::mute() noexcept
    {
        NUCODE_MIC_DEVICE_CALL(bt_micp_mic_dev_mute());
    }

    Error MicrophoneDevice::unmute() noexcept
    {
        NUCODE_MIC_DEVICE_CALL(bt_micp_mic_dev_unmute());
    }

    Error MicrophoneDevice::disableMute() noexcept
    {
        NUCODE_MIC_DEVICE_CALL(bt_micp_mic_dev_mute_disable());
    }

    Error MicrophoneDevice::setInputGain(std::int8_t gain) noexcept
    {
        if ((gain < microphoneBackend.input.minimum_gain) ||
            (gain > microphoneBackend.input.maximum_gain))
        {
            return record(Error::invalid_argument);
        }
        NUCODE_MIC_DEVICE_CALL(bt_aics_gain_set(microphoneBackend.included.aics[0], gain));
    }

    Error MicrophoneDevice::muteInput() noexcept
    {
        NUCODE_MIC_DEVICE_CALL(bt_aics_mute(microphoneBackend.included.aics[0]));
    }

    Error MicrophoneDevice::unmuteInput() noexcept
    {
        NUCODE_MIC_DEVICE_CALL(bt_aics_unmute(microphoneBackend.included.aics[0]));
    }

    Error MicrophoneDevice::setInputMode(AudioInputMode mode) noexcept
    {
        NUCODE_MIC_DEVICE_CALL(setServerInputMode(microphoneBackend.included.aics[0], mode));
    }

    Error MicrophoneDevice::setInputDescription(const char *description) noexcept
    {
        if (!validDescription(description))
        {
            return record(Error::invalid_argument);
        }
        NUCODE_MIC_DEVICE_CALL(
            bt_aics_description_set(microphoneBackend.included.aics[0], description));
    }

#undef NUCODE_MIC_DEVICE_CALL

    bool MicrophoneDevice::ready() const noexcept
    {
        return started_ && ownsMicrophone(this, generation_);
    }

    MicrophoneState MicrophoneDevice::state() const noexcept
    {
        return ready() ? microphoneBackend.microphone : MicrophoneState{};
    }

    AudioInputState MicrophoneDevice::inputState() const noexcept
    {
        return ready() ? microphoneBackend.input : AudioInputState{};
    }

    std::uint32_t MicrophoneDevice::stateUpdates() const noexcept
    {
        return ready() ? microphoneBackend.updates : 0U;
    }

    Error MicrophoneDevice::lastError() const noexcept
    {
        return (ready() && (microphoneBackend.error != 0)) ? mapNativeError(microphoneBackend.error)
                                                           : last_error_;
    }

    int MicrophoneDevice::nativeCode() const noexcept
    {
        return (ready() && (microphoneBackend.error != 0)) ? microphoneBackend.error : native_code_;
    }

    Error MicrophoneDevice::record(Error error, int native_code) noexcept
    {
        last_error_ = error;
        native_code_ = native_code;
        return error;
    }

#else

    Error MicrophoneDevice::begin(const MicrophoneDeviceConfig &) noexcept
    {
        return record(Error::unsupported);
    }

    Error MicrophoneDevice::end() noexcept
    {
        return record(Error::not_started);
    }

#define NUCODE_MIC_DEVICE_UNSUPPORTED(name, signature)                                             \
    Error MicrophoneDevice::name signature noexcept                                                \
    {                                                                                              \
        return record(Error::unsupported);                                                         \
    }

    NUCODE_MIC_DEVICE_UNSUPPORTED(mute, ())
    NUCODE_MIC_DEVICE_UNSUPPORTED(unmute, ())
    NUCODE_MIC_DEVICE_UNSUPPORTED(disableMute, ())
    NUCODE_MIC_DEVICE_UNSUPPORTED(setInputGain, (std::int8_t))
    NUCODE_MIC_DEVICE_UNSUPPORTED(muteInput, ())
    NUCODE_MIC_DEVICE_UNSUPPORTED(unmuteInput, ())
    NUCODE_MIC_DEVICE_UNSUPPORTED(setInputMode, (AudioInputMode))
    NUCODE_MIC_DEVICE_UNSUPPORTED(setInputDescription, (const char *))

#undef NUCODE_MIC_DEVICE_UNSUPPORTED

    bool MicrophoneDevice::ready() const noexcept
    {
        return false;
    }
    MicrophoneState MicrophoneDevice::state() const noexcept
    {
        return {};
    }
    AudioInputState MicrophoneDevice::inputState() const noexcept
    {
        return {};
    }
    std::uint32_t MicrophoneDevice::stateUpdates() const noexcept
    {
        return 0U;
    }
    Error MicrophoneDevice::lastError() const noexcept
    {
        return last_error_;
    }
    int MicrophoneDevice::nativeCode() const noexcept
    {
        return native_code_;
    }
    Error MicrophoneDevice::record(Error error, int native_code) noexcept
    {
        last_error_ = error;
        native_code_ = native_code;
        return error;
    }

#endif

} // namespace nucode::ble::audio

#else

namespace nucode::ble::audio
{
    Error VolumeRenderer::begin(const VolumeRendererConfig &) noexcept
    {
        return record(Error::unsupported);
    }
    Error VolumeRenderer::end() noexcept
    {
        return record(Error::not_started);
    }
#define NUCODE_RENDERER_STUB(name, signature)                                                      \
    Error VolumeRenderer::name signature noexcept                                                  \
    {                                                                                              \
        return record(Error::unsupported);                                                         \
    }
    NUCODE_RENDERER_STUB(setVolume, (std::uint8_t))
    NUCODE_RENDERER_STUB(volumeUp, ())
    NUCODE_RENDERER_STUB(volumeDown, ())
    NUCODE_RENDERER_STUB(mute, ())
    NUCODE_RENDERER_STUB(unmute, ())
    NUCODE_RENDERER_STUB(setOffset, (std::int16_t))
    NUCODE_RENDERER_STUB(setOutputLocation, (std::uint32_t))
    NUCODE_RENDERER_STUB(setOutputDescription, (const char *))
    NUCODE_RENDERER_STUB(setInputGain, (std::int8_t))
    NUCODE_RENDERER_STUB(muteInput, ())
    NUCODE_RENDERER_STUB(unmuteInput, ())
    NUCODE_RENDERER_STUB(setInputMode, (AudioInputMode))
    NUCODE_RENDERER_STUB(setInputDescription, (const char *))
#undef NUCODE_RENDERER_STUB
    bool VolumeRenderer::ready() const noexcept
    {
        return false;
    }
    VolumeState VolumeRenderer::state() const noexcept
    {
        return {};
    }
    VolumeOffsetState VolumeRenderer::offsetState() const noexcept
    {
        return {};
    }
    AudioInputState VolumeRenderer::inputState() const noexcept
    {
        return {};
    }
    std::uint32_t VolumeRenderer::stateUpdates() const noexcept
    {
        return 0U;
    }
    Error VolumeRenderer::lastError() const noexcept
    {
        return last_error_;
    }
    int VolumeRenderer::nativeCode() const noexcept
    {
        return native_code_;
    }
    Error VolumeRenderer::record(Error error, int native_code) noexcept
    {
        last_error_ = error;
        native_code_ = native_code;
        return error;
    }

    Error MicrophoneDevice::begin(const MicrophoneDeviceConfig &) noexcept
    {
        return record(Error::unsupported);
    }
    Error MicrophoneDevice::end() noexcept
    {
        return record(Error::not_started);
    }
#define NUCODE_MIC_DEVICE_STUB(name, signature)                                                    \
    Error MicrophoneDevice::name signature noexcept                                                \
    {                                                                                              \
        return record(Error::unsupported);                                                         \
    }
    NUCODE_MIC_DEVICE_STUB(mute, ())
    NUCODE_MIC_DEVICE_STUB(unmute, ())
    NUCODE_MIC_DEVICE_STUB(disableMute, ())
    NUCODE_MIC_DEVICE_STUB(setInputGain, (std::int8_t))
    NUCODE_MIC_DEVICE_STUB(muteInput, ())
    NUCODE_MIC_DEVICE_STUB(unmuteInput, ())
    NUCODE_MIC_DEVICE_STUB(setInputMode, (AudioInputMode))
    NUCODE_MIC_DEVICE_STUB(setInputDescription, (const char *))
#undef NUCODE_MIC_DEVICE_STUB
    bool MicrophoneDevice::ready() const noexcept
    {
        return false;
    }
    MicrophoneState MicrophoneDevice::state() const noexcept
    {
        return {};
    }
    AudioInputState MicrophoneDevice::inputState() const noexcept
    {
        return {};
    }
    std::uint32_t MicrophoneDevice::stateUpdates() const noexcept
    {
        return 0U;
    }
    Error MicrophoneDevice::lastError() const noexcept
    {
        return last_error_;
    }
    int MicrophoneDevice::nativeCode() const noexcept
    {
        return native_code_;
    }
    Error MicrophoneDevice::record(Error error, int native_code) noexcept
    {
        last_error_ = error;
        native_code_ = native_code;
        return error;
    }
} // namespace nucode::ble::audio

#endif
