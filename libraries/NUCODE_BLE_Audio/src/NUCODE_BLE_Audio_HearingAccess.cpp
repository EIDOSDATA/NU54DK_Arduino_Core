/**
 * @file NUCODE_BLE_Audio_HearingAccess.cpp
 * @brief Hearing Access Service server와 client 공개 API를 구현합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include "NUCODE_BLE_Audio.h"

#if !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE) &&                                                   \
    (defined(CONFIG_BT_HAS) || defined(CONFIG_BT_HAS_CLIENT))

#include <NUCODE_BLE.h>
#include <internal/NUCODE_BLE_Internal.h>

#include <zephyr/bluetooth/audio/has.h>
#include <zephyr/bluetooth/conn.h>
#include <zephyr/kernel.h>

#include <errno.h>
#include <string.h>

namespace nucode::ble::audio
{
    namespace
    {
        constexpr std::size_t maximumServerPresets = 8U;
        constexpr std::size_t maximumClientPresets = 8U;

        /** @brief Zephyr HAS 반환값을 공개 오류로 변환합니다. */
        Error mapNativeError(int error) noexcept
        {
            if (error == 0)
            {
                return Error::none;
            }
            if ((error == -EINVAL) || (error == -ERANGE))
            {
                return Error::invalid_argument;
            }
            if (error == -EALREADY)
            {
                return Error::already_started;
            }
            if ((error == -EBUSY) || (error == -EINPROGRESS))
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

        /** @brief HAS preset 이름을 공개 고정 buffer로 복사합니다. */
        bool copyPresetName(char (&destination)[HearingPreset::maximum_name_bytes + 1U],
                            const char *source) noexcept
        {
            if (source == nullptr)
            {
                return false;
            }
            const std::size_t length = strnlen(source, HearingPreset::maximum_name_bytes + 1U);
            if ((length == 0U) || (length > HearingPreset::maximum_name_bytes))
            {
                return false;
            }
            (void)memcpy(destination, source, length);
            destination[length] = '\0';
            return true;
        }

#if defined(CONFIG_BT_HAS)
        /** @brief image 수명 동안 유지하는 HAS server 상태입니다. */
        struct HearingServerBackend
        {
            HearingAccessServer *owner = nullptr;
            HearingAccessServerConfig config = {};
            HearingPreset presets[maximumServerPresets] = {};
            std::size_t preset_count = 0U;
            std::uint8_t active_index = 0U;
            std::uint32_t selection_changes = 0U;
            bool service_registered = false;
        };

        HearingServerBackend serverBackend;
        K_MUTEX_DEFINE(serverMutex);

        /** @brief 공개 보청기 형식을 Zephyr 형식으로 변환합니다. */
        enum bt_has_hearing_aid_type nativeHearingAidType(HearingAidType type) noexcept
        {
            switch (type)
            {
            case HearingAidType::binaural:
                return BT_HAS_HEARING_AID_TYPE_BINAURAL;
            case HearingAidType::monaural:
                return BT_HAS_HEARING_AID_TYPE_MONAURAL;
            case HearingAidType::banded:
                return BT_HAS_HEARING_AID_TYPE_BANDED;
            default:
                return BT_HAS_HEARING_AID_TYPE_MONAURAL;
            }
        }

        /** @brief server 설정이 HAS 제약과 일치하는지 확인합니다. */
        bool validServerConfig(const HearingAccessServerConfig &config) noexcept
        {
            const auto type = static_cast<std::uint8_t>(config.type);
            if (type > static_cast<std::uint8_t>(HearingAidType::banded))
            {
                return false;
            }
            if ((config.preset_synchronization || config.independent_presets) &&
                (config.type != HearingAidType::binaural))
            {
                return false;
            }
            return true;
        }

        /** @brief image-lifetime HAS 설정이 최초 등록 설정과 같은지 확인합니다. */
        bool sameServerConfig(const HearingAccessServerConfig &left,
                              const HearingAccessServerConfig &right) noexcept
        {
            return (left.type == right.type) &&
                   (left.preset_synchronization == right.preset_synchronization) &&
                   (left.independent_presets == right.independent_presets);
        }

        /** @brief preset index를 server 공개 cache에서 찾습니다. */
        HearingPreset *findServerPreset(std::uint8_t index) noexcept
        {
            for (std::size_t position = 0U; position < serverBackend.preset_count; ++position)
            {
                if (serverBackend.presets[position].index == index)
                {
                    return &serverBackend.presets[position];
                }
            }
            return nullptr;
        }

        /** @brief 원격 preset 선택을 공개 상태에 반영합니다. */
        int serverPresetSelected(std::uint8_t index, bool) noexcept
        {
            k_mutex_lock(&serverMutex, K_FOREVER);
            HearingPreset *preset = findServerPreset(index);
            if ((serverBackend.owner == nullptr) || (preset == nullptr) || !preset->available)
            {
                k_mutex_unlock(&serverMutex);
                return -EBUSY;
            }
            serverBackend.active_index = index;
            ++serverBackend.selection_changes;
            k_mutex_unlock(&serverMutex);
            return 0;
        }

        /** @brief 원격 이름 변경을 공개 preset cache에 반영합니다. */
        void serverPresetNameChanged(std::uint8_t index, const char *name) noexcept
        {
            k_mutex_lock(&serverMutex, K_FOREVER);
            HearingPreset *preset = findServerPreset(index);
            if ((serverBackend.owner != nullptr) && (preset != nullptr))
            {
                (void)copyPresetName(preset->name, name);
            }
            k_mutex_unlock(&serverMutex);
        }

        const struct bt_has_preset_ops serverPresetOperations = {
            .select = serverPresetSelected,
            .name_changed = serverPresetNameChanged,
        };
#endif

#if defined(CONFIG_BT_HAS_CLIENT)
        /** @brief 한 client 객체가 소유하는 고정 HAS 검색 상태입니다. */
        struct HearingClientBackend
        {
            HearingAccessClient *owner = nullptr;
            BLEConnectionHandle handle = {};
            struct bt_conn *connection = nullptr;
            struct bt_has *service = nullptr;
            HearingPreset presets[maximumClientPresets] = {};
            std::size_t preset_count = 0U;
            std::uint32_t generation = 0U;
            std::uint32_t updates = 0U;
            HearingAccessStage stage = HearingAccessStage::idle;
            HearingAccessStep step = HearingAccessStep::none;
            std::uint8_t active_index = 0U;
            int error = 0;
            bool busy = false;
            bool callbacks_registered = false;
        };

        HearingClientBackend clientBackend;
        K_MUTEX_DEFINE(clientMutex);

        /** @brief callback record를 고정 client cache에 추가하거나 교체합니다. */
        bool storeClientPreset(const struct bt_has_preset_record *record) noexcept
        {
            if ((record == nullptr) || (record->index == 0U))
            {
                return false;
            }
            HearingPreset *target = nullptr;
            for (std::size_t position = 0U; position < clientBackend.preset_count; ++position)
            {
                if (clientBackend.presets[position].index == record->index)
                {
                    target = &clientBackend.presets[position];
                    break;
                }
            }
            if (target == nullptr)
            {
                if (clientBackend.preset_count >= maximumClientPresets)
                {
                    return false;
                }
                target = &clientBackend.presets[clientBackend.preset_count++];
            }
            HearingPreset value = {};
            value.index = record->index;
            value.available = (record->properties & BT_HAS_PROP_AVAILABLE) != 0;
            value.writable = (record->properties & BT_HAS_PROP_WRITABLE) != 0;
            if (!copyPresetName(value.name, record->name))
            {
                return false;
            }
            *target = value;
            ++clientBackend.updates;
            return true;
        }

        /** @brief HAS discovery 완료를 현재 client generation에 반영합니다. */
        void clientDiscovered(struct bt_conn *connection, int error, struct bt_has *service,
                              enum bt_has_hearing_aid_type, enum bt_has_capabilities) noexcept
        {
            k_mutex_lock(&clientMutex, K_FOREVER);
            if ((clientBackend.owner == nullptr) || (clientBackend.connection != connection))
            {
                k_mutex_unlock(&clientMutex);
                return;
            }
            clientBackend.error = error;
            clientBackend.service = error == 0 ? service : nullptr;
            clientBackend.busy = false;
            clientBackend.stage =
                error == 0 ? HearingAccessStage::ready : HearingAccessStage::failed;
            if (error == 0)
            {
                ++clientBackend.updates;
            }
            k_mutex_unlock(&clientMutex);
        }

        /** @brief 활성 preset 변경 완료를 현재 client에 반영합니다. */
        void clientPresetSwitched(struct bt_has *service, int error, std::uint8_t index) noexcept
        {
            k_mutex_lock(&clientMutex, K_FOREVER);
            if ((clientBackend.owner == nullptr) || (clientBackend.service != service))
            {
                k_mutex_unlock(&clientMutex);
                return;
            }
            clientBackend.error = error;
            clientBackend.busy = false;
            clientBackend.stage =
                error == 0 ? HearingAccessStage::ready : HearingAccessStage::failed;
            if (error == 0)
            {
                clientBackend.active_index = index;
                ++clientBackend.updates;
            }
            k_mutex_unlock(&clientMutex);
        }

        /** @brief preset read 응답을 고정 client cache에 복사합니다. */
        void clientPresetRead(struct bt_has *service, int error,
                              const struct bt_has_preset_record *record, bool is_last) noexcept
        {
            k_mutex_lock(&clientMutex, K_FOREVER);
            if ((clientBackend.owner == nullptr) || (clientBackend.service != service))
            {
                k_mutex_unlock(&clientMutex);
                return;
            }
            if ((error == 0) && (record != nullptr) && !storeClientPreset(record))
            {
                error = -ENOMEM;
            }
            clientBackend.error = error;
            if ((error != 0) || is_last)
            {
                clientBackend.busy = false;
                clientBackend.stage =
                    error == 0 ? HearingAccessStage::ready : HearingAccessStage::failed;
            }
            k_mutex_unlock(&clientMutex);
        }

        /** @brief preset update 알림을 고정 client cache에 복사합니다. */
        void clientPresetUpdated(struct bt_has *service, std::uint8_t,
                                 const struct bt_has_preset_record *record, bool) noexcept
        {
            k_mutex_lock(&clientMutex, K_FOREVER);
            if ((clientBackend.owner != nullptr) && (clientBackend.service == service) &&
                !storeClientPreset(record))
            {
                clientBackend.error = -ENOMEM;
                clientBackend.stage = HearingAccessStage::failed;
            }
            k_mutex_unlock(&clientMutex);
        }

        /** @brief 삭제 알림의 preset을 고정 client cache에서 제거합니다. */
        void clientPresetDeleted(struct bt_has *service, std::uint8_t index, bool) noexcept
        {
            k_mutex_lock(&clientMutex, K_FOREVER);
            if ((clientBackend.owner == nullptr) || (clientBackend.service != service))
            {
                k_mutex_unlock(&clientMutex);
                return;
            }
            for (std::size_t position = 0U; position < clientBackend.preset_count; ++position)
            {
                if (clientBackend.presets[position].index == index)
                {
                    for (std::size_t next = position + 1U; next < clientBackend.preset_count;
                         ++next)
                    {
                        clientBackend.presets[next - 1U] = clientBackend.presets[next];
                    }
                    --clientBackend.preset_count;
                    clientBackend.presets[clientBackend.preset_count] = {};
                    ++clientBackend.updates;
                    break;
                }
            }
            k_mutex_unlock(&clientMutex);
        }

        /** @brief availability 알림을 고정 client cache에 반영합니다. */
        void clientPresetAvailability(struct bt_has *service, std::uint8_t index, bool available,
                                      bool) noexcept
        {
            k_mutex_lock(&clientMutex, K_FOREVER);
            if ((clientBackend.owner != nullptr) && (clientBackend.service == service))
            {
                for (std::size_t position = 0U; position < clientBackend.preset_count; ++position)
                {
                    if (clientBackend.presets[position].index == index)
                    {
                        clientBackend.presets[position].available = available;
                        ++clientBackend.updates;
                        break;
                    }
                }
            }
            k_mutex_unlock(&clientMutex);
        }

        const struct bt_has_client_cb clientCallbacks = {
            .discover = clientDiscovered,
            .preset_switch = clientPresetSwitched,
            .preset_read_rsp = clientPresetRead,
            .preset_update = clientPresetUpdated,
            .preset_deleted = clientPresetDeleted,
            .preset_availability = clientPresetAvailability,
        };
#endif
    } // namespace

#if defined(CONFIG_BT_HAS)
    Error HearingAccessServer::begin(const HearingAccessServerConfig &config) noexcept
    {
        if (!validServerConfig(config))
        {
            return record(Error::invalid_argument, -EINVAL);
        }
        k_mutex_lock(&serverMutex, K_FOREVER);
        if (started_)
        {
            k_mutex_unlock(&serverMutex);
            return record(Error::already_started, -EALREADY);
        }
        if (serverBackend.owner != nullptr)
        {
            k_mutex_unlock(&serverMutex);
            return record(Error::busy, -EBUSY);
        }
        if (serverBackend.service_registered && !sameServerConfig(serverBackend.config, config))
        {
            k_mutex_unlock(&serverMutex);
            return record(Error::unsupported, -ENOTSUP);
        }
        const bool register_service = !serverBackend.service_registered;
        k_mutex_unlock(&serverMutex);

        if (register_service)
        {
            const struct bt_has_features_param features = {
                .type = nativeHearingAidType(config.type),
                .preset_sync_support = config.preset_synchronization,
                .independent_presets = config.independent_presets,
            };
            const int result = bt_has_register(&features);
            if (result != 0)
            {
                return record(mapNativeError(result), result);
            }
        }

        k_mutex_lock(&serverMutex, K_FOREVER);
        if (serverBackend.owner != nullptr)
        {
            k_mutex_unlock(&serverMutex);
            return record(Error::busy, -EBUSY);
        }
        serverBackend.owner = this;
        serverBackend.config = config;
        serverBackend.service_registered = true;
        serverBackend.active_index = bt_has_preset_active_get();
        started_ = true;
        k_mutex_unlock(&serverMutex);
        return record(Error::none);
    }

    Error HearingAccessServer::end() noexcept
    {
        k_mutex_lock(&serverMutex, K_FOREVER);
        if (!started_ || (serverBackend.owner != this))
        {
            k_mutex_unlock(&serverMutex);
            return record(Error::not_started);
        }
        std::uint8_t indexes[maximumServerPresets] = {};
        const std::size_t count = serverBackend.preset_count;
        for (std::size_t position = 0U; position < count; ++position)
        {
            indexes[position] = serverBackend.presets[position].index;
        }
        k_mutex_unlock(&serverMutex);

        for (std::size_t position = 0U; position < count; ++position)
        {
            const int result = bt_has_preset_unregister(indexes[position]);
            if ((result != 0) && (result != -ENOENT))
            {
                return record(mapNativeError(result), result);
            }
        }
        (void)bt_has_preset_active_clear();

        k_mutex_lock(&serverMutex, K_FOREVER);
        serverBackend.owner = nullptr;
        serverBackend.preset_count = 0U;
        serverBackend.active_index = 0U;
        (void)memset(serverBackend.presets, 0, sizeof(serverBackend.presets));
        started_ = false;
        k_mutex_unlock(&serverMutex);
        return record(Error::none);
    }

    Error HearingAccessServer::addPreset(std::uint8_t index, const char *name, bool writable,
                                         bool available) noexcept
    {
        HearingPreset value = {};
        value.index = index;
        value.writable = writable;
        value.available = available;
        if ((index == 0U) || !copyPresetName(value.name, name))
        {
            return record(Error::invalid_argument, -EINVAL);
        }
#if !defined(CONFIG_BT_HAS_PRESET_NAME_DYNAMIC)
        if (writable)
        {
            return record(Error::unsupported, -ENOTSUP);
        }
#endif
        k_mutex_lock(&serverMutex, K_FOREVER);
        if (!started_ || (serverBackend.owner != this))
        {
            k_mutex_unlock(&serverMutex);
            return record(Error::not_started);
        }
        if (findServerPreset(index) != nullptr)
        {
            k_mutex_unlock(&serverMutex);
            return record(Error::already_started, -EALREADY);
        }
        if (serverBackend.preset_count >= maximumServerPresets)
        {
            k_mutex_unlock(&serverMutex);
            return record(Error::buffer_too_small, -ENOMEM);
        }
        k_mutex_unlock(&serverMutex);

        enum bt_has_properties properties = BT_HAS_PROP_NONE;
        if (writable)
        {
            properties = static_cast<enum bt_has_properties>(properties | BT_HAS_PROP_WRITABLE);
        }
        if (available)
        {
            properties = static_cast<enum bt_has_properties>(properties | BT_HAS_PROP_AVAILABLE);
        }
        const struct bt_has_preset_register_param parameters = {
            .index = index,
            .properties = properties,
            .name = value.name,
            .ops = &serverPresetOperations,
        };
        const int result = bt_has_preset_register(&parameters);
        if (result != 0)
        {
            return record(mapNativeError(result), result);
        }

        k_mutex_lock(&serverMutex, K_FOREVER);
        serverBackend.presets[serverBackend.preset_count++] = value;
        k_mutex_unlock(&serverMutex);
        return record(Error::none);
    }

    Error HearingAccessServer::setActivePreset(std::uint8_t index) noexcept
    {
        k_mutex_lock(&serverMutex, K_FOREVER);
        HearingPreset *preset = findServerPreset(index);
        const bool valid =
            started_ && (serverBackend.owner == this) && (preset != nullptr) && preset->available;
        k_mutex_unlock(&serverMutex);
        if (!valid)
        {
            return record(Error::invalid_argument, -EINVAL);
        }
        const int result = bt_has_preset_active_set(index);
        if (result != 0)
        {
            return record(mapNativeError(result), result);
        }
        k_mutex_lock(&serverMutex, K_FOREVER);
        serverBackend.active_index = index;
        ++serverBackend.selection_changes;
        k_mutex_unlock(&serverMutex);
        return record(Error::none);
    }

    Error HearingAccessServer::setPresetAvailable(std::uint8_t index, bool available) noexcept
    {
        k_mutex_lock(&serverMutex, K_FOREVER);
        HearingPreset *preset = findServerPreset(index);
        if (!started_ || (serverBackend.owner != this) || (preset == nullptr))
        {
            k_mutex_unlock(&serverMutex);
            return record(Error::invalid_argument, -EINVAL);
        }
        if (preset->available == available)
        {
            k_mutex_unlock(&serverMutex);
            return record(Error::none);
        }
        k_mutex_unlock(&serverMutex);
        const int result =
            available ? bt_has_preset_available(index) : bt_has_preset_unavailable(index);
        if (result != 0)
        {
            return record(mapNativeError(result), result);
        }
        k_mutex_lock(&serverMutex, K_FOREVER);
        preset = findServerPreset(index);
        if (preset != nullptr)
        {
            preset->available = available;
        }
        k_mutex_unlock(&serverMutex);
        return record(Error::none);
    }

    Error HearingAccessServer::renamePreset(std::uint8_t index, const char *name) noexcept
    {
        char copied[HearingPreset::maximum_name_bytes + 1U] = {};
        if (!copyPresetName(copied, name))
        {
            return record(Error::invalid_argument, -EINVAL);
        }
        k_mutex_lock(&serverMutex, K_FOREVER);
        HearingPreset *preset = findServerPreset(index);
        if (!started_ || (serverBackend.owner != this) || (preset == nullptr))
        {
            k_mutex_unlock(&serverMutex);
            return record(Error::invalid_argument, -EINVAL);
        }
        if (!preset->writable)
        {
            k_mutex_unlock(&serverMutex);
            return record(Error::unsupported, -ENOTSUP);
        }
        k_mutex_unlock(&serverMutex);
        const int result = bt_has_preset_name_change(index, copied);
        if (result != 0)
        {
            return record(mapNativeError(result), result);
        }
        k_mutex_lock(&serverMutex, K_FOREVER);
        preset = findServerPreset(index);
        if (preset != nullptr)
        {
            (void)copyPresetName(preset->name, copied);
        }
        k_mutex_unlock(&serverMutex);
        return record(Error::none);
    }

    std::uint8_t HearingAccessServer::activePreset() const noexcept
    {
        k_mutex_lock(&serverMutex, K_FOREVER);
        const std::uint8_t value =
            started_ && (serverBackend.owner == this) ? serverBackend.active_index : 0U;
        k_mutex_unlock(&serverMutex);
        return value;
    }

    std::size_t HearingAccessServer::presetCount() const noexcept
    {
        k_mutex_lock(&serverMutex, K_FOREVER);
        const std::size_t value =
            started_ && (serverBackend.owner == this) ? serverBackend.preset_count : 0U;
        k_mutex_unlock(&serverMutex);
        return value;
    }

    Error HearingAccessServer::preset(std::size_t position, HearingPreset &value) const noexcept
    {
        k_mutex_lock(&serverMutex, K_FOREVER);
        if (!started_ || (serverBackend.owner != this))
        {
            k_mutex_unlock(&serverMutex);
            return Error::not_started;
        }
        if (position >= serverBackend.preset_count)
        {
            k_mutex_unlock(&serverMutex);
            return Error::invalid_argument;
        }
        value = serverBackend.presets[position];
        k_mutex_unlock(&serverMutex);
        return Error::none;
    }

    std::uint32_t HearingAccessServer::selectionChanges() const noexcept
    {
        k_mutex_lock(&serverMutex, K_FOREVER);
        const std::uint32_t value =
            started_ && (serverBackend.owner == this) ? serverBackend.selection_changes : 0U;
        k_mutex_unlock(&serverMutex);
        return value;
    }
#else
    Error HearingAccessServer::begin(const HearingAccessServerConfig &) noexcept
    {
        return record(Error::unsupported, -ENOTSUP);
    }
    Error HearingAccessServer::end() noexcept
    {
        return record(Error::not_started);
    }
    Error HearingAccessServer::addPreset(std::uint8_t, const char *, bool, bool) noexcept
    {
        return record(Error::unsupported, -ENOTSUP);
    }
    Error HearingAccessServer::setActivePreset(std::uint8_t) noexcept
    {
        return record(Error::unsupported, -ENOTSUP);
    }
    Error HearingAccessServer::setPresetAvailable(std::uint8_t, bool) noexcept
    {
        return record(Error::unsupported, -ENOTSUP);
    }
    Error HearingAccessServer::renamePreset(std::uint8_t, const char *) noexcept
    {
        return record(Error::unsupported, -ENOTSUP);
    }
    std::uint8_t HearingAccessServer::activePreset() const noexcept
    {
        return 0U;
    }
    std::size_t HearingAccessServer::presetCount() const noexcept
    {
        return 0U;
    }
    Error HearingAccessServer::preset(std::size_t, HearingPreset &) const noexcept
    {
        return Error::unsupported;
    }
    std::uint32_t HearingAccessServer::selectionChanges() const noexcept
    {
        return 0U;
    }
#endif

    Error HearingAccessServer::lastError() const noexcept
    {
        return last_error_;
    }

    int HearingAccessServer::nativeCode() const noexcept
    {
        return native_code_;
    }

    Error HearingAccessServer::record(Error error, int native_code) noexcept
    {
        last_error_ = error;
        native_code_ = native_code;
        return error;
    }

#if defined(CONFIG_BT_HAS_CLIENT)
    Error HearingAccessClient::begin(const BLEConnectionHandle &connection) noexcept
    {
        if (!connection.valid())
        {
            return record(Error::invalid_argument, -EINVAL);
        }
        struct bt_conn *native = internal::referenceConnection(connection);
        if (native == nullptr)
        {
            return record(Error::not_connected, -ENOTCONN);
        }
        k_mutex_lock(&clientMutex, K_FOREVER);
        if (started_)
        {
            k_mutex_unlock(&clientMutex);
            bt_conn_unref(native);
            return record(Error::already_started, -EALREADY);
        }
        if (clientBackend.owner != nullptr)
        {
            k_mutex_unlock(&clientMutex);
            bt_conn_unref(native);
            return record(Error::busy, -EBUSY);
        }
        const bool register_callbacks = !clientBackend.callbacks_registered;
        k_mutex_unlock(&clientMutex);
        if (register_callbacks)
        {
            const int callback_result = bt_has_client_cb_register(&clientCallbacks);
            if ((callback_result != 0) && (callback_result != -EALREADY))
            {
                bt_conn_unref(native);
                return record(mapNativeError(callback_result), callback_result);
            }
        }

        k_mutex_lock(&clientMutex, K_FOREVER);
        ++clientBackend.generation;
        if (clientBackend.generation == 0U)
        {
            ++clientBackend.generation;
        }
        clientBackend.owner = this;
        clientBackend.handle = connection;
        clientBackend.connection = native;
        clientBackend.service = nullptr;
        clientBackend.preset_count = 0U;
        clientBackend.updates = 0U;
        clientBackend.active_index = 0U;
        clientBackend.error = 0;
        clientBackend.busy = true;
        clientBackend.callbacks_registered = true;
        clientBackend.stage = HearingAccessStage::discovering;
        clientBackend.step = HearingAccessStep::discover;
        (void)memset(clientBackend.presets, 0, sizeof(clientBackend.presets));
        started_ = true;
        generation_ = clientBackend.generation;
        k_mutex_unlock(&clientMutex);

        const int result = bt_has_client_discover(native);
        if (result != 0)
        {
            k_mutex_lock(&clientMutex, K_FOREVER);
            if ((clientBackend.owner == this) && (clientBackend.generation == generation_))
            {
                clientBackend.owner = nullptr;
                clientBackend.connection = nullptr;
                clientBackend.busy = false;
                clientBackend.error = result;
                clientBackend.stage = HearingAccessStage::failed;
            }
            started_ = false;
            k_mutex_unlock(&clientMutex);
            bt_conn_unref(native);
            return record(mapNativeError(result), result);
        }
        return record(Error::none);
    }

    void HearingAccessClient::poll() noexcept
    {
        k_mutex_lock(&clientMutex, K_FOREVER);
        const bool owned =
            started_ && (clientBackend.owner == this) && (clientBackend.generation == generation_);
        const BLEConnectionHandle handle = clientBackend.handle;
        k_mutex_unlock(&clientMutex);
        if (!owned)
        {
            return;
        }
        struct bt_conn *current = internal::referenceConnection(handle);
        if (current != nullptr)
        {
            bt_conn_unref(current);
            return;
        }
        k_mutex_lock(&clientMutex, K_FOREVER);
        if ((clientBackend.owner == this) && (clientBackend.generation == generation_))
        {
            clientBackend.busy = false;
            clientBackend.error = -ENOTCONN;
            clientBackend.stage = HearingAccessStage::disconnected;
        }
        k_mutex_unlock(&clientMutex);
    }

    Error HearingAccessClient::end() noexcept
    {
        k_mutex_lock(&clientMutex, K_FOREVER);
        if (!started_ || (clientBackend.owner != this) || (clientBackend.generation != generation_))
        {
            k_mutex_unlock(&clientMutex);
            return record(Error::not_started);
        }
        struct bt_conn *connection = clientBackend.connection;
        clientBackend.owner = nullptr;
        clientBackend.handle = {};
        clientBackend.connection = nullptr;
        clientBackend.service = nullptr;
        clientBackend.preset_count = 0U;
        clientBackend.busy = false;
        clientBackend.stage = HearingAccessStage::idle;
        clientBackend.step = HearingAccessStep::cleanup;
        ++clientBackend.generation;
        started_ = false;
        generation_ = 0U;
        k_mutex_unlock(&clientMutex);
        if (connection != nullptr)
        {
            bt_conn_unref(connection);
        }
        return record(Error::none);
    }

    Error HearingAccessClient::readPresets(std::uint8_t start_index,
                                           std::uint8_t maximum_count) noexcept
    {
        if ((start_index == 0U) || (maximum_count == 0U))
        {
            return record(Error::invalid_argument, -EINVAL);
        }
        k_mutex_lock(&clientMutex, K_FOREVER);
        if (!started_ || (clientBackend.owner != this) || (clientBackend.generation != generation_))
        {
            k_mutex_unlock(&clientMutex);
            return record(Error::not_started);
        }
        if ((clientBackend.stage != HearingAccessStage::ready) || clientBackend.busy ||
            (clientBackend.service == nullptr))
        {
            k_mutex_unlock(&clientMutex);
            return record(Error::busy, -EBUSY);
        }
        struct bt_has *service = clientBackend.service;
        clientBackend.preset_count = 0U;
        clientBackend.busy = true;
        clientBackend.stage = HearingAccessStage::operating;
        clientBackend.step = HearingAccessStep::read_presets;
        k_mutex_unlock(&clientMutex);
        const int result = bt_has_client_presets_read(service, start_index, maximum_count);
        if (result != 0)
        {
            k_mutex_lock(&clientMutex, K_FOREVER);
            clientBackend.busy = false;
            clientBackend.error = result;
            clientBackend.stage = HearingAccessStage::failed;
            k_mutex_unlock(&clientMutex);
        }
        return record(mapNativeError(result), result);
    }

    /** @brief 공통 preset 전환 요청의 상태와 즉시 오류를 처리합니다. */
    template <typename Request>
    Error requestPresetChange(HearingAccessClient *owner, std::uint32_t generation,
                              HearingAccessStep step, Request request, Error &last_error,
                              int &native_code) noexcept
    {
        k_mutex_lock(&clientMutex, K_FOREVER);
        if ((clientBackend.owner != owner) || (clientBackend.generation != generation))
        {
            k_mutex_unlock(&clientMutex);
            last_error = Error::not_started;
            native_code = 0;
            return last_error;
        }
        if ((clientBackend.stage != HearingAccessStage::ready) || clientBackend.busy ||
            (clientBackend.service == nullptr))
        {
            k_mutex_unlock(&clientMutex);
            last_error = Error::busy;
            native_code = -EBUSY;
            return last_error;
        }
        struct bt_has *service = clientBackend.service;
        clientBackend.busy = true;
        clientBackend.stage = HearingAccessStage::operating;
        clientBackend.step = step;
        k_mutex_unlock(&clientMutex);
        const int result = request(service);
        if (result != 0)
        {
            k_mutex_lock(&clientMutex, K_FOREVER);
            clientBackend.busy = false;
            clientBackend.error = result;
            clientBackend.stage = HearingAccessStage::failed;
            k_mutex_unlock(&clientMutex);
        }
        last_error = mapNativeError(result);
        native_code = result;
        return last_error;
    }

    Error HearingAccessClient::setActivePreset(std::uint8_t index, bool synchronize) noexcept
    {
        if (index == 0U)
        {
            return record(Error::invalid_argument, -EINVAL);
        }
        return requestPresetChange(
            this, generation_, HearingAccessStep::set_active,
            [index, synchronize](struct bt_has *service)
            {
                return bt_has_client_preset_set(service, index, synchronize);
            },
            last_error_, native_code_);
    }

    Error HearingAccessClient::nextPreset(bool synchronize) noexcept
    {
        return requestPresetChange(
            this, generation_, HearingAccessStep::next,
            [synchronize](struct bt_has *service)
            {
                return bt_has_client_preset_next(service, synchronize);
            },
            last_error_, native_code_);
    }

    Error HearingAccessClient::previousPreset(bool synchronize) noexcept
    {
        return requestPresetChange(
            this, generation_, HearingAccessStep::previous,
            [synchronize](struct bt_has *service)
            {
                return bt_has_client_preset_prev(service, synchronize);
            },
            last_error_, native_code_);
    }

    bool HearingAccessClient::ready() const noexcept
    {
        return stage() == HearingAccessStage::ready;
    }

    bool HearingAccessClient::busy() const noexcept
    {
        k_mutex_lock(&clientMutex, K_FOREVER);
        const bool value = started_ && (clientBackend.owner == this) &&
                           (clientBackend.generation == generation_) && clientBackend.busy;
        k_mutex_unlock(&clientMutex);
        return value;
    }

    HearingAccessStage HearingAccessClient::stage() const noexcept
    {
        k_mutex_lock(&clientMutex, K_FOREVER);
        const HearingAccessStage value =
            started_ && (clientBackend.owner == this) && (clientBackend.generation == generation_)
                ? clientBackend.stage
                : HearingAccessStage::idle;
        k_mutex_unlock(&clientMutex);
        return value;
    }

    HearingAccessStep HearingAccessClient::lastStep() const noexcept
    {
        k_mutex_lock(&clientMutex, K_FOREVER);
        const HearingAccessStep value =
            started_ && (clientBackend.owner == this) && (clientBackend.generation == generation_)
                ? clientBackend.step
                : HearingAccessStep::none;
        k_mutex_unlock(&clientMutex);
        return value;
    }

    std::uint8_t HearingAccessClient::activePreset() const noexcept
    {
        k_mutex_lock(&clientMutex, K_FOREVER);
        const std::uint8_t value =
            started_ && (clientBackend.owner == this) && (clientBackend.generation == generation_)
                ? clientBackend.active_index
                : 0U;
        k_mutex_unlock(&clientMutex);
        return value;
    }

    std::size_t HearingAccessClient::presetCount() const noexcept
    {
        k_mutex_lock(&clientMutex, K_FOREVER);
        const std::size_t value =
            started_ && (clientBackend.owner == this) && (clientBackend.generation == generation_)
                ? clientBackend.preset_count
                : 0U;
        k_mutex_unlock(&clientMutex);
        return value;
    }

    Error HearingAccessClient::preset(std::size_t position, HearingPreset &value) const noexcept
    {
        k_mutex_lock(&clientMutex, K_FOREVER);
        if (!started_ || (clientBackend.owner != this) || (clientBackend.generation != generation_))
        {
            k_mutex_unlock(&clientMutex);
            return Error::not_started;
        }
        if (position >= clientBackend.preset_count)
        {
            k_mutex_unlock(&clientMutex);
            return Error::invalid_argument;
        }
        value = clientBackend.presets[position];
        k_mutex_unlock(&clientMutex);
        return Error::none;
    }

    std::uint32_t HearingAccessClient::stateUpdates() const noexcept
    {
        k_mutex_lock(&clientMutex, K_FOREVER);
        const std::uint32_t value =
            started_ && (clientBackend.owner == this) && (clientBackend.generation == generation_)
                ? clientBackend.updates
                : 0U;
        k_mutex_unlock(&clientMutex);
        return value;
    }

    Error HearingAccessClient::lastError() const noexcept
    {
        k_mutex_lock(&clientMutex, K_FOREVER);
        const int native =
            started_ && (clientBackend.owner == this) && (clientBackend.generation == generation_)
                ? clientBackend.error
                : 0;
        k_mutex_unlock(&clientMutex);
        return native == 0 ? last_error_ : mapNativeError(native);
    }

    int HearingAccessClient::nativeCode() const noexcept
    {
        k_mutex_lock(&clientMutex, K_FOREVER);
        const int native =
            started_ && (clientBackend.owner == this) && (clientBackend.generation == generation_)
                ? clientBackend.error
                : 0;
        k_mutex_unlock(&clientMutex);
        return native == 0 ? native_code_ : native;
    }
#else
    Error HearingAccessClient::begin(const BLEConnectionHandle &) noexcept
    {
        return record(Error::unsupported, -ENOTSUP);
    }
    void HearingAccessClient::poll() noexcept
    {
    }
    Error HearingAccessClient::end() noexcept
    {
        return record(Error::not_started);
    }
    Error HearingAccessClient::readPresets(std::uint8_t, std::uint8_t) noexcept
    {
        return record(Error::unsupported, -ENOTSUP);
    }
    Error HearingAccessClient::setActivePreset(std::uint8_t, bool) noexcept
    {
        return record(Error::unsupported, -ENOTSUP);
    }
    Error HearingAccessClient::nextPreset(bool) noexcept
    {
        return record(Error::unsupported, -ENOTSUP);
    }
    Error HearingAccessClient::previousPreset(bool) noexcept
    {
        return record(Error::unsupported, -ENOTSUP);
    }
    bool HearingAccessClient::ready() const noexcept
    {
        return false;
    }
    bool HearingAccessClient::busy() const noexcept
    {
        return false;
    }
    HearingAccessStage HearingAccessClient::stage() const noexcept
    {
        return HearingAccessStage::idle;
    }
    HearingAccessStep HearingAccessClient::lastStep() const noexcept
    {
        return HearingAccessStep::none;
    }
    std::uint8_t HearingAccessClient::activePreset() const noexcept
    {
        return 0U;
    }
    std::size_t HearingAccessClient::presetCount() const noexcept
    {
        return 0U;
    }
    Error HearingAccessClient::preset(std::size_t, HearingPreset &) const noexcept
    {
        return Error::unsupported;
    }
    std::uint32_t HearingAccessClient::stateUpdates() const noexcept
    {
        return 0U;
    }
    Error HearingAccessClient::lastError() const noexcept
    {
        return last_error_;
    }
    int HearingAccessClient::nativeCode() const noexcept
    {
        return native_code_;
    }
#endif

    Error HearingAccessClient::record(Error error, int native_code) noexcept
    {
        last_error_ = error;
        native_code_ = native_code;
        return error;
    }
} // namespace nucode::ble::audio

#else

namespace nucode::ble::audio
{
#define NUCODE_HEARING_SERVER_FALLBACK(name, signature)                                            \
    Error HearingAccessServer::name signature noexcept                                             \
    {                                                                                              \
        return record(Error::unsupported);                                                         \
    }
    NUCODE_HEARING_SERVER_FALLBACK(begin, (const HearingAccessServerConfig &))
    Error HearingAccessServer::end() noexcept
    {
        return record(Error::not_started);
    }
    NUCODE_HEARING_SERVER_FALLBACK(addPreset, (std::uint8_t, const char *, bool, bool))
    NUCODE_HEARING_SERVER_FALLBACK(setActivePreset, (std::uint8_t))
    NUCODE_HEARING_SERVER_FALLBACK(setPresetAvailable, (std::uint8_t, bool))
    NUCODE_HEARING_SERVER_FALLBACK(renamePreset, (std::uint8_t, const char *))
#undef NUCODE_HEARING_SERVER_FALLBACK
    std::uint8_t HearingAccessServer::activePreset() const noexcept
    {
        return 0U;
    }
    std::size_t HearingAccessServer::presetCount() const noexcept
    {
        return 0U;
    }
    Error HearingAccessServer::preset(std::size_t, HearingPreset &) const noexcept
    {
        return Error::unsupported;
    }
    std::uint32_t HearingAccessServer::selectionChanges() const noexcept
    {
        return 0U;
    }
    Error HearingAccessServer::lastError() const noexcept
    {
        return last_error_;
    }
    int HearingAccessServer::nativeCode() const noexcept
    {
        return native_code_;
    }
    Error HearingAccessServer::record(Error error, int native_code) noexcept
    {
        last_error_ = error;
        native_code_ = native_code;
        return error;
    }

#define NUCODE_HEARING_CLIENT_FALLBACK(name, signature)                                            \
    Error HearingAccessClient::name signature noexcept                                             \
    {                                                                                              \
        return record(Error::unsupported);                                                         \
    }
    NUCODE_HEARING_CLIENT_FALLBACK(begin, (const BLEConnectionHandle &))
    void HearingAccessClient::poll() noexcept
    {
    }
    Error HearingAccessClient::end() noexcept
    {
        return record(Error::not_started);
    }
    NUCODE_HEARING_CLIENT_FALLBACK(readPresets, (std::uint8_t, std::uint8_t))
    NUCODE_HEARING_CLIENT_FALLBACK(setActivePreset, (std::uint8_t, bool))
    NUCODE_HEARING_CLIENT_FALLBACK(nextPreset, (bool))
    NUCODE_HEARING_CLIENT_FALLBACK(previousPreset, (bool))
#undef NUCODE_HEARING_CLIENT_FALLBACK
    bool HearingAccessClient::ready() const noexcept
    {
        return false;
    }
    bool HearingAccessClient::busy() const noexcept
    {
        return false;
    }
    HearingAccessStage HearingAccessClient::stage() const noexcept
    {
        return HearingAccessStage::idle;
    }
    HearingAccessStep HearingAccessClient::lastStep() const noexcept
    {
        return HearingAccessStep::none;
    }
    std::uint8_t HearingAccessClient::activePreset() const noexcept
    {
        return 0U;
    }
    std::size_t HearingAccessClient::presetCount() const noexcept
    {
        return 0U;
    }
    Error HearingAccessClient::preset(std::size_t, HearingPreset &) const noexcept
    {
        return Error::unsupported;
    }
    std::uint32_t HearingAccessClient::stateUpdates() const noexcept
    {
        return 0U;
    }
    Error HearingAccessClient::lastError() const noexcept
    {
        return last_error_;
    }
    int HearingAccessClient::nativeCode() const noexcept
    {
        return native_code_;
    }
    Error HearingAccessClient::record(Error error, int native_code) noexcept
    {
        last_error_ = error;
        native_code_ = native_code;
        return error;
    }
} // namespace nucode::ble::audio

#endif
