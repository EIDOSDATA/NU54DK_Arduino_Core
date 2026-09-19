/**
 * @file NUCODE_BLE_Audio_ControlController.cpp
 * @brief VCP Volume Controller와 MICP Microphone Controller 공개 API를 구현합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include "NUCODE_BLE_Audio.h"

#if !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE) &&                                                   \
    (defined(CONFIG_BT_VCP_VOL_CTLR) || defined(CONFIG_BT_MICP_MIC_CTLR))

#include <NUCODE_BLE.h>
#include <internal/NUCODE_BLE_Internal.h>

#include <zephyr/bluetooth/audio/aics.h>
#include <zephyr/bluetooth/audio/micp.h>
#include <zephyr/bluetooth/audio/vcp.h>
#include <zephyr/bluetooth/audio/vocs.h>
#include <zephyr/bluetooth/conn.h>
#include <zephyr/sys/atomic.h>

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

        /** @brief 원격 write에 사용할 bounded UTF-8 설명인지 확인합니다. */
        bool validDescription(const char *description) noexcept
        {
            return (description != nullptr) &&
                   (strnlen(description, maximumDescriptionLength + 1U) <=
                    maximumDescriptionLength);
        }

        /** @brief client가 변경할 수 있는 AICS gain mode인지 확인합니다. */
        bool writableMode(AudioInputMode mode) noexcept
        {
            return (mode == AudioInputMode::manual) || (mode == AudioInputMode::automatic);
        }
    } // namespace

#if defined(CONFIG_BT_VCP_VOL_CTLR) && (CONFIG_BT_VCP_VOL_CTLR_MAX_VOCS_INST == 1) &&              \
    (CONFIG_BT_VCP_VOL_CTLR_MAX_AICS_INST == 1)

    namespace
    {
        /** @brief 한 연결에 결합한 VCP/VOCS/AICS client 상태입니다. */
        struct VolumeControllerBackend
        {
            VolumeController *owner = nullptr;
            BLEConnectionHandle handle = {};
            struct bt_conn *connection = nullptr;
            struct bt_vcp_vol_ctlr *controller = nullptr;
            struct bt_vocs *offset_service = nullptr;
            struct bt_aics *input_service = nullptr;
            std::uint32_t generation = 0U;
            std::uint32_t pending_generation = 0U;
            std::uint32_t updates = 0U;
            bool callbacks_registered = false;
            bool retired_connection = false;
            VolumeState volume = {};
            VolumeOffsetState offset = {};
            AudioInputState input = {};
            atomic_t stage = ATOMIC_INIT(static_cast<atomic_val_t>(AudioControlStage::idle));
            atomic_t step = ATOMIC_INIT(static_cast<atomic_val_t>(AudioControlStep::none));
            atomic_t busy = ATOMIC_INIT(0);
            atomic_t error = ATOMIC_INIT(0);
        };

        VolumeControllerBackend volumeBackend;

        /** @brief 이전 callback이 남을 수 있는 active 연결의 재소유를 차단합니다. */
        bool retiredVolumeConnectionActive() noexcept
        {
            if (!volumeBackend.retired_connection)
            {
                return false;
            }
            struct bt_conn *connection = internal::referenceConnection(volumeBackend.handle);
            if (connection == nullptr)
            {
                volumeBackend.retired_connection = false;
                volumeBackend.controller = nullptr;
                volumeBackend.offset_service = nullptr;
                volumeBackend.input_service = nullptr;
                return false;
            }
            bt_conn_unref(connection);
            return true;
        }

        /** @brief callback instance가 현재 active 연결과 generation에 속하는지 확인합니다. */
        bool currentVolumeController(struct bt_vcp_vol_ctlr *controller) noexcept
        {
            if ((volumeBackend.owner == nullptr) || (controller == nullptr) ||
                (controller != volumeBackend.controller) || (volumeBackend.connection == nullptr))
            {
                return false;
            }
            struct bt_conn *connection = nullptr;
            return (bt_vcp_vol_ctlr_conn_get(controller, &connection) == 0) &&
                   (connection == volumeBackend.connection) &&
                   internal::activeConnection(connection);
        }

        /** @brief VOCS callback instance가 현재 active 연결에 속하는지 확인합니다. */
        bool currentOffsetService(struct bt_vocs *instance) noexcept
        {
            if ((volumeBackend.owner == nullptr) || (instance == nullptr) ||
                (instance != volumeBackend.offset_service) || (volumeBackend.connection == nullptr))
            {
                return false;
            }
            struct bt_conn *connection = nullptr;
            return (bt_vocs_client_conn_get(instance, &connection) == 0) &&
                   (connection == volumeBackend.connection) &&
                   internal::activeConnection(connection);
        }

        /** @brief AICS callback instance가 현재 active 연결에 속하는지 확인합니다. */
        bool currentVolumeInput(struct bt_aics *instance) noexcept
        {
            if ((volumeBackend.owner == nullptr) || (instance == nullptr) ||
                (instance != volumeBackend.input_service) || (volumeBackend.connection == nullptr))
            {
                return false;
            }
            struct bt_conn *connection = nullptr;
            return (bt_aics_client_conn_get(instance, &connection) == 0) &&
                   (connection == volumeBackend.connection) &&
                   internal::activeConnection(connection);
        }

        /** @brief 현재 pending 작업을 결과와 함께 종료합니다. */
        void finishVolumeOperation(int error) noexcept
        {
            if ((volumeBackend.owner == nullptr) ||
                (volumeBackend.pending_generation != volumeBackend.generation))
            {
                return;
            }
            atomic_set(&volumeBackend.error, error);
            atomic_set(&volumeBackend.busy, 0);
            atomic_set(&volumeBackend.stage, static_cast<atomic_val_t>(AudioControlStage::ready));
        }

        /** @brief VCP와 포함 service 검색 완료를 검증합니다. */
        void volumeDiscovered(struct bt_vcp_vol_ctlr *controller, int error,
                              std::uint8_t offset_count, std::uint8_t input_count) noexcept
        {
            if ((volumeBackend.owner == nullptr) || (controller != volumeBackend.controller) ||
                (volumeBackend.pending_generation != volumeBackend.generation))
            {
                return;
            }
            if ((error == 0) && ((offset_count != 1U) || (input_count != 1U)))
            {
                error = -ENODEV;
            }
            if (error == 0)
            {
                struct bt_vcp_included included = {};
                error = bt_vcp_vol_ctlr_included_get(controller, &included);
                if ((error == 0) &&
                    ((included.vocs_cnt != 1U) || (included.aics_cnt != 1U) ||
                     (included.vocs == nullptr) || (included.aics == nullptr) ||
                     (included.vocs[0] == nullptr) || (included.aics[0] == nullptr)))
                {
                    error = -ENODEV;
                }
                if (error == 0)
                {
                    volumeBackend.offset_service = included.vocs[0];
                    volumeBackend.input_service = included.aics[0];
                }
            }
            atomic_set(&volumeBackend.error, error);
            atomic_set(&volumeBackend.busy, 0);
            atomic_set(&volumeBackend.stage,
                       static_cast<atomic_val_t>(error == 0 ? AudioControlStage::ready
                                                            : AudioControlStage::failed));
        }

        /** @brief VCS state read 또는 notification을 공개 상태에 반영합니다. */
        void volumeStateChanged(struct bt_vcp_vol_ctlr *controller, int error, std::uint8_t volume,
                                std::uint8_t mute) noexcept
        {
            if (!currentVolumeController(controller))
            {
                return;
            }
            atomic_set(&volumeBackend.error, error);
            if (error == 0)
            {
                volumeBackend.volume.volume = volume;
                volumeBackend.volume.muted = mute == BT_VCP_STATE_MUTED;
                ++volumeBackend.updates;
            }
            if ((static_cast<AudioControlStep>(atomic_get(&volumeBackend.step)) ==
                 AudioControlStep::read_volume) &&
                atomic_get(&volumeBackend.busy))
            {
                finishVolumeOperation(error);
            }
        }

        /** @brief VCS flags read 또는 notification을 공개 상태에 반영합니다. */
        void volumeFlagsChanged(struct bt_vcp_vol_ctlr *controller, int error,
                                std::uint8_t flags) noexcept
        {
            if (!currentVolumeController(controller))
            {
                return;
            }
            atomic_set(&volumeBackend.error, error);
            if (error == 0)
            {
                volumeBackend.volume.flags = flags;
                ++volumeBackend.updates;
            }
        }

        /** @brief VCS control point 작업 완료를 기록합니다. */
        void volumeWriteComplete(struct bt_vcp_vol_ctlr *controller, int error) noexcept
        {
            if (currentVolumeController(controller))
            {
                finishVolumeOperation(error);
            }
        }

        /** @brief VOCS offset read 또는 notification을 공개 상태에 반영합니다. */
        void offsetStateChanged(struct bt_vocs *instance, int error, std::int16_t offset) noexcept
        {
            if (!currentOffsetService(instance))
            {
                return;
            }
            atomic_set(&volumeBackend.error, error);
            if (error == 0)
            {
                volumeBackend.offset.offset = offset;
                ++volumeBackend.updates;
            }
            if ((static_cast<AudioControlStep>(atomic_get(&volumeBackend.step)) ==
                 AudioControlStep::read_offset) &&
                atomic_get(&volumeBackend.busy))
            {
                finishVolumeOperation(error);
            }
        }

        /** @brief VOCS location read 또는 notification을 공개 상태에 반영합니다. */
        void offsetLocationChanged(struct bt_vocs *instance, int error,
                                   std::uint32_t location) noexcept
        {
            if (!currentOffsetService(instance))
            {
                return;
            }
            atomic_set(&volumeBackend.error, error);
            if (error == 0)
            {
                volumeBackend.offset.location = location;
                ++volumeBackend.updates;
            }
        }

        /** @brief VOCS description read 또는 notification 결과를 기록합니다. */
        void offsetDescriptionChanged(struct bt_vocs *instance, int error, char *) noexcept
        {
            if (!currentOffsetService(instance))
            {
                return;
            }
            atomic_set(&volumeBackend.error, error);
            if (error == 0)
            {
                ++volumeBackend.updates;
            }
        }

        /** @brief VOCS control point 작업 완료를 기록합니다. */
        void offsetWriteComplete(struct bt_vocs *instance, int error) noexcept
        {
            if (currentOffsetService(instance))
            {
                finishVolumeOperation(error);
            }
        }

        /** @brief VCP 포함 AICS state를 공개 상태에 반영합니다. */
        void volumeInputStateChanged(struct bt_aics *instance, int error, std::int8_t gain,
                                     std::uint8_t mute, std::uint8_t mode) noexcept
        {
            if (!currentVolumeInput(instance))
            {
                return;
            }
            atomic_set(&volumeBackend.error, error);
            if (error == 0)
            {
                volumeBackend.input.gain = gain;
                volumeBackend.input.muted = mute == BT_AICS_STATE_MUTED;
                volumeBackend.input.mute_disabled = mute == BT_AICS_STATE_MUTE_DISABLED;
                volumeBackend.input.mode = static_cast<AudioInputMode>(mode);
                ++volumeBackend.updates;
            }
            if ((static_cast<AudioControlStep>(atomic_get(&volumeBackend.step)) ==
                 AudioControlStep::read_input) &&
                atomic_get(&volumeBackend.busy))
            {
                finishVolumeOperation(error);
            }
        }

        /** @brief VCP 포함 AICS gain 범위를 공개 상태에 반영합니다. */
        void volumeInputGainSetting(struct bt_aics *instance, int error, std::uint8_t units,
                                    std::int8_t minimum, std::int8_t maximum) noexcept
        {
            if (!currentVolumeInput(instance))
            {
                return;
            }
            atomic_set(&volumeBackend.error, error);
            if (error == 0)
            {
                volumeBackend.input.units = units;
                volumeBackend.input.minimum_gain = minimum;
                volumeBackend.input.maximum_gain = maximum;
                ++volumeBackend.updates;
            }
        }

        /** @brief VCP 포함 AICS type을 공개 상태에 반영합니다. */
        void volumeInputType(struct bt_aics *instance, int error, std::uint8_t type) noexcept
        {
            if (!currentVolumeInput(instance))
            {
                return;
            }
            atomic_set(&volumeBackend.error, error);
            if (error == 0)
            {
                volumeBackend.input.type = static_cast<AudioInputType>(type);
                ++volumeBackend.updates;
            }
        }

        /** @brief VCP 포함 AICS active 상태를 공개 상태에 반영합니다. */
        void volumeInputStatus(struct bt_aics *instance, int error, bool active) noexcept
        {
            if (!currentVolumeInput(instance))
            {
                return;
            }
            atomic_set(&volumeBackend.error, error);
            if (error == 0)
            {
                volumeBackend.input.active = active;
                ++volumeBackend.updates;
            }
        }

        /** @brief VCP 포함 AICS 설명 변경 결과를 기록합니다. */
        void volumeInputDescription(struct bt_aics *instance, int error, char *) noexcept
        {
            if (!currentVolumeInput(instance))
            {
                return;
            }
            atomic_set(&volumeBackend.error, error);
            if (error == 0)
            {
                ++volumeBackend.updates;
            }
        }

        /** @brief VCP 포함 AICS control point 작업 완료를 기록합니다. */
        void volumeInputWriteComplete(struct bt_aics *instance, int error) noexcept
        {
            if (currentVolumeInput(instance))
            {
                finishVolumeOperation(error);
            }
        }

        struct bt_vcp_vol_ctlr_cb volumeControllerCallbacks = {
            .state = volumeStateChanged,
            .flags = volumeFlagsChanged,
            .discover = volumeDiscovered,
            .vol_down = volumeWriteComplete,
            .vol_up = volumeWriteComplete,
            .mute = volumeWriteComplete,
            .unmute = volumeWriteComplete,
            .vol_down_unmute = volumeWriteComplete,
            .vol_up_unmute = volumeWriteComplete,
            .vol_set = volumeWriteComplete,
            .vocs_cb =
                {
                    .state = offsetStateChanged,
                    .location = offsetLocationChanged,
                    .description = offsetDescriptionChanged,
                    .set_offset = offsetWriteComplete,
                },
            .aics_cb =
                {
                    .state = volumeInputStateChanged,
                    .gain_setting = volumeInputGainSetting,
                    .type = volumeInputType,
                    .status = volumeInputStatus,
                    .description = volumeInputDescription,
                    .set_gain = volumeInputWriteComplete,
                    .unmute = volumeInputWriteComplete,
                    .mute = volumeInputWriteComplete,
                    .set_manual_mode = volumeInputWriteComplete,
                    .set_auto_mode = volumeInputWriteComplete,
                },
        };

        /** @brief 현재 facade가 VCP controller backend를 소유하는지 확인합니다. */
        bool ownsVolumeController(const VolumeController *owner, std::uint32_t generation) noexcept
        {
            return (volumeBackend.owner == owner) && (volumeBackend.generation == generation);
        }
    } // namespace

    Error VolumeController::begin(const BLEConnectionHandle &connection) noexcept
    {
        if (started_)
        {
            return record(Error::already_started);
        }
        if (volumeBackend.owner != nullptr)
        {
            return record(Error::busy);
        }
        if (retiredVolumeConnectionActive())
        {
            return record(Error::busy, -EBUSY);
        }

        struct bt_conn *native = internal::referenceConnection(connection);
        if (native == nullptr)
        {
            return record(Error::not_connected, -ENOTCONN);
        }
        if (!volumeBackend.callbacks_registered)
        {
            const int callback_result = bt_vcp_vol_ctlr_cb_register(&volumeControllerCallbacks);
            if ((callback_result != 0) && (callback_result != -EALREADY))
            {
                bt_conn_unref(native);
                return record(mapNativeError(callback_result), callback_result);
            }
            volumeBackend.callbacks_registered = true;
        }

        ++volumeBackend.generation;
        if (volumeBackend.generation == 0U)
        {
            ++volumeBackend.generation;
        }
        volumeBackend.owner = this;
        volumeBackend.handle = connection;
        volumeBackend.connection = native;
        volumeBackend.controller = nullptr;
        volumeBackend.offset_service = nullptr;
        volumeBackend.input_service = nullptr;
        volumeBackend.pending_generation = volumeBackend.generation;
        volumeBackend.updates = 0U;
        volumeBackend.volume = {};
        volumeBackend.offset = {};
        volumeBackend.input = {};
        atomic_set(&volumeBackend.error, 0);
        atomic_set(&volumeBackend.busy, 1);
        atomic_set(&volumeBackend.step, static_cast<atomic_val_t>(AudioControlStep::discover));
        atomic_set(&volumeBackend.stage, static_cast<atomic_val_t>(AudioControlStage::discovering));

        const int result = bt_vcp_vol_ctlr_discover(native, &volumeBackend.controller);
        if (result != 0)
        {
            volumeBackend.owner = nullptr;
            volumeBackend.connection = nullptr;
            volumeBackend.controller = nullptr;
            atomic_set(&volumeBackend.busy, 0);
            atomic_set(&volumeBackend.error, result);
            atomic_set(&volumeBackend.stage, static_cast<atomic_val_t>(AudioControlStage::failed));
            bt_conn_unref(native);
            return record(mapNativeError(result), result);
        }

        started_ = true;
        generation_ = volumeBackend.generation;
        return record(Error::none);
    }

    void VolumeController::poll() noexcept
    {
        if (!started_ || !ownsVolumeController(this, generation_))
        {
            return;
        }
        struct bt_conn *current = internal::referenceConnection(volumeBackend.handle);
        if (current == nullptr)
        {
            volumeBackend.controller = nullptr;
            volumeBackend.offset_service = nullptr;
            volumeBackend.input_service = nullptr;
            atomic_set(&volumeBackend.error, -ENOTCONN);
            atomic_set(&volumeBackend.busy, 0);
            atomic_set(&volumeBackend.stage,
                       static_cast<atomic_val_t>(AudioControlStage::disconnected));
            return;
        }
        bt_conn_unref(current);
    }

    Error VolumeController::end() noexcept
    {
        if (!started_)
        {
            return record(Error::not_started);
        }
        if (ownsVolumeController(this, generation_))
        {
            struct bt_conn *active = internal::referenceConnection(volumeBackend.handle);
            volumeBackend.retired_connection = active != nullptr;
            if (active != nullptr)
            {
                bt_conn_unref(active);
            }
            volumeBackend.owner = nullptr;
            ++volumeBackend.generation;
            volumeBackend.pending_generation = 0U;
            volumeBackend.controller = nullptr;
            volumeBackend.offset_service = nullptr;
            volumeBackend.input_service = nullptr;
            atomic_set(&volumeBackend.busy, 0);
            atomic_set(&volumeBackend.stage, static_cast<atomic_val_t>(AudioControlStage::idle));
            if (volumeBackend.connection != nullptr)
            {
                bt_conn_unref(volumeBackend.connection);
                volumeBackend.connection = nullptr;
            }
        }
        started_ = false;
        return record(Error::none);
    }

#define NUCODE_VOLUME_CONTROLLER_REQUEST(step_value, expression, immediate)                        \
    do                                                                                             \
    {                                                                                              \
        if (!ownsVolumeController(this, generation_))                                              \
        {                                                                                          \
            return record(Error::not_started);                                                     \
        }                                                                                          \
        if (stage() == AudioControlStage::disconnected)                                            \
        {                                                                                          \
            return record(Error::not_connected, -ENOTCONN);                                        \
        }                                                                                          \
        if (!ready() || !atomic_cas(&volumeBackend.busy, 0, 1))                                    \
        {                                                                                          \
            return record(Error::busy, -EBUSY);                                                    \
        }                                                                                          \
        volumeBackend.pending_generation = generation_;                                            \
        atomic_set(&volumeBackend.step, static_cast<atomic_val_t>(AudioControlStep::step_value));  \
        atomic_set(&volumeBackend.stage, static_cast<atomic_val_t>(AudioControlStage::operating)); \
        atomic_set(&volumeBackend.error, 0);                                                       \
        const int result = (expression);                                                           \
        if ((result != 0) || (immediate))                                                          \
        {                                                                                          \
            finishVolumeOperation(result);                                                         \
        }                                                                                          \
        return record(mapNativeError(result), result == 0 ? 0 : result);                           \
    } while (false)

    Error VolumeController::readVolume() noexcept
    {
        NUCODE_VOLUME_CONTROLLER_REQUEST(
            read_volume, bt_vcp_vol_ctlr_read_state(volumeBackend.controller), false);
    }

    Error VolumeController::setVolume(std::uint8_t volume) noexcept
    {
        NUCODE_VOLUME_CONTROLLER_REQUEST(
            set_volume, bt_vcp_vol_ctlr_set_vol(volumeBackend.controller, volume), false);
    }

    Error VolumeController::volumeUp() noexcept
    {
        NUCODE_VOLUME_CONTROLLER_REQUEST(volume_up,
                                         bt_vcp_vol_ctlr_vol_up(volumeBackend.controller), false);
    }

    Error VolumeController::volumeDown() noexcept
    {
        NUCODE_VOLUME_CONTROLLER_REQUEST(volume_down,
                                         bt_vcp_vol_ctlr_vol_down(volumeBackend.controller), false);
    }

    Error VolumeController::mute() noexcept
    {
        NUCODE_VOLUME_CONTROLLER_REQUEST(mute_volume,
                                         bt_vcp_vol_ctlr_mute(volumeBackend.controller), false);
    }

    Error VolumeController::unmute() noexcept
    {
        NUCODE_VOLUME_CONTROLLER_REQUEST(unmute_volume,
                                         bt_vcp_vol_ctlr_unmute(volumeBackend.controller), false);
    }

    Error VolumeController::readOffset() noexcept
    {
        NUCODE_VOLUME_CONTROLLER_REQUEST(read_offset,
                                         bt_vocs_state_get(volumeBackend.offset_service), false);
    }

    Error VolumeController::setOffset(std::int16_t offset) noexcept
    {
        if ((offset < BT_VOCS_MIN_OFFSET) || (offset > BT_VOCS_MAX_OFFSET))
        {
            return record(Error::invalid_argument);
        }
        NUCODE_VOLUME_CONTROLLER_REQUEST(
            set_offset, bt_vocs_state_set(volumeBackend.offset_service, offset), false);
    }

    Error VolumeController::setOutputLocation(std::uint32_t location) noexcept
    {
        NUCODE_VOLUME_CONTROLLER_REQUEST(
            set_output_location, bt_vocs_location_set(volumeBackend.offset_service, location),
            true);
    }

    Error VolumeController::setOutputDescription(const char *description) noexcept
    {
        if (!validDescription(description))
        {
            return record(Error::invalid_argument);
        }
        NUCODE_VOLUME_CONTROLLER_REQUEST(
            set_output_description,
            bt_vocs_description_set(volumeBackend.offset_service, description), true);
    }

    Error VolumeController::readInput() noexcept
    {
        NUCODE_VOLUME_CONTROLLER_REQUEST(read_input, bt_aics_state_get(volumeBackend.input_service),
                                         false);
    }

    Error VolumeController::setInputGain(std::int8_t gain) noexcept
    {
        if ((gain < volumeBackend.input.minimum_gain) || (gain > volumeBackend.input.maximum_gain))
        {
            return record(Error::invalid_argument);
        }
        NUCODE_VOLUME_CONTROLLER_REQUEST(
            set_input_gain, bt_aics_gain_set(volumeBackend.input_service, gain), false);
    }

    Error VolumeController::muteInput() noexcept
    {
        NUCODE_VOLUME_CONTROLLER_REQUEST(mute_input, bt_aics_mute(volumeBackend.input_service),
                                         false);
    }

    Error VolumeController::unmuteInput() noexcept
    {
        NUCODE_VOLUME_CONTROLLER_REQUEST(unmute_input, bt_aics_unmute(volumeBackend.input_service),
                                         false);
    }

    Error VolumeController::setInputMode(AudioInputMode mode) noexcept
    {
        if (!writableMode(mode))
        {
            return record(Error::invalid_argument);
        }
        if (mode == AudioInputMode::manual)
        {
            NUCODE_VOLUME_CONTROLLER_REQUEST(
                set_input_mode, bt_aics_manual_gain_set(volumeBackend.input_service), false);
        }
        NUCODE_VOLUME_CONTROLLER_REQUEST(
            set_input_mode, bt_aics_automatic_gain_set(volumeBackend.input_service), false);
    }

    Error VolumeController::setInputDescription(const char *description) noexcept
    {
        if (!validDescription(description))
        {
            return record(Error::invalid_argument);
        }
        NUCODE_VOLUME_CONTROLLER_REQUEST(
            set_input_description,
            bt_aics_description_set(volumeBackend.input_service, description), true);
    }

#undef NUCODE_VOLUME_CONTROLLER_REQUEST

    bool VolumeController::ready() const noexcept
    {
        return started_ && ownsVolumeController(this, generation_) &&
               (stage() == AudioControlStage::ready) && (volumeBackend.controller != nullptr) &&
               (volumeBackend.offset_service != nullptr) &&
               (volumeBackend.input_service != nullptr);
    }

    bool VolumeController::busy() const noexcept
    {
        return started_ && ownsVolumeController(this, generation_) &&
               atomic_get(&volumeBackend.busy);
    }

    AudioControlStage VolumeController::stage() const noexcept
    {
        return ownsVolumeController(this, generation_)
                   ? static_cast<AudioControlStage>(atomic_get(&volumeBackend.stage))
                   : AudioControlStage::idle;
    }

    AudioControlStep VolumeController::lastStep() const noexcept
    {
        return ownsVolumeController(this, generation_)
                   ? static_cast<AudioControlStep>(atomic_get(&volumeBackend.step))
                   : AudioControlStep::none;
    }

    VolumeState VolumeController::state() const noexcept
    {
        return ownsVolumeController(this, generation_) ? volumeBackend.volume : VolumeState{};
    }

    VolumeOffsetState VolumeController::offsetState() const noexcept
    {
        return ownsVolumeController(this, generation_) ? volumeBackend.offset : VolumeOffsetState{};
    }

    AudioInputState VolumeController::inputState() const noexcept
    {
        return ownsVolumeController(this, generation_) ? volumeBackend.input : AudioInputState{};
    }

    std::uint32_t VolumeController::stateUpdates() const noexcept
    {
        return ownsVolumeController(this, generation_) ? volumeBackend.updates : 0U;
    }

    Error VolumeController::lastError() const noexcept
    {
        const int native = ownsVolumeController(this, generation_)
                               ? static_cast<int>(atomic_get(&volumeBackend.error))
                               : 0;
        return native == 0 ? last_error_ : mapNativeError(native);
    }

    int VolumeController::nativeCode() const noexcept
    {
        const int native = ownsVolumeController(this, generation_)
                               ? static_cast<int>(atomic_get(&volumeBackend.error))
                               : 0;
        return native == 0 ? native_code_ : native;
    }

    Error VolumeController::record(Error error, int native_code) noexcept
    {
        last_error_ = error;
        native_code_ = native_code;
        return error;
    }

#else

#define NUCODE_VOLUME_CONTROLLER_STUB(name, signature)                                             \
    Error VolumeController::name signature noexcept                                                \
    {                                                                                              \
        return record(Error::unsupported);                                                         \
    }
    NUCODE_VOLUME_CONTROLLER_STUB(begin, (const BLEConnectionHandle &))
    void VolumeController::poll() noexcept
    {
    }
    Error VolumeController::end() noexcept
    {
        return record(Error::not_started);
    }
    NUCODE_VOLUME_CONTROLLER_STUB(readVolume, ())
    NUCODE_VOLUME_CONTROLLER_STUB(setVolume, (std::uint8_t))
    NUCODE_VOLUME_CONTROLLER_STUB(volumeUp, ())
    NUCODE_VOLUME_CONTROLLER_STUB(volumeDown, ())
    NUCODE_VOLUME_CONTROLLER_STUB(mute, ())
    NUCODE_VOLUME_CONTROLLER_STUB(unmute, ())
    NUCODE_VOLUME_CONTROLLER_STUB(readOffset, ())
    NUCODE_VOLUME_CONTROLLER_STUB(setOffset, (std::int16_t))
    NUCODE_VOLUME_CONTROLLER_STUB(setOutputLocation, (std::uint32_t))
    NUCODE_VOLUME_CONTROLLER_STUB(setOutputDescription, (const char *))
    NUCODE_VOLUME_CONTROLLER_STUB(readInput, ())
    NUCODE_VOLUME_CONTROLLER_STUB(setInputGain, (std::int8_t))
    NUCODE_VOLUME_CONTROLLER_STUB(muteInput, ())
    NUCODE_VOLUME_CONTROLLER_STUB(unmuteInput, ())
    NUCODE_VOLUME_CONTROLLER_STUB(setInputMode, (AudioInputMode))
    NUCODE_VOLUME_CONTROLLER_STUB(setInputDescription, (const char *))
#undef NUCODE_VOLUME_CONTROLLER_STUB
    bool VolumeController::ready() const noexcept
    {
        return false;
    }
    bool VolumeController::busy() const noexcept
    {
        return false;
    }
    AudioControlStage VolumeController::stage() const noexcept
    {
        return AudioControlStage::idle;
    }
    AudioControlStep VolumeController::lastStep() const noexcept
    {
        return AudioControlStep::none;
    }
    VolumeState VolumeController::state() const noexcept
    {
        return {};
    }
    VolumeOffsetState VolumeController::offsetState() const noexcept
    {
        return {};
    }
    AudioInputState VolumeController::inputState() const noexcept
    {
        return {};
    }
    std::uint32_t VolumeController::stateUpdates() const noexcept
    {
        return 0U;
    }
    Error VolumeController::lastError() const noexcept
    {
        return last_error_;
    }
    int VolumeController::nativeCode() const noexcept
    {
        return native_code_;
    }
    Error VolumeController::record(Error error, int native_code) noexcept
    {
        last_error_ = error;
        native_code_ = native_code;
        return error;
    }

#endif

#if defined(CONFIG_BT_MICP_MIC_CTLR) && (CONFIG_BT_MICP_MIC_CTLR_MAX_AICS_INST == 1)

    namespace
    {
        /** @brief 한 연결에 결합한 MICP/AICS client 상태입니다. */
        struct MicrophoneControllerBackend
        {
            MicrophoneController *owner = nullptr;
            BLEConnectionHandle handle = {};
            struct bt_conn *connection = nullptr;
            struct bt_micp_mic_ctlr *controller = nullptr;
            struct bt_aics *input_service = nullptr;
            std::uint32_t generation = 0U;
            std::uint32_t pending_generation = 0U;
            std::uint32_t updates = 0U;
            bool callbacks_registered = false;
            bool retired_connection = false;
            MicrophoneState microphone = {};
            AudioInputState input = {};
            atomic_t stage = ATOMIC_INIT(static_cast<atomic_val_t>(AudioControlStage::idle));
            atomic_t step = ATOMIC_INIT(static_cast<atomic_val_t>(AudioControlStep::none));
            atomic_t busy = ATOMIC_INIT(0);
            atomic_t error = ATOMIC_INIT(0);
        };

        MicrophoneControllerBackend microphoneControllerBackend;

        /** @brief 이전 callback이 남을 수 있는 active 연결의 재소유를 차단합니다. */
        bool retiredMicrophoneConnectionActive() noexcept
        {
            if (!microphoneControllerBackend.retired_connection)
            {
                return false;
            }
            struct bt_conn *connection =
                internal::referenceConnection(microphoneControllerBackend.handle);
            if (connection == nullptr)
            {
                microphoneControllerBackend.retired_connection = false;
                microphoneControllerBackend.controller = nullptr;
                microphoneControllerBackend.input_service = nullptr;
                return false;
            }
            bt_conn_unref(connection);
            return true;
        }

        /** @brief MICP callback instance가 현재 active 연결에 속하는지 확인합니다. */
        bool currentMicrophoneController(struct bt_micp_mic_ctlr *controller) noexcept
        {
            if ((microphoneControllerBackend.owner == nullptr) || (controller == nullptr) ||
                (controller != microphoneControllerBackend.controller) ||
                (microphoneControllerBackend.connection == nullptr))
            {
                return false;
            }
            struct bt_conn *connection = nullptr;
            return (bt_micp_mic_ctlr_conn_get(controller, &connection) == 0) &&
                   (connection == microphoneControllerBackend.connection) &&
                   internal::activeConnection(connection);
        }

        /** @brief MICP 포함 AICS callback이 현재 active 연결에 속하는지 확인합니다. */
        bool currentMicrophoneInput(struct bt_aics *instance) noexcept
        {
            if ((microphoneControllerBackend.owner == nullptr) || (instance == nullptr) ||
                (instance != microphoneControllerBackend.input_service) ||
                (microphoneControllerBackend.connection == nullptr))
            {
                return false;
            }
            struct bt_conn *connection = nullptr;
            return (bt_aics_client_conn_get(instance, &connection) == 0) &&
                   (connection == microphoneControllerBackend.connection) &&
                   internal::activeConnection(connection);
        }

        /** @brief 현재 MICP pending 작업을 종료합니다. */
        void finishMicrophoneOperation(int error) noexcept
        {
            if ((microphoneControllerBackend.owner == nullptr) ||
                (microphoneControllerBackend.pending_generation !=
                 microphoneControllerBackend.generation))
            {
                return;
            }
            atomic_set(&microphoneControllerBackend.error, error);
            atomic_set(&microphoneControllerBackend.busy, 0);
            atomic_set(&microphoneControllerBackend.stage,
                       static_cast<atomic_val_t>(AudioControlStage::ready));
        }

        /** @brief MICS와 포함 AICS 검색 완료를 검증합니다. */
        void microphoneDiscovered(struct bt_micp_mic_ctlr *controller, int error,
                                  std::uint8_t input_count) noexcept
        {
            if ((microphoneControllerBackend.owner == nullptr) ||
                (controller != microphoneControllerBackend.controller) ||
                (microphoneControllerBackend.pending_generation !=
                 microphoneControllerBackend.generation))
            {
                return;
            }
            if ((error == 0) && (input_count != 1U))
            {
                error = -ENODEV;
            }
            if (error == 0)
            {
                struct bt_micp_included included = {};
                error = bt_micp_mic_ctlr_included_get(controller, &included);
                if ((error == 0) && ((included.aics_cnt != 1U) || (included.aics == nullptr) ||
                                     (included.aics[0] == nullptr)))
                {
                    error = -ENODEV;
                }
                if (error == 0)
                {
                    microphoneControllerBackend.input_service = included.aics[0];
                }
            }
            atomic_set(&microphoneControllerBackend.error, error);
            atomic_set(&microphoneControllerBackend.busy, 0);
            atomic_set(&microphoneControllerBackend.stage,
                       static_cast<atomic_val_t>(error == 0 ? AudioControlStage::ready
                                                            : AudioControlStage::failed));
        }

        /** @brief MICS mute read 또는 notification을 공개 상태에 반영합니다. */
        void microphoneStateChanged(struct bt_micp_mic_ctlr *controller, int error,
                                    std::uint8_t mute) noexcept
        {
            if (!currentMicrophoneController(controller))
            {
                return;
            }
            atomic_set(&microphoneControllerBackend.error, error);
            if (error == 0)
            {
                microphoneControllerBackend.microphone.muted = mute == BT_MICP_MUTE_MUTED;
                microphoneControllerBackend.microphone.mute_disabled =
                    mute == BT_MICP_MUTE_DISABLED;
                ++microphoneControllerBackend.updates;
            }
            if ((static_cast<AudioControlStep>(atomic_get(&microphoneControllerBackend.step)) ==
                 AudioControlStep::read_microphone) &&
                atomic_get(&microphoneControllerBackend.busy))
            {
                finishMicrophoneOperation(error);
            }
        }

        /** @brief MICS control point 작업 완료를 기록합니다. */
        void microphoneWriteComplete(struct bt_micp_mic_ctlr *controller, int error) noexcept
        {
            if (currentMicrophoneController(controller))
            {
                finishMicrophoneOperation(error);
            }
        }

        /** @brief MICP 포함 AICS state를 공개 상태에 반영합니다. */
        void microphoneControllerInputState(struct bt_aics *instance, int error, std::int8_t gain,
                                            std::uint8_t mute, std::uint8_t mode) noexcept
        {
            if (!currentMicrophoneInput(instance))
            {
                return;
            }
            atomic_set(&microphoneControllerBackend.error, error);
            if (error == 0)
            {
                microphoneControllerBackend.input.gain = gain;
                microphoneControllerBackend.input.muted = mute == BT_AICS_STATE_MUTED;
                microphoneControllerBackend.input.mute_disabled =
                    mute == BT_AICS_STATE_MUTE_DISABLED;
                microphoneControllerBackend.input.mode = static_cast<AudioInputMode>(mode);
                ++microphoneControllerBackend.updates;
            }
            if ((static_cast<AudioControlStep>(atomic_get(&microphoneControllerBackend.step)) ==
                 AudioControlStep::read_input) &&
                atomic_get(&microphoneControllerBackend.busy))
            {
                finishMicrophoneOperation(error);
            }
        }

        /** @brief MICP 포함 AICS gain 범위를 공개 상태에 반영합니다. */
        void microphoneControllerGainSetting(struct bt_aics *instance, int error,
                                             std::uint8_t units, std::int8_t minimum,
                                             std::int8_t maximum) noexcept
        {
            if (!currentMicrophoneInput(instance))
            {
                return;
            }
            atomic_set(&microphoneControllerBackend.error, error);
            if (error == 0)
            {
                microphoneControllerBackend.input.units = units;
                microphoneControllerBackend.input.minimum_gain = minimum;
                microphoneControllerBackend.input.maximum_gain = maximum;
                ++microphoneControllerBackend.updates;
            }
        }

        /** @brief MICP 포함 AICS type을 공개 상태에 반영합니다. */
        void microphoneControllerInputType(struct bt_aics *instance, int error,
                                           std::uint8_t type) noexcept
        {
            if (!currentMicrophoneInput(instance))
            {
                return;
            }
            atomic_set(&microphoneControllerBackend.error, error);
            if (error == 0)
            {
                microphoneControllerBackend.input.type = static_cast<AudioInputType>(type);
                ++microphoneControllerBackend.updates;
            }
        }

        /** @brief MICP 포함 AICS active 상태를 공개 상태에 반영합니다. */
        void microphoneControllerInputStatus(struct bt_aics *instance, int error,
                                             bool active) noexcept
        {
            if (!currentMicrophoneInput(instance))
            {
                return;
            }
            atomic_set(&microphoneControllerBackend.error, error);
            if (error == 0)
            {
                microphoneControllerBackend.input.active = active;
                ++microphoneControllerBackend.updates;
            }
        }

        /** @brief MICP 포함 AICS 설명 변경 결과를 기록합니다. */
        void microphoneControllerInputDescription(struct bt_aics *instance, int error,
                                                  char *) noexcept
        {
            if (!currentMicrophoneInput(instance))
            {
                return;
            }
            atomic_set(&microphoneControllerBackend.error, error);
            if (error == 0)
            {
                ++microphoneControllerBackend.updates;
            }
        }

        /** @brief MICP 포함 AICS control point 작업 완료를 기록합니다. */
        void microphoneControllerInputWrite(struct bt_aics *instance, int error) noexcept
        {
            if (currentMicrophoneInput(instance))
            {
                finishMicrophoneOperation(error);
            }
        }

        struct bt_micp_mic_ctlr_cb microphoneControllerCallbacks = {
            .mute = microphoneStateChanged,
            .discover = microphoneDiscovered,
            .mute_written = microphoneWriteComplete,
            .unmute_written = microphoneWriteComplete,
            .aics_cb =
                {
                    .state = microphoneControllerInputState,
                    .gain_setting = microphoneControllerGainSetting,
                    .type = microphoneControllerInputType,
                    .status = microphoneControllerInputStatus,
                    .description = microphoneControllerInputDescription,
                    .set_gain = microphoneControllerInputWrite,
                    .unmute = microphoneControllerInputWrite,
                    .mute = microphoneControllerInputWrite,
                    .set_manual_mode = microphoneControllerInputWrite,
                    .set_auto_mode = microphoneControllerInputWrite,
                },
        };

        /** @brief 현재 facade가 MICP controller backend를 소유하는지 확인합니다. */
        bool ownsMicrophoneController(const MicrophoneController *owner,
                                      std::uint32_t generation) noexcept
        {
            return (microphoneControllerBackend.owner == owner) &&
                   (microphoneControllerBackend.generation == generation);
        }
    } // namespace

    Error MicrophoneController::begin(const BLEConnectionHandle &connection) noexcept
    {
        if (started_)
        {
            return record(Error::already_started);
        }
        if (microphoneControllerBackend.owner != nullptr)
        {
            return record(Error::busy);
        }
        if (retiredMicrophoneConnectionActive())
        {
            return record(Error::busy, -EBUSY);
        }

        struct bt_conn *native = internal::referenceConnection(connection);
        if (native == nullptr)
        {
            return record(Error::not_connected, -ENOTCONN);
        }
        if (!microphoneControllerBackend.callbacks_registered)
        {
            const int callback_result =
                bt_micp_mic_ctlr_cb_register(&microphoneControllerCallbacks);
            if ((callback_result != 0) && (callback_result != -EALREADY))
            {
                bt_conn_unref(native);
                return record(mapNativeError(callback_result), callback_result);
            }
            microphoneControllerBackend.callbacks_registered = true;
        }

        ++microphoneControllerBackend.generation;
        if (microphoneControllerBackend.generation == 0U)
        {
            ++microphoneControllerBackend.generation;
        }
        microphoneControllerBackend.owner = this;
        microphoneControllerBackend.handle = connection;
        microphoneControllerBackend.connection = native;
        microphoneControllerBackend.controller = nullptr;
        microphoneControllerBackend.input_service = nullptr;
        microphoneControllerBackend.pending_generation = microphoneControllerBackend.generation;
        microphoneControllerBackend.updates = 0U;
        microphoneControllerBackend.microphone = {};
        microphoneControllerBackend.input = {};
        atomic_set(&microphoneControllerBackend.error, 0);
        atomic_set(&microphoneControllerBackend.busy, 1);
        atomic_set(&microphoneControllerBackend.step,
                   static_cast<atomic_val_t>(AudioControlStep::discover));
        atomic_set(&microphoneControllerBackend.stage,
                   static_cast<atomic_val_t>(AudioControlStage::discovering));

        const int result =
            bt_micp_mic_ctlr_discover(native, &microphoneControllerBackend.controller);
        if (result != 0)
        {
            microphoneControllerBackend.owner = nullptr;
            microphoneControllerBackend.connection = nullptr;
            microphoneControllerBackend.controller = nullptr;
            atomic_set(&microphoneControllerBackend.busy, 0);
            atomic_set(&microphoneControllerBackend.error, result);
            atomic_set(&microphoneControllerBackend.stage,
                       static_cast<atomic_val_t>(AudioControlStage::failed));
            bt_conn_unref(native);
            return record(mapNativeError(result), result);
        }

        started_ = true;
        generation_ = microphoneControllerBackend.generation;
        return record(Error::none);
    }

    void MicrophoneController::poll() noexcept
    {
        if (!started_ || !ownsMicrophoneController(this, generation_))
        {
            return;
        }
        struct bt_conn *current = internal::referenceConnection(microphoneControllerBackend.handle);
        if (current == nullptr)
        {
            microphoneControllerBackend.controller = nullptr;
            microphoneControllerBackend.input_service = nullptr;
            atomic_set(&microphoneControllerBackend.error, -ENOTCONN);
            atomic_set(&microphoneControllerBackend.busy, 0);
            atomic_set(&microphoneControllerBackend.stage,
                       static_cast<atomic_val_t>(AudioControlStage::disconnected));
            return;
        }
        bt_conn_unref(current);
    }

    Error MicrophoneController::end() noexcept
    {
        if (!started_)
        {
            return record(Error::not_started);
        }
        if (ownsMicrophoneController(this, generation_))
        {
            struct bt_conn *active =
                internal::referenceConnection(microphoneControllerBackend.handle);
            microphoneControllerBackend.retired_connection = active != nullptr;
            if (active != nullptr)
            {
                bt_conn_unref(active);
            }
            microphoneControllerBackend.owner = nullptr;
            ++microphoneControllerBackend.generation;
            microphoneControllerBackend.pending_generation = 0U;
            microphoneControllerBackend.controller = nullptr;
            microphoneControllerBackend.input_service = nullptr;
            atomic_set(&microphoneControllerBackend.busy, 0);
            atomic_set(&microphoneControllerBackend.stage,
                       static_cast<atomic_val_t>(AudioControlStage::idle));
            if (microphoneControllerBackend.connection != nullptr)
            {
                bt_conn_unref(microphoneControllerBackend.connection);
                microphoneControllerBackend.connection = nullptr;
            }
        }
        started_ = false;
        return record(Error::none);
    }

#define NUCODE_MIC_CONTROLLER_REQUEST(step_value, expression, immediate)                           \
    do                                                                                             \
    {                                                                                              \
        if (!ownsMicrophoneController(this, generation_))                                          \
        {                                                                                          \
            return record(Error::not_started);                                                     \
        }                                                                                          \
        if (stage() == AudioControlStage::disconnected)                                            \
        {                                                                                          \
            return record(Error::not_connected, -ENOTCONN);                                        \
        }                                                                                          \
        if (!ready() || !atomic_cas(&microphoneControllerBackend.busy, 0, 1))                      \
        {                                                                                          \
            return record(Error::busy, -EBUSY);                                                    \
        }                                                                                          \
        microphoneControllerBackend.pending_generation = generation_;                              \
        atomic_set(&microphoneControllerBackend.step,                                              \
                   static_cast<atomic_val_t>(AudioControlStep::step_value));                       \
        atomic_set(&microphoneControllerBackend.stage,                                             \
                   static_cast<atomic_val_t>(AudioControlStage::operating));                       \
        atomic_set(&microphoneControllerBackend.error, 0);                                         \
        const int result = (expression);                                                           \
        if ((result != 0) || (immediate))                                                          \
        {                                                                                          \
            finishMicrophoneOperation(result);                                                     \
        }                                                                                          \
        return record(mapNativeError(result), result == 0 ? 0 : result);                           \
    } while (false)

    Error MicrophoneController::readMicrophone() noexcept
    {
        NUCODE_MIC_CONTROLLER_REQUEST(
            read_microphone, bt_micp_mic_ctlr_mute_get(microphoneControllerBackend.controller),
            false);
    }

    Error MicrophoneController::mute() noexcept
    {
        NUCODE_MIC_CONTROLLER_REQUEST(
            mute_microphone, bt_micp_mic_ctlr_mute(microphoneControllerBackend.controller), false);
    }

    Error MicrophoneController::unmute() noexcept
    {
        NUCODE_MIC_CONTROLLER_REQUEST(
            unmute_microphone, bt_micp_mic_ctlr_unmute(microphoneControllerBackend.controller),
            false);
    }

    Error MicrophoneController::readInput() noexcept
    {
        NUCODE_MIC_CONTROLLER_REQUEST(
            read_input, bt_aics_state_get(microphoneControllerBackend.input_service), false);
    }

    Error MicrophoneController::setInputGain(std::int8_t gain) noexcept
    {
        if ((gain < microphoneControllerBackend.input.minimum_gain) ||
            (gain > microphoneControllerBackend.input.maximum_gain))
        {
            return record(Error::invalid_argument);
        }
        NUCODE_MIC_CONTROLLER_REQUEST(
            set_input_gain, bt_aics_gain_set(microphoneControllerBackend.input_service, gain),
            false);
    }

    Error MicrophoneController::muteInput() noexcept
    {
        NUCODE_MIC_CONTROLLER_REQUEST(
            mute_input, bt_aics_mute(microphoneControllerBackend.input_service), false);
    }

    Error MicrophoneController::unmuteInput() noexcept
    {
        NUCODE_MIC_CONTROLLER_REQUEST(
            unmute_input, bt_aics_unmute(microphoneControllerBackend.input_service), false);
    }

    Error MicrophoneController::setInputMode(AudioInputMode mode) noexcept
    {
        if (!writableMode(mode))
        {
            return record(Error::invalid_argument);
        }
        if (mode == AudioInputMode::manual)
        {
            NUCODE_MIC_CONTROLLER_REQUEST(
                set_input_mode, bt_aics_manual_gain_set(microphoneControllerBackend.input_service),
                false);
        }
        NUCODE_MIC_CONTROLLER_REQUEST(
            set_input_mode, bt_aics_automatic_gain_set(microphoneControllerBackend.input_service),
            false);
    }

    Error MicrophoneController::setInputDescription(const char *description) noexcept
    {
        if (!validDescription(description))
        {
            return record(Error::invalid_argument);
        }
        NUCODE_MIC_CONTROLLER_REQUEST(
            set_input_description,
            bt_aics_description_set(microphoneControllerBackend.input_service, description), true);
    }

#undef NUCODE_MIC_CONTROLLER_REQUEST

    bool MicrophoneController::ready() const noexcept
    {
        return started_ && ownsMicrophoneController(this, generation_) &&
               (stage() == AudioControlStage::ready) &&
               (microphoneControllerBackend.controller != nullptr) &&
               (microphoneControllerBackend.input_service != nullptr);
    }

    bool MicrophoneController::busy() const noexcept
    {
        return started_ && ownsMicrophoneController(this, generation_) &&
               atomic_get(&microphoneControllerBackend.busy);
    }

    AudioControlStage MicrophoneController::stage() const noexcept
    {
        return ownsMicrophoneController(this, generation_)
                   ? static_cast<AudioControlStage>(atomic_get(&microphoneControllerBackend.stage))
                   : AudioControlStage::idle;
    }

    AudioControlStep MicrophoneController::lastStep() const noexcept
    {
        return ownsMicrophoneController(this, generation_)
                   ? static_cast<AudioControlStep>(atomic_get(&microphoneControllerBackend.step))
                   : AudioControlStep::none;
    }

    MicrophoneState MicrophoneController::state() const noexcept
    {
        return ownsMicrophoneController(this, generation_) ? microphoneControllerBackend.microphone
                                                           : MicrophoneState{};
    }

    AudioInputState MicrophoneController::inputState() const noexcept
    {
        return ownsMicrophoneController(this, generation_) ? microphoneControllerBackend.input
                                                           : AudioInputState{};
    }

    std::uint32_t MicrophoneController::stateUpdates() const noexcept
    {
        return ownsMicrophoneController(this, generation_) ? microphoneControllerBackend.updates
                                                           : 0U;
    }

    Error MicrophoneController::lastError() const noexcept
    {
        const int native = ownsMicrophoneController(this, generation_)
                               ? static_cast<int>(atomic_get(&microphoneControllerBackend.error))
                               : 0;
        return native == 0 ? last_error_ : mapNativeError(native);
    }

    int MicrophoneController::nativeCode() const noexcept
    {
        const int native = ownsMicrophoneController(this, generation_)
                               ? static_cast<int>(atomic_get(&microphoneControllerBackend.error))
                               : 0;
        return native == 0 ? native_code_ : native;
    }

    Error MicrophoneController::record(Error error, int native_code) noexcept
    {
        last_error_ = error;
        native_code_ = native_code;
        return error;
    }

#else

#define NUCODE_MIC_CONTROLLER_STUB(name, signature)                                                \
    Error MicrophoneController::name signature noexcept                                            \
    {                                                                                              \
        return record(Error::unsupported);                                                         \
    }
    NUCODE_MIC_CONTROLLER_STUB(begin, (const BLEConnectionHandle &))
    void MicrophoneController::poll() noexcept
    {
    }
    Error MicrophoneController::end() noexcept
    {
        return record(Error::not_started);
    }
    NUCODE_MIC_CONTROLLER_STUB(readMicrophone, ())
    NUCODE_MIC_CONTROLLER_STUB(mute, ())
    NUCODE_MIC_CONTROLLER_STUB(unmute, ())
    NUCODE_MIC_CONTROLLER_STUB(readInput, ())
    NUCODE_MIC_CONTROLLER_STUB(setInputGain, (std::int8_t))
    NUCODE_MIC_CONTROLLER_STUB(muteInput, ())
    NUCODE_MIC_CONTROLLER_STUB(unmuteInput, ())
    NUCODE_MIC_CONTROLLER_STUB(setInputMode, (AudioInputMode))
    NUCODE_MIC_CONTROLLER_STUB(setInputDescription, (const char *))
#undef NUCODE_MIC_CONTROLLER_STUB
    bool MicrophoneController::ready() const noexcept
    {
        return false;
    }
    bool MicrophoneController::busy() const noexcept
    {
        return false;
    }
    AudioControlStage MicrophoneController::stage() const noexcept
    {
        return AudioControlStage::idle;
    }
    AudioControlStep MicrophoneController::lastStep() const noexcept
    {
        return AudioControlStep::none;
    }
    MicrophoneState MicrophoneController::state() const noexcept
    {
        return {};
    }
    AudioInputState MicrophoneController::inputState() const noexcept
    {
        return {};
    }
    std::uint32_t MicrophoneController::stateUpdates() const noexcept
    {
        return 0U;
    }
    Error MicrophoneController::lastError() const noexcept
    {
        return last_error_;
    }
    int MicrophoneController::nativeCode() const noexcept
    {
        return native_code_;
    }
    Error MicrophoneController::record(Error error, int native_code) noexcept
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
#define NUCODE_VOLUME_CONTROLLER_FALLBACK(name, signature)                                         \
    Error VolumeController::name signature noexcept                                                \
    {                                                                                              \
        return record(Error::unsupported);                                                         \
    }
    NUCODE_VOLUME_CONTROLLER_FALLBACK(begin, (const BLEConnectionHandle &))
    void VolumeController::poll() noexcept
    {
    }
    Error VolumeController::end() noexcept
    {
        return record(Error::not_started);
    }
    NUCODE_VOLUME_CONTROLLER_FALLBACK(readVolume, ())
    NUCODE_VOLUME_CONTROLLER_FALLBACK(setVolume, (std::uint8_t))
    NUCODE_VOLUME_CONTROLLER_FALLBACK(volumeUp, ())
    NUCODE_VOLUME_CONTROLLER_FALLBACK(volumeDown, ())
    NUCODE_VOLUME_CONTROLLER_FALLBACK(mute, ())
    NUCODE_VOLUME_CONTROLLER_FALLBACK(unmute, ())
    NUCODE_VOLUME_CONTROLLER_FALLBACK(readOffset, ())
    NUCODE_VOLUME_CONTROLLER_FALLBACK(setOffset, (std::int16_t))
    NUCODE_VOLUME_CONTROLLER_FALLBACK(setOutputLocation, (std::uint32_t))
    NUCODE_VOLUME_CONTROLLER_FALLBACK(setOutputDescription, (const char *))
    NUCODE_VOLUME_CONTROLLER_FALLBACK(readInput, ())
    NUCODE_VOLUME_CONTROLLER_FALLBACK(setInputGain, (std::int8_t))
    NUCODE_VOLUME_CONTROLLER_FALLBACK(muteInput, ())
    NUCODE_VOLUME_CONTROLLER_FALLBACK(unmuteInput, ())
    NUCODE_VOLUME_CONTROLLER_FALLBACK(setInputMode, (AudioInputMode))
    NUCODE_VOLUME_CONTROLLER_FALLBACK(setInputDescription, (const char *))
#undef NUCODE_VOLUME_CONTROLLER_FALLBACK
    bool VolumeController::ready() const noexcept
    {
        return false;
    }
    bool VolumeController::busy() const noexcept
    {
        return false;
    }
    AudioControlStage VolumeController::stage() const noexcept
    {
        return AudioControlStage::idle;
    }
    AudioControlStep VolumeController::lastStep() const noexcept
    {
        return AudioControlStep::none;
    }
    VolumeState VolumeController::state() const noexcept
    {
        return {};
    }
    VolumeOffsetState VolumeController::offsetState() const noexcept
    {
        return {};
    }
    AudioInputState VolumeController::inputState() const noexcept
    {
        return {};
    }
    std::uint32_t VolumeController::stateUpdates() const noexcept
    {
        return 0U;
    }
    Error VolumeController::lastError() const noexcept
    {
        return last_error_;
    }
    int VolumeController::nativeCode() const noexcept
    {
        return native_code_;
    }
    Error VolumeController::record(Error error, int native_code) noexcept
    {
        last_error_ = error;
        native_code_ = native_code;
        return error;
    }

#define NUCODE_MIC_CONTROLLER_FALLBACK(name, signature)                                            \
    Error MicrophoneController::name signature noexcept                                            \
    {                                                                                              \
        return record(Error::unsupported);                                                         \
    }
    NUCODE_MIC_CONTROLLER_FALLBACK(begin, (const BLEConnectionHandle &))
    void MicrophoneController::poll() noexcept
    {
    }
    Error MicrophoneController::end() noexcept
    {
        return record(Error::not_started);
    }
    NUCODE_MIC_CONTROLLER_FALLBACK(readMicrophone, ())
    NUCODE_MIC_CONTROLLER_FALLBACK(mute, ())
    NUCODE_MIC_CONTROLLER_FALLBACK(unmute, ())
    NUCODE_MIC_CONTROLLER_FALLBACK(readInput, ())
    NUCODE_MIC_CONTROLLER_FALLBACK(setInputGain, (std::int8_t))
    NUCODE_MIC_CONTROLLER_FALLBACK(muteInput, ())
    NUCODE_MIC_CONTROLLER_FALLBACK(unmuteInput, ())
    NUCODE_MIC_CONTROLLER_FALLBACK(setInputMode, (AudioInputMode))
    NUCODE_MIC_CONTROLLER_FALLBACK(setInputDescription, (const char *))
#undef NUCODE_MIC_CONTROLLER_FALLBACK
    bool MicrophoneController::ready() const noexcept
    {
        return false;
    }
    bool MicrophoneController::busy() const noexcept
    {
        return false;
    }
    AudioControlStage MicrophoneController::stage() const noexcept
    {
        return AudioControlStage::idle;
    }
    AudioControlStep MicrophoneController::lastStep() const noexcept
    {
        return AudioControlStep::none;
    }
    MicrophoneState MicrophoneController::state() const noexcept
    {
        return {};
    }
    AudioInputState MicrophoneController::inputState() const noexcept
    {
        return {};
    }
    std::uint32_t MicrophoneController::stateUpdates() const noexcept
    {
        return 0U;
    }
    Error MicrophoneController::lastError() const noexcept
    {
        return last_error_;
    }
    int MicrophoneController::nativeCode() const noexcept
    {
        return native_code_;
    }
    Error MicrophoneController::record(Error error, int native_code) noexcept
    {
        last_error_ = error;
        native_code_ = native_code;
        return error;
    }
} // namespace nucode::ble::audio

#endif
