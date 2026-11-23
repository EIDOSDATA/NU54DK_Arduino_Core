/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par 목적
 * 원격 오디오 장치의 volume과 microphone 상태를 제어하는 예제입니다.
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
 * - Serial 문구 `Audio control device found`를 포함한 정상 상태 전이를 확인합니다.
 * - Serial 문구 `Volume discovery started`를 포함한 정상 상태 전이를 확인합니다.
 * - Serial 문구 `Audio control recovery limit reached`를 포함한 정상 상태 전이를 확인합니다.
 * @par 흔한 오류
 * - 권장 profile과 sidecar가 다르면 기능·Kconfig가 빠질 수 있으므로 먼저 설정을 다시 확인합니다.
 * - 여러 probe가 연결된 상태에서 UID를 생략하면 다른 보드에 upload될 수 있습니다.
 * - `Volume discovery failed native=` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * - `Audio control security failed reason=` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * - `Audio control security request failed` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * @par 다음 예제
 * - `NUCODE_BLE_Audio/AudioControlDevice`
 * - `NUCODE_BLE_Audio/BapBroadcastAssistant`
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
 * identity `NUCODE_BLE_Audio/AudioControlController`, sha256 `9b9068667f8918275ebbb66a4062b4d7bc0367a30c07ea4041de7ee820f08722`
 * @nucode_example_setup_end */

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
    /** @brief 연결 뒤 보안과 두 profile 준비 단계를 추적합니다. */
    enum class ConnectionPhase : std::uint8_t
    {
        idle,
        securing,
        volume_discovery,
        microphone_discovery,
        ready,
        recovering,
    };

    VolumeController volumeController;
    MicrophoneController microphoneController;
    BLEAddress peerAddress;
    BLEConnectionHandle peerConnection;
    bool peerFound = false;
    bool volumeStarted = false;
    bool microphoneStarted = false;
    bool scanPending = false;
    std::uint32_t scanAt = 0U;
    constexpr std::uint8_t maximumProfileRecoveries = 3U;
    constexpr std::uint8_t maximumDisconnectAttempts = 3U;
    constexpr std::uint32_t securityTimeoutMs = 10000U;
    constexpr std::uint32_t profileTimeoutMs = 10000U;
    std::uint8_t profileRecoveries = 0U;
    std::uint8_t disconnectAttempts = 0U;
    bool profileRecoveryPending = false;
    std::uint32_t disconnectAt = 0U;
    ConnectionPhase connectionPhase = ConnectionPhase::idle;
    std::uint32_t phaseDeadline = 0U;

    void scheduleProfileRecovery();

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
                connectionPhase = ConnectionPhase::volume_discovery;
                phaseDeadline = millis() + profileTimeoutMs;
                Serial.println("Volume discovery started");
            }
            else
            {
                Serial.print("Volume discovery failed native=");
                Serial.println(volumeController.nativeCode());
                scheduleProfileRecovery();
            }
        }
        else if (((event.event == SecurityEvent::pairing_failed) ||
                  (event.event == SecurityEvent::pairing_cancelled) ||
                  (event.event == SecurityEvent::timeout) ||
                  (event.event == SecurityEvent::error)) &&
                 (event.connection == peerConnection))
        {
            Serial.print("Audio control security failed reason=");
            Serial.println(event.reason);
            scheduleProfileRecovery();
        }
    }

    /** @brief 연결 수명에 두 controller와 재검색을 결합합니다. */
    void onBleEvent(const BLEEventInfo &event, void *context)
    {
        static_cast<void>(context);
        if ((event.event == BLEEvent::connected) && (event.role == BLELinkRole::central))
        {
            peerConnection = event.connection;
            connectionPhase = ConnectionPhase::securing;
            phaseDeadline = millis() + securityTimeoutMs;
            if (!BLESecurity.requestSecurity(peerConnection))
            {
                Serial.println("Audio control security request failed");
                scheduleProfileRecovery();
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
            profileRecoveryPending = false;
            disconnectAttempts = 0U;
            connectionPhase = ConnectionPhase::idle;
            phaseDeadline = 0U;
            if (profileRecoveries < maximumProfileRecoveries)
            {
                scanPending = true;
                scanAt = millis() + 100U;
            }
            else
            {
                scanPending = false;
                Serial.println("Audio control recovery limit reached");
            }
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

    /** @brief 실패한 profile을 정리하고 bounded reconnect를 예약합니다. */
    void scheduleProfileRecovery()
    {
        if (profileRecoveryPending || (profileRecoveries >= maximumProfileRecoveries))
        {
            return;
        }
        Serial.print("Audio control profile recovery attempt=");
        Serial.println(profileRecoveries + 1U);
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
        ++profileRecoveries;
        disconnectAttempts = 0U;
        profileRecoveryPending = true;
        connectionPhase = ConnectionPhase::recovering;
        disconnectAt = millis();
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
    Serial.println(
        "Commands: r=volume f=offset i=speaker input k=microphone l=microphone input s=state");
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

    if (profileRecoveryPending && BLEConnection.connected() &&
        (static_cast<std::int32_t>(millis() - disconnectAt) >= 0))
    {
        if (disconnectAttempts < maximumDisconnectAttempts)
        {
            ++disconnectAttempts;
            static_cast<void>(BLEConnection.disconnect(peerConnection));
            disconnectAt = millis() + 2000U;
        }
        else
        {
            profileRecoveryPending = false;
            Serial.println("Audio control disconnect recovery stopped");
        }
    }
    else if (profileRecoveryPending && !BLEConnection.connected() && !BLEConnection.connecting())
    {
        profileRecoveryPending = false;
        if (profileRecoveries < maximumProfileRecoveries)
        {
            scanPending = true;
            scanAt = millis() + 100U;
        }
    }

    if (volumeStarted && volumeController.ready() && !microphoneStarted)
    {
        const Error result = microphoneController.begin(peerConnection);
        if (result == Error::none)
        {
            microphoneStarted = true;
            connectionPhase = ConnectionPhase::microphone_discovery;
            phaseDeadline = millis() + profileTimeoutMs;
            Serial.println("Microphone discovery started");
        }
        else
        {
            report("Microphone discovery", result, microphoneController.nativeCode());
            scheduleProfileRecovery();
        }
    }

    if (volumeController.ready() && microphoneController.ready())
    {
        profileRecoveries = 0U;
        connectionPhase = ConnectionPhase::ready;
        phaseDeadline = 0U;
    }

    if (!profileRecoveryPending && BLEConnection.connected() &&
        ((connectionPhase == ConnectionPhase::securing) ||
         (connectionPhase == ConnectionPhase::volume_discovery) ||
         (connectionPhase == ConnectionPhase::microphone_discovery)) &&
        (static_cast<std::int32_t>(millis() - phaseDeadline) >= 0))
    {
        Serial.println("Audio control phase timeout");
        scheduleProfileRecovery();
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
        else if (command == 'f')
        {
            report("Read output offset", volumeController.readOffset(),
                   volumeController.nativeCode());
        }
        else if (command == 'i')
        {
            report("Read program input", volumeController.readInput(),
                   volumeController.nativeCode());
        }
        else if (command == 'k')
        {
            report("Read microphone", microphoneController.readMicrophone(),
                   microphoneController.nativeCode());
        }
        else if (command == 'l')
        {
            report("Read microphone input", microphoneController.readInput(),
                   microphoneController.nativeCode());
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

    if (!profileRecoveryPending && ((volumeController.stage() == AudioControlStage::failed) ||
                                    (microphoneController.stage() == AudioControlStage::failed)))
    {
        Serial.print("Audio control profile failed volume=");
        Serial.print(volumeController.nativeCode());
        Serial.print(" microphone=");
        Serial.println(microphoneController.nativeCode());
        scheduleProfileRecovery();
    }
    delay(1U);
}
