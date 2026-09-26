/**
 * @file BapUnicastSource.ino
 * @brief 합성 PCM을 LC3로 encode해 LE Audio unicast sink로 보냅니다.
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
using nucode::ble::audio::UnicastClientStage;

namespace
{
    UnicastClient audioSource;
    Lc3Codec codec;
    BLEAddress peerAddress;
    BLEConnectionHandle peer;
    bool peerFound = false;
    bool restartScan = false;
    bool announcedStreaming = false;
    bool announcedStopped = false;
    bool reportedFailure = false;
    std::uint32_t lastFrameAt = 0U;
    std::uint16_t wavePosition = 0U;

    /** @brief ASCS UUID를 광고하는 첫 연결 가능한 sink를 선택합니다. */
    void onScanResult(const BLEScanResult &result, void *context)
    {
        static_cast<void>(context);
        if (!peerFound && result.connectable)
        {
            peerAddress = result.address;
            peerFound = true;
            Serial.println("LE Audio sink found");
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
            const Error result = audioSource.begin(peer);
            if (result == Error::none)
            {
                Serial.println("LE Audio connected; preparing");
            }
            else
            {
                Serial.print("LE Audio client begin failed: ");
                Serial.println(audioSource.nativeCode());
                static_cast<void>(BLEConnection.disconnect(peer));
            }
        }
        else if ((event.event == BLEEvent::disconnected) && (event.connection == peer))
        {
            const Error result = audioSource.end();
            if ((result != Error::none) && (result != Error::not_started))
            {
                Serial.print("LE Audio client end failed: ");
                Serial.println(audioSource.nativeCode());
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
    if (!BLEDevice.begin("NU54-AUDIO-SRC") || !BLEScan.clearFilters() ||
        !BLEScan.filterServiceUuid(BLEUuid(0x184EU)) || !BLEScan.start(true))
    {
        Serial.println("LE Audio scan start failed");
    }
}

/** @brief PACS/ASCS 단계를 진행하고 합성 LC3 frame을 10 ms 간격으로 보냅니다. */
void loop()
{
    BLEDevice.poll();
    audioSource.poll();

    while (Serial.available() > 0)
    {
        if (Serial.read() == 's')
        {
            const Error result = audioSource.stop();
            if (result != Error::none)
            {
                Serial.print("LE Audio stop failed: ");
                Serial.print(static_cast<unsigned int>(result));
                Serial.print(" native=");
                Serial.println(audioSource.nativeCode());
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

    const UnicastClientStage stage = audioSource.stage();
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
        Serial.print(static_cast<unsigned int>(audioSource.failedAt()));
        Serial.print(" error=");
        Serial.print(static_cast<unsigned int>(audioSource.lastError()));
        Serial.print(" step=");
        Serial.print(static_cast<unsigned int>(audioSource.lastStep()));
        Serial.print(" native=");
        Serial.println(audioSource.nativeCode());
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
        Serial.println("LE Audio source streaming");
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
    const Error sent = audioSource.sendFrame(frame);
    if ((sent != Error::none) && (sent != Error::busy))
    {
        Serial.print("LE Audio send failed: ");
        Serial.println(audioSource.nativeCode());
    }
    const std::uint32_t count = audioSource.sentFrames();
    if ((sent == Error::none) && (count % 100U) == 0U)
    {
        Serial.print("LE Audio sent frames=");
        Serial.println(count);
    }
}
