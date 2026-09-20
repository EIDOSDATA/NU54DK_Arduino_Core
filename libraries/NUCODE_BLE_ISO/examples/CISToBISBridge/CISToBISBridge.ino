/**
 * @file CISToBISBridge.ino
 * @brief CIS 사용자 SDU를 읽어 같은 payload를 BIS로 전달합니다.
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE_ISO.h>

using nucode::ble::iso::CisFrame;
using nucode::ble::iso::Error;
using nucode::ble::iso::RawBis;
using nucode::ble::iso::RawCis;
using nucode::ble::iso::Role;

namespace
{
    /** @brief peer 및 receiver와 각각 공유하는 16-byte 식별자입니다. */
    constexpr char cisSessionId[] = "NUCODE-C2B-CIS01";
    constexpr char bisSessionId[] = "NUCODE-C2B-BIS01";
    static_assert(sizeof(cisSessionId) == 17U, "CIS session ID must be 16 bytes");
    static_assert(sizeof(bisSessionId) == 17U, "BIS session ID must be 16 bytes");

    RawCis cis;
    RawBis bis;
    CisFrame pendingFrame = {};
    std::uint16_t cisReceived = 0U;
    std::uint16_t bisForwarded = 0U;
    std::uint16_t errors = 0U;
    std::uint32_t sessionMs = 0U;
    std::uint32_t lastForwardMs = 0U;
    std::uint32_t restartMs = 0U;
    bool running = false;
    bool bisStarted = false;
    bool framePending = false;
    bool closing = false;

    /** @brief CIS payload의 사용자 sequence와 검사 byte를 확인합니다. */
    bool validFrame(const CisFrame &frame, std::uint16_t &number)
    {
        if (frame.length != 8U || frame.data[0] != 'C' || frame.data[1] != 'B' ||
            frame.data[6] != 0xC1U || frame.data[7] != 0x52U)
        {
            return false;
        }
        number = static_cast<std::uint16_t>(frame.data[2]) |
                 (static_cast<std::uint16_t>(frame.data[3]) << 8U);
        return number < 100U &&
               frame.data[4] == static_cast<std::uint8_t>(number ^ 0x5AU) &&
               frame.data[5] == static_cast<std::uint8_t>((number >> 8U) ^ 0xA5U);
    }

    /** @brief 두 공개 API가 소유한 무선 자원의 해제를 시작합니다. */
    void stopSession()
    {
        if (bisStarted && !bis.stopped())
        {
            bis.stop();
        }
        if (!cis.stopped())
        {
            cis.stop();
        }
        closing = true;
    }

    /** @brief 같은 session의 CIS를 먼저 연결합니다. */
    void startSession()
    {
        const Error result = cis.begin(Role::cis_to_bis_bridge,
                                       reinterpret_cast<const std::uint8_t *>(cisSessionId));
        if (result != Error::none)
        {
            Serial.print("CIS bridge start failed: ");
            Serial.println(static_cast<unsigned>(result));
            restartMs = millis() + 1000U;
            return;
        }
        cisReceived = 0U;
        bisForwarded = 0U;
        errors = 0U;
        sessionMs = millis();
        lastForwardMs = 0U;
        bisStarted = false;
        framePending = false;
        running = true;
        closing = false;
        Serial.println("CIS bridge scanning");
    }
}

/** @brief 공개 API가 포함된 Core revision을 표시합니다. */
void setup()
{
    Serial.begin(115200);
    Serial.print("CIS bridge core revision=");
    Serial.println(RawCis::buildRevision());
    startSession();
}

/** @brief 한 CIS의 100개 사용자 SDU를 BIS에 그대로 전달합니다. */
void loop()
{
    if (!running)
    {
        if (static_cast<std::int32_t>(millis() - restartMs) >= 0)
        {
            startSession();
        }
        delay(1);
        return;
    }

    const Error cisProgress = cis.poll();
    if (!closing && cisProgress == Error::transport_failure)
    {
        Serial.print("CIS bridge receive error: ");
        Serial.println(cis.nativeError());
        stopSession();
    }
    if (!closing && !bisStarted && cis.connected())
    {
        const Error result = bis.begin(Role::cis_to_bis_bridge,
                                       reinterpret_cast<const std::uint8_t *>(bisSessionId));
        if (result != Error::none)
        {
            Serial.print("CIS bridge broadcast start failed: ");
            Serial.println(static_cast<unsigned>(result));
            stopSession();
        }
        else
        {
            bisStarted = true;
            Serial.println("CIS bridge broadcasting");
        }
    }
    if (bisStarted)
    {
        const Error bisProgress = bis.poll();
        if (!closing && bisProgress == Error::transport_failure)
        {
            Serial.print("CIS bridge broadcast error: ");
            Serial.println(bis.nativeError());
            stopSession();
        }
    }
    if (!closing && bisStarted && bis.connected() && !framePending &&
        cisReceived < 100U && cis.readFrame(pendingFrame))
    {
        std::uint16_t number = 0U;
        if (!validFrame(pendingFrame, number) || number != cisReceived)
        {
            ++errors;
            Serial.print("CIS bridge invalid frame: ");
            Serial.println(number);
            stopSession();
        }
        else
        {
            ++cisReceived;
            framePending = true;
        }
    }
    if (!closing && framePending)
    {
        const Error result = bis.sendFrame(pendingFrame.data, pendingFrame.length);
        if (result == Error::none)
        {
            ++bisForwarded;
            framePending = false;
            lastForwardMs = millis();
        }
        else if (result != Error::busy && result != Error::not_ready)
        {
            Serial.print("CIS bridge forward failed: ");
            Serial.println(static_cast<unsigned>(result));
            stopSession();
        }
    }
    if (!closing && bisForwarded == 100U && millis() - lastForwardMs >= 750U)
    {
        Serial.print("CIS bridge received=");
        Serial.print(cisReceived);
        Serial.print(" forwarded=");
        Serial.print(bisForwarded);
        Serial.print(" errors=");
        Serial.println(errors);
        stopSession();
    }
    if (!closing && millis() - sessionMs >= 15000U)
    {
        Serial.print("CIS bridge timeout received=");
        Serial.print(cisReceived);
        Serial.print(" forwarded=");
        Serial.println(bisForwarded);
        stopSession();
    }
    if (closing && cis.stopped() && (!bisStarted || bis.stopped()))
    {
        Serial.println("CIS bridge stopped");
        running = false;
        restartMs = millis() + 1000U;
    }
    delay(1);
}
