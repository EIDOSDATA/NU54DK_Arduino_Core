/**
 * @file BapUnicastDuplexClient.ino
 * @brief 합성 PCM을 보내고 상대 LC3 frame을 복호화하는 양방향 client입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE.h>
#include <NUCODE_BLE_Audio.h>

using nucode::ble::BLEAddress;
using nucode::ble::BLEConnectionHandle;
using nucode::ble::BLEEvent;
using nucode::ble::BLEEventInfo;
using nucode::ble::BLELinkRole;
using nucode::ble::BLEScanResult;
using nucode::ble::BLEUuid;
using nucode::ble::audio::Error;
using nucode::ble::audio::Lc3Codec;
using nucode::ble::audio::UnicastClient;
using nucode::ble::audio::UnicastClientMode;
using nucode::ble::audio::UnicastClientStage;

namespace
{
    UnicastClient audioClient;
    Lc3Codec codec;
    BLEAddress peerAddress;
    BLEConnectionHandle peer;
    bool peerFound = false;
    bool restartScan = false;
    bool announcedStreaming = false;
    bool announcedStopped = false;
    bool reportedFailure = false;
    std::uint32_t lastFrameAt = 0U;
    std::uint32_t decodedFrames = 0U;
    std::uint16_t wavePosition = 0U;

    /** @brief ASCS UUID를 광고하는 첫 연결 가능한 sink를 선택합니다. */
    void onScanResult(const BLEScanResult &result, void *context)
    {
        static_cast<void>(context);
        if (!peerFound && result.connectable)
        {
            peerAddress = result.address;
            peerFound = true;
            Serial.println("LE Audio duplex server found");
            if (!BLEScan.stop())
            {
                Serial.println("LE Audio scan stop failed");
            }
        }
    }

    /** @brief 공개 BLE 연결의 수명을 unicast client에 전달합니다. */
    void onBleEvent(const BLEEventInfo &event, void *context)
    {
        static_cast<void>(context);
        if ((event.event == BLEEvent::connected) && (event.role == BLELinkRole::central))
        {
            peer = event.connection;
            announcedStopped = false;
            decodedFrames = 0U;
            const Error result = audioClient.begin(peer, UnicastClientMode::duplex);
            if (result == Error::none)
            {
                Serial.println("LE Audio connected; preparing");
            }
            else
            {
                Serial.print("LE Audio duplex client begin failed: ");
                Serial.println(audioClient.nativeCode());
                static_cast<void>(BLEConnection.disconnect(peer));
            }
        }
        else if ((event.event == BLEEvent::disconnected) && (event.connection == peer))
        {
            const Error result = audioClient.end();
            if ((result != Error::none) && (result != Error::not_started))
            {
                Serial.print("LE Audio client end failed: ");
                Serial.println(audioClient.nativeCode());
            }
            peer = BLEConnectionHandle();
            peerFound = false;
            restartScan = true;
            announcedStreaming = false;
            announcedStopped = false;
            reportedFailure = false;
            Serial.println("LE Audio peer disconnected");
        }
    }

    /** @brief 16 kHz의 bounded 삼각파 PCM frame 하나를 생성합니다. */
    void fillPcm(std::int16_t (&pcm)[160])
    {
        for (std::size_t index = 0U; index < 160U; index++)
        {
            const std::uint16_t phase = static_cast<std::uint16_t>((wavePosition + index) % 160U);
            const std::int32_t rising = (phase < 80U) ? phase : (160U - phase);
            pcm[index] = static_cast<std::int16_t>(rising * 300 - 12000);
        }
        wavePosition = static_cast<std::uint16_t>((wavePosition + 17U) % 160U);
    }
} // namespace

/** @brief codec와 공개 BLE 검색을 시작합니다. */
void setup()
{
    Serial.begin(115200);
    if (codec.begin() != Error::none)
    {
        Serial.println("LE Audio codec start failed");
        return;
    }
    BLEScan.onResult(onScanResult);
    BLEDevice.onEventInfo(onBleEvent);
    if (!BLEDevice.begin("NU54-AUDIO-DPX-C") || !BLEScan.clearFilters() ||
        !BLEScan.filterServiceUuid(BLEUuid(0x184EU)) || !BLEScan.start(true))
    {
        Serial.println("LE Audio scan start failed");
    }
}

/** @brief 양방향 ASE를 진행하며 수신 frame을 복호화하고 합성 LC3를 보냅니다. */
void loop()
{
    BLEDevice.poll();
    audioClient.poll();

    std::uint8_t receivedFrame[40] = {};
    std::int16_t decodedPcm[160] = {};
    while (audioClient.readFrame(receivedFrame))
    {
        const Error decoded = codec.decode(receivedFrame, sizeof(receivedFrame), decodedPcm,
                                           160U);
        if (decoded != Error::none)
        {
            Serial.println("LE Audio duplex decode failed");
            continue;
        }
        decodedFrames++;
        if ((decodedFrames % 100U) == 0U)
        {
            std::uint32_t energy = 0U;
            for (const std::int16_t sample : decodedPcm)
            {
                const std::int32_t value = sample;
                energy += static_cast<std::uint32_t>((value < 0) ? -value : value);
            }
            Serial.print("LE Audio duplex received=");
            Serial.print(decodedFrames);
            Serial.print(" energy=");
            Serial.print(energy);
            Serial.print(" dropped=");
            Serial.println(audioClient.droppedFrames());
        }
    }

    while (Serial.available() > 0)
    {
        if (Serial.read() == 's')
        {
            const Error result = audioClient.stop();
            if (result != Error::none)
            {
                Serial.print("LE Audio stop failed: ");
                Serial.print(static_cast<unsigned int>(result));
                Serial.print(" native=");
                Serial.println(audioClient.nativeCode());
            }
        }
    }

    if (peerFound && !BLEConnection.connected() && !BLEConnection.connecting())
    {
        peerFound = false;
        if (!BLEConnection.connect(peerAddress))
        {
            restartScan = true;
            Serial.println("LE Audio connect failed");
        }
    }
    if (restartScan && !BLEConnection.connected() && !BLEConnection.connecting())
    {
        restartScan = false;
        if (!BLEScan.running() && !BLEScan.start(true))
        {
            Serial.println("LE Audio scan restart failed");
        }
        else
        {
            Serial.println("LE Audio scan restarted");
        }
    }

    const UnicastClientStage stage = audioClient.stage();
    if ((stage == UnicastClientStage::released) && !announcedStopped)
    {
        announcedStopped = true;
        Serial.println("LE Audio stream stopped");
        if (!BLEConnection.disconnect(peer))
        {
            Serial.println("LE Audio disconnect failed");
        }
    }
    if ((stage == UnicastClientStage::failed) && !reportedFailure)
    {
        reportedFailure = true;
        Serial.print("LE Audio setup failed at stage=");
        Serial.print(static_cast<unsigned int>(audioClient.failedAt()));
        Serial.print(" error=");
        Serial.print(static_cast<unsigned int>(audioClient.lastError()));
        Serial.print(" step=");
        Serial.print(static_cast<unsigned int>(audioClient.lastStep()));
        Serial.print(" native=");
        Serial.println(audioClient.nativeCode());
        if (BLEConnection.connected(peer))
        {
            static_cast<void>(BLEConnection.disconnect(peer));
        }
    }
    if (stage != UnicastClientStage::streaming)
    {
        delay(1);
        return;
    }
    if (!announcedStreaming)
    {
        announcedStreaming = true;
        lastFrameAt = millis();
        Serial.println("LE Audio duplex client streaming");
    }
    const std::uint32_t now = millis();
    if ((now - lastFrameAt) < 10U)
    {
        delay(1);
        return;
    }
    lastFrameAt = now;

    std::int16_t pcm[160] = {};
    std::uint8_t frame[40] = {};
    fillPcm(pcm);
    const Error encoded = codec.encode(pcm, 160U, frame, sizeof(frame));
    if (encoded != Error::none)
    {
        Serial.println("LE Audio encode failed");
        return;
    }
    const Error sent = audioClient.sendFrame(frame);
    if ((sent != Error::none) && (sent != Error::busy))
    {
        Serial.print("LE Audio send failed: ");
        Serial.println(audioClient.nativeCode());
    }
    const std::uint32_t count = audioClient.sentFrames();
    if ((sent == Error::none) && (count % 100U) == 0U)
    {
        Serial.print("LE Audio duplex sent frames=");
        Serial.println(count);
    }
}
