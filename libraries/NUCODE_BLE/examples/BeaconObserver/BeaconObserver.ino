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
 * Apple·Google peer와 외장 Beacon 실기 상호운용은 사용자 후속 검증 항목
 * @par Metadata
 * identity `NUCODE_BLE/BeaconObserver`, sha256 `524b7b09093c383f2fd86580f6d7deb0b5b05869c532f0943fe21439151f2722`
 * @nucode_example_setup_end */

/**
 * @file BeaconObserver.ino
 * @brief passive scan으로 iBeacon, Eddystone UID, BTHome v2 광고를 구분해 출력합니다.
 * @par 목적
 * 세 가지 Beacon 포맷의 원본 AD payload를 공통 코덱으로 안전하게 해석합니다.
 * @par 준비물
 * NU54DK 2대를 권장하며 한 대에는 BeaconAdvertiser를 업로드합니다.
 * @par 설정
 * BLE NUS feature set을 선택하고 Serial Monitor를 115200 baud로 엽니다.
 * @par 실행
 * BeaconAdvertiser를 먼저 실행한 뒤 이 보드의 passive scan 결과를 관찰합니다.
 * @par 성공 출력
 * 포맷 이름과 iBeacon major/minor, Eddystone UID, BTHome 온습도가 출력됩니다.
 * @par 흔한 오류
 * 결과가 없으면 두 보드의 안테나 간격, 광고 보드 전원과 profile을 확인합니다.
 * @par 다음 예제
 * 광고 송신은 BeaconAdvertiser, 일반 scan filter는 GAPCentral을 참고합니다.
 */

#include <NUCODE_BLE.h>

namespace
{

    /** @brief 한 byte를 두 자리 16진수로 출력합니다. */
    void printHexByte(uint8_t value)
    {
        if (value < 0x10U)
        {
            Serial.print('0');
        }
        Serial.print(value, HEX);
    }

    /** @brief 0.01 단위 signed 값을 소수 둘째 자리까지 출력합니다. */
    void printSignedCenti(int16_t value)
    {
        int32_t magnitude = value;
        if (magnitude < 0)
        {
            Serial.print('-');
            magnitude = -magnitude;
        }
        Serial.print(magnitude / 100L);
        Serial.print('.');
        if (magnitude % 100L < 10L)
        {
            Serial.print('0');
        }
        Serial.print(magnitude % 100L);
    }

    /** @brief 0.01 단위 unsigned 값을 소수 둘째 자리까지 출력합니다. */
    void printUnsignedCenti(uint16_t value)
    {
        Serial.print(value / 100U);
        Serial.print('.');
        if (value % 100U < 10U)
        {
            Serial.print('0');
        }
        Serial.print(value % 100U);
    }

    /** @brief iBeacon 식별 필드를 한 줄로 출력합니다. */
    void printIBeacon(const nucode::ble::BLEIBeaconFrame &frame, int8_t rssi)
    {
        Serial.print("iBeacon UUID=");
        for (size_t index = 0U; index < sizeof(frame.uuid); ++index)
        {
            printHexByte(frame.uuid[index]);
        }
        Serial.print(" major=");
        Serial.print(frame.major);
        Serial.print(" minor=");
        Serial.print(frame.minor);
        Serial.print(" RSSI=");
        Serial.println(rssi);
    }

    /** @brief Eddystone namespace와 instance를 한 줄로 출력합니다. */
    void printEddystone(const nucode::ble::BLEEddystoneUidFrame &frame, int8_t rssi)
    {
        Serial.print("Eddystone UID=");
        for (size_t index = 0U; index < sizeof(frame.namespace_id); ++index)
        {
            printHexByte(frame.namespace_id[index]);
        }
        Serial.print('/');
        for (size_t index = 0U; index < sizeof(frame.instance_id); ++index)
        {
            printHexByte(frame.instance_id[index]);
        }
        Serial.print(" RSSI=");
        Serial.println(rssi);
    }

    /** @brief BTHome packet ID와 합성 온습도를 한 줄로 출력합니다. */
    void printBTHome(const nucode::ble::BLEBTHomeSensorFrame &frame, int8_t rssi)
    {
        Serial.print("BTHome packet=");
        Serial.print(frame.packet_id);
        Serial.print(" temperature=");
        printSignedCenti(frame.temperature_centi_celsius);
        Serial.print("C humidity=");
        printUnsignedCenti(frame.humidity_centi_percent);
        Serial.print("% RSSI=");
        Serial.println(rssi);
    }

} // namespace

/** @brief scan payload를 세 코덱에 순서대로 적용하고 인식된 포맷만 출력합니다. */
void onScanResult(const nucode::ble::BLEScanResult &result, void *context)
{
    static_cast<void>(context);

    nucode::ble::BLEIBeaconFrame iBeacon;
    if (nucode::ble::BLEBeaconCodec::decodeIBeaconAdvertisement(
            result.payload, result.payload_length, iBeacon) ==
        nucode::ble::BLEBeaconCodecError::none)
    {
        printIBeacon(iBeacon, result.rssi);
        return;
    }

    nucode::ble::BLEEddystoneUidFrame eddystone;
    if (nucode::ble::BLEBeaconCodec::decodeEddystoneUidAdvertisement(
            result.payload, result.payload_length, eddystone) ==
        nucode::ble::BLEBeaconCodecError::none)
    {
        printEddystone(eddystone, result.rssi);
        return;
    }

    nucode::ble::BLEBTHomeSensorFrame bthome;
    if (nucode::ble::BLEBeaconCodec::decodeBTHomeSensorAdvertisement(
            result.payload, result.payload_length, bthome) ==
        nucode::ble::BLEBeaconCodecError::none)
    {
        printBTHome(bthome, result.rssi);
    }
}

void setup()
{
    Serial.begin(115200);
    BLEScan.onResult(onScanResult);
    if (!BLEDevice.begin("NU54-BEACON-SCAN") || !BLEScan.clearFilters() ||
        !BLEScan.start(false))
    {
        Serial.println("beacon passive scan failed");
    }
}

void loop()
{
    BLEDevice.poll();
}
