/**
 * @file main.cpp
 * @brief 세 NU54DK에서 M32-W06 Mesh provisioning과 model traffic을 검증합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <Arduino.h>
#include <NUCODE_BLE_Mesh.h>

#include <zephyr/bluetooth/mesh.h>
#include <zephyr/kernel.h>

#include <cstddef>
#include <cstdint>
#include <errno.h>
#include <string.h>

#ifndef M32_MESH_CORE_REVISION
#error "M32_MESH_CORE_REVISION is required"
#endif

namespace
{
    using namespace nucode::mesh;

    constexpr char protocol[] = "M32MESH|1";
    constexpr char clear_prefix[] = "M32MESH|1|CLEAR|nonce=";
    constexpr char start_prefix[] = "M32MESH|1|START|nonce=";
    constexpr char stop_prefix[] = "M32MESH|1|STOP|nonce=";
    constexpr std::size_t nonce_length = 32U;
    constexpr std::uint16_t provisioner_address = 0x0001U;
    constexpr std::uint16_t node_a_address = 0x0100U;
    constexpr std::uint16_t node_b_address = 0x0200U;
    constexpr std::uint32_t base_message_target = 300U;
    constexpr std::uint32_t secured_message_target = 200U;
    constexpr std::uint32_t total_message_target =
        base_message_target + secured_message_target;
    constexpr std::uint32_t node_message_target = total_message_target / 2U;
    constexpr std::int64_t message_ack_timeout_ms = 2000;
    constexpr std::uint32_t message_retry_limit = 3U;
    constexpr std::int64_t message_response_drain_ms = 50;
    constexpr std::uint32_t configuration_retry_limit = 3U;
    constexpr std::int64_t configuration_retry_delay_ms = 500;
    constexpr std::int64_t session_timeout_ms = 600000;

    static_assert(CONFIG_BT_MESH_CDB_NODE_COUNT >= 3,
                  "local provisioner와 두 remote node의 CDB slot이 필요합니다");
    static_assert(CONFIG_BT_MESH_CDB_SUBNET_COUNT >= 1,
                  "primary subnet CDB slot이 필요합니다");
    static_assert(CONFIG_BT_MESH_CDB_APP_KEY_COUNT >= 1,
                  "application key CDB slot이 필요합니다");
    static_assert(CONFIG_BT_MESH_SUBNET_COUNT >= 1,
                  "local primary subnet slot이 필요합니다");
    static_assert(CONFIG_BT_MESH_APP_KEY_COUNT >= 1,
                  "local application key slot이 필요합니다");
    static_assert(CONFIG_BT_MESH_MODEL_KEY_COUNT >= 1,
                  "model application key binding slot이 필요합니다");

    constexpr std::uint8_t application_key[16] = {
        0x32U, 0x06U, 0x54U, 0x15U, 0xA5U, 0x5AU, 0x11U, 0x22U,
        0x33U, 0x44U, 0x55U, 0x66U, 0x77U, 0x88U, 0x99U, 0xAAU,
    };

    char command[160] = {};
    char nonce[nonce_length + 1U] = {};
    std::size_t command_length = 0U;
    bool cleared = false;
    bool started = false;
    bool session_complete = false;
    bool failed = false;
    bool stop_requested = false;
    bool unprovisioned_rejected = false;
#if defined(NUCODE_M32_MESH_PROVISIONER)
    bool invalid_destination_rejected = false;
    bool wrong_key_rejected = false;
#else
    bool feature_enabled = false;
#endif
    bool payload_integrity = true;
    std::int64_t deadline_ms = 0;
    std::int64_t progress_deadline_ms = 0;

#if defined(NUCODE_M32_MESH_PROVISIONER)
    std::uint8_t discovered_node_a[16] = {};
    std::uint8_t discovered_node_b[16] = {};
    bool node_a_discovered = false;
    bool node_b_discovered = false;
    bool provisioning_pending = false;
    std::uint32_t provisioning_attempts = 0U;
    std::uint32_t provisioning_links_opened = 0U;
    std::uint32_t provisioning_links_closed = 0U;
    std::int64_t next_provisioning_ms = 0;
    std::int64_t configuration_not_before_ms = 0;
    bool node_a_added = false;
    bool node_b_added = false;
    bool local_configured = false;
    bool node_a_configured = false;
    bool node_b_configured = false;
    std::uint32_t configuration_retry_count = 0U;
    std::uint32_t configuration_retries = 0U;
    std::int64_t next_configuration_attempt_ms = 0;
    bool message_outstanding = false;
    bool expected_state = false;
    std::uint16_t expected_source = 0U;
    std::uint32_t message_retry_count = 0U;
    std::uint32_t message_retries = 0U;
    std::uint32_t sent_messages = 0U;
    std::uint32_t acknowledged_messages = 0U;
    std::uint32_t maximum_latency_ms = 0U;
    std::int64_t send_started_ms = 0;
    std::int64_t next_message_ms = 0;
#else
    bool provisioned_event = false;
    std::uint32_t received_messages = 0U;
#endif

    /** @brief 현재 image의 고정 역할을 반환합니다. */
    const char *roleName()
    {
#if defined(NUCODE_M32_MESH_PROVISIONER)
        return "provisioner";
#elif defined(NUCODE_M32_MESH_NODE_A)
        return "node_a";
#else
        return "node_b";
#endif
    }

    /** @brief 역할별 고정 local address를 반환합니다. */
    std::uint16_t localAddress()
    {
#if defined(NUCODE_M32_MESH_PROVISIONER)
        return provisioner_address;
#elif defined(NUCODE_M32_MESH_NODE_A)
        return node_a_address;
#else
        return node_b_address;
#endif
    }

    /** @brief 결과 record에 nonce와 exact Core revision을 결합합니다. */
    void printSuffix()
    {
        Serial.print("|nonce=");
        Serial.print(nonce);
        Serial.print("|core=");
        Serial.print(M32_MESH_CORE_REVISION);
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

    /** @brief nonce와 exact revision이 포함된 명령을 검증합니다. */
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
                     M32_MESH_CORE_REVISION) != 0)
        {
            return false;
        }
        ::memcpy(nonce, cursor, nonce_length);
        nonce[nonce_length] = '\0';
        return true;
    }

#if !defined(NUCODE_M32_MESH_PROVISIONER)
    /** @brief 초기화 직후 또는 CLEAR 뒤 unprovisioned 송신 거부를 검사합니다. */
    void checkUnprovisionedBoundary()
    {
        Destination destination{};
        destination.address = provisioner_address;
        unprovisioned_rejected = !NUCODEMesh.sendOnOff(destination, true, false) &&
                                 NUCODEMesh.lastError() == Error::not_provisioned;
    }
#endif

    /** @brief Mesh event를 역할별 유한 상태로 복사합니다. */
    void onMeshEvent(const EventRecord &record, void *)
    {
#if defined(NUCODE_M32_MESH_PROVISIONER)
        if (record.event == Event::unprovisioned_device)
        {
            if (record.uuid[15] == 0xA1U && !node_a_added)
            {
                ::memcpy(discovered_node_a, record.uuid, sizeof(discovered_node_a));
                node_a_discovered = true;
            }
            else if (record.uuid[15] == 0xB2U && !node_b_added)
            {
                ::memcpy(discovered_node_b, record.uuid, sizeof(discovered_node_b));
                node_b_discovered = true;
            }
        }
        else if (record.event == Event::node_added)
        {
            if (record.address == node_a_address)
            {
                node_a_added = true;
            }
            else if (record.address == node_b_address)
            {
                node_b_added = true;
            }
            else
            {
                fail("unexpected_node", record.address);
            }
        }
        else if (record.event == Event::provisioning_link_opened)
        {
            ++provisioning_links_opened;
        }
        else if (record.event == Event::provisioning_link_closed)
        {
            provisioning_pending = false;
            ++provisioning_links_closed;
            next_provisioning_ms = k_uptime_get() + 1000;
            if (node_a_added && node_b_added)
            {
                configuration_not_before_ms = k_uptime_get() + 1500;
            }
        }
        else if (record.event == Event::model_status && message_outstanding)
        {
            if (record.model != Model::generic_on_off ||
                record.address != expected_source || record.payload_size < 1U ||
                (record.payload[0] != 0U) != expected_state)
            {
                payload_integrity = false;
                fail("status_payload");
                return;
            }
            const std::uint32_t latency = static_cast<std::uint32_t>(
                k_uptime_get() - send_started_ms);
            if (latency > maximum_latency_ms)
            {
                maximum_latency_ms = latency;
            }
            ++acknowledged_messages;
            message_outstanding = false;
            message_retry_count = 0U;
            next_message_ms = k_uptime_get() + message_response_drain_ms;
        }
#else
        if (record.event == Event::provisioned)
        {
            provisioned_event = true;
        }
        else if (record.event == Event::model_status &&
                 record.model == Model::generic_on_off_server)
        {
            if (record.payload_size < 2U || record.payload[0] > 1U)
            {
                payload_integrity = false;
                fail("set_payload");
                return;
            }
            if (received_messages < node_message_target)
            {
                ++received_messages;
            }
        }
#endif
    }

    /** @brief 저장 상태를 지우고 동일 image에서 새 bounded session을 준비합니다. */
    void clearMeshState()
    {
        if (!NUCODEMesh.reset())
        {
            fail("clear", NUCODEMesh.lastDriverError());
            return;
        }
        cleared = true;
        started = false;
        session_complete = false;
#if defined(NUCODE_M32_MESH_PROVISIONER)
        node_a_discovered = false;
        node_b_discovered = false;
        provisioning_pending = false;
        provisioning_attempts = 0U;
        provisioning_links_opened = 0U;
        provisioning_links_closed = 0U;
        next_provisioning_ms = 0;
        configuration_not_before_ms = 0;
        node_a_added = false;
        node_b_added = false;
        local_configured = false;
        node_a_configured = false;
        node_b_configured = false;
        configuration_retry_count = 0U;
        configuration_retries = 0U;
        next_configuration_attempt_ms = 0;
        sent_messages = 0U;
        acknowledged_messages = 0U;
        message_outstanding = false;
        message_retry_count = 0U;
        message_retries = 0U;
        next_message_ms = 0;
#else
        provisioned_event = false;
        received_messages = 0U;
        feature_enabled = false;
        checkUnprovisionedBoundary();
#endif
        Serial.print(protocol);
        Serial.print("|CLEARED|role=");
        Serial.print(roleName());
        Serial.print("|unprovisioned_rejected=");
        Serial.print(unprovisioned_rejected ? 1 : 0);
        printSuffix();
        Serial.println();
    }

    /** @brief 역할별 session deadline을 열고 실제 Mesh 절차를 시작합니다. */
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

#if defined(NUCODE_M32_MESH_PROVISIONER)
    /** @brief 발견한 두 UUID를 한 번에 하나씩 고정 주소로 provisioning합니다. */
    void driveProvisioning()
    {
        if (!started || provisioning_pending)
        {
            return;
        }
        if (!node_a_discovered || !node_b_discovered)
        {
            return;
        }
        if (k_uptime_get() < next_provisioning_ms)
        {
            return;
        }
        const std::uint8_t *uuid = nullptr;
        std::uint16_t address = 0U;
        if (node_a_discovered && !node_a_added)
        {
            uuid = discovered_node_a;
            address = node_a_address;
        }
        else if (node_b_discovered && !node_b_added)
        {
            uuid = discovered_node_b;
            address = node_b_address;
        }
        if (uuid != nullptr)
        {
            ++provisioning_attempts;
            provisioning_pending = NUCODEMesh.provision(
                uuid, Bearer::advertising, address);
            if (!provisioning_pending)
            {
                if (NUCODEMesh.lastError() == Error::busy)
                {
                    next_provisioning_ms = k_uptime_get() + 1000;
                    return;
                }
                fail("provision", NUCODEMesh.lastDriverError());
            }
        }
    }

    /** @brief 손실된 Configuration 응답은 유한 횟수만 다시 요청합니다. */
    bool retryConfiguration(const char *stage)
    {
        const int error = NUCODEMesh.lastDriverError();
        if (error == -ETIMEDOUT && configuration_retry_count < configuration_retry_limit)
        {
            ++configuration_retry_count;
            ++configuration_retries;
            next_configuration_attempt_ms =
                k_uptime_get() + configuration_retry_delay_ms;
            return true;
        }
        fail(stage, error);
        return false;
    }

    /** @brief local client와 두 remote server에 동일 AppKey·binding을 구성합니다. */
    void driveConfiguration()
    {
        if (!node_a_added || !node_b_added)
        {
            return;
        }
        if (provisioning_pending || provisioning_links_closed < 2U ||
            k_uptime_get() < configuration_not_before_ms ||
            k_uptime_get() < next_configuration_attempt_ms)
        {
            return;
        }
        if (!local_configured)
        {
            if (!NUCODEMesh.configureAppKey(provisioner_address, application_key))
            {
                retryConfiguration("configure_local_app_key");
                return;
            }
            if (!NUCODEMesh.bindModel(provisioner_address, provisioner_address,
                                      Model::generic_on_off))
            {
                retryConfiguration("configure_local_model");
                return;
            }
            local_configured = true;
            configuration_retry_count = 0U;
        }
        if (!node_a_configured)
        {
            if (!NUCODEMesh.configureAppKey(node_a_address, application_key))
            {
                retryConfiguration("configure_node_a_app_key");
                return;
            }
            if (!NUCODEMesh.bindModel(node_a_address, node_a_address,
                                      Model::generic_on_off_server))
            {
                retryConfiguration("configure_node_a_model");
                return;
            }
            node_a_configured = true;
            configuration_retry_count = 0U;
        }
        if (!node_b_configured)
        {
            if (!NUCODEMesh.configureAppKey(node_b_address, application_key))
            {
                retryConfiguration("configure_node_b_app_key");
                return;
            }
            if (!NUCODEMesh.bindModel(node_b_address, node_b_address,
                                      Model::generic_on_off_server))
            {
                retryConfiguration("configure_node_b_model");
                return;
            }
            node_b_configured = true;
            configuration_retry_count = 0U;
        }
        if (!invalid_destination_rejected)
        {
            Destination invalid{};
            invalid.address = BT_MESH_ADDR_ALL_NODES;
            invalid_destination_rejected = !NUCODEMesh.sendOnOff(invalid, true, false);
            Destination wrong_key{};
            wrong_key.address = node_a_address;
            wrong_key.app_key_index = 0x0FFFU;
            wrong_key_rejected = !NUCODEMesh.sendOnOff(wrong_key, true, false);
            if (!invalid_destination_rejected || !wrong_key_rejected)
            {
                fail("negative_boundary");
            }
        }
    }

    /** @brief 300 base와 200 secured acknowledged message를 순차 전송합니다. */
    void driveMessages()
    {
        if (!local_configured || !node_a_configured || !node_b_configured)
        {
            return;
        }
        if (message_outstanding)
        {
            if (k_uptime_get() - send_started_ms < message_ack_timeout_ms)
            {
                return;
            }
            if (message_retry_count >= message_retry_limit)
            {
                fail("model_ack_timeout", -ETIMEDOUT);
                return;
            }
            Destination retry_destination{};
            retry_destination.address = expected_source;
            send_started_ms = k_uptime_get();
            if (!NUCODEMesh.sendOnOff(retry_destination, expected_state, true))
            {
                fail("model_retry", NUCODEMesh.lastDriverError());
                return;
            }
            ++message_retry_count;
            ++message_retries;
            return;
        }
        if (sent_messages >= total_message_target || k_uptime_get() < next_message_ms)
        {
            return;
        }
        Destination destination{};
        destination.address = (sent_messages & 1U) == 0U ?
                                  node_a_address : node_b_address;
        expected_source = destination.address;
        expected_state = (sent_messages & 2U) != 0U;
        send_started_ms = k_uptime_get();
        if (!NUCODEMesh.sendOnOff(destination, expected_state, true))
        {
            fail("model_send", NUCODEMesh.lastDriverError());
            return;
        }
        ++sent_messages;
        message_outstanding = true;
    }

    /** @brief provisioner의 exact 분모와 negative를 출력합니다. */
    void finishProvisioner()
    {
        if (session_complete || acknowledged_messages < total_message_target)
        {
            return;
        }
        if (!payload_integrity || maximum_latency_ms > 2000U ||
            !invalid_destination_rejected || !wrong_key_rejected)
        {
            fail("result_boundary");
            return;
        }
        Serial.print(protocol);
        Serial.print("|RESULT|role=provisioner|provisioned_nodes=2|configured_nodes=2");
        Serial.print("|base_messages=");
        Serial.print(base_message_target);
        Serial.print("|secured_messages=");
        Serial.print(secured_message_target);
        Serial.print("|acknowledged=");
        Serial.print(acknowledged_messages);
        Serial.print("|max_latency_ms=");
        Serial.print(maximum_latency_ms);
        Serial.print("|invalid_destination_rejected=1|wrong_key_rejected=1");
        Serial.print("|payload_integrity=pass");
        printSuffix();
        Serial.println();
        Serial.print(protocol);
        Serial.print("|END|role=provisioner|status=pass");
        printSuffix();
        Serial.println();
        session_complete = true;
    }
#else
    /** @brief provisioned node에서 Friend/LPN과 역할별 feature를 활성화합니다. */
    void driveNodeFeature()
    {
        if (!started || feature_enabled || !provisioned_event ||
            !NUCODEMesh.provisioned())
        {
            return;
        }
#if defined(NUCODE_M32_MESH_NODE_A)
        feature_enabled = NUCODEMesh.setFeature(Feature::relay, true) &&
                          NUCODEMesh.setFeature(Feature::friend_node, true);
#else
        feature_enabled = NUCODEMesh.setFeature(Feature::low_power_node, true) &&
                          NUCODEMesh.setFeature(Feature::gatt_proxy, true);
#endif
        if (!feature_enabled)
        {
            fail("feature_enable", NUCODEMesh.lastDriverError());
        }
    }

    /** @brief node의 수신 분모·보안 payload·feature를 출력합니다. */
    void finishNode()
    {
        if (session_complete || received_messages < node_message_target)
        {
            return;
        }
        if (!feature_enabled || !unprovisioned_rejected || !payload_integrity)
        {
            fail("result_boundary");
            return;
        }
        Serial.print(protocol);
        Serial.print("|RESULT|role=");
        Serial.print(roleName());
        Serial.print("|received=");
        Serial.print(received_messages);
        Serial.print("|unprovisioned_rejected=1|feature=pass|payload_integrity=pass");
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

    /** @brief 개발 중 상태를 5초 주기로 출력합니다. */
    void printProgress()
    {
        Serial.print(protocol);
        Serial.print("|PROGRESS|role=");
        Serial.print(roleName());
#if defined(NUCODE_M32_MESH_PROVISIONER)
        Serial.print("|added=");
        Serial.print((node_a_added ? 1 : 0) + (node_b_added ? 1 : 0));
        Serial.print("|configured=");
        Serial.print((node_a_configured ? 1 : 0) + (node_b_configured ? 1 : 0));
        Serial.print("|configuration_retries=");
        Serial.print(configuration_retries);
        Serial.print("|provision_attempts=");
        Serial.print(provisioning_attempts);
        Serial.print("|links_opened=");
        Serial.print(provisioning_links_opened);
        Serial.print("|links_closed=");
        Serial.print(provisioning_links_closed);
        Serial.print("|sent=");
        Serial.print(sent_messages);
        Serial.print("|acknowledged=");
        Serial.print(acknowledged_messages);
        Serial.print("|retries=");
        Serial.print(message_retries);
#else
        Serial.print("|provisioned=");
        Serial.print(NUCODEMesh.provisioned() ? 1 : 0);
        Serial.print("|feature=");
        Serial.print(feature_enabled ? 1 : 0);
        Serial.print("|received=");
        Serial.print(received_messages);
#endif
        printSuffix();
        Serial.println();
    }

    /** @brief 역할 feature와 Mesh bearer를 정지하고 cleanup을 기록합니다. */
    void stopSession()
    {
        bool cleanup = NUCODEMesh.cancelProvisioning();
#if defined(NUCODE_M32_MESH_NODE_A)
        cleanup = NUCODEMesh.setFeature(Feature::friend_node, false) && cleanup;
        cleanup = NUCODEMesh.setFeature(Feature::relay, false) && cleanup;
#elif defined(NUCODE_M32_MESH_NODE_B)
        cleanup = NUCODEMesh.setFeature(Feature::low_power_node, false) && cleanup;
        cleanup = NUCODEMesh.setFeature(Feature::gatt_proxy, false) && cleanup;
#endif
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
        stop_requested = false;
    }

    /** @brief PROBE·CLEAR·START·STOP 명령을 처리합니다. */
    void processCommand()
    {
        if (::strcmp(command, "M32MESH|1|PROBE") == 0)
        {
            Serial.print(protocol);
            Serial.print("|READY|role=");
            Serial.print(roleName());
            Serial.print("|provisioned=");
            Serial.print(NUCODEMesh.provisioned() ? 1 : 0);
            Serial.print("|core=");
            Serial.print(M32_MESH_CORE_REVISION);
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
            Serial.println(CONFIG_BT_MESH_MODEL_KEY_COUNT);
            return;
        }
        if (acceptRevisionCommand(clear_prefix))
        {
            clearMeshState();
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
            stop_requested = true;
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
#if defined(NUCODE_M32_MESH_PROVISIONER)
    configuration.role = Role::provisioner;
#else
    configuration.role = Role::node;
#endif
    configuration.bearers = Bearer::advertising;
    configuration.local_address = localAddress();
    configuration.uuid[0] = 0x32U;
    configuration.uuid[1] = 0x06U;
    configuration.uuid[2] = 0x54U;
    configuration.uuid[3] = 0x15U;
#if defined(NUCODE_M32_MESH_NODE_A)
    configuration.uuid[15] = 0xA1U;
#elif defined(NUCODE_M32_MESH_NODE_B)
    configuration.uuid[15] = 0xB2U;
#else
    configuration.uuid[15] = 0xC3U;
#endif
    NUCODEMesh.onEvent(onMeshEvent);
    if (!NUCODEMesh.begin(configuration))
    {
        fail("mesh_begin", NUCODEMesh.lastDriverError());
    }
}

void loop()
{
    NUCODEMesh.poll();
    pollSerial();
    if (failed)
    {
        return;
    }
    if (started && !session_complete)
    {
#if defined(NUCODE_M32_MESH_PROVISIONER)
        driveProvisioning();
        driveConfiguration();
        driveMessages();
        finishProvisioner();
#else
        driveNodeFeature();
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
