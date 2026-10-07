/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par 목적
 * CAP Acceptor를 확인하고 LC3 unicast의 시작·취소·중단을 반복합니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: Adaptive capabilities (experimental) (adaptive, 실험적 대안)
 * @par 보드와 역할
 * 2대 — 1) CapUnicastInitiator (initiator); 2) CapUnicastAcceptor (acceptor)
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * nucode-build.json, prj.conf
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 추가 조건 없음
 * @par 준비물
 * - NU54DK 보드 2대 — 1) CapUnicastInitiator (initiator); 2) CapUnicastAcceptor (acceptor)
 * @par 설정
 * - Tools → Feature set에서 `ble` profile을 선택합니다.
 * - Sketch 폴더의 sidecar를 함께 설치합니다: nucode-build.json, prj.conf
 * - Serial Monitor는 115200 baud로 엽니다.
 * @par 실행 순서
 * - 권장 profile로 현재 Sketch와 metadata에 적힌 각 peer 역할 Sketch를 빌드합니다.
 * - probe가 여러 대이면 `NUCODE_PROBE_UID`를 지정하고 Arduino Upload로 역할별 보드를 구분합니다.
 * - peer·외장 조건을 먼저 준비한 뒤 reset 또는 예제에 명시된 입력으로 실행합니다.
 * @par 성공 출력
 * - Serial 문구 `CAP Acceptor found`를 포함한 정상 상태 전이를 확인합니다.
 * - Serial 문구 `CAP connected; discovering services`를 포함한 정상 상태 전이를 확인합니다.
 * - Serial 문구 `CAP peer disconnected`를 포함한 정상 상태 전이를 확인합니다.
 * @par 흔한 오류
 * - 권장 profile과 sidecar가 다르면 기능·Kconfig가 빠질 수 있으므로 먼저 설정을 다시 확인합니다.
 * - 여러 probe가 연결된 상태에서 UID를 생략하면 다른 보드에 upload될 수 있습니다.
 * - `CAP begin failed:` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * - `CAP cleanup failed:` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * - `CAP unicast setup failed` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * @par 다음 예제
 * - `NUCODE_BLE_Audio/CsipSetCoordinator`
 * - `NUCODE_BLE_Audio/CsipSetMember`
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
 * identity `NUCODE_BLE_Audio/CapUnicastInitiator`, sha256 `f9cc6df839f097ba2e8c3f9276d668d4383c74c8afbcd351ebb795607fe6b516`
 * @nucode_example_setup_end */

/**
 * @file CapUnicastInitiator.ino
 * @brief CAP Acceptor를 확인하고 LC3 unicast의 시작·취소·중단을 반복합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE.h>
#include <NUCODE_BLE_Audio.h>

using nucode::ble::BLEAddress;
using nucode::ble::BLEConnectionHandle;
using nucode::ble::BLEEvent;
using nucode::ble::BLEEventInfo;
using nucode::ble::BLELinkRole;
using nucode::ble::BLEScanResult;
using nucode::ble::BLEUuid;
using nucode::ble::audio::CapUnicastInitiator;
using nucode::ble::audio::CapUnicastStage;
using nucode::ble::audio::Error;
using nucode::ble::audio::Lc3Codec;

namespace
{
    CapUnicastInitiator initiator;
    Lc3Codec codec;
    BLEAddress peerAddress;
    BLEConnectionHandle peer;
    bool peerFound = false;
    bool restartScan = false;
    bool startIssued = false;
    bool stopIssued = false;
    bool failureReported = false;
    bool cancellationReported = false;
    std::uint32_t completedSessions = 0U;
    std::uint32_t lastFrameAt = 0U;
    std::uint32_t lastStatusAt = 0U;
    std::uint16_t wavePosition = 0U;

    /** @brief CAS를 광고하는 첫 연결 가능한 Acceptor를 선택합니다. */
    void onScanResult(const BLEScanResult &result, void *context)
    {
        static_cast<void>(context);
        if (!peerFound && result.connectable)
        {
            peerAddress = result.address;
            peerFound = true;
            static_cast<void>(BLEScan.stop());
            Serial.println("CAP Acceptor found");
        }
    }

    /** @brief 공개 BLE 연결을 CAP unicast Initiator에 전달합니다. */
    void onBleEvent(const BLEEventInfo &event, void *context)
    {
        static_cast<void>(context);
        if ((event.event == BLEEvent::connected) && (event.role == BLELinkRole::central))
        {
            peer = event.connection;
            startIssued = false;
            stopIssued = false;
            failureReported = false;
            cancellationReported = false;
            const Error result = initiator.begin(peer);
            if (result == Error::none)
            {
                Serial.println("CAP connected; discovering services");
            }
            else
            {
                Serial.print("CAP begin failed: ");
                Serial.println(initiator.nativeCode());
                static_cast<void>(BLEConnection.disconnect(peer));
            }
        }
        else if ((event.event == BLEEvent::disconnected) && (event.connection == peer))
        {
            const Error result = initiator.end();
            if ((result != Error::none) && (result != Error::not_started))
            {
                Serial.print("CAP cleanup failed: ");
                Serial.println(initiator.nativeCode());
            }
            peer = BLEConnectionHandle();
            peerFound = false;
            restartScan = true;
            startIssued = false;
            stopIssued = false;
            Serial.println("CAP peer disconnected");
        }
    }

    /** @brief 16 kHz bounded 삼각파 PCM frame 하나를 생성합니다. */
    void fillPcm(std::int16_t (&pcm)[160])
    {
        for (std::size_t index = 0U; index < 160U; index++)
        {
            const std::uint16_t phase = static_cast<std::uint16_t>((wavePosition + index) % 160U);
            const std::int32_t rising = (phase < 80U) ? phase : (160U - phase);
            pcm[index] = static_cast<std::int16_t>(rising * 300 - 12000);
        }
        wavePosition = static_cast<std::uint16_t>((wavePosition + 17U) % 160U);
    }
} // namespace

/** @brief codec와 CAS 기반 Acceptor 검색을 시작합니다. */
void setup()
{
    Serial.begin(115200);
    BLEScan.onResult(onScanResult);
    BLEDevice.onEventInfo(onBleEvent);
    if ((codec.begin() != Error::none) || !BLEDevice.begin("NU54-CAP-UNICAST") ||
        !BLEScan.clearFilters() || !BLEScan.filterServiceUuid(BLEUuid(0x1853U)) ||
        !BLEScan.start(true))
    {
        Serial.println("CAP unicast setup failed");
        return;
    }
    Serial.println("CAP Acceptor scan started");
}

/** @brief CAP group을 시작하고 홀수 session에서는 진행 중 절차 취소를 확인합니다. */
void loop()
{
    BLEDevice.poll();
    initiator.poll();
    const std::uint32_t now = millis();
    if ((now - lastStatusAt) >= 2000U)
    {
        lastStatusAt = now;
        Serial.print("CAP Initiator status found=");
        Serial.print(peerFound ? 1 : 0);
        Serial.print(" connected=");
        Serial.print(BLEConnection.connected() ? 1 : 0);
        Serial.print(" connecting=");
        Serial.print(BLEConnection.connecting() ? 1 : 0);
        Serial.print(" stage=");
        Serial.println(static_cast<unsigned int>(initiator.stage()));
    }

    if (peerFound && !BLEConnection.connected() && !BLEConnection.connecting())
    {
        peerFound = false;
        if (!BLEConnection.connect(peerAddress))
        {
            restartScan = true;
            Serial.println("CAP connect failed");
        }
    }
    if (restartScan && !BLEConnection.connected() && !BLEConnection.connecting())
    {
        restartScan = false;
        if (!BLEScan.running() && !BLEScan.start(true))
        {
            restartScan = true;
            Serial.println("CAP scan restart failed");
        }
    }

    if (initiator.ready() && !startIssued)
    {
        const Error result = initiator.start();
        startIssued = result == Error::none;
        Serial.print("CAP group start result=");
        Serial.println(static_cast<unsigned int>(result));
        if (startIssued && ((completedSessions % 2U) == 1U))
        {
            const Error cancelled = initiator.cancel();
            Serial.print("CAP in-flight cancel result=");
            Serial.println(static_cast<unsigned int>(cancelled));
        }
    }

    if (initiator.cancelled() && !cancellationReported)
    {
        cancellationReported = true;
        completedSessions++;
        Serial.print("CAP procedure cancelled native=");
        Serial.println(initiator.nativeCode());
        static_cast<void>(BLEConnection.disconnect(peer));
    }

    if ((initiator.stage() == CapUnicastStage::failed) && !failureReported)
    {
        failureReported = true;
        Serial.print("CAP procedure failed step=");
        Serial.print(static_cast<unsigned int>(initiator.lastStep()));
        Serial.print(" peer=");
        Serial.print(initiator.failedOnPeer() ? 1 : 0);
        Serial.print(" native=");
        Serial.println(initiator.nativeCode());
        static_cast<void>(BLEConnection.disconnect(peer));
    }

    if (!initiator.streaming())
    {
        if (startIssued && stopIssued && initiator.ready())
        {
            const Error result = initiator.end();
            if (result == Error::none)
            {
                completedSessions++;
                Serial.print("CAP completed sessions=");
                Serial.println(completedSessions);
                static_cast<void>(BLEConnection.disconnect(peer));
            }
        }
        delay(1U);
        return;
    }

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
        Serial.println("CAP encode failed");
        return;
    }
    const Error sent = initiator.sendFrame(frame);
    if ((sent != Error::none) && (sent != Error::busy))
    {
        Serial.print("CAP send failed: ");
        Serial.println(initiator.nativeCode());
    }
    const std::uint32_t count = initiator.sentFrames();
    if ((sent == Error::none) && ((count % 100U) == 0U))
    {
        Serial.print("CAP sent frames=");
        Serial.println(count);
    }
    if (!stopIssued && (count >= 120U))
    {
        const Error result = initiator.stop();
        stopIssued = result == Error::none;
        const Error duplicate = initiator.stop();
        Serial.print("CAP stop result=");
        Serial.print(static_cast<unsigned int>(result));
        Serial.print(" duplicate=");
        Serial.println(static_cast<unsigned int>(duplicate));
    }
}
