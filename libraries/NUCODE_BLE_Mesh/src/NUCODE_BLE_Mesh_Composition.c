/**
 * @file NUCODE_BLE_Mesh_Composition.c
 * @brief C99 compound literal이 필요한 Bluetooth Mesh composition을 정의합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <zephyr/bluetooth/mesh.h>

#if defined(CONFIG_NUCODE_BLE_MESH_MANAGEMENT)
#include <zephyr/bluetooth/mesh/brg_cfg_cli.h>
#include <zephyr/bluetooth/mesh/brg_cfg_srv.h>
#include <zephyr/bluetooth/mesh/large_comp_data_cli.h>
#include <zephyr/bluetooth/mesh/large_comp_data_srv.h>
#include <zephyr/bluetooth/mesh/od_priv_proxy_cli.h>
#include <zephyr/bluetooth/mesh/od_priv_proxy_srv.h>
#include <zephyr/bluetooth/mesh/op_agg_cli.h>
#include <zephyr/bluetooth/mesh/op_agg_srv.h>
#include <zephyr/bluetooth/mesh/priv_beacon_cli.h>
#include <zephyr/bluetooth/mesh/priv_beacon_srv.h>
#include <zephyr/bluetooth/mesh/rpr_cli.h>
#include <zephyr/bluetooth/mesh/rpr_srv.h>
#include <zephyr/bluetooth/mesh/sar_cfg_cli.h>
#include <zephyr/bluetooth/mesh/sar_cfg_srv.h>
#include <zephyr/bluetooth/mesh/sol_pdu_rpl_cli.h>
#endif

#if defined(CONFIG_NUCODE_BLE_MESH_UPDATE)
#include <zephyr/bluetooth/mesh/blob_cli.h>
#include <zephyr/bluetooth/mesh/blob_srv.h>
#include <zephyr/bluetooth/mesh/dfd_srv.h>
#include <zephyr/bluetooth/mesh/dfu_srv.h>

/** @brief C++ update backend가 소유하는 raw BLOB Server model입니다. */
extern struct bt_mesh_blob_srv nucode_mesh_blob_server_instance;

/** @brief C++ update backend가 소유하는 raw BLOB Client model입니다. */
extern struct bt_mesh_blob_cli nucode_mesh_blob_client_instance;

/** @brief C++ update backend가 소유하는 Mesh DFU Target model입니다. */
extern struct bt_mesh_dfu_srv nucode_mesh_dfu_server_instance;

/** @brief C++ update backend가 소유하는 Firmware Distributor model입니다. */
extern struct bt_mesh_dfd_srv nucode_mesh_distributor_instance;
#endif

#include <errno.h>
#include <stdint.h>
#include <stdbool.h>

/** @brief C++ backend가 model status를 bounded event로 변환합니다. */
extern int nucode_mesh_model_status(const struct bt_mesh_model *model,
                                    struct bt_mesh_msg_ctx *message_context,
                                    struct net_buf_simple *buffer);

static struct bt_mesh_cfg_cli configuration_client;
static struct bt_mesh_health_cli health_client;

#if defined(CONFIG_NUCODE_BLE_MESH_MANAGEMENT)
/** @brief Remote Provisioning scan report를 C++ bounded event queue로 전달합니다. */
extern void nucode_mesh_management_remote_scan_report(
    struct bt_mesh_rpr_cli *client, const struct bt_mesh_rpr_node *server,
    struct bt_mesh_rpr_unprov *unprovisioned, struct net_buf_simple *advertising_data);

static struct bt_mesh_rpr_cli remote_provisioning_client = {
    .scan_report = nucode_mesh_management_remote_scan_report,
};
static struct bt_mesh_sar_cfg_cli sar_configuration_client;
static struct bt_mesh_large_comp_data_cli large_composition_client;
static struct bt_mesh_priv_beacon_cli private_beacon_client;
static struct bt_mesh_od_priv_proxy_cli on_demand_private_proxy_client;
static struct bt_mesh_sol_pdu_rpl_cli solicitation_rpl_client;
static struct bt_mesh_brg_cfg_cli bridge_configuration_client;
#endif

/** @brief Health attention 시작을 application별 표시 장치에 맡깁니다. */
static void attention_on(const struct bt_mesh_model *model)
{
    (void)model;
}

/** @brief Health attention 종료를 application별 표시 장치에 맡깁니다. */
static void attention_off(const struct bt_mesh_model *model)
{
    (void)model;
}

static const struct bt_mesh_health_srv_cb health_server_callbacks = {
    .attn_on = attention_on,
    .attn_off = attention_off,
};
static struct bt_mesh_health_srv health_server = {
    .cb = &health_server_callbacks,
};
BT_MESH_HEALTH_PUB_DEFINE(health_publication, 8);

static const struct bt_mesh_model_op on_off_operations[] = {
    {BT_MESH_MODEL_OP_2(0x82, 0x04), BT_MESH_LEN_MIN(1), nucode_mesh_model_status},
    BT_MESH_MODEL_OP_END,
};
static const struct bt_mesh_model_op level_operations[] = {
    {BT_MESH_MODEL_OP_2(0x82, 0x08), BT_MESH_LEN_MIN(2), nucode_mesh_model_status},
    BT_MESH_MODEL_OP_END,
};
static const struct bt_mesh_model_op lightness_operations[] = {
    {BT_MESH_MODEL_OP_2(0x82, 0x4E), BT_MESH_LEN_MIN(2), nucode_mesh_model_status},
    BT_MESH_MODEL_OP_END,
};
static const struct bt_mesh_model_op sensor_operations[] = {
    {BT_MESH_MODEL_OP_1(0x52), BT_MESH_LEN_MIN(1), nucode_mesh_model_status},
    BT_MESH_MODEL_OP_END,
};
static const struct bt_mesh_model_op time_operations[] = {
    {BT_MESH_MODEL_OP_1(0x5D), BT_MESH_LEN_MIN(5), nucode_mesh_model_status},
    BT_MESH_MODEL_OP_END,
};
static const struct bt_mesh_model_op scene_operations[] = {
    {BT_MESH_MODEL_OP_1(0x5E), BT_MESH_LEN_MIN(3), nucode_mesh_model_status},
    BT_MESH_MODEL_OP_END,
};
static const struct bt_mesh_model_op scheduler_operations[] = {
    {BT_MESH_MODEL_OP_2(0x82, 0x4A), BT_MESH_LEN_EXACT(2), nucode_mesh_model_status},
    BT_MESH_MODEL_OP_END,
};

static bool on_off_state;
BT_MESH_MODEL_PUB_DEFINE(on_off_server_publication, NULL,
                         BT_MESH_MODEL_BUF_LEN(BT_MESH_MODEL_OP_2(0x82, 0x04), 1));

/** @brief Generic OnOff Server의 현재 상태를 요청자에게 반환합니다. */
static int on_off_get(const struct bt_mesh_model *model,
                      struct bt_mesh_msg_ctx *message_context,
                      struct net_buf_simple *buffer)
{
    (void)buffer;
    BT_MESH_MODEL_BUF_DEFINE(response, BT_MESH_MODEL_OP_2(0x82, 0x04), 1);
    bt_mesh_model_msg_init(&response, BT_MESH_MODEL_OP_2(0x82, 0x04));
    net_buf_simple_add_u8(&response, on_off_state ? 1U : 0U);
    return bt_mesh_model_send(model, message_context, &response, NULL, NULL);
}

/** @brief Generic OnOff Set acknowledged 요청을 처리합니다. */
static int on_off_set_acknowledged(const struct bt_mesh_model *model,
                                   struct bt_mesh_msg_ctx *message_context,
                                   struct net_buf_simple *buffer)
{
    nucode_mesh_model_status(model, message_context, buffer);
    const uint8_t requested = net_buf_simple_pull_u8(buffer);
    net_buf_simple_pull_u8(buffer);
    if (requested > 1U)
    {
        return -EINVAL;
    }
    on_off_state = requested != 0U;
    return on_off_get(model, message_context, buffer);
}

/** @brief Generic OnOff Set Unacknowledged 요청을 처리합니다. */
static int on_off_set_unacknowledged(const struct bt_mesh_model *model,
                                     struct bt_mesh_msg_ctx *message_context,
                                     struct net_buf_simple *buffer)
{
    nucode_mesh_model_status(model, message_context, buffer);
    const uint8_t requested = net_buf_simple_pull_u8(buffer);
    net_buf_simple_pull_u8(buffer);
    if (requested > 1U)
    {
        return -EINVAL;
    }
    on_off_state = requested != 0U;
    return 0;
}

static const struct bt_mesh_model_op on_off_server_operations[] = {
    {BT_MESH_MODEL_OP_2(0x82, 0x01), BT_MESH_LEN_EXACT(0), on_off_get},
    {BT_MESH_MODEL_OP_2(0x82, 0x02), BT_MESH_LEN_MIN(2), on_off_set_acknowledged},
    {BT_MESH_MODEL_OP_2(0x82, 0x03), BT_MESH_LEN_MIN(2), on_off_set_unacknowledged},
    BT_MESH_MODEL_OP_END,
};

static const struct bt_mesh_model root_models[] = {
    BT_MESH_MODEL_CFG_SRV,
    BT_MESH_MODEL_CFG_CLI(&configuration_client),
    BT_MESH_MODEL_HEALTH_SRV(&health_server, &health_publication, NULL),
    BT_MESH_MODEL_HEALTH_CLI(&health_client),
    BT_MESH_MODEL(BT_MESH_MODEL_ID_GEN_ONOFF_CLI, on_off_operations, NULL, NULL),
    BT_MESH_MODEL(BT_MESH_MODEL_ID_GEN_LEVEL_CLI, level_operations, NULL, NULL),
    BT_MESH_MODEL(BT_MESH_MODEL_ID_LIGHT_LIGHTNESS_CLI, lightness_operations, NULL, NULL),
    BT_MESH_MODEL(BT_MESH_MODEL_ID_SENSOR_CLI, sensor_operations, NULL, NULL),
    BT_MESH_MODEL(BT_MESH_MODEL_ID_TIME_CLI, time_operations, NULL, NULL),
    BT_MESH_MODEL(BT_MESH_MODEL_ID_SCENE_CLI, scene_operations, NULL, NULL),
    BT_MESH_MODEL(BT_MESH_MODEL_ID_SCHEDULER_CLI, scheduler_operations, NULL, NULL),
    BT_MESH_MODEL(BT_MESH_MODEL_ID_GEN_ONOFF_SRV, on_off_server_operations,
                  &on_off_server_publication, NULL),
#if defined(CONFIG_NUCODE_BLE_MESH_MANAGEMENT)
    BT_MESH_MODEL_RPR_CLI(&remote_provisioning_client),
    BT_MESH_MODEL_RPR_SRV,
    BT_MESH_MODEL_SAR_CFG_CLI(&sar_configuration_client),
    BT_MESH_MODEL_SAR_CFG_SRV,
    BT_MESH_MODEL_OP_AGG_CLI,
    BT_MESH_MODEL_OP_AGG_SRV,
    BT_MESH_MODEL_LARGE_COMP_DATA_CLI(&large_composition_client),
    BT_MESH_MODEL_LARGE_COMP_DATA_SRV,
    BT_MESH_MODEL_PRIV_BEACON_CLI(&private_beacon_client),
    BT_MESH_MODEL_PRIV_BEACON_SRV,
    BT_MESH_MODEL_OD_PRIV_PROXY_CLI(&on_demand_private_proxy_client),
    BT_MESH_MODEL_OD_PRIV_PROXY_SRV,
    BT_MESH_MODEL_SOL_PDU_RPL_CLI(&solicitation_rpl_client),
    BT_MESH_MODEL_BRG_CFG_CLI(&bridge_configuration_client),
    BT_MESH_MODEL_BRG_CFG_SRV,
#endif
};

#if defined(CONFIG_NUCODE_BLE_MESH_UPDATE)
static const struct bt_mesh_model blob_models[] = {
    BT_MESH_MODEL_BLOB_CLI(&nucode_mesh_blob_client_instance),
    BT_MESH_MODEL_BLOB_SRV(&nucode_mesh_blob_server_instance),
};
static const struct bt_mesh_model dfu_target_models[] = {
    BT_MESH_MODEL_DFU_SRV(&nucode_mesh_dfu_server_instance),
};
static const struct bt_mesh_model distributor_models[] = {
    BT_MESH_MODEL_DFD_SRV(&nucode_mesh_distributor_instance),
};
#endif

static const struct bt_mesh_elem elements[] = {
    BT_MESH_ELEM(0, root_models, BT_MESH_MODEL_NONE),
#if defined(CONFIG_NUCODE_BLE_MESH_UPDATE)
    BT_MESH_ELEM(1, blob_models, BT_MESH_MODEL_NONE),
    BT_MESH_ELEM(2, dfu_target_models, BT_MESH_MODEL_NONE),
    BT_MESH_ELEM(3, distributor_models, BT_MESH_MODEL_NONE),
#endif
};
static const struct bt_mesh_comp composition = {
    .cid = BT_COMP_ID_LF,
    .pid = 0x0054U,
    .vid = 0x0006U,
    .elem_count = ARRAY_SIZE(elements),
    .elem = elements,
};

/** @brief C++ lifecycle backend에 고정 composition을 반환합니다. */
const struct bt_mesh_comp *nucode_mesh_composition(void)
{
    return &composition;
}

/** @brief 공개 model enum 순서에 해당하는 client model을 반환합니다. */
const struct bt_mesh_model *nucode_mesh_model(uint8_t model)
{
    const size_t model_offset = 4U;
    if (model < 8U)
    {
        return &root_models[model_offset + model];
    }
#if defined(CONFIG_NUCODE_BLE_MESH_UPDATE)
    switch (model)
    {
        case 8U:
            return &blob_models[0];
        case 9U:
            return &blob_models[1];
        case 10U:
            return &dfu_target_models[1];
        case 11U:
            return &distributor_models[3];
        default:
            break;
    }
#endif
#if defined(CONFIG_NUCODE_BLE_MESH_MANAGEMENT)
    if (model == 12U)
    {
        return bt_mesh_model_find(&elements[0], BT_MESH_MODEL_ID_SOL_PDU_RPL_CLI);
    }
#endif
    return NULL;
}

/** @brief local Generic OnOff Server 상태를 변경하고 필요하면 publish합니다. */
int nucode_mesh_onoff_server_set(bool enabled, bool publish)
{
    const size_t server_offset = 11U;
    on_off_state = enabled;
    if (!publish)
    {
        return 0;
    }
    bt_mesh_model_msg_init(on_off_server_publication.msg,
                           BT_MESH_MODEL_OP_2(0x82, 0x04));
    net_buf_simple_add_u8(on_off_server_publication.msg, enabled ? 1U : 0U);
    return bt_mesh_model_publish(&root_models[server_offset]);
}

/** @brief local Generic OnOff Server 현재 상태를 반환합니다. */
bool nucode_mesh_onoff_server_get(void)
{
    return on_off_state;
}

/** @brief C++ backend에 Health Client instance를 반환합니다. */
struct bt_mesh_health_cli *nucode_mesh_health_client(void)
{
    return &health_client;
}

#if defined(CONFIG_NUCODE_BLE_MESH_MANAGEMENT)
/** @brief C++ 관리 backend에 Remote Provisioning Client를 반환합니다. */
struct bt_mesh_rpr_cli *nucode_mesh_remote_provisioning_client(void)
{
    return &remote_provisioning_client;
}
#endif
