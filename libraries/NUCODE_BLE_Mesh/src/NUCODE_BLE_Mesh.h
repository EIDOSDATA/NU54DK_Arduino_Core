/**
 * @file NUCODE_BLE_Mesh.h
 * @brief Bluetooth Mesh provisioning, foundation 역할과 표준 model 전송 API입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#ifndef NUCODE_BLE_MESH_H_
#define NUCODE_BLE_MESH_H_

#include <Arduino.h>

#include <cstddef>
#include <cstdint>

namespace nucode::mesh
{

    /** @brief Mesh 장치의 주 역할입니다. */
    enum class Role : std::uint8_t
    {
        node,
        provisioner,
    };

    /** @brief 지원하는 provisioning bearer입니다. */
    enum class Bearer : std::uint8_t
    {
        advertising = 0x01U,
        gatt = 0x02U,
        all = 0x03U,
    };

    /** @brief runtime에서 켜거나 끌 수 있는 Mesh feature입니다. */
    enum class Feature : std::uint8_t
    {
        relay,
        friend_node,
        low_power_node,
        gatt_proxy,
    };

    /** @brief 공개 API가 구분하는 표준 client model입니다. */
    enum class Model : std::uint8_t
    {
        generic_on_off,
        generic_level,
        light_lightness,
        sensor,
        time,
        scene,
        scheduler,
        generic_on_off_server,
        blob_client,
        blob_server,
        mesh_dfu_target,
        firmware_distributor,
        solicitation_rpl_configuration,
    };

    /** @brief Key Refresh 절차에서 요청할 전환 단계입니다. */
    enum class KeyRefreshTransition : std::uint8_t
    {
        use_new_keys = 2U,
        revoke_old_keys = 3U,
    };

    /** @brief Mesh lifecycle과 수신 상태 event입니다. */
    enum class Event : std::uint8_t
    {
        initialized,
        unprovisioned_device,
        provisioning_link_opened,
        provisioning_link_closed,
        provisioned,
        node_added,
        reset,
        model_status,
        error,
    };

    /** @brief 마지막 Mesh 동작의 공개 오류 분류입니다. */
    enum class Error : std::uint8_t
    {
        none,
        invalid_argument,
        invalid_context,
        already_started,
        not_started,
        not_provisioned,
        unsupported,
        busy,
        event_overflow,
        driver_error,
    };

    /** @brief begin()에 전달하는 고정 수명 구성입니다. */
    struct Configuration
    {
        Role role = Role::node;
        Bearer bearers = Bearer::all;
        std::uint8_t uuid[16]{};
        std::uint16_t local_address = 0x0001U;
        std::uint8_t default_ttl = 7U;
    };

    /** @brief 표준 model 송신 대상과 key·transport 정책입니다. */
    struct Destination
    {
        std::uint16_t address = 0xC000U;
        std::uint16_t net_key_index = 0U;
        std::uint16_t app_key_index = 0U;
        std::uint8_t ttl = 7U;
        bool force_segment_acknowledgment = false;
    };

    /** @brief 원격 SIG model에 적용할 publication 정책입니다. */
    struct Publication
    {
        std::uint16_t address = 0xC000U;
        std::uint16_t app_key_index = 0U;
        std::uint8_t ttl = 7U;
        std::uint32_t period_ms = 0U;
        std::uint16_t retransmit_interval_ms = 50U;
        std::uint8_t retransmit_count = 2U;
        bool friendship_credentials = false;
    };

    /** @brief poll()에서 전달하는 bounded event snapshot입니다. */
    struct EventRecord
    {
        static constexpr std::size_t payload_capacity = 32U;

        Event event = Event::initialized;
        Model model = Model::generic_on_off;
        Bearer bearer = Bearer::advertising;
        std::uint16_t address = 0U;
        std::uint16_t net_key_index = 0U;
        std::uint8_t element_count = 0U;
        std::uint8_t uuid[16]{};
        std::uint8_t payload[payload_capacity]{};
        std::uint8_t payload_size = 0U;
        bool payload_truncated = false;
        Error error = Error::none;
        int driver_error = 0;
    };

    /** @brief Health Fault Status의 고정 크기 snapshot입니다. */
    struct HealthFaults
    {
        static constexpr std::size_t capacity = 16U;

        std::uint16_t company_id = 0U;
        std::uint8_t test_id = 0U;
        std::uint8_t faults[capacity]{};
        std::uint8_t fault_count = 0U;
        bool truncated = false;
    };

    /** @brief Sketch main 문맥에서 호출되는 Mesh event callback입니다. */
    using EventCallback = void (*)(const EventRecord &record, void *context);

    /**
     * @brief Bluetooth Mesh의 고정 composition과 provisioning lifecycle을 제공합니다.
     *
     * callback과 수신 model 상태는 고정 queue로 복사되며 poll()에서만 사용자
     * callback을 호출합니다. 객체는 단일 전역 instance로 사용합니다.
     */
    class MeshDevice final
    {
      public:
        MeshDevice() = default;
        MeshDevice(const MeshDevice &) = delete;
        MeshDevice &operator=(const MeshDevice &) = delete;

        /** @brief Bluetooth Mesh를 초기화하고 저장 설정을 복원합니다. */
        [[nodiscard]] bool begin(const Configuration &configuration) noexcept;

        /** @brief queued event를 Sketch main 문맥으로 전달합니다. */
        void poll() noexcept;

        /** @brief 사용자 event callback을 등록합니다. */
        void onEvent(EventCallback callback, void *context = nullptr) noexcept;

        /** @brief 아직 provisioning되지 않은 node의 PB-ADV/PB-GATT를 활성화합니다. */
        [[nodiscard]] bool enableProvisioning(Bearer bearers = Bearer::all) noexcept;

        /** @brief 새 provisioning 시도를 막고 discovery bearer를 중지합니다. */
        [[nodiscard]] bool cancelProvisioning() noexcept;

        /** @brief 발견한 UUID를 PB-ADV 또는 PB-GATT로 provisioning합니다. */
        [[nodiscard]] bool provision(const std::uint8_t uuid[16], Bearer bearer,
                                     std::uint16_t address = 0U) noexcept;

        /** @brief local provisioning과 저장된 Mesh 상태를 지우고 재시작 가능하게 만듭니다. */
        [[nodiscard]] bool reset() noexcept;

        /** @brief local node가 provisioning 완료 상태인지 반환합니다. */
        [[nodiscard]] bool provisioned() const noexcept;

        /** @brief Relay, Friend, LPN 또는 GATT Proxy runtime 상태를 바꿉니다. */
        [[nodiscard]] bool setFeature(Feature feature, bool enabled) noexcept;

        /** @brief LPN이 Friend Poll을 즉시 전송하도록 요청합니다. */
        [[nodiscard]] bool pollFriend() noexcept;

        /** @brief local provisioner 또는 원격 node에 application key를 추가합니다. */
        [[nodiscard]] bool configureAppKey(std::uint16_t node_address,
                                           const std::uint8_t app_key[16],
                                           std::uint16_t app_key_index = 0U,
                                           std::uint16_t net_key_index = 0U) noexcept;

        /** @brief local/remote subnet과 application key를 Key Refresh phase 1로 갱신합니다. */
        [[nodiscard]] bool updateKeys(std::uint16_t node_address,
                                      const std::uint8_t net_key[16],
                                      const std::uint8_t app_key[16],
                                      std::uint16_t app_key_index = 0U,
                                      std::uint16_t net_key_index = 0U) noexcept;

        /** @brief remote node와 local provisioner의 Key Refresh phase를 순서대로 전환합니다. */
        [[nodiscard]] bool transitionKeyRefresh(std::uint16_t node_address,
                                                KeyRefreshTransition transition,
                                                std::uint16_t net_key_index = 0U) noexcept;

        /**
         * @brief local provisioner 또는 원격 element의 SIG model에 application key를 bind합니다.
         *
         * local model binding은 현재 begin lifecycle에 적용되므로 재시작 뒤 다시 호출해야 합니다.
         */
        [[nodiscard]] bool bindModel(std::uint16_t node_address,
                                     std::uint16_t element_address, Model model,
                                     std::uint16_t app_key_index = 0U,
                                     std::uint16_t net_key_index = 0U) noexcept;

        /** @brief 원격 element의 SIG model에 group subscription을 추가합니다. */
        [[nodiscard]] bool subscribeModel(std::uint16_t node_address,
                                          std::uint16_t element_address, Model model,
                                          std::uint16_t group_address,
                                          std::uint16_t net_key_index = 0U) noexcept;

        /** @brief 원격 element의 SIG model publication 주소·주기·재전송을 설정합니다. */
        [[nodiscard]] bool configurePublication(std::uint16_t node_address,
                                                std::uint16_t element_address,
                                                Model model,
                                                const Publication &publication,
                                                std::uint16_t net_key_index = 0U) noexcept;

        /** @brief 원격 Health Server의 현재 fault를 동기 조회합니다. */
        [[nodiscard]] bool readHealthFaults(const Destination &destination,
                                            std::uint16_t company_id,
                                            HealthFaults &faults) noexcept;

        /** @brief Generic OnOff Set 또는 Set Unacknowledged를 전송합니다. */
        [[nodiscard]] bool sendOnOff(const Destination &destination, bool enabled,
                                     bool acknowledged = true) noexcept;

        /**
         * @brief 지정 transaction ID로 Generic OnOff 요청을 전송합니다.
         *
         * @details acknowledged 응답을 받지 못한 application이 같은 transaction을
         * bounded 재전송할 때 사용합니다. 새 요청에는 기본 sendOnOff를 사용합니다.
         */
        [[nodiscard]] bool sendOnOff(const Destination &destination, bool enabled,
                                     bool acknowledged,
                                     std::uint8_t transaction_id) noexcept;

        /** @brief local Generic OnOff Server 상태를 바꾸고 선택적으로 publish합니다. */
        [[nodiscard]] bool setLocalOnOff(bool enabled, bool publish = true) noexcept;

        /** @brief local Generic OnOff Server의 현재 상태를 반환합니다. */
        [[nodiscard]] bool localOnOff() const noexcept;

        /** @brief Generic Level Set 또는 Set Unacknowledged를 전송합니다. */
        [[nodiscard]] bool sendLevel(const Destination &destination, std::int16_t level,
                                     bool acknowledged = true) noexcept;

        /** @brief Light Lightness Set 또는 Set Unacknowledged를 전송합니다. */
        [[nodiscard]] bool sendLightness(const Destination &destination,
                                         std::uint16_t lightness,
                                         bool acknowledged = true) noexcept;

        /** @brief Sensor Get을 전송합니다. property 0은 전체 sensor 조회입니다. */
        [[nodiscard]] bool requestSensor(const Destination &destination,
                                         std::uint16_t property = 0U) noexcept;

        /** @brief Time Get을 전송합니다. */
        [[nodiscard]] bool requestTime(const Destination &destination) noexcept;

        /** @brief Scene Recall 또는 Recall Unacknowledged를 전송합니다. */
        [[nodiscard]] bool recallScene(const Destination &destination, std::uint16_t scene,
                                       bool acknowledged = true) noexcept;

        /** @brief Scheduler Get을 전송합니다. */
        [[nodiscard]] bool requestSchedule(const Destination &destination) noexcept;

        /** @brief 누적 queue overflow 수를 반환합니다. */
        [[nodiscard]] std::uint32_t droppedEvents() const noexcept;

        /** @brief 마지막 공개 오류를 반환합니다. */
        [[nodiscard]] Error lastError() const noexcept;

        /** @brief 마지막 Zephyr 음수 오류를 반환합니다. */
        [[nodiscard]] int lastDriverError() const noexcept;

        /** @brief 마지막 원격 Configuration Status 값을 반환합니다. */
        [[nodiscard]] std::uint8_t lastConfigurationStatus() const noexcept;
    };

} // namespace nucode::mesh

/** @brief NU54DK의 단일 Bluetooth Mesh 객체입니다. */
extern nucode::mesh::MeshDevice NUCODEMesh;

#endif
