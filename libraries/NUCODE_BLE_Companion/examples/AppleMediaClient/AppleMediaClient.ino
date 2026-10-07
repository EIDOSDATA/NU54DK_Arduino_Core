/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par 목적
 * Apple AMS의 track 정보와 사용자 media control을 처리합니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 1대 — 1) AppleMediaClient (AMS client)
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * 없음
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * AMS를 제공하는 실제 Apple peer가 필요하며 제품 상호운용은 사용자 후속 NOT_RUN입니다.
 * @par 준비물
 * - NU54DK 보드 1대 — 1) AppleMediaClient (AMS client)
 * - AMS를 제공하는 실제 Apple peer가 필요하며 제품 상호운용은 사용자 후속 NOT_RUN입니다.
 * @par 설정
 * - Tools → Feature set에서 `ble` profile을 선택합니다.
 * - Serial Monitor는 115200 baud로 엽니다.
 * @par 실행 순서
 * - 권장 profile로 현재 Sketch와 metadata에 적힌 각 peer 역할 Sketch를 빌드합니다.
 * - probe가 여러 대이면 `NUCODE_PROBE_UID`를 지정하고 Arduino Upload로 역할별 보드를 구분합니다.
 * - peer·외장 조건을 먼저 준비한 뒤 reset 또는 예제에 명시된 입력으로 실행합니다.
 * @par 성공 출력
 * - Serial 문구 `AMS ready`를 포함한 정상 상태 전이를 확인합니다.
 * - Serial 문구 `entity=`를 포함한 정상 상태 전이를 확인합니다.
 * - Serial 문구 `attribute=`를 포함한 정상 상태 전이를 확인합니다.
 * @par 흔한 오류
 * - 권장 profile과 sidecar가 다르면 기능·Kconfig가 빠질 수 있으므로 먼저 설정을 다시 확인합니다.
 * - 여러 probe가 연결된 상태에서 UID를 생략하면 다른 보드에 upload될 수 있습니다.
 * - `request error:` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * - `AMS error:` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * @par 다음 예제
 * - `NUCODE_BLE_Companion/AppleNotificationClient`
 * @par 종료와 재시작
 * - 예제의 stop/end/disconnect 또는 유한 완료 흐름 뒤 오류와 자원 반환을 확인합니다.
 * - 실패 문구와 driver 상태를 확인한 뒤 명시적 reset 또는 예제의 재시작 흐름을 사용합니다.
 * @par 보안
 * - explicit_security_or_signed_artifact_flow
 * - 예제의 pairing·bond·서명·credential 조건을 생략하지 않고 오류 출력을 확인합니다.
 * @par 제한
 * - Compile·Host 검사는 실제 보드 runtime 또는 외부 제품 상호운용 PASS를 대신하지 않습니다.
 * - 목적과 metadata 조건 밖의 성능·동시성·정밀도는 이 예제의 보증 범위가 아닙니다.
 * @par Negative
 * - wrong_profile_or_missing_sidecar
 * - missing_or_wrong_role_peer
 * - startup_or_runtime_error_reported
 * @par Traceability
 * Recipe `ble_profiles_and_ecosystems`; 내부 증거 ID는 metadata에서 관리합니다.
 * 직접 upstream 복사 아님; NCS `99553055607b2e9885fbc80ccd11fa9da81c2df0`, Zephyr `bf801e4e3d19e1ffa76164346480cb7734dd2800`
 * build `clean_installed_compile_required`, runtime `procedure_documented_not_physical_pass`
 * @par Metadata
 * identity `NUCODE_BLE_Companion/AppleMediaClient`, sha256 `a5e30fa0e8ab8d1263b21e7e959ff9400f24e0ba9e4675427731ae9e37da2e38`
 * @nucode_example_setup_end */

/**
 * @file AppleMediaClient.ino
 * @brief Apple AMS의 track 정보와 사용자 media control을 처리합니다.
 * @par 목적
 * track artist·album·title·duration을 구독하고 지원된 재생 명령만 전송합니다.
 * @par 준비물
 * NU54DK 1대와 AMS를 제공하는 Apple peer·media app이 필요하며 실제 상호운용은 미검증입니다.
 * @par 설정
 * BLE NUS feature set과 115200 baud를 사용하고 Apple Bluetooth 설정에서 pairing합니다.
 * @par 실행
 * 음악을 재생한 뒤 Serial에서 p=play/pause, n=next, t=title 전체 읽기, q=종료를 입력합니다.
 * @par 성공 출력
 * AMS ready, supported commands, 실제 수신 track byte와 command accepted가 출력됩니다.
 * @par 흔한 오류
 * peer가 통지하지 않은 command는 unsupported이며 truncated title은 t로 다시 읽습니다.
 * @par 다음 예제
 * 알림 수신은 AppleNotificationClient, credential template는 library README를 참고합니다.
 */
#include <NUCODE_BLE_Companion.h>

using namespace nucode::ble;
using namespace nucode::ble::companion;
using CompanionError = nucode::ble::companion::Error;
using CompanionEvent = nucode::ble::companion::Event;
namespace
{
    AppleClient client;
    bool stopped = false;
    bool restartAdvertising = false;

    /** @brief 동기 오류와 성공적인 요청 접수를 구분합니다. */
    void showError(CompanionError result)
    {
        if (result != CompanionError::none)
        {
            Serial.print("request error: ");
            Serial.println(static_cast<unsigned>(result));
        }
    }

    /** @brief 실제 연결 handle을 AMS client에 전달합니다. */
    void gapEvent(const BLEEventInfo &event, void *)
    {
        if (event.event == BLEEvent::connected)
        {
            AppleClient::stopAdvertising();
            showError(client.begin(event.connection, Service::media));
        }
    }

    /** @brief 사용자 track 구독과 실제 payload 처리를 수행합니다. */
    void companionEvent(const EventInfo &event, void *)
    {
        if (event.event == CompanionEvent::ready)
        {
            Serial.println("AMS ready");
            const uint8_t trackAttributes[] = {0, 1, 2, 3};
            showError(client.selectMediaAttributes(2, trackAttributes, sizeof(trackAttributes)));
        }
        else if (event.event == CompanionEvent::media_update)
        {
            Serial.print("entity=");
            Serial.print(event.entity);
            Serial.print(" attribute=");
            Serial.print(event.attribute);
            Serial.print(event.truncated ? " truncated: " : ": ");
            Serial.write(event.data, event.length);
            Serial.println();
        }
        else if (event.event == CompanionEvent::supported_commands)
        {
            Serial.print("supported commands: ");
            Serial.println(event.command_mask, HEX);
        }
        else if (event.event == CompanionEvent::command_complete)
        {
            Serial.println("command accepted by peer");
        }
        else if (event.event == CompanionEvent::disconnected)
        {
            restartAdvertising = !stopped;
        }
        else if (event.event == CompanionEvent::error)
        {
            Serial.print("AMS error: ");
            Serial.print(static_cast<unsigned>(event.error));
            Serial.print(" native=");
            Serial.println(event.native_code);
        }
    }
} // namespace

/** @brief 공개 callback을 등록하고 AMS solicitation 광고를 시작합니다. */
void setup()
{
    Serial.begin(115200);
    BLEDevice.onEventInfo(gapEvent);
    client.onEvent(companionEvent);
    showError(AppleClient::advertise(Service::media, "NU54 Media"));
    Serial.println("Pair in Apple settings; p=play/pause n=next t=full title q=stop");
}

/** @brief 실제 media event와 사용자가 선택한 제어·읽기·종료 명령을 처리합니다. */
void loop()
{
    BLEDevice.poll();
    client.poll();
    if (restartAdvertising)
    {
        restartAdvertising = false;
        showError(AppleClient::advertise(Service::media, "NU54 Media"));
    }
    if (Serial.available() > 0)
    {
        const int command = Serial.read();
        if (command == 'q')
        {
            stopped = true;
            client.end();
            AppleClient::stopAdvertising();
        }
        else if (command == 'p' || command == 'n')
        {
            showError(client.sendMediaCommand(command == 'p' ? 2 : 3));
        }
        else if (command == 't')
        {
            showError(client.readMediaAttribute(2, 2));
        }
    }
    delay(5);
}
