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
#include <zephyr/kernel.h>

#include <errno.h>
#include <string.h>

namespace nucode::ble::audio
{
    namespace
    {
        constexpr std::size_t maximumDescriptionLength = 31U;

        /** @brief 바이트 길이가 정해진 문자열의 UTF-8 well-formed 여부를 검사합니다. */
        bool validUtf8(const char *text, std::size_t length) noexcept
        {
            std::size_t index = 0U;
            while (index < length)
            {
                const auto first = static_cast<std::uint8_t>(text[index]);
                if (first <= 0x7fU)
                {
                    ++index;
                    continue;
                }

                std::size_t continuation_count = 0U;
                std::uint32_t code_point = 0U;
                std::uint32_t minimum = 0U;
                if ((first & 0xe0U) == 0xc0U)
                {
                    continuation_count = 1U;
                    code_point = first & 0x1fU;
                    minimum = 0x80U;
                }
                else if ((first & 0xf0U) == 0xe0U)
                {
                    continuation_count = 2U;
                    code_point = first & 0x0fU;
                    minimum = 0x800U;
                }
                else if ((first & 0xf8U) == 0xf0U)
                {
                    continuation_count = 3U;
                    code_point = first & 0x07U;
                    minimum = 0x10000U;
                }
                else
                {
                    return false;
                }
                if (index + continuation_count >= length)
                {
                    return false;
                }
                for (std::size_t offset = 1U; offset <= continuation_count; ++offset)
                {
                    const auto next = static_cast<std::uint8_t>(text[index + offset]);
                    if ((next & 0xc0U) != 0x80U)
                    {
                        return false;
                    }
                    code_point = (code_point << 6U) | (next & 0x3fU);
                }
                if ((code_point < minimum) || (code_point > 0x10ffffU) ||
                    ((code_point >= 0xd800U) && (code_point <= 0xdfffU)))
                {
                    return false;
                }
                index += continuation_count + 1U;
            }
            return true;
        }

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
            if (description == nullptr)
            {
                return false;
            }
            const std::size_t length = strnlen(description, maximumDescriptionLength + 1U);
            return (length <= maximumDescriptionLength) && validUtf8(description, length);
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
            bool output_location_writable = false;
            bool output_description_writable = false;
            bool input_description_writable = false;
            int error = 0;
            VolumeState volume = {};
            VolumeOffsetState offset = {};
            AudioInputState input = {};
            struct bt_vcp_included included = {};
        };

        RendererBackend rendererBackend;
        K_MUTEX_DEFINE(rendererBackendMutex);

        /** @brief 재등록할 수 없는 Volume Renderer 설정이 최초 등록값과 같은지 검사합니다. */
        bool rendererImmutableConfigMatches(const VolumeRendererConfig &config) noexcept
        {
            return (rendererBackend.output_location_writable == config.output.location_writable) &&
                   (rendererBackend.output_description_writable ==
                    config.output.description_writable) &&
                   (rendererBackend.input.minimum_gain == config.input.minimum_gain) &&
                   (rendererBackend.input.maximum_gain == config.input.maximum_gain) &&
                   (rendererBackend.input.units == config.input.units) &&
                   (rendererBackend.input.type == config.input.type) &&
                   (rendererBackend.input_description_writable ==
                    config.input.description_writable);
        }

        /** @brief VCS state read 또는 변경을 bounded 공개 상태에 반영합니다. */
        void rendererVolumeState(struct bt_conn *, int error, std::uint8_t volume,
                                 std::uint8_t mute) noexcept
        {
            k_mutex_lock(&rendererBackendMutex, K_FOREVER);
            if (rendererBackend.owner == nullptr)
            {
                k_mutex_unlock(&rendererBackendMutex);
                return;
            }
            rendererBackend.error = error;
            if (error == 0)
            {
                rendererBackend.volume.volume = volume;
                rendererBackend.volume.muted = mute == BT_VCP_STATE_MUTED;
                ++rendererBackend.updates;
            }
            k_mutex_unlock(&rendererBackendMutex);
        }

        /** @brief VCS flags read 또는 변경을 공개 상태에 반영합니다. */
        void rendererFlags(struct bt_conn *, int error, std::uint8_t flags) noexcept
        {
            k_mutex_lock(&rendererBackendMutex, K_FOREVER);
            if (rendererBackend.owner == nullptr)
            {
                k_mutex_unlock(&rendererBackendMutex);
                return;
            }
            rendererBackend.error = error;
            if (error == 0)
            {
                rendererBackend.volume.flags = flags;
                ++rendererBackend.updates;
            }
            k_mutex_unlock(&rendererBackendMutex);
        }

        /** @brief 포함 VOCS offset 변경을 공개 상태에 반영합니다. */
        void rendererOffsetState(struct bt_vocs *instance, int error, std::int16_t offset) noexcept
        {
            k_mutex_lock(&rendererBackendMutex, K_FOREVER);
            if ((rendererBackend.owner == nullptr) ||
                ((rendererBackend.included.vocs != nullptr) &&
                 (instance != rendererBackend.included.vocs[0])))
            {
                k_mutex_unlock(&rendererBackendMutex);
                return;
            }
            rendererBackend.error = error;
            if (error == 0)
            {
                rendererBackend.offset.offset = offset;
                ++rendererBackend.updates;
            }
            k_mutex_unlock(&rendererBackendMutex);
        }

        /** @brief 포함 VOCS location 변경을 공개 상태에 반영합니다. */
        void rendererOffsetLocation(struct bt_vocs *instance, int error,
                                    std::uint32_t location) noexcept
        {
            k_mutex_lock(&rendererBackendMutex, K_FOREVER);
            if ((rendererBackend.owner == nullptr) ||
                ((rendererBackend.included.vocs != nullptr) &&
                 (instance != rendererBackend.included.vocs[0])))
            {
                k_mutex_unlock(&rendererBackendMutex);
                return;
            }
            rendererBackend.error = error;
            if (error == 0)
            {
                rendererBackend.offset.location = location;
                ++rendererBackend.updates;
            }
            k_mutex_unlock(&rendererBackendMutex);
        }

        /** @brief 포함 VOCS 설명 변경 결과를 기록합니다. */
        void rendererOffsetDescription(struct bt_vocs *instance, int error, char *) noexcept
        {
            k_mutex_lock(&rendererBackendMutex, K_FOREVER);
            if ((rendererBackend.owner == nullptr) ||
                ((rendererBackend.included.vocs != nullptr) &&
                 (instance != rendererBackend.included.vocs[0])))
            {
                k_mutex_unlock(&rendererBackendMutex);
                return;
            }
            rendererBackend.error = error;
            if (error == 0)
            {
                ++rendererBackend.updates;
            }
            k_mutex_unlock(&rendererBackendMutex);
        }

        /** @brief 포함 AICS state 변경을 공개 상태에 반영합니다. */
        void rendererInputState(struct bt_aics *instance, int error, std::int8_t gain,
                                std::uint8_t mute, std::uint8_t mode) noexcept
        {
            k_mutex_lock(&rendererBackendMutex, K_FOREVER);
            if ((rendererBackend.owner == nullptr) ||
                ((rendererBackend.included.aics != nullptr) &&
                 (instance != rendererBackend.included.aics[0])))
            {
                k_mutex_unlock(&rendererBackendMutex);
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
            k_mutex_unlock(&rendererBackendMutex);
        }

        /** @brief 포함 AICS gain 범위를 공개 상태에 반영합니다. */
        void rendererInputGainSetting(struct bt_aics *instance, int error, std::uint8_t units,
                                      std::int8_t minimum, std::int8_t maximum) noexcept
        {
            k_mutex_lock(&rendererBackendMutex, K_FOREVER);
            if ((rendererBackend.owner == nullptr) ||
                ((rendererBackend.included.aics != nullptr) &&
                 (instance != rendererBackend.included.aics[0])))
            {
                k_mutex_unlock(&rendererBackendMutex);
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
            k_mutex_unlock(&rendererBackendMutex);
        }

        /** @brief 포함 AICS 입력 형식을 공개 상태에 반영합니다. */
        void rendererInputType(struct bt_aics *instance, int error, std::uint8_t type) noexcept
        {
            k_mutex_lock(&rendererBackendMutex, K_FOREVER);
            if ((rendererBackend.owner == nullptr) ||
                ((rendererBackend.included.aics != nullptr) &&
                 (instance != rendererBackend.included.aics[0])))
            {
                k_mutex_unlock(&rendererBackendMutex);
                return;
            }
            rendererBackend.error = error;
            if (error == 0)
            {
                rendererBackend.input.type = static_cast<AudioInputType>(type);
                ++rendererBackend.updates;
            }
            k_mutex_unlock(&rendererBackendMutex);
        }

        /** @brief 포함 AICS active 상태를 공개 상태에 반영합니다. */
        void rendererInputStatus(struct bt_aics *instance, int error, bool active) noexcept
        {
            k_mutex_lock(&rendererBackendMutex, K_FOREVER);
            if ((rendererBackend.owner == nullptr) ||
                ((rendererBackend.included.aics != nullptr) &&
                 (instance != rendererBackend.included.aics[0])))
            {
                k_mutex_unlock(&rendererBackendMutex);
                return;
            }
            rendererBackend.error = error;
            if (error == 0)
            {
                rendererBackend.input.active = active;
                ++rendererBackend.updates;
            }
            k_mutex_unlock(&rendererBackendMutex);
        }

        /** @brief 포함 AICS 설명 변경 결과를 기록합니다. */
        void rendererInputDescription(struct bt_aics *instance, int error, char *) noexcept
        {
            k_mutex_lock(&rendererBackendMutex, K_FOREVER);
            if ((rendererBackend.owner == nullptr) ||
                ((rendererBackend.included.aics != nullptr) &&
                 (instance != rendererBackend.included.aics[0])))
            {
                k_mutex_unlock(&rendererBackendMutex);
                return;
            }
            rendererBackend.error = error;
            if (error == 0)
            {
                ++rendererBackend.updates;
            }
            k_mutex_unlock(&rendererBackendMutex);
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
        bool ownsRendererLocked(const VolumeRenderer *owner, std::uint32_t generation) noexcept
        {
            return rendererBackend.registered && (rendererBackend.owner == owner) &&
                   (rendererBackend.generation == generation);
        }
    } // namespace

    Error VolumeRenderer::begin(const VolumeRendererConfig &config) noexcept
    {
        k_mutex_lock(&rendererBackendMutex, K_FOREVER);
        const bool object_started = started_;
        k_mutex_unlock(&rendererBackendMutex);
        if (object_started)
        {
            return record(Error::already_started);
        }
        if (!BLEDevice.initialized())
        {
            return record(Error::not_ready);
        }
        if ((config.step == 0U) || (config.output.offset < BT_VOCS_MIN_OFFSET) ||
            (config.output.offset > BT_VOCS_MAX_OFFSET) ||
            !validDescription(config.output.description) || !validInputConfig(config.input))
        {
            return record(Error::invalid_argument);
        }

        k_mutex_lock(&rendererBackendMutex, K_FOREVER);
        if (rendererBackend.owner != nullptr)
        {
            k_mutex_unlock(&rendererBackendMutex);
            return record(Error::busy);
        }
        if (rendererBackend.registered && !rendererImmutableConfigMatches(config))
        {
            k_mutex_unlock(&rendererBackendMutex);
            return record(Error::invalid_argument, -EINVAL);
        }
        if (rendererBackend.registered && rendererBackend.input.mute_disabled)
        {
            k_mutex_unlock(&rendererBackendMutex);
            return record(Error::unsupported, -ENOTSUP);
        }
        if (rendererBackend.registered && ((rendererBackend.included.vocs_cnt != 1U) ||
                                           (rendererBackend.included.aics_cnt != 1U) ||
                                           (rendererBackend.included.vocs == nullptr) ||
                                           (rendererBackend.included.aics == nullptr) ||
                                           (rendererBackend.included.vocs[0] == nullptr) ||
                                           (rendererBackend.included.aics[0] == nullptr)))
        {
            k_mutex_unlock(&rendererBackendMutex);
            return record(Error::unsupported, -ENODEV);
        }
        const bool already_registered = rendererBackend.registered;
        ++rendererBackend.generation;
        if (rendererBackend.generation == 0U)
        {
            ++rendererBackend.generation;
        }
        rendererBackend.owner = this;
        rendererBackend.error = 0;
        rendererBackend.updates = 0U;
        const std::uint32_t generation = rendererBackend.generation;
        struct bt_vocs *output_service =
            already_registered ? rendererBackend.included.vocs[0] : nullptr;
        struct bt_aics *input_service =
            already_registered ? rendererBackend.included.aics[0] : nullptr;
        k_mutex_unlock(&rendererBackendMutex);

        int result = 0;
        if (!already_registered)
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
                struct bt_vcp_included included = {};
                result = bt_vcp_vol_rend_included_get(&included);
                if ((result == 0) &&
                    ((included.vocs_cnt != 1U) || (included.aics_cnt != 1U) ||
                     (included.vocs == nullptr) || (included.aics == nullptr) ||
                     (included.vocs[0] == nullptr) || (included.aics[0] == nullptr)))
                {
                    result = -ENODEV;
                }
                k_mutex_lock(&rendererBackendMutex, K_FOREVER);
                rendererBackend.registered = true;
                rendererBackend.output_location_writable = config.output.location_writable;
                rendererBackend.output_description_writable = config.output.description_writable;
                rendererBackend.input_description_writable = config.input.description_writable;
                rendererBackend.input.minimum_gain = config.input.minimum_gain;
                rendererBackend.input.maximum_gain = config.input.maximum_gain;
                rendererBackend.input.units = config.input.units;
                rendererBackend.input.type = config.input.type;
                if (result == 0)
                {
                    rendererBackend.included = included;
                }
                k_mutex_unlock(&rendererBackendMutex);
                if (result == 0)
                {
                    output_service = included.vocs[0];
                    input_service = included.aics[0];
                }
            }
        }

        if (result == 0)
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
                result = bt_vocs_state_set(output_service, config.output.offset);
            }
            if (result == 0)
            {
                result = bt_vocs_location_set(output_service, config.output.location);
            }
            if (result == 0)
            {
                result = bt_vocs_description_set(output_service, config.output.description);
            }
            if (result == 0)
            {
                result = bt_aics_gain_set(input_service, config.input.gain);
            }
            if (result == 0)
            {
                result = config.input.muted ? bt_aics_mute(input_service)
                                            : bt_aics_unmute(input_service);
            }
            if (result == 0)
            {
                result = setServerInputMode(input_service, config.input.mode);
            }
            if (result == 0)
            {
                result = config.input.active ? bt_aics_activate(input_service)
                                             : bt_aics_deactivate(input_service);
            }
            if (result == 0)
            {
                result = bt_aics_description_set(input_service, config.input.description);
            }
            if (result == 0)
            {
                result = bt_vcp_vol_rend_get_state();
            }
            if (result == 0)
            {
                result = bt_vcp_vol_rend_get_flags();
            }
            if (result == 0)
            {
                result = bt_vocs_state_get(output_service);
            }
            if (result == 0)
            {
                result = bt_vocs_location_get(output_service);
            }
            if (result == 0)
            {
                result = bt_aics_state_get(input_service);
            }
            if (result == 0)
            {
                result = bt_aics_gain_setting_get(input_service);
            }
            if (result == 0)
            {
                result = bt_aics_type_get(input_service);
            }
            if (result == 0)
            {
                result = bt_aics_status_get(input_service);
            }
        }
        if (result != 0)
        {
            k_mutex_lock(&rendererBackendMutex, K_FOREVER);
            if (ownsRendererLocked(this, generation))
            {
                rendererBackend.owner = nullptr;
                rendererBackend.error = result;
                ++rendererBackend.generation;
            }
            k_mutex_unlock(&rendererBackendMutex);
            return record(mapNativeError(result), result);
        }

        k_mutex_lock(&rendererBackendMutex, K_FOREVER);
        started_ = true;
        generation_ = generation;
        k_mutex_unlock(&rendererBackendMutex);
        return record(Error::none);
    }

    Error VolumeRenderer::end() noexcept
    {
        k_mutex_lock(&rendererBackendMutex, K_FOREVER);
        if (!started_)
        {
            k_mutex_unlock(&rendererBackendMutex);
            return record(Error::not_started);
        }
        if (ownsRendererLocked(this, generation_))
        {
            rendererBackend.owner = nullptr;
            ++rendererBackend.generation;
        }
        started_ = false;
        k_mutex_unlock(&rendererBackendMutex);
        return record(Error::none);
    }

#define NUCODE_RENDERER_CALL(method)                                                               \
    do                                                                                             \
    {                                                                                              \
        k_mutex_lock(&rendererBackendMutex, K_FOREVER);                                            \
        if (!ownsRendererLocked(this, generation_))                                                \
        {                                                                                          \
            k_mutex_unlock(&rendererBackendMutex);                                                 \
            return record(Error::not_started);                                                     \
        }                                                                                          \
        struct bt_vocs *output_service = rendererBackend.included.vocs[0];                         \
        struct bt_aics *input_service = rendererBackend.included.aics[0];                          \
        const std::uint32_t call_generation = rendererBackend.generation;                          \
        k_mutex_unlock(&rendererBackendMutex);                                                     \
        const int result = (method);                                                               \
        k_mutex_lock(&rendererBackendMutex, K_FOREVER);                                            \
        if (ownsRendererLocked(this, call_generation))                                             \
        {                                                                                          \
            rendererBackend.error = result;                                                        \
        }                                                                                          \
        k_mutex_unlock(&rendererBackendMutex);                                                     \
        return record(mapNativeError(result), result == 0 ? 0 : result);                           \
    } while (false)

    Error VolumeRenderer::setVolume(std::uint8_t volume) noexcept
    {
        NUCODE_RENDERER_CALL(bt_vcp_vol_rend_set_vol(volume));
    }

    Error VolumeRenderer::volumeUp() noexcept
    {
        NUCODE_RENDERER_CALL(bt_vcp_vol_rend_vol_up());
    }

    Error VolumeRenderer::volumeDown() noexcept
    {
        NUCODE_RENDERER_CALL(bt_vcp_vol_rend_vol_down());
    }

    Error VolumeRenderer::mute() noexcept
    {
        NUCODE_RENDERER_CALL(bt_vcp_vol_rend_mute());
    }

    Error VolumeRenderer::unmute() noexcept
    {
        NUCODE_RENDERER_CALL(bt_vcp_vol_rend_unmute());
    }

    Error VolumeRenderer::setOffset(std::int16_t offset) noexcept
    {
        if ((offset < BT_VOCS_MIN_OFFSET) || (offset > BT_VOCS_MAX_OFFSET))
        {
            return record(Error::invalid_argument);
        }
        NUCODE_RENDERER_CALL(bt_vocs_state_set(output_service, offset));
    }

    Error VolumeRenderer::setOutputLocation(std::uint32_t location) noexcept
    {
        NUCODE_RENDERER_CALL(bt_vocs_location_set(output_service, location));
    }

    Error VolumeRenderer::setOutputDescription(const char *description) noexcept
    {
        if (!validDescription(description))
        {
            return record(Error::invalid_argument);
        }
        NUCODE_RENDERER_CALL(bt_vocs_description_set(output_service, description));
    }

    Error VolumeRenderer::setInputGain(std::int8_t gain) noexcept
    {
        k_mutex_lock(&rendererBackendMutex, K_FOREVER);
        const bool valid_gain = (gain >= rendererBackend.input.minimum_gain) &&
                                (gain <= rendererBackend.input.maximum_gain);
        k_mutex_unlock(&rendererBackendMutex);
        if (!valid_gain)
        {
            return record(Error::invalid_argument);
        }
        NUCODE_RENDERER_CALL(bt_aics_gain_set(input_service, gain));
    }

    Error VolumeRenderer::muteInput() noexcept
    {
        NUCODE_RENDERER_CALL(bt_aics_mute(input_service));
    }

    Error VolumeRenderer::unmuteInput() noexcept
    {
        NUCODE_RENDERER_CALL(bt_aics_unmute(input_service));
    }

    Error VolumeRenderer::setInputMode(AudioInputMode mode) noexcept
    {
        NUCODE_RENDERER_CALL(setServerInputMode(input_service, mode));
    }

    Error VolumeRenderer::setInputDescription(const char *description) noexcept
    {
        if (!validDescription(description))
        {
            return record(Error::invalid_argument);
        }
        NUCODE_RENDERER_CALL(bt_aics_description_set(input_service, description));
    }

#undef NUCODE_RENDERER_CALL

    bool VolumeRenderer::ready() const noexcept
    {
        k_mutex_lock(&rendererBackendMutex, K_FOREVER);
        const bool value = started_ && ownsRendererLocked(this, generation_);
        k_mutex_unlock(&rendererBackendMutex);
        return value;
    }

    VolumeState VolumeRenderer::state() const noexcept
    {
        k_mutex_lock(&rendererBackendMutex, K_FOREVER);
        const VolumeState value =
            ownsRendererLocked(this, generation_) ? rendererBackend.volume : VolumeState{};
        k_mutex_unlock(&rendererBackendMutex);
        return value;
    }

    VolumeOffsetState VolumeRenderer::offsetState() const noexcept
    {
        k_mutex_lock(&rendererBackendMutex, K_FOREVER);
        const VolumeOffsetState value =
            ownsRendererLocked(this, generation_) ? rendererBackend.offset : VolumeOffsetState{};
        k_mutex_unlock(&rendererBackendMutex);
        return value;
    }

    AudioInputState VolumeRenderer::inputState() const noexcept
    {
        k_mutex_lock(&rendererBackendMutex, K_FOREVER);
        const AudioInputState value =
            ownsRendererLocked(this, generation_) ? rendererBackend.input : AudioInputState{};
        k_mutex_unlock(&rendererBackendMutex);
        return value;
    }

    std::uint32_t VolumeRenderer::stateUpdates() const noexcept
    {
        k_mutex_lock(&rendererBackendMutex, K_FOREVER);
        const std::uint32_t value =
            ownsRendererLocked(this, generation_) ? rendererBackend.updates : 0U;
        k_mutex_unlock(&rendererBackendMutex);
        return value;
    }

    Error VolumeRenderer::lastError() const noexcept
    {
        k_mutex_lock(&rendererBackendMutex, K_FOREVER);
        const int error = ownsRendererLocked(this, generation_) ? rendererBackend.error : 0;
        const Error fallback = last_error_;
        k_mutex_unlock(&rendererBackendMutex);
        return error != 0 ? mapNativeError(error) : fallback;
    }

    int VolumeRenderer::nativeCode() const noexcept
    {
        k_mutex_lock(&rendererBackendMutex, K_FOREVER);
        const int error = ownsRendererLocked(this, generation_) ? rendererBackend.error : 0;
        const int fallback = native_code_;
        k_mutex_unlock(&rendererBackendMutex);
        return error != 0 ? error : fallback;
    }

    Error VolumeRenderer::record(Error error, int native_code) noexcept
    {
        k_mutex_lock(&rendererBackendMutex, K_FOREVER);
        last_error_ = error;
        native_code_ = native_code;
        k_mutex_unlock(&rendererBackendMutex);
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
            bool input_description_writable = false;
            int error = 0;
            MicrophoneState microphone = {};
            AudioInputState input = {};
            struct bt_micp_included included = {};
        };

        MicrophoneBackend microphoneBackend;
        K_MUTEX_DEFINE(microphoneBackendMutex);

        /** @brief 재등록할 수 없는 Microphone Device 설정이 최초 등록값과 같은지 검사합니다. */
        bool microphoneImmutableConfigMatches(const MicrophoneDeviceConfig &config) noexcept
        {
            return (microphoneBackend.input.minimum_gain == config.input.minimum_gain) &&
                   (microphoneBackend.input.maximum_gain == config.input.maximum_gain) &&
                   (microphoneBackend.input.units == config.input.units) &&
                   (microphoneBackend.input.type == config.input.type) &&
                   (microphoneBackend.input_description_writable ==
                    config.input.description_writable);
        }

        /** @brief MICS mute 변경을 공개 상태에 반영합니다. */
        void microphoneMuteState(std::uint8_t mute) noexcept
        {
            k_mutex_lock(&microphoneBackendMutex, K_FOREVER);
            if (microphoneBackend.owner == nullptr)
            {
                k_mutex_unlock(&microphoneBackendMutex);
                return;
            }
            microphoneBackend.microphone.muted = mute == BT_MICP_MUTE_MUTED;
            microphoneBackend.microphone.mute_disabled = mute == BT_MICP_MUTE_DISABLED;
            microphoneBackend.error = 0;
            ++microphoneBackend.updates;
            k_mutex_unlock(&microphoneBackendMutex);
        }

        /** @brief MICP 포함 AICS state 변경을 공개 상태에 반영합니다. */
        void microphoneInputState(struct bt_aics *instance, int error, std::int8_t gain,
                                  std::uint8_t mute, std::uint8_t mode) noexcept
        {
            k_mutex_lock(&microphoneBackendMutex, K_FOREVER);
            if ((microphoneBackend.owner == nullptr) ||
                ((microphoneBackend.included.aics != nullptr) &&
                 (instance != microphoneBackend.included.aics[0])))
            {
                k_mutex_unlock(&microphoneBackendMutex);
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
            k_mutex_unlock(&microphoneBackendMutex);
        }

        /** @brief MICP 포함 AICS gain 범위를 공개 상태에 반영합니다. */
        void microphoneInputGainSetting(struct bt_aics *instance, int error, std::uint8_t units,
                                        std::int8_t minimum, std::int8_t maximum) noexcept
        {
            k_mutex_lock(&microphoneBackendMutex, K_FOREVER);
            if ((microphoneBackend.owner == nullptr) ||
                ((microphoneBackend.included.aics != nullptr) &&
                 (instance != microphoneBackend.included.aics[0])))
            {
                k_mutex_unlock(&microphoneBackendMutex);
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
            k_mutex_unlock(&microphoneBackendMutex);
        }

        /** @brief MICP 포함 AICS type을 공개 상태에 반영합니다. */
        void microphoneInputType(struct bt_aics *instance, int error, std::uint8_t type) noexcept
        {
            k_mutex_lock(&microphoneBackendMutex, K_FOREVER);
            if ((microphoneBackend.owner == nullptr) ||
                ((microphoneBackend.included.aics != nullptr) &&
                 (instance != microphoneBackend.included.aics[0])))
            {
                k_mutex_unlock(&microphoneBackendMutex);
                return;
            }
            microphoneBackend.error = error;
            if (error == 0)
            {
                microphoneBackend.input.type = static_cast<AudioInputType>(type);
                ++microphoneBackend.updates;
            }
            k_mutex_unlock(&microphoneBackendMutex);
        }

        /** @brief MICP 포함 AICS active 상태를 공개 상태에 반영합니다. */
        void microphoneInputStatus(struct bt_aics *instance, int error, bool active) noexcept
        {
            k_mutex_lock(&microphoneBackendMutex, K_FOREVER);
            if ((microphoneBackend.owner == nullptr) ||
                ((microphoneBackend.included.aics != nullptr) &&
                 (instance != microphoneBackend.included.aics[0])))
            {
                k_mutex_unlock(&microphoneBackendMutex);
                return;
            }
            microphoneBackend.error = error;
            if (error == 0)
            {
                microphoneBackend.input.active = active;
                ++microphoneBackend.updates;
            }
            k_mutex_unlock(&microphoneBackendMutex);
        }

        /** @brief MICP 포함 AICS 설명 변경 결과를 기록합니다. */
        void microphoneInputDescription(struct bt_aics *instance, int error, char *) noexcept
        {
            k_mutex_lock(&microphoneBackendMutex, K_FOREVER);
            if ((microphoneBackend.owner == nullptr) ||
                ((microphoneBackend.included.aics != nullptr) &&
                 (instance != microphoneBackend.included.aics[0])))
            {
                k_mutex_unlock(&microphoneBackendMutex);
                return;
            }
            microphoneBackend.error = error;
            if (error == 0)
            {
                ++microphoneBackend.updates;
            }
            k_mutex_unlock(&microphoneBackendMutex);
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
        bool ownsMicrophoneLocked(const MicrophoneDevice *owner, std::uint32_t generation) noexcept
        {
            return microphoneBackend.registered && (microphoneBackend.owner == owner) &&
                   (microphoneBackend.generation == generation);
        }
    } // namespace

    Error MicrophoneDevice::begin(const MicrophoneDeviceConfig &config) noexcept
    {
        k_mutex_lock(&microphoneBackendMutex, K_FOREVER);
        const bool object_started = started_;
        k_mutex_unlock(&microphoneBackendMutex);
        if (object_started)
        {
            return record(Error::already_started);
        }
        if (!BLEDevice.initialized())
        {
            return record(Error::not_ready);
        }
        if (!validInputConfig(config.input))
        {
            return record(Error::invalid_argument);
        }

        k_mutex_lock(&microphoneBackendMutex, K_FOREVER);
        if (microphoneBackend.owner != nullptr)
        {
            k_mutex_unlock(&microphoneBackendMutex);
            return record(Error::busy);
        }
        if (microphoneBackend.registered && !microphoneImmutableConfigMatches(config))
        {
            k_mutex_unlock(&microphoneBackendMutex);
            return record(Error::invalid_argument, -EINVAL);
        }
        if (microphoneBackend.registered &&
            (microphoneBackend.microphone.mute_disabled || microphoneBackend.input.mute_disabled))
        {
            k_mutex_unlock(&microphoneBackendMutex);
            return record(Error::unsupported, -ENOTSUP);
        }
        if (microphoneBackend.registered && ((microphoneBackend.included.aics_cnt != 1U) ||
                                             (microphoneBackend.included.aics == nullptr) ||
                                             (microphoneBackend.included.aics[0] == nullptr)))
        {
            k_mutex_unlock(&microphoneBackendMutex);
            return record(Error::unsupported, -ENODEV);
        }
        const bool already_registered = microphoneBackend.registered;
        ++microphoneBackend.generation;
        if (microphoneBackend.generation == 0U)
        {
            ++microphoneBackend.generation;
        }
        microphoneBackend.owner = this;
        microphoneBackend.error = 0;
        microphoneBackend.updates = 0U;
        const std::uint32_t generation = microphoneBackend.generation;
        struct bt_aics *input_service =
            already_registered ? microphoneBackend.included.aics[0] : nullptr;
        k_mutex_unlock(&microphoneBackendMutex);

        int result = 0;
        if (!already_registered)
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
                struct bt_micp_included included = {};
                result = bt_micp_mic_dev_included_get(&included);
                if ((result == 0) && ((included.aics_cnt != 1U) || (included.aics == nullptr) ||
                                      (included.aics[0] == nullptr)))
                {
                    result = -ENODEV;
                }
                k_mutex_lock(&microphoneBackendMutex, K_FOREVER);
                microphoneBackend.registered = true;
                microphoneBackend.input_description_writable = config.input.description_writable;
                microphoneBackend.input.minimum_gain = config.input.minimum_gain;
                microphoneBackend.input.maximum_gain = config.input.maximum_gain;
                microphoneBackend.input.units = config.input.units;
                microphoneBackend.input.type = config.input.type;
                if (result == 0)
                {
                    microphoneBackend.included = included;
                }
                k_mutex_unlock(&microphoneBackendMutex);
                if (result == 0)
                {
                    input_service = included.aics[0];
                }
            }
        }

        if (result == 0)
        {
            result = config.muted ? bt_micp_mic_dev_mute() : bt_micp_mic_dev_unmute();
            if (result == 0)
            {
                result = bt_aics_gain_set(input_service, config.input.gain);
            }
            if (result == 0)
            {
                result = config.input.muted ? bt_aics_mute(input_service)
                                            : bt_aics_unmute(input_service);
            }
            if (result == 0)
            {
                result = setServerInputMode(input_service, config.input.mode);
            }
            if (result == 0)
            {
                result = config.input.active ? bt_aics_activate(input_service)
                                             : bt_aics_deactivate(input_service);
            }
            if (result == 0)
            {
                result = bt_aics_description_set(input_service, config.input.description);
            }
            if (result == 0)
            {
                result = bt_micp_mic_dev_mute_get();
            }
            if (result == 0)
            {
                result = bt_aics_state_get(input_service);
            }
            if (result == 0)
            {
                result = bt_aics_gain_setting_get(input_service);
            }
            if (result == 0)
            {
                result = bt_aics_type_get(input_service);
            }
            if (result == 0)
            {
                result = bt_aics_status_get(input_service);
            }
        }
        if (result != 0)
        {
            k_mutex_lock(&microphoneBackendMutex, K_FOREVER);
            if (ownsMicrophoneLocked(this, generation))
            {
                microphoneBackend.owner = nullptr;
                microphoneBackend.error = result;
                ++microphoneBackend.generation;
            }
            k_mutex_unlock(&microphoneBackendMutex);
            return record(mapNativeError(result), result);
        }

        k_mutex_lock(&microphoneBackendMutex, K_FOREVER);
        started_ = true;
        generation_ = generation;
        k_mutex_unlock(&microphoneBackendMutex);
        return record(Error::none);
    }

    Error MicrophoneDevice::end() noexcept
    {
        k_mutex_lock(&microphoneBackendMutex, K_FOREVER);
        if (!started_)
        {
            k_mutex_unlock(&microphoneBackendMutex);
            return record(Error::not_started);
        }
        if (ownsMicrophoneLocked(this, generation_))
        {
            microphoneBackend.owner = nullptr;
            ++microphoneBackend.generation;
        }
        started_ = false;
        k_mutex_unlock(&microphoneBackendMutex);
        return record(Error::none);
    }

#define NUCODE_MIC_DEVICE_CALL(method)                                                             \
    do                                                                                             \
    {                                                                                              \
        k_mutex_lock(&microphoneBackendMutex, K_FOREVER);                                          \
        if (!ownsMicrophoneLocked(this, generation_))                                              \
        {                                                                                          \
            k_mutex_unlock(&microphoneBackendMutex);                                               \
            return record(Error::not_started);                                                     \
        }                                                                                          \
        struct bt_aics *input_service = microphoneBackend.included.aics[0];                        \
        const std::uint32_t call_generation = microphoneBackend.generation;                        \
        k_mutex_unlock(&microphoneBackendMutex);                                                   \
        const int result = (method);                                                               \
        k_mutex_lock(&microphoneBackendMutex, K_FOREVER);                                          \
        if (ownsMicrophoneLocked(this, call_generation))                                           \
        {                                                                                          \
            microphoneBackend.error = result;                                                      \
        }                                                                                          \
        k_mutex_unlock(&microphoneBackendMutex);                                                   \
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
        k_mutex_lock(&microphoneBackendMutex, K_FOREVER);
        const bool valid_gain = (gain >= microphoneBackend.input.minimum_gain) &&
                                (gain <= microphoneBackend.input.maximum_gain);
        k_mutex_unlock(&microphoneBackendMutex);
        if (!valid_gain)
        {
            return record(Error::invalid_argument);
        }
        NUCODE_MIC_DEVICE_CALL(bt_aics_gain_set(input_service, gain));
    }

    Error MicrophoneDevice::muteInput() noexcept
    {
        NUCODE_MIC_DEVICE_CALL(bt_aics_mute(input_service));
    }

    Error MicrophoneDevice::unmuteInput() noexcept
    {
        NUCODE_MIC_DEVICE_CALL(bt_aics_unmute(input_service));
    }

    Error MicrophoneDevice::setInputMode(AudioInputMode mode) noexcept
    {
        NUCODE_MIC_DEVICE_CALL(setServerInputMode(input_service, mode));
    }

    Error MicrophoneDevice::setInputDescription(const char *description) noexcept
    {
        if (!validDescription(description))
        {
            return record(Error::invalid_argument);
        }
        NUCODE_MIC_DEVICE_CALL(bt_aics_description_set(input_service, description));
    }

#undef NUCODE_MIC_DEVICE_CALL

    bool MicrophoneDevice::ready() const noexcept
    {
        k_mutex_lock(&microphoneBackendMutex, K_FOREVER);
        const bool value = started_ && ownsMicrophoneLocked(this, generation_);
        k_mutex_unlock(&microphoneBackendMutex);
        return value;
    }

    MicrophoneState MicrophoneDevice::state() const noexcept
    {
        k_mutex_lock(&microphoneBackendMutex, K_FOREVER);
        const MicrophoneState value = ownsMicrophoneLocked(this, generation_)
                                          ? microphoneBackend.microphone
                                          : MicrophoneState{};
        k_mutex_unlock(&microphoneBackendMutex);
        return value;
    }

    AudioInputState MicrophoneDevice::inputState() const noexcept
    {
        k_mutex_lock(&microphoneBackendMutex, K_FOREVER);
        const AudioInputState value =
            ownsMicrophoneLocked(this, generation_) ? microphoneBackend.input : AudioInputState{};
        k_mutex_unlock(&microphoneBackendMutex);
        return value;
    }

    std::uint32_t MicrophoneDevice::stateUpdates() const noexcept
    {
        k_mutex_lock(&microphoneBackendMutex, K_FOREVER);
        const std::uint32_t value =
            ownsMicrophoneLocked(this, generation_) ? microphoneBackend.updates : 0U;
        k_mutex_unlock(&microphoneBackendMutex);
        return value;
    }

    Error MicrophoneDevice::lastError() const noexcept
    {
        k_mutex_lock(&microphoneBackendMutex, K_FOREVER);
        const int error = ownsMicrophoneLocked(this, generation_) ? microphoneBackend.error : 0;
        const Error fallback = last_error_;
        k_mutex_unlock(&microphoneBackendMutex);
        return error != 0 ? mapNativeError(error) : fallback;
    }

    int MicrophoneDevice::nativeCode() const noexcept
    {
        k_mutex_lock(&microphoneBackendMutex, K_FOREVER);
        const int error = ownsMicrophoneLocked(this, generation_) ? microphoneBackend.error : 0;
        const int fallback = native_code_;
        k_mutex_unlock(&microphoneBackendMutex);
        return error != 0 ? error : fallback;
    }

    Error MicrophoneDevice::record(Error error, int native_code) noexcept
    {
        k_mutex_lock(&microphoneBackendMutex, K_FOREVER);
        last_error_ = error;
        native_code_ = native_code;
        k_mutex_unlock(&microphoneBackendMutex);
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
