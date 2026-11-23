/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par 목적
 * GMAP gateway가 terminal 역할을 확인한 뒤 LC3 unicast를 송신합니다.
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
 * - Serial 문구 `GMAP local roles=0x1 service=GMAS features=ugg:0x0,ugt:0x0,bgs:0x0,bgr:0x0`를 포함한 정상 상태 전이를 확인합니다.
 * - Serial 문구 `Gaming gateway searching for a terminal`를 포함한 정상 상태 전이를 확인합니다.
 * - Serial 문구 `GMAP peer roles=0x`를 포함한 정상 상태 전이를 확인합니다.
 * @par 흔한 오류
 * - 권장 profile과 sidecar가 다르면 기능·Kconfig가 빠질 수 있으므로 먼저 설정을 다시 확인합니다.
 * - 여러 probe가 연결된 상태에서 UID를 생략하면 다른 보드에 upload될 수 있습니다.
 * - `GMAP security request failed` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * - `GMAP discovery start failed native=` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * - `Gaming gateway start failed:` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * @par 다음 예제
 * - `NUCODE_BLE_Audio/GamingAudioReceiver`
 * - `NUCODE_BLE_Audio/GamingAudioTerminal`
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
 * identity `NUCODE_BLE_Audio/GamingAudioGateway`, sha256 `c40681d44f4563c02aa12e680fb8df2419c42bf99f582101be44015874c002c5`
 * @nucode_example_setup_end */

/**
 * @file GamingAudioGateway.ino
 * @brief GMAP gateway가 terminal 역할을 확인한 뒤 LC3 unicast를 송신합니다.
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
    using nucode::ble::audio::GamingAudioPeer;
    using nucode::ble::audio::GamingAudioRole;
    using nucode::ble::audio::GamingAudioRoles;
    using nucode::ble::audio::GamingAudioStage;
    using nucode::ble::audio::Lc3Codec;
    using nucode::ble::audio::UnicastClient;
    using nucode::ble::audio::UnicastClientStage;

    GamingAudioRoles profile;
    UnicastClient audioSource;
    Lc3Codec codec;
    nucode::ble::BLEAddress candidate;
    nucode::ble::BLEConnectionHandle peer;
    bool candidateReady = false;
    bool restartScan = false;
    bool audioStarted = false;
    bool reportedStreaming = false;
    bool reportedFailure = false;
    std::uint32_t lastFrameAt = 0U;
    std::uint32_t sentFrames = 0U;
    std::uint16_t wavePosition = 0U;

    /** @brief GMAS 광고 하나를 선택합니다. */
    void onScanResult(const nucode::ble::BLEScanResult &result, void *context)
    {
        static_cast<void>(context);
        if (!candidateReady && result.connectable && !result.scan_response)
        {
            candidate = result.address;
            candidateReady = true;
            static_cast<void>(BLEScan.stop());
        }
    }

    /** @brief exact central 연결을 보안과 discovery session에 결합합니다. */
    void onBleEvent(const nucode::ble::BLEEventInfo &event, void *context)
    {
        static_cast<void>(context);
        if ((event.event == nucode::ble::BLEEvent::connected) &&
            (event.role == nucode::ble::BLELinkRole::central))
        {
            peer = event.connection;
            if (!BLESecurity.requestSecurity(peer))
            {
                Serial.println("GMAP security request failed");
            }
        }
        else if ((event.event == nucode::ble::BLEEvent::disconnected) && (event.connection == peer))
        {
            static_cast<void>(audioSource.end());
            peer = {};
            candidateReady = false;
            restartScan = true;
            audioStarted = false;
            reportedStreaming = false;
            reportedFailure = false;
        }
    }

    /** @brief encrypted peer에서 GMAS 역할·feature 검색을 시작합니다. */
    void onSecurityEvent(const nucode::ble::SecurityEventRecord &event, void *context)
    {
        static_cast<void>(context);
        if ((event.connection == peer) &&
            ((event.event == nucode::ble::SecurityEvent::paired) ||
             (event.event == nucode::ble::SecurityEvent::security_changed)))
        {
            const Error result = profile.discover(peer);
            if ((result != Error::none) && (result != Error::busy))
            {
                Serial.print("GMAP discovery start failed native=");
                Serial.println(profile.nativeCode());
            }
        }
    }

    /** @brief 16 kHz의 bounded 삼각파 PCM frame 하나를 생성합니다. */
    void fillPcm(std::int16_t (&pcm)[160])
    {
        for (std::size_t index = 0U; index < 160U; index++)
        {
            const std::uint16_t phase = static_cast<std::uint16_t>((wavePosition + index) % 160U);
            const std::int32_t rising = (phase < 80U) ? phase : (160U - phase);
            pcm[index] = static_cast<std::int16_t>(rising * 300 - 12000);
        }
        wavePosition = static_cast<std::uint16_t>((wavePosition + 23U) % 160U);
    }

    /** @brief 설정 또는 stack 오류를 단계 이름과 함께 출력합니다. */
    void require(bool condition, const char *stage)
    {
        if (condition)
        {
            return;
        }
        Serial.print("Gaming gateway start failed: ");
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
    BLEDevice.onEventInfo(onBleEvent);
    BLEScan.onResult(onScanResult);
    BLESecurity.onEvent(onSecurityEvent);

    GamingAudioFeatures features;
    require(BLESecurity.begin(security), "security");
    require(BLEDevice.begin("NU54-GAME-GATEWAY"), "device");
    require(codec.begin() == Error::none, "codec");
    require(profile.begin(GamingAudioRole::unicast_game_gateway, features) == Error::none, "roles");
    Serial.println("GMAP local roles=0x1 service=GMAS features=ugg:0x0,ugt:0x0,bgs:0x0,bgr:0x0");
    require(BLEScan.clearFilters(), "scan clear");
    require(BLEScan.filterServiceUuid(nucode::ble::BLEUuid(0x1858U)), "GMAS filter");
    require(BLEScan.start(true), "scan");
    Serial.println("Gaming gateway searching for a terminal");
}

void loop()
{
    BLEDevice.poll();
    BLESecurity.poll();
    profile.poll();
    audioSource.poll();

    if (candidateReady && !peer.valid())
    {
        candidateReady = false;
        if (!BLEConnection.connect(candidate))
        {
            restartScan = true;
        }
    }
    if (restartScan && !BLEScan.running())
    {
        restartScan = !BLEScan.start(true);
    }
    if (!audioStarted && (profile.stage() == GamingAudioStage::discovered))
    {
        GamingAudioPeer information;
        const Error readResult = profile.peer(information);
        if (readResult == Error::none)
        {
            Serial.print("GMAP peer roles=0x");
            Serial.println(information.roles, HEX);
            Serial.print("GMAP peer features=ugg:0x");
            Serial.print(information.features.unicast_gateway, HEX);
            Serial.print(",ugt:0x");
            Serial.print(information.features.unicast_terminal, HEX);
            Serial.print(",bgs:0x");
            Serial.print(information.features.broadcast_sender, HEX);
            Serial.print(",bgr:0x");
            Serial.println(information.features.broadcast_receiver, HEX);
        }
        if ((readResult != Error::none) ||
            !profile.peerSupports(GamingAudioRole::unicast_game_terminal))
        {
            Serial.println("Gaming terminal role rejected");
            static_cast<void>(BLEConnection.disconnect(peer));
        }
        else
        {
            const Error result = audioSource.begin(peer);
            audioStarted = result == Error::none;
            if (!audioStarted)
            {
                Serial.print("Gaming unicast start failed native=");
                Serial.println(audioSource.nativeCode());
                static_cast<void>(BLEConnection.disconnect(peer));
            }
        }
    }

    while (Serial.available() > 0)
    {
        const char command = static_cast<char>(Serial.read());
        if ((command == 'r') && peer.valid())
        {
            static_cast<void>(BLEConnection.disconnect(peer));
        }
        else if (command == 'x')
        {
            const nucode::ble::BLEConnectionHandle invalid;
            Serial.println(profile.discover(invalid) == Error::not_connected
                               ? "Invalid GMAP peer rejected"
                               : "Invalid GMAP peer unexpectedly accepted");
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
            invalidFeatures.unicast_gateway = 0x80U;
            Serial.println(invalidProfile.begin(GamingAudioRole::unicast_game_gateway,
                                                invalidFeatures) == Error::invalid_argument
                               ? "Invalid GMAP feature rejected"
                               : "Invalid GMAP feature unexpectedly accepted");
        }
        else if (command == 's')
        {
            const Error result = audioSource.stop();
            Serial.print("Gaming stream stop result=");
            Serial.println(static_cast<unsigned int>(result));
        }
    }

    if ((audioSource.stage() == UnicastClientStage::failed) && !reportedFailure)
    {
        reportedFailure = true;
        Serial.print("Gaming unicast failed native=");
        Serial.println(audioSource.nativeCode());
    }
    if (audioSource.stage() != UnicastClientStage::streaming)
    {
        delay(1U);
        return;
    }
    if (!reportedStreaming)
    {
        reportedStreaming = true;
        Serial.println("Gaming unicast streaming");
    }

    const std::uint32_t now = millis();
    if ((now - lastFrameAt) < 10U)
    {
        delay(1U);
        return;
    }
    lastFrameAt = now;

    std::int16_t pcm[160] = {};
    std::uint8_t frame[40] = {};
    fillPcm(pcm);
    if (codec.encode(pcm, 160U, frame, sizeof(frame)) != Error::none)
    {
        Serial.println("Gaming LC3 encode failed");
        return;
    }
    const Error sent = audioSource.sendFrame(frame);
    if (sent == Error::none)
    {
        sentFrames++;
        if ((sentFrames % 100U) == 0U)
        {
            Serial.print("Gaming sent frames=");
            Serial.println(sentFrames);
        }
    }
    else if (sent != Error::busy)
    {
        Serial.print("Gaming send failed native=");
        Serial.println(audioSource.nativeCode());
    }
}
