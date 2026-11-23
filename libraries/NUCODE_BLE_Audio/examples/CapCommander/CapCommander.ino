/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par 목적
 * CAP Acceptor의 암호화 broadcast 수신 절차를 제어합니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: Adaptive capabilities (experimental) (adaptive, 실험적 대안)
 * @par 보드와 역할
 * 2대 — 1) CapCommander (commander); 2) CapAcceptor (acceptor)
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * nucode-build.json, prj.conf
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 추가 조건 없음
 * @par 준비물
 * - NU54DK 보드 2대 — 1) CapCommander (commander); 2) CapAcceptor (acceptor)
 * @par 설정
 * - Tools → Feature set에서 `ble` profile을 선택합니다.
 * - Sketch 폴더의 sidecar를 함께 설치합니다: nucode-build.json, prj.conf
 * - Serial Monitor는 115200 baud로 엽니다.
 * @par 실행 순서
 * - 권장 profile로 현재 Sketch와 metadata에 적힌 각 peer 역할 Sketch를 빌드합니다.
 * - probe가 여러 대이면 `NUCODE_PROBE_UID`를 지정하고 Arduino Upload로 역할별 보드를 구분합니다.
 * - peer·외장 조건을 먼저 준비한 뒤 reset 또는 예제에 명시된 입력으로 실행합니다.
 * @par 성공 출력
 * - Serial 문구 `CAP acceptor found`를 포함한 정상 상태 전이를 확인합니다.
 * - Serial 문구 `CAP broadcast source selected`를 포함한 정상 상태 전이를 확인합니다.
 * - Serial 문구 `CAP discovery started`를 포함한 정상 상태 전이를 확인합니다.
 * @par 흔한 오류
 * - 권장 profile과 sidecar가 다르면 기능·Kconfig가 빠질 수 있으므로 먼저 설정을 다시 확인합니다.
 * - 여러 probe가 연결된 상태에서 UID를 생략하면 다른 보드에 upload될 수 있습니다.
 * - `CAP discovery start failed:` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * - `CAP connection parameter request failed` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * - `CAP security request failed` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * @par 다음 예제
 * - `NUCODE_BLE_Audio/CapInitiator`
 * - `NUCODE_BLE_Audio/CapUnicastAcceptor`
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
 * identity `NUCODE_BLE_Audio/CapCommander`, sha256 `6807d9d622dd167572d4be1007d978a7e614c95c4c618a781e1e22d98e58ffbd`
 * @nucode_example_setup_end */

/**
 * @file CapCommander.ino
 * @brief CAP Acceptor의 암호화 broadcast 수신 절차를 제어합니다.
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
using nucode::ble::audio::BroadcastCode;
using nucode::ble::audio::CapCommander;
using nucode::ble::audio::CapStage;
using nucode::ble::audio::Error;

namespace
{
    enum class ScanTarget : std::uint8_t
    {
        acceptor,
        source,
        none,
    };

    constexpr BroadcastCode broadcastCode = {
        0x4e, 0x55, 0x35, 0x34, 0x2d, 0x43, 0x41, 0x50,
        0x2d, 0x43, 0x4f, 0x44, 0x45, 0x2d, 0x30, 0x31,
    };
    CapCommander commander;
    BLEAddress acceptorAddress;
    BLEConnectionHandle acceptorConnection;
    ScanTarget scanTarget = ScanTarget::acceptor;
    CapStage previousStage = CapStage::idle;
    bool acceptorFound = false;
    bool sourceSelected = false;
    bool sourceScanStarted = false;
    bool startPending = false;
    bool codePending = false;
    bool commanderStarted = false;
    bool acceptorScanPending = false;
    std::uint32_t acceptorScanAt = 0U;
    bool streamWasSynchronized = false;
    bool lossStopPending = false;
    bool lossRemovePending = false;
    bool sourceRescanPending = false;

    /** @brief 현재 source 선택을 비우고 새 broadcast 광고 검색을 준비합니다. */
    void prepareSourceScan()
    {
        sourceSelected = false;
        sourceScanStarted = false;
        startPending = false;
        codePending = false;
        streamWasSynchronized = false;
        sourceRescanPending = false;
    }

    /** @brief Common Audio Service를 광고하는 Acceptor 검색을 시작합니다. */
    bool startAcceptorScan()
    {
        scanTarget = ScanTarget::acceptor;
        return BLEScan.clearFilters() &&
               BLEScan.filterServiceUuid(BLEUuid(0x1853U)) && BLEScan.start(true);
    }

    /** @brief 현재 단계에 맞는 CAP Acceptor 또는 Broadcast Source를 선택합니다. */
    void onScanResult(const BLEScanResult &result, void *context)
    {
        static_cast<void>(context);
        if ((scanTarget == ScanTarget::acceptor) && result.connectable)
        {
            acceptorAddress = result.address;
            acceptorFound = true;
            scanTarget = ScanTarget::none;
            static_cast<void>(BLEScan.stop());
            Serial.println("CAP acceptor found");
        }
        else if ((scanTarget == ScanTarget::source) && !result.connectable &&
                 (commander.selectSource(result) == Error::none))
        {
            sourceSelected = true;
            startPending = true;
            scanTarget = ScanTarget::none;
            static_cast<void>(BLEScan.stop());
            Serial.println("CAP broadcast source selected");
        }
    }

    /** @brief encrypted 연결이 준비되면 CAP discovery를 시작합니다. */
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
                 (event.connection == acceptorConnection) && !commanderStarted)
        {
            const Error result = commander.begin(acceptorConnection);
            if (result == Error::none)
            {
                commanderStarted = true;
                Serial.println("CAP discovery started");
            }
            else
            {
                Serial.print("CAP discovery start failed: ");
                Serial.println(commander.nativeCode());
            }
        }
    }

    /** @brief BLE link 수명에 security와 Commander 수명을 결합합니다. */
    void onBleEvent(const BLEEventInfo &event, void *context)
    {
        static_cast<void>(context);
        if ((event.event == BLEEvent::connected) &&
            (event.role == BLELinkRole::central))
        {
            acceptorConnection = event.connection;
            if (!BLEConnection.requestParameters(acceptorConnection, 24U, 40U,
                                                  0U, 2000U))
            {
                Serial.println("CAP connection parameter request failed");
            }
            if (!BLESecurity.requestSecurity(acceptorConnection))
            {
                Serial.println("CAP security request failed");
            }
        }
        else if ((event.event == BLEEvent::disconnected) &&
                 (event.connection == acceptorConnection))
        {
            if (commanderStarted)
            {
                static_cast<void>(commander.end());
            }
            commanderStarted = false;
            acceptorConnection = BLEConnectionHandle();
            acceptorFound = false;
            prepareSourceScan();
            lossStopPending = false;
            lossRemovePending = false;
            sourceRescanPending = false;
            acceptorScanPending = true;
            acceptorScanAt = millis() + 100U;
            Serial.print("CAP acceptor disconnected reason=");
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
        Serial.println(commander.nativeCode());
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
    if (!BLESecurity.begin(security) || !BLEDevice.begin("NU54-CAP-COMMANDER") ||
        !startAcceptorScan())
    {
        Serial.println("CAP commander start failed");
    }
}

/** @brief CAP discovery·수신 시작·code 배포·중단·제거 절차를 진행합니다. */
void loop()
{
    BLEDevice.poll();
    BLESecurity.poll();

    if (acceptorScanPending && !BLEConnection.connected() &&
        !BLEConnection.connecting() &&
        (static_cast<std::int32_t>(millis() - acceptorScanAt) >= 0))
    {
        if (startAcceptorScan())
        {
            acceptorScanPending = false;
            Serial.println("CAP acceptor scan restarted");
        }
        else
        {
            acceptorScanAt = millis() + 1000U;
            Serial.println("CAP acceptor scan restart failed");
        }
    }

    if (acceptorFound && !BLEConnection.connected() && !BLEConnection.connecting())
    {
        acceptorFound = false;
        if (!BLEConnection.connect(acceptorAddress, acceptorConnection))
        {
            Serial.println("CAP acceptor connect failed");
        }
    }

    const CapStage stage = commander.stage();
    if (stage != previousStage)
    {
        previousStage = stage;
        Serial.print("CAP commander stage=");
        Serial.print(static_cast<unsigned int>(stage));
        Serial.print(" step=");
        Serial.print(static_cast<unsigned int>(commander.lastStep()));
        Serial.print(" native=");
        Serial.println(commander.nativeCode());
    }
    if ((stage == CapStage::failed) &&
        (lossStopPending || lossRemovePending || sourceRescanPending))
    {
        if (BLEConnection.disconnect(acceptorConnection))
        {
            lossStopPending = false;
            lossRemovePending = false;
            sourceRescanPending = false;
            streamWasSynchronized = false;
            Serial.println("CAP recovery link restart");
        }
        else
        {
            Serial.println("CAP recovery link restart failed");
        }
    }
    if (lossStopPending && commander.ready())
    {
        const Error result = commander.stopReception();
        reportRequest("CAP recovery stop", result);
        if (result == Error::none)
        {
            lossStopPending = false;
            lossRemovePending = true;
        }
    }
    if (lossRemovePending && commander.ready() &&
        !commander.periodicSynchronized() && !commander.bisSynchronized())
    {
        const Error result = commander.removeSource();
        reportRequest("CAP recovery remove", result);
        if ((result == Error::none) || (result == Error::not_ready))
        {
            lossRemovePending = false;
            if (result == Error::none)
            {
                sourceRescanPending = true;
            }
            else
            {
                prepareSourceScan();
                Serial.println("CAP recovery source rescan pending");
            }
        }
    }
    if (sourceRescanPending && commander.ready() && !commander.hasSource())
    {
        prepareSourceScan();
        Serial.println("CAP recovery source rescan pending");
    }
    if (commanderStarted && commander.ready() && !sourceScanStarted &&
        !sourceSelected)
    {
        sourceScanStarted = true;
        scanTarget = ScanTarget::source;
        if (!BLEScan.clearFilters() || !BLEScan.startExtended(false, false, false))
        {
            Serial.println("CAP source scan failed");
        }
        else
        {
            Serial.println("CAP source scan started");
        }
    }
    if (startPending && commander.ready())
    {
        startPending = false;
        reportRequest("CAP reception start", commander.startReception());
    }
    if (commander.hasSource() && !codePending && commander.ready())
    {
        codePending = true;
        reportRequest("CAP broadcast code",
                      commander.distributeBroadcastCode(broadcastCode));
    }

    while (Serial.available() > 0)
    {
        const char command = static_cast<char>(Serial.read());
        if (command == 's')
        {
            streamWasSynchronized = false;
            lossStopPending = false;
            lossRemovePending = false;
            sourceRescanPending = false;
            reportRequest("CAP reception stop", commander.stopReception());
        }
        else if (command == 'd')
        {
            const Error result = commander.removeSource();
            reportRequest("CAP source remove", result);
            if ((result == Error::none) || (result == Error::not_ready))
            {
                if (result == Error::none)
                {
                    sourceRescanPending = true;
                }
                else
                {
                    prepareSourceScan();
                }
            }
        }
        else if (command == 'r')
        {
            reportRequest("CAP reception restart", commander.startReception());
        }
        else if (command == 'c')
        {
            reportRequest("CAP broadcast code",
                          commander.distributeBroadcastCode(broadcastCode));
        }
        else if (command == 'x')
        {
            BLEScanResult invalidSource;
            reportRequest("CAP invalid source", commander.selectSource(invalidSource));
        }
    }

    static std::uint32_t reportedUpdates = 0U;
    if (commander.stateUpdates() != reportedUpdates)
    {
        reportedUpdates = commander.stateUpdates();
        Serial.print("CAP state update=");
        Serial.print(reportedUpdates);
        Serial.print(" source=");
        Serial.print(commander.hasSource() ? commander.sourceId() : 255U);
        Serial.print(" pa=");
        Serial.print(commander.periodicSynchronized() ? 1 : 0);
        Serial.print(" bis=");
        Serial.println(commander.bisSynchronized() ? 1 : 0);
        if (commander.bisSynchronized())
        {
            streamWasSynchronized = true;
        }
        else if (streamWasSynchronized && commander.hasSource() && commander.ready())
        {
            streamWasSynchronized = false;
            lossStopPending = true;
            Serial.println("CAP source loss detected");
        }
    }
    delay(1U);
}
