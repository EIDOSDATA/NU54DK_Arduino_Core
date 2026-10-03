/**
 * @file NUCODE_BLE_Mesh_Update.cpp
 * @brief Bluetooth Mesh BLOB·DFU·Distributor와 MCUboot backend입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#if !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE)

#include "NUCODE_BLE_Mesh_Update.h"

#include <zephyr/bluetooth/mesh.h>
#include <zephyr/bluetooth/mesh/blob_cli.h>
#include <zephyr/bluetooth/mesh/blob_io_flash.h>
#include <zephyr/bluetooth/mesh/blob_srv.h>
#include <zephyr/bluetooth/mesh/cfg.h>
#include <zephyr/bluetooth/mesh/dfd_srv.h>
#include <zephyr/bluetooth/mesh/dfu_metadata.h>
#include <zephyr/bluetooth/mesh/dfu_srv.h>
#include <zephyr/dfu/mcuboot.h>
#include <zephyr/storage/flash_map.h>
#include <zephyr/sys/byteorder.h>
#include <zephyr/sys/reboot.h>

extern "C"
{
#include "mesh/dfd_srv_internal.h"
#include "mesh/dfu_slot.h"
}

#include <errno.h>
#include <string.h>

extern "C"
{
    extern struct bt_mesh_blob_srv nucode_mesh_blob_server_instance;
    extern struct bt_mesh_blob_cli nucode_mesh_blob_client_instance;
    extern struct bt_mesh_dfu_srv nucode_mesh_dfu_server_instance;
    extern struct bt_mesh_dfd_srv nucode_mesh_distributor_instance;
}

namespace
{
    using nucode::mesh::BlobTransfer;
    using nucode::mesh::BlobTransferMode;
    using nucode::mesh::FirmwareDistribution;
    using nucode::mesh::UpdateError;
    using nucode::mesh::UpdatePhase;

    struct FirmwareIdentity
    {
        std::uint16_t company_id;
        std::uint8_t major;
        std::uint8_t minor;
        std::uint16_t revision;
        std::uint32_t build;
    } __packed;

    struct UpdateContext
    {
        bool started = false;
        bool expected_digest_valid = false;
        bool apply_pending = false;
        std::uint8_t expected_digest[32]{};
        std::uint32_t expected_image_size = 0U;
        std::size_t slot_size = 0U;
        UpdatePhase phase = UpdatePhase::idle;
        UpdatePhase distribution_phase = UpdatePhase::idle;
        UpdateError error = UpdateError::none;
        int driver_error = 0;
        struct mcuboot_img_sem_ver current_version{};
        struct bt_mesh_blob_io_flash flash_stream{};
        struct bt_mesh_blob_cli_inputs client_inputs{};
        struct bt_mesh_blob_xfer client_transfer{};
        struct bt_mesh_blob_target client_targets[BlobTransfer::target_capacity]{};
        struct bt_mesh_blob_target_pull pull_contexts[BlobTransfer::target_capacity]{};
    };

    UpdateContext update_context{};
    FirmwareIdentity firmware_identity{};

    bool fail(UpdateError error, int driver_error = 0) noexcept
    {
        update_context.error = error;
        update_context.driver_error = driver_error;
        if (error != UpdateError::busy)
        {
            update_context.phase = UpdatePhase::failed;
        }
        return false;
    }

    bool success() noexcept
    {
        update_context.error = UpdateError::none;
        update_context.driver_error = 0;
        return true;
    }

    bool requireStarted() noexcept
    {
        if (!update_context.started)
        {
            return fail(UpdateError::not_started);
        }
        return true;
    }

    std::size_t partitionSize(std::uint8_t area_id) noexcept
    {
        const struct flash_area *area = nullptr;
        if (flash_area_open(area_id, &area) != 0)
        {
            return 0U;
        }
        const std::size_t size = area->fa_size;
        flash_area_close(area);
        return size;
    }

    bool newerVersion(const struct mcuboot_img_sem_ver &candidate,
                      const struct mcuboot_img_sem_ver &current) noexcept
    {
        if (candidate.major != current.major)
        {
            return candidate.major > current.major;
        }
        if (candidate.minor != current.minor)
        {
            return candidate.minor > current.minor;
        }
        if (candidate.revision != current.revision)
        {
            return candidate.revision > current.revision;
        }
        return candidate.build_num > current.build_num;
    }

    int verifyDigest(const std::uint8_t digest[32], std::uint32_t image_size) noexcept
    {
        if ((digest == nullptr) || (image_size == 0U) || (image_size > update_context.slot_size))
        {
            return -EINVAL;
        }

        const struct flash_area *area = nullptr;
        int error = flash_area_open(PARTITION_ID(slot1_partition), &area);
        if (error != 0)
        {
            return error;
        }

        std::uint8_t read_buffer[256]{};
        struct flash_area_check check{};
        check.match = digest;
        check.clen = image_size;
        check.off = 0;
        check.rbuf = read_buffer;
        check.rblen = sizeof(read_buffer);
        error = flash_area_check_int_sha256(area, &check);
        flash_area_close(area);
        return error;
    }

    int validateStagedImage() noexcept
    {
        struct mcuboot_img_header header{};
        const int header_error =
            boot_read_bank_header(PARTITION_ID(slot1_partition), &header, sizeof(header));
        if ((header_error != 0) || (header.mcuboot_version != 1U))
        {
            return header_error != 0 ? header_error : -EBADMSG;
        }
        if (update_context.expected_digest_valid)
        {
            return verifyDigest(update_context.expected_digest, update_context.expected_image_size);
        }
        return 0;
    }

    int rawServerStart(struct bt_mesh_blob_srv *server, struct bt_mesh_msg_ctx *message_context,
                       struct bt_mesh_blob_xfer *transfer)
    {
        (void)server;
        (void)message_context;
        if ((transfer == nullptr) || (transfer->size == 0U) ||
            (transfer->size > update_context.slot_size))
        {
            return -ENOMEM;
        }
        update_context.phase = UpdatePhase::transferring;
        return 0;
    }

    void rawServerEnd(struct bt_mesh_blob_srv *server, std::uint64_t id, bool succeeded)
    {
        (void)server;
        (void)id;
        update_context.phase = succeeded ? UpdatePhase::completed : UpdatePhase::failed;
    }

    void rawServerSuspended(struct bt_mesh_blob_srv *server)
    {
        (void)server;
        update_context.phase = UpdatePhase::suspended;
    }

    void rawServerResume(struct bt_mesh_blob_srv *server)
    {
        (void)server;
        update_context.phase = UpdatePhase::transferring;
    }

    int rawServerRecover(struct bt_mesh_blob_srv *server, struct bt_mesh_blob_xfer *transfer,
                         const struct bt_mesh_blob_io **io)
    {
        (void)server;
        (void)transfer;
        *io = &update_context.flash_stream.io;
        update_context.phase = UpdatePhase::transferring;
        return 0;
    }

    void rawClientLostTarget(struct bt_mesh_blob_cli *client, struct bt_mesh_blob_target *target,
                             enum bt_mesh_blob_status reason)
    {
        (void)client;
        (void)target;
        update_context.error = UpdateError::driver_error;
        update_context.driver_error = -static_cast<int>(reason) - 1;
    }

    void rawClientSuspended(struct bt_mesh_blob_cli *client)
    {
        (void)client;
        update_context.phase = UpdatePhase::suspended;
    }

    void rawClientEnd(struct bt_mesh_blob_cli *client, const struct bt_mesh_blob_xfer *transfer,
                      bool succeeded)
    {
        (void)client;
        (void)transfer;
        update_context.phase = succeeded ? UpdatePhase::completed : UpdatePhase::failed;
    }

    int metadataCheck(struct bt_mesh_dfu_srv *server, const struct bt_mesh_dfu_img *image,
                      struct net_buf_simple *raw_metadata, enum bt_mesh_dfu_effect *effect)
    {
        (void)server;
        (void)image;
        struct bt_mesh_dfu_metadata metadata{};
        const int error = bt_mesh_dfu_metadata_decode(raw_metadata, &metadata);
        if (error != 0)
        {
            return error;
        }

        struct mcuboot_img_sem_ver version{};
        version.major = metadata.fw_ver.major;
        version.minor = metadata.fw_ver.minor;
        version.revision = metadata.fw_ver.revision;
        version.build_num = metadata.fw_ver.build_num;
        if (!newerVersion(version, update_context.current_version) ||
            ((metadata.fw_core_type & BT_MESH_DFU_FW_CORE_TYPE_APP) == 0U) ||
            (metadata.fw_size == 0U) || (metadata.fw_size > update_context.slot_size))
        {
            return -EINVAL;
        }

        std::uint8_t key[16]{};
        std::uint32_t local_hash = 0U;
        const int hash_error = bt_mesh_dfu_metadata_comp_hash_local_get(key, &local_hash);
        if (hash_error != 0)
        {
            return hash_error;
        }
        *effect =
            local_hash == metadata.comp_hash ? BT_MESH_DFU_EFFECT_NONE : BT_MESH_DFU_EFFECT_UNPROV;
        return 0;
    }

    int dfuStart(struct bt_mesh_dfu_srv *server, const struct bt_mesh_dfu_img *image,
                 struct net_buf_simple *metadata, const struct bt_mesh_blob_io **io)
    {
        (void)server;
        (void)image;
        (void)metadata;
        if (bt_mesh_blob_cli_is_busy(&nucode_mesh_blob_client_instance) ||
            bt_mesh_blob_srv_is_busy(&nucode_mesh_blob_server_instance))
        {
            return -EBUSY;
        }
        *io = &update_context.flash_stream.io;
        update_context.phase = UpdatePhase::transferring;
        return 0;
    }

    void dfuEnd(struct bt_mesh_dfu_srv *server, const struct bt_mesh_dfu_img *image, bool succeeded)
    {
        (void)image;
        if (!succeeded)
        {
            update_context.phase = UpdatePhase::failed;
            return;
        }
        const int error = validateStagedImage();
        if (error == 0)
        {
            update_context.phase = UpdatePhase::verified;
            bt_mesh_dfu_srv_verified(server);
        }
        else
        {
            update_context.error = update_context.expected_digest_valid
                                       ? UpdateError::digest_mismatch
                                       : UpdateError::invalid_image;
            update_context.driver_error = error;
            update_context.phase = UpdatePhase::failed;
            bt_mesh_dfu_srv_rejected(server);
        }
    }

    int dfuRecover(struct bt_mesh_dfu_srv *server, const struct bt_mesh_dfu_img *image,
                   const struct bt_mesh_blob_io **io)
    {
        (void)server;
        (void)image;
        *io = &update_context.flash_stream.io;
        update_context.phase = UpdatePhase::transferring;
        return 0;
    }

    int dfuApply(struct bt_mesh_dfu_srv *server, const struct bt_mesh_dfu_img *image)
    {
        (void)server;
        (void)image;
        const int error = boot_request_upgrade(BOOT_UPGRADE_TEST);
        if (error != 0)
        {
            update_context.driver_error = error;
            update_context.phase = UpdatePhase::failed;
            return error;
        }
        update_context.apply_pending = true;
        update_context.phase = UpdatePhase::apply_pending;
        sys_reboot(SYS_REBOOT_WARM);
        return 0;
    }

    int distributorReceive(struct bt_mesh_dfd_srv *server, const struct bt_mesh_dfu_slot *slot,
                           const struct bt_mesh_blob_io **io)
    {
        (void)server;
        if ((slot == nullptr) || (slot->size == 0U) || (slot->size > update_context.slot_size))
        {
            return -ENOMEM;
        }
        *io = &update_context.flash_stream.io;
        return 0;
    }

    void distributorDelete(struct bt_mesh_dfd_srv *server, const struct bt_mesh_dfu_slot *slot)
    {
        (void)server;
        (void)slot;
        update_context.distribution_phase = UpdatePhase::idle;
    }

    int distributorSend(struct bt_mesh_dfd_srv *server, const struct bt_mesh_dfu_slot *slot,
                        const struct bt_mesh_blob_io **io)
    {
        (void)server;
        if ((slot == nullptr) || (slot->size == 0U) || (slot->size > update_context.slot_size))
        {
            return -EINVAL;
        }
        *io = &update_context.flash_stream.io;
        return 0;
    }

    void distributorPhase(struct bt_mesh_dfd_srv *server, enum bt_mesh_dfd_phase phase)
    {
        (void)server;
        switch (phase)
        {
        case BT_MESH_DFD_PHASE_IDLE:
            update_context.distribution_phase = UpdatePhase::idle;
            break;
        case BT_MESH_DFD_PHASE_TRANSFER_ACTIVE:
            update_context.distribution_phase = UpdatePhase::transferring;
            break;
        case BT_MESH_DFD_PHASE_TRANSFER_SUSPENDED:
            update_context.distribution_phase = UpdatePhase::suspended;
            break;
        case BT_MESH_DFD_PHASE_TRANSFER_SUCCESS:
            update_context.distribution_phase = UpdatePhase::verified;
            break;
        case BT_MESH_DFD_PHASE_APPLYING_UPDATE:
            update_context.distribution_phase = UpdatePhase::apply_pending;
            break;
        case BT_MESH_DFD_PHASE_COMPLETED:
            update_context.distribution_phase = UpdatePhase::completed;
            break;
        default:
            update_context.distribution_phase = UpdatePhase::failed;
            break;
        }
    }

    const struct bt_mesh_blob_srv_cb raw_server_callbacks = {
        .start = rawServerStart,
        .end = rawServerEnd,
        .suspended = rawServerSuspended,
        .resume = rawServerResume,
        .recover = rawServerRecover,
    };

    const struct bt_mesh_blob_cli_cb raw_client_callbacks = {
        .lost_target = rawClientLostTarget,
        .suspended = rawClientSuspended,
        .end = rawClientEnd,
    };

    const struct bt_mesh_dfu_srv_cb dfu_callbacks = {
        .check = metadataCheck,
        .start = dfuStart,
        .end = dfuEnd,
        .recover = dfuRecover,
        .apply = dfuApply,
    };

    const struct bt_mesh_dfd_srv_cb distributor_callbacks = {
        .recv = distributorReceive,
        .del = distributorDelete,
        .send = distributorSend,
        .phase = distributorPhase,
    };

    struct bt_mesh_dfu_img update_images[] = {
        {
            .fwid = &firmware_identity,
            .fwid_len = sizeof(firmware_identity),
            .uri = nullptr,
        },
    };
} // namespace

extern "C"
{
    struct bt_mesh_blob_srv nucode_mesh_blob_server_instance = {
        .cb = &raw_server_callbacks,
    };
    struct bt_mesh_blob_cli nucode_mesh_blob_client_instance = {
        .cb = &raw_client_callbacks,
    };
    struct bt_mesh_dfu_srv nucode_mesh_dfu_server_instance =
        BT_MESH_DFU_SRV_INIT(&dfu_callbacks, update_images, ARRAY_SIZE(update_images));
    struct bt_mesh_dfd_srv nucode_mesh_distributor_instance =
        BT_MESH_DFD_SRV_INIT(&distributor_callbacks);
}

namespace nucode::mesh
{
    bool MeshUpdate::begin() noexcept
    {
        struct mcuboot_img_header header{};
        int error = boot_read_bank_header(PARTITION_ID(slot0_partition), &header, sizeof(header));
        if ((error != 0) || (header.mcuboot_version != 1U))
        {
            return fail(UpdateError::invalid_image, error != 0 ? error : -EBADMSG);
        }

        update_context.slot_size = partitionSize(PARTITION_ID(slot1_partition));
        if (update_context.slot_size == 0U)
        {
            return fail(UpdateError::driver_error, -ENODEV);
        }
        error = bt_mesh_blob_io_flash_init(&update_context.flash_stream,
                                           PARTITION_ID(slot1_partition), 0);
        if (error != 0)
        {
            return fail(UpdateError::driver_error, error);
        }

        update_context.current_version = header.h.v1.sem_ver;
        firmware_identity.company_id = sys_cpu_to_le16(CONFIG_BT_COMPANY_ID);
        firmware_identity.major = header.h.v1.sem_ver.major;
        firmware_identity.minor = header.h.v1.sem_ver.minor;
        firmware_identity.revision = sys_cpu_to_le16(header.h.v1.sem_ver.revision);
        firmware_identity.build = sys_cpu_to_le32(header.h.v1.sem_ver.build_num);
        if (boot_is_img_confirmed() &&
            (nucode_mesh_dfu_server_instance.update.phase == BT_MESH_DFU_PHASE_APPLYING))
        {
            bt_mesh_dfu_srv_applied(&nucode_mesh_dfu_server_instance);
        }
        update_context.started = true;
        update_context.phase = UpdatePhase::idle;
        update_context.distribution_phase = UpdatePhase::idle;
        return success();
    }

    bool MeshUpdate::prepareBlobReceive(std::uint64_t id, std::uint8_t ttl,
                                        std::uint16_t timeout_base) noexcept
    {
        if (!requireStarted())
        {
            return false;
        }
        if ((id == 0U) || (ttl > 0x7FU))
        {
            return fail(UpdateError::invalid_argument);
        }
        const int error = bt_mesh_blob_srv_recv(&nucode_mesh_blob_server_instance, id,
                                                &update_context.flash_stream.io, ttl, timeout_base);
        if (error != 0)
        {
            return fail(error == -EBUSY ? UpdateError::busy : UpdateError::driver_error, error);
        }
        update_context.phase = UpdatePhase::transferring;
        return success();
    }

    bool MeshUpdate::sendBlob(const BlobTransfer &transfer) noexcept
    {
        if (!requireStarted())
        {
            return false;
        }
        if ((transfer.id == 0U) || (transfer.size == 0U) ||
            (transfer.size > update_context.slot_size) || (transfer.targets == nullptr) ||
            (transfer.target_count == 0U) ||
            (transfer.target_count > BlobTransfer::target_capacity) || (transfer.ttl > 0x7FU) ||
            (transfer.app_key_index > 0x0FFFU) || !bt_mesh_app_key_exists(transfer.app_key_index) ||
            (transfer.block_size_log < 6U) || (transfer.block_size_log > 20U) ||
            (transfer.chunk_size == 0U))
        {
            return fail(UpdateError::invalid_argument);
        }

        sys_slist_init(&update_context.client_inputs.targets);
        memset(update_context.client_targets, 0, sizeof(update_context.client_targets));
        memset(update_context.pull_contexts, 0, sizeof(update_context.pull_contexts));
        for (std::size_t index = 0U; index < transfer.target_count; ++index)
        {
            if ((transfer.targets[index].address == 0U) ||
                (transfer.targets[index].address > 0x7FFFU))
            {
                return fail(UpdateError::invalid_argument);
            }
            update_context.client_targets[index].addr = transfer.targets[index].address;
            update_context.client_targets[index].status = BT_MESH_BLOB_SUCCESS;
            update_context.client_targets[index].pull = &update_context.pull_contexts[index];
            sys_slist_append(&update_context.client_inputs.targets,
                             &update_context.client_targets[index].n);
        }

        update_context.client_inputs.app_idx = transfer.app_key_index;
        update_context.client_inputs.group = transfer.group_address;
        update_context.client_inputs.ttl = transfer.ttl;
        update_context.client_inputs.timeout_base = transfer.timeout_base;
        update_context.client_transfer.id = transfer.id;
        update_context.client_transfer.size = transfer.size;
        update_context.client_transfer.mode = transfer.mode == BlobTransferMode::pull
                                                  ? BT_MESH_BLOB_XFER_MODE_PULL
                                                  : BT_MESH_BLOB_XFER_MODE_PUSH;
        update_context.client_transfer.block_size_log = transfer.block_size_log;
        update_context.client_transfer.chunk_size = transfer.chunk_size;
        bt_mesh_blob_cli_set_chunk_interval_ms(&nucode_mesh_blob_client_instance,
                                               transfer.chunk_interval_ms);
        const int error =
            bt_mesh_blob_cli_send(&nucode_mesh_blob_client_instance, &update_context.client_inputs,
                                  &update_context.client_transfer, &update_context.flash_stream.io);
        if (error != 0)
        {
            return fail(error == -EBUSY ? UpdateError::busy : UpdateError::driver_error, error);
        }
        update_context.phase = UpdatePhase::transferring;
        return success();
    }

    bool MeshUpdate::suspendBlob() noexcept
    {
        if (!requireStarted())
        {
            return false;
        }
        const int error = bt_mesh_blob_cli_suspend(&nucode_mesh_blob_client_instance);
        if (error != 0)
        {
            return fail(UpdateError::driver_error, error);
        }
        update_context.phase = UpdatePhase::suspended;
        return success();
    }

    bool MeshUpdate::resumeBlob() noexcept
    {
        if (!requireStarted())
        {
            return false;
        }
        const int error = bt_mesh_blob_cli_resume(&nucode_mesh_blob_client_instance);
        if (error != 0)
        {
            return fail(UpdateError::driver_error, error);
        }
        update_context.phase = UpdatePhase::transferring;
        return success();
    }

    void MeshUpdate::cancelBlob() noexcept
    {
        if (!update_context.started)
        {
            return;
        }
        bt_mesh_blob_cli_cancel(&nucode_mesh_blob_client_instance);
        static_cast<void>(bt_mesh_blob_srv_cancel(&nucode_mesh_blob_server_instance));
        update_context.phase = UpdatePhase::idle;
    }

    std::uint8_t MeshUpdate::clientProgress() const noexcept
    {
        return bt_mesh_blob_cli_xfer_progress_active_get(&nucode_mesh_blob_client_instance);
    }

    std::uint8_t MeshUpdate::serverProgress() const noexcept
    {
        return bt_mesh_blob_srv_progress(&nucode_mesh_blob_server_instance);
    }

    bool MeshUpdate::busy() const noexcept
    {
        return bt_mesh_blob_cli_is_busy(&nucode_mesh_blob_client_instance) ||
               bt_mesh_blob_srv_is_busy(&nucode_mesh_blob_server_instance) ||
               bt_mesh_dfu_srv_is_busy(&nucode_mesh_dfu_server_instance);
    }

    bool MeshUpdate::expectImageDigest(const std::uint8_t digest[32],
                                       std::uint32_t image_size) noexcept
    {
        if (!requireStarted())
        {
            return false;
        }
        if ((digest == nullptr) || (image_size == 0U) || (image_size > update_context.slot_size))
        {
            return fail(UpdateError::invalid_argument);
        }
        memcpy(update_context.expected_digest, digest, sizeof(update_context.expected_digest));
        update_context.expected_image_size = image_size;
        update_context.expected_digest_valid = true;
        return success();
    }

    bool MeshUpdate::verifyStagedDigest(const std::uint8_t digest[32],
                                        std::uint32_t image_size) noexcept
    {
        if (!requireStarted())
        {
            return false;
        }
        const int error = verifyDigest(digest, image_size);
        if (error != 0)
        {
            return fail(error == -EILSEQ ? UpdateError::digest_mismatch : UpdateError::driver_error,
                        error);
        }
        return success();
    }

    bool MeshUpdate::requestTestUpgrade() noexcept
    {
        if (!requireStarted())
        {
            return false;
        }
        const int validation_error = validateStagedImage();
        if (validation_error != 0)
        {
            return fail(update_context.expected_digest_valid ? UpdateError::digest_mismatch
                                                             : UpdateError::invalid_image,
                        validation_error);
        }
        const int error = boot_request_upgrade(BOOT_UPGRADE_TEST);
        if (error != 0)
        {
            return fail(UpdateError::driver_error, error);
        }
        update_context.apply_pending = true;
        update_context.phase = UpdatePhase::apply_pending;
        return success();
    }

    bool MeshUpdate::confirmRunningImage() noexcept
    {
        if (!requireStarted())
        {
            return false;
        }
        const int error = boot_write_img_confirmed();
        if (error != 0)
        {
            return fail(UpdateError::driver_error, error);
        }
        bt_mesh_dfu_srv_applied(&nucode_mesh_dfu_server_instance);
        update_context.apply_pending = false;
        update_context.phase = UpdatePhase::completed;
        return success();
    }

    bool MeshUpdate::startDistribution(const FirmwareDistribution &distribution) noexcept
    {
        if (!requireStarted())
        {
            return false;
        }
        if ((distribution.image_size == 0U) ||
            (distribution.image_size > update_context.slot_size) ||
            (distribution.targets == nullptr) || (distribution.target_count == 0U) ||
            (distribution.target_count > FirmwareDistribution::target_capacity) ||
            (distribution.app_key_index > 0x0FFFU) ||
            !bt_mesh_app_key_exists(distribution.app_key_index) || (distribution.ttl > 0x7FU) ||
            (distribution.element_count == 0U))
        {
            return fail(UpdateError::invalid_argument);
        }
        for (std::size_t index = 0U; index < distribution.target_count; ++index)
        {
            const std::uint16_t address = distribution.targets[index].address;
            if ((address == 0U) || (address > 0x7FFFU))
            {
                return fail(UpdateError::invalid_argument);
            }
        }

        const enum bt_mesh_dfd_status clear_status =
            bt_mesh_dfd_srv_receivers_delete_all(&nucode_mesh_distributor_instance);
        if (clear_status != BT_MESH_DFD_SUCCESS)
        {
            return fail(UpdateError::busy, -static_cast<int>(clear_status) - 1);
        }
        bt_mesh_dfu_slot_del_all();

        struct bt_mesh_dfu_slot *slot = bt_mesh_dfu_slot_reserve();
        if (slot == nullptr)
        {
            return fail(UpdateError::driver_error, -ENOMEM);
        }

        std::uint8_t composition_key[16]{};
        std::uint32_t composition_hash = 0U;
        int error = bt_mesh_dfu_metadata_comp_hash_local_get(composition_key, &composition_hash);
        if (error != 0)
        {
            bt_mesh_dfu_slot_release(slot);
            return fail(UpdateError::driver_error, error);
        }

        struct bt_mesh_dfu_metadata metadata{};
        metadata.fw_ver.major = distribution.version.major;
        metadata.fw_ver.minor = distribution.version.minor;
        metadata.fw_ver.revision = distribution.version.revision;
        metadata.fw_ver.build_num = distribution.version.build;
        metadata.fw_size = distribution.image_size;
        metadata.fw_core_type = BT_MESH_DFU_FW_CORE_TYPE_APP;
        metadata.comp_hash = distribution.preserve_composition
                                 ? composition_hash
                                 : ~composition_hash;
        metadata.elems = distribution.element_count;
        NET_BUF_SIMPLE_DEFINE(metadata_buffer, CONFIG_BT_MESH_DFU_METADATA_MAXLEN);
        error = bt_mesh_dfu_metadata_encode(&metadata, &metadata_buffer);
        if (error != 0)
        {
            bt_mesh_dfu_slot_release(slot);
            return fail(UpdateError::driver_error, error);
        }

        FirmwareIdentity identity{};
        identity.company_id = sys_cpu_to_le16(CONFIG_BT_COMPANY_ID);
        identity.major = distribution.version.major;
        identity.minor = distribution.version.minor;
        identity.revision = sys_cpu_to_le16(distribution.version.revision);
        identity.build = sys_cpu_to_le32(distribution.version.build);
        error = bt_mesh_dfu_slot_fwid_set(slot, reinterpret_cast<const std::uint8_t *>(&identity),
                                          sizeof(identity));
        if (error == 0)
        {
            error = bt_mesh_dfu_slot_info_set(slot, distribution.image_size, metadata_buffer.data,
                                              metadata_buffer.len);
        }
        if (error == 0)
        {
            error = bt_mesh_dfu_slot_commit(slot);
        }
        if (error != 0)
        {
            bt_mesh_dfu_slot_release(slot);
            return fail(UpdateError::driver_error, error);
        }

        for (std::size_t index = 0U; index < distribution.target_count; ++index)
        {
            const enum bt_mesh_dfd_status add_status = bt_mesh_dfd_srv_receiver_add(
                &nucode_mesh_distributor_instance, distribution.targets[index].address,
                distribution.targets[index].image_index);
            if (add_status != BT_MESH_DFD_SUCCESS)
            {
                static_cast<void>(
                    bt_mesh_dfd_srv_receivers_delete_all(&nucode_mesh_distributor_instance));
                return fail(UpdateError::driver_error, -static_cast<int>(add_status) - 1);
            }
        }

        const int slot_index = bt_mesh_dfu_slot_img_idx_get(slot);
        if (slot_index < 0)
        {
            return fail(UpdateError::driver_error, slot_index);
        }
        struct bt_mesh_dfd_start_params parameters{};
        parameters.app_idx = distribution.app_key_index;
        parameters.timeout_base = distribution.timeout_base;
        parameters.slot_idx = static_cast<std::uint16_t>(slot_index);
        parameters.group = distribution.group_address;
        parameters.xfer_mode = distribution.mode == BlobTransferMode::pull
                                   ? BT_MESH_BLOB_XFER_MODE_PULL
                                   : BT_MESH_BLOB_XFER_MODE_PUSH;
        parameters.ttl = distribution.ttl;
        parameters.apply = distribution.apply;
        const enum bt_mesh_dfd_status start_status =
            bt_mesh_dfd_srv_start(&nucode_mesh_distributor_instance, &parameters);
        if (start_status != BT_MESH_DFD_SUCCESS)
        {
            return fail(UpdateError::driver_error, -static_cast<int>(start_status) - 1);
        }
        update_context.distribution_phase = UpdatePhase::transferring;
        return success();
    }

    bool MeshUpdate::cancelDistribution() noexcept
    {
        if (!requireStarted())
        {
            return false;
        }
        const enum bt_mesh_dfd_status status =
            bt_mesh_dfd_srv_cancel(&nucode_mesh_distributor_instance, nullptr);
        if (status != BT_MESH_DFD_SUCCESS)
        {
            return fail(UpdateError::driver_error, -static_cast<int>(status) - 1);
        }
        const enum bt_mesh_dfd_status clear_status =
            bt_mesh_dfd_srv_receivers_delete_all(&nucode_mesh_distributor_instance);
        if (clear_status != BT_MESH_DFD_SUCCESS)
        {
            return fail(UpdateError::driver_error, -static_cast<int>(clear_status) - 1);
        }
        update_context.distribution_phase = UpdatePhase::idle;
        return success();
    }

    void MeshUpdate::rebootToApply() noexcept
    {
        if (update_context.started && update_context.apply_pending)
        {
            sys_reboot(SYS_REBOOT_WARM);
        }
    }

    UpdatePhase MeshUpdate::phase() const noexcept
    {
        return update_context.phase;
    }

    UpdatePhase MeshUpdate::distributionPhase() const noexcept
    {
        return update_context.distribution_phase;
    }

    UpdateError MeshUpdate::lastError() const noexcept
    {
        return update_context.error;
    }

    int MeshUpdate::lastDriverError() const noexcept
    {
        return update_context.driver_error;
    }
} // namespace nucode::mesh

nucode::mesh::MeshUpdate NUCODEMeshUpdate;

#endif
