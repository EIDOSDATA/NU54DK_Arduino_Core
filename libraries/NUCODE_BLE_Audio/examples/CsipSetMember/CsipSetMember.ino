/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par 목적
 * Serial로 rank를 고른 뒤 CSIS Member를 광고하고 잠금 상태를 표시합니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: Adaptive capabilities (experimental) (adaptive, 실험적 대안)
 * @par 보드와 역할
 * 2대 — 1) CsipSetCoordinator (coordinator); 2) CsipSetMember (set member)
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * nucode-build.json, prj.conf
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 추가 조건 없음
 * @par 준비물
 * - NU54DK 보드 2대 — 1) CsipSetCoordinator (coordinator); 2) CsipSetMember (set member)
 * @par 설정
 * - Tools → Feature set에서 `ble` profile을 선택합니다.
 * - Sketch 폴더의 sidecar를 함께 설치합니다: nucode-build.json, prj.conf
 * - Serial Monitor는 115200 baud로 엽니다.
 * @par 실행 순서
 * - 권장 profile로 현재 Sketch와 metadata에 적힌 각 peer 역할 Sketch를 빌드합니다.
 * - probe가 여러 대이면 `NUCODE_PROBE_UID`를 지정하고 Arduino Upload로 역할별 보드를 구분합니다.
 * - peer·외장 조건을 먼저 준비한 뒤 reset 또는 예제에 명시된 입력으로 실행합니다.
 * @par 성공 출력
 * - Serial 문구 `Enter this member rank (1 or 2):`를 포함한 정상 상태 전이를 확인합니다.
 * - Serial 문구 `Set member bonded; physically verify the controller, then send a`를 포함한 정상 상태 전이를 확인합니다.
 * - Serial 문구 `Set member ready; send a to authorize SIRK read, f to force-release`를 포함한 정상 상태 전이를 확인합니다.
 * @par 흔한 오류
 * - 권장 profile과 sidecar가 다르면 기능·Kconfig가 빠질 수 있으므로 먼저 설정을 다시 확인합니다.
 * - 여러 probe가 연결된 상태에서 UID를 생략하면 다른 보드에 upload될 수 있습니다.
 * - `Set member start failed:` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * - `Set SIRK read authorization revoke failed` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * - `Set member pairing approval failed` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * @par 다음 예제
 * - `NUCODE_BLE_Audio/ExternalI2sSpeakerSink`
 * - `NUCODE_BLE_Audio/ExternalPdmMicrophoneSource`
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
 * identity `NUCODE_BLE_Audio/CsipSetMember`, sha256 `cead2aa69963e42e49939750acba8c34b9aa63d76a9181c15c338879af2b53d9`
 * @nucode_example_setup_end */

/**
 * @file CsipSetMember.ino
 * @brief Serial로 rank를 고른 뒤 CSIS Member를 광고하고 잠금 상태를 표시합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE.h>
#include <NUCODE_BLE_Audio.h>
#include <NUCODE_BLE_Security.h>

namespace
{
    nucode::ble::audio::CsipSetMember setMember;
    nucode::ble::BLEConnectionHandle activeConnection;
    nucode::ble::BLEConnectionHandle authorizationCandidate;
    std::uint32_t reportedLockChanges = 0U;
    std::uint32_t securityDeadlineMs = 0U;
    std::uint32_t recoveryRetryMs = 0U;
    std::uint32_t disconnectDeadlineMs = 0U;
    bool recoveryPending = false;
    bool disconnectPending = false;
    bool advertisingRestartPending = false;

    constexpr std::uint32_t securityTimeoutMs = 30000U;
    constexpr std::uint32_t disconnectTimeoutMs = 5000U;
    constexpr std::uint32_t recoveryRetryMsValue = 250U;

    /** @brief 이 고정 키는 로컬 상호운용 시험 전용이며 제품에는 고유 비밀을 주입해야 합니다. */
    constexpr nucode::ble::audio::CsipSetKey setKey = {{
        0x91U, 0x72U, 0x44U, 0x13U, 0xa8U, 0x5cU, 0x2dU, 0xe1U,
        0x0bU, 0x6fU, 0xc3U, 0x39U, 0x57U, 0x8aU, 0xd4U, 0x20U,
    }};

    /** @brief 실패 단계를 출력하고 불완전한 실행을 막습니다. */
    void require(bool condition, const char *stage)
    {
        if (condition)
        {
            return;
        }
        Serial.print("Set member start failed: ");
        Serial.println(stage);
        while (true)
        {
            delay(1000U);
        }
    }

    /** @brief 매 광고 시작마다 새 RSI로 payload를 교체합니다. */
    bool startMemberAdvertising()
    {
        std::uint8_t rsi[6] = {};
        return setMember.generateRsi(rsi) == nucode::ble::audio::Error::none &&
               BLEAdvertising.clear() &&
               BLEAdvertising.addServiceUuid(nucode::ble::BLEUuid(0x1846U)) &&
               BLEAdvertising.setResolvableSetIdentifier(rsi) && BLEAdvertising.start();
    }

    /** @brief 현재 exact link를 보안 실패 복구 대상으로 표시합니다. */
    void requestConnectionRecovery(const nucode::ble::BLEConnectionHandle &connection)
    {
        if (activeConnection == connection)
        {
            securityDeadlineMs = 0U;
            recoveryPending = true;
            recoveryRetryMs = millis();
        }
    }

    /** @brief 두 member가 같은 sketch에서 서로 다른 rank를 선택하게 합니다. */
    std::uint8_t chooseRank()
    {
        Serial.println("Enter this member rank (1 or 2):");
        while (true)
        {
            if (Serial.available() != 0)
            {
                const int value = Serial.read();
                if (value == '1' || value == '2')
                {
                    return static_cast<std::uint8_t>(value - '0');
                }
            }
            delay(1U);
        }
    }

    /** @brief coordinator가 시작하는 bonded encryption을 bounded wait합니다. */
    void onBleEvent(const nucode::ble::BLEEventInfo &information, void *context)
    {
        static_cast<void>(context);
        if (information.event == nucode::ble::BLEEvent::connected)
        {
            activeConnection = information.connection;
            authorizationCandidate = {};
            recoveryPending = false;
            disconnectPending = false;
            advertisingRestartPending = false;
            securityDeadlineMs = millis() + securityTimeoutMs;
        }
        else if (information.event == nucode::ble::BLEEvent::disconnected)
        {
            if (authorizationCandidate == information.connection)
            {
                if (setMember.authorizeSirkRead(information.connection, false) !=
                    nucode::ble::audio::Error::none)
                {
                    Serial.println("Set SIRK read authorization revoke failed");
                }
                authorizationCandidate = {};
            }
            if (activeConnection == information.connection)
            {
                activeConnection = {};
                securityDeadlineMs = 0U;
                recoveryPending = false;
                disconnectPending = false;
                disconnectDeadlineMs = 0U;
                advertisingRestartPending = true;
                recoveryRetryMs = millis();
            }
        }
    }

    /** @brief Just Works 요청을 승인하고 bonding 결과를 표시합니다. */
    void onSecurityEvent(const nucode::ble::SecurityEventRecord &record, void *context)
    {
        static_cast<void>(context);
        if (record.event == nucode::ble::SecurityEvent::pairing_requested)
        {
            if (!BLESecurity.acceptPairing(record.connection, true))
            {
                Serial.println("Set member pairing approval failed");
                requestConnectionRecovery(record.connection);
            }
        }
        else if (record.event == nucode::ble::SecurityEvent::paired ||
                 record.event == nucode::ble::SecurityEvent::bond_verified)
        {
            if (record.connection == activeConnection && !recoveryPending &&
                !disconnectPending)
            {
                securityDeadlineMs = 0U;
                authorizationCandidate = record.connection;
                Serial.println("Set member bonded; physically verify the controller, then send a");
            }
        }
        else if (record.connection == activeConnection &&
                 (record.event == nucode::ble::SecurityEvent::pairing_failed ||
                  record.event == nucode::ble::SecurityEvent::pairing_cancelled ||
                  record.event == nucode::ble::SecurityEvent::timeout ||
                  record.event == nucode::ble::SecurityEvent::error))
        {
            Serial.println("Set member security failed");
            requestConnectionRecovery(record.connection);
        }
    }
} // namespace

void setup()
{
    Serial.begin(115200);
    const std::uint8_t rank = chooseRank();

    nucode::ble::SecurityConfig security{};
    security.minimum_level = nucode::ble::SecurityLevel::encrypted;
    security.bonding = true;
    security.io_capability = nucode::ble::SecurityIoCapability::no_input_output;
    BLESecurity.onEvent(onSecurityEvent);
    BLEDevice.onEventInfo(onBleEvent);

    require(BLESecurity.begin(security), "security");
    require(BLEDevice.begin(rank == 1U ? "NU54-SET-ONE" : "NU54-SET-TWO"), "device");

    nucode::ble::audio::CsipMemberConfig member{};
    member.key = setKey;
    member.set_size = 2U;
    member.rank = rank;
    member.lockable = true;
    require(setMember.begin(member) == nucode::ble::audio::Error::none, "member");

    require(startMemberAdvertising(), "advertising-start");
    Serial.println("Set member ready; send a to authorize SIRK read, f to force-release");
    Serial.println("Provision a unique secret before using this outside a local test setup");
}

void loop()
{
    BLEDevice.poll();
    BLESecurity.poll();

    if (securityDeadlineMs != 0U &&
        static_cast<std::int32_t>(millis() - securityDeadlineMs) >= 0)
    {
        Serial.println("Set member security timeout");
        requestConnectionRecovery(activeConnection);
    }
    if (disconnectPending &&
        static_cast<std::int32_t>(millis() - disconnectDeadlineMs) >= 0)
    {
        Serial.println("Set member recovery disconnect timeout");
        disconnectPending = false;
        recoveryPending = true;
        recoveryRetryMs = millis();
    }
    if (recoveryPending && !disconnectPending &&
        static_cast<std::int32_t>(millis() - recoveryRetryMs) >= 0)
    {
        if (activeConnection.valid() && BLEConnection.connected(activeConnection))
        {
            if (BLEConnection.disconnect(activeConnection))
            {
                disconnectPending = true;
                disconnectDeadlineMs = millis() + disconnectTimeoutMs;
                recoveryPending = false;
            }
            else
            {
                Serial.println("Set member recovery disconnect failed");
                recoveryRetryMs = millis() + recoveryRetryMsValue;
            }
        }
        else
        {
            activeConnection = {};
            recoveryPending = false;
            advertisingRestartPending = true;
            recoveryRetryMs = millis();
        }
    }
    if (advertisingRestartPending &&
        static_cast<std::int32_t>(millis() - recoveryRetryMs) >= 0)
    {
        if (BLEAdvertising.running() || startMemberAdvertising())
        {
            advertisingRestartPending = false;
        }
        else
        {
            Serial.println("Set member advertising restart failed");
            recoveryRetryMs = millis() + recoveryRetryMsValue;
        }
    }

    if (setMember.lockChanges() != reportedLockChanges)
    {
        reportedLockChanges = setMember.lockChanges();
        Serial.println(setMember.locked() ? "Set locked" : "Set released");
    }
    if (Serial.available() != 0)
    {
        const int command = Serial.read();
        if (command == 'a' && authorizationCandidate.valid())
        {
            if (setMember.authorizeSirkRead(authorizationCandidate) !=
                nucode::ble::audio::Error::none)
            {
                Serial.println("Set SIRK read authorization failed");
            }
            else
            {
                Serial.println("Bonded controller identity authorized");
            }
        }
        else if (command == 'f' &&
                 setMember.forceRelease() != nucode::ble::audio::Error::none)
        {
            Serial.println("Set force release failed");
        }
    }
    delay(1U);
}
