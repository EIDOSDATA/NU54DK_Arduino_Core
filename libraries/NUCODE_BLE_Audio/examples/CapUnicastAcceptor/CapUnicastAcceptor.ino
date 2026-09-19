/**
 * @file CapUnicastAcceptor.ino
 * @brief CAP Acceptor의 unicast LC3 stream을 수신하고 PCM으로 복호화합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE.h>
#include <NUCODE_BLE_Audio.h>

using nucode::ble::BLEEvent;
using nucode::ble::BLEEventInfo;
using nucode::ble::BLEUuid;
using nucode::ble::audio::CapAcceptor;
using nucode::ble::audio::Error;
using nucode::ble::audio::Lc3Codec;
using nucode::ble::audio::UnicastServer;

namespace
{
    CapAcceptor acceptor;
    UnicastServer audioSink;
    Lc3Codec codec;
    bool restartAdvertising = false;
    std::uint32_t decodedFrames = 0U;

    /** @brief 연결 해제 뒤 다음 Initiator를 받을 광고를 예약합니다. */
    void onBleEvent(const BLEEventInfo &event, void *context)
    {
        static_cast<void>(context);
        if (event.event == BLEEvent::disconnected)
        {
            restartAdvertising = true;
            Serial.print("CAP Initiator disconnected reason=");
            Serial.println(event.reason);
        }
    }

    /** @brief PCM frame의 절대값 합으로 실제 decode 결과를 확인합니다. */
    std::uint32_t frameEnergy(const std::int16_t (&pcm)[160])
    {
        std::uint32_t energy = 0U;
        for (const std::int16_t sample : pcm)
        {
            const std::int32_t value = sample;
            energy += static_cast<std::uint32_t>((value < 0) ? -value : value);
        }
        return energy;
    }
} // namespace

/** @brief CAS와 PACS/ASCS sink, codec, 연결 가능 광고를 시작합니다. */
void setup()
{
    Serial.begin(115200);
    BLEDevice.onEventInfo(onBleEvent);
    if (!BLEDevice.begin("NU54-CAP-UNICAST-SINK") || (acceptor.begin() != Error::none) ||
        (audioSink.begin() != Error::none) || (codec.begin() != Error::none))
    {
        Serial.print("CAP Acceptor setup failed: ");
        Serial.println(audioSink.nativeCode());
        return;
    }

    constexpr std::uint8_t announcement[] = {1U, 0x03U, 0x00U, 0x00U, 0x00U, 0U};
    if (!BLEAdvertising.clear() || !BLEAdvertising.setConnectable(true) ||
        !BLEAdvertising.addServiceUuid(BLEUuid(0x1853U)) ||
        !BLEAdvertising.addServiceUuid(BLEUuid(0x184EU)) ||
        !BLEAdvertising.setServiceData(BLEUuid(0x184EU), announcement, sizeof(announcement)) ||
        !BLEAdvertising.start())
    {
        Serial.println("CAP Acceptor advertising failed");
        return;
    }
    Serial.println("CAP unicast Acceptor ready");
}

/** @brief 수신 LC3 frame을 공개 codec으로 복호화하고 통계를 출력합니다. */
void loop()
{
    BLEDevice.poll();
    if (restartAdvertising && !BLEConnection.connected())
    {
        restartAdvertising = false;
        if (!BLEAdvertising.start())
        {
            restartAdvertising = true;
            Serial.println("CAP Acceptor advertising restart failed");
        }
    }

    std::uint8_t frame[40] = {};
    while (audioSink.readFrame(frame))
    {
        std::int16_t pcm[160] = {};
        if (codec.decode(frame, sizeof(frame), pcm, 160U) != Error::none)
        {
            Serial.println("CAP decode failed");
            continue;
        }
        decodedFrames++;
        if ((decodedFrames % 100U) == 0U)
        {
            Serial.print("CAP decoded frames=");
            Serial.print(decodedFrames);
            Serial.print(" energy=");
            Serial.print(frameEnergy(pcm));
            Serial.print(" dropped=");
            Serial.println(audioSink.droppedFrames());
        }
    }
    delay(1U);
}
