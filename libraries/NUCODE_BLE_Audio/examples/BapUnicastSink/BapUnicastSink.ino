/**
 * @file BapUnicastSink.ino
 * @brief LE Audio unicast LC3 frame을 수신하여 합성 PCM을 복호화합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE.h>
#include <NUCODE_BLE_Audio.h>

using nucode::ble::BLEEvent;
using nucode::ble::BLEEventInfo;
using nucode::ble::BLEUuid;
using nucode::ble::audio::Error;
using nucode::ble::audio::Lc3Codec;
using nucode::ble::audio::UnicastServer;

namespace
{
    UnicastServer audioSink;
    Lc3Codec codec;
    bool restartAdvertising = false;
    std::uint32_t decodedFrames = 0U;

    /** @brief 연결 해제 시 다음 unicast client를 받을 광고를 예약합니다. */
    void onBleEvent(const BLEEventInfo &event, void *context)
    {
        static_cast<void>(context);
        if (event.event == BLEEvent::disconnected)
        {
            restartAdvertising = true;
            Serial.println("LE Audio peer disconnected");
        }
    }

    /** @brief 공개 API 오류를 사용자에게 알려 줍니다. */
    void printError(const char *step, Error error)
    {
        Serial.print("LE Audio ");
        Serial.print(step);
        Serial.print(" failed: ");
        Serial.print(static_cast<unsigned int>(error));
        Serial.print(" native=");
        Serial.println(audioSink.nativeCode());
    }
} // namespace

/** @brief PACS/ASCS sink와 LC3 codec을 시작하고 연결 가능 광고를 냅니다. */
void setup()
{
    Serial.begin(115200);
    BLEDevice.onEventInfo(onBleEvent);
    if (!BLEDevice.begin("NU54-AUDIO-SNK"))
    {
        Serial.println("LE Audio Bluetooth start failed");
        return;
    }
    const Error serverResult = audioSink.begin();
    if (serverResult != Error::none)
    {
        printError("server", serverResult);
        return;
    }
    const Error codecResult = codec.begin();
    if (codecResult != Error::none)
    {
        printError("codec", codecResult);
        return;
    }

    /** @brief ASCS UUID 0x184E 뒤에 대상 announcement와 context를 넣습니다. */
    constexpr std::uint8_t announcement[] = {1U, 0x03U, 0x00U, 0x00U, 0x00U, 0U};
    if (!BLEAdvertising.clear() || !BLEAdvertising.setConnectable(true) ||
        !BLEAdvertising.addServiceUuid(BLEUuid(0x184EU)) ||
        !BLEAdvertising.setServiceData(BLEUuid(0x184EU), announcement, sizeof(announcement)) ||
        !BLEAdvertising.start())
    {
        Serial.println("LE Audio advertising failed");
        return;
    }
    Serial.println("LE Audio sink advertising");
}

/** @brief 수신 LC3 frame을 공개 codec으로 복호화하고 수신 통계를 출력합니다. */
void loop()
{
    BLEDevice.poll();
    if (restartAdvertising && !BLEConnection.connected())
    {
        restartAdvertising = false;
        if (!BLEAdvertising.start())
        {
            Serial.println("LE Audio advertising restart failed");
        }
    }

    std::uint8_t frame[40] = {};
    std::int16_t pcm[160] = {};
    while (audioSink.readFrame(frame))
    {
        const Error result = codec.decode(frame, sizeof(frame), pcm, 160U);
        if (result != Error::none)
        {
            printError("decode", result);
            continue;
        }
        decodedFrames++;
        if ((decodedFrames % 100U) == 0U)
        {
            std::uint32_t energy = 0U;
            for (const std::int16_t sample : pcm)
            {
                const std::int32_t value = sample;
                energy += static_cast<std::uint32_t>((value < 0) ? -value : value);
            }
            Serial.print("LE Audio decoded frames=");
            Serial.print(decodedFrames);
            Serial.print(" energy=");
            Serial.print(energy);
            Serial.print(" dropped=");
            Serial.println(audioSink.droppedFrames());
        }
    }
    delay(1);
}
