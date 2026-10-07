/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par 목적
 * BASS Scan Delegator에 broadcast source를 추가하고 상태를 확인합니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: Adaptive capabilities (experimental) (adaptive, 실험적 대안)
 * @par 보드와 역할
 * 3대 — 1) BapBroadcastSource (source/transmitter); 2) BapBroadcastAssistant 실행 보드; 3) BapBroadcastDelegatorSink (sink/receiver)
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * nucode-build.json, prj.conf
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 추가 조건 없음
 * @par 준비물
 * - NU54DK 보드 3대 — 1) BapBroadcastSource (source/transmitter); 2) BapBroadcastAssistant 실행 보드; 3) BapBroadcastDelegatorSink (sink/receiver)
 * @par 설정
 * - Tools → Feature set에서 `ble` profile을 선택합니다.
 * - Sketch 폴더의 sidecar를 함께 설치합니다: nucode-build.json, prj.conf
 * - Serial Monitor는 115200 baud로 엽니다.
 * @par 실행 순서
 * - 권장 profile로 현재 Sketch와 metadata에 적힌 각 peer 역할 Sketch를 빌드합니다.
 * - probe가 여러 대이면 `NUCODE_PROBE_UID`를 지정하고 Arduino Upload로 역할별 보드를 구분합니다.
 * - peer·외장 조건을 먼저 준비한 뒤 reset 또는 예제에 명시된 입력으로 실행합니다.
 * @par 성공 출력
 * - Serial 문구 `broadcast delegator found`를 포함한 정상 상태 전이를 확인합니다.
 * - Serial 문구 `broadcast source selected`를 포함한 정상 상태 전이를 확인합니다.
 * - Serial 문구 `BASS discovery started`를 포함한 정상 상태 전이를 확인합니다.
 * @par 흔한 오류
 * - 권장 profile과 sidecar가 다르면 기능·Kconfig가 빠질 수 있으므로 먼저 설정을 다시 확인합니다.
 * - 여러 probe가 연결된 상태에서 UID를 생략하면 다른 보드에 upload될 수 있습니다.
 * - `BASS discovery start failed:` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * - `delegator parameter request failed` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * - `delegator security request failed` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * @par 다음 예제
 * - `NUCODE_BLE_Audio/BapBroadcastDelegatorSink`
 * - `NUCODE_BLE_Audio/BapBroadcastSink`
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
 * identity `NUCODE_BLE_Audio/BapBroadcastAssistant`, sha256 `5032bb387495551e4e584eafb9143c16413e80f183a54e21a73310428bb8cb3d`
 * @nucode_example_setup_end */

/**
 * @file BapBroadcastAssistant.ino
 * @brief BASS Scan Delegator에 broadcast source를 추가하고 상태를 확인합니다.
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
using nucode::ble::audio::BroadcastAssistant;
using nucode::ble::audio::BroadcastAssistantStage;
using nucode::ble::audio::BroadcastAssistantStep;
using nucode::ble::audio::BroadcastCode;
using nucode::ble::audio::Error;

namespace
{
    enum class ScanTarget : std::uint8_t
    {
        delegator,
        source,
        none,
    };

    constexpr BroadcastCode broadcastCode = {
        0x4e, 0x55, 0x35, 0x34, 0x2d, 0x41, 0x55, 0x44,
        0x49, 0x4f, 0x2d, 0x43, 0x4f, 0x44, 0x45, 0x31,
    };
    BroadcastAssistant assistant;
    BLEAddress delegatorAddress;
    BLEConnectionHandle delegatorConnection;
    ScanTarget scanTarget = ScanTarget::delegator;
    BroadcastAssistantStage previousStage = BroadcastAssistantStage::idle;
    bool delegatorFound = false;
    bool sourceSelected = false;
    bool sourceScanStarted = false;
    bool addPending = false;
    bool codePending = false;
    bool assistantStarted = false;
    bool delegatorScanPending = false;
    std::uint32_t delegatorScanAt = 0U;

    /** @brief BASS service를 광고하는 Scan Delegator 검색을 시작합니다. */
    bool startDelegatorScan()
    {
        scanTarget = ScanTarget::delegator;
        return BLEScan.clearFilters() &&
               BLEScan.filterServiceUuid(BLEUuid(0x184FU)) &&
               BLEScan.start(true);
    }

    /** @brief 현재 검색 단계에 맞는 Delegator 또는 Broadcast Source를 선택합니다. */
    void onScanResult(const BLEScanResult &result, void *context)
    {
        static_cast<void>(context);
        if ((scanTarget == ScanTarget::delegator) && result.connectable)
        {
            delegatorAddress = result.address;
            delegatorFound = true;
            scanTarget = ScanTarget::none;
            static_cast<void>(BLEScan.stop());
            Serial.println("broadcast delegator found");
        }
        else if ((scanTarget == ScanTarget::source) && !result.connectable &&
                 (assistant.selectSource(result) == Error::none))
        {
            sourceSelected = true;
            addPending = true;
            scanTarget = ScanTarget::none;
            static_cast<void>(BLEScan.stop());
            Serial.println("broadcast source selected");
        }
    }

    /** @brief encrypted 연결이 준비되면 BASS 검색을 시작합니다. */
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
                 (event.connection == delegatorConnection) && !assistantStarted)
        {
            const Error result = assistant.begin(delegatorConnection);
            if (result == Error::none)
            {
                assistantStarted = true;
                Serial.println("BASS discovery started");
            }
            else
            {
                Serial.print("BASS discovery start failed: ");
                Serial.println(assistant.nativeCode());
            }
        }
    }

    /** @brief BLE link 수명에 security와 Assistant 수명을 결합합니다. */
    void onBleEvent(const BLEEventInfo &event, void *context)
    {
        static_cast<void>(context);
        if ((event.event == BLEEvent::connected) &&
            (event.role == BLELinkRole::central))
        {
            delegatorConnection = event.connection;
            if (!BLEConnection.requestParameters(delegatorConnection, 24U, 40U,
                                                  0U, 2000U))
            {
                Serial.println("delegator parameter request failed");
            }
            if (!BLESecurity.requestSecurity(delegatorConnection))
            {
                Serial.println("delegator security request failed");
            }
        }
        else if ((event.event == BLEEvent::disconnected) &&
                 (event.connection == delegatorConnection))
        {
            if (assistantStarted)
            {
                static_cast<void>(assistant.end());
            }
            assistantStarted = false;
            delegatorConnection = BLEConnectionHandle();
            delegatorFound = false;
            sourceSelected = false;
            sourceScanStarted = false;
            addPending = false;
            codePending = false;
            delegatorScanPending = true;
            delegatorScanAt = millis() + 100U;
            Serial.print("broadcast delegator disconnected reason=");
            Serial.println(event.reason);
        }
    }

    /** @brief operation 시작 결과와 원본 오류를 한 형식으로 출력합니다. */
    void reportRequest(const char *name, Error result)
    {
        Serial.print(name);
        Serial.print(": ");
        Serial.print(static_cast<unsigned int>(result));
        Serial.print(" native=");
        Serial.println(assistant.nativeCode());
    }
} // namespace

/** @brief security와 공개 BLE 검색을 시작합니다. */
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
    if (!BLESecurity.begin(security) || !BLEDevice.begin("NU54-AUDIO-ASSISTANT") ||
        !startDelegatorScan())
    {
        Serial.println("broadcast assistant start failed");
    }
}

/** @brief BASS add/code/modify/remove 명령과 receive state 변화를 진행합니다. */
void loop()
{
    BLEDevice.poll();
    BLESecurity.poll();

    if (delegatorScanPending && !BLEConnection.connected() &&
        !BLEConnection.connecting() &&
        (static_cast<std::int32_t>(millis() - delegatorScanAt) >= 0))
    {
        if (startDelegatorScan())
        {
            delegatorScanPending = false;
            Serial.println("broadcast delegator scan restarted");
        }
        else
        {
            delegatorScanAt = millis() + 1000U;
            Serial.println("broadcast delegator scan restart failed");
        }
    }

    if (delegatorFound && !BLEConnection.connected() && !BLEConnection.connecting())
    {
        delegatorFound = false;
        if (!BLEConnection.connect(delegatorAddress, delegatorConnection))
        {
            Serial.println("broadcast delegator connect failed");
        }
    }

    const BroadcastAssistantStage stage = assistant.stage();
    if (stage != previousStage)
    {
        previousStage = stage;
        Serial.print("assistant stage=");
        Serial.print(static_cast<unsigned int>(stage));
        Serial.print(" step=");
        Serial.print(static_cast<unsigned int>(assistant.lastStep()));
        Serial.print(" native=");
        Serial.println(assistant.nativeCode());
    }
    if (assistantStarted && (stage == BroadcastAssistantStage::ready) &&
        !sourceScanStarted && !sourceSelected)
    {
        sourceScanStarted = true;
        scanTarget = ScanTarget::source;
        if (!BLEScan.clearFilters() || !BLEScan.startExtended(false, false, false))
        {
            Serial.println("broadcast source scan failed");
        }
        else
        {
            Serial.println("broadcast source scan started");
        }
    }
    if (addPending && (stage == BroadcastAssistantStage::ready))
    {
        addPending = false;
        reportRequest("BASS add source", assistant.addSource());
    }
    if (assistant.hasSource() && !codePending &&
        (stage == BroadcastAssistantStage::ready))
    {
        codePending = true;
        reportRequest("BASS broadcast code", assistant.setBroadcastCode(broadcastCode));
    }

    while (Serial.available() > 0)
    {
        const char command = static_cast<char>(Serial.read());
        if (command == 'a')
        {
            reportRequest("BASS duplicate add", assistant.addSource());
        }
        else if (command == 'm')
        {
            reportRequest("BASS stop source", assistant.modifySource(false));
        }
        else if (command == 'r')
        {
            if (assistant.hasSource())
            {
                reportRequest("BASS resume source", assistant.modifySource(true));
            }
            else
            {
                reportRequest("BASS re-add source", assistant.addSource());
                codePending = false;
            }
        }
        else if (command == 'd')
        {
            reportRequest("BASS remove source", assistant.removeSource());
            codePending = false;
        }
        else if (command == 'x')
        {
            BLEScanResult invalidSource;
            reportRequest("BASS invalid source", assistant.selectSource(invalidSource));
        }
    }

    static std::uint32_t reportedUpdates = 0U;
    if (assistant.stateUpdates() != reportedUpdates)
    {
        reportedUpdates = assistant.stateUpdates();
        Serial.print("receive state update=");
        Serial.print(reportedUpdates);
        Serial.print(" source=");
        Serial.print(assistant.hasSource() ? assistant.sourceId() : 255U);
        Serial.print(" pa=");
        Serial.print(assistant.periodicSynchronized() ? 1 : 0);
        Serial.print(" bis=");
        Serial.println(assistant.bisSynchronized() ? 1 : 0);
    }
    delay(1U);
}
