/**
 * @file NUCODE_BLE_GAP.cpp
 * @brief NU54DK의 고정 자원 BLE Core/GAP Arduino API를 구현합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE_GAP.h>

#if !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE)
#include <internal/NUCODE_BLE_Internal.h>

#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/conn.h>
#include <zephyr/bluetooth/gap.h>
#include <zephyr/bluetooth/gatt.h>
#include <zephyr/bluetooth/hci.h>
#include <zephyr/kernel.h>
#include <zephyr/net_buf.h>
#include <zephyr/sys/atomic.h>
#include <zephyr/sys/util.h>

#include <errno.h>
#include <stdio.h>
#include <string.h>

namespace
{

    using nucode::ble::BLEAddress;
    using nucode::ble::BLEError;
    using nucode::ble::BLEEvent;
    using nucode::ble::BLEEventCallback;
    using nucode::ble::BLEPhy;
    using nucode::ble::BLEScanCallback;
    using nucode::ble::BLEScanResult;
    using nucode::ble::BLEUuid;

    constexpr std::size_t maximum_service_uuids = 4U;
    constexpr std::size_t maximum_ad_field_data = 29U;
    constexpr std::uint16_t minimum_advertising_interval = 0x0020U;
    constexpr std::uint16_t maximum_advertising_interval = 0x4000U;
    constexpr std::uint16_t default_advertising_interval_min = 0x00a0U;
    constexpr std::uint16_t default_advertising_interval_max = 0x00f0U;

    /** @brief callback에서 main thread로 전달하는 작은 GAP event record입니다. */
    struct GapEventRecord
    {
        BLEEvent event;
        std::uint32_t generation;
    };

    /** @brief scan payload와 callback 시작 session을 함께 보존합니다. */
    struct ScanResultRecord
    {
        BLEScanResult result;
        std::uint32_t generation;
    };

    /** @brief legacy advertising의 caller 입력을 고정 buffer에 보존합니다. */
    struct AdvertisingConfiguration
    {
        bool connectable = true;
        bool scan_response_name = true;
        std::uint8_t flags = BT_LE_AD_GENERAL | BT_LE_AD_NO_BREDR;
        std::uint16_t interval_min = default_advertising_interval_min;
        std::uint16_t interval_max = default_advertising_interval_max;
        BLEUuid service_uuids[maximum_service_uuids] = {};
        std::size_t service_uuid_count = 0U;
        bool has_manufacturer_data = false;
        std::uint16_t company_id = 0U;
        std::uint8_t manufacturer_data[maximum_ad_field_data] = {};
        std::size_t manufacturer_length = 0U;
        bool has_service_data = false;
        BLEUuid service_data_uuid;
        std::uint8_t service_data[maximum_ad_field_data] = {};
        std::size_t service_data_length = 0U;
    };

    /** @brief software scan filter의 bounded 복사본입니다. */
    struct ScanConfiguration
    {
        bool has_name = false;
        char name[CONFIG_BT_DEVICE_NAME_MAX + 1U] = {};
        bool has_uuid = false;
        BLEUuid uuid;
        bool has_address = false;
        BLEAddress address;
    };

    K_MSGQ_DEFINE(gap_event_queue, sizeof(GapEventRecord),
                  CONFIG_NUCODE_BLE_CORE_EVENT_QUEUE_SIZE,
                  alignof(GapEventRecord));
    K_MSGQ_DEFINE(scan_result_queue, sizeof(ScanResultRecord),
                  CONFIG_NUCODE_BLE_SCAN_RESULT_QUEUE_SIZE,
                  alignof(BLEScanResult));
    K_MUTEX_DEFINE(gap_lifecycle_mutex);

    atomic_t device_initialized = ATOMIC_INIT(0);
    atomic_t advertising_active = ATOMIC_INIT(0);
    atomic_t scanning_active = ATOMIC_INIT(0);
    atomic_t connection_connecting = ATOMIC_INIT(0);
    atomic_t connection_active = ATOMIC_INIT(0);
    atomic_t mtu_exchange_active = ATOMIC_INIT(0);
    atomic_t last_error_value = ATOMIC_INIT(static_cast<atomic_val_t>(BLEError::none));
    atomic_t last_driver_error_value = ATOMIC_INIT(0);
    atomic_t dropped_event_value = ATOMIC_INIT(0);
    atomic_t dropped_scan_value = ATOMIC_INIT(0);
    atomic_t gatt_callback_registered = ATOMIC_INIT(0);
    atomic_t device_session_generation = ATOMIC_INIT(1);

    struct k_spinlock connection_lock;
    struct k_spinlock configuration_lock;
    struct bt_conn *active_connection = nullptr;
    struct bt_conn *pending_connection = nullptr;
    std::uint32_t active_connection_generation = 0U;
    std::uint32_t pending_connection_generation = 0U;

    char local_name[CONFIG_BT_DEVICE_NAME_MAX + 1U] = {};
    AdvertisingConfiguration advertising_configuration;
    ScanConfiguration scan_configuration;
    BLEAddress last_peer_address;

    BLEEventCallback event_callback = nullptr;
    void *event_context = nullptr;
    BLEScanCallback scan_callback = nullptr;
    void *scan_context = nullptr;

    struct bt_gatt_exchange_params mtu_exchange_parameters = {};

    /** @brief ASCII hex 한 글자를 0..15로 변환합니다. */
    int hexValue(char value) noexcept
    {
        if (value >= '0' && value <= '9')
        {
            return value - '0';
        }
        if (value >= 'a' && value <= 'f')
        {
            return value - 'a' + 10;
        }
        if (value >= 'A' && value <= 'F')
        {
            return value - 'A' + 10;
        }
        return -1;
    }

    /** @brief local name의 UTF-8이 well-formed인지 동적 할당 없이 검증합니다. */
    bool validUtf8(const char *text, std::size_t length) noexcept
    {
        std::size_t index = 0U;
        while (index < length)
        {
            const auto first = static_cast<std::uint8_t>(text[index]);
            if (first <= 0x7fU)
            {
                ++index;
                continue;
            }

            std::size_t continuation_count = 0U;
            std::uint32_t code_point = 0U;
            std::uint32_t minimum = 0U;
            if ((first & 0xe0U) == 0xc0U)
            {
                continuation_count = 1U;
                code_point = first & 0x1fU;
                minimum = 0x80U;
            }
            else if ((first & 0xf0U) == 0xe0U)
            {
                continuation_count = 2U;
                code_point = first & 0x0fU;
                minimum = 0x800U;
            }
            else if ((first & 0xf8U) == 0xf0U)
            {
                continuation_count = 3U;
                code_point = first & 0x07U;
                minimum = 0x10000U;
            }
            else
            {
                return false;
            }
            if (index + continuation_count >= length)
            {
                return false;
            }
            for (std::size_t offset = 1U; offset <= continuation_count; ++offset)
            {
                const auto next = static_cast<std::uint8_t>(text[index + offset]);
                if ((next & 0xc0U) != 0x80U)
                {
                    return false;
                }
                code_point = (code_point << 6U) | (next & 0x3fU);
            }
            if (code_point < minimum || code_point > 0x10ffffU ||
                (code_point >= 0xd800U && code_point <= 0xdfffU))
            {
                return false;
            }
            index += continuation_count + 1U;
        }
        return true;
    }

    /** @brief thread 전용 공개 API가 ISR에서 호출되지 않았는지 검사합니다. */
    bool requireThreadContext() noexcept
    {
        return nucode::ble::internal::requireThreadContext();
    }

    /** @brief event queue에 사용자 callback 대신 작은 record만 저장합니다. */
    void queueEvent(BLEEvent event, std::uint32_t generation = 0U) noexcept
    {
        const std::uint32_t current_generation = static_cast<std::uint32_t>(
            atomic_get(&device_session_generation));
        const GapEventRecord record = {
            .event = event,
            .generation = generation == 0U ? current_generation : generation,
        };
        if (k_msgq_put(&gap_event_queue, &record, K_NO_WAIT) != 0)
        {
            atomic_inc(&dropped_event_value);
            atomic_set(&last_driver_error_value, -ENOBUFS);
            atomic_set(&last_error_value,
                       static_cast<atomic_val_t>(BLEError::event_overflow));
        }
    }

    /** @brief 공개 주소를 Zephyr LE 주소로 변환합니다. */
    bool toZephyrAddress(const BLEAddress &source, bt_addr_le_t &destination) noexcept
    {
        if (!source.valid())
        {
            return false;
        }
        destination.type = source.type() == BLEAddress::Type::public_address
                               ? BT_ADDR_LE_PUBLIC
                               : BT_ADDR_LE_RANDOM;
        ::memcpy(destination.a.val, source.data(), sizeof(destination.a.val));
        return true;
    }

    /** @brief Zephyr LE 주소를 callback 밖 수명의 공개 주소로 복사합니다. */
    BLEAddress fromZephyrAddress(const bt_addr_le_t &source) noexcept
    {
        const bool public_type = source.type == BT_ADDR_LE_PUBLIC ||
                                 source.type == BT_ADDR_LE_PUBLIC_ID;
        return BLEAddress(source.a.val, public_type
                                            ? BLEAddress::Type::public_address
                                            : BLEAddress::Type::random_address);
    }

    /** @brief active connection에 race-safe 임시 reference를 얻습니다. */
    struct bt_conn *referenceActiveConnection() noexcept
    {
        k_spinlock_key_t key = k_spin_lock(&connection_lock);
        struct bt_conn *connection = active_connection;
        if (connection != nullptr)
        {
            bt_conn_ref(connection);
        }
        k_spin_unlock(&connection_lock, key);
        return connection;
    }

    /** @brief callback connection이 현재 session의 active link인지 검사합니다. */
    bool activeConnectionGeneration(struct bt_conn *connection,
                                    std::uint32_t &generation) noexcept
    {
        k_spinlock_key_t key = k_spin_lock(&connection_lock);
        const bool matches = active_connection == connection &&
                             active_connection_generation != 0U;
        generation = matches ? active_connection_generation : 0U;
        k_spin_unlock(&connection_lock, key);
        return matches && generation == static_cast<std::uint32_t>(
                                            atomic_get(&device_session_generation));
    }

    /** @brief raw AD payload에서 완전·축약 local name을 복사합니다. */
    void copyAdvertisedName(BLEScanResult &result) noexcept
    {
        std::size_t index = 0U;
        while (index < result.payload_length)
        {
            const std::size_t field_length = result.payload[index];
            if (field_length == 0U)
            {
                break;
            }
            if (index + field_length + 1U > result.payload_length)
            {
                result.truncated = true;
                return;
            }
            const std::uint8_t type = result.payload[index + 1U];
            if (type == BT_DATA_NAME_COMPLETE || type == BT_DATA_NAME_SHORTENED)
            {
                const std::size_t available = field_length - 1U;
                const std::size_t copy_length =
                    available < BLEScanResult::maximum_name_length
                        ? available
                        : BLEScanResult::maximum_name_length;
                ::memcpy(result.name, &result.payload[index + 2U], copy_length);
                result.name[copy_length] = '\0';
                if (copy_length != available)
                {
                    result.truncated = true;
                }
                return;
            }
            index += field_length + 1U;
        }
    }

    /** @brief AD service UUID list에서 exact UUID를 찾습니다. */
    bool payloadContainsUuid(const BLEScanResult &result, const BLEUuid &uuid) noexcept
    {
        std::uint8_t incomplete_type = 0U;
        std::uint8_t complete_type = 0U;
        switch (uuid.type())
        {
        case BLEUuid::Type::uuid16:
            incomplete_type = BT_DATA_UUID16_SOME;
            complete_type = BT_DATA_UUID16_ALL;
            break;
        case BLEUuid::Type::uuid32:
            incomplete_type = BT_DATA_UUID32_SOME;
            complete_type = BT_DATA_UUID32_ALL;
            break;
        case BLEUuid::Type::uuid128:
            incomplete_type = BT_DATA_UUID128_SOME;
            complete_type = BT_DATA_UUID128_ALL;
            break;
        default:
            return false;
        }

        std::size_t index = 0U;
        while (index < result.payload_length)
        {
            const std::size_t field_length = result.payload[index];
            if (field_length == 0U || index + field_length + 1U > result.payload_length)
            {
                break;
            }
            const std::uint8_t type = result.payload[index + 1U];
            if (type == incomplete_type || type == complete_type)
            {
                const std::size_t data_length = field_length - 1U;
                for (std::size_t offset = 0U; offset + uuid.size() <= data_length;
                     offset += uuid.size())
                {
                    if (::memcmp(&result.payload[index + 2U + offset], uuid.data(),
                                 uuid.size()) == 0)
                    {
                        return true;
                    }
                }
            }
            index += field_length + 1U;
        }
        return false;
    }

    /** @brief 현재 software filter가 모두 scan 결과와 일치하는지 검사합니다. */
    bool scanResultMatches(const BLEScanResult &result) noexcept
    {
        k_spinlock_key_t key = k_spin_lock(&configuration_lock);
        const ScanConfiguration filters = scan_configuration;
        k_spin_unlock(&configuration_lock, key);

        if (filters.has_address && result.address != filters.address)
        {
            return false;
        }
        if (filters.has_name && ::strcmp(result.name, filters.name) != 0)
        {
            return false;
        }
        if (filters.has_uuid && !payloadContainsUuid(result, filters.uuid))
        {
            return false;
        }
        return true;
    }

    /** @brief stack scan callback에서 bounded 결과만 queue로 복사합니다. */
    void scanReceived(const bt_addr_le_t *address, std::int8_t rssi,
                      std::uint8_t advertising_type,
                      struct net_buf_simple *data) noexcept
    {
        if (atomic_get(&scanning_active) == 0 || address == nullptr || data == nullptr)
        {
            return;
        }
        const std::uint32_t generation = static_cast<std::uint32_t>(
            atomic_get(&device_session_generation));

        BLEScanResult result = {};
        result.address = fromZephyrAddress(*address);
        result.rssi = rssi;
        result.connectable = advertising_type == BT_GAP_ADV_TYPE_ADV_IND ||
                             advertising_type == BT_GAP_ADV_TYPE_ADV_DIRECT_IND;
        result.scan_response = advertising_type == BT_GAP_ADV_TYPE_SCAN_RSP;
        const std::size_t copy_length =
            data->len < BLEScanResult::maximum_payload_length
                ? data->len
                : BLEScanResult::maximum_payload_length;
        result.payload_length = static_cast<std::uint8_t>(copy_length);
        result.truncated = data->len > BLEScanResult::maximum_payload_length;
        if (copy_length != 0U)
        {
            ::memcpy(result.payload, data->data, copy_length);
        }
        copyAdvertisedName(result);

        if (!scanResultMatches(result))
        {
            return;
        }
        if (atomic_get(&scanning_active) == 0 ||
            generation != static_cast<std::uint32_t>(
                              atomic_get(&device_session_generation)))
        {
            return;
        }
        const ScanResultRecord record = {
            .result = result,
            .generation = generation,
        };
        if (k_msgq_put(&scan_result_queue, &record, K_NO_WAIT) != 0)
        {
            atomic_inc(&dropped_scan_value);
            nucode::ble::internal::recordError(BLEError::scan_result_overflow,
                                               -ENOBUFS, true);
            return;
        }
        queueEvent(BLEEvent::scan_result, generation);
    }

    /** @brief MTU 교환 완료를 main-thread event로 변환합니다. */
    void mtuExchangeCompleted(struct bt_conn *connection, std::uint8_t error,
                              struct bt_gatt_exchange_params *parameters) noexcept
    {
        ARG_UNUSED(parameters);
        std::uint32_t generation = 0U;
        if (!activeConnectionGeneration(connection, generation))
        {
            return;
        }
        atomic_set(&mtu_exchange_active, 0);
        if (error != 0U)
        {
            nucode::ble::internal::recordError(BLEError::driver_error,
                                               -static_cast<int>(error), true);
            return;
        }
        queueEvent(BLEEvent::mtu_changed, generation);
    }

    /** @brief GATT layer가 관찰한 ATT MTU 변경을 main thread에 전달합니다. */
    void mtuUpdated(struct bt_conn *connection, std::uint16_t transmit,
                    std::uint16_t receive) noexcept
    {
        ARG_UNUSED(transmit);
        ARG_UNUSED(receive);
        std::uint32_t generation = 0U;
        if (atomic_get(&device_initialized) != 0 &&
            activeConnectionGeneration(connection, generation))
        {
            queueEvent(BLEEvent::mtu_changed, generation);
        }
    }

    struct bt_gatt_cb gatt_callbacks = {
        .att_mtu_updated = mtuUpdated,
    };

    /** @brief generic BLE incoming/outgoing connection을 단일 slot에 연결합니다. */
    void connectionEstablished(struct bt_conn *connection, std::uint8_t error) noexcept
    {
        bool owns_connection = false;
        bool handles_current_attempt = false;
        struct bt_conn *release_connection = nullptr;
        std::uint32_t connection_generation = 0U;
        const std::uint32_t current_generation = static_cast<std::uint32_t>(
            atomic_get(&device_session_generation));
        k_spinlock_key_t key = k_spin_lock(&connection_lock);
        if (pending_connection == connection)
        {
            handles_current_attempt =
                pending_connection_generation == current_generation &&
                atomic_get(&device_initialized) != 0;
            connection_generation = pending_connection_generation;
            if (error == 0U && handles_current_attempt && active_connection == nullptr)
            {
                active_connection = pending_connection;
                active_connection_generation = pending_connection_generation;
                pending_connection = nullptr;
                pending_connection_generation = 0U;
                owns_connection = true;
            }
            else
            {
                release_connection = pending_connection;
                pending_connection = nullptr;
                pending_connection_generation = 0U;
            }
        }
        else if (error == 0U && atomic_get(&device_initialized) != 0 &&
                 atomic_get(&advertising_active) != 0 &&
                 active_connection == nullptr)
        {
            owns_connection = true;
            active_connection = bt_conn_ref(connection);
            active_connection_generation = current_generation;
            connection_generation = current_generation;
        }
        k_spin_unlock(&connection_lock, key);

        if (release_connection != nullptr)
        {
            if (error == 0U)
            {
                static_cast<void>(bt_conn_disconnect(
                    release_connection, BT_HCI_ERR_REMOTE_USER_TERM_CONN));
            }
            bt_conn_unref(release_connection);
        }

        if (!owns_connection && !(handles_current_attempt && error != 0U))
        {
            return;
        }
        atomic_set(&connection_connecting, 0);
        if (error != 0U)
        {
            atomic_set(&connection_active, 0);
            nucode::ble::internal::recordError(BLEError::driver_error,
                                               -static_cast<int>(error), true);
            return;
        }

        if (atomic_get(&device_initialized) == 0 ||
            connection_generation != static_cast<std::uint32_t>(
                                         atomic_get(&device_session_generation)))
        {
            atomic_set(&connection_active, 0);
            static_cast<void>(bt_conn_disconnect(
                connection, BT_HCI_ERR_REMOTE_USER_TERM_CONN));
            return;
        }
        atomic_set(&advertising_active, 0);
        atomic_set(&connection_active, 1);
        if (atomic_get(&device_initialized) == 0 ||
            connection_generation != static_cast<std::uint32_t>(
                                         atomic_get(&device_session_generation)))
        {
            atomic_set(&connection_active, 0);
            static_cast<void>(bt_conn_disconnect(
                connection, BT_HCI_ERR_REMOTE_USER_TERM_CONN));
            return;
        }
        nucode::ble::internal::gattConnected(connection, connection_generation);
        nucode::ble::internal::securityConnected(connection);
        queueEvent(BLEEvent::connected, connection_generation);
    }

    /** @brief disconnect에서 모든 generic handle/reference를 먼저 무효화합니다. */
    void connectionDisconnected(struct bt_conn *connection, std::uint8_t reason) noexcept
    {
        ARG_UNUSED(reason);
        bool owns_connection = false;
        std::uint32_t connection_generation = 0U;
        k_spinlock_key_t key = k_spin_lock(&connection_lock);
        if (active_connection == connection)
        {
            owns_connection = true;
            connection_generation = active_connection_generation;
            active_connection = nullptr;
            active_connection_generation = 0U;
        }
        k_spin_unlock(&connection_lock, key);
        if (!owns_connection)
        {
            return;
        }

        nucode::ble::internal::gattDisconnected(connection, connection_generation);
        nucode::ble::internal::securityDisconnected(connection);
        bt_conn_unref(connection);
        atomic_set(&connection_active, 0);
        atomic_set(&connection_connecting, 0);
        atomic_set(&mtu_exchange_active, 0);
        if (atomic_get(&device_initialized) != 0)
        {
            queueEvent(BLEEvent::disconnected, connection_generation);
        }
    }

    /** @brief LE connection parameter update를 main-thread event로 변환합니다. */
    void parametersUpdated(struct bt_conn *connection, std::uint16_t interval,
                           std::uint16_t latency, std::uint16_t timeout) noexcept
    {
        ARG_UNUSED(interval);
        ARG_UNUSED(latency);
        ARG_UNUSED(timeout);
        std::uint32_t generation = 0U;
        if (atomic_get(&device_initialized) != 0 &&
            activeConnectionGeneration(connection, generation))
        {
            queueEvent(BLEEvent::parameters_changed, generation);
        }
    }

#if defined(CONFIG_BT_USER_PHY_UPDATE)
    /** @brief LE PHY update를 main-thread event로 변환합니다. */
    void phyUpdated(struct bt_conn *connection,
                    struct bt_conn_le_phy_info *information) noexcept
    {
        ARG_UNUSED(information);
        std::uint32_t generation = 0U;
        if (atomic_get(&device_initialized) != 0 &&
            activeConnectionGeneration(connection, generation))
        {
            queueEvent(BLEEvent::phy_changed, generation);
        }
    }
#endif

#if defined(CONFIG_BT_SMP) || defined(CONFIG_BT_CLASSIC)
    /** @brief security 변경을 M21의 bounded event 계층으로 전달합니다. */
    void linkSecurityChanged(struct bt_conn *connection, bt_security_t level,
                             enum bt_security_err error) noexcept
    {
        nucode::ble::internal::securityChanged(connection, level, error);
    }
#endif

    BT_CONN_CB_DEFINE(nucode_ble_gap_connection_callbacks) = {
        .connected = connectionEstablished,
        .disconnected = connectionDisconnected,
        .le_param_updated = parametersUpdated,
#if defined(CONFIG_BT_SMP) || defined(CONFIG_BT_CLASSIC)
        .security_changed = linkSecurityChanged,
#endif
#if defined(CONFIG_BT_USER_PHY_UPDATE)
        .le_phy_updated = phyUpdated,
#endif
    };

    /** @brief BLE PHY bit를 portable enum으로 변환합니다. */
    BLEPhy publicPhy(std::uint8_t phy) noexcept
    {
        if ((phy & BT_GAP_LE_PHY_2M) != 0U)
        {
            return BLEPhy::le_2m;
        }
        if ((phy & BT_GAP_LE_PHY_CODED) != 0U)
        {
            return BLEPhy::coded;
        }
        if ((phy & BT_GAP_LE_PHY_1M) != 0U)
        {
            return BLEPhy::le_1m;
        }
        return BLEPhy::unknown;
    }

    /** @brief AD field를 payload budget을 검사하며 배열에 추가합니다. */
    bool appendAdvertisingField(struct bt_data *fields, std::size_t &field_count,
                                std::size_t maximum_fields, std::size_t &serialized,
                                std::uint8_t type, const std::uint8_t *data,
                                std::size_t length) noexcept
    {
        if (field_count >= maximum_fields || length > UINT8_MAX ||
            serialized + length + 2U > nucode::ble::Advertising::maximum_payload_length)
        {
            return false;
        }
        fields[field_count] = {
            .type = type,
            .data_len = static_cast<std::uint8_t>(length),
            .data = data,
        };
        ++field_count;
        serialized += length + 2U;
        return true;
    }

} // namespace

namespace nucode::ble::internal
{

    void recordError(BLEError error, int driver_error, bool notify) noexcept
    {
        atomic_set(&last_error_value, static_cast<atomic_val_t>(error));
        atomic_set(&last_driver_error_value, driver_error);
        if (notify && error != BLEError::none)
        {
            queueEvent(BLEEvent::error);
        }
    }

    struct bt_conn *referenceConnection() noexcept
    {
        return referenceActiveConnection();
    }

} // namespace nucode::ble::internal

namespace nucode::ble
{

    BLEUuid::BLEUuid(std::uint16_t value) noexcept : type_(Type::uuid16)
    {
        bytes_[0] = static_cast<std::uint8_t>(value & 0xffU);
        bytes_[1] = static_cast<std::uint8_t>((value >> 8U) & 0xffU);
    }

    BLEUuid::BLEUuid(const char *canonical) noexcept
    {
        if (canonical == nullptr || ::strlen(canonical) != 36U ||
            canonical[8] != '-' || canonical[13] != '-' || canonical[18] != '-' ||
            canonical[23] != '-')
        {
            return;
        }

        std::uint8_t network_order[16] = {};
        std::size_t source = 0U;
        std::size_t destination = 0U;
        while (source < 36U)
        {
            if (canonical[source] == '-')
            {
                ++source;
                continue;
            }
            if (source + 1U >= 36U || destination >= sizeof(network_order))
            {
                return;
            }
            const int high = hexValue(canonical[source]);
            const int low = hexValue(canonical[source + 1U]);
            if (high < 0 || low < 0)
            {
                return;
            }
            network_order[destination++] =
                static_cast<std::uint8_t>((high << 4U) | low);
            source += 2U;
        }
        if (destination != sizeof(network_order))
        {
            return;
        }
        for (std::size_t index = 0U; index < sizeof(network_order); ++index)
        {
            bytes_[index] = network_order[sizeof(network_order) - index - 1U];
        }
        type_ = Type::uuid128;
    }

    BLEUuid BLEUuid::from32(std::uint32_t value) noexcept
    {
        BLEUuid result;
        result.type_ = Type::uuid32;
        for (std::size_t index = 0U; index < 4U; ++index)
        {
            result.bytes_[index] =
                static_cast<std::uint8_t>((value >> (index * 8U)) & 0xffU);
        }
        return result;
    }

    bool BLEUuid::valid() const noexcept
    {
        return type_ != Type::invalid;
    }

    BLEUuid::Type BLEUuid::type() const noexcept
    {
        return type_;
    }

    std::size_t BLEUuid::size() const noexcept
    {
        return static_cast<std::size_t>(type_);
    }

    const std::uint8_t *BLEUuid::data() const noexcept
    {
        return bytes_;
    }

    bool BLEUuid::format(char *output, std::size_t capacity) const noexcept
    {
        if (output == nullptr || !valid())
        {
            return false;
        }
        if (type_ == Type::uuid16)
        {
            if (capacity < 5U)
            {
                return false;
            }
            const std::uint16_t value = static_cast<std::uint16_t>(bytes_[0]) |
                                        (static_cast<std::uint16_t>(bytes_[1]) << 8U);
            return ::snprintf(output, capacity, "%04x", value) == 4;
        }
        if (type_ == Type::uuid32)
        {
            if (capacity < 9U)
            {
                return false;
            }
            std::uint32_t value = 0U;
            for (std::size_t index = 0U; index < 4U; ++index)
            {
                value |= static_cast<std::uint32_t>(bytes_[index]) << (index * 8U);
            }
            return ::snprintf(output, capacity, "%08lx",
                              static_cast<unsigned long>(value)) == 8;
        }
        if (capacity < 37U)
        {
            return false;
        }
        std::uint8_t network_order[16] = {};
        for (std::size_t index = 0U; index < sizeof(network_order); ++index)
        {
            network_order[index] = bytes_[sizeof(network_order) - index - 1U];
        }
        return ::snprintf(
                   output, capacity,
                   "%02x%02x%02x%02x-%02x%02x-%02x%02x-%02x%02x-"
                   "%02x%02x%02x%02x%02x%02x",
                   network_order[0], network_order[1], network_order[2], network_order[3],
                   network_order[4], network_order[5], network_order[6], network_order[7],
                   network_order[8], network_order[9], network_order[10], network_order[11],
                   network_order[12], network_order[13], network_order[14],
                   network_order[15]) == 36;
    }

    bool BLEUuid::operator==(const BLEUuid &other) const noexcept
    {
        return type_ == other.type_ && valid() &&
               ::memcmp(bytes_, other.bytes_, size()) == 0;
    }

    bool BLEUuid::operator!=(const BLEUuid &other) const noexcept
    {
        return !(*this == other);
    }

    BLEAddress::BLEAddress(const char *text, Type type) noexcept
    {
        if (text == nullptr || type == Type::invalid)
        {
            return;
        }
        unsigned int values[6] = {};
        int consumed = 0;
        if (::sscanf(text, "%2x:%2x:%2x:%2x:%2x:%2x%n", &values[0], &values[1],
                     &values[2], &values[3], &values[4], &values[5], &consumed) != 6 ||
            consumed != 17 || text[consumed] != '\0')
        {
            return;
        }
        for (std::size_t index = 0U; index < 6U; ++index)
        {
            if (values[index] > 0xffU)
            {
                return;
            }
            bytes_[5U - index] = static_cast<std::uint8_t>(values[index]);
        }
        type_ = type;
    }

    BLEAddress::BLEAddress(const std::uint8_t bytes[6], Type type) noexcept
    {
        if (bytes == nullptr || type == Type::invalid)
        {
            return;
        }
        ::memcpy(bytes_, bytes, sizeof(bytes_));
        type_ = type;
    }

    bool BLEAddress::valid() const noexcept
    {
        return type_ != Type::invalid;
    }

    BLEAddress::Type BLEAddress::type() const noexcept
    {
        return type_;
    }

    const std::uint8_t *BLEAddress::data() const noexcept
    {
        return bytes_;
    }

    bool BLEAddress::format(char *output, std::size_t capacity) const noexcept
    {
        if (output == nullptr || capacity < 18U || !valid())
        {
            return false;
        }
        return ::snprintf(output, capacity, "%02X:%02X:%02X:%02X:%02X:%02X",
                          bytes_[5], bytes_[4], bytes_[3], bytes_[2], bytes_[1],
                          bytes_[0]) == 17;
    }

    bool BLEAddress::operator==(const BLEAddress &other) const noexcept
    {
        return type_ == other.type_ && valid() &&
               ::memcmp(bytes_, other.bytes_, sizeof(bytes_)) == 0;
    }

    bool BLEAddress::operator!=(const BLEAddress &other) const noexcept
    {
        return !(*this == other);
    }

    bool Device::begin(const char *name) noexcept
    {
        if (!requireThreadContext() || name == nullptr)
        {
            if (name == nullptr)
            {
                internal::recordError(BLEError::invalid_argument, -EINVAL, true);
            }
            return false;
        }
        const std::size_t length = ::strlen(name);
        if (length == 0U || length > CONFIG_BT_DEVICE_NAME_MAX ||
            !validUtf8(name, length))
        {
            internal::recordError(BLEError::invalid_argument, -EINVAL, true);
            return false;
        }

        k_mutex_lock(&gap_lifecycle_mutex, K_FOREVER);
        if (atomic_get(&device_initialized) != 0)
        {
            k_mutex_unlock(&gap_lifecycle_mutex);
            internal::recordError(BLEError::already_started, -EALREADY, true);
            return false;
        }
        if (!internal::claimFacade(internal::FacadeOwner::generic))
        {
            k_mutex_unlock(&gap_lifecycle_mutex);
            internal::recordError(BLEError::already_started, -EALREADY, true);
            return false;
        }

        int result = internal::prepareGattDatabase();
        if (result == 0)
        {
            result = internal::ensureStack();
        }
        if (result == 0)
        {
            result = bt_set_name(name);
        }
        if (result < 0)
        {
            internal::releaseFacade(internal::FacadeOwner::generic);
            k_mutex_unlock(&gap_lifecycle_mutex);
            internal::recordError(BLEError::driver_error, result, true);
            return false;
        }

        k_msgq_purge(&gap_event_queue);
        k_msgq_purge(&scan_result_queue);
        atomic_set(&advertising_active, 0);
        atomic_set(&scanning_active, 0);
        atomic_set(&connection_connecting, 0);
        atomic_set(&connection_active, 0);
        atomic_set(&mtu_exchange_active, 0);
        ::memcpy(local_name, name, length + 1U);
        if (atomic_cas(&gatt_callback_registered, 0, 1))
        {
            bt_gatt_cb_register(&gatt_callbacks);
        }
        atomic_set(&device_initialized, 1);
        internal::recordError(BLEError::none, 0, false);
        k_mutex_unlock(&gap_lifecycle_mutex);
        queueEvent(BLEEvent::initialized);
        return true;
    }

    void Device::poll() noexcept
    {
        if (!requireThreadContext())
        {
            return;
        }
        GapEventRecord record = {};
        while (k_msgq_get(&gap_event_queue, &record, K_NO_WAIT) == 0)
        {
            if (record.generation != static_cast<std::uint32_t>(
                                         atomic_get(&device_session_generation)))
            {
                continue;
            }
            BLEEventCallback callback = event_callback;
            if (callback != nullptr)
            {
                callback(record.event, event_context);
            }
        }

        BLEScanCallback result_callback = scan_callback;
        if (result_callback != nullptr)
        {
            ScanResultRecord record = {};
            while (k_msgq_get(&scan_result_queue, &record, K_NO_WAIT) == 0)
            {
                if (record.generation == static_cast<std::uint32_t>(
                                             atomic_get(
                                                 &device_session_generation)))
                {
                    result_callback(record.result, scan_context);
                }
            }
        }
        internal::pollGatt();
    }

    void Device::end() noexcept
    {
        if (!requireThreadContext())
        {
            return;
        }
        k_mutex_lock(&gap_lifecycle_mutex, K_FOREVER);
        if (atomic_get(&device_initialized) == 0)
        {
            k_mutex_unlock(&gap_lifecycle_mutex);
            return;
        }
        atomic_set(&device_initialized, 0);
        atomic_inc(&device_session_generation);

        const bool stop_scan = atomic_cas(&scanning_active, 1, 0);
        const bool stop_advertising = atomic_cas(&advertising_active, 1, 0);
        if (stop_scan)
        {
            static_cast<void>(bt_le_scan_stop());
        }
        if (stop_advertising)
        {
            static_cast<void>(bt_le_adv_stop());
        }

        struct bt_conn *active = nullptr;
        struct bt_conn *pending = nullptr;
        k_spinlock_key_t key = k_spin_lock(&connection_lock);
        active = active_connection;
        pending = pending_connection;
        active_connection = nullptr;
        pending_connection = nullptr;
        active_connection_generation = 0U;
        pending_connection_generation = 0U;
        last_peer_address = BLEAddress{};
        k_spin_unlock(&connection_lock, key);

        atomic_set(&connection_connecting, 0);
        atomic_set(&connection_active, 0);
        atomic_set(&mtu_exchange_active, 0);
        k_msgq_purge(&gap_event_queue);
        k_msgq_purge(&scan_result_queue);

        if (pending != nullptr)
        {
            static_cast<void>(bt_conn_disconnect(
                pending, BT_HCI_ERR_REMOTE_USER_TERM_CONN));
            bt_conn_unref(pending);
        }
        if (active != nullptr)
        {
            nucode::ble::internal::securityDisconnected(active);
            static_cast<void>(bt_conn_disconnect(
                active, BT_HCI_ERR_REMOTE_USER_TERM_CONN));
            bt_conn_unref(active);
        }
        nucode::ble::internal::gattEnded();
        internal::releaseFacade(internal::FacadeOwner::generic);
        k_mutex_unlock(&gap_lifecycle_mutex);
    }

    bool Device::initialized() const noexcept
    {
        return atomic_get(&device_initialized) != 0;
    }

    const char *Device::localName() const noexcept
    {
        return local_name;
    }

    void Device::onEvent(BLEEventCallback callback, void *context) noexcept
    {
        event_callback = callback;
        event_context = context;
    }

    bool Device::addService(BLEService &service) noexcept
    {
        if (!requireThreadContext())
        {
            return false;
        }
        return internal::addGattService(service);
    }

    BLEError Device::lastError() const noexcept
    {
        return static_cast<BLEError>(atomic_get(&last_error_value));
    }

    int Device::lastDriverError() const noexcept
    {
        return static_cast<int>(atomic_get(&last_driver_error_value));
    }

    std::uint32_t Device::droppedEvents() const noexcept
    {
        return static_cast<std::uint32_t>(atomic_get(&dropped_event_value));
    }

    bool Advertising::clear() noexcept
    {
        if (!requireThreadContext() || running())
        {
            if (running())
            {
                internal::recordError(BLEError::busy, -EBUSY, true);
            }
            return false;
        }
        k_spinlock_key_t key = k_spin_lock(&configuration_lock);
        advertising_configuration = AdvertisingConfiguration{};
        k_spin_unlock(&configuration_lock, key);
        return true;
    }

    bool Advertising::setConnectable(bool connectable) noexcept
    {
        if (!requireThreadContext() || running())
        {
            if (running())
            {
                internal::recordError(BLEError::busy, -EBUSY, true);
            }
            return false;
        }
        advertising_configuration.connectable = connectable;
        return true;
    }

    bool Advertising::setFlags(std::uint8_t flags) noexcept
    {
        if (!requireThreadContext() || running())
        {
            if (running())
            {
                internal::recordError(BLEError::busy, -EBUSY, true);
            }
            return false;
        }
        advertising_configuration.flags = flags;
        return true;
    }

    bool Advertising::setInterval(std::uint16_t minimum,
                                  std::uint16_t maximum) noexcept
    {
        if (!requireThreadContext() || running())
        {
            if (running())
            {
                internal::recordError(BLEError::busy, -EBUSY, true);
            }
            return false;
        }
        if (minimum < minimum_advertising_interval ||
            maximum > maximum_advertising_interval || minimum > maximum)
        {
            internal::recordError(BLEError::invalid_argument, -EINVAL, true);
            return false;
        }
        advertising_configuration.interval_min = minimum;
        advertising_configuration.interval_max = maximum;
        return true;
    }

    bool Advertising::addServiceUuid(const BLEUuid &uuid) noexcept
    {
        if (!requireThreadContext() || running())
        {
            if (running())
            {
                internal::recordError(BLEError::busy, -EBUSY, true);
            }
            return false;
        }
        if (!uuid.valid())
        {
            internal::recordError(BLEError::invalid_argument, -EINVAL, true);
            return false;
        }
        for (std::size_t index = 0U;
             index < advertising_configuration.service_uuid_count; ++index)
        {
            if (advertising_configuration.service_uuids[index] == uuid)
            {
                internal::recordError(BLEError::duplicate, -EEXIST, true);
                return false;
            }
        }
        if (advertising_configuration.service_uuid_count >= maximum_service_uuids)
        {
            internal::recordError(BLEError::payload_overflow, -ENOSPC, true);
            return false;
        }
        advertising_configuration
            .service_uuids[advertising_configuration.service_uuid_count++] = uuid;
        return true;
    }

    bool Advertising::setManufacturerData(std::uint16_t company_id, const void *data,
                                          std::size_t length) noexcept
    {
        if (!requireThreadContext() || running())
        {
            if (running())
            {
                internal::recordError(BLEError::busy, -EBUSY, true);
            }
            return false;
        }
        if ((data == nullptr && length != 0U) || length + 2U > maximum_ad_field_data)
        {
            internal::recordError(BLEError::payload_overflow, -EMSGSIZE, true);
            return false;
        }
        advertising_configuration.company_id = company_id;
        advertising_configuration.manufacturer_length = length;
        advertising_configuration.has_manufacturer_data = true;
        if (length != 0U)
        {
            ::memcpy(advertising_configuration.manufacturer_data, data, length);
        }
        return true;
    }

    bool Advertising::setServiceData(const BLEUuid &uuid, const void *data,
                                     std::size_t length) noexcept
    {
        if (!requireThreadContext() || running())
        {
            if (running())
            {
                internal::recordError(BLEError::busy, -EBUSY, true);
            }
            return false;
        }
        if (!uuid.valid() || (data == nullptr && length != 0U) ||
            uuid.size() + length > maximum_ad_field_data)
        {
            internal::recordError(
                uuid.valid() ? BLEError::payload_overflow : BLEError::invalid_argument,
                uuid.valid() ? -EMSGSIZE : -EINVAL, true);
            return false;
        }
        advertising_configuration.service_data_uuid = uuid;
        advertising_configuration.service_data_length = length;
        advertising_configuration.has_service_data = true;
        if (length != 0U)
        {
            ::memcpy(advertising_configuration.service_data, data, length);
        }
        return true;
    }

    bool Advertising::setScanResponseName(bool enabled) noexcept
    {
        if (!requireThreadContext() || running())
        {
            if (running())
            {
                internal::recordError(BLEError::busy, -EBUSY, true);
            }
            return false;
        }
        advertising_configuration.scan_response_name = enabled;
        return true;
    }

    bool Advertising::start() noexcept
    {
        if (!requireThreadContext())
        {
            return false;
        }
        if (atomic_get(&device_initialized) == 0)
        {
            internal::recordError(BLEError::not_initialized, -EPERM, true);
            return false;
        }
        if (running())
        {
            internal::recordError(BLEError::already_started, -EALREADY, true);
            return false;
        }
        if (atomic_get(&scanning_active) != 0 || atomic_get(&connection_connecting) != 0 ||
            atomic_get(&connection_active) != 0)
        {
            internal::recordError(BLEError::busy, -EBUSY, true);
            return false;
        }

        const AdvertisingConfiguration configuration = advertising_configuration;
        struct bt_data advertising_fields[8] = {};
        struct bt_data scan_response_fields[1] = {};
        std::uint8_t manufacturer_field[maximum_ad_field_data] = {};
        std::uint8_t service_data_field[maximum_ad_field_data] = {};
        std::uint8_t uuid16_field[maximum_ad_field_data] = {};
        std::uint8_t uuid32_field[maximum_ad_field_data] = {};
        std::uint8_t uuid128_field[maximum_ad_field_data] = {};
        std::size_t uuid16_length = 0U;
        std::size_t uuid32_length = 0U;
        std::size_t uuid128_length = 0U;
        std::size_t advertising_count = 0U;
        std::size_t advertising_size = 0U;
        std::size_t scan_response_count = 0U;
        std::size_t scan_response_size = 0U;

        if (!appendAdvertisingField(advertising_fields, advertising_count,
                                    ARRAY_SIZE(advertising_fields), advertising_size,
                                    BT_DATA_FLAGS, &configuration.flags, 1U))
        {
            internal::recordError(BLEError::payload_overflow, -EMSGSIZE, true);
            return false;
        }
        for (std::size_t index = 0U; index < configuration.service_uuid_count; ++index)
        {
            const BLEUuid &uuid = configuration.service_uuids[index];
            std::uint8_t *field = uuid128_field;
            std::size_t *field_length = &uuid128_length;
            if (uuid.type() == BLEUuid::Type::uuid16)
            {
                field = uuid16_field;
                field_length = &uuid16_length;
            }
            else if (uuid.type() == BLEUuid::Type::uuid32)
            {
                field = uuid32_field;
                field_length = &uuid32_length;
            }
            if (*field_length + uuid.size() > maximum_ad_field_data)
            {
                internal::recordError(BLEError::payload_overflow, -EMSGSIZE, true);
                return false;
            }
            ::memcpy(&field[*field_length], uuid.data(), uuid.size());
            *field_length += uuid.size();
        }
        const struct
        {
            std::uint8_t type;
            const std::uint8_t *data;
            std::size_t length;
        } uuid_fields[] = {
            {BT_DATA_UUID16_ALL, uuid16_field, uuid16_length},
            {BT_DATA_UUID32_ALL, uuid32_field, uuid32_length},
            {BT_DATA_UUID128_ALL, uuid128_field, uuid128_length},
        };
        for (const auto &field : uuid_fields)
        {
            if (field.length != 0U &&
                !appendAdvertisingField(
                    advertising_fields, advertising_count,
                    ARRAY_SIZE(advertising_fields), advertising_size, field.type,
                    field.data, field.length))
            {
                internal::recordError(BLEError::payload_overflow, -EMSGSIZE, true);
                return false;
            }
        }
        if (configuration.has_manufacturer_data)
        {
            manufacturer_field[0] =
                static_cast<std::uint8_t>(configuration.company_id & 0xffU);
            manufacturer_field[1] =
                static_cast<std::uint8_t>((configuration.company_id >> 8U) & 0xffU);
            ::memcpy(&manufacturer_field[2], configuration.manufacturer_data,
                     configuration.manufacturer_length);
            if (!appendAdvertisingField(
                    advertising_fields, advertising_count, ARRAY_SIZE(advertising_fields),
                    advertising_size, BT_DATA_MANUFACTURER_DATA, manufacturer_field,
                    configuration.manufacturer_length + 2U))
            {
                internal::recordError(BLEError::payload_overflow, -EMSGSIZE, true);
                return false;
            }
        }
        if (configuration.has_service_data)
        {
            const BLEUuid &uuid = configuration.service_data_uuid;
            ::memcpy(service_data_field, uuid.data(), uuid.size());
            ::memcpy(&service_data_field[uuid.size()], configuration.service_data,
                     configuration.service_data_length);
            const std::uint8_t type =
                uuid.type() == BLEUuid::Type::uuid16
                    ? BT_DATA_SVC_DATA16
                    : (uuid.type() == BLEUuid::Type::uuid32 ? BT_DATA_SVC_DATA32
                                                            : BT_DATA_SVC_DATA128);
            if (!appendAdvertisingField(
                    advertising_fields, advertising_count, ARRAY_SIZE(advertising_fields),
                    advertising_size, type, service_data_field,
                    uuid.size() + configuration.service_data_length))
            {
                internal::recordError(BLEError::payload_overflow, -EMSGSIZE, true);
                return false;
            }
        }
        if (configuration.scan_response_name)
        {
            const std::size_t name_length = ::strlen(local_name);
            if (!appendAdvertisingField(
                    scan_response_fields, scan_response_count,
                    ARRAY_SIZE(scan_response_fields), scan_response_size,
                    BT_DATA_NAME_COMPLETE,
                    reinterpret_cast<const std::uint8_t *>(local_name), name_length))
            {
                internal::recordError(BLEError::payload_overflow, -EMSGSIZE, true);
                return false;
            }
        }

        std::uint32_t options = configuration.connectable ? BT_LE_ADV_OPT_CONN
                                                          : BT_LE_ADV_OPT_NONE;
        if (!configuration.connectable && scan_response_count != 0U)
        {
            options |= BT_LE_ADV_OPT_SCANNABLE;
        }
        const struct bt_le_adv_param parameters = {
            .id = BT_ID_DEFAULT,
            .sid = 0U,
            .secondary_max_skip = 0U,
            .options = options,
            .interval_min = configuration.interval_min,
            .interval_max = configuration.interval_max,
            .peer = nullptr,
        };
        const int result = bt_le_adv_start(
            &parameters, advertising_fields, advertising_count, scan_response_fields,
            scan_response_count);
        if (result < 0)
        {
            internal::recordError(BLEError::driver_error, result, true);
            return false;
        }
        atomic_set(&advertising_active, 1);
        internal::recordError(BLEError::none, 0, false);
        queueEvent(BLEEvent::advertising_started);
        return true;
    }

    bool Advertising::stop() noexcept
    {
        if (!requireThreadContext())
        {
            return false;
        }
        if (!running())
        {
            internal::recordError(BLEError::wrong_state, -EALREADY, true);
            return false;
        }
        const int result = bt_le_adv_stop();
        if (result < 0)
        {
            internal::recordError(BLEError::driver_error, result, true);
            return false;
        }
        atomic_set(&advertising_active, 0);
        queueEvent(BLEEvent::advertising_stopped);
        return true;
    }

    bool Advertising::running() const noexcept
    {
        return atomic_get(&advertising_active) != 0;
    }

    bool Scan::clearFilters() noexcept
    {
        if (!requireThreadContext() || running())
        {
            if (running())
            {
                internal::recordError(BLEError::busy, -EBUSY, true);
            }
            return false;
        }
        k_spinlock_key_t key = k_spin_lock(&configuration_lock);
        scan_configuration = ScanConfiguration{};
        k_spin_unlock(&configuration_lock, key);
        k_msgq_purge(&scan_result_queue);
        return true;
    }

    bool Scan::filterName(const char *exact_name) noexcept
    {
        if (!requireThreadContext() || running())
        {
            if (running())
            {
                internal::recordError(BLEError::busy, -EBUSY, true);
            }
            return false;
        }
        if (exact_name == nullptr)
        {
            internal::recordError(BLEError::invalid_argument, -EINVAL, true);
            return false;
        }
        const std::size_t length = ::strlen(exact_name);
        if (length == 0U || length > CONFIG_BT_DEVICE_NAME_MAX ||
            !validUtf8(exact_name, length))
        {
            internal::recordError(BLEError::invalid_argument, -EINVAL, true);
            return false;
        }
        k_spinlock_key_t key = k_spin_lock(&configuration_lock);
        ::memcpy(scan_configuration.name, exact_name, length + 1U);
        scan_configuration.has_name = true;
        k_spin_unlock(&configuration_lock, key);
        return true;
    }

    bool Scan::filterServiceUuid(const BLEUuid &uuid) noexcept
    {
        if (!requireThreadContext() || running())
        {
            if (running())
            {
                internal::recordError(BLEError::busy, -EBUSY, true);
            }
            return false;
        }
        if (!uuid.valid())
        {
            internal::recordError(BLEError::invalid_argument, -EINVAL, true);
            return false;
        }
        k_spinlock_key_t key = k_spin_lock(&configuration_lock);
        scan_configuration.uuid = uuid;
        scan_configuration.has_uuid = true;
        k_spin_unlock(&configuration_lock, key);
        return true;
    }

    bool Scan::filterAddress(const BLEAddress &address) noexcept
    {
        if (!requireThreadContext() || running())
        {
            if (running())
            {
                internal::recordError(BLEError::busy, -EBUSY, true);
            }
            return false;
        }
        if (!address.valid())
        {
            internal::recordError(BLEError::invalid_argument, -EINVAL, true);
            return false;
        }
        k_spinlock_key_t key = k_spin_lock(&configuration_lock);
        scan_configuration.address = address;
        scan_configuration.has_address = true;
        k_spin_unlock(&configuration_lock, key);
        return true;
    }

    bool Scan::start(bool active) noexcept
    {
        if (!requireThreadContext())
        {
            return false;
        }
        if (atomic_get(&device_initialized) == 0)
        {
            internal::recordError(BLEError::not_initialized, -EPERM, true);
            return false;
        }
        if (running())
        {
            internal::recordError(BLEError::already_started, -EALREADY, true);
            return false;
        }
        if (atomic_get(&advertising_active) != 0 ||
            atomic_get(&connection_connecting) != 0 || atomic_get(&connection_active) != 0)
        {
            internal::recordError(BLEError::busy, -EBUSY, true);
            return false;
        }
        k_msgq_purge(&scan_result_queue);
        const struct bt_le_scan_param parameters = {
            .type = active ? BT_LE_SCAN_TYPE_ACTIVE : BT_LE_SCAN_TYPE_PASSIVE,
            .options = BT_LE_SCAN_OPT_FILTER_DUPLICATE,
            .interval = BT_GAP_SCAN_FAST_INTERVAL,
            .window = BT_GAP_SCAN_FAST_WINDOW,
            .timeout = 0U,
            .interval_coded = 0U,
            .window_coded = 0U,
        };
        const int result = bt_le_scan_start(&parameters, scanReceived);
        if (result < 0)
        {
            internal::recordError(BLEError::driver_error, result, true);
            return false;
        }
        atomic_set(&scanning_active, 1);
        queueEvent(BLEEvent::scan_started);
        return true;
    }

    bool Scan::stop() noexcept
    {
        if (!requireThreadContext())
        {
            return false;
        }
        if (!running())
        {
            internal::recordError(BLEError::wrong_state, -EALREADY, true);
            return false;
        }
        const int result = bt_le_scan_stop();
        if (result < 0)
        {
            internal::recordError(BLEError::driver_error, result, true);
            return false;
        }
        atomic_set(&scanning_active, 0);
        queueEvent(BLEEvent::scan_stopped);
        return true;
    }

    bool Scan::running() const noexcept
    {
        return atomic_get(&scanning_active) != 0;
    }

    int Scan::available() const noexcept
    {
        return static_cast<int>(k_msgq_num_used_get(&scan_result_queue));
    }

    bool Scan::read(BLEScanResult &result) noexcept
    {
        ScanResultRecord record = {};
        while (k_msgq_get(&scan_result_queue, &record, K_NO_WAIT) == 0)
        {
            if (record.generation == static_cast<std::uint32_t>(
                                         atomic_get(&device_session_generation)))
            {
                result = record.result;
                return true;
            }
        }
        return false;
    }

    void Scan::onResult(BLEScanCallback callback, void *context) noexcept
    {
        scan_callback = callback;
        scan_context = context;
    }

    std::uint32_t Scan::droppedResults() const noexcept
    {
        return static_cast<std::uint32_t>(atomic_get(&dropped_scan_value));
    }

    bool Connection::connect(const BLEAddress &address) noexcept
    {
        if (!requireThreadContext())
        {
            return false;
        }
        if (atomic_get(&device_initialized) == 0)
        {
            internal::recordError(BLEError::not_initialized, -EPERM, true);
            return false;
        }
        if (!address.valid())
        {
            internal::recordError(BLEError::invalid_argument, -EINVAL, true);
            return false;
        }
        if (connecting() || connected())
        {
            internal::recordError(BLEError::already_started, -EALREADY, true);
            return false;
        }
        if (atomic_get(&advertising_active) != 0)
        {
            internal::recordError(BLEError::busy, -EBUSY, true);
            return false;
        }
        if (atomic_get(&scanning_active) != 0 && !BLEScan.stop())
        {
            return false;
        }

        bt_addr_le_t peer = {};
        if (!toZephyrAddress(address, peer))
        {
            internal::recordError(BLEError::invalid_argument, -EINVAL, true);
            return false;
        }
        struct bt_conn *connection = nullptr;
        const int result = bt_conn_le_create(&peer, BT_CONN_LE_CREATE_CONN,
                                             BT_LE_CONN_PARAM_DEFAULT, &connection);
        if (result < 0)
        {
            internal::recordError(BLEError::driver_error, result, true);
            return false;
        }
        k_spinlock_key_t key = k_spin_lock(&connection_lock);
        pending_connection = connection;
        pending_connection_generation = static_cast<std::uint32_t>(
            atomic_get(&device_session_generation));
        last_peer_address = address;
        k_spin_unlock(&connection_lock, key);
        atomic_set(&connection_connecting, 1);
        queueEvent(BLEEvent::connecting);
        return true;
    }

    bool Connection::disconnect() noexcept
    {
        if (!requireThreadContext())
        {
            return false;
        }
        struct bt_conn *connection = referenceActiveConnection();
        if (connection == nullptr)
        {
            internal::recordError(BLEError::not_connected, -ENOTCONN, true);
            return false;
        }
        const int result = bt_conn_disconnect(connection,
                                              BT_HCI_ERR_REMOTE_USER_TERM_CONN);
        bt_conn_unref(connection);
        if (result < 0)
        {
            internal::recordError(BLEError::driver_error, result, true);
            return false;
        }
        return true;
    }

    bool Connection::reconnect() noexcept
    {
        if (!last_peer_address.valid())
        {
            internal::recordError(BLEError::wrong_state, -ENOENT, true);
            return false;
        }
        return connect(last_peer_address);
    }

    bool Connection::connecting() const noexcept
    {
        return atomic_get(&connection_connecting) != 0;
    }

    bool Connection::connected() const noexcept
    {
        return atomic_get(&connection_active) != 0;
    }

    BLEAddress Connection::peerAddress() const noexcept
    {
        return last_peer_address;
    }

    std::size_t Connection::mtu() const noexcept
    {
        struct bt_conn *connection = referenceActiveConnection();
        if (connection == nullptr)
        {
            return 0U;
        }
        const std::size_t value = bt_gatt_get_mtu(connection);
        bt_conn_unref(connection);
        return value;
    }

    bool Connection::requestMtu() noexcept
    {
        if (!requireThreadContext())
        {
            return false;
        }
        struct bt_conn *connection = referenceActiveConnection();
        if (connection == nullptr)
        {
            internal::recordError(BLEError::not_connected, -ENOTCONN, true);
            return false;
        }
        if (!atomic_cas(&mtu_exchange_active, 0, 1))
        {
            bt_conn_unref(connection);
            internal::recordError(BLEError::busy, -EBUSY, true);
            return false;
        }
        mtu_exchange_parameters.func = mtuExchangeCompleted;
        const int result = bt_gatt_exchange_mtu(connection, &mtu_exchange_parameters);
        bt_conn_unref(connection);
        if (result < 0)
        {
            atomic_set(&mtu_exchange_active, 0);
            internal::recordError(result == -EALREADY ? BLEError::already_started
                                                      : BLEError::driver_error,
                                  result, true);
            return false;
        }
        return true;
    }

    BLEPhy Connection::phy() const noexcept
    {
#if defined(CONFIG_BT_USER_PHY_UPDATE)
        struct bt_conn *connection = referenceActiveConnection();
        if (connection == nullptr)
        {
            return BLEPhy::unknown;
        }
        struct bt_conn_info information = {};
        const int result = bt_conn_get_info(connection, &information);
        bt_conn_unref(connection);
        if (result < 0 || information.type != BT_CONN_TYPE_LE ||
            information.le.phy == nullptr)
        {
            return BLEPhy::unknown;
        }
        return publicPhy(information.le.phy->tx_phy);
#else
        return BLEPhy::unknown;
#endif
    }

    bool Connection::requestPhy(bool allow_2m, bool allow_coded) noexcept
    {
#if defined(CONFIG_BT_USER_PHY_UPDATE)
        if (!requireThreadContext())
        {
            return false;
        }
        struct bt_conn *connection = referenceActiveConnection();
        if (connection == nullptr)
        {
            internal::recordError(BLEError::not_connected, -ENOTCONN, true);
            return false;
        }
        std::uint8_t mask = BT_GAP_LE_PHY_1M;
        if (allow_2m)
        {
            mask |= BT_GAP_LE_PHY_2M;
        }
        if (allow_coded)
        {
            mask |= BT_GAP_LE_PHY_CODED;
        }
        const struct bt_conn_le_phy_param parameters = {
            .options = BT_CONN_LE_PHY_OPT_NONE,
            .pref_tx_phy = mask,
            .pref_rx_phy = mask,
        };
        const int result = bt_conn_le_phy_update(connection, &parameters);
        bt_conn_unref(connection);
        if (result < 0)
        {
            internal::recordError(BLEError::driver_error, result, true);
            return false;
        }
        return true;
#else
        ARG_UNUSED(allow_2m);
        ARG_UNUSED(allow_coded);
        internal::recordError(BLEError::unsupported, -ENOTSUP, true);
        return false;
#endif
    }

    bool Connection::txPower(std::int8_t &dbm) const noexcept
    {
        if (!requireThreadContext())
        {
            return false;
        }
        struct bt_conn *connection = referenceActiveConnection();
        if (connection == nullptr)
        {
            internal::recordError(BLEError::not_connected, -ENOTCONN, true);
            return false;
        }
        struct bt_conn_le_tx_power power = {
            .phy = 0U,
            .current_level = 0,
            .max_level = 0,
        };
        const int result = bt_conn_le_get_tx_power_level(connection, &power);
        bt_conn_unref(connection);
        if (result < 0)
        {
            internal::recordError(result == -ENOTSUP ? BLEError::unsupported
                                                     : BLEError::driver_error,
                                  result, true);
            return false;
        }
        dbm = power.current_level;
        return true;
    }

    bool Connection::requestParameters(std::uint16_t interval_min,
                                       std::uint16_t interval_max,
                                       std::uint16_t latency,
                                       std::uint16_t timeout) noexcept
    {
        if (!requireThreadContext())
        {
            return false;
        }
        const std::uint64_t supervision_units =
            static_cast<std::uint64_t>(timeout) * 4U;
        const std::uint64_t connection_event_units =
            static_cast<std::uint64_t>(latency + 1U) * interval_max;
        if (interval_min < 6U || interval_max > 3200U ||
            interval_min > interval_max || latency > 499U || timeout < 10U ||
            timeout > 3200U || supervision_units <= connection_event_units)
        {
            internal::recordError(BLEError::invalid_argument, -EINVAL, true);
            return false;
        }
        struct bt_conn *connection = referenceActiveConnection();
        if (connection == nullptr)
        {
            internal::recordError(BLEError::not_connected, -ENOTCONN, true);
            return false;
        }
        const struct bt_le_conn_param parameters = {
            .interval_min = interval_min,
            .interval_max = interval_max,
            .latency = latency,
            .timeout = timeout,
        };
        const int result = bt_conn_le_param_update(connection, &parameters);
        bt_conn_unref(connection);
        if (result < 0)
        {
            internal::recordError(BLEError::driver_error, result, true);
            return false;
        }
        return true;
    }

} // namespace nucode::ble

nucode::ble::Device BLEDevice;
nucode::ble::Advertising BLEAdvertising;
nucode::ble::Scan BLEScan;
nucode::ble::Connection BLEConnection;

#endif
