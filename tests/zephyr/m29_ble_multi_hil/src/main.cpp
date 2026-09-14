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

    /** @brief 현재 image의 고정 role 이름을 반환합니다. */
    const char *roleName()
    {
#if defined(NUCODE_M29_MULTI_PERIPHERAL)
        return "peripheral";
#elif defined(NUCODE_M29_MULTI_MIXED)
        return "mixed";
#else
        return "central";
#endif
    }

    /** @brief 현재 role이 GATT·CoC client traffic을 생성하는지 반환합니다. */
    constexpr bool hasClient()
    {
#if defined(NUCODE_M29_MULTI_PERIPHERAL)
        return false;
#else
        return true;
#endif
    }

    /** @brief 현재 role이 GATT·CoC server traffic을 수신하는지 반환합니다. */
    constexpr bool hasServer()
    {
#if defined(NUCODE_M29_MULTI_CENTRAL)
        return false;
#else
        return true;
#endif
    }

    /** @brief 현재 server link의 RF marker를 반환합니다. */
    constexpr std::uint8_t serverMarker()
    {
#if defined(NUCODE_M29_MULTI_PERIPHERAL)
        return peripheral_marker;
#else
        return mixed_marker;
#endif
    }

    /** @brief 현재 client가 찾아야 할 peer의 RF marker를 반환합니다. */
    constexpr std::uint8_t peerMarker()
    {
#if defined(NUCODE_M29_MULTI_MIXED)
        return peripheral_marker;
#else
        return mixed_marker;
#endif
    }

    /** @brief 모든 session record에 nonce와 exact Core revision을 붙입니다. */
    void printSuffix()
    {
        Serial.print("|nonce=");
        Serial.print(nonce);
        Serial.print("|core=");
        Serial.print(M29_MULTI_CORE_REVISION);
    }

    /** @brief 첫 실패를 고정 protocol로 출력하고 추가 target 동작을 중단합니다. */
    void fail(const char *stage, int code = 0)
    {
        if (session_finished)
        {
            return;
        }
        Serial.print(protocol);
        Serial.print("|FAIL|role=");
        Serial.print(roleName());
        Serial.print("|stage=");
        Serial.print(stage == nullptr ? "unknown" : stage);
        Serial.print("|code=");
        Serial.print(code);
        printSuffix();
        Serial.println();
        session_finished = true;
    }

    /** @brief 공개 callback이 Arduino main thread에서 실행됐는지 확인합니다. */
    void checkCallbackContext()
    {
        if (k_current_get() != setup_thread)
        {
            callback_context_valid = false;
            fail("callback_context");
        }
    }

    /** @brief READY record를 full Core revision과 함께 출력합니다. */
    void printReady()
    {
        Serial.print(protocol);
        Serial.print("|READY|role=");
        Serial.print(roleName());
        Serial.print("|core=");
        Serial.println(M29_MULTI_CORE_REVISION);
    }

    /** @brief BEGIN record를 session identity와 함께 출력합니다. */
    void printBegin()
    {
        Serial.print(protocol);
        Serial.print("|BEGIN|role=");
        Serial.print(roleName());
        Serial.print("|test=M29-MULTI-01");
        printSuffix();
        Serial.println();
    }

    /** @brief 128-bit lowercase nonce와 exact revision START만 허용합니다. */
    bool acceptStartCommand()
    {
        const std::size_t prefix_length = ::strlen(start_prefix);
        if (::strncmp(command, start_prefix, prefix_length) != 0)
        {
            return false;
        }
        const char *nonce_start = command + prefix_length;
        char nonce_candidate[MultiPayload::nonce_text_length + 1U] = {};
        ::memcpy(nonce_candidate, nonce_start, MultiPayload::nonce_text_length);
        if (::strcmp(nonce_start + MultiPayload::nonce_text_length, core_suffix) != 0 ||
            !MultiPayload::decodeNonce(nonce_candidate, nonce_binary))
        {
            return false;
        }
        ::memcpy(nonce, nonce_candidate, sizeof(nonce));
        return true;
    }

    /** @brief advertising payload 안의 company ID·role·128-bit nonce를 확인합니다. */
    bool validRfPeer(const nucode::ble::BLEScanResult &result)
    {
        std::size_t cursor = 0U;
        while (cursor < result.payload_length)
        {
            const std::uint8_t field_length = result.payload[cursor];
            if (field_length == 0U || cursor + field_length >= result.payload_length)
            {
                return false;
            }
            const std::uint8_t type = result.payload[cursor + 1U];
            if (type == BT_DATA_MANUFACTURER_DATA &&
                field_length == MultiPayload::nonce_binary_length + 4U)
            {
                const std::uint8_t *value = &result.payload[cursor + 2U];
                return value[0] == static_cast<std::uint8_t>(company_id & 0xffU) &&
                       value[1] == static_cast<std::uint8_t>(company_id >> 8U) &&
                       value[2] == peerMarker() &&
                       ::memcmp(value + 3U, nonce_binary,
                                MultiPayload::nonce_binary_length) == 0;
            }
            cursor += field_length + 1U;
        }
        return false;
    }

    /** @brief role marker와 full nonce를 포함한 connectable advertising을 시작합니다. */
    [[maybe_unused]] bool startAdvertising()
    {
        std::uint8_t manufacturer[MultiPayload::nonce_binary_length + 1U] = {};
        manufacturer[0] = serverMarker();
        ::memcpy(manufacturer + 1U, nonce_binary, MultiPayload::nonce_binary_length);
        if (!BLEAdvertising.clear() || !BLEAdvertising.setConnectable(true) ||
            !BLEAdvertising.setManufacturerData(company_id, manufacturer,
                                                  sizeof(manufacturer)) ||
            !BLEAdvertising.setScanResponseName(true) || !BLEAdvertising.start())
        {
            return false;
        }
        Serial.print(protocol);
        Serial.print("|ADVERTISE|role=");
        Serial.print(roleName());
        Serial.print("|marker=");
        Serial.print(serverMarker());
        Serial.print("|psm=129|status=pass");
        printSuffix();
        Serial.println();
        return true;
    }

    /** @brief company ID·role·exact nonce로 peer를 고르는 active scan을 시작합니다. */
    [[maybe_unused]] bool startScan()
    {
        if (!BLEScan.clearFilters() || !BLEScan.start(true))
        {
            return false;
        }
        scan_started = true;
        Serial.print(protocol);
        Serial.print("|SCAN|role=");
        Serial.print(roleName());
        Serial.print("|status=pass");
        printSuffix();
        Serial.println();
        return true;
    }

    /** @brief 두 link가 모두 준비된 뒤 role별 고정 연결 수를 출력합니다. */
    void printLinkIfReady()
    {
        if (link_reported)
        {
            return;
        }
#if defined(NUCODE_M29_MULTI_MIXED)
        if (!client_discovered || !client_channel_connected ||
            !server_connection.valid() || !server_channel_connected)
        {
            return;
        }
        const unsigned int links = 2U;
#elif defined(NUCODE_M29_MULTI_PERIPHERAL)
        if (!server_connection.valid() || !server_channel_connected)
        {
            return;
        }
        const unsigned int links = 1U;
#else
        if (!client_discovered || !client_channel_connected)
        {
            return;
        }
        const unsigned int links = 1U;
#endif
        link_reported = true;
        Serial.print(protocol);
        Serial.print("|LINK|role=");
        Serial.print(roleName());
        Serial.print("|connections=");
        Serial.print(links);
        Serial.print("|gatt=ready|coc=ready");
        printSuffix();
        Serial.println();
    }

    /** @brief mixed의 upstream 준비 뒤에만 downstream advertising을 시작합니다. */
    void startMixedAdvertisingIfReady()
    {
#if defined(NUCODE_M29_MULTI_MIXED)
        if (mixed_advertising_started || !client_discovered || !client_channel_connected)
        {
            return;
        }
        Serial.print(protocol);
        Serial.print("|UPSTREAM|role=mixed|gatt=ready|coc=ready");
        printSuffix();
        Serial.println();
        mixed_advertising_started = true;
        if (!startAdvertising())
        {
            fail("mixed_advertising", BLEDevice.lastDriverError());
        }
#endif
    }

    /** @brief GATT와 CoC에 각각 최대 한 작업만 유지해 두 transport를 병렬 진행합니다. */
    void issueClientTraffic()
    {
        if (!hasClient() || !traffic_started)
        {
            return;
        }
        if (!gatt_inflight && client_gatt_completed < required_operations)
        {
            MultiPayload::build(gatt_payload, peerMarker(), MultiPayload::gatt_kind,
                                client_gatt_completed, nonce_binary);
            if (!BLEClient.write(client_connection, gatt_payload, sizeof(gatt_payload)))
            {
                fail("gatt_write_start", BLEDevice.lastDriverError());
                return;
            }
            gatt_inflight = true;
        }
        if (!coc_waiting_for_echo && client_coc_received < required_operations)
        {
            MultiPayload::build(coc_payload, peerMarker(), MultiPayload::coc_kind,
                                client_coc_received, nonce_binary);
            if (!BLEL2cap.send(client_channel, coc_payload, sizeof(coc_payload)))
            {
                fail("coc_send_start", BLEDevice.lastDriverError());
                return;
            }
            coc_waiting_for_echo = true;
        }
    }

    /** @brief 모든 local link가 100회씩 전진한 지점을 고정 progress record로 출력합니다. */
    void printProgress()
    {
        std::uint32_t completed = required_operations;
        if (hasClient())
        {
            completed = client_gatt_completed < client_coc_received
                            ? client_gatt_completed
                            : client_coc_received;
        }
        if (hasServer())
        {
            const std::uint32_t server_completed =
                server_gatt_received < server_coc_sent ? server_gatt_received
                                                       : server_coc_sent;
            if (server_completed < completed)
            {
                completed = server_completed;
            }
        }
        while (progress_reported + 100U <= completed)
        {
            progress_reported += 100U;
            Serial.print(protocol);
            Serial.print("|PROGRESS|role=");
            Serial.print(roleName());
            Serial.print("|operations_per_link=");
            Serial.print(progress_reported);
            printSuffix();
            Serial.println();
        }
    }

    /** @brief role별 모든 정량 조건과 production CoC 통계를 확인해 RESULT·END를 출력합니다. */
    void finishIfComplete()
    {
        if (session_finished || !traffic_started)
        {
            return;
        }
        const bool client_complete = !hasClient() ||
                                     (client_gatt_completed == required_operations &&
                                      client_coc_received == required_operations &&
            client_coc_sent == required_operations);
        const bool server_complete = !hasServer() ||
                                     (server_gatt_received == required_operations &&
                                      server_coc_received == required_operations &&
                                      server_coc_sent == required_operations);
        if (!client_complete || !server_complete)
        {
            return;
        }
        const nucode::ble::BLEL2capStatistics statistics = BLEL2cap.statistics();
#if defined(NUCODE_M29_MULTI_MIXED)
        const std::uint32_t expected_connections = 2U;
        const std::uint32_t expected_packets = 2000U;
#else
        const std::uint32_t expected_connections = 1U;
        const std::uint32_t expected_packets = 1000U;
#endif
        if (statistics.connected != expected_connections || statistics.sent != expected_packets ||
            statistics.received != expected_packets || statistics.disconnected != 0U ||
            statistics.backpressure != 0U || statistics.rejected != 0U ||
            statistics.dropped_events != 0U || cross_link_events != 0U ||
            payload_errors != 0U || !callback_context_valid)
        {
            fail("final_statistics");
            return;
        }
        Serial.print(protocol);
        Serial.print("|RESULT|role=");
        Serial.print(roleName());
        Serial.print("|connections=");
        Serial.print(expected_connections);
        Serial.print("|gatt_tx=");
        Serial.print(client_gatt_completed);
        Serial.print("|gatt_rx=");
        Serial.print(server_gatt_received);
        Serial.print("|coc_tx=");
        Serial.print(client_coc_sent + server_coc_sent);
        Serial.print("|coc_rx=");
        Serial.print(client_coc_received + server_coc_received);
        Serial.print("|cross_link=0|payload_errors=0|dropped_events=0");
        Serial.print("|callback_context=pass");
        printSuffix();
        Serial.println();
        Serial.print(protocol);
        Serial.print("|END|role=");
        Serial.print(roleName());
        Serial.print("|status=pass");
        printSuffix();
        Serial.println();
        session_finished = true;
    }

    /** @brief mixed/central에서 두 transport가 준비된 순간 traffic을 시작합니다. */
    void startTrafficIfReady()
    {
        if (traffic_started)
        {
            return;
        }
        if (hasClient() && (!client_discovered || !client_channel_connected))
        {
            return;
        }
        if (hasServer() && (!server_connection.valid() || !server_channel_connected))
        {
            return;
        }
        printLinkIfReady();
        traffic_started = true;
        issueClientTraffic();
    }

    /** @brief exact nonce가 포함된 peer scan result 하나만 연결합니다. */
    void onScanResult(const nucode::ble::BLEScanResult &result, void *context)
    {
        static_cast<void>(context);
        checkCallbackContext();
        if (session_finished || !session_started || !scan_started || peer_found ||
            !result.connectable || result.scan_response || !validRfPeer(result))
        {
            return;
        }
        peer_found = true;
        peer_address = result.address;
    }

    /** @brief link 식별 가능한 GATT client 완료만 현재 client state에 반영합니다. */
    void onClientEvent(const nucode::ble::BLEGattClientEventInfo &information, void *context)
    {
        static_cast<void>(context);
        checkCallbackContext();
        if (!session_started || session_finished)
        {
            return;
        }
        if (information.connection != client_connection)
        {
            ++cross_link_events;
            fail("cross_link_gatt_client");
            return;
        }
        if (information.event == nucode::ble::BLEGattClientEvent::operation_failed)
        {
            fail("gatt_client_operation", information.status);
            return;
        }
        if (!client_discovered)
        {
            if (information.event != nucode::ble::BLEGattClientEvent::discovery_complete ||
                !BLEClient.discovered(client_connection))
            {
                fail("gatt_discovery_result");
                return;
            }
            client_discovered = true;
            startMixedAdvertisingIfReady();
            startTrafficIfReady();
            return;
        }
        if (information.event != nucode::ble::BLEGattClientEvent::write_complete ||
            !gatt_inflight)
        {
            fail("gatt_write_event");
            return;
        }
        gatt_inflight = false;
        ++client_gatt_completed;
        issueClientTraffic();
        printProgress();
        finishIfComplete();
    }

    /** @brief server write의 link marker·sequence·payload를 main thread에서 검증합니다. */
    void onCharacteristicEvent(nucode::ble::BLECharacteristic &characteristic,
                               const nucode::ble::BLECharacteristicEventInfo &information,
                               void *context)
    {
        static_cast<void>(characteristic);
        static_cast<void>(context);
        checkCallbackContext();
        if (!session_started || session_finished ||
            information.event != nucode::ble::BLECharacteristicEvent::written)
        {
            return;
        }
        if (information.connection != server_connection)
        {
            ++cross_link_events;
            fail("cross_link_gatt_server");
            return;
        }
        if (information.offset != 0U || information.without_response ||
            !MultiPayload::valid(information.data, information.length, serverMarker(),
                                 MultiPayload::gatt_kind, server_gatt_received,
                                 nonce_binary))
        {
            ++payload_errors;
            fail("gatt_server_payload");
            return;
        }
        ++server_gatt_received;
        printProgress();
        finishIfComplete();
    }

    /** @brief GAP의 local role로 mixed의 두 generation handle을 분리합니다. */
    void onBleEvent(const nucode::ble::BLEEventInfo &information, void *context)
    {
        static_cast<void>(context);
        checkCallbackContext();
        if (!session_started || session_finished)
        {
            return;
        }
        if (information.event == nucode::ble::BLEEvent::error)
        {
            fail("gap_error", BLEDevice.lastDriverError());
            return;
        }
        if (information.event == nucode::ble::BLEEvent::connected)
        {
            if (!information.connection.valid())
            {
                fail("connection_handle");
                return;
            }
            if (information.role == nucode::ble::BLELinkRole::central && hasClient())
            {
                if (client_connection.valid() &&
                    client_connection != information.connection)
                {
                    ++cross_link_events;
                    fail("duplicate_client_link");
                    return;
                }
                client_connection = information.connection;
                if (!BLEL2cap.connect(client_connection, coc_psm, client_channel) ||
                    !BLEClient.discover(client_connection, service_uuid, characteristic_uuid))
                {
                    fail("client_link_setup", BLEDevice.lastDriverError());
                }
                return;
            }
            if (information.role == nucode::ble::BLELinkRole::peripheral && hasServer())
            {
                if (server_connection.valid())
                {
                    ++cross_link_events;
                    fail("duplicate_server_link");
                    return;
                }
                server_connection = information.connection;
                printLinkIfReady();
                startTrafficIfReady();
                return;
            }
            ++cross_link_events;
            fail("unexpected_connection_role");
            return;
        }
        if (information.event == nucode::ble::BLEEvent::disconnected)
        {
            fail("early_disconnect");
        }
    }

    /** @brief 두 link의 CoC channel·payload·echo를 generation handle로 분리합니다. */
    void onL2capEvent(const nucode::ble::BLEL2capEventInfo &information, void *context)
    {
        static_cast<void>(context);
        checkCallbackContext();
        if (!session_started || session_finished)
        {
            return;
        }
        const bool client_event = client_channel.valid() && information.channel == client_channel;
        const bool server_event = server_channel.valid() && information.channel == server_channel;
        if (information.event == nucode::ble::BLEL2capEvent::connected)
        {
            if (information.connection == client_connection && information.channel == client_channel &&
                hasClient() && !client_channel_connected)
            {
                if (information.local_mtu != 512U || information.remote_mtu != 512U)
                {
                    fail("client_coc_mtu");
                    return;
                }
                client_channel_connected = true;
                startMixedAdvertisingIfReady();
                startTrafficIfReady();
                return;
            }
            if (information.connection == server_connection && hasServer() &&
                !server_channel_connected)
            {
                if (information.local_mtu != 512U || information.remote_mtu != 512U)
                {
                    fail("server_coc_mtu");
                    return;
                }
                server_channel = information.channel;
                server_channel_connected = true;
                printLinkIfReady();
                startTrafficIfReady();
                return;
            }
            ++cross_link_events;
            fail("cross_link_coc_connect");
            return;
        }
        if (!client_event && !server_event)
        {
            ++cross_link_events;
            fail("cross_link_coc_event");
            return;
        }
        if (information.event == nucode::ble::BLEL2capEvent::disconnected)
        {
            fail("early_coc_disconnect", information.status);
            return;
        }
        if (information.event == nucode::ble::BLEL2capEvent::sent)
        {
            if (client_event)
            {
                ++client_coc_sent;
                if (client_coc_sent > required_operations)
                {
                    fail("client_coc_sent_overflow");
                }
                printProgress();
                finishIfComplete();
            }
            else if (!server_echo_pending)
            {
                fail("server_coc_unexpected_sent");
            }
            else
            {
                server_echo_pending = false;
                ++server_coc_sent;
                printProgress();
                finishIfComplete();
            }
            return;
        }
        if (information.event != nucode::ble::BLEL2capEvent::received)
        {
            return;
        }
        if (client_event)
        {
            if (!coc_waiting_for_echo ||
                !MultiPayload::valid(information.data, information.length, peerMarker(),
                                     MultiPayload::coc_kind, client_coc_received,
                                     nonce_binary))
            {
                ++payload_errors;
                fail("client_coc_payload");
                return;
            }
            coc_waiting_for_echo = false;
            ++client_coc_received;
            issueClientTraffic();
            printProgress();
            finishIfComplete();
            return;
        }
        if (server_echo_pending ||
            !MultiPayload::valid(information.data, information.length, serverMarker(),
                                 MultiPayload::coc_kind, server_coc_received, nonce_binary))
        {
            ++payload_errors;
            fail("server_coc_payload");
            return;
        }
        ++server_coc_received;
        server_echo_pending = true;
        if (!BLEL2cap.send(server_channel, information.data, information.length))
        {
            server_echo_pending = false;
            fail("server_coc_echo", BLEDevice.lastDriverError());
        }
    }

    /** @brief 검증된 START 뒤 role별 server와 scan/advertising을 시작합니다. */
    void startProtocol()
    {
        if (!acceptStartCommand())
        {
            fail("start_record");
            return;
        }
        session_started = true;
        session_deadline = k_uptime_get() + session_timeout_ms;
        printBegin();
        if (hasServer() && !BLEL2cap.startServer(coc_psm))
        {
            fail("coc_server", BLEDevice.lastDriverError());
            return;
        }
#if defined(NUCODE_M29_MULTI_PERIPHERAL)
        if (!startAdvertising())
        {
            fail("peripheral_advertising", BLEDevice.lastDriverError());
        }
#else
        if (!startScan())
        {
            fail("scan_start", BLEDevice.lastDriverError());
        }
#endif
    }

    /** @brief Host의 bounded 한 줄 command만 수집합니다. */
    void pollHostCommand()
    {
        while (Serial.available() > 0 && !session_started && !session_finished)
        {
            const int incoming = Serial.read();
            if (incoming < 0)
            {
                return;
            }
            const char value = static_cast<char>(incoming);
            if (value == '\r')
            {
                continue;
            }
            if (value == '\n')
            {
                command[command_length] = '\0';
                if (::strcmp(command, ready_query) == 0)
                {
                    command_length = 0U;
                    printReady();
                    return;
                }
                startProtocol();
                return;
            }
            if (command_length + 1U >= sizeof(command))
            {
                fail("command_overflow");
                return;
            }
            command[command_length++] = value;
        }
    }

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
