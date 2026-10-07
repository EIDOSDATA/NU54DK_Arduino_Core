/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par 목적
 * 한 BLE link에 두 LE CoC channel을 열고 512-byte echo를 확인하는 client 예제입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: Adaptive capabilities (experimental) (adaptive, 실험적 대안)
 * @par 보드와 역할
 * 2대 — 1) L2capCocClient (client/controller); 2) L2capCocServer (server/device)
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * nucode-build.json
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 추가 조건 없음
 * @par 준비물
 * - NU54DK 보드 2대 — 1) L2capCocClient (client/controller); 2) L2capCocServer (server/device)
 * @par 설정
 * - Tools → Feature set에서 `ble` profile을 선택합니다.
 * - Sketch 폴더의 sidecar를 함께 설치합니다: nucode-build.json
 * - Serial Monitor는 115200 baud로 엽니다.
 * @par 실행 순서
 * - 권장 profile로 현재 Sketch와 metadata에 적힌 각 peer 역할 Sketch를 빌드합니다.
 * - probe가 여러 대이면 `NUCODE_PROBE_UID`를 지정하고 Arduino Upload로 역할별 보드를 구분합니다.
 * - peer·외장 조건을 먼저 준비한 뒤 reset 또는 예제에 명시된 입력으로 실행합니다.
 * @par 성공 출력
 * - Serial 문구 `LE CoC channel ready, count=`를 포함한 정상 상태 전이를 확인합니다.
 * - Serial 문구 `LE CoC echo corrupt`를 포함한 정상 상태 전이를 확인합니다.
 * - Serial 문구 `LE CoC echo PASS, count=`를 포함한 정상 상태 전이를 확인합니다.
 * @par 흔한 오류
 * - 권장 profile과 sidecar가 다르면 기능·Kconfig가 빠질 수 있으므로 먼저 설정을 다시 확인합니다.
 * - 여러 probe가 연결된 상태에서 UID를 생략하면 다른 보드에 upload될 수 있습니다.
 * - `LE CoC connect failed, channel=` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * - `LE CoC client start failed, error=` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * - `BLE peer connect failed` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * @par 다음 예제
 * - `NUCODE_BLE/L2capCocServer`
 * - `NUCODE_BLE/LeChannelMapControl`
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
 * Recipe `ble_l2cap`; 내부 증거 ID는 metadata에서 관리합니다.
 * 직접 upstream 복사 아님; NCS `99553055607b2e9885fbc80ccd11fa9da81c2df0`, Zephyr `bf801e4e3d19e1ffa76164346480cb7734dd2800`
 * build `clean_installed_compile_required`, runtime `procedure_documented_not_physical_pass`
 * @par Metadata
 * identity `NUCODE_BLE/L2capCocClient`, sha256 `bed4bf0ddbd05acce10a8b4aeb5b83ad17be65c8506d055ae2d720f2473ad18e`
 * @nucode_example_setup_end */

/**
 * @file L2capCocClient.ino
 * @brief 한 BLE link에 두 LE CoC channel을 열고 512-byte echo를 확인하는 client 예제입니다.
 */

#include <NUCODE_BLE.h>

#include <string.h>

constexpr std::uint16_t echoPsm = 0x0080U;
constexpr std::size_t channelCount = 2U;

nucode::ble::BLEAddress peerAddress;
nucode::ble::BLEConnectionHandle peerConnection;
nucode::ble::BLEL2capChannelHandle channels[channelCount];
std::uint8_t payload[nucode::ble::L2capCoc::maximum_sdu_length] = {};
std::uint32_t sequence = 0U;
std::uint32_t lastSendMs = 0U;
std::size_t connectedChannels = 0U;
std::size_t echoCount = 0U;
std::size_t pendingEchoes = 0U;
bool peerFound = false;

/** @brief exact local-name scan 결과의 주소를 main thread에서 보존합니다. */
void onScanResult(const nucode::ble::BLEScanResult &result, void *context)
{
    static_cast<void>(context);
    if (!peerFound)
    {
        peerAddress = result.address;
        peerFound = true;
    }
}

/** @brief GAP 연결 뒤 동일 PSM에 두 channel 연결을 시작합니다. */
void onBleEvent(const nucode::ble::BLEEventInfo &information, void *context)
{
    static_cast<void>(context);
    if (information.event == nucode::ble::BLEEvent::connected &&
        information.role == nucode::ble::BLELinkRole::central)
    {
        peerConnection = information.connection;
        for (std::size_t index = 0U; index < channelCount; ++index)
        {
            if (!BLEL2cap.connect(peerConnection, echoPsm, channels[index]))
            {
                Serial.print("LE CoC connect failed, channel=");
                Serial.println(index);
                break;
            }
        }
    }
    else if (information.event == nucode::ble::BLEEvent::disconnected)
    {
        connectedChannels = 0U;
        pendingEchoes = 0U;
        peerConnection = nucode::ble::BLEConnectionHandle{};
    }
}

/** @brief channel 연결과 echo payload를 main thread에서 검증합니다. */
void onL2capEvent(const nucode::ble::BLEL2capEventInfo &information, void *context)
{
    static_cast<void>(context);
    if (information.event == nucode::ble::BLEL2capEvent::connected)
    {
        ++connectedChannels;
        Serial.print("LE CoC channel ready, count=");
        Serial.println(connectedChannels);
    }
    else if (information.event == nucode::ble::BLEL2capEvent::received)
    {
        if (information.length != sizeof(payload) ||
            ::memcmp(information.data, payload, sizeof(payload)) != 0)
        {
            Serial.println("LE CoC echo corrupt");
            return;
        }
        ++echoCount;
        if (pendingEchoes != 0U)
        {
            --pendingEchoes;
        }
        Serial.print("LE CoC echo PASS, count=");
        Serial.println(echoCount);
    }
}

/** @brief sequence와 byte offset으로 검증 가능한 512-byte SDU를 만듭니다. */
void preparePayload()
{
    for (std::size_t index = 0U; index < sizeof(payload); ++index)
    {
        payload[index] = static_cast<std::uint8_t>((sequence + index * 13U) & 0xffU);
    }
    ++sequence;
}

void setup()
{
    Serial.begin(115200);
    BLEDevice.onEventInfo(onBleEvent);
    BLEScan.onResult(onScanResult);
    BLEL2cap.onEvent(onL2capEvent);
    if (!BLEDevice.begin("NU54-CoC-Client") || !BLEScan.clearFilters() ||
        !BLEScan.filterName("NU54-CoC-Echo") || !BLEScan.start(true))
    {
        Serial.print("LE CoC client start failed, error=");
        Serial.println(static_cast<unsigned>(BLEDevice.lastError()));
    }
}

void loop()
{
    BLEDevice.poll();
    if (peerFound && !BLEConnection.connected() && !BLEConnection.connecting())
    {
        peerFound = false;
        static_cast<void>(BLEScan.stop());
        if (!BLEConnection.connect(peerAddress))
        {
            Serial.println("BLE peer connect failed");
        }
    }

    const std::uint32_t now = millis();
    if (connectedChannels == channelCount && pendingEchoes == 0U &&
        now - lastSendMs >= 1000U &&
        BLEL2cap.availableForWrite() >= channelCount)
    {
        lastSendMs = now;
        preparePayload();
        for (const nucode::ble::BLEL2capChannelHandle channel : channels)
        {
            if (!BLEL2cap.send(channel, payload, sizeof(payload)))
            {
                Serial.print("LE CoC send backpressure, free=");
                Serial.println(BLEL2cap.availableForWrite());
                break;
            }
            ++pendingEchoes;
        }
    }
}
