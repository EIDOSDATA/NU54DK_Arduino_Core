/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par 목적
 * 보안 BLE 연결에서 Ranging Service와 CS reflector를 실행합니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: Adaptive capabilities (experimental) (adaptive, 실험적 대안)
 * @par 보드와 역할
 * 2대 — 1) RasInitiator (initiator); 2) RasReflector (reflector)
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * nucode-build.json, prj.conf
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * Initiator와 함께 사용하며 거리 결과는 Initiator Serial에서 확인합니다.
 * @par 준비물
 * - NU54DK 보드 2대 — 1) RasInitiator (initiator); 2) RasReflector (reflector)
 * - Initiator와 함께 사용하며 거리 결과는 Initiator Serial에서 확인합니다.
 * @par 설정
 * - Tools → Feature set에서 `ble` profile을 선택합니다.
 * - Sketch 폴더의 sidecar를 함께 설치합니다: nucode-build.json, prj.conf
 * - Serial Monitor는 115200 baud로 엽니다.
 * @par 실행 순서
 * - 권장 profile로 현재 Sketch와 metadata에 적힌 각 peer 역할 Sketch를 빌드합니다.
 * - probe가 여러 대이면 `NUCODE_PROBE_UID`를 지정하고 Arduino Upload로 역할별 보드를 구분합니다.
 * - peer·외장 조건을 먼저 준비한 뒤 reset 또는 예제에 명시된 입력으로 실행합니다.
 * @par 성공 출력
 * - Serial 문구 `CS reflector connected`를 포함한 정상 상태 전이를 확인합니다.
 * - Serial 문구 `CS reflector disconnected`를 포함한 정상 상태 전이를 확인합니다.
 * - Serial 문구 `CS reflector advertising`를 포함한 정상 상태 전이를 확인합니다.
 * @par 흔한 오류
 * - 권장 profile과 sidecar가 다르면 기능·Kconfig가 빠질 수 있으므로 먼저 설정을 다시 확인합니다.
 * - 여러 probe가 연결된 상태에서 UID를 생략하면 다른 보드에 upload될 수 있습니다.
 * - `CS reflector begin failed:` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * - `CS reflector advertising failed` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * - `CS reflector advertising restart failed` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * @par 다음 예제
 * - `NUCODE_BLE_ChannelSounding/RasInitiator`
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
 * Recipe `ble_channel_sounding`; 내부 증거 ID는 metadata에서 관리합니다.
 * 직접 upstream 복사 아님; NCS `99553055607b2e9885fbc80ccd11fa9da81c2df0`, Zephyr `bf801e4e3d19e1ffa76164346480cb7734dd2800`
 * build `clean_installed_compile_required`, runtime `procedure_documented_not_physical_pass`
 * @par Metadata
 * identity `NUCODE_BLE_ChannelSounding/RasReflector`, sha256 `fe27a56889708a4311500f878cfddbd8450c6f86e28b5a1c586e8da723860ce8`
 * @nucode_example_setup_end */

/**
 * @file RasReflector.ino
 * @brief 보안 BLE 연결에서 Ranging Service와 CS reflector를 실행합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE.h>
#include <NUCODE_BLE_ChannelSounding.h>

using nucode::ble::BLEConnectionHandle;
using nucode::ble::BLEEvent;
using nucode::ble::BLEEventInfo;
using nucode::ble::BLEUuid;
using nucode::ble::cs::Error;
using nucode::ble::cs::RasReflector;

namespace
{
    RasReflector reflector;
    BLEConnectionHandle peer;
    bool restartAdvertising = false;
    bool wasSecure = false;
    bool wasReady = false;
    bool wasActive = false;
    bool quiesceRequested = false;
    bool quiesceDisconnectRequested = false;
    bool quiesceReported = false;

    /** @brief 연결 상태 변화를 공개 API로 reflector에 전달합니다. */
    void onBleEvent(const BLEEventInfo &event, void *context)
    {
        static_cast<void>(context);
        if (event.event == BLEEvent::connected)
        {
            peer = event.connection;
            if (quiesceRequested)
            {
                quiesceDisconnectRequested = false;
                return;
            }
            const Error result = reflector.begin(peer);
            if (result == Error::none)
            {
                Serial.println("CS reflector connected");
            }
            else
            {
                Serial.print("CS reflector begin failed: ");
                Serial.println(reflector.nativeCode());
            }
        }
        else if ((event.event == BLEEvent::disconnected) &&
                 (event.connection == peer))
        {
            reflector.end();
            peer = BLEConnectionHandle();
            restartAdvertising = !quiesceRequested;
            wasSecure = false;
            wasReady = false;
            wasActive = false;
            Serial.println("CS reflector disconnected");
        }
    }

    /** @brief advertising·CS·ACL을 끝내고 재광고를 금지합니다. */
    void requestQuiesce()
    {
        quiesceRequested = true;
        quiesceDisconnectRequested = false;
        quiesceReported = false;
        restartAdvertising = false;
        reflector.end();
        if (BLEAdvertising.running() && !BLEAdvertising.stop())
        {
            Serial.println("CS quiesce advertising stop failed");
        }
        Serial.println("CS quiesce requested role=reflector");
    }

    /** @brief quiesce 뒤 active ACL·pending 연결·advertising·CS가 모두 0인지 공개합니다. */
    void pollQuiesce()
    {
        if (!quiesceRequested)
        {
            return;
        }
        if (BLEAdvertising.running())
        {
            if (!BLEAdvertising.stop())
            {
                return;
            }
        }
        if (peer.valid() && BLEConnection.connected() &&
            !quiesceDisconnectRequested)
        {
            if (!BLEConnection.disconnect(peer))
            {
                return;
            }
            quiesceDisconnectRequested = true;
        }
        if (!peer.valid() && !BLEConnection.connected() &&
            !BLEConnection.connecting() && !BLEAdvertising.running() &&
            !quiesceReported)
        {
            quiesceReported = true;
            Serial.println(
                "CS_QUIESCED role=reflector active_acl=0 pending=0 advertising=0 cs=0");
        }
    }
}

/** @brief Ranging Service UUID와 연결 가능한 광고를 시작합니다. */
void setup()
{
    Serial.begin(115200);
    BLEDevice.onEventInfo(onBleEvent);
    if (!BLEDevice.begin("NU54-CS-RSP") || !BLEAdvertising.clear() ||
        !BLEAdvertising.setConnectable(true) ||
        !BLEAdvertising.addServiceUuid(BLEUuid(0x185BU)) ||
        !BLEAdvertising.start())
    {
        Serial.println("CS reflector advertising failed");
        return;
    }
    Serial.println("CS reflector advertising");
}

/** @brief CS 설정 완료와 보안·절차 상태를 Arduino 문맥에서 관찰합니다. */
void loop()
{
    BLEDevice.poll();
    reflector.poll();
    pollQuiesce();

    if (!quiesceRequested && restartAdvertising && !BLEConnection.connected())
    {
        restartAdvertising = false;
        if (!BLEAdvertising.start())
        {
            Serial.println("CS reflector advertising restart failed");
        }
    }

    if (peer.valid())
    {
        const bool secure = reflector.secure();
        const bool ready = reflector.ready();
        const bool active = reflector.active();
        if (secure && !wasSecure)
        {
            Serial.println("CS reflector secure L2");
        }
        if (ready && !wasReady)
        {
            Serial.println("CS reflector config ready");
        }
        if (active != wasActive)
        {
            Serial.println(active ? "CS procedures enabled" :
                                   "CS procedures disabled");
        }
        wasSecure = secure;
        wasReady = ready;
        wasActive = active;
    }

    if (reflector.lastError() == Error::controller_error)
    {
        Serial.print("CS reflector controller error: ");
        Serial.println(reflector.nativeCode());
        reflector.end();
    }
    if (Serial.available() > 0)
    {
        const int command = Serial.read();
        if (command == 'q')
        {
            requestQuiesce();
        }
    }
    delay(1);
}
