/** @file @brief native SDK adapter의 실제 실행 코드를 오류·지연·재연결로 검증합니다. */
#include <NUCODE_BLE_ObjectTransfer.h>
#include <NUCODE_BLE_Glucose.h>
#include <cassert>
#include <cstring>
#include <cerrno>
#if defined(CONFIG_BT_OTS)
#include <zephyr/bluetooth/services/ots.h>
#include <bluetooth/services/cgms.h>
#include <zephyr/kernel.h>
#endif
using namespace nucode::ble;
using namespace nucode::ble::profiles;

#if defined(CONFIG_BT_OTS)
/** @brief primary 발견 뒤 8개 mandatory characteristic과 CCC 완료를 주입합니다. */
void discoveryComplete()
{
    auto *parameters = native_discovery;
    bt_gatt_service_val service{nullptr, 40U};
    bt_gatt_attr attribute{nullptr, &service, 10U};
    parameters->func(&native_connection, &attribute, parameters);
    const std::uint16_t uuids[] = {BT_UUID_OTS_FEATURE_VAL,   BT_UUID_OTS_NAME_VAL,
                                   BT_UUID_OTS_TYPE_VAL,      BT_UUID_OTS_SIZE_VAL,
                                   BT_UUID_OTS_ID_VAL,        BT_UUID_OTS_PROPERTIES_VAL,
                                   BT_UUID_OTS_ACTION_CP_VAL, BT_UUID_OTS_LIST_CP_VAL};
    std::uint16_t handle = 12U;
    for (auto value : uuids)
    {
        const bt_uuid_16 uuid = BT_UUID_INIT_16(value);
        bt_gatt_chrc characteristic{&uuid.uuid, handle++};
        attribute.user_data = &characteristic;
        parameters->func(&native_connection, &attribute, parameters);
    }
    parameters->func(&native_connection, nullptr, parameters);
    for (auto *subscription : native_subscriptions)
    {
        assert((subscription->flags[0] & (1U << BT_GATT_SUBSCRIBE_FLAG_VOLATILE)) != 0U);
        subscription->subscribe(&native_connection, 0U, subscription);
    }
}
/** @brief 실제 완료 read event만 제한된 CoC teardown 창을 여는지 준비합니다. */
void finishRead(ObjectTransferClient &client, std::uint8_t *payload)
{
    native_ots_error = 0;
    assert(client.metadata());
    native_client->cur_object.size = {3U, 512U};
    native_client->cb->obj_metadata_read(native_client, &native_connection, 0, 0U);
    ObjectEvent event;
    assert(client.readEvent(event) && event.type == ObjectEventType::metadata);
    assert(client.read());
    assert(native_client->cb->obj_data_read(native_client, &native_connection, 0U, 1U, payload,
                                            false) == BT_OTS_CONTINUE);
    assert(client.bytesReceived() == 1U && client.busy());
    assert(native_client->cb->obj_data_read(native_client, &native_connection, 1U, 2U, payload + 1U,
                                            true) == BT_OTS_CONTINUE);
    assert(client.readEvent(event) && event.type == ObjectEventType::received);
}
#endif
int main(int argc, char **argv)
{
    assert(argc == 2);
    ObjectTransferServer server;
    ObjectTransferClient client;
    GlucoseService glucose;
    ObjectEvent event;
#if !defined(CONFIG_BT_OTS) || CONFIG_BT_MAX_CONN != 1
    static_cast<void>(argv);
    assert(!server.begin() && server.lastError() == -ENOTSUP);
    assert(!client.begin({1U}) && client.lastError() == -ENOTSUP);
    assert(!client.selectFirst() && !client.selectNext() && !client.metadata());
    assert(!client.create(512U) && !client.remove() && !client.cancel());
    assert(!client.readEvent(event) && !server.readEvent(event));
    assert(!glucose.begin() && glucose.lastError() == -ENOTSUP);
    assert(!glucose.add(100) && !glucose.sessionActive());
#else
    if (std::strcmp(argv[1], "glucose") == 0)
    {
        assert(!glucose.add(100) && glucose.lastError() == -EACCES);
        assert(!glucose.begin(0U) && !glucose.begin(1U, 256U));
        assert(glucose.begin() && glucose.sessionActive());
        assert(!glucose.begin());
        assert(!glucose.add(2048) && glucose.lastError() == -EINVAL);
        assert(glucose.add(123, -1) && native_glucose_value == 0xf07bU);
        native_glucose_error = -ENOMEM;
        assert(!glucose.add(100) && glucose.lastError() == -ENOMEM);
        native_glucose_callbacks->session_state_changed(false);
        assert(!glucose.sessionActive());
        return 0;
    }
    if (std::strcmp(argv[1], "server") == 0)
    {
        assert(server.begin() && !server.begin());
        const std::uint8_t payload[] = {10U, 20U, 30U};
        std::uint64_t id = 0U;
        assert(server.add("sample", payload, 3U, true, true, id));
        assert(id == 0x100U && server.lastError() == 0);
        assert(server.readEvent(event) && event.type == ObjectEventType::created && event.id == id);
        /** @brief 원격 rename 중 local 이름 검사·객체 삭제가 시작되지 않도록 거부합니다. */
        BLEConnection.live = true;
        std::uint64_t unchanged_id = 0x123U;
        assert(!server.add("other", payload, 3U, true, true, unchanged_id));
        assert(server.lastError() == -EINVAL && unchanged_id == 0x123U);
        assert(!server.remove(id) && server.lastError() == -EBUSY);
        assert(!server.readEvent(event));
        BLEConnection.live = false;
        assert(!server.add("sample", payload, 3U, true, true, id));
        assert(native_authorization != nullptr);
        assert(native_authorization->write_authorize(nullptr, nullptr));
        const bt_gatt_attr no_uuid{nullptr, nullptr, 0U};
        assert(native_authorization->read_authorize(nullptr, &no_uuid));
        const bt_uuid custom_uuid{2U};
        const bt_gatt_attr custom_attribute{&custom_uuid, nullptr, 0U};
        assert(native_authorization->write_authorize(nullptr, &custom_attribute));
        const bt_uuid_16 control = BT_UUID_INIT_16(BT_UUID_OTS_ACTION_CP_VAL);
        const bt_gatt_attr attribute{&control.uuid, nullptr, 0U};
        native_connection.security = 1U;
        assert(!native_authorization->write_authorize(&native_connection, &attribute));
        void *bytes = nullptr;
        assert(native_server_callbacks->obj_read(&native_server, &native_connection, id, &bytes, 3U,
                                                 0) < 0);
        native_connection.security = 2U;
        assert(native_authorization->write_authorize(&native_connection, &attribute));
        assert(native_server_callbacks->obj_read(&native_server, &native_connection, id, &bytes, 3U,
                                                 0) == 3);
        assert(std::memcmp(bytes, payload, 3U) == 0);
        assert(native_server_callbacks->obj_read(&native_server, &native_connection, id, &bytes, 4U,
                                                 0) < 0);
        assert(native_server_callbacks->obj_write(&native_server, &native_connection, id, payload,
                                                  3U, 511, 0U) < 0);
        assert(native_server_callbacks->obj_write(&native_server, &native_connection, id, payload,
                                                  3U, 3, 0U) == 3);
        assert(server.readEvent(event) && event.type == ObjectEventType::received &&
               event.length == 6U);
        assert(server.remove(id) && !server.remove(id));
        assert(server.readEvent(event) && event.type == ObjectEventType::deleted);
        bt_ots_obj_add_param temporary{};
        temporary.size = 32U;
        temporary.type.uuid.type = BT_UUID_TYPE_16;
        temporary.type.uuid_16.val = BT_UUID_OTS_TYPE_UNSPECIFIED_VAL;
        bt_ots_obj_created_desc description{};
        native_connection.security = 1U;
        assert(native_server_callbacks->obj_created(&native_server, &native_connection, 0x200U,
                                                    &temporary, &description) < 0);
        native_connection.security = 2U;
        assert(native_server_callbacks->obj_created(&native_server, &native_connection, 0x200U,
                                                    &temporary, &description) == 0);
        native_connection.security = 1U;
        assert(native_server_callbacks->obj_deleted(&native_server, &native_connection, 0x200U) ==
               0);
        return 0;
    }
    /** @brief mock도 bond된 비휘발 node의 보존·중복 등록 위험을 재현해야 합니다. */
    bt_gatt_subscribe_params retained{};
    retained.notify = [](bt_conn *, bt_gatt_subscribe_params *, const void *, std::uint16_t)
    {
        return BT_GATT_ITER_STOP;
    };
    assert(bt_gatt_subscribe(&native_connection, &retained) == 0);
    native_remove_subscriptions(&native_connection, true);
    assert(native_subscription_head == &retained);
    assert(bt_gatt_subscribe(&native_connection, &retained) == -EALREADY);
    atomic_set_bit(retained.flags, BT_GATT_SUBSCRIBE_FLAG_VOLATILE);
    native_remove_subscriptions(&native_connection, true);
    assert(native_subscription_head == nullptr);
    native_removed_subscriptions = 0U;
    native_subscription_count = 0U;
    assert(!client.begin({1U}));
    BLEConnection.peer = {1U};
    BLEConnection.live = true;
    native_connection.security = 1U;
    assert(!client.begin({1U}) && native_connection.references == 0U);
    native_connection.security = 2U;
    assert(client.begin({1U}) && client.busy());
    assert(!client.begin({1U}) && native_connection.references == 1U);
    discoveryComplete();
    assert(client.readEvent(event) && event.type == ObjectEventType::ready && !client.busy());
    if (std::strcmp(argv[1], "client_bonded_reconnect") == 0)
    {
        for (unsigned cycle = 0U; cycle < 3U; ++cycle)
        {
            assert(client.selectFirst());
            const auto notify = native_client->oacp_sub_params.notify;
            const auto complete = native_client->oacp_sub_params.subscribe;
            native_remove_subscriptions(&native_connection, true);
            assert(native_subscription_head == nullptr &&
                   native_indication_calls == 2U * (cycle + 1U));
            BLEConnection.live = false;
            native_callbacks->disconnected(&native_connection, 0x13U);
            assert(client.readEvent(event) && event.type == ObjectEventType::disconnected);
            complete(&native_connection, 0U, &native_client->oacp_sub_params);
            assert(notify(&native_connection, &native_client->oacp_sub_params, nullptr, 0U) ==
                   BT_GATT_ITER_STOP);
            assert(!client.readEvent(event) && !client.busy());
            assert(native_indication_calls == 2U * (cycle + 1U));
            BLEConnection.live = true;
            BLEConnection.peer = {cycle + 2U};
            assert(client.begin(BLEConnection.peer));
            bt_conn stale_connection;
            bt_gatt_subscribe_params unrelated_parameters{};
            complete(&native_connection, 0U, &unrelated_parameters);
            assert(notify(&native_connection, &unrelated_parameters, nullptr, 0U) ==
                   BT_GATT_ITER_STOP);
            complete(&stale_connection, 0U, &native_client->oacp_sub_params);
            assert(!client.readEvent(event) && client.busy());
            discoveryComplete();
            assert(client.readEvent(event) && event.type == ObjectEventType::ready);
            complete(&native_connection, 0U, &native_client->oacp_sub_params);
            assert(!client.readEvent(event));
            assert(native_registers == 1U && native_unregisters == 0U);
        }
        assert(native_removed_subscriptions == 6U);
        return 0;
    }
    if (std::strcmp(argv[1], "client_retry") == 0)
    {
        std::uint8_t payload[] = {1U, 2U, 3U};
        assert(client.metadata());
        native_client->cur_object.size = {3U, 512U};
        native_client->cb->obj_metadata_read(native_client, &native_connection, 0, 0U);
        assert(client.readEvent(event) && event.type == ObjectEventType::metadata);
        native_ots_error = -ENOMEM;
        assert(!client.write(payload, 3U) && !client.busy());
        assert(client.readEvent(event) && event.status == -ENOMEM);
        finishRead(client, payload);
        native_ots_error = -ENOMEM;
        assert(client.write(payload, 3U) && client.busy() && !client.readEvent(event));
        const unsigned writes = native_writes;
        payload[0] = 99U;
        assert(static_cast<const std::uint8_t *>(native_payload)[0] == 1U);
        client.poll();
        assert(native_writes == writes);
        waited_us += 20000U;
        client.poll();
        assert(native_writes == writes + 1U && client.busy());
        native_ots_error = -EIO;
        waited_us += 20000U;
        client.poll();
        assert(client.readEvent(event) && event.status == -EIO && !client.busy());
        finishRead(client, payload);
        native_ots_error = -ENOMEM;
        assert(client.write(payload, 3U) && client.busy());
        native_ots_error = 0;
        waited_us += 20000U;
        client.poll();
        assert(client.busy() && !client.readEvent(event));
        native_client->cb->obj_data_written(native_client, &native_connection, 3U);
        assert(client.readEvent(event) && event.type == ObjectEventType::written);
        finishRead(client, payload);
        native_ots_error = -ENOMEM;
        assert(client.read() && client.busy());
        const unsigned reads = native_reads;
        assert(client.cancel());
        waited_us += 20000U;
        client.poll();
        assert(native_reads == reads);
        BLEConnection.live = false;
        native_remove_subscriptions(&native_connection, true);
        native_callbacks->disconnected(&native_connection, 0x13U);
        assert(client.readEvent(event) && event.type == ObjectEventType::disconnected);
        assert(!client.busy() && native_connection.references == 0U);
        BLEConnection.live = true;
        native_ots_error = 0;
        assert(client.begin({1U}));
        discoveryComplete();
        assert(client.readEvent(event) && event.type == ObjectEventType::ready);
        assert(native_registers == 1U && native_unregisters == 0U);
        finishRead(client, payload);
        native_ots_error = -ENOMEM;
        assert(client.write(payload, 3U));
        waited_us += 10001000U;
        client.poll();
        assert(client.readEvent(event) && event.status == -ETIMEDOUT);
        assert(BLEConnection.disconnects == 2U && !client.busy());
        const unsigned timed_out_writes = native_writes;
        waited_us += 20000U;
        client.poll();
        assert(native_writes == timed_out_writes);
        return 0;
    }
    assert(!client.select(0U));
    assert(client.selectFirst() && !client.selectNext());
    bt_conn unrelated_connection;
    native_client->cb->obj_selected(native_client, &unrelated_connection, 1);
    assert(client.busy() && !client.readEvent(event));
    native_client->cb->obj_selected(native_client, &native_connection, 1);
    assert(client.readEvent(event) && event.type == ObjectEventType::selected);
    assert(client.metadata());
    const std::uint8_t pending_payload[] = {1U, 2U, 3U};
    native_client->cur_object.size = {512U, 512U};
    assert(!client.read() && client.lastError() == -EBUSY);
    assert(!client.write(pending_payload, sizeof(pending_payload)) && client.lastError() == -EBUSY);
    native_client->cur_object.id = 0x100U;
    native_client->cur_object.size = {3U, 512U};
    std::strcpy(native_client->cur_object.name_c, "sample");
    native_client->cb->obj_metadata_read(native_client, &native_connection, 0, 0U);
    assert(client.readEvent(event) && event.type == ObjectEventType::metadata &&
           event.id == 0x100U);
    native_client->cur_object.size = {600U, 0U};
    std::uint8_t payload[] = {1U, 2U, 3U};
    assert(client.read());
    assert(native_client->cb->obj_data_read(native_client, &native_connection, 0U, 3U, payload,
                                            true) == BT_OTS_CONTINUE);
    assert(client.readEvent(event) && event.type == ObjectEventType::received &&
           event.length == 3U);
    assert(client.read());
    assert(native_client->cb->obj_data_read(native_client, &native_connection, 511U, 3U, payload,
                                            true) == BT_OTS_STOP);
    assert(client.readEvent(event) && event.type == ObjectEventType::error &&
           event.status == -EMSGSIZE);
    assert(!client.write(payload, 3U, 511U));
    assert(client.write(payload, 3U));
    payload[0] = 99U;
    assert(static_cast<const std::uint8_t *>(native_payload)[0] == 1U);
    native_client->cb->obj_data_written(native_client, &native_connection, 3U);
    assert(client.readEvent(event) && event.type == ObjectEventType::written);
    assert(client.create(512U));
    const auto *raw = static_cast<const std::uint8_t *>(native_write->data);
    assert(native_write->length == 7U && raw[0] == 1U && raw[2] == 2U);
    native_write->func(&native_connection, 0U, native_write);
    const std::uint8_t created[] = {0x60U, 1U, 1U};
    native_client->oacp_sub_params.notify(&native_connection, &native_client->oacp_sub_params,
                                          created, 3U);
    assert(client.readEvent(event) && event.type == ObjectEventType::created && !client.busy());
    assert(client.rename("test"));
    native_write->func(&native_connection, 0U, native_write);
    assert(client.readEvent(event) && event.type == ObjectEventType::written);
    assert(!client.rename("123456789012345678901234567890123"));
    assert(client.rename("12345678901234567890123456789012"));
    assert(native_write->length == 32U);
    native_write->func(&native_connection, 0U, native_write);
    assert(client.readEvent(event) && event.type == ObjectEventType::written);
    assert(client.remove());
    const std::uint8_t removed[] = {0x60U, 2U, 1U};
    native_client->oacp_sub_params.notify(&native_connection, &native_client->oacp_sub_params,
                                          removed, 3U);
    assert(client.busy() && !client.readEvent(event));
    native_write->func(&native_connection, 0U, native_write);
    assert(client.readEvent(event) && event.type == ObjectEventType::deleted);
    assert(client.selectNext());
    waited_us = 11000000U;
    client.poll();
    assert(client.readEvent(event) && event.status == -ETIMEDOUT &&
           BLEConnection.disconnects == 1U);
    assert(native_callbacks != nullptr);
    BLEConnection.live = false;
    native_remove_subscriptions(&native_connection, true);
    native_callbacks->disconnected(&native_connection, 0x13U);
    assert(client.readEvent(event) && event.type == ObjectEventType::disconnected);
    assert(native_connection.references == 0U && native_unregisters == 0U);
    assert(!client.selectFirst());
    BLEConnection.live = true;
    BLEConnection.peer = {2U};
    assert(!client.begin({1U}) && client.begin({2U}));
    discoveryComplete();
    assert(client.readEvent(event) && event.peer == BLEConnection.peer &&
           event.type == ObjectEventType::ready);
    assert(native_registers == 1U && native_unregisters == 0U);
#endif
    return 0;
}
