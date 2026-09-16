/**
 * @file CISPeripheral.ino
 * @brief CIS 사용자 SDU의 내용과 순서를 Arduino 코드에서 검사합니다.
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE_ISO.h>

using nucode::ble::iso::CisFrame;
using nucode::ble::iso::Error;
using nucode::ble::iso::RawCis;
using nucode::ble::iso::Role;

namespace
{
    /** @brief central 예제와 같은 16-byte 연결 식별자입니다. */
    constexpr char sessionId[] = "NUCODE-RAW-CIS01";
    static_assert(sizeof(sessionId) == 17U, "session ID must be 16 bytes");

    RawCis cis;
    std::uint16_t received = 0U;
    std::uint16_t errors = 0U;
    std::uint32_t restart_ms = 0U;
    bool running = false;
    bool saw_connection = false;
    bool closing = false;

    /** @brief Arduino 애플리케이션이 받은 payload·sequence를 검사합니다. */
    bool validFrame(const CisFrame &frame)
    {
        if (frame.length != 8U || frame.data[0] != 'N' || frame.data[1] != 'U' ||
            frame.data[6] != 0xC1U || frame.data[7] != 0x50U)
        {
            return false;
        }
        const std::uint16_t number = static_cast<std::uint16_t>(frame.data[2]) |
                                     (static_cast<std::uint16_t>(frame.data[3]) << 8U);
        return number == received &&
               frame.data[4] == static_cast<std::uint8_t>(number ^ 0x5AU) &&
               frame.data[5] == static_cast<std::uint8_t>((number >> 8U) ^ 0xA5U);
    }

    /** @brief 공개 ISO API로 다음 광고 세션을 시작합니다. */
    void startSession()
    {
        const Error result = cis.begin(Role::cis_peripheral,
                                       reinterpret_cast<const std::uint8_t *>(sessionId));
        if (result != Error::none)
        {
            Serial.print("CIS start failed: ");
            Serial.println(static_cast<unsigned>(result));
            restart_ms = millis() + 1000U;
            return;
        }
        received = 0U;
        errors = 0U;
        saw_connection = false;
        closing = false;
        running = true;
        Serial.println("CIS peripheral advertising");
    }
}

/** @brief Serial과 사용자 CIS 수신 세션을 시작합니다. */
void setup()
{
    Serial.begin(115200);
    Serial.print("CIS core revision=");
    Serial.println(RawCis::buildRevision());
    startSession();
}

/** @brief 받은 SDU를 처리하고 연결 해제 뒤 다음 세션을 준비합니다. */
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

    const Error progress = cis.poll();
    if (progress == Error::transport_failure && !closing)
    {
        Serial.print("CIS error: ");
        Serial.println(cis.nativeError());
        cis.stop();
        closing = true;
    }
    if (cis.connected())
    {
        saw_connection = true;
    }
    CisFrame frame = {};
    while (!closing && cis.readFrame(frame))
    {
        if (!validFrame(frame))
        {
            ++errors;
        }
        ++received;
    }
    if (!closing && saw_connection && !cis.connected())
    {
        Serial.print("CIS received frames=");
        Serial.print(received);
        Serial.print(" errors=");
        Serial.println(errors);
        cis.stop();
        closing = true;
    }
    if (closing && cis.stopped())
    {
        running = false;
        restart_ms = millis() + 1000U;
    }
    delay(1);
}
