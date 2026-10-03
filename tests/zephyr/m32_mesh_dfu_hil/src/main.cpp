/**
 * @file main.cpp
 * @brief 세 NU54DK에서 signed Mesh DFU 배포와 MCUboot rollback을 검증합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <Arduino.h>
#include <NUCODE_BLE_Mesh_Update.h>

#include <zephyr/bluetooth/mesh.h>
#include <zephyr/bluetooth/mesh/dfd_srv.h>
#include <zephyr/bluetooth/mesh/dfu_srv.h>
#include <zephyr/dfu/mcuboot.h>
#include <zephyr/kernel.h>
#include <zephyr/settings/settings.h>
#include <zephyr/storage/flash_map.h>

extern "C"
{
#include "mesh/access.h"
}

#include <cstddef>
#include <cstdint>
#include <errno.h>
#include <string.h>

#ifndef M32_MDFU_CORE_REVISION
#error "M32_MDFU_CORE_REVISION is required"
#endif

#if !defined(NUCODE_M32_MDFU_CANDIDATE)
#ifndef M32_MDFU_CANDIDATE_SHA256
#error "M32_MDFU_CANDIDATE_SHA256 is required"
#endif
#ifndef M32_MDFU_CANDIDATE_SIZE
#error "M32_MDFU_CANDIDATE_SIZE is required"
#endif
#endif

extern "C"
{
    extern struct bt_mesh_dfu_srv nucode_mesh_dfu_server_instance;
    extern struct bt_mesh_dfd_srv nucode_mesh_distributor_instance;
}

namespace
{
    using namespace nucode::mesh;

    constexpr char protocol[] = "M32MDFU|1";
    constexpr char clear_prefix[] = "M32MDFU|1|CLEAR|nonce=";
    constexpr char start_prefix[] = "M32MDFU|1|START|nonce=";
    constexpr char apply_prefix[] = "M32MDFU|1|APPLY|nonce=";
    constexpr char next_prefix[] = "M32MDFU|1|NEXT|nonce=";
    constexpr char stop_prefix[] = "M32MDFU|1|STOP|nonce=";
    constexpr char nonce_setting[] = "m32mdfu/nonce";
    constexpr char role_setting[] = "m32mdfu/role";
    constexpr std::size_t nonce_length = 32U;
    constexpr std::uint16_t distributor_address = 0x0001U;
    constexpr std::uint16_t target_a_address = 0x0100U;
    constexpr std::uint16_t target_b_address = 0x0200U;
    constexpr std::uint8_t distribution_iteration_target = 5U;
    /** @brief 5회 signed Mesh DFU와 각 rollback을 포함하는 세션의 유한 상한입니다. */
    constexpr std::int64_t session_timeout_ms = 10800000;
    constexpr std::uint32_t partial_image_size_limit = 4096U;
    constexpr std::uint8_t application_key[16] = {
        0x32U, 0x08U, 0xDFU, 0x15U, 0x11U, 0x22U, 0x33U, 0x44U,
        0x55U, 0x66U, 0x77U, 0x88U, 0x99U, 0xAAU, 0xBBU, 0xCCU,
    };
    constexpr std::uint32_t configuration_retry_limit = 3U;
    constexpr std::int64_t configuration_retry_delay_ms = 500;
    constexpr std::uint32_t provisioning_attempt_limit = 6U;
    static_assert(CONFIG_BT_MESH_CDB_NODE_COUNT >= 3,
                  "local provisioner와 remote target 두 개의 CDB slot이 필요합니다");

    char command[192] = {};
    char nonce[nonce_length + 1U] = {};
    std::size_t command_length = 0U;
    bool nonce_valid = false;
    bool cleared = false;
    bool started = false;
    bool failed = false;
    bool complete = false;
    bool candidate_applied = false;
    std::int64_t deadline_ms = 0;
    std::int64_t progress_deadline_ms = 0;

#if defined(NUCODE_M32_MDFU_DISTRIBUTOR)
    enum class DistributionStage : std::uint8_t
    {
        wrong_image,
        wait_wrong_image,
        partial_image,
        wait_partial_image,
        valid_image,
        wait_valid_image,
        wait_next,
        finished,
    };

    std::uint8_t target_a_uuid[16] = {};
    std::uint8_t target_b_uuid[16] = {};
    bool target_a_discovered = false;
    bool target_b_discovered = false;
    bool target_a_added = false;
    bool target_b_added = false;
    bool provisioning_pending = false;
    bool local_configured = false;
    bool target_a_configured = false;
    bool target_b_configured = false;
    std::uint32_t provisioning_attempts = 0U;
    std::uint32_t provisioning_links_closed = 0U;
    std::int64_t configuration_not_before_ms = 0;
    std::uint8_t configuration_step = 0U;
    std::uint32_t configuration_retries = 0U;
    std::int64_t next_configuration_attempt_ms = 0;
    bool wrong_key_rejected = false;
    bool wrong_image_rejected = false;
    bool partial_image_rejected = false;
    std::uint8_t distribution_iteration = 0U;
    DistributionStage distribution_stage = DistributionStage::wrong_image;
#endif

    /** @brief MCUboot active image의 semantic version입니다. */
    struct ActiveImage
    {
        std::uint8_t major = 0U;
        std::uint8_t minor = 0U;
        std::uint16_t revision = 0U;
        std::uint32_t build = 0U;
        bool confirmed = false;
    };

    /** @brief 16진수 한 문자를 값으로 변환합니다. */
    bool hexValue(char value, std::uint8_t &result)
    {
        if (value >= '0' && value <= '9')
        {
            result = static_cast<std::uint8_t>(value - '0');
            return true;
        }
        if (value >= 'a' && value <= 'f')
        {
            result = static_cast<std::uint8_t>(value - 'a' + 10);
            return true;
        }
        return false;
    }

#if defined(NUCODE_M32_MDFU_TARGET_A) || defined(NUCODE_M32_MDFU_TARGET_B)
    /** @brief CMake이 고정한 candidate digest를 binary로 변환합니다. */
    bool candidateDigest(std::uint8_t digest[32])
    {
        constexpr char encoded[] = M32_MDFU_CANDIDATE_SHA256;
        if (sizeof(encoded) != 65U)
        {
            return false;
        }
        for (std::size_t index = 0U; index < 32U; ++index)
        {
            std::uint8_t high = 0U;
            std::uint8_t low = 0U;
            if (!hexValue(encoded[index * 2U], high) || !hexValue(encoded[index * 2U + 1U], low))
            {
                return false;
            }
            digest[index] = static_cast<std::uint8_t>((high << 4U) | low);
        }
        return true;
    }
#endif

    /** @brief provisioned address를 포함해 현재 역할을 반환합니다. */
    const char *roleName()
    {
#if defined(NUCODE_M32_MDFU_DISTRIBUTOR)
        return "distributor";
#elif defined(NUCODE_M32_MDFU_TARGET_A)
        return "target_a";
#elif defined(NUCODE_M32_MDFU_TARGET_B)
        return "target_b";
#else
        const std::uint16_t address = bt_mesh_primary_addr();
        if (address == target_a_address)
        {
            return "target_a";
        }
        if (address == target_b_address)
        {
            return "target_b";
        }
        return "candidate_unknown";
#endif
    }

    /** @brief protocol record에 session과 exact source를 결합합니다. */
    void printSuffix()
    {
        Serial.print("|nonce=");
        Serial.print(nonce_valid ? nonce : "none");
        Serial.print("|core=");
        Serial.print(M32_MDFU_CORE_REVISION);
    }

    /** @brief 첫 실패만 bounded protocol로 출력합니다. */
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

    /** @brief active slot의 MCUboot header를 읽습니다. */
    bool activeImage(ActiveImage &image)
    {
        struct mcuboot_img_header header{};
        const int error =
            boot_read_bank_header(PARTITION_ID(slot0_partition), &header, sizeof(header));
        if ((error != 0) || (header.mcuboot_version != 1U))
        {
            return false;
        }
        image.major = header.h.v1.sem_ver.major;
        image.minor = header.h.v1.sem_ver.minor;
        image.revision = header.h.v1.sem_ver.revision;
        image.build = header.h.v1.sem_ver.build_num;
        image.confirmed = boot_is_img_confirmed();
        return true;
    }

    /** @brief 저장된 session nonce를 직접 읽습니다. */
    int loadNonceEntry(const char *key, std::size_t length, settings_read_cb read_callback,
                       void *callback_argument, void *)
    {
        if ((key == nullptr) || (::strcmp(key, "nonce") != 0) || (length != sizeof(nonce)))
        {
            return 0;
        }
        const ssize_t read = read_callback(callback_argument, nonce, sizeof(nonce));
        nonce_valid = read == static_cast<ssize_t>(sizeof(nonce)) && nonce[nonce_length] == '\0';
        return nonce_valid ? 1 : -EINVAL;
    }

    /** @brief reset 뒤에도 이어지는 session nonce를 복원합니다. */
    void loadNonce()
    {
        nonce_valid = false;
        static_cast<void>(settings_load_subtree_direct("m32mdfu", loadNonceEntry, nullptr));
    }

    /** @brief 현재 boot image와 confirm 상태를 기록합니다. */
    void reportBoot()
    {
        if (!nonce_valid)
        {
            return;
        }
        ActiveImage image{};
        if (!activeImage(image))
        {
            fail("active_header");
            return;
        }
        Serial.print(protocol);
        Serial.print("|BOOT|role=");
        Serial.print(roleName());
        Serial.print("|version=");
        Serial.print(image.major);
        Serial.print('.');
        Serial.print(image.minor);
        Serial.print('.');
        Serial.print(image.revision);
        Serial.print('+');
        Serial.print(static_cast<unsigned long>(image.build));
        Serial.print("|confirmed=");
        Serial.print(image.confirmed ? 1 : 0);
        Serial.print("|active_slot=");
        Serial.print(static_cast<unsigned int>(boot_fetch_active_slot()));
        printSuffix();
        Serial.println();
    }

    /** @brief nonce와 revision이 결합된 command를 검증합니다. */
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
            std::uint8_t ignored = 0U;
            if (!hexValue(cursor[index], ignored))
            {
                return false;
            }
        }
        constexpr char core_prefix[] = "|core=";
        if (::strncmp(cursor + nonce_length, core_prefix, sizeof(core_prefix) - 1U) != 0 ||
            ::strcmp(cursor + nonce_length + sizeof(core_prefix) - 1U, M32_MDFU_CORE_REVISION) != 0)
        {
            return false;
        }
        ::memcpy(nonce, cursor, nonce_length);
        nonce[nonce_length] = '\0';
        nonce_valid = true;
        return true;
    }

    /** @brief Mesh provisioning event를 역할 상태로 복사합니다. */
    void onMeshEvent(const EventRecord &record, void *)
    {
#if defined(NUCODE_M32_MDFU_DISTRIBUTOR)
        if (record.event == Event::unprovisioned_device)
        {
            if ((record.uuid[15] == 0xA1U) && !target_a_added)
            {
                ::memcpy(target_a_uuid, record.uuid, sizeof(target_a_uuid));
                target_a_discovered = true;
            }
            else if ((record.uuid[15] == 0xB2U) && !target_b_added)
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
        static_cast<void>(record);
#endif
    }

    /** @brief Mesh와 session 상태를 초기화합니다. */
    void clearState()
    {
        NUCODEMeshUpdate.cancelBlob();
        if (!NUCODEMesh.reset())
        {
            fail("clear", NUCODEMesh.lastDriverError());
            return;
        }
        static_cast<void>(settings_delete(nonce_setting));
        static_cast<void>(settings_delete(role_setting));
        cleared = true;
        started = false;
        complete = false;
        candidate_applied = false;
#if defined(NUCODE_M32_MDFU_DISTRIBUTOR)
        target_a_discovered = false;
        target_b_discovered = false;
        target_a_added = false;
        target_b_added = false;
        provisioning_pending = false;
        local_configured = false;
        target_a_configured = false;
        target_b_configured = false;
        provisioning_attempts = 0U;
        provisioning_links_closed = 0U;
        configuration_not_before_ms = 0;
        configuration_step = 0U;
        configuration_retries = 0U;
        next_configuration_attempt_ms = 0;
        wrong_key_rejected = false;
        wrong_image_rejected = false;
        partial_image_rejected = false;
        distribution_iteration = 0U;
        distribution_stage = DistributionStage::wrong_image;
#endif
        Serial.print(protocol);
        Serial.print("|CLEARED|role=");
        Serial.print(roleName());
        printSuffix();
        Serial.println();
    }

    /** @brief session nonce를 저장하고 역할 실행을 시작합니다. */
    void startSession()
    {
        if (!cleared)
        {
            fail("start_without_clear");
            return;
        }
        const char role = roleName()[7];
        if ((settings_save_one(nonce_setting, nonce, sizeof(nonce)) != 0) ||
            (settings_save_one(role_setting, &role, sizeof(role)) != 0))
        {
            fail("nonce_store");
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

#if defined(NUCODE_M32_MDFU_DISTRIBUTOR)
    /** @brief 발견한 두 target을 고정 주소로 순차 provisioning합니다. */
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
            provisioning_pending = NUCODEMesh.provision(uuid, Bearer::advertising, address);
            if (provisioning_pending)
            {
                ++provisioning_attempts;
            }
            else
            {
                if (NUCODEMesh.lastDriverError() == -ETIMEDOUT)
                {
                    ++provisioning_attempts;
                    configuration_not_before_ms = k_uptime_get() + 1000;
                    return;
                }
                if (NUCODEMesh.lastDriverError() == -EBUSY)
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

    /** @brief Distributor 의존 model과 두 DFU Target model을 순차적으로 binding합니다. */
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
        const char *stage = "configure_mdfu";
        switch (configuration_step)
        {
            case 0U:
            {
                result = NUCODEMesh.configureAppKey(distributor_address,
                                                    application_key);
                stage = "configure_distributor_app_key";
                break;
            }
            case 1U:
            {
                result = NUCODEMesh.bindModel(distributor_address,
                                              distributor_address + 3U,
                                              Model::firmware_distributor);
                stage = "bind_distributor";
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
                result = NUCODEMesh.bindModel(target_a_address,
                                              target_a_address + 2U,
                                              Model::mesh_dfu_target);
                stage = "bind_target_a_dfu";
                break;
            }
            case 4U:
            {
                result = NUCODEMesh.configureAppKey(target_b_address, application_key);
                stage = "configure_target_b_app_key";
                break;
            }
            case 5U:
            {
                result = NUCODEMesh.bindModel(target_b_address,
                                              target_b_address + 2U,
                                              Model::mesh_dfu_target);
                stage = "bind_target_b_dfu";
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
        else if (configuration_step == 4U)
        {
            target_a_configured = true;
        }
        else if (configuration_step >= 6U)
        {
            target_b_configured = true;
        }
    }

    /** @brief 두 target의 최종 DFU 상태가 모두 성공인지 확인합니다. */
    bool distributionTargetsSucceeded()
    {
        if (nucode_mesh_distributor_instance.target_cnt != 2U)
        {
            return false;
        }
        for (std::uint16_t index = 0U; index < 2U; ++index)
        {
            const struct bt_mesh_dfu_target &target =
                nucode_mesh_distributor_instance.targets[index];
            const bool applied_with_same_composition =
                target.phase == BT_MESH_DFU_PHASE_APPLY_SUCCESS;
            const bool expected_unprovisioning =
                (target.effect == BT_MESH_DFU_EFFECT_UNPROV) &&
                (target.blob.acked == 0U) && (target.blob.timedout != 0U);
            if ((target.status != BT_MESH_DFU_SUCCESS) ||
                (!applied_with_same_composition && !expected_unprovisioning))
            {
                return false;
            }
        }
        return true;
    }

    /** @brief signed candidate와 negative image를 두 target에 배포합니다. */
    void driveDistribution()
    {
        if (!target_b_configured)
        {
            return;
        }
        if ((distribution_stage == DistributionStage::wait_wrong_image) ||
            (distribution_stage == DistributionStage::wait_partial_image) ||
            (distribution_stage == DistributionStage::wait_valid_image) ||
            (distribution_stage == DistributionStage::wait_next) ||
            (distribution_stage == DistributionStage::finished))
        {
            return;
        }
        const FirmwareDistributionTarget targets[] = {
            {static_cast<std::uint16_t>(target_a_address + 2U), 0U},
            {static_cast<std::uint16_t>(target_b_address + 2U), 0U},
        };
        FirmwareDistribution distribution{};
        distribution.version = {2U, 0U, 0U, 0U};
        distribution.image_size = M32_MDFU_CANDIDATE_SIZE;
        distribution.targets = targets;
        distribution.target_count = 2U;
        distribution.element_count = 4U;
        distribution.timeout_base = 10U;
        distribution.ttl = 7U;
        distribution.apply = true;
        distribution.preserve_composition = false;

        if (!wrong_key_rejected)
        {
            FirmwareDistribution wrong_key = distribution;
            wrong_key.app_key_index = 0x0FFFU;
            wrong_key_rejected = !NUCODEMeshUpdate.startDistribution(wrong_key);
            if (!wrong_key_rejected)
            {
                fail("wrong_key_accept");
                return;
            }
        }

        DistributionStage next_stage = DistributionStage::wait_valid_image;
        if (distribution_stage == DistributionStage::wrong_image)
        {
            distribution.version = {0U, 0U, 0U, 0U};
            next_stage = DistributionStage::wait_wrong_image;
        }
        else if (distribution_stage == DistributionStage::partial_image)
        {
            if (M32_MDFU_CANDIDATE_SIZE <= 16U)
            {
                fail("candidate_size");
                return;
            }
            const std::uint32_t shortened_size = M32_MDFU_CANDIDATE_SIZE - 16U;
            distribution.image_size = shortened_size < partial_image_size_limit
                                          ? shortened_size
                                          : partial_image_size_limit;
            next_stage = DistributionStage::wait_partial_image;
        }
        if (!NUCODEMeshUpdate.startDistribution(distribution))
        {
            fail("distribution_start", NUCODEMeshUpdate.lastDriverError());
            return;
        }
        distribution_stage = next_stage;
    }

    /** @brief negative 결과와 5회 배포의 10 target 분모를 기록합니다. */
    void finishDistribution()
    {
        if (complete)
        {
            return;
        }
        const UpdatePhase phase = NUCODEMeshUpdate.distributionPhase();
        if ((distribution_stage == DistributionStage::wait_wrong_image) ||
            (distribution_stage == DistributionStage::wait_partial_image))
        {
            if ((phase != UpdatePhase::failed) && (phase != UpdatePhase::completed))
            {
                return;
            }
            if (distributionTargetsSucceeded())
            {
                fail(distribution_stage == DistributionStage::wait_wrong_image
                         ? "wrong_image_accept"
                         : "partial_image_accept");
                return;
            }
            if (!NUCODEMeshUpdate.cancelDistribution())
            {
                fail("negative_cancel", NUCODEMeshUpdate.lastDriverError());
                return;
            }
            if (distribution_stage == DistributionStage::wait_wrong_image)
            {
                wrong_image_rejected = true;
                distribution_stage = DistributionStage::partial_image;
            }
            else
            {
                partial_image_rejected = true;
                distribution_stage = DistributionStage::valid_image;
            }
            return;
        }
        if (distribution_stage != DistributionStage::wait_valid_image)
        {
            return;
        }
        if (phase == UpdatePhase::failed)
        {
            fail("distribution", NUCODEMeshUpdate.lastDriverError());
            return;
        }
        if (phase != UpdatePhase::completed)
        {
            return;
        }
        if (!distributionTargetsSucceeded())
        {
            fail("target_status");
            return;
        }
        ++distribution_iteration;
        Serial.print(protocol);
        Serial.print("|ITERATION|role=distributor|iteration=");
        Serial.print(static_cast<unsigned int>(distribution_iteration));
        Serial.print("|targets=2|version=2.0.0+0");
        Serial.print("|signed_sha256=");
        Serial.print(M32_MDFU_CANDIDATE_SHA256);
        Serial.print("|image_size=");
        Serial.print(static_cast<unsigned long>(M32_MDFU_CANDIDATE_SIZE));
        printSuffix();
        Serial.println();
        if (distribution_iteration < distribution_iteration_target)
        {
            distribution_stage = DistributionStage::wait_next;
            return;
        }
        distribution_stage = DistributionStage::finished;
        Serial.print(protocol);
        Serial.print("|RESULT|role=distributor|iterations=5|targets=10|version=2.0.0+0");
        Serial.print("|signed_sha256=");
        Serial.print(M32_MDFU_CANDIDATE_SHA256);
        Serial.print("|image_size=");
        Serial.print(static_cast<unsigned long>(M32_MDFU_CANDIDATE_SIZE));
        Serial.print("|wrong_key_rejected=");
        Serial.print(wrong_key_rejected ? 1 : 0);
        Serial.print("|wrong_image_rejected=");
        Serial.print(wrong_image_rejected ? 1 : 0);
        Serial.print("|partial_image_rejected=");
        Serial.print(partial_image_rejected ? 1 : 0);
        printSuffix();
        Serial.println();
        Serial.print(protocol);
        Serial.print("|END|role=distributor|status=pass");
        printSuffix();
        Serial.println();
        complete = true;
    }
#endif

    /** @brief Firmware Distribution과 Mesh bearer를 정리합니다. */
    void stopSession()
    {
#if defined(NUCODE_M32_MDFU_DISTRIBUTOR)
        if (!NUCODEMeshUpdate.cancelDistribution())
        {
            fail("cancel_distribution", NUCODEMeshUpdate.lastDriverError());
            return;
        }
#endif
        const bool cleanup = NUCODEMesh.cancelProvisioning();
        const int suspend_error = bt_mesh_suspend();
        if (!cleanup || (suspend_error != 0))
        {
            fail("stop", suspend_error != 0 ? suspend_error : NUCODEMesh.lastDriverError());
            return;
        }
        Serial.print(protocol);
        Serial.print("|STOPPED|role=");
        Serial.print(roleName());
        Serial.print("|cleanup=pass");
        printSuffix();
        Serial.println();
    }

#if defined(NUCODE_M32_MDFU_DISTRIBUTOR) || defined(NUCODE_M32_MDFU_CANDIDATE)
    /** @brief 저장된 nonce와 iteration을 가진 후속 명령을 해석합니다. */
    bool parseIterationCommand(const char *prefix, std::uint8_t &iteration, const char *&suffix)
    {
        const std::size_t prefix_length = ::strlen(prefix);
        if (!nonce_valid || (::strncmp(command, prefix, prefix_length) != 0) ||
            (::strncmp(command + prefix_length, nonce, nonce_length) != 0))
        {
            return false;
        }
        constexpr char iteration_prefix[] = "|iteration=";
        const char *cursor = command + prefix_length + nonce_length;
        if (::strncmp(cursor, iteration_prefix, sizeof(iteration_prefix) - 1U) != 0)
        {
            return false;
        }
        cursor += sizeof(iteration_prefix) - 1U;
        if ((cursor[0] < '1') || (cursor[0] > '5'))
        {
            return false;
        }
        iteration = static_cast<std::uint8_t>(cursor[0] - '0');
        suffix = cursor + 1;
        return true;
    }
#endif

    /** @brief candidate 적용 완료를 confirm 또는 rollback 경로로 보고합니다. */
    bool applyCandidateCommand()
    {
#if defined(NUCODE_M32_MDFU_CANDIDATE)
        std::uint8_t iteration = 0U;
        const char *suffix = nullptr;
        if (!parseIterationCommand(apply_prefix, iteration, suffix))
        {
            return false;
        }
        constexpr char confirm_prefix[] = "|confirm=";
        if (::strncmp(suffix, confirm_prefix, sizeof(confirm_prefix) - 1U) != 0)
        {
            return false;
        }
        suffix += sizeof(confirm_prefix) - 1U;
        if (((suffix[0] != '0') && (suffix[0] != '1')) ||
            (::strncmp(suffix + 1, "|core=", 6U) != 0) ||
            (::strcmp(suffix + 7, M32_MDFU_CORE_REVISION) != 0))
        {
            return false;
        }
        if (candidate_applied)
        {
            fail("duplicate_apply");
            return true;
        }
        const bool confirm = suffix[0] == '1';
        if (confirm)
        {
            if (!NUCODEMeshUpdate.confirmRunningImage())
            {
                fail("confirm", NUCODEMeshUpdate.lastDriverError());
                return true;
            }
        }
        else
        {
            bt_mesh_dfu_srv_applied(&nucode_mesh_dfu_server_instance);
        }
        candidate_applied = true;
        Serial.print(protocol);
        Serial.print("|APPLIED|role=");
        Serial.print(roleName());
        Serial.print("|iteration=");
        Serial.print(static_cast<unsigned int>(iteration));
        Serial.print("|confirmed=");
        Serial.print(confirm ? 1 : 0);
        printSuffix();
        Serial.println();
        return true;
#else
        return false;
#endif
    }

    /** @brief 다음 valid 배포 iteration을 명시적으로 재개합니다. */
    bool nextDistributionCommand()
    {
#if defined(NUCODE_M32_MDFU_DISTRIBUTOR)
        std::uint8_t iteration = 0U;
        const char *suffix = nullptr;
        if (!parseIterationCommand(next_prefix, iteration, suffix))
        {
            return false;
        }
        if ((::strncmp(suffix, "|core=", 6U) != 0) ||
            (::strcmp(suffix + 6, M32_MDFU_CORE_REVISION) != 0))
        {
            return false;
        }
        const std::uint8_t expected = static_cast<std::uint8_t>(distribution_iteration + 1U);
        if ((distribution_stage != DistributionStage::wait_next) || (iteration != expected) ||
            !NUCODEMeshUpdate.cancelDistribution())
        {
            fail("next_distribution", NUCODEMeshUpdate.lastDriverError());
            return true;
        }
        distribution_stage = DistributionStage::valid_image;
        Serial.print(protocol);
        Serial.print("|NEXTED|role=distributor|iteration=");
        Serial.print(static_cast<unsigned int>(iteration));
        printSuffix();
        Serial.println();
        return true;
#else
        return false;
#endif
    }

    /** @brief PROBE·CLEAR·START·STOP 명령을 처리합니다. */
    void processCommand()
    {
        if (::strcmp(command, "M32MDFU|1|PROBE") == 0)
        {
            ActiveImage image{};
            if (!activeImage(image))
            {
                fail("probe_header");
                return;
            }
            Serial.print(protocol);
            Serial.print("|READY|role=");
            Serial.print(roleName());
            Serial.print("|version=");
            Serial.print(image.major);
            Serial.print('.');
            Serial.print(image.minor);
            Serial.print('.');
            Serial.print(image.revision);
            Serial.print('+');
            Serial.print(static_cast<unsigned long>(image.build));
            Serial.print("|confirmed=");
            Serial.print(image.confirmed ? 1 : 0);
            Serial.print("|cdb_node_slots=");
            Serial.print(CONFIG_BT_MESH_CDB_NODE_COUNT);
            Serial.print("|cdb_local_slots=1");
            Serial.print("|core=");
            Serial.println(M32_MDFU_CORE_REVISION);
            return;
        }
        if (applyCandidateCommand() || nextDistributionCommand())
        {
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
        if ((::strncmp(command, stop_prefix, sizeof(stop_prefix) - 1U) == 0) && nonce_valid &&
            (::strcmp(command + sizeof(stop_prefix) - 1U, nonce) == 0))
        {
            stopSession();
            return;
        }
        fail("command");
    }

    /** @brief CR/LF serial command를 overflow 없이 수집합니다. */
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
            if ((incoming < 0) || (command_length + 1U >= sizeof(command)))
            {
                command_length = 0U;
                fail("command_length");
                continue;
            }
            command[command_length++] = static_cast<char>(incoming);
        }
    }
} // namespace

/** @brief Mesh 역할과 signed image digest 검사를 준비합니다. */
void setup()
{
    Serial.begin(115200);
    Configuration configuration{};
#if defined(NUCODE_M32_MDFU_DISTRIBUTOR)
    configuration.role = Role::provisioner;
    configuration.local_address = distributor_address;
    configuration.uuid[15] = 0xD1U;
#else
    configuration.role = Role::node;
#if defined(NUCODE_M32_MDFU_TARGET_A)
    configuration.local_address = target_a_address;
    configuration.uuid[15] = 0xA1U;
#elif defined(NUCODE_M32_MDFU_TARGET_B)
    configuration.local_address = target_b_address;
    configuration.uuid[15] = 0xB2U;
#else
    configuration.local_address = target_a_address;
    configuration.uuid[15] = 0xC3U;
#endif
#endif
    configuration.uuid[0] = 0x32U;
    configuration.uuid[1] = 0x08U;
    configuration.uuid[2] = 0x54U;
    configuration.uuid[3] = 0x15U;
    NUCODEMesh.onEvent(onMeshEvent);
    if (!NUCODEMesh.begin(configuration))
    {
        fail("mesh_begin", NUCODEMesh.lastDriverError());
        return;
    }
    if (!NUCODEMeshUpdate.begin())
    {
        fail("update_begin", NUCODEMeshUpdate.lastDriverError());
        return;
    }
    loadNonce();

#if !defined(NUCODE_M32_MDFU_DISTRIBUTOR) && !defined(NUCODE_M32_MDFU_CANDIDATE)
    std::uint8_t digest[32]{};
    if (!candidateDigest(digest) ||
        !NUCODEMeshUpdate.expectImageDigest(digest, M32_MDFU_CANDIDATE_SIZE))
    {
        fail("candidate_digest", NUCODEMeshUpdate.lastDriverError());
        return;
    }
#endif

#if defined(NUCODE_M32_MDFU_CANDIDATE)
    ActiveImage image{};
    if (!activeImage(image) || (image.major != 2U))
    {
        fail("candidate_version");
        return;
    }
    if ((bt_mesh_primary_addr() != target_a_address) &&
        (bt_mesh_primary_addr() != target_b_address))
    {
        fail("candidate_address", bt_mesh_primary_addr());
        return;
    }
#endif
    reportBoot();
}

/** @brief provisioning·distribution과 bounded UART protocol을 진행합니다. */
void loop()
{
    NUCODEMesh.poll();
    pollSerial();
    if (failed)
    {
        return;
    }
#if defined(NUCODE_M32_MDFU_DISTRIBUTOR)
    if (started && !complete)
    {
        driveProvisioning();
        driveConfiguration();
        driveDistribution();
        finishDistribution();
        if (k_uptime_get() >= progress_deadline_ms)
        {
            Serial.print(protocol);
            Serial.print("|PROGRESS|role=distributor|phase=");
            Serial.print(static_cast<unsigned int>(NUCODEMeshUpdate.distributionPhase()));
            printSuffix();
            Serial.println();
            progress_deadline_ms = k_uptime_get() + 5000;
        }
    }
#endif
    if (started && (k_uptime_get() >= deadline_ms))
    {
        fail("timeout");
    }
    delay(1);
}
