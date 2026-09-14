/** @file @brief 실제 Security/profile의 callback·reference·bond 상태를 검증합니다. */
#include <NUCODE_BLE_Security.h>
#include <internal/NUCODE_BLE_Internal.h>
#include <security_mock.h>
#include <zephyr/kernel.h>
#include <zephyr/settings/settings.h>
#include <zephyr/sys/byteorder.h>
#include <array>
#include <cstring>
#include <iostream>
using namespace nucode::ble;

namespace nucode::ble::internal
{
    /** @brief Security 단독 호스트 시험에는 사용자 GATT database가 없습니다. */
    int prepareGattDatabase() noexcept
    {
        return 0;
    }

    /** @brief Security 단독 호스트 시험에는 기록할 GATT database identity가 없습니다. */
    int recordGattDatabaseIdentity() noexcept
    {
        return 0;
    }

    /** @brief Security 단독 호스트 시험에는 사용자 GATT schema가 없습니다. */
    bool hasGattSchema() noexcept
    {
        return false;
    }

    /** @brief Security 단독 호스트 시험에서 GATT poll을 생략합니다. */
    void pollGatt() noexcept
    {
    }

    /** @brief Security 단독 호스트 시험에는 LE CoC main-thread 작업이 없습니다. */
    void pollL2cap() noexcept
    {
    }

    /** @brief Security 단독 호스트 시험에는 LE CoC 종료 작업이 없습니다. */
    void l2capEnded() noexcept
    {
    }

    /** @brief Security 단독 호스트 시험에서 GATT 연결 통지를 소비합니다. */
    void gattConnected(struct bt_conn *, BLEConnectionHandle) noexcept
    {
    }

    /** @brief Security 단독 호스트 시험에서 GATT 해제 통지를 소비합니다. */
    void gattDisconnected(struct bt_conn *, BLEConnectionHandle) noexcept
    {
    }

    /** @brief Security 단독 호스트 시험에서 GATT 종료 통지를 소비합니다. */
    void gattEnded() noexcept
    {
    }

    /** @brief Security 단독 호스트 시험에서 사용자 GATT service를 거부합니다. */
    bool addGattService(BLEService &) noexcept
    {
        return false;
    }
} // namespace nucode::ble::internal

std::array<unsigned, 20> events{};
bool accept_in_callback = false;
PeerAddress last_peer{};
BLEConnectionHandle central_handle{};
BLEConnectionHandle peripheral_handle{};
unsigned central_pairing_events = 0U;
unsigned peripheral_pairing_events = 0U;
void observed(const SecurityEventRecord &event, void *)
{
    ++events[static_cast<unsigned>(event.event)];
    last_peer = event.peer;
    if (event.event == SecurityEvent::pairing_requested ||
        event.event == SecurityEvent::passkey_input_requested)
    {
        if (event.connection == central_handle)
        {
            ++central_pairing_events;
        }
        if (event.connection == peripheral_handle)
        {
            ++peripheral_pairing_events;
        }
    }
    if (accept_in_callback && event.event == SecurityEvent::pairing_requested)
    {
        assert(BLESecurity.acceptPairing(true));
        accept_in_callback = false;
    }
}
void connect(unsigned index = 0)
{
    mock_next_connection = &mock_connections[index];
    assert(
        BLEConnection.connect(BLEAddress("01:02:03:04:05:06", BLEAddress::Type::public_address)));
    mock_conn_callbacks->connected(mock_next_connection, 0);
    assert(mock_next_connection->refs >= 2);
    BLEDevice.poll();
}
void disconnect(unsigned index = 0)
{
    mock_conn_callbacks->disconnected(&mock_connections[index], 0x13);
    assert(mock_connections[index].refs == 0);
}

/** @brief legacy advertising으로 두 번째 peripheral link를 주입합니다. */
void connectPeripheral(unsigned index)
{
    assert(BLEAdvertising.clear());
    assert(BLEAdvertising.start());
    mock_connections[index].role = BT_CONN_ROLE_PERIPHERAL;
    mock_conn_callbacks->connected(&mock_connections[index], 0U);
    BLEDevice.poll();
    assert(mock_connections[index].refs == 2);
}

/** @brief production metadata와 같은 CRC-32를 Host fixture에 계산합니다. */
std::uint32_t metadataCrc(const std::uint8_t *data, std::size_t length)
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

/** @brief current·legacy·future metadata record를 settings mock에 준비합니다. */
void primeBondMetadata(std::uint16_t schema, std::size_t stored_length)
{
    std::uint8_t record[22] = {};
    sys_put_le32(0x32424e4dUL, &record[0]);
    sys_put_le16(schema, &record[4]);
    record[6] = BT_ADDR_LE_PUBLIC;
    std::memcpy(&record[7], mock_peer.a.val, sizeof(mock_peer.a.val));
    record[13] = 16U;
    record[14] = BT_SECURITY_L2;
    record[15] = BT_SECURITY_FLAG_SC;
    if (schema == 1U)
    {
        sys_put_le32(metadataCrc(record, 16U), &record[16]);
    }
    else
    {
        sys_put_le16(1U, &record[16]);
        sys_put_le32(metadataCrc(record, 18U), &record[18]);
    }
    assert(settings_save_one("nucode/security/bond/0", record, stored_length) == 0);
}
int main(int argc, char **argv)
{
    assert(argc == 2);
    const char *scenario = argv[1];
    mock_saved_bond =
        std::strcmp(scenario, "restored_bond") == 0 || std::strcmp(scenario, "erase_failure") == 0;
    if (std::strcmp(scenario, "identity_type_normalization") == 0)
    {
        mock_peer.type = BT_ADDR_LE_RANDOM_ID;
    }
    else if (std::strcmp(scenario, "deferred_rpa_identity") == 0)
    {
        mock_peer.type = BT_ADDR_LE_RANDOM;
        mock_peer.a.val[5] = 0x40U;
    }
    SecurityConfig configuration{};
    configuration.response_timeout_ms = 1000;
    const bool oob_scenario = std::strncmp(scenario, "oob_", 4U) == 0;
    configuration.secure_connections_oob = oob_scenario;
    if (std::strcmp(scenario, "restored_bond") == 0 ||
        std::strcmp(scenario, "erase_failure") == 0)
    {
        primeBondMetadata(2U, 22U);
    }
    else if (std::strcmp(scenario, "bond_legacy_migration") == 0)
    {
        mock_saved_bond = true;
        primeBondMetadata(1U, 20U);
    }
    else if (std::strcmp(scenario, "bond_future_rejected") == 0)
    {
        mock_saved_bond = true;
        primeBondMetadata(3U, 22U);
    }
    else if (std::strcmp(scenario, "bond_truncated_rejected") == 0)
    {
        mock_saved_bond = true;
        primeBondMetadata(2U, 11U);
    }
    assert(BLESecurity.begin(configuration));
    BLESecurity.onEvent(observed, nullptr);
    SecureConnectionsOobRecord local_oob{};
    SecureConnectionsOobRecord remote_oob{};
    std::uint8_t oob_nonce[16] = {};
    if (oob_scenario)
    {
        for (std::size_t index = 0U; index < sizeof(oob_nonce); ++index)
        {
            oob_nonce[index] = static_cast<std::uint8_t>(index + 1U);
            mock_local_sc.r[index] = static_cast<std::uint8_t>(0x10U + index);
            mock_local_sc.c[index] = static_cast<std::uint8_t>(0x30U + index);
        }
        assert(BLESecurity.createLocalOob(OobRole::central, oob_nonce, sizeof(oob_nonce),
                                          local_oob));
        remote_oob.schema = SecureConnectionsOobRecord::current_schema;
        remote_oob.role = OobRole::peripheral;
        remote_oob.identity.type = BT_ADDR_LE_PUBLIC;
        remote_oob.pairing_address.type = mock_peer.type;
        std::memcpy(remote_oob.identity.value, mock_peer.a.val,
                    sizeof(remote_oob.identity.value));
        for (std::size_t index = 0U; index < sizeof(remote_oob.pairing_address.value); ++index)
        {
            remote_oob.pairing_address.value[index] =
                mock_peer.a.val[sizeof(remote_oob.pairing_address.value) - index - 1U];
        }
        std::memcpy(remote_oob.session_nonce, oob_nonce, sizeof(oob_nonce));
        for (std::size_t index = 0U; index < sizeof(remote_oob.random); ++index)
        {
            remote_oob.random[index] = static_cast<std::uint8_t>(0x50U + index);
            remote_oob.confirm[index] = static_cast<std::uint8_t>(0x70U + index);
        }
        if (std::strcmp(scenario, "oob_mismatch") == 0)
        {
            remote_oob.pairing_address.value[0] ^= 0x80U;
        }
        assert(BLESecurity.setRemoteOob(OobRole::central, remote_oob));
        assert(mock_oob_flag);
    }
    assert(BLEDevice.begin("security"));
    connect();
    auto *connection = &mock_connections[0];
    if (std::strcmp(scenario, "bond_legacy_migration") == 0)
    {
        assert(BLESecurity.bondMigrationCount() == 1U);
        assert(BLESecurity.rejectedBondCount() == 0U);
        assert(mock_settings_lengths[0] == 22U);
        assert(BLESecurity.bondState() == BondState::restored_candidate);
    }
    else if (std::strcmp(scenario, "bond_future_rejected") == 0 ||
             std::strcmp(scenario, "bond_truncated_rejected") == 0)
    {
        assert(BLESecurity.bondMigrationCount() == 0U);
        assert(BLESecurity.rejectedBondCount() >= 1U);
        assert(!mock_saved_bond);
        assert(BLESecurity.bondState() == BondState::none);
    }
    else if (std::strcmp(scenario, "oob_codec") == 0)
    {
        std::uint8_t frame[OobFrameCodec::maximum_frame_bytes] = {};
        std::size_t frame_length = 0U;
        SecureConnectionsOobRecord decoded{};
        assert(OobFrameCodec::encode(local_oob, frame, sizeof(frame), frame_length));
        assert(frame_length == OobFrameCodec::frame_bytes);
        assert(OobFrameCodec::decode(frame, frame_length, decoded));
        assert(std::memcmp(&decoded, &local_oob, sizeof(decoded)) == 0);
        frame[22] ^= 0x01U;
        assert(!OobFrameCodec::decode(frame, frame_length, decoded));

        std::uint8_t ndef[OobNdefAdapter::maximum_ndef_bytes] = {};
        std::size_t ndef_length = 0U;
        assert(OobNdefAdapter::enabled());
        assert(OobNdefAdapter::encode(local_oob, ndef, sizeof(ndef), ndef_length));
        assert(ndef_length <= OobNdefAdapter::maximum_ndef_bytes);
        assert(OobNdefAdapter::decode(ndef, ndef_length, decoded));
        assert(std::memcmp(&decoded, &local_oob, sizeof(decoded)) == 0);
        ndef[ndef_length - 1U] ^= 0x01U;
        assert(!OobNdefAdapter::decode(ndef, ndef_length, decoded));
    }
    else if (std::strcmp(scenario, "oob_pairing") == 0 ||
             std::strcmp(scenario, "oob_mismatch") == 0)
    {
        bt_conn_oob_info information{};
        information.type = bt_conn_oob_info::BT_CONN_OOB_LE_SC;
        information.lesc.oob_config =
            decltype(bt_conn_oob_info{}.lesc)::BT_CONN_OOB_BOTH_PEERS;
        mock_auth->oob_data_request(connection, &information);
        if (std::strcmp(scenario, "oob_pairing") == 0)
        {
            assert(mock_cancel_calls == 0U);
            assert(std::memcmp(mock_set_local_sc.r, local_oob.random,
                               sizeof(local_oob.random)) == 0);
            assert(std::memcmp(mock_set_remote_sc.c, remote_oob.confirm,
                               sizeof(remote_oob.confirm)) == 0);
            BLESecurity.poll();
            assert(events[static_cast<unsigned>(SecurityEvent::oob_data_applied)] == 1U);
        }
        else
        {
            assert(mock_cancel_calls == 1U);
            BLESecurity.poll();
            assert(events[static_cast<unsigned>(SecurityEvent::oob_data_rejected)] == 1U);
        }
        assert(BLESecurity.clearOob(OobRole::central));
        assert(!mock_oob_flag);
    }
    else if (std::strcmp(scenario, "pairing_failure") == 0)
    {
        mock_auth->pairing_confirm(connection);
        assert(connection->refs == 3);
        mock_auth_info->pairing_failed(connection, BT_SECURITY_ERR_AUTH_FAIL);
        assert(connection->refs == 2 && !BLESecurity.paired() && !BLESecurity.bonded());
        BLESecurity.poll();
        assert(events[static_cast<unsigned>(SecurityEvent::pairing_failed)] == 1);
        assert(BLESecurity.lastError() == SecurityError::rejected);
    }
    else if (std::strcmp(scenario, "pending_timeout") == 0)
    {
        mock_auth->passkey_entry(connection);
        assert(connection->refs == 3);
        waited_us = 1000000;
        BLESecurity.poll();
        assert(connection->refs == 2 && mock_cancel_calls == 1);
        assert(BLESecurity.lastError() == SecurityError::timeout);
        assert(!BLESecurity.enterPasskey(123456));
    }
    else if (std::strcmp(scenario, "pending_duplicate") == 0)
    {
        mock_auth->passkey_entry(connection);
        mock_auth->pairing_confirm(connection);
        assert(connection->refs == 3 && mock_cancel_calls == 1);
        assert(!BLESecurity.enterPasskey(1000000));
        assert(BLESecurity.enterPasskey(123456) && connection->refs == 2);
    }
    else if (std::strcmp(scenario, "reentrant") == 0)
    {
        accept_in_callback = true;
        mock_auth->pairing_confirm(connection);
        BLESecurity.poll();
        assert(!accept_in_callback && mock_confirm_calls == 1 && connection->refs == 2);
    }
    else if (std::strcmp(scenario, "late_callback") == 0)
    {
        mock_auth->passkey_confirm(connection, 111111);
        disconnect();
        connect(1);
        mock_auth_info->pairing_complete(connection, true);
        mock_auth_info->pairing_failed(connection, BT_SECURITY_ERR_AUTH_FAIL);
        mock_auth->passkey_entry(connection);
        BLESecurity.poll();
        assert(!BLESecurity.paired() && !BLESecurity.bonded());
        assert(connection->refs == 0 && mock_connections[1].refs == 2);
        assert(events[static_cast<unsigned>(SecurityEvent::paired)] == 0);
    }
    else if (std::strcmp(scenario, "not_persisted") == 0)
    {
        connection->security = BT_SECURITY_L2;
        mock_auth_info->pairing_complete(connection, true);
        assert(BLESecurity.paired() && !BLESecurity.bonded());
        assert(BLESecurity.bondState() == BondState::persistence_pending &&
               BLESecurity.bondCount() == 0);
        disconnect();
        connect(1);
        mock_connections[1].security = BT_SECURITY_L2;
        internal::securityChanged(&mock_connections[1], BT_SECURITY_L2, BT_SECURITY_ERR_SUCCESS);
        assert(!BLESecurity.bonded() && BLESecurity.bondState() == BondState::none);
    }
    else if (std::strcmp(scenario, "restored_bond") == 0 ||
             std::strcmp(scenario, "erase_failure") == 0)
    {
        assert(BLESecurity.bondState() == BondState::restored_candidate && !BLESecurity.bonded());
        connection->security = BT_SECURITY_L2;
        internal::securityChanged(connection, BT_SECURITY_L2, BT_SECURITY_ERR_SUCCESS);
        assert(BLESecurity.bonded());
        assert(BLESecurity.requestSecurity() && mock_security_calls == 0);
        BLESecurity.poll();
        assert(events[static_cast<unsigned>(SecurityEvent::security_changed)] == 1);
        PeerAddress peer{};
        assert(BLESecurity.copyBonds(&peer, 1) == 1);
        if (std::strcmp(scenario, "erase_failure") == 0)
        {
            mock_unpair_error = -EIO;
            assert(!BLESecurity.eraseBond(peer) && BLESecurity.bonded());
            assert(!BLESecurity.eraseAllBonds() && BLESecurity.bonded());
            mock_unpair_error = 0;
            assert(BLESecurity.eraseBond(peer));
            assert(!BLESecurity.bonded() &&
                   BLESecurity.bondState() == BondState::removal_requested);
        }
        else
        {
            disconnect();
            connect(1);
            assert(BLESecurity.bondState() == BondState::restored_candidate);
            mock_auth->pairing_accept(&mock_connections[1], nullptr);
            assert(!BLESecurity.bonded() && BLESecurity.bondState() == BondState::none);
        }
    }
    else if (std::strcmp(scenario, "driver_failure") == 0)
    {
        mock_security_error = -EBUSY;
        assert(!BLESecurity.requestSecurity() && connection->refs == 2);
        mock_security_error = 0;
        assert(BLESecurity.requestSecurity());
        mock_auth->pairing_confirm(connection);
        mock_auth_error = -EIO;
        assert(!BLESecurity.acceptPairing(true) && connection->refs == 2);
    }
    else if (std::strcmp(scenario, "identity_type_normalization") == 0)
    {
        connection->security = BT_SECURITY_L2;
        internal::securityChanged(connection, BT_SECURITY_L2, BT_SECURITY_ERR_SUCCESS);
        BLESecurity.poll();
        assert(events[static_cast<unsigned>(SecurityEvent::security_changed)] == 1);
        assert(last_peer.type == BT_ADDR_LE_RANDOM);
        assert(std::memcmp(last_peer.value, mock_peer.a.val, sizeof(last_peer.value)) == 0);
    }
    else if (std::strcmp(scenario, "deferred_rpa_identity") == 0)
    {
        connection->security = BT_SECURITY_L2;
        internal::securityChanged(connection, BT_SECURITY_L2, BT_SECURITY_ERR_SUCCESS);
        BLESecurity.poll();
        assert(events[static_cast<unsigned>(SecurityEvent::security_changed)] == 0);
        mock_peer.type = BT_ADDR_LE_RANDOM_ID;
        mock_peer.a.val[0] = 0x6bU;
        mock_peer.a.val[5] = 0xe4U;
        BLESecurity.poll();
        assert(events[static_cast<unsigned>(SecurityEvent::security_changed)] == 1);
        assert(last_peer.type == BT_ADDR_LE_RANDOM);
        assert(last_peer.value[0] == 0x6bU && last_peer.value[5] == 0xe4U);
    }
    else if (std::strcmp(scenario, "queue_overflow") == 0)
    {
        for (unsigned i = 0; i < 40; ++i)
        {
            mock_auth->passkey_display(connection, i);
        }
        assert(BLESecurity.lastError() == SecurityError::busy &&
               BLESecurity.lastDriverError() == -ENOBUFS);
        BLESecurity.poll();
        assert(events[static_cast<unsigned>(SecurityEvent::passkey_display)] == 24);
    }
    else if (std::strcmp(scenario, "dual_pending_isolation") == 0)
    {
        connectPeripheral(1);
        central_handle = BLEConnection.handle(BLELinkRole::central);
        peripheral_handle = BLEConnection.handle(BLELinkRole::peripheral);
        assert(central_handle.valid() && peripheral_handle.valid() &&
               central_handle != peripheral_handle);
        mock_auth->passkey_entry(connection);
        mock_auth->pairing_confirm(&mock_connections[1]);
        assert(connection->refs == 3 && mock_connections[1].refs == 3);
        BLESecurity.poll();
        assert(central_pairing_events == 1U && peripheral_pairing_events == 1U);
        assert(BLESecurity.acceptPairing(peripheral_handle, true));
        assert(mock_connections[1].refs == 2 && connection->refs == 3);
        assert(BLESecurity.enterPasskey(central_handle, 123456U));
        assert(connection->refs == 2);
        connection->security = BT_SECURITY_L2;
        mock_connections[1].security = BT_SECURITY_L3;
        mock_auth_info->pairing_complete(connection, true);
        mock_auth_info->pairing_complete(&mock_connections[1], true);
        assert(BLESecurity.paired(central_handle));
        assert(BLESecurity.paired(peripheral_handle));
        assert(BLESecurity.currentLevel(central_handle) == SecurityLevel::encrypted);
        assert(BLESecurity.currentLevel(peripheral_handle) == SecurityLevel::authenticated);
        internal::securityChanged(connection, central_handle, BT_SECURITY_L2,
                                  BT_SECURITY_ERR_AUTH_FAIL);
        assert(!BLESecurity.paired(central_handle));
        assert(BLESecurity.paired(peripheral_handle));
        const BLEConnectionHandle stale = central_handle;
        disconnect(0);
        assert(!BLESecurity.paired(stale));
        assert(BLESecurity.currentLevel(stale) == SecurityLevel::none);
        assert(!BLESecurity.requestSecurity(stale));
        assert(BLESecurity.paired(peripheral_handle));
    }
    else if (std::strcmp(scenario, "dual_timeout_isolation") == 0)
    {
        connectPeripheral(1);
        central_handle = BLEConnection.handle(BLELinkRole::central);
        peripheral_handle = BLEConnection.handle(BLELinkRole::peripheral);
        mock_auth->passkey_entry(connection);
        waited_us = 500000;
        mock_auth->pairing_confirm(&mock_connections[1]);
        waited_us = 1000000;
        BLESecurity.poll();
        assert(mock_cancel_calls == 1U && connection->refs == 2);
        assert(mock_connections[1].refs == 3);
        assert(!BLESecurity.enterPasskey(central_handle, 123456U));
        assert(BLESecurity.acceptPairing(peripheral_handle, true));
        assert(mock_connections[1].refs == 2);
    }
    else if (std::strcmp(scenario, "sparse_pending_duplicate") == 0)
    {
        connectPeripheral(1);
        central_handle = BLEConnection.handle(BLELinkRole::central);
        peripheral_handle = BLEConnection.handle(BLELinkRole::peripheral);
        mock_auth->passkey_entry(connection);
        mock_auth->pairing_confirm(&mock_connections[1]);
        assert(BLESecurity.enterPasskey(central_handle, 123456U));
        assert(connection->refs == 2 && mock_connections[1].refs == 3);
        mock_auth->pairing_confirm(&mock_connections[1]);
        assert(mock_cancel_calls == 1U && mock_connections[1].refs == 3);
        assert(BLESecurity.acceptPairing(peripheral_handle, true));
        assert(mock_connections[1].refs == 2);
    }
    else if (std::strcmp(scenario, "profiles") == 0)
    {
        assert(BLEBattery.setLevel(42) && BLEBattery.level() == 42);
        assert(!BLEBattery.setLevel(101));
        mock_battery_error = -EIO;
        assert(!BLEBattery.setLevel(50) && BLEBattery.level() == 42);
        DeviceInformation information{};
        information.manufacturer = "maker";
        information.model = "model";
        mock_dis_fail_at = 2;
        assert(!BLEDeviceInformation.configure(information));
        mock_dis_fail_at = 0;
        assert(BLEDeviceInformation.configure(information));
        assert(mock_dis_values["bt/dis/model"] == std::string("model\0", 6));
    }
    else if (std::strcmp(scenario, "hid") == 0)
    {
        assert(BLEKeyboard.begin() && connection->refs == 3);
        assert(mock_hids_parameters.is_kb && mock_hids_parameters.info.bcd_hid == 0x0111);
        assert(mock_hids_parameters.info.flags ==
               (BT_HIDS_REMOTE_WAKE | BT_HIDS_NORMALLY_CONNECTABLE));
        assert(mock_hids_parameters.inp_rep_group_init.cnt == 1);
        assert(mock_hids_parameters.inp_rep_group_init.reports[0].id == 1);
        assert(mock_hids_parameters.inp_rep_group_init.reports[0].size == 8);
        assert(mock_hids_parameters.rep_map.size == 47 &&
               mock_hids_parameters.rep_map.data[0] == 0x05);
        assert(!BLEKeyboard.press(4));
        connection->security = BT_SECURITY_L2;
        assert(BLEKeyboard.press(4, 2) && !mock_hids_boot);
        assert(mock_hids_data[0] == 2 && mock_hids_data[2] == 4);
        mock_hids_parameters.pm_evt_handler(BT_HIDS_PM_EVT_BOOT_MODE_ENTERED, connection);
        assert(BLEKeyboard.releaseAll() && mock_hids_boot && mock_hids_data[2] == 0);
        assert(!BLEKeyboard.press(0x66));
        mock_hids_send_error = -EACCES;
        assert(!BLEKeyboard.press(4) && BLEKeyboard.lastError() == SecurityError::not_subscribed);
        mock_hids_detach_error = -EIO;
        disconnect();
        assert(!BLEKeyboard.connected());
        mock_hids_detach_error = 0;
        connect(1);
        mock_connections[1].security = BT_SECURITY_L2;
        mock_hids_send_error = 0;
        assert(BLEKeyboard.press(5) && !mock_hids_boot);
    }
    else
    {
        assert(false);
    }
    BLEDevice.end();
    for (const auto &c : mock_connections)
    {
        assert(c.refs == 0);
    }
    std::cout << "R12_SECURITY_PASS=" << scenario << '\n';
}
