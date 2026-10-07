/**
 * @file main.cpp
 * @brief 두 NU54DK에서 세 Beacon 형식의 600개 광고 수신을 검증합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <Arduino.h>
#include <NUCODE_BLE.h>

#include <zephyr/kernel.h>

#include <cstddef>
#include <cstdint>
#include <string.h>

#ifndef M33_BEACON_CORE_REVISION
#error "M33_BEACON_CORE_REVISION is required"
#endif

namespace
{

    constexpr char protocol[] = "M33BEACON|1";
    constexpr char start_prefix[] = "M33BEACON|1|START|nonce=";
    constexpr char stop_prefix[] = "M33BEACON|1|STOP|nonce=";
    constexpr std::size_t nonce_length = 32U;
    constexpr std::uint32_t packet_target = 600U;
    constexpr std::uint32_t per_format_target = 150U;
    constexpr std::uint32_t unique_target = 10U;
    constexpr std::uint32_t switch_target = 90U;
    constexpr std::int64_t switch_interval_ms = 1500;
    constexpr std::int64_t session_timeout_ms = 170000;

    enum class BeaconFormat : std::uint8_t
    {
        i_beacon,
        eddystone,
        bthome,
    };

    char command[128] = {};
    char nonce[nonce_length + 1U] = {};
    std::size_t command_length = 0U;
    bool started = false;
    bool finished = false;
    bool stop_requested = false;
    bool callback_context_valid = true;
    bool codec_negative_pass = false;
    std::int64_t deadline_ms = 0;
    struct k_thread *main_thread = nullptr;

#if defined(NUCODE_M33_BEACON_ADVERTISER)
    BeaconFormat active_format = BeaconFormat::i_beacon;
    std::uint8_t format_sequences[3] = {};
    std::uint32_t switches = 0U;
    std::int64_t next_switch_ms = 0;
#else
    bool seen[3][256] = {};
    std::uint32_t raw_counts[3] = {};
    std::uint32_t unique_counts[3] = {};
    std::uint32_t semantic_errors = 0U;
#endif

    /** @brief 현재 image의 고정 역할 이름을 반환합니다. */
    const char *roleName()
    {
#if defined(NUCODE_M33_BEACON_ADVERTISER)
        return "advertiser";
#else
        return "observer";
#endif
    }

    /** @brief 모든 결과 record에 nonce와 exact revision을 결합합니다. */
    void printSuffix()
    {
        Serial.print("|nonce=");
        Serial.print(nonce);
        Serial.print("|core=");
        Serial.print(M33_BEACON_CORE_REVISION);
    }

    /** @brief 첫 오류만 bounded protocol로 출력합니다. */
    void fail(const char *stage, int code = 0)
    {
        if (finished)
        {
            return;
        }
        Serial.print(protocol);
        Serial.print("|FAIL|role=");
        Serial.print(roleName());
        Serial.print("|stage=");
        Serial.print(stage);
        Serial.print("|code=");
        Serial.print(code);
        printSuffix();
        Serial.println();
        finished = true;
    }

    /** @brief STOP 자원 해제 실패를 완료 상태와 무관하게 한 번 보고합니다. */
    void cleanupFail(const char *stage, int code)
    {
        Serial.print(protocol);
        Serial.print("|FAIL|role=");
        Serial.print(roleName());
        Serial.print("|stage=");
        Serial.print(stage);
        Serial.print("|code=");
        Serial.print(code);
        printSuffix();
        Serial.print("|advertising=");
        Serial.print(BLEAdvertising.running() ? 1 : 0);
        Serial.print("|scan=");
        Serial.print(BLEScan.running() ? 1 : 0);
        Serial.print("|device=");
        Serial.print(BLEDevice.initialized() ? 1 : 0);
        Serial.println();
        stop_requested = false;
        started = false;
    }

    /** @brief callback이 Arduino main thread에서 dispatch됐는지 확인합니다. */
    [[maybe_unused]] void checkCallbackContext()
    {
        if (k_current_get() != main_thread)
        {
            callback_context_valid = false;
            fail("callback_context");
        }
    }

    /** @brief START record의 nonce와 exact revision을 검증합니다. */
    bool acceptStart()
    {
        const std::size_t prefix_length = ::strlen(start_prefix);
        if (::strncmp(command, start_prefix, prefix_length) != 0)
        {
            return false;
        }
        const char *cursor = command + prefix_length;
        for (std::size_t index = 0U; index < nonce_length; ++index)
        {
            const char value = cursor[index];
            if (!((value >= '0' && value <= '9') || (value >= 'a' && value <= 'f')))
            {
                return false;
            }
        }
        constexpr char core_prefix[] = "|core=";
        if (::strncmp(cursor + nonce_length, core_prefix, sizeof(core_prefix) - 1U) != 0 ||
            ::strcmp(cursor + nonce_length + sizeof(core_prefix) - 1U, M33_BEACON_CORE_REVISION) !=
                0)
        {
            return false;
        }
        ::memcpy(nonce, cursor, nonce_length);
        nonce[nonce_length] = '\0';
        return true;
    }

    /** @brief 공통 코덱의 target-side 길이와 값 거부를 확인합니다. */
    bool validateCodecNegativePaths()
    {
        nucode::ble::BLEBTHomeSensorFrame invalid;
        invalid.humidity_centi_percent = 10001U;
        std::uint8_t output[32] = {};
        std::size_t length = 0U;
        if (nucode::ble::BLEBeaconCodec::encodeBTHomeSensor(invalid, output, sizeof(output),
                                                            length) !=
            nucode::ble::BLEBeaconCodecError::invalid_value)
        {
            return false;
        }
        nucode::ble::BLEIBeaconFrame decoded;
        return nucode::ble::BLEBeaconCodec::decodeIBeaconManufacturerData(output, 1U, decoded) ==
               nucode::ble::BLEBeaconCodecError::invalid_value;
    }

#if defined(NUCODE_M33_BEACON_ADVERTISER)
    /** @brief iBeacon 시험 frame을 현재 sequence와 실행 nonce로 구성합니다. */
    bool startIBeacon(std::uint8_t sequence)
    {
        nucode::ble::BLEIBeaconFrame frame;
        const std::uint8_t magic[] = {0x4dU, 0x33U, 0x33U, 0x49U};
        ::memcpy(frame.uuid, magic, sizeof(magic));
        ::memcpy(frame.uuid + sizeof(magic), nonce, 8U);
        frame.major = 0x3349U;
        frame.minor = sequence;
        frame.measured_power_dbm = -59;

        std::uint8_t payload[nucode::ble::BLEBeaconCodec::i_beacon_manufacturer_data_length] = {};
        std::size_t length = 0U;
        return nucode::ble::BLEBeaconCodec::encodeIBeacon(frame, payload, sizeof(payload),
                                                          length) ==
                   nucode::ble::BLEBeaconCodecError::none &&
               BLEAdvertising.setManufacturerData(nucode::ble::BLEBeaconCodec::i_beacon_company_id,
                                                  payload, length) &&
               BLEAdvertising.start();
    }

    /** @brief Eddystone UID 시험 frame을 현재 sequence와 실행 nonce로 구성합니다. */
    bool startEddystone(std::uint8_t sequence)
    {
        nucode::ble::BLEEddystoneUidFrame frame;
        const std::uint8_t magic[] = {0x4dU, 0x33U, 0x33U, 0x45U};
        ::memcpy(frame.namespace_id, magic, sizeof(magic));
        ::memcpy(frame.namespace_id + sizeof(magic), nonce, 6U);
        frame.instance_id[0] = 0x42U;
        frame.instance_id[1] = 0x43U;
        frame.instance_id[2] = 0x4eU;
        frame.instance_id[3] = sequence;
        frame.instance_id[4] = static_cast<std::uint8_t>(~sequence);
        frame.instance_id[5] = 0x01U;
        frame.tx_power_at_zero_meters_dbm = -20;

        std::uint8_t payload[nucode::ble::BLEBeaconCodec::eddystone_uid_service_data_length] = {};
        std::size_t length = 0U;
        const nucode::ble::BLEUuid service(nucode::ble::BLEBeaconCodec::eddystone_service_uuid);
        return nucode::ble::BLEBeaconCodec::encodeEddystoneUid(frame, payload, sizeof(payload),
                                                               length) ==
                   nucode::ble::BLEBeaconCodecError::none &&
               BLEAdvertising.addServiceUuid(service) &&
               BLEAdvertising.setServiceData(service, payload, length) && BLEAdvertising.start();
    }

    /** @brief BTHome 합성 측정 frame을 현재 sequence와 nonce로 구성합니다. */
    bool startBTHome(std::uint8_t sequence)
    {
        nucode::ble::BLEBTHomeSensorFrame frame;
        frame.packet_id = sequence;
        frame.temperature_centi_celsius =
            static_cast<std::int16_t>(2000 + static_cast<unsigned char>(nonce[0]));
        frame.humidity_centi_percent =
            static_cast<std::uint16_t>(4000U + static_cast<unsigned char>(nonce[1]));

        std::uint8_t payload[nucode::ble::BLEBeaconCodec::bthome_sensor_service_data_length] = {};
        std::size_t length = 0U;
        const nucode::ble::BLEUuid service(nucode::ble::BLEBeaconCodec::bthome_service_uuid);
        return nucode::ble::BLEBeaconCodec::encodeBTHomeSensor(frame, payload, sizeof(payload),
                                                               length) ==
                   nucode::ble::BLEBeaconCodecError::none &&
               BLEAdvertising.addServiceUuid(service) &&
               BLEAdvertising.setServiceData(service, payload, length) && BLEAdvertising.start();
    }

    /** @brief legacy 광고를 비우고 선택한 Beacon frame을 시작합니다. */
    bool startFormat(BeaconFormat format)
    {
        if (!BLEAdvertising.clear() || !BLEAdvertising.setConnectable(false) ||
            !BLEAdvertising.setFlags(0x06U) || !BLEAdvertising.setInterval(0x00a0U, 0x00a0U))
        {
            return false;
        }
        const std::uint8_t index = static_cast<std::uint8_t>(format);
        const std::uint8_t sequence = format_sequences[index]++;
        switch (format)
        {
        case BeaconFormat::i_beacon:
            return startIBeacon(sequence);
        case BeaconFormat::eddystone:
            return startEddystone(sequence);
        case BeaconFormat::bthome:
            return startBTHome(sequence);
        }
        return false;
    }

    /** @brief 세 Beacon 형식을 고정 순서로 순환합니다. */
    BeaconFormat nextFormat(BeaconFormat format)
    {
        switch (format)
        {
        case BeaconFormat::i_beacon:
            return BeaconFormat::eddystone;
        case BeaconFormat::eddystone:
            return BeaconFormat::bthome;
        case BeaconFormat::bthome:
            return BeaconFormat::i_beacon;
        }
        return BeaconFormat::i_beacon;
    }

    /** @brief 광고 전환 분모와 target-side negative 결과를 출력합니다. */
    void finishAdvertiser()
    {
        Serial.print(protocol);
        Serial.print("|RESULT|role=advertiser|switches=");
        Serial.print(switches);
        Serial.print("|ibeacon_sequences=");
        Serial.print(format_sequences[0]);
        Serial.print("|eddystone_sequences=");
        Serial.print(format_sequences[1]);
        Serial.print("|bthome_sequences=");
        Serial.print(format_sequences[2]);
        Serial.print("|codec_negative=");
        Serial.print(codec_negative_pass ? "pass" : "fail");
        printSuffix();
        Serial.println();
        Serial.print(protocol);
        Serial.print("|END|role=advertiser|status=pass");
        printSuffix();
        Serial.println();
        finished = true;
    }
#else
    /** @brief 인식한 format과 sequence를 중복 포함 수신 분모에 반영합니다. */
    void observe(std::uint8_t format, std::uint8_t sequence)
    {
        ++raw_counts[format];
        if (!seen[format][sequence])
        {
            seen[format][sequence] = true;
            ++unique_counts[format];
        }
    }

    /** @brief iBeacon 시험 식별자와 nonce를 검사합니다. */
    bool validIBeacon(const nucode::ble::BLEIBeaconFrame &frame)
    {
        const std::uint8_t magic[] = {0x4dU, 0x33U, 0x33U, 0x49U};
        return ::memcmp(frame.uuid, magic, sizeof(magic)) == 0 &&
               ::memcmp(frame.uuid + sizeof(magic), nonce, 8U) == 0 && frame.major == 0x3349U &&
               frame.measured_power_dbm == -59;
    }

    /** @brief Eddystone UID 시험 식별자와 nonce를 검사합니다. */
    bool validEddystone(const nucode::ble::BLEEddystoneUidFrame &frame)
    {
        const std::uint8_t magic[] = {0x4dU, 0x33U, 0x33U, 0x45U};
        const std::uint8_t sequence = frame.instance_id[3];
        return ::memcmp(frame.namespace_id, magic, sizeof(magic)) == 0 &&
               ::memcmp(frame.namespace_id + sizeof(magic), nonce, 6U) == 0 &&
               frame.instance_id[0] == 0x42U && frame.instance_id[1] == 0x43U &&
               frame.instance_id[2] == 0x4eU &&
               frame.instance_id[4] == static_cast<std::uint8_t>(~sequence) &&
               frame.instance_id[5] == 0x01U && frame.tx_power_at_zero_meters_dbm == -20;
    }

    /** @brief BTHome 합성 측정값이 실행 nonce와 일치하는지 검사합니다. */
    bool validBTHome(const nucode::ble::BLEBTHomeSensorFrame &frame)
    {
        return frame.temperature_centi_celsius ==
                   static_cast<std::int16_t>(2000 + static_cast<unsigned char>(nonce[0])) &&
               frame.humidity_centi_percent ==
                   static_cast<std::uint16_t>(4000U + static_cast<unsigned char>(nonce[1])) &&
               !frame.trigger_based;
    }

    /** @brief scan payload를 세 코덱으로 해석하고 시험 frame만 계수합니다. */
    void onScanResult(const nucode::ble::BLEScanResult &result, void *)
    {
        checkCallbackContext();
        if (!started || finished)
        {
            return;
        }

        nucode::ble::BLEIBeaconFrame i_beacon;
        if (nucode::ble::BLEBeaconCodec::decodeIBeaconAdvertisement(
                result.payload, result.payload_length, i_beacon) ==
            nucode::ble::BLEBeaconCodecError::none)
        {
            if (validIBeacon(i_beacon))
            {
                observe(0U, static_cast<std::uint8_t>(i_beacon.minor));
            }
            else if (i_beacon.major == 0x3349U)
            {
                ++semantic_errors;
            }
            return;
        }

        nucode::ble::BLEEddystoneUidFrame eddystone;
        if (nucode::ble::BLEBeaconCodec::decodeEddystoneUidAdvertisement(
                result.payload, result.payload_length, eddystone) ==
            nucode::ble::BLEBeaconCodecError::none)
        {
            if (validEddystone(eddystone))
            {
                observe(1U, eddystone.instance_id[3]);
            }
            else if (eddystone.instance_id[0] == 0x42U && eddystone.instance_id[1] == 0x43U &&
                     eddystone.instance_id[2] == 0x4eU)
            {
                ++semantic_errors;
            }
            return;
        }

        nucode::ble::BLEBTHomeSensorFrame bthome;
        if (nucode::ble::BLEBeaconCodec::decodeBTHomeSensorAdvertisement(
                result.payload, result.payload_length, bthome) ==
                nucode::ble::BLEBeaconCodecError::none &&
            validBTHome(bthome))
        {
            observe(2U, bthome.packet_id);
        }
    }

    /** @brief 600개 수신과 format별 분모를 모두 만족했는지 반환합니다. */
    bool observerComplete()
    {
        const std::uint32_t total = raw_counts[0] + raw_counts[1] + raw_counts[2];
        return total >= packet_target && raw_counts[0] >= per_format_target &&
               raw_counts[1] >= per_format_target && raw_counts[2] >= per_format_target &&
               unique_counts[0] >= unique_target && unique_counts[1] >= unique_target &&
               unique_counts[2] >= unique_target;
    }

    /** @brief format별 raw·unique 수신과 semantic 오류를 출력합니다. */
    void finishObserver()
    {
        Serial.print(protocol);
        Serial.print("|RESULT|role=observer|raw=");
        Serial.print(raw_counts[0] + raw_counts[1] + raw_counts[2]);
        Serial.print("|ibeacon_raw=");
        Serial.print(raw_counts[0]);
        Serial.print("|eddystone_raw=");
        Serial.print(raw_counts[1]);
        Serial.print("|bthome_raw=");
        Serial.print(raw_counts[2]);
        Serial.print("|ibeacon_unique=");
        Serial.print(unique_counts[0]);
        Serial.print("|eddystone_unique=");
        Serial.print(unique_counts[1]);
        Serial.print("|bthome_unique=");
        Serial.print(unique_counts[2]);
        Serial.print("|semantic_errors=");
        Serial.print(semantic_errors);
        Serial.print("|dropped=");
        Serial.print(BLEScan.droppedResults());
        Serial.print("|callback_context=");
        Serial.print(callback_context_valid ? "pass" : "fail");
        Serial.print("|codec_negative=");
        Serial.print(codec_negative_pass ? "pass" : "fail");
        printSuffix();
        Serial.println();
        Serial.print(protocol);
        Serial.print("|END|role=observer|status=pass");
        printSuffix();
        Serial.println();
        finished = true;
    }

    /** @brief timeout 원인 분리를 위해 현재 수신 분모를 실패 직전에 출력합니다. */
    void printObserverSnapshot()
    {
        Serial.print(protocol);
        Serial.print("|SNAPSHOT|role=observer|raw=");
        Serial.print(raw_counts[0] + raw_counts[1] + raw_counts[2]);
        Serial.print("|ibeacon_raw=");
        Serial.print(raw_counts[0]);
        Serial.print("|eddystone_raw=");
        Serial.print(raw_counts[1]);
        Serial.print("|bthome_raw=");
        Serial.print(raw_counts[2]);
        Serial.print("|ibeacon_unique=");
        Serial.print(unique_counts[0]);
        Serial.print("|eddystone_unique=");
        Serial.print(unique_counts[1]);
        Serial.print("|bthome_unique=");
        Serial.print(unique_counts[2]);
        Serial.print("|semantic_errors=");
        Serial.print(semantic_errors);
        Serial.print("|dropped=");
        Serial.print(BLEScan.droppedResults());
        printSuffix();
        Serial.println();
    }
#endif

    /** @brief 검증된 START 뒤 image 역할의 radio 시험을 시작합니다. */
    void beginProtocol()
    {
        finished = false;
        if (!acceptStart())
        {
            fail("start_record");
            return;
        }
        stop_requested = false;
        callback_context_valid = true;
#if defined(NUCODE_M33_BEACON_ADVERTISER)
        active_format = BeaconFormat::i_beacon;
        ::memset(format_sequences, 0, sizeof(format_sequences));
        switches = 0U;
        next_switch_ms = 0;
#else
        ::memset(seen, 0, sizeof(seen));
        ::memset(raw_counts, 0, sizeof(raw_counts));
        ::memset(unique_counts, 0, sizeof(unique_counts));
        semantic_errors = 0U;
#endif
        if (!BLEDevice.initialized() && !BLEDevice.begin(roleName()))
        {
            fail("device_restart", BLEDevice.lastDriverError());
            return;
        }
        codec_negative_pass = validateCodecNegativePaths();
        if (!codec_negative_pass)
        {
            fail("codec_negative");
            return;
        }
        started = true;
        deadline_ms = k_uptime_get() + session_timeout_ms;
        Serial.print(protocol);
        Serial.print("|BEGIN|role=");
        Serial.print(roleName());
        printSuffix();
        Serial.println();
#if defined(NUCODE_M33_BEACON_ADVERTISER)
        if (!startFormat(active_format))
        {
            fail("advertising_start", BLEDevice.lastDriverError());
            return;
        }
        switches = 1U;
        next_switch_ms = k_uptime_get() + switch_interval_ms;
#else
        if (!BLEScan.clearFilters() || !BLEScan.start(false))
        {
            fail("scan_start", BLEDevice.lastDriverError());
        }
#endif
    }

    /** @brief STOP 때 광고·검색과 library 자원을 bounded하게 회수합니다. */
    void stopProtocol()
    {
#if defined(NUCODE_M33_BEACON_ADVERTISER)
        if (BLEAdvertising.running() && !BLEAdvertising.stop())
        {
            const int error = BLEDevice.lastDriverError();
            BLEDevice.end();
            cleanupFail("cleanup_advertising_stop", error);
            return;
        }
#else
        if (BLEScan.running() && !BLEScan.stop())
        {
            const int error = BLEDevice.lastDriverError();
            BLEDevice.end();
            cleanupFail("cleanup_scan_stop", error);
            return;
        }
#endif
        BLEDevice.end();
        if (BLEAdvertising.running() || BLEScan.running() || BLEDevice.initialized())
        {
            cleanupFail("cleanup_resource_state", BLEDevice.lastDriverError());
            return;
        }
        Serial.print(protocol);
        Serial.print("|STOPPED|role=");
        Serial.print(roleName());
        printSuffix();
        Serial.print("|advertising=0|scan=0|device=0");
        Serial.println();
        stop_requested = false;
        started = false;
    }

    /** @brief CR/LF 명령을 고정 buffer로 읽어 PROBE·START·STOP만 처리합니다. */
    void pollCommand()
    {
        while (Serial.available() > 0)
        {
            const int input = Serial.read();
            if (input == '\r')
            {
                continue;
            }
            if (input != '\n')
            {
                if (command_length + 1U >= sizeof(command))
                {
                    command_length = 0U;
                    fail("command_overflow");
                    return;
                }
                command[command_length++] = static_cast<char>(input);
                command[command_length] = '\0';
                continue;
            }
            if (::strcmp(command, "M33BEACON|1|PROBE") == 0)
            {
                Serial.print(protocol);
                Serial.print("|READY|role=");
                Serial.print(roleName());
                Serial.print("|core=");
                Serial.println(M33_BEACON_CORE_REVISION);
            }
            else if (!started && ::strncmp(command, start_prefix, ::strlen(start_prefix)) == 0)
            {
                beginProtocol();
            }
            else if (started && ::strncmp(command, stop_prefix, ::strlen(stop_prefix)) == 0)
            {
                const char *requested_nonce = command + ::strlen(stop_prefix);
                if (::strcmp(requested_nonce, nonce) == 0)
                {
                    stop_requested = true;
                }
            }
            command_length = 0U;
            command[0] = '\0';
        }
    }

} // namespace

void setup()
{
    main_thread = k_current_get();
    Serial.begin(115200);
    const std::int64_t serial_deadline = k_uptime_get() + 5000;
    while (!Serial && k_uptime_get() < serial_deadline)
    {
        delay(10);
    }
#if !defined(NUCODE_M33_BEACON_ADVERTISER)
    BLEScan.onResult(onScanResult);
#endif
    if (!BLEDevice.begin(roleName()))
    {
        fail("device_begin", BLEDevice.lastDriverError());
    }
}

void loop()
{
    pollCommand();
    if (BLEDevice.initialized())
    {
        BLEDevice.poll();
    }
    if (started && !finished && k_uptime_get() >= deadline_ms)
    {
#if !defined(NUCODE_M33_BEACON_ADVERTISER)
        printObserverSnapshot();
#endif
        fail("session_timeout");
    }
#if defined(NUCODE_M33_BEACON_ADVERTISER)
    if (started && !finished && k_uptime_get() >= next_switch_ms)
    {
        if (switches >= switch_target)
        {
            finishAdvertiser();
        }
        else
        {
            if (!BLEAdvertising.stop())
            {
                fail("advertising_stop", BLEDevice.lastDriverError());
            }
            else
            {
                active_format = nextFormat(active_format);
                if (!startFormat(active_format))
                {
                    fail("advertising_restart", BLEDevice.lastDriverError());
                }
                else
                {
                    ++switches;
                    next_switch_ms += switch_interval_ms;
                }
            }
        }
    }
#else
    if (started && !finished && observerComplete())
    {
        finishObserver();
    }
#endif
    if (stop_requested)
    {
        stopProtocol();
    }
    delay(1);
}
