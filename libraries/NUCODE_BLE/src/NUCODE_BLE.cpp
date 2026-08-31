/**
 * @file NUCODE_BLE.cpp
 * @brief NCS NUS service/client 기반 Arduino Stream을 구현합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE.h>

#if !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE)
#include <internal/NUCODE_BLE_Internal.h>

#include <bluetooth/gatt_dm.h>
#include <bluetooth/services/nus.h>
#include <bluetooth/services/nus_client.h>
#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/conn.h>
#include <zephyr/bluetooth/gap.h>
#include <zephyr/bluetooth/hci.h>
#include <zephyr/kernel.h>
#include <zephyr/net_buf.h>
#include <zephyr/sys/atomic.h>
#include <zephyr/sys/util.h>

#include <errno.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

namespace
{

    using nucode::ble::Error;
    using nucode::ble::Event;
    using nucode::ble::EventCallback;

    /** @brief 한 image에서 선택할 수 있는 NUS GAP 역할입니다. */
    enum class Role : atomic_val_t
    {
        none = 0,
        peripheral = 1,
        central = 2,
    };

    /** @brief 비동기 TX가 끝날 때까지 library가 소유하는 최대 payload입니다. */
    constexpr std::size_t maximum_tx_payload = 244U;

    /** @brief exact local name 저장 공간입니다. */
    constexpr std::size_t maximum_local_name = CONFIG_BT_DEVICE_NAME_MAX;

    K_MSGQ_DEFINE(ble_rx_queue, sizeof(std::uint8_t),
                  CONFIG_NUCODE_BLE_RX_BUFFER_SIZE, alignof(std::uint8_t));
    K_MSGQ_DEFINE(ble_event_queue, sizeof(Event),
                  CONFIG_NUCODE_BLE_EVENT_QUEUE_SIZE, alignof(Event));
    K_MUTEX_DEFINE(ble_lifecycle_mutex);
    K_MUTEX_DEFINE(ble_tx_mutex);
    K_SEM_DEFINE(ble_tx_complete, 0, 1);

    atomic_t role_value = ATOMIC_INIT(static_cast<atomic_val_t>(Role::none));
    atomic_t modules_initialized = ATOMIC_INIT(0);
    atomic_t advertising_value = ATOMIC_INIT(0);
    atomic_t scanning_value = ATOMIC_INIT(0);
    atomic_t connected_value = ATOMIC_INIT(0);
    atomic_t ready_value = ATOMIC_INIT(0);
    atomic_t ending_value = ATOMIC_INIT(0);
    atomic_t auto_restart_value = ATOMIC_INIT(0);
    atomic_t restart_value = ATOMIC_INIT(0);
    atomic_t connect_candidate_value = ATOMIC_INIT(0);
    atomic_t receive_event_pending = ATOMIC_INIT(0);
    atomic_t last_error_value = ATOMIC_INIT(static_cast<atomic_val_t>(Error::none));
    atomic_t last_driver_error_value = ATOMIC_INIT(0);
    atomic_t dropped_rx_value = ATOMIC_INIT(0);
    atomic_t tx_result_value = ATOMIC_INIT(0);

    struct k_spinlock connection_lock;
    struct k_spinlock scan_lock;
    struct bt_conn *active_connection = nullptr;
    struct bt_conn *pending_connection = nullptr;
    bt_addr_le_t candidate_address = {};
    char expected_name[maximum_local_name + 1U] = {};
    char peripheral_name[maximum_local_name + 1U] = {};

    EventCallback event_callback = nullptr;
    void *event_context = nullptr;

    struct bt_nus_client nus_client = {};

    /** @brief 동적 STL 없이 두 payload 길이의 작은 값을 반환합니다. */
    constexpr std::size_t smaller(std::size_t left, std::size_t right) noexcept
    {
        return left < right ? left : right;
    }

    /** @brief 현재 역할을 형식 안전하게 읽습니다. */
    Role currentRole() noexcept
    {
        return static_cast<Role>(atomic_get(&role_value));
    }

    /** @brief event queue overflow를 무한 재귀 없이 기록합니다. */
    void queueEvent(Event event) noexcept
    {
        if (k_msgq_put(&ble_event_queue, &event, K_NO_WAIT) != 0)
        {
            atomic_set(&last_driver_error_value, -ENOBUFS);
            atomic_set(&last_error_value, static_cast<atomic_val_t>(Error::event_overflow));
        }
    }

    /** @brief 마지막 공개 오류와 driver 오류를 함께 기록합니다. */
    void recordError(Error error, int driver_error = 0, bool notify = false) noexcept
    {
        atomic_set(&last_driver_error_value, driver_error);
        atomic_set(&last_error_value, static_cast<atomic_val_t>(error));
        if (notify && error != Error::none)
        {
            queueEvent(Event::error);
        }
    }

    /** @brief thread 문맥 전용 공개 API를 검증합니다. */
    bool requireThreadContext() noexcept
    {
        if (k_is_in_isr())
        {
            recordError(Error::invalid_context, -EWOULDBLOCK, true);
            return false;
        }
        return true;
    }

    /** @brief callback payload를 고정 RX queue로 복사합니다. */
    void enqueueReceived(const std::uint8_t *data, std::uint16_t length) noexcept
    {
        if (data == nullptr)
        {
            return;
        }
        for (std::uint16_t index = 0U; index < length; ++index)
        {
            if (k_msgq_put(&ble_rx_queue, &data[index], K_NO_WAIT) != 0)
            {
                atomic_inc(&dropped_rx_value);
                recordError(Error::rx_overflow, -ENOBUFS);
            }
        }
        if (atomic_cas(&receive_event_pending, 0, 1))
        {
            queueEvent(Event::received);
        }
    }

    /** @brief NUS Peripheral RX write callback입니다. */
    void peripheralReceived(struct bt_conn *connection, const std::uint8_t *const data,
                            std::uint16_t length)
    {
        ARG_UNUSED(connection);
        enqueueReceived(data, length);
    }

    /** @brief Peripheral notification 완료를 blocking write에 전달합니다. */
    void peripheralSent(struct bt_conn *connection)
    {
        ARG_UNUSED(connection);
        atomic_set(&tx_result_value, 0);
        k_sem_give(&ble_tx_complete);
    }

    /** @brief Peripheral CCC 상태를 ready 계약으로 변환합니다. */
    void peripheralSendEnabled(enum bt_nus_send_status status)
    {
        const bool enabled = status == BT_NUS_SEND_STATUS_ENABLED;
        atomic_set(&ready_value, enabled ? 1 : 0);
        if (enabled)
        {
            queueEvent(Event::ready);
        }
    }

    /** @brief NUS Central notification callback입니다. */
    std::uint8_t centralReceived(struct bt_nus_client *client, const std::uint8_t *data,
                                 std::uint16_t length)
    {
        ARG_UNUSED(client);
        enqueueReceived(data, length);
        return BT_GATT_ITER_CONTINUE;
    }

    /** @brief Central write 완료까지 caller-owned buffer 수명을 연장합니다. */
    void centralSent(struct bt_nus_client *client, std::uint8_t error,
                     const std::uint8_t *data, std::uint16_t length)
    {
        ARG_UNUSED(client);
        ARG_UNUSED(data);
        ARG_UNUSED(length);
        atomic_set(&tx_result_value, static_cast<atomic_val_t>(error));
        k_sem_give(&ble_tx_complete);
    }

    /** @brief peer가 notification을 해제하면 ready 상태를 내립니다. */
    void centralUnsubscribed(struct bt_nus_client *client)
    {
        ARG_UNUSED(client);
        atomic_set(&ready_value, 0);
    }

    struct bt_nus_cb nus_server_callbacks = {
        .received = peripheralReceived,
        .sent = peripheralSent,
        .send_enabled = peripheralSendEnabled,
    };

    struct bt_nus_client_init_param nus_client_parameters = {
        .cb = {
            .received = centralReceived,
            .sent = centralSent,
            .unsubscribed = centralUnsubscribed,
        },
    };

    /** @brief active connection에 임시 reference를 얻습니다. */
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

    /** @brief GATT discovery 성공 뒤 NUS handle과 notification을 준비합니다. */
    void discoveryCompleted(struct bt_gatt_dm *discovery, void *context)
    {
        ARG_UNUSED(context);
        int result = bt_nus_handles_assign(discovery, &nus_client);
        if (result == 0)
        {
            result = bt_nus_subscribe_receive(&nus_client);
        }
        const int release_result = bt_gatt_dm_data_release(discovery);
        if (result == 0 && release_result < 0)
        {
            result = release_result;
        }
        if (result < 0)
        {
            recordError(Error::driver_error, result, true);
            return;
        }
        atomic_set(&ready_value, 1);
        queueEvent(Event::ready);
    }

    /** @brief NUS service 부재를 명시적 오류로 기록하고 연결을 종료합니다. */
    void discoveryNotFound(struct bt_conn *connection, void *context)
    {
        ARG_UNUSED(context);
        recordError(Error::not_ready, -ENOENT, true);
        static_cast<void>(bt_conn_disconnect(connection, BT_HCI_ERR_REMOTE_USER_TERM_CONN));
    }

    /** @brief GATT discovery 오류를 보존합니다. */
    void discoveryError(struct bt_conn *connection, int error, void *context)
    {
        ARG_UNUSED(context);
        recordError(Error::driver_error, error, true);
        static_cast<void>(bt_conn_disconnect(connection, BT_HCI_ERR_REMOTE_USER_TERM_CONN));
    }

    const struct bt_gatt_dm_cb discovery_callbacks = {
        .completed = discoveryCompleted,
        .service_not_found = discoveryNotFound,
        .error_found = discoveryError,
    };

    /** @brief 새 BLE link를 role별 NUS 준비 절차로 연결합니다. */
    void connectionEstablished(struct bt_conn *connection, std::uint8_t error)
    {
        if (currentRole() == Role::none || atomic_get(&ending_value) != 0)
        {
            return;
        }
        if (error != 0U)
        {
            k_spinlock_key_t key = k_spin_lock(&connection_lock);
            if (pending_connection != nullptr)
            {
                bt_conn_unref(pending_connection);
                pending_connection = nullptr;
            }
            k_spin_unlock(&connection_lock, key);
            atomic_set(&connected_value, 0);
            atomic_set(&ready_value, 0);
            atomic_set(&restart_value, 1);
            recordError(Error::driver_error, -static_cast<int>(error), true);
            return;
        }

        k_spinlock_key_t key = k_spin_lock(&connection_lock);
        if (atomic_get(&ending_value) != 0 || currentRole() == Role::none)
        {
            k_spin_unlock(&connection_lock, key);
            return;
        }
        if (pending_connection == connection)
        {
            active_connection = pending_connection;
            pending_connection = nullptr;
        }
        else
        {
            active_connection = bt_conn_ref(connection);
        }
        k_spin_unlock(&connection_lock, key);

        atomic_set(&advertising_value, 0);
        atomic_set(&scanning_value, 0);
        atomic_set(&connected_value, 1);
        queueEvent(Event::connected);

        if (currentRole() == Role::central)
        {
            const int result = bt_gatt_dm_start(connection, BT_UUID_NUS_SERVICE,
                                                &discovery_callbacks, nullptr);
            if (result < 0)
            {
                recordError(Error::driver_error, result, true);
                static_cast<void>(bt_conn_disconnect(connection,
                                                     BT_HCI_ERR_REMOTE_USER_TERM_CONN));
            }
        }
    }

    /** @brief disconnect를 event로 보존하고 connection reference를 회수합니다. */
    void connectionDisconnected(struct bt_conn *connection, std::uint8_t reason)
    {
        ARG_UNUSED(reason);
        if (currentRole() == Role::none)
        {
            return;
        }
        k_spinlock_key_t key = k_spin_lock(&connection_lock);
        if (active_connection == connection)
        {
            bt_conn_unref(active_connection);
            active_connection = nullptr;
        }
        nus_client.conn = nullptr;
        k_spin_unlock(&connection_lock, key);
        atomic_set(&connected_value, 0);
        atomic_set(&ready_value, 0);
        if (atomic_get(&ending_value) == 0)
        {
            queueEvent(Event::disconnected);
        }
    }

    /** @brief connection object가 pool로 돌아간 뒤에만 재광고·재연결을 허용합니다. */
    void connectionRecycled()
    {
        if (atomic_get(&auto_restart_value) != 0 && atomic_get(&ending_value) == 0)
        {
            atomic_set(&restart_value, 1);
        }
        else if (atomic_get(&ending_value) != 0)
        {
            atomic_set(&role_value, static_cast<atomic_val_t>(Role::none));
            atomic_set(&ending_value, 0);
            nucode::ble::internal::releaseFacade(
                nucode::ble::internal::FacadeOwner::nus);
        }
    }

    BT_CONN_CB_DEFINE(nucode_ble_connection_callbacks) = {
        .connected = connectionEstablished,
        .disconnected = connectionDisconnected,
        .recycled = connectionRecycled,
    };

    /** @brief advertising data에서 exact local name을 찾습니다. */
    bool parseExactName(struct bt_data *data, void *context)
    {
        bool *matched = static_cast<bool *>(context);
        if (data->type != BT_DATA_NAME_COMPLETE && data->type != BT_DATA_NAME_SHORTENED)
        {
            return true;
        }

        k_spinlock_key_t key = k_spin_lock(&scan_lock);
        const std::size_t expected_length = ::strlen(expected_name);
        *matched = data->data_len == expected_length &&
                   ::memcmp(data->data, expected_name, expected_length) == 0;
        k_spin_unlock(&scan_lock, key);
        return !*matched;
    }

    /** @brief scan callback에서는 후보 주소만 복사하고 연결은 poll에 위임합니다. */
    void deviceFound(const bt_addr_le_t *address, std::int8_t rssi,
                     std::uint8_t advertising_type, struct net_buf_simple *data)
    {
        ARG_UNUSED(rssi);
        if (atomic_get(&scanning_value) == 0 ||
            (advertising_type != BT_GAP_ADV_TYPE_ADV_IND &&
             advertising_type != BT_GAP_ADV_TYPE_ADV_DIRECT_IND &&
             advertising_type != BT_GAP_ADV_TYPE_SCAN_RSP))
        {
            return;
        }

        bool matched = false;
        bt_data_parse(data, parseExactName, &matched);
        if (!matched || !atomic_cas(&connect_candidate_value, 0, 1))
        {
            return;
        }
        k_spinlock_key_t key = k_spin_lock(&scan_lock);
        bt_addr_le_copy(&candidate_address, address);
        k_spin_unlock(&scan_lock, key);
    }

    /** @brief Bluetooth stack과 NUS 양쪽 모듈을 한 번만 초기화합니다. */
    int initializeModules() noexcept
    {
        // bt_enable은 M19 공용 once-init 경계에서만 호출합니다.
        const int stack_result = nucode::ble::internal::ensureStack();
        if (stack_result < 0)
        {
            return stack_result;
        }
        if (atomic_get(&modules_initialized) == 0)
        {
            int result = bt_nus_init(&nus_server_callbacks);
            if (result == 0)
            {
                result = bt_nus_client_init(&nus_client, &nus_client_parameters);
            }
            if (result < 0)
            {
                return result;
            }
            atomic_set(&modules_initialized, 1);
        }
        return 0;
    }

    /** @brief 저장한 local name과 NUS UUID로 connectable advertising을 시작합니다. */
    int startPeripheralAdvertising() noexcept
    {
        static const std::uint8_t flags = BT_LE_AD_GENERAL | BT_LE_AD_NO_BREDR;
        static const std::uint8_t nus_uuid[] = {BT_UUID_NUS_VAL};
        const struct bt_data advertising_data[] = {
            BT_DATA(BT_DATA_FLAGS, &flags, sizeof(flags)),
            BT_DATA(BT_DATA_UUID128_ALL, nus_uuid, sizeof(nus_uuid)),
        };
        const struct bt_data scan_response[] = {
            BT_DATA(BT_DATA_NAME_COMPLETE, peripheral_name,
                    static_cast<std::uint8_t>(::strlen(peripheral_name))),
        };
        const int result = bt_le_adv_start(BT_LE_ADV_CONN_FAST_2,
                                           advertising_data, ARRAY_SIZE(advertising_data),
                                           scan_response, ARRAY_SIZE(scan_response));
        if (result == 0)
        {
            atomic_set(&advertising_value, 1);
            queueEvent(Event::advertising_started);
        }
        return result;
    }

    /** @brief 저장한 exact name으로 active scan을 시작합니다. */
    int startCentralScan() noexcept
    {
        atomic_set(&connect_candidate_value, 0);
        const int result = bt_le_scan_start(BT_LE_SCAN_ACTIVE, deviceFound);
        if (result == 0)
        {
            atomic_set(&scanning_value, 1);
            queueEvent(Event::scan_started);
        }
        return result;
    }

    /** @brief poll에서 후보 peer와 BLE connection을 생성합니다. */
    void connectCandidate() noexcept
    {
        if (!atomic_cas(&connect_candidate_value, 1, 0))
        {
            return;
        }
        const int stop_result = bt_le_scan_stop();
        atomic_set(&scanning_value, 0);
        if (stop_result < 0)
        {
            recordError(Error::driver_error, stop_result, true);
            atomic_set(&restart_value, 1);
            return;
        }

        bt_addr_le_t address = {};
        k_spinlock_key_t scan_key = k_spin_lock(&scan_lock);
        bt_addr_le_copy(&address, &candidate_address);
        k_spin_unlock(&scan_lock, scan_key);

        struct bt_conn *connection = nullptr;
        const int result = bt_conn_le_create(&address, BT_CONN_LE_CREATE_CONN,
                                             BT_LE_CONN_PARAM_DEFAULT, &connection);
        if (result < 0)
        {
            recordError(Error::driver_error, result, true);
            atomic_set(&restart_value, 1);
            return;
        }
        k_spinlock_key_t connection_key = k_spin_lock(&connection_lock);
        pending_connection = connection;
        k_spin_unlock(&connection_lock, connection_key);
    }

} // namespace

namespace nucode::ble
{

    bool NusSerial::beginPeripheral(const char *local_name) noexcept
    {
        if (!requireThreadContext() || local_name == nullptr)
        {
            if (local_name == nullptr)
            {
                recordError(Error::invalid_argument, -EINVAL, true);
            }
            return false;
        }
        const std::size_t length = ::strlen(local_name);
        if (length == 0U || length > maximum_local_name)
        {
            recordError(Error::invalid_argument, -EINVAL, true);
            return false;
        }

        k_mutex_lock(&ble_lifecycle_mutex, K_FOREVER);
        if (currentRole() != Role::none)
        {
            k_mutex_unlock(&ble_lifecycle_mutex);
            recordError(Error::already_started, -EALREADY, true);
            return false;
        }
        if (!nucode::ble::internal::claimFacade(
                nucode::ble::internal::FacadeOwner::nus))
        {
            k_mutex_unlock(&ble_lifecycle_mutex);
            recordError(Error::already_started, -EALREADY, true);
            return false;
        }
        int result = initializeModules();
        if (result == 0)
        {
            result = bt_set_name(local_name);
        }
        if (result == 0)
        {
            ::memcpy(peripheral_name, local_name, length + 1U);
            atomic_set(&role_value, static_cast<atomic_val_t>(Role::peripheral));
            atomic_set(&ending_value, 0);
            k_msgq_purge(&ble_rx_queue);
            k_msgq_purge(&ble_event_queue);
            recordError(Error::none);
        }
        k_mutex_unlock(&ble_lifecycle_mutex);
        if (result < 0)
        {
            nucode::ble::internal::releaseFacade(
                nucode::ble::internal::FacadeOwner::nus);
            recordError(Error::driver_error, result, true);
            return false;
        }
        return true;
    }

    bool NusSerial::startAdvertising() noexcept
    {
        if (!requireThreadContext())
        {
            return false;
        }
        if (currentRole() != Role::peripheral)
        {
            recordError(Error::wrong_role, -EPERM, true);
            return false;
        }
        if (atomic_get(&connected_value) != 0 || atomic_get(&advertising_value) != 0)
        {
            recordError(Error::busy, -EBUSY, true);
            return false;
        }
        atomic_set(&auto_restart_value, 1);
        const int result = startPeripheralAdvertising();
        if (result < 0)
        {
            recordError(Error::driver_error, result, true);
            return false;
        }
        recordError(Error::none);
        return true;
    }

    bool NusSerial::beginCentral() noexcept
    {
        if (!requireThreadContext())
        {
            return false;
        }
        k_mutex_lock(&ble_lifecycle_mutex, K_FOREVER);
        if (currentRole() != Role::none)
        {
            k_mutex_unlock(&ble_lifecycle_mutex);
            recordError(Error::already_started, -EALREADY, true);
            return false;
        }
        if (!nucode::ble::internal::claimFacade(
                nucode::ble::internal::FacadeOwner::nus))
        {
            k_mutex_unlock(&ble_lifecycle_mutex);
            recordError(Error::already_started, -EALREADY, true);
            return false;
        }
        const int result = initializeModules();
        if (result == 0)
        {
            atomic_set(&role_value, static_cast<atomic_val_t>(Role::central));
            atomic_set(&ending_value, 0);
            k_msgq_purge(&ble_rx_queue);
            k_msgq_purge(&ble_event_queue);
            recordError(Error::none);
        }
        k_mutex_unlock(&ble_lifecycle_mutex);
        if (result < 0)
        {
            nucode::ble::internal::releaseFacade(
                nucode::ble::internal::FacadeOwner::nus);
            recordError(Error::driver_error, result, true);
            return false;
        }
        return true;
    }

    bool NusSerial::scanForNus(const char *exact_name) noexcept
    {
        if (!requireThreadContext() || exact_name == nullptr)
        {
            if (exact_name == nullptr)
            {
                recordError(Error::invalid_argument, -EINVAL, true);
            }
            return false;
        }
        const std::size_t length = ::strlen(exact_name);
        if (length == 0U || length > maximum_local_name)
        {
            recordError(Error::invalid_argument, -EINVAL, true);
            return false;
        }
        if (currentRole() != Role::central)
        {
            recordError(Error::wrong_role, -EPERM, true);
            return false;
        }
        if (atomic_get(&connected_value) != 0 || atomic_get(&scanning_value) != 0)
        {
            recordError(Error::busy, -EBUSY, true);
            return false;
        }
        k_spinlock_key_t key = k_spin_lock(&scan_lock);
        ::memcpy(expected_name, exact_name, length + 1U);
        k_spin_unlock(&scan_lock, key);
        atomic_set(&auto_restart_value, 1);
        const int result = startCentralScan();
        if (result < 0)
        {
            recordError(Error::driver_error, result, true);
            return false;
        }
        recordError(Error::none);
        return true;
    }

    void NusSerial::poll() noexcept
    {
        if (!requireThreadContext())
        {
            return;
        }
        connectCandidate();
        if (atomic_cas(&restart_value, 1, 0) && atomic_get(&auto_restart_value) != 0 &&
            atomic_get(&ending_value) == 0 && atomic_get(&connected_value) == 0)
        {
            const int result = currentRole() == Role::peripheral
                                   ? startPeripheralAdvertising()
                                   : (currentRole() == Role::central ? startCentralScan() : -EPERM);
            if (result < 0)
            {
                recordError(Error::driver_error, result, true);
            }
        }

        Event event = Event::error;
        while (k_msgq_get(&ble_event_queue, &event, K_NO_WAIT) == 0)
        {
            if (event == Event::received)
            {
                atomic_set(&receive_event_pending, 0);
            }
            EventCallback callback = event_callback;
            if (callback != nullptr)
            {
                callback(event, event_context);
            }
        }
    }

    bool NusSerial::connected() const noexcept
    {
        return atomic_get(&connected_value) != 0;
    }

    bool NusSerial::ready() const noexcept
    {
        return atomic_get(&ready_value) != 0;
    }

    bool NusSerial::disconnect() noexcept
    {
        if (!requireThreadContext())
        {
            return false;
        }
        struct bt_conn *connection = referenceActiveConnection();
        if (connection == nullptr)
        {
            recordError(Error::not_connected, -ENOTCONN, true);
            return false;
        }
        const int result = bt_conn_disconnect(connection, BT_HCI_ERR_REMOTE_USER_TERM_CONN);
        bt_conn_unref(connection);
        if (result < 0)
        {
            recordError(Error::driver_error, result, true);
            return false;
        }
        recordError(Error::none);
        return true;
    }

    void NusSerial::end() noexcept
    {
        if (!requireThreadContext())
        {
            return;
        }
        atomic_set(&auto_restart_value, 0);
        atomic_set(&ending_value, 1);
        if (atomic_cas(&advertising_value, 1, 0))
        {
            static_cast<void>(bt_le_adv_stop());
        }
        if (atomic_cas(&scanning_value, 1, 0))
        {
            static_cast<void>(bt_le_scan_stop());
        }
        struct bt_conn *pending = nullptr;
        k_spinlock_key_t key = k_spin_lock(&connection_lock);
        pending = pending_connection;
        pending_connection = nullptr;
        k_spin_unlock(&connection_lock, key);
        const bool wait_for_pending_recycle = pending != nullptr;
        if (pending != nullptr)
        {
            static_cast<void>(bt_conn_disconnect(
                pending, BT_HCI_ERR_REMOTE_USER_TERM_CONN));
            bt_conn_unref(pending);
        }
        struct bt_conn *connection = referenceActiveConnection();
        if (connection != nullptr)
        {
            static_cast<void>(bt_conn_disconnect(connection, BT_HCI_ERR_REMOTE_USER_TERM_CONN));
            bt_conn_unref(connection);
        }
        else if (!wait_for_pending_recycle)
        {
            atomic_set(&role_value, static_cast<atomic_val_t>(Role::none));
            atomic_set(&ending_value, 0);
            nucode::ble::internal::releaseFacade(
                nucode::ble::internal::FacadeOwner::nus);
        }
        atomic_set(&ready_value, 0);
    }

    void NusSerial::onEvent(EventCallback callback, void *context) noexcept
    {
        if (!requireThreadContext())
        {
            return;
        }
        event_callback = callback;
        event_context = context;
    }

    std::size_t NusSerial::mtu() const noexcept
    {
        struct bt_conn *connection = referenceActiveConnection();
        if (connection == nullptr)
        {
            return 0U;
        }
        const std::size_t payload = bt_nus_get_mtu(connection);
        bt_conn_unref(connection);
        return smaller(payload, maximum_tx_payload);
    }

    std::uint32_t NusSerial::droppedRxBytes() const noexcept
    {
        return static_cast<std::uint32_t>(atomic_get(&dropped_rx_value));
    }

    Error NusSerial::lastError() const noexcept
    {
        return static_cast<Error>(atomic_get(&last_error_value));
    }

    int NusSerial::lastDriverError() const noexcept
    {
        return static_cast<int>(atomic_get(&last_driver_error_value));
    }

    int NusSerial::available()
    {
        return static_cast<int>(k_msgq_num_used_get(&ble_rx_queue));
    }

    int NusSerial::read()
    {
        std::uint8_t value = 0U;
        return k_msgq_get(&ble_rx_queue, &value, K_NO_WAIT) == 0 ? value : -1;
    }

    int NusSerial::peek()
    {
        std::uint8_t value = 0U;
        return k_msgq_peek(&ble_rx_queue, &value) == 0 ? value : -1;
    }

    void NusSerial::flush()
    {
        if (!requireThreadContext())
        {
            return;
        }
        k_mutex_lock(&ble_tx_mutex, K_FOREVER);
        k_mutex_unlock(&ble_tx_mutex);
    }

    int NusSerial::availableForWrite()
    {
        return ready() ? static_cast<int>(mtu()) : 0;
    }

    std::size_t NusSerial::write(std::uint8_t value)
    {
        return write(&value, 1U);
    }

    std::size_t NusSerial::write(const std::uint8_t *buffer, std::size_t size)
    {
        if (!requireThreadContext() || buffer == nullptr)
        {
            if (buffer == nullptr && size != 0U)
            {
                recordError(Error::invalid_argument, -EINVAL, true);
            }
            return 0U;
        }
        if (size == 0U)
        {
            return 0U;
        }
        if (!connected())
        {
            recordError(Error::not_connected, -ENOTCONN, true);
            return 0U;
        }
        if (!ready())
        {
            recordError(Error::not_ready, -EAGAIN, true);
            return 0U;
        }

        k_mutex_lock(&ble_tx_mutex, K_FOREVER);
        std::uint8_t tx_buffer[maximum_tx_payload] = {};
        std::size_t sent = 0U;
        while (sent < size)
        {
            struct bt_conn *connection = referenceActiveConnection();
            if (connection == nullptr)
            {
                recordError(Error::not_connected, -ENOTCONN, true);
                break;
            }
            const std::size_t chunk = smaller(
                smaller(size - sent, static_cast<std::size_t>(bt_nus_get_mtu(connection))),
                maximum_tx_payload);
            ::memcpy(tx_buffer, buffer + sent, chunk);
            k_sem_reset(&ble_tx_complete);
            atomic_set(&tx_result_value, 0);
            const int result = currentRole() == Role::peripheral
                                   ? bt_nus_send(connection, tx_buffer,
                                                 static_cast<std::uint16_t>(chunk))
                                   : bt_nus_client_send(&nus_client, tx_buffer,
                                                        static_cast<std::uint16_t>(chunk));
            bt_conn_unref(connection);
            if (result < 0)
            {
                recordError(result == -EALREADY ? Error::busy : Error::driver_error,
                            result, true);
                break;
            }
            if (k_sem_take(&ble_tx_complete, K_SECONDS(5)) != 0)
            {
                recordError(Error::timeout, -ETIMEDOUT, true);
                break;
            }
            const int completion = static_cast<int>(atomic_get(&tx_result_value));
            if (completion != 0)
            {
                recordError(Error::driver_error, -completion, true);
                break;
            }
            sent += chunk;
        }
        k_mutex_unlock(&ble_tx_mutex);
        if (sent == size)
        {
            recordError(Error::none);
        }
        return sent;
    }

} // namespace nucode::ble

nucode::ble::NusSerial BLESerial;

#endif
