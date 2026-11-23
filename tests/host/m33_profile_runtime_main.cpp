/** @file @brief 실제 GATT backend 위 표준 서비스의 link 격리·권한을 시험합니다.
 * SPDX-License-Identifier: MIT
 */
#define main baseline_gatt_fixture_main
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wreturn-type"
#include "r12_ble_gatt_main.cpp"
#pragma GCC diagnostic pop
#undef main
#include <NUCODE_BLE_Profiles.h>
#include <NUCODE_BLE_Security.h>
#include <NUCODE_BLE_ObjectStore.h>
using namespace nucode::ble::profiles;

static SecurityLevel test_security = SecurityLevel::none;
static bool test_bonded = false;
static unsigned deletion_requests = 0U;
namespace nucode::ble
{
    SecurityLevel SecurityManager::currentLevel(BLEConnectionHandle) const noexcept
    {
        return test_security;
    }
    bool SecurityManager::paired(BLEConnectionHandle) const noexcept
    {
        return test_bonded;
    }
    bool SecurityManager::bonded(BLEConnectionHandle) const noexcept
    {
        return test_bonded;
    }
    BondState SecurityManager::bondState(BLEConnectionHandle) const noexcept
    {
        return test_bonded ? BondState::persistence_pending : BondState::none;
    }
    bool SecurityManager::eraseBond(const PeerAddress &) noexcept
    {
        ++deletion_requests;
        return true;
    }
} // namespace nucode::ble
nucode::ble::SecurityManager BLESecurity;

/** @brief 등록된 attribute를 UUID로 찾아 실제 ATT callback을 호출합니다. */
const bt_gatt_attr *attributeFor(std::uint16_t uuid)
{
    for (auto *registered : mock_services)
    {
        if (registered == nullptr)
        {
            continue;
        }
        for (std::size_t index = 0U; index < registered->attr_count; ++index)
        {
            const auto &attribute = registered->attrs[index];
            if (attribute.uuid != nullptr && attribute.uuid->type == BT_UUID_TYPE_16 &&
                reinterpret_cast<const bt_uuid_16 *>(attribute.uuid)->val == uuid)
            {
                return &attribute;
            }
        }
    }
    return nullptr;
}
bool deletionAllowed(const BondDeleteRequest &request, void *)
{
    return request.length == 1U && request.authorization_code[0] == 0xa5U;
}
int main(int argc, char **argv)
{
    assert(argc == 2);
    if (std::strcmp(argv[1], "object_store") == 0)
    {
        ObjectStore store;
        const std::uint8_t data[] = {1U, 2U, 3U, 4U};
        std::uint8_t output[4] = {};
        assert(store.create(0x100U, "read-only", 4U, data, 4U, false, false) != nullptr);
        assert(!store.erase(0x100U) && !store.write(0x100U, 0U, data, 4U));
        assert(store.create(0x200U, "write", 8U, data, 4U, true, true) != nullptr);
        assert(!store.write(0x200U, 7U, data, 2U));
        assert(!store.write(0x200U, static_cast<std::size_t>(-1), data, 2U));
        assert(!store.read(0x200U, 3U, output, 2U));
        assert(store.write(0x200U, 4U, data, 4U));
        assert(store.read(0x200U, 4U, output, 4U));
        assert(std::memcmp(output, data, 4U) == 0);
        assert(store.find(0x104U) == nullptr);
        assert(store.erase(0x200U));
        assert(!store.read(0x200U, 0U, output, 1U));
        assert(store.create(0x201U, "reused", 8U, data, 4U, true, true) != nullptr);
        assert(store.find(0x200U) == nullptr && store.count() == 2U);
        assert(store.create(0x201U, "duplicate", 8U, data, 4U, true, true) == nullptr);
        assert(store.create(0x202U, "third", 8U, data, 4U, true, true) != nullptr);
        assert(store.create(0x203U, "fourth", 8U, data, 4U, true, true) != nullptr);
        assert(store.create(0x204U, "full", 8U, data, 4U, true, true) == nullptr);
        return 0;
    }
    if (std::strcmp(argv[1], "alerts") == 0)
    {
        static AlertService alerts;
        assert(alerts.begin() && BLEDevice.begin("alerts"));
        connect();
        const auto first = BLEConnection.handle(BLELinkRole::central);
        assert(BLEAdvertising.clear() && BLEAdvertising.start());
        mock_conn_callbacks->connected(&mock_connections[1], 0U);
        BLEDevice.poll();
        const auto second = BLEConnection.handle(BLELinkRole::peripheral);
        assert(second.valid() && second != first);
        const auto *control = attributeFor(0x2a44U);
        assert(control != nullptr);
        const std::uint8_t enable_email[] = {0U, 1U};
        const std::uint8_t invalid_category[] = {0U, 10U};
        assert(control->write(&mock_connections[0], control, invalid_category, 2U, 0U, 0U) < 0);
        assert(control->write(&mock_connections[0], control, enable_email, 1U, 0U, 0U) < 0);
        assert(control->write(&mock_connections[0], control, enable_email, 2U, 1U, 0U) < 0);
        assert(control->write(&mock_connections[0], control, enable_email, 2U, 0U, 0U) == 2);
        BLEDevice.poll();
        const Alert value{1U, 2U, "email"};
        assert(!alerts.send(second, value));
        assert(alerts.send(first, value));
        assert(mock_notification_connection == &mock_connections[0]);
        mock_notification.func(&mock_connections[0], mock_notification.user_data);
        BLEDevice.poll();
        mock_conn_callbacks->disconnected(&mock_connections[0], 0x13U);
        BLEDevice.poll();
        alerts.poll();
        assert(!alerts.send(first, value) && !alerts.send(second, value));
        return 0;
    }
    if (std::strcmp(argv[1], "bonds") == 0)
    {
        static BondManagementService management;
        assert(!management.begin(nullptr));
        assert(management.begin(deletionAllowed) && BLEDevice.begin("bonds"));
        connect();
        const auto *control = attributeFor(0x2aa4U);
        assert(control != nullptr);
        const std::uint8_t command[] = {3U, 0xa5U};
        const std::uint8_t all_bonds[] = {6U, 0xa5U};
        const std::uint8_t wrong_code[] = {3U, 0xa4U};
        assert(control->write(&mock_connections[0], control, command, 2U, 0U, 0U) < 0);
        test_security = SecurityLevel::encrypted;
        assert(control->write(&mock_connections[0], control, command, 2U, 0U, 0U) < 0);
        test_bonded = true;
        assert(!management.armed());
        assert(control->write(&mock_connections[0], control, command, 2U, 0U, 0U) < 0);
        management.setArmed(true);
        assert(control->write(&mock_connections[0], control, all_bonds, 2U, 0U, 0U) < 0);
        assert(control->write(&mock_connections[0], control, wrong_code, 2U, 0U, 0U) < 0);
        assert(control->write(&mock_connections[0], control, command, 2U, 1U, 0U) < 0);
        assert(control->write(&mock_connections[0], control, command, 2U, 0U, 0U) == 2);
        assert(!management.armed());
        assert(control->write(&mock_connections[0], control, command, 2U, 0U, 0U) < 0);
        BLEDevice.poll();
        assert(deletion_requests == 1U && management.acceptedCount() == 1U);
        return 0;
    }
    const Kind kind = std::strcmp(argv[1], "cts") == 0    ? Kind::current_time
                      : std::strcmp(argv[1], "csc") == 0  ? Kind::cycling
                      : std::strcmp(argv[1], "rscs") == 0 ? Kind::running
                      : std::strcmp(argv[1], "ets") == 0  ? Kind::elapsed_time
                                                          : Kind::thermometer;
    static SensorService sensor(kind);
    assert(sensor.begin() && !sensor.begin());
    assert(BLEDevice.begin("sensor"));
    connect();
    Packet packet;
    if (kind == Kind::cycling)
    {
        CyclingMeasurement value;
        assert(Codec::encode(value, packet));
        assert(!sensor.setValue(packet));
        value.has_wheel = false;
        assert(Codec::encode(value, packet));
    }
    else if (kind == Kind::running)
    {
        RunningMeasurement value;
        value.has_distance = true;
        assert(Codec::encode(value, packet));
        assert(!sensor.setValue(packet));
        value.has_distance = false;
        assert(Codec::encode(value, packet));
    }
    else if (kind == Kind::current_time)
    {
        assert(Codec::encode(CurrentTime{}, packet));
    }
    else if (kind == Kind::elapsed_time)
    {
        assert(Codec::encode(ElapsedTime{}, packet));
    }
    else
    {
        assert(Codec::encode(Temperature{}, packet));
    }
    assert(sensor.setValue(packet));
    const auto peer = BLEConnection.handle(BLELinkRole::central);
    assert(sensor.send(peer));
    if (Codec::usesIndications(kind))
    {
        assert(mock_indication_connection == &mock_connections[0]);
        mock_indication->func(&mock_connections[0], mock_indication, 0U);
        mock_indication->destroy(mock_indication);
    }
    else
    {
        assert(mock_notification_connection == &mock_connections[0]);
        mock_notification.func(&mock_connections[0], mock_notification.user_data);
    }
    BLEDevice.poll();
    mock_conn_callbacks->disconnected(&mock_connections[0], 0x13U);
    BLEDevice.poll();
    assert(!sensor.send(peer));
    return 0;
}
