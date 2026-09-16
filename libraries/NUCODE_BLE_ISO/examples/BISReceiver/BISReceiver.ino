/**
 * @file BISReceiver.ino
 * @brief 동기화한 BIS의 사용자 SDU와 순서를 Arduino 코드에서 검사합니다.
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
    constexpr char sessionId[] = "NUCODE-RAW-BIS01";
    static_assert(sizeof(sessionId) == 17U, "session ID must be 16 bytes");

    RawBis bis;
    std::uint16_t received = 0U;
    std::uint16_t errors = 0U;
    std::uint32_t session_ms = 0U;
    std::uint32_t restart_ms = 0U;
    bool running = false;
    bool closing = false;

    /** @brief 수신 payload와 예상 sequence를 사용자 영역에서 검사합니다. */
    bool validFrame(const BisFrame &frame)
    {
        if (frame.length != 8U || frame.data[0] != 'B' || frame.data[1] != 'I' ||
            frame.data[6] != 0xB1U || frame.data[7] != 0x50U)
        {
            return false;
        }
        const std::uint16_t number = static_cast<std::uint16_t>(frame.data[2]) |
                                     (static_cast<std::uint16_t>(frame.data[3]) << 8U);
        return number == received &&
               frame.data[4] == static_cast<std::uint8_t>(number ^ 0x5AU) &&
               frame.data[5] == static_cast<std::uint8_t>((number >> 8U) ^ 0xA5U);
    }

    /** @brief session ID가 일치하는 periodic advertising을 찾습니다. */
    void startSession()
    {
        const Error result = bis.begin(Role::bis_receiver,
                                       reinterpret_cast<const std::uint8_t *>(sessionId));
        if (result != Error::none)
        {
            Serial.print("BIS start failed: ");
            Serial.println(static_cast<unsigned>(result));
            restart_ms = millis() + 1000U;
            return;
        }
        received = 0U;
        errors = 0U;
        session_ms = millis();
        running = true;
        closing = false;
        Serial.println("BIS receiver scanning");
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

/** @brief 받은 SDU 100개의 payload를 검증하고 sync를 반환합니다. */
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
    if (progress == Error::transport_failure && !closing)
    {
        Serial.print("BIS error: ");
        Serial.println(bis.nativeError());
        bis.stop();
        closing = true;
    }
    BisFrame frame = {};
    while (!closing && bis.readFrame(frame))
    {
        if (!validFrame(frame))
        {
            ++errors;
        }
        ++received;
    }
    if (!closing && received == 100U)
    {
        Serial.print("BIS received frames=");
        Serial.print(received);
        Serial.print(" errors=");
        Serial.println(errors);
        bis.stop();
        closing = true;
    }
    if (!closing && millis() - session_ms >= 15000U)
    {
        Serial.print("BIS receive timeout frames=");
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
