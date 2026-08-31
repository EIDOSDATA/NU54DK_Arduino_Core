/**
 * @file main.cpp
 * @brief 두 NU54DK 사이의 M19 GAP 검색·연결·재연결 HIL protocol을 구현합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <Arduino.h>
#include <NUCODE_BLE_GAP.h>

#include <zephyr/kernel.h>

#include <cstddef>
#include <cstdint>
#include <string.h>

namespace
{

constexpr char start_prefix[] = "NUCODE_M19_START:";
constexpr char peer_name[] = "NU54-GAP";
constexpr std::size_t nonce_length = 32U;
constexpr std::size_t nonce_binding_length = 6U;
constexpr std::uint16_t company_id = 0x054dU;
constexpr std::int64_t link_hold_ms = 700;
constexpr std::int64_t reconnect_delay_ms = 600;

nucode::ble::BLEUuid service_uuid;
char nonce[nonce_length + 1U] = {};
std::uint8_t nonce_binding[nonce_binding_length] = {};
char command[64] = {};
std::size_t command_length = 0U;
bool protocol_started = false;
bool protocol_failed = false;
bool callback_context_valid = true;
struct k_thread *setup_thread = nullptr;
std::uint32_t connection_count = 0U;
std::uint32_t disconnection_count = 0U;
#ifdef NUCODE_M19_CENTRAL
std::int64_t connected_at = 0;
bool disconnect_pending = false;
std::int64_t reconnect_at = 0;
bool reconnect_pending = false;
bool scan_accepted = false;
#endif

/** @brief 현재 role 이름을 반환합니다. */
const char *roleName()
{
#ifdef NUCODE_M19_CENTRAL
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
        Serial.print("NUCODE_M19_FAIL:role=");
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

/** @brief hex nonce 한 글자를 binary nibble로 변환합니다. */
std::uint8_t hexNibble(char value)
{
    return static_cast<std::uint8_t>(value <= '9' ? value - '0'
                                                  : value - 'a' + 10);
}

/** @brief full nonce UUID와 48-bit manufacturer 보조 binding을 만듭니다. */
bool configureNonceBinding()
{
    char canonical[37] = {};
    const std::size_t groups[] = {8U, 4U, 4U, 4U, 12U};
    std::size_t source = 0U;
    std::size_t destination = 0U;
    for (std::size_t group = 0U; group < 5U; ++group)
    {
        if (group != 0U)
        {
            canonical[destination++] = '-';
        }
        memcpy(&canonical[destination], &nonce[source], groups[group]);
        source += groups[group];
        destination += groups[group];
    }
    service_uuid = nucode::ble::BLEUuid(canonical);
    for (std::size_t index = 0U; index < nonce_binding_length; ++index)
    {
        nonce_binding[index] = static_cast<std::uint8_t>(
            (hexNibble(nonce[index * 2U]) << 4U) |
            hexNibble(nonce[index * 2U + 1U]));
    }
    return service_uuid.valid();
}

#ifdef NUCODE_M19_CENTRAL
/** @brief AD payload에서 exact manufacturer data를 검증합니다. */
bool validManufacturerData(const nucode::ble::BLEScanResult &result)
{
    std::size_t cursor = 0U;
    while (cursor < result.payload_length)
    {
        const std::size_t field_length = result.payload[cursor];
        if (field_length == 0U)
        {
            break;
        }
        if (cursor + field_length >= result.payload_length)
        {
            return false;
        }
        if (result.payload[cursor + 1U] == 0xffU && field_length == 9U)
        {
            const std::uint8_t *value = &result.payload[cursor + 2U];
            return value[0] == static_cast<std::uint8_t>(company_id & 0xffU) &&
                   value[1] == static_cast<std::uint8_t>(company_id >> 8U) &&
                   memcmp(&value[2], nonce_binding,
                          nonce_binding_length) == 0;
        }
        cursor += field_length + 1U;
    }
    return false;
}

/** @brief UUID software filter를 통과한 광고를 검증하고 연결을 시작합니다. */
void onScanResult(const nucode::ble::BLEScanResult &result, void *context)
{
    static_cast<void>(context);
    checkCallbackContext();
    if (!protocol_started || protocol_failed || scan_accepted)
    {
        return;
    }
    if (!result.connectable || result.scan_response || !validManufacturerData(result))
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
    passToken("NUCODE_M19_CENTRAL:SCAN_FILTER:PASS");
    if (!BLEConnection.connect(result.address))
    {
        fail("connect-start");
    }
}
#endif

/** @brief GAP event를 main-thread 상태 전이로 바꿉니다. */
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
#ifdef NUCODE_M19_CENTRAL
        connected_at = k_uptime_get();
        disconnect_pending = true;
#endif
        if (connection_count == 1U)
        {
            Serial.print("NUCODE_M19_EVENT:CONNECTED:round=1:nonce=");
            Serial.println(nonce);
#ifdef NUCODE_M19_CENTRAL
            std::int8_t tx_power = 0;
            if (!BLEConnection.requestMtu() ||
                !BLEConnection.requestPhy(true, false) ||
                !BLEConnection.requestParameters(24U, 40U, 0U, 400U) ||
                !BLEConnection.txPower(tx_power))
            {
                fail("link-request");
                return;
            }
            passToken("NUCODE_M19_CENTRAL:TX_POWER:PASS");
            passToken("NUCODE_M19_CENTRAL:LINK_REQUESTS:PASS");
#endif
        }
        else if (connection_count == 2U)
        {
            Serial.print("NUCODE_M19_EVENT:CONNECTED:round=2:nonce=");
            Serial.println(nonce);
            Serial.print("NUCODE_M19_");
#ifdef NUCODE_M19_CENTRAL
            Serial.print("CENTRAL");
#else
            Serial.print("PERIPHERAL");
#endif
            Serial.print(":RECONNECT:PASS:nonce=");
            Serial.println(nonce);
        }
        else
        {
            fail("connection-count");
        }
    }
    else if (event == nucode::ble::BLEEvent::disconnected)
    {
        ++disconnection_count;
        Serial.print("NUCODE_M19_EVENT:DISCONNECTED:count=");
        Serial.print(disconnection_count);
        Serial.print(":nonce=");
        Serial.println(nonce);

        if (disconnection_count == 1U)
        {
#ifdef NUCODE_M19_CENTRAL
            reconnect_at = k_uptime_get() + reconnect_delay_ms;
            reconnect_pending = true;
#else
            if (!BLEAdvertising.start())
            {
                fail("readvertise");
                return;
            }
            passToken("NUCODE_M19_PERIPHERAL:READVERTISE:PASS");
#endif
        }
        else if (disconnection_count == 2U)
        {
            Serial.print("NUCODE_M19_");
#ifdef NUCODE_M19_CENTRAL
            Serial.print("CENTRAL");
#else
            Serial.print("PERIPHERAL");
#endif
            Serial.print(":FINAL:PASS:callback_context=");
            Serial.print(callback_context_valid ? "PASS" : "FAIL");
            Serial.print(":reconnect=PASS:nonce=");
            Serial.println(nonce);
        }
    }
}

/** @brief 검증된 start command로 role별 GAP 동작을 시작합니다. */
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
    if (!configureNonceBinding())
    {
        fail("nonce-binding");
        return;
    }
    protocol_started = true;

#ifdef NUCODE_M19_CENTRAL
    if (!BLEScan.clearFilters() || !BLEScan.filterServiceUuid(service_uuid) ||
        !BLEScan.start(true))
    {
        fail("scan-start");
        return;
    }
#else
    if (!BLEAdvertising.clear() || !BLEAdvertising.setConnectable(true) ||
        !BLEAdvertising.setInterval(160U, 240U) ||
        !BLEAdvertising.addServiceUuid(service_uuid) ||
        !BLEAdvertising.setManufacturerData(company_id, nonce_binding,
                                             nonce_binding_length) ||
        !BLEAdvertising.setScanResponseName(true) || !BLEAdvertising.start())
    {
        fail("advertise-start");
        return;
    }
    passToken("NUCODE_M19_PERIPHERAL:ADVERTISE:PASS");
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
    BLEDevice.onEvent(onBleEvent);
#ifdef NUCODE_M19_CENTRAL
    BLEScan.onResult(onScanResult);
#endif
    if (!BLEDevice.begin(peer_name))
    {
        fail("device-begin");
        return;
    }
    Serial.print("NUCODE_M19_READY:role=");
    Serial.println(roleName());
}

void loop()
{
    pollHostCommand();
    BLEDevice.poll();
    if (!protocol_started || protocol_failed)
    {
        delay(1);
        return;
    }
#ifdef NUCODE_M19_CENTRAL
    const std::int64_t now = k_uptime_get();
    if (disconnect_pending && BLEConnection.connected() &&
        now - connected_at >= link_hold_ms)
    {
        disconnect_pending = false;
        if (!BLEConnection.disconnect())
        {
            fail("disconnect-start");
        }
    }
    if (reconnect_pending && !BLEConnection.connected() &&
        !BLEConnection.connecting() && now >= reconnect_at)
    {
        reconnect_pending = false;
        passToken("NUCODE_M19_CENTRAL:RECONNECT_REQUEST:PASS");
        if (!BLEConnection.reconnect())
        {
            fail("reconnect-start");
        }
    }
#endif
    delay(1);
}
