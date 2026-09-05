/** @file @brief 실제 Security/profile의 callback·reference·bond 상태를 검증합니다. */
#include <NUCODE_BLE_Security.h>
#include <internal/NUCODE_BLE_Internal.h>
#include <security_mock.h>
#include <zephyr/kernel.h>
#include <array>
#include <cstring>
#include <iostream>
using namespace nucode::ble;
std::array<unsigned, 16> events{};
bool accept_in_callback = false;
void observed(const SecurityEventRecord &event, void *)
{
    ++events[static_cast<unsigned>(event.event)];
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
int main(int argc, char **argv)
{
    assert(argc == 2);
    const char *scenario = argv[1];
    mock_saved_bond =
        std::strcmp(scenario, "restored_bond") == 0 || std::strcmp(scenario, "erase_failure") == 0;
    SecurityConfig configuration{};
    configuration.response_timeout_ms = 1000;
    assert(BLESecurity.begin(configuration));
    BLESecurity.onEvent(observed, nullptr);
    assert(BLEDevice.begin("security"));
    connect();
    auto *connection = &mock_connections[0];
    if (std::strcmp(scenario, "pairing_failure") == 0)
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
