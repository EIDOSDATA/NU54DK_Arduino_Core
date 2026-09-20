/**
 * @file CapInitiator.ino
 * @brief CAP Initiator로 합성 LC3 broadcast를 시작하고 갱신합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE.h>
#include <NUCODE_BLE_Audio.h>

using nucode::ble::audio::BroadcastCode;
using nucode::ble::audio::CapInitiator;
using nucode::ble::audio::Error;
using nucode::ble::audio::Lc3Codec;

namespace
{
    constexpr const char *broadcastName = "NU54-CAP-BROADCAST";
    constexpr BroadcastCode broadcastCode = {
        0x4e, 0x55, 0x35, 0x34, 0x2d, 0x43, 0x41, 0x50,
        0x2d, 0x43, 0x4f, 0x44, 0x45, 0x2d, 0x30, 0x31,
    };
    constexpr std::uint16_t mediaContext = 0x0004U;
    constexpr std::uint16_t conversationalContext = 0x0002U;
    CapInitiator initiator;
    Lc3Codec codec;
    std::uint32_t lastFrameAt = 0U;
    std::uint16_t wavePosition = 0U;
    bool announcedStreaming = false;
    bool useMediaContext = true;

    /** @brief 16 kHz의 bounded 삼각파 PCM frame 하나를 생성합니다. */
    void fillPcm(std::int16_t (&pcm)[160])
    {
        for (std::size_t index = 0U; index < 160U; index++)
        {
            const std::uint16_t phase =
                static_cast<std::uint16_t>((wavePosition + index) % 160U);
            const std::int32_t rising = (phase < 80U) ? phase : (160U - phase);
            pcm[index] = static_cast<std::int16_t>(rising * 300 - 12000);
        }
        wavePosition = static_cast<std::uint16_t>((wavePosition + 17U) % 160U);
    }

    /** @brief 공개 CAP API로 암호화 broadcast를 시작합니다. */
    bool startBroadcast()
    {
        const Error result = initiator.begin(broadcastName, broadcastCode);
        if (result != Error::none)
        {
            Serial.print("CAP initiator start failed: ");
            Serial.println(initiator.nativeCode());
            return false;
        }
        announcedStreaming = false;
        Serial.println("CAP initiator preparing");
        return true;
    }
} // namespace

/** @brief Bluetooth, LC3 codec과 CAP Initiator를 순서대로 시작합니다. */
void setup()
{
    Serial.begin(115200);
    if (!BLEDevice.begin("NU54-CAP-INITIATOR"))
    {
        Serial.println("Bluetooth start failed");
        return;
    }
    if (codec.begin() != Error::none)
    {
        Serial.println("LC3 codec start failed");
        return;
    }
    static_cast<void>(startBroadcast());
}

/** @brief LC3 frame 송신과 CAP update·stop·restart 명령을 처리합니다. */
void loop()
{
    BLEDevice.poll();

    while (Serial.available() > 0)
    {
        const char command = static_cast<char>(Serial.read());
        if (command == 's')
        {
            const Error result = initiator.end();
            Serial.print("CAP initiator stopped: ");
            Serial.println(static_cast<unsigned int>(result));
        }
        else if (command == 'r')
        {
            static_cast<void>(startBroadcast());
        }
        else if (command == 'u')
        {
            useMediaContext = !useMediaContext;
            const Error result = initiator.updateContext(
                useMediaContext ? mediaContext : conversationalContext);
            Serial.print("CAP metadata updated: ");
            Serial.println(static_cast<unsigned int>(result));
        }
        else if (command == 'x')
        {
            const Error result = initiator.updateContext(0U);
            Serial.print("CAP invalid metadata: ");
            Serial.println(static_cast<unsigned int>(result));
        }
    }

    if (!initiator.streaming())
    {
        delay(1U);
        return;
    }
    if (!announcedStreaming)
    {
        announcedStreaming = true;
        lastFrameAt = millis();
        Serial.println("CAP initiator streaming");
    }

    const std::uint32_t now = millis();
    if ((now - lastFrameAt) < 10U)
    {
        delay(1U);
        return;
    }
    lastFrameAt = now;

    std::int16_t pcm[160] = {};
    std::uint8_t frame[40] = {};
    fillPcm(pcm);
    if (codec.encode(pcm, 160U, frame, sizeof(frame)) != Error::none)
    {
        Serial.println("LC3 encode failed");
        return;
    }
    const Error sent = initiator.sendFrame(frame);
    if ((sent != Error::none) && (sent != Error::busy))
    {
        Serial.print("CAP send failed: ");
        Serial.println(initiator.nativeCode());
        return;
    }
    const std::uint32_t count = initiator.sentFrames();
    if ((sent == Error::none) && ((count % 100U) == 0U))
    {
        Serial.print("CAP sent frames=");
        Serial.println(count);
    }
}
