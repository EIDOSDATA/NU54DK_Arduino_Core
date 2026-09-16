/**
 * @file bis_encrypted_wrong_code.ino
 * @brief 잘못된 Broadcast Code로 MIC 거부와 사용자 SDU 비유출을 확인합니다.
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE_ISO.h>

using nucode::ble::iso::BisFrame;
using nucode::ble::iso::Error;
using nucode::ble::iso::RawBis;
using nucode::ble::iso::Role;

namespace
{
    constexpr char sessionId[] = "NUCODE-ENC-BIS01";
    constexpr char wrongCode[] = "MUCODE-BIS-CODE1";
    static_assert(sizeof(sessionId) == 17U, "session ID must be 16 bytes");
    static_assert(sizeof(wrongCode) == 17U, "broadcast code must be 16 bytes");

    RawBis receiver;
    std::uint16_t leaked = 0U;
    std::uint32_t started_ms = 0U;
    bool running = false;
    bool closing = false;
    bool finished = false;
}

/** @brief 공개 API로 정상 source와 다른 Broadcast Code를 선택합니다. */
void setup()
{
    Serial.begin(115200);
    Serial.print("BIS core revision=");
    Serial.println(RawBis::buildRevision());
    const Error result = receiver.begin(
        Role::bis_encrypted_receiver,
        reinterpret_cast<const std::uint8_t *>(sessionId),
        reinterpret_cast<const std::uint8_t *>(wrongCode));
    if (result != Error::none)
    {
        Serial.print("BIS wrong code begin failed: ");
        Serial.println(static_cast<unsigned>(result));
        finished = true;
        return;
    }
    started_ms = millis();
    running = true;
    Serial.println("BIS wrong code scanning");
}

/** @brief 잘못된 code에서 유효 SDU가 0개인지 확인하고 자원을 반환합니다. */
void loop()
{
    if (finished)
    {
        delay(10);
        return;
    }
    const Error progress = receiver.poll();
    BisFrame frame = {};
    while (receiver.readFrame(frame))
    {
        ++leaked;
    }
    if (running && !closing && progress == Error::transport_failure)
    {
        const int native = receiver.nativeError();
        if (native == -61 && leaked == 0U)
        {
            Serial.println("BIS wrong code rejected native=-61 leaked=0");
        }
        else
        {
            Serial.print("BIS wrong code failed native=");
            Serial.print(native);
            Serial.print(" leaked=");
            Serial.println(leaked);
        }
        receiver.stop();
        closing = true;
    }
    if (running && !closing && millis() - started_ms >= 12000U)
    {
        Serial.print("BIS wrong code timeout leaked=");
        Serial.println(leaked);
        receiver.stop();
        closing = true;
    }
    if (closing && receiver.stopped())
    {
        finished = true;
        Serial.println("BIS wrong code stopped");
    }
    delay(1);
}
