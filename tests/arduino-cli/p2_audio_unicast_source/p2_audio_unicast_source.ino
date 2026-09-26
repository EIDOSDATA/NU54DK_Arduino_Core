/**
 * @file p2_audio_unicast_source.ino
 * @brief 합성 PCM→LC3→CIS 경로를 송신하며 P2 메모리를 계측합니다.
 */

#include <NUCODE_BLE.h>
#include <NUCODE_BLE_Audio.h>
#include <P2MemoryTelemetry.h>

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
    bool reportedFailure = false;
    bool stopRequested = false;
    bool disconnectRequested = false;
    bool finished = false;
    std::uint32_t sentAtStop = 0U;
    std::uint32_t lastFrameAt = 0U;
    std::uint16_t wavePosition = 0U;

    /** @brief 공개 예제처럼 ASCS 광고 peer를 찾습니다. */
    void onScanResult(const BLEScanResult &result, void *context)
    {
        static_cast<void>(context);
        if (!stopRequested && !peerFound && result.connectable)
        {
            peerAddress = result.address;
            peerFound = true;
            if (!BLEScan.stop())
            {
                Serial.println("P2_AUDIO_FAIL scan-stop");
            }
        }
    }

    /** @brief BLE 연결의 수명을 unicast client에 전달합니다. */
    void onBleEvent(const BLEEventInfo &event, void *context)
    {
        static_cast<void>(context);
        if ((event.event == BLEEvent::connected) && (event.role == BLELinkRole::central))
        {
            peer = event.connection;
            if (audioSource.begin(peer) != Error::none)
            {
                Serial.println("P2_AUDIO_FAIL client-begin");
                static_cast<void>(BLEConnection.disconnect(peer));
            }
        }
        else if ((event.event == BLEEvent::disconnected) && (event.connection == peer))
        {
            const Error result = audioSource.end();
            if ((result != Error::none) && (result != Error::not_started))
            {
                Serial.println("P2_AUDIO_FAIL client-end");
            }
            peer = BLEConnectionHandle();
            disconnectRequested = false;
            peerFound = false;
            restartScan = !stopRequested;
            announcedStreaming = false;
            reportedFailure = false;
        }
    }

    /** @brief 공개 예제와 같은 16 kHz bounded 삼각파를 생성합니다. */
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
}

/** @brief codec·BLE scan과 메모리 계측을 시작합니다. */
void setup()
{
    Serial.begin(115200);
    Serial.println("P2_READY role=audio-source");
    if (codec.begin() != Error::none)
    {
        Serial.println("P2_AUDIO_FAIL codec-begin");
        return;
    }
    BLEScan.onResult(onScanResult);
    BLEDevice.onEventInfo(onBleEvent);
    if (!BLEDevice.begin("NU54-AUDIO-SRC") || !BLEScan.clearFilters() ||
        !BLEScan.filterServiceUuid(BLEUuid(0x184EU)) || !BLEScan.start(true))
    {
        Serial.println("P2_AUDIO_FAIL scan-begin");
    }
    nucode::test::reportMemory("ready");
}

/** @brief LC3 frame을 10 ms 간격으로 전송하고 명시적으로 정리합니다. */
void loop()
{
    if (finished)
    {
        delay(10);
        return;
    }
    BLEDevice.poll();
    audioSource.poll();

    if (Serial.available() > 0 && Serial.read() == 's')
    {
        stopRequested = true;
        sentAtStop = audioSource.sentFrames();
        if (audioSource.stage() == UnicastClientStage::streaming &&
            audioSource.stop() != Error::none)
        {
            Serial.println("P2_AUDIO_FAIL stream-stop");
        }
    }
    if (peerFound && !stopRequested && !BLEConnection.connected() &&
        !BLEConnection.connecting())
    {
        peerFound = false;
        if (!BLEConnection.connect(peerAddress))
        {
            restartScan = true;
            Serial.println("P2_AUDIO_FAIL connect");
        }
    }
    if (restartScan && !stopRequested && !BLEConnection.connected() &&
        !BLEConnection.connecting())
    {
        restartScan = false;
        if (!BLEScan.running() && !BLEScan.start(true))
        {
            Serial.println("P2_AUDIO_FAIL scan-restart");
        }
    }

    const UnicastClientStage stage = audioSource.stage();
    if (stopRequested && stage == UnicastClientStage::released && peer.valid() &&
        !disconnectRequested)
    {
        if (!BLEConnection.disconnect(peer))
        {
            Serial.println("P2_AUDIO_FAIL disconnect");
        }
        else
        {
            disconnectRequested = true;
        }
    }
    if ((stage == UnicastClientStage::failed) && !reportedFailure)
    {
        reportedFailure = true;
        Serial.print("P2_AUDIO_FAIL stage=");
        Serial.print(static_cast<unsigned>(audioSource.failedAt()));
        Serial.print(" native=");
        Serial.println(audioSource.nativeCode());
    }
    if (stopRequested && !peer.valid())
    {
        codec.end();
        BLEDevice.end();
        nucode::test::reportMemory("stopped");
        Serial.print("P2_STOP role=audio-source sent=");
        Serial.println(sentAtStop);
        finished = true;
        return;
    }
    if (stage != UnicastClientStage::streaming || stopRequested)
    {
        delay(1);
        return;
    }
    if (!announcedStreaming)
    {
        announcedStreaming = true;
        lastFrameAt = millis();
        Serial.println("P2_AUDIO_STREAM role=source");
    }
    if (millis() - lastFrameAt < 10U)
    {
        delay(1);
        return;
    }
    lastFrameAt = millis();
    std::int16_t pcm[160] = {};
    std::uint8_t frame[40] = {};
    fillPcm(pcm);
    if (codec.encode(pcm, 160U, frame, sizeof(frame)) != Error::none)
    {
        Serial.println("P2_AUDIO_FAIL encode");
        return;
    }
    const Error sent = audioSource.sendFrame(frame);
    if ((sent != Error::none) && (sent != Error::busy))
    {
        Serial.println("P2_AUDIO_FAIL send");
    }
    const std::uint32_t count = audioSource.sentFrames();
    if ((sent == Error::none) && (count % 100U) == 0U)
    {
        Serial.print("P2_AUDIO_SENT frames=");
        Serial.println(count);
    }
}
