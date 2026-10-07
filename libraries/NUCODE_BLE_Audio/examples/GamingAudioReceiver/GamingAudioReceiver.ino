/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par 목적
 * GMAP broadcast receiver가 LC3 방송을 찾아 PCM으로 복호화합니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: Adaptive capabilities (experimental) (adaptive, 실험적 대안)
 * @par 보드와 역할
 * 2대 — 1) GamingAudioBroadcaster (broadcaster); 2) GamingAudioReceiver (receiver)
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * nucode-build.json, prj.conf
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 추가 조건 없음
 * @par 준비물
 * - NU54DK 보드 2대 — 1) GamingAudioBroadcaster (broadcaster); 2) GamingAudioReceiver (receiver)
 * @par 설정
 * - Tools → Feature set에서 `ble` profile을 선택합니다.
 * - Sketch 폴더의 sidecar를 함께 설치합니다: nucode-build.json, prj.conf
 * - Serial Monitor는 115200 baud로 엽니다.
 * @par 실행 순서
 * - 권장 profile로 현재 Sketch와 metadata에 적힌 각 peer 역할 Sketch를 빌드합니다.
 * - probe가 여러 대이면 `NUCODE_PROBE_UID`를 지정하고 Arduino Upload로 역할별 보드를 구분합니다.
 * - peer·외장 조건을 먼저 준비한 뒤 reset 또는 예제에 명시된 입력으로 실행합니다.
 * @par 성공 출력
 * - Serial 문구 `Gaming broadcast receiver scanning`를 포함한 정상 상태 전이를 확인합니다.
 * - Serial 문구 `GMAP local roles=0x8 service=GMAS features=ugg:0x0,ugt:0x0,bgs:0x0,bgr:0x0`를 포함한 정상 상태 전이를 확인합니다.
 * - Serial 문구 `Gaming broadcast sink stop result=`를 포함한 정상 상태 전이를 확인합니다.
 * @par 흔한 오류
 * - 권장 profile과 sidecar가 다르면 기능·Kconfig가 빠질 수 있으므로 먼저 설정을 다시 확인합니다.
 * - 여러 probe가 연결된 상태에서 UID를 생략하면 다른 보드에 upload될 수 있습니다.
 * - `Gaming broadcast sink start failed native=` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * - `Gaming receiver start failed:` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * - `Gaming broadcast sync failed native=` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * @par 다음 예제
 * - `NUCODE_BLE_Audio/GamingAudioTerminal`
 * - `NUCODE_BLE_Audio/HearingAccessClient`
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
 * identity `NUCODE_BLE_Audio/GamingAudioReceiver`, sha256 `c35ee0f51ac9ba721c9c0646106dfa91d68b0faeafcfdb0e102a1780d093ac71`
 * @nucode_example_setup_end */

/**
 * @file GamingAudioReceiver.ino
 * @brief GMAP broadcast receiver가 LC3 방송을 찾아 PCM으로 복호화합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE.h>
#include <NUCODE_BLE_Audio.h>

namespace
{
    using nucode::ble::audio::BroadcastSink;
    using nucode::ble::audio::BroadcastStage;
    using nucode::ble::audio::Error;
    using nucode::ble::audio::GamingAudioFeatures;
    using nucode::ble::audio::GamingAudioRole;
    using nucode::ble::audio::GamingAudioRoles;
    using nucode::ble::audio::Lc3Codec;

    constexpr const char *broadcastName = "NU54-GAME-AUDIO";
    GamingAudioRoles profile;
    BroadcastSink audioSink;
    Lc3Codec codec;
    bool reportedFailure = false;

    /** @brief 방송 검색을 시작하고 오류를 원본 코드와 함께 출력합니다. */
    bool startListening()
    {
        const Error result = audioSink.begin(broadcastName);
        if (result != Error::none)
        {
            Serial.print("Gaming broadcast sink start failed native=");
            Serial.println(audioSink.nativeCode());
            return false;
        }
        reportedFailure = false;
        Serial.println("Gaming broadcast receiver scanning");
        return true;
    }

    /** @brief 초기화 실패를 성공 출력과 구분합니다. */
    void require(bool condition, const char *stage)
    {
        if (condition)
        {
            return;
        }
        Serial.print("Gaming receiver start failed: ");
        Serial.println(stage);
        while (true)
        {
            delay(1000U);
        }
    }
} // namespace

void setup()
{
    Serial.begin(115200);
    GamingAudioFeatures features;

    require(BLEDevice.begin("NU54-GAME-RECEIVER"), "device");
    require(profile.begin(GamingAudioRole::broadcast_game_receiver, features) == Error::none,
            "roles");
    Serial.println("GMAP local roles=0x8 service=GMAS features=ugg:0x0,ugt:0x0,bgs:0x0,bgr:0x0");
    require(codec.begin() == Error::none, "codec");
    require(startListening(), "broadcast");
}

void loop()
{
    BLEDevice.poll();
    profile.poll();
    audioSink.poll();

    while (Serial.available() > 0)
    {
        const char command = static_cast<char>(Serial.read());
        if (command == 's')
        {
            const Error result = audioSink.end();
            Serial.print("Gaming broadcast sink stop result=");
            Serial.println(static_cast<unsigned int>(result));
        }
        else if (command == 'r')
        {
            static_cast<void>(startListening());
        }
        else if (command == 'x')
        {
            GamingAudioRoles unsupported;
            const GamingAudioFeatures noFeatures;
            Serial.println(unsupported.begin(GamingAudioRole::broadcast_game_sender, noFeatures) ==
                                   Error::unsupported
                               ? "Unsupported GMAP role rejected"
                               : "Unsupported GMAP role unexpectedly accepted");
        }
        else if (command == 'q')
        {
            Lc3Codec incompatibleCodec;
            nucode::ble::audio::Lc3Config incompatibleQuality;
            incompatibleQuality.frame_duration_us = 5000U;
            Serial.println(incompatibleCodec.begin(incompatibleQuality) == Error::invalid_argument
                               ? "Gaming quality mismatch rejected"
                               : "Gaming quality mismatch unexpectedly accepted");
        }
        else if (command == 'f')
        {
            GamingAudioRoles invalidProfile;
            GamingAudioFeatures invalidFeatures;
            invalidFeatures.broadcast_receiver = 0x80U;
            Serial.println(invalidProfile.begin(GamingAudioRole::broadcast_game_receiver,
                                                invalidFeatures) == Error::invalid_argument
                               ? "Invalid GMAP feature rejected"
                               : "Invalid GMAP feature unexpectedly accepted");
        }
    }

    if ((audioSink.stage() == BroadcastStage::failed) && !reportedFailure)
    {
        reportedFailure = true;
        Serial.print("Gaming broadcast sync failed native=");
        Serial.println(audioSink.nativeCode());
    }
    std::uint8_t frame[40] = {};
    std::int16_t pcm[160] = {};
    while (audioSink.readFrame(frame))
    {
        if (codec.decode(frame, sizeof(frame), pcm, 160U) != Error::none)
        {
            Serial.println("Gaming LC3 decode failed");
            continue;
        }
        const std::uint32_t count = audioSink.receivedFrames();
        if ((count % 100U) == 0U)
        {
            Serial.print("Gaming broadcast received=");
            Serial.print(count);
            Serial.print(" dropped=");
            Serial.println(audioSink.droppedFrames());
        }
    }
    delay(1U);
}
