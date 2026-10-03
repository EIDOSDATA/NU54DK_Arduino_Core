/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 2대 — 1) 표준 GATT collector; 2) StandardSensor/AlertSensor/GlucoseSensor 중 선택한 server
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * 없음
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * sensorKind와 server를 맞춥니다. CGMS는 양쪽 표시 숫자를 비교해 각각 y로 승인하는 L3 인증이 필요하며 185초 실행합니다.
 * @par Metadata
 * identity `NUCODE_BLE_Profiles/StandardCollector`, sha256 `bcb74f43aea377e728eedf4cb26d0f580ef45f602a7dd37cce65bfc290fb225c`
 * @nucode_example_setup_end */

/**
 * @file StandardCollector.ino
 * @brief 표준 characteristic을 발견하고 측정값을 엄격히 해석합니다.
 * @par 목적
 * HTS·CTS·CSC·RSCS·ETS·ANS·CGMS 값을 같은 발견·구독 흐름으로 수신합니다.
 * @par 준비물
 * NU54DK 2대: 이 client와 선택한 sensorKind의 server 예제.
 * @par 설정
 * Feature set BLE NUS, 115200 baud, sensorKind를 server와 맞춥니다.
 * @par 실행 순서
 * server를 먼저 시작합니다. 60초(CGMS는 185초) 동안 수신하며 해제 시 다시 검색합니다.
 * CGMS는 양쪽 Serial Monitor의 6자리 숫자를 비교하고 일치할 때 각각 y로 승인합니다.
 * @par 성공 출력
 * decoded measurement와 해석한 숫자 또는 알림 문구가 출력됩니다.
 * @par 흔한 오류
 * UUID 불일치는 발견 실패입니다. ANS는 control point로 email category를 먼저 허용합니다.
 * @par 다음 예제
 * StandardSensor, AlertSensor, GlucoseSensor, ObjectClient를 참고합니다.
 */
#include <NUCODE_BLE_Profiles.h>
#include <NUCODE_BLE_Security.h>

using namespace nucode::ble;
using namespace nucode::ble::profiles;
constexpr Kind sensorKind = Kind::thermometer;
const BLEUuid serviceUuid(static_cast<uint16_t>(sensorKind));
BLEConnectionHandle peer;
BLEConnectionHandle confirmationPeer;
bool discoveryStarted = false;
bool running = false;
bool rescan = false;
bool enablingAlert = sensorKind == Kind::alert;
uint32_t startedAt = 0U;

/** @brief 수신한 byte를 사용자 값으로 복원하고 명확한 단위로 표시합니다. */
void showMeasurement(const uint8_t *data, size_t length)
{
    if (!Codec::valid(sensorKind, data, length))
    {
        Serial.println("invalid measurement rejected");
        return;
    }
    Serial.print("decoded measurement: ");
    switch (sensorKind)
    {
    case Kind::thermometer:
    {
        Temperature value;
        static_cast<void>(Codec::decode(data, length, value));
        Serial.print(value.mantissa);
        Serial.print(" x 10^");
        Serial.print(value.exponent);
        Serial.println(value.fahrenheit ? " F" : " C");
        break;
    }
    case Kind::cycling:
    {
        CyclingMeasurement value;
        static_cast<void>(Codec::decode(data, length, value));
        Serial.print(value.crank_revolutions);
        Serial.println(" crank revolutions");
        break;
    }
    case Kind::running:
    {
        RunningMeasurement value;
        static_cast<void>(Codec::decode(data, length, value));
        Serial.print(value.speed256);
        Serial.println(" /256 m/s");
        break;
    }
    case Kind::current_time:
    {
        CurrentTime value;
        static_cast<void>(Codec::decode(data, length, value));
        Serial.print(value.date.hour);
        Serial.print(':');
        Serial.print(value.date.minute);
        Serial.print(':');
        Serial.println(value.date.second);
        break;
    }
    case Kind::elapsed_time:
    {
        ElapsedTime value;
        static_cast<void>(Codec::decode(data, length, value));
        Serial.print(static_cast<uint32_t>(value.counter));
        Serial.println(" ticks (low 32 bits)");
        break;
    }
    case Kind::glucose:
    {
        GlucoseMeasurement value;
        static_cast<void>(Codec::decode(data, length, value));
        Serial.print(value.mantissa);
        Serial.print(" x 10^");
        Serial.print(value.exponent);
        Serial.println(" mg/dL (synthetic)");
        break;
    }
    case Kind::alert:
    {
        Alert value;
        static_cast<void>(Codec::decode(data, length, value));
        Serial.println(value.text);
        break;
    }
    default:
        break;
    }
}
void onScan(const BLEScanResult &result, void *)
{
    if (!peer.valid() && result.connectable)
    {
        if (!BLEScan.stop() || !BLEConnection.connect(result.address, peer))
        {
            Serial.println("connect failed");
            rescan = true;
        }
    }
}
/** @brief CGMS는 실제 L3 도달 뒤에만 특성을 발견합니다. */
void discoverMeasurement()
{
    if (!discoveryStarted)
    {
        enablingAlert = sensorKind == Kind::alert;
        discoveryStarted = BLEClient.discover(
            peer, serviceUuid,
            BLEUuid(enablingAlert ? 0x2a44U : Codec::measurementUuid(sensorKind)));
        if (!discoveryStarted)
        {
            Serial.println("discovery failed");
        }
    }
}

/** @brief numeric comparison을 자동 승인하지 않고 실제 사용자 입력에 연결합니다. */
void onSecurity(const SecurityEventRecord &event, void *)
{
    if (event.connection != peer)
    {
        return;
    }
    if (event.event == SecurityEvent::passkey_confirmation_requested ||
        event.event == SecurityEvent::passkey_display)
    {
        char digits[7];
        snprintf(digits, sizeof(digits), "%06lu", static_cast<unsigned long>(event.passkey));
        Serial.print("Compare passkey: ");
        Serial.println(digits);
        if (event.event == SecurityEvent::passkey_confirmation_requested)
        {
            confirmationPeer = event.connection;
            Serial.println("Enter y only if both displays match; n rejects (30 s).");
        }
    }
    else if (event.event == SecurityEvent::pairing_requested)
    {
        static_cast<void>(BLESecurity.acceptPairing(event.connection, false));
        Serial.println("Unauthenticated pairing rejected: CGMS requires L3.");
    }
    else if (event.event == SecurityEvent::security_changed &&
             event.level >= SecurityLevel::authenticated)
    {
        confirmationPeer = {};
        discoverMeasurement();
    }
    else if (event.event == SecurityEvent::pairing_cancelled ||
             event.event == SecurityEvent::pairing_failed || event.event == SecurityEvent::timeout)
    {
        confirmationPeer = {};
        Serial.println("pairing cancelled/failed; no authenticated subscription");
    }
}

void onLink(const BLEEventInfo &event, void *)
{
    if (event.connection != peer)
    {
        return;
    }
    if (event.event == BLEEvent::connected)
    {
        if (sensorKind == Kind::glucose)
        {
            if (!BLESecurity.requestSecurity(peer))
            {
                Serial.println("authentication request failed");
            }
        }
        else
        {
            discoverMeasurement();
        }
    }
    else if (event.event == BLEEvent::disconnected)
    {
        peer = {};
        confirmationPeer = {};
        discoveryStarted = false;
        rescan = true;
    }
}
void onGatt(const BLEGattClientEventInfo &event, void *)
{
    if (event.connection != peer)
    {
        return;
    }
    if (event.event == BLEGattClientEvent::discovery_complete)
    {
        if (enablingAlert)
        {
            const uint8_t enableEmail[] = {0U, 1U};
            if (!BLEClient.write(peer, enableEmail, sizeof(enableEmail)))
            {
                Serial.println("alert enable failed");
            }
        }
        else
        {
            const bool subscribed = Codec::usesIndications(sensorKind)
                                        ? BLEClient.subscribeIndications(peer)
                                        : BLEClient.subscribeNotifications(peer);
            Serial.println(subscribed ? "subscription requested" : "subscription failed");
        }
    }
    else if (event.event == BLEGattClientEvent::write_complete && enablingAlert)
    {
        enablingAlert = false;
        if (!BLEClient.discover(peer, serviceUuid, BLEUuid(Codec::measurementUuid(sensorKind))))
        {
            Serial.println("alert discovery failed");
        }
    }
    else if (event.event == BLEGattClientEvent::notification_received ||
             event.event == BLEGattClientEvent::indication_received ||
             event.event == BLEGattClientEvent::read_complete)
    {
        showMeasurement(event.data, event.length);
    }
    else if (event.event == BLEGattClientEvent::operation_failed)
    {
        Serial.print("GATT failed: ");
        Serial.println(event.att_error);
    }
}
void setup()
{
    Serial.begin(115200);
    SecurityConfig security;
    security.minimum_level = SecurityLevel::authenticated;
    security.io_capability = SecurityIoCapability::display_yes_no;
    BLESecurity.onEvent(onSecurity);
    BLEDevice.onEventInfo(onLink);
    BLEClient.onDetailedEvent(onGatt);
    BLEScan.onResult(onScan);
    running = (sensorKind != Kind::glucose || BLESecurity.begin(security)) &&
              BLEDevice.begin("NU54-COLLECTOR") && BLEScan.filterServiceUuid(serviceUuid) &&
              BLEScan.start(true);
    startedAt = millis();
    Serial.println(running ? "collector scanning" : "collector start failed");
}
void loop()
{
    if (!running)
    {
        return;
    }
    BLEDevice.poll();
    if (sensorKind == Kind::glucose)
    {
        BLESecurity.poll();
        while (Serial.available() > 0)
        {
            const char command = static_cast<char>(Serial.read());
            if (confirmationPeer.valid() && (command == 'y' || command == 'n'))
            {
                Serial.println(BLESecurity.confirmPasskey(confirmationPeer, command == 'y')
                                   ? "comparison response submitted"
                                   : "comparison response failed");
                confirmationPeer = {};
            }
        }
    }
    const uint32_t duration = sensorKind == Kind::glucose ? 185000U : 60000U;
    if (millis() - startedAt >= duration)
    {
        if (confirmationPeer.valid())
        {
            static_cast<void>(BLESecurity.cancelPairing(confirmationPeer));
            confirmationPeer = {};
        }
        BLEDevice.end();
        running = false;
        Serial.println("collector stopped");
    }
    else if (rescan && !peer.valid())
    {
        rescan = !BLEScan.start(true);
    }
}
