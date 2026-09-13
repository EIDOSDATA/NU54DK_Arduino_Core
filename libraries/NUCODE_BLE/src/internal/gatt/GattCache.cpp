/**
 * @file GattCache.cpp
 * @brief application database identity와 bonded peer의 robust GATT cache를 관리합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#if !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE)

#include "GattInternal.h"

#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/settings/settings.h>

#include <errno.h>

namespace nucode::ble::internal::gatt
{
    namespace
    {
        inline constexpr std::uint32_t default_database_revision = 1U;
        inline constexpr std::uint32_t database_identity_magic = 0x4944424eU;
        inline constexpr std::size_t database_identity_record_length = 28U;
        inline constexpr char database_identity_key[] = "nucode/gatt/database_identity";
        inline constexpr std::uint32_t cache_record_magic = 0x4347424eU;
        inline constexpr std::uint16_t cache_record_format = 1U;
        inline constexpr std::size_t cache_record_length = 84U;
        inline constexpr std::size_t maximum_cache_records = 4U;
        inline constexpr char cache_record_key[] = "nucode/gatt/cache/0";

        /** @brief revision을 실제 database hash에 포함시키는 내부 primary service 상태입니다. */
        struct CacheDatabaseState
        {
            struct k_spinlock lock;
            atomic_t revision = ATOMIC_INIT(static_cast<atomic_val_t>(default_database_revision));
            atomic_t registered = ATOMIC_INIT(0);
            struct bt_uuid_128 revision_uuid = {};
            struct bt_gatt_attr attribute = {};
            struct bt_gatt_service service = {};
        };

        CacheDatabaseState database_state{};

        /** @brief Settings에 저장된 최대 4개 peer cache와 누적 counter를 소유합니다. */
        struct PersistentCacheState
        {
            struct k_spinlock lock;
            atomic_t loaded = ATOMIC_INIT(0);
            atomic_t next_replacement = ATOMIC_INIT(0);
            atomic_t restored = ATOMIC_INIT(0);
            atomic_t saved = ATOMIC_INIT(0);
            atomic_t invalidated = ATOMIC_INIT(0);
            atomic_t corrupt_rejected = ATOMIC_INIT(0);
            atomic_t stale_handle_rejected = ATOMIC_INIT(0);
            std::uint8_t records[maximum_cache_records][cache_record_length] = {};
            bool valid[maximum_cache_records] = {};
        };

        PersistentCacheState persistent_cache{};

        /** @brief little-endian 16-bit 값을 wire record에 기록합니다. */
        void putLe16(std::uint8_t *output, std::uint16_t value) noexcept
        {
            output[0] = static_cast<std::uint8_t>(value & 0xffU);
            output[1] = static_cast<std::uint8_t>((value >> 8U) & 0xffU);
        }

        /** @brief little-endian 32-bit 값을 wire record에 기록합니다. */
        void putLe32(std::uint8_t *output, std::uint32_t value) noexcept
        {
            output[0] = static_cast<std::uint8_t>(value & 0xffU);
            output[1] = static_cast<std::uint8_t>((value >> 8U) & 0xffU);
            output[2] = static_cast<std::uint8_t>((value >> 16U) & 0xffU);
            output[3] = static_cast<std::uint8_t>((value >> 24U) & 0xffU);
        }

        /** @brief wire record에서 little-endian 16-bit 값을 읽습니다. */
        std::uint16_t getLe16(const std::uint8_t *input) noexcept
        {
            return static_cast<std::uint16_t>(input[0]) |
                   (static_cast<std::uint16_t>(input[1]) << 8U);
        }

        /** @brief wire record에서 little-endian 32-bit 값을 읽습니다. */
        std::uint32_t getLe32(const std::uint8_t *input) noexcept
        {
            return static_cast<std::uint32_t>(input[0]) |
                   (static_cast<std::uint32_t>(input[1]) << 8U) |
                   (static_cast<std::uint32_t>(input[2]) << 16U) |
                   (static_cast<std::uint32_t>(input[3]) << 24U);
        }

        /** @brief 고정 byte에 대한 IEEE CRC32를 heap 없이 계산합니다. */
        std::uint32_t crc32(const std::uint8_t *data, std::size_t length) noexcept
        {
            std::uint32_t value = 0xffffffffU;
            for (std::size_t index = 0U; index < length; ++index)
            {
                value ^= data[index];
                for (std::uint8_t bit = 0U; bit < 8U; ++bit)
                {
                    const std::uint32_t mask = 0U - (value & 1U);
                    value = (value >> 1U) ^ (0xedb88320U & mask);
                }
            }
            return value ^ 0xffffffffU;
        }

        /** @brief BLE UUID를 1-byte width와 16-byte little-endian field로 기록합니다. */
        void encodeUuid(std::uint8_t *output, const BLEUuid &uuid) noexcept
        {
            output[0] = static_cast<std::uint8_t>(uuid.size());
            ::memset(&output[1], 0, 16U);
            ::memcpy(&output[1], uuid.data(), uuid.size());
        }

        /** @brief wire UUID가 exact requested UUID와 같은지 비교합니다. */
        bool recordUuidEquals(const std::uint8_t *input, const BLEUuid &uuid) noexcept
        {
            return input[0] == uuid.size() &&
                   ::memcmp(&input[1], uuid.data(), uuid.size()) == 0;
        }

        /** @brief cache slot의 고정 Settings key를 만듭니다. */
        [[maybe_unused]] void cacheKey(
            std::size_t index, char output[sizeof(cache_record_key)]) noexcept
        {
            ::memcpy(output, cache_record_key, sizeof(cache_record_key));
            output[sizeof(cache_record_key) - 2U] = static_cast<char>('0' + index);
        }

        /** @brief wire record의 version·length·identity·UUID·handle·CRC를 fail-closed로 검증합니다. */
        [[maybe_unused]] bool validCacheRecord(
            const std::uint8_t record[cache_record_length]) noexcept
        {
            const std::uint8_t service_width = record[33];
            const std::uint8_t characteristic_width = record[50];
            const std::uint16_t service_start = getLe16(&record[67]);
            const std::uint16_t service_end = getLe16(&record[69]);
            const std::uint16_t declaration = getLe16(&record[71]);
            const std::uint16_t value = getLe16(&record[73]);
            const std::uint16_t ccc = getLe16(&record[75]);
            if (getLe32(&record[0]) != cache_record_magic ||
                getLe16(&record[4]) != cache_record_format ||
                getLe16(&record[6]) != cache_record_length || getLe16(&record[8]) == 0U ||
                record[10] > static_cast<std::uint8_t>(BLEAddress::Type::random_address) ||
                (service_width != 2U && service_width != 16U) ||
                (characteristic_width != 2U && characteristic_width != 16U) ||
                service_start < BT_ATT_FIRST_ATTRIBUTE_HANDLE || service_end < service_start ||
                declaration < service_start || declaration >= service_end || value <= declaration ||
                value > service_end || (ccc != 0U && (ccc <= value || ccc > service_end)) ||
                record[77] == 0U || getLe32(&record[80]) != crc32(record, 80U))
            {
                return false;
            }
            for (std::size_t index = service_width; index < 16U; ++index)
            {
                if (record[34U + index] != 0U)
                {
                    return false;
                }
            }
            for (std::size_t index = characteristic_width; index < 16U; ++index)
            {
                if (record[51U + index] != 0U)
                {
                    return false;
                }
            }
            return record[78] == 0U && record[79] == 0U;
        }

        /** @brief 네 Settings slot을 한 번 로드하고 잘린·손상 record를 폐기합니다. */
        void loadPersistentCache() noexcept
        {
            if (!atomic_cas(&persistent_cache.loaded, 0, 1))
            {
                return;
            }
#if defined(CONFIG_BT_SETTINGS)
            for (std::size_t index = 0U; index < maximum_cache_records; ++index)
            {
                char key[sizeof(cache_record_key)] = {};
                cacheKey(index, key);
                std::uint8_t record[cache_record_length] = {};
                const ssize_t length = settings_load_one(key, record, sizeof(record));
                if (length == -ENOENT || length == 0)
                {
                    continue;
                }
                if (length != static_cast<ssize_t>(sizeof(record)) || !validCacheRecord(record))
                {
                    atomic_inc(&persistent_cache.corrupt_rejected);
                    static_cast<void>(settings_delete(key));
                    continue;
                }
                ::memcpy(persistent_cache.records[index], record, sizeof(record));
                persistent_cache.valid[index] = true;
            }
#endif
        }

        /** @brief exact identity·UUID·schema·hash와 일치하는 cache slot을 찾습니다. */
        int findCacheRecord(const BLEAddress &identity, const BLEUuid &service_uuid,
                            const BLEUuid &characteristic_uuid, std::uint16_t schema_version,
                            const std::uint8_t hash[GattDatabase::hash_length]) noexcept
        {
            loadPersistentCache();
            for (std::size_t index = 0U; index < maximum_cache_records; ++index)
            {
                const std::uint8_t *record = persistent_cache.records[index];
                if (!persistent_cache.valid[index] || getLe16(&record[8]) != schema_version ||
                    record[10] != static_cast<std::uint8_t>(identity.type()) ||
                    ::memcmp(&record[11], identity.data(), 6U) != 0 ||
                    ::memcmp(&record[17], hash, GattDatabase::hash_length) != 0 ||
                    !recordUuidEquals(&record[33], service_uuid) ||
                    !recordUuidEquals(&record[50], characteristic_uuid))
                {
                    continue;
                }
                return static_cast<int>(index);
            }
            return -1;
        }

        /** @brief 같은 peer identity의 예전 cache가 존재하는지 확인합니다. */
        bool hasIdentityRecord(const BLEAddress &identity) noexcept
        {
            loadPersistentCache();
            for (std::size_t index = 0U; index < maximum_cache_records; ++index)
            {
                const std::uint8_t *record = persistent_cache.records[index];
                if (persistent_cache.valid[index] &&
                    record[10] == static_cast<std::uint8_t>(identity.type()) &&
                    ::memcmp(&record[11], identity.data(), 6U) == 0)
                {
                    return true;
                }
            }
            return false;
        }

        /** @brief identity와 UUID가 같은 record 또는 빈 slot을 선택합니다. */
        std::size_t selectCacheRecord(const BLEAddress &identity, const BLEUuid &service_uuid,
                                      const BLEUuid &characteristic_uuid) noexcept
        {
            for (std::size_t index = 0U; index < maximum_cache_records; ++index)
            {
                const std::uint8_t *record = persistent_cache.records[index];
                if (persistent_cache.valid[index] &&
                    record[10] == static_cast<std::uint8_t>(identity.type()) &&
                    ::memcmp(&record[11], identity.data(), 6U) == 0 &&
                    recordUuidEquals(&record[33], service_uuid) &&
                    recordUuidEquals(&record[50], characteristic_uuid))
                {
                    return index;
                }
            }
            for (std::size_t index = 0U; index < maximum_cache_records; ++index)
            {
                if (!persistent_cache.valid[index])
                {
                    return index;
                }
            }
            const atomic_val_t replacement = atomic_inc(&persistent_cache.next_replacement);
            return static_cast<std::size_t>(replacement) % maximum_cache_records;
        }

        /** @brief 현재 remote handle snapshot을 CRC 보호 record로 저장합니다. */
        bool saveCacheRecord(ClientState &state, const BLEAddress &identity) noexcept
        {
            BLERemoteService service;
            BLERemoteCharacteristic characteristic;
            copyRemoteHandles(state, service, characteristic);
            if (!service.valid() || !characteristic.valid())
            {
                return false;
            }
            loadPersistentCache();
            const std::size_t index =
                selectCacheRecord(identity, state.target_service_uuid,
                                  state.target_characteristic_uuid);
            std::uint8_t record[cache_record_length] = {};
            putLe32(&record[0], cache_record_magic);
            putLe16(&record[4], cache_record_format);
            putLe16(&record[6], static_cast<std::uint16_t>(sizeof(record)));
            putLe16(&record[8], state.cache_schema_version);
            record[10] = static_cast<std::uint8_t>(identity.type());
            ::memcpy(&record[11], identity.data(), 6U);
            ::memcpy(&record[17], state.remote_database_hash, GattDatabase::hash_length);
            encodeUuid(&record[33], state.target_service_uuid);
            encodeUuid(&record[50], state.target_characteristic_uuid);
            putLe16(&record[67], service.startHandle());
            putLe16(&record[69], service.endHandle());
            putLe16(&record[71], GattAccess::declarationHandle(characteristic));
            putLe16(&record[73], characteristic.valueHandle());
            putLe16(&record[75], characteristic.cccHandle());
            record[77] = static_cast<std::uint8_t>(characteristic.properties());
            putLe32(&record[80], crc32(record, 80U));
#if defined(CONFIG_BT_SETTINGS)
            char settings_key[sizeof(cache_record_key)] = {};
            cacheKey(index, settings_key);
            if (settings_save_one(settings_key, record, sizeof(record)) < 0)
            {
                return false;
            }
#endif
            k_spinlock_key_t lock_key = k_spin_lock(&persistent_cache.lock);
            ::memcpy(persistent_cache.records[index], record, sizeof(record));
            persistent_cache.valid[index] = true;
            k_spin_unlock(&persistent_cache.lock, lock_key);
            atomic_inc(&persistent_cache.saved);
            return true;
        }

        /** @brief identity와 일치하는 영속 cache record를 모두 폐기합니다. */
        bool eraseCacheRecords(const BLEAddress &identity) noexcept
        {
            loadPersistentCache();
            for (std::size_t index = 0U; index < maximum_cache_records; ++index)
            {
                const std::uint8_t *record = persistent_cache.records[index];
                if (!persistent_cache.valid[index] ||
                    record[10] != static_cast<std::uint8_t>(identity.type()) ||
                    ::memcmp(&record[11], identity.data(), 6U) != 0)
                {
                    continue;
                }
#if defined(CONFIG_BT_SETTINGS)
                char settings_key[sizeof(cache_record_key)] = {};
                cacheKey(index, settings_key);
                if (settings_delete(settings_key) < 0)
                {
                    return false;
                }
#endif
                k_spinlock_key_t lock_key = k_spin_lock(&persistent_cache.lock);
                ::memset(persistent_cache.records[index], 0,
                         sizeof(persistent_cache.records[index]));
                persistent_cache.valid[index] = false;
                k_spin_unlock(&persistent_cache.lock, lock_key);
            }
            return true;
        }

        /** @brief cache record의 추적 handle을 link state에 복원합니다. */
        void restoreCacheRecord(ClientState &state, const std::uint8_t *record) noexcept
        {
            k_spinlock_key_t key = k_spin_lock(&state.client_state_lock);
            GattAccess::set(state.remote_service, state.target_service_uuid,
                            getLe16(&record[67]), getLe16(&record[69]));
            GattAccess::set(state.remote_characteristic, state.target_characteristic_uuid,
                            getLe16(&record[71]), getLe16(&record[73]),
                            static_cast<BLEProperty>(record[77]));
            GattAccess::setCcc(state.remote_characteristic, getLe16(&record[75]));
            k_spin_unlock(&state.client_state_lock, key);
            atomic_set(&state.client_stage, static_cast<atomic_val_t>(ClientStage::ready));
            atomic_set(&state.cache_state,
                       static_cast<atomic_val_t>(BLEGattCacheState::restored));
            atomic_set(&state.cache_stage, static_cast<atomic_val_t>(CacheStage::idle));
            clearClientOperationToken(state);
            atomic_set(&state.client_busy_value, 0);
            atomic_inc(&persistent_cache.restored);
            queueClientEvent(state, BLEGattClientEvent::cache_restored);
            queueClientEvent(state, BLEGattClientEvent::discovery_complete);
        }

        /** @brief cache discovery parameter를 소유한 link state를 찾습니다. */
        ClientState *findCacheDiscoveryState(
            struct bt_gatt_discover_params *parameters) noexcept
        {
            for (ClientState &state : clientStates())
            {
                if (&state.cache_discovery_parameters == parameters)
                {
                    return &state;
                }
            }
            return nullptr;
        }

        /** @brief cache read parameter를 소유한 link state를 찾습니다. */
        ClientState *findCacheReadState(struct bt_gatt_read_params *parameters) noexcept
        {
            for (ClientState &state : clientStates())
            {
                if (&state.cache_read_parameters == parameters)
                {
                    return &state;
                }
            }
            return nullptr;
        }

        /** @brief cache write parameter를 소유한 link state를 찾습니다. */
        ClientState *findCacheWriteState(struct bt_gatt_write_params *parameters) noexcept
        {
            for (ClientState &state : clientStates())
            {
                if (&state.cache_write_parameters == parameters)
                {
                    return &state;
                }
            }
            return nullptr;
        }

        /** @brief cache Service Changed subscription을 소유한 link state를 찾습니다. */
        ClientState *findCacheSubscriptionState(
            struct bt_gatt_subscribe_params *parameters) noexcept
        {
            for (ClientState &state : clientStates())
            {
                if (&state.cache_subscribe_parameters == parameters)
                {
                    return &state;
                }
            }
            return nullptr;
        }

        /** @brief cache에 필요한 resolved bonded identity를 exact link에서 구합니다. */
        bool cacheIdentity(ClientState &state, BLEAddress &identity) noexcept
        {
            if (!BLEConnection.identityResolved(state.connection_handle))
            {
                return false;
            }
            identity = BLEConnection.peerAddress(state.connection_handle);
            if (!identity.valid())
            {
                return false;
            }
#if defined(CONFIG_BT_SMP)
            struct bt_conn *connection =
                nucode::ble::internal::referenceConnection(state.connection_handle);
            if (connection == nullptr)
            {
                return false;
            }
            const bool bonded = bt_le_bond_exists(BT_ID_DEFAULT, bt_conn_get_dst(connection));
            bt_conn_unref(connection);
            return bonded;
#else
            return false;
#endif
        }

        /** @brief remote handle을 사용 전에 폐기하고 stale 사용을 차단합니다. */
        bool clearCachedHandles(ClientState &state) noexcept
        {
            k_spinlock_key_t key = k_spin_lock(&state.client_state_lock);
            const bool had_handles = state.remote_service.valid() ||
                                     state.remote_characteristic.valid();
            GattAccess::clear(state.remote_service);
            GattAccess::clear(state.remote_characteristic);
            for (BLERemoteDescriptor &descriptor : state.remote_descriptors)
            {
                GattAccess::clear(descriptor);
            }
            state.remote_descriptor_count = 0U;
            k_spin_unlock(&state.client_state_lock, key);
            atomic_set(&state.client_stage, static_cast<atomic_val_t>(ClientStage::idle));
            atomic_set(&state.client_subscribed, 0);
            atomic_set(&state.client_subscription_value, 0);
            return had_handles;
        }

        /** @brief cache state machine을 종료하고 상세 operation failure를 보고합니다. */
        void failCache(ClientState &state, int driver_error,
                       std::uint8_t att_error = 0U) noexcept
        {
            static_cast<void>(clearCachedHandles(state));
            atomic_set(&state.cache_stage, static_cast<atomic_val_t>(CacheStage::idle));
            atomic_set(&state.cache_state,
                       static_cast<atomic_val_t>(BLEGattCacheState::failed));
            failClient(state, driver_error, att_error);
        }

        /** @brief cache discovery를 exact UUID·handle 범위에서 시작합니다. */
        bool startCacheDiscovery(ClientState &state, struct bt_conn *connection,
                                 const struct bt_uuid *uuid,
                                 bt_gatt_discover_func_t callback, std::uint16_t start,
                                 std::uint16_t end, std::uint8_t type,
                                 CacheStage stage) noexcept
        {
            if (connection == nullptr || !validClientOperation(state, connection) ||
                start == 0U || end < start)
            {
                failCache(state, -ENOTCONN);
                return false;
            }
            ::memset(&state.cache_discovery_parameters, 0,
                     sizeof(state.cache_discovery_parameters));
            state.cache_discovery_parameters.uuid = uuid;
            state.cache_discovery_parameters.func = callback;
            state.cache_discovery_parameters.start_handle = start;
            state.cache_discovery_parameters.end_handle = end;
            state.cache_discovery_parameters.type = type;
            atomic_set(&state.cache_stage, static_cast<atomic_val_t>(stage));
            const int result = bt_gatt_discover(connection, &state.cache_discovery_parameters);
            if (result < 0)
            {
                failCache(state, result);
                return false;
            }
            return true;
        }

        /** @brief standard GATT primary service handle 범위를 저장합니다. */
        std::uint8_t cacheGattServiceDiscovered(
            struct bt_conn *connection, const struct bt_gatt_attr *attribute,
            struct bt_gatt_discover_params *parameters) noexcept
        {
            ClientState *state = findCacheDiscoveryState(parameters);
            if (state == nullptr || !validClientOperation(*state, connection))
            {
                return BT_GATT_ITER_STOP;
            }
            if (attribute == nullptr)
            {
                failCache(*state, -ENOENT);
                return BT_GATT_ITER_STOP;
            }
            const auto *service =
                static_cast<const struct bt_gatt_service_val *>(attribute->user_data);
            if (service == nullptr || service->end_handle < attribute->handle)
            {
                failCache(*state, -EINVAL);
                return BT_GATT_ITER_STOP;
            }
            state->gatt_service_start_handle = attribute->handle;
            state->gatt_service_end_handle = service->end_handle;
            atomic_set(&state->cache_stage,
                       static_cast<atomic_val_t>(CacheStage::gatt_service_found));
            return BT_GATT_ITER_STOP;
        }

        /** @brief standard cache characteristic의 value handle을 단계별로 저장합니다. */
        std::uint8_t cacheCharacteristicDiscovered(
            struct bt_conn *connection, const struct bt_gatt_attr *attribute,
            struct bt_gatt_discover_params *parameters) noexcept
        {
            ClientState *state = findCacheDiscoveryState(parameters);
            if (state == nullptr || !validClientOperation(*state, connection))
            {
                return BT_GATT_ITER_STOP;
            }
            if (attribute == nullptr || attribute->user_data == nullptr)
            {
                failCache(*state, -ENOENT);
                return BT_GATT_ITER_STOP;
            }
            const auto *characteristic =
                static_cast<const struct bt_gatt_chrc *>(attribute->user_data);
            const CacheStage stage =
                static_cast<CacheStage>(atomic_get(&state->cache_stage));
            if (characteristic->value_handle <= attribute->handle ||
                characteristic->value_handle > state->gatt_service_end_handle)
            {
                failCache(*state, -EINVAL);
                return BT_GATT_ITER_STOP;
            }
            if (stage == CacheStage::discovering_service_changed)
            {
                state->service_changed_value_handle = characteristic->value_handle;
                atomic_set(&state->cache_stage,
                           static_cast<atomic_val_t>(CacheStage::service_changed_found));
            }
            else if (stage == CacheStage::discovering_client_features)
            {
                state->client_features_handle = characteristic->value_handle;
                atomic_set(&state->cache_stage,
                           static_cast<atomic_val_t>(CacheStage::client_features_found));
            }
            else if (stage == CacheStage::discovering_database_hash)
            {
                state->database_hash_handle = characteristic->value_handle;
                atomic_set(&state->cache_stage,
                           static_cast<atomic_val_t>(CacheStage::database_hash_found));
            }
            else
            {
                failCache(*state, -EINVAL);
            }
            return BT_GATT_ITER_STOP;
        }

        /** @brief Service Changed CCC handle을 standard service 범위에서 저장합니다. */
        std::uint8_t cacheServiceChangedCccDiscovered(
            struct bt_conn *connection, const struct bt_gatt_attr *attribute,
            struct bt_gatt_discover_params *parameters) noexcept
        {
            ClientState *state = findCacheDiscoveryState(parameters);
            if (state == nullptr || !validClientOperation(*state, connection))
            {
                return BT_GATT_ITER_STOP;
            }
            if (attribute == nullptr || attribute->handle <= state->service_changed_value_handle ||
                attribute->handle > state->gatt_service_end_handle)
            {
                failCache(*state, -ENOENT);
                return BT_GATT_ITER_STOP;
            }
            state->service_changed_ccc_handle = attribute->handle;
            atomic_set(&state->cache_stage,
                       static_cast<atomic_val_t>(CacheStage::service_changed_ccc_found));
            return BT_GATT_ITER_STOP;
        }

        /** @brief target primary service handle 범위를 cache miss discovery에 저장합니다. */
        std::uint8_t cacheTargetServiceDiscovered(
            struct bt_conn *connection, const struct bt_gatt_attr *attribute,
            struct bt_gatt_discover_params *parameters) noexcept
        {
            ClientState *state = findCacheDiscoveryState(parameters);
            if (state == nullptr || !validClientOperation(*state, connection))
            {
                return BT_GATT_ITER_STOP;
            }
            if (attribute == nullptr || attribute->user_data == nullptr)
            {
                failCache(*state, -ENOENT);
                return BT_GATT_ITER_STOP;
            }
            const auto *service =
                static_cast<const struct bt_gatt_service_val *>(attribute->user_data);
            if (service->end_handle < attribute->handle)
            {
                failCache(*state, -EINVAL);
                return BT_GATT_ITER_STOP;
            }
            k_spinlock_key_t key = k_spin_lock(&state->client_state_lock);
            GattAccess::set(state->remote_service, state->target_service_uuid,
                            attribute->handle, service->end_handle);
            k_spin_unlock(&state->client_state_lock, key);
            atomic_set(&state->cache_stage,
                       static_cast<atomic_val_t>(CacheStage::target_service_found));
            return BT_GATT_ITER_STOP;
        }

        /** @brief target characteristic handle·property를 cache miss discovery에 저장합니다. */
        std::uint8_t cacheTargetCharacteristicDiscovered(
            struct bt_conn *connection, const struct bt_gatt_attr *attribute,
            struct bt_gatt_discover_params *parameters) noexcept
        {
            ClientState *state = findCacheDiscoveryState(parameters);
            if (state == nullptr || !validClientOperation(*state, connection))
            {
                return BT_GATT_ITER_STOP;
            }
            if (attribute == nullptr || attribute->user_data == nullptr)
            {
                failCache(*state, -ENOENT);
                return BT_GATT_ITER_STOP;
            }
            const auto *characteristic =
                static_cast<const struct bt_gatt_chrc *>(attribute->user_data);
            const BLERemoteService service = copyRemoteService(*state);
            if (characteristic->value_handle <= attribute->handle ||
                characteristic->value_handle > service.endHandle())
            {
                failCache(*state, -EINVAL);
                return BT_GATT_ITER_STOP;
            }
            k_spinlock_key_t key = k_spin_lock(&state->client_state_lock);
            GattAccess::set(state->remote_characteristic, state->target_characteristic_uuid,
                            attribute->handle, characteristic->value_handle,
                            static_cast<BLEProperty>(characteristic->properties));
            k_spin_unlock(&state->client_state_lock, key);
            atomic_set(&state->cache_stage,
                       static_cast<atomic_val_t>(CacheStage::target_characteristic_found));
            return BT_GATT_ITER_STOP;
        }

        /** @brief target CCC handle을 cache miss discovery에 저장합니다. */
        std::uint8_t cacheTargetCccDiscovered(
            struct bt_conn *connection, const struct bt_gatt_attr *attribute,
            struct bt_gatt_discover_params *parameters) noexcept
        {
            ClientState *state = findCacheDiscoveryState(parameters);
            if (state == nullptr || !validClientOperation(*state, connection))
            {
                return BT_GATT_ITER_STOP;
            }
            const BLERemoteService service = copyRemoteService(*state);
            const BLERemoteCharacteristic characteristic =
                copyRemoteCharacteristic(*state);
            if (attribute == nullptr || attribute->handle <= characteristic.valueHandle() ||
                attribute->handle > service.endHandle())
            {
                failCache(*state, -ENOENT);
                return BT_GATT_ITER_STOP;
            }
            k_spinlock_key_t key = k_spin_lock(&state->client_state_lock);
            GattAccess::setCcc(state->remote_characteristic, attribute->handle);
            k_spin_unlock(&state->client_state_lock, key);
            atomic_set(&state->cache_stage,
                       static_cast<atomic_val_t>(CacheStage::target_ccc_found));
            return BT_GATT_ITER_STOP;
        }

        /** @brief robust caching Client Supported Features write 완료를 단계에 반영합니다. */
        void cacheFeaturesWritten(struct bt_conn *connection, std::uint8_t error,
                                  struct bt_gatt_write_params *parameters) noexcept
        {
            ClientState *state = findCacheWriteState(parameters);
            if (state == nullptr || !validClientOperation(*state, connection))
            {
                return;
            }
            if (error != 0U)
            {
                failCache(*state, -EIO, error);
                return;
            }
            atomic_set(&state->cache_stage,
                       static_cast<atomic_val_t>(CacheStage::client_features_written));
        }

        /** @brief remote database hash를 exact 16 byte로 복사하고 단계를 완료합니다. */
        std::uint8_t cacheDatabaseHashRead(struct bt_conn *connection, std::uint8_t error,
                                           struct bt_gatt_read_params *parameters,
                                           const void *data, std::uint16_t length) noexcept
        {
            ClientState *state = findCacheReadState(parameters);
            if (state == nullptr || !validClientOperation(*state, connection))
            {
                return BT_GATT_ITER_STOP;
            }
            if (error != 0U)
            {
                failCache(*state, -EIO, error);
                return BT_GATT_ITER_STOP;
            }
            if (data != nullptr)
            {
                if (state->read_length + length > GattDatabase::hash_length)
                {
                    failCache(*state, -EMSGSIZE);
                    return BT_GATT_ITER_STOP;
                }
                ::memcpy(&state->remote_database_hash[state->read_length], data, length);
                state->read_length += length;
                return BT_GATT_ITER_CONTINUE;
            }
            if (state->read_length != GattDatabase::hash_length)
            {
                failCache(*state, -EMSGSIZE);
                return BT_GATT_ITER_STOP;
            }
            atomic_set(&state->cache_stage,
                       static_cast<atomic_val_t>(CacheStage::database_hash_read));
            queueClientEvent(*state, BLEGattClientEvent::database_hash_read,
                             state->remote_database_hash, GattDatabase::hash_length);
            return BT_GATT_ITER_STOP;
        }

        /** @brief Service Changed CCC subscription 완료를 확인합니다. */
        void cacheServiceChangedSubscribed(
            struct bt_conn *connection, std::uint8_t error,
            struct bt_gatt_subscribe_params *parameters) noexcept
        {
            ClientState *state = findCacheSubscriptionState(parameters);
            if (state == nullptr || !validClientOperation(*state, connection))
            {
                return;
            }
            if (error != 0U)
            {
                failCache(*state, -EIO, error);
                return;
            }
            state->cache_subscription_connection = connection;
            atomic_set(&state->cache_stage,
                       static_cast<atomic_val_t>(CacheStage::service_changed_subscribed));
        }

        /** @brief Service Changed를 받자마자 handle을 먼저 폐기하고 재탐색을 예약합니다. */
        std::uint8_t cacheServiceChanged(
            struct bt_conn *connection, struct bt_gatt_subscribe_params *parameters,
            const void *data, std::uint16_t length) noexcept
        {
            ClientState *state = findCacheSubscriptionState(parameters);
            if (state == nullptr || connection == nullptr ||
                state->cache_subscription_connection != connection ||
                !currentGattConnection(*state, connection))
            {
                return BT_GATT_ITER_STOP;
            }
            if (data == nullptr)
            {
                state->cache_subscription_connection = nullptr;
                return BT_GATT_ITER_STOP;
            }
            const auto *range = static_cast<const std::uint8_t *>(data);
            if (length != 4U || getLe16(&range[0]) == 0U ||
                getLe16(&range[2]) < getLe16(&range[0]))
            {
                failCache(*state, -EINVAL);
                return BT_GATT_ITER_STOP;
            }
            BLEAddress identity;
            if (!cacheIdentity(*state, identity))
            {
                failCache(*state, -EACCES);
                return BT_GATT_ITER_STOP;
            }
            const bool busy = atomic_get(&state->client_busy_value) != 0;
            const bool had_handles = clearCachedHandles(*state);
            if (!eraseCacheRecords(identity))
            {
                failCache(*state, -EIO);
                return BT_GATT_ITER_STOP;
            }
            atomic_inc(&persistent_cache.invalidated);
            atomic_set(&state->cache_state,
                       static_cast<atomic_val_t>(BLEGattCacheState::invalidated));
            queueClientEvent(*state, BLEGattClientEvent::service_changed, data, length);
            queueClientEvent(*state, BLEGattClientEvent::cache_invalidated);
            if (busy)
            {
                clearClientOperationToken(*state);
                atomic_set(&state->client_busy_value, 0);
                atomic_inc(&persistent_cache.stale_handle_rejected);
                atomic_set(&state->cache_state,
                           static_cast<atomic_val_t>(BLEGattCacheState::failed));
                atomic_set(&state->cache_stage, static_cast<atomic_val_t>(CacheStage::idle));
                return BT_GATT_ITER_CONTINUE;
            }
            if (had_handles)
            {
                atomic_set(&state->cache_stage,
                           static_cast<atomic_val_t>(CacheStage::rediscovery_pending));
            }
            return BT_GATT_ITER_CONTINUE;
        }

        /** @brief cache miss discovery를 영속 record로 저장하고 operation을 완료합니다. */
        void completeCacheDiscovery(ClientState &state) noexcept
        {
            BLEAddress identity;
            if (!cacheIdentity(state, identity) || !saveCacheRecord(state, identity))
            {
                failCache(state, -EIO);
                return;
            }
            atomic_set(&state.client_stage, static_cast<atomic_val_t>(ClientStage::ready));
            atomic_set(&state.cache_stage, static_cast<atomic_val_t>(CacheStage::idle));
            atomic_set(&state.cache_state,
                       static_cast<atomic_val_t>(BLEGattCacheState::discovered));
            clearClientOperationToken(state);
            atomic_set(&state.client_busy_value, 0);
            queueClientEvent(state, BLEGattClientEvent::cache_saved);
            queueClientEvent(state, BLEGattClientEvent::discovery_complete);
        }

        /** @brief database hash characteristic의 exact 16-byte read를 시작합니다. */
        bool startCacheHashRead(ClientState &state, struct bt_conn *connection) noexcept
        {
            if (state.database_hash_handle == 0U ||
                !validClientOperation(state, connection))
            {
                failCache(state, -ENOTCONN);
                return false;
            }
            ::memset(state.remote_database_hash, 0, sizeof(state.remote_database_hash));
            state.read_length = 0U;
            ::memset(&state.cache_read_parameters, 0, sizeof(state.cache_read_parameters));
            state.cache_read_parameters.func = cacheDatabaseHashRead;
            state.cache_read_parameters.handle_count = 1U;
            state.cache_read_parameters.single.handle = state.database_hash_handle;
            state.cache_read_parameters.single.offset = 0U;
            atomic_set(&state.cache_stage,
                       static_cast<atomic_val_t>(CacheStage::reading_database_hash));
            const int result = bt_gatt_read(connection, &state.cache_read_parameters);
            if (result < 0)
            {
                failCache(state, result);
                return false;
            }
            return true;
        }

        /** @brief hash 확인 후 exact record를 복원하거나 target discovery를 시작합니다. */
        void applyCacheOrDiscover(ClientState &state, struct bt_conn *connection) noexcept
        {
            BLEAddress identity;
            if (!cacheIdentity(state, identity))
            {
                failCache(state, -EACCES);
                return;
            }
            const int record_index =
                findCacheRecord(identity, state.target_service_uuid,
                                state.target_characteristic_uuid, state.cache_schema_version,
                                state.remote_database_hash);
            if (record_index >= 0)
            {
                restoreCacheRecord(state,
                                   persistent_cache.records[static_cast<std::size_t>(record_index)]);
                return;
            }
            if (hasIdentityRecord(identity))
            {
                if (!eraseCacheRecords(identity))
                {
                    failCache(state, -EIO);
                    return;
                }
                atomic_inc(&persistent_cache.invalidated);
                queueClientEvent(state, BLEGattClientEvent::cache_invalidated);
            }
            static_cast<void>(clearCachedHandles(state));
            const struct bt_uuid *uuid =
                state.target_service_zephyr_uuid.assign(state.target_service_uuid);
            if (uuid == nullptr)
            {
                failCache(state, -EINVAL);
                return;
            }
            static_cast<void>(startCacheDiscovery(
                state, connection, uuid, cacheTargetServiceDiscovered,
                BT_ATT_FIRST_ATTRIBUTE_HANDLE, BT_ATT_LAST_ATTRIBUTE_HANDLE,
                BT_GATT_DISCOVER_PRIMARY, CacheStage::discovering_target_service));
        }

        /** @brief GATT Database Hash characteristic attribute를 정확히 한 개 찾습니다. */
        std::uint8_t findDatabaseHash(const struct bt_gatt_attr *attribute,
                                      std::uint16_t handle, void *context) noexcept
        {
            ARG_UNUSED(handle);
            if (attribute == nullptr || context == nullptr ||
                attribute->uuid->type != BT_UUID_TYPE_16)
            {
                return BT_GATT_ITER_CONTINUE;
            }
            const auto *uuid = reinterpret_cast<const struct bt_uuid_16 *>(attribute->uuid);
            if (uuid->val != BT_UUID_GATT_DB_HASH_VAL)
            {
                return BT_GATT_ITER_CONTINUE;
            }
            auto **result = static_cast<const struct bt_gatt_attr **>(context);
            if (*result != nullptr)
            {
                return BT_GATT_ITER_STOP;
            }
            *result = attribute;
            return BT_GATT_ITER_CONTINUE;
        }

        /** @brief revision에서 내부 128-bit primary service UUID를 결정적으로 만듭니다. */
        void assignRevisionUuid(std::uint32_t revision) noexcept
        {
            static constexpr std::uint8_t base_uuid[16] = {
                0x6eU, 0x75U, 0x63U, 0x6fU, 0x64U, 0x65U, 0x2dU, 0x67U,
                0x61U, 0x74U, 0x74U, 0x2dU, 0x72U, 0x65U, 0x76U, 0x01U,
            };
            database_state.revision_uuid.uuid.type = BT_UUID_TYPE_128;
            ::memcpy(database_state.revision_uuid.val, base_uuid, sizeof(base_uuid));
            putLe32(database_state.revision_uuid.val, revision);
        }

        /** @brief revision과 실제 hash를 version·length·CRC가 있는 record로 저장합니다. */
        [[maybe_unused]] int saveDatabaseIdentity(
            std::uint32_t revision,
            const std::uint8_t hash[GattDatabase::hash_length]) noexcept
        {
#if defined(CONFIG_BT_SETTINGS)
            std::uint8_t record[database_identity_record_length] = {};
            putLe32(&record[0], database_identity_magic);
            putLe16(&record[4], 1U);
            putLe16(&record[6], static_cast<std::uint16_t>(sizeof(record)));
            putLe32(&record[8], revision);
            ::memcpy(&record[12], hash, GattDatabase::hash_length);
            putLe32(&record[24], crc32(record, 24U));
            return settings_save_one(database_identity_key, record, sizeof(record));
#else
            ARG_UNUSED(revision);
            ARG_UNUSED(hash);
            return 0;
#endif
        }
    } // namespace

    void clearClientCacheState(ClientState &state) noexcept
    {
        atomic_set(&state.cache_state, static_cast<atomic_val_t>(BLEGattCacheState::idle));
        atomic_set(&state.cache_stage, static_cast<atomic_val_t>(CacheStage::idle));
        state.cache_schema_version = 0U;
        state.gatt_service_start_handle = 0U;
        state.gatt_service_end_handle = 0U;
        state.service_changed_value_handle = 0U;
        state.service_changed_ccc_handle = 0U;
        state.client_features_handle = 0U;
        state.database_hash_handle = 0U;
        state.cache_subscription_connection = nullptr;
        ::memset(state.remote_database_hash, 0, sizeof(state.remote_database_hash));
        ::memset(&state.cache_discovery_parameters, 0,
                 sizeof(state.cache_discovery_parameters));
        ::memset(&state.cache_read_parameters, 0, sizeof(state.cache_read_parameters));
        ::memset(&state.cache_write_parameters, 0, sizeof(state.cache_write_parameters));
        ::memset(&state.cache_subscribe_parameters, 0,
                 sizeof(state.cache_subscribe_parameters));
    }

    bool startCachedDiscovery(BLEConnectionHandle connection_handle,
                              const BLEUuid &service_uuid,
                              const BLEUuid &characteristic_uuid,
                              std::uint16_t schema_version) noexcept
    {
        if (!service_uuid.valid() || !characteristic_uuid.valid() || schema_version == 0U ||
            service_uuid.type() == BLEUuid::Type::uuid32 ||
            characteristic_uuid.type() == BLEUuid::Type::uuid32)
        {
            recordError(BLEError::invalid_argument, -EINVAL, true);
            return false;
        }
        ClientState *state = findClientState(connection_handle);
        if (state == nullptr)
        {
            recordError(BLEError::not_connected, -ENOTCONN, true);
            return false;
        }
        BLEAddress identity;
        if (!cacheIdentity(*state, identity))
        {
            recordError(BLEError::wrong_state, -EACCES, true);
            return false;
        }
        if (!atomic_cas(&state->client_busy_value, 0, 1))
        {
            recordError(BLEError::busy, -EBUSY, true);
            return false;
        }
        struct bt_conn *connection = referenceConnection(connection_handle);
        if (connection == nullptr || !currentGattConnection(*state, connection))
        {
            if (connection != nullptr)
            {
                bt_conn_unref(connection);
            }
            atomic_set(&state->client_busy_value, 0);
            recordError(BLEError::not_connected, -ENOTCONN, true);
            return false;
        }
        state->target_service_uuid = service_uuid;
        state->target_characteristic_uuid = characteristic_uuid;
        state->cache_schema_version = schema_version;
        state->gatt_service_start_handle = 0U;
        state->gatt_service_end_handle = 0U;
        state->service_changed_value_handle = 0U;
        state->service_changed_ccc_handle = 0U;
        state->client_features_handle = 0U;
        state->database_hash_handle = 0U;
        state->read_length = 0U;
        static_cast<void>(clearCachedHandles(*state));
        atomic_set(&state->cache_state,
                   static_cast<atomic_val_t>(BLEGattCacheState::synchronizing));
        setClientOperationToken(*state, connection);
        const bool started = startCacheDiscovery(
            *state, connection, BT_UUID_GATT, cacheGattServiceDiscovered,
            BT_ATT_FIRST_ATTRIBUTE_HANDLE, BT_ATT_LAST_ATTRIBUTE_HANDLE,
            BT_GATT_DISCOVER_PRIMARY, CacheStage::discovering_gatt_service);
        bt_conn_unref(connection);
        return started;
    }

    BLEGattCacheState clientCacheState(BLEConnectionHandle connection) noexcept
    {
        ClientState *state = findClientState(connection);
        return state == nullptr
                   ? BLEGattCacheState::idle
                   : static_cast<BLEGattCacheState>(atomic_get(&state->cache_state));
    }

    bool invalidateClientCache(BLEConnectionHandle connection) noexcept
    {
        ClientState *state = findClientState(connection);
        if (state == nullptr)
        {
            recordError(BLEError::not_connected, -ENOTCONN, true);
            return false;
        }
        if (atomic_get(&state->client_busy_value) != 0)
        {
            recordError(BLEError::busy, -EBUSY, true);
            return false;
        }
        BLEAddress identity;
        if (!cacheIdentity(*state, identity) || !eraseCacheRecords(identity))
        {
            recordError(BLEError::wrong_state, -EACCES, true);
            return false;
        }
        static_cast<void>(clearCachedHandles(*state));
        atomic_inc(&persistent_cache.invalidated);
        atomic_set(&state->cache_state,
                   static_cast<atomic_val_t>(BLEGattCacheState::invalidated));
        queueClientEvent(*state, BLEGattClientEvent::cache_invalidated);
        return true;
    }

    BLEGattCacheStatistics clientCacheStatistics() noexcept
    {
        return {
            .restored = static_cast<std::uint32_t>(atomic_get(&persistent_cache.restored)),
            .saved = static_cast<std::uint32_t>(atomic_get(&persistent_cache.saved)),
            .invalidated =
                static_cast<std::uint32_t>(atomic_get(&persistent_cache.invalidated)),
            .corrupt_rejected =
                static_cast<std::uint32_t>(atomic_get(&persistent_cache.corrupt_rejected)),
            .stale_handle_rejected =
                static_cast<std::uint32_t>(atomic_get(&persistent_cache.stale_handle_rejected)),
        };
    }

    void progressGattCache() noexcept
    {
        for (ClientState &state : clientStates())
        {
            CacheStage stage = static_cast<CacheStage>(atomic_get(&state.cache_stage));
            if (stage == CacheStage::idle)
            {
                continue;
            }
            if (stage == CacheStage::rediscovery_pending)
            {
                if (!atomic_cas(&state.client_busy_value, 0, 1))
                {
                    continue;
                }
                struct bt_conn *connection = referenceConnection(state.connection_handle);
                if (connection == nullptr)
                {
                    atomic_set(&state.client_busy_value, 0);
                    failCache(state, -ENOTCONN);
                    continue;
                }
                setClientOperationToken(state, connection);
                static_cast<void>(startCacheHashRead(state, connection));
                bt_conn_unref(connection);
                continue;
            }

            struct bt_conn *connection = referenceConnection(state.connection_handle);
            if (connection == nullptr || !validClientOperation(state, connection))
            {
                if (connection != nullptr)
                {
                    bt_conn_unref(connection);
                }
                failCache(state, -ENOTCONN);
                continue;
            }

            switch (stage)
            {
                case CacheStage::gatt_service_found:
                    static_cast<void>(startCacheDiscovery(
                        state, connection, BT_UUID_GATT_SC,
                        cacheCharacteristicDiscovered,
                        static_cast<std::uint16_t>(state.gatt_service_start_handle + 1U),
                        state.gatt_service_end_handle, BT_GATT_DISCOVER_CHARACTERISTIC,
                        CacheStage::discovering_service_changed));
                    break;
                case CacheStage::service_changed_found:
                    static_cast<void>(startCacheDiscovery(
                        state, connection, BT_UUID_GATT_CCC,
                        cacheServiceChangedCccDiscovered,
                        static_cast<std::uint16_t>(state.service_changed_value_handle + 1U),
                        state.gatt_service_end_handle, BT_GATT_DISCOVER_DESCRIPTOR,
                        CacheStage::discovering_service_changed_ccc));
                    break;
                case CacheStage::service_changed_ccc_found:
                {
                    ::memset(&state.cache_subscribe_parameters, 0,
                             sizeof(state.cache_subscribe_parameters));
                    state.cache_subscribe_parameters.notify = cacheServiceChanged;
                    state.cache_subscribe_parameters.subscribe =
                        cacheServiceChangedSubscribed;
                    state.cache_subscribe_parameters.value_handle =
                        state.service_changed_value_handle;
                    state.cache_subscribe_parameters.ccc_handle =
                        state.service_changed_ccc_handle;
                    state.cache_subscribe_parameters.value = BT_GATT_CCC_INDICATE;
                    atomic_set_bit(state.cache_subscribe_parameters.flags,
                                   BT_GATT_SUBSCRIBE_FLAG_VOLATILE);
                    atomic_set(&state.cache_stage,
                               static_cast<atomic_val_t>(
                                   CacheStage::subscribing_service_changed));
                    const int result =
                        bt_gatt_subscribe(connection, &state.cache_subscribe_parameters);
                    if (result < 0)
                    {
                        failCache(state, result);
                    }
                    break;
                }
                case CacheStage::service_changed_subscribed:
                    static_cast<void>(startCacheDiscovery(
                        state, connection, BT_UUID_GATT_CLIENT_FEATURES,
                        cacheCharacteristicDiscovered,
                        static_cast<std::uint16_t>(state.gatt_service_start_handle + 1U),
                        state.gatt_service_end_handle, BT_GATT_DISCOVER_CHARACTERISTIC,
                        CacheStage::discovering_client_features));
                    break;
                case CacheStage::client_features_found:
                {
                    ::memset(&state.cache_write_parameters, 0,
                             sizeof(state.cache_write_parameters));
                    state.cache_write_parameters.func = cacheFeaturesWritten;
                    state.cache_write_parameters.handle = state.client_features_handle;
                    state.cache_write_parameters.offset = 0U;
                    state.cache_write_parameters.data = &state.client_features_value;
                    state.cache_write_parameters.length = 1U;
                    atomic_set(&state.cache_stage,
                               static_cast<atomic_val_t>(CacheStage::writing_client_features));
                    const int result =
                        bt_gatt_write(connection, &state.cache_write_parameters);
                    if (result < 0)
                    {
                        failCache(state, result);
                    }
                    break;
                }
                case CacheStage::client_features_written:
                    static_cast<void>(startCacheDiscovery(
                        state, connection, BT_UUID_GATT_DB_HASH,
                        cacheCharacteristicDiscovered,
                        static_cast<std::uint16_t>(state.gatt_service_start_handle + 1U),
                        state.gatt_service_end_handle, BT_GATT_DISCOVER_CHARACTERISTIC,
                        CacheStage::discovering_database_hash));
                    break;
                case CacheStage::database_hash_found:
                    static_cast<void>(startCacheHashRead(state, connection));
                    break;
                case CacheStage::database_hash_read:
                    atomic_set(&state.cache_stage,
                               static_cast<atomic_val_t>(
                                   CacheStage::discovering_target_service));
                    applyCacheOrDiscover(state, connection);
                    break;
                case CacheStage::target_service_found:
                {
                    const BLERemoteService service = copyRemoteService(state);
                    const struct bt_uuid *uuid =
                        state.target_characteristic_zephyr_uuid.assign(
                            state.target_characteristic_uuid);
                    if (uuid == nullptr)
                    {
                        failCache(state, -EINVAL);
                        break;
                    }
                    static_cast<void>(startCacheDiscovery(
                        state, connection, uuid, cacheTargetCharacteristicDiscovered,
                        static_cast<std::uint16_t>(service.startHandle() + 1U),
                        service.endHandle(), BT_GATT_DISCOVER_CHARACTERISTIC,
                        CacheStage::discovering_target_characteristic));
                    break;
                }
                case CacheStage::target_characteristic_found:
                {
                    const BLERemoteService service = copyRemoteService(state);
                    const BLERemoteCharacteristic characteristic =
                        copyRemoteCharacteristic(state);
                    const BLEProperty properties = characteristic.properties();
                    if (!hasProperty(properties, BLEProperty::notify) &&
                        !hasProperty(properties, BLEProperty::indicate))
                    {
                        completeCacheDiscovery(state);
                        break;
                    }
                    static_cast<void>(startCacheDiscovery(
                        state, connection, BT_UUID_GATT_CCC, cacheTargetCccDiscovered,
                        static_cast<std::uint16_t>(characteristic.valueHandle() + 1U),
                        service.endHandle(), BT_GATT_DISCOVER_DESCRIPTOR,
                        CacheStage::discovering_target_ccc));
                    break;
                }
                case CacheStage::target_ccc_found:
                    completeCacheDiscovery(state);
                    break;
                default:
                    break;
            }
            bt_conn_unref(connection);
        }
    }

    bool setGattDatabaseRevision(std::uint32_t revision) noexcept
    {
        if (revision == 0U || stackReady() || atomic_get(&database_state.registered) != 0)
        {
            recordError(revision == 0U ? BLEError::invalid_argument : BLEError::wrong_state,
                        revision == 0U ? -EINVAL : -EPERM, true);
            return false;
        }
        atomic_set(&database_state.revision, static_cast<atomic_val_t>(revision));
        return true;
    }

    std::uint32_t gattDatabaseRevision() noexcept
    {
        return static_cast<std::uint32_t>(atomic_get(&database_state.revision));
    }

    int prepareGattCacheDatabase() noexcept
    {
        if (atomic_get(&database_state.registered) != 0)
        {
            return 0;
        }
        assignRevisionUuid(gattDatabaseRevision());
        database_state.attribute.uuid = BT_UUID_GATT_PRIMARY;
        database_state.attribute.perm = BT_GATT_PERM_READ;
        database_state.attribute.read = bt_gatt_attr_read_service;
        database_state.attribute.write = nullptr;
        database_state.attribute.user_data = &database_state.revision_uuid.uuid;
        database_state.service.attrs = &database_state.attribute;
        database_state.service.attr_count = 1U;
        const int result = bt_gatt_service_register(&database_state.service);
        if (result == 0)
        {
            atomic_set(&database_state.registered, 1);
        }
        return result;
    }

    void rollbackGattCacheDatabase() noexcept
    {
        if (atomic_cas(&database_state.registered, 1, 0))
        {
            static_cast<void>(bt_gatt_service_unregister(&database_state.service));
        }
    }

    bool readGattDatabaseHash(std::uint8_t output[GattDatabase::hash_length]) noexcept
    {
        if (output == nullptr || !stackReady())
        {
            return false;
        }
        const struct bt_gatt_attr *attribute = nullptr;
        bt_gatt_foreach_attr(BT_ATT_FIRST_ATTRIBUTE_HANDLE, BT_ATT_LAST_ATTRIBUTE_HANDLE,
                             findDatabaseHash, &attribute);
        if (attribute == nullptr || attribute->read == nullptr)
        {
            return false;
        }
        const ssize_t length = attribute->read(nullptr, attribute, output,
                                               GattDatabase::hash_length, 0U);
        return length == static_cast<ssize_t>(GattDatabase::hash_length);
    }

    int recordGattDatabaseIdentity() noexcept
    {
#if defined(CONFIG_BT_GATT_CACHING)
        std::uint8_t hash[GattDatabase::hash_length] = {};
        if (!readGattDatabaseHash(hash))
        {
            return -EIO;
        }
        return saveDatabaseIdentity(gattDatabaseRevision(), hash);
#else
        return 0;
#endif
    }

} // namespace nucode::ble::internal::gatt

namespace nucode::ble::internal
{
    int recordGattDatabaseIdentity() noexcept
    {
        return gatt::recordGattDatabaseIdentity();
    }
} // namespace nucode::ble::internal

namespace nucode::ble
{
    bool GattDatabase::setRevision(std::uint32_t revision) noexcept
    {
        if (!internal::requireThreadContext())
        {
            return false;
        }
        return internal::gatt::setGattDatabaseRevision(revision);
    }

    std::uint32_t GattDatabase::revision() const noexcept
    {
        return internal::gatt::gattDatabaseRevision();
    }

    bool GattDatabase::hash(std::uint8_t output[hash_length]) const noexcept
    {
        if (!internal::requireThreadContext() || output == nullptr)
        {
            if (output == nullptr)
            {
                internal::recordError(BLEError::invalid_argument, -EINVAL, true);
            }
            return false;
        }
        return internal::gatt::readGattDatabaseHash(output);
    }

    bool GattClient::discoverCached(BLEConnectionHandle connection,
                                    const BLEUuid &service_uuid,
                                    const BLEUuid &characteristic_uuid,
                                    std::uint16_t schema_version) noexcept
    {
        if (!internal::requireThreadContext())
        {
            return false;
        }
        return internal::gatt::startCachedDiscovery(
            connection, service_uuid, characteristic_uuid, schema_version);
    }

    BLEGattCacheState GattClient::cacheState(BLEConnectionHandle connection) const noexcept
    {
        return internal::gatt::clientCacheState(connection);
    }

    bool GattClient::invalidateCache(BLEConnectionHandle connection) noexcept
    {
        if (!internal::requireThreadContext())
        {
            return false;
        }
        return internal::gatt::invalidateClientCache(connection);
    }

    BLEGattCacheStatistics GattClient::cacheStatistics() const noexcept
    {
        return internal::gatt::clientCacheStatistics();
    }
} // namespace nucode::ble

nucode::ble::GattDatabase BLEGattDatabase;

#endif
