/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par 목적
 * volume과 microphone 제어 service를 제공하는 오디오 장치 예제입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: Adaptive capabilities (experimental) (adaptive, 실험적 대안)
 * @par 보드와 역할
 * 2대 — 1) AudioControlController (controller); 2) AudioControlDevice (device)
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * nucode-build.json, prj.conf
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 추가 조건 없음
 * @par 준비물
 * - NU54DK 보드 2대 — 1) AudioControlController (controller); 2) AudioControlDevice (device)
 * @par 설정
 * - Tools → Feature set에서 `ble` profile을 선택합니다.
 * - Sketch 폴더의 sidecar를 함께 설치합니다: nucode-build.json, prj.conf
 * - Serial Monitor는 115200 baud로 엽니다.
 * @par 실행 순서
 * - 권장 profile로 현재 Sketch와 metadata에 적힌 각 peer 역할 Sketch를 빌드합니다.
 * - probe가 여러 대이면 `NUCODE_PROBE_UID`를 지정하고 Arduino Upload로 역할별 보드를 구분합니다.
 * - peer·외장 조건을 먼저 준비한 뒤 reset 또는 예제에 명시된 입력으로 실행합니다.
 * @par 성공 출력
 * - Serial 문구 `Audio controller connected`를 포함한 정상 상태 전이를 확인합니다.
 * - Serial 문구 `Audio controller disconnected reason=`를 포함한 정상 상태 전이를 확인합니다.
 * - Serial 문구 `result=`를 포함한 정상 상태 전이를 확인합니다.
 * @par 흔한 오류
 * - 권장 profile과 sidecar가 다르면 기능·Kconfig가 빠질 수 있으므로 먼저 설정을 다시 확인합니다.
 * - 여러 probe가 연결된 상태에서 UID를 생략하면 다른 보드에 upload될 수 있습니다.
 * - `Audio control device start failed volume=` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * @par 다음 예제
 * - `NUCODE_BLE_Audio/BapBroadcastAssistant`
 * - `NUCODE_BLE_Audio/BapBroadcastDelegatorSink`
 * @par 종료와 재시작
 * - 예제의 stop/end/disconnect 또는 유한 완료 흐름 뒤 오류와 자원 반환을 확인합니다.
 * - 실패 문구와 driver 상태를 확인한 뒤 명시적 reset 또는 예제의 재시작 흐름을 사용합니다.
 * @par 보안
 * - wireless_example_no_implicit_security_claim
 * - 무선 연결 성공만으로 인증·암호화·상호운용 보안을 주장하지 않습니다.
 * @par 제한
 * - Compile·Host 검사는 실제 보드 runtime 또는 외부 제품 상호운용 PASS를 대신하지 않습니다.
 * - 목적과 metadata 조건 밖의 성능·동시성·정밀도는 이 예제의 보증 범위가 아닙니다.
 * @par Negative
 * - wrong_profile_or_missing_sidecar
 * - missing_or_wrong_role_peer
 * - startup_or_runtime_error_reported
 * @par Traceability
 * Recipe `ble_audio`; 내부 증거 ID는 metadata에서 관리합니다.
 * 직접 upstream 복사 아님; NCS `99553055607b2e9885fbc80ccd11fa9da81c2df0`, Zephyr `bf801e4e3d19e1ffa76164346480cb7734dd2800`
 * build `clean_installed_compile_required`, runtime `procedure_documented_not_physical_pass`
 * @par Metadata
 * identity `NUCODE_BLE_Audio/AudioControlDevice`, sha256 `8361174bdfba06ed730fb7a0fbd6c1a4060fb86b00279d469878efde6ca1d5a6`
 * @nucode_example_setup_end */

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
