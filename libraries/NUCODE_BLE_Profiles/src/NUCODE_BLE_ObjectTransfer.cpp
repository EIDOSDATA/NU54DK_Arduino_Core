/** @file @brief 고정 NCS OTS/OTC API를 main-thread queue와 bounded storage에 연결합니다.
 * SPDX-License-Identifier: MIT
 */
#if !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE)
#include "NUCODE_BLE_ObjectTransfer.h"
#include <errno.h>
#if (defined(CONFIG_BT_OTS) || defined(CONFIG_BT_OTS_CLIENT)) && CONFIG_BT_MAX_CONN == 1
#include <internal/NUCODE_BLE_Internal.h>
#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/gatt.h>
#include <zephyr/bluetooth/services/ots.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/byteorder.h>
#include <string.h>
#endif

namespace nucode::ble::profiles
{
    namespace
    {
        /** @brief main API와 stack callback의 오류 상태를 data race 없이 공유합니다. */
        struct ErrorState
        {
            int value = 0;
            ErrorState &operator=(int error) noexcept
            {
                __atomic_store_n(&value, error, __ATOMIC_RELEASE);
                return *this;
            }
            operator int() const noexcept
            {
                return __atomic_load_n(&value, __ATOMIC_ACQUIRE);
            }
        };
        ErrorState server_error;
        ErrorState client_error;
#if (defined(CONFIG_BT_OTS) || defined(CONFIG_BT_OTS_CLIENT)) && CONFIG_BT_MAX_CONN == 1
        static_assert(CONFIG_BT_OTS_OBJ_MAX_NAME_LEN == ObjectStore::maximum_name,
                      "OTS object name configuration must be exactly 32 bytes");
        K_MSGQ_DEFINE(server_events, sizeof(ObjectEvent), 8U, 4U);
        K_MSGQ_DEFINE(client_events, sizeof(ObjectEvent), 8U, 4U);
        /** @brief queue 손실은 다음 API에서 오류로 드러내고 성공으로 무시하지 않습니다. */
        void emit(struct k_msgq &queue, const ObjectEvent &event, ErrorState &error) noexcept
        {
            if (k_msgq_put(&queue, &event, K_NO_WAIT) != 0)
            {
                error = -ENOBUFS;
            }
        }
#endif
#if defined(CONFIG_BT_OTS) && CONFIG_BT_MAX_CONN == 1
        ObjectStore objects;
        bt_ots *server = nullptr;
        bool server_ready = false;
        const char *pending_name = nullptr;
        const std::uint8_t *pending_data = nullptr;
        std::size_t pending_length = 0U;
        bool pending_writable = false;
        bool pending_removable = false;
        std::uint64_t added_id = 0U;
        K_MUTEX_DEFINE(object_mutex);

        /** @brief native rename/delete가 conn을 전달하지 않아 ATT 진입점에서 보호합니다. */
        bool authorizeObjectAccess(bt_conn *conn, const bt_gatt_attr *attribute)
        {
            if (attribute == nullptr || attribute->uuid == nullptr ||
                attribute->uuid->type != BT_UUID_TYPE_16)
            {
                return true;
            }
            const auto uuid = BT_UUID_16(attribute->uuid)->val;
            return uuid < BT_UUID_OTS_FEATURE_VAL || uuid > BT_UUID_OTS_CHANGED_VAL ||
                   (conn != nullptr && bt_conn_get_security(conn) >= BT_SECURITY_L2);
        }
        const bt_gatt_authorization_cb object_authorization = {authorizeObjectAccess,
                                                               authorizeObjectAccess};

        /** @brief main thread와 stack callback이 같은 object 상태를 직렬화합니다. */
        struct ServerGuard
        {
            ServerGuard()
            {
                k_mutex_lock(&object_mutex, K_FOREVER);
            }
            ~ServerGuard()
            {
                k_mutex_unlock(&object_mutex);
            }
        };

        int created(bt_ots *, bt_conn *conn, std::uint64_t id,
                    const bt_ots_obj_add_param *parameters, bt_ots_obj_created_desc *description)
        {
            ServerGuard guard;
            if (parameters == nullptr || description == nullptr ||
                (conn != nullptr && bt_conn_get_security(conn) < BT_SECURITY_L2) ||
                parameters->type.uuid.type != BT_UUID_TYPE_16 ||
                parameters->type.uuid_16.val != BT_UUID_OTS_TYPE_UNSPECIFIED_VAL)
            {
                return -EINVAL;
            }
            k_mutex_lock(&object_mutex, K_FOREVER);
            auto *object = objects.create(id, conn == nullptr ? pending_name : "", parameters->size,
                                          conn == nullptr ? pending_data : nullptr,
                                          conn == nullptr ? pending_length : 0U,
                                          conn == nullptr ? pending_writable : true,
                                          conn == nullptr ? pending_removable : true);
            if (object == nullptr)
            {
                k_mutex_unlock(&object_mutex);
                return -ENOMEM;
            }
            description->name = object->name;
            description->size.cur = object->size;
            description->size.alloc = object->capacity;
            description->props = 0U;
            BT_OTS_OBJ_SET_PROP_READ(description->props);
            if (object->writable)
            {
                BT_OTS_OBJ_SET_PROP_WRITE(description->props);
                BT_OTS_OBJ_SET_PROP_PATCH(description->props);
            }
            if (object->removable)
            {
                BT_OTS_OBJ_SET_PROP_DELETE(description->props);
            }
            added_id = id;
            k_mutex_unlock(&object_mutex);
            ObjectEvent event;
            event.type = ObjectEventType::created;
            event.peer = internal::handleForActiveConnection(conn);
            event.id = id;
            emit(server_events, event, server_error);
            return 0;
        }
        int deleted(bt_ots *, bt_conn *conn, std::uint64_t id)
        {
            ServerGuard guard;
            const auto *object = objects.find(id);
            /** @brief disconnect 정리는 보안 수준이 내려간 뒤에도 이름 없는 임시 객체를 폐기합니다. */
            if (conn != nullptr && bt_conn_get_security(conn) < BT_SECURITY_L2 &&
                (object == nullptr || object->name[0] != '\0'))
            {
                return -EACCES;
            }
            k_mutex_lock(&object_mutex, K_FOREVER);
            const bool removed = objects.erase(id);
            k_mutex_unlock(&object_mutex);
            if (!removed)
            {
                return -EACCES;
            }
            ObjectEvent event;
            event.type = ObjectEventType::deleted;
            event.peer = internal::handleForActiveConnection(conn);
            event.id = id;
            emit(server_events, event, server_error);
            return 0;
        }
        void selected(bt_ots *, bt_conn *conn, std::uint64_t id)
        {
            ServerGuard guard;
            ObjectEvent event;
            event.type = ObjectEventType::selected;
            event.peer = internal::handleForActiveConnection(conn);
            event.id = id;
            emit(server_events, event, server_error);
        }
        ssize_t readObject(bt_ots *, bt_conn *conn, std::uint64_t id, void **data,
                           std::size_t length, off_t offset)
        {
            if (conn == nullptr || bt_conn_get_security(conn) < BT_SECURITY_L2 || offset < 0)
            {
                return -EACCES;
            }
            if (data == nullptr)
            {
                return 0;
            }
            k_mutex_lock(&object_mutex, K_FOREVER);
            auto *object = objects.find(id);
            if (object == nullptr || static_cast<std::size_t>(offset) > object->size ||
                length > object->size - static_cast<std::size_t>(offset))
            {
                k_mutex_unlock(&object_mutex);
                return -EINVAL;
            }
            *data = object->bytes + offset;
            k_mutex_unlock(&object_mutex);
            return static_cast<ssize_t>(length < 128U ? length : 128U);
        }
        ssize_t writeObject(bt_ots *, bt_conn *conn, std::uint64_t id, const void *data,
                            std::size_t length, off_t offset, std::size_t remaining)
        {
            ServerGuard guard;
            if (conn == nullptr || bt_conn_get_security(conn) < BT_SECURITY_L2 || offset < 0)
            {
                return -EACCES;
            }
            k_mutex_lock(&object_mutex, K_FOREVER);
            const bool written = objects.write(id, static_cast<std::size_t>(offset),
                                               static_cast<const std::uint8_t *>(data), length);
            ObjectEvent event;
            if (written && remaining == 0U)
            {
                const auto *object = objects.find(id);
                event.type = ObjectEventType::received;
                event.peer = internal::handleForActiveConnection(conn);
                event.id = id;
                event.length = object->size;
                memcpy(event.data, object->bytes, object->size);
            }
            k_mutex_unlock(&object_mutex);
            if (!written)
            {
                return -EINVAL;
            }
            if (remaining == 0U)
            {
                emit(server_events, event, server_error);
            }
            return static_cast<ssize_t>(length);
        }
        bt_ots_cb server_callbacks{};
#endif
#if defined(CONFIG_BT_OTS_CLIENT) && CONFIG_BT_MAX_CONN == 1
        bt_ots_client client{};
        bt_ots_client_cb client_callbacks{};
        bt_gatt_discover_params discovery{};
        bt_gatt_write_params raw_write{};
        bt_uuid_16 service_uuid = BT_UUID_INIT_16(BT_UUID_OTS_VAL);
        bt_conn *client_connection = nullptr;
        BLEConnectionHandle client_peer;
        bool registered = false;
        bool client_ready = false;
        atomic_t operation_pending = ATOMIC_INIT(0);
        std::int64_t deadline = 0;
        std::uint8_t subscribed = 0U;
        std::uint8_t tx_buffer[ObjectStore::maximum_bytes] = {};
        ObjectEvent received_object;
        std::uint8_t raw_opcode = 0U;
        bool raw_is_control = false;
        bool raw_ack_seen = false;
        bool raw_response_seen = false;
        ObjectEvent raw_response;
        enum class DeferredTransfer : std::uint8_t
        {
            none,
            read,
            write,
        };
        DeferredTransfer deferred_transfer = DeferredTransfer::none;
        std::int64_t post_read_teardown_until = 0;
        std::int64_t retry_at = 0;
        std::size_t deferred_length = 0U;
        std::uint32_t deferred_offset = 0U;
        std::uint32_t known_size = 0U, known_capacity = 0U;
        K_MUTEX_DEFINE(client_mutex);
        /** @brief disconnect와 사용자 요청의 native reference 수명을 직렬화합니다. */
        struct ClientGuard
        {
            ClientGuard()
            {
                k_mutex_lock(&client_mutex, K_FOREVER);
            }
            ~ClientGuard()
            {
                k_mutex_unlock(&client_mutex);
            }
        };

        void complete(ObjectEvent &event)
        {
            event.peer = client_peer;
            deferred_transfer = DeferredTransfer::none;
            atomic_clear(&operation_pending);
            client_error = event.status;
            emit(client_events, event, client_error);
        }
        void operationError(int error)
        {
            ObjectEvent event;
            event.type = ObjectEventType::error;
            event.status = error;
            complete(event);
        }
        bool startOperation()
        {
            if (!client_ready || client_connection == nullptr ||
                !BLEConnection.connected(client_peer) || !atomic_cas(&operation_pending, 0, 1))
            {
                client_error = -EBUSY;
                return false;
            }
            deadline = k_uptime_get() + 10000;
            return true;
        }
        bool submitted(int result)
        {
            if (result != 0)
            {
                operationError(result);
                return false;
            }
            return true;
        }
        /**
         * @brief 완료 read callback 뒤 비동기 CoC 해제 구간의 ENOMEM만 지연 처리합니다.
         * @details NCS 3.4.0 OTC는 public closed callback이 없습니다. 완료 read가 연
         * 10초 창 안에서만 최대 10ms마다 재시도하며 다른 오류와 일반 ENOMEM은 실패합니다.
         */
        bool submitTransfer(DeferredTransfer transfer, std::size_t length = 0U,
                            std::uint32_t offset = 0U)
        {
            const int result =
                transfer == DeferredTransfer::read
                    ? bt_ots_client_read_object_data(&client, client_connection)
                    : bt_ots_client_write_object_data(&client, client_connection, tx_buffer, length,
                                                      offset, BT_OTS_OACP_WRITE_OP_MODE_NONE);
            if (result == -ENOMEM && post_read_teardown_until > k_uptime_get())
            {
                deferred_transfer = transfer;
                deferred_length = length;
                deferred_offset = offset;
                retry_at = k_uptime_get() + 10;
                if (deadline > post_read_teardown_until)
                {
                    deadline = post_read_teardown_until;
                }
                client_error = 0;
                return true;
            }
            deferred_transfer = DeferredTransfer::none;
            post_read_teardown_until = 0;
            return submitted(result);
        }
        void objectSelected(bt_ots_client *, bt_conn *conn, int result)
        {
            ClientGuard guard;
            if (conn != client_connection)
            {
                return;
            }
            ObjectEvent event;
            event.type = result == 1 ? ObjectEventType::selected : ObjectEventType::error;
            event.status = result == 1 ? 0 : result;
            event.id = client.cur_object.id;
            known_size = 0U;
            known_capacity = 0U;
            complete(event);
        }
        void objectMetadata(bt_ots_client *, bt_conn *conn, int error, std::uint8_t)
        {
            ClientGuard guard;
            if (conn != client_connection)
            {
                return;
            }
            ObjectEvent event;
            event.type = error == 0 ? ObjectEventType::metadata : ObjectEventType::error;
            event.status = error;
            event.id = client.cur_object.id;
            event.length = client.cur_object.size.cur;
            event.properties = client.cur_object.props;
            const std::size_t name_length =
                strnlen(client.cur_object.name_c, sizeof(client.cur_object.name_c));
            if (name_length > ObjectStore::maximum_name)
            {
                operationError(-EBADMSG);
                return;
            }
            memcpy(event.name, client.cur_object.name_c, name_length);
            if (error == 0)
            {
                known_size = client.cur_object.size.cur;
                known_capacity = client.cur_object.size.alloc;
            }
            complete(event);
        }
        int objectRead(bt_ots_client *, bt_conn *conn, std::uint32_t offset, std::uint32_t length,
                       std::uint8_t *data, bool finished)
        {
            ClientGuard guard;
            if (conn != client_connection)
            {
                return BT_OTS_STOP;
            }
            if (offset > ObjectStore::maximum_bytes ||
                length > ObjectStore::maximum_bytes - offset || (length != 0U && data == nullptr) ||
                offset != received_object.length)
            {
                operationError(-EMSGSIZE);
                return BT_OTS_STOP;
            }
            if (length != 0U)
            {
                memcpy(received_object.data + offset, data, length);
            }
            received_object.length += length;
            if (finished)
            {
                received_object.type = ObjectEventType::received;
                received_object.id = client.cur_object.id;
                post_read_teardown_until = k_uptime_get() + 10000;
                complete(received_object);
            }
            return BT_OTS_CONTINUE;
        }
        void objectWritten(bt_ots_client *, bt_conn *conn, std::size_t length)
        {
            ClientGuard guard;
            if (conn != client_connection)
            {
                return;
            }
            ObjectEvent event;
            event.type = ObjectEventType::written;
            event.id = client.cur_object.id;
            event.length = length;
            complete(event);
        }
        std::uint8_t indication(bt_conn *conn, bt_gatt_subscribe_params *parameters,
                                const void *data, std::uint16_t length)
        {
            ClientGuard guard;
            if (conn != client_connection)
            {
                return BT_GATT_ITER_STOP;
            }
            /** @brief 현재 연결의 소유 구독만 SDK에 전달해 제거 때 busy도 해제합니다. */
            if (parameters != &client.oacp_sub_params && parameters != &client.olcp_sub_params)
            {
                return BT_GATT_ITER_STOP;
            }
            if (data != nullptr && parameters == &client.oacp_sub_params && raw_opcode != 0U)
            {
                const auto *bytes = static_cast<const std::uint8_t *>(data);
                if (length == 3U && bytes[0] == 0x60U && bytes[1] == raw_opcode)
                {
                    ObjectEvent event;
                    event.type = bytes[2] == 1U ? (raw_opcode == 1U ? ObjectEventType::created
                                                                    : ObjectEventType::deleted)
                                                : ObjectEventType::error;
                    event.status = bytes[2] == 1U ? 0 : bytes[2];
                    raw_response = event;
                    raw_response_seen = true;
                    if (raw_ack_seen)
                    {
                        raw_opcode = 0U;
                        complete(raw_response);
                    }
                    return BT_GATT_ITER_CONTINUE;
                }
            }
            return bt_ots_client_indicate_handler(conn, parameters, data, length);
        }
        void subscriptionComplete(bt_conn *conn, std::uint8_t error,
                                  bt_gatt_subscribe_params *parameters)
        {
            ClientGuard guard;
            const std::uint8_t bit = parameters == &client.oacp_sub_params   ? 1U
                                     : parameters == &client.olcp_sub_params ? 2U
                                                                             : 0U;
            if (conn != client_connection || bit == 0U || (subscribed & bit) != 0U ||
                client_ready || atomic_get(&operation_pending) == 0)
            {
                return;
            }
            if (error != 0U)
            {
                operationError(error);
                return;
            }
            subscribed |= bit;
            if (subscribed == 3U)
            {
                client_ready = true;
                ObjectEvent event;
                event.type = ObjectEventType::ready;
                complete(event);
            }
        }
        int subscribe(bt_gatt_subscribe_params &parameters, bt_gatt_discover_params &discover,
                      std::uint16_t handle)
        {
            parameters.disc_params = &discover;
            parameters.ccc_handle = BT_GATT_AUTO_DISCOVER_CCC_HANDLE;
            parameters.end_handle = client.end_handle;
            parameters.value_handle = handle;
            parameters.value = BT_GATT_CCC_INDICATE;
            parameters.notify = indication;
            parameters.subscribe = subscriptionComplete;
            /** @brief 다음 begin의 재초기화 전에 bonded 구독 node도 해제되게 합니다. */
            atomic_set_bit(parameters.flags, BT_GATT_SUBSCRIBE_FLAG_VOLATILE);
            return bt_gatt_subscribe(client_connection, &parameters);
        }
        std::uint8_t discovered(bt_conn *conn, const bt_gatt_attr *attribute,
                                bt_gatt_discover_params *parameters)
        {
            ClientGuard guard;
            if (conn != client_connection)
            {
                return BT_GATT_ITER_STOP;
            }
            if (attribute == nullptr)
            {
                if (parameters->type != BT_GATT_DISCOVER_CHARACTERISTIC ||
                    client.feature_handle == 0U || client.obj_name_handle == 0U ||
                    client.obj_type_handle == 0U || client.obj_size_handle == 0U ||
                    client.obj_id_handle == 0U || client.obj_properties_handle == 0U ||
                    client.oacp_handle == 0U || client.olcp_handle == 0U)
                {
                    operationError(-ENOENT);
                    return BT_GATT_ITER_STOP;
                }
                /** @brief SDK L2CAP list node는 image lifetime에 한 번만 등록합니다. */
                const int result = registered ? 0 : bt_ots_client_register(&client);
                registered = registered || result == 0;
                if (result != 0 ||
                    subscribe(client.oacp_sub_params, client.oacp_sub_disc_params,
                              client.oacp_handle) != 0 ||
                    subscribe(client.olcp_sub_params, client.olcp_sub_disc_params,
                              client.olcp_handle) != 0)
                {
                    operationError(result != 0 ? result : -EIO);
                }
                return BT_GATT_ITER_STOP;
            }
            if (parameters->type == BT_GATT_DISCOVER_PRIMARY)
            {
                const auto *service =
                    static_cast<const bt_gatt_service_val *>(attribute->user_data);
                client.start_handle = attribute->handle;
                client.end_handle = service->end_handle;
                parameters->uuid = nullptr;
                parameters->start_handle = attribute->handle + 1U;
                parameters->end_handle = service->end_handle;
                parameters->type = BT_GATT_DISCOVER_CHARACTERISTIC;
                const int result = bt_gatt_discover(conn, parameters);
                if (result != 0)
                {
                    operationError(result);
                }
                return BT_GATT_ITER_STOP;
            }
            const auto *characteristic = static_cast<const bt_gatt_chrc *>(attribute->user_data);
            if (characteristic->uuid->type != BT_UUID_TYPE_16)
            {
                return BT_GATT_ITER_CONTINUE;
            }
            const auto uuid = BT_UUID_16(characteristic->uuid)->val;
            switch (uuid)
            {
            case BT_UUID_OTS_FEATURE_VAL:
                client.feature_handle = characteristic->value_handle;
                break;
            case BT_UUID_OTS_NAME_VAL:
                client.obj_name_handle = characteristic->value_handle;
                break;
            case BT_UUID_OTS_TYPE_VAL:
                client.obj_type_handle = characteristic->value_handle;
                break;
            case BT_UUID_OTS_SIZE_VAL:
                client.obj_size_handle = characteristic->value_handle;
                break;
            case BT_UUID_OTS_ID_VAL:
                client.obj_id_handle = characteristic->value_handle;
                break;
            case BT_UUID_OTS_PROPERTIES_VAL:
                client.obj_properties_handle = characteristic->value_handle;
                break;
            case BT_UUID_OTS_ACTION_CP_VAL:
                client.oacp_handle = characteristic->value_handle;
                break;
            case BT_UUID_OTS_LIST_CP_VAL:
                client.olcp_handle = characteristic->value_handle;
                break;
            default:
                break;
            }
            return BT_GATT_ITER_CONTINUE;
        }
        void rawWriteComplete(bt_conn *conn, std::uint8_t error, bt_gatt_write_params *)
        {
            ClientGuard guard;
            if (conn != client_connection)
            {
                return;
            }
            if (error != 0U)
            {
                raw_opcode = 0U;
                operationError(error);
            }
            else if (!raw_is_control)
            {
                ObjectEvent event;
                event.type = ObjectEventType::written;
                complete(event);
            }
            else
            {
                raw_ack_seen = true;
                if (raw_response_seen)
                {
                    raw_opcode = 0U;
                    complete(raw_response);
                }
            }
        }
        bool rawWrite(std::uint16_t handle, std::size_t length)
        {
            raw_is_control = raw_opcode != 0U;
            raw_ack_seen = false;
            raw_response_seen = false;
            raw_write = {};
            raw_write.handle = handle;
            raw_write.data = tx_buffer;
            raw_write.length = length;
            raw_write.func = rawWriteComplete;
            return submitted(bt_gatt_write(client_connection, &raw_write));
        }
        void disconnected(bt_conn *conn, std::uint8_t reason)
        {
            ClientGuard guard;
            if (conn != client_connection)
            {
                return;
            }
            client_ready = false;
            deferred_transfer = DeferredTransfer::none;
            post_read_teardown_until = 0;
            known_size = 0U;
            known_capacity = 0U;
            ObjectEvent event;
            event.type = ObjectEventType::disconnected;
            event.status = reason;
            complete(event);
            bt_conn_unref(client_connection);
            client_connection = nullptr;
            client_peer = {};
        }
        BT_CONN_CB_DEFINE(object_callbacks) = {.disconnected = disconnected};
#endif
    } // namespace

    bool ObjectTransferServer::begin() noexcept
    {
#if defined(CONFIG_BT_OTS) && CONFIG_BT_MAX_CONN == 1
        if (server != nullptr || !BLEDevice.initialized())
        {
            server_error = -EINVAL;
            return false;
        }
        server_error = bt_gatt_authorization_cb_register(&object_authorization);
        if (server_error != 0)
        {
            return false;
        }
        server_callbacks.obj_created = created;
        server_callbacks.obj_deleted = deleted;
        server_callbacks.obj_selected = selected;
        server_callbacks.obj_read = readObject;
        server_callbacks.obj_write = writeObject;
        server = bt_ots_free_instance_get();
        if (server == nullptr)
        {
            server_error = -ENOMEM;
            static_cast<void>(bt_gatt_authorization_cb_register(nullptr));
            return false;
        }
        bt_ots_init_param parameters{};
        BT_OTS_OACP_SET_FEAT_READ(parameters.features.oacp);
        BT_OTS_OACP_SET_FEAT_WRITE(parameters.features.oacp);
        BT_OTS_OACP_SET_FEAT_PATCH(parameters.features.oacp);
        BT_OTS_OACP_SET_FEAT_CREATE(parameters.features.oacp);
        BT_OTS_OACP_SET_FEAT_DELETE(parameters.features.oacp);
        BT_OTS_OLCP_SET_FEAT_GO_TO(parameters.features.olcp);
        parameters.cb = &server_callbacks;
        server_error = bt_ots_init(server, &parameters);
        server_ready = server_error == 0;
        if (!server_ready)
        {
            static_cast<void>(bt_gatt_authorization_cb_register(nullptr));
        }
        return server_ready;
#else
        server_error = -ENOTSUP;
        return false;
#endif
    }
    bool ObjectTransferServer::add(const char *name, const std::uint8_t *data, std::size_t length,
                                   bool writable, bool removable, std::uint64_t &id) noexcept
    {
#if defined(CONFIG_BT_OTS) && CONFIG_BT_MAX_CONN == 1
        if (!server_ready || BLEConnection.count() != 0U || name == nullptr || name[0] == '\0' ||
            length > ObjectStore::maximum_bytes || (data == nullptr && length != 0U))
        {
            server_error = -EINVAL;
            return false;
        }
        ServerGuard guard;
        pending_name = name;
        pending_data = data;
        pending_length = length;
        pending_writable = writable;
        pending_removable = removable;
        added_id = 0U;
        bt_ots_obj_add_param parameters{};
        parameters.size = ObjectStore::maximum_bytes;
        parameters.type.uuid.type = BT_UUID_TYPE_16;
        parameters.type.uuid_16.val = BT_UUID_OTS_TYPE_UNSPECIFIED_VAL;
        const int result = bt_ots_obj_add(server, &parameters);
        server_error = result < 0 ? result : 0;
        pending_name = nullptr;
        pending_data = nullptr;
        if (server_error == 0)
        {
            id = added_id;
        }
        return server_error == 0;
#else
        static_cast<void>(name);
        static_cast<void>(data);
        static_cast<void>(length);
        static_cast<void>(writable);
        static_cast<void>(removable);
        static_cast<void>(id);
        server_error = -ENOTSUP;
        return false;
#endif
    }
    bool ObjectTransferServer::remove(std::uint64_t id) noexcept
    {
#if defined(CONFIG_BT_OTS) && CONFIG_BT_MAX_CONN == 1
        if (!server_ready || BLEConnection.count() != 0U)
        {
            server_error = -EBUSY;
            return false;
        }
        ServerGuard guard;
        server_error = bt_ots_obj_delete(server, id);
        return server_error == 0;
#else
        static_cast<void>(id);
        server_error = -ENOTSUP;
        return false;
#endif
    }
    bool ObjectTransferServer::readEvent(ObjectEvent &event) noexcept
    {
#if defined(CONFIG_BT_OTS) && CONFIG_BT_MAX_CONN == 1
        return k_msgq_get(&server_events, &event, K_NO_WAIT) == 0;
#else
        static_cast<void>(event);
        return false;
#endif
    }
    int ObjectTransferServer::lastError() const noexcept
    {
#if defined(CONFIG_BT_OTS) && CONFIG_BT_MAX_CONN == 1
        if (server != nullptr)
        {
            ServerGuard guard;
            return server_error;
        }
#endif
        return server_error;
    }
    bool ObjectTransferClient::begin(BLEConnectionHandle peer) noexcept
    {
#if defined(CONFIG_BT_OTS_CLIENT) && CONFIG_BT_MAX_CONN == 1
        ClientGuard guard;
        if (client_connection != nullptr || !BLEConnection.connected(peer))
        {
            client_error = -EBUSY;
            return false;
        }
        client_connection = internal::referenceConnection(peer);
        if (client_connection == nullptr ||
            bt_conn_get_security(client_connection) < BT_SECURITY_L2)
        {
            if (client_connection != nullptr)
            {
                bt_conn_unref(client_connection);
                client_connection = nullptr;
            }
            client_error = -EACCES;
            return false;
        }
        client = {};
        client_callbacks = {};
        client_callbacks.obj_selected = objectSelected;
        client_callbacks.obj_metadata_read = objectMetadata;
        client_callbacks.obj_data_read = objectRead;
        client_callbacks.obj_data_written = objectWritten;
        client.cb = &client_callbacks;
        client_peer = peer;
        subscribed = 0U;
        raw_opcode = 0U;
        client_ready = false;
        known_size = 0U;
        known_capacity = 0U;
        deferred_transfer = DeferredTransfer::none;
        post_read_teardown_until = 0;
        atomic_set(&operation_pending, 1);
        deadline = k_uptime_get() + 10000;
        discovery = {};
        discovery.uuid = &service_uuid.uuid;
        discovery.start_handle = BT_ATT_FIRST_ATTRIBUTE_HANDLE;
        discovery.end_handle = BT_ATT_LAST_ATTRIBUTE_HANDLE;
        discovery.type = BT_GATT_DISCOVER_PRIMARY;
        discovery.func = discovered;
        return submitted(bt_gatt_discover(client_connection, &discovery));
#else
        static_cast<void>(peer);
        client_error = -ENOTSUP;
        return false;
#endif
    }
    void ObjectTransferClient::poll() noexcept
    {
#if defined(CONFIG_BT_OTS_CLIENT) && CONFIG_BT_MAX_CONN == 1
        ClientGuard guard;
        if (atomic_get(&operation_pending) != 0 && k_uptime_get() >= deadline)
        {
            operationError(-ETIMEDOUT);
            static_cast<void>(cancel());
        }
        else if (deferred_transfer != DeferredTransfer::none && k_uptime_get() >= retry_at)
        {
            static_cast<void>(submitTransfer(deferred_transfer, deferred_length, deferred_offset));
        }
#endif
    }
    bool ObjectTransferClient::selectFirst() noexcept
    {
#if defined(CONFIG_BT_OTS_CLIENT) && CONFIG_BT_MAX_CONN == 1
        ClientGuard guard;
        return startOperation() &&
               submitted(bt_ots_client_select_first(&client, client_connection));
#else
        client_error = -ENOTSUP;
        return false;
#endif
    }
    bool ObjectTransferClient::selectNext() noexcept
    {
#if defined(CONFIG_BT_OTS_CLIENT) && CONFIG_BT_MAX_CONN == 1
        ClientGuard guard;
        return startOperation() && submitted(bt_ots_client_select_next(&client, client_connection));
#else
        client_error = -ENOTSUP;
        return false;
#endif
    }
    bool ObjectTransferClient::select(std::uint64_t id) noexcept
    {
#if defined(CONFIG_BT_OTS_CLIENT) && CONFIG_BT_MAX_CONN == 1
        ClientGuard guard;
        if (id < 0x100U || id > 0xffffffffffffULL)
        {
            client_error = -EINVAL;
            return false;
        }
        return startOperation() &&
               submitted(bt_ots_client_select_id(&client, client_connection, id));
#else
        static_cast<void>(id);
        client_error = -ENOTSUP;
        return false;
#endif
    }
    bool ObjectTransferClient::metadata() noexcept
    {
#if defined(CONFIG_BT_OTS_CLIENT) && CONFIG_BT_MAX_CONN == 1
        ClientGuard guard;
        if (!startOperation())
        {
            return false;
        }
        known_size = 0U;
        known_capacity = 0U;
        return submitted(bt_ots_client_read_object_metadata(
            &client, client_connection,
            BT_OTS_METADATA_REQ_NAME | BT_OTS_METADATA_REQ_TYPE | BT_OTS_METADATA_REQ_SIZE |
                BT_OTS_METADATA_REQ_ID | BT_OTS_METADATA_REQ_PROPS));
#else
        client_error = -ENOTSUP;
        return false;
#endif
    }
    bool ObjectTransferClient::read() noexcept
    {
#if defined(CONFIG_BT_OTS_CLIENT) && CONFIG_BT_MAX_CONN == 1
        ClientGuard guard;
        if (atomic_get(&operation_pending) != 0)
        {
            client_error = -EBUSY;
            return false;
        }
        if (known_size == 0U || known_size > ObjectStore::maximum_bytes)
        {
            client_error = -EMSGSIZE;
            return false;
        }
        if (!startOperation())
        {
            return false;
        }
        received_object = {};
        return submitTransfer(DeferredTransfer::read);
#else
        client_error = -ENOTSUP;
        return false;
#endif
    }
    bool ObjectTransferClient::write(const std::uint8_t *data, std::size_t length,
                                     std::uint32_t offset) noexcept
    {
#if defined(CONFIG_BT_OTS_CLIENT) && CONFIG_BT_MAX_CONN == 1
        ClientGuard guard;
        if (atomic_get(&operation_pending) != 0)
        {
            client_error = -EBUSY;
            return false;
        }
        if (data == nullptr || length == 0U || length > sizeof(tx_buffer) ||
            offset > known_capacity || length > known_capacity - offset)
        {
            client_error = -EINVAL;
            return false;
        }
        if (!startOperation())
        {
            return false;
        }
        memcpy(tx_buffer, data, length);
        return submitTransfer(DeferredTransfer::write, length, offset);
#else
        static_cast<void>(data);
        static_cast<void>(length);
        static_cast<void>(offset);
        client_error = -ENOTSUP;
        return false;
#endif
    }
    bool ObjectTransferClient::create(std::uint32_t capacity) noexcept
    {
#if defined(CONFIG_BT_OTS_CLIENT) && CONFIG_BT_MAX_CONN == 1
        ClientGuard guard;
        if (capacity == 0U || capacity > ObjectStore::maximum_bytes)
        {
            client_error = -EINVAL;
            return false;
        }
        if (!startOperation())
        {
            return false;
        }
        raw_opcode = 1U;
        tx_buffer[0] = 1U;
        sys_put_le32(capacity, tx_buffer + 1U);
        sys_put_le16(BT_UUID_OTS_TYPE_UNSPECIFIED_VAL, tx_buffer + 5U);
        return rawWrite(client.oacp_handle, 7U);
#else
        static_cast<void>(capacity);
        client_error = -ENOTSUP;
        return false;
#endif
    }
    bool ObjectTransferClient::rename(const char *name) noexcept
    {
#if defined(CONFIG_BT_OTS_CLIENT) && CONFIG_BT_MAX_CONN == 1
        ClientGuard guard;
        if (name == nullptr)
        {
            client_error = -EINVAL;
            return false;
        }
        const std::size_t length = strnlen(name, ObjectStore::maximum_name + 1U);
        if (length == 0U || length > ObjectStore::maximum_name || !startOperation())
        {
            client_error = -EINVAL;
            return false;
        }
        raw_opcode = 0U;
        memcpy(tx_buffer, name, length);
        return rawWrite(client.obj_name_handle, length);
#else
        static_cast<void>(name);
        client_error = -ENOTSUP;
        return false;
#endif
    }
    bool ObjectTransferClient::remove() noexcept
    {
#if defined(CONFIG_BT_OTS_CLIENT) && CONFIG_BT_MAX_CONN == 1
        ClientGuard guard;
        if (!startOperation())
        {
            return false;
        }
        raw_opcode = 2U;
        tx_buffer[0] = 2U;
        return rawWrite(client.oacp_handle, 1U);
#else
        client_error = -ENOTSUP;
        return false;
#endif
    }
    bool ObjectTransferClient::cancel() noexcept
    {
#if defined(CONFIG_BT_OTS_CLIENT) && CONFIG_BT_MAX_CONN == 1
        ClientGuard guard;
        deferred_transfer = DeferredTransfer::none;
        post_read_teardown_until = 0;
        return client_connection != nullptr && BLEConnection.disconnect(client_peer);
#else
        client_error = -ENOTSUP;
        return false;
#endif
    }
    bool ObjectTransferClient::busy() const noexcept
    {
#if defined(CONFIG_BT_OTS_CLIENT) && CONFIG_BT_MAX_CONN == 1
        return atomic_get(&operation_pending) != 0;
#else
        return false;
#endif
    }
    std::size_t ObjectTransferClient::bytesReceived() const noexcept
    {
#if defined(CONFIG_BT_OTS_CLIENT) && CONFIG_BT_MAX_CONN == 1
        ClientGuard guard;
        return received_object.length;
#else
        return 0U;
#endif
    }
    bool ObjectTransferClient::readEvent(ObjectEvent &event) noexcept
    {
#if defined(CONFIG_BT_OTS_CLIENT) && CONFIG_BT_MAX_CONN == 1
        return k_msgq_get(&client_events, &event, K_NO_WAIT) == 0;
#else
        static_cast<void>(event);
        return false;
#endif
    }
    int ObjectTransferClient::lastError() const noexcept
    {
#if defined(CONFIG_BT_OTS_CLIENT) && CONFIG_BT_MAX_CONN == 1
        ClientGuard guard;
#endif
        return client_error;
    }
} // namespace nucode::ble::profiles
#endif
