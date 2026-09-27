/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: Adaptive capabilities (experimental) (adaptive, 실험적 대안)
 * @par 보드와 역할
 * 2대 — 1) BapUnicastDuplexClient (client/controller); 2) BapUnicastDuplexServer (server/device)
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * nucode-build.json, prj.conf
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 추가 조건 없음
 * @par Metadata
 * identity `NUCODE_BLE_Audio/BapUnicastDuplexServer`, sha256 `59c829b558d6060925020e60d6ac1bb0ebbd2b7402881a10528b1dece5453d39`
 * @nucode_example_setup_end */

/**
 * @file BapUnicastDuplexServer.ino
 * @brief 한 CIS의 양방향 LC3 stream을 받아 복호화하고 합성 PCM을 보냅니다.
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
using nucode::ble::audio::UnicastServerMode;

namespace
{
    UnicastServer audioServer;
    Lc3Codec codec;
    bool restartAdvertising = false;
    std::uint32_t decodedFrames = 0U;
    std::uint32_t lastFrameAt = 0U;
    std::uint32_t lastReportedSent = 0U;
    std::uint16_t wavePosition = 0U;

    /** @brief 연결 해제 뒤 새 client를 위한 광고를 예약합니다. */
    void onBleEvent(const BLEEventInfo &event, void *context)
    {
        static_cast<void>(context);
        if (event.event == BLEEvent::disconnected)
        {
            restartAdvertising = true;
            Serial.println("LE Audio duplex peer disconnected");
        }
    }

    /** @brief 고정 16 kHz 삼각파 PCM frame을 만듭니다. */
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

    /** @brief 공개 API 오류와 원본 stack 코드를 출력합니다. */
    void printError(const char *step, Error error)
    {
        Serial.print("LE Audio duplex ");
        Serial.print(step);
        Serial.print(" failed: ");
        Serial.print(static_cast<unsigned int>(error));
        Serial.print(" native=");
        Serial.println(audioServer.nativeCode());
    }
} // namespace

/** @brief PACS/ASCS 양방향 역할과 LC3 codec을 준비하고 연결 가능 광고를 시작합니다. */
void setup()
{
    Serial.begin(115200);
    BLEDevice.onEventInfo(onBleEvent);
    if (!BLEDevice.begin("NU54-AUDIO-DPX"))
    {
        Serial.println("LE Audio Bluetooth start failed");
        return;
    }
    const Error serverResult = audioServer.begin(UnicastServerMode::duplex);
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

    /** @brief ASCS UUID와 일반 audio announcement를 광고합니다. */
    constexpr std::uint8_t announcement[] = {1U, 0x03U, 0x00U, 0x00U, 0x00U, 0U};
    if (!BLEAdvertising.clear() || !BLEAdvertising.setConnectable(true) ||
        !BLEAdvertising.addServiceUuid(BLEUuid(0x184EU)) ||
        !BLEAdvertising.setServiceData(BLEUuid(0x184EU), announcement, sizeof(announcement)) ||
        !BLEAdvertising.start())
    {
        Serial.println("LE Audio duplex advertising failed");
        return;
    }
    Serial.println("LE Audio duplex server advertising");
}

/** @brief 수신 frame을 복호화하고 10 ms마다 반대 방향 LC3 frame을 전송합니다. */
void loop()
{
    BLEDevice.poll();
    if (restartAdvertising && !BLEConnection.connected())
    {
        restartAdvertising = false;
        if (!BLEAdvertising.start())
        {
            Serial.println("LE Audio duplex advertising restart failed");
        }
    }

    std::uint8_t receivedFrame[40] = {};
    std::int16_t decodedPcm[160] = {};
    while (audioServer.readFrame(receivedFrame))
    {
        const Error result = codec.decode(receivedFrame, sizeof(receivedFrame), decodedPcm, 160U);
        if (result != Error::none)
        {
            printError("decode", result);
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
            Serial.println(audioServer.droppedFrames());
        }
    }

    const std::uint32_t now = millis();
    if (audioServer.sourceStreaming() && ((now - lastFrameAt) >= 10U))
    {
        lastFrameAt = now;
        std::int16_t pcm[160] = {};
        std::uint8_t frame[40] = {};
        fillPcm(pcm);
        const Error encoded = codec.encode(pcm, 160U, frame, sizeof(frame));
        if (encoded != Error::none)
        {
            printError("encode", encoded);
        }
        else
        {
            const Error sent = audioServer.sendFrame(frame);
            if ((sent != Error::none) && (sent != Error::busy) &&
                !((sent == Error::not_ready) && !audioServer.sourceStreaming()))
            {
                printError("send", sent);
            }
            const std::uint32_t sentFrames = audioServer.sentFrames();
            if ((sentFrames % 100U) == 0U && (sentFrames != lastReportedSent))
            {
                lastReportedSent = sentFrames;
                Serial.print("LE Audio duplex sent=");
                Serial.println(sentFrames);
            }
        }
    }
    delay(1);
}
