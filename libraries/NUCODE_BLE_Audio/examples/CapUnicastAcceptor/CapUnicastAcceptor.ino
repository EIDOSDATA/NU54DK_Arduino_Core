/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par 목적
 * CAP Acceptor의 unicast LC3 stream을 수신하고 PCM으로 복호화합니다.
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
 * - Serial 문구 `CAP Initiator disconnected reason=`를 포함한 정상 상태 전이를 확인합니다.
 * - Serial 문구 `CAP Acceptor starting`를 포함한 정상 상태 전이를 확인합니다.
 * - Serial 문구 `CAP Acceptor BLE ready`를 포함한 정상 상태 전이를 확인합니다.
 * @par 흔한 오류
 * - 권장 profile과 sidecar가 다르면 기능·Kconfig가 빠질 수 있으므로 먼저 설정을 다시 확인합니다.
 * - 여러 probe가 연결된 상태에서 UID를 생략하면 다른 보드에 upload될 수 있습니다.
 * - `CAP Acceptor BLE start failed` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * - `CAP service registration failed:` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * - `CAP unicast server failed:` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * @par 다음 예제
 * - `NUCODE_BLE_Audio/CapUnicastInitiator`
 * - `NUCODE_BLE_Audio/CsipSetCoordinator`
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
 * identity `NUCODE_BLE_Audio/CapUnicastAcceptor`, sha256 `eda8a1ea395f75a34d6f95ca005ca4574bbc0219a5bb6f03aed430b46100805a`
 * @nucode_example_setup_end */

/**
 * @file CapUnicastAcceptor.ino
 * @brief CAP Acceptor의 unicast LC3 stream을 수신하고 PCM으로 복호화합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE.h>
#include <NUCODE_BLE_Audio.h>

using nucode::ble::BLEEvent;
using nucode::ble::BLEEventInfo;
using nucode::ble::BLEUuid;
using nucode::ble::audio::CapAcceptor;
using nucode::ble::audio::Error;
using nucode::ble::audio::Lc3Codec;
using nucode::ble::audio::UnicastServer;

namespace
{
    CapAcceptor acceptor;
    UnicastServer audioSink;
    Lc3Codec codec;
    bool restartAdvertising = false;
    bool setupReady = false;
    const char *statusMessage = "starting";
    std::uint32_t decodedFrames = 0U;
    std::uint32_t lastStatusAt = 0U;

    /** @brief 연결 해제 뒤 다음 Initiator를 받을 광고를 예약합니다. */
    void onBleEvent(const BLEEventInfo &event, void *context)
    {
        static_cast<void>(context);
        if (event.event == BLEEvent::disconnected)
        {
            restartAdvertising = true;
            Serial.print("CAP Initiator disconnected reason=");
            Serial.println(event.reason);
        }
    }

    /** @brief PCM frame의 절대값 합으로 실제 decode 결과를 확인합니다. */
    std::uint32_t frameEnergy(const std::int16_t (&pcm)[160])
    {
        std::uint32_t energy = 0U;
        for (const std::int16_t sample : pcm)
        {
            const std::int32_t value = sample;
            energy += static_cast<std::uint32_t>((value < 0) ? -value : value);
        }
        return energy;
    }
} // namespace

/** @brief CAS와 PACS/ASCS sink, codec, 연결 가능 광고를 시작합니다. */
void setup()
{
    Serial.begin(115200);
    Serial.println("CAP Acceptor starting");
    BLEDevice.onEventInfo(onBleEvent);
    if (!BLEDevice.begin("NU54-CAP-UNICAST-SINK"))
    {
        statusMessage = "BLE start failed";
        Serial.println("CAP Acceptor BLE start failed");
        return;
    }
    Serial.println("CAP Acceptor BLE ready");

    if (acceptor.begin() != Error::none)
    {
        statusMessage = "service registration failed";
        Serial.print("CAP service registration failed: ");
        Serial.println(acceptor.nativeCode());
        return;
    }
    Serial.println("CAP service ready");

    if (audioSink.begin() != Error::none)
    {
        statusMessage = "unicast server failed";
        Serial.print("CAP unicast server failed: ");
        Serial.println(audioSink.nativeCode());
        return;
    }
    Serial.println("CAP unicast server ready");

    if (codec.begin() != Error::none)
    {
        statusMessage = "codec failed";
        Serial.println("CAP codec failed");
        return;
    }
    Serial.println("CAP codec ready");

    constexpr std::uint8_t announcement[] = {1U, 0x03U, 0x00U, 0x00U, 0x00U, 0U};
    if (!BLEAdvertising.clear() || !BLEAdvertising.setConnectable(true) ||
        !BLEAdvertising.addServiceUuid(BLEUuid(0x1853U)) ||
        !BLEAdvertising.addServiceUuid(BLEUuid(0x184EU)) ||
        !BLEAdvertising.setServiceData(BLEUuid(0x184EU), announcement, sizeof(announcement)) ||
        !BLEAdvertising.start())
    {
        statusMessage = "advertising failed";
        Serial.println("CAP Acceptor advertising failed");
        return;
    }
    setupReady = true;
    statusMessage = "waiting for Initiator";
    Serial.println("CAP unicast Acceptor ready");
}

/** @brief 수신 LC3 frame을 공개 codec으로 복호화하고 통계를 출력합니다. */
void loop()
{
    const std::uint32_t now = millis();
    if ((now - lastStatusAt) >= 2000U)
    {
        lastStatusAt = now;
        Serial.print("CAP Acceptor status: ");
        Serial.println(statusMessage);
    }
    if (!setupReady)
    {
        delay(1U);
        return;
    }

    BLEDevice.poll();
    if (restartAdvertising && !BLEConnection.connected())
    {
        restartAdvertising = false;
        if (!BLEAdvertising.start())
        {
            restartAdvertising = true;
            Serial.println("CAP Acceptor advertising restart failed");
        }
    }

    std::uint8_t frame[40] = {};
    while (audioSink.readFrame(frame))
    {
        std::int16_t pcm[160] = {};
        if (codec.decode(frame, sizeof(frame), pcm, 160U) != Error::none)
        {
            Serial.println("CAP decode failed");
            continue;
        }
        decodedFrames++;
        if ((decodedFrames % 100U) == 0U)
        {
            Serial.print("CAP decoded frames=");
            Serial.print(decodedFrames);
            Serial.print(" energy=");
            Serial.print(frameEnergy(pcm));
            Serial.print(" dropped=");
            Serial.println(audioSink.droppedFrames());
        }
    }
    delay(1U);
}
