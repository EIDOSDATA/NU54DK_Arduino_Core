/**
 * @file AudioControlController.ino
 * @brief 원격 오디오 장치의 volume과 microphone 상태를 제어하는 예제입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE.h>
#include <NUCODE_BLE_Audio.h>
#include <NUCODE_BLE_Security.h>

using nucode::ble::BLEAddress;
using nucode::ble::BLEConnectionHandle;
using nucode::ble::BLEEvent;
using nucode::ble::BLEEventInfo;
using nucode::ble::BLELinkRole;
using nucode::ble::BLEScanResult;
using nucode::ble::BLEUuid;
using nucode::ble::SecurityConfig;
using nucode::ble::SecurityEvent;
using nucode::ble::SecurityEventRecord;
using nucode::ble::SecurityIoCapability;
using nucode::ble::SecurityLevel;
using nucode::ble::audio::AudioControlStage;
using nucode::ble::audio::AudioInputMode;
using nucode::ble::audio::Error;
using nucode::ble::audio::MicrophoneController;
using nucode::ble::audio::VolumeController;

namespace
{
    VolumeController volumeController;
    MicrophoneController microphoneController;
    BLEAddress peerAddress;
    BLEConnectionHandle peerConnection;
    bool peerFound = false;
    bool volumeStarted = false;
    bool microphoneStarted = false;
    bool scanPending = false;
    std::uint32_t scanAt = 0U;

    /** @brief Volume Control Service를 광고하는 장치를 검색합니다. */
    bool startScan()
    {
        return BLEScan.clearFilters() && BLEScan.filterServiceUuid(BLEUuid(0x1844U)) &&
               BLEScan.start(true);
    }

    /** @brief 처음 발견한 connectable 오디오 장치를 선택합니다. */
    void onScanResult(const BLEScanResult &result, void *context)
    {
        static_cast<void>(context);
        if (!peerFound && result.connectable)
        {
            peerAddress = result.address;
            peerFound = true;
            static_cast<void>(BLEScan.stop());
            Serial.println("Audio control device found");
        }
    }

    /** @brief 암호화된 연결에서 먼저 VCP discovery를 시작합니다. */
    void onSecurityEvent(const SecurityEventRecord &event, void *context)
    {
        static_cast<void>(context);
        if (event.event == SecurityEvent::pairing_requested)
        {
            static_cast<void>(BLESecurity.acceptPairing(event.connection, true));
        }
        else if (((event.event == SecurityEvent::paired) ||
                  (event.event == SecurityEvent::bond_verified) ||
                  (event.event == SecurityEvent::security_changed)) &&
                 (event.connection == peerConnection) && !volumeStarted)
        {
            const Error result = volumeController.begin(peerConnection);
            if (result == Error::none)
            {
                volumeStarted = true;
                Serial.println("Volume discovery started");
            }
            else
            {
                Serial.print("Volume discovery failed native=");
                Serial.println(volumeController.nativeCode());
            }
        }
    }

    /** @brief 연결 수명에 두 controller와 재검색을 결합합니다. */
    void onBleEvent(const BLEEventInfo &event, void *context)
    {
        static_cast<void>(context);
        if ((event.event == BLEEvent::connected) && (event.role == BLELinkRole::central))
        {
            peerConnection = event.connection;
            if (!BLESecurity.requestSecurity(peerConnection))
            {
                Serial.println("Audio control security request failed");
            }
        }
        else if ((event.event == BLEEvent::disconnected) && (event.connection == peerConnection))
        {
            if (microphoneStarted)
            {
                static_cast<void>(microphoneController.end());
            }
            if (volumeStarted)
            {
                static_cast<void>(volumeController.end());
            }
            microphoneStarted = false;
            volumeStarted = false;
            peerFound = false;
            peerConnection = BLEConnectionHandle();
            scanPending = true;
            scanAt = millis() + 100U;
            Serial.print("Audio control device disconnected reason=");
            Serial.println(event.reason);
        }
    }

    /** @brief 공개 API 요청 결과와 원본 profile 오류를 출력합니다. */
    void report(const char *operation, Error result, int nativeCode)
    {
        Serial.print(operation);
        Serial.print(" result=");
        Serial.print(static_cast<unsigned int>(result));
        Serial.print(" native=");
        Serial.println(nativeCode);
    }

    /** @brief 원격 volume·offset·두 input·microphone 상태를 출력합니다. */
    void printState()
    {
        const auto volume = volumeController.state();
        const auto output = volumeController.offsetState();
        const auto speakerInput = volumeController.inputState();
        const auto microphone = microphoneController.state();
        const auto microphoneInput = microphoneController.inputState();
        Serial.print("volume=");
        Serial.print(volume.volume);
        Serial.print(" muted=");
        Serial.print(volume.muted ? 1 : 0);
        Serial.print(" offset=");
        Serial.print(output.offset);
        Serial.print(" speaker_gain=");
        Serial.print(speakerInput.gain);
        Serial.print(" microphone_muted=");
        Serial.print(microphone.muted ? 1 : 0);
        Serial.print(" microphone_gain=");
        Serial.println(microphoneInput.gain);
    }
} // namespace

/** @brief BLE central, security와 오디오 장치 검색을 시작합니다. */
void setup()
{
    Serial.begin(115200);

    SecurityConfig security;
    security.minimum_level = SecurityLevel::encrypted;
    security.bonding = false;
    security.io_capability = SecurityIoCapability::no_input_output;
    BLESecurity.onEvent(onSecurityEvent);
    BLEDevice.onEventInfo(onBleEvent);
    BLEScan.onResult(onScanResult);
    if (!BLESecurity.begin(security) || !BLEDevice.begin("NU54-AUDIO-REMOTE") || !startScan())
    {
        Serial.println("Audio control controller start failed");
    }
}

/** @brief discovery와 사용자가 선택한 원격 상태 변경을 순서대로 진행합니다. */
void loop()
{
    BLEDevice.poll();
    BLESecurity.poll();
    volumeController.poll();
    microphoneController.poll();

    if (scanPending && !BLEConnection.connected() && !BLEConnection.connecting() &&
        (static_cast<std::int32_t>(millis() - scanAt) >= 0))
    {
        if (startScan())
        {
            scanPending = false;
        }
        else
        {
            scanAt = millis() + 1000U;
        }
    }
    if (peerFound && !BLEConnection.connected() && !BLEConnection.connecting())
    {
        peerFound = false;
        if (!BLEConnection.connect(peerAddress, peerConnection))
        {
            scanPending = true;
            scanAt = millis() + 1000U;
            Serial.println("Audio control connect failed");
        }
    }

    if (volumeStarted && volumeController.ready() && !microphoneStarted)
    {
        const Error result = microphoneController.begin(peerConnection);
        if (result == Error::none)
        {
            microphoneStarted = true;
            Serial.println("Microphone discovery started");
        }
        else if (result != Error::busy)
        {
            report("Microphone discovery", result, microphoneController.nativeCode());
        }
    }

    while (volumeController.ready() && microphoneController.ready() && (Serial.available() > 0))
    {
        const char command = static_cast<char>(Serial.read());
        if (command == '+')
        {
            report("Volume up", volumeController.volumeUp(), volumeController.nativeCode());
        }
        else if (command == '-')
        {
            report("Volume down", volumeController.volumeDown(), volumeController.nativeCode());
        }
        else if (command == 'm')
        {
            report("Volume mute", volumeController.mute(), volumeController.nativeCode());
        }
        else if (command == 'u')
        {
            report("Volume unmute", volumeController.unmute(), volumeController.nativeCode());
        }
        else if (command == 'o')
        {
            const std::int16_t next =
                static_cast<std::int16_t>(volumeController.offsetState().offset + 8);
            report("Output offset", volumeController.setOffset(next),
                   volumeController.nativeCode());
        }
        else if (command == 'g')
        {
            const std::int8_t next =
                static_cast<std::int8_t>(volumeController.inputState().gain + 1);
            report("Program input gain", volumeController.setInputGain(next),
                   volumeController.nativeCode());
        }
        else if (command == 'c')
        {
            report("Microphone mute", microphoneController.mute(),
                   microphoneController.nativeCode());
        }
        else if (command == 'v')
        {
            report("Microphone unmute", microphoneController.unmute(),
                   microphoneController.nativeCode());
        }
        else if (command == 'h')
        {
            const std::int8_t next =
                static_cast<std::int8_t>(microphoneController.inputState().gain + 1);
            report("Microphone input gain", microphoneController.setInputGain(next),
                   microphoneController.nativeCode());
        }
        else if (command == 'a')
        {
            report("Microphone automatic gain",
                   microphoneController.setInputMode(AudioInputMode::automatic),
                   microphoneController.nativeCode());
        }
        else if (command == 'r')
        {
            report("Read volume", volumeController.readVolume(), volumeController.nativeCode());
        }
        else if (command == 's')
        {
            printState();
        }
    }

    static std::uint32_t volumeUpdates = 0U;
    static std::uint32_t microphoneUpdates = 0U;
    if ((volumeUpdates != volumeController.stateUpdates()) ||
        (microphoneUpdates != microphoneController.stateUpdates()))
    {
        volumeUpdates = volumeController.stateUpdates();
        microphoneUpdates = microphoneController.stateUpdates();
        printState();
    }

    if ((volumeController.stage() == AudioControlStage::failed) ||
        (microphoneController.stage() == AudioControlStage::failed))
    {
        Serial.print("Audio control profile failed volume=");
        Serial.print(volumeController.nativeCode());
        Serial.print(" microphone=");
        Serial.println(microphoneController.nativeCode());
        delay(1000U);
    }
    delay(1U);
}
