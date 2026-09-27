/**
 * @file main.cpp
 * @brief 두 NU54DK로 M29-W03의 512-byte reliable write 원자성을 반복 검증합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <Arduino.h>
#include <NUCODE_BLE.h>

#include <zephyr/kernel.h>

#include <cstddef>
#include <cstdint>
#include <string.h>

#ifndef M29_LONG_WRITE_CORE_REVISION
#error "M29_LONG_WRITE_CORE_REVISION is required"
#endif

static_assert(nucode::ble::BLECharacteristic::maximum_value_length == 512U);
static_assert(CONFIG_BT_MAX_CONN == 2);
static_assert(CONFIG_BT_CTLR_SDC_PERIPHERAL_COUNT == 1);
static_assert(CONFIG_BT_L2CAP_TX_MTU == 247);
static_assert(CONFIG_BT_ATT_PREPARE_COUNT == 6);

namespace
{

    constexpr char protocol[] = "M29W03|1";
    constexpr char ready_query[] = "M29W03|1|READY?";
    constexpr char start_prefix[] = "M29W03|1|START|nonce=";
    constexpr char core_field[] = "|core=";
    constexpr char peer_name[] = "NU54-M29-WRITE";
    constexpr char service_text[] = "8e7e2903-7d8c-4c1a-9d2d-8b6519f77410";
    constexpr char characteristic_text[] = "8e7e2904-7d8c-4c1a-9d2d-8b6519f77410";
    constexpr std::size_t nonce_text_length = 32U;
    constexpr std::size_t nonce_binary_length = 16U;
    constexpr std::size_t payload_length = 512U;
    constexpr std::uint32_t required_iterations = 100U;
    constexpr std::int64_t protocol_timeout_ms = 300000;
    constexpr std::int64_t disconnect_settle_ms = 100;

    enum class Phase : std::uint8_t
    {
        waiting,
        scanning,
        connecting,
        mtu,
        discovering,
        writing,
        reading,
        settling,
        complete,
    };

    const nucode::ble::BLEUuid service_uuid(service_text);
    const nucode::ble::BLEUuid characteristic_uuid(characteristic_text);
    nucode::ble::BLEService test_service(service_uuid);
    nucode::ble::BLECharacteristic test_characteristic(
        characteristic_uuid, nucode::ble::BLEProperty::read | nucode::ble::BLEProperty::write,
        nucode::ble::BLEPermission::read | nucode::ble::BLEPermission::write, payload_length);

    char nonce[nonce_text_length + 1U] = {};
    std::uint8_t nonce_binary[nonce_binary_length] = {};
    std::uint8_t payload[payload_length] = {};
    [[maybe_unused]] std::uint8_t snapshot[payload_length] = {};
    char command[128] = {};
    std::size_t command_length = 0U;
    bool protocol_started = false;
    bool protocol_finished = false;
    bool callback_context_valid = true;
    bool link_reported = false;
    [[maybe_unused]] bool disconnect_requested = false;
    Phase phase = Phase::waiting;
    struct k_thread *setup_thread = nullptr;
    std::int64_t protocol_deadline = 0;
    [[maybe_unused]] std::int64_t disconnect_at = 0;
    nucode::ble::BLEConnectionHandle connection_handle;
    [[maybe_unused]] std::uint32_t iteration = 0U;
    [[maybe_unused]] std::uint32_t completed_reads = 0U;
    [[maybe_unused]] std::uint32_t completed_writes = 0U;
    [[maybe_unused]] std::uint32_t corrupt_values = 0U;
    [[maybe_unused]] std::uint32_t partial_commits = 0U;

    /** @brief 현재 image의 고정 role 이름을 반환합니다. */
    const char *roleName()
    {
#if defined(NUCODE_M29_LONG_WRITE_CENTRAL)
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
        Serial.print(M29_LONG_WRITE_CORE_REVISION);
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

    /** @brief session nonce와 iteration으로 512-byte deterministic payload를 만듭니다. */
    void buildPayload(std::uint32_t value_iteration)
    {
        for (std::size_t index = 0U; index < payload_length; ++index)
        {
            payload[index] = static_cast<std::uint8_t>(nonce_binary[index % nonce_binary_length] ^
                                                       static_cast<std::uint8_t>(index) ^
                                                       static_cast<std::uint8_t>(index >> 8U) ^
                                                       static_cast<std::uint8_t>(value_iteration));
        }
    }

    /** @brief 지정 iteration의 512-byte payload 전체를 검증합니다. */
    bool validPayload(const std::uint8_t *data, std::size_t length, std::uint32_t value_iteration)
    {
        if (data == nullptr || length != payload_length)
        {
            return false;
        }
        for (std::size_t index = 0U; index < payload_length; ++index)
        {
            const std::uint8_t expected = static_cast<std::uint8_t>(
                nonce_binary[index % nonce_binary_length] ^ static_cast<std::uint8_t>(index) ^
                static_cast<std::uint8_t>(index >> 8U) ^
                static_cast<std::uint8_t>(value_iteration));
            if (data[index] != expected)
            {
                return false;
            }
        }
        return true;
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
            ::strcmp(revision_field + ::strlen(core_field), M29_LONG_WRITE_CORE_REVISION) != 0)
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
        Serial.println(M29_LONG_WRITE_CORE_REVISION);
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
#if defined(NUCODE_M29_LONG_WRITE_CENTRAL)
        Serial.print("|reads=");
        Serial.print(completed_reads);
        Serial.print("|writes=");
        Serial.print(completed_writes);
        Serial.print("|bytes=");
        Serial.print(payload_length);
        Serial.print("|corrupt=");
        Serial.print(corrupt_values);
        Serial.print("|stale=0|callback_context=");
        Serial.print(callback_context_valid ? "pass" : "fail");
#else
        Serial.print("|writes=");
        Serial.print(completed_writes);
        Serial.print("|bytes=");
        Serial.print(payload_length);
        Serial.print("|corrupt=");
        Serial.print(corrupt_values);
        Serial.print("|partial_commit=");
        Serial.print(partial_commits);
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

#if defined(NUCODE_M29_LONG_WRITE_CENTRAL)
    /** @brief 현재 iteration의 512-byte reliable write를 시작합니다. */
    void startWrite()
    {
        buildPayload(iteration);
        phase = Phase::writing;
        if (!BLEClient.write(connection_handle, payload, sizeof(payload)))
        {
            fail("write_start", BLEDevice.lastDriverError());
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

    /** @brief discovery·write·read를 exact link에서 100회 직렬 진행합니다. */
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
            fail("gatt_operation", information.status);
            return;
        }
        if (phase == Phase::discovering)
        {
            if (information.event != nucode::ble::BLEGattClientEvent::discovery_complete ||
                !BLEClient.discovered(connection_handle))
            {
                fail("discovery_result");
                return;
            }
            startWrite();
            return;
        }
        if (phase == Phase::writing)
        {
            if (information.event != nucode::ble::BLEGattClientEvent::write_complete)
            {
                fail("unexpected_write_event");
                return;
            }
            ++completed_writes;
            phase = Phase::reading;
            if (!BLEClient.read(connection_handle))
            {
                fail("read_start");
            }
            return;
        }
        if (phase != Phase::reading ||
            information.event != nucode::ble::BLEGattClientEvent::read_complete)
        {
            fail("unexpected_read_event");
            return;
        }
        if (!validPayload(information.data, information.length, iteration))
        {
            ++corrupt_values;
            fail("read_payload");
            return;
        }
        ++completed_reads;
        if (completed_reads == required_iterations && completed_writes == required_iterations)
        {
            phase = Phase::settling;
            disconnect_at = k_uptime_get() + disconnect_settle_ms;
            return;
        }
        ++iteration;
        startWrite();
    }
#else
    /** @brief server가 완성된 512-byte 값 하나만 main thread에 전달했는지 확인합니다. */
    void onCharacteristicEvent(nucode::ble::BLECharacteristic &characteristic,
                               const nucode::ble::BLECharacteristicEventInfo &information,
                               void *context)
    {
        static_cast<void>(context);
        checkCallbackContext();
        if (protocol_finished || information.event != nucode::ble::BLECharacteristicEvent::written)
        {
            return;
        }
        if (information.connection != connection_handle)
        {
            fail("cross_link_write");
            return;
        }
        if (information.length != payload_length || information.offset != 0U ||
            information.without_response)
        {
            ++partial_commits;
            fail("partial_commit");
            return;
        }
        if (!validPayload(information.data, information.length, completed_writes))
        {
            ++corrupt_values;
            fail("write_payload");
            return;
        }
        const std::size_t copied = characteristic.readValue(snapshot, sizeof(snapshot));
        if (!validPayload(snapshot, copied, completed_writes))
        {
            ++corrupt_values;
            fail("cached_payload");
            return;
        }
        ++completed_writes;
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
            fail("gap_error", BLEDevice.lastDriverError());
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
#if defined(NUCODE_M29_LONG_WRITE_CENTRAL)
            if (information.role != nucode::ble::BLELinkRole::central)
#else
            if (information.role != nucode::ble::BLELinkRole::peripheral)
#endif
            {
                fail("connection_role");
                return;
            }
            phase = Phase::mtu;
#if defined(NUCODE_M29_LONG_WRITE_CENTRAL)
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
#if defined(NUCODE_M29_LONG_WRITE_CENTRAL)
            phase = Phase::discovering;
            if (!BLEClient.discover(connection_handle, service_uuid, characteristic_uuid))
            {
                fail("discovery_start");
            }
#endif
            return;
        }
        if (information.event == nucode::ble::BLEEvent::disconnected)
        {
#if defined(NUCODE_M29_LONG_WRITE_CENTRAL)
            if (phase != Phase::settling)
            {
                fail("early_disconnect");
                return;
            }
            printResultAndEnd();
#else
            if (!link_reported || completed_writes != required_iterations)
            {
                fail("incomplete_disconnect", static_cast<int>(completed_writes));
                return;
            }
            printResultAndEnd();
#endif
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
#if defined(NUCODE_M29_LONG_WRITE_CENTRAL)
        phase = Phase::scanning;
        if (!BLEScan.clearFilters() || !BLEScan.filterServiceUuid(service_uuid) ||
            !BLEScan.start(true))
        {
            fail("scan_start");
        }
#else
        buildPayload(0U);
        if (!test_characteristic.setValue(payload, sizeof(payload)))
        {
            fail("payload_seed");
            return;
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
#if !defined(NUCODE_M29_LONG_WRITE_CENTRAL)
    test_characteristic.onEvent(onCharacteristicEvent);
    if (!test_service.addCharacteristic(test_characteristic) || !BLEDevice.addService(test_service))
    {
        fail("schema");
        return;
    }
#endif
    BLEDevice.onEventInfo(onBleEvent);
#if defined(NUCODE_M29_LONG_WRITE_CENTRAL)
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
#if defined(NUCODE_M29_LONG_WRITE_CENTRAL)
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
