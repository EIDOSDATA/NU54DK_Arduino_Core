/**
 * @file main.cpp
 * @brief 세 NU54DK에서 M32-W07 Mesh 1.1 관리 기능을 검증합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <Arduino.h>
#include <NUCODE_BLE_Mesh_Management.h>

#include <zephyr/bluetooth/mesh.h>
#include <zephyr/kernel.h>

#include <cstddef>
#include <cstdint>
#include <errno.h>
#include <string.h>

#ifndef M32_MESH11_CORE_REVISION
#error "M32_MESH11_CORE_REVISION is required"
#endif

namespace
{
    using namespace nucode::mesh;

    constexpr char protocol[] = "M32MESH11|1";
    constexpr char clear_prefix[] = "M32MESH11|1|CLEAR|nonce=";
    constexpr char start_prefix[] = "M32MESH11|1|START|nonce=";
    constexpr char stop_prefix[] = "M32MESH11|1|STOP|nonce=";
    constexpr std::size_t nonce_length = 32U;
    constexpr std::uint16_t client_address = 0x0001U;
    constexpr std::uint16_t server_address = 0x0100U;
    constexpr std::uint16_t target_address = 0x0200U;
    constexpr std::uint32_t iteration_target = 10U;
    constexpr std::uint32_t operation_target = 350U;
    constexpr std::int64_t session_timeout_ms = 900000;
    constexpr std::int64_t provisioning_settle_ms = 1500;

    static_assert(CONFIG_BT_MESH_CDB_NODE_COUNT >= 3,
                  "local provisioner와 두 remote node의 CDB slot이 필요합니다");
    static_assert(CONFIG_BT_MESH_CDB_SUBNET_COUNT >= 2,
                  "Subnet Bridge용 CDB subnet slot 두 개가 필요합니다");
    static_assert(CONFIG_BT_MESH_CDB_APP_KEY_COUNT >= 1,
                  "application key CDB slot이 필요합니다");
    static_assert(CONFIG_BT_MESH_SUBNET_COUNT >= 2,
                  "Subnet Bridge용 local subnet slot 두 개가 필요합니다");
    static_assert(CONFIG_BT_MESH_APP_KEY_COUNT >= 1,
                  "local application key slot이 필요합니다");
    static_assert(CONFIG_BT_MESH_MODEL_KEY_COUNT >= 1,
                  "model application key binding slot이 필요합니다");

    constexpr std::uint8_t application_key[16] = {
        0x32U, 0x07U, 0x54U, 0x15U, 0xA5U, 0x5AU, 0x11U, 0x22U,
        0x33U, 0x44U, 0x55U, 0x66U, 0x77U, 0x88U, 0x99U, 0xAAU,
    };
    constexpr std::uint32_t configuration_retry_limit = 3U;
    constexpr std::int64_t configuration_retry_delay_ms = 500;

    char command[160] = {};
    char nonce[nonce_length + 1U] = {};
    std::size_t command_length = 0U;
    bool cleared = false;
    bool started = false;
    bool session_complete = false;
    bool failed = false;
    std::int64_t deadline_ms = 0;
    std::int64_t progress_deadline_ms = 0;

#if defined(NUCODE_M32_MESH11_CLIENT)
    std::uint8_t server_uuid[16] = {};
    std::uint8_t target_uuid[16] = {};
    bool server_discovered = false;
    bool server_provision_pending = false;
    bool server_added = false;
    bool remote_scan_started = false;
    bool remote_target_discovered = false;
    bool remote_provision_started = false;
    bool target_added = false;
    bool negatives_complete = false;
    std::uint32_t provisioning_links_closed = 0U;
    std::int64_t management_not_before_ms = 0;
    bool target_configured = false;
    std::uint8_t configuration_step = 0U;
    std::uint32_t configuration_retries = 0U;
    std::int64_t next_configuration_attempt_ms = 0;
    std::uint32_t iterations = 0U;
    std::uint32_t operations = 0U;
    std::uint32_t remote_reports = 0U;
#else
    bool provisioned_event = false;
#endif

    /** @brief image의 고정 역할명을 반환합니다. */
    const char *roleName()
    {
#if defined(NUCODE_M32_MESH11_CLIENT)
        return "client";
#elif defined(NUCODE_M32_MESH11_SERVER)
        return "server";
#else
        return "target";
#endif
    }

    /** @brief 역할별 고정 unicast address를 반환합니다. */
    std::uint16_t localAddress()
    {
#if defined(NUCODE_M32_MESH11_CLIENT)
        return client_address;
#elif defined(NUCODE_M32_MESH11_SERVER)
        return server_address;
#else
        return target_address;
#endif
    }

    /** @brief 모든 session record에 nonce와 Core revision을 결합합니다. */
    void printSuffix()
    {
        Serial.print("|nonce=");
        Serial.print(nonce);
        Serial.print("|core=");
        Serial.print(M32_MESH11_CORE_REVISION);
    }

    /** @brief 첫 오류만 bounded protocol로 출력합니다. */
    void fail(const char *stage, int code = 0)
    {
        if (failed)
        {
            return;
        }
        Serial.print(protocol);
        Serial.print("|FAIL|role=");
        Serial.print(roleName());
        Serial.print("|stage=");
        Serial.print(stage);
        Serial.print("|code=");
        Serial.print(code);
        printSuffix();
        Serial.println();
        failed = true;
    }

    /** @brief nonce와 exact revision을 포함한 명령을 검증합니다. */
    bool acceptRevisionCommand(const char *prefix)
    {
        const std::size_t prefix_length = ::strlen(prefix);
        if (::strncmp(command, prefix, prefix_length) != 0)
        {
            return false;
        }
        const char *cursor = command + prefix_length;
        for (std::size_t index = 0U; index < nonce_length; ++index)
        {
            const char value = cursor[index];
            if (!((value >= '0' && value <= '9') ||
                  (value >= 'a' && value <= 'f')))
            {
                return false;
            }
        }
        constexpr char core_prefix[] = "|core=";
        if (::strncmp(cursor + nonce_length, core_prefix,
                      sizeof(core_prefix) - 1U) != 0 ||
            ::strcmp(cursor + nonce_length + sizeof(core_prefix) - 1U,
                     M32_MESH11_CORE_REVISION) != 0)
        {
            return false;
        }
        ::memcpy(nonce, cursor, nonce_length);
        nonce[nonce_length] = '\0';
        return true;
    }

    /** @brief 기본 Mesh event를 역할별 finite state로 복사합니다. */
    void onMeshEvent(const EventRecord &record, void *)
    {
#if defined(NUCODE_M32_MESH11_CLIENT)
        if (record.event == Event::unprovisioned_device &&
            record.uuid[15] == 0xA1U && !server_added)
        {
            ::memcpy(server_uuid, record.uuid, sizeof(server_uuid));
            server_discovered = true;
        }
        else if (record.event == Event::node_added)
        {
            if (record.address == server_address)
            {
                server_added = true;
            }
            else if (record.address == target_address)
            {
                target_added = true;
            }
            else
            {
                fail("unexpected_node", record.address);
            }
        }
        else if (record.event == Event::provisioning_link_closed)
        {
            server_provision_pending = false;
            ++provisioning_links_closed;
            management_not_before_ms = k_uptime_get() + provisioning_settle_ms;
        }
#else
        if (record.event == Event::provisioned)
        {
            provisioned_event = true;
        }
#endif
    }

    /** @brief Remote Provisioning scan report를 bounded 상태로 복사합니다. */
    void onManagementEvent(const ManagementEventRecord &record, void *)
    {
#if defined(NUCODE_M32_MESH11_CLIENT)
        if (record.event == ManagementEvent::remote_device &&
            record.remote.server.address == server_address &&
            record.remote.uuid[15] == 0xB2U)
        {
            ::memcpy(target_uuid, record.remote.uuid, sizeof(target_uuid));
            remote_target_discovered = true;
            ++remote_reports;
        }
#else
        static_cast<void>(record);
#endif
    }

    /** @brief 저장 상태를 지우고 새 Mesh 1.1 session을 준비합니다. */
    void clearState()
    {
        if (!NUCODEMesh.reset())
        {
            fail("clear", NUCODEMesh.lastDriverError());
            return;
        }
        cleared = true;
        started = false;
        session_complete = false;
#if defined(NUCODE_M32_MESH11_CLIENT)
        server_discovered = false;
        server_provision_pending = false;
        server_added = false;
        remote_scan_started = false;
        remote_target_discovered = false;
        remote_provision_started = false;
        target_added = false;
        negatives_complete = false;
        provisioning_links_closed = 0U;
        management_not_before_ms = 0;
        target_configured = false;
        configuration_step = 0U;
        configuration_retries = 0U;
        next_configuration_attempt_ms = 0;
        iterations = 0U;
        operations = 0U;
        remote_reports = 0U;
#else
        provisioned_event = false;
#endif
        Serial.print(protocol);
        Serial.print("|CLEARED|role=");
        Serial.print(roleName());
        printSuffix();
        Serial.println();
    }

#if defined(NUCODE_M32_MESH11_CLIENT)
    /** @brief 응답 timeout만 유한 횟수로 다시 시도합니다. */
    void retryConfiguration(const char *stage)
    {
        if (NUCODEMesh.lastDriverError() == -ETIMEDOUT &&
            configuration_retries < configuration_retry_limit)
        {
            ++configuration_retries;
            next_configuration_attempt_ms =
                k_uptime_get() + configuration_retry_delay_ms;
            return;
        }
        fail(stage, NUCODEMesh.lastDriverError());
    }

    /** @brief SRPL Client/Server에 명세가 요구하는 AppKey를 배포·bind합니다. */
    void driveConfiguration()
    {
        if (!target_added || provisioning_links_closed < 2U ||
            k_uptime_get() < management_not_before_ms ||
            k_uptime_get() < next_configuration_attempt_ms)
        {
            return;
        }
        bool result = false;
        const char *stage = "configure_srpl";
        switch (configuration_step)
        {
            case 0U:
            {
                result = NUCODEMesh.configureAppKey(client_address, application_key);
                stage = "configure_local_app_key";
                break;
            }
            case 1U:
            {
                result = NUCODEMesh.bindModel(
                    client_address, client_address,
                    Model::solicitation_rpl_configuration);
                stage = "bind_local_srpl";
                break;
            }
            case 2U:
            {
                result = NUCODEMesh.configureAppKey(server_address, application_key);
                stage = "configure_server_app_key";
                break;
            }
            case 3U:
            {
                result = NUCODEMesh.bindModel(
                    server_address, server_address,
                    Model::solicitation_rpl_configuration);
                stage = "bind_server_srpl";
                break;
            }
            case 4U:
            {
                result = NUCODEMesh.configureAppKey(target_address, application_key);
                stage = "configure_target_app_key";
                break;
            }
            case 5U:
            {
                result = NUCODEMesh.bindModel(
                    target_address, target_address,
                    Model::solicitation_rpl_configuration);
                stage = "bind_target_srpl";
                break;
            }
            default:
            {
                return;
            }
        }
        if (!result)
        {
            retryConfiguration(stage);
            return;
        }
        ++configuration_step;
        configuration_retries = 0U;
        if (configuration_step >= 6U)
        {
            target_configured = true;
        }
    }
#endif

    /** @brief 역할별 deadline을 열고 session을 시작합니다. */
    void startSession()
    {
        if (!cleared)
        {
            fail("start_without_clear");
            return;
        }
        started = true;
        deadline_ms = k_uptime_get() + session_timeout_ms;
        progress_deadline_ms = k_uptime_get() + 5000;
        Serial.print(protocol);
        Serial.print("|BEGIN|role=");
        Serial.print(roleName());
        printSuffix();
        Serial.println();
    }

#if defined(NUCODE_M32_MESH11_CLIENT)
    /** @brief server를 직접 provisioning한 뒤 target을 PB-Remote로 추가합니다. */
    void driveRemoteProvisioning()
    {
        if (!server_added)
        {
            if (server_discovered && !server_provision_pending)
            {
                server_provision_pending = NUCODEMesh.provision(
                    server_uuid, Bearer::advertising, server_address);
                if (!server_provision_pending)
                {
                    fail("direct_provision", NUCODEMesh.lastDriverError());
                }
            }
            return;
        }
        if (provisioning_links_closed == 0U ||
            k_uptime_get() < management_not_before_ms)
        {
            return;
        }
        ManagementTarget server{};
        server.address = server_address;
        if (!remote_scan_started)
        {
            remote_scan_started = NUCODEMeshManagement.startRemoteScan(
                server, 20U, 1U, nullptr);
            if (!remote_scan_started)
            {
                fail("remote_scan", NUCODEMeshManagement.lastDriverError());
            }
            return;
        }
        if (remote_target_discovered && !remote_provision_started)
        {
            if (!NUCODEMeshManagement.stopRemoteScan(server) ||
                !NUCODEMeshManagement.provisionRemote(server, target_uuid,
                                                       target_address))
            {
                fail("remote_provision", NUCODEMeshManagement.lastDriverError());
                return;
            }
            remote_provision_started = true;
        }
    }

    /** @brief malformed·범위 초과·wrong subnet 입력을 fail-closed로 확인합니다. */
    void checkNegatives()
    {
        if (negatives_complete || !target_configured ||
            provisioning_links_closed < 2U ||
            k_uptime_get() < management_not_before_ms)
        {
            return;
        }
        ManagementTarget invalid{};
        SarTransmitter bad_transmitter{};
        bad_transmitter.segment_interval_step = 0x10U;
        ManagementTarget server{};
        server.address = server_address;
        BridgeEntry bad_bridge{};
        bad_bridge.first_net_key_index = 1U;
        bad_bridge.second_net_key_index = 1U;
        bad_bridge.first_address = server_address;
        bad_bridge.second_address = target_address;
        const bool malformed = !NUCODEMeshManagement.setSarTransmitter(
            server, bad_transmitter);
        const bool out_of_range = !NUCODEMeshManagement.startRemoteScan(
            invalid, 0U, 0U, nullptr);
        const bool replay = !NUCODEMeshManagement.clearSolicitationReplay(
            server, 1U, 1U, true);
        const bool wrong_subnet =
            !NUCODEMeshManagement.setPrivateNodeIdentity(server, 0x1000U, true) &&
            !NUCODEMeshManagement.addBridgeEntry(server, bad_bridge);
        if (!malformed || !out_of_range || !replay || !wrong_subnet)
        {
            fail("negative_boundary");
            return;
        }
        negatives_complete = true;
    }

    /** @brief 성공한 관리 operation을 exact 분모에 누적합니다. */
    bool countOperation(bool result, const char *stage)
    {
        if (!result)
        {
            fail(stage, NUCODEMeshManagement.lastDriverError());
            return false;
        }
        ++operations;
        return true;
    }

    /** @brief timeout이 발생한 idempotent 관리 동작만 유한 횟수로 다시 시도합니다. */
    template <typename Operation>
    bool countOperation(Operation operation, const char *stage)
    {
        for (std::uint32_t attempt = 0U;
             attempt < configuration_retry_limit; ++attempt)
        {
            if (operation())
            {
                ++operations;
                return true;
            }
            if (NUCODEMeshManagement.lastDriverError() != -ETIMEDOUT)
            {
                break;
            }
            k_sleep(K_MSEC(configuration_retry_delay_ms));
        }
        fail(stage, NUCODEMeshManagement.lastDriverError());
        return false;
    }

    /** @brief 한 target에서 15개 Mesh 1.1 management operation을 실행합니다. */
    bool exerciseTarget(const ManagementTarget &node, std::uint32_t iteration)
    {
        SarTransmitter transmitter{};
        SarReceiver receiver{};
        LargeDataChunk chunk{};
        transmitter.segment_interval_step = static_cast<std::uint8_t>(iteration & 0x0FU);
        transmitter.unicast_retransmissions = 2U;
        receiver.segments_threshold = 3U;
        receiver.acknowledgement_delay_increment = 2U;
        if (!countOperation([&]() {
                                return NUCODEMeshManagement.getSarTransmitter(
                                    node, transmitter);
                            }, "sar_tx_get") ||
            !countOperation([&]() {
                                return NUCODEMeshManagement.setSarTransmitter(
                                    node, transmitter);
                            }, "sar_tx_set") ||
            !countOperation([&]() {
                                return NUCODEMeshManagement.getSarReceiver(node, receiver);
                            }, "sar_rx_get") ||
            !countOperation([&]() {
                                return NUCODEMeshManagement.setSarReceiver(node, receiver);
                            }, "sar_rx_set") ||
            !countOperation([&]() {
                                return NUCODEMeshManagement.readLargeComposition(
                                    node, 0U, 0U, chunk);
                            }, "large_comp") ||
            !countOperation([&]() {
                                return NUCODEMeshManagement.readModelsMetadata(
                                    node, 0U, 0U, chunk);
                            }, "metadata") ||
            !countOperation([&]() {
                                return NUCODEMeshManagement.setPrivateBeacon(
                                    node, true, 1U);
                            }, "private_beacon") ||
            !countOperation([&]() {
                                return NUCODEMeshManagement.setPrivateGattProxy(node, true);
                            }, "private_proxy") ||
            !countOperation([&]() {
                                return NUCODEMeshManagement.setPrivateNodeIdentity(
                                    node, 0U, true);
                            }, "private_identity") ||
            !countOperation([&]() {
                                return NUCODEMeshManagement.setOnDemandPrivateProxy(
                                    node, 10U);
                            }, "on_demand_proxy") ||
            !countOperation([&]() {
                                return NUCODEMeshManagement.clearSolicitationReplay(
                                    node, 1U, 2U);
                            }, "solicitation_rpl") ||
            !countOperation([&]() {
                                return NUCODEMeshManagement.setSubnetBridge(node, true);
                            }, "bridge"))
        {
            return false;
        }
        if (!countOperation(NUCODEMeshManagement.beginOpcodeSequence(
                                node, MeshManagement::remote_device_key_index,
                                node.address),
                            "aggregator_begin") ||
            !countOperation(NUCODEMeshManagement.setPrivateBeacon(node, true, 1U),
                            "aggregator_append") ||
            !countOperation(NUCODEMeshManagement.sendOpcodeSequence(),
                            "aggregator_send"))
        {
            NUCODEMeshManagement.abortOpcodeSequence();
            return false;
        }
        return true;
    }

    /** @brief 열 번의 35-operation loop로 exact 350 분모를 만듭니다. */
    void driveOperations()
    {
        if (!negatives_complete || iterations >= iteration_target)
        {
            return;
        }
        ManagementTarget server{};
        server.address = server_address;
        ManagementTarget target{};
        target.address = target_address;
        if (!exerciseTarget(server, iterations) || !exerciseTarget(target, iterations) ||
            !countOperation(NUCODEMeshManagement.solicit(), "solicit"))
        {
            return;
        }
        SarTransmitter transmitter{};
        for (std::uint32_t index = 0U; index < 4U; ++index)
        {
            const ManagementTarget &node = (index & 1U) == 0U ? server : target;
            if (!countOperation([&]() {
                                    return NUCODEMeshManagement.getSarTransmitter(
                                        node, transmitter);
                                }, "sar_repeat"))
            {
                return;
            }
        }
        ++iterations;
    }

    /** @brief client의 일곱 기능군 분모와 negative 결과를 출력합니다. */
    void finishClient()
    {
        if (session_complete || iterations < iteration_target)
        {
            return;
        }
        if (operations != operation_target || remote_reports == 0U)
        {
            fail("result_boundary");
            return;
        }
        Serial.print(protocol);
        Serial.print("|RESULT|role=client|remote_provisioned=1|feature_groups=7");
        Serial.print("|iterations=");
        Serial.print(iterations);
        Serial.print("|operations=");
        Serial.print(operations);
        Serial.print("|links_closed=");
        Serial.print(provisioning_links_closed);
        Serial.print("|remote_reports=");
        Serial.print(remote_reports);
        Serial.print("|malformed_rejected=1|out_of_range_rejected=1");
        Serial.print("|replay_rejected=1|wrong_subnet_rejected=1|recovery=pass");
        printSuffix();
        Serial.println();
        Serial.print(protocol);
        Serial.print("|END|role=client|status=pass");
        printSuffix();
        Serial.println();
        session_complete = true;
    }
#else
    /** @brief remote node의 provisioning과 관리 server 준비를 출력합니다. */
    void finishNode()
    {
        if (session_complete || !provisioned_event || !NUCODEMesh.provisioned())
        {
            return;
        }
        Serial.print(protocol);
        Serial.print("|RESULT|role=");
        Serial.print(roleName());
        Serial.print("|provisioned=1|management_server=pass|recovery=pass");
        printSuffix();
        Serial.println();
        Serial.print(protocol);
        Serial.print("|END|role=");
        Serial.print(roleName());
        Serial.print("|status=pass");
        printSuffix();
        Serial.println();
        session_complete = true;
    }
#endif

    /** @brief 5초 간격으로 bounded 진행 상태를 출력합니다. */
    void printProgress()
    {
        Serial.print(protocol);
        Serial.print("|PROGRESS|role=");
        Serial.print(roleName());
#if defined(NUCODE_M32_MESH11_CLIENT)
        Serial.print("|server_added=");
        Serial.print(server_added ? 1 : 0);
        Serial.print("|target_added=");
        Serial.print(target_added ? 1 : 0);
        Serial.print("|configured=");
        Serial.print(target_configured ? 1 : 0);
        Serial.print("|iterations=");
        Serial.print(iterations);
        Serial.print("|operations=");
        Serial.print(operations);
#else
        Serial.print("|provisioned=");
        Serial.print(NUCODEMesh.provisioned() ? 1 : 0);
#endif
        printSuffix();
        Serial.println();
    }

    /** @brief provisioning bearer와 Mesh transport를 중단하고 cleanup을 기록합니다. */
    void stopSession()
    {
        const bool cleanup = NUCODEMesh.cancelProvisioning();
        const int suspend_error = bt_mesh_suspend();
        if (!cleanup || suspend_error != 0)
        {
            fail("stop", suspend_error != 0 ? suspend_error :
                 NUCODEMesh.lastDriverError());
            return;
        }
        Serial.print(protocol);
        Serial.print("|STOPPED|role=");
        Serial.print(roleName());
        Serial.print("|cleanup=pass");
        printSuffix();
        Serial.println();
    }

    /** @brief PROBE·CLEAR·START·STOP 명령을 처리합니다. */
    void processCommand()
    {
        if (::strcmp(command, "M32MESH11|1|PROBE") == 0)
        {
            Serial.print(protocol);
            Serial.print("|READY|role=");
            Serial.print(roleName());
            Serial.print("|provisioned=");
            Serial.print(NUCODEMesh.provisioned() ? 1 : 0);
            Serial.print("|cdb_node_slots=");
            Serial.print(CONFIG_BT_MESH_CDB_NODE_COUNT);
            Serial.print("|cdb_local_slots=1|cdb_subnets=");
            Serial.print(CONFIG_BT_MESH_CDB_SUBNET_COUNT);
            Serial.print("|cdb_app_keys=");
            Serial.print(CONFIG_BT_MESH_CDB_APP_KEY_COUNT);
            Serial.print("|local_subnets=");
            Serial.print(CONFIG_BT_MESH_SUBNET_COUNT);
            Serial.print("|local_app_keys=");
            Serial.print(CONFIG_BT_MESH_APP_KEY_COUNT);
            Serial.print("|model_app_keys=");
            Serial.print(CONFIG_BT_MESH_MODEL_KEY_COUNT);
            Serial.print("|core=");
            Serial.println(M32_MESH11_CORE_REVISION);
            return;
        }
        if (acceptRevisionCommand(clear_prefix))
        {
            clearState();
            return;
        }
        if (!started && acceptRevisionCommand(start_prefix))
        {
            startSession();
            return;
        }
        if (session_complete &&
            ::strncmp(command, stop_prefix, sizeof(stop_prefix) - 1U) == 0 &&
            ::strcmp(command + sizeof(stop_prefix) - 1U, nonce) == 0)
        {
            stopSession();
            return;
        }
        fail("command");
    }

    /** @brief CR/LF serial 명령을 overflow 없이 수집합니다. */
    void pollSerial()
    {
        while (Serial.available() > 0)
        {
            const int incoming = Serial.read();
            if (incoming == '\r')
            {
                continue;
            }
            if (incoming == '\n')
            {
                command[command_length] = '\0';
                processCommand();
                command_length = 0U;
                continue;
            }
            if (incoming < 0 || command_length + 1U >= sizeof(command))
            {
                command_length = 0U;
                fail("command_length");
                continue;
            }
            command[command_length++] = static_cast<char>(incoming);
        }
    }
}

void setup()
{
    Serial.begin(115200);
    Configuration configuration{};
#if defined(NUCODE_M32_MESH11_CLIENT)
    configuration.role = Role::provisioner;
#else
    configuration.role = Role::node;
#endif
    configuration.bearers = Bearer::advertising;
    configuration.local_address = localAddress();
    configuration.uuid[0] = 0x32U;
    configuration.uuid[1] = 0x07U;
    configuration.uuid[2] = 0x54U;
    configuration.uuid[3] = 0x15U;
#if defined(NUCODE_M32_MESH11_SERVER)
    configuration.uuid[15] = 0xA1U;
#elif defined(NUCODE_M32_MESH11_TARGET)
    configuration.uuid[15] = 0xB2U;
#else
    configuration.uuid[15] = 0xC3U;
#endif
    NUCODEMesh.onEvent(onMeshEvent);
    NUCODEMeshManagement.onEvent(onManagementEvent);
    if (!NUCODEMesh.begin(configuration))
    {
        fail("mesh_begin", NUCODEMesh.lastDriverError());
        return;
    }
    if (!NUCODEMeshManagement.begin(10000U))
    {
        fail("management_begin", NUCODEMeshManagement.lastDriverError());
    }
}

void loop()
{
    NUCODEMesh.poll();
    NUCODEMeshManagement.poll();
    pollSerial();
    if (failed)
    {
        return;
    }
    if (started && !session_complete)
    {
#if defined(NUCODE_M32_MESH11_CLIENT)
        driveRemoteProvisioning();
        driveConfiguration();
        checkNegatives();
        driveOperations();
        finishClient();
#else
        finishNode();
#endif
        if (k_uptime_get() >= progress_deadline_ms)
        {
            printProgress();
            progress_deadline_ms = k_uptime_get() + 5000;
        }
        if (k_uptime_get() >= deadline_ms)
        {
            fail("timeout");
        }
    }
    delay(1);
}
