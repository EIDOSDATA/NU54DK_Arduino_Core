/** @file @brief NCS 3.4.0 OTS callback·반환값 계약의 최소 시험 대역입니다. */
#pragma once
#include <zephyr/bluetooth/gatt.h>
#include <sys/types.h>
#define BT_UUID_OTS_VAL 0x1825
#define BT_UUID_OTS_FEATURE_VAL 0x2abd
#define BT_UUID_OTS_NAME_VAL 0x2abe
#define BT_UUID_OTS_TYPE_VAL 0x2abf
#define BT_UUID_OTS_SIZE_VAL 0x2ac0
#define BT_UUID_OTS_ID_VAL 0x2ac3
#define BT_UUID_OTS_PROPERTIES_VAL 0x2ac4
#define BT_UUID_OTS_ACTION_CP_VAL 0x2ac5
#define BT_UUID_OTS_LIST_CP_VAL 0x2ac6
#define BT_UUID_OTS_CHANGED_VAL 0x2ac8
#define BT_UUID_OTS_TYPE_UNSPECIFIED_VAL 0x2aca
#define BT_OTS_OBJ_SET_PROP_READ(value) ((value) |= 1U << 2U)
#define BT_OTS_OBJ_SET_PROP_WRITE(value) ((value) |= 1U << 3U)
#define BT_OTS_OBJ_SET_PROP_PATCH(value) ((value) |= 1U << 5U)
#define BT_OTS_OBJ_SET_PROP_DELETE(value) ((value) |= 1U << 0U)
#define BT_OTS_OACP_SET_FEAT_READ(value) ((value) |= 1U << 4U)
#define BT_OTS_OACP_SET_FEAT_WRITE(value) ((value) |= 1U << 5U)
#define BT_OTS_OACP_SET_FEAT_PATCH(value) ((value) |= 1U << 8U)
#define BT_OTS_OACP_SET_FEAT_CREATE(value) ((value) |= 1U << 0U)
#define BT_OTS_OACP_SET_FEAT_DELETE(value) ((value) |= 1U << 1U)
#define BT_OTS_OLCP_SET_FEAT_GO_TO(value) ((value) |= 1U)
constexpr std::uint8_t BT_OTS_METADATA_REQ_NAME = 1U, BT_OTS_METADATA_REQ_TYPE = 2U,
                       BT_OTS_METADATA_REQ_SIZE = 4U, BT_OTS_METADATA_REQ_ID = 32U,
                       BT_OTS_METADATA_REQ_PROPS = 64U;
constexpr int BT_OTS_STOP = 0, BT_OTS_CONTINUE = 1, BT_OTS_OACP_WRITE_OP_MODE_NONE = 0;
struct bt_ots
{
};
union bt_ots_obj_type
{
    bt_uuid uuid;
    bt_uuid_16 uuid_16;
};
struct bt_ots_obj_add_param
{
    std::uint32_t size;
    bt_ots_obj_type type;
};
struct NativeObjectSize
{
    std::uint32_t cur, alloc;
};
struct bt_ots_obj_created_desc
{
    char *name;
    NativeObjectSize size;
    std::uint32_t props;
};
struct bt_ots_cb
{
    int (*obj_created)(bt_ots *, bt_conn *, std::uint64_t, const bt_ots_obj_add_param *,
                       bt_ots_obj_created_desc *);
    int (*obj_deleted)(bt_ots *, bt_conn *, std::uint64_t);
    void (*obj_selected)(bt_ots *, bt_conn *, std::uint64_t);
    ssize_t (*obj_read)(bt_ots *, bt_conn *, std::uint64_t, void **, std::size_t, off_t);
    ssize_t (*obj_write)(bt_ots *, bt_conn *, std::uint64_t, const void *, std::size_t, off_t,
                         std::size_t);
};
struct bt_ots_init_param
{
    struct
    {
        std::uint32_t oacp, olcp;
    } features;
    bt_ots_cb *cb;
};
struct bt_ots_client;
struct bt_ots_client_cb
{
    void (*obj_selected)(bt_ots_client *, bt_conn *, int);
    void (*obj_metadata_read)(bt_ots_client *, bt_conn *, int, std::uint8_t);
    int (*obj_data_read)(bt_ots_client *, bt_conn *, std::uint32_t, std::uint32_t, std::uint8_t *,
                         bool);
    void (*obj_data_written)(bt_ots_client *, bt_conn *, std::size_t);
};
struct bt_ots_client
{
    std::uint16_t start_handle, end_handle, feature_handle, obj_name_handle, obj_type_handle,
        obj_size_handle, obj_id_handle, obj_properties_handle, oacp_handle, olcp_handle;
    bt_gatt_subscribe_params oacp_sub_params, olcp_sub_params;
    bt_gatt_discover_params oacp_sub_disc_params, olcp_sub_disc_params;
    bt_ots_client_cb *cb;
    struct
    {
        std::uint64_t id;
        NativeObjectSize size;
        std::uint32_t props;
        char name_c[33];
    } cur_object;
};
inline bt_ots native_server;
inline bt_ots_cb *native_server_callbacks = nullptr;
inline bt_ots_client *native_client = nullptr;
inline std::uint64_t native_next_id = 0x100U;
inline int native_ots_error = 0;
inline unsigned native_unregisters = 0U;
inline unsigned native_registers = 0U;
inline const void *native_payload = nullptr;
inline std::size_t native_payload_length = 0U;
inline unsigned native_reads = 0U, native_writes = 0U;
inline bt_ots *bt_ots_free_instance_get()
{
    return &native_server;
}
inline int bt_ots_init(bt_ots *, bt_ots_init_param *parameters)
{
    native_server_callbacks = parameters->cb;
    return native_ots_error;
}
inline int bt_ots_obj_add(bt_ots *server, const bt_ots_obj_add_param *parameters)
{
    bt_ots_obj_created_desc description{};
    const int result = native_server_callbacks->obj_created(server, nullptr, native_next_id,
                                                            parameters, &description);
    return result == 0 ? static_cast<int>(native_next_id++) : result;
}
inline int bt_ots_obj_delete(bt_ots *server, std::uint64_t id)
{
    return native_server_callbacks->obj_deleted(server, nullptr, id);
}
inline int bt_ots_client_register(bt_ots_client *client)
{
    ++native_registers;
    if (native_registers > 1U)
    {
        return -ELOOP;
    }
    native_client = client;
    return native_ots_error;
}
inline int bt_ots_client_unregister(std::uint8_t)
{
    ++native_unregisters;
    native_client = nullptr;
    return 0;
}
inline int bt_ots_client_select_first(bt_ots_client *, bt_conn *)
{
    return native_ots_error;
}
inline int bt_ots_client_select_next(bt_ots_client *, bt_conn *)
{
    return native_ots_error;
}
inline int bt_ots_client_select_id(bt_ots_client *, bt_conn *, std::uint64_t)
{
    return native_ots_error;
}
inline int bt_ots_client_read_object_metadata(bt_ots_client *, bt_conn *, std::uint8_t)
{
    return native_ots_error;
}
inline int bt_ots_client_read_object_data(bt_ots_client *, bt_conn *)
{
    ++native_reads;
    return native_ots_error;
}
inline int bt_ots_client_write_object_data(bt_ots_client *, bt_conn *, const void *data,
                                           std::size_t length, off_t, int)
{
    ++native_writes;
    native_payload = data;
    native_payload_length = length;
    return native_ots_error;
}
inline unsigned native_indication_calls = 0U;
inline std::uint8_t bt_ots_client_indicate_handler(bt_conn *, bt_gatt_subscribe_params *,
                                                   const void *, std::uint16_t)
{
    ++native_indication_calls;
    return BT_GATT_ITER_CONTINUE;
}
