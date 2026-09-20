/**
 * @file BISTimeReceiver.ino
 * @brief BIS 사용자 SDU와 수신 HCI 시각의 단조성을 검사합니다.
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE_ISO.h>

using nucode::ble::iso::BisFrame;
using nucode::ble::iso::Error;
using nucode::ble::iso::RawBis;
using nucode::ble::iso::Role;

namespace
{
    /** @brief source 예제와 공유하는 16-byte session ID입니다. */
    constexpr char sessionId[] = "NUCODE-TIME-BIS1";
    static_assert(sizeof(sessionId) == 17U, "session ID must be 16 bytes");

    RawBis bis;
    std::uint16_t received = 0U;
    std::uint16_t timestamped = 0U;
    std::uint16_t errors = 0U;
    std::uint32_t last_timestamp_us = 0U;
    std::uint32_t session_ms = 0U;
    std::uint32_t restart_ms = 0U;
    bool running = false;
    bool closing = false;
    bool connection_reported = false;

    /** @brief 수신 payload와 예상 sequence를 사용자 영역에서 검사합니다. */
    bool validFrame(const BisFrame &frame, std::uint16_t &number)
    {
        if (frame.length != 8U || frame.data[0] != 'T' || frame.data[1] != 'I' ||
            frame.data[6] != 0xB1U || frame.data[7] != 0x50U)
        {
            return false;
        }
        number = static_cast<std::uint16_t>(frame.data[2]) |
                 (static_cast<std::uint16_t>(frame.data[3]) << 8U);
        return number < 100U &&
               frame.data[4] == static_cast<std::uint8_t>(number ^ 0x5AU) &&
               frame.data[5] == static_cast<std::uint8_t>((number >> 8U) ^ 0xA5U);
    }

    /** @brief 수신 payload와 timestamp 검증 결과를 표시합니다. */
    void reportSession()
    {
        if (received == 100U && timestamped == 100U && errors == 0U)
        {
            Serial.print("BIS time received frames=");
            Serial.print(received);
            Serial.print(" timestamps=");
            Serial.print(timestamped);
            Serial.println(" errors=0");
        }
        else
        {
            Serial.print("BIS time invalid frames=");
            Serial.print(received);
            Serial.print(" timestamps=");
            Serial.print(timestamped);
            Serial.print(" errors=");
            Serial.println(errors);
        }
        bis.stop();
        closing = true;
    }

    /** @brief session ID가 일치하는 periodic advertising을 찾습니다. */
    void startSession()
    {
        const Error result = bis.begin(Role::bis_time_receiver,
                                       reinterpret_cast<const std::uint8_t *>(sessionId));
        if (result != Error::none)
        {
            Serial.print("BIS start failed: ");
            Serial.println(static_cast<unsigned>(result));
            restart_ms = millis() + 1000U;
            return;
        }
        received = 0U;
        timestamped = 0U;
        errors = 0U;
        last_timestamp_us = 0U;
        session_ms = millis();
        running = true;
        closing = false;
        connection_reported = false;
        Serial.println("BIS time receiver scanning");
    }
}

/** @brief 공개 API와 Core image revision을 표시합니다. */
void setup()
{
    Serial.begin(115200);
    Serial.print("BIS core revision=");
    Serial.println(RawBis::buildRevision());
    startSession();
}

/** @brief 받은 SDU 100개의 payload와 controller 시각을 검증합니다. */
void loop()
{
    if (!running)
    {
        if (static_cast<std::int32_t>(millis() - restart_ms) >= 0)
        {
            startSession();
        }
        delay(1);
        return;
    }
    const Error progress = bis.poll();
    if (!connection_reported && bis.connected())
    {
        connection_reported = true;
        Serial.print("BIS time receiver synchronized ms=");
        Serial.println(millis() - session_ms);
    }
    BisFrame frame = {};
    while (!closing && bis.readFrame(frame))
    {
        std::uint16_t number = 0U;
        if (!validFrame(frame, number))
        {
            ++errors;
            continue;
        }
        if (received == 0U)
        {
            Serial.print("BIS time first frame=");
            Serial.println(number);
        }
        if (number != received)
        {
            ++errors;
        }
        if (!frame.timestamp_valid ||
            (timestamped > 0U &&
             static_cast<std::int32_t>(frame.timestamp_us - last_timestamp_us) <= 0))
        {
            ++errors;
        }
        else
        {
            ++timestamped;
            last_timestamp_us = frame.timestamp_us;
        }
        ++received;
    }
    if (!closing && received == 100U)
    {
        reportSession();
    }
    if (!closing && progress == Error::peer_stopped)
    {
        reportSession();
    }
    if (!closing && progress == Error::transport_failure)
    {
        Serial.print("BIS time error: ");
        Serial.print(bis.nativeError());
        Serial.print(" frames=");
        Serial.print(received);
        Serial.print(" timestamps=");
        Serial.print(timestamped);
        Serial.print(" errors=");
        Serial.println(errors);
        bis.stop();
        closing = true;
    }
    if (!closing && millis() - session_ms >= 15000U)
    {
        Serial.print("BIS time receive timeout frames=");
        Serial.println(received);
        bis.stop();
        closing = true;
    }
    if (closing && bis.stopped())
    {
        running = false;
        restart_ms = millis() + 1000U;
    }
    delay(1);
}
