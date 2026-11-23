#include <cassert>
#include <cerrno>
#include <cstddef>

#include "../../libraries/NUCODE_BLE_Companion/src/NUCODE_BLE_Companion.cpp"

using namespace nucode::ble;
using namespace nucode::ble::companion;

namespace
{
    struct CapturedEvent
    {
        Event event;
        Error error;
        int native_code;
    };

    CapturedEvent events[4]{};
    std::size_t event_count;

    /** @brief 공개 callback으로 전달된 보안·연결 종료 순서를 저장합니다. */
    void capture(const EventInfo &event, void *)
    {
        assert(event_count < 4U);
        events[event_count++] = {event.event, event.error, event.native_code};
    }

    /** @brief 현재 session을 disconnect callback까지 진행해 전역 owner를 정리합니다. */
    void finishSession(AppleClient &client, bt_conn &connection, std::uint8_t reason)
    {
        const std::size_t previous_count = event_count;
        nucode::ble::companion::companion_callbacks.disconnected(&connection, reason);
        client.poll();
        assert(event_count == previous_count + 1U);
        assert(events[event_count - 1U].event == Event::disconnected);
    }
} // namespace

int main()
{
    BLEDevice.initialized_value = true;
    assert(AppleClient::advertise(Service::notifications, "Already Initialized") == Error::none);
    assert(BLEDevice.begin_calls == 0U);
    assert(internal::gap::companion_stub_advertising_starts == 1U);
    assert(BLEAdvertising.running());
    AppleClient::stopAdvertising();
    assert(internal::gap::companion_stub_advertising_stops == 1U);
    assert(!BLEAdvertising.running());
    BLEDevice.initialized_value = false;
    assert(AppleClient::advertise(Service::media, "Initialize Once") == Error::none);
    assert(BLEDevice.begin_calls == 1U);
    assert(internal::gap::companion_stub_advertising_starts == 2U);
    AppleClient::stopAdvertising();
    assert(internal::gap::companion_stub_advertising_stops == 2U);

    bt_conn connection{};
    companion_stub_connection = &connection;
    BLEConnectionHandle handle{1};

    AppleClient immediate;
    immediate.onEvent(capture);
    companion_stub_security_result = -EACCES;
    assert(immediate.begin(handle, Service::notifications) == Error::security);
    immediate.poll();
    assert(event_count == 1U);
    assert(events[0].event == Event::error);
    assert(events[0].error == Error::security);
    assert(events[0].native_code == -EACCES);
    finishSession(immediate, connection, BT_HCI_ERR_REMOTE_USER_TERM_CONN);

    event_count = 0U;
    companion_stub_security_result = 0;
    companion_stub_security_level = BT_SECURITY_L1;
    AppleClient asynchronous;
    asynchronous.onEvent(capture);
    assert(asynchronous.begin(handle, Service::media) == Error::none);
    nucode::ble::companion::companion_callbacks.security_changed(&connection, BT_SECURITY_L1,
                                                                 BT_SECURITY_ERR_PAIR_NOT_ALLOWED);
    nucode::ble::companion::companion_callbacks.disconnected(&connection,
                                                             BT_HCI_ERR_REMOTE_USER_TERM_CONN);
    asynchronous.poll();
    assert(event_count == 1U);
    assert(events[0].event == Event::error);
    assert(events[0].error == Error::security);
    assert(events[0].native_code == BT_SECURITY_ERR_PAIR_NOT_ALLOWED);
    asynchronous.poll();
    assert(event_count == 2U);
    assert(events[1].event == Event::disconnected);
    return 0;
}
