/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par 목적
 * 원격 Hearing Access preset을 읽고 선택하는 예제입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: Adaptive capabilities (experimental) (adaptive, 실험적 대안)
 * @par 보드와 역할
 * 2대 — 1) HearingAccessClient (client/controller); 2) HearingAccessServer (server/device)
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * nucode-build.json, prj.conf
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 추가 조건 없음
 * @par 준비물
 * - NU54DK 보드 2대 — 1) HearingAccessClient (client/controller); 2) HearingAccessServer (server/device)
 * @par 설정
 * - Tools → Feature set에서 `ble` profile을 선택합니다.
 * - Sketch 폴더의 sidecar를 함께 설치합니다: nucode-build.json, prj.conf
 * - Serial Monitor는 115200 baud로 엽니다.
 * @par 실행 순서
 * - 권장 profile로 현재 Sketch와 metadata에 적힌 각 peer 역할 Sketch를 빌드합니다.
 * - probe가 여러 대이면 `NUCODE_PROBE_UID`를 지정하고 Arduino Upload로 역할별 보드를 구분합니다.
 * - peer·외장 조건을 먼저 준비한 뒤 reset 또는 예제에 명시된 입력으로 실행합니다.
 * @par 성공 출력
 * - Serial 문구 `Hearing Access server found`를 포함한 정상 상태 전이를 확인합니다.
 * - Serial 문구 `Hearing Access server disconnected reason=`를 포함한 정상 상태 전이를 확인합니다.
 * - Serial 문구 `result=`를 포함한 정상 상태 전이를 확인합니다.
 * @par 흔한 오류
 * - 권장 profile과 sidecar가 다르면 기능·Kconfig가 빠질 수 있으므로 먼저 설정을 다시 확인합니다.
 * - 여러 probe가 연결된 상태에서 UID를 생략하면 다른 보드에 upload될 수 있습니다.
 * - `Hearing Access security request failed` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * - `Hearing Access client start failed` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * - `Commands: 1/5/8=select n=next p=previous r=read x=invalid y=sync c=clear bonds s=state` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * @par 다음 예제
 * - `NUCODE_BLE_Audio/HearingAccessServer`
 * - `NUCODE_BLE_Audio/Lc3SyntheticLoopback`
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
 * identity `NUCODE_BLE_Audio/HearingAccessClient`, sha256 `48bc21647a2e80b792cc32c5f1af602b3ed336ab6efed3153098324db52e8eb3`
 * @nucode_example_setup_end */

/**
 * @file HearingAccessClient.ino
 * @brief 원격 Hearing Access preset을 읽고 선택하는 예제입니다.
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
using nucode::ble::audio::Error;
using nucode::ble::audio::HearingAccessClient;
using nucode::ble::audio::HearingAccessStage;
using nucode::ble::audio::HearingPreset;

namespace
{
    HearingAccessClient hearingAccess;
    BLEAddress peerAddress;
    BLEConnectionHandle peerConnection;
    bool peerFound = false;
    bool profileStarted = false;
    bool profileAttempted = false;
    bool presetsRequested = false;
    std::uint32_t presetsReadAt = 0U;
    std::uint32_t profileStartAt = 0U;
    bool scanPending = false;
    std::uint32_t scanAt = 0U;
    std::uint32_t profileDeadline = 0U;
    constexpr std::uint32_t securitySettlingMs = 100U;
    constexpr std::uint32_t profileTimeoutMs = 10000U;

    /** @brief Hearing Access Service UUID를 광고하는 장치를 검색합니다. */
    bool startScan()
    {
        return BLEScan.clearFilters() && BLEScan.filterServiceUuid(BLEUuid(0x1854U)) &&
               BLEScan.start(true);
    }

    /** @brief 처음 발견한 connectable Hearing Access server를 선택합니다. */
    void onScanResult(const BLEScanResult &result, void *context)
    {
        static_cast<void>(context);
        if (!peerFound && result.connectable)
        {
            peerAddress = result.address;
            peerFound = true;
            static_cast<void>(BLEScan.stop());
            Serial.println("Hearing Access server found");
        }
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

    /** @brief 연결과 profile 수명을 결합하고 해제 뒤 재검색합니다. */
    void onBleEvent(const BLEEventInfo &event, void *context)
    {
        static_cast<void>(context);
        if ((event.event == BLEEvent::connected) && (event.role == BLELinkRole::central))
        {
            peerConnection = event.connection;
            profileAttempted = false;
            profileStartAt = 0U;
            if (!BLESecurity.requestSecurity(peerConnection))
            {
                Serial.println("Hearing Access security request failed");
            }
        }
        else if ((event.event == BLEEvent::disconnected) && (event.connection == peerConnection))
        {
            if (profileStarted)
            {
                static_cast<void>(hearingAccess.end());
            }
            peerConnection = BLEConnectionHandle();
            peerFound = false;
            profileStarted = false;
            profileAttempted = false;
            presetsRequested = false;
            presetsReadAt = 0U;
            profileStartAt = 0U;
            scanPending = true;
            scanAt = millis() + 100U;
            Serial.print("Hearing Access server disconnected reason=");
            Serial.println(event.reason);
        }
    }

    /** @brief 공개 API 결과와 HAS 원본 오류를 출력합니다. */
    void report(const char *operation, Error result)
    {
        Serial.print(operation);
        Serial.print(" result=");
        Serial.print(static_cast<unsigned int>(result));
        Serial.print(" native=");
        Serial.println(hearingAccess.nativeCode());
    }

    /** @brief 원격 preset cache와 active index를 출력합니다. */
    void printPresets()
    {
        Serial.print("active=");
        Serial.print(hearingAccess.activePreset());
        Serial.print(" presets=");
        Serial.println(hearingAccess.presetCount());
        for (std::size_t position = 0U; position < hearingAccess.presetCount(); ++position)
        {
            HearingPreset preset;
            if (hearingAccess.preset(position, preset) == Error::none)
            {
                Serial.print("preset index=");
                Serial.print(preset.index);
                Serial.print(" available=");
                Serial.print(preset.available ? 1 : 0);
                Serial.print(" writable=");
                Serial.print(preset.writable ? 1 : 0);
                Serial.print(" name=");
                Serial.println(preset.name);
            }
        }
    }
} // namespace

/** @brief central, security와 Hearing Access 검색을 시작합니다. */
void setup()
{
    Serial.begin(115200);

    SecurityConfig security;
    security.minimum_level = SecurityLevel::encrypted;
    security.bonding = true;
    security.io_capability = SecurityIoCapability::no_input_output;
    BLESecurity.onEvent(onSecurityEvent);
    BLEDevice.onEventInfo(onBleEvent);
    BLEScan.onResult(onScanResult);
    if (!BLESecurity.begin(security) || !BLEDevice.begin("NU54-HEARING-REMOTE") || !startScan())
    {
        Serial.println("Hearing Access client start failed");
    }
    Serial.println(
        "Commands: 1/5/8=select n=next p=previous r=read x=invalid y=sync c=clear bonds s=state");
}

/** @brief discovery와 사용자가 선택한 원격 preset 절차를 진행합니다. */
void loop()
{
    BLEDevice.poll();
    BLESecurity.poll();
    hearingAccess.poll();

    if (peerConnection.valid() && !profileStarted && !profileAttempted &&
        (BLESecurity.currentLevel(peerConnection) >= SecurityLevel::encrypted))
    {
        if (profileStartAt == 0U)
        {
            profileStartAt = millis() + securitySettlingMs;
        }
        else if (static_cast<std::int32_t>(millis() - profileStartAt) >= 0)
        {
            profileAttempted = true;
            const Error result = hearingAccess.begin(peerConnection);
            if (result == Error::none)
            {
                profileStarted = true;
                profileDeadline = millis() + profileTimeoutMs;
                Serial.println("Hearing Access discovery started");
            }
            else
            {
                Serial.print("Hearing Access discovery failed native=");
                Serial.println(hearingAccess.nativeCode());
                if (BLEConnection.disconnect(peerConnection))
                {
                    Serial.println("Hearing Access recovery requested");
                }
            }
        }
    }

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
            Serial.println("Hearing Access connect failed");
        }
    }

    if (profileStarted && hearingAccess.ready() && !presetsRequested && (presetsReadAt == 0U))
    {
        presetsReadAt = millis() + 500U;
    }
    if (profileStarted && hearingAccess.ready() && !presetsRequested && (presetsReadAt != 0U) &&
        (static_cast<std::int32_t>(millis() - presetsReadAt) >= 0))
    {
        const Error result = hearingAccess.readPresets();
        report("Read presets", result);
        presetsRequested = result == Error::none;
    }
    if (profileStarted && !hearingAccess.ready() &&
        (static_cast<std::int32_t>(millis() - profileDeadline) >= 0) &&
        (hearingAccess.stage() != HearingAccessStage::operating))
    {
        const HearingAccessStage stage = hearingAccess.stage();
        Serial.print("Hearing Access profile timeout stage=");
        Serial.print(static_cast<unsigned int>(stage));
        Serial.print(" native=");
        Serial.println(hearingAccess.nativeCode());
        if ((stage == HearingAccessStage::failed) && BLEConnection.disconnect(peerConnection))
        {
            Serial.println("Hearing Access recovery requested");
        }
        profileDeadline = millis() + profileTimeoutMs;
    }

    while (Serial.available() > 0)
    {
        const char command = static_cast<char>(Serial.read());
        if ((command == '1') || (command == '5') || (command == '8'))
        {
            report("Select preset",
                   hearingAccess.setActivePreset(static_cast<std::uint8_t>(command - '0')));
        }
        else if (command == 'n')
        {
            report("Next preset", hearingAccess.nextPreset());
        }
        else if (command == 'p')
        {
            report("Previous preset", hearingAccess.previousPreset());
        }
        else if (command == 'r')
        {
            report("Read presets", hearingAccess.readPresets());
        }
        else if (command == 'x')
        {
            report("Invalid preset", hearingAccess.setActivePreset(0U));
        }
        else if (command == 'y')
        {
            report("Synchronized preset", hearingAccess.setActivePreset(5U, true));
        }
        else if (command == 'c')
        {
            const bool accepted = BLESecurity.eraseAllBonds();
            const std::size_t remaining = BLESecurity.bondCount();
            Serial.print("Hearing bond cleanup result=");
            Serial.print(accepted ? 1 : 0);
            Serial.print(" remaining=");
            Serial.println(remaining);
        }
        else if (command == 's')
        {
            printPresets();
        }
    }

    static HearingAccessStage previousStage = HearingAccessStage::idle;
    const HearingAccessStage currentStage = hearingAccess.stage();
    if ((currentStage == HearingAccessStage::failed) && (currentStage != previousStage))
    {
        Serial.print("Hearing Access operation rejected step=");
        Serial.print(static_cast<unsigned int>(hearingAccess.lastStep()));
        Serial.print(" error=");
        Serial.print(static_cast<unsigned int>(hearingAccess.lastError()));
        Serial.print(" native=");
        Serial.println(hearingAccess.nativeCode());
    }
    previousStage = currentStage;

    static std::uint32_t updates = 0U;
    if (updates != hearingAccess.stateUpdates())
    {
        updates = hearingAccess.stateUpdates();
        printPresets();
    }
    delay(1U);
}
