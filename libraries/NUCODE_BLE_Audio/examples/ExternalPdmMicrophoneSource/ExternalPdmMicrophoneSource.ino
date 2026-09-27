/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE Audio external I/O (DAP UART disconnected) (`ble_audio_io`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 2대 — 1) ExternalPdmMicrophoneSource (source/transmitter); 2) ExternalI2sSpeakerSink (sink/receiver)
 * @par Serial Monitor
 * 사용하지 않음
 * @par 필수 sidecar
 * prj.conf
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * DAP UART를 분리하고 PDM 또는 I2S 외장 장치의 전압·clock·GND 결선을 확인합니다.
 * @par Metadata
 * identity `NUCODE_BLE_Audio/ExternalPdmMicrophoneSource`, sha256 `e8a0acabea4b151ee9afe53aa5dcf37824a13d6209b82b6523b6653c565eabb0`
 * @nucode_example_setup_end */

/**
 * @file ExternalPdmMicrophoneSource.ino
 * @brief 외부 PDM microphone의 PCM을 LC3 unicast source로 전송합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE.h>
#include <NUCODE_BLE_Audio.h>
#include <NUCODE_Peripheral_Fabric.h>

using nucode::arduino::PdmConfiguration;
using nucode::arduino::PdmEvent;
using nucode::arduino::PdmEventType;
using nucode::arduino::PdmFabric;
using nucode::arduino::StreamElectricalProfile;
using nucode::arduino::streamFabric;
using nucode::arduino::StreamFabricResult;
using nucode::ble::BLEEvent;
using nucode::ble::BLEEventInfo;
using nucode::ble::BLEUuid;
using nucode::ble::audio::Error;
using nucode::ble::audio::Lc3Codec;
using nucode::ble::audio::UnicastServer;
using nucode::ble::audio::UnicastServerMode;

namespace
{
    constexpr std::size_t samplesPerFrame = 160U;
    alignas(4) std::int16_t microphoneBuffers[2][samplesPerFrame] = {};
    PdmFabric *microphone = nullptr;
    UnicastServer audioServer;
    Lc3Codec codec;
    bool restartAdvertising = false;
    bool ready = false;

    /** @brief peer가 끊기면 같은 audio source 광고를 다시 시작합니다. */
    void onBleEvent(const BLEEventInfo &event, void *context)
    {
        static_cast<void>(context);
        if (event.event == BLEEvent::disconnected)
        {
            restartAdvertising = true;
        }
    }

    /** @brief PDM frame을 LC3로 압축해 활성 source ASE로 보냅니다. */
    void sendMicrophoneFrame(const std::int16_t *samples)
    {
        if (!audioServer.sourceStreaming())
        {
            return;
        }
        std::uint8_t frame[40] = {};
        if (codec.encode(samples, samplesPerFrame, frame, sizeof(frame)) == Error::none)
        {
            const Error sent = audioServer.sendFrame(frame);
            if ((sent != Error::none) && (sent != Error::busy))
            {
                ready = false;
            }
        }
    }
} // namespace

/** @brief BLE Audio source와 16 kHz PDM microphone의 연속 DMA capture를 시작합니다. */
void setup()
{
    pinMode(LED_BUILTIN, OUTPUT);
    digitalWrite(LED_BUILTIN, LOW);
    BLEDevice.onEventInfo(onBleEvent);

    microphone = streamFabric().pdm(20U);
    const PdmConfiguration microphoneConfiguration{
        PIN_P1_04, PIN_P1_06, 16000U, false, false, StreamElectricalProfile::dap_uart_disabled};
    if ((microphone == nullptr) || !BLEDevice.begin("NU54-PDM-AUDIO") ||
        (audioServer.begin(UnicastServerMode::duplex) != Error::none) ||
        (codec.begin() != Error::none) ||
        (microphone->configure(microphoneConfiguration) != StreamFabricResult::success) ||
        (microphone->start(microphoneBuffers[0], samplesPerFrame) != StreamFabricResult::success) ||
        (microphone->queueBuffer(microphoneBuffers[1], samplesPerFrame) !=
         StreamFabricResult::success))
    {
        return;
    }

    constexpr std::uint8_t announcement[] = {1U, 0x03U, 0x00U, 0x00U, 0x00U, 0U};
    if (!BLEAdvertising.clear() || !BLEAdvertising.setConnectable(true) ||
        !BLEAdvertising.addServiceUuid(BLEUuid(0x184EU)) ||
        !BLEAdvertising.setServiceData(BLEUuid(0x184EU), announcement, sizeof(announcement)) ||
        !BLEAdvertising.start())
    {
        return;
    }
    ready = true;
}

/** @brief 완료된 PDM buffer를 전송하고 즉시 다음 DMA 구간으로 반환합니다. */
void loop()
{
    BLEDevice.poll();
    if (restartAdvertising && !BLEConnection.connected())
    {
        restartAdvertising = false;
        ready = BLEAdvertising.start();
    }

    PdmEvent event{};
    while ((microphone != nullptr) && microphone->takeEvent(event))
    {
        if ((event.type == PdmEventType::buffer_complete) && (event.samples == samplesPerFrame) &&
            (event.buffer != nullptr))
        {
            sendMicrophoneFrame(event.buffer);
            if (microphone->queueBuffer(event.buffer, event.samples) != StreamFabricResult::success)
            {
                ready = false;
            }
        }
        else if ((event.type == PdmEventType::overflow) || (event.type == PdmEventType::error))
        {
            ready = false;
        }
    }

    digitalWrite(LED_BUILTIN, ready && audioServer.sourceStreaming() ? HIGH : LOW);
    delay(1U);
}
