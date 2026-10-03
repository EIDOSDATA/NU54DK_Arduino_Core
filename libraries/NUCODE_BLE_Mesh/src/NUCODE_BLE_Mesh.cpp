/**
 * @file NUCODE_BLE_Mesh.cpp
 * @brief Zephyr Bluetooth Mesh를 bounded Arduino lifecycle로 구현합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#if !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE)

#include <NUCODE_BLE_Mesh.h>

#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/mesh.h>
#include <zephyr/bluetooth/mesh/cdb.h>
#include <zephyr/bluetooth/mesh/cfg.h>
#include <zephyr/bluetooth/mesh/cfg_cli.h>
#include <zephyr/bluetooth/mesh/health_cli.h>
#include <zephyr/settings/settings.h>
#include <zephyr/sys/atomic.h>
#include <zephyr/sys/byteorder.h>

#include <errno.h>
#include <string.h>

/** @brief NUCODE BLE Core가 함께 링크됐을 때 settings one-shot 상태를 공유합니다. */
extern "C" void nucode_ble_note_settings_loaded(int result) __attribute__((weak));

#if !defined(CONFIG_NUCODE_BLE_MESH_EVENT_QUEUE_SIZE)
#define CONFIG_NUCODE_BLE_MESH_EVENT_QUEUE_SIZE 16
#endif

namespace nucode::mesh
{
    extern "C"
    {
        const struct bt_mesh_comp *nucode_mesh_composition(void);
        const struct bt_mesh_model *nucode_mesh_model(std::uint8_t model);
        struct bt_mesh_health_cli *nucode_mesh_health_client(void);
        int nucode_mesh_onoff_server_set(bool enabled, bool publish);
        bool nucode_mesh_onoff_server_get(void);
    }

    namespace
    {
        constexpr std::uint32_t on_off_set_opcode = BT_MESH_MODEL_OP_2(0x82, 0x02);
        constexpr std::uint32_t on_off_set_unack_opcode = BT_MESH_MODEL_OP_2(0x82, 0x03);
        constexpr std::uint32_t level_set_opcode = BT_MESH_MODEL_OP_2(0x82, 0x06);
        constexpr std::uint32_t level_set_unack_opcode = BT_MESH_MODEL_OP_2(0x82, 0x07);
        constexpr std::uint32_t lightness_set_opcode = BT_MESH_MODEL_OP_2(0x82, 0x4C);
        constexpr std::uint32_t lightness_set_unack_opcode = BT_MESH_MODEL_OP_2(0x82, 0x4D);
        constexpr std::uint32_t sensor_get_opcode = BT_MESH_MODEL_OP_2(0x82, 0x31);
        constexpr std::uint32_t time_get_opcode = BT_MESH_MODEL_OP_2(0x82, 0x37);
        constexpr std::uint32_t scene_recall_opcode = BT_MESH_MODEL_OP_2(0x82, 0x42);
        constexpr std::uint32_t scene_recall_unack_opcode = BT_MESH_MODEL_OP_2(0x82, 0x43);
        constexpr std::uint32_t scheduler_get_opcode = BT_MESH_MODEL_OP_2(0x82, 0x49);

#if !defined(CONFIG_BT_MESH_PROXY_SOLICITATION) || \
    !defined(CONFIG_BT_MESH_OD_PRIV_PROXY_SRV)
        /** @brief 비활성 선택 기능이 남긴 settings 값을 안전하게 소비합니다. */
        int loadDisabledOptionalSetting(const char *, std::size_t,
                                        settings_read_cb, void *) noexcept
        {
            return 0;
        }
#endif

#if !defined(CONFIG_BT_MESH_PROXY_SOLICITATION)
        SETTINGS_STATIC_HANDLER_DEFINE(nucode_mesh_sseq_compat,
                                       "bt/mesh/SSeq", NULL,
                                       loadDisabledOptionalSetting, NULL, NULL);
#endif

#if !defined(CONFIG_BT_MESH_OD_PRIV_PROXY_SRV)
        SETTINGS_STATIC_HANDLER_DEFINE(nucode_mesh_srpl_compat,
                                       "bt/mesh/SRPL", NULL,
                                       loadDisabledOptionalSetting, NULL, NULL);
#endif

        struct Context
        {
            atomic_t started = ATOMIC_INIT(0);
            atomic_t dropped_events = ATOMIC_INIT(0);
            struct k_spinlock callback_lock;
            Configuration configuration{};
            EventCallback callback = nullptr;
            void *callback_context = nullptr;
            Error error = Error::none;
            int driver_error = 0;
            std::uint8_t configuration_status = 0U;
            std::uint8_t transaction_id = 0U;
        };

        K_MSGQ_DEFINE(event_queue, sizeof(EventRecord),
                      CONFIG_NUCODE_BLE_MESH_EVENT_QUEUE_SIZE, alignof(EventRecord));

        Context mesh_context{};

        void setError(Error error, int driver_error = 0) noexcept
        {
            mesh_context.error = error;
            mesh_context.driver_error = driver_error;
        }

        void queueEvent(const EventRecord &record) noexcept
        {
            if (k_msgq_put(&event_queue, &record, K_NO_WAIT) != 0)
            {
                atomic_inc(&mesh_context.dropped_events);
                setError(Error::event_overflow, -ENOBUFS);
            }
        }

        Bearer publicBearer(bt_mesh_prov_bearer_t bearer) noexcept
        {
            if ((bearer & BT_MESH_PROV_GATT) != 0U)
            {
                return Bearer::gatt;
            }
            return Bearer::advertising;
        }

        bt_mesh_prov_bearer_t nativeBearers(Bearer bearer) noexcept
        {
            std::uint8_t value = 0U;
            if ((static_cast<std::uint8_t>(bearer) &
                 static_cast<std::uint8_t>(Bearer::advertising)) != 0U)
            {
                value |= BT_MESH_PROV_ADV;
            }
            if ((static_cast<std::uint8_t>(bearer) &
                 static_cast<std::uint8_t>(Bearer::gatt)) != 0U)
            {
                value |= BT_MESH_PROV_GATT;
            }
            return static_cast<bt_mesh_prov_bearer_t>(value);
        }

        Model publicModel(const struct bt_mesh_model *model) noexcept
        {
            switch (model->id)
            {
                case BT_MESH_MODEL_ID_GEN_LEVEL_CLI:
                    return Model::generic_level;
                case BT_MESH_MODEL_ID_LIGHT_LIGHTNESS_CLI:
                    return Model::light_lightness;
                case BT_MESH_MODEL_ID_SENSOR_CLI:
                    return Model::sensor;
                case BT_MESH_MODEL_ID_TIME_CLI:
                    return Model::time;
                case BT_MESH_MODEL_ID_SCENE_CLI:
                    return Model::scene;
                case BT_MESH_MODEL_ID_SCHEDULER_CLI:
                    return Model::scheduler;
                case BT_MESH_MODEL_ID_GEN_ONOFF_CLI:
                    return Model::generic_on_off;
                case BT_MESH_MODEL_ID_GEN_ONOFF_SRV:
                    return Model::generic_on_off_server;
#if defined(CONFIG_NUCODE_BLE_MESH_UPDATE)
                case BT_MESH_MODEL_ID_BLOB_CLI:
                    return Model::blob_client;
                case BT_MESH_MODEL_ID_BLOB_SRV:
                    return Model::blob_server;
                case BT_MESH_MODEL_ID_DFU_SRV:
                    return Model::mesh_dfu_target;
                case BT_MESH_MODEL_ID_DFD_SRV:
                    return Model::firmware_distributor;
#endif
                default:
                    return Model::generic_on_off;
            }
        }

        void unprovisionedBeacon(std::uint8_t uuid[16], bt_mesh_prov_oob_info_t,
                                 std::uint32_t *)
        {
            EventRecord record{};
            record.event = Event::unprovisioned_device;
            record.bearer = Bearer::advertising;
            memcpy(record.uuid, uuid, sizeof(record.uuid));
            queueEvent(record);
        }

        void unprovisionedBeaconGatt(std::uint8_t uuid[16], bt_mesh_prov_oob_info_t)
        {
            EventRecord record{};
            record.event = Event::unprovisioned_device;
            record.bearer = Bearer::gatt;
            memcpy(record.uuid, uuid, sizeof(record.uuid));
            queueEvent(record);
        }

        void linkOpen(bt_mesh_prov_bearer_t bearer)
        {
            EventRecord record{};
            record.event = Event::provisioning_link_opened;
            record.bearer = publicBearer(bearer);
            queueEvent(record);
        }

        void linkClose(bt_mesh_prov_bearer_t bearer)
        {
            EventRecord record{};
            record.event = Event::provisioning_link_closed;
            record.bearer = publicBearer(bearer);
            queueEvent(record);
        }

        void provisioningComplete(std::uint16_t net_key_index, std::uint16_t address)
        {
            EventRecord record{};
            record.event = Event::provisioned;
            record.net_key_index = net_key_index;
            record.address = address;
            queueEvent(record);
        }

        void nodeAdded(std::uint16_t net_key_index, std::uint8_t uuid[16],
                       std::uint16_t address, std::uint8_t element_count)
        {
            EventRecord record{};
            record.event = Event::node_added;
            record.net_key_index = net_key_index;
            record.address = address;
            record.element_count = element_count;
            memcpy(record.uuid, uuid, sizeof(record.uuid));
            queueEvent(record);
        }

        void meshReset()
        {
            EventRecord record{};
            record.event = Event::reset;
            queueEvent(record);
        }

        struct bt_mesh_prov provisioning{};

        bool validDestination(const Destination &destination) noexcept
        {
            return destination.address != BT_MESH_ADDR_UNASSIGNED &&
                   destination.address != BT_MESH_ADDR_ALL_NODES &&
                   destination.ttl <= BT_MESH_TTL_MAX;
        }

        bool validUnicastAddress(std::uint16_t address) noexcept
        {
            return address != BT_MESH_ADDR_UNASSIGNED && address < 0x8000U;
        }

        bool readyProvisioner() noexcept
        {
            if (atomic_get(&mesh_context.started) == 0)
            {
                setError(Error::not_started);
                return false;
            }
            if (!bt_mesh_is_provisioned())
            {
                setError(Error::not_provisioned);
                return false;
            }
            if (mesh_context.configuration.role != Role::provisioner)
            {
                setError(Error::invalid_context);
                return false;
            }
            return true;
        }

        bool finishConfiguration(int error, std::uint8_t status) noexcept
        {
            mesh_context.configuration_status = status;
            if (error != 0)
            {
                setError(error == -EBUSY ? Error::busy : Error::driver_error, error);
                return false;
            }
            if (status != 0U)
            {
                setError(Error::driver_error, -EREMOTE);
                return false;
            }
            setError(Error::none);
            return true;
        }

        /**
         * @brief local model에 application key를 직접 bind합니다.
         *
         * Config Client 전송 경로는 자기 자신을 대상으로 한 access message를
         * loopback하지 않으므로 local provisioner model은 공개 model key slot을
         * 직접 갱신합니다. begin 이후 매번 호출되는 구성 단계에서 적용되며,
         * 이미 같은 key가 bind된 경우에도 성공으로 처리합니다.
         */
        bool bindLocalModel(const struct bt_mesh_model *model,
                            std::uint16_t app_key_index) noexcept
        {
            constexpr std::uint8_t invalid_app_key_status = 0x03U;
            constexpr std::uint8_t insufficient_resources_status = 0x05U;

            if (!bt_mesh_app_key_exists(app_key_index))
            {
                return finishConfiguration(0, invalid_app_key_status);
            }
            for (std::size_t index = 0U; index < model->keys_cnt; ++index)
            {
                if (model->keys[index] == app_key_index)
                {
                    return finishConfiguration(0, 0U);
                }
            }
            for (std::size_t index = 0U; index < model->keys_cnt; ++index)
            {
                if (model->keys[index] == BT_MESH_KEY_UNUSED)
                {
                    model->keys[index] = app_key_index;
                    return finishConfiguration(0, 0U);
                }
            }
            return finishConfiguration(0, insufficient_resources_status);
        }

        bool encodePublicationPeriod(std::uint32_t milliseconds,
                                     std::uint8_t &period) noexcept
        {
            if (milliseconds == 0U)
            {
                period = 0U;
                return true;
            }
            if (milliseconds % 100U == 0U && milliseconds / 100U <= 63U)
            {
                period = BT_MESH_PUB_PERIOD_100MS(milliseconds / 100U);
                return true;
            }
            if (milliseconds % 1000U == 0U && milliseconds / 1000U <= 63U)
            {
                period = BT_MESH_PUB_PERIOD_SEC(milliseconds / 1000U);
                return true;
            }
            if (milliseconds % 10000U == 0U && milliseconds / 10000U <= 63U)
            {
                period = BT_MESH_PUB_PERIOD_10SEC(milliseconds / 10000U);
                return true;
            }
            if (milliseconds % 600000U == 0U && milliseconds / 600000U <= 63U)
            {
                period = BT_MESH_PUB_PERIOD_10MIN(milliseconds / 600000U);
                return true;
            }
            return false;
        }

        const struct bt_mesh_model *modelFor(Model model) noexcept
        {
            return nucode_mesh_model(static_cast<std::uint8_t>(model));
        }

        bool send(Model model, const Destination &destination, std::uint32_t opcode,
                  const std::uint8_t *payload, std::size_t payload_size) noexcept
        {
            if (atomic_get(&mesh_context.started) == 0)
            {
                setError(Error::not_started);
                return false;
            }
            if (!bt_mesh_is_provisioned())
            {
                setError(Error::not_provisioned);
                return false;
            }
            if (!validDestination(destination) || payload_size > 12U)
            {
                setError(Error::invalid_argument);
                return false;
            }

            NET_BUF_SIMPLE_DEFINE(message, BT_MESH_MODEL_BUF_LEN(BT_MESH_MODEL_OP_2(0x82, 0x01),
                                                                  12));
            bt_mesh_model_msg_init(&message, opcode);
            if (payload_size != 0U)
            {
                net_buf_simple_add_mem(&message, payload, payload_size);
            }

            struct bt_mesh_msg_ctx native_context{};
            native_context.net_idx = destination.net_key_index;
            native_context.app_idx = destination.app_key_index;
            native_context.addr = destination.address;
            native_context.send_ttl = destination.ttl;
            native_context.send_rel = destination.force_segment_acknowledgment;
            const int error = bt_mesh_model_send(modelFor(model), &native_context, &message,
                                                 nullptr, nullptr);
            if (error != 0)
            {
                setError(error == -EBUSY ? Error::busy : Error::driver_error, error);
                return false;
            }
            setError(Error::none);
            return true;
        }

        bool initializeProvisioner(const Configuration &configuration) noexcept
        {
            std::uint8_t network_key[16]{};
            std::uint8_t device_key[16]{};
            int error = bt_rand(network_key, sizeof(network_key));
            if (error != 0)
            {
                setError(Error::driver_error, error);
                return false;
            }
            error = bt_mesh_cdb_create(network_key);
            if (error == -EALREADY &&
                bt_mesh_cdb_subnet_get(BT_MESH_NET_PRIMARY) == nullptr)
            {
                bt_mesh_cdb_clear();
                error = bt_mesh_cdb_create(network_key);
            }
            if (error != 0 && error != -EALREADY)
            {
                setError(Error::driver_error, error);
                return false;
            }
            if (bt_mesh_is_provisioned())
            {
                return true;
            }
            error = bt_rand(device_key, sizeof(device_key));
            if (error == 0)
            {
                error = bt_mesh_provision(network_key, BT_MESH_NET_PRIMARY, 0U, 0U,
                                          configuration.local_address, device_key);
            }
            if (error != 0 && error != -EALREADY)
            {
                setError(Error::driver_error, error);
                return false;
            }
            return true;
        }

        /**
         * @brief 일반 node 역할에 남은 provisioner CDB를 제거합니다.
         *
         * 동일 보드가 provisioner image에서 node image로 역할을 바꾸면 sector flash 뒤에도
         * CDB settings가 유지될 수 있습니다. 이 CDB는 일반 node의 network 상태와 별개이며,
         * 남겨 두면 새 provisioning 주소와 충돌해 local provisioning 완료가 거부됩니다.
         */
        void clearInactiveProvisionerDatabase() noexcept
        {
            if (atomic_test_bit(bt_mesh_cdb.flags, BT_MESH_CDB_VALID))
            {
                bt_mesh_cdb_clear();
            }
        }

    } // namespace

    /** @brief C composition handler가 전달한 status를 bounded event queue에 복사합니다. */
    extern "C" int nucode_mesh_model_status(const struct bt_mesh_model *model,
                                             struct bt_mesh_msg_ctx *message_context,
                                             struct net_buf_simple *buffer)
    {
        EventRecord record{};
        record.event = Event::model_status;
        record.model = publicModel(model);
        record.address = message_context->addr;
        const std::size_t available = buffer->len;
        const std::size_t copied = available < EventRecord::payload_capacity ?
                                       available : EventRecord::payload_capacity;
        record.payload_size = static_cast<std::uint8_t>(copied);
        record.payload_truncated = available > copied;
        if (copied != 0U)
        {
            memcpy(record.payload, buffer->data, copied);
        }
        queueEvent(record);
        return 0;
    }

    bool MeshDevice::begin(const Configuration &configuration) noexcept
    {
        if (atomic_cas(&mesh_context.started, 0, 1) == 0)
        {
            setError(Error::already_started);
            return false;
        }
        if (configuration.local_address == 0U || configuration.local_address >= 0x8000U ||
            nativeBearers(configuration.bearers) == 0U)
        {
            atomic_set(&mesh_context.started, 0);
            setError(Error::invalid_argument);
            return false;
        }

        mesh_context.configuration = configuration;
        provisioning = {};
        provisioning.uuid = mesh_context.configuration.uuid;
        provisioning.unprovisioned_beacon = unprovisionedBeacon;
        provisioning.unprovisioned_beacon_gatt = unprovisionedBeaconGatt;
        provisioning.link_open = linkOpen;
        provisioning.link_close = linkClose;
        provisioning.complete = provisioningComplete;
        provisioning.node_added = nodeAdded;
        provisioning.reset = meshReset;

        int error = bt_enable(nullptr);
        if (error != 0 && error != -EALREADY)
        {
            atomic_set(&mesh_context.started, 0);
            setError(Error::driver_error, error);
            return false;
        }
        error = bt_mesh_init(&provisioning, nucode_mesh_composition());
        if (error != 0)
        {
            atomic_set(&mesh_context.started, 0);
            setError(Error::driver_error, error);
            return false;
        }
        error = settings_load();
        if (nucode_ble_note_settings_loaded != nullptr)
        {
            nucode_ble_note_settings_loaded(error);
        }
        if (error != 0)
        {
            atomic_set(&mesh_context.started, 0);
            setError(Error::driver_error, error);
            return false;
        }

        if (configuration.role == Role::provisioner)
        {
            if (!initializeProvisioner(configuration))
            {
                atomic_set(&mesh_context.started, 0);
                return false;
            }
            error = bt_mesh_prov_enable(nativeBearers(configuration.bearers));
            if (error != 0 && error != -EALREADY)
            {
                atomic_set(&mesh_context.started, 0);
                setError(Error::driver_error, error);
                return false;
            }
        }
        else
        {
            clearInactiveProvisionerDatabase();
            if (!bt_mesh_is_provisioned())
            {
                error = bt_mesh_prov_enable(nativeBearers(configuration.bearers));
                if (error != 0 && error != -EALREADY)
                {
                    atomic_set(&mesh_context.started, 0);
                    setError(Error::driver_error, error);
                    return false;
                }
            }
        }

        EventRecord record{};
        record.event = Event::initialized;
        queueEvent(record);
        setError(Error::none);
        return true;
    }

    void MeshDevice::poll() noexcept
    {
        EventRecord record{};
        while (k_msgq_get(&event_queue, &record, K_NO_WAIT) == 0)
        {
            k_spinlock_key_t key = k_spin_lock(&mesh_context.callback_lock);
            EventCallback callback = mesh_context.callback;
            void *context = mesh_context.callback_context;
            k_spin_unlock(&mesh_context.callback_lock, key);
            if (callback != nullptr)
            {
                callback(record, context);
            }
        }
    }

    void MeshDevice::onEvent(EventCallback callback, void *context) noexcept
    {
        k_spinlock_key_t key = k_spin_lock(&mesh_context.callback_lock);
        mesh_context.callback = callback;
        mesh_context.callback_context = context;
        k_spin_unlock(&mesh_context.callback_lock, key);
    }

    bool MeshDevice::enableProvisioning(Bearer bearers) noexcept
    {
        if (atomic_get(&mesh_context.started) == 0)
        {
            setError(Error::not_started);
            return false;
        }
        const bt_mesh_prov_bearer_t native = nativeBearers(bearers);
        if (native == 0U)
        {
            setError(Error::invalid_argument);
            return false;
        }
        const int error = bt_mesh_prov_enable(native);
        if (error != 0 && error != -EALREADY)
        {
            setError(Error::driver_error, error);
            return false;
        }
        setError(Error::none);
        return true;
    }

    bool MeshDevice::cancelProvisioning() noexcept
    {
        if (atomic_get(&mesh_context.started) == 0)
        {
            setError(Error::not_started);
            return false;
        }
        const int error = bt_mesh_prov_disable(nativeBearers(mesh_context.configuration.bearers));
        if (error != 0 && error != -EALREADY)
        {
            setError(Error::driver_error, error);
            return false;
        }
        setError(Error::none);
        return true;
    }

    bool MeshDevice::provision(const std::uint8_t uuid[16], Bearer bearer,
                               std::uint16_t address) noexcept
    {
        if (atomic_get(&mesh_context.started) == 0)
        {
            setError(Error::not_started);
            return false;
        }
        if (mesh_context.configuration.role != Role::provisioner || uuid == nullptr ||
            (address != 0U && address >= 0x8000U))
        {
            setError(Error::invalid_context);
            return false;
        }

        int error = -ENOTSUP;
        if (bearer == Bearer::advertising)
        {
            error = bt_mesh_provision_adv(uuid, BT_MESH_NET_PRIMARY, address, 0U);
        }
        else if (bearer == Bearer::gatt)
        {
            error = bt_mesh_provision_gatt(uuid, BT_MESH_NET_PRIMARY, address, 0U);
        }
        else
        {
            setError(Error::invalid_argument);
            return false;
        }
        if (error != 0)
        {
            setError(error == -EBUSY ? Error::busy : Error::driver_error, error);
            return false;
        }
        setError(Error::none);
        return true;
    }

    bool MeshDevice::reset() noexcept
    {
        if (atomic_get(&mesh_context.started) == 0)
        {
            setError(Error::not_started);
            return false;
        }
        bt_mesh_reset();
        if (mesh_context.configuration.role == Role::provisioner)
        {
            bt_mesh_cdb_clear();
            if (!initializeProvisioner(mesh_context.configuration))
            {
                return false;
            }
        }
        else
        {
            clearInactiveProvisionerDatabase();
        }
        const int error = bt_mesh_prov_enable(nativeBearers(mesh_context.configuration.bearers));
        if (error != 0 && error != -EALREADY)
        {
            setError(Error::driver_error, error);
            return false;
        }
        setError(Error::none);
        return true;
    }

    bool MeshDevice::provisioned() const noexcept
    {
        return atomic_get(&mesh_context.started) != 0 && bt_mesh_is_provisioned();
    }

    bool MeshDevice::setFeature(Feature feature, bool enabled) noexcept
    {
        if (atomic_get(&mesh_context.started) == 0)
        {
            setError(Error::not_started);
            return false;
        }

        int error = -ENOTSUP;
        const enum bt_mesh_feat_state state = enabled ? BT_MESH_FEATURE_ENABLED :
                                                        BT_MESH_FEATURE_DISABLED;
        switch (feature)
        {
            case Feature::relay:
                error = bt_mesh_relay_set(state, BT_MESH_TRANSMIT(2, 20));
                break;
            case Feature::friend_node:
                error = bt_mesh_friend_set(state);
                break;
            case Feature::low_power_node:
                error = bt_mesh_lpn_set(enabled);
                break;
            case Feature::gatt_proxy:
                error = bt_mesh_gatt_proxy_set(state);
                break;
        }
        if (error != 0)
        {
            setError(error == -ENOTSUP ? Error::unsupported : Error::driver_error, error);
            return false;
        }
        setError(Error::none);
        return true;
    }

    bool MeshDevice::pollFriend() noexcept
    {
        const int error = bt_mesh_lpn_poll();
        if (error != 0)
        {
            setError(error == -ENOTSUP ? Error::unsupported : Error::driver_error, error);
            return false;
        }
        setError(Error::none);
        return true;
    }

    bool MeshDevice::configureAppKey(std::uint16_t node_address,
                                     const std::uint8_t app_key[16],
                                     std::uint16_t app_key_index,
                                     std::uint16_t net_key_index) noexcept
    {
        if (!readyProvisioner())
        {
            return false;
        }
        if (!validUnicastAddress(node_address) || app_key == nullptr ||
            app_key_index > 0x0FFFU || net_key_index > 0x0FFFU)
        {
            setError(Error::invalid_argument);
            return false;
        }
        const std::uint8_t local_status = bt_mesh_app_key_add(app_key_index, net_key_index,
                                                              app_key);
        if (local_status != 0U)
        {
            return finishConfiguration(0, local_status);
        }
        if (node_address == mesh_context.configuration.local_address)
        {
            return finishConfiguration(0, 0U);
        }
        std::uint8_t status = 0U;
        const int error = bt_mesh_cfg_cli_app_key_add(net_key_index, node_address,
                                                      net_key_index, app_key_index,
                                                      app_key, &status);
        return finishConfiguration(error, status);
    }

    bool MeshDevice::updateKeys(std::uint16_t node_address,
                                const std::uint8_t net_key[16],
                                const std::uint8_t app_key[16],
                                std::uint16_t app_key_index,
                                std::uint16_t net_key_index) noexcept
    {
        if (!readyProvisioner())
        {
            return false;
        }
        if (!validUnicastAddress(node_address) || net_key == nullptr || app_key == nullptr ||
            app_key_index > 0x0FFFU || net_key_index > 0x0FFFU)
        {
            setError(Error::invalid_argument);
            return false;
        }

        std::uint8_t status = bt_mesh_subnet_update(net_key_index, net_key);
        if (status == 0U)
        {
            status = bt_mesh_app_key_update(app_key_index, net_key_index, app_key);
        }
        if (status != 0U)
        {
            return finishConfiguration(0, status);
        }

        int error = bt_mesh_cfg_cli_net_key_update(net_key_index, node_address,
                                                   net_key_index, net_key, &status);
        if (error != 0 || status != 0U)
        {
            return finishConfiguration(error, status);
        }
        error = bt_mesh_cfg_cli_app_key_update(net_key_index, node_address,
                                               net_key_index, app_key_index,
                                               app_key, &status);
        return finishConfiguration(error, status);
    }

    bool MeshDevice::transitionKeyRefresh(std::uint16_t node_address,
                                          KeyRefreshTransition transition,
                                          std::uint16_t net_key_index) noexcept
    {
        if (!readyProvisioner())
        {
            return false;
        }
        if (!validUnicastAddress(node_address) || net_key_index > 0x0FFFU)
        {
            setError(Error::invalid_argument);
            return false;
        }

        std::uint8_t status = 0U;
        std::uint8_t phase = static_cast<std::uint8_t>(transition);
        const int error = bt_mesh_cfg_cli_krp_set(net_key_index, node_address,
                                                  net_key_index, phase,
                                                  &status, &phase);
        if (!finishConfiguration(error, status))
        {
            return false;
        }
        status = bt_mesh_subnet_kr_phase_set(net_key_index, &phase);
        return finishConfiguration(0, status);
    }

    bool MeshDevice::bindModel(std::uint16_t node_address,
                               std::uint16_t element_address, Model model,
                               std::uint16_t app_key_index,
                               std::uint16_t net_key_index) noexcept
    {
        if (!readyProvisioner())
        {
            return false;
        }
        const struct bt_mesh_model *native_model = modelFor(model);
        if (!validUnicastAddress(node_address) || !validUnicastAddress(element_address) ||
            native_model == nullptr || app_key_index > 0x0FFFU || net_key_index > 0x0FFFU)
        {
            setError(Error::invalid_argument);
            return false;
        }
        if (node_address == mesh_context.configuration.local_address)
        {
            const struct bt_mesh_elem *native_element = bt_mesh_model_elem(native_model);
            if (native_element == nullptr || native_element->rt == nullptr ||
                element_address != native_element->rt->addr)
            {
                setError(Error::invalid_argument);
                return false;
            }

            const auto bind_local = [=](std::uint16_t model_id) noexcept
            {
                const struct bt_mesh_model *local_model =
                    bt_mesh_model_find(native_element, model_id);
                if (local_model == nullptr)
                {
                    setError(Error::invalid_argument);
                    return false;
                }
                return bindLocalModel(local_model, app_key_index);
            };
#if defined(CONFIG_NUCODE_BLE_MESH_UPDATE)
            if (model == Model::mesh_dfu_target)
            {
                return bind_local(BT_MESH_MODEL_ID_BLOB_SRV) &&
                       bind_local(BT_MESH_MODEL_ID_DFU_SRV);
            }
            if (model == Model::firmware_distributor)
            {
                return bind_local(BT_MESH_MODEL_ID_BLOB_CLI) &&
                       bind_local(BT_MESH_MODEL_ID_DFU_CLI) &&
                       bind_local(BT_MESH_MODEL_ID_BLOB_SRV) &&
                       bind_local(BT_MESH_MODEL_ID_DFD_SRV);
            }
#endif
#if defined(CONFIG_NUCODE_BLE_MESH_MANAGEMENT)
            if (model == Model::solicitation_rpl_configuration)
            {
                return bind_local(BT_MESH_MODEL_ID_SOL_PDU_RPL_CLI) &&
                       bind_local(BT_MESH_MODEL_ID_SOL_PDU_RPL_SRV);
            }
#endif
            return bindLocalModel(native_model, app_key_index);
        }
        const auto bind = [=](std::uint16_t model_id) noexcept
        {
            std::uint8_t status = 0U;
            const int error = bt_mesh_cfg_cli_mod_app_bind(
                net_key_index, node_address, element_address, app_key_index,
                model_id, &status);
            return finishConfiguration(error, status);
        };
#if defined(CONFIG_NUCODE_BLE_MESH_UPDATE)
        if (model == Model::mesh_dfu_target)
        {
            return bind(BT_MESH_MODEL_ID_BLOB_SRV) &&
                   bind(BT_MESH_MODEL_ID_DFU_SRV);
        }
        if (model == Model::firmware_distributor)
        {
            return bind(BT_MESH_MODEL_ID_BLOB_CLI) &&
                   bind(BT_MESH_MODEL_ID_DFU_CLI) &&
                   bind(BT_MESH_MODEL_ID_BLOB_SRV) &&
                   bind(BT_MESH_MODEL_ID_DFD_SRV);
        }
#endif
#if defined(CONFIG_NUCODE_BLE_MESH_MANAGEMENT)
        if (model == Model::solicitation_rpl_configuration)
        {
            return bind(BT_MESH_MODEL_ID_SOL_PDU_RPL_CLI) &&
                   bind(BT_MESH_MODEL_ID_SOL_PDU_RPL_SRV);
        }
#endif
        return bind(native_model->id);
    }

    bool MeshDevice::subscribeModel(std::uint16_t node_address,
                                    std::uint16_t element_address, Model model,
                                    std::uint16_t group_address,
                                    std::uint16_t net_key_index) noexcept
    {
        if (!readyProvisioner())
        {
            return false;
        }
        const struct bt_mesh_model *native_model = modelFor(model);
        if (!validUnicastAddress(node_address) || !validUnicastAddress(element_address) ||
            group_address < 0xC000U || group_address > 0xFEFFU ||
            native_model == nullptr || net_key_index > 0x0FFFU)
        {
            setError(Error::invalid_argument);
            return false;
        }
        std::uint8_t status = 0U;
        const int error = bt_mesh_cfg_cli_mod_sub_add(net_key_index, node_address,
                                                      element_address, group_address,
                                                      native_model->id, &status);
        return finishConfiguration(error, status);
    }

    bool MeshDevice::configurePublication(std::uint16_t node_address,
                                          std::uint16_t element_address, Model model,
                                          const Publication &publication,
                                          std::uint16_t net_key_index) noexcept
    {
        if (!readyProvisioner())
        {
            return false;
        }
        const struct bt_mesh_model *native_model = modelFor(model);
        std::uint8_t period = 0U;
        if (!validUnicastAddress(node_address) || !validUnicastAddress(element_address) ||
            publication.address == BT_MESH_ADDR_UNASSIGNED ||
            publication.address == BT_MESH_ADDR_ALL_NODES ||
            publication.app_key_index > 0x0FFFU || net_key_index > 0x0FFFU ||
            publication.ttl > BT_MESH_TTL_MAX || publication.retransmit_count > 7U ||
            publication.retransmit_interval_ms < 10U ||
            publication.retransmit_interval_ms > 320U ||
            publication.retransmit_interval_ms % 10U != 0U || native_model == nullptr ||
            !encodePublicationPeriod(publication.period_ms, period))
        {
            setError(Error::invalid_argument);
            return false;
        }

        struct bt_mesh_cfg_cli_mod_pub native_publication{};
        native_publication.addr = publication.address;
        native_publication.app_idx = publication.app_key_index;
        native_publication.cred_flag = publication.friendship_credentials;
        native_publication.ttl = publication.ttl;
        native_publication.period = period;
        native_publication.transmit = BT_MESH_TRANSMIT(publication.retransmit_count,
                                                       publication.retransmit_interval_ms);
        std::uint8_t status = 0U;
        const int error = bt_mesh_cfg_cli_mod_pub_set(net_key_index, node_address,
                                                      element_address, native_model->id,
                                                      &native_publication, &status);
        return finishConfiguration(error, status);
    }

    bool MeshDevice::readHealthFaults(const Destination &destination,
                                      std::uint16_t company_id,
                                      HealthFaults &faults) noexcept
    {
        if (atomic_get(&mesh_context.started) == 0)
        {
            setError(Error::not_started);
            return false;
        }
        if (!bt_mesh_is_provisioned())
        {
            setError(Error::not_provisioned);
            return false;
        }
        if (!validUnicastAddress(destination.address) || destination.ttl > BT_MESH_TTL_MAX)
        {
            setError(Error::invalid_argument);
            return false;
        }

        struct bt_mesh_msg_ctx native_context{};
        native_context.net_idx = destination.net_key_index;
        native_context.app_idx = destination.app_key_index;
        native_context.addr = destination.address;
        native_context.send_ttl = destination.ttl;
        native_context.send_rel = destination.force_segment_acknowledgment;

        HealthFaults result{};
        result.company_id = company_id;
        std::size_t count = HealthFaults::capacity;
        const int error = bt_mesh_health_cli_fault_get(nucode_mesh_health_client(),
                                                       &native_context, company_id,
                                                       &result.test_id, result.faults,
                                                       &count);
        if (error != 0)
        {
            setError(error == -EBUSY ? Error::busy : Error::driver_error, error);
            return false;
        }
        result.fault_count = static_cast<std::uint8_t>(count);
        result.truncated = count == HealthFaults::capacity;
        faults = result;
        setError(Error::none);
        return true;
    }

    bool MeshDevice::sendOnOff(const Destination &destination, bool enabled,
                               bool acknowledged) noexcept
    {
        const std::uint8_t transaction_id = mesh_context.transaction_id++;
        return sendOnOff(destination, enabled, acknowledged, transaction_id);
    }

    bool MeshDevice::sendOnOff(const Destination &destination, bool enabled,
                               bool acknowledged,
                               std::uint8_t transaction_id) noexcept
    {
        const std::uint8_t payload[] = {
            static_cast<std::uint8_t>(enabled ? 1U : 0U), transaction_id};
        return send(Model::generic_on_off, destination,
                    acknowledged ? on_off_set_opcode : on_off_set_unack_opcode,
                    payload, sizeof(payload));
    }

    bool MeshDevice::setLocalOnOff(bool enabled, bool publish) noexcept
    {
        if (atomic_get(&mesh_context.started) == 0)
        {
            setError(Error::not_started);
            return false;
        }
        const int error = nucode_mesh_onoff_server_set(enabled, publish);
        if (error != 0)
        {
            setError(error == -EADDRNOTAVAIL ? Error::invalid_context : Error::driver_error,
                     error);
            return false;
        }
        setError(Error::none);
        return true;
    }

    bool MeshDevice::localOnOff() const noexcept
    {
        return nucode_mesh_onoff_server_get();
    }

    bool MeshDevice::sendLevel(const Destination &destination, std::int16_t level,
                               bool acknowledged) noexcept
    {
        std::uint8_t payload[3]{};
        sys_put_le16(static_cast<std::uint16_t>(level), payload);
        payload[2] = mesh_context.transaction_id++;
        return send(Model::generic_level, destination,
                    acknowledged ? level_set_opcode : level_set_unack_opcode,
                    payload, sizeof(payload));
    }

    bool MeshDevice::sendLightness(const Destination &destination, std::uint16_t lightness,
                                   bool acknowledged) noexcept
    {
        std::uint8_t payload[3]{};
        sys_put_le16(lightness, payload);
        payload[2] = mesh_context.transaction_id++;
        return send(Model::light_lightness, destination,
                    acknowledged ? lightness_set_opcode : lightness_set_unack_opcode,
                    payload, sizeof(payload));
    }

    bool MeshDevice::requestSensor(const Destination &destination,
                                   std::uint16_t property) noexcept
    {
        std::uint8_t payload[2]{};
        const std::size_t size = property == 0U ? 0U : sizeof(payload);
        if (size != 0U)
        {
            sys_put_le16(property, payload);
        }
        return send(Model::sensor, destination, sensor_get_opcode, payload, size);
    }

    bool MeshDevice::requestTime(const Destination &destination) noexcept
    {
        return send(Model::time, destination, time_get_opcode, nullptr, 0U);
    }

    bool MeshDevice::recallScene(const Destination &destination, std::uint16_t scene,
                                 bool acknowledged) noexcept
    {
        if (scene == 0U)
        {
            setError(Error::invalid_argument);
            return false;
        }
        std::uint8_t payload[3]{};
        sys_put_le16(scene, payload);
        payload[2] = mesh_context.transaction_id++;
        return send(Model::scene, destination,
                    acknowledged ? scene_recall_opcode : scene_recall_unack_opcode,
                    payload, sizeof(payload));
    }

    bool MeshDevice::requestSchedule(const Destination &destination) noexcept
    {
        return send(Model::scheduler, destination, scheduler_get_opcode, nullptr, 0U);
    }

    std::uint32_t MeshDevice::droppedEvents() const noexcept
    {
        return static_cast<std::uint32_t>(atomic_get(&mesh_context.dropped_events));
    }

    Error MeshDevice::lastError() const noexcept
    {
        return mesh_context.error;
    }

    int MeshDevice::lastDriverError() const noexcept
    {
        return mesh_context.driver_error;
    }

    std::uint8_t MeshDevice::lastConfigurationStatus() const noexcept
    {
        return mesh_context.configuration_status;
    }

} // namespace nucode::mesh

nucode::mesh::MeshDevice NUCODEMesh;

#endif
