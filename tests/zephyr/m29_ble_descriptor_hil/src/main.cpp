/**
 * @file main.cpp
 * @brief 두 NU54DK로 M29-W04 descriptor·authorization·read multiple을 반복 검증합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <Arduino.h>
#include <NUCODE_BLE.h>

#include <zephyr/kernel.h>

#include <cstddef>
#include <cstdint>
#include <errno.h>
#include <string.h>

#ifndef M29_DESCRIPTOR_CORE_REVISION
#error "M29_DESCRIPTOR_CORE_REVISION is required"
#endif

static_assert(nucode::ble::BLECharacteristic::maximum_descriptors == 4U);
static_assert(CONFIG_BT_GATT_READ_MULTIPLE == 1);
static_assert(CONFIG_BT_MAX_CONN == 2);
static_assert(CONFIG_BT_CTLR_SDC_PERIPHERAL_COUNT == 1);

namespace
{

    constexpr char protocol[] = "M29W04|1";
    constexpr char ready_query[] = "M29W04|1|READY?";
    constexpr char start_prefix[] = "M29W04|1|START|nonce=";
    constexpr char core_field[] = "|core=";
    constexpr char peer_name[] = "NU54-M29-DESC";
    constexpr char service_text[] = "8e7e2905-7d8c-4c1a-9d2d-8b6519f77410";
    constexpr char characteristic_text[] = "8e7e2906-7d8c-4c1a-9d2d-8b6519f77410";
    constexpr char descriptor_text_0[] = "8e7e2910-7d8c-4c1a-9d2d-8b6519f77410";
    constexpr char descriptor_text_1[] = "8e7e2911-7d8c-4c1a-9d2d-8b6519f77410";
    constexpr char descriptor_text_2[] = "8e7e2912-7d8c-4c1a-9d2d-8b6519f77410";
    constexpr char descriptor_text_3[] = "8e7e2913-7d8c-4c1a-9d2d-8b6519f77410";
    constexpr std::size_t nonce_text_length = 32U;
    constexpr std::size_t nonce_binary_length = 16U;
    constexpr std::size_t descriptor_count = 4U;
    constexpr std::size_t descriptor_value_length = 4U;
    constexpr std::uint32_t required_iterations = 100U;
    constexpr std::uint8_t authorization_att_error = 0x08U;
    constexpr std::int64_t protocol_timeout_ms = 300000;
    constexpr std::int64_t disconnect_settle_ms = 100;

    enum class Phase : std::uint8_t
    {
        waiting,
        scanning,
        connecting,
        mtu,
        discovering_characteristic,
        discovering_descriptor,
        rejecting,
        unlocking,
        reading,
        settling,
        complete,
    };

    const nucode::ble::BLEUuid service_uuid(service_text);
    const nucode::ble::BLEUuid characteristic_uuid(characteristic_text);
    const nucode::ble::BLEUuid descriptor_uuid_0(descriptor_text_0);
    const nucode::ble::BLEUuid descriptor_uuid_1(descriptor_text_1);
    const nucode::ble::BLEUuid descriptor_uuid_2(descriptor_text_2);
    const nucode::ble::BLEUuid descriptor_uuid_3(descriptor_text_3);
    const nucode::ble::BLEUuid *const descriptor_uuids[descriptor_count] = {
        &descriptor_uuid_0,
        &descriptor_uuid_1,
        &descriptor_uuid_2,
        &descriptor_uuid_3,
    };
    nucode::ble::BLEService test_service(service_uuid);
    nucode::ble::BLECharacteristic test_characteristic(
        characteristic_uuid, nucode::ble::BLEProperty::read | nucode::ble::BLEProperty::write,
        nucode::ble::BLEPermission::read | nucode::ble::BLEPermission::write,
        nonce_binary_length);
    nucode::ble::BLEDescriptor descriptor_0(descriptor_uuid_0,
                                             nucode::ble::BLEPermission::read,
                                             descriptor_value_length);
    nucode::ble::BLEDescriptor descriptor_1(descriptor_uuid_1,
                                             nucode::ble::BLEPermission::read,
                                             descriptor_value_length);
    nucode::ble::BLEDescriptor descriptor_2(descriptor_uuid_2,
                                             nucode::ble::BLEPermission::read,
                                             descriptor_value_length);
    nucode::ble::BLEDescriptor descriptor_3(descriptor_uuid_3,
                                             nucode::ble::BLEPermission::read,
                                             descriptor_value_length);
    nucode::ble::BLEDescriptor *const descriptors[descriptor_count] = {
        &descriptor_0,
        &descriptor_1,
        &descriptor_2,
        &descriptor_3,
    };

    char nonce[nonce_text_length + 1U] = {};
    std::uint8_t nonce_binary[nonce_binary_length] = {};
    char command[128] = {};
    std::size_t command_length = 0U;
    bool protocol_started = false;
    bool protocol_finished = false;
    bool callback_context_valid = true;
    [[maybe_unused]] bool descriptor_access_allowed = false;
    bool link_reported = false;
    [[maybe_unused]] bool disconnect_requested = false;
    Phase phase = Phase::waiting;
    struct k_thread *setup_thread = nullptr;
    std::int64_t protocol_deadline = 0;
    [[maybe_unused]] std::int64_t disconnect_at = 0;
    nucode::ble::BLEConnectionHandle connection_handle;
    [[maybe_unused]] std::size_t descriptor_discovery_index = 0U;
    [[maybe_unused]] std::uint16_t descriptor_handles[descriptor_count] = {};
    [[maybe_unused]] std::uint32_t completed_reads = 0U;
    [[maybe_unused]] std::uint32_t corrupt_values = 0U;
    [[maybe_unused]] std::uint32_t expected_denials = 0U;
    [[maybe_unused]] std::uint32_t authorization_errors = 0U;
    [[maybe_unused]] std::uint32_t authorization_checks = 0U;
    [[maybe_unused]] std::uint32_t authorization_allowed_events = 0U;
    [[maybe_unused]] std::uint32_t authorization_denied_events = 0U;
    [[maybe_unused]] std::uint32_t descriptor_written_events = 0U;

    /** @brief 현재 image의 고정 role 이름을 반환합니다. */
    const char *roleName()
    {
#if defined(NUCODE_M29_DESCRIPTOR_CENTRAL)
        return "central";
#else
        return "peripheral";
#endif
    }

    /** @brief 모든 session record에 exact nonce와 Core revision을 붙입니다. */
    void printSuffix()
    {
        Serial.print("|nonce=");
        Serial.print(nonce);
        Serial.print("|core=");
        Serial.print(M29_DESCRIPTOR_CORE_REVISION);
    }

    /** @brief 첫 실패를 고정 protocol로 출력하고 추가 동작을 중단합니다. */
    void fail(const char *stage, int code = 0)
    {
        if (protocol_finished)
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
        protocol_finished = true;
    }

    /** @brief callback이 Arduino main thread에서 실행됐는지 누적 확인합니다. */
    void checkCallbackContext()
    {
        if (k_current_get() != setup_thread)
        {
            callback_context_valid = false;
            fail("callback_context");
        }
    }

    /** @brief 소문자 hexadecimal nibble을 binary 값으로 변환합니다. */
    std::uint8_t hexNibble(char value)
    {
        return static_cast<std::uint8_t>(value <= '9' ? value - '0' : value - 'a' + 10);
    }

    /** @brief nonce를 binary seed로 변환합니다. */
    void decodeNonce()
    {
        for (std::size_t index = 0U; index < nonce_binary_length; ++index)
        {
            nonce_binary[index] = static_cast<std::uint8_t>((hexNibble(nonce[index * 2U]) << 4U) |
                                                            hexNibble(nonce[index * 2U + 1U]));
        }
    }

    /** @brief Host start record의 문법·nonce·exact revision을 엄격히 검증합니다. */
    bool acceptStartCommand()
    {
        const std::size_t prefix_length = ::strlen(start_prefix);
        if (::strncmp(command, start_prefix, prefix_length) != 0)
        {
            return false;
        }
        const char *nonce_text = command + prefix_length;
        for (std::size_t index = 0U; index < nonce_text_length; ++index)
        {
            const char value = nonce_text[index];
            if (!((value >= '0' && value <= '9') || (value >= 'a' && value <= 'f')))
            {
                return false;
            }
        }
        const char *revision_field = nonce_text + nonce_text_length;
        if (::strncmp(revision_field, core_field, ::strlen(core_field)) != 0 ||
            ::strcmp(revision_field + ::strlen(core_field), M29_DESCRIPTOR_CORE_REVISION) != 0)
        {
            return false;
        }
        ::memcpy(nonce, nonce_text, nonce_text_length);
        nonce[nonce_text_length] = '\0';
        decodeNonce();
        return true;
    }

    /** @brief READY 뒤 검증 session 시작 record를 출력합니다. */
    void printBegin()
    {
        Serial.print(protocol);
        Serial.print("|BEGIN|role=");
        Serial.print(roleName());
        printSuffix();
        Serial.println();
    }

    /** @brief Host 질의에 현재 image identity READY를 한 번 출력합니다. */
    void printReady()
    {
        Serial.print(protocol);
        Serial.print("|READY|role=");
        Serial.print(roleName());
        Serial.print("|core=");
        Serial.println(M29_DESCRIPTOR_CORE_REVISION);
    }

    /** @brief 실제 negotiated ATT MTU를 고정 LINK record로 출력합니다. */
    void printLink()
    {
        Serial.print(protocol);
        Serial.print("|LINK|role=");
        Serial.print(roleName());
        Serial.print("|mtu=");
        Serial.print(BLEConnection.mtu(connection_handle));
        printSuffix();
        Serial.println();
        link_reported = true;
    }

    /** @brief role별 정량 결과와 END를 고정 순서로 출력합니다. */
    void printResultAndEnd()
    {
        Serial.print(protocol);
        Serial.print("|RESULT|role=");
        Serial.print(roleName());
#if defined(NUCODE_M29_DESCRIPTOR_CENTRAL)
        Serial.print("|descriptors=");
        Serial.print(descriptor_discovery_index);
        Serial.print("|reads=");
        Serial.print(completed_reads);
        Serial.print("|handles=4|bytes=16|expected_denials=");
        Serial.print(expected_denials);
        Serial.print("|authorization_errors=");
        Serial.print(authorization_errors);
        Serial.print("|corrupt=");
        Serial.print(corrupt_values);
        Serial.print("|stale=0|callback_context=");
        Serial.print(callback_context_valid ? "pass" : "fail");
#else
        Serial.print("|descriptors=4|authorization_checks=");
        Serial.print(authorization_checks);
        Serial.print("|allowed=");
        Serial.print(authorization_allowed_events);
        Serial.print("|denied=");
        Serial.print(authorization_denied_events);
        Serial.print("|descriptor_writes=");
        Serial.print(descriptor_written_events);
        Serial.print("|authorization_errors=");
        Serial.print(authorization_errors);
        Serial.print("|callback_context=");
        Serial.print(callback_context_valid ? "pass" : "fail");
#endif
        printSuffix();
        Serial.println();
        Serial.print(protocol);
        Serial.print("|END|role=");
        Serial.print(roleName());
        Serial.print("|status=pass");
        printSuffix();
        Serial.println();
        protocol_finished = true;
        phase = Phase::complete;
    }

#if defined(NUCODE_M29_DESCRIPTOR_CENTRAL)
    /** @brief 네 descriptor의 exact remote handle로 다음 Read Multiple을 시작합니다. */
    void startReadMultiple()
    {
        phase = Phase::reading;
        if (!BLEClient.readMultiple(connection_handle, descriptor_handles, descriptor_count))
        {
            fail("read_multiple_start", BLEDevice.lastDriverError());
        }
    }

    /** @brief 다음 descriptor UUID를 discovery하거나 authorization negative를 시작합니다. */
    void continueDescriptorDiscovery()
    {
        if (descriptor_discovery_index < descriptor_count)
        {
            phase = Phase::discovering_descriptor;
            if (!BLEClient.discoverDescriptor(connection_handle,
                                              *descriptor_uuids[descriptor_discovery_index]))
            {
                fail("descriptor_discovery_start", BLEDevice.lastDriverError());
            }
            return;
        }
        const std::uint8_t rejected[] = {0xDEU, 0xADU};
        phase = Phase::rejecting;
        if (!BLEClient.write(connection_handle, rejected, sizeof(rejected)))
        {
            fail("authorization_negative_start", BLEDevice.lastDriverError());
        }
    }

    /** @brief exact service UUID가 포함된 connectable report 하나만 연결합니다. */
    void onScanResult(const nucode::ble::BLEScanResult &result, void *context)
    {
        static_cast<void>(context);
        checkCallbackContext();
        if (protocol_finished || phase != Phase::scanning || !result.connectable ||
            result.scan_response)
        {
            return;
        }
        if (!BLEScan.stop())
        {
            fail("scan_stop");
            return;
        }
        Serial.print(protocol);
        Serial.print("|SCAN|role=central|status=pass");
        printSuffix();
        Serial.println();
        phase = Phase::connecting;
        if (!BLEConnection.connect(result.address, connection_handle))
        {
            fail("connect_start");
        }
    }

    /** @brief descriptor discovery·authorization·4-handle read를 exact link에서 진행합니다. */
    void onClientEvent(const nucode::ble::BLEGattClientEventInfo &information, void *context)
    {
        static_cast<void>(context);
        checkCallbackContext();
        if (protocol_finished)
        {
            return;
        }
        if (information.connection != connection_handle)
        {
            fail("cross_link_event");
            return;
        }
        if (information.event == nucode::ble::BLEGattClientEvent::operation_failed)
        {
            if (phase != Phase::rejecting || information.att_error != authorization_att_error)
            {
                ++authorization_errors;
                fail("unexpected_gatt_failure", information.att_error);
                return;
            }
            ++expected_denials;
            phase = Phase::unlocking;
            if (!BLEClient.write(connection_handle, nonce_binary, sizeof(nonce_binary)))
            {
                fail("authorization_positive_start", BLEDevice.lastDriverError());
            }
            return;
        }
        if (phase == Phase::discovering_characteristic)
        {
            if (information.event != nucode::ble::BLEGattClientEvent::discovery_complete ||
                !BLEClient.discovered(connection_handle))
            {
                fail("characteristic_discovery_result");
                return;
            }
            continueDescriptorDiscovery();
            return;
        }
        if (phase == Phase::discovering_descriptor)
        {
            if (information.event !=
                nucode::ble::BLEGattClientEvent::descriptor_discovery_complete ||
                BLEClient.descriptorCount(connection_handle) != descriptor_discovery_index + 1U)
            {
                fail("descriptor_discovery_result");
                return;
            }
            const nucode::ble::BLERemoteDescriptor descriptor =
                BLEClient.remoteDescriptor(connection_handle, descriptor_discovery_index);
            if (!descriptor.valid() || descriptor.uuid() !=
                                           *descriptor_uuids[descriptor_discovery_index])
            {
                fail("descriptor_identity");
                return;
            }
            descriptor_handles[descriptor_discovery_index] = descriptor.handle();
            ++descriptor_discovery_index;
            continueDescriptorDiscovery();
            return;
        }
        if (phase == Phase::unlocking)
        {
            if (information.event != nucode::ble::BLEGattClientEvent::write_complete)
            {
                fail("authorization_positive_result");
                return;
            }
            startReadMultiple();
            return;
        }
        if (phase != Phase::reading ||
            information.event != nucode::ble::BLEGattClientEvent::read_multiple_complete)
        {
            fail("unexpected_client_event");
            return;
        }
        if (information.length != nonce_binary_length || information.data == nullptr ||
            ::memcmp(information.data, nonce_binary, nonce_binary_length) != 0)
        {
            ++corrupt_values;
            fail("read_multiple_payload");
            return;
        }
        ++completed_reads;
        if (completed_reads == required_iterations)
        {
            phase = Phase::settling;
            disconnect_at = k_uptime_get() + disconnect_settle_ms;
            return;
        }
        startReadMultiple();
    }
#else
    /** @brief characteristic write는 exact 128-bit nonce만 허용합니다. */
    bool authorizeCharacteristic(const nucode::ble::BLEGattAuthorizationRequest &request,
                                 void *context)
    {
        static_cast<void>(context);
        ++authorization_checks;
        if (request.connection != connection_handle || request.characteristic !=
                                                        &test_characteristic ||
            request.descriptor != nullptr)
        {
            ++authorization_errors;
            return false;
        }
        if (request.operation == nucode::ble::BLEGattAuthorizationOperation::read)
        {
            return true;
        }
        const bool allowed = !request.prepare && !request.execute &&
                             !request.without_response && request.offset == 0U &&
                             request.length == nonce_binary_length && request.data != nullptr &&
                             ::memcmp(request.data, nonce_binary, nonce_binary_length) == 0;
        if (allowed)
        {
            descriptor_access_allowed = true;
        }
        return allowed;
    }

    /** @brief descriptor는 unlock 뒤 exact link의 read만 허용합니다. */
    bool authorizeDescriptor(const nucode::ble::BLEGattAuthorizationRequest &request,
                             void *context)
    {
        nucode::ble::BLEDescriptor *expected =
            static_cast<nucode::ble::BLEDescriptor *>(context);
        ++authorization_checks;
        const bool valid = request.connection == connection_handle &&
                           request.characteristic == &test_characteristic &&
                           request.descriptor == expected &&
                           request.operation == nucode::ble::BLEGattAuthorizationOperation::read &&
                           request.data == nullptr && request.length == 0U &&
                           descriptor_access_allowed;
        if (!valid)
        {
            ++authorization_errors;
        }
        return valid;
    }

    /** @brief 동기 authorization 결과가 main thread로 정확히 복사됐는지 검증합니다. */
    void onCharacteristicEvent(nucode::ble::BLECharacteristic &characteristic,
                               const nucode::ble::BLECharacteristicEventInfo &information,
                               void *context)
    {
        static_cast<void>(context);
        checkCallbackContext();
        if (protocol_finished || &characteristic != &test_characteristic ||
            information.connection != connection_handle)
        {
            ++authorization_errors;
            fail("server_event_identity");
            return;
        }
        if (information.event == nucode::ble::BLECharacteristicEvent::authorization_allowed)
        {
            ++authorization_allowed_events;
            return;
        }
        if (information.event == nucode::ble::BLECharacteristicEvent::authorization_denied)
        {
            ++authorization_denied_events;
            return;
        }
        if (information.event == nucode::ble::BLECharacteristicEvent::descriptor_written)
        {
            ++descriptor_written_events;
            return;
        }
        if (information.event != nucode::ble::BLECharacteristicEvent::written)
        {
            ++authorization_errors;
            fail("unexpected_server_event");
        }
    }
#endif

    /** @brief GAP detailed event에서 exact link와 MTU·disconnect 경계를 검증합니다. */
    void onBleEvent(const nucode::ble::BLEEventInfo &information, void *context)
    {
        static_cast<void>(context);
        checkCallbackContext();
        if (!protocol_started || protocol_finished)
        {
            return;
        }
        if (information.event == nucode::ble::BLEEvent::error)
        {
            const int driver_error = BLEDevice.lastDriverError();
#if defined(NUCODE_M29_DESCRIPTOR_CENTRAL)
            /** @brief 예상 ATT 거부는 뒤따르는 상세 event에서 error code까지 판정합니다. */
            if (phase == Phase::rejecting && driver_error == -EIO)
            {
                return;
            }
#endif
            fail("gap_error", driver_error);
            return;
        }
        if (information.event == nucode::ble::BLEEvent::connected)
        {
            connection_handle = information.connection;
            if (!connection_handle.valid())
            {
                fail("connection_handle");
                return;
            }
#if defined(NUCODE_M29_DESCRIPTOR_CENTRAL)
            if (information.role != nucode::ble::BLELinkRole::central)
#else
            if (information.role != nucode::ble::BLELinkRole::peripheral)
#endif
            {
                fail("connection_role");
                return;
            }
            phase = Phase::mtu;
#if defined(NUCODE_M29_DESCRIPTOR_CENTRAL)
            if (!BLEConnection.requestMtu(connection_handle))
            {
                fail("mtu_request");
            }
#endif
            return;
        }
        if (information.connection != connection_handle)
        {
            return;
        }
        if (information.event == nucode::ble::BLEEvent::mtu_changed && !link_reported)
        {
            if (BLEConnection.mtu(connection_handle) != 247U)
            {
                fail("mtu_value", static_cast<int>(BLEConnection.mtu(connection_handle)));
                return;
            }
            printLink();
#if defined(NUCODE_M29_DESCRIPTOR_CENTRAL)
            phase = Phase::discovering_characteristic;
            if (!BLEClient.discover(connection_handle, service_uuid, characteristic_uuid))
            {
                fail("characteristic_discovery_start");
            }
#endif
            return;
        }
        if (information.event == nucode::ble::BLEEvent::disconnected)
        {
#if defined(NUCODE_M29_DESCRIPTOR_CENTRAL)
            if (phase != Phase::settling || descriptor_discovery_index != descriptor_count ||
                completed_reads != required_iterations || expected_denials != 1U ||
                authorization_errors != 0U || corrupt_values != 0U)
            {
                fail("incomplete_disconnect", static_cast<int>(completed_reads));
                return;
            }
#else
            if (!link_reported || authorization_checks != 402U ||
                authorization_allowed_events != 401U || authorization_denied_events != 1U ||
                descriptor_written_events != 0U || authorization_errors != 0U)
            {
                fail("authorization_totals", static_cast<int>(authorization_checks));
                return;
            }
#endif
            printResultAndEnd();
        }
    }

    /** @brief 검증된 start record에서 role별 advertising 또는 scan을 시작합니다. */
    void startProtocol()
    {
        if (!acceptStartCommand())
        {
            fail("start_record");
            return;
        }
        protocol_started = true;
        protocol_deadline = k_uptime_get() + protocol_timeout_ms;
        printBegin();
#if defined(NUCODE_M29_DESCRIPTOR_CENTRAL)
        phase = Phase::scanning;
        if (!BLEScan.clearFilters() || !BLEScan.filterServiceUuid(service_uuid) ||
            !BLEScan.start(true))
        {
            fail("scan_start");
        }
#else
        if (!test_characteristic.setValue(nonce_binary, sizeof(nonce_binary)))
        {
            fail("characteristic_seed");
            return;
        }
        for (std::size_t index = 0U; index < descriptor_count; ++index)
        {
            if (!descriptors[index]->setValue(nonce_binary + index * descriptor_value_length,
                                              descriptor_value_length))
            {
                fail("descriptor_seed", static_cast<int>(index));
                return;
            }
        }
        phase = Phase::connecting;
        if (!BLEAdvertising.clear() || !BLEAdvertising.setConnectable(true) ||
            !BLEAdvertising.addServiceUuid(service_uuid) ||
            !BLEAdvertising.setScanResponseName(true) || !BLEAdvertising.start())
        {
            fail("advertising_start");
            return;
        }
        Serial.print(protocol);
        Serial.print("|ADVERTISE|role=peripheral|status=pass");
        printSuffix();
        Serial.println();
#endif
    }

    /** @brief Host의 bounded 한 줄 start command만 수집합니다. */
    void pollHostCommand()
    {
        while (Serial.available() > 0 && !protocol_started && !protocol_finished)
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
#if !defined(NUCODE_M29_DESCRIPTOR_CENTRAL)
    test_characteristic.onAuthorize(authorizeCharacteristic);
    test_characteristic.onEvent(onCharacteristicEvent);
    for (std::size_t index = 0U; index < descriptor_count; ++index)
    {
        descriptors[index]->onAuthorize(authorizeDescriptor, descriptors[index]);
        if (!test_characteristic.addDescriptor(*descriptors[index]))
        {
            fail("descriptor_schema", static_cast<int>(index));
            return;
        }
    }
    if (!test_service.addCharacteristic(test_characteristic) || !BLEDevice.addService(test_service))
    {
        fail("service_schema");
        return;
    }
#endif
    BLEDevice.onEventInfo(onBleEvent);
#if defined(NUCODE_M29_DESCRIPTOR_CENTRAL)
    BLEScan.onResult(onScanResult);
    BLEClient.onDetailedEvent(onClientEvent);
#endif
    if (!BLEDevice.begin(peer_name))
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
#if defined(NUCODE_M29_DESCRIPTOR_CENTRAL)
    if (!protocol_finished && phase == Phase::settling && !disconnect_requested &&
        k_uptime_get() >= disconnect_at)
    {
        if (!BLEConnection.disconnect(connection_handle))
        {
            fail("disconnect");
        }
        else
        {
            disconnect_requested = true;
        }
    }
#endif
    if (protocol_started && !protocol_finished && k_uptime_get() >= protocol_deadline)
    {
        fail("timeout");
    }
    delay(1);
}
