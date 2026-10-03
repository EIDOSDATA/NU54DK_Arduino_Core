/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
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
 * @par Metadata
 * identity `NUCODE_BLE_Profiles/StandardSensor`, sha256 `cab08bd98178cb379ee6c79950aba136efd7af76dda89b48de24c7fec4e36ecf`
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
