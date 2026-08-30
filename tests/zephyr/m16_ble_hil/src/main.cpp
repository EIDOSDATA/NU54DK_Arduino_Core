/**
 * @file main.cpp
 * @brief 두 NU54DK 사이의 M16 NUS 양방향·재연결 HIL protocol을 구현합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <Arduino.h>
#include <NUCODE_BLE.h>

#include <zephyr/kernel.h>
#include <zephyr/sys/util.h>

#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

namespace
{

constexpr char start_prefix[] = "NUCODE_M16_START:";
constexpr char peer_name[] = "NU54-NUS";
constexpr size_t nonce_length = 32U;
constexpr size_t first_round_total = 1U + 20U + 21U + 64U;
constexpr size_t second_round_total = 21U;

char nonce[nonce_length + 1U] = {};
char command[64] = {};
size_t command_length = 0U;
bool protocol_started = false;
bool protocol_failed = false;
bool callback_context_valid = true;
struct k_thread *setup_thread = nullptr;
uint32_t connection_count = 0U;
uint32_t disconnection_count = 0U;

#ifdef NUCODE_M16_CENTRAL
constexpr size_t frame_lengths[] = {1U, 20U, 21U, 64U};
uint8_t expected[64] = {};
size_t expected_length = 0U;
size_t received_length = 0U;
size_t frame_index = 0U;
bool waiting_echo = false;
bool first_disconnect_requested = false;
bool final_complete = false;
#else
size_t received_this_connection = 0U;
bool first_round_reported = false;
bool final_complete = false;
#endif

/** @brief HIL 실패를 한 번만 UART에 기록합니다. */
void fail(const char *reason)
{
    if (!protocol_failed)
    {
        Serial.print("NUCODE_M16_FAIL:role=");
#ifdef NUCODE_M16_CENTRAL
        Serial.print("central");
#else
        Serial.print("peripheral");
#endif
        Serial.print(":reason=");
        Serial.println(reason);
    }
    protocol_failed = true;
}

#ifdef NUCODE_M16_CENTRAL
/** @brief Central role에서 동일 nonce로 재현 가능한 payload를 만듭니다. */
void makePayload(uint8_t marker, uint8_t *buffer, size_t length)
{
    if (buffer == nullptr || length == 0U)
    {
        return;
    }
    buffer[0] = marker;
    for (size_t index = 1U; index < length; ++index)
    {
        buffer[index] = static_cast<uint8_t>(nonce[(index - 1U) % nonce_length]);
    }
}
#endif

/** @brief BLE event callback이 setup/loop와 같은 Arduino main thread인지 검증합니다. */
void onBleEvent(nucode::ble::Event event, void *context)
{
    ARG_UNUSED(context);
    if (k_current_get() != setup_thread)
    {
        callback_context_valid = false;
        fail("callback-context");
    }
    if (event == nucode::ble::Event::connected)
    {
        ++connection_count;
#ifndef NUCODE_M16_CENTRAL
        received_this_connection = 0U;
#endif
        Serial.print("NUCODE_M16_EVENT:CONNECTED:round=");
        Serial.print(connection_count);
        Serial.print(":nonce=");
        Serial.println(nonce);
    }
    else if (event == nucode::ble::Event::ready)
    {
        Serial.print("NUCODE_M16_EVENT:READY:round=");
        Serial.print(connection_count);
        Serial.print(":nonce=");
        Serial.println(nonce);
    }
    else if (event == nucode::ble::Event::disconnected)
    {
        ++disconnection_count;
        Serial.print("NUCODE_M16_EVENT:DISCONNECTED:count=");
        Serial.print(disconnection_count);
        Serial.print(":nonce=");
        Serial.println(nonce);
    }
}

/** @brief 완전한 host start command를 검증하고 role별 BLE를 시작합니다. */
void startProtocol()
{
    const size_t prefix_length = strlen(start_prefix);
    if (strncmp(command, start_prefix, prefix_length) != 0 ||
        strlen(command + prefix_length) != nonce_length)
    {
        fail("bad-start-command");
        return;
    }
    for (size_t index = 0U; index < nonce_length; ++index)
    {
        const char value = command[prefix_length + index];
        if (!((value >= '0' && value <= '9') || (value >= 'a' && value <= 'f')))
        {
            fail("bad-nonce");
            return;
        }
    }
    memcpy(nonce, command + prefix_length, nonce_length + 1U);
    protocol_started = true;
    BLESerial.onEvent(onBleEvent);
#ifdef NUCODE_M16_CENTRAL
    if (!BLESerial.beginCentral() || !BLESerial.scanForNus(peer_name))
    {
        fail("central-start");
        return;
    }
    Serial.print("NUCODE_M16_CENTRAL:SCAN:PASS:nonce=");
#else
    if (!BLESerial.beginPeripheral(peer_name) || !BLESerial.startAdvertising())
    {
        fail("peripheral-start");
        return;
    }
    Serial.print("NUCODE_M16_PERIPHERAL:ADVERTISE:PASS:nonce=");
#endif
    Serial.println(nonce);
}

/** @brief host UART에서 newline command 한 줄을 bounded buffer로 읽습니다. */
void pollHostCommand()
{
    while (!protocol_started && Serial.available() > 0)
    {
        const int read = Serial.read();
        if (read < 0)
        {
            return;
        }
        const char value = static_cast<char>(read);
        if (value == '\r')
        {
            continue;
        }
        if (value == '\n')
        {
            command[command_length] = '\0';
            startProtocol();
            command_length = 0U;
            return;
        }
        if (command_length + 1U >= sizeof(command))
        {
            fail("command-overflow");
            command_length = 0U;
            return;
        }
        command[command_length++] = value;
    }
}

#ifdef NUCODE_M16_CENTRAL
/** @brief 현재 echo가 기대 payload와 byte 단위로 같은지 검사합니다. */
void receiveCentralEcho()
{
    while (waiting_echo && BLESerial.available() > 0)
    {
        const int value = BLESerial.read();
        if (value < 0 || received_length >= expected_length ||
            static_cast<uint8_t>(value) != expected[received_length])
        {
            fail("echo-mismatch");
            return;
        }
        ++received_length;
    }
    if (!waiting_echo || received_length != expected_length)
    {
        return;
    }
    waiting_echo = false;
    Serial.print("NUCODE_M16_CENTRAL:FRAME:PASS:round=");
    Serial.print(connection_count);
    Serial.print(":size=");
    Serial.print(expected_length);
    Serial.print(":nonce=");
    Serial.println(nonce);
    if (connection_count == 1U)
    {
        ++frame_index;
    }
    else
    {
        final_complete = true;
        Serial.print("NUCODE_M16_CENTRAL:FINAL:PASS:callback_context=");
        Serial.print(callback_context_valid ? "PASS" : "FAIL");
        Serial.print(":reconnect=PASS:nonce=");
        Serial.println(nonce);
    }
}

/** @brief 연결 round에 맞는 다음 NUS write를 전송합니다. */
void driveCentral()
{
    receiveCentralEcho();
    if (protocol_failed || final_complete || waiting_echo || !BLESerial.ready())
    {
        return;
    }
    if (connection_count == 1U && frame_index < ARRAY_SIZE(frame_lengths))
    {
        expected_length = frame_lengths[frame_index];
        makePayload(static_cast<uint8_t>('A' + frame_index), expected, expected_length);
    }
    else if (connection_count == 1U && !first_disconnect_requested)
    {
        first_disconnect_requested = true;
        if (!BLESerial.disconnect())
        {
            fail("disconnect-request");
        }
        return;
    }
    else if (connection_count >= 2U)
    {
        expected_length = second_round_total;
        makePayload('Z', expected, expected_length);
    }
    else
    {
        return;
    }
    received_length = 0U;
    if (BLESerial.write(expected, expected_length) != expected_length)
    {
        fail("central-write");
        return;
    }
    waiting_echo = true;
}
#else
/** @brief Peripheral 수신 stream을 그대로 notify하여 양방향 경로를 검증합니다. */
void drivePeripheral()
{
    uint8_t buffer[64] = {};
    size_t length = 0U;
    while (length < sizeof(buffer) && BLESerial.available() > 0)
    {
        const int value = BLESerial.read();
        if (value < 0)
        {
            break;
        }
        buffer[length++] = static_cast<uint8_t>(value);
    }
    if (length == 0U)
    {
        return;
    }
    if (BLESerial.write(buffer, length) != length)
    {
        fail("peripheral-notify");
        return;
    }
    received_this_connection += length;
    if (connection_count == 1U && received_this_connection == first_round_total &&
        !first_round_reported)
    {
        first_round_reported = true;
        Serial.print("NUCODE_M16_PERIPHERAL:ROUND:PASS:round=1:bytes=");
        Serial.print(received_this_connection);
        Serial.print(":nonce=");
        Serial.println(nonce);
    }
    else if (connection_count >= 2U && received_this_connection == second_round_total &&
             !final_complete)
    {
        final_complete = true;
        Serial.print("NUCODE_M16_PERIPHERAL:FINAL:PASS:callback_context=");
        Serial.print(callback_context_valid ? "PASS" : "FAIL");
        Serial.print(":reconnect=PASS:bytes=");
        Serial.print(received_this_connection);
        Serial.print(":nonce=");
        Serial.println(nonce);
    }
    else if (received_this_connection > first_round_total)
    {
        fail("unexpected-byte-count");
    }
}
#endif

} // namespace

void setup()
{
    setup_thread = k_current_get();
    Serial.begin(115200);
    Serial.print("NUCODE_M16_READY:role=");
#ifdef NUCODE_M16_CENTRAL
    Serial.println("central");
#else
    Serial.println("peripheral");
#endif
}

void loop()
{
    pollHostCommand();
    if (!protocol_started || protocol_failed)
    {
        return;
    }
    BLESerial.poll();
#ifdef NUCODE_M16_CENTRAL
    driveCentral();
#else
    drivePeripheral();
#endif
}
