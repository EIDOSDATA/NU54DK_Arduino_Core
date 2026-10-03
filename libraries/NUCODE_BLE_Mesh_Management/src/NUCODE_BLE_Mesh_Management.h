/**
 * @file NUCODE_BLE_Mesh_Management.h
 * @brief Bluetooth Mesh 1.1 관리·privacy·bridging 공개 API입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#ifndef NUCODE_BLE_MESH_MANAGEMENT_H
#define NUCODE_BLE_MESH_MANAGEMENT_H

#include <NUCODE_BLE_Mesh.h>

#include <cstddef>
#include <cstdint>

namespace nucode::mesh
{
    /** @brief 원격 관리 message의 목적지입니다. */
    struct ManagementTarget
    {
        std::uint16_t address = 0U;
        std::uint16_t net_key_index = 0U;
        std::uint16_t app_key_index = 0U;
        std::uint8_t ttl = 7U;
    };

    /** @brief Remote Provisioning에서 발견한 unprovisioned device입니다. */
    struct RemoteDevice
    {
        static constexpr std::size_t advertising_capacity = 31U;

        ManagementTarget server{};
        std::uint8_t uuid[16]{};
        std::int8_t rssi = 0;
        std::uint16_t oob_information = 0U;
        std::uint8_t advertising_data[advertising_capacity]{};
        std::uint8_t advertising_size = 0U;
        bool advertising_truncated = false;
    };

    /** @brief SAR Transmitter 상태의 공개 snapshot입니다. */
    struct SarTransmitter
    {
        std::uint8_t segment_interval_step = 0U;
        std::uint8_t unicast_retransmissions = 0U;
        std::uint8_t unicast_retransmissions_without_progress = 0U;
        std::uint8_t unicast_retransmission_interval_step = 0U;
        std::uint8_t unicast_retransmission_interval_increment = 0U;
        std::uint8_t multicast_retransmissions = 0U;
        std::uint8_t multicast_retransmission_interval = 0U;
    };

    /** @brief SAR Receiver 상태의 공개 snapshot입니다. */
    struct SarReceiver
    {
        std::uint8_t segments_threshold = 0U;
        std::uint8_t acknowledgement_delay_increment = 0U;
        std::uint8_t discard_timeout = 0U;
        std::uint8_t receiver_segment_interval_step = 0U;
        std::uint8_t acknowledgement_retransmissions = 0U;
    };

    /** @brief Large Composition Data 또는 Models Metadata의 유한 조각입니다. */
    struct LargeDataChunk
    {
        static constexpr std::size_t capacity = 64U;

        std::uint8_t page = 0U;
        std::uint16_t offset = 0U;
        std::uint16_t total_size = 0U;
        std::uint8_t data[capacity]{};
        std::uint8_t size = 0U;
        bool truncated = false;
    };

    /** @brief Subnet Bridging table의 한 항목입니다. */
    struct BridgeEntry
    {
        bool bidirectional = true;
        std::uint16_t first_net_key_index = 0U;
        std::uint16_t second_net_key_index = 0U;
        std::uint16_t first_address = 0U;
        std::uint16_t second_address = 0U;
    };

    /** @brief Mesh 1.1 관리 event 종류입니다. */
    enum class ManagementEvent : std::uint8_t
    {
        remote_device,
        operation_complete,
        operation_failed,
    };

    /** @brief Mesh 1.1 관리 오류입니다. */
    enum class ManagementError : std::uint8_t
    {
        none,
        not_started,
        invalid_argument,
        queue_full,
        driver_error,
    };

    /** @brief callback에 복사되는 고정 크기 event입니다. */
    struct ManagementEventRecord
    {
        ManagementEvent event = ManagementEvent::operation_complete;
        RemoteDevice remote{};
        ManagementError error = ManagementError::none;
        int driver_error = 0;
    };

    /** @brief Sketch main 문맥에서 호출되는 관리 event callback입니다. */
    using ManagementEventCallback = void (*)(const ManagementEventRecord &record,
                                              void *context);

    /**
     * @brief Bluetooth Mesh 1.1 관리 model을 bounded Arduino API로 제공합니다.
     *
     * blocking status API는 호출자가 지정한 timeout 안에서만 대기합니다. Remote
     * Provisioning scan report는 고정 queue에 복사되고 poll()에서 전달됩니다.
     */
    class MeshManagement final
    {
      public:
        /** @brief foundation model을 Opcode Aggregator에 넣는 remote Device Key index입니다. */
        static constexpr std::uint16_t remote_device_key_index = 0xFFFDU;

        /** @brief 관리 API를 시작하고 동기 model timeout을 고정합니다. */
        [[nodiscard]] bool begin(std::uint32_t timeout_ms = 5000U) noexcept;

        /** @brief queued event를 Sketch main 문맥으로 전달합니다. */
        void poll() noexcept;

        /** @brief 사용자 event callback을 등록합니다. */
        void onEvent(ManagementEventCallback callback, void *context = nullptr) noexcept;

        /** @brief 원격 서버에서 unprovisioned device scan을 시작합니다. */
        [[nodiscard]] bool startRemoteScan(const ManagementTarget &server,
                                           std::uint8_t timeout_seconds,
                                           std::uint8_t maximum_devices = 4U,
                                           const std::uint8_t *uuid = nullptr) noexcept;

        /** @brief 원격 서버의 진행 중 scan을 중지합니다. */
        [[nodiscard]] bool stopRemoteScan(const ManagementTarget &server) noexcept;

        /** @brief 원격 서버의 provisioning link를 닫습니다. */
        [[nodiscard]] bool closeRemoteLink(const ManagementTarget &server) noexcept;

        /** @brief 발견한 device를 PB-Remote로 provisioning합니다. */
        [[nodiscard]] bool provisionRemote(const ManagementTarget &server,
                                           const std::uint8_t uuid[16],
                                           std::uint16_t node_address = 0U) noexcept;

        /** @brief 원격 SAR Transmitter 설정을 읽습니다. */
        [[nodiscard]] bool getSarTransmitter(const ManagementTarget &target,
                                             SarTransmitter &state) noexcept;

        /** @brief 원격 SAR Transmitter 설정을 검증하고 변경합니다. */
        [[nodiscard]] bool setSarTransmitter(const ManagementTarget &target,
                                             const SarTransmitter &state) noexcept;

        /** @brief 원격 SAR Receiver 설정을 읽습니다. */
        [[nodiscard]] bool getSarReceiver(const ManagementTarget &target,
                                          SarReceiver &state) noexcept;

        /** @brief 원격 SAR Receiver 설정을 검증하고 변경합니다. */
        [[nodiscard]] bool setSarReceiver(const ManagementTarget &target,
                                          const SarReceiver &state) noexcept;

        /** @brief AppKey 또는 remote Device Key로 Opcode Aggregator sequence를 시작합니다. */
        [[nodiscard]] bool beginOpcodeSequence(const ManagementTarget &target,
                                               std::uint16_t app_key_index,
                                               std::uint16_t element_address) noexcept;

        /** @brief 진행 중 sequence의 남은 SDU 공간을 반환합니다. */
        [[nodiscard]] std::size_t opcodeSequenceTailroom() const noexcept;

        /** @brief 누적한 opcode sequence를 전송합니다. */
        [[nodiscard]] bool sendOpcodeSequence() noexcept;

        /** @brief 진행 중 opcode sequence를 폐기합니다. */
        void abortOpcodeSequence() noexcept;

        /** @brief Large Composition Data page 조각을 읽습니다. */
        [[nodiscard]] bool readLargeComposition(const ManagementTarget &target,
                                                std::uint8_t page,
                                                std::uint16_t offset,
                                                LargeDataChunk &chunk) noexcept;

        /** @brief Models Metadata page 조각을 읽습니다. */
        [[nodiscard]] bool readModelsMetadata(const ManagementTarget &target,
                                              std::uint8_t page,
                                              std::uint16_t offset,
                                              LargeDataChunk &chunk) noexcept;

        /** @brief Private Beacon과 random refresh interval을 설정합니다. */
        [[nodiscard]] bool setPrivateBeacon(const ManagementTarget &target, bool enabled,
                                            std::uint8_t random_interval_steps) noexcept;

        /** @brief Private GATT Proxy 상태를 설정합니다. */
        [[nodiscard]] bool setPrivateGattProxy(const ManagementTarget &target,
                                               bool enabled) noexcept;

        /** @brief 지정 subnet의 Private Node Identity 상태를 설정합니다. */
        [[nodiscard]] bool setPrivateNodeIdentity(const ManagementTarget &target,
                                                  std::uint16_t identity_net_key_index,
                                                  bool enabled) noexcept;

        /** @brief On-Demand Private Proxy의 광고 수명을 설정합니다. */
        [[nodiscard]] bool setOnDemandPrivateProxy(const ManagementTarget &target,
                                                   std::uint8_t lifetime) noexcept;

        /** @brief local node에서 Solicitation PDU 광고를 예약합니다. */
        [[nodiscard]] bool solicit(std::uint16_t net_key_index = 0U) noexcept;

        /** @brief 원격 solicitation replay protection list 범위를 지웁니다. */
        [[nodiscard]] bool clearSolicitationReplay(const ManagementTarget &target,
                                                   std::uint16_t range_start,
                                                   std::uint8_t range_length,
                                                   bool acknowledged = true) noexcept;

        /** @brief 원격 Subnet Bridge 기능을 설정합니다. */
        [[nodiscard]] bool setSubnetBridge(const ManagementTarget &target,
                                           bool enabled) noexcept;

        /** @brief 원격 Bridging table에 허용 항목을 추가합니다. */
        [[nodiscard]] bool addBridgeEntry(const ManagementTarget &target,
                                          const BridgeEntry &entry) noexcept;

        /** @brief 원격 Bridging table에서 항목을 제거합니다. */
        [[nodiscard]] bool removeBridgeEntry(const ManagementTarget &target,
                                             const BridgeEntry &entry) noexcept;

        /** @brief 누적 queue overflow 수를 반환합니다. */
        [[nodiscard]] std::uint32_t droppedEvents() const noexcept;

        /** @brief 마지막 공개 오류를 반환합니다. */
        [[nodiscard]] ManagementError lastError() const noexcept;

        /** @brief 마지막 Zephyr 음수 오류를 반환합니다. */
        [[nodiscard]] int lastDriverError() const noexcept;
    };
}

/** @brief NU54DK의 단일 Bluetooth Mesh 1.1 관리 객체입니다. */
extern nucode::mesh::MeshManagement NUCODEMeshManagement;

#endif
