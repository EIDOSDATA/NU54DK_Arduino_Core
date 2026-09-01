/**
 * @file main.cpp
 * @brief 두 NU54DK 사이의 M20 범용 GATT server/client HIL protocol을 구현합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <Arduino.h>
#include <NUCODE_BLE.h>

#include <zephyr/kernel.h>

#include <cstddef>
#include <cstdint>
#include <string.h>

namespace
{

    constexpr char start_prefix[] = "NUCODE_M20_START:";
    constexpr char peer_name[] = "NU54-GATT";
    constexpr char service_text[] = "8e7e2001-7d8c-4c1a-9d2d-8b6519f77410";
    constexpr char characteristic_text[] = "8e7e2002-7d8c-4c1a-9d2d-8b6519f77410";
    constexpr std::size_t nonce_length = 32U;
    constexpr std::size_t nonce_bytes_length = nonce_length / 2U;
    constexpr std::int64_t reconnect_delay_ms = 700;

    const nucode::ble::BLEUuid service_uuid(service_text);
    const nucode::ble::BLEUuid characteristic_uuid(characteristic_text);
    nucode::ble::BLEService test_service(service_uuid);
    nucode::ble::BLECharacteristic test_characteristic(
        characteristic_uuid,
        nucode::ble::BLEProperty::read | nucode::ble::BLEProperty::write |
            nucode::ble::BLEProperty::write_without_response |
            nucode::ble::BLEProperty::notify | nucode::ble::BLEProperty::indicate,
        nucode::ble::BLEPermission::read | nucode::ble::BLEPermission::write, 32U);

    char nonce[nonce_length + 1U] = {};
    std::uint8_t nonce_bytes[nonce_bytes_length] = {};
    char command[64] = {};
    std::size_t command_length = 0U;
    bool protocol_started = false;
    bool protocol_failed = false;
    bool callback_context_valid = true;
    struct k_thread *setup_thread = nullptr;
    std::uint32_t connection_count = 0U;
    std::uint32_t disconnection_count = 0U;

#ifdef NUCODE_M20_CENTRAL
    enum class CentralPhase : std::uint8_t
    {
        idle,
        discovering_round_1,
        reading,
        writing_response,
        writing_command,
        subscribing_notification_1,
        waiting_notification_1,
        unsubscribing_notification_1,
        subscribing_indication,
        waiting_indication,
        unsubscribing_indication,
        waiting_disconnect_1,
        reconnect_delay,
        discovering_round_2,
        subscribing_notification_2,
        waiting_notification_2,
        unsubscribing_notification_2,
        waiting_disconnect_2,
        complete,
    };

    CentralPhase phase = CentralPhase::idle;
    std::int64_t reconnect_at = 0;
    bool scan_accepted = false;
#endif

    /** @brief 현재 role 이름을 반환합니다. */
    const char *roleName()
    {
#ifdef NUCODE_M20_CENTRAL
        return "central";
#else
        return "peripheral";
#endif
    }

    /** @brief HIL 실패를 한 번만 UART에 기록합니다. */
    void fail(const char *reason)
    {
        if (!protocol_failed)
        {
            Serial.print("NUCODE_M20_FAIL:role=");
            Serial.print(roleName());
            Serial.print(":reason=");
            Serial.println(reason);
        }
        protocol_failed = true;
    }

    /** @brief protocol token 뒤에 현재 nonce를 붙입니다. */
    void passToken(const char *token)
    {
        Serial.print(token);
        Serial.print(":nonce=");
        Serial.println(nonce);
    }

    /** @brief callback이 Arduino main thread에서 실행됐는지 누적 검사합니다. */
    void checkCallbackContext()
    {
        if (k_current_get() != setup_thread)
        {
            callback_context_valid = false;
            fail("callback-context");
        }
    }

    /** @brief exact payload 일치 여부를 검사합니다. */
    bool matches(const std::uint8_t *data, std::size_t length,
                 const char *expected)
    {
        const std::size_t expected_length = strlen(expected);
        return data != nullptr && length == expected_length &&
               memcmp(data, expected, length) == 0;
    }

    /** @brief 소문자 16진수 한 글자를 binary nibble로 변환합니다. */
    std::uint8_t hexNibble(char value)
    {
        return value <= '9' ? static_cast<std::uint8_t>(value - '0')
                            : static_cast<std::uint8_t>(value - 'a' + 10);
    }

#ifdef NUCODE_M20_CENTRAL
    /** @brief peer가 반환한 128-bit nonce challenge가 정확한지 검사합니다. */
    bool matchesNonce(const std::uint8_t *data, std::size_t length)
    {
        return data != nullptr && length == nonce_bytes_length &&
               memcmp(data, nonce_bytes, nonce_bytes_length) == 0;
    }
#endif

#ifndef NUCODE_M20_CENTRAL
    /** @brief server write·CCC·indication 완료를 main-thread에서 검증합니다. */
    void onCharacteristic(
        nucode::ble::BLECharacteristic &characteristic,
        const nucode::ble::BLECharacteristicEventInfo &event, void *context)
    {
        static_cast<void>(context);
        checkCallbackContext();
        if (!protocol_started || protocol_failed)
        {
            return;
        }
        if (&characteristic != &test_characteristic)
        {
            fail("characteristic-owner");
            return;
        }

        if (event.event == nucode::ble::BLECharacteristicEvent::written)
        {
            if (!event.without_response && matches(event.data, event.length, "WR"))
            {
                passToken("NUCODE_M20_PERIPHERAL:WRITE_RESPONSE:PASS");
            }
            else if (event.without_response && matches(event.data, event.length, "WC"))
            {
                passToken("NUCODE_M20_PERIPHERAL:WRITE_COMMAND:PASS");
            }
            else
            {
                fail("write-payload");
            }
            return;
        }

        if (event.event == nucode::ble::BLECharacteristicEvent::subscribed)
        {
            if (event.status == 1)
            {
                const char *payload = connection_count == 1U ? "NTF1" : "NTF2";
                if (!test_characteristic.setValue(payload, 4U) ||
                    !test_characteristic.notify())
                {
                    fail("notify-send");
                }
            }
            else if (event.status == 2 && connection_count == 1U)
            {
                if (!test_characteristic.setValue("IND1", 4U) ||
                    !test_characteristic.indicate())
                {
                    fail("indicate-send");
                }
            }
            else
            {
                fail("ccc-value");
            }
            return;
        }

        if (event.event ==
            nucode::ble::BLECharacteristicEvent::indication_confirmed)
        {
            passToken("NUCODE_M20_PERIPHERAL:INDICATION_CONFIRMED:PASS");
        }
        else if (event.event ==
                 nucode::ble::BLECharacteristicEvent::indication_failed)
        {
            fail("indication-failed");
        }
    }
#else
    /** @brief service UUID filter 결과를 연결 대상으로 사용합니다. */
    void onScanResult(const nucode::ble::BLEScanResult &result, void *context)
    {
        static_cast<void>(context);
        checkCallbackContext();
        if (!protocol_started || protocol_failed || scan_accepted)
        {
            return;
        }
        if (!result.connectable || result.scan_response)
        {
            fail("filtered-advertisement");
            return;
        }
        scan_accepted = true;
        if (!BLEScan.stop())
        {
            fail("scan-stop");
            return;
        }
        passToken("NUCODE_M20_CENTRAL:SCAN_FILTER:PASS");
        if (!BLEConnection.connect(result.address))
        {
            fail("connect-start");
        }
    }

    /** @brief generic GATT client callback의 단계별 결과를 검증합니다. */
    void onClientEvent(nucode::ble::BLEGattClientEvent event,
                       const std::uint8_t *data, std::size_t length, void *context)
    {
        static_cast<void>(context);
        checkCallbackContext();
        if (protocol_failed)
        {
            return;
        }
        if (event == nucode::ble::BLEGattClientEvent::operation_failed)
        {
            fail("client-operation");
            return;
        }
        if (event == nucode::ble::BLEGattClientEvent::handles_invalidated)
        {
            if (BLEClient.discovered() || BLEClient.remoteService().valid() ||
                BLEClient.remoteCharacteristic().valid())
            {
                fail("handle-invalidation");
                return;
            }
            Serial.print("NUCODE_M20_CENTRAL:HANDLES_INVALIDATED:PASS:round=");
            Serial.print(disconnection_count);
            Serial.print(":nonce=");
            Serial.println(nonce);
            if (disconnection_count == 2U)
            {
                phase = CentralPhase::complete;
                Serial.print(
                    "NUCODE_M20_CENTRAL:FINAL:PASS:callback_context=");
                Serial.print(callback_context_valid ? "PASS" : "FAIL");
                Serial.print(":rediscovery=PASS:nonce=");
                Serial.println(nonce);
            }
            return;
        }

        switch (phase)
        {
        case CentralPhase::discovering_round_1:
            if (event != nucode::ble::BLEGattClientEvent::discovery_complete ||
                !BLEClient.discovered() || !BLEClient.remoteService().valid() ||
                !BLEClient.remoteCharacteristic().valid())
            {
                fail("discover-round-1");
                return;
            }
            passToken("NUCODE_M20_CENTRAL:DISCOVERY:PASS:round=1");
            phase = CentralPhase::reading;
            if (!BLEClient.read())
            {
                fail("read-start");
            }
            break;
        case CentralPhase::reading:
            if (event != nucode::ble::BLEGattClientEvent::read_complete ||
                !matchesNonce(data, length))
            {
                fail("read-result");
                return;
            }
            passToken("NUCODE_M20_CENTRAL:NONCE_CHALLENGE:PASS");
            passToken("NUCODE_M20_CENTRAL:READ:PASS");
            phase = CentralPhase::writing_response;
            if (!BLEClient.write("WR", 2U))
            {
                fail("write-start");
            }
            break;
        case CentralPhase::writing_response:
            if (event != nucode::ble::BLEGattClientEvent::write_complete)
            {
                fail("write-complete");
                return;
            }
            passToken("NUCODE_M20_CENTRAL:WRITE_RESPONSE:PASS");
            phase = CentralPhase::writing_command;
            if (!BLEClient.writeWithoutResponse("WC", 2U))
            {
                fail("write-command-start");
            }
            break;
        case CentralPhase::writing_command:
            if (event !=
                nucode::ble::BLEGattClientEvent::write_without_response_complete)
            {
                fail("write-command-complete");
                return;
            }
            passToken("NUCODE_M20_CENTRAL:WRITE_COMMAND:PASS");
            phase = CentralPhase::subscribing_notification_1;
            if (!BLEClient.subscribeNotifications())
            {
                fail("notify-subscribe-start");
            }
            break;
        case CentralPhase::subscribing_notification_1:
            if (event != nucode::ble::BLEGattClientEvent::subscribed)
            {
                fail("notify-subscribe");
                return;
            }
            passToken("NUCODE_M20_CENTRAL:SUBSCRIBE_NOTIFY:PASS:round=1");
            phase = CentralPhase::waiting_notification_1;
            break;
        case CentralPhase::waiting_notification_1:
            if (event != nucode::ble::BLEGattClientEvent::notification_received ||
                !matches(data, length, "NTF1"))
            {
                fail("notification-round-1");
                return;
            }
            passToken("NUCODE_M20_CENTRAL:NOTIFICATION:PASS:round=1");
            phase = CentralPhase::unsubscribing_notification_1;
            if (!BLEClient.unsubscribe())
            {
                fail("notify-unsubscribe-start");
            }
            break;
        case CentralPhase::unsubscribing_notification_1:
            if (event != nucode::ble::BLEGattClientEvent::unsubscribed)
            {
                fail("notify-unsubscribe");
                return;
            }
            passToken("NUCODE_M20_CENTRAL:UNSUBSCRIBE_NOTIFY:PASS:round=1");
            phase = CentralPhase::subscribing_indication;
            if (!BLEClient.subscribeIndications())
            {
                fail("indicate-subscribe-start");
            }
            break;
        case CentralPhase::subscribing_indication:
            if (event != nucode::ble::BLEGattClientEvent::subscribed)
            {
                fail("indicate-subscribe");
                return;
            }
            passToken("NUCODE_M20_CENTRAL:SUBSCRIBE_INDICATE:PASS");
            phase = CentralPhase::waiting_indication;
            break;
        case CentralPhase::waiting_indication:
            if (event != nucode::ble::BLEGattClientEvent::indication_received ||
                !matches(data, length, "IND1"))
            {
                fail("indication-result");
                return;
            }
            passToken("NUCODE_M20_CENTRAL:INDICATION:PASS");
            phase = CentralPhase::unsubscribing_indication;
            if (!BLEClient.unsubscribe())
            {
                fail("indicate-unsubscribe-start");
            }
            break;
        case CentralPhase::unsubscribing_indication:
            if (event != nucode::ble::BLEGattClientEvent::unsubscribed)
            {
                fail("indicate-unsubscribe");
                return;
            }
            passToken("NUCODE_M20_CENTRAL:UNSUBSCRIBE_INDICATE:PASS");
            phase = CentralPhase::waiting_disconnect_1;
            if (!BLEConnection.disconnect())
            {
                fail("disconnect-round-1");
            }
            break;
        case CentralPhase::discovering_round_2:
            if (event != nucode::ble::BLEGattClientEvent::discovery_complete ||
                !BLEClient.discovered())
            {
                fail("discover-round-2");
                return;
            }
            passToken("NUCODE_M20_CENTRAL:DISCOVERY:PASS:round=2");
            phase = CentralPhase::subscribing_notification_2;
            if (!BLEClient.subscribeNotifications())
            {
                fail("notify-subscribe-round-2-start");
            }
            break;
        case CentralPhase::subscribing_notification_2:
            if (event != nucode::ble::BLEGattClientEvent::subscribed)
            {
                fail("notify-subscribe-round-2");
                return;
            }
            passToken("NUCODE_M20_CENTRAL:SUBSCRIBE_NOTIFY:PASS:round=2");
            phase = CentralPhase::waiting_notification_2;
            break;
        case CentralPhase::waiting_notification_2:
            if (event != nucode::ble::BLEGattClientEvent::notification_received ||
                !matches(data, length, "NTF2"))
            {
                fail("notification-round-2");
                return;
            }
            passToken("NUCODE_M20_CENTRAL:NOTIFICATION:PASS:round=2");
            phase = CentralPhase::unsubscribing_notification_2;
            if (!BLEClient.unsubscribe())
            {
                fail("notify-unsubscribe-round-2-start");
            }
            break;
        case CentralPhase::unsubscribing_notification_2:
            if (event != nucode::ble::BLEGattClientEvent::unsubscribed)
            {
                fail("notify-unsubscribe-round-2");
                return;
            }
            passToken("NUCODE_M20_CENTRAL:UNSUBSCRIBE_NOTIFY:PASS:round=2");
            phase = CentralPhase::waiting_disconnect_2;
            if (!BLEConnection.disconnect())
            {
                fail("disconnect-round-2");
            }
            break;
        default:
            fail("unexpected-client-event");
            break;
        }
    }
#endif

    /** @brief GAP event로 연결 round와 재광고·재발견 경계를 제어합니다. */
    void onBleEvent(nucode::ble::BLEEvent event, void *context)
    {
        static_cast<void>(context);
        checkCallbackContext();
        if (!protocol_started || protocol_failed)
        {
            return;
        }
        if (event == nucode::ble::BLEEvent::connected)
        {
            ++connection_count;
            Serial.print("NUCODE_M20_EVENT:CONNECTED:round=");
            Serial.print(connection_count);
            Serial.print(":nonce=");
            Serial.println(nonce);
#ifdef NUCODE_M20_CENTRAL
            if (!BLEConnection.requestMtu())
            {
                fail("mtu-request");
                return;
            }
            if (connection_count == 1U)
            {
                phase = CentralPhase::discovering_round_1;
            }
            else if (connection_count == 2U)
            {
                phase = CentralPhase::discovering_round_2;
            }
            else
            {
                fail("connection-count");
                return;
            }
            if (!BLEClient.discover(service_uuid, characteristic_uuid))
            {
                fail("discover-start");
            }
#endif
        }
        else if (event == nucode::ble::BLEEvent::disconnected)
        {
            ++disconnection_count;
            Serial.print("NUCODE_M20_EVENT:DISCONNECTED:count=");
            Serial.print(disconnection_count);
            Serial.print(":nonce=");
            Serial.println(nonce);
            if (disconnection_count == 1U)
            {
#ifdef NUCODE_M20_CENTRAL
                phase = CentralPhase::reconnect_delay;
                reconnect_at = k_uptime_get() + reconnect_delay_ms;
#else
                if (!BLEAdvertising.start())
                {
                    fail("readvertise");
                    return;
                }
                passToken("NUCODE_M20_PERIPHERAL:READVERTISE:PASS");
#endif
            }
            else if (disconnection_count == 2U)
            {
#ifdef NUCODE_M20_CENTRAL
                phase = CentralPhase::waiting_disconnect_2;
#else
                Serial.print("NUCODE_M20_");
                Serial.print("PERIPHERAL");
                Serial.print(":FINAL:PASS:callback_context=");
                Serial.print(callback_context_valid ? "PASS" : "FAIL");
                Serial.print(":rediscovery=PASS:nonce=");
                Serial.println(nonce);
#endif
            }
        }
    }

    /** @brief 검증된 start command로 scan 또는 advertising을 시작합니다. */
    void startProtocol()
    {
        const std::size_t prefix_length = strlen(start_prefix);
        if (strncmp(command, start_prefix, prefix_length) != 0 ||
            strlen(command + prefix_length) != nonce_length)
        {
            fail("bad-start-command");
            return;
        }
        for (std::size_t index = 0U; index < nonce_length; ++index)
        {
            const char value = command[prefix_length + index];
            if (!((value >= '0' && value <= '9') || (value >= 'a' && value <= 'f')))
            {
                fail("bad-nonce");
                return;
            }
        }
        memcpy(nonce, command + prefix_length, nonce_length + 1U);
        for (std::size_t index = 0U; index < nonce_bytes_length; ++index)
        {
            nonce_bytes[index] = static_cast<std::uint8_t>(
                (hexNibble(nonce[index * 2U]) << 4U) |
                hexNibble(nonce[index * 2U + 1U]));
        }
#ifndef NUCODE_M20_CENTRAL
        if (!test_characteristic.setValue(nonce_bytes, nonce_bytes_length))
        {
            fail("nonce-challenge-seed");
            return;
        }
#endif
        protocol_started = true;

#ifdef NUCODE_M20_CENTRAL
        if (!BLEScan.clearFilters() || !BLEScan.filterServiceUuid(service_uuid) ||
            !BLEScan.start(true))
        {
            fail("scan-start");
        }
#else
        if (!BLEAdvertising.clear() || !BLEAdvertising.setConnectable(true) ||
            !BLEAdvertising.addServiceUuid(service_uuid) ||
            !BLEAdvertising.setScanResponseName(true) || !BLEAdvertising.start())
        {
            fail("advertise-start");
            return;
        }
        passToken("NUCODE_M20_PERIPHERAL:ADVERTISE:PASS");
#endif
    }

    /** @brief host UART의 bounded start command를 수집합니다. */
    void pollHostCommand()
    {
        while (Serial.available() > 0 && !protocol_started && !protocol_failed)
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
                startProtocol();
                return;
            }
            if (command_length + 1U >= sizeof(command))
            {
                fail("command-overflow");
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
#ifndef NUCODE_M20_CENTRAL
    if (!test_service.addCharacteristic(test_characteristic) ||
        !BLEDevice.addService(test_service) ||
        !test_characteristic.setValue("INIT", 4U))
    {
        fail("schema");
        return;
    }
    test_characteristic.onEvent(onCharacteristic);
#endif
    BLEDevice.onEvent(onBleEvent);
#ifdef NUCODE_M20_CENTRAL
    BLEScan.onResult(onScanResult);
    BLEClient.onEvent(onClientEvent);
#endif
    if (!BLEDevice.begin(peer_name))
    {
        fail("device-begin");
        return;
    }
    Serial.print("NUCODE_M20_READY:role=");
    Serial.println(roleName());
}

void loop()
{
    pollHostCommand();
    BLEDevice.poll();
#ifdef NUCODE_M20_CENTRAL
    if (protocol_started && !protocol_failed &&
        phase == CentralPhase::reconnect_delay &&
        k_uptime_get() >= reconnect_at && !BLEConnection.connected() &&
        !BLEConnection.connecting())
    {
        passToken("NUCODE_M20_CENTRAL:RECONNECT_REQUEST:PASS");
        phase = CentralPhase::idle;
        if (!BLEConnection.reconnect())
        {
            fail("reconnect-start");
        }
    }
#endif
    delay(1);
}
