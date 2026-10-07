/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par 목적
 * 사용자 측정값을 HTS·CTS·CSC·RSCS·ETS 중 선택한 표준 GATT로 전송합니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 2대 — 1) 선택한 표준 측정 service server; 2) 같은 sensorKind의 StandardCollector
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * 없음
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 두 sketch의 sensorKind를 맞춥니다. CTS/HTS/CSC/RSCS/ETS 값은 합성 예시이며 외장 센서를 검증하지 않습니다.
 * @par 준비물
 * - NU54DK 보드 2대 — 1) 선택한 표준 측정 service server; 2) 같은 sensorKind의 StandardCollector
 * - 두 sketch의 sensorKind를 맞춥니다. CTS/HTS/CSC/RSCS/ETS 값은 합성 예시이며 외장 센서를 검증하지 않습니다.
 * @par 설정
 * - Tools → Feature set에서 `ble` profile을 선택합니다.
 * - Serial Monitor는 115200 baud로 엽니다.
 * @par 실행 순서
 * - 권장 profile로 현재 Sketch와 metadata에 적힌 각 peer 역할 Sketch를 빌드합니다.
 * - probe가 여러 대이면 `NUCODE_PROBE_UID`를 지정하고 Arduino Upload로 역할별 보드를 구분합니다.
 * - peer·외장 조건을 먼저 준비한 뒤 reset 또는 예제에 명시된 입력으로 실행합니다.
 * @par 성공 출력
 * - Serial 문구 `sensor stopped`를 포함한 정상 상태 전이를 확인합니다.
 * @par 흔한 오류
 * - 권장 profile과 sidecar가 다르면 기능·Kconfig가 빠질 수 있으므로 먼저 설정을 다시 확인합니다.
 * - 여러 probe가 연결된 상태에서 UID를 생략하면 다른 보드에 upload될 수 있습니다.
 * @par 다음 예제
 * - `NUCODE_BLE_Profiles/AlertSensor`
 * - `NUCODE_BLE_Profiles/BondManagement`
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
 * Recipe `ble_profiles_and_ecosystems`; 내부 증거 ID는 metadata에서 관리합니다.
 * 직접 upstream 복사 아님; NCS `99553055607b2e9885fbc80ccd11fa9da81c2df0`, Zephyr `bf801e4e3d19e1ffa76164346480cb7734dd2800`
 * build `clean_installed_compile_required`, runtime `procedure_documented_not_physical_pass`
 * @par Metadata
 * identity `NUCODE_BLE_Profiles/StandardSensor`, sha256 `51630e252df124d29395b7a50576b2039d18b275eb5c0f96afc28882dbce2344`
 * @nucode_example_setup_end */

/**
 * @file StandardSensor.ino
 * @brief 사용자 측정값을 HTS·CTS·CSC·RSCS·ETS 중 선택한 표준 GATT로 전송합니다.
 * @par 목적
 * sensorKind 하나로 서비스를 고르고 .ino에서 synthetic 값을 생성·변경합니다.
 * @par 준비물
 * NU54DK 2대: 이 server와 StandardCollector. 실제 센서가 없는 합성 데이터 예제입니다.
 * @par 설정
 * Feature set BLE NUS, 115200 baud. 두 Sketch의 sensorKind를 일치시킵니다.
 * @par 실행 순서
 * server를 먼저 시작하고 collector를 실행합니다. 60초 뒤 연결을 종료합니다.
 * @par 성공 출력
 * 서버의 measurement queued와 collector의 decoded measurement가 함께 보여야 합니다.
 * @par 흔한 오류
 * HTS/ETS는 indication을 구독해야 합니다. CSC는 crank-only, RSCS 누적 거리는 미광고입니다.
 * @par 다음 예제
 * StandardCollector, AlertSensor, GlucoseSensor와 ObjectServer를 참고합니다.
 */
#include <NUCODE_BLE_Profiles.h>

using namespace nucode::ble::profiles;
constexpr Kind sensorKind = Kind::thermometer;
SensorService sensor(sensorKind);
bool running = false;
uint32_t startedAt = 0U;
uint32_t previousAt = 0U;
uint16_t samples = 0U;

/** @brief 선택한 형식의 사용자 데이터를 직접 구성합니다. */
bool makeMeasurement(Packet &packet)
{
    switch (sensorKind)
    {
    case Kind::thermometer:
    {
        Temperature value;
        value.mantissa = 2350 + (samples % 10U);
        value.exponent = -2;
        return Codec::encode(value, packet);
    }
    case Kind::current_time:
    {
        CurrentTime value;
        value.date = {2026U, 10U, 3U, 12U, 0U, static_cast<uint8_t>(samples % 60U)};
        value.adjust_reason = 1U;
        return Codec::encode(value, packet);
    }
    case Kind::cycling:
    {
        CyclingMeasurement value;
        value.has_wheel = false;
        value.crank_revolutions = samples;
        value.crank_event1024 = static_cast<uint16_t>(samples * 1024U);
        return Codec::encode(value, packet);
    }
    case Kind::running:
    {
        RunningMeasurement value;
        value.speed256 = 512U;
        value.cadence = 120U;
        value.running = true;
        value.has_stride = true;
        value.stride_cm = 100U;
        return Codec::encode(value, packet);
    }
    case Kind::elapsed_time:
    {
        ElapsedTime value;
        value.flags = 0x21U;
        value.counter = samples;
        value.clock_status = 0U;
        return Codec::encode(value, packet);
    }
    default:
        return false;
    }
}

void setup()
{
    Serial.begin(115200);
    running =
        sensor.begin() && BLEDevice.begin("NU54-SENSOR") && BLEAdvertising.clear() &&
        BLEAdvertising.addServiceUuid(nucode::ble::BLEUuid(static_cast<uint16_t>(sensorKind))) &&
        BLEAdvertising.start();
    startedAt = millis();
    Serial.println(running ? "sensor ready: synthetic data" : "sensor start failed");
}

void loop()
{
    if (!running)
    {
        return;
    }
    BLEDevice.poll();
    if (millis() - startedAt >= 60000U)
    {
        BLEDevice.end();
        running = false;
        Serial.println("sensor stopped");
        return;
    }
    if (millis() - previousAt < 1000U)
    {
        return;
    }
    previousAt = millis();
    Packet packet;
    ++samples;
    const auto peer = BLEConnection.handle(nucode::ble::BLELinkRole::peripheral);
    if (makeMeasurement(packet) && sensor.setValue(packet) && peer.valid())
    {
        Serial.println(sensor.send(peer) ? "measurement queued"
                                         : "measurement not subscribed/busy");
    }
}
