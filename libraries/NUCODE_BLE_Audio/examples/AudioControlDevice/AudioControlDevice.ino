/**
 * @file AudioControlDevice.ino
 * @brief volume과 microphone 제어 service를 제공하는 오디오 장치 예제입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE.h>
#include <NUCODE_BLE_Audio.h>
#include <NUCODE_BLE_Security.h>

using nucode::ble::BLEEvent;
using nucode::ble::BLEEventInfo;
using nucode::ble::BLEUuid;
using nucode::ble::SecurityConfig;
using nucode::ble::SecurityEvent;
using nucode::ble::SecurityEventRecord;
using nucode::ble::SecurityIoCapability;
using nucode::ble::SecurityLevel;
using nucode::ble::audio::AudioInputMode;
using nucode::ble::audio::AudioInputType;
using nucode::ble::audio::Error;
using nucode::ble::audio::MicrophoneDevice;
using nucode::ble::audio::MicrophoneDeviceConfig;
using nucode::ble::audio::VolumeRenderer;
using nucode::ble::audio::VolumeRendererConfig;

namespace
{
    VolumeRenderer renderer;
    MicrophoneDevice microphone;
    bool restartAdvertising = false;
    std::uint32_t restartAt = 0U;

    /** @brief Volume Control과 Microphone Control UUID를 함께 광고합니다. */
    bool startAdvertising()
    {
        return BLEAdvertising.clear() && BLEAdvertising.setConnectable(true) &&
               BLEAdvertising.addServiceUuid(BLEUuid(0x1844U)) &&
               BLEAdvertising.addServiceUuid(BLEUuid(0x184DU)) &&
               BLEAdvertising.setScanResponseName(true) && BLEAdvertising.start();
    }

    /** @brief Just Works pairing 요청을 승인합니다. */
    void onSecurityEvent(const SecurityEventRecord &event, void *context)
    {
        static_cast<void>(context);
        if (event.event == SecurityEvent::pairing_requested)
        {
            static_cast<void>(BLESecurity.acceptPairing(event.connection, true));
        }
    }

    /** @brief controller 연결 해제 뒤 광고 재시작을 예약합니다. */
    void onBleEvent(const BLEEventInfo &event, void *context)
    {
        static_cast<void>(context);
        if (event.event == BLEEvent::connected)
        {
            Serial.println("Audio controller connected");
        }
        else if (event.event == BLEEvent::disconnected)
        {
            restartAdvertising = true;
            restartAt = millis() + 100U;
            Serial.print("Audio controller disconnected reason=");
            Serial.println(event.reason);
        }
    }

    /** @brief 공개 API 요청 결과를 사람이 읽을 수 있게 출력합니다. */
    void report(const char *operation, Error result, int nativeCode)
    {
        Serial.print(operation);
        Serial.print(" result=");
        Serial.print(static_cast<unsigned int>(result));
        Serial.print(" native=");
        Serial.println(nativeCode);
    }

    /** @brief 두 service의 마지막 상태를 출력합니다. */
    void printState()
    {
        const auto volume = renderer.state();
        const auto output = renderer.offsetState();
        const auto speakerInput = renderer.inputState();
        const auto microphoneState = microphone.state();
        const auto microphoneInput = microphone.inputState();
        Serial.print("volume=");
        Serial.print(volume.volume);
        Serial.print(" muted=");
        Serial.print(volume.muted ? 1 : 0);
        Serial.print(" offset=");
        Serial.print(output.offset);
        Serial.print(" speaker_gain=");
        Serial.print(speakerInput.gain);
        Serial.print(" microphone_muted=");
        Serial.print(microphoneState.muted ? 1 : 0);
        Serial.print(" microphone_gain=");
        Serial.println(microphoneInput.gain);
    }
} // namespace

/** @brief security와 두 오디오 제어 service를 광고 전에 준비합니다. */
void setup()
{
    Serial.begin(115200);

    SecurityConfig security;
    security.minimum_level = SecurityLevel::encrypted;
    security.bonding = false;
    security.io_capability = SecurityIoCapability::no_input_output;
    BLESecurity.onEvent(onSecurityEvent);
    BLEDevice.onEventInfo(onBleEvent);

    VolumeRendererConfig volumeConfig;
    volumeConfig.volume = 100U;
    volumeConfig.step = 5U;
    volumeConfig.output.description = "Front speaker";
    volumeConfig.input.type = AudioInputType::streaming;
    volumeConfig.input.description = "Program input";

    MicrophoneDeviceConfig microphoneConfig;
    microphoneConfig.input.type = AudioInputType::microphone;
    microphoneConfig.input.description = "Main microphone";

    if (!BLESecurity.begin(security) || !BLEDevice.begin("NU54-AUDIO-CONTROL") ||
        (renderer.begin(volumeConfig) != Error::none) ||
        (microphone.begin(microphoneConfig) != Error::none) || !startAdvertising())
    {
        Serial.print("Audio control device start failed volume=");
        Serial.print(renderer.nativeCode());
        Serial.print(" microphone=");
        Serial.println(microphone.nativeCode());
        return;
    }
    Serial.println("Audio control device ready");
    printState();
}

/** @brief BLE event와 사용자가 선택한 local volume·microphone 변경을 처리합니다. */
void loop()
{
    BLEDevice.poll();
    BLESecurity.poll();

    if (restartAdvertising && !BLEAdvertising.running() &&
        (static_cast<std::int32_t>(millis() - restartAt) >= 0))
    {
        if (startAdvertising())
        {
            restartAdvertising = false;
            Serial.println("Audio control advertising restarted");
        }
        else
        {
            restartAt = millis() + 1000U;
        }
    }

    while (Serial.available() > 0)
    {
        const char command = static_cast<char>(Serial.read());
        if (command == '+')
        {
            report("Volume up", renderer.volumeUp(), renderer.nativeCode());
        }
        else if (command == '-')
        {
            report("Volume down", renderer.volumeDown(), renderer.nativeCode());
        }
        else if (command == 'm')
        {
            report("Volume mute", renderer.mute(), renderer.nativeCode());
        }
        else if (command == 'u')
        {
            report("Volume unmute", renderer.unmute(), renderer.nativeCode());
        }
        else if (command == 'o')
        {
            const std::int16_t next = static_cast<std::int16_t>(renderer.offsetState().offset + 8);
            report("Output offset", renderer.setOffset(next), renderer.nativeCode());
        }
        else if (command == 'i')
        {
            const std::int8_t next = static_cast<std::int8_t>(renderer.inputState().gain + 1);
            report("Program input gain", renderer.setInputGain(next), renderer.nativeCode());
        }
        else if (command == 'c')
        {
            report("Microphone mute", microphone.mute(), microphone.nativeCode());
        }
        else if (command == 'v')
        {
            report("Microphone unmute", microphone.unmute(), microphone.nativeCode());
        }
        else if (command == 'g')
        {
            const std::int8_t next = static_cast<std::int8_t>(microphone.inputState().gain + 1);
            report("Microphone input gain", microphone.setInputGain(next), microphone.nativeCode());
        }
        else if (command == 'a')
        {
            report("Microphone automatic gain", microphone.setInputMode(AudioInputMode::automatic),
                   microphone.nativeCode());
        }
        else if (command == 's')
        {
            printState();
        }
    }

    static std::uint32_t volumeUpdates = 0U;
    static std::uint32_t microphoneUpdates = 0U;
    if ((volumeUpdates != renderer.stateUpdates()) ||
        (microphoneUpdates != microphone.stateUpdates()))
    {
        volumeUpdates = renderer.stateUpdates();
        microphoneUpdates = microphone.stateUpdates();
        printState();
    }
    delay(1U);
}
