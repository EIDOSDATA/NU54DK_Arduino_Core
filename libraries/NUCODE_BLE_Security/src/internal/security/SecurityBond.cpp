/** @file @brief boot bond snapshot·검증·삭제 rollback입니다.
 * SPDX-License-Identifier: MIT
 */
#if !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE)
#include "SecurityInternal.h"
#include <zephyr/sys/byteorder.h>

#include <stdio.h>
namespace nucode::ble::internal::security
{
    namespace
    {
        BondStorage state{};

        /** @brief settings 비활성 구성에서는 저장 record가 없는 것으로 처리합니다. */
        ssize_t loadSetting(const char *key, void *value, std::size_t capacity) noexcept
        {
#if defined(CONFIG_BT_SETTINGS)
            return settings_load_one(key, value, capacity);
#else
            static_cast<void>(key);
            static_cast<void>(value);
            static_cast<void>(capacity);
            return -ENOENT;
#endif
        }

        /** @brief settings 비활성 구성에서는 영속 저장을 지원하지 않음을 반환합니다. */
        int saveSetting(const char *key, const void *value, std::size_t length) noexcept
        {
#if defined(CONFIG_BT_SETTINGS)
            return settings_save_one(key, value, length);
#else
            static_cast<void>(key);
            static_cast<void>(value);
            static_cast<void>(length);
            return -ENOTSUP;
#endif
        }

        /** @brief settings 비활성 구성에서는 삭제할 영속 record가 없는 것으로 처리합니다. */
        int deleteSetting(const char *key) noexcept
        {
#if defined(CONFIG_BT_SETTINGS)
            return settings_delete(key);
#else
            static_cast<void>(key);
            return 0;
#endif
        }
    }
    BondStorage &bondStorage() noexcept
    {
        return state;
    }
    namespace
    {
        bt_addr_le_t startup_bonds[CONFIG_BT_MAX_PAIRED] = {};
        constexpr std::uint32_t metadata_magic = 0x32424e4dUL;
        constexpr std::uint16_t legacy_metadata_schema = 1U;
        constexpr std::uint16_t current_metadata_schema = 2U;
        constexpr std::size_t legacy_metadata_bytes = 20U;
        constexpr std::size_t current_metadata_bytes = 22U;
        constexpr std::uint8_t metadata_flag_sc = 0x01U;
        constexpr std::uint8_t metadata_flag_oob = 0x02U;

        /** @brief bond metadata record CRC-32를 heap 없이 계산합니다. */
        std::uint32_t metadataCrc(const std::uint8_t *data, std::size_t length) noexcept
        {
            std::uint32_t crc = 0xffffffffUL;
            for (std::size_t index = 0U; index < length; ++index)
            {
                crc ^= data[index];
                for (std::uint8_t bit = 0U; bit < 8U; ++bit)
                {
                    const std::uint32_t mask = 0U - (crc & 1U);
                    crc = (crc >> 1U) ^ (0xedb88320UL & mask);
                }
            }
            return ~crc;
        }

        /** @brief 고정 slot의 settings key를 생성합니다. */
        bool metadataKey(std::size_t index, char *key, std::size_t capacity) noexcept
        {
            return key != nullptr && index < maximum_bond_records &&
                   ::snprintf(key, capacity, "nucode/security/bond/%u",
                              static_cast<unsigned int>(index)) > 0;
        }

        /** @brief 공개 identity 주소 두 개가 같은지 확인합니다. */
        bool samePeer(const PeerAddress &left, const PeerAddress &right) noexcept
        {
            return left.type == right.type &&
                   ::memcmp(left.value, right.value, sizeof(left.value)) == 0;
        }

        /** @brief native 주소가 RPA가 아닌 유효 identity인지 확인합니다. */
        bool validIdentity(const bt_addr_le_t *peer) noexcept
        {
            if (peer == nullptr || isResolvablePrivateAddress(peer))
            {
                return false;
            }
            return peer->type == BT_ADDR_LE_PUBLIC || peer->type == BT_ADDR_LE_RANDOM ||
                   peer->type == BT_ADDR_LE_PUBLIC_ID || peer->type == BT_ADDR_LE_RANDOM_ID;
        }

        /** @brief schema 2 metadata record를 고정 byte 배열로 직렬화합니다. */
        void encodeMetadata(const BondMetadataSnapshot &metadata,
                            std::uint8_t record[current_metadata_bytes]) noexcept
        {
            ::memset(record, 0, current_metadata_bytes);
            sys_put_le32(metadata_magic, &record[0]);
            sys_put_le16(current_metadata_schema, &record[4]);
            record[6] = metadata.peer.type;
            ::memcpy(&record[7], metadata.peer.value, sizeof(metadata.peer.value));
            record[13] = metadata.key_size;
            record[14] = metadata.security_level;
            record[15] = metadata.flags;
            sys_put_le16(metadata.database_revision, &record[16]);
            sys_put_le32(metadataCrc(record, 18U), &record[18]);
        }

        /** @brief current/legacy metadata record를 검사해 공개 snapshot으로 복원합니다. */
        bool decodeMetadata(const std::uint8_t *record, std::size_t length,
                            std::uint16_t database_revision, BondMetadataSnapshot &metadata,
                            bool &legacy) noexcept
        {
            metadata = {};
            legacy = false;
            if (record == nullptr ||
                (length != legacy_metadata_bytes && length != current_metadata_bytes) ||
                sys_get_le32(&record[0]) != metadata_magic)
            {
                return false;
            }
            const std::uint16_t schema = sys_get_le16(&record[4]);
            const std::size_t crc_offset = schema == legacy_metadata_schema ? 16U : 18U;
            if ((schema == legacy_metadata_schema && length != legacy_metadata_bytes) ||
                (schema == current_metadata_schema && length != current_metadata_bytes) ||
                (schema != legacy_metadata_schema && schema != current_metadata_schema) ||
                sys_get_le32(&record[crc_offset]) != metadataCrc(record, crc_offset) ||
                (record[6] != BT_ADDR_LE_PUBLIC && record[6] != BT_ADDR_LE_RANDOM) ||
                record[13] != 16U || record[14] < BT_SECURITY_L2 || record[14] > BT_SECURITY_L4 ||
                (record[15] & metadata_flag_sc) == 0U)
            {
                return false;
            }
            metadata.peer.type = record[6];
            ::memcpy(metadata.peer.value, &record[7], sizeof(metadata.peer.value));
            metadata.key_size = record[13];
            metadata.security_level = record[14];
            metadata.flags = record[15];
            metadata.database_revision =
                schema == legacy_metadata_schema ? database_revision : sys_get_le16(&record[16]);
            if (metadata.database_revision != database_revision)
            {
                return false;
            }
            metadata.valid = true;
            legacy = schema == legacy_metadata_schema;
            return true;
        }

        /** @brief startup native bond 목록에 공개 peer가 존재하는지 확인합니다. */
        bool startupContains(const PeerAddress &peer) noexcept
        {
            bool found = false;
            k_spinlock_key_t key = k_spin_lock(&bondStorage().startup_bond_lock);
            for (std::size_t index = 0U; index < bondStorage().startup_bond_count; ++index)
            {
                if (samePeer(publicAddress(&startup_bonds[index]), peer))
                {
                    found = true;
                    break;
                }
            }
            k_spin_unlock(&bondStorage().startup_bond_lock, key);
            return found;
        }

        /** @brief metadata snapshot에 peer가 존재하는지 확인합니다. */
        bool metadataContains(const PeerAddress &peer) noexcept
        {
            bool found = false;
            k_spinlock_key_t key = k_spin_lock(&bondStorage().bond_lock);
            for (std::size_t index = 0U; index < maximum_bond_records; ++index)
            {
                const BondMetadataSnapshot &metadata = bondStorage().metadata[index];
                if (metadata.valid && samePeer(metadata.peer, peer))
                {
                    found = true;
                    break;
                }
            }
            k_spin_unlock(&bondStorage().bond_lock, key);
            return found;
        }

        /** @brief invalid metadata와 metadata 없는 native bond를 fail-closed로 정리합니다. */
        void loadBondMetadata() noexcept
        {
            BondMetadataSnapshot loaded[maximum_bond_records] = {};
            for (std::size_t index = 0U; index < maximum_bond_records; ++index)
            {
                char key[40] = {};
                std::uint8_t record[current_metadata_bytes] = {};
                if (!metadataKey(index, key, sizeof(key)))
                {
                    continue;
                }
                const ssize_t length = loadSetting(key, record, sizeof(record));
                if (length == 0 || length == -ENOENT)
                {
                    continue;
                }
                bool legacy = false;
                if (length < 0 ||
                    !decodeMetadata(record, static_cast<std::size_t>(length),
                                    securityState().security_config.bond_database_revision,
                                    loaded[index], legacy) ||
                    !startupContains(loaded[index].peer))
                {
                    static_cast<void>(deleteSetting(key));
                    atomic_inc(&bondStorage().rejected_count);
                    continue;
                }
                bool duplicate = false;
                for (std::size_t previous = 0U; previous < index; ++previous)
                {
                    duplicate = duplicate || (loaded[previous].valid &&
                                              samePeer(loaded[previous].peer, loaded[index].peer));
                }
                if (duplicate)
                {
                    loaded[index] = {};
                    static_cast<void>(deleteSetting(key));
                    atomic_inc(&bondStorage().rejected_count);
                    continue;
                }
                if (legacy)
                {
                    std::uint8_t migrated[current_metadata_bytes] = {};
                    encodeMetadata(loaded[index], migrated);
                    if (saveSetting(key, migrated, sizeof(migrated)) != 0)
                    {
                        loaded[index] = {};
                        static_cast<void>(deleteSetting(key));
                        atomic_inc(&bondStorage().rejected_count);
                        continue;
                    }
                    atomic_inc(&bondStorage().migration_count);
                    const bt_addr_le_t migrated_peer = nativeAddress(loaded[index].peer);
                    queueEvent(makePeerEvent(SecurityEvent::bond_metadata_migrated, &migrated_peer,
                                             BondState::none));
                }
            }

            k_spinlock_key_t metadata_key = k_spin_lock(&bondStorage().bond_lock);
            for (std::size_t index = 0U; index < maximum_bond_records; ++index)
            {
                bondStorage().metadata[index] = loaded[index];
            }
            k_spin_unlock(&bondStorage().bond_lock, metadata_key);

            bt_addr_le_t rejected[CONFIG_BT_MAX_PAIRED] = {};
            std::size_t rejected_count = 0U;
            k_spinlock_key_t startup_key = k_spin_lock(&bondStorage().startup_bond_lock);
            for (std::size_t index = 0U; index < bondStorage().startup_bond_count; ++index)
            {
                if (!metadataContains(publicAddress(&startup_bonds[index])) &&
                    rejected_count < ARRAY_SIZE(rejected))
                {
                    bt_addr_le_copy(&rejected[rejected_count++], &startup_bonds[index]);
                }
            }
            k_spin_unlock(&bondStorage().startup_bond_lock, startup_key);
            for (std::size_t index = 0U; index < rejected_count; ++index)
            {
                const bt_addr_le_t peer = rejected[index];
                static_cast<void>(bt_unpair(BT_ID_DEFAULT, &peer));
                removeStartupBond(&peer);
                atomic_inc(&bondStorage().rejected_count);
                queueEvent(
                    makePeerEvent(SecurityEvent::bond_metadata_rejected, &peer, BondState::none));
            }
        }
    } // namespace
    /** @brief 공개 가능한 현재 bond 상태 snapshot을 반환합니다. */
    BondState currentBondState() noexcept
    {
        return static_cast<BondState>(atomic_get(&bondStorage().bond_state_value));
    }

    /** @brief exact link의 bond 상태를 generation slot에서 반환합니다. */
    BondState currentBondState(struct bt_conn *connection) noexcept
    {
        if (connection == nullptr)
        {
            return BondState::none;
        }
        BondState result = BondState::none;
        k_spinlock_key_t key = k_spin_lock(&securityState().connection_lock);
        for (std::size_t index = 0U; index < maximum_security_links; ++index)
        {
            const SecurityLinkState &link = securityState().links[index];
            if (link.connection == connection)
            {
                result = link.bond_lifecycle.state;
                break;
            }
        }
        k_spin_unlock(&securityState().connection_lock, key);
        return result;
    }

    /** @brief 현재 peer의 bond 상태를 원자적으로 교체합니다. */
    void setBondLifecycle(const bt_addr_le_t *peer, BondState state,
                          bool paired_this_connection) noexcept
    {
        k_spinlock_key_t key = k_spin_lock(&bondStorage().bond_lock);
        bondStorage().bond_lifecycle = {};
        if (peer != nullptr)
        {
            bt_addr_le_copy(&bondStorage().bond_lifecycle.peer, peer);
            bondStorage().bond_lifecycle.peer_valid = true;
        }
        bondStorage().bond_lifecycle.state = state;
        bondStorage().bond_lifecycle.paired_this_connection = paired_this_connection;
        k_spin_unlock(&bondStorage().bond_lock, key);
        atomic_set(&bondStorage().bond_state_value, static_cast<atomic_val_t>(state));
    }

    /** @brief exact link의 bond 상태와 필요 시 legacy mirror를 교체합니다. */
    void setBondLifecycle(struct bt_conn *connection, const bt_addr_le_t *peer, BondState state,
                          bool paired_this_connection) noexcept
    {
        bool found = false;
        bool legacy = false;
        k_spinlock_key_t key = k_spin_lock(&securityState().connection_lock);
        for (std::size_t index = 0U; index < maximum_security_links; ++index)
        {
            SecurityLinkState &link = securityState().links[index];
            if (link.connection != connection)
            {
                continue;
            }
            link.bond_lifecycle = {};
            if (peer != nullptr)
            {
                bt_addr_le_copy(&link.bond_lifecycle.peer, peer);
                link.bond_lifecycle.peer_valid = true;
            }
            link.bond_lifecycle.state = state;
            link.bond_lifecycle.paired_this_connection = paired_this_connection;
            found = true;
            legacy = securityState().active_connection == connection;
            break;
        }
        k_spin_unlock(&securityState().connection_lock, key);
        if (found && legacy)
        {
            setBondLifecycle(peer, state, paired_this_connection);
        }
    }

    /** @brief 지정 peer와 현재 bond 후보가 같은지 확인합니다. */
    bool bondLifecycleMatches(const bt_addr_le_t *peer) noexcept
    {
        if (peer == nullptr)
        {
            return false;
        }
        bool matches = false;
        k_spinlock_key_t key = k_spin_lock(&bondStorage().bond_lock);
        matches = bondStorage().bond_lifecycle.peer_valid &&
                  bt_addr_le_eq(&bondStorage().bond_lifecycle.peer, peer);
        k_spin_unlock(&bondStorage().bond_lock, key);
        return matches;
    }

    /** @brief 지정 connection의 bond 후보와 peer가 같은지 확인합니다. */
    bool bondLifecycleMatches(struct bt_conn *connection, const bt_addr_le_t *peer) noexcept
    {
        if (connection == nullptr || peer == nullptr)
        {
            return false;
        }
        bool matches = false;
        k_spinlock_key_t key = k_spin_lock(&securityState().connection_lock);
        for (std::size_t index = 0U; index < maximum_security_links; ++index)
        {
            const SecurityLinkState &link = securityState().links[index];
            if (link.connection == connection)
            {
                matches = link.bond_lifecycle.peer_valid &&
                          bt_addr_le_eq(&link.bond_lifecycle.peer, peer);
                break;
            }
        }
        k_spin_unlock(&securityState().connection_lock, key);
        return matches;
    }

    /** @brief 오류 rollback에 사용할 bond 상태 snapshot을 복사합니다. */
    BondLifecycleState copyBondLifecycle() noexcept
    {
        BondLifecycleState snapshot = {};
        k_spinlock_key_t key = k_spin_lock(&bondStorage().bond_lock);
        snapshot = bondStorage().bond_lifecycle;
        k_spin_unlock(&bondStorage().bond_lock, key);
        return snapshot;
    }

    /** @brief exact link의 bond 상태 snapshot을 복사합니다. */
    BondLifecycleState copyBondLifecycle(struct bt_conn *connection) noexcept
    {
        BondLifecycleState snapshot = {};
        if (connection == nullptr)
        {
            return snapshot;
        }
        k_spinlock_key_t key = k_spin_lock(&securityState().connection_lock);
        for (std::size_t index = 0U; index < maximum_security_links; ++index)
        {
            const SecurityLinkState &link = securityState().links[index];
            if (link.connection == connection)
            {
                snapshot = link.bond_lifecycle;
                break;
            }
        }
        k_spin_unlock(&securityState().connection_lock, key);
        return snapshot;
    }

    /** @brief 이전 bond 상태 snapshot을 복원합니다. */
    void restoreBondLifecycle(const BondLifecycleState &snapshot) noexcept
    {
        setBondLifecycle(snapshot.peer_valid ? &snapshot.peer : nullptr, snapshot.state,
                         snapshot.paired_this_connection);
    }

    /** @brief boot 때 로드된 bond 목록에 peer가 있었는지 확인합니다. */
    bool isStartupBond(const bt_addr_le_t *peer) noexcept
    {
        if (peer == nullptr)
        {
            return false;
        }
        bool found = false;
        k_spinlock_key_t key = k_spin_lock(&bondStorage().startup_bond_lock);
        for (std::size_t index = 0U; index < bondStorage().startup_bond_count; ++index)
        {
            if (bt_addr_le_eq(&startup_bonds[index], peer))
            {
                found = true;
                break;
            }
        }
        k_spin_unlock(&bondStorage().startup_bond_lock, key);
        return found;
    }

    /** @brief 실제 삭제 callback을 받은 peer를 boot bond snapshot에서 제거합니다. */
    void removeStartupBond(const bt_addr_le_t *peer) noexcept
    {
        if (peer == nullptr)
        {
            return;
        }
        k_spinlock_key_t key = k_spin_lock(&bondStorage().startup_bond_lock);
        for (std::size_t index = 0U; index < bondStorage().startup_bond_count; ++index)
        {
            if (!bt_addr_le_eq(&startup_bonds[index], peer))
            {
                continue;
            }
            for (std::size_t move = index + 1U; move < bondStorage().startup_bond_count; ++move)
            {
                bt_addr_le_copy(&startup_bonds[move - 1U], &startup_bonds[move]);
            }
            --bondStorage().startup_bond_count;
            break;
        }
        k_spin_unlock(&bondStorage().startup_bond_lock, key);
    }

    /** @brief resolved identity에 유효한 current metadata가 있는지 확인합니다. */
    bool bondMetadataValid(const bt_addr_le_t *peer) noexcept
    {
        if (!validIdentity(peer))
        {
            return false;
        }
        return metadataContains(publicAddress(peer));
    }

    /** @brief 복원 link가 metadata의 key 크기·수준·SC/OOB flag를 충족하는지 확인합니다. */
    bool bondMetadataValid(struct bt_conn *connection) noexcept
    {
        if (connection == nullptr || !validIdentity(bt_conn_get_dst(connection)))
        {
            return false;
        }
        BondMetadataSnapshot expected = {};
        const PeerAddress peer = publicAddress(bt_conn_get_dst(connection));
        k_spinlock_key_t key = k_spin_lock(&bondStorage().bond_lock);
        for (std::size_t index = 0U; index < maximum_bond_records; ++index)
        {
            const BondMetadataSnapshot &metadata = bondStorage().metadata[index];
            if (metadata.valid && samePeer(metadata.peer, peer))
            {
                expected = metadata;
                break;
            }
        }
        k_spin_unlock(&bondStorage().bond_lock, key);
        if (!expected.valid)
        {
            return false;
        }
        struct bt_conn_info information = {};
        if (bt_conn_get_info(connection, &information) < 0)
        {
            return false;
        }
        const bool oob_required = (expected.flags & metadata_flag_oob) != 0U;
        const bool oob_present =
            (static_cast<std::uint8_t>(information.security.flags) & BT_SECURITY_FLAG_OOB) != 0U;
        return information.security.enc_key_size == expected.key_size &&
               information.security.level >= expected.security_level &&
               (static_cast<std::uint8_t>(information.security.flags) & BT_SECURITY_FLAG_SC) !=
                   0U &&
               (!oob_required || oob_present);
    }

    /** @brief 새 bond의 검증 metadata를 resolved identity 기준 고정 slot에 저장합니다. */
    bool persistBondMetadata(struct bt_conn *connection) noexcept
    {
        const bt_addr_le_t *const native_peer =
            connection == nullptr ? nullptr : bt_conn_get_dst(connection);
        if (!validIdentity(native_peer))
        {
            return false;
        }
        struct bt_conn_info information = {};
        if (bt_conn_get_info(connection, &information) < 0 ||
            information.security.enc_key_size != 16U ||
            information.security.level < BT_SECURITY_L2 ||
            information.security.level > BT_SECURITY_L4 ||
            (static_cast<std::uint8_t>(information.security.flags) & BT_SECURITY_FLAG_SC) == 0U)
        {
            return false;
        }

        BondMetadataSnapshot metadata = {};
        metadata.peer = publicAddress(native_peer);
        metadata.database_revision = securityState().security_config.bond_database_revision;
        metadata.key_size = information.security.enc_key_size;
        metadata.security_level = static_cast<std::uint8_t>(information.security.level);
        metadata.flags = metadata_flag_sc;
        if ((static_cast<std::uint8_t>(information.security.flags) & BT_SECURITY_FLAG_OOB) != 0U)
        {
            metadata.flags |= metadata_flag_oob;
        }
        metadata.valid = true;

        std::size_t selected = maximum_bond_records;
        k_spinlock_key_t key = k_spin_lock(&bondStorage().bond_lock);
        for (std::size_t index = 0U; index < maximum_bond_records; ++index)
        {
            if (bondStorage().metadata[index].valid &&
                samePeer(bondStorage().metadata[index].peer, metadata.peer))
            {
                selected = index;
                break;
            }
            if (selected == maximum_bond_records && !bondStorage().metadata[index].valid)
            {
                selected = index;
            }
        }
        k_spin_unlock(&bondStorage().bond_lock, key);
        if (selected == maximum_bond_records)
        {
            return false;
        }

        char settings_key[40] = {};
        std::uint8_t record[current_metadata_bytes] = {};
        if (!metadataKey(selected, settings_key, sizeof(settings_key)))
        {
            return false;
        }
        encodeMetadata(metadata, record);
        if (saveSetting(settings_key, record, sizeof(record)) != 0)
        {
            return false;
        }
        key = k_spin_lock(&bondStorage().bond_lock);
        bondStorage().metadata[selected] = metadata;
        k_spin_unlock(&bondStorage().bond_lock, key);
        return true;
    }

    /** @brief 지정 identity의 metadata를 native bond와 함께 제거합니다. */
    void eraseBondMetadata(const bt_addr_le_t *peer) noexcept
    {
        if (peer == nullptr)
        {
            return;
        }
        const PeerAddress target = publicAddress(peer);
        for (std::size_t index = 0U; index < maximum_bond_records; ++index)
        {
            bool matching = false;
            k_spinlock_key_t key = k_spin_lock(&bondStorage().bond_lock);
            matching = bondStorage().metadata[index].valid &&
                       samePeer(bondStorage().metadata[index].peer, target);
            if (matching)
            {
                bondStorage().metadata[index] = {};
            }
            k_spin_unlock(&bondStorage().bond_lock, key);
            if (matching)
            {
                char settings_key[40] = {};
                if (metadataKey(index, settings_key, sizeof(settings_key)))
                {
                    static_cast<void>(deleteSetting(settings_key));
                }
            }
        }
    }

    /** @brief 네 metadata slot을 모두 삭제합니다. */
    void eraseAllBondMetadata() noexcept
    {
        for (std::size_t index = 0U; index < maximum_bond_records; ++index)
        {
            char settings_key[40] = {};
            if (metadataKey(index, settings_key, sizeof(settings_key)))
            {
                static_cast<void>(deleteSetting(settings_key));
            }
        }
        k_spinlock_key_t key = k_spin_lock(&bondStorage().bond_lock);
        for (std::size_t index = 0U; index < maximum_bond_records; ++index)
        {
            bondStorage().metadata[index] = {};
        }
        k_spin_unlock(&bondStorage().bond_lock, key);
    }

    /** @brief L2 이상으로 확인된 저장 bond 후보를 검증 완료 상태로 승격합니다. */
    void verifySecureBond(struct bt_conn *connection, bt_security_t level) noexcept
    {
        if (connection == nullptr || level < BT_SECURITY_L2)
        {
            return;
        }
        const bt_addr_le_t *const peer = bt_conn_get_dst(connection);
        if (bondLifecycleMatches(connection, peer) &&
            currentBondState(connection) == BondState::restored_candidate)
        {
            if (!bondMetadataValid(connection))
            {
                static_cast<void>(bt_unpair(BT_ID_DEFAULT, peer));
                eraseBondMetadata(peer);
                removeStartupBond(peer);
                atomic_inc(&bondStorage().rejected_count);
                setBondLifecycle(connection, nullptr, BondState::none, false);
                setLinkPaired(connection, false);
                queueEvent(makeEvent(SecurityEvent::bond_metadata_rejected, connection));
                return;
            }
            setBondLifecycle(connection, peer, BondState::verified, false);
            setLinkPaired(connection, true);
            queueEvent(makeEvent(SecurityEvent::bond_verified, connection));
        }
        else if (currentBondState(connection) != BondState::removal_requested)
        {
            setLinkPaired(connection, true);
        }
    }

    /** @brief 첫 연결에서 boot 시작 bond 목록을 최초 한 번만 고정합니다. */
    void captureStartupBonds() noexcept
    {
        if (!atomic_cas(&bondStorage().startup_bond_snapshot_ready, 0, 1))
        {
            return;
        }

        struct Snapshot
        {
            bt_addr_le_t bonds[ARRAY_SIZE(startup_bonds)] = {};
            std::size_t count = 0U;
        } snapshot;
        if (nucode::ble::internal::settingsReady())
        {
            bt_foreach_bond(
                BT_ID_DEFAULT,
                [](const struct bt_bond_info *information, void *context)
                {
                    Snapshot *output = static_cast<Snapshot *>(context);
                    if (information != nullptr && output != nullptr &&
                        output->count < ARRAY_SIZE(output->bonds))
                    {
                        bt_addr_le_copy(&output->bonds[output->count], &information->addr);
                        ++output->count;
                    }
                },
                &snapshot);
        }

        k_spinlock_key_t key = k_spin_lock(&bondStorage().startup_bond_lock);
        bondStorage().startup_bond_count = snapshot.count;
        for (std::size_t index = 0U; index < snapshot.count; ++index)
        {
            bt_addr_le_copy(&startup_bonds[index], &snapshot.bonds[index]);
        }
        k_spin_unlock(&bondStorage().startup_bond_lock, key);
        loadBondMetadata();
    }

} // namespace nucode::ble::internal::security
namespace nucode::ble
{
    using namespace internal::security;
    std::size_t SecurityManager::bondCount() const noexcept
    {
        std::size_t count = 0U;
        bt_foreach_bond(
            BT_ID_DEFAULT,
            [](const struct bt_bond_info *information, void *context)
            {
                ARG_UNUSED(information);
                std::size_t *value = static_cast<std::size_t *>(context);
                if (value != nullptr)
                {
                    ++(*value);
                }
            },
            &count);
        return count;
    }

    std::size_t SecurityManager::copyBonds(PeerAddress *buffer, std::size_t capacity) const noexcept
    {
        if (buffer == nullptr || capacity == 0U)
        {
            return 0U;
        }
        struct Context
        {
            PeerAddress *buffer;
            std::size_t capacity;
            std::size_t count;
        } context = {buffer, capacity, 0U};
        bt_foreach_bond(
            BT_ID_DEFAULT,
            [](const struct bt_bond_info *information, void *opaque)
            {
                Context *output = static_cast<Context *>(opaque);
                if (output != nullptr && output->count < output->capacity)
                {
                    output->buffer[output->count++] = publicAddress(&information->addr);
                }
            },
            &context);
        return context.count;
    }

    std::uint16_t SecurityManager::bondDatabaseRevision() const noexcept
    {
        return securityState().security_config.bond_database_revision;
    }

    std::uint32_t SecurityManager::bondMigrationCount() const noexcept
    {
        return static_cast<std::uint32_t>(atomic_get(&bondStorage().migration_count));
    }

    std::uint32_t SecurityManager::rejectedBondCount() const noexcept
    {
        return static_cast<std::uint32_t>(atomic_get(&bondStorage().rejected_count));
    }

    bool SecurityManager::eraseBond(const PeerAddress &peer) noexcept
    {
        if (!requireThreadContext())
        {
            return false;
        }
        const bt_addr_le_t address = nativeAddress(peer);
        const BondLifecycleState previous = copyBondLifecycle();
        struct bt_conn *connection = referenceActiveConnection();
        const BondLifecycleState link_previous = copyBondLifecycle(connection);
        if (bondLifecycleMatches(&address))
        {
            setBondLifecycle(&address, BondState::removal_requested, false);
        }
        if (connection != nullptr && bondLifecycleMatches(connection, &address))
        {
            setBondLifecycle(connection, &address, BondState::removal_requested, false);
        }
        const int result = bt_unpair(BT_ID_DEFAULT, &address);
        if (result < 0)
        {
            restoreBondLifecycle(previous);
            if (connection != nullptr)
            {
                setBondLifecycle(connection,
                                 link_previous.peer_valid ? &link_previous.peer : nullptr,
                                 link_previous.state, link_previous.paired_this_connection);
            }
            if (connection != nullptr)
            {
                bt_conn_unref(connection);
            }
            recordSecurityError(SecurityError::driver_error, result);
            return false;
        }
        if (connection != nullptr)
        {
            bt_conn_unref(connection);
        }
        eraseBondMetadata(&address);
        queueEvent(makePeerEvent(SecurityEvent::bond_removal_requested, &address,
                                 BondState::removal_requested));
        recordSecurityError(SecurityError::none);
        return true;
    }

    bool SecurityManager::eraseAllBonds() noexcept
    {
        if (!requireThreadContext())
        {
            return false;
        }
        const BondLifecycleState previous = copyBondLifecycle();
        struct bt_conn *connection = referenceActiveConnection();
        const BondLifecycleState link_previous = copyBondLifecycle(connection);
        setBondLifecycle(previous.peer_valid ? &previous.peer : nullptr,
                         BondState::removal_requested, false);
        if (connection != nullptr)
        {
            setBondLifecycle(connection, link_previous.peer_valid ? &link_previous.peer : nullptr,
                             BondState::removal_requested, false);
        }
        const int result = bt_unpair(BT_ID_DEFAULT, BT_ADDR_LE_ANY);
        if (result < 0)
        {
            restoreBondLifecycle(previous);
            if (connection != nullptr)
            {
                setBondLifecycle(connection,
                                 link_previous.peer_valid ? &link_previous.peer : nullptr,
                                 link_previous.state, link_previous.paired_this_connection);
                bt_conn_unref(connection);
            }
            recordSecurityError(SecurityError::driver_error, result);
            return false;
        }
        if (connection != nullptr)
        {
            bt_conn_unref(connection);
        }
        eraseAllBondMetadata();
        queueEvent(makePeerEvent(SecurityEvent::all_bonds_removal_requested, nullptr,
                                 BondState::removal_requested));
        recordSecurityError(SecurityError::none);
        return true;
    }

} // namespace nucode::ble
#endif
