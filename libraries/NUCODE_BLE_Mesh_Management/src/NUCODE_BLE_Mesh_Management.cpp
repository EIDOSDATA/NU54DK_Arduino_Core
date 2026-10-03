/**
 * @file NUCODE_BLE_Mesh_Management.cpp
 * @brief Bluetooth Mesh 1.1 관리 API의 Zephyr backend입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include "NUCODE_BLE_Mesh_Management.h"

#include <zephyr/bluetooth/mesh.h>
#include <zephyr/bluetooth/mesh/brg_cfg_cli.h>
#include <zephyr/bluetooth/mesh/large_comp_data_cli.h>
#include <zephyr/bluetooth/mesh/od_priv_proxy_cli.h>
#include <zephyr/bluetooth/mesh/op_agg_cli.h>
#include <zephyr/bluetooth/mesh/priv_beacon_cli.h>
#include <zephyr/bluetooth/mesh/proxy.h>
#include <zephyr/bluetooth/mesh/rpr_cli.h>
#include <zephyr/bluetooth/mesh/sar_cfg_cli.h>
#include <zephyr/bluetooth/mesh/sol_pdu_rpl_cli.h>
#include <zephyr/kernel.h>
#include <zephyr/net_buf.h>
#include <zephyr/sys/atomic.h>

#include <string.h>

extern "C"
{
    struct bt_mesh_rpr_cli *nucode_mesh_remote_provisioning_client(void);
}

namespace nucode::mesh
{
    namespace
    {
        struct ManagementContext
        {
            atomic_t started;
            atomic_t dropped_events;
            ManagementEventCallback callback = nullptr;
            void *callback_context = nullptr;
            ManagementError error = ManagementError::none;
            int driver_error = 0;
        };

        ManagementContext management_context{};
        K_MSGQ_DEFINE(management_event_queue, sizeof(ManagementEventRecord),
                      CONFIG_NUCODE_BLE_MESH_MANAGEMENT_EVENT_QUEUE_SIZE,
                      alignof(ManagementEventRecord));

        bool validTarget(const ManagementTarget &target) noexcept
        {
            return target.address >= 0x0001U && target.address <= 0x7FFFU &&
                   target.net_key_index <= 0x0FFFU &&
                   target.app_key_index <= 0x0FFFU && target.ttl <= 0x7FU;
        }

        bool fail(ManagementError error, int driver_error = 0) noexcept
        {
            management_context.error = error;
            management_context.driver_error = driver_error;
            return false;
        }

        bool success() noexcept
        {
            management_context.error = ManagementError::none;
            management_context.driver_error = 0;
            return true;
        }

        bool requireStarted() noexcept
        {
            if (atomic_get(&management_context.started) == 0)
            {
                return fail(ManagementError::not_started);
            }
            return true;
        }

        bool requireTarget(const ManagementTarget &target) noexcept
        {
            if (!requireStarted())
            {
                return false;
            }
            if (!validTarget(target))
            {
                return fail(ManagementError::invalid_argument);
            }
            return true;
        }

        bool complete(int error) noexcept
        {
            if (error != 0)
            {
                return fail(ManagementError::driver_error, error);
            }
            return success();
        }

        bt_mesh_rpr_node remoteServer(const ManagementTarget &target) noexcept
        {
            bt_mesh_rpr_node server{};
            server.addr = target.address;
            server.net_idx = target.net_key_index;
            server.ttl = target.ttl;
            return server;
        }

        bt_mesh_sar_tx nativeSarTransmitter(const SarTransmitter &state) noexcept
        {
            bt_mesh_sar_tx native{};
            native.seg_int_step = state.segment_interval_step;
            native.unicast_retrans_count = state.unicast_retransmissions;
            native.unicast_retrans_without_prog_count =
                state.unicast_retransmissions_without_progress;
            native.unicast_retrans_int_step = state.unicast_retransmission_interval_step;
            native.unicast_retrans_int_inc =
                state.unicast_retransmission_interval_increment;
            native.multicast_retrans_count = state.multicast_retransmissions;
            native.multicast_retrans_int = state.multicast_retransmission_interval;
            return native;
        }

        void copySarTransmitter(const bt_mesh_sar_tx &native,
                                SarTransmitter &state) noexcept
        {
            state.segment_interval_step = native.seg_int_step;
            state.unicast_retransmissions = native.unicast_retrans_count;
            state.unicast_retransmissions_without_progress =
                native.unicast_retrans_without_prog_count;
            state.unicast_retransmission_interval_step = native.unicast_retrans_int_step;
            state.unicast_retransmission_interval_increment = native.unicast_retrans_int_inc;
            state.multicast_retransmissions = native.multicast_retrans_count;
            state.multicast_retransmission_interval = native.multicast_retrans_int;
        }

        bool validSarTransmitter(const SarTransmitter &state) noexcept
        {
            return state.segment_interval_step <= 0x0FU &&
                   state.unicast_retransmissions <= 0x0FU &&
                   state.unicast_retransmissions_without_progress <= 0x0FU &&
                   state.unicast_retransmission_interval_step <= 0x0FU &&
                   state.unicast_retransmission_interval_increment <= 0x0FU &&
                   state.multicast_retransmissions <= 0x0FU &&
                   state.multicast_retransmission_interval <= 0x0FU;
        }

        bt_mesh_sar_rx nativeSarReceiver(const SarReceiver &state) noexcept
        {
            bt_mesh_sar_rx native{};
            native.seg_thresh = state.segments_threshold;
            native.ack_delay_inc = state.acknowledgement_delay_increment;
            native.discard_timeout = state.discard_timeout;
            native.rx_seg_int_step = state.receiver_segment_interval_step;
            native.ack_retrans_count = state.acknowledgement_retransmissions;
            return native;
        }

        void copySarReceiver(const bt_mesh_sar_rx &native, SarReceiver &state) noexcept
        {
            state.segments_threshold = native.seg_thresh;
            state.acknowledgement_delay_increment = native.ack_delay_inc;
            state.discard_timeout = native.discard_timeout;
            state.receiver_segment_interval_step = native.rx_seg_int_step;
            state.acknowledgement_retransmissions = native.ack_retrans_count;
        }

        bool validSarReceiver(const SarReceiver &state) noexcept
        {
            return state.segments_threshold <= 0x1FU &&
                   state.acknowledgement_delay_increment <= 0x07U &&
                   state.discard_timeout <= 0x0FU &&
                   state.receiver_segment_interval_step <= 0x0FU &&
                   state.acknowledgement_retransmissions <= 0x03U;
        }

        bt_mesh_brg_cfg_table_entry nativeBridgeEntry(const BridgeEntry &entry) noexcept
        {
            bt_mesh_brg_cfg_table_entry native{};
            native.directions = entry.bidirectional ? BT_MESH_BRG_CFG_DIR_TWOWAY :
                                                      BT_MESH_BRG_CFG_DIR_ONEWAY;
            native.net_idx1 = entry.first_net_key_index;
            native.net_idx2 = entry.second_net_key_index;
            native.addr1 = entry.first_address;
            native.addr2 = entry.second_address;
            return native;
        }

        bool validBridgeEntry(const BridgeEntry &entry) noexcept
        {
            return entry.first_net_key_index <= 0x0FFFU &&
                   entry.second_net_key_index <= 0x0FFFU &&
                   entry.first_net_key_index != entry.second_net_key_index &&
                   entry.first_address >= 0x0001U && entry.first_address <= 0x7FFFU &&
                   entry.second_address >= 0x0001U && entry.second_address <= 0x7FFFU;
        }

        bool readLargeData(const ManagementTarget &target, std::uint8_t page,
                           std::uint16_t offset, LargeDataChunk &chunk,
                           bool metadata) noexcept
        {
            if (!requireStarted())
            {
                return false;
            }
            if (!validTarget(target))
            {
                return fail(ManagementError::invalid_argument);
            }

            NET_BUF_SIMPLE_DEFINE(buffer, LargeDataChunk::capacity);
            bt_mesh_large_comp_data_rsp response{};
            response.data = &buffer;
            const int error = metadata ?
                bt_mesh_models_metadata_get(target.net_key_index, target.address, page,
                                            offset, &response) :
                bt_mesh_large_comp_data_get(target.net_key_index, target.address, page,
                                            offset, &response);
            if (error != 0)
            {
                return fail(ManagementError::driver_error, error);
            }

            chunk = LargeDataChunk{};
            chunk.page = response.page;
            chunk.offset = response.offset;
            chunk.total_size = response.total_size;
            const std::size_t copy_size = buffer.len < LargeDataChunk::capacity ?
                                              buffer.len : LargeDataChunk::capacity;
            if (copy_size > 0U)
            {
                memcpy(chunk.data, buffer.data, copy_size);
            }
            chunk.size = static_cast<std::uint8_t>(copy_size);
            chunk.truncated = response.total_size >
                              static_cast<std::uint32_t>(response.offset) + copy_size;
            return success();
        }
    }

    extern "C" void nucode_mesh_management_remote_scan_report(
        bt_mesh_rpr_cli *client, const bt_mesh_rpr_node *server,
        bt_mesh_rpr_unprov *unprovisioned, net_buf_simple *advertising_data)
    {
        (void)client;
        if (server == nullptr || unprovisioned == nullptr)
        {
            return;
        }

        ManagementEventRecord record{};
        record.event = ManagementEvent::remote_device;
        record.remote.server.address = server->addr;
        record.remote.server.net_key_index = server->net_idx;
        record.remote.server.ttl = server->ttl;
        memcpy(record.remote.uuid, unprovisioned->uuid, sizeof(record.remote.uuid));
        record.remote.rssi = unprovisioned->rssi;
        record.remote.oob_information = unprovisioned->oob;
        if (advertising_data != nullptr)
        {
            const std::size_t copy_size =
                advertising_data->len < RemoteDevice::advertising_capacity ?
                    advertising_data->len : RemoteDevice::advertising_capacity;
            if (copy_size > 0U)
            {
                memcpy(record.remote.advertising_data, advertising_data->data, copy_size);
            }
            record.remote.advertising_size = static_cast<std::uint8_t>(copy_size);
            record.remote.advertising_truncated =
                advertising_data->len > RemoteDevice::advertising_capacity;
        }
        if (k_msgq_put(&management_event_queue, &record, K_NO_WAIT) != 0)
        {
            atomic_inc(&management_context.dropped_events);
        }
    }

    bool MeshManagement::begin(std::uint32_t timeout_ms) noexcept
    {
        if (timeout_ms < 100U || timeout_ms > 60000U)
        {
            return fail(ManagementError::invalid_argument);
        }
        k_msgq_purge(&management_event_queue);
        atomic_set(&management_context.dropped_events, 0);
        bt_mesh_rpr_cli_timeout_set(static_cast<std::int32_t>(timeout_ms));
        bt_mesh_sar_cfg_cli_timeout_set(static_cast<std::int32_t>(timeout_ms));
        bt_mesh_op_agg_cli_timeout_set(static_cast<std::int32_t>(timeout_ms));
        bt_mesh_od_priv_proxy_cli_timeout_set(static_cast<std::int32_t>(timeout_ms));
        bt_mesh_sol_pdu_rpl_cli_timeout_set(static_cast<std::int32_t>(timeout_ms));
        bt_mesh_brg_cfg_cli_timeout_set(static_cast<std::int32_t>(timeout_ms));
        atomic_set(&management_context.started, 1);
        return success();
    }

    void MeshManagement::poll() noexcept
    {
        ManagementEventRecord record{};
        while (k_msgq_get(&management_event_queue, &record, K_NO_WAIT) == 0)
        {
            if (management_context.callback != nullptr)
            {
                management_context.callback(record, management_context.callback_context);
            }
        }
    }

    void MeshManagement::onEvent(ManagementEventCallback callback, void *context) noexcept
    {
        management_context.callback = callback;
        management_context.callback_context = context;
    }

    bool MeshManagement::startRemoteScan(const ManagementTarget &server,
                                         std::uint8_t timeout_seconds,
                                         std::uint8_t maximum_devices,
                                         const std::uint8_t *uuid) noexcept
    {
        if (!requireStarted())
        {
            return false;
        }
        if (!validTarget(server) || timeout_seconds == 0U || maximum_devices == 0U ||
            maximum_devices > CONFIG_BT_MESH_RPR_SRV_SCANNED_ITEMS_MAX)
        {
            return fail(ManagementError::invalid_argument);
        }
        const bt_mesh_rpr_node native_server = remoteServer(server);
        bt_mesh_rpr_scan_status status{};
        return complete(bt_mesh_rpr_scan_start(nucode_mesh_remote_provisioning_client(),
                                               &native_server, uuid, timeout_seconds,
                                               maximum_devices, &status));
    }

    bool MeshManagement::stopRemoteScan(const ManagementTarget &server) noexcept
    {
        if (!requireTarget(server))
        {
            return false;
        }
        const bt_mesh_rpr_node native_server = remoteServer(server);
        bt_mesh_rpr_scan_status status{};
        return complete(bt_mesh_rpr_scan_stop(nucode_mesh_remote_provisioning_client(),
                                              &native_server, &status));
    }

    bool MeshManagement::closeRemoteLink(const ManagementTarget &server) noexcept
    {
        if (!requireTarget(server))
        {
            return false;
        }
        const bt_mesh_rpr_node native_server = remoteServer(server);
        bt_mesh_rpr_link response{};
        return complete(bt_mesh_rpr_link_close(nucode_mesh_remote_provisioning_client(),
                                               &native_server, &response));
    }

    bool MeshManagement::provisionRemote(const ManagementTarget &server,
                                         const std::uint8_t uuid[16],
                                         std::uint16_t node_address) noexcept
    {
        if (!requireTarget(server))
        {
            return false;
        }
        if (uuid == nullptr || node_address > 0x7FFFU)
        {
            return fail(ManagementError::invalid_argument);
        }
        const bt_mesh_rpr_node native_server = remoteServer(server);
        return complete(bt_mesh_provision_remote(nucode_mesh_remote_provisioning_client(),
                                                 &native_server, uuid,
                                                 server.net_key_index, node_address));
    }

    bool MeshManagement::getSarTransmitter(const ManagementTarget &target,
                                           SarTransmitter &state) noexcept
    {
        if (!requireTarget(target))
        {
            return false;
        }
        bt_mesh_sar_tx response{};
        const int error = bt_mesh_sar_cfg_cli_transmitter_get(
            target.net_key_index, target.address, &response);
        if (error != 0)
        {
            return fail(ManagementError::driver_error, error);
        }
        copySarTransmitter(response, state);
        return success();
    }

    bool MeshManagement::setSarTransmitter(const ManagementTarget &target,
                                           const SarTransmitter &state) noexcept
    {
        if (!requireTarget(target))
        {
            return false;
        }
        if (!validSarTransmitter(state))
        {
            return fail(ManagementError::invalid_argument);
        }
        const bt_mesh_sar_tx request = nativeSarTransmitter(state);
        bt_mesh_sar_tx response{};
        return complete(bt_mesh_sar_cfg_cli_transmitter_set(
            target.net_key_index, target.address, &request, &response));
    }

    bool MeshManagement::getSarReceiver(const ManagementTarget &target,
                                        SarReceiver &state) noexcept
    {
        if (!requireTarget(target))
        {
            return false;
        }
        bt_mesh_sar_rx response{};
        const int error = bt_mesh_sar_cfg_cli_receiver_get(
            target.net_key_index, target.address, &response);
        if (error != 0)
        {
            return fail(ManagementError::driver_error, error);
        }
        copySarReceiver(response, state);
        return success();
    }

    bool MeshManagement::setSarReceiver(const ManagementTarget &target,
                                        const SarReceiver &state) noexcept
    {
        if (!requireTarget(target))
        {
            return false;
        }
        if (!validSarReceiver(state))
        {
            return fail(ManagementError::invalid_argument);
        }
        const bt_mesh_sar_rx request = nativeSarReceiver(state);
        bt_mesh_sar_rx response{};
        return complete(bt_mesh_sar_cfg_cli_receiver_set(
            target.net_key_index, target.address, &request, &response));
    }

    bool MeshManagement::beginOpcodeSequence(const ManagementTarget &target,
                                             std::uint16_t app_key_index,
                                             std::uint16_t element_address) noexcept
    {
        if (!requireTarget(target))
        {
            return false;
        }
        if ((app_key_index > 0x0FFFU &&
             app_key_index != MeshManagement::remote_device_key_index) ||
            element_address < 0x0001U ||
            element_address > 0x7FFFU)
        {
            return fail(ManagementError::invalid_argument);
        }
        return complete(bt_mesh_op_agg_cli_seq_start(target.net_key_index, app_key_index,
                                                     target.address, element_address));
    }

    std::size_t MeshManagement::opcodeSequenceTailroom() const noexcept
    {
        return bt_mesh_op_agg_cli_seq_is_started() ? bt_mesh_op_agg_cli_seq_tailroom() : 0U;
    }

    bool MeshManagement::sendOpcodeSequence() noexcept
    {
        if (!requireStarted())
        {
            return false;
        }
        if (!bt_mesh_op_agg_cli_seq_is_started())
        {
            return fail(ManagementError::invalid_argument);
        }
        return complete(bt_mesh_op_agg_cli_seq_send());
    }

    void MeshManagement::abortOpcodeSequence() noexcept
    {
        if (bt_mesh_op_agg_cli_seq_is_started())
        {
            bt_mesh_op_agg_cli_seq_abort();
        }
    }

    bool MeshManagement::readLargeComposition(const ManagementTarget &target,
                                              std::uint8_t page,
                                              std::uint16_t offset,
                                              LargeDataChunk &chunk) noexcept
    {
        return readLargeData(target, page, offset, chunk, false);
    }

    bool MeshManagement::readModelsMetadata(const ManagementTarget &target,
                                            std::uint8_t page,
                                            std::uint16_t offset,
                                            LargeDataChunk &chunk) noexcept
    {
        return readLargeData(target, page, offset, chunk, true);
    }

    bool MeshManagement::setPrivateBeacon(const ManagementTarget &target, bool enabled,
                                          std::uint8_t random_interval_steps) noexcept
    {
        if (!requireTarget(target))
        {
            return false;
        }
        bt_mesh_priv_beacon request{};
        request.enabled = enabled ? 1U : 0U;
        request.rand_interval = random_interval_steps;
        bt_mesh_priv_beacon response{};
        bt_mesh_priv_beacon *response_pointer =
            bt_mesh_op_agg_cli_seq_is_started() ? nullptr : &response;
        return complete(bt_mesh_priv_beacon_cli_set(target.net_key_index, target.address,
                                                    &request, response_pointer));
    }

    bool MeshManagement::setPrivateGattProxy(const ManagementTarget &target,
                                             bool enabled) noexcept
    {
        if (!requireTarget(target))
        {
            return false;
        }
        std::uint8_t response = 0U;
        return complete(bt_mesh_priv_beacon_cli_gatt_proxy_set(
            target.net_key_index, target.address, enabled ? 1U : 0U, &response));
    }

    bool MeshManagement::setPrivateNodeIdentity(const ManagementTarget &target,
                                                std::uint16_t identity_net_key_index,
                                                bool enabled) noexcept
    {
        if (!requireTarget(target))
        {
            return false;
        }
        if (identity_net_key_index > 0x0FFFU)
        {
            return fail(ManagementError::invalid_argument);
        }
        bt_mesh_priv_node_id request{};
        request.net_idx = identity_net_key_index;
        request.state = enabled ? 1U : 0U;
        bt_mesh_priv_node_id response{};
        return complete(bt_mesh_priv_beacon_cli_node_id_set(
            target.net_key_index, target.address, &request, &response));
    }

    bool MeshManagement::setOnDemandPrivateProxy(const ManagementTarget &target,
                                                 std::uint8_t lifetime) noexcept
    {
        if (!requireTarget(target))
        {
            return false;
        }
        std::uint8_t response = 0U;
        return complete(bt_mesh_od_priv_proxy_cli_set(target.net_key_index, target.address,
                                                      lifetime, &response));
    }

    bool MeshManagement::solicit(std::uint16_t net_key_index) noexcept
    {
        if (!requireStarted())
        {
            return false;
        }
        if (net_key_index > 0x0FFFU)
        {
            return fail(ManagementError::invalid_argument);
        }
        return complete(bt_mesh_proxy_solicit(net_key_index));
    }

    bool MeshManagement::clearSolicitationReplay(const ManagementTarget &target,
                                                 std::uint16_t range_start,
                                                 std::uint8_t range_length,
                                                 bool acknowledged) noexcept
    {
        if (!requireTarget(target))
        {
            return false;
        }
        if (range_start < 0x0001U || range_start > 0x7FFFU || range_length == 1U)
        {
            return fail(ManagementError::invalid_argument);
        }
        bt_mesh_msg_ctx context{};
        context.net_idx = target.net_key_index;
        context.app_idx = target.app_key_index;
        context.addr = target.address;
        context.send_ttl = target.ttl;
        if (!acknowledged)
        {
            return complete(bt_mesh_sol_pdu_rpl_clear_unack(&context, range_start,
                                                            range_length));
        }
        std::uint16_t response_start = 0U;
        std::uint8_t response_length = 0U;
        return complete(bt_mesh_sol_pdu_rpl_clear(&context, range_start, range_length,
                                                  &response_start, &response_length));
    }

    bool MeshManagement::setSubnetBridge(const ManagementTarget &target,
                                         bool enabled) noexcept
    {
        if (!requireTarget(target))
        {
            return false;
        }
        bt_mesh_brg_cfg_state response = BT_MESH_BRG_CFG_DISABLED;
        const bt_mesh_brg_cfg_state request = enabled ? BT_MESH_BRG_CFG_ENABLED :
                                                       BT_MESH_BRG_CFG_DISABLED;
        return complete(bt_mesh_brg_cfg_cli_set(target.net_key_index, target.address,
                                                request, &response));
    }

    bool MeshManagement::addBridgeEntry(const ManagementTarget &target,
                                        const BridgeEntry &entry) noexcept
    {
        if (!requireTarget(target))
        {
            return false;
        }
        if (!validBridgeEntry(entry))
        {
            return fail(ManagementError::invalid_argument);
        }
        bt_mesh_brg_cfg_table_entry request = nativeBridgeEntry(entry);
        bt_mesh_brg_cfg_table_status response{};
        return complete(bt_mesh_brg_cfg_cli_table_add(target.net_key_index, target.address,
                                                      &request, &response));
    }

    bool MeshManagement::removeBridgeEntry(const ManagementTarget &target,
                                           const BridgeEntry &entry) noexcept
    {
        if (!requireTarget(target))
        {
            return false;
        }
        if (!validBridgeEntry(entry))
        {
            return fail(ManagementError::invalid_argument);
        }
        bt_mesh_brg_cfg_table_status response{};
        return complete(bt_mesh_brg_cfg_cli_table_remove(
            target.net_key_index, target.address, entry.first_net_key_index,
            entry.second_net_key_index, entry.first_address, entry.second_address,
            &response));
    }

    std::uint32_t MeshManagement::droppedEvents() const noexcept
    {
        return static_cast<std::uint32_t>(atomic_get(&management_context.dropped_events));
    }

    ManagementError MeshManagement::lastError() const noexcept
    {
        return management_context.error;
    }

    int MeshManagement::lastDriverError() const noexcept
    {
        return management_context.driver_error;
    }
}

nucode::mesh::MeshManagement NUCODEMeshManagement;
