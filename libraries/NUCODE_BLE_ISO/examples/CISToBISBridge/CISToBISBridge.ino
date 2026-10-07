/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par 목적
 * CIS 사용자 SDU를 읽어 같은 payload를 BIS로 전달합니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: Adaptive capabilities (experimental) (adaptive, 실험적 대안)
 * @par 보드와 역할
 * 3대 — 1) CISToBISPeer (peer); 2) CISToBISBridge (bridge); 3) CISToBISReceiver (receiver)
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * nucode-build.json, prj.conf
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 추가 조건 없음
 * @par 준비물
 * - NU54DK 보드 3대 — 1) CISToBISPeer (peer); 2) CISToBISBridge (bridge); 3) CISToBISReceiver (receiver)
 * @par 설정
 * - Tools → Feature set에서 `ble` profile을 선택합니다.
 * - Sketch 폴더의 sidecar를 함께 설치합니다: nucode-build.json, prj.conf
 * - Serial Monitor는 115200 baud로 엽니다.
 * @par 실행 순서
 * - 권장 profile로 현재 Sketch와 metadata에 적힌 각 peer 역할 Sketch를 빌드합니다.
 * - probe가 여러 대이면 `NUCODE_PROBE_UID`를 지정하고 Arduino Upload로 역할별 보드를 구분합니다.
 * - peer·외장 조건을 먼저 준비한 뒤 reset 또는 예제에 명시된 입력으로 실행합니다.
 * @par 성공 출력
 * - Serial 문구 `CIS bridge scanning`를 포함한 정상 상태 전이를 확인합니다.
 * - Serial 문구 `CIS bridge core revision=`를 포함한 정상 상태 전이를 확인합니다.
 * - Serial 문구 `CIS bridge broadcasting`를 포함한 정상 상태 전이를 확인합니다.
 * @par 흔한 오류
 * - 권장 profile과 sidecar가 다르면 기능·Kconfig가 빠질 수 있으므로 먼저 설정을 다시 확인합니다.
 * - 여러 probe가 연결된 상태에서 UID를 생략하면 다른 보드에 upload될 수 있습니다.
 * - `CIS bridge start failed:` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * - `CIS bridge receive error:` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * - `CIS bridge broadcast start failed:` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * @par 다음 예제
 * - `NUCODE_BLE_ISO/CISToBISPeer`
 * - `NUCODE_BLE_ISO/CISToBISReceiver`
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
 * Recipe `ble_iso`; 내부 증거 ID는 metadata에서 관리합니다.
 * 직접 upstream 복사 아님; NCS `99553055607b2e9885fbc80ccd11fa9da81c2df0`, Zephyr `bf801e4e3d19e1ffa76164346480cb7734dd2800`
 * build `clean_installed_compile_required`, runtime `procedure_documented_not_physical_pass`
 * @par Metadata
 * identity `NUCODE_BLE_ISO/CISToBISBridge`, sha256 `b006e939ad912fb50c9b4edb8d5a54f0d223c01ebfd2377cb341f457f63c12a2`
 * @nucode_example_setup_end */

/**
 * @file CISToBISBridge.ino
 * @brief CIS 사용자 SDU를 읽어 같은 payload를 BIS로 전달합니다.
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE_ISO.h>

using nucode::ble::iso::CisFrame;
using nucode::ble::iso::Error;
using nucode::ble::iso::RawBis;
using nucode::ble::iso::RawCis;
using nucode::ble::iso::Role;

namespace
{
    /** @brief peer 및 receiver와 각각 공유하는 16-byte 식별자입니다. */
    constexpr char cisSessionId[] = "NUCODE-C2B-CIS01";
    constexpr char bisSessionId[] = "NUCODE-C2B-BIS01";
    static_assert(sizeof(cisSessionId) == 17U, "CIS session ID must be 16 bytes");
    static_assert(sizeof(bisSessionId) == 17U, "BIS session ID must be 16 bytes");

    RawCis cis;
    RawBis bis;
    CisFrame pendingFrame = {};
    std::uint16_t cisReceived = 0U;
    std::uint16_t bisForwarded = 0U;
    std::uint16_t errors = 0U;
    std::uint32_t sessionMs = 0U;
    std::uint32_t lastForwardMs = 0U;
    std::uint32_t restartMs = 0U;
    bool running = false;
    bool bisStarted = false;
    bool framePending = false;
    bool closing = false;

    /** @brief CIS payload의 사용자 sequence와 검사 byte를 확인합니다. */
    bool validFrame(const CisFrame &frame, std::uint16_t &number)
    {
        if (frame.length != 8U || frame.data[0] != 'C' || frame.data[1] != 'B' ||
            frame.data[6] != 0xC1U || frame.data[7] != 0x52U)
        {
            return false;
        }
        number = static_cast<std::uint16_t>(frame.data[2]) |
                 (static_cast<std::uint16_t>(frame.data[3]) << 8U);
        return number < 100U &&
               frame.data[4] == static_cast<std::uint8_t>(number ^ 0x5AU) &&
               frame.data[5] == static_cast<std::uint8_t>((number >> 8U) ^ 0xA5U);
    }

    /** @brief 두 공개 API가 소유한 무선 자원의 해제를 시작합니다. */
    void stopSession()
    {
        if (bisStarted && !bis.stopped())
        {
            bis.stop();
        }
        if (!cis.stopped())
        {
            cis.stop();
        }
        closing = true;
    }

    /** @brief 같은 session의 CIS를 먼저 연결합니다. */
    void startSession()
    {
        const Error result = cis.begin(Role::cis_to_bis_bridge,
                                       reinterpret_cast<const std::uint8_t *>(cisSessionId));
        if (result != Error::none)
        {
            Serial.print("CIS bridge start failed: ");
            Serial.println(static_cast<unsigned>(result));
            restartMs = millis() + 1000U;
            return;
        }
        cisReceived = 0U;
        bisForwarded = 0U;
        errors = 0U;
        sessionMs = millis();
        lastForwardMs = 0U;
        bisStarted = false;
        framePending = false;
        running = true;
        closing = false;
        Serial.println("CIS bridge scanning");
    }
}

/** @brief 공개 API가 포함된 Core revision을 표시합니다. */
void setup()
{
    Serial.begin(115200);
    Serial.print("CIS bridge core revision=");
    Serial.println(RawCis::buildRevision());
    startSession();
}

/** @brief 한 CIS의 100개 사용자 SDU를 BIS에 그대로 전달합니다. */
void loop()
{
    if (!running)
    {
        if (static_cast<std::int32_t>(millis() - restartMs) >= 0)
        {
            startSession();
        }
        delay(1);
        return;
    }

    const Error cisProgress = cis.poll();
    if (!closing && cisProgress == Error::transport_failure)
    {
        Serial.print("CIS bridge receive error: ");
        Serial.println(cis.nativeError());
        stopSession();
    }
    if (!closing && !bisStarted && cis.connected())
    {
        const Error result = bis.begin(Role::cis_to_bis_bridge,
                                       reinterpret_cast<const std::uint8_t *>(bisSessionId));
        if (result != Error::none)
        {
            Serial.print("CIS bridge broadcast start failed: ");
            Serial.println(static_cast<unsigned>(result));
            stopSession();
        }
        else
        {
            bisStarted = true;
            Serial.println("CIS bridge broadcasting");
        }
    }
    if (bisStarted)
    {
        const Error bisProgress = bis.poll();
        if (!closing && bisProgress == Error::transport_failure)
        {
            Serial.print("CIS bridge broadcast error: ");
            Serial.println(bis.nativeError());
            stopSession();
        }
    }
    if (!closing && bisStarted && bis.connected() && !framePending &&
        cisReceived < 100U && cis.readFrame(pendingFrame))
    {
        std::uint16_t number = 0U;
        if (!validFrame(pendingFrame, number) || number != cisReceived)
        {
            ++errors;
            Serial.print("CIS bridge invalid frame: ");
            Serial.println(number);
            stopSession();
        }
        else
        {
            ++cisReceived;
            framePending = true;
        }
    }
    if (!closing && framePending)
    {
        const Error result = bis.sendFrame(pendingFrame.data, pendingFrame.length);
        if (result == Error::none)
        {
            ++bisForwarded;
            framePending = false;
            lastForwardMs = millis();
        }
        else if (result != Error::busy && result != Error::not_ready)
        {
            Serial.print("CIS bridge forward failed: ");
            Serial.println(static_cast<unsigned>(result));
            stopSession();
        }
    }
    if (!closing && bisForwarded == 100U && millis() - lastForwardMs >= 750U)
    {
        Serial.print("CIS bridge received=");
        Serial.print(cisReceived);
        Serial.print(" forwarded=");
        Serial.print(bisForwarded);
        Serial.print(" errors=");
        Serial.println(errors);
        stopSession();
    }
    if (!closing && millis() - sessionMs >= 15000U)
    {
        Serial.print("CIS bridge timeout received=");
        Serial.print(cisReceived);
        Serial.print(" forwarded=");
        Serial.println(bisForwarded);
        stopSession();
    }
    if (closing && cis.stopped() && (!bisStarted || bis.stopped()))
    {
        Serial.println("CIS bridge stopped");
        running = false;
        restartMs = millis() + 1000U;
    }
    delay(1);
}
