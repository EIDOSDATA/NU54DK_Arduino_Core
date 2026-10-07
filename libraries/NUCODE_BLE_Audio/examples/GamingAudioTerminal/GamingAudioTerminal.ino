/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par 목적
 * GMAP terminal이 gateway의 LC3 unicast를 수신하고 복호화합니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: Adaptive capabilities (experimental) (adaptive, 실험적 대안)
 * @par 보드와 역할
 * 2대 — 1) GamingAudioGateway (gateway); 2) GamingAudioTerminal (terminal)
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * nucode-build.json, prj.conf
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 추가 조건 없음
 * @par 준비물
 * - NU54DK 보드 2대 — 1) GamingAudioGateway (gateway); 2) GamingAudioTerminal (terminal)
 * @par 설정
 * - Tools → Feature set에서 `ble` profile을 선택합니다.
 * - Sketch 폴더의 sidecar를 함께 설치합니다: nucode-build.json, prj.conf
 * - Serial Monitor는 115200 baud로 엽니다.
 * @par 실행 순서
 * - 권장 profile로 현재 Sketch와 metadata에 적힌 각 peer 역할 Sketch를 빌드합니다.
 * - probe가 여러 대이면 `NUCODE_PROBE_UID`를 지정하고 Arduino Upload로 역할별 보드를 구분합니다.
 * - peer·외장 조건을 먼저 준비한 뒤 reset 또는 예제에 명시된 입력으로 실행합니다.
 * @par 성공 출력
 * - Serial 문구 `GMAP local roles=0x2 service=GMAS features=ugg:0x0,ugt:0x4,bgs:0x0,bgr:0x0`를 포함한 정상 상태 전이를 확인합니다.
 * - Serial 문구 `Gaming terminal ready for unicast audio`를 포함한 정상 상태 전이를 확인합니다.
 * - Serial 문구 `Gaming unicast server stop result=`를 포함한 정상 상태 전이를 확인합니다.
 * @par 흔한 오류
 * - 권장 profile과 sidecar가 다르면 기능·Kconfig가 빠질 수 있으므로 먼저 설정을 다시 확인합니다.
 * - 여러 probe가 연결된 상태에서 UID를 생략하면 다른 보드에 upload될 수 있습니다.
 * - `Gaming terminal start failed:` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * - `Gaming LC3 decode failed` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * @par 다음 예제
 * - `NUCODE_BLE_Audio/HearingAccessClient`
 * - `NUCODE_BLE_Audio/HearingAccessServer`
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
 * identity `NUCODE_BLE_Audio/GamingAudioTerminal`, sha256 `46736e0580fad2707a9141c5087993248e0ff852d11dc334ae7242b98595601b`
 * @nucode_example_setup_end */

/**
 * @file GamingAudioTerminal.ino
 * @brief GMAP terminal이 gateway의 LC3 unicast를 수신하고 복호화합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE.h>
#include <NUCODE_BLE_Audio.h>
#include <NUCODE_BLE_Security.h>

namespace
{
    using nucode::ble::audio::Error;
    using nucode::ble::audio::GamingAudioFeatures;
    using nucode::ble::audio::GamingAudioRole;
    using nucode::ble::audio::GamingAudioRoles;
    using nucode::ble::audio::GamingTerminalFeature;
    using nucode::ble::audio::Lc3Codec;
    using nucode::ble::audio::UnicastServer;

    GamingAudioRoles profile;
    UnicastServer audioSink;
    Lc3Codec codec;
    bool restartAdvertising = false;
    bool audioStopped = false;
    std::uint32_t decodedFrames = 0U;

    /** @brief encrypted GMAS 읽기를 위해 pairing을 승인합니다. */
    void onSecurityEvent(const nucode::ble::SecurityEventRecord &event, void *context)
    {
        static_cast<void>(context);
        if (event.event == nucode::ble::SecurityEvent::pairing_requested)
        {
            static_cast<void>(BLESecurity.acceptPairing(event.connection, true));
        }
    }

    /** @brief 연결 해제 뒤 GMAS와 ASCS 광고를 다시 시작합니다. */
    void onBleEvent(const nucode::ble::BLEEventInfo &event, void *context)
    {
        static_cast<void>(context);
        if (event.event == nucode::ble::BLEEvent::disconnected)
        {
            restartAdvertising = !audioStopped;
        }
    }

    /** @brief GMAS와 ASCS UUID를 connectable 광고에 넣습니다. */
    bool startAdvertising()
    {
        constexpr std::uint8_t announcement[] = {1U, 0x03U, 0x00U, 0x00U, 0x00U, 0U};
        return BLEAdvertising.clear() && BLEAdvertising.setConnectable(true) &&
               BLEAdvertising.addServiceUuid(nucode::ble::BLEUuid(0x1858U)) &&
               BLEAdvertising.addServiceUuid(nucode::ble::BLEUuid(0x184EU)) &&
               BLEAdvertising.setServiceData(nucode::ble::BLEUuid(0x184EU), announcement,
                                             sizeof(announcement)) &&
               BLEAdvertising.setScanResponseName(true) && BLEAdvertising.start();
    }

    /** @brief 설정 오류를 성공 상태와 구분해 출력합니다. */
    void require(bool condition, const char *stage)
    {
        if (condition)
        {
            return;
        }
        Serial.print("Gaming terminal start failed: ");
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

    nucode::ble::SecurityConfig security;
    security.minimum_level = nucode::ble::SecurityLevel::encrypted;
    security.bonding = false;
    security.io_capability = nucode::ble::SecurityIoCapability::no_input_output;
    BLESecurity.onEvent(onSecurityEvent);
    BLEDevice.onEventInfo(onBleEvent);

    GamingAudioFeatures features;
    features.unicast_terminal = static_cast<std::uint8_t>(GamingTerminalFeature::sink);
    require(BLESecurity.begin(security), "security");
    require(BLEDevice.begin("NU54-GAME-TERMINAL"), "device");
    require(profile.begin(GamingAudioRole::unicast_game_terminal, features) == Error::none,
            "roles");
    Serial.println("GMAP local roles=0x2 service=GMAS features=ugg:0x0,ugt:0x4,bgs:0x0,bgr:0x0");
    require(audioSink.begin() == Error::none, "unicast server");
    require(codec.begin() == Error::none, "codec");
    require(startAdvertising(), "advertising");
    Serial.println("Gaming terminal ready for unicast audio");
}

void loop()
{
    BLEDevice.poll();
    BLESecurity.poll();
    profile.poll();

    if (restartAdvertising && !BLEAdvertising.running())
    {
        restartAdvertising = !startAdvertising();
    }
    while (Serial.available() > 0)
    {
        const char command = static_cast<char>(Serial.read());
        if (command == 'r')
        {
            if (audioStopped)
            {
                audioStopped = audioSink.begin() != Error::none;
            }
            restartAdvertising = !audioStopped;
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
            invalidFeatures.unicast_terminal = 0x80U;
            Serial.println(invalidProfile.begin(GamingAudioRole::unicast_game_terminal,
                                                invalidFeatures) == Error::invalid_argument
                               ? "Invalid GMAP feature rejected"
                               : "Invalid GMAP feature unexpectedly accepted");
        }
        else if (command == 's')
        {
            static_cast<void>(BLEAdvertising.stop());
            const Error result = audioSink.end();
            audioStopped = result == Error::none;
            Serial.print("Gaming unicast server stop result=");
            Serial.println(static_cast<unsigned int>(result));
        }
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
        decodedFrames++;
        if ((decodedFrames % 100U) == 0U)
        {
            Serial.print("Gaming decoded frames=");
            Serial.print(decodedFrames);
            Serial.print(" dropped=");
            Serial.println(audioSink.droppedFrames());
        }
    }
    delay(1U);
}
