/**
 * @file main.cpp
 * @brief 세 NU54DK에서 두 link의 GATT·LE CoC 동시 traffic을 검증합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <Arduino.h>
#include <NUCODE_BLE.h>

#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/hci_types.h>
#include <zephyr/kernel.h>

#include "M29MultiPayload.h"

#include <cstddef>
#include <cstdint>
#include <string.h>

#ifndef M29_MULTI_CORE_REVISION
#error "M29_MULTI_CORE_REVISION is required"
#endif

static_assert(CONFIG_BT_MAX_CONN == 2);
static_assert(CONFIG_BT_CTLR_SDC_PERIPHERAL_COUNT == 1);
static_assert(CONFIG_BT_L2CAP_DYNAMIC_CHANNEL == 1);
static_assert(nucode::ble::L2capCoc::maximum_channels == 2U);
static_assert(nucode::ble::L2capCoc::transmit_buffers == 4U);

namespace
{

    using MultiPayload = nucode::test::m29::MultiPayload;

    constexpr char protocol[] = "M29W07D|1";
    constexpr char ready_query[] = "M29W07D|1|READY?";
    constexpr char start_prefix[] = "M29W07D|1|START|test=M29-MULTI-01|nonce=";
    constexpr char core_suffix[] = "|core=" M29_MULTI_CORE_REVISION;
    constexpr char service_text[] = "90bf2a40-14f5-4d3d-92c7-299334932a20";
    constexpr char characteristic_text[] = "90bf2a41-14f5-4d3d-92c7-299334932a20";
    constexpr std::uint16_t company_id = 0x29a7U;
    constexpr std::uint16_t coc_psm = 0x0081U;
    constexpr std::uint32_t required_operations = 1000U;
    constexpr std::int64_t session_timeout_ms = 900000;
    constexpr std::uint8_t peripheral_marker = 0xa1U;
    constexpr std::uint8_t mixed_marker = 0xb2U;

    const nucode::ble::BLEUuid service_uuid(service_text);
    const nucode::ble::BLEUuid characteristic_uuid(characteristic_text);
    nucode::ble::BLEService test_service(service_uuid);
    nucode::ble::BLECharacteristic test_characteristic(
        characteristic_uuid, nucode::ble::BLEProperty::write,
        nucode::ble::BLEPermission::write, MultiPayload::payload_length);

    char command[160] = {};
    std::size_t command_length = 0U;
    char nonce[MultiPayload::nonce_text_length + 1U] = {};
    std::uint8_t nonce_binary[MultiPayload::nonce_binary_length] = {};
    std::uint8_t gatt_payload[MultiPayload::payload_length] = {};
    std::uint8_t coc_payload[MultiPayload::payload_length] = {};
    bool session_started = false;
    bool session_finished = false;
    bool callback_context_valid = true;
    bool peer_found = false;
    bool scan_started = false;
    bool client_discovered = false;
    bool client_channel_connected = false;
    bool server_channel_connected = false;
    [[maybe_unused]] bool mixed_advertising_started = false;
    bool link_reported = false;
    bool traffic_started = false;
    bool gatt_inflight = false;
    bool coc_waiting_for_echo = false;
    bool server_echo_pending = false;
    std::int64_t session_deadline = 0;
    std::uint32_t progress_reported = 0U;
    std::uint32_t client_gatt_completed = 0U;
    std::uint32_t client_coc_sent = 0U;
    std::uint32_t client_coc_received = 0U;
    std::uint32_t server_gatt_received = 0U;
    std::uint32_t server_coc_received = 0U;
    std::uint32_t server_coc_sent = 0U;
    std::uint32_t cross_link_events = 0U;
    std::uint32_t payload_errors = 0U;
    nucode::ble::BLEAddress peer_address;
    nucode::ble::BLEConnectionHandle client_connection;
    nucode::ble::BLEConnectionHandle server_connection;
    nucode::ble::BLEL2capChannelHandle client_channel;
    nucode::ble::BLEL2capChannelHandle server_channel;
    struct k_thread *setup_thread = nullptr;

#include "M29MultiProtocol.inc"
#include "M29MultiRadio.inc"
#include "M29MultiTraffic.inc"
#include "M29MultiEvents.inc"
#include "M29MultiCommand.inc"

} // namespace

void setup()
{
    setup_thread = k_current_get();
    Serial.begin(115200);
    const std::int64_t deadline = k_uptime_get() + 5000;
    while (!Serial && k_uptime_get() < deadline)
    {
        delay(10);
    }
    if (hasServer())
    {
        test_characteristic.onEvent(onCharacteristicEvent);
        if (!test_service.addCharacteristic(test_characteristic) ||
            !BLEDevice.addService(test_service))
        {
            fail("schema");
            return;
        }
    }
    BLEDevice.onEventInfo(onBleEvent);
    BLEL2cap.onEvent(onL2capEvent);
    if (hasClient())
    {
        BLEScan.onResult(onScanResult);
        BLEClient.onDetailedEvent(onClientEvent);
    }
    if (!BLEDevice.begin(roleName()))
    {
        fail("device_begin", BLEDevice.lastDriverError());
        return;
    }
    printReady();
}

void loop()
{
    pollHostCommand();
    BLEDevice.poll();
    if (!session_started || session_finished)
    {
        delay(1);
        return;
    }
    if (peer_found && scan_started)
    {
        peer_found = false;
        scan_started = false;
        if (!BLEScan.stop() || !BLEConnection.connect(peer_address, client_connection))
        {
            fail("connect_start", BLEDevice.lastDriverError());
        }
    }
    issueClientTraffic();
    printProgress();
    finishIfComplete();
    if (!session_finished && k_uptime_get() >= session_deadline)
    {
        fail("timeout");
    }
    delay(1);
}
