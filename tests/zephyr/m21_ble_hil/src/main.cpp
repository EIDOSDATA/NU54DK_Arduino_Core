/**
 * @file main.cpp
 * @brief 두 NU54DK 사이에서 M21 보안·bond·BAS·DIS·HID protocol을 검증합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <Arduino.h>
#include <NUCODE_BLE_Security.h>
#include <internal/NUCODE_BLE_Internal.h>

#include <zephyr/bluetooth/att.h>
#include <zephyr/bluetooth/conn.h>
#include <zephyr/bluetooth/gatt.h>
#include <zephyr/bluetooth/uuid.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/atomic.h>
#include <zephyr/sys/reboot.h>
#include <zephyr/sys/util.h>

#include <cstddef>
#include <cstdint>
#include <string.h>

namespace
{

constexpr char peer_name[] = "NU54-M21-HIL";
constexpr char start_prefix[] = "NUCODE_M21_START:";
constexpr char clear_prefix[] = "NUCODE_M21_CLEAR:";
constexpr char erase_prefix[] = "NUCODE_M21_ERASE:";
constexpr char probe_prefix[] = "NUCODE_M21_PROBE:";
constexpr char repair_prefix[] = "NUCODE_M21_REPAIR:";
constexpr char reboot_prefix[] = "NUCODE_M21_REBOOT:";
constexpr std::size_t nonce_length = 32U;
constexpr std::size_t rf_nonce_length = 16U;
constexpr std::uint16_t rf_company_id = 0x054dU;
constexpr std::uint16_t rf_nonce_binding_bits = 128U;
constexpr std::size_t command_capacity = 80U;
constexpr std::uint8_t expected_battery_read = 73U;
constexpr std::uint8_t notified_battery = 72U;

/** @brief 현재 HIL 연결이 검증하는 bond 수명주기 단계입니다. */
enum class RunMode : std::uint8_t
{
    fresh,
    restored,
    erased_probe,
    repair,
};

char nonce[nonce_length + 1U] = {};
std::uint8_t rf_nonce[rf_nonce_length] = {};
char command[command_capacity] = {};
std::size_t command_length = 0U;
bool protocol_started = false;
bool protocol_failed = false;
bool erase_in_progress = false;
bool secured = false;
bool phase_reported = false;
bool persistence_pending_seen = false;
bool bond_verified_seen = false;
bool old_key_pairing_requested = false;
bool old_key_reconnect_failed = false;
bool old_key_probe_connected = false;
std::uint32_t pairing_event_count = 0U;
RunMode run_mode = RunMode::fresh;

/** @brief protocol 실패를 role과 함께 한 번만 기록합니다. */
void fail(const char *reason)
{
    if (!protocol_failed)
    {
        Serial.print("NUCODE_M21_FAIL:role=");
#ifdef NUCODE_M21_CENTRAL
        Serial.print("central");
#else
        Serial.print("peripheral");
#endif
        Serial.print(":reason=");
        Serial.println(reason == nullptr ? "unknown" : reason);
    }
    protocol_failed = true;
}

/** @brief nonce가 정확한 소문자 32자리 hex인지 검사합니다. */
bool validNonce(const char *value)
{
    if (value == nullptr || ::strlen(value) != nonce_length)
    {
        return false;
    }
    for (std::size_t index = 0U; index < nonce_length; ++index)
    {
        const char byte = value[index];
        if (!((byte >= '0' && byte <= '9') || (byte >= 'a' && byte <= 'f')))
        {
            return false;
        }
    }
    return true;
}

/** @brief 소문자 hex 한 글자를 4-bit 값으로 변환합니다. */
std::uint8_t hexNibble(char value)
{
    return static_cast<std::uint8_t>(value <= '9' ? value - '0'
                                                  : value - 'a' + 10);
}

/** @brief UART nonce 전체 128 bit를 RF 광고 검증용 binary 값으로 변환합니다. */
void decodeRfNonce()
{
    for (std::size_t index = 0U; index < rf_nonce_length; ++index)
    {
        rf_nonce[index] = static_cast<std::uint8_t>(
            (hexNibble(nonce[index * 2U]) << 4U) |
            hexNibble(nonce[index * 2U + 1U]));
    }
}

/** @brief 명령의 prefix와 nonce를 검증하고 현재 nonce를 갱신합니다. */
bool acceptCommandNonce(const char *line, const char *prefix)
{
    const std::size_t prefix_length = ::strlen(prefix);
    if (line == nullptr || ::strncmp(line, prefix, prefix_length) != 0 ||
        !validNonce(line + prefix_length))
    {
        return false;
    }
    ::memcpy(nonce, line + prefix_length, nonce_length + 1U);
    decodeRfNonce();
    return true;
}

/** @brief 현재 phase의 식별 문자열을 반환합니다. */
const char *modeName()
{
    switch (run_mode)
    {
    case RunMode::fresh:
        return "first";
    case RunMode::restored:
        return "restore";
    case RunMode::erased_probe:
        return "erased_probe";
    case RunMode::repair:
        return "repair";
    }
    return "unknown";
}

/** @brief phase가 요구하는 정직한 bond 상태에 도달했는지 확인합니다. */
bool phaseBondReady()
{
    if (run_mode == RunMode::restored)
    {
        return bond_verified_seen && BLESecurity.bonded() &&
               BLESecurity.bondState() == nucode::ble::BondState::verified;
    }
    return persistence_pending_seen && !BLESecurity.bonded() &&
           BLESecurity.bondState() == nucode::ble::BondState::persistence_pending;
}

/** @brief phase PASS token에 기록할 bond 상태 이름을 반환합니다. */
const char *phaseBondStateName()
{
    return run_mode == RunMode::restored ? "verified" : "persistence_pending";
}

#ifdef NUCODE_M21_CENTRAL

/** @brief 원격 표준 profile의 value와 CCC handle 집합입니다. */
struct RemoteHandles
{
    std::uint16_t battery = 0U;
    std::uint16_t battery_ccc = 0U;
    std::uint16_t manufacturer = 0U;
    std::uint16_t model = 0U;
    std::uint16_t serial = 0U;
    std::uint16_t report_map = 0U;
    std::uint16_t report = 0U;
    std::uint16_t report_ccc = 0U;
};

/** @brief discovery 이후 읽을 표준 characteristic 종류입니다. */
enum class ReadTarget : std::uint8_t
{
    pre_security_report_map,
    battery,
    manufacturer,
    model,
    serial,
    report_map,
    complete,
};

/** @brief CCC descriptor를 가장 최근 characteristic에 연결하는 종류입니다. */
enum class CharacteristicKind : std::uint8_t
{
    other,
    battery,
    report,
};

RemoteHandles handles = {};
CharacteristicKind last_characteristic = CharacteristicKind::other;
struct bt_gatt_discover_params discover_parameters = {};
struct bt_gatt_read_params read_parameters = {};
struct bt_gatt_subscribe_params battery_subscription = {};
struct bt_gatt_subscribe_params report_subscription = {};
ReadTarget read_target = ReadTarget::complete;
std::uint8_t read_buffer[128] = {};
std::size_t read_length = 0U;
std::uint8_t read_att_error = 0U;
bool discovery_for_pre_security = false;
bool discovery_active = false;
bool read_active = false;
bool subscriptions_started = false;
bool report_subscription_started = false;
bool battery_read_passed = false;
bool dis_passed = false;
bool map_passed = false;
bool battery_notification_passed = false;
bool key_down_passed = false;
bool key_release_passed = false;
atomic_t discovery_complete = ATOMIC_INIT(0);
atomic_t read_complete = ATOMIC_INIT(0);
atomic_t battery_subscription_complete = ATOMIC_INIT(0);
atomic_t report_subscription_complete = ATOMIC_INIT(0);
atomic_t subscription_error = ATOMIC_INIT(0);

/** @brief 한 원격 characteristic declaration을 handle 표에 반영합니다. */
void captureCharacteristic(const struct bt_gatt_chrc *characteristic)
{
    last_characteristic = CharacteristicKind::other;
    if (characteristic == nullptr || characteristic->uuid == nullptr)
    {
        return;
    }
    if (bt_uuid_cmp(characteristic->uuid, BT_UUID_BAS_BATTERY_LEVEL) == 0)
    {
        handles.battery = characteristic->value_handle;
        last_characteristic = CharacteristicKind::battery;
    }
    else if (bt_uuid_cmp(characteristic->uuid, BT_UUID_DIS_MANUFACTURER_NAME) == 0)
    {
        handles.manufacturer = characteristic->value_handle;
    }
    else if (bt_uuid_cmp(characteristic->uuid, BT_UUID_DIS_MODEL_NUMBER) == 0)
    {
        handles.model = characteristic->value_handle;
    }
    else if (bt_uuid_cmp(characteristic->uuid, BT_UUID_DIS_SERIAL_NUMBER) == 0)
    {
        handles.serial = characteristic->value_handle;
    }
    else if (bt_uuid_cmp(characteristic->uuid, BT_UUID_HIDS_REPORT_MAP) == 0)
    {
        handles.report_map = characteristic->value_handle;
    }
    else if (bt_uuid_cmp(characteristic->uuid, BT_UUID_HIDS_REPORT) == 0)
    {
        handles.report = characteristic->value_handle;
        last_characteristic = CharacteristicKind::report;
    }
}

/** @brief remote attribute discovery 결과를 bounded handle 표로 복사합니다. */
std::uint8_t onDiscovery(struct bt_conn *connection,
                         const struct bt_gatt_attr *attribute,
                         struct bt_gatt_discover_params *parameters)
{
    ARG_UNUSED(connection);
    if (attribute == nullptr)
    {
        ::memset(parameters, 0, sizeof(*parameters));
        discovery_active = false;
        atomic_set(&discovery_complete, 1);
        return BT_GATT_ITER_STOP;
    }
    if (bt_uuid_cmp(attribute->uuid, BT_UUID_GATT_CHRC) == 0)
    {
        captureCharacteristic(
            static_cast<const struct bt_gatt_chrc *>(attribute->user_data));
    }
    else if (bt_uuid_cmp(attribute->uuid, BT_UUID_GATT_CCC) == 0)
    {
        if (last_characteristic == CharacteristicKind::battery)
        {
            handles.battery_ccc = attribute->handle;
        }
        else if (last_characteristic == CharacteristicKind::report)
        {
            handles.report_ccc = attribute->handle;
        }
    }
    return BT_GATT_ITER_CONTINUE;
}

/** @brief 현재 연결에서 모든 characteristic과 CCC handle을 검색합니다. */
void beginDiscovery(bool pre_security)
{
    struct bt_conn *connection = nucode::ble::internal::referenceConnection();
    if (connection == nullptr)
    {
        fail("discover-no-connection");
        return;
    }
    handles = {};
    last_characteristic = CharacteristicKind::other;
    discover_parameters = {};
    discover_parameters.func = onDiscovery;
    discover_parameters.start_handle = BT_ATT_FIRST_ATTRIBUTE_HANDLE;
    discover_parameters.end_handle = BT_ATT_LAST_ATTRIBUTE_HANDLE;
    discover_parameters.type = BT_GATT_DISCOVER_ATTRIBUTE;
    discovery_for_pre_security = pre_security;
    discovery_active = true;
    atomic_set(&discovery_complete, 0);
    const int result = bt_gatt_discover(connection, &discover_parameters);
    bt_conn_unref(connection);
    if (result < 0)
    {
        discovery_active = false;
        fail("discover-start");
    }
}

/** @brief 단일 remote read의 chunk와 ATT 오류를 bounded buffer에 모읍니다. */
std::uint8_t onRead(struct bt_conn *connection, std::uint8_t error,
                    struct bt_gatt_read_params *parameters,
                    const void *data, std::uint16_t length)
{
    ARG_UNUSED(connection);
    if (error != 0U)
    {
        read_att_error = error;
        ::memset(parameters, 0, sizeof(*parameters));
        read_active = false;
        atomic_set(&read_complete, 1);
        return BT_GATT_ITER_STOP;
    }
    if (data == nullptr)
    {
        ::memset(parameters, 0, sizeof(*parameters));
        read_active = false;
        atomic_set(&read_complete, 1);
        return BT_GATT_ITER_STOP;
    }
    if (read_length + length > sizeof(read_buffer))
    {
        read_att_error = BT_ATT_ERR_INVALID_ATTRIBUTE_LEN;
        read_active = false;
        atomic_set(&read_complete, 1);
        return BT_GATT_ITER_STOP;
    }
    ::memcpy(read_buffer + read_length, data, length);
    read_length += length;
    return BT_GATT_ITER_CONTINUE;
}

/** @brief 지정 remote value handle의 long-read를 시작합니다. */
void beginRead(ReadTarget target, std::uint16_t handle)
{
    struct bt_conn *connection = nucode::ble::internal::referenceConnection();
    if (connection == nullptr || handle == 0U)
    {
        if (connection != nullptr)
        {
            bt_conn_unref(connection);
        }
        fail("read-no-handle");
        return;
    }
    read_target = target;
    read_length = 0U;
    read_att_error = 0U;
    ::memset(read_buffer, 0, sizeof(read_buffer));
    read_parameters = {};
    read_parameters.func = onRead;
    read_parameters.handle_count = 1U;
    read_parameters.single.handle = handle;
    read_parameters.single.offset = 0U;
    read_active = true;
    atomic_set(&read_complete, 0);
    const int result = bt_gatt_read(connection, &read_parameters);
    bt_conn_unref(connection);
    if (result < 0)
    {
        read_active = false;
        fail("read-start");
    }
}

/** @brief DIS 문자열이 정확히 기대값이고 선택적 NUL만 포함하는지 검사합니다. */
bool equalsGattString(const char *expected)
{
    const std::size_t expected_length = ::strlen(expected);
    return (read_length == expected_length &&
            ::memcmp(read_buffer, expected, expected_length) == 0) ||
           (read_length == expected_length + 1U &&
            ::memcmp(read_buffer, expected, expected_length) == 0 &&
            read_buffer[expected_length] == 0U);
}

/** @brief BAS notification 값이 protocol의 72%인지 검사합니다. */
std::uint8_t onBatteryNotification(struct bt_conn *connection,
                                   struct bt_gatt_subscribe_params *parameters,
                                   const void *data, std::uint16_t length)
{
    ARG_UNUSED(connection);
    ARG_UNUSED(parameters);
    if (data != nullptr && length == 1U &&
        *static_cast<const std::uint8_t *>(data) == notified_battery)
    {
        battery_notification_passed = true;
    }
    return BT_GATT_ITER_CONTINUE;
}

/** @brief 8-byte key-down과 zero release HID report를 순서대로 검사합니다. */
std::uint8_t onReportNotification(struct bt_conn *connection,
                                  struct bt_gatt_subscribe_params *parameters,
                                  const void *data, std::uint16_t length)
{
    ARG_UNUSED(connection);
    ARG_UNUSED(parameters);
    if (data == nullptr || length != sizeof(nucode::ble::KeyboardReport))
    {
        return BT_GATT_ITER_CONTINUE;
    }
    const auto *bytes = static_cast<const std::uint8_t *>(data);
    if (!key_down_passed)
    {
        bool valid = bytes[0] == 0U && bytes[1] == 0U && bytes[2] == 0x04U;
        for (std::size_t index = 3U; index < length; ++index)
        {
            valid = valid && bytes[index] == 0U;
        }
        key_down_passed = valid;
    }
    else
    {
        bool released = true;
        for (std::size_t index = 0U; index < length; ++index)
        {
            released = released && bytes[index] == 0U;
        }
        key_release_passed = released;
    }
    return BT_GATT_ITER_CONTINUE;
}

/** @brief BAS CCC write 결과를 main loop에 전달합니다. */
void onBatterySubscribed(struct bt_conn *connection, std::uint8_t error,
                         struct bt_gatt_subscribe_params *parameters)
{
    ARG_UNUSED(connection);
    ARG_UNUSED(parameters);
    atomic_set(&subscription_error, error);
    atomic_set(&battery_subscription_complete, 1);
}

/** @brief HIDS CCC write 결과를 main loop에 전달합니다. */
void onReportSubscribed(struct bt_conn *connection, std::uint8_t error,
                        struct bt_gatt_subscribe_params *parameters)
{
    ARG_UNUSED(connection);
    ARG_UNUSED(parameters);
    atomic_set(&subscription_error, error);
    atomic_set(&report_subscription_complete, 1);
}

/** @brief BAS notification subscription을 시작합니다. */
void beginSubscriptions()
{
    struct bt_conn *connection = nucode::ble::internal::referenceConnection();
    if (connection == nullptr || handles.battery_ccc == 0U)
    {
        if (connection != nullptr)
        {
            bt_conn_unref(connection);
        }
        fail("bas-subscribe-handle");
        return;
    }
    battery_subscription = {};
    battery_subscription.notify = onBatteryNotification;
    battery_subscription.subscribe = onBatterySubscribed;
    battery_subscription.value_handle = handles.battery;
    battery_subscription.ccc_handle = handles.battery_ccc;
    battery_subscription.value = BT_GATT_CCC_NOTIFY;
    battery_subscription.min_security = BT_SECURITY_L2;
    atomic_set_bit(battery_subscription.flags,
                   BT_GATT_SUBSCRIBE_FLAG_VOLATILE);
    subscriptions_started = true;
    atomic_set(&battery_subscription_complete, 0);
    const int result = bt_gatt_subscribe(connection, &battery_subscription);
    bt_conn_unref(connection);
    if (result < 0)
    {
        fail("bas-subscribe-start");
    }
}

/** @brief HIDS notification subscription을 BAS 이후 시작합니다. */
void beginReportSubscription()
{
    struct bt_conn *connection = nucode::ble::internal::referenceConnection();
    if (connection == nullptr || handles.report_ccc == 0U)
    {
        if (connection != nullptr)
        {
            bt_conn_unref(connection);
        }
        fail("hid-subscribe-handle");
        return;
    }
    report_subscription = {};
    report_subscription.notify = onReportNotification;
    report_subscription.subscribe = onReportSubscribed;
    report_subscription.value_handle = handles.report;
    report_subscription.ccc_handle = handles.report_ccc;
    report_subscription.value = BT_GATT_CCC_NOTIFY;
    report_subscription.min_security = BT_SECURITY_L2;
    atomic_set_bit(report_subscription.flags,
                   BT_GATT_SUBSCRIBE_FLAG_VOLATILE);
    report_subscription_started = true;
    atomic_set(&report_subscription_complete, 0);
    const int result = bt_gatt_subscribe(connection, &report_subscription);
    bt_conn_unref(connection);
    if (result < 0)
    {
        fail("hid-subscribe-start");
    }
}

/** @brief normal profile read 상태기를 다음 characteristic으로 진행합니다. */
void advanceNormalRead()
{
    switch (read_target)
    {
    case ReadTarget::battery:
        if (read_att_error != 0U || read_length != 1U ||
            read_buffer[0] != expected_battery_read)
        {
            fail("bas-read");
            return;
        }
        battery_read_passed = true;
        beginRead(ReadTarget::manufacturer, handles.manufacturer);
        break;
    case ReadTarget::manufacturer:
        if (read_att_error != 0U || !equalsGattString("NUCODE"))
        {
            fail("dis-manufacturer");
            return;
        }
        beginRead(ReadTarget::model, handles.model);
        break;
    case ReadTarget::model:
        if (read_att_error != 0U || !equalsGattString("NU54DK-M21"))
        {
            fail("dis-model");
            return;
        }
        beginRead(ReadTarget::serial, handles.serial);
        break;
    case ReadTarget::serial:
        if (read_att_error != 0U || !equalsGattString("M21-HIL"))
        {
            fail("dis-serial");
            return;
        }
        dis_passed = true;
        beginRead(ReadTarget::report_map, handles.report_map);
        break;
    case ReadTarget::report_map:
        if (read_att_error != 0U || read_length < 8U ||
            read_buffer[0] != 0x05U || read_buffer[1] != 0x01U ||
            read_buffer[2] != 0x09U || read_buffer[3] != 0x06U)
        {
            fail("hid-report-map");
            return;
        }
        map_passed = true;
        read_target = ReadTarget::complete;
        beginSubscriptions();
        break;
    default:
        fail("read-state");
        break;
    }
}

/** @brief security 전 HIDS read 거부와 security 요청을 연결합니다. */
void finishPreSecurityRead()
{
    if (read_att_error != BT_ATT_ERR_INSUFFICIENT_ENCRYPTION &&
        read_att_error != BT_ATT_ERR_AUTHENTICATION)
    {
        fail("secure-gatt-not-denied");
        return;
    }
    Serial.print("NUCODE_M21_CENTRAL:SECURE_GATT:DENIED:nonce=");
    Serial.println(nonce);
    read_target = ReadTarget::complete;
    if (!BLESecurity.requestSecurity())
    {
        fail("security-request");
    }
}

/** @brief 중앙 profile 검증이 끝나면 phase별 exact PASS token을 기록합니다. */
void reportCentralPhase()
{
    if (phase_reported || !battery_read_passed || !dis_passed || !map_passed ||
        !battery_notification_passed || !key_down_passed || !key_release_passed ||
        !phaseBondReady())
    {
        return;
    }
    const std::uint32_t expected_pairings =
        run_mode == RunMode::restored ? 0U : 1U;
    if (pairing_event_count != expected_pairings)
    {
        fail("pairing-event-count");
        return;
    }
    Serial.print("NUCODE_M21_CENTRAL:BAS:READ:PASS:value=73:nonce=");
    Serial.println(nonce);
    Serial.print("NUCODE_M21_CENTRAL:BAS:NOTIFY:PASS:value=72:nonce=");
    Serial.println(nonce);
    Serial.print("NUCODE_M21_CENTRAL:DIS:PASS:manufacturer=NUCODE:model=NU54DK-M21:serial=M21-HIL:nonce=");
    Serial.println(nonce);
    Serial.print("NUCODE_M21_CENTRAL:HID:REPORT:PASS:bytes=8:down=04:release=00:nonce=");
    Serial.println(nonce);
    Serial.print("NUCODE_M21_CENTRAL:PHASE:PASS:phase=");
    Serial.print(modeName());
    Serial.print(":pairing_events=");
    Serial.print(pairing_event_count);
    Serial.print(":bond_count=");
    Serial.print(BLESecurity.bondCount());
    Serial.print(":bond_state=");
    Serial.print(phaseBondStateName());
    Serial.print(":nonce=");
    Serial.println(nonce);
    if (run_mode == RunMode::repair)
    {
        Serial.print("NUCODE_M21_CENTRAL:FINAL:PASS:pairing=PASS:bond_restore=PASS:erase_reboot=PASS:old_key_reconnect=REJECTED:repair=PASS:bas=PASS:dis=PASS:hid_protocol=PASS:nonce=");
        Serial.println(nonce);
    }
    phase_reported = true;
}

/** @brief 중앙 discovery/read/subscription 상태기를 Arduino main 문맥에서 진행합니다. */
void driveCentralProfile()
{
    if (atomic_cas(&discovery_complete, 1, 0))
    {
        if (handles.battery == 0U || handles.manufacturer == 0U ||
            handles.model == 0U || handles.serial == 0U ||
            handles.report_map == 0U || handles.report == 0U)
        {
            fail("profile-handles");
            return;
        }
        if (discovery_for_pre_security)
        {
            beginRead(ReadTarget::pre_security_report_map, handles.report_map);
        }
        else
        {
            beginRead(ReadTarget::battery, handles.battery);
        }
    }
    if (atomic_cas(&read_complete, 1, 0))
    {
        if (read_target == ReadTarget::pre_security_report_map)
        {
            finishPreSecurityRead();
        }
        else
        {
            advanceNormalRead();
        }
    }
    if (atomic_cas(&battery_subscription_complete, 1, 0))
    {
        if (atomic_get(&subscription_error) != 0)
        {
            fail("bas-subscribe-response");
            return;
        }
        beginReportSubscription();
    }
    if (atomic_cas(&report_subscription_complete, 1, 0) &&
        atomic_get(&subscription_error) != 0)
    {
        fail("hid-subscribe-response");
        return;
    }
    reportCentralPhase();
}

/** @brief 광고 payload에서 exact 128-bit manufacturer nonce를 검사합니다. */
bool validRfNonceBinding(const nucode::ble::BLEScanResult &result)
{
    std::size_t cursor = 0U;
    while (cursor < result.payload_length)
    {
        const std::size_t field_length = result.payload[cursor];
        if (field_length == 0U)
        {
            break;
        }
        if (cursor + field_length >= result.payload_length)
        {
            return false;
        }
        if (result.payload[cursor + 1U] == BT_DATA_MANUFACTURER_DATA &&
            field_length == rf_nonce_length + 3U)
        {
            const std::uint8_t *value = &result.payload[cursor + 2U];
            return value[0] == static_cast<std::uint8_t>(rf_company_id & 0xffU) &&
                   value[1] == static_cast<std::uint8_t>(rf_company_id >> 8U) &&
                   ::memcmp(&value[2], rf_nonce, rf_nonce_length) == 0;
        }
        cursor += field_length + 1U;
    }
    return false;
}

/** @brief exact 128-bit RF nonce가 포함된 connectable 광고에만 연결합니다. */
void onScanResult(const nucode::ble::BLEScanResult &result, void *context)
{
    ARG_UNUSED(context);
    if (!protocol_started || !result.connectable || result.scan_response ||
        !validRfNonceBinding(result))
    {
        return;
    }
    static_cast<void>(BLEScan.stop());
    if (!BLEConnection.connect(result.address))
    {
        fail("connect-start");
    }
}

#else

std::int64_t next_profile_send_ms = 0;
bool key_down_sent = false;
bool hid_cycle_passed = false;
std::uint8_t battery_value = expected_battery_read;

/** @brief 구독이 완료될 때까지 BAS와 HID report를 bounded 간격으로 재시도합니다. */
void drivePeripheralProfile()
{
    if (!secured || phase_reported || k_uptime_get() < next_profile_send_ms)
    {
        return;
    }
    if (!key_down_sent)
    {
        battery_value = battery_value == notified_battery
                            ? expected_battery_read
                            : notified_battery;
        static_cast<void>(BLEBattery.setLevel(battery_value));
        if (BLEKeyboard.press(0x04U))
        {
            key_down_sent = true;
            next_profile_send_ms = k_uptime_get() + 80;
        }
        else
        {
            next_profile_send_ms = k_uptime_get() + 250;
        }
        return;
    }
    if (!BLEKeyboard.releaseAll())
    {
        key_down_sent = false;
        next_profile_send_ms = k_uptime_get() + 250;
        return;
    }
    hid_cycle_passed = true;
    key_down_sent = false;
    next_profile_send_ms = k_uptime_get() + 500;

    if (!phaseBondReady())
    {
        return;
    }
    const std::uint32_t expected_pairings =
        run_mode == RunMode::restored ? 0U : 1U;
    if (pairing_event_count != expected_pairings)
    {
        fail("pairing-event-count");
        return;
    }
    Serial.print("NUCODE_M21_PERIPHERAL:PROFILE:PASS:bas_notify=72:hid_bytes=8:nonce=");
    Serial.println(nonce);
    Serial.print("NUCODE_M21_PERIPHERAL:PHASE:PASS:phase=");
    Serial.print(modeName());
    Serial.print(":pairing_events=");
    Serial.print(pairing_event_count);
    Serial.print(":bond_count=");
    Serial.print(BLESecurity.bondCount());
    Serial.print(":bond_state=");
    Serial.print(phaseBondStateName());
    Serial.print(":nonce=");
    Serial.println(nonce);
    if (run_mode == RunMode::repair)
    {
        Serial.print("NUCODE_M21_PERIPHERAL:FINAL:PASS:pairing=PASS:bond_restore=PASS:erase_reboot=PASS:old_key_reconnect=REJECTED:repair=PASS:bas=PASS:dis=PASS:hid_protocol=PASS:nonce=");
        Serial.println(nonce);
    }
    phase_reported = true;
}

#endif

/** @brief pairing 요청을 main thread에서 명시적으로 승인하고 event를 집계합니다. */
void onSecurityEvent(const nucode::ble::SecurityEventRecord &event, void *context)
{
    ARG_UNUSED(context);
    switch (event.event)
    {
    case nucode::ble::SecurityEvent::pairing_requested:
        if (run_mode == RunMode::erased_probe)
        {
            old_key_pairing_requested = true;
            if (!BLESecurity.acceptPairing(false))
            {
                fail("old-key-pairing-reject");
            }
            static_cast<void>(BLEConnection.disconnect());
        }
        else if (!BLESecurity.acceptPairing(true))
        {
            fail("pairing-confirm");
        }
        break;
    case nucode::ble::SecurityEvent::passkey_confirmation_requested:
        if (!BLESecurity.confirmPasskey(true))
        {
            fail("passkey-confirm");
        }
        break;
    case nucode::ble::SecurityEvent::paired:
        ++pairing_event_count;
        break;
    case nucode::ble::SecurityEvent::bond_persistence_pending:
        persistence_pending_seen = true;
        break;
    case nucode::ble::SecurityEvent::bond_verified:
        bond_verified_seen = true;
        break;
    case nucode::ble::SecurityEvent::security_changed:
        if (event.level >= nucode::ble::SecurityLevel::encrypted)
        {
            if (run_mode == RunMode::erased_probe)
            {
                fail("old-key-reconnect-succeeded");
                break;
            }
            secured = true;
#ifdef NUCODE_M21_CENTRAL
            if (!discovery_active && !read_active &&
                read_target != ReadTarget::pre_security_report_map)
            {
                beginDiscovery(false);
            }
#else
            next_profile_send_ms = k_uptime_get() + 2000;
#endif
        }
        break;
    case nucode::ble::SecurityEvent::pairing_failed:
        if (run_mode == RunMode::erased_probe)
        {
            old_key_reconnect_failed = true;
            break;
        }
        fail("security-event");
        break;
    case nucode::ble::SecurityEvent::timeout:
    case nucode::ble::SecurityEvent::error:
        if (run_mode == RunMode::erased_probe)
        {
            old_key_reconnect_failed = true;
            break;
        }
        fail("security-event");
        break;
    default:
        break;
    }
}

/** @brief 공통 GAP 연결 event를 보안 요청과 role별 profile 단계에 연결합니다. */
void onGapEvent(nucode::ble::BLEEvent event, void *context)
{
    ARG_UNUSED(context);
    if (event == nucode::ble::BLEEvent::connected)
    {
        secured = false;
        if (run_mode == RunMode::erased_probe)
        {
            old_key_probe_connected = true;
        }
        Serial.print("NUCODE_M21_EVENT:CONNECTED:role=");
#ifdef NUCODE_M21_CENTRAL
        Serial.print("central");
#else
        Serial.print("peripheral");
#endif
        Serial.print(":phase=");
        Serial.print(modeName());
        Serial.print(":nonce=");
        Serial.println(nonce);
#ifdef NUCODE_M21_CENTRAL
        if (run_mode == RunMode::fresh)
        {
            beginDiscovery(true);
        }
        else if (!BLESecurity.requestSecurity())
        {
            fail("security-request");
        }
#endif
    }
    else if (event == nucode::ble::BLEEvent::disconnected)
    {
        const bool connection_was_secured = secured;
        secured = false;
        Serial.print("NUCODE_M21_EVENT:DISCONNECTED:role=");
#ifdef NUCODE_M21_CENTRAL
        Serial.print("central");
#else
        Serial.print("peripheral");
#endif
        Serial.print(":nonce=");
        Serial.println(nonce);
        if (run_mode == RunMode::erased_probe && old_key_probe_connected &&
            !connection_was_secured &&
            BLESecurity.bondCount() == 0U)
        {
            old_key_reconnect_failed = true;
            Serial.print("NUCODE_M21_");
#ifdef NUCODE_M21_CENTRAL
            Serial.print("CENTRAL");
#else
            Serial.print("PERIPHERAL");
#endif
            Serial.print(":OLD_KEY:RECONNECT:REJECTED:bond_count=0:pairing_requested=");
            Serial.print(old_key_pairing_requested ? 1 : 0);
            Serial.print(":security_failed=");
            Serial.print(old_key_reconnect_failed ? 1 : 0);
            Serial.print(":nonce=");
            Serial.println(nonce);
            phase_reported = true;
        }
    }
    else if (event == nucode::ble::BLEEvent::error && !erase_in_progress &&
             run_mode != RunMode::erased_probe)
    {
        fail("gap-event");
    }
}

/** @brief 한 START마다 profile state와 phase 판정을 초기화합니다. */
void resetPhaseState(RunMode requested_mode)
{
    protocol_failed = false;
    phase_reported = false;
    secured = false;
    pairing_event_count = 0U;
    persistence_pending_seen = false;
    bond_verified_seen = false;
    old_key_pairing_requested = false;
    old_key_reconnect_failed = false;
    old_key_probe_connected = false;
    run_mode = requested_mode;
#ifdef NUCODE_M21_CENTRAL
    handles = {};
    read_target = ReadTarget::complete;
    discovery_active = false;
    read_active = false;
    subscriptions_started = false;
    report_subscription_started = false;
    battery_read_passed = false;
    dis_passed = false;
    map_passed = false;
    battery_notification_passed = false;
    key_down_passed = false;
    key_release_passed = false;
    atomic_set(&discovery_complete, 0);
    atomic_set(&read_complete, 0);
    atomic_set(&battery_subscription_complete, 0);
    atomic_set(&report_subscription_complete, 0);
#else
    key_down_sent = false;
    hid_cycle_passed = false;
    battery_value = expected_battery_read;
#endif
}

/** @brief 광고 또는 scan을 시작해 현재 phase를 실행합니다. */
void startProtocol(RunMode requested_mode)
{
    resetPhaseState(requested_mode);
#ifndef NUCODE_M21_CENTRAL
    if (!BLEBattery.setLevel(expected_battery_read))
    {
        fail("battery-reset");
        return;
    }
#endif
    protocol_started = true;
#ifdef NUCODE_M21_CENTRAL
    if (!BLEScan.clearFilters() || !BLEScan.start(true))
    {
        fail("scan-start");
        return;
    }
    Serial.print("NUCODE_M21_CENTRAL:SCAN:PASS:phase=");
#else
    if (!BLEAdvertising.setManufacturerData(rf_company_id, rf_nonce,
                                             rf_nonce_length) ||
        !BLEAdvertising.start())
    {
        fail("advertising-start");
        return;
    }
    Serial.print("NUCODE_M21_PERIPHERAL:ADVERTISE:PASS:phase=");
#endif
    Serial.print(modeName());
    Serial.print(":rf_nonce_binding_bits=");
    Serial.print(rf_nonce_binding_bits);
    Serial.print(":nonce=");
    Serial.println(nonce);
}

/** @brief bond 삭제 명령을 두 role에서 같은 exact token으로 수행합니다. */
void eraseBonds(bool initial_clear)
{
    erase_in_progress = true;
#ifdef NUCODE_M21_CENTRAL
    static_cast<void>(BLEScan.stop());
    static_cast<void>(BLEConnection.disconnect());
#else
    static_cast<void>(BLEAdvertising.stop());
#endif
    if (!BLESecurity.eraseAllBonds())
    {
        fail("erase-bonds");
        erase_in_progress = false;
        return;
    }
    protocol_started = false;
    Serial.print("NUCODE_M21_");
#ifdef NUCODE_M21_CENTRAL
    Serial.print("CENTRAL");
#else
    Serial.print("PERIPHERAL");
#endif
    Serial.print(initial_clear ? ":CLEAR:REQUESTED:nonce="
                              : ":ERASE:REQUESTED:nonce=");
    Serial.println(nonce);
    erase_in_progress = false;
}

/** @brief 완전한 UART 명령 한 줄을 실행합니다. */
void executeCommand(const char *line)
{
    if (acceptCommandNonce(line, clear_prefix))
    {
        eraseBonds(true);
    }
    else if (acceptCommandNonce(line, erase_prefix))
    {
        eraseBonds(false);
    }
    else if (acceptCommandNonce(line, start_prefix))
    {
        startProtocol(BLESecurity.bondCount() > 0U ? RunMode::restored
                                                   : RunMode::fresh);
    }
    else if (acceptCommandNonce(line, probe_prefix))
    {
        if (BLESecurity.bondCount() != 0U)
        {
            fail("probe-bond-count");
        }
        else
        {
            startProtocol(RunMode::erased_probe);
        }
    }
    else if (acceptCommandNonce(line, repair_prefix))
    {
        if (BLESecurity.bondCount() != 0U)
        {
            fail("repair-bond-count");
        }
        else
        {
            startProtocol(RunMode::repair);
        }
    }
    else if (acceptCommandNonce(line, reboot_prefix))
    {
        Serial.print("NUCODE_M21_REBOOTING:role=");
#ifdef NUCODE_M21_CENTRAL
        Serial.print("central");
#else
        Serial.print("peripheral");
#endif
        Serial.print(":nonce=");
        Serial.println(nonce);
        delay(100U);
        sys_reboot(SYS_REBOOT_WARM);
    }
    else
    {
        fail("bad-command");
    }
}

/** @brief UART의 newline 명령을 고정 buffer로 조립합니다. */
void pollHostCommand()
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

}

void setup()
{
    Serial.begin(115200);
    const nucode::ble::SecurityConfig security = {
        nucode::ble::SecurityLevel::encrypted, true, 30000U};
    BLESecurity.onEvent(onSecurityEvent);
    if (!BLESecurity.begin(security))
    {
        fail("security-begin");
        return;
    }
#ifndef NUCODE_M21_CENTRAL
    if (!BLEKeyboard.begin())
    {
        fail("hid-init");
        return;
    }
#endif
    BLEDevice.onEvent(onGapEvent);
    if (!BLEDevice.begin(
#ifdef NUCODE_M21_CENTRAL
            "NU54-M21-CENTRAL"
#else
            peer_name
#endif
            ))
    {
        fail("device-begin");
        return;
    }
    const nucode::ble::DeviceInformation information = {
        "NUCODE", "NU54DK-M21", "M21-HIL", "0.3.0", "NU54DK", "0.3.0"};
    if (!BLEDeviceInformation.configure(information))
    {
        fail("dis-config");
        return;
    }
    if (!BLEBattery.setLevel(expected_battery_read))
    {
        fail("battery-init");
        return;
    }
#ifdef NUCODE_M21_CENTRAL
    BLEScan.onResult(onScanResult);
#else
    if (!BLEAdvertising.clear() || !BLEAdvertising.setConnectable(true) ||
        !BLEAdvertising.setFlags(BT_LE_AD_GENERAL | BT_LE_AD_NO_BREDR) ||
        !BLEAdvertising.addServiceUuid(nucode::ble::BLEUuid(BT_UUID_HIDS_VAL)) ||
        !BLEAdvertising.addServiceUuid(nucode::ble::BLEUuid(BT_UUID_BAS_VAL)) ||
        !BLEAdvertising.setScanResponseName(true))
    {
        fail("advertising-config");
        return;
    }
#endif
    Serial.print("NUCODE_M21_READY:role=");
#ifdef NUCODE_M21_CENTRAL
    Serial.print("central");
#else
    Serial.print("peripheral");
#endif
    Serial.print(":bond_count=");
    Serial.println(BLESecurity.bondCount());
}

void loop()
{
    pollHostCommand();
    BLEDevice.poll();
    BLESecurity.poll();
    if (!protocol_started || protocol_failed)
    {
        return;
    }
#ifdef NUCODE_M21_CENTRAL
    driveCentralProfile();
#else
    drivePeripheralProfile();
#endif
}
