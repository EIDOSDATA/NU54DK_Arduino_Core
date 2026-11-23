/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par 목적
 * Standard Quality 공개 오디오 방송을 찾아 LC3 frame을 복호화합니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: Adaptive capabilities (experimental) (adaptive, 실험적 대안)
 * @par 보드와 역할
 * 2대 — 1) PublicAudioBroadcastSource (source/transmitter); 2) PublicAudioBroadcastSink (sink/receiver)
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * nucode-build.json, prj.conf
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 추가 조건 없음
 * @par 준비물
 * - NU54DK 보드 2대 — 1) PublicAudioBroadcastSource (source/transmitter); 2) PublicAudioBroadcastSink (sink/receiver)
 * @par 설정
 * - Tools → Feature set에서 `ble` profile을 선택합니다.
 * - Sketch 폴더의 sidecar를 함께 설치합니다: nucode-build.json, prj.conf
 * - Serial Monitor는 115200 baud로 엽니다.
 * @par 실행 순서
 * - 권장 profile로 현재 Sketch와 metadata에 적힌 각 peer 역할 Sketch를 빌드합니다.
 * - probe가 여러 대이면 `NUCODE_PROBE_UID`를 지정하고 Arduino Upload로 역할별 보드를 구분합니다.
 * - peer·외장 조건을 먼저 준비한 뒤 reset 또는 예제에 명시된 입력으로 실행합니다.
 * @par 성공 출력
 * - Serial 문구 `public audio sink scanning`를 포함한 정상 상태 전이를 확인합니다.
 * - Serial 문구 `public audio sink stopped`를 포함한 정상 상태 전이를 확인합니다.
 * - Serial 문구 `selected public audio name=`를 포함한 정상 상태 전이를 확인합니다.
 * @par 흔한 오류
 * - 권장 profile과 sidecar가 다르면 기능·Kconfig가 빠질 수 있으므로 먼저 설정을 다시 확인합니다.
 * - 여러 probe가 연결된 상태에서 UID를 생략하면 다른 보드에 upload될 수 있습니다.
 * - `public audio sink start failed:` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * - `public audio sink stop failed:` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * - `Bluetooth start failed` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * @par 다음 예제
 * - `NUCODE_BLE_Audio/PublicAudioBroadcastSource`
 * - `NUCODE_BLE_Audio/TelephonyMediaBroadcaster`
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
 * identity `NUCODE_BLE_Audio/PublicAudioBroadcastSink`, sha256 `f449cfb18ca3d52d00fc17841c36800980ec004f86c72d4bbe0ca822b5bb3766`
 * @nucode_example_setup_end */

/**
 * @file PublicAudioBroadcastSink.ino
 * @brief Standard Quality 공개 오디오 방송을 찾아 LC3 frame을 복호화합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE.h>
#include <NUCODE_BLE_Audio.h>

using nucode::ble::audio::BroadcastCode;
using nucode::ble::audio::BroadcastStage;
using nucode::ble::audio::Error;
using nucode::ble::audio::Lc3Codec;
using nucode::ble::audio::PublicAudioBroadcastSink;
using nucode::ble::audio::PublicBroadcastFilter;
using nucode::ble::audio::PublicBroadcastInfo;
using nucode::ble::audio::PublicBroadcastQuality;

namespace
{
    constexpr BroadcastCode broadcastCode = {
        0x4e, 0x55, 0x43, 0x4f, 0x44, 0x45, 0x2d, 0x50,
        0x55, 0x42, 0x4c, 0x49, 0x43, 0x2d, 0x30, 0x31,
    };
    constexpr BroadcastCode alternateBroadcastCode = {
        0x4f, 0x55, 0x43, 0x4f, 0x44, 0x45, 0x2d, 0x50,
        0x55, 0x42, 0x4c, 0x49, 0x43, 0x2d, 0x30, 0x31,
    };
    PublicBroadcastFilter broadcastFilter = {
        .broadcast_name = "NUCODE-PUBLIC-AUDIO",
        .required_quality = PublicBroadcastQuality::standard,
    };
    PublicAudioBroadcastSink audioSink;
    Lc3Codec codec;
    bool listening = false;
    bool announcedSelection = false;
    bool announcedStreaming = false;
    bool recoveryPending = false;
    bool automaticRecovery = true;
    std::uint32_t recoveryAt = 0U;

    /** @brief 다음 정리·재시작 시도를 1초 뒤로 제한합니다. */
    void scheduleRecovery()
    {
        recoveryPending = true;
        recoveryAt = millis() + 1000U;
    }

    /** @brief 공개 API로 조건에 맞는 방송 검색을 시작합니다. */
    bool startListening(const BroadcastCode &code)
    {
        broadcastFilter.required_quality = PublicBroadcastQuality::standard;
        const Error result = audioSink.begin(broadcastFilter, code);
        if (result != Error::none)
        {
            Serial.print("public audio sink start failed: ");
            Serial.println(audioSink.nativeCode());
            listening = audioSink.stage() == BroadcastStage::failed;
            return false;
        }
        listening = true;
        announcedSelection = false;
        announcedStreaming = false;
        recoveryPending = false;
        Serial.println("public audio sink scanning");
        return true;
    }

    /** @brief 실행 중인 검색을 끝내고 객체 상태를 갱신합니다. */
    bool stopListening()
    {
        if (listening)
        {
            const Error result = audioSink.end();
            if (result != Error::none)
            {
                Serial.print("public audio sink stop failed: ");
                Serial.println(audioSink.nativeCode());
                return false;
            }
            listening = false;
        }
        return true;
    }

    /** @brief PCM frame의 절대값 합으로 실제 decode 결과를 확인합니다. */
    std::uint32_t frameEnergy(const std::int16_t (&pcm)[160])
    {
        std::uint32_t energy = 0U;
        for (const std::int16_t sample : pcm)
        {
            const std::int32_t value = sample;
            energy += static_cast<std::uint32_t>(value < 0 ? -value : value);
        }
        return energy;
    }
} // namespace

/** @brief Bluetooth, LC3 codec과 공개 오디오 sink를 순서대로 시작합니다. */
void setup()
{
    Serial.begin(115200);
    if (!BLEDevice.begin("NUCODE-PUBLIC-SINK"))
    {
        Serial.println("Bluetooth start failed");
        return;
    }
    if (codec.begin() != Error::none)
    {
        Serial.println("LC3 codec start failed");
        return;
    }
    static_cast<void>(startListening(broadcastCode));
}

/** @brief 검색·동기화를 진행하고 공개 LC3 frame을 PCM으로 decode합니다. */
void loop()
{
    BLEDevice.poll();
    audioSink.poll();

    while (Serial.available() > 0)
    {
        const char command = static_cast<char>(Serial.read());
        if (command == 's')
        {
            automaticRecovery = false;
            recoveryPending = false;
            if (stopListening())
            {
                Serial.println("public audio sink stopped");
            }
        }
        else if (command == 'r')
        {
            automaticRecovery = true;
            if (stopListening() && !startListening(broadcastCode))
            {
                scheduleRecovery();
            }
        }
        else if (command == 'w')
        {
            automaticRecovery = true;
            if (stopListening() && !startListening(alternateBroadcastCode))
            {
                scheduleRecovery();
            }
        }
        else if (command == 'h')
        {
            automaticRecovery = true;
            if (stopListening())
            {
                broadcastFilter.required_quality = PublicBroadcastQuality::high;
                const Error result = audioSink.begin(broadcastFilter, broadcastCode);
                Serial.print("high quality rejected: ");
                Serial.println(static_cast<unsigned int>(result));
                broadcastFilter.required_quality = PublicBroadcastQuality::standard;
                scheduleRecovery();
            }
        }
    }

    PublicBroadcastInfo selectedInfo = {};
    if (!announcedSelection && audioSink.selected(selectedInfo))
    {
        announcedSelection = true;
        Serial.print("selected public audio name=");
        Serial.print(selectedInfo.broadcast_name);
        Serial.print(" program=");
        Serial.print(selectedInfo.program_info);
        Serial.print(" encrypted=");
        Serial.println(selectedInfo.encrypted ? "yes" : "no");
    }

    if (listening && automaticRecovery && !recoveryPending &&
        (audioSink.stage() == BroadcastStage::failed))
    {
        Serial.print("public audio sync failed: ");
        Serial.print(audioSink.nativeCode());
        Serial.print(" step=");
        Serial.println(static_cast<unsigned int>(audioSink.lastStep()));
        scheduleRecovery();
    }
    if (recoveryPending &&
        (static_cast<std::int32_t>(millis() - recoveryAt) >= 0))
    {
        recoveryPending = false;
        if (listening && !stopListening())
        {
            scheduleRecovery();
        }
        else if (!startListening(broadcastCode))
        {
            scheduleRecovery();
        }
    }
    if (audioSink.streaming() && !announcedStreaming)
    {
        announcedStreaming = true;
        Serial.println("public audio sink streaming");
    }

    std::uint8_t frame[40] = {};
    while (audioSink.readFrame(frame))
    {
        std::int16_t pcm[160] = {};
        if (codec.decode(frame, sizeof(frame), pcm, 160U) != Error::none)
        {
            Serial.println("LC3 decode failed");
            continue;
        }
        const std::uint32_t count = audioSink.receivedFrames();
        if ((count % 100U) == 0U)
        {
            Serial.print("public audio received=");
            Serial.print(count);
            Serial.print(" energy=");
            Serial.print(frameEnergy(pcm));
            Serial.print(" dropped=");
            Serial.println(audioSink.droppedFrames());
        }
    }
    delay(1U);
}
