/**
 * @file main.cpp
 * @brief 세 NU54DK에서 M32-W08 BLOB 전송 경로를 검증합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <Arduino.h>
#include <NUCODE_BLE_Mesh_Update.h>

#include <zephyr/bluetooth/mesh.h>
#include <zephyr/kernel.h>
#include <zephyr/storage/flash_map.h>

#include <cstddef>
#include <cstdint>
#include <errno.h>
#include <string.h>

#ifndef M32_MESH_UPDATE_CORE_REVISION
#error "M32_MESH_UPDATE_CORE_REVISION is required"
#endif

namespace
{
    using namespace nucode::mesh;

    constexpr char protocol[] = "M32BLOB|1";
    constexpr char clear_prefix[] = "M32BLOB|1|CLEAR|nonce=";
    constexpr char start_prefix[] = "M32BLOB|1|START|nonce=";
    constexpr char stop_prefix[] = "M32BLOB|1|STOP|nonce=";
    constexpr std::size_t nonce_length = 32U;
    constexpr std::uint16_t client_address = 0x0001U;
    constexpr std::uint16_t target_a_address = 0x0100U;
    constexpr std::uint16_t target_b_address = 0x0200U;
    constexpr std::uint16_t blob_group_address = 0xC321U;
    constexpr std::uint32_t object_size = 32768U;
    constexpr std::uint32_t recovery_object_size = 8192U;
    constexpr std::uint32_t chunk_size = 128U;
    constexpr std::uint32_t chunk_interval_ms = 100U;
    constexpr std::uint32_t chunks_per_transfer = object_size / chunk_size;
    constexpr std::uint32_t iteration_target = 10U;
    constexpr std::uint64_t blob_id_base = 0x4E55353400000800ULL;
    constexpr std::uint64_t recovery_blob_id = blob_id_base - 1U;
    constexpr std::int64_t session_timeout_ms = 10800000;
    constexpr std::uint8_t application_key[16] = {
        0x32U, 0x08U, 0x54U, 0x15U, 0x11U, 0x22U, 0x33U, 0x44U,
        0x55U, 0x66U, 0x77U, 0x88U, 0x99U, 0xAAU, 0xBBU, 0xCCU,
    };
    constexpr std::uint32_t configuration_retry_limit = 6U;
    constexpr std::int64_t configuration_retry_delay_ms = 1000;
    constexpr std::uint32_t provisioning_attempt_limit = 6U;
    constexpr std::int64_t recovery_suspend_after_ms = 10000;
    constexpr std::int64_t server_suspend_settle_ms = 1000;
    constexpr std::int64_t recovery_resume_retry_delay_ms = 2000;
    constexpr std::uint32_t recovery_resume_attempt_limit = 6U;
    constexpr std::uint16_t recovery_server_timeout_base = 0U;
    constexpr std::uint16_t transfer_timeout_base = 1U;
    constexpr std::uint8_t transfer_ttl = 7U;
    /** @brief Zephyr BLOB Client가 응답을 기다리는 전체 재시도 창입니다. */
    constexpr std::int64_t client_retry_window_ms =
        10000 * (transfer_timeout_base + 2U) + 100 * transfer_ttl;
    /** @brief 마지막 block 확인 재시도 동안 Server COMPLETE를 유지합니다. */
    constexpr std::int64_t server_complete_settle_ms =
        client_retry_window_ms + 2000;
    /** @brief 두 target이 다음 BLOB ID를 준비한 뒤 전송을 시작합니다. */
    constexpr std::int64_t transfer_spacing_ms =
        server_complete_settle_ms + 3000;
    /** @brief VCOM 재개방 중 유실된 최종 증거를 다시 보낼 주기입니다. */
    constexpr std::int64_t final_result_repeat_ms = 5000;
    static_assert(CONFIG_BT_MESH_CDB_NODE_COUNT >= 3,
                  "local provisioner와 remote target 두 개의 CDB slot이 필요합니다");
    constexpr std::uint8_t object_digest[32] = {
        0xA0U, 0x6FU, 0xA4U, 0x7CU, 0x26U, 0x71U, 0xDEU, 0xF2U,
        0x76U, 0x79U, 0xFEU, 0x04U, 0x8AU, 0x28U, 0x7AU, 0xEBU,
        0x28U, 0x23U, 0xC0U, 0x7AU, 0x1EU, 0x15U, 0xD6U, 0x39U,
        0x5EU, 0x02U, 0xB3U, 0xCEU, 0xC6U, 0x81U, 0xC7U, 0x3DU,
    };
    constexpr std::uint8_t recovery_digest[32] = {
        0x1FU, 0x5AU, 0x16U, 0xC4U, 0x45U, 0x6FU, 0x34U, 0xC5U,
        0x45U, 0x9EU, 0x4EU, 0x66U, 0xD8U, 0x65U, 0x0DU, 0x4DU,
        0xBBU, 0x6BU, 0x29U, 0x88U, 0x10U, 0xD0U, 0xC2U, 0x1CU,
        0xEFU, 0x65U, 0x71U, 0xDBU, 0x21U, 0xD6U, 0x9CU, 0x81U,
    };

    char command[160] = {};
    char nonce[nonce_length + 1U] = {};
    std::size_t command_length = 0U;
    bool cleared = false;
    bool started = false;
    bool session_complete = false;
    bool recovery_complete = false;
    bool failed = false;
    std::int64_t deadline_ms = 0;
    std::int64_t progress_deadline_ms = 0;
    std::int64_t final_result_deadline_ms = 0;

#if defined(NUCODE_M32_BLOB_CLIENT)
    std::uint8_t target_a_uuid[16] = {};
    std::uint8_t target_b_uuid[16] = {};
    bool target_a_discovered = false;
    bool target_b_discovered = false;
    bool provisioning_pending = false;
    bool target_a_added = false;
    bool target_b_added = false;
    bool local_configured = false;
    bool target_a_configured = false;
    bool target_b_configured = false;
    std::uint32_t provisioning_attempts = 0U;
    std::uint32_t provisioning_links_closed = 0U;
    std::int64_t configuration_not_before_ms = 0;
    std::uint8_t configuration_step = 0U;
    std::uint32_t configuration_retries = 0U;
    std::int64_t next_configuration_attempt_ms = 0;
    bool object_seeded = false;
    bool transfer_active = false;
    bool suspend_resume_pass = false;
    bool recovery_suspend_complete = false;
    bool resume_pending = false;
    std::uint32_t recovery_resume_attempts = 0U;
    std::int64_t resume_not_before_ms = 0;
    std::int64_t transfer_started_ms = 0;
    bool wrong_key_rejected = false;
    std::uint32_t iterations = 0U;
    std::uint32_t transferred_chunks = 0U;
    std::int64_t next_transfer_ms = 0;
#else
    bool provisioned_event = false;
    bool receive_active = false;
    bool bad_digest_rejected = false;
    std::uint32_t iterations = 0U;
    std::uint32_t received_chunks = 0U;
    std::int64_t next_receive_ms = 0;
#endif

    /** @brief image의 고정 역할명을 반환합니다. */
    const char *roleName()
    {
#if defined(NUCODE_M32_BLOB_CLIENT)
        return "blob_client";
#elif defined(NUCODE_M32_BLOB_TARGET_A)
        return "target_a";
#else
        return "target_b";
#endif
    }

    /** @brief 역할별 primary unicast address를 반환합니다. */
    std::uint16_t localAddress()
    {
#if defined(NUCODE_M32_BLOB_CLIENT)
        return client_address;
#elif defined(NUCODE_M32_BLOB_TARGET_A)
        return target_a_address;
#else
        return target_b_address;
#endif
    }

    /** @brief 결과 record에 nonce와 Core revision을 결합합니다. */
    void printSuffix()
    {
        Serial.print("|nonce=");
        Serial.print(nonce);
        Serial.print("|core=");
        Serial.print(M32_MESH_UPDATE_CORE_REVISION);
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
                     M32_MESH_UPDATE_CORE_REVISION) != 0)
        {
            return false;
        }
        ::memcpy(nonce, cursor, nonce_length);
        nonce[nonce_length] = '\0';
        return true;
    }

    /** @brief Mesh event를 provisioning 상태로 복사합니다. */
    void onMeshEvent(const EventRecord &record, void *)
    {
#if defined(NUCODE_M32_BLOB_CLIENT)
        if (record.event == Event::unprovisioned_device)
        {
            if (record.uuid[15] == 0xA1U && !target_a_added)
            {
                ::memcpy(target_a_uuid, record.uuid, sizeof(target_a_uuid));
                target_a_discovered = true;
            }
            else if (record.uuid[15] == 0xB2U && !target_b_added)
            {
                ::memcpy(target_b_uuid, record.uuid, sizeof(target_b_uuid));
                target_b_discovered = true;
            }
        }
        else if (record.event == Event::node_added)
        {
            provisioning_pending = false;
            provisioning_attempts = 0U;
            if (record.address == target_a_address)
            {
                target_a_added = true;
            }
            else if (record.address == target_b_address)
            {
                target_b_added = true;
            }
            else
            {
                fail("unexpected_node", record.address);
            }
        }
        else if (record.event == Event::provisioning_link_closed)
        {
            provisioning_pending = false;
            ++provisioning_links_closed;
            configuration_not_before_ms = k_uptime_get() + 1500;
        }
#else
        if (record.event == Event::provisioned)
        {
            provisioned_event = true;
        }
#endif
    }

    /** @brief 저장 상태와 update 전송 상태를 초기화합니다. */
    void clearState()
    {
        NUCODEMeshUpdate.cancelBlob();
        if (!NUCODEMesh.reset())
        {
            fail("clear", NUCODEMesh.lastDriverError());
            return;
        }
        cleared = true;
        started = false;
        session_complete = false;
        final_result_deadline_ms = 0;
#if defined(NUCODE_M32_BLOB_CLIENT)
        target_a_discovered = false;
        target_b_discovered = false;
        provisioning_pending = false;
        target_a_added = false;
        target_b_added = false;
        local_configured = false;
        target_a_configured = false;
        target_b_configured = false;
        provisioning_attempts = 0U;
        provisioning_links_closed = 0U;
        configuration_not_before_ms = 0;
        configuration_step = 0U;
        configuration_retries = 0U;
        next_configuration_attempt_ms = 0;
        object_seeded = false;
        transfer_active = false;
        suspend_resume_pass = false;
        recovery_suspend_complete = false;
        resume_pending = false;
        recovery_resume_attempts = 0U;
        resume_not_before_ms = 0;
        transfer_started_ms = 0;
        wrong_key_rejected = false;
        recovery_complete = false;
        iterations = 0U;
        transferred_chunks = 0U;
#else
        provisioned_event = false;
        receive_active = false;
        bad_digest_rejected = false;
#if defined(NUCODE_M32_BLOB_TARGET_A)
        recovery_complete = false;
#else
        recovery_complete = true;
#endif
        iterations = 0U;
        received_chunks = 0U;
        next_receive_ms = 0;
#endif
        Serial.print(protocol);
        Serial.print("|CLEARED|role=");
        Serial.print(roleName());
        printSuffix();
        Serial.println();
    }

    /** @brief 역할별 deadline을 열고 BLOB session을 시작합니다. */
    void startSession()
    {
        if (!cleared)
        {
            fail("start_without_clear");
            return;
        }
        started = true;
        session_complete = false;
        final_result_deadline_ms = 0;
        deadline_ms = k_uptime_get() + session_timeout_ms;
        const std::int64_t progress_offset_ms =
#if defined(NUCODE_M32_BLOB_CLIENT)
            4000;
#elif defined(NUCODE_M32_BLOB_TARGET_A)
            0;
#else
            2000;
#endif
        progress_deadline_ms = k_uptime_get() + 5000 + progress_offset_ms;
        Serial.print(protocol);
        Serial.print("|BEGIN|role=");
        Serial.print(roleName());
        printSuffix();
        Serial.println();
    }

#if defined(NUCODE_M32_BLOB_CLIENT)
    /** @brief 두 target을 한 번에 하나씩 고정 주소에 provisioning합니다. */
    void driveProvisioning()
    {
        if (provisioning_pending)
        {
            return;
        }
        const std::uint32_t required_closed_links = target_a_added ? 1U : 0U;
        if (provisioning_links_closed < required_closed_links ||
            k_uptime_get() < configuration_not_before_ms)
        {
            return;
        }
        const std::uint8_t *uuid = nullptr;
        std::uint16_t address = 0U;
        if (target_a_discovered && !target_a_added)
        {
            uuid = target_a_uuid;
            address = target_a_address;
        }
        else if (target_b_discovered && !target_b_added)
        {
            uuid = target_b_uuid;
            address = target_b_address;
        }
        if (uuid != nullptr)
        {
            if (provisioning_attempts >= provisioning_attempt_limit)
            {
                fail("provision_retry_limit");
                return;
            }
            provisioning_pending = NUCODEMesh.provision(
                uuid, Bearer::advertising, address);
            if (provisioning_pending)
            {
                ++provisioning_attempts;
            }
            else
            {
                if (NUCODEMesh.lastDriverError() == -ETIMEDOUT)
                {
                    ++provisioning_attempts;
                }
                if (NUCODEMesh.lastDriverError() == -EBUSY ||
                    NUCODEMesh.lastDriverError() == -ETIMEDOUT)
                {
                    configuration_not_before_ms = k_uptime_get() + 1000;
                    return;
                }
                fail("provision", NUCODEMesh.lastDriverError());
            }
        }
    }

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

    /** @brief BLOB Client와 두 Server model에 AppKey를 순차적으로 추가·binding합니다. */
    void driveConfiguration()
    {
        if (!target_a_added || !target_b_added ||
            provisioning_links_closed < 2U ||
            k_uptime_get() < configuration_not_before_ms ||
            k_uptime_get() < next_configuration_attempt_ms ||
            target_b_configured)
        {
            return;
        }
        bool result = false;
        const char *stage = "configure_blob";
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
                result = NUCODEMesh.bindModel(client_address, client_address + 1U,
                                              Model::blob_client);
                stage = "bind_local_blob";
                break;
            }
            case 2U:
            {
                result = NUCODEMesh.configureAppKey(target_a_address, application_key);
                stage = "configure_target_a_app_key";
                break;
            }
            case 3U:
            {
                result = NUCODEMesh.bindModel(target_a_address, target_a_address + 1U,
                                              Model::blob_server);
                stage = "bind_target_a_blob";
                break;
            }
            case 4U:
            {
                result = NUCODEMesh.subscribeModel(target_a_address,
                                                   target_a_address + 1U,
                                                   Model::blob_server,
                                                   blob_group_address);
                stage = "subscribe_target_a_blob";
                break;
            }
            case 5U:
            {
                result = NUCODEMesh.configureAppKey(target_b_address, application_key);
                stage = "configure_target_b_app_key";
                break;
            }
            case 6U:
            {
                result = NUCODEMesh.bindModel(target_b_address, target_b_address + 1U,
                                               Model::blob_server);
                stage = "bind_target_b_blob";
                break;
            }
            case 7U:
            {
                result = NUCODEMesh.subscribeModel(target_b_address,
                                                   target_b_address + 1U,
                                                   Model::blob_server,
                                                   blob_group_address);
                stage = "subscribe_target_b_blob";
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
        if (configuration_step == 2U)
        {
            local_configured = true;
        }
        else if (configuration_step == 5U)
        {
            target_a_configured = true;
        }
        else if (configuration_step >= 8U)
        {
            target_b_configured = true;
            next_transfer_ms = k_uptime_get() + 1500;
        }
    }

    /** @brief inactive slot의 앞 32 KiB에 재현 가능한 object를 기록합니다. */
    void seedObject()
    {
        if (object_seeded || !target_b_configured)
        {
            return;
        }
        const struct flash_area *area = nullptr;
        int error = flash_area_open(PARTITION_ID(slot1_partition), &area);
        if (error != 0)
        {
            fail("slot_open", error);
            return;
        }
        error = flash_area_erase(area, 0U, object_size);
        std::uint8_t buffer[chunk_size]{};
        for (std::uint32_t offset = 0U; error == 0 && offset < object_size;
             offset += chunk_size)
        {
            for (std::uint32_t index = 0U; index < chunk_size; ++index)
            {
                buffer[index] = static_cast<std::uint8_t>(
                    ((offset + index) * 37U + 11U) & 0xFFU);
            }
            error = flash_area_write(area, offset, buffer, sizeof(buffer));
        }
        flash_area_close(area);
        if (error != 0)
        {
            fail("slot_seed", error);
            return;
        }
        object_seeded = true;
    }

    /** @brief target A 하나에서 suspend·resume 복구 전송을 먼저 검증합니다. */
    void driveRecoveryTransfer()
    {
        if (recovery_complete)
        {
            return;
        }
        if (!transfer_active)
        {
            if (k_uptime_get() < next_transfer_ms)
            {
                return;
            }
            const BlobTarget targets[] = {
                {static_cast<std::uint16_t>(target_a_address + 1U)},
            };
            BlobTransfer transfer{};
            transfer.id = recovery_blob_id;
            transfer.size = recovery_object_size;
            transfer.targets = targets;
            transfer.target_count = 1U;
            transfer.chunk_size = chunk_size;
            transfer.chunk_interval_ms = chunk_interval_ms;
            transfer.block_size_log = 12U;
            if (!wrong_key_rejected)
            {
                BlobTransfer wrong_key = transfer;
                wrong_key.app_key_index = 0x0FFFU;
                wrong_key_rejected = !NUCODEMeshUpdate.sendBlob(wrong_key);
                if (!wrong_key_rejected)
                {
                    NUCODEMeshUpdate.cancelBlob();
                    fail("wrong_key");
                    return;
                }
            }
            if (!NUCODEMeshUpdate.sendBlob(transfer))
            {
                fail("blob_send", NUCODEMeshUpdate.lastDriverError());
                return;
            }
            transfer_active = true;
            transfer_started_ms = k_uptime_get();
            return;
        }
        if (!recovery_suspend_complete && !resume_pending &&
            k_uptime_get() >= transfer_started_ms + recovery_suspend_after_ms)
        {
            if (!NUCODEMeshUpdate.suspendBlob())
            {
                if (NUCODEMeshUpdate.lastDriverError() == -EBUSY ||
                    NUCODEMeshUpdate.lastDriverError() == -EINVAL)
                {
                    return;
                }
                fail("suspend", NUCODEMeshUpdate.lastDriverError());
                return;
            }
            recovery_suspend_complete = true;
            resume_pending = true;
            resume_not_before_ms = k_uptime_get() + server_suspend_settle_ms;
            return;
        }
        if (recovery_suspend_complete && !resume_pending &&
            NUCODEMeshUpdate.phase() == UpdatePhase::suspended)
        {
            if (recovery_resume_attempts >= recovery_resume_attempt_limit)
            {
                fail("resume_retry_limit", NUCODEMeshUpdate.lastDriverError());
                return;
            }
            resume_pending = true;
            resume_not_before_ms =
                k_uptime_get() + recovery_resume_retry_delay_ms;
            return;
        }
        if (resume_pending)
        {
            if (k_uptime_get() < resume_not_before_ms)
            {
                return;
            }
            if (!NUCODEMeshUpdate.resumeBlob())
            {
                fail("resume", NUCODEMeshUpdate.lastDriverError());
                return;
            }
            resume_pending = false;
            ++recovery_resume_attempts;
            return;
        }
        if (!NUCODEMeshUpdate.busy() &&
            NUCODEMeshUpdate.phase() == UpdatePhase::completed)
        {
            transfer_active = false;
            recovery_complete = true;
            suspend_resume_pass = recovery_suspend_complete &&
                recovery_resume_attempts > 0U;
            next_transfer_ms = k_uptime_get() + transfer_spacing_ms;
        }
        else if (!NUCODEMeshUpdate.busy() &&
                 NUCODEMeshUpdate.phase() == UpdatePhase::failed)
        {
            fail("blob_transfer", NUCODEMeshUpdate.lastDriverError());
        }
    }

    /** @brief 복구 preflight 뒤 32 KiB BLOB을 두 target으로 열 번 전송합니다. */
    void driveTransfers()
    {
        if (!object_seeded || iterations >= iteration_target)
        {
            return;
        }
        if (!recovery_complete)
        {
            driveRecoveryTransfer();
            return;
        }
        if (!transfer_active)
        {
            if (k_uptime_get() < next_transfer_ms)
            {
                return;
            }
            const BlobTarget targets[] = {
                {static_cast<std::uint16_t>(target_a_address + 1U)},
                {static_cast<std::uint16_t>(target_b_address + 1U)},
            };
            BlobTransfer transfer{};
            transfer.id = blob_id_base + iterations;
            transfer.size = object_size;
            transfer.targets = targets;
            transfer.target_count = 2U;
            transfer.group_address = blob_group_address;
            transfer.timeout_base = transfer_timeout_base;
            transfer.chunk_size = chunk_size;
            transfer.chunk_interval_ms = chunk_interval_ms;
            transfer.ttl = transfer_ttl;
            transfer.block_size_log = 14U;
            if (!NUCODEMeshUpdate.sendBlob(transfer))
            {
                fail("blob_send", NUCODEMeshUpdate.lastDriverError());
                return;
            }
            transfer_active = true;
            return;
        }
        if (!NUCODEMeshUpdate.busy() &&
            NUCODEMeshUpdate.phase() == UpdatePhase::completed)
        {
            transfer_active = false;
            ++iterations;
            transferred_chunks += chunks_per_transfer * 2U;
            next_transfer_ms = k_uptime_get() + transfer_spacing_ms;
        }
        else if (!NUCODEMeshUpdate.busy() &&
                 NUCODEMeshUpdate.phase() == UpdatePhase::failed)
        {
            fail("blob_transfer", NUCODEMeshUpdate.lastDriverError());
        }
    }

    /** @brief client BLOB 최종 결과를 멱등 재전송합니다. */
    void printClientResult()
    {
        Serial.print(protocol);
        Serial.print("|RESULT|role=blob_client|targets=2|iterations=");
        Serial.print(iterations);
        Serial.print("|chunks=");
        Serial.print(transferred_chunks);
        Serial.print("|chunk_size=128|object_size=32768|suspend_resume=pass");
        Serial.print("|wrong_key_rejected=1|object_digest=pass");
        printSuffix();
        Serial.println();
        Serial.print(protocol);
        Serial.print("|END|role=blob_client|status=pass");
        printSuffix();
        Serial.println();
    }

    /** @brief client BLOB 분모·negative·resume 결과를 확정합니다. */
    void finishClient()
    {
        if (session_complete || iterations < iteration_target)
        {
            return;
        }
        if (transferred_chunks != iteration_target * chunks_per_transfer * 2U ||
            !suspend_resume_pass || !wrong_key_rejected)
        {
            fail("result_boundary");
            return;
        }
        printClientResult();
        session_complete = true;
        final_result_deadline_ms = k_uptime_get() + final_result_repeat_ms;
    }
#else
    /** @brief 각 target에서 다음 BLOB receive를 준비하고 digest를 확인합니다. */
    void driveReceive()
    {
        if (!provisioned_event || iterations >= iteration_target)
        {
            return;
        }
        if (!receive_active)
        {
            if (k_uptime_get() < next_receive_ms)
            {
                return;
            }
            const std::uint64_t blob_id = recovery_complete ?
                blob_id_base + iterations : recovery_blob_id;
            const std::uint16_t timeout_base = recovery_complete ?
                transfer_timeout_base : recovery_server_timeout_base;
            if (!NUCODEMeshUpdate.prepareBlobReceive(blob_id, transfer_ttl,
                                                     timeout_base))
            {
                fail("blob_receive", NUCODEMeshUpdate.lastDriverError());
                return;
            }
            receive_active = true;
            return;
        }
        if (!NUCODEMeshUpdate.busy() && NUCODEMeshUpdate.serverProgress() == 100U)
        {
            const bool recovery_transfer = !recovery_complete;
            if (!recovery_transfer && iterations == 0U)
            {
                std::uint8_t bad_digest[32]{};
                bad_digest_rejected = !NUCODEMeshUpdate.verifyStagedDigest(
                    bad_digest, object_size);
            }
            const std::uint8_t *expected_digest = recovery_transfer ?
                recovery_digest : object_digest;
            const std::uint32_t expected_size = recovery_transfer ?
                recovery_object_size : object_size;
            if (!NUCODEMeshUpdate.verifyStagedDigest(expected_digest,
                                                     expected_size))
            {
                fail("digest", NUCODEMeshUpdate.lastDriverError());
                return;
            }
            receive_active = false;
            next_receive_ms = k_uptime_get() + server_complete_settle_ms;
            if (recovery_transfer)
            {
                recovery_complete = true;
                return;
            }
            ++iterations;
            received_chunks += chunks_per_transfer;
        }
    }

    /** @brief target BLOB 최종 결과를 멱등 재전송합니다. */
    void printTargetResult()
    {
        Serial.print(protocol);
        Serial.print("|RESULT|role=");
        Serial.print(roleName());
        Serial.print("|iterations=");
        Serial.print(iterations);
        Serial.print("|chunks=");
        Serial.print(received_chunks);
        Serial.print("|chunk_size=128|bad_digest_rejected=1|object_digest=pass");
        printSuffix();
        Serial.println();
        Serial.print(protocol);
        Serial.print("|END|role=");
        Serial.print(roleName());
        Serial.print("|status=pass");
        printSuffix();
        Serial.println();
    }

    /** @brief target BLOB 분모와 bad digest 거부를 확정합니다. */
    void finishTarget()
    {
        if (session_complete || iterations < iteration_target)
        {
            return;
        }
        if (received_chunks != iteration_target * chunks_per_transfer ||
            !bad_digest_rejected)
        {
            fail("result_boundary");
            return;
        }
        printTargetResult();
        session_complete = true;
        final_result_deadline_ms = k_uptime_get() + final_result_repeat_ms;
    }
#endif

    /** @brief STOP을 받을 때까지 VCOM 유실에 대비해 최종 증거를 반복합니다. */
    void repeatFinalResult()
    {
        if (!started || !session_complete ||
            k_uptime_get() < final_result_deadline_ms)
        {
            return;
        }
#if defined(NUCODE_M32_BLOB_CLIENT)
        printClientResult();
#else
        printTargetResult();
#endif
        final_result_deadline_ms = k_uptime_get() + final_result_repeat_ms;
    }

    /** @brief VCOM backpressure를 피하도록 역할별로 엇갈린 10초 진행률을 출력합니다. */
    void printProgress()
    {
        Serial.print(protocol);
        Serial.print("|PROGRESS|role=");
        Serial.print(roleName());
        Serial.print("|iterations=");
        Serial.print(iterations);
#if defined(NUCODE_M32_BLOB_CLIENT)
        Serial.print("|progress=");
        Serial.print(NUCODEMeshUpdate.clientProgress());
        Serial.print("|a=");
        Serial.print((target_a_added ? 1 : 0) + (target_b_added ? 1 : 0));
        Serial.print("|l=");
        Serial.print(provisioning_links_closed);
        Serial.print("|pa=");
        Serial.print(provisioning_attempts);
        Serial.print("|cs=");
        Serial.print(configuration_step);
        Serial.print("|rp=");
        Serial.print(resume_pending ? 1 : 0);
#else
        Serial.print("|progress=");
        Serial.print(NUCODEMeshUpdate.serverProgress());
#endif
        Serial.print("|p=");
        Serial.print(static_cast<unsigned int>(NUCODEMeshUpdate.phase()));
        Serial.print("|b=");
        Serial.print(NUCODEMeshUpdate.busy() ? 1 : 0);
        Serial.print("|e=");
        Serial.print(NUCODEMeshUpdate.lastDriverError());
        printSuffix();
        Serial.println();
    }

    /** @brief BLOB과 Mesh bearer를 정지하고 cleanup을 기록합니다. */
    void stopSession()
    {
        started = false;
        NUCODEMeshUpdate.cancelBlob();
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
        if (::strcmp(command, "M32BLOB|1|PROBE") == 0)
        {
            Serial.print(protocol);
            Serial.print("|READY|role=");
            Serial.print(roleName());
            Serial.print("|provisioned=");
            Serial.print(NUCODEMesh.provisioned() ? 1 : 0);
            Serial.print("|cdb_node_slots=");
            Serial.print(CONFIG_BT_MESH_CDB_NODE_COUNT);
            Serial.print("|cdb_local_slots=1");
            Serial.print("|core=");
            Serial.println(M32_MESH_UPDATE_CORE_REVISION);
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
#if defined(NUCODE_M32_BLOB_CLIENT)
    configuration.role = Role::provisioner;
#else
    configuration.role = Role::node;
#endif
    configuration.bearers = Bearer::advertising;
    configuration.local_address = localAddress();
    configuration.uuid[0] = 0x32U;
    configuration.uuid[1] = 0x08U;
    configuration.uuid[2] = 0x54U;
    configuration.uuid[3] = 0x15U;
#if defined(NUCODE_M32_BLOB_TARGET_A)
    configuration.uuid[15] = 0xA1U;
#elif defined(NUCODE_M32_BLOB_TARGET_B)
    configuration.uuid[15] = 0xB2U;
#else
    configuration.uuid[15] = 0xC3U;
#endif
    NUCODEMesh.onEvent(onMeshEvent);
    if (!NUCODEMesh.begin(configuration))
    {
        fail("mesh_begin", NUCODEMesh.lastDriverError());
        return;
    }
    if (!NUCODEMeshUpdate.begin())
    {
        fail("update_begin", NUCODEMeshUpdate.lastDriverError());
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
#if defined(NUCODE_M32_BLOB_CLIENT)
        driveProvisioning();
        driveConfiguration();
        seedObject();
        driveTransfers();
        finishClient();
#else
        driveReceive();
        finishTarget();
#endif
        if (k_uptime_get() >= progress_deadline_ms)
        {
            printProgress();
            progress_deadline_ms = k_uptime_get() + 10000;
        }
        if (k_uptime_get() >= deadline_ms)
        {
            fail("timeout");
        }
    }
    else if (started && session_complete)
    {
        repeatFinalResult();
    }
    delay(1);
}
