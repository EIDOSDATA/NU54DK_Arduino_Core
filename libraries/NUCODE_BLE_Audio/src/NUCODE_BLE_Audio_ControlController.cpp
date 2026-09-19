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
#include <zephyr/kernel.h>
#include <zephyr/sys/atomic.h>

#include <errno.h>
#include <string.h>

namespace nucode::ble::audio
{
    namespace
    {
        /** @brief VCP discovery 뒤 실제 remote snapshot을 채우는 순서입니다. */
        enum class VolumeBootstrapStep : std::uint8_t
        {
            none,
            volume_state,
            volume_flags,
            output_state,
            output_location,
            input_state,
            input_gain_setting,
            input_type,
            input_status,
            complete,
        };

        /** @brief MICP discovery 뒤 실제 remote snapshot을 채우는 순서입니다. */
        enum class MicrophoneBootstrapStep : std::uint8_t
        {
            none,
            microphone_state,
            input_state,
            input_gain_setting,
            input_type,
            input_status,
            complete,
        };

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

        /** @brief 원격 write에 사용할 bounded UTF-8 설명인지 확인합니다. */
        bool validDescription(const char *description) noexcept
        {
            if (description == nullptr)
            {
                return false;
            }
            const std::size_t length = strnlen(description, maximumDescriptionLength + 1U);
            return (length <= maximumDescriptionLength) && validUtf8(description, length);
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
            VolumeBootstrapStep bootstrap = VolumeBootstrapStep::none;
            VolumeState volume = {};
            VolumeOffsetState offset = {};
            AudioInputState input = {};
            atomic_t stage = ATOMIC_INIT(static_cast<atomic_val_t>(AudioControlStage::idle));
            atomic_t step = ATOMIC_INIT(static_cast<atomic_val_t>(AudioControlStep::none));
            atomic_t busy = ATOMIC_INIT(0);
            atomic_t error = ATOMIC_INIT(0);
        };

        VolumeControllerBackend volumeBackend;
        K_MUTEX_DEFINE(volumeBackendMutex);

        /** @brief 이전 callback이 남을 수 있는 active 연결의 재소유를 차단합니다. */
        bool retiredVolumeConnectionActive() noexcept
        {
            k_mutex_lock(&volumeBackendMutex, K_FOREVER);
            const bool retired = volumeBackend.retired_connection;
            const BLEConnectionHandle handle = volumeBackend.handle;
            k_mutex_unlock(&volumeBackendMutex);
            if (!retired)
            {
                return false;
            }
            struct bt_conn *connection = internal::referenceConnection(handle);
            if (connection == nullptr)
            {
                k_mutex_lock(&volumeBackendMutex, K_FOREVER);
                if (volumeBackend.retired_connection && (volumeBackend.handle == handle))
                {
                    volumeBackend.retired_connection = false;
                    volumeBackend.controller = nullptr;
                    volumeBackend.offset_service = nullptr;
                    volumeBackend.input_service = nullptr;
                }
                k_mutex_unlock(&volumeBackendMutex);
                return false;
            }
            bt_conn_unref(connection);
            return true;
        }

        /** @brief callback instance가 현재 active 연결과 generation에 속하는지 확인합니다. */
        std::uint32_t currentVolumeController(struct bt_vcp_vol_ctlr *controller) noexcept
        {
            k_mutex_lock(&volumeBackendMutex, K_FOREVER);
            if ((volumeBackend.owner == nullptr) || (controller == nullptr) ||
                (controller != volumeBackend.controller) || (volumeBackend.connection == nullptr))
            {
                k_mutex_unlock(&volumeBackendMutex);
                return 0U;
            }
            struct bt_conn *expected_connection = volumeBackend.connection;
            const std::uint32_t generation = volumeBackend.generation;
            k_mutex_unlock(&volumeBackendMutex);
            struct bt_conn *connection = nullptr;
            if ((bt_vcp_vol_ctlr_conn_get(controller, &connection) != 0) ||
                (connection != expected_connection) || !internal::activeConnection(connection))
            {
                return 0U;
            }
            k_mutex_lock(&volumeBackendMutex, K_FOREVER);
            const bool current = (volumeBackend.owner != nullptr) &&
                                 (volumeBackend.controller == controller) &&
                                 (volumeBackend.connection == expected_connection) &&
                                 (volumeBackend.generation == generation);
            k_mutex_unlock(&volumeBackendMutex);
            return current ? generation : 0U;
        }

        /** @brief discovery callback의 controller를 현재 연결에 원자적으로 결합합니다. */
        std::uint32_t currentVolumeDiscovery(struct bt_vcp_vol_ctlr *controller) noexcept
        {
            k_mutex_lock(&volumeBackendMutex, K_FOREVER);
            if ((volumeBackend.owner == nullptr) || (controller == nullptr) ||
                ((volumeBackend.controller != nullptr) &&
                 (volumeBackend.controller != controller)) ||
                (volumeBackend.connection == nullptr) ||
                (static_cast<AudioControlStage>(atomic_get(&volumeBackend.stage)) !=
                 AudioControlStage::discovering))
            {
                k_mutex_unlock(&volumeBackendMutex);
                return 0U;
            }
            struct bt_conn *expected_connection = volumeBackend.connection;
            const std::uint32_t generation = volumeBackend.generation;
            k_mutex_unlock(&volumeBackendMutex);

            struct bt_conn *connection = nullptr;
            if ((bt_vcp_vol_ctlr_conn_get(controller, &connection) != 0) ||
                (connection != expected_connection) || !internal::activeConnection(connection))
            {
                return 0U;
            }
            k_mutex_lock(&volumeBackendMutex, K_FOREVER);
            const bool current = (volumeBackend.owner != nullptr) &&
                                 ((volumeBackend.controller == nullptr) ||
                                  (volumeBackend.controller == controller)) &&
                                 (volumeBackend.connection == expected_connection) &&
                                 (volumeBackend.generation == generation);
            if (current)
            {
                volumeBackend.controller = controller;
            }
            k_mutex_unlock(&volumeBackendMutex);
            return current ? generation : 0U;
        }

        /** @brief VOCS callback instance가 현재 active 연결에 속하는지 확인합니다. */
        std::uint32_t currentOffsetService(struct bt_vocs *instance) noexcept
        {
            k_mutex_lock(&volumeBackendMutex, K_FOREVER);
            if ((volumeBackend.owner == nullptr) || (instance == nullptr) ||
                (instance != volumeBackend.offset_service) || (volumeBackend.connection == nullptr))
            {
                k_mutex_unlock(&volumeBackendMutex);
                return 0U;
            }
            struct bt_conn *expected_connection = volumeBackend.connection;
            const std::uint32_t generation = volumeBackend.generation;
            k_mutex_unlock(&volumeBackendMutex);
            struct bt_conn *connection = nullptr;
            if ((bt_vocs_client_conn_get(instance, &connection) != 0) ||
                (connection != expected_connection) || !internal::activeConnection(connection))
            {
                return 0U;
            }
            k_mutex_lock(&volumeBackendMutex, K_FOREVER);
            const bool current = (volumeBackend.owner != nullptr) &&
                                 (volumeBackend.offset_service == instance) &&
                                 (volumeBackend.connection == expected_connection) &&
                                 (volumeBackend.generation == generation);
            k_mutex_unlock(&volumeBackendMutex);
            return current ? generation : 0U;
        }

        /** @brief AICS callback instance가 현재 active 연결에 속하는지 확인합니다. */
        std::uint32_t currentVolumeInput(struct bt_aics *instance) noexcept
        {
            k_mutex_lock(&volumeBackendMutex, K_FOREVER);
            if ((volumeBackend.owner == nullptr) || (instance == nullptr) ||
                (instance != volumeBackend.input_service) || (volumeBackend.connection == nullptr))
            {
                k_mutex_unlock(&volumeBackendMutex);
                return 0U;
            }
            struct bt_conn *expected_connection = volumeBackend.connection;
            const std::uint32_t generation = volumeBackend.generation;
            k_mutex_unlock(&volumeBackendMutex);
            struct bt_conn *connection = nullptr;
            if ((bt_aics_client_conn_get(instance, &connection) != 0) ||
                (connection != expected_connection) || !internal::activeConnection(connection))
            {
                return 0U;
            }
            k_mutex_lock(&volumeBackendMutex, K_FOREVER);
            const bool current = (volumeBackend.owner != nullptr) &&
                                 (volumeBackend.input_service == instance) &&
                                 (volumeBackend.connection == expected_connection) &&
                                 (volumeBackend.generation == generation);
            k_mutex_unlock(&volumeBackendMutex);
            return current ? generation : 0U;
        }

        /** @brief 현재 pending 작업을 결과와 함께 종료합니다. */
        void finishVolumeOperation(std::uint32_t generation, int error) noexcept
        {
            k_mutex_lock(&volumeBackendMutex, K_FOREVER);
            if ((volumeBackend.owner == nullptr) || (volumeBackend.generation != generation) ||
                (volumeBackend.pending_generation != generation))
            {
                k_mutex_unlock(&volumeBackendMutex);
                return;
            }
            atomic_set(&volumeBackend.error, error);
            atomic_set(&volumeBackend.busy, 0);
            atomic_set(&volumeBackend.stage, static_cast<atomic_val_t>(AudioControlStage::ready));
            k_mutex_unlock(&volumeBackendMutex);
        }

        /** @brief bootstrap read의 즉시 시작 오류를 failed 상태로 고정합니다. */
        void failVolumeBootstrap(std::uint32_t generation, int error) noexcept
        {
            k_mutex_lock(&volumeBackendMutex, K_FOREVER);
            if ((volumeBackend.owner != nullptr) && (volumeBackend.generation == generation) &&
                (static_cast<AudioControlStage>(atomic_get(&volumeBackend.stage)) ==
                 AudioControlStage::discovering))
            {
                atomic_set(&volumeBackend.error, error);
                atomic_set(&volumeBackend.busy, 0);
                atomic_set(&volumeBackend.stage,
                           static_cast<atomic_val_t>(AudioControlStage::failed));
            }
            k_mutex_unlock(&volumeBackendMutex);
        }

        /** @brief 잠금 밖에서 현재 bootstrap read 한 단계를 시작합니다. */
        void startVolumeBootstrap(std::uint32_t generation, VolumeBootstrapStep step) noexcept
        {
            k_mutex_lock(&volumeBackendMutex, K_FOREVER);
            if ((volumeBackend.owner == nullptr) || (volumeBackend.generation != generation) ||
                (volumeBackend.bootstrap != step) ||
                (static_cast<AudioControlStage>(atomic_get(&volumeBackend.stage)) !=
                 AudioControlStage::discovering))
            {
                k_mutex_unlock(&volumeBackendMutex);
                return;
            }
            struct bt_vcp_vol_ctlr *controller = volumeBackend.controller;
            struct bt_vocs *output_service = volumeBackend.offset_service;
            struct bt_aics *input_service = volumeBackend.input_service;
            k_mutex_unlock(&volumeBackendMutex);

            int result = -EINVAL;
            switch (step)
            {
            case VolumeBootstrapStep::volume_state:
                result = bt_vcp_vol_ctlr_read_state(controller);
                break;
            case VolumeBootstrapStep::volume_flags:
                result = bt_vcp_vol_ctlr_read_flags(controller);
                break;
            case VolumeBootstrapStep::output_state:
                result = bt_vocs_state_get(output_service);
                break;
            case VolumeBootstrapStep::output_location:
                result = bt_vocs_location_get(output_service);
                break;
            case VolumeBootstrapStep::input_state:
                result = bt_aics_state_get(input_service);
                break;
            case VolumeBootstrapStep::input_gain_setting:
                result = bt_aics_gain_setting_get(input_service);
                break;
            case VolumeBootstrapStep::input_type:
                result = bt_aics_type_get(input_service);
                break;
            case VolumeBootstrapStep::input_status:
                result = bt_aics_status_get(input_service);
                break;
            default:
                break;
            }
            if (result != 0)
            {
                failVolumeBootstrap(generation, result);
            }
        }

        /** @brief callback 결과를 반영하고 다음 bootstrap read를 예약합니다. */
        void advanceVolumeBootstrap(std::uint32_t generation, VolumeBootstrapStep completed,
                                    int error) noexcept
        {
            VolumeBootstrapStep next = VolumeBootstrapStep::none;
            k_mutex_lock(&volumeBackendMutex, K_FOREVER);
            if ((volumeBackend.owner == nullptr) || (volumeBackend.generation != generation) ||
                (volumeBackend.bootstrap != completed) ||
                (static_cast<AudioControlStage>(atomic_get(&volumeBackend.stage)) !=
                 AudioControlStage::discovering))
            {
                k_mutex_unlock(&volumeBackendMutex);
                return;
            }
            if (error != 0)
            {
                atomic_set(&volumeBackend.error, error);
                atomic_set(&volumeBackend.busy, 0);
                atomic_set(&volumeBackend.stage,
                           static_cast<atomic_val_t>(AudioControlStage::failed));
                k_mutex_unlock(&volumeBackendMutex);
                return;
            }

            next = static_cast<VolumeBootstrapStep>(static_cast<std::uint8_t>(completed) + 1U);
            volumeBackend.bootstrap = next;
            if (next == VolumeBootstrapStep::complete)
            {
                atomic_set(&volumeBackend.error, 0);
                atomic_set(&volumeBackend.busy, 0);
                atomic_set(&volumeBackend.stage,
                           static_cast<atomic_val_t>(AudioControlStage::ready));
            }
            k_mutex_unlock(&volumeBackendMutex);
            if (next != VolumeBootstrapStep::complete)
            {
                startVolumeBootstrap(generation, next);
            }
        }

        /** @brief VCP와 포함 service 검색 완료를 검증합니다. */
        void volumeDiscovered(struct bt_vcp_vol_ctlr *controller, int error,
                              std::uint8_t offset_count, std::uint8_t input_count) noexcept
        {
            const std::uint32_t generation = currentVolumeDiscovery(controller);
            if (generation == 0U)
            {
                return;
            }
            if ((error == 0) && ((offset_count != 1U) || (input_count != 1U)))
            {
                error = -ENODEV;
            }
            struct bt_vcp_included included = {};
            if (error == 0)
            {
                error = bt_vcp_vol_ctlr_included_get(controller, &included);
                if ((error == 0) &&
                    ((included.vocs_cnt != 1U) || (included.aics_cnt != 1U) ||
                     (included.vocs == nullptr) || (included.aics == nullptr) ||
                     (included.vocs[0] == nullptr) || (included.aics[0] == nullptr)))
                {
                    error = -ENODEV;
                }
            }
            k_mutex_lock(&volumeBackendMutex, K_FOREVER);
            if ((volumeBackend.owner == nullptr) || (volumeBackend.generation != generation) ||
                (volumeBackend.pending_generation != generation))
            {
                k_mutex_unlock(&volumeBackendMutex);
                return;
            }
            atomic_set(&volumeBackend.error, error);
            if (error != 0)
            {
                atomic_set(&volumeBackend.busy, 0);
                atomic_set(&volumeBackend.stage,
                           static_cast<atomic_val_t>(AudioControlStage::failed));
                k_mutex_unlock(&volumeBackendMutex);
                return;
            }
            volumeBackend.offset_service = included.vocs[0];
            volumeBackend.input_service = included.aics[0];
            volumeBackend.bootstrap = VolumeBootstrapStep::volume_state;
            k_mutex_unlock(&volumeBackendMutex);
            startVolumeBootstrap(generation, VolumeBootstrapStep::volume_state);
        }

        /** @brief VCS state read 또는 notification을 공개 상태에 반영합니다. */
        void volumeStateChanged(struct bt_vcp_vol_ctlr *controller, int error, std::uint8_t volume,
                                std::uint8_t mute) noexcept
        {
            const std::uint32_t generation = currentVolumeController(controller);
            if (generation == 0U)
            {
                return;
            }
            bool completes_read = false;
            k_mutex_lock(&volumeBackendMutex, K_FOREVER);
            if (volumeBackend.generation != generation)
            {
                k_mutex_unlock(&volumeBackendMutex);
                return;
            }
            atomic_set(&volumeBackend.error, error);
            if (error == 0)
            {
                volumeBackend.volume.volume = volume;
                volumeBackend.volume.muted = mute == BT_VCP_STATE_MUTED;
                ++volumeBackend.updates;
            }
            completes_read = (static_cast<AudioControlStep>(atomic_get(&volumeBackend.step)) ==
                              AudioControlStep::read_volume) &&
                             atomic_get(&volumeBackend.busy);
            k_mutex_unlock(&volumeBackendMutex);
            advanceVolumeBootstrap(generation, VolumeBootstrapStep::volume_state, error);
            if (completes_read)
            {
                finishVolumeOperation(generation, error);
            }
        }

        /** @brief VCS flags read 또는 notification을 공개 상태에 반영합니다. */
        void volumeFlagsChanged(struct bt_vcp_vol_ctlr *controller, int error,
                                std::uint8_t flags) noexcept
        {
            const std::uint32_t generation = currentVolumeController(controller);
            if (generation == 0U)
            {
                return;
            }
            k_mutex_lock(&volumeBackendMutex, K_FOREVER);
            if (volumeBackend.generation != generation)
            {
                k_mutex_unlock(&volumeBackendMutex);
                return;
            }
            atomic_set(&volumeBackend.error, error);
            if (error == 0)
            {
                volumeBackend.volume.flags = flags;
                ++volumeBackend.updates;
            }
            k_mutex_unlock(&volumeBackendMutex);
            advanceVolumeBootstrap(generation, VolumeBootstrapStep::volume_flags, error);
        }

        /** @brief VCS control point 작업 완료를 기록합니다. */
        void volumeWriteComplete(struct bt_vcp_vol_ctlr *controller, int error) noexcept
        {
            const std::uint32_t generation = currentVolumeController(controller);
            if (generation != 0U)
            {
                finishVolumeOperation(generation, error);
            }
        }

        /** @brief VOCS offset read 또는 notification을 공개 상태에 반영합니다. */
        void offsetStateChanged(struct bt_vocs *instance, int error, std::int16_t offset) noexcept
        {
            const std::uint32_t generation = currentOffsetService(instance);
            if (generation == 0U)
            {
                return;
            }
            bool completes_read = false;
            k_mutex_lock(&volumeBackendMutex, K_FOREVER);
            if (volumeBackend.generation != generation)
            {
                k_mutex_unlock(&volumeBackendMutex);
                return;
            }
            atomic_set(&volumeBackend.error, error);
            if (error == 0)
            {
                volumeBackend.offset.offset = offset;
                ++volumeBackend.updates;
            }
            completes_read = (static_cast<AudioControlStep>(atomic_get(&volumeBackend.step)) ==
                              AudioControlStep::read_offset) &&
                             atomic_get(&volumeBackend.busy);
            k_mutex_unlock(&volumeBackendMutex);
            advanceVolumeBootstrap(generation, VolumeBootstrapStep::output_state, error);
            if (completes_read)
            {
                finishVolumeOperation(generation, error);
            }
        }

        /** @brief VOCS location read 또는 notification을 공개 상태에 반영합니다. */
        void offsetLocationChanged(struct bt_vocs *instance, int error,
                                   std::uint32_t location) noexcept
        {
            const std::uint32_t generation = currentOffsetService(instance);
            if (generation == 0U)
            {
                return;
            }
            k_mutex_lock(&volumeBackendMutex, K_FOREVER);
            if (volumeBackend.generation != generation)
            {
                k_mutex_unlock(&volumeBackendMutex);
                return;
            }
            atomic_set(&volumeBackend.error, error);
            if (error == 0)
            {
                volumeBackend.offset.location = location;
                ++volumeBackend.updates;
            }
            k_mutex_unlock(&volumeBackendMutex);
            advanceVolumeBootstrap(generation, VolumeBootstrapStep::output_location, error);
        }

        /** @brief VOCS description read 또는 notification 결과를 기록합니다. */
        void offsetDescriptionChanged(struct bt_vocs *instance, int error, char *) noexcept
        {
            const std::uint32_t generation = currentOffsetService(instance);
            if (generation == 0U)
            {
                return;
            }
            k_mutex_lock(&volumeBackendMutex, K_FOREVER);
            if (volumeBackend.generation != generation)
            {
                k_mutex_unlock(&volumeBackendMutex);
                return;
            }
            atomic_set(&volumeBackend.error, error);
            if (error == 0)
            {
                ++volumeBackend.updates;
            }
            k_mutex_unlock(&volumeBackendMutex);
        }

        /** @brief VOCS control point 작업 완료를 기록합니다. */
        void offsetWriteComplete(struct bt_vocs *instance, int error) noexcept
        {
            const std::uint32_t generation = currentOffsetService(instance);
            if (generation != 0U)
            {
                finishVolumeOperation(generation, error);
            }
        }

        /** @brief VCP 포함 AICS state를 공개 상태에 반영합니다. */
        void volumeInputStateChanged(struct bt_aics *instance, int error, std::int8_t gain,
                                     std::uint8_t mute, std::uint8_t mode) noexcept
        {
            const std::uint32_t generation = currentVolumeInput(instance);
            if (generation == 0U)
            {
                return;
            }
            bool completes_read = false;
            k_mutex_lock(&volumeBackendMutex, K_FOREVER);
            if (volumeBackend.generation != generation)
            {
                k_mutex_unlock(&volumeBackendMutex);
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
            completes_read = (static_cast<AudioControlStep>(atomic_get(&volumeBackend.step)) ==
                              AudioControlStep::read_input) &&
                             atomic_get(&volumeBackend.busy);
            k_mutex_unlock(&volumeBackendMutex);
            advanceVolumeBootstrap(generation, VolumeBootstrapStep::input_state, error);
            if (completes_read)
            {
                finishVolumeOperation(generation, error);
            }
        }

        /** @brief VCP 포함 AICS gain 범위를 공개 상태에 반영합니다. */
        void volumeInputGainSetting(struct bt_aics *instance, int error, std::uint8_t units,
                                    std::int8_t minimum, std::int8_t maximum) noexcept
        {
            const std::uint32_t generation = currentVolumeInput(instance);
            if (generation == 0U)
            {
                return;
            }
            k_mutex_lock(&volumeBackendMutex, K_FOREVER);
            if (volumeBackend.generation != generation)
            {
                k_mutex_unlock(&volumeBackendMutex);
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
            k_mutex_unlock(&volumeBackendMutex);
            advanceVolumeBootstrap(generation, VolumeBootstrapStep::input_gain_setting, error);
        }

        /** @brief VCP 포함 AICS type을 공개 상태에 반영합니다. */
        void volumeInputType(struct bt_aics *instance, int error, std::uint8_t type) noexcept
        {
            const std::uint32_t generation = currentVolumeInput(instance);
            if (generation == 0U)
            {
                return;
            }
            k_mutex_lock(&volumeBackendMutex, K_FOREVER);
            if (volumeBackend.generation != generation)
            {
                k_mutex_unlock(&volumeBackendMutex);
                return;
            }
            atomic_set(&volumeBackend.error, error);
            if (error == 0)
            {
                volumeBackend.input.type = static_cast<AudioInputType>(type);
                ++volumeBackend.updates;
            }
            k_mutex_unlock(&volumeBackendMutex);
            advanceVolumeBootstrap(generation, VolumeBootstrapStep::input_type, error);
        }

        /** @brief VCP 포함 AICS active 상태를 공개 상태에 반영합니다. */
        void volumeInputStatus(struct bt_aics *instance, int error, bool active) noexcept
        {
            const std::uint32_t generation = currentVolumeInput(instance);
            if (generation == 0U)
            {
                return;
            }
            k_mutex_lock(&volumeBackendMutex, K_FOREVER);
            if (volumeBackend.generation != generation)
            {
                k_mutex_unlock(&volumeBackendMutex);
                return;
            }
            atomic_set(&volumeBackend.error, error);
            if (error == 0)
            {
                volumeBackend.input.active = active;
                ++volumeBackend.updates;
            }
            k_mutex_unlock(&volumeBackendMutex);
            advanceVolumeBootstrap(generation, VolumeBootstrapStep::input_status, error);
        }

        /** @brief VCP 포함 AICS 설명 변경 결과를 기록합니다. */
        void volumeInputDescription(struct bt_aics *instance, int error, char *) noexcept
        {
            const std::uint32_t generation = currentVolumeInput(instance);
            if (generation == 0U)
            {
                return;
            }
            k_mutex_lock(&volumeBackendMutex, K_FOREVER);
            if (volumeBackend.generation != generation)
            {
                k_mutex_unlock(&volumeBackendMutex);
                return;
            }
            atomic_set(&volumeBackend.error, error);
            if (error == 0)
            {
                ++volumeBackend.updates;
            }
            k_mutex_unlock(&volumeBackendMutex);
        }

        /** @brief VCP 포함 AICS control point 작업 완료를 기록합니다. */
        void volumeInputWriteComplete(struct bt_aics *instance, int error) noexcept
        {
            const std::uint32_t generation = currentVolumeInput(instance);
            if (generation != 0U)
            {
                finishVolumeOperation(generation, error);
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
        bool ownsVolumeControllerLocked(const VolumeController *owner,
                                        std::uint32_t generation) noexcept
        {
            return (volumeBackend.owner == owner) && (volumeBackend.generation == generation);
        }
    } // namespace

    Error VolumeController::begin(const BLEConnectionHandle &connection) noexcept
    {
        k_mutex_lock(&volumeBackendMutex, K_FOREVER);
        const bool object_started = started_;
        k_mutex_unlock(&volumeBackendMutex);
        if (object_started)
        {
            return record(Error::already_started);
        }
        k_mutex_lock(&volumeBackendMutex, K_FOREVER);
        const bool owner_present = volumeBackend.owner != nullptr;
        const bool callbacks_registered = volumeBackend.callbacks_registered;
        k_mutex_unlock(&volumeBackendMutex);
        if (owner_present)
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
        if (!callbacks_registered)
        {
            const int callback_result = bt_vcp_vol_ctlr_cb_register(&volumeControllerCallbacks);
            if ((callback_result != 0) && (callback_result != -EALREADY))
            {
                bt_conn_unref(native);
                return record(mapNativeError(callback_result), callback_result);
            }
            k_mutex_lock(&volumeBackendMutex, K_FOREVER);
            volumeBackend.callbacks_registered = true;
            k_mutex_unlock(&volumeBackendMutex);
        }

        k_mutex_lock(&volumeBackendMutex, K_FOREVER);
        if (volumeBackend.owner != nullptr)
        {
            k_mutex_unlock(&volumeBackendMutex);
            bt_conn_unref(native);
            return record(Error::busy, -EBUSY);
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
        volumeBackend.bootstrap = VolumeBootstrapStep::none;
        atomic_set(&volumeBackend.error, 0);
        atomic_set(&volumeBackend.busy, 1);
        atomic_set(&volumeBackend.step, static_cast<atomic_val_t>(AudioControlStep::discover));
        atomic_set(&volumeBackend.stage, static_cast<atomic_val_t>(AudioControlStage::discovering));
        const std::uint32_t generation = volumeBackend.generation;
        k_mutex_unlock(&volumeBackendMutex);

        struct bt_vcp_vol_ctlr *controller = nullptr;
        const int result = bt_vcp_vol_ctlr_discover(native, &controller);
        if (result != 0)
        {
            k_mutex_lock(&volumeBackendMutex, K_FOREVER);
            if (ownsVolumeControllerLocked(this, generation))
            {
                volumeBackend.owner = nullptr;
                volumeBackend.connection = nullptr;
                volumeBackend.controller = nullptr;
                atomic_set(&volumeBackend.busy, 0);
                atomic_set(&volumeBackend.error, result);
                atomic_set(&volumeBackend.stage,
                           static_cast<atomic_val_t>(AudioControlStage::failed));
            }
            k_mutex_unlock(&volumeBackendMutex);
            bt_conn_unref(native);
            return record(mapNativeError(result), result);
        }
        k_mutex_lock(&volumeBackendMutex, K_FOREVER);
        if (ownsVolumeControllerLocked(this, generation) &&
            ((volumeBackend.controller == nullptr) || (volumeBackend.controller == controller)))
        {
            volumeBackend.controller = controller;
        }
        else
        {
            volumeBackend.owner = nullptr;
            volumeBackend.connection = nullptr;
            volumeBackend.controller = nullptr;
            ++volumeBackend.generation;
            atomic_set(&volumeBackend.busy, 0);
            atomic_set(&volumeBackend.error, -ESTALE);
            atomic_set(&volumeBackend.stage, static_cast<atomic_val_t>(AudioControlStage::failed));
            k_mutex_unlock(&volumeBackendMutex);
            bt_conn_unref(native);
            return record(Error::stack_error, -ESTALE);
        }
        k_mutex_unlock(&volumeBackendMutex);

        k_mutex_lock(&volumeBackendMutex, K_FOREVER);
        started_ = true;
        generation_ = generation;
        k_mutex_unlock(&volumeBackendMutex);
        return record(Error::none);
    }

    void VolumeController::poll() noexcept
    {
        k_mutex_lock(&volumeBackendMutex, K_FOREVER);
        const bool owned = started_ && ownsVolumeControllerLocked(this, generation_);
        const BLEConnectionHandle handle = volumeBackend.handle;
        k_mutex_unlock(&volumeBackendMutex);
        if (!owned)
        {
            return;
        }
        struct bt_conn *current = internal::referenceConnection(handle);
        if (current == nullptr)
        {
            k_mutex_lock(&volumeBackendMutex, K_FOREVER);
            if (ownsVolumeControllerLocked(this, generation_) && (volumeBackend.handle == handle))
            {
                volumeBackend.controller = nullptr;
                volumeBackend.offset_service = nullptr;
                volumeBackend.input_service = nullptr;
                atomic_set(&volumeBackend.error, -ENOTCONN);
                atomic_set(&volumeBackend.busy, 0);
                atomic_set(&volumeBackend.stage,
                           static_cast<atomic_val_t>(AudioControlStage::disconnected));
            }
            k_mutex_unlock(&volumeBackendMutex);
            return;
        }
        bt_conn_unref(current);
    }

    Error VolumeController::end() noexcept
    {
        k_mutex_lock(&volumeBackendMutex, K_FOREVER);
        if (!started_)
        {
            k_mutex_unlock(&volumeBackendMutex);
            return record(Error::not_started);
        }
        if (ownsVolumeControllerLocked(this, generation_))
        {
            const BLEConnectionHandle handle = volumeBackend.handle;
            struct bt_conn *connection = volumeBackend.connection;
            volumeBackend.retired_connection = true;
            volumeBackend.owner = nullptr;
            ++volumeBackend.generation;
            volumeBackend.pending_generation = 0U;
            volumeBackend.controller = nullptr;
            volumeBackend.offset_service = nullptr;
            volumeBackend.input_service = nullptr;
            atomic_set(&volumeBackend.busy, 0);
            atomic_set(&volumeBackend.stage, static_cast<atomic_val_t>(AudioControlStage::idle));
            volumeBackend.connection = nullptr;
            k_mutex_unlock(&volumeBackendMutex);

            struct bt_conn *active = internal::referenceConnection(handle);
            k_mutex_lock(&volumeBackendMutex, K_FOREVER);
            if (volumeBackend.handle == handle)
            {
                volumeBackend.retired_connection = active != nullptr;
            }
            k_mutex_unlock(&volumeBackendMutex);
            if (active != nullptr)
            {
                bt_conn_unref(active);
            }
            if (connection != nullptr)
            {
                bt_conn_unref(connection);
            }
            k_mutex_lock(&volumeBackendMutex, K_FOREVER);
            started_ = false;
            k_mutex_unlock(&volumeBackendMutex);
            return record(Error::none);
        }
        started_ = false;
        k_mutex_unlock(&volumeBackendMutex);
        return record(Error::none);
    }

#define NUCODE_VOLUME_CONTROLLER_REQUEST(step_value, expression, immediate)                        \
    do                                                                                             \
    {                                                                                              \
        k_mutex_lock(&volumeBackendMutex, K_FOREVER);                                              \
        if (!ownsVolumeControllerLocked(this, generation_))                                        \
        {                                                                                          \
            k_mutex_unlock(&volumeBackendMutex);                                                   \
            return record(Error::not_started);                                                     \
        }                                                                                          \
        if (static_cast<AudioControlStage>(atomic_get(&volumeBackend.stage)) ==                    \
            AudioControlStage::disconnected)                                                       \
        {                                                                                          \
            k_mutex_unlock(&volumeBackendMutex);                                                   \
            return record(Error::not_connected, -ENOTCONN);                                        \
        }                                                                                          \
        if ((static_cast<AudioControlStage>(atomic_get(&volumeBackend.stage)) !=                   \
             AudioControlStage::ready) ||                                                          \
            !atomic_cas(&volumeBackend.busy, 0, 1))                                                \
        {                                                                                          \
            k_mutex_unlock(&volumeBackendMutex);                                                   \
            return record(Error::busy, -EBUSY);                                                    \
        }                                                                                          \
        volumeBackend.pending_generation = generation_;                                            \
        atomic_set(&volumeBackend.step, static_cast<atomic_val_t>(AudioControlStep::step_value));  \
        atomic_set(&volumeBackend.stage, static_cast<atomic_val_t>(AudioControlStage::operating)); \
        atomic_set(&volumeBackend.error, 0);                                                       \
        struct bt_vcp_vol_ctlr *controller = volumeBackend.controller;                             \
        struct bt_vocs *output_service = volumeBackend.offset_service;                             \
        struct bt_aics *input_service = volumeBackend.input_service;                               \
        const std::uint32_t call_generation = volumeBackend.generation;                            \
        k_mutex_unlock(&volumeBackendMutex);                                                       \
        const int result = (expression);                                                           \
        if ((result != 0) || (immediate))                                                          \
        {                                                                                          \
            finishVolumeOperation(call_generation, result);                                        \
        }                                                                                          \
        return record(mapNativeError(result), result == 0 ? 0 : result);                           \
    } while (false)

    Error VolumeController::readVolume() noexcept
    {
        NUCODE_VOLUME_CONTROLLER_REQUEST(read_volume, bt_vcp_vol_ctlr_read_state(controller),
                                         false);
    }

    Error VolumeController::setVolume(std::uint8_t volume) noexcept
    {
        NUCODE_VOLUME_CONTROLLER_REQUEST(set_volume, bt_vcp_vol_ctlr_set_vol(controller, volume),
                                         false);
    }

    Error VolumeController::volumeUp() noexcept
    {
        NUCODE_VOLUME_CONTROLLER_REQUEST(volume_up, bt_vcp_vol_ctlr_vol_up(controller), false);
    }

    Error VolumeController::volumeDown() noexcept
    {
        NUCODE_VOLUME_CONTROLLER_REQUEST(volume_down, bt_vcp_vol_ctlr_vol_down(controller), false);
    }

    Error VolumeController::mute() noexcept
    {
        NUCODE_VOLUME_CONTROLLER_REQUEST(mute_volume, bt_vcp_vol_ctlr_mute(controller), false);
    }

    Error VolumeController::unmute() noexcept
    {
        NUCODE_VOLUME_CONTROLLER_REQUEST(unmute_volume, bt_vcp_vol_ctlr_unmute(controller), false);
    }

    Error VolumeController::readOffset() noexcept
    {
        NUCODE_VOLUME_CONTROLLER_REQUEST(read_offset, bt_vocs_state_get(output_service), false);
    }

    Error VolumeController::setOffset(std::int16_t offset) noexcept
    {
        if ((offset < BT_VOCS_MIN_OFFSET) || (offset > BT_VOCS_MAX_OFFSET))
        {
            return record(Error::invalid_argument);
        }
        NUCODE_VOLUME_CONTROLLER_REQUEST(set_offset, bt_vocs_state_set(output_service, offset),
                                         false);
    }

    Error VolumeController::setOutputLocation(std::uint32_t location) noexcept
    {
        NUCODE_VOLUME_CONTROLLER_REQUEST(set_output_location,
                                         bt_vocs_location_set(output_service, location), true);
    }

    Error VolumeController::setOutputDescription(const char *description) noexcept
    {
        if (!validDescription(description))
        {
            return record(Error::invalid_argument);
        }
        NUCODE_VOLUME_CONTROLLER_REQUEST(
            set_output_description, bt_vocs_description_set(output_service, description), true);
    }

    Error VolumeController::readInput() noexcept
    {
        NUCODE_VOLUME_CONTROLLER_REQUEST(read_input, bt_aics_state_get(input_service), false);
    }

    Error VolumeController::setInputGain(std::int8_t gain) noexcept
    {
        k_mutex_lock(&volumeBackendMutex, K_FOREVER);
        const bool valid_gain = (gain >= volumeBackend.input.minimum_gain) &&
                                (gain <= volumeBackend.input.maximum_gain);
        k_mutex_unlock(&volumeBackendMutex);
        if (!valid_gain)
        {
            return record(Error::invalid_argument);
        }
        NUCODE_VOLUME_CONTROLLER_REQUEST(set_input_gain, bt_aics_gain_set(input_service, gain),
                                         false);
    }

    Error VolumeController::muteInput() noexcept
    {
        NUCODE_VOLUME_CONTROLLER_REQUEST(mute_input, bt_aics_mute(input_service), false);
    }

    Error VolumeController::unmuteInput() noexcept
    {
        NUCODE_VOLUME_CONTROLLER_REQUEST(unmute_input, bt_aics_unmute(input_service), false);
    }

    Error VolumeController::setInputMode(AudioInputMode mode) noexcept
    {
        if (!writableMode(mode))
        {
            return record(Error::invalid_argument);
        }
        if (mode == AudioInputMode::manual)
        {
            NUCODE_VOLUME_CONTROLLER_REQUEST(set_input_mode, bt_aics_manual_gain_set(input_service),
                                             false);
        }
        NUCODE_VOLUME_CONTROLLER_REQUEST(set_input_mode, bt_aics_automatic_gain_set(input_service),
                                         false);
    }

    Error VolumeController::setInputDescription(const char *description) noexcept
    {
        if (!validDescription(description))
        {
            return record(Error::invalid_argument);
        }
        NUCODE_VOLUME_CONTROLLER_REQUEST(set_input_description,
                                         bt_aics_description_set(input_service, description), true);
    }

#undef NUCODE_VOLUME_CONTROLLER_REQUEST

    bool VolumeController::ready() const noexcept
    {
        k_mutex_lock(&volumeBackendMutex, K_FOREVER);
        const bool value = started_ && ownsVolumeControllerLocked(this, generation_) &&
                           (static_cast<AudioControlStage>(atomic_get(&volumeBackend.stage)) ==
                            AudioControlStage::ready) &&
                           (volumeBackend.controller != nullptr) &&
                           (volumeBackend.offset_service != nullptr) &&
                           (volumeBackend.input_service != nullptr);
        k_mutex_unlock(&volumeBackendMutex);
        return value;
    }

    bool VolumeController::busy() const noexcept
    {
        k_mutex_lock(&volumeBackendMutex, K_FOREVER);
        const bool value = started_ && ownsVolumeControllerLocked(this, generation_) &&
                           atomic_get(&volumeBackend.busy);
        k_mutex_unlock(&volumeBackendMutex);
        return value;
    }

    AudioControlStage VolumeController::stage() const noexcept
    {
        k_mutex_lock(&volumeBackendMutex, K_FOREVER);
        const AudioControlStage value =
            ownsVolumeControllerLocked(this, generation_)
                ? static_cast<AudioControlStage>(atomic_get(&volumeBackend.stage))
                : AudioControlStage::idle;
        k_mutex_unlock(&volumeBackendMutex);
        return value;
    }

    AudioControlStep VolumeController::lastStep() const noexcept
    {
        k_mutex_lock(&volumeBackendMutex, K_FOREVER);
        const AudioControlStep value =
            ownsVolumeControllerLocked(this, generation_)
                ? static_cast<AudioControlStep>(atomic_get(&volumeBackend.step))
                : AudioControlStep::none;
        k_mutex_unlock(&volumeBackendMutex);
        return value;
    }

    VolumeState VolumeController::state() const noexcept
    {
        k_mutex_lock(&volumeBackendMutex, K_FOREVER);
        const VolumeState value =
            ownsVolumeControllerLocked(this, generation_) ? volumeBackend.volume : VolumeState{};
        k_mutex_unlock(&volumeBackendMutex);
        return value;
    }

    VolumeOffsetState VolumeController::offsetState() const noexcept
    {
        k_mutex_lock(&volumeBackendMutex, K_FOREVER);
        const VolumeOffsetState value = ownsVolumeControllerLocked(this, generation_)
                                            ? volumeBackend.offset
                                            : VolumeOffsetState{};
        k_mutex_unlock(&volumeBackendMutex);
        return value;
    }

    AudioInputState VolumeController::inputState() const noexcept
    {
        k_mutex_lock(&volumeBackendMutex, K_FOREVER);
        const AudioInputState value =
            ownsVolumeControllerLocked(this, generation_) ? volumeBackend.input : AudioInputState{};
        k_mutex_unlock(&volumeBackendMutex);
        return value;
    }

    std::uint32_t VolumeController::stateUpdates() const noexcept
    {
        k_mutex_lock(&volumeBackendMutex, K_FOREVER);
        const std::uint32_t value =
            ownsVolumeControllerLocked(this, generation_) ? volumeBackend.updates : 0U;
        k_mutex_unlock(&volumeBackendMutex);
        return value;
    }

    Error VolumeController::lastError() const noexcept
    {
        k_mutex_lock(&volumeBackendMutex, K_FOREVER);
        const int native = ownsVolumeControllerLocked(this, generation_)
                               ? static_cast<int>(atomic_get(&volumeBackend.error))
                               : 0;
        const Error fallback = last_error_;
        k_mutex_unlock(&volumeBackendMutex);
        return native == 0 ? fallback : mapNativeError(native);
    }

    int VolumeController::nativeCode() const noexcept
    {
        k_mutex_lock(&volumeBackendMutex, K_FOREVER);
        const int native = ownsVolumeControllerLocked(this, generation_)
                               ? static_cast<int>(atomic_get(&volumeBackend.error))
                               : 0;
        const int fallback = native_code_;
        k_mutex_unlock(&volumeBackendMutex);
        return native == 0 ? fallback : native;
    }

    Error VolumeController::record(Error error, int native_code) noexcept
    {
        k_mutex_lock(&volumeBackendMutex, K_FOREVER);
        last_error_ = error;
        native_code_ = native_code;
        k_mutex_unlock(&volumeBackendMutex);
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
            MicrophoneBootstrapStep bootstrap = MicrophoneBootstrapStep::none;
            MicrophoneState microphone = {};
            AudioInputState input = {};
            atomic_t stage = ATOMIC_INIT(static_cast<atomic_val_t>(AudioControlStage::idle));
            atomic_t step = ATOMIC_INIT(static_cast<atomic_val_t>(AudioControlStep::none));
            atomic_t busy = ATOMIC_INIT(0);
            atomic_t error = ATOMIC_INIT(0);
        };

        MicrophoneControllerBackend microphoneControllerBackend;
        K_MUTEX_DEFINE(microphoneControllerBackendMutex);

        /** @brief 이전 callback이 남을 수 있는 active 연결의 재소유를 차단합니다. */
        bool retiredMicrophoneConnectionActive() noexcept
        {
            k_mutex_lock(&microphoneControllerBackendMutex, K_FOREVER);
            const bool retired = microphoneControllerBackend.retired_connection;
            const BLEConnectionHandle handle = microphoneControllerBackend.handle;
            k_mutex_unlock(&microphoneControllerBackendMutex);
            if (!retired)
            {
                return false;
            }
            struct bt_conn *connection = internal::referenceConnection(handle);
            if (connection == nullptr)
            {
                k_mutex_lock(&microphoneControllerBackendMutex, K_FOREVER);
                if (microphoneControllerBackend.retired_connection &&
                    (microphoneControllerBackend.handle == handle))
                {
                    microphoneControllerBackend.retired_connection = false;
                    microphoneControllerBackend.controller = nullptr;
                    microphoneControllerBackend.input_service = nullptr;
                }
                k_mutex_unlock(&microphoneControllerBackendMutex);
                return false;
            }
            bt_conn_unref(connection);
            return true;
        }

        /** @brief MICP callback instance가 현재 active 연결에 속하는지 확인합니다. */
        std::uint32_t currentMicrophoneController(struct bt_micp_mic_ctlr *controller) noexcept
        {
            k_mutex_lock(&microphoneControllerBackendMutex, K_FOREVER);
            if ((microphoneControllerBackend.owner == nullptr) || (controller == nullptr) ||
                (controller != microphoneControllerBackend.controller) ||
                (microphoneControllerBackend.connection == nullptr))
            {
                k_mutex_unlock(&microphoneControllerBackendMutex);
                return 0U;
            }
            struct bt_conn *expected_connection = microphoneControllerBackend.connection;
            const std::uint32_t generation = microphoneControllerBackend.generation;
            k_mutex_unlock(&microphoneControllerBackendMutex);
            struct bt_conn *connection = nullptr;
            if ((bt_micp_mic_ctlr_conn_get(controller, &connection) != 0) ||
                (connection != expected_connection) || !internal::activeConnection(connection))
            {
                return 0U;
            }
            k_mutex_lock(&microphoneControllerBackendMutex, K_FOREVER);
            const bool current = (microphoneControllerBackend.owner != nullptr) &&
                                 (microphoneControllerBackend.controller == controller) &&
                                 (microphoneControllerBackend.connection == expected_connection) &&
                                 (microphoneControllerBackend.generation == generation);
            k_mutex_unlock(&microphoneControllerBackendMutex);
            return current ? generation : 0U;
        }

        /** @brief discovery callback의 controller를 현재 연결에 원자적으로 결합합니다. */
        std::uint32_t currentMicrophoneDiscovery(struct bt_micp_mic_ctlr *controller) noexcept
        {
            k_mutex_lock(&microphoneControllerBackendMutex, K_FOREVER);
            if ((microphoneControllerBackend.owner == nullptr) || (controller == nullptr) ||
                ((microphoneControllerBackend.controller != nullptr) &&
                 (microphoneControllerBackend.controller != controller)) ||
                (microphoneControllerBackend.connection == nullptr) ||
                (static_cast<AudioControlStage>(atomic_get(&microphoneControllerBackend.stage)) !=
                 AudioControlStage::discovering))
            {
                k_mutex_unlock(&microphoneControllerBackendMutex);
                return 0U;
            }
            struct bt_conn *expected_connection = microphoneControllerBackend.connection;
            const std::uint32_t generation = microphoneControllerBackend.generation;
            k_mutex_unlock(&microphoneControllerBackendMutex);

            struct bt_conn *connection = nullptr;
            if ((bt_micp_mic_ctlr_conn_get(controller, &connection) != 0) ||
                (connection != expected_connection) || !internal::activeConnection(connection))
            {
                return 0U;
            }
            k_mutex_lock(&microphoneControllerBackendMutex, K_FOREVER);
            const bool current = (microphoneControllerBackend.owner != nullptr) &&
                                 ((microphoneControllerBackend.controller == nullptr) ||
                                  (microphoneControllerBackend.controller == controller)) &&
                                 (microphoneControllerBackend.connection == expected_connection) &&
                                 (microphoneControllerBackend.generation == generation);
            if (current)
            {
                microphoneControllerBackend.controller = controller;
            }
            k_mutex_unlock(&microphoneControllerBackendMutex);
            return current ? generation : 0U;
        }

        /** @brief MICP 포함 AICS callback이 현재 active 연결에 속하는지 확인합니다. */
        std::uint32_t currentMicrophoneInput(struct bt_aics *instance) noexcept
        {
            k_mutex_lock(&microphoneControllerBackendMutex, K_FOREVER);
            if ((microphoneControllerBackend.owner == nullptr) || (instance == nullptr) ||
                (instance != microphoneControllerBackend.input_service) ||
                (microphoneControllerBackend.connection == nullptr))
            {
                k_mutex_unlock(&microphoneControllerBackendMutex);
                return 0U;
            }
            struct bt_conn *expected_connection = microphoneControllerBackend.connection;
            const std::uint32_t generation = microphoneControllerBackend.generation;
            k_mutex_unlock(&microphoneControllerBackendMutex);
            struct bt_conn *connection = nullptr;
            if ((bt_aics_client_conn_get(instance, &connection) != 0) ||
                (connection != expected_connection) || !internal::activeConnection(connection))
            {
                return 0U;
            }
            k_mutex_lock(&microphoneControllerBackendMutex, K_FOREVER);
            const bool current = (microphoneControllerBackend.owner != nullptr) &&
                                 (microphoneControllerBackend.input_service == instance) &&
                                 (microphoneControllerBackend.connection == expected_connection) &&
                                 (microphoneControllerBackend.generation == generation);
            k_mutex_unlock(&microphoneControllerBackendMutex);
            return current ? generation : 0U;
        }

        /** @brief 현재 MICP pending 작업을 종료합니다. */
        void finishMicrophoneOperation(std::uint32_t generation, int error) noexcept
        {
            k_mutex_lock(&microphoneControllerBackendMutex, K_FOREVER);
            if ((microphoneControllerBackend.owner == nullptr) ||
                (microphoneControllerBackend.generation != generation) ||
                (microphoneControllerBackend.pending_generation != generation))
            {
                k_mutex_unlock(&microphoneControllerBackendMutex);
                return;
            }
            atomic_set(&microphoneControllerBackend.error, error);
            atomic_set(&microphoneControllerBackend.busy, 0);
            atomic_set(&microphoneControllerBackend.stage,
                       static_cast<atomic_val_t>(AudioControlStage::ready));
            k_mutex_unlock(&microphoneControllerBackendMutex);
        }

        /** @brief MICP bootstrap read의 즉시 시작 오류를 failed 상태로 고정합니다. */
        void failMicrophoneBootstrap(std::uint32_t generation, int error) noexcept
        {
            k_mutex_lock(&microphoneControllerBackendMutex, K_FOREVER);
            if ((microphoneControllerBackend.owner != nullptr) &&
                (microphoneControllerBackend.generation == generation) &&
                (static_cast<AudioControlStage>(atomic_get(&microphoneControllerBackend.stage)) ==
                 AudioControlStage::discovering))
            {
                atomic_set(&microphoneControllerBackend.error, error);
                atomic_set(&microphoneControllerBackend.busy, 0);
                atomic_set(&microphoneControllerBackend.stage,
                           static_cast<atomic_val_t>(AudioControlStage::failed));
            }
            k_mutex_unlock(&microphoneControllerBackendMutex);
        }

        /** @brief 잠금 밖에서 현재 MICP bootstrap read 한 단계를 시작합니다. */
        void startMicrophoneBootstrap(std::uint32_t generation,
                                      MicrophoneBootstrapStep step) noexcept
        {
            k_mutex_lock(&microphoneControllerBackendMutex, K_FOREVER);
            if ((microphoneControllerBackend.owner == nullptr) ||
                (microphoneControllerBackend.generation != generation) ||
                (microphoneControllerBackend.bootstrap != step) ||
                (static_cast<AudioControlStage>(atomic_get(&microphoneControllerBackend.stage)) !=
                 AudioControlStage::discovering))
            {
                k_mutex_unlock(&microphoneControllerBackendMutex);
                return;
            }
            struct bt_micp_mic_ctlr *controller = microphoneControllerBackend.controller;
            struct bt_aics *input_service = microphoneControllerBackend.input_service;
            k_mutex_unlock(&microphoneControllerBackendMutex);

            int result = -EINVAL;
            switch (step)
            {
            case MicrophoneBootstrapStep::microphone_state:
                result = bt_micp_mic_ctlr_mute_get(controller);
                break;
            case MicrophoneBootstrapStep::input_state:
                result = bt_aics_state_get(input_service);
                break;
            case MicrophoneBootstrapStep::input_gain_setting:
                result = bt_aics_gain_setting_get(input_service);
                break;
            case MicrophoneBootstrapStep::input_type:
                result = bt_aics_type_get(input_service);
                break;
            case MicrophoneBootstrapStep::input_status:
                result = bt_aics_status_get(input_service);
                break;
            default:
                break;
            }
            if (result != 0)
            {
                failMicrophoneBootstrap(generation, result);
            }
        }

        /** @brief callback 결과를 반영하고 다음 MICP bootstrap read를 예약합니다. */
        void advanceMicrophoneBootstrap(std::uint32_t generation, MicrophoneBootstrapStep completed,
                                        int error) noexcept
        {
            MicrophoneBootstrapStep next = MicrophoneBootstrapStep::none;
            k_mutex_lock(&microphoneControllerBackendMutex, K_FOREVER);
            if ((microphoneControllerBackend.owner == nullptr) ||
                (microphoneControllerBackend.generation != generation) ||
                (microphoneControllerBackend.bootstrap != completed) ||
                (static_cast<AudioControlStage>(atomic_get(&microphoneControllerBackend.stage)) !=
                 AudioControlStage::discovering))
            {
                k_mutex_unlock(&microphoneControllerBackendMutex);
                return;
            }
            if (error != 0)
            {
                atomic_set(&microphoneControllerBackend.error, error);
                atomic_set(&microphoneControllerBackend.busy, 0);
                atomic_set(&microphoneControllerBackend.stage,
                           static_cast<atomic_val_t>(AudioControlStage::failed));
                k_mutex_unlock(&microphoneControllerBackendMutex);
                return;
            }

            next = static_cast<MicrophoneBootstrapStep>(static_cast<std::uint8_t>(completed) + 1U);
            microphoneControllerBackend.bootstrap = next;
            if (next == MicrophoneBootstrapStep::complete)
            {
                atomic_set(&microphoneControllerBackend.error, 0);
                atomic_set(&microphoneControllerBackend.busy, 0);
                atomic_set(&microphoneControllerBackend.stage,
                           static_cast<atomic_val_t>(AudioControlStage::ready));
            }
            k_mutex_unlock(&microphoneControllerBackendMutex);
            if (next != MicrophoneBootstrapStep::complete)
            {
                startMicrophoneBootstrap(generation, next);
            }
        }

        /** @brief MICS와 포함 AICS 검색 완료를 검증합니다. */
        void microphoneDiscovered(struct bt_micp_mic_ctlr *controller, int error,
                                  std::uint8_t input_count) noexcept
        {
            const std::uint32_t generation = currentMicrophoneDiscovery(controller);
            if (generation == 0U)
            {
                return;
            }
            if ((error == 0) && (input_count != 1U))
            {
                error = -ENODEV;
            }
            struct bt_micp_included included = {};
            if (error == 0)
            {
                error = bt_micp_mic_ctlr_included_get(controller, &included);
                if ((error == 0) && ((included.aics_cnt != 1U) || (included.aics == nullptr) ||
                                     (included.aics[0] == nullptr)))
                {
                    error = -ENODEV;
                }
            }
            k_mutex_lock(&microphoneControllerBackendMutex, K_FOREVER);
            if ((microphoneControllerBackend.owner == nullptr) ||
                (microphoneControllerBackend.generation != generation) ||
                (microphoneControllerBackend.pending_generation != generation))
            {
                k_mutex_unlock(&microphoneControllerBackendMutex);
                return;
            }
            atomic_set(&microphoneControllerBackend.error, error);
            if (error != 0)
            {
                atomic_set(&microphoneControllerBackend.busy, 0);
                atomic_set(&microphoneControllerBackend.stage,
                           static_cast<atomic_val_t>(AudioControlStage::failed));
                k_mutex_unlock(&microphoneControllerBackendMutex);
                return;
            }
            microphoneControllerBackend.input_service = included.aics[0];
            microphoneControllerBackend.bootstrap = MicrophoneBootstrapStep::microphone_state;
            k_mutex_unlock(&microphoneControllerBackendMutex);
            startMicrophoneBootstrap(generation, MicrophoneBootstrapStep::microphone_state);
        }

        /** @brief MICS mute read 또는 notification을 공개 상태에 반영합니다. */
        void microphoneStateChanged(struct bt_micp_mic_ctlr *controller, int error,
                                    std::uint8_t mute) noexcept
        {
            const std::uint32_t generation = currentMicrophoneController(controller);
            if (generation == 0U)
            {
                return;
            }
            bool completes_read = false;
            k_mutex_lock(&microphoneControllerBackendMutex, K_FOREVER);
            if (microphoneControllerBackend.generation != generation)
            {
                k_mutex_unlock(&microphoneControllerBackendMutex);
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
            completes_read =
                (static_cast<AudioControlStep>(atomic_get(&microphoneControllerBackend.step)) ==
                 AudioControlStep::read_microphone) &&
                atomic_get(&microphoneControllerBackend.busy);
            k_mutex_unlock(&microphoneControllerBackendMutex);
            advanceMicrophoneBootstrap(generation, MicrophoneBootstrapStep::microphone_state,
                                       error);
            if (completes_read)
            {
                finishMicrophoneOperation(generation, error);
            }
        }

        /** @brief MICS control point 작업 완료를 기록합니다. */
        void microphoneWriteComplete(struct bt_micp_mic_ctlr *controller, int error) noexcept
        {
            const std::uint32_t generation = currentMicrophoneController(controller);
            if (generation != 0U)
            {
                finishMicrophoneOperation(generation, error);
            }
        }

        /** @brief MICP 포함 AICS state를 공개 상태에 반영합니다. */
        void microphoneControllerInputState(struct bt_aics *instance, int error, std::int8_t gain,
                                            std::uint8_t mute, std::uint8_t mode) noexcept
        {
            const std::uint32_t generation = currentMicrophoneInput(instance);
            if (generation == 0U)
            {
                return;
            }
            bool completes_read = false;
            k_mutex_lock(&microphoneControllerBackendMutex, K_FOREVER);
            if (microphoneControllerBackend.generation != generation)
            {
                k_mutex_unlock(&microphoneControllerBackendMutex);
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
            completes_read =
                (static_cast<AudioControlStep>(atomic_get(&microphoneControllerBackend.step)) ==
                 AudioControlStep::read_input) &&
                atomic_get(&microphoneControllerBackend.busy);
            k_mutex_unlock(&microphoneControllerBackendMutex);
            advanceMicrophoneBootstrap(generation, MicrophoneBootstrapStep::input_state, error);
            if (completes_read)
            {
                finishMicrophoneOperation(generation, error);
            }
        }

        /** @brief MICP 포함 AICS gain 범위를 공개 상태에 반영합니다. */
        void microphoneControllerGainSetting(struct bt_aics *instance, int error,
                                             std::uint8_t units, std::int8_t minimum,
                                             std::int8_t maximum) noexcept
        {
            const std::uint32_t generation = currentMicrophoneInput(instance);
            if (generation == 0U)
            {
                return;
            }
            k_mutex_lock(&microphoneControllerBackendMutex, K_FOREVER);
            if (microphoneControllerBackend.generation != generation)
            {
                k_mutex_unlock(&microphoneControllerBackendMutex);
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
            k_mutex_unlock(&microphoneControllerBackendMutex);
            advanceMicrophoneBootstrap(generation, MicrophoneBootstrapStep::input_gain_setting,
                                       error);
        }

        /** @brief MICP 포함 AICS type을 공개 상태에 반영합니다. */
        void microphoneControllerInputType(struct bt_aics *instance, int error,
                                           std::uint8_t type) noexcept
        {
            const std::uint32_t generation = currentMicrophoneInput(instance);
            if (generation == 0U)
            {
                return;
            }
            k_mutex_lock(&microphoneControllerBackendMutex, K_FOREVER);
            if (microphoneControllerBackend.generation != generation)
            {
                k_mutex_unlock(&microphoneControllerBackendMutex);
                return;
            }
            atomic_set(&microphoneControllerBackend.error, error);
            if (error == 0)
            {
                microphoneControllerBackend.input.type = static_cast<AudioInputType>(type);
                ++microphoneControllerBackend.updates;
            }
            k_mutex_unlock(&microphoneControllerBackendMutex);
            advanceMicrophoneBootstrap(generation, MicrophoneBootstrapStep::input_type, error);
        }

        /** @brief MICP 포함 AICS active 상태를 공개 상태에 반영합니다. */
        void microphoneControllerInputStatus(struct bt_aics *instance, int error,
                                             bool active) noexcept
        {
            const std::uint32_t generation = currentMicrophoneInput(instance);
            if (generation == 0U)
            {
                return;
            }
            k_mutex_lock(&microphoneControllerBackendMutex, K_FOREVER);
            if (microphoneControllerBackend.generation != generation)
            {
                k_mutex_unlock(&microphoneControllerBackendMutex);
                return;
            }
            atomic_set(&microphoneControllerBackend.error, error);
            if (error == 0)
            {
                microphoneControllerBackend.input.active = active;
                ++microphoneControllerBackend.updates;
            }
            k_mutex_unlock(&microphoneControllerBackendMutex);
            advanceMicrophoneBootstrap(generation, MicrophoneBootstrapStep::input_status, error);
        }

        /** @brief MICP 포함 AICS 설명 변경 결과를 기록합니다. */
        void microphoneControllerInputDescription(struct bt_aics *instance, int error,
                                                  char *) noexcept
        {
            const std::uint32_t generation = currentMicrophoneInput(instance);
            if (generation == 0U)
            {
                return;
            }
            k_mutex_lock(&microphoneControllerBackendMutex, K_FOREVER);
            if (microphoneControllerBackend.generation != generation)
            {
                k_mutex_unlock(&microphoneControllerBackendMutex);
                return;
            }
            atomic_set(&microphoneControllerBackend.error, error);
            if (error == 0)
            {
                ++microphoneControllerBackend.updates;
            }
            k_mutex_unlock(&microphoneControllerBackendMutex);
        }

        /** @brief MICP 포함 AICS control point 작업 완료를 기록합니다. */
        void microphoneControllerInputWrite(struct bt_aics *instance, int error) noexcept
        {
            const std::uint32_t generation = currentMicrophoneInput(instance);
            if (generation != 0U)
            {
                finishMicrophoneOperation(generation, error);
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
        bool ownsMicrophoneControllerLocked(const MicrophoneController *owner,
                                            std::uint32_t generation) noexcept
        {
            return (microphoneControllerBackend.owner == owner) &&
                   (microphoneControllerBackend.generation == generation);
        }
    } // namespace

    Error MicrophoneController::begin(const BLEConnectionHandle &connection) noexcept
    {
        k_mutex_lock(&microphoneControllerBackendMutex, K_FOREVER);
        const bool object_started = started_;
        k_mutex_unlock(&microphoneControllerBackendMutex);
        if (object_started)
        {
            return record(Error::already_started);
        }
        k_mutex_lock(&microphoneControllerBackendMutex, K_FOREVER);
        const bool owner_present = microphoneControllerBackend.owner != nullptr;
        const bool callbacks_registered = microphoneControllerBackend.callbacks_registered;
        k_mutex_unlock(&microphoneControllerBackendMutex);
        if (owner_present)
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
        if (!callbacks_registered)
        {
            const int callback_result =
                bt_micp_mic_ctlr_cb_register(&microphoneControllerCallbacks);
            if ((callback_result != 0) && (callback_result != -EALREADY))
            {
                bt_conn_unref(native);
                return record(mapNativeError(callback_result), callback_result);
            }
            k_mutex_lock(&microphoneControllerBackendMutex, K_FOREVER);
            microphoneControllerBackend.callbacks_registered = true;
            k_mutex_unlock(&microphoneControllerBackendMutex);
        }

        k_mutex_lock(&microphoneControllerBackendMutex, K_FOREVER);
        if (microphoneControllerBackend.owner != nullptr)
        {
            k_mutex_unlock(&microphoneControllerBackendMutex);
            bt_conn_unref(native);
            return record(Error::busy, -EBUSY);
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
        microphoneControllerBackend.bootstrap = MicrophoneBootstrapStep::none;
        atomic_set(&microphoneControllerBackend.error, 0);
        atomic_set(&microphoneControllerBackend.busy, 1);
        atomic_set(&microphoneControllerBackend.step,
                   static_cast<atomic_val_t>(AudioControlStep::discover));
        atomic_set(&microphoneControllerBackend.stage,
                   static_cast<atomic_val_t>(AudioControlStage::discovering));
        const std::uint32_t generation = microphoneControllerBackend.generation;
        k_mutex_unlock(&microphoneControllerBackendMutex);

        struct bt_micp_mic_ctlr *controller = nullptr;
        const int result = bt_micp_mic_ctlr_discover(native, &controller);
        if (result != 0)
        {
            k_mutex_lock(&microphoneControllerBackendMutex, K_FOREVER);
            if (ownsMicrophoneControllerLocked(this, generation))
            {
                microphoneControllerBackend.owner = nullptr;
                microphoneControllerBackend.connection = nullptr;
                microphoneControllerBackend.controller = nullptr;
                atomic_set(&microphoneControllerBackend.busy, 0);
                atomic_set(&microphoneControllerBackend.error, result);
                atomic_set(&microphoneControllerBackend.stage,
                           static_cast<atomic_val_t>(AudioControlStage::failed));
            }
            k_mutex_unlock(&microphoneControllerBackendMutex);
            bt_conn_unref(native);
            return record(mapNativeError(result), result);
        }
        k_mutex_lock(&microphoneControllerBackendMutex, K_FOREVER);
        if (ownsMicrophoneControllerLocked(this, generation) &&
            ((microphoneControllerBackend.controller == nullptr) ||
             (microphoneControllerBackend.controller == controller)))
        {
            microphoneControllerBackend.controller = controller;
        }
        else
        {
            microphoneControllerBackend.owner = nullptr;
            microphoneControllerBackend.connection = nullptr;
            microphoneControllerBackend.controller = nullptr;
            ++microphoneControllerBackend.generation;
            atomic_set(&microphoneControllerBackend.busy, 0);
            atomic_set(&microphoneControllerBackend.error, -ESTALE);
            atomic_set(&microphoneControllerBackend.stage,
                       static_cast<atomic_val_t>(AudioControlStage::failed));
            k_mutex_unlock(&microphoneControllerBackendMutex);
            bt_conn_unref(native);
            return record(Error::stack_error, -ESTALE);
        }
        k_mutex_unlock(&microphoneControllerBackendMutex);

        k_mutex_lock(&microphoneControllerBackendMutex, K_FOREVER);
        started_ = true;
        generation_ = generation;
        k_mutex_unlock(&microphoneControllerBackendMutex);
        return record(Error::none);
    }

    void MicrophoneController::poll() noexcept
    {
        k_mutex_lock(&microphoneControllerBackendMutex, K_FOREVER);
        const bool owned = started_ && ownsMicrophoneControllerLocked(this, generation_);
        const BLEConnectionHandle handle = microphoneControllerBackend.handle;
        k_mutex_unlock(&microphoneControllerBackendMutex);
        if (!owned)
        {
            return;
        }
        struct bt_conn *current = internal::referenceConnection(handle);
        if (current == nullptr)
        {
            k_mutex_lock(&microphoneControllerBackendMutex, K_FOREVER);
            if (ownsMicrophoneControllerLocked(this, generation_) &&
                (microphoneControllerBackend.handle == handle))
            {
                microphoneControllerBackend.controller = nullptr;
                microphoneControllerBackend.input_service = nullptr;
                atomic_set(&microphoneControllerBackend.error, -ENOTCONN);
                atomic_set(&microphoneControllerBackend.busy, 0);
                atomic_set(&microphoneControllerBackend.stage,
                           static_cast<atomic_val_t>(AudioControlStage::disconnected));
            }
            k_mutex_unlock(&microphoneControllerBackendMutex);
            return;
        }
        bt_conn_unref(current);
    }

    Error MicrophoneController::end() noexcept
    {
        k_mutex_lock(&microphoneControllerBackendMutex, K_FOREVER);
        if (!started_)
        {
            k_mutex_unlock(&microphoneControllerBackendMutex);
            return record(Error::not_started);
        }
        if (ownsMicrophoneControllerLocked(this, generation_))
        {
            const BLEConnectionHandle handle = microphoneControllerBackend.handle;
            struct bt_conn *connection = microphoneControllerBackend.connection;
            microphoneControllerBackend.retired_connection = true;
            microphoneControllerBackend.owner = nullptr;
            ++microphoneControllerBackend.generation;
            microphoneControllerBackend.pending_generation = 0U;
            microphoneControllerBackend.controller = nullptr;
            microphoneControllerBackend.input_service = nullptr;
            atomic_set(&microphoneControllerBackend.busy, 0);
            atomic_set(&microphoneControllerBackend.stage,
                       static_cast<atomic_val_t>(AudioControlStage::idle));
            microphoneControllerBackend.connection = nullptr;
            k_mutex_unlock(&microphoneControllerBackendMutex);

            struct bt_conn *active = internal::referenceConnection(handle);
            k_mutex_lock(&microphoneControllerBackendMutex, K_FOREVER);
            if (microphoneControllerBackend.handle == handle)
            {
                microphoneControllerBackend.retired_connection = active != nullptr;
            }
            k_mutex_unlock(&microphoneControllerBackendMutex);
            if (active != nullptr)
            {
                bt_conn_unref(active);
            }
            if (connection != nullptr)
            {
                bt_conn_unref(connection);
            }
            k_mutex_lock(&microphoneControllerBackendMutex, K_FOREVER);
            started_ = false;
            k_mutex_unlock(&microphoneControllerBackendMutex);
            return record(Error::none);
        }
        started_ = false;
        k_mutex_unlock(&microphoneControllerBackendMutex);
        return record(Error::none);
    }

#define NUCODE_MIC_CONTROLLER_REQUEST(step_value, expression, immediate)                           \
    do                                                                                             \
    {                                                                                              \
        k_mutex_lock(&microphoneControllerBackendMutex, K_FOREVER);                                \
        if (!ownsMicrophoneControllerLocked(this, generation_))                                    \
        {                                                                                          \
            k_mutex_unlock(&microphoneControllerBackendMutex);                                     \
            return record(Error::not_started);                                                     \
        }                                                                                          \
        if (static_cast<AudioControlStage>(atomic_get(&microphoneControllerBackend.stage)) ==      \
            AudioControlStage::disconnected)                                                       \
        {                                                                                          \
            k_mutex_unlock(&microphoneControllerBackendMutex);                                     \
            return record(Error::not_connected, -ENOTCONN);                                        \
        }                                                                                          \
        if ((static_cast<AudioControlStage>(atomic_get(&microphoneControllerBackend.stage)) !=     \
             AudioControlStage::ready) ||                                                          \
            !atomic_cas(&microphoneControllerBackend.busy, 0, 1))                                  \
        {                                                                                          \
            k_mutex_unlock(&microphoneControllerBackendMutex);                                     \
            return record(Error::busy, -EBUSY);                                                    \
        }                                                                                          \
        microphoneControllerBackend.pending_generation = generation_;                              \
        atomic_set(&microphoneControllerBackend.step,                                              \
                   static_cast<atomic_val_t>(AudioControlStep::step_value));                       \
        atomic_set(&microphoneControllerBackend.stage,                                             \
                   static_cast<atomic_val_t>(AudioControlStage::operating));                       \
        atomic_set(&microphoneControllerBackend.error, 0);                                         \
        struct bt_micp_mic_ctlr *controller = microphoneControllerBackend.controller;              \
        struct bt_aics *input_service = microphoneControllerBackend.input_service;                 \
        const std::uint32_t call_generation = microphoneControllerBackend.generation;              \
        k_mutex_unlock(&microphoneControllerBackendMutex);                                         \
        const int result = (expression);                                                           \
        if ((result != 0) || (immediate))                                                          \
        {                                                                                          \
            finishMicrophoneOperation(call_generation, result);                                    \
        }                                                                                          \
        return record(mapNativeError(result), result == 0 ? 0 : result);                           \
    } while (false)

    Error MicrophoneController::readMicrophone() noexcept
    {
        NUCODE_MIC_CONTROLLER_REQUEST(read_microphone, bt_micp_mic_ctlr_mute_get(controller),
                                      false);
    }

    Error MicrophoneController::mute() noexcept
    {
        NUCODE_MIC_CONTROLLER_REQUEST(mute_microphone, bt_micp_mic_ctlr_mute(controller), false);
    }

    Error MicrophoneController::unmute() noexcept
    {
        NUCODE_MIC_CONTROLLER_REQUEST(unmute_microphone, bt_micp_mic_ctlr_unmute(controller),
                                      false);
    }

    Error MicrophoneController::readInput() noexcept
    {
        NUCODE_MIC_CONTROLLER_REQUEST(read_input, bt_aics_state_get(input_service), false);
    }

    Error MicrophoneController::setInputGain(std::int8_t gain) noexcept
    {
        k_mutex_lock(&microphoneControllerBackendMutex, K_FOREVER);
        const bool valid_gain = (gain >= microphoneControllerBackend.input.minimum_gain) &&
                                (gain <= microphoneControllerBackend.input.maximum_gain);
        k_mutex_unlock(&microphoneControllerBackendMutex);
        if (!valid_gain)
        {
            return record(Error::invalid_argument);
        }
        NUCODE_MIC_CONTROLLER_REQUEST(set_input_gain, bt_aics_gain_set(input_service, gain), false);
    }

    Error MicrophoneController::muteInput() noexcept
    {
        NUCODE_MIC_CONTROLLER_REQUEST(mute_input, bt_aics_mute(input_service), false);
    }

    Error MicrophoneController::unmuteInput() noexcept
    {
        NUCODE_MIC_CONTROLLER_REQUEST(unmute_input, bt_aics_unmute(input_service), false);
    }

    Error MicrophoneController::setInputMode(AudioInputMode mode) noexcept
    {
        if (!writableMode(mode))
        {
            return record(Error::invalid_argument);
        }
        if (mode == AudioInputMode::manual)
        {
            NUCODE_MIC_CONTROLLER_REQUEST(set_input_mode, bt_aics_manual_gain_set(input_service),
                                          false);
        }
        NUCODE_MIC_CONTROLLER_REQUEST(set_input_mode, bt_aics_automatic_gain_set(input_service),
                                      false);
    }

    Error MicrophoneController::setInputDescription(const char *description) noexcept
    {
        if (!validDescription(description))
        {
            return record(Error::invalid_argument);
        }
        NUCODE_MIC_CONTROLLER_REQUEST(set_input_description,
                                      bt_aics_description_set(input_service, description), true);
    }

#undef NUCODE_MIC_CONTROLLER_REQUEST

    bool MicrophoneController::ready() const noexcept
    {
        k_mutex_lock(&microphoneControllerBackendMutex, K_FOREVER);
        const bool value =
            started_ && ownsMicrophoneControllerLocked(this, generation_) &&
            (static_cast<AudioControlStage>(atomic_get(&microphoneControllerBackend.stage)) ==
             AudioControlStage::ready) &&
            (microphoneControllerBackend.controller != nullptr) &&
            (microphoneControllerBackend.input_service != nullptr);
        k_mutex_unlock(&microphoneControllerBackendMutex);
        return value;
    }

    bool MicrophoneController::busy() const noexcept
    {
        k_mutex_lock(&microphoneControllerBackendMutex, K_FOREVER);
        const bool value = started_ && ownsMicrophoneControllerLocked(this, generation_) &&
                           atomic_get(&microphoneControllerBackend.busy);
        k_mutex_unlock(&microphoneControllerBackendMutex);
        return value;
    }

    AudioControlStage MicrophoneController::stage() const noexcept
    {
        k_mutex_lock(&microphoneControllerBackendMutex, K_FOREVER);
        const AudioControlStage value =
            ownsMicrophoneControllerLocked(this, generation_)
                ? static_cast<AudioControlStage>(atomic_get(&microphoneControllerBackend.stage))
                : AudioControlStage::idle;
        k_mutex_unlock(&microphoneControllerBackendMutex);
        return value;
    }

    AudioControlStep MicrophoneController::lastStep() const noexcept
    {
        k_mutex_lock(&microphoneControllerBackendMutex, K_FOREVER);
        const AudioControlStep value =
            ownsMicrophoneControllerLocked(this, generation_)
                ? static_cast<AudioControlStep>(atomic_get(&microphoneControllerBackend.step))
                : AudioControlStep::none;
        k_mutex_unlock(&microphoneControllerBackendMutex);
        return value;
    }

    MicrophoneState MicrophoneController::state() const noexcept
    {
        k_mutex_lock(&microphoneControllerBackendMutex, K_FOREVER);
        const MicrophoneState value = ownsMicrophoneControllerLocked(this, generation_)
                                          ? microphoneControllerBackend.microphone
                                          : MicrophoneState{};
        k_mutex_unlock(&microphoneControllerBackendMutex);
        return value;
    }

    AudioInputState MicrophoneController::inputState() const noexcept
    {
        k_mutex_lock(&microphoneControllerBackendMutex, K_FOREVER);
        const AudioInputState value = ownsMicrophoneControllerLocked(this, generation_)
                                          ? microphoneControllerBackend.input
                                          : AudioInputState{};
        k_mutex_unlock(&microphoneControllerBackendMutex);
        return value;
    }

    std::uint32_t MicrophoneController::stateUpdates() const noexcept
    {
        k_mutex_lock(&microphoneControllerBackendMutex, K_FOREVER);
        const std::uint32_t value = ownsMicrophoneControllerLocked(this, generation_)
                                        ? microphoneControllerBackend.updates
                                        : 0U;
        k_mutex_unlock(&microphoneControllerBackendMutex);
        return value;
    }

    Error MicrophoneController::lastError() const noexcept
    {
        k_mutex_lock(&microphoneControllerBackendMutex, K_FOREVER);
        const int native = ownsMicrophoneControllerLocked(this, generation_)
                               ? static_cast<int>(atomic_get(&microphoneControllerBackend.error))
                               : 0;
        const Error fallback = last_error_;
        k_mutex_unlock(&microphoneControllerBackendMutex);
        return native == 0 ? fallback : mapNativeError(native);
    }

    int MicrophoneController::nativeCode() const noexcept
    {
        k_mutex_lock(&microphoneControllerBackendMutex, K_FOREVER);
        const int native = ownsMicrophoneControllerLocked(this, generation_)
                               ? static_cast<int>(atomic_get(&microphoneControllerBackend.error))
                               : 0;
        const int fallback = native_code_;
        k_mutex_unlock(&microphoneControllerBackendMutex);
        return native == 0 ? fallback : native;
    }

    Error MicrophoneController::record(Error error, int native_code) noexcept
    {
        k_mutex_lock(&microphoneControllerBackendMutex, K_FOREVER);
        last_error_ = error;
        native_code_ = native_code;
        k_mutex_unlock(&microphoneControllerBackendMutex);
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
