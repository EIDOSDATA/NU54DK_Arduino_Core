/**
 * @file BISEncryptedReceiver.ino
 * @brief 암호화 BIS의 사용자 SDU와 순서를 Arduino 코드에서 검사합니다.
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
    constexpr char sessionId[] = "NUCODE-ENC-BIS01";
    static_assert(sizeof(sessionId) == 17U, "session ID must be 16 bytes");

    /** @brief source 예제의 Broadcast Code와 동일하게 설정합니다. */
    constexpr char broadcastCode[] = "NUCODE-BIS-CODE1";
    static_assert(sizeof(broadcastCode) == 17U, "broadcast code must be 16 bytes");

    RawBis bis;
    std::uint16_t received = 0U;
    std::uint16_t errors = 0U;
    std::uint16_t missing = 0U;
    std::uint16_t last_sequence = 0U;
    std::uint32_t session_ms = 0U;
    std::uint32_t restart_ms = 0U;
    bool running = false;
    bool closing = false;
    bool connection_reported = false;
    bool have_frame = false;

    /** @brief 수신 payload와 예상 sequence를 사용자 영역에서 검사합니다. */
    bool validFrame(const BisFrame &frame, std::uint16_t &number)
    {
        if (frame.length != 8U || frame.data[0] != 'B' || frame.data[1] != 'I' ||
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

    /** @brief 수신량·누락·오류를 한 session의 종료 결과로 표시합니다. */
    void reportSession()
    {
        if (have_frame)
        {
            missing += static_cast<std::uint16_t>(99U - last_sequence);
        }
        Serial.print("BIS received frames=");
        Serial.print(received);
        Serial.print(" missing=");
        Serial.print(missing);
        Serial.print(" errors=");
        Serial.println(errors);
        bis.stop();
        closing = true;
    }

    /** @brief session ID가 일치하는 periodic advertising을 찾습니다. */
    void startSession()
    {
        const Error result = bis.begin(Role::bis_encrypted_receiver,
                                       reinterpret_cast<const std::uint8_t *>(sessionId),
                                       reinterpret_cast<const std::uint8_t *>(broadcastCode));
        if (result != Error::none)
        {
            Serial.print("BIS start failed: ");
            Serial.println(static_cast<unsigned>(result));
            restart_ms = millis() + 1000U;
            return;
        }
        received = 0U;
        errors = 0U;
        missing = 0U;
        last_sequence = 0U;
        have_frame = false;
        session_ms = millis();
        running = true;
        closing = false;
        connection_reported = false;
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
    if (!connection_reported && bis.connected())
    {
        connection_reported = true;
        Serial.print("BIS receiver synchronized ms=");
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
        if (!have_frame)
        {
            Serial.print("BIS first frame=");
            Serial.println(number);
            missing = number;
            have_frame = true;
        }
        else if (number <= last_sequence)
        {
            ++errors;
            continue;
        }
        else
        {
            missing += static_cast<std::uint16_t>(number - last_sequence - 1U);
        }
        last_sequence = number;
        ++received;
    }
    if (!closing && received == 100U)
    {
        reportSession();
    }
    if (!closing && progress == Error::peer_stopped)
    {
        if (received >= 99U && missing + (99U - last_sequence) <= 1U &&
            errors == 0U)
        {
            reportSession();
        }
        else
        {
            Serial.print("BIS peer stopped before enough frames: ");
            Serial.print(received);
            Serial.print(" missing=");
            Serial.print(missing);
            Serial.print(" errors=");
            Serial.println(errors);
            bis.stop();
            closing = true;
        }
    }
    if (!closing && progress == Error::transport_failure)
    {
        Serial.print("BIS error: ");
        Serial.print(bis.nativeError());
        Serial.print(" frames=");
        Serial.print(received);
        Serial.print(" missing=");
        Serial.print(missing);
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
