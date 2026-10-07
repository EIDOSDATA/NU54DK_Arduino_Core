/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par 목적
 * preset을 게시하고 local·remote 선택을 처리하는 Hearing Access 예제입니다.
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
 * - Serial 문구 `Hearing client connected`를 포함한 정상 상태 전이를 확인합니다.
 * - Serial 문구 `Hearing client disconnected reason=`를 포함한 정상 상태 전이를 확인합니다.
 * - Serial 문구 `result=`를 포함한 정상 상태 전이를 확인합니다.
 * @par 흔한 오류
 * - 권장 profile과 sidecar가 다르면 기능·Kconfig가 빠질 수 있으므로 먼저 설정을 다시 확인합니다.
 * - 여러 probe가 연결된 상태에서 UID를 생략하면 다른 보드에 upload될 수 있습니다.
 * - `Hearing Access server start failed native=` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * @par 다음 예제
 * - `NUCODE_BLE_Audio/Lc3SyntheticLoopback`
 * - `NUCODE_BLE_Audio/MediaControlClient`
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
 * identity `NUCODE_BLE_Audio/HearingAccessServer`, sha256 `83f9e7f684d375725e35df4758b22e6a22bf0eb447f60a8aac4b389251ca28ea`
 * @nucode_example_setup_end */

/**
 * @file HearingAccessServer.ino
 * @brief preset을 게시하고 local·remote 선택을 처리하는 Hearing Access 예제입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE.h>
#include <NUCODE_BLE_Audio.h>
#include <NUCODE_BLE_Security.h>

using nucode::ble::BLEEvent;
using nucode::ble::BLEEventInfo;
using nucode::ble::BLEUuid;
using nucode::ble::SecurityConfig;
using nucode::ble::SecurityEvent;
using nucode::ble::SecurityEventRecord;
using nucode::ble::SecurityIoCapability;
using nucode::ble::SecurityLevel;
using nucode::ble::audio::Error;
using nucode::ble::audio::HearingAccessServer;
using nucode::ble::audio::HearingAccessServerConfig;
using nucode::ble::audio::HearingAidType;
using nucode::ble::audio::HearingPreset;

namespace
{
    HearingAccessServer hearingAccess;
    bool restartAdvertising = false;
    std::uint32_t restartAt = 0U;

    /** @brief Hearing Access Service UUID와 장치 이름을 광고합니다. */
    bool startAdvertising()
    {
        return BLEAdvertising.clear() && BLEAdvertising.setConnectable(true) &&
               BLEAdvertising.addServiceUuid(BLEUuid(0x1854U)) &&
               BLEAdvertising.setScanResponseName(true) && BLEAdvertising.start();
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

    /** @brief client 연결 해제 뒤 광고 재시작을 예약합니다. */
    void onBleEvent(const BLEEventInfo &event, void *context)
    {
        static_cast<void>(context);
        if (event.event == BLEEvent::connected)
        {
            Serial.println("Hearing client connected");
        }
        else if (event.event == BLEEvent::disconnected)
        {
            restartAdvertising = true;
            restartAt = millis() + 100U;
            Serial.print("Hearing client disconnected reason=");
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

    /** @brief 현재 preset 목록과 active index를 출력합니다. */
    void printPresets()
    {
        Serial.print("active=");
        Serial.print(hearingAccess.activePreset());
        Serial.print(" selections=");
        Serial.println(hearingAccess.selectionChanges());
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

/** @brief 보안, HAS preset database와 광고를 준비합니다. */
void setup()
{
    Serial.begin(115200);

    SecurityConfig security;
    security.minimum_level = SecurityLevel::encrypted;
    security.bonding = true;
    security.io_capability = SecurityIoCapability::no_input_output;
    BLESecurity.onEvent(onSecurityEvent);
    BLEDevice.onEventInfo(onBleEvent);

    HearingAccessServerConfig config;
    config.type = HearingAidType::monaural;
    if (!BLESecurity.begin(security) || !BLEDevice.begin("NU54-HEARING-AID") ||
        (hearingAccess.begin(config) != Error::none) ||
        (hearingAccess.addPreset(1U, "Universal") != Error::none) ||
        (hearingAccess.addPreset(5U, "Outdoor") != Error::none) ||
        (hearingAccess.addPreset(8U, "Noisy room") != Error::none) ||
        (hearingAccess.setActivePreset(1U) != Error::none) || !startAdvertising())
    {
        Serial.print("Hearing Access server start failed native=");
        Serial.println(hearingAccess.nativeCode());
        return;
    }
    Serial.println("Commands: 1/5/8=select n=rename 8 a=toggle 5 c=clear bonds s=state");
    printPresets();
}

/** @brief BLE event와 사용자가 선택한 preset 변경을 처리합니다. */
void loop()
{
    BLEDevice.poll();
    BLESecurity.poll();

    if (restartAdvertising && !BLEAdvertising.running() &&
        (static_cast<std::int32_t>(millis() - restartAt) >= 0))
    {
        if (startAdvertising())
        {
            restartAdvertising = false;
            Serial.println("Hearing Access advertising restarted");
        }
        else
        {
            restartAt = millis() + 1000U;
        }
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
            report("Rename preset", hearingAccess.renamePreset(8U, "Conversation"));
        }
        else if (command == 'a')
        {
            HearingPreset preset;
            bool available = false;
            for (std::size_t position = 0U; position < hearingAccess.presetCount(); ++position)
            {
                if ((hearingAccess.preset(position, preset) == Error::none) && (preset.index == 5U))
                {
                    available = preset.available;
                    break;
                }
            }
            report("Toggle preset availability", hearingAccess.setPresetAvailable(5U, !available));
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

    static std::uint32_t changes = 0U;
    if (changes != hearingAccess.selectionChanges())
    {
        changes = hearingAccess.selectionChanges();
        printPresets();
    }
    delay(1U);
}
