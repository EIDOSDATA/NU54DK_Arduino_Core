/**
 * @file main.cpp
 * @brief 두 NU54DK 사이에서 일곱 BLE profile의 실제 GATT 동작을 검증합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <Arduino.h>
#include <NUCODE_BLE_Security.h>
#include <internal/NUCODE_BLE_Internal.h>

#include <zephyr/bluetooth/att.h>
#include <zephyr/bluetooth/gatt.h>
#include <zephyr/bluetooth/uuid.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/atomic.h>
#include <zephyr/sys/byteorder.h>
#include <zephyr/sys/util.h>

#include <cstddef>
#include <cstdint>
#include <string.h>

namespace
{

    constexpr char protocol[] = "M30PROFILE|1";
    constexpr std::size_t nonce_characters = 32U;
    constexpr std::size_t nonce_bytes = 16U;
    constexpr std::uint16_t company_id = 0x054dU;
    constexpr std::uint16_t required_operations = 100U;
    constexpr std::uint8_t catalog_entries = 7U;
    constexpr std::size_t command_capacity = 128U;
    constexpr std::int64_t protocol_timeout_ms = 120000;
    constexpr std::int64_t security_delay_ms = 300;

    char nonce[nonce_characters + 1U] = {};
    std::uint8_t nonce_binary[nonce_bytes] = {};
    char command[command_capacity] = {};
    std::size_t command_length = 0U;
    bool started = false;
    bool failed = false;
    bool secured = false;
    nucode::ble::BLEConnectionHandle connection_handle = {};
    std::int64_t deadline_ms = 0;
#if defined(NUCODE_M30_PROFILE_CENTRAL)
    std::int64_t security_due_ms = 0;
#endif

    /** @brief 현재 image 역할 이름을 반환합니다. */
    const char *roleName()
    {
#if defined(NUCODE_M30_PROFILE_CENTRAL)
        return "central";
#else
        return "peripheral";
#endif
    }

    /** @brief nonce와 exact Core revision suffix를 출력합니다. */
    void printSuffix()
    {
        Serial.print("|nonce=");
        Serial.print(nonce);
        Serial.print("|core=");
        Serial.print(M30_PROFILE_CORE_REVISION);
    }

    /** @brief protocol 실패를 민감 정보 없이 한 번만 출력합니다. */
    void fail(const char *reason)
    {
        if (!failed)
        {
            Serial.print(protocol);
            Serial.print("|FAIL|role=");
            Serial.print(roleName());
            Serial.print("|reason=");
            Serial.print(reason == nullptr ? "unknown" : reason);
            printSuffix();
            Serial.println();
        }
        failed = true;
    }

    /** @brief 소문자 128-bit nonce를 검증해 광고용 binary로 변환합니다. */
    bool decodeNonce(const char *text)
    {
        if (text == nullptr || ::strlen(text) != nonce_characters)
        {
            return false;
        }
        for (std::size_t index = 0U; index < nonce_characters; ++index)
        {
            const char value = text[index];
            if (!((value >= '0' && value <= '9') || (value >= 'a' && value <= 'f')))
            {
                return false;
            }
        }
        for (std::size_t index = 0U; index < nonce_bytes; ++index)
        {
            const char high = text[index * 2U];
            const char low = text[index * 2U + 1U];
            const std::uint8_t high_value = static_cast<std::uint8_t>(
                high <= '9' ? high - '0' : high - 'a' + 10);
            const std::uint8_t low_value = static_cast<std::uint8_t>(
                low <= '9' ? low - '0' : low - 'a' + 10);
            nonce_binary[index] = static_cast<std::uint8_t>((high_value << 4U) | low_value);
        }
        ::memcpy(nonce, text, nonce_characters + 1U);
        return true;
    }

    /** @brief START 명령이 nonce와 exact Core revision을 모두 포함하는지 검사합니다. */
    bool parseStart(const char *line)
    {
        constexpr char prefix[] = "M30PROFILE|1|START|nonce=";
        constexpr char core_marker[] = "|core=";
        const std::size_t prefix_length = sizeof(prefix) - 1U;
        if (line == nullptr || ::strncmp(line, prefix, prefix_length) != 0)
        {
            return false;
        }
        const char *value = line + prefix_length;
        if (::strlen(value) != nonce_characters + sizeof(core_marker) - 1U + 40U ||
            ::strncmp(value + nonce_characters, core_marker,
                      sizeof(core_marker) - 1U) != 0 ||
            ::strcmp(value + nonce_characters + sizeof(core_marker) - 1U,
                     M30_PROFILE_CORE_REVISION) != 0)
        {
            return false;
        }
        char parsed[nonce_characters + 1U] = {};
        ::memcpy(parsed, value, nonce_characters);
        return decodeNonce(parsed);
    }

#if defined(NUCODE_M30_PROFILE_CENTRAL)
    /** @brief scan 결과의 manufacturer field가 현재 nonce와 정확히 같은지 검사합니다. */
    bool validPayload(const nucode::ble::BLEScanResult &result)
    {
        std::size_t cursor = 0U;
        while (cursor < result.payload_length)
        {
            const std::uint8_t field_length = result.payload[cursor];
            if (field_length == 0U || cursor + field_length >= result.payload_length)
            {
                return false;
            }
            if (result.payload[cursor + 1U] == BT_DATA_MANUFACTURER_DATA &&
                field_length == nonce_bytes + 3U)
            {
                const std::uint8_t *value = &result.payload[cursor + 2U];
                return value[0] == static_cast<std::uint8_t>(company_id & 0xffU) &&
                       value[1] == static_cast<std::uint8_t>(company_id >> 8U) &&
                       ::memcmp(&value[2], nonce_binary, sizeof(nonce_binary)) == 0;
            }
            cursor += field_length + 1U;
        }
        return false;
    }
#endif

#if defined(NUCODE_M30_PROFILE_CENTRAL)

    /** @brief 일곱 profile의 원격 value handle을 고정 배열로 보존합니다. */
    struct RemoteHandles
    {
        std::uint16_t battery = 0U;
        std::uint16_t manufacturer = 0U;
        std::uint16_t keyboard = 0U;
        std::uint16_t mouse = 0U;
        std::uint16_t consumer = 0U;
        std::uint16_t heart_rate = 0U;
        std::uint16_t temperature = 0U;
        std::uint16_t humidity = 0U;
    };

    enum class CentralState : std::uint8_t
    {
        idle,
        discovering,
        subscribing,
        reading_dis,
        waiting_notifications,
        complete,
    };

    RemoteHandles handles = {};
    CentralState central_state = CentralState::idle;
    struct bt_gatt_discover_params discovery_parameters = {};
    struct bt_gatt_read_params read_parameters = {};
    struct bt_gatt_subscribe_params subscriptions[7] = {};
    struct bt_gatt_discover_params ccc_discovery[7] = {};
    atomic_t discovery_complete = ATOMIC_INIT(0);
    atomic_t subscription_complete = ATOMIC_INIT(0);
    atomic_t subscription_error = ATOMIC_INIT(0);
    atomic_t read_complete = ATOMIC_INIT(0);
    atomic_t read_error = ATOMIC_INIT(0);
    std::uint8_t subscription_index = 0U;
    std::uint16_t dis_reads = 0U;
    std::uint16_t notification_counts[7] = {};
    std::uint16_t payload_errors = 0U;
    std::uint8_t read_buffer[16] = {};
    std::size_t read_length = 0U;
    bool result_reported = false;

    /** @brief characteristic discovery에서 profile value handle을 분류합니다. */
    void captureCharacteristic(const struct bt_gatt_chrc *characteristic)
    {
        if (characteristic == nullptr || characteristic->uuid == nullptr)
        {
            return;
        }
        if (bt_uuid_cmp(characteristic->uuid, BT_UUID_BAS_BATTERY_LEVEL) == 0)
        {
            handles.battery = characteristic->value_handle;
        }
        else if (bt_uuid_cmp(characteristic->uuid, BT_UUID_DIS_MANUFACTURER_NAME) == 0)
        {
            handles.manufacturer = characteristic->value_handle;
        }
        else if (bt_uuid_cmp(characteristic->uuid, BT_UUID_HIDS_REPORT) == 0 &&
                 (characteristic->properties & BT_GATT_CHRC_NOTIFY) != 0U)
        {
            if (handles.keyboard == 0U)
            {
                handles.keyboard = characteristic->value_handle;
            }
            else if (handles.mouse == 0U)
            {
                handles.mouse = characteristic->value_handle;
            }
            else if (handles.consumer == 0U)
            {
                handles.consumer = characteristic->value_handle;
            }
            else
            {
                ++payload_errors;
            }
        }
        else if (bt_uuid_cmp(characteristic->uuid, BT_UUID_HRS_MEASUREMENT) == 0)
        {
            handles.heart_rate = characteristic->value_handle;
        }
        else if (bt_uuid_cmp(characteristic->uuid, BT_UUID_TEMPERATURE) == 0)
        {
            handles.temperature = characteristic->value_handle;
        }
        else if (bt_uuid_cmp(characteristic->uuid, BT_UUID_HUMIDITY) == 0)
        {
            handles.humidity = characteristic->value_handle;
        }
    }

    /** @brief full characteristic discovery 결과를 bounded handle 표로 복사합니다. */
    std::uint8_t onDiscovery(struct bt_conn *connection, const struct bt_gatt_attr *attribute,
                             struct bt_gatt_discover_params *parameters)
    {
        ARG_UNUSED(connection);
        if (attribute == nullptr)
        {
            ::memset(parameters, 0, sizeof(*parameters));
            atomic_set(&discovery_complete, 1);
            return BT_GATT_ITER_STOP;
        }
        captureCharacteristic(static_cast<const struct bt_gatt_chrc *>(attribute->user_data));
        return BT_GATT_ITER_CONTINUE;
    }

    /** @brief 모든 원격 characteristic의 discovery를 시작합니다. */
    void beginDiscovery()
    {
        struct bt_conn *connection = nucode::ble::internal::referenceConnection(connection_handle);
        if (connection == nullptr)
        {
            fail("discover-connection");
            return;
        }
        handles = {};
        discovery_parameters = {};
        discovery_parameters.func = onDiscovery;
        discovery_parameters.start_handle = BT_ATT_FIRST_ATTRIBUTE_HANDLE;
        discovery_parameters.end_handle = BT_ATT_LAST_ATTRIBUTE_HANDLE;
        discovery_parameters.type = BT_GATT_DISCOVER_CHARACTERISTIC;
        central_state = CentralState::discovering;
        atomic_set(&discovery_complete, 0);
        const int result = bt_gatt_discover(connection, &discovery_parameters);
        bt_conn_unref(connection);
        if (result < 0)
        {
            fail("discover-start");
        }
    }

    /** @brief 수신 handle에 따라 profile별 payload와 순번을 검증합니다. */
    std::uint8_t onNotification(struct bt_conn *connection,
                                struct bt_gatt_subscribe_params *parameters,
                                const void *data, std::uint16_t length)
    {
        ARG_UNUSED(connection);
        if (data == nullptr || parameters == nullptr)
        {
            return BT_GATT_ITER_CONTINUE;
        }
        std::size_t profile = ARRAY_SIZE(notification_counts);
        if (parameters->value_handle == handles.battery)
        {
            profile = 0U;
        }
        else if (parameters->value_handle == handles.keyboard)
        {
            profile = 1U;
        }
        else if (parameters->value_handle == handles.mouse)
        {
            profile = 2U;
        }
        else if (parameters->value_handle == handles.consumer)
        {
            profile = 3U;
        }
        else if (parameters->value_handle == handles.heart_rate)
        {
            profile = 4U;
        }
        else if (parameters->value_handle == handles.temperature)
        {
            profile = 5U;
        }
        else if (parameters->value_handle == handles.humidity)
        {
            profile = 6U;
        }
        if (profile >= ARRAY_SIZE(notification_counts))
        {
            ++payload_errors;
            return BT_GATT_ITER_CONTINUE;
        }
        const std::uint16_t expected = notification_counts[profile];
        bool valid = expected < required_operations;
        const auto *bytes = static_cast<const std::uint8_t *>(data);
        switch (profile)
        {
        case 0U:
            valid = valid && length == 1U && bytes[0] == (expected % 100U) + 1U;
            break;
        case 1U:
            valid = valid && length == 8U && bytes[0] == 0U && bytes[1] == 0U &&
                    bytes[2] == 4U + (expected % 20U);
            break;
        case 2U:
            valid = valid && length == 4U && bytes[0] == (expected % 2U) &&
                    static_cast<std::int8_t>(bytes[1]) ==
                        static_cast<std::int8_t>((expected % 11U) - 5);
            break;
        case 3U:
            valid = valid && length == 2U && sys_get_le16(bytes) == 0x00e9U;
            break;
        case 4U:
            valid = valid && length == 2U && bytes[1] == 60U + (expected % 100U);
            break;
        case 5U:
            valid = valid && length == 2U &&
                    static_cast<std::int16_t>(sys_get_le16(bytes)) == 2000 + expected;
            break;
        case 6U:
            valid = valid && length == 2U && sys_get_le16(bytes) == 4000U + expected;
            break;
        default:
            valid = false;
            break;
        }
        if (!valid)
        {
            ++payload_errors;
        }
        else
        {
            ++notification_counts[profile];
        }
        return BT_GATT_ITER_CONTINUE;
    }

    /** @brief CCC write 결과를 main loop 상태 기계로 전달합니다. */
    void onSubscribed(struct bt_conn *connection, std::uint8_t error,
                      struct bt_gatt_subscribe_params *parameters)
    {
        ARG_UNUSED(connection);
        ARG_UNUSED(parameters);
        atomic_set(&subscription_error, error);
        atomic_set(&subscription_complete, 1);
    }

    /** @brief 현재 index profile의 CCC 자동 discovery와 구독을 시작합니다. */
    void beginSubscription()
    {
        const std::uint16_t value_handles[] = {
            handles.battery,    handles.keyboard, handles.mouse,      handles.consumer,
            handles.heart_rate, handles.temperature, handles.humidity,
        };
        if (subscription_index >= ARRAY_SIZE(value_handles))
        {
            central_state = CentralState::reading_dis;
            return;
        }
        struct bt_conn *connection = nucode::ble::internal::referenceConnection(connection_handle);
        if (connection == nullptr || value_handles[subscription_index] == 0U)
        {
            if (connection != nullptr)
            {
                bt_conn_unref(connection);
            }
            fail("subscribe-handle");
            return;
        }
        subscriptions[subscription_index] = {};
        ccc_discovery[subscription_index] = {};
        subscriptions[subscription_index].notify = onNotification;
        subscriptions[subscription_index].subscribe = onSubscribed;
        subscriptions[subscription_index].value_handle = value_handles[subscription_index];
        subscriptions[subscription_index].ccc_handle = BT_GATT_AUTO_DISCOVER_CCC_HANDLE;
        subscriptions[subscription_index].end_handle = BT_ATT_LAST_ATTRIBUTE_HANDLE;
        subscriptions[subscription_index].disc_params = &ccc_discovery[subscription_index];
        subscriptions[subscription_index].value = BT_GATT_CCC_NOTIFY;
        subscriptions[subscription_index].min_security = BT_SECURITY_L2;
        atomic_set_bit(subscriptions[subscription_index].flags,
                       BT_GATT_SUBSCRIBE_FLAG_VOLATILE);
        atomic_set(&subscription_complete, 0);
        atomic_set(&subscription_error, 0);
        const int result = bt_gatt_subscribe(connection, &subscriptions[subscription_index]);
        bt_conn_unref(connection);
        if (result < 0)
        {
            fail("subscribe-start");
        }
    }

    /** @brief 한 DIS manufacturer read의 전체 응답을 검사합니다. */
    std::uint8_t onRead(struct bt_conn *connection, std::uint8_t error,
                        struct bt_gatt_read_params *parameters, const void *data,
                        std::uint16_t length)
    {
        ARG_UNUSED(connection);
        if (error != 0U)
        {
            atomic_set(&read_error, error);
            atomic_set(&read_complete, 1);
            return BT_GATT_ITER_STOP;
        }
        if (data == nullptr)
        {
            ::memset(parameters, 0, sizeof(*parameters));
            atomic_set(&read_complete, 1);
            return BT_GATT_ITER_STOP;
        }
        if (read_length + length > sizeof(read_buffer))
        {
            atomic_set(&read_error, BT_ATT_ERR_INVALID_ATTRIBUTE_LEN);
            atomic_set(&read_complete, 1);
            return BT_GATT_ITER_STOP;
        }
        ::memcpy(&read_buffer[read_length], data, length);
        read_length += length;
        return BT_GATT_ITER_CONTINUE;
    }

    /** @brief DIS manufacturer characteristic 한 번의 실제 GATT read를 시작합니다. */
    void beginDisRead()
    {
        struct bt_conn *connection = nucode::ble::internal::referenceConnection(connection_handle);
        if (connection == nullptr || handles.manufacturer == 0U)
        {
            if (connection != nullptr)
            {
                bt_conn_unref(connection);
            }
            fail("read-handle");
            return;
        }
        read_parameters = {};
        read_parameters.func = onRead;
        read_parameters.handle_count = 1U;
        read_parameters.single.handle = handles.manufacturer;
        read_parameters.single.offset = 0U;
        read_length = 0U;
        ::memset(read_buffer, 0, sizeof(read_buffer));
        atomic_set(&read_complete, 0);
        atomic_set(&read_error, 0);
        const int result = bt_gatt_read(connection, &read_parameters);
        bt_conn_unref(connection);
        if (result < 0)
        {
            fail("read-start");
        }
    }

    /** @brief nonce가 일치하는 connectable peer 하나만 연결합니다. */
    void onScanResult(const nucode::ble::BLEScanResult &result, void *context)
    {
        ARG_UNUSED(context);
        if (!started || failed || connection_handle.valid() || !result.connectable ||
            result.scan_response || !validPayload(result))
        {
            return;
        }
        if (!BLEScan.stop() || !BLEConnection.connect(result.address, connection_handle))
        {
            fail("connect");
        }
    }

    /** @brief central discovery·구독·DIS read·정량 결과 상태 기계를 구동합니다. */
    void driveCentral()
    {
        if (!secured || failed)
        {
            return;
        }
        if (central_state == CentralState::idle)
        {
            beginDiscovery();
        }
        else if (central_state == CentralState::discovering &&
                 atomic_cas(&discovery_complete, 1, 0))
        {
            if (handles.battery == 0U || handles.manufacturer == 0U ||
                handles.keyboard == 0U || handles.mouse == 0U || handles.consumer == 0U ||
                handles.heart_rate == 0U || handles.temperature == 0U ||
                handles.humidity == 0U)
            {
                fail("catalog");
                return;
            }
            central_state = CentralState::subscribing;
            subscription_index = 0U;
            beginSubscription();
        }
        else if (central_state == CentralState::subscribing &&
                 atomic_cas(&subscription_complete, 1, 0))
        {
            if (atomic_get(&subscription_error) != 0)
            {
                fail("subscribe-response");
                return;
            }
            ++subscription_index;
            if (subscription_index < ARRAY_SIZE(subscriptions))
            {
                beginSubscription();
            }
            else
            {
                central_state = CentralState::reading_dis;
                beginDisRead();
            }
        }
        else if (central_state == CentralState::reading_dis &&
                 atomic_cas(&read_complete, 1, 0))
        {
            const bool valid = atomic_get(&read_error) == 0 &&
                               ((read_length == 6U &&
                                 ::memcmp(read_buffer, "NUCODE", 6U) == 0) ||
                                (read_length == 7U &&
                                 ::memcmp(read_buffer, "NUCODE", 6U) == 0 &&
                                 read_buffer[6] == 0U));
            if (!valid)
            {
                ++payload_errors;
            }
            ++dis_reads;
            if (dis_reads < required_operations)
            {
                beginDisRead();
            }
            else
            {
                central_state = CentralState::waiting_notifications;
                Serial.print(protocol);
                Serial.print("|READY|role=central|catalog=7|dis_reads=100");
                printSuffix();
                Serial.println();
            }
        }
        else if (central_state == CentralState::waiting_notifications)
        {
            bool complete = true;
            for (const std::uint16_t count : notification_counts)
            {
                complete = complete && count == required_operations;
            }
            if (complete && !result_reported)
            {
                Serial.print(protocol);
                Serial.print("|RESULT|role=central|catalog=7|operations=100");
                Serial.print("|bas=100|dis=100|keyboard=100|mouse=100|consumer=100");
                Serial.print("|hrs=100|ess_temperature=100|ess_humidity=100|payload_errors=");
                Serial.print(payload_errors);
                printSuffix();
                Serial.println();
                result_reported = true;
                central_state = CentralState::complete;
            }
        }
    }

#else

    std::uint16_t operation_round = 0U;
    std::uint8_t operation_stage = 0U;
    bool run_requested = false;
    bool result_reported = false;

    /** @brief nonce를 포함하는 connectable legacy advertising을 시작합니다. */
    bool startAdvertising()
    {
        return BLEAdvertising.clear() && BLEAdvertising.setConnectable(true) &&
               BLEAdvertising.setFlags(BT_LE_AD_GENERAL | BT_LE_AD_NO_BREDR) &&
               BLEAdvertising.setManufacturerData(company_id, nonce_binary,
                                                    sizeof(nonce_binary)) &&
               BLEAdvertising.addServiceUuid(nucode::ble::BLEUuid(BT_UUID_HIDS_VAL)) &&
               BLEAdvertising.start();
    }

    /** @brief profile API가 전송 자원을 얻을 때까지 현재 operation을 재시도합니다. */
    void drivePeripheral()
    {
        if (!run_requested || !secured || failed || result_reported)
        {
            return;
        }
        bool sent = false;
        const std::uint16_t round = operation_round;
        switch (operation_stage)
        {
        case 0U:
            sent = BLEBattery.setLevel(static_cast<std::uint8_t>((round % 100U) + 1U));
            break;
        case 1U:
            sent = BLEKeyboard.press(static_cast<std::uint8_t>(4U + (round % 20U)));
            break;
        case 2U:
            sent = BLEMouse.move(static_cast<std::int8_t>((round % 11U) - 5),
                                 static_cast<std::int8_t>((round % 9U) - 4), 0,
                                 static_cast<std::uint8_t>(round % 2U));
            break;
        case 3U:
            sent = BLEConsumerControl.press(0x00e9U);
            break;
        case 4U:
            sent = BLEHeartRate.setRate(static_cast<std::uint16_t>(60U + (round % 100U)));
            break;
        case 5U:
            sent = BLEEnvironmentalSensing.setTemperature(
                static_cast<std::int16_t>(2000 + round));
            break;
        case 6U:
            sent = BLEEnvironmentalSensing.setHumidity(
                static_cast<std::uint16_t>(4000U + round));
            break;
        default:
            fail("operation-stage");
            return;
        }
        if (!sent)
        {
            return;
        }
        ++operation_stage;
        if (operation_stage == 7U)
        {
            operation_stage = 0U;
            ++operation_round;
        }
        if (operation_round == required_operations)
        {
            Serial.print(protocol);
            Serial.print("|RESULT|role=peripheral|catalog=7|operations=100");
            Serial.print("|bas=100|keyboard=100|mouse=100|consumer=100|hrs=100");
            Serial.print("|ess_temperature=100|ess_humidity=100|driver_errors=0");
            printSuffix();
            Serial.println();
            result_reported = true;
        }
    }

#endif

    /** @brief GAP 연결 lifecycle을 역할별 보안 상태 기계로 전달합니다. */
    void onBleEvent(const nucode::ble::BLEEventInfo &information, void *context)
    {
        ARG_UNUSED(context);
        if (!started || failed)
        {
            return;
        }
        if (information.event == nucode::ble::BLEEvent::connected)
        {
            connection_handle = information.connection;
#if defined(NUCODE_M30_PROFILE_CENTRAL)
            security_due_ms = k_uptime_get() + security_delay_ms;
#endif
        }
        else if (information.event == nucode::ble::BLEEvent::disconnected)
        {
            fail("disconnected");
        }
        else if (information.event == nucode::ble::BLEEvent::error)
        {
            fail("gap-error");
        }
    }

    /** @brief Just Works 요청을 승인하고 L2 도달을 기록합니다. */
    void onSecurityEvent(const nucode::ble::SecurityEventRecord &event, void *context)
    {
        ARG_UNUSED(context);
        if (failed)
        {
            return;
        }
        if (event.event == nucode::ble::SecurityEvent::pairing_requested)
        {
            if (!BLESecurity.acceptPairing(event.connection, true))
            {
                fail("pairing-accept");
            }
        }
        else if (event.event == nucode::ble::SecurityEvent::security_changed &&
                 event.level >= nucode::ble::SecurityLevel::encrypted)
        {
            secured = true;
        }
        else if (event.event == nucode::ble::SecurityEvent::pairing_failed ||
                 event.event == nucode::ble::SecurityEvent::pairing_cancelled ||
                 event.event == nucode::ble::SecurityEvent::timeout ||
                 event.event == nucode::ble::SecurityEvent::error)
        {
            fail("security-event");
        }
    }

    /** @brief READY·START·RUN UART 명령을 exact 상태에 적용합니다. */
    void executeCommand(const char *line)
    {
        if (::strcmp(line, "M30PROFILE|1|READY?") == 0)
        {
            Serial.print(protocol);
            Serial.print("|BOOT|role=");
            Serial.print(roleName());
            Serial.print("|catalog=7|core=");
            Serial.println(M30_PROFILE_CORE_REVISION);
            return;
        }
        constexpr char start_marker[] = "M30PROFILE|1|START|";
        if (::strncmp(line, start_marker, sizeof(start_marker) - 1U) == 0 && !started)
        {
            if (!parseStart(line))
            {
                fail("start-command");
                return;
            }
            started = true;
            deadline_ms = k_uptime_get() + protocol_timeout_ms;
#if defined(NUCODE_M30_PROFILE_CENTRAL)
            if (!BLEScan.clearFilters() || !BLEScan.start(false))
            {
                fail("scan-start");
                return;
            }
#else
            if (!startAdvertising())
            {
                fail("advertising-start");
                return;
            }
#endif
            Serial.print(protocol);
            Serial.print("|BEGIN|role=");
            Serial.print(roleName());
            printSuffix();
            Serial.println();
            return;
        }
#if !defined(NUCODE_M30_PROFILE_CENTRAL)
        if (::strcmp(line, "M30PROFILE|1|RUN") == 0 && started && secured && !run_requested)
        {
            run_requested = true;
            Serial.print(protocol);
            Serial.print("|RUNNING|role=peripheral|operations=100");
            printSuffix();
            Serial.println();
            return;
        }
#endif
        fail("command-state");
    }

    /** @brief VCOM newline 명령을 고정 buffer로 조립합니다. */
    void pollCommand()
    {
        while (Serial.available() > 0)
        {
            const int incoming = Serial.read();
            if (incoming < 0)
            {
                return;
            }
            const char value = static_cast<char>(incoming);
            if (value == '\r')
            {
                continue;
            }
            if (value == '\n')
            {
                command[command_length] = '\0';
                executeCommand(command);
                command_length = 0U;
                return;
            }
            if (command_length + 1U >= sizeof(command))
            {
                command_length = 0U;
                fail("command-overflow");
                return;
            }
            command[command_length++] = value;
        }
    }

} // namespace

void setup()
{
    Serial.begin(115200);
    nucode::ble::SecurityConfig security = {};
    security.minimum_level = nucode::ble::SecurityLevel::encrypted;
    security.bonding = false;
    security.response_timeout_ms = 30000U;
    security.io_capability = nucode::ble::SecurityIoCapability::no_input_output;
    BLESecurity.onEvent(onSecurityEvent);
    if (!BLESecurity.begin(security))
    {
        fail("security-begin");
        return;
    }
#if !defined(NUCODE_M30_PROFILE_CENTRAL)
    if (!BLEKeyboard.begin() || !BLEMouse.begin() || !BLEConsumerControl.begin())
    {
        fail("hid-begin");
        return;
    }
#endif
    BLEDevice.onEventInfo(onBleEvent);
    if (!BLEDevice.begin(
#if defined(NUCODE_M30_PROFILE_CENTRAL)
            "NU54-M30-PROFILE-C"
#else
            "NU54-M30-PROFILE-P"
#endif
            ))
    {
        fail("device-begin");
        return;
    }
    if (!BLESecurity.eraseAllBonds())
    {
        fail("bond-clear");
        return;
    }
    const nucode::ble::DeviceInformation information = {
        "NUCODE", "NU54DK-M30", "M30-PROFILE", "0.5.0", "NU54DK", "0.5.0"};
    if (!BLEDeviceInformation.configure(information) || !BLEBattery.setLevel(1U) ||
        !BLEHeartRate.setRate(60U) ||
        !BLEEnvironmentalSensing.setTemperature(2000) ||
        !BLEEnvironmentalSensing.setHumidity(4000U))
    {
        fail("profile-init");
        return;
    }
#if defined(NUCODE_M30_PROFILE_CENTRAL)
    BLEScan.onResult(onScanResult);
#endif
    Serial.print(protocol);
    Serial.print("|BOOT|role=");
    Serial.print(roleName());
    Serial.print("|catalog=7|core=");
    Serial.println(M30_PROFILE_CORE_REVISION);
}

void loop()
{
    pollCommand();
    BLEDevice.poll();
    BLESecurity.poll();
    if (failed)
    {
        return;
    }
    const std::int64_t now = k_uptime_get();
    if (deadline_ms != 0 && now >= deadline_ms)
    {
        fail("protocol-timeout");
        return;
    }
#if defined(NUCODE_M30_PROFILE_CENTRAL)
    if (connection_handle.valid() && !secured && security_due_ms != 0 && now >= security_due_ms)
    {
        security_due_ms = 0;
        if (!BLESecurity.requestSecurity(connection_handle))
        {
            fail("security-request");
            return;
        }
    }
    driveCentral();
#else
    drivePeripheral();
#endif
    delay(2);
}
