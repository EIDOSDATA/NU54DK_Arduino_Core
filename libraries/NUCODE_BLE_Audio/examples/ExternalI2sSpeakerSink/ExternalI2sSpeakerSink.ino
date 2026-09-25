/**
 * @file ExternalI2sSpeakerSink.ino
 * @brief 수신한 LC3 audio를 외부 I2S codec 또는 speaker로 재생합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE.h>
#include <NUCODE_BLE_Audio.h>
#include <NUCODE_Peripheral_Fabric.h>

using nucode::arduino::I2sBuffers;
using nucode::arduino::I2sChannels;
using nucode::arduino::I2sConfiguration;
using nucode::arduino::I2sEvent;
using nucode::arduino::I2sEventType;
using nucode::arduino::I2sFabric;
using nucode::arduino::I2sSampleWidth;
using nucode::arduino::StreamElectricalProfile;
using nucode::arduino::streamFabric;
using nucode::arduino::StreamFabricResult;
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
    constexpr std::size_t samplesPerFrame = 160U;
    alignas(4) std::uint32_t speakerBuffers[2][samplesPerFrame] = {};
    std::int16_t latestPcm[samplesPerFrame] = {};
    I2sFabric *speaker = nullptr;
    UnicastClient audioClient;
    Lc3Codec codec;
    BLEAddress peerAddress;
    BLEConnectionHandle peer;
    bool peerFound = false;
    bool restartScan = false;
    bool ready = false;

    /** @brief ASCS를 광고하는 첫 연결 가능한 audio source를 선택합니다. */
    void onScanResult(const BLEScanResult &result, void *context)
    {
        static_cast<void>(context);
        if (!peerFound && result.connectable)
        {
            peerAddress = result.address;
            peerFound = true;
            static_cast<void>(BLEScan.stop());
        }
    }

    /** @brief BLE 연결 수명을 unicast client에 전달합니다. */
    void onBleEvent(const BLEEventInfo &event, void *context)
    {
        static_cast<void>(context);
        if ((event.event == BLEEvent::connected) && (event.role == BLELinkRole::central))
        {
            peer = event.connection;
            ready = audioClient.begin(peer, UnicastClientMode::duplex) == Error::none;
        }
        else if ((event.event == BLEEvent::disconnected) && (event.connection == peer))
        {
            static_cast<void>(audioClient.end());
            peer = BLEConnectionHandle();
            peerFound = false;
            restartScan = true;
            ready = false;
        }
    }

    /** @brief mono PCM 한 frame을 16-bit stereo I2S word로 복제합니다. */
    void fillSpeakerBuffer(std::uint32_t *output)
    {
        for (std::size_t index = 0U; index < samplesPerFrame; index++)
        {
            const std::uint32_t sample = static_cast<std::uint16_t>(latestPcm[index]);
            output[index] = sample | (sample << 16U);
        }
    }
} // namespace

/** @brief BLE Audio client와 16 kHz I2S output DMA를 시작합니다. */
void setup()
{
    pinMode(LED_BUILTIN, OUTPUT);
    digitalWrite(LED_BUILTIN, LOW);
    BLEScan.onResult(onScanResult);
    BLEDevice.onEventInfo(onBleEvent);

    speaker = streamFabric().i2s(20U);
    const I2sConfiguration speakerConfiguration{PIN_P1_04,
                                                PIN_P1_05,
                                                0xFFU,
                                                PIN_P1_07,
                                                0xFFU,
                                                16000U,
                                                I2sSampleWidth::bits16,
                                                I2sChannels::stereo,
                                                true,
                                                StreamElectricalProfile::dap_uart_disabled};
    if ((speaker == nullptr) || (codec.begin() != Error::none) ||
        (speaker->configure(speakerConfiguration) != StreamFabricResult::success) ||
        (speaker->start({nullptr, speakerBuffers[0], samplesPerFrame}) !=
         StreamFabricResult::success) ||
        (speaker->queueBuffers({nullptr, speakerBuffers[1], samplesPerFrame}) !=
         StreamFabricResult::success) ||
        !BLEDevice.begin("NU54-I2S-AUDIO") || !BLEScan.clearFilters() ||
        !BLEScan.filterServiceUuid(BLEUuid(0x184EU)) || !BLEScan.start(true))
    {
        return;
    }
}

/** @brief 수신 LC3를 복호화하고 반환된 DMA buffer를 다음 I2S frame으로 채웁니다. */
void loop()
{
    BLEDevice.poll();
    audioClient.poll();

    std::uint8_t frame[40] = {};
    while (audioClient.readFrame(frame))
    {
        if (codec.decode(frame, sizeof(frame), latestPcm, samplesPerFrame) != Error::none)
        {
            ready = false;
        }
    }

    I2sEvent event{};
    while ((speaker != nullptr) && speaker->takeEvent(event))
    {
        if ((event.type == I2sEventType::buffers_complete) && (event.released.transmit != nullptr))
        {
            auto *const released = const_cast<std::uint32_t *>(event.released.transmit);
            fillSpeakerBuffer(released);
            if (speaker->queueBuffers({nullptr, released, samplesPerFrame}) !=
                StreamFabricResult::success)
            {
                ready = false;
            }
        }
        else if ((event.type == I2sEventType::underrun) || (event.type == I2sEventType::error))
        {
            ready = false;
        }
    }

    if (peerFound && !BLEConnection.connected() && !BLEConnection.connecting())
    {
        peerFound = false;
        if (!BLEConnection.connect(peerAddress))
        {
            restartScan = true;
        }
    }
    if (restartScan && !BLEConnection.connected() && !BLEConnection.connecting())
    {
        restartScan = false;
        if (!BLEScan.running())
        {
            static_cast<void>(BLEScan.start(true));
        }
    }

    const UnicastClientStage stage = audioClient.stage();
    if (stage == UnicastClientStage::failed)
    {
        ready = false;
        if (BLEConnection.connected(peer))
        {
            static_cast<void>(BLEConnection.disconnect(peer));
        }
    }
    else if (stage == UnicastClientStage::streaming)
    {
        ready = true;
    }
    digitalWrite(LED_BUILTIN, ready ? HIGH : LOW);
    delay(1U);
}
