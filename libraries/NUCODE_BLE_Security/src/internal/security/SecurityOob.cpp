/**
 * @file SecurityOob.cpp
 * @brief 유선·NFC carrier가 공유하는 LE Secure Connections OOB 구현입니다.
 *
 * SPDX-License-Identifier: MIT
 */
#if !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE)
#include "SecurityInternal.h"

#include <zephyr/sys/byteorder.h>

namespace nucode::ble::internal::security
{
    namespace
    {
        OobState state{};
        constexpr std::uint8_t frame_magic[4] = {'N', '3', '0', 'O'};
        constexpr std::size_t frame_crc_offset = 70U;

        /** @brief 공개 OOB 역할 값이 고정 두 값 중 하나인지 확인합니다. */
        bool validRole(OobRole role) noexcept
        {
            return role == OobRole::peripheral || role == OobRole::central;
        }

        /** @brief 공개 주소 표현이 지원되는 identity/random type인지 확인합니다. */
        bool validAddress(const PeerAddress &address) noexcept
        {
            return address.type == BT_ADDR_LE_PUBLIC || address.type == BT_ADDR_LE_RANDOM;
        }

        /** @brief session nonce가 실수로 비어 있지 않은지 확인합니다. */
        bool validNonce(const std::uint8_t *nonce, std::size_t length) noexcept
        {
            if (nonce == nullptr || length != 16U)
            {
                return false;
            }
            std::uint8_t combined = 0U;
            for (std::size_t index = 0U; index < length; ++index)
            {
                combined |= nonce[index];
            }
            return combined != 0U;
        }

        /** @brief canonical OOB record의 공개 필드를 검사합니다. */
        bool validRecord(const SecureConnectionsOobRecord &record) noexcept
        {
            return record.schema == SecureConnectionsOobRecord::current_schema &&
                   validRole(record.role) && validAddress(record.identity) &&
                   validAddress(record.pairing_address) &&
                   validNonce(record.session_nonce, sizeof(record.session_nonce));
        }

        /** @brief heap 없이 frame 무결성에 사용하는 표준 CRC-32를 계산합니다. */
        std::uint32_t crc32(const std::uint8_t *data, std::size_t length) noexcept
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

        /** @brief OOB 역할을 고정 slot index로 변환합니다. */
        std::size_t roleIndex(OobRole role) noexcept
        {
            return role == OobRole::peripheral ? 0U : 1U;
        }

        /** @brief connection의 로컬 역할을 공개 OOB 역할로 변환합니다. */
        bool connectionRole(const struct bt_conn_info &information, OobRole &role) noexcept
        {
            if (information.role == BT_CONN_ROLE_PERIPHERAL)
            {
                role = OobRole::peripheral;
                return true;
            }
            if (information.role == BT_CONN_ROLE_CENTRAL)
            {
                role = OobRole::central;
                return true;
            }
            return false;
        }

        /** @brief 두 공개 주소가 byte 단위로 같은지 확인합니다. */
        bool sameAddress(const PeerAddress &left, const PeerAddress &right) noexcept
        {
            return left.type == right.type &&
                   ::memcmp(left.value, right.value, sizeof(left.value)) == 0;
        }

        /** @brief callback 실패를 fail-closed 취소와 비밀 없는 event로 기록합니다. */
        void rejectOob(struct bt_conn *connection, int error, std::uint8_t reason) noexcept
        {
            static_cast<void>(bt_conn_auth_cancel(connection));
            recordSecurityError(SecurityError::rejected, error);
            queueEvent(makeEvent(SecurityEvent::oob_data_rejected, connection, 0U, reason));
        }
    } // namespace

    OobState &oobState() noexcept
    {
        return state;
    }

    /** @brief begin 때 두 OOB slot과 stack 광고 flag를 초기화합니다. */
    void resetOobState() noexcept
    {
        k_spinlock_key_t key = k_spin_lock(&oobState().lock);
        oobState().slots[0] = {};
        oobState().slots[0].role = OobRole::peripheral;
        oobState().slots[1] = {};
        oobState().slots[1].role = OobRole::central;
        k_spin_unlock(&oobState().lock, key);
        bt_le_oob_set_sc_flag(false);
    }

    /** @brief SMP callback에서 exact link 주소와 저장 record를 대조해 OOB data를 공급합니다. */
    void oobDataRequest(struct bt_conn *connection, struct bt_conn_oob_info *information)
    {
        if (connection == nullptr || information == nullptr ||
            information->type != bt_conn_oob_info::BT_CONN_OOB_LE_SC ||
            !securityState().security_config.secure_connections_oob ||
            !isActiveConnection(connection))
        {
            if (connection != nullptr)
            {
                rejectOob(connection, -EINVAL, 1U);
            }
            return;
        }

        struct bt_conn_info connection_information = {};
        OobRole role = OobRole::peripheral;
        if (bt_conn_get_info(connection, &connection_information) < 0 ||
            !connectionRole(connection_information, role) ||
            connection_information.le.local == nullptr ||
            connection_information.le.remote == nullptr)
        {
            rejectOob(connection, -ENOTCONN, 2U);
            return;
        }

        OobSlot snapshot = {};
        k_spinlock_key_t key = k_spin_lock(&oobState().lock);
        snapshot = oobState().slots[roleIndex(role)];
        k_spin_unlock(&oobState().lock, key);

        const PeerAddress local_address = publicAddress(connection_information.le.local);
        const PeerAddress remote_address = publicAddress(connection_information.le.remote);
        const bool local_required =
            information->lesc.oob_config !=
            decltype(bt_conn_oob_info{}.lesc)::BT_CONN_OOB_REMOTE_ONLY;
        const bool remote_required =
            information->lesc.oob_config !=
            decltype(bt_conn_oob_info{}.lesc)::BT_CONN_OOB_LOCAL_ONLY;
        if (local_required &&
            (!snapshot.local_valid ||
             !sameAddress(snapshot.local.pairing_address, local_address)))
        {
            rejectOob(connection, -EACCES, 3U);
            return;
        }
        if (remote_required &&
            (!snapshot.remote_valid ||
             !sameAddress(snapshot.remote.pairing_address, remote_address)))
        {
            rejectOob(connection, -EACCES, 4U);
            return;
        }
        if (snapshot.local_valid && snapshot.remote_valid &&
            ::memcmp(snapshot.local.session_nonce, snapshot.remote.session_nonce,
                     sizeof(snapshot.local.session_nonce)) != 0)
        {
            rejectOob(connection, -EACCES, 5U);
            return;
        }

        struct bt_le_oob_sc_data local = {};
        struct bt_le_oob_sc_data remote = {};
        if (local_required)
        {
            ::memcpy(local.r, snapshot.local.random, sizeof(local.r));
            ::memcpy(local.c, snapshot.local.confirm, sizeof(local.c));
        }
        if (remote_required)
        {
            ::memcpy(remote.r, snapshot.remote.random, sizeof(remote.r));
            ::memcpy(remote.c, snapshot.remote.confirm, sizeof(remote.c));
        }
        const int result = bt_le_oob_set_sc_data(connection, local_required ? &local : nullptr,
                                                  remote_required ? &remote : nullptr);
        if (result != 0)
        {
            rejectOob(connection, result, 6U);
            return;
        }
        markPairingStarted(connection);
        recordSecurityError(SecurityError::none);
        queueEvent(makeEvent(SecurityEvent::oob_data_applied, connection));
    }

} // namespace nucode::ble::internal::security

namespace nucode::ble
{
    using namespace internal::security;

    namespace
    {
        constexpr char ndef_mime_type[] = "application/vnd.bluetooth.le.oob";
        constexpr std::uint8_t ndef_header = 0xd2U;
        constexpr std::uint8_t ad_le_address = 0x1bU;
        constexpr std::uint8_t ad_le_role = 0x1cU;
        constexpr std::uint8_t ad_sc_confirm = 0x22U;
        constexpr std::uint8_t ad_sc_random = 0x23U;
        constexpr std::uint8_t ad_manufacturer = 0xffU;
        constexpr std::uint16_t nucode_company_id = 0xffffU;
        constexpr std::size_t ndef_payload_bytes = 126U;
        constexpr std::size_t ndef_record_bytes =
            3U + sizeof(ndef_mime_type) - 1U + ndef_payload_bytes;

        /** @brief NDEF payload에 하나의 Bluetooth AD structure를 추가합니다. */
        [[maybe_unused]] bool appendAd(std::uint8_t type, const std::uint8_t *value,
                                       std::size_t value_length, std::uint8_t *payload,
                                       std::size_t capacity, std::size_t &cursor) noexcept
        {
            if (value == nullptr || value_length + 1U > 255U ||
                cursor + value_length + 2U > capacity)
            {
                return false;
            }
            payload[cursor++] = static_cast<std::uint8_t>(value_length + 1U);
            payload[cursor++] = type;
            ::memcpy(&payload[cursor], value, value_length);
            cursor += value_length;
            return true;
        }
    } // namespace

    bool OobFrameCodec::encode(const SecureConnectionsOobRecord &record, std::uint8_t *buffer,
                               std::size_t capacity, std::size_t &length) noexcept
    {
        length = 0U;
        if (buffer == nullptr || capacity < frame_bytes || !validRecord(record))
        {
            return false;
        }
        ::memset(buffer, 0, frame_bytes);
        ::memcpy(&buffer[0], frame_magic, sizeof(frame_magic));
        buffer[4] = record.schema;
        buffer[5] = static_cast<std::uint8_t>(record.role);
        sys_put_le16(static_cast<std::uint16_t>(frame_bytes), &buffer[6]);
        buffer[8] = record.identity.type;
        ::memcpy(&buffer[9], record.identity.value, sizeof(record.identity.value));
        buffer[15] = record.pairing_address.type;
        ::memcpy(&buffer[16], record.pairing_address.value,
                 sizeof(record.pairing_address.value));
        ::memcpy(&buffer[22], record.random, sizeof(record.random));
        ::memcpy(&buffer[38], record.confirm, sizeof(record.confirm));
        ::memcpy(&buffer[54], record.session_nonce, sizeof(record.session_nonce));
        sys_put_le32(crc32(buffer, frame_crc_offset), &buffer[frame_crc_offset]);
        length = frame_bytes;
        return true;
    }

    bool OobFrameCodec::decode(const std::uint8_t *buffer, std::size_t length,
                               SecureConnectionsOobRecord &record) noexcept
    {
        record = {};
        if (buffer == nullptr || length != frame_bytes ||
            ::memcmp(&buffer[0], frame_magic, sizeof(frame_magic)) != 0 ||
            sys_get_le16(&buffer[6]) != frame_bytes ||
            sys_get_le32(&buffer[frame_crc_offset]) != crc32(buffer, frame_crc_offset))
        {
            return false;
        }
        SecureConnectionsOobRecord candidate = {};
        candidate.schema = buffer[4];
        candidate.role = static_cast<OobRole>(buffer[5]);
        candidate.identity.type = buffer[8];
        ::memcpy(candidate.identity.value, &buffer[9], sizeof(candidate.identity.value));
        candidate.pairing_address.type = buffer[15];
        ::memcpy(candidate.pairing_address.value, &buffer[16],
                 sizeof(candidate.pairing_address.value));
        ::memcpy(candidate.random, &buffer[22], sizeof(candidate.random));
        ::memcpy(candidate.confirm, &buffer[38], sizeof(candidate.confirm));
        ::memcpy(candidate.session_nonce, &buffer[54], sizeof(candidate.session_nonce));
        if (!validRecord(candidate))
        {
            return false;
        }
        record = candidate;
        return true;
    }

    bool OobNdefAdapter::enabled() noexcept
    {
#if defined(CONFIG_NUCODE_BLE_NFC_OOB_ADAPTER)
        return true;
#else
        return false;
#endif
    }

    bool OobNdefAdapter::encode(const SecureConnectionsOobRecord &record, std::uint8_t *buffer,
                                std::size_t capacity, std::size_t &length) noexcept
    {
        length = 0U;
#if !defined(CONFIG_NUCODE_BLE_NFC_OOB_ADAPTER)
        ARG_UNUSED(record);
        ARG_UNUSED(buffer);
        ARG_UNUSED(capacity);
        return false;
#else
        if (buffer == nullptr || capacity < ndef_record_bytes || !validRecord(record))
        {
            return false;
        }
        std::uint8_t frame[OobFrameCodec::frame_bytes] = {};
        std::size_t frame_length = 0U;
        if (!OobFrameCodec::encode(record, frame, sizeof(frame), frame_length))
        {
            return false;
        }

        buffer[0] = ndef_header;
        buffer[1] = static_cast<std::uint8_t>(sizeof(ndef_mime_type) - 1U);
        buffer[2] = static_cast<std::uint8_t>(ndef_payload_bytes);
        ::memcpy(&buffer[3], ndef_mime_type, sizeof(ndef_mime_type) - 1U);
        std::uint8_t *payload = &buffer[3U + sizeof(ndef_mime_type) - 1U];
        std::size_t cursor = 0U;

        std::uint8_t address[7] = {};
        ::memcpy(address, record.pairing_address.value, sizeof(record.pairing_address.value));
        address[6] = record.pairing_address.type;
        const std::uint8_t role = record.role == OobRole::peripheral ? 0U : 1U;
        std::uint8_t manufacturer[2U + OobFrameCodec::frame_bytes] = {};
        sys_put_le16(nucode_company_id, manufacturer);
        ::memcpy(&manufacturer[2], frame, frame_length);
        if (!appendAd(ad_le_address, address, sizeof(address), payload, ndef_payload_bytes,
                      cursor) ||
            !appendAd(ad_le_role, &role, sizeof(role), payload, ndef_payload_bytes, cursor) ||
            !appendAd(ad_sc_confirm, record.confirm, sizeof(record.confirm), payload,
                      ndef_payload_bytes, cursor) ||
            !appendAd(ad_sc_random, record.random, sizeof(record.random), payload,
                      ndef_payload_bytes, cursor) ||
            !appendAd(ad_manufacturer, manufacturer, sizeof(manufacturer), payload,
                      ndef_payload_bytes, cursor) ||
            cursor != ndef_payload_bytes)
        {
            return false;
        }
        length = ndef_record_bytes;
        return true;
#endif
    }

    bool OobNdefAdapter::decode(const std::uint8_t *buffer, std::size_t length,
                                SecureConnectionsOobRecord &record) noexcept
    {
        record = {};
#if !defined(CONFIG_NUCODE_BLE_NFC_OOB_ADAPTER)
        ARG_UNUSED(buffer);
        ARG_UNUSED(length);
        return false;
#else
        if (buffer == nullptr || length != ndef_record_bytes || buffer[0] != ndef_header ||
            buffer[1] != sizeof(ndef_mime_type) - 1U ||
            buffer[2] != ndef_payload_bytes ||
            ::memcmp(&buffer[3], ndef_mime_type, sizeof(ndef_mime_type) - 1U) != 0)
        {
            return false;
        }
        const std::uint8_t *payload = &buffer[3U + sizeof(ndef_mime_type) - 1U];
        std::size_t cursor = 0U;
        bool address_seen = false;
        bool role_seen = false;
        bool confirm_seen = false;
        bool random_seen = false;
        bool manufacturer_seen = false;
        PeerAddress address = {};
        OobRole role = OobRole::peripheral;
        std::uint8_t confirm[16] = {};
        std::uint8_t random[16] = {};
        SecureConnectionsOobRecord candidate = {};

        while (cursor < ndef_payload_bytes)
        {
            const std::uint8_t field_length = payload[cursor++];
            if (field_length == 0U || cursor + field_length > ndef_payload_bytes)
            {
                return false;
            }
            const std::uint8_t type = payload[cursor++];
            const std::uint8_t *value = &payload[cursor];
            const std::size_t value_length = field_length - 1U;
            if (type == ad_le_address && value_length == 7U && !address_seen)
            {
                ::memcpy(address.value, value, sizeof(address.value));
                address.type = value[6];
                address_seen = true;
            }
            else if (type == ad_le_role && value_length == 1U && value[0] <= 1U && !role_seen)
            {
                role = value[0] == 0U ? OobRole::peripheral : OobRole::central;
                role_seen = true;
            }
            else if (type == ad_sc_confirm && value_length == sizeof(confirm) && !confirm_seen)
            {
                ::memcpy(confirm, value, sizeof(confirm));
                confirm_seen = true;
            }
            else if (type == ad_sc_random && value_length == sizeof(random) && !random_seen)
            {
                ::memcpy(random, value, sizeof(random));
                random_seen = true;
            }
            else if (type == ad_manufacturer &&
                     value_length == 2U + OobFrameCodec::frame_bytes && !manufacturer_seen &&
                     sys_get_le16(value) == nucode_company_id &&
                     OobFrameCodec::decode(&value[2], OobFrameCodec::frame_bytes, candidate))
            {
                manufacturer_seen = true;
            }
            else
            {
                return false;
            }
            cursor += value_length;
        }
        if (!address_seen || !role_seen || !confirm_seen || !random_seen ||
            !manufacturer_seen || role != candidate.role ||
            !sameAddress(address, candidate.pairing_address) ||
            ::memcmp(confirm, candidate.confirm, sizeof(confirm)) != 0 ||
            ::memcmp(random, candidate.random, sizeof(random)) != 0)
        {
            return false;
        }
        record = candidate;
        return true;
#endif
    }

    bool SecurityManager::createLocalOob(OobRole role, const std::uint8_t *session_nonce,
                                         std::size_t nonce_length,
                                         SecureConnectionsOobRecord &record) noexcept
    {
        record = {};
        if (!requireThreadContext())
        {
            return false;
        }
        if (atomic_get(&securityState().security_initialized) == 0)
        {
            recordSecurityError(SecurityError::not_initialized, -EACCES);
            return false;
        }
        if (!securityState().security_config.secure_connections_oob || !validRole(role) ||
            !validNonce(session_nonce, nonce_length))
        {
            recordSecurityError(SecurityError::invalid_argument, -EINVAL);
            return false;
        }

        bt_addr_le_t identities[1] = {};
        std::size_t identity_count = ARRAY_SIZE(identities);
        struct bt_le_oob native = {};
        bt_id_get(identities, &identity_count);
        int result = 0;
        if (identity_count == 1U)
        {
            result = bt_le_oob_get_local(BT_ID_DEFAULT, &native);
        }
        if (result != 0 || identity_count != 1U)
        {
            recordSecurityError(SecurityError::driver_error,
                                result != 0 ? result : -ENOENT);
            return false;
        }

        SecureConnectionsOobRecord candidate = {};
        candidate.role = role;
        candidate.identity = publicAddress(&identities[0]);
        candidate.pairing_address = publicAddress(&native.addr);
        ::memcpy(candidate.random, native.le_sc_data.r, sizeof(candidate.random));
        ::memcpy(candidate.confirm, native.le_sc_data.c, sizeof(candidate.confirm));
        ::memcpy(candidate.session_nonce, session_nonce, sizeof(candidate.session_nonce));
        if (!validRecord(candidate))
        {
            recordSecurityError(SecurityError::driver_error, -EBADMSG);
            return false;
        }

        k_spinlock_key_t key = k_spin_lock(&oobState().lock);
        OobSlot &slot = oobState().slots[roleIndex(role)];
        slot = {};
        slot.role = role;
        slot.local = candidate;
        slot.local_valid = true;
        k_spin_unlock(&oobState().lock, key);
        bt_le_oob_set_sc_flag(false);
        record = candidate;
        recordSecurityError(SecurityError::none);
        return true;
    }

    bool SecurityManager::setRemoteOob(OobRole local_role,
                                       const SecureConnectionsOobRecord &record) noexcept
    {
        if (!requireThreadContext())
        {
            return false;
        }
        if (atomic_get(&securityState().security_initialized) == 0)
        {
            recordSecurityError(SecurityError::not_initialized, -EACCES);
            return false;
        }
        if (!securityState().security_config.secure_connections_oob ||
            !validRole(local_role) || !validRecord(record) || record.role == local_role)
        {
            recordSecurityError(SecurityError::invalid_argument, -EINVAL);
            return false;
        }

        bool accepted = false;
        k_spinlock_key_t key = k_spin_lock(&oobState().lock);
        OobSlot &slot = oobState().slots[roleIndex(local_role)];
        if (slot.local_valid &&
            ::memcmp(slot.local.session_nonce, record.session_nonce,
                     sizeof(record.session_nonce)) == 0)
        {
            slot.remote = record;
            slot.remote_valid = true;
            accepted = true;
        }
        k_spin_unlock(&oobState().lock, key);
        if (!accepted)
        {
            recordSecurityError(SecurityError::rejected, -EACCES);
            return false;
        }
        bt_le_oob_set_sc_flag(true);
        recordSecurityError(SecurityError::none);
        return true;
    }

    bool SecurityManager::clearOob(OobRole role) noexcept
    {
        if (!requireThreadContext())
        {
            return false;
        }
        if (!validRole(role))
        {
            recordSecurityError(SecurityError::invalid_argument, -EINVAL);
            return false;
        }
        bool another_ready = false;
        k_spinlock_key_t key = k_spin_lock(&oobState().lock);
        OobSlot &slot = oobState().slots[roleIndex(role)];
        slot = {};
        slot.role = role;
        for (std::size_t index = 0U; index < maximum_security_links; ++index)
        {
            another_ready = another_ready || oobState().slots[index].remote_valid;
        }
        k_spin_unlock(&oobState().lock, key);
        bt_le_oob_set_sc_flag(another_ready);
        recordSecurityError(SecurityError::none);
        return true;
    }

} // namespace nucode::ble
#endif
