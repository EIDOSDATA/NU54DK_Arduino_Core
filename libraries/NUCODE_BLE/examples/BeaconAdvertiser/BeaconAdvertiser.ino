/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 2대 — 1) BeaconAdvertiser (broadcaster); 2) BeaconObserver (passive scanner)
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * 없음
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * Apple iBeacon 상용 인증·브랜딩과 외부 단말 상호운용 검증은 이 예제 범위에 포함되지 않음
 * @par Metadata
 * identity `NUCODE_BLE/BeaconAdvertiser`, sha256 `770c6f9f138f0c0ea196b67121187a8b858092b538c6d1deda3ac7235282eb5b`
 * @nucode_example_setup_end */

/**
 * @file BeaconAdvertiser.ino
 * @brief 한 보드에서 iBeacon, Eddystone UID, BTHome v2 광고를 차례로 송신합니다.
 * @par 목적
 * 세 가지 대표 Beacon 포맷을 별도 예제로 흩뜨리지 않고 한 흐름에서 비교합니다.
 * @par 준비물
 * NU54DK 1대가 필요하며, 관찰에는 BeaconObserver를 올린 NU54DK 1대를 권장합니다.
 * @par 설정
 * BLE NUS feature set을 선택하고 Serial Monitor를 115200 baud로 엽니다.
 * @par 실행
 * 업로드 후 보드를 재시작하면 5초마다 다음 Beacon 포맷으로 전환합니다.
 * @par 성공 출력
 * `advertising: iBeacon`, `Eddystone UID`, `BTHome v2`가 차례로 출력됩니다.
 * @par 흔한 오류
 * 외부 앱이 보이지 않으면 위치·Bluetooth 권한과 passive scan 지원 여부를 확인합니다.
 * @par 다음 예제
 * 수신 byte 해석은 BeaconObserver, 일반 광고 구성은 GAPPeripheral을 참고합니다.
 */

#include <NUCODE_BLE.h>

namespace
{

    enum class BeaconFormat : uint8_t
    {
        i_beacon,
        eddystone_uid,
        bthome_v2,
    };

    constexpr unsigned long format_interval_ms = 5000UL;
    BeaconFormat activeFormat = BeaconFormat::i_beacon;
    unsigned long formatStartedAt = 0UL;
    uint8_t packetId = 0U;

    /** @brief 겹치지 않는 고정 길이 byte 배열을 복사합니다. */
    void copyBytes(uint8_t *destination, const uint8_t *source, size_t length)
    {
        for (size_t index = 0U; index < length; ++index)
        {
            destination[index] = source[index];
        }
    }

    /** @brief iBeacon manufacturer data를 구성해 non-connectable 광고를 시작합니다. */
    bool startIBeacon()
    {
        nucode::ble::BLEIBeaconFrame frame;
        const uint8_t uuid[] = {
            0x12U, 0x34U, 0x56U, 0x78U, 0x12U, 0x34U, 0x56U, 0x78U,
            0x12U, 0x34U, 0x56U, 0x78U, 0x9aU, 0xbcU, 0xdeU, 0xf0U,
        };
        copyBytes(frame.uuid, uuid, sizeof(uuid));
        frame.major = 1U;
        frame.minor = 54U;
        frame.measured_power_dbm = -59;

        uint8_t payload[nucode::ble::BLEBeaconCodec::i_beacon_manufacturer_data_length] = {};
        size_t length = 0U;
        if (nucode::ble::BLEBeaconCodec::encodeIBeacon(
                frame, payload, sizeof(payload), length) !=
            nucode::ble::BLEBeaconCodecError::none)
        {
            return false;
        }
        return BLEAdvertising.setManufacturerData(
                   nucode::ble::BLEBeaconCodec::i_beacon_company_id, payload, length) &&
               BLEAdvertising.start();
    }

    /** @brief Eddystone UID service data를 구성해 광고를 시작합니다. */
    bool startEddystoneUid()
    {
        nucode::ble::BLEEddystoneUidFrame frame;
        frame.tx_power_at_zero_meters_dbm = -20;
        const uint8_t namespaceId[] = {
            0x6eU, 0x75U, 0x63U, 0x6fU, 0x64U, 0x65U, 0x2dU, 0x6eU, 0x75U, 0x35U,
        };
        const uint8_t instanceId[] = {0x34U, 0x64U, 0x6bU, 0x00U, 0x00U, 0x01U};
        copyBytes(frame.namespace_id, namespaceId, sizeof(namespaceId));
        copyBytes(frame.instance_id, instanceId, sizeof(instanceId));

        uint8_t payload[nucode::ble::BLEBeaconCodec::eddystone_uid_service_data_length] = {};
        size_t length = 0U;
        const nucode::ble::BLEUuid service(
            nucode::ble::BLEBeaconCodec::eddystone_service_uuid);
        if (nucode::ble::BLEBeaconCodec::encodeEddystoneUid(
                frame, payload, sizeof(payload), length) !=
                nucode::ble::BLEBeaconCodecError::none ||
            !BLEAdvertising.addServiceUuid(service))
        {
            return false;
        }
        return BLEAdvertising.setServiceData(service, payload, length) && BLEAdvertising.start();
    }

    /** @brief 합성 온습도를 담은 비암호화 BTHome v2 광고를 시작합니다. */
    bool startBTHome()
    {
        nucode::ble::BLEBTHomeSensorFrame frame;
        frame.packet_id = packetId++;
        frame.temperature_centi_celsius = 2350;
        frame.humidity_centi_percent = 4800U;

        uint8_t payload[nucode::ble::BLEBeaconCodec::bthome_sensor_service_data_length] = {};
        size_t length = 0U;
        const nucode::ble::BLEUuid service(nucode::ble::BLEBeaconCodec::bthome_service_uuid);
        if (nucode::ble::BLEBeaconCodec::encodeBTHomeSensor(
                frame, payload, sizeof(payload), length) !=
                nucode::ble::BLEBeaconCodecError::none ||
            !BLEAdvertising.addServiceUuid(service))
        {
            return false;
        }
        return BLEAdvertising.setServiceData(service, payload, length) && BLEAdvertising.start();
    }

    /** @brief 공통 legacy advertising 설정 뒤 선택한 포맷을 시작합니다. */
    bool startFormat(BeaconFormat format)
    {
        if (!BLEAdvertising.clear() || !BLEAdvertising.setConnectable(false) ||
            !BLEAdvertising.setFlags(0x06U) ||
            !BLEAdvertising.setInterval(0x00a0U, 0x00f0U))
        {
            return false;
        }

        bool started = false;
        const char *label = nullptr;
        switch (format)
        {
            case BeaconFormat::i_beacon:
                label = "advertising: iBeacon";
                started = startIBeacon();
                break;
            case BeaconFormat::eddystone_uid:
                label = "advertising: Eddystone UID";
                started = startEddystoneUid();
                break;
            case BeaconFormat::bthome_v2:
                label = "advertising: BTHome v2";
                started = startBTHome();
                break;
        }
        if (started && label != nullptr)
        {
            Serial.println(label);
        }
        return started;
    }

    /** @brief 다음 Beacon 포맷을 반환합니다. */
    BeaconFormat nextFormat(BeaconFormat format)
    {
        switch (format)
        {
            case BeaconFormat::i_beacon:
                return BeaconFormat::eddystone_uid;
            case BeaconFormat::eddystone_uid:
                return BeaconFormat::bthome_v2;
            case BeaconFormat::bthome_v2:
                return BeaconFormat::i_beacon;
        }
        return BeaconFormat::i_beacon;
    }

} // namespace

void setup()
{
    Serial.begin(115200);
    if (!BLEDevice.begin("NU54-BEACON") || !startFormat(activeFormat))
    {
        Serial.println("beacon advertising start failed");
        return;
    }
    formatStartedAt = millis();
}

void loop()
{
    BLEDevice.poll();
    if (millis() - formatStartedAt < format_interval_ms)
    {
        return;
    }

    if (!BLEAdvertising.stop())
    {
        Serial.println("beacon advertising stop failed");
        formatStartedAt = millis();
        return;
    }
    activeFormat = nextFormat(activeFormat);
    if (!startFormat(activeFormat))
    {
        Serial.println("beacon advertising restart failed");
    }
    formatStartedAt = millis();
}
