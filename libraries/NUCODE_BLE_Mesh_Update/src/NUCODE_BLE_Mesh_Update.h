/**
 * @file NUCODE_BLE_Mesh_Update.h
 * @brief Bluetooth Mesh BLOB 전송과 서명 firmware update 공개 API입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#ifndef NUCODE_BLE_MESH_UPDATE_H
#define NUCODE_BLE_MESH_UPDATE_H

#include <NUCODE_BLE_Mesh.h>

#include <cstddef>
#include <cstdint>

namespace nucode::mesh
{
    /** @brief BLOB 전송 방향입니다. */
    enum class BlobTransferMode : std::uint8_t
    {
        push,
        pull,
    };

    /** @brief BLOB을 받을 Mesh node의 유한 주소 정보입니다. */
    struct BlobTarget
    {
        std::uint16_t address = 0U;
    };

    /** @brief BLOB Client 전송 parameter입니다. */
    struct BlobTransfer
    {
        static constexpr std::size_t target_capacity = 4U;

        std::uint64_t id = 0U;
        std::uint32_t size = 0U;
        const BlobTarget *targets = nullptr;
        std::size_t target_count = 0U;
        std::uint16_t app_key_index = 0U;
        std::uint16_t group_address = 0U;
        std::uint16_t timeout_base = 1U;
        std::uint16_t chunk_size = 128U;
        std::uint32_t chunk_interval_ms = 20U;
        std::uint8_t ttl = 7U;
        std::uint8_t block_size_log = 12U;
        BlobTransferMode mode = BlobTransferMode::push;
    };

    /** @brief Mesh DFU metadata에 넣을 signed firmware version입니다. */
    struct FirmwareVersion
    {
        std::uint8_t major = 0U;
        std::uint8_t minor = 0U;
        std::uint16_t revision = 0U;
        std::uint32_t build = 0U;
    };

    /** @brief Firmware Distributor가 갱신할 target과 image index입니다. */
    struct FirmwareDistributionTarget
    {
        std::uint16_t address = 0U;
        std::uint8_t image_index = 0U;
    };

    /** @brief inactive slot의 signed image를 배포하는 유한 parameter입니다. */
    struct FirmwareDistribution
    {
        static constexpr std::size_t target_capacity = 4U;

        FirmwareVersion version{};
        std::uint32_t image_size = 0U;
        const FirmwareDistributionTarget *targets = nullptr;
        std::size_t target_count = 0U;
        std::uint16_t app_key_index = 0U;
        std::uint16_t group_address = 0U;
        std::uint16_t timeout_base = 1U;
        std::uint16_t element_count = 0U;
        std::uint8_t ttl = 7U;
        bool apply = true;
        bool preserve_composition = true;
        BlobTransferMode mode = BlobTransferMode::push;
    };

    /** @brief Mesh update 처리 단계입니다. */
    enum class UpdatePhase : std::uint8_t
    {
        idle,
        transferring,
        suspended,
        verified,
        apply_pending,
        completed,
        failed,
    };

    /** @brief Mesh update 공개 오류입니다. */
    enum class UpdateError : std::uint8_t
    {
        none,
        not_started,
        invalid_argument,
        busy,
        invalid_image,
        digest_mismatch,
        driver_error,
    };

    /** @brief BLOB과 Mesh DFU를 inactive slot에 연결하는 bounded API입니다. */
    class MeshUpdate final
    {
      public:
        /** @brief 내부 slot stream과 현재 MCUboot image identity를 준비합니다. */
        [[nodiscard]] bool begin() noexcept;

        /** @brief raw BLOB Server가 지정 ID를 inactive slot으로 받도록 준비합니다. */
        [[nodiscard]] bool prepareBlobReceive(std::uint64_t id, std::uint8_t ttl = 7U,
                                              std::uint16_t timeout_base = 1U) noexcept;

        /** @brief inactive slot의 BLOB을 push 또는 pull mode로 전송합니다. */
        [[nodiscard]] bool sendBlob(const BlobTransfer &transfer) noexcept;

        /** @brief BLOB Client 전송을 일시 중지합니다. */
        [[nodiscard]] bool suspendBlob() noexcept;

        /** @brief 일시 중지된 BLOB Client 전송을 재개합니다. */
        [[nodiscard]] bool resumeBlob() noexcept;

        /** @brief Client와 raw Server의 진행 중 BLOB 전송을 취소합니다. */
        void cancelBlob() noexcept;

        /** @brief BLOB Client의 현재 진행률을 percent로 반환합니다. */
        [[nodiscard]] std::uint8_t clientProgress() const noexcept;

        /** @brief raw BLOB Server의 현재 진행률을 percent로 반환합니다. */
        [[nodiscard]] std::uint8_t serverProgress() const noexcept;

        /** @brief BLOB 또는 Mesh DFU model이 전송 중인지 반환합니다. */
        [[nodiscard]] bool busy() const noexcept;

        /** @brief 다음 DFU image에 요구할 SHA-256 digest와 byte 길이를 고정합니다. */
        [[nodiscard]] bool expectImageDigest(const std::uint8_t digest[32],
                                             std::uint32_t image_size) noexcept;

        /** @brief inactive slot의 지정 범위를 SHA-256 digest로 검사합니다. */
        [[nodiscard]] bool verifyStagedDigest(const std::uint8_t digest[32],
                                              std::uint32_t image_size) noexcept;

        /** @brief verified image를 MCUboot test upgrade로 예약합니다. */
        [[nodiscard]] bool requestTestUpgrade() noexcept;

        /** @brief 새 image가 정상 동작한 뒤 MCUboot rollback을 해제합니다. */
        [[nodiscard]] bool confirmRunningImage() noexcept;

        /** @brief inactive slot의 signed image를 등록하고 target 배포를 시작합니다. */
        [[nodiscard]] bool startDistribution(const FirmwareDistribution &distribution) noexcept;

        /** @brief 진행 중인 Firmware Distribution과 target 목록을 취소합니다. */
        [[nodiscard]] bool cancelDistribution() noexcept;

        /** @brief 명시적으로 warm reboot하여 예약한 image 적용을 시작합니다. */
        void rebootToApply() noexcept;

        /** @brief 마지막 update 단계를 반환합니다. */
        [[nodiscard]] UpdatePhase phase() const noexcept;

        /** @brief Firmware Distributor의 현재 단계를 반환합니다. */
        [[nodiscard]] UpdatePhase distributionPhase() const noexcept;

        /** @brief 마지막 공개 오류를 반환합니다. */
        [[nodiscard]] UpdateError lastError() const noexcept;

        /** @brief 마지막 Zephyr 음수 오류를 반환합니다. */
        [[nodiscard]] int lastDriverError() const noexcept;
    };
} // namespace nucode::mesh

/** @brief NU54DK의 단일 Bluetooth Mesh update 객체입니다. */
extern nucode::mesh::MeshUpdate NUCODEMeshUpdate;

#endif
