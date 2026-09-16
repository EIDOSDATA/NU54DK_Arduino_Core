/**
 * @file CISCentral.ino
 * @brief 사용자 payload를 CIS로 보내고 세션을 반복합니다.
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE_ISO.h>

using nucode::ble::iso::Error;
using nucode::ble::iso::RawCis;
using nucode::ble::iso::Role;

namespace
{
    /** @brief 두 예제 보드가 공유하는 16-byte 연결 식별자입니다. */
    constexpr char sessionId[] = "NUCODE-RAW-CIS01";
    static_assert(sizeof(sessionId) == 17U, "session ID must be 16 bytes");

    RawCis cis;
    std::uint16_t sequence = 0U;
    std::uint32_t last_send_ms = 0U;
    std::uint32_t restart_ms = 0U;
    bool running = false;
    bool closing = false;

    /** @brief 사용자가 바꿀 수 있는 8-byte 데모 측정값을 만듭니다. */
    void makeFrame(std::uint16_t number, std::uint8_t payload[8])
    {
        payload[0] = 'N';
        payload[1] = 'U';
        payload[2] = static_cast<std::uint8_t>(number);
        payload[3] = static_cast<std::uint8_t>(number >> 8U);
        payload[4] = static_cast<std::uint8_t>(number ^ 0x5AU);
        payload[5] = static_cast<std::uint8_t>((number >> 8U) ^ 0xA5U);
        payload[6] = 0xC1U;
        payload[7] = 0x50U;
    }

    /** @brief 공개 ISO API로 새 연결을 시작합니다. */
    void startSession()
    {
        const Error result = cis.begin(Role::cis_central,
                                       reinterpret_cast<const std::uint8_t *>(sessionId));
        if (result != Error::none)
        {
            Serial.print("CIS start failed: ");
            Serial.println(static_cast<unsigned>(result));
            restart_ms = millis() + 1000U;
            return;
        }
        sequence = 0U;
        last_send_ms = millis();
        running = true;
        closing = false;
        Serial.println("CIS central scanning");
    }
}

/** @brief Serial과 사용자 CIS 세션을 시작합니다. */
void setup()
{
    Serial.begin(115200);
    startSession();
}

/** @brief 사용자가 만든 100개 SDU를 보내고 연결 자원을 반환합니다. */
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
    if (!closing && cis.connected() && sequence < 100U &&
        millis() - last_send_ms >= 20U)
    {
        std::uint8_t payload[8] = {};
        makeFrame(sequence, payload);
        const Error result = cis.sendFrame(payload, sizeof(payload));
        if (result == Error::none)
        {
            ++sequence;
            last_send_ms = millis();
        }
        else if (result != Error::busy && result != Error::not_ready)
        {
            Serial.print("CIS send failed: ");
            Serial.println(static_cast<unsigned>(result));
            cis.stop();
            closing = true;
        }
    }
    if (!closing && sequence == 100U && millis() - last_send_ms >= 500U)
    {
        Serial.print("CIS sent frames=");
        Serial.println(sequence);
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
