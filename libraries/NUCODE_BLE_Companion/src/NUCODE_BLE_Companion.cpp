/** @file @brief NCS GATT discovery와 Zephyr 전송을 Apple wire codec에 연결합니다.
 * SPDX-License-Identifier: MIT
 * @note UUID·discovery 순서는 고정 NCS의 peripheral_ancs_client와 peripheral_ams_client를 따릅니다.
 */
#include "NUCODE_BLE_Companion.h"
#if !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE)
#if !defined(CONFIG_BT_GATT_DM) || !defined(CONFIG_BT_SMP)
#error "AppleClient requires the BLE feature set with GATT discovery and SMP security"
#endif
#include <internal/gap/GapInternal.h>
#include <bluetooth/gatt_dm.h>
#include <zephyr/bluetooth/uuid.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/atomic.h>
#include <errno.h>
#include <string.h>

namespace nucode::ble::companion
{
    namespace
    {
        const bt_uuid_128 ancs_uuid = BT_UUID_INIT_128(
            BT_UUID_128_ENCODE(0x7905f431, 0xb5ce, 0x4e99, 0xa40f, 0x4b1e122d00d0));
        const bt_uuid_128 ancs_ns = BT_UUID_INIT_128(
            BT_UUID_128_ENCODE(0x9fbf120d, 0x6301, 0x42d9, 0x8c58, 0x25e699a21dbd));
        const bt_uuid_128 ancs_ds = BT_UUID_INIT_128(
            BT_UUID_128_ENCODE(0x22eac6e9, 0x24d6, 0x4bb5, 0xbe44, 0xb36ace7c7bfb));
        const bt_uuid_128 ancs_cp = BT_UUID_INIT_128(
            BT_UUID_128_ENCODE(0x69d1d8f3, 0x45e1, 0x49a8, 0x9821, 0x9bbdfdaad9d9));
        const bt_uuid_128 ams_uuid = BT_UUID_INIT_128(
            BT_UUID_128_ENCODE(0x89d3502b, 0x0f36, 0x433a, 0x8ef4, 0xc502ad55f8dc));
        const bt_uuid_128 ams_rc = BT_UUID_INIT_128(
            BT_UUID_128_ENCODE(0x9b3c81d8, 0x57b1, 0x4a8a, 0xb8df, 0x0e56f7ca51c2));
        const bt_uuid_128 ams_eu = BT_UUID_INIT_128(
            BT_UUID_128_ENCODE(0x2f7cabce, 0x808d, 0x411f, 0x9a0c, 0xbb92ba96c102));
        const bt_uuid_128 ams_ea = BT_UUID_INIT_128(
            BT_UUID_128_ENCODE(0xc6b2f38c, 0x23ab, 0x46d8, 0xa6ab, 0xa3a870bbd5d7));
        enum class Kind : uint8_t
        {
            discovery,
            subscribed,
            first,
            second,
            written,
            read,
            error
        };
        struct Message
        {
            Kind kind;
            int status;
            size_t size;
            uint8_t data[512];
        };
        K_MSGQ_DEFINE(messages, sizeof(Message), 8, 4);
        atomic_ptr_t connection_pointer;
        atomic_t overflow;
        atomic_t pending_disconnect;
        atomic_t pending_security_error;
        constexpr atomic_val_t security_error_bias = 65536;
        AppleClient *owner;
        Service service;
        bt_gatt_subscribe_params subscriptions[2];
        bt_gatt_write_params write_parameters;
        bt_gatt_read_params read_parameters;
        uint16_t handles[3];
        uint16_t ccc[2];
        uint16_t command_mask;
        uint8_t transmit[16];
        uint8_t read_buffer[512];
        size_t read_length;
        uint8_t read_entity;
        uint8_t read_attribute;
        AttributeAssembler assembler;
        uint8_t requested_attribute;
        uint32_t requested_uid;
        int stage;
        bool write_busy;
        bool attribute_busy;
        bool reading;
        bool read_after_write;
        bool stopping;
        bool advertising;
        int64_t deadline;
        int64_t operation_deadline;

        bt_conn *connection()
        {
            return static_cast<bt_conn *>(atomic_ptr_get(&connection_pointer));
        }

        void enqueue(Kind kind, int status = 0, const void *data = nullptr, size_t size = 0)
        {
            Message message{};
            message.kind = kind;
            message.status = status;
            if (size > sizeof(message.data))
            {
                message.kind = Kind::error;
                message.status = -EMSGSIZE;
            }
            else if (data != nullptr)
            {
                message.size = size;
                memcpy(message.data, data, size);
            }
            if (k_msgq_put(&messages, &message, K_NO_WAIT) != 0)
            {
                atomic_set(&overflow, 1);
            }
        }

        void disconnected(bt_conn *conn, uint8_t reason)
        {
            if (conn == connection())
            {
                /** @brief 종료는 queue 포화에서도 유실하지 않는 별도 terminal 신호입니다. */
                atomic_set(&pending_disconnect, static_cast<atomic_val_t>(reason) + 1);
            }
        }

        /** @brief 비동기 보안 실패를 queue 포화·disconnect 순서와 무관하게 보존합니다. */
        void securityChanged(bt_conn *conn, bt_security_t, enum bt_security_err error)
        {
            if (conn == connection() && error != BT_SECURITY_ERR_SUCCESS)
            {
                atomic_set(&pending_security_error,
                           static_cast<atomic_val_t>(error) + security_error_bias);
            }
        }

        BT_CONN_CB_DEFINE(companion_callbacks) = {
            .disconnected = disconnected,
            .security_changed = securityChanged,
        };

        uint8_t notified(bt_conn *conn, bt_gatt_subscribe_params *parameters, const void *data,
                         uint16_t size)
        {
            if (conn != connection())
            {
                return BT_GATT_ITER_STOP;
            }
            if (data == nullptr)
            {
                return BT_GATT_ITER_STOP;
            }
            enqueue(parameters == &subscriptions[0] ? Kind::first : Kind::second, 0, data, size);
            return BT_GATT_ITER_CONTINUE;
        }

        void subscribed(bt_conn *conn, uint8_t error, bt_gatt_subscribe_params *)
        {
            if (conn == connection())
            {
                enqueue(Kind::subscribed, error);
            }
        }

        void written(bt_conn *conn, uint8_t error, bt_gatt_write_params *)
        {
            if (conn == connection())
            {
                enqueue(Kind::written, error);
            }
        }

        uint8_t readCallback(bt_conn *conn, uint8_t error, bt_gatt_read_params *, const void *data,
                             uint16_t size)
        {
            if (conn != connection())
            {
                return BT_GATT_ITER_STOP;
            }
            enqueue(Kind::read, error, data, data == nullptr ? 0 : size);
            return error == 0 && data != nullptr ? BT_GATT_ITER_CONTINUE : BT_GATT_ITER_STOP;
        }

        bool assign(bt_gatt_dm *dm, const bt_uuid *uuid, size_t index, uint8_t properties)
        {
            const auto *characteristic = bt_gatt_dm_char_by_uuid(dm, uuid);
            if (characteristic == nullptr)
            {
                return false;
            }
            const auto *metadata = bt_gatt_dm_attr_chrc_val(characteristic);
            if (metadata == nullptr || (metadata->properties & properties) != properties)
            {
                return false;
            }
            const auto *value = bt_gatt_dm_desc_by_uuid(dm, characteristic, uuid);
            if (value == nullptr)
            {
                return false;
            }
            handles[index] = value->handle;
            if ((properties & BT_GATT_CHRC_NOTIFY) != 0)
            {
                const auto *descriptor =
                    bt_gatt_dm_desc_by_uuid(dm, characteristic, BT_UUID_GATT_CCC);
                if (descriptor == nullptr)
                {
                    return false;
                }
                ccc[index] = descriptor->handle;
            }
            return true;
        }

        void discovered(bt_gatt_dm *dm, void *)
        {
            const bool same_connection = bt_gatt_dm_conn_get(dm) == connection();
            bool valid = same_connection;
            if (valid && service == Service::notifications)
            {
                valid = assign(dm, &ancs_ns.uuid, 0, BT_GATT_CHRC_NOTIFY) &&
                        assign(dm, &ancs_ds.uuid, 1, BT_GATT_CHRC_NOTIFY) &&
                        assign(dm, &ancs_cp.uuid, 2, BT_GATT_CHRC_WRITE);
            }
            else if (valid)
            {
                valid = assign(dm, &ams_rc.uuid, 0, BT_GATT_CHRC_NOTIFY | BT_GATT_CHRC_WRITE) &&
                        assign(dm, &ams_eu.uuid, 1, BT_GATT_CHRC_NOTIFY | BT_GATT_CHRC_WRITE) &&
                        assign(dm, &ams_ea.uuid, 2, BT_GATT_CHRC_READ | BT_GATT_CHRC_WRITE);
            }
            const int released = bt_gatt_dm_data_release(dm);
            if (same_connection)
            {
                enqueue(Kind::discovery, !valid ? -ENOENT : released);
            }
        }

        void serviceMissing(bt_conn *conn, void *)
        {
            if (conn == connection())
            {
                enqueue(Kind::discovery, -ENOENT);
            }
        }

        void discoveryError(bt_conn *conn, int error, void *)
        {
            if (conn == connection())
            {
                enqueue(Kind::discovery, error);
            }
        }

        const bt_gatt_dm_cb discovery_callbacks = {.completed = discovered,
                                                   .service_not_found = serviceMissing,
                                                   .error_found = discoveryError};

        int subscribe(size_t index)
        {
            auto &parameters = subscriptions[index];
            parameters.notify = notified;
            parameters.subscribe = subscribed;
            parameters.value_handle = handles[index];
            parameters.ccc_handle = ccc[index];
            parameters.value = BT_GATT_CCC_NOTIFY;
            atomic_set_bit(parameters.flags, BT_GATT_SUBSCRIBE_FLAG_VOLATILE);
            return bt_gatt_subscribe(connection(), &parameters);
        }

        Error send(size_t handle, const uint8_t *data, size_t size)
        {
            if (owner == nullptr || stage != 4 || stopping)
            {
                return Error::not_ready;
            }
            if (write_busy || reading || attribute_busy)
            {
                return Error::busy;
            }
            if (size > sizeof(transmit))
            {
                return Error::overflow;
            }
            memcpy(transmit, data, size);
            write_parameters = {};
            write_parameters.func = written;
            write_parameters.handle = handles[handle];
            write_parameters.data = transmit;
            write_parameters.length = size;
            write_busy = true;
            operation_deadline = k_uptime_get() + 5000;
            const int result = bt_gatt_write(connection(), &write_parameters);
            if (result != 0)
            {
                write_busy = false;
                return Error::transport;
            }
            return Error::none;
        }
    } // namespace

    Error AppleClient::begin(BLEConnectionHandle link, Service selected) noexcept
    {
        if (owner != nullptr || connection() != nullptr)
        {
            return Error::busy;
        }
        if (selected != Service::notifications && selected != Service::media)
        {
            return Error::invalid_argument;
        }
        bt_conn *conn = internal::referenceConnection(link);
        if (conn == nullptr)
        {
            return Error::stale_session;
        }
        k_msgq_purge(&messages);
        atomic_clear(&overflow);
        atomic_clear(&pending_disconnect);
        atomic_clear(&pending_security_error);
        atomic_ptr_set(&connection_pointer, conn);
        owner = this;
        service = selected;
        memset(subscriptions, 0, sizeof(subscriptions));
        memset(handles, 0, sizeof(handles));
        memset(ccc, 0, sizeof(ccc));
        command_mask = 0;
        assembler.reset();
        write_busy = attribute_busy = reading = read_after_write = stopping = false;
        stage = 0;
        deadline = k_uptime_get() + 15000;
        const int result = bt_conn_set_security(conn, BT_SECURITY_L2);
        if (result != 0)
        {
            atomic_set(&pending_security_error,
                       static_cast<atomic_val_t>(result) + security_error_bias);
            return Error::security;
        }
        return Error::none;
    }

    void AppleClient::onEvent(Callback callback, void *context) noexcept
    {
        callback_ = callback;
        context_ = context;
    }

    bool AppleClient::ready() const noexcept
    {
        return owner == this && stage == 4 && !stopping;
    }

    void AppleClient::end() noexcept
    {
        if (owner == this && connection() != nullptr && !stopping)
        {
            stopping = true;
            assembler.reset();
            memset(read_buffer, 0, sizeof(read_buffer));
            (void)bt_conn_disconnect(connection(), BT_HCI_ERR_REMOTE_USER_TERM_CONN);
        }
    }

    void AppleClient::poll() noexcept
    {
        if (owner != this)
        {
            return;
        }
        const atomic_val_t security_error = atomic_set(&pending_security_error, 0);
        if (security_error != 0 && !stopping)
        {
            EventInfo event{};
            event.event = Event::error;
            event.error = Error::security;
            event.native_code = static_cast<int>(security_error - security_error_bias);
            end();
            if (callback_ != nullptr)
            {
                callback_(event, context_);
            }
            return;
        }
        const atomic_val_t disconnected_reason = atomic_set(&pending_disconnect, 0);
        if (disconnected_reason != 0)
        {
            bt_conn *old = connection();
            atomic_ptr_set(&connection_pointer, nullptr);
            owner = nullptr;
            stage = 0;
            assembler.reset();
            memset(transmit, 0, sizeof(transmit));
            memset(read_buffer, 0, sizeof(read_buffer));
            k_msgq_purge(&messages);
            if (old != nullptr)
            {
                bt_conn_unref(old);
            }
            EventInfo event{};
            event.event = Event::disconnected;
            event.native_code = disconnected_reason - 1;
            if (callback_ != nullptr)
            {
                callback_(event, context_);
            }
            return;
        }
        if (!stopping && atomic_cas(&overflow, 1, 0))
        {
            k_msgq_purge(&messages);
            enqueue(Kind::error, -ENOBUFS);
        }
        if (!stopping &&
            ((stage != 4 && k_uptime_get() >= deadline) ||
             ((write_busy || attribute_busy || reading) && k_uptime_get() >= operation_deadline)))
        {
            enqueue(Kind::error, -ETIMEDOUT);
        }
        if (!stopping && stage == 0 && bt_conn_get_security(connection()) >= BT_SECURITY_L2)
        {
            stage = 1;
            const int result = bt_gatt_dm_start(
                connection(), service == Service::notifications ? &ancs_uuid.uuid : &ams_uuid.uuid,
                &discovery_callbacks, nullptr);
            if (result != 0)
            {
                enqueue(Kind::error, result);
            }
        }
        Message message{};
        while (k_msgq_get(&messages, &message, K_NO_WAIT) == 0)
        {
            EventInfo event{};
            bool deliver = true;
            if (stopping)
            {
                deliver = false;
            }
            else if (message.status != 0 || message.kind == Kind::error)
            {
                event.event = Event::error;
                event.error = message.status == -ETIMEDOUT ? Error::timeout
                              : (message.status == -ENOBUFS || message.status == -EMSGSIZE)
                                  ? Error::overflow
                                  : Error::transport;
                event.native_code = message.status;
                end();
            }
            else if (message.kind == Kind::discovery || message.kind == Kind::subscribed)
            {
                if (message.kind == Kind::discovery)
                {
                    stage = 2;
                }
                else
                {
                    ++stage;
                }
                if (stage == 4)
                {
                    event.event = Event::ready;
                }
                else
                {
                    const int result = subscribe(static_cast<size_t>(stage - 2));
                    if (result != 0)
                    {
                        enqueue(Kind::error, result);
                    }
                    deliver = false;
                }
            }
            else if (message.kind == Kind::first && service == Service::notifications)
            {
                event.event = Event::notification;
                event.error = decodeNotification(message.data, message.size, event.notification);
            }
            else if (message.kind == Kind::second && service == Service::notifications)
            {
                event.error = attribute_busy ? assembler.feed(message.data, message.size)
                                             : Error::stale_session;
                if (event.error == Error::none && assembler.complete())
                {
                    event.event = Event::attribute;
                    event.attribute = requested_attribute;
                    event.notification.uid = requested_uid;
                    event.data = assembler.text();
                    event.length = assembler.length();
                    attribute_busy = false;
                }
                else if (event.error == Error::none)
                {
                    deliver = false;
                }
            }
            else if (message.kind == Kind::first)
            {
                event.event = Event::supported_commands;
                event.error = decodeMediaCommands(message.data, message.size, command_mask);
                event.command_mask = command_mask;
            }
            else if (message.kind == Kind::second)
            {
                MediaUpdate update{};
                event.error = decodeMediaUpdate(message.data, message.size, update);
                event.event = Event::media_update;
                event.entity = update.entity;
                event.attribute = update.attribute;
                event.truncated = update.truncated;
                event.data = update.text;
                event.length = update.length;
            }
            else if (message.kind == Kind::written)
            {
                write_busy = false;
                event.event = Event::command_complete;
                if (read_after_write)
                {
                    read_after_write = false;
                    reading = true;
                    read_length = 0;
                    read_parameters = {};
                    read_parameters.func = readCallback;
                    read_parameters.handle_count = 1;
                    read_parameters.single.handle = handles[2];
                    const int result = bt_gatt_read(connection(), &read_parameters);
                    if (result != 0)
                    {
                        enqueue(Kind::error, result);
                    }
                    deliver = false;
                }
            }
            else if (message.kind == Kind::read)
            {
                if (message.size > sizeof(read_buffer) - read_length)
                {
                    event.error = Error::overflow;
                }
                else if (message.size != 0)
                {
                    memcpy(read_buffer + read_length, message.data, message.size);
                    read_length += message.size;
                    deliver = false;
                }
                else
                {
                    reading = false;
                    event.event = Event::media_update;
                    event.entity = read_entity;
                    event.attribute = read_attribute;
                    event.data = read_buffer;
                    event.length = read_length;
                }
            }
            if (event.error != Error::none)
            {
                event.event = Event::error;
                end();
            }
            if (deliver && callback_ != nullptr)
            {
                callback_(event, context_);
            }
            if (owner == nullptr)
            {
                break;
            }
        }
    }

    Error AppleClient::requestAttribute(uint32_t uid, uint8_t attribute) noexcept
    {
        if (owner != this || service != Service::notifications)
        {
            return Error::not_ready;
        }
        uint8_t request[8];
        size_t size = 0;
        Error result = encodeAttributeRequest(uid, attribute, 128, request, sizeof(request), size);
        if (result == Error::none)
        {
            result = send(2, request, size);
        }
        if (result == Error::none)
        {
            requested_attribute = attribute;
            requested_uid = uid;
            attribute_busy = true;
            (void)assembler.begin(uid, attribute);
        }
        return result;
    }

    Error AppleClient::performAction(const Notification &notification, bool positive) noexcept
    {
        if (owner != this || service != Service::notifications)
        {
            return Error::not_ready;
        }
        uint8_t request[6];
        const Error result =
            encodeNotificationAction(notification, positive, request, sizeof(request));
        return result == Error::none ? send(2, request, sizeof(request)) : result;
    }

    Error AppleClient::selectMediaAttributes(uint8_t entity, const uint8_t *attributes,
                                             size_t count) noexcept
    {
        if (owner != this || service != Service::media)
        {
            return Error::not_ready;
        }
        if (entity > 2 || count > 4 || (attributes == nullptr && count != 0))
        {
            return Error::invalid_argument;
        }
        uint8_t request[5] = {entity};
        uint8_t seen = 0;
        for (size_t i = 0; i < count; ++i)
        {
            if (!validMediaAttribute(entity, attributes[i]) || (seen & (1U << attributes[i])) != 0)
            {
                return Error::invalid_argument;
            }
            seen |= static_cast<uint8_t>(1U << attributes[i]);
            request[i + 1] = attributes[i];
        }
        return send(1, request, count + 1);
    }

    Error AppleClient::sendMediaCommand(uint8_t command) noexcept
    {
        if (owner != this || service != Service::media || command > 13 ||
            (command_mask & (1U << command)) == 0)
        {
            return Error::unsupported;
        }
        return send(0, &command, 1);
    }

    Error AppleClient::readMediaAttribute(uint8_t entity, uint8_t attribute) noexcept
    {
        if (owner != this || service != Service::media || !validMediaAttribute(entity, attribute))
        {
            return Error::invalid_argument;
        }
        const uint8_t request[] = {entity, attribute};
        const Error result = send(2, request, sizeof(request));
        if (result == Error::none)
        {
            read_after_write = true;
            read_entity = entity;
            read_attribute = attribute;
        }
        return result;
    }

    Error AppleClient::advertise(Service selected, const char *name) noexcept
    {
        if (advertising || owner != nullptr || BLEAdvertising.running())
        {
            return Error::busy;
        }
        if (name == nullptr || strlen(name) == 0 || strlen(name) > 29 ||
            (selected != Service::notifications && selected != Service::media))
        {
            return Error::invalid_argument;
        }
        if (!BLEDevice.initialized() && !BLEDevice.begin(name))
        {
            return Error::transport;
        }
        const uint8_t flags = BT_LE_AD_GENERAL | BT_LE_AD_NO_BREDR;
        const bt_data ad[] = {{BT_DATA_FLAGS, 1, &flags},
                              {BT_DATA_SOLICIT128, 16,
                               selected == Service::notifications ? ancs_uuid.val : ams_uuid.val}};
        const bt_data scan[] = {{BT_DATA_NAME_COMPLETE, static_cast<uint8_t>(strlen(name)),
                                 reinterpret_cast<const uint8_t *>(name)}};
        const int result = bt_le_adv_start(BT_LE_ADV_CONN_FAST_2, ad, 2, scan, 1);
        advertising = result == 0;
        if (advertising)
        {
            internal::gap::legacyAdvertisingStarted();
        }
        return result == 0 ? Error::none : Error::transport;
    }

    void AppleClient::stopAdvertising() noexcept
    {
        if (advertising)
        {
            if (!BLEAdvertising.running())
            {
                advertising = false;
            }
            else if (bt_le_adv_stop() == 0)
            {
                internal::gap::legacyAdvertisingStopped();
                advertising = false;
            }
        }
    }
} // namespace nucode::ble::companion
#endif
