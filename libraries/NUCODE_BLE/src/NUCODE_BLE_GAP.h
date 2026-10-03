/**
 * @file NUCODE_BLE_GAP.h
 * @brief NU54DK의 고정 자원 BLE Core/GAP Arduino API를 선언합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#ifndef NUCODE_BLE_GAP_H_
#define NUCODE_BLE_GAP_H_

#include <cstddef>
#include <cstdint>

namespace nucode::ble
{

    class BLEService;

    namespace internal
    {
        struct BLEConnectionHandleAccess;
    }

    /** @brief BLE Core/GAP와 범용 GATT가 공유하는 공개 오류 분류입니다. */
    enum class BLEError : std::uint8_t
    {
        none,
        invalid_argument,
        invalid_context,
        not_initialized,
        already_started,
        wrong_state,
        busy,
        payload_overflow,
        event_overflow,
        scan_result_overflow,
        unsupported,
        not_connected,
        timeout,
        schema_full,
        duplicate,
        not_found,
        value_overflow,
        driver_error,
    };

    /** @brief BLE Core/GAP 상태 변화를 나타내는 main-thread event입니다. */
    enum class BLEEvent : std::uint8_t
    {
        initialized,
        advertising_started,
        advertising_stopped,
        scan_started,
        scan_stopped,
        scan_result,
        connecting,
        connected,
        disconnected,
        mtu_changed,
        phy_changed,
        parameters_changed,
        extended_advertising_created,
        extended_advertising_started,
        extended_advertising_stopped,
        extended_advertising_deleted,
        periodic_advertising_started,
        periodic_advertising_stopped,
        periodic_sync_created,
        periodic_sync_synchronized,
        periodic_sync_terminated,
        periodic_sync_deleted,
        periodic_report,
        past_subscribed,
        past_unsubscribed,
        past_transferred,
        pawr_data_requested,
        pawr_response_received,
        identity_resolved,
        data_length_changed,
        remote_information_available,
        transmit_power_report,
        path_loss_changed,
        subrate_changed,
        connection_rate_changed,
        remote_features_available,
        frame_space_changed,
        rpa_expired,
        error,
        connection_recycled,
    };

    /** @brief BLEDevice.poll() 문맥에서만 호출되는 Core/GAP callback입니다. */
    using BLEEventCallback = void (*)(BLEEvent event, void *context);

    /** @brief local 장치가 BLE link에서 맡는 역할입니다. */
    enum class BLELinkRole : std::uint8_t
    {
        none,
        central,
        peripheral,
    };

    /** @brief LE Power Control이 구분하는 송신 PHY입니다. */
    enum class BLETransmitPowerPhy : std::uint8_t
    {
        none,
        le_1m,
        le_2m,
        coded_s8,
        coded_s2,
        unknown = 0xffU,
    };

    /** @brief 송신 전력 보고를 발생시킨 표준 절차입니다. */
    enum class BLETransmitPowerReportReason : std::uint8_t
    {
        local_changed,
        remote_changed,
        remote_read_completed,
        unknown = 0xffU,
    };

    /** @brief Path Loss Monitoring이 보고하는 현재 구간입니다. */
    enum class BLEPathLossZone : std::uint8_t
    {
        low,
        middle,
        high,
        unavailable,
        unknown = 0xffU,
    };

    /** @brief callback 밖에서도 유지되는 LE 송신 전력 보고 복사본입니다. */
    struct BLETransmitPowerReport
    {
        BLETransmitPowerReportReason reason = BLETransmitPowerReportReason::unknown;
        BLETransmitPowerPhy phy = BLETransmitPowerPhy::unknown;
        std::int8_t level_dbm = 127;
        std::int8_t delta_db = 127;
        bool at_minimum = false;
        bool at_maximum = false;
    };

    /** @brief callback 밖에서도 유지되는 Path Loss 구간 보고 복사본입니다. */
    struct BLEPathLossReport
    {
        BLEPathLossZone zone = BLEPathLossZone::unknown;
        std::uint8_t path_loss_db = 0xffU;
    };

    /** @brief Connection Subrating 요청과 기본값에 공통으로 사용하는 표준 단위입니다. */
    struct BLESubrateParameters
    {
        std::uint16_t minimum_factor = 1U;
        std::uint16_t maximum_factor = 10U;
        std::uint16_t maximum_peripheral_latency = 0U;
        std::uint16_t continuation_number = 0U;
        std::uint16_t supervision_timeout_10ms = 400U;
    };

    /** @brief controller가 보고한 link별 Connection Subrating 결과입니다. */
    struct BLESubrateInfo
    {
        std::uint8_t status = 0xffU;
        std::uint16_t factor = 1U;
        std::uint16_t continuation_number = 0U;
        std::uint16_t peripheral_latency = 0U;
        std::uint16_t supervision_timeout_10ms = 0U;
    };

    /** @brief 125 us 단위의 표준 Shorter Connection Interval 요청입니다. */
    struct BLEConnectionRateParameters
    {
        std::uint16_t interval_minimum_125us = 6U;
        std::uint16_t interval_maximum_125us = 80U;
        std::uint16_t subrate_minimum = 1U;
        std::uint16_t subrate_maximum = 1U;
        std::uint16_t maximum_peripheral_latency = 0U;
        std::uint16_t continuation_number = 0U;
        std::uint16_t supervision_timeout_10ms = 400U;
        std::uint16_t event_length_minimum_125us = 1U;
        std::uint16_t event_length_maximum_125us = 0x3e7fU;
    };

    /** @brief controller가 보고한 실제 connection rate 결과입니다. */
    struct BLEConnectionRateInfo
    {
        std::uint8_t status = 0xffU;
        std::uint32_t interval_us = 0U;
        std::uint16_t subrate_factor = 1U;
        std::uint16_t peripheral_latency = 0U;
        std::uint16_t continuation_number = 0U;
        std::uint16_t supervision_timeout_10ms = 0U;
    };

    /** @brief Frame Space Update의 PHY·spacing 종류와 허용 범위입니다. */
    struct BLEFrameSpaceParameters
    {
        static constexpr std::uint8_t phy_le_1m = 0x01U;
        static constexpr std::uint8_t phy_le_2m = 0x02U;
        static constexpr std::uint8_t phy_coded = 0x04U;
        static constexpr std::uint16_t spacing_acl_central_to_peripheral = 0x0001U;
        static constexpr std::uint16_t spacing_acl_peripheral_to_central = 0x0002U;
        static constexpr std::uint16_t spacing_acl_mces = 0x0004U;

        std::uint8_t phy_mask = phy_le_2m;
        std::uint16_t spacing_type_mask =
            spacing_acl_central_to_peripheral | spacing_acl_peripheral_to_central;
        std::uint16_t minimum_us = 0U;
        std::uint16_t maximum_us = 150U;
    };

    /** @brief controller가 보고한 실제 Frame Space Update 결과입니다. */
    struct BLEFrameSpaceInfo
    {
        std::uint8_t status = 0xffU;
        std::uint8_t initiator = 0xffU;
        std::uint16_t frame_space_us = 0U;
        std::uint8_t phy_mask = 0U;
        std::uint16_t spacing_type_mask = 0U;
    };

    /** @brief Bluetooth 6.x 확장 LE feature page의 고정 크기 복사본입니다. */
    struct BLEExtendedFeatureSet
    {
        static constexpr std::size_t maximum_size = 248U;
        static constexpr std::uint8_t maximum_page = 10U;

        std::uint8_t status = 0xffU;
        std::uint8_t maximum_remote_page = 0U;
        std::uint8_t maximum_valid_page = 0U;
        std::uint8_t features[maximum_size] = {};

        /** @brief page와 page 내부 bit 번호의 지원 여부를 반환합니다. */
        [[nodiscard]] bool supported(std::uint8_t page,
                                     std::uint16_t bit) const noexcept
        {
            const std::size_t page_size = page == 0U ? 8U : 24U;
            if (page > maximum_valid_page || page > maximum_page ||
                bit >= page_size * 8U)
            {
                return false;
            }
            const std::size_t offset = page == 0U ? 0U : 8U + (page - 1U) * 24U;
            return (features[offset + bit / 8U] & (1U << (bit % 8U))) != 0U;
        }
    };

    /** @brief 고정 Host/controller의 Sleep Clock Accuracy 지원 경계입니다. */
    struct BLESleepClockAccuracySupport
    {
        bool controller_procedure = false;
        bool host_request_and_report = false;
    };

    /** @brief slot 재사용을 generation으로 구분하는 불투명 BLE link handle입니다. */
    class BLEConnectionHandle final
    {
      public:
        BLEConnectionHandle() = default;

        /** @brief 현재 API 호출에 사용할 수 있는 형식의 handle인지 반환합니다. */
        [[nodiscard]] constexpr bool valid() const noexcept
        {
            return token_ != 0U;
        }

        [[nodiscard]] constexpr bool operator==(const BLEConnectionHandle &other) const noexcept
        {
            return token_ == other.token_;
        }

        [[nodiscard]] constexpr bool operator!=(const BLEConnectionHandle &other) const noexcept
        {
            return !(*this == other);
        }

      private:
        explicit constexpr BLEConnectionHandle(std::uint64_t token) noexcept : token_(token)
        {
        }

        std::uint64_t token_ = 0U;
        friend struct internal::BLEConnectionHandleAccess;
    };

    /** @brief advertising set 재생성을 generation으로 구분하는 불투명 handle입니다. */
    class BLEAdvertisingSetHandle final
    {
      public:
        BLEAdvertisingSetHandle() = default;

        /** @brief 현재 API 호출에 사용할 수 있는 형식의 handle인지 반환합니다. */
        [[nodiscard]] constexpr bool valid() const noexcept
        {
            return token_ != 0U;
        }

        [[nodiscard]] constexpr bool operator==(const BLEAdvertisingSetHandle &other) const noexcept
        {
            return token_ == other.token_;
        }

        [[nodiscard]] constexpr bool operator!=(const BLEAdvertisingSetHandle &other) const noexcept
        {
            return !(*this == other);
        }

      private:
        explicit constexpr BLEAdvertisingSetHandle(std::uint32_t token) noexcept : token_(token)
        {
        }

        std::uint32_t token_ = 0U;
        friend struct internal::BLEConnectionHandleAccess;
    };

    /** @brief periodic sync 재생성을 generation으로 구분하는 불투명 handle입니다. */
    class BLEPeriodicSyncHandle final
    {
      public:
        BLEPeriodicSyncHandle() = default;

        /** @brief 현재 API 호출에 사용할 수 있는 형식의 handle인지 반환합니다. */
        [[nodiscard]] constexpr bool valid() const noexcept
        {
            return token_ != 0U;
        }

        [[nodiscard]] constexpr bool operator==(const BLEPeriodicSyncHandle &other) const noexcept
        {
            return token_ == other.token_;
        }

        [[nodiscard]] constexpr bool operator!=(const BLEPeriodicSyncHandle &other) const noexcept
        {
            return !(*this == other);
        }

      private:
        explicit constexpr BLEPeriodicSyncHandle(std::uint32_t token) noexcept : token_(token)
        {
        }

        std::uint32_t token_ = 0U;
        friend struct internal::BLEConnectionHandleAccess;
    };

    /** @brief Nordic QoS connection-event 보고의 callback 밖 수명 복사본입니다. */
    struct BLENordicConnectionEventReport
    {
        BLEConnectionHandle connection;
        std::uint16_t event_counter = 0U;
        std::uint8_t channel_index = 0xffU;
        std::uint16_t crc_ok_count = 0U;
        std::uint16_t crc_error_count = 0U;
        std::uint16_t negative_acknowledgement_count = 0U;
        bool receive_timeout = false;
    };

    /** @brief Nordic QoS channel survey가 보고한 40개 LE channel energy입니다. */
    struct BLENordicChannelSurveyReport
    {
        static constexpr std::size_t channel_count = 40U;
        static constexpr std::int8_t unavailable = 127;

        std::int8_t channel_energy_dbm[channel_count] = {};
    };

    /** @brief controller clock 도메인의 connection anchor point 복사본입니다. */
    struct BLENordicAnchorPointReport
    {
        BLEConnectionHandle connection;
        std::uint16_t event_counter = 0U;
        std::uint64_t controller_clock_us = 0U;
    };

    /** @brief 고정 SDK LE Flushable ACL Data의 controller·Host 적용 경계입니다. */
    struct BLEFlushableAclSupport
    {
        bool controller_experimental = false;
        bool host_transmit_path = false;
        bool usable = false;
    };

    /** @brief BLEDevice.poll() 문맥의 Nordic connection-event QoS callback입니다. */
    using BLENordicConnectionEventCallback =
        void (*)(const BLENordicConnectionEventReport &report, void *context);

    /** @brief BLEDevice.poll() 문맥의 Nordic channel-survey callback입니다. */
    using BLENordicChannelSurveyCallback =
        void (*)(const BLENordicChannelSurveyReport &report, void *context);

    /** @brief BLEDevice.poll() 문맥의 Nordic anchor-point callback입니다. */
    using BLENordicAnchorPointCallback =
        void (*)(const BLENordicAnchorPointReport &report, void *context);

    /** @brief system workqueue 문맥에서 제한된 작업만 수행하는 radio prepare callback입니다. */
    using BLENordicRadioPrepareCallback =
        void (*)(BLEConnectionHandle connection, void *context);

    /** @brief 기존 event에 link handle과 local 역할을 결합한 상세 event입니다. */
    struct BLEEventInfo
    {
        BLEEvent event = BLEEvent::error;
        BLEConnectionHandle connection;
        BLEAdvertisingSetHandle advertising_set;
        BLEPeriodicSyncHandle periodic_sync;
        BLELinkRole role = BLELinkRole::none;
        /** @brief disconnected event의 HCI reason이며 다른 event에서는 0입니다. */
        std::uint8_t reason = 0U;
        /** @brief transmit_power_report event의 값 복사본입니다. */
        BLETransmitPowerReport transmit_power;
        /** @brief path_loss_changed event의 값 복사본입니다. */
        BLEPathLossReport path_loss;
    };

    /** @brief BLEDevice.poll() 문맥에서만 호출되는 link 식별 가능 callback입니다. */
    using BLEEventInfoCallback = void (*)(const BLEEventInfo &information, void *context);

    /** @brief 지원하는 공개 UUID 저장 형식입니다. */
    class BLEUuid final
    {
      public:
        /** @brief UUID의 실제 폭입니다. */
        enum class Type : std::uint8_t
        {
            invalid = 0,
            uuid16 = 2,
            uuid32 = 4,
            uuid128 = 16,
        };

        BLEUuid() = default;

        /** @brief 16-bit Bluetooth UUID를 만듭니다. */
        explicit BLEUuid(std::uint16_t value) noexcept;

        /** @brief canonical 128-bit UUID 문자열을 해석합니다. */
        explicit BLEUuid(const char *canonical) noexcept;

        /** @brief 32-bit Bluetooth UUID를 명시적으로 만듭니다. */
        [[nodiscard]] static BLEUuid from32(std::uint32_t value) noexcept;

        /** @brief UUID가 지원하는 올바른 형식인지 반환합니다. */
        [[nodiscard]] bool valid() const noexcept;

        /** @brief UUID 폭을 반환합니다. */
        [[nodiscard]] Type type() const noexcept;

        /** @brief Bluetooth little-endian byte 수를 반환합니다. */
        [[nodiscard]] std::size_t size() const noexcept;

        /** @brief 객체 수명 동안 유효한 Bluetooth little-endian byte를 반환합니다. */
        [[nodiscard]] const std::uint8_t *data() const noexcept;

        /** @brief UUID를 0 종료 문자열로 기록하고 성공 여부를 반환합니다. */
        [[nodiscard]] bool format(char *output, std::size_t capacity) const noexcept;

        [[nodiscard]] bool operator==(const BLEUuid &other) const noexcept;
        [[nodiscard]] bool operator!=(const BLEUuid &other) const noexcept;

      private:
        Type type_ = Type::invalid;
        std::uint8_t bytes_[16] = {};
    };

    /** @brief Bluetooth LE 주소의 공개 형식입니다. */
    class BLEAddress final
    {
      public:
        /** @brief public 또는 random 주소 종류입니다. */
        enum class Type : std::uint8_t
        {
            public_address = 0,
            random_address = 1,
            invalid = 0xff,
        };

        BLEAddress() = default;

        /** @brief AA:BB:CC:DD:EE:FF 문자열과 주소 종류를 해석합니다. */
        explicit BLEAddress(const char *text, Type type = Type::public_address) noexcept;

        /** @brief raw Bluetooth little-endian 주소로 객체를 만듭니다. */
        BLEAddress(const std::uint8_t bytes[6], Type type) noexcept;

        /** @brief 주소가 올바르게 설정되었는지 반환합니다. */
        [[nodiscard]] bool valid() const noexcept;

        /** @brief 주소 종류를 반환합니다. */
        [[nodiscard]] Type type() const noexcept;

        /** @brief 객체 수명 동안 유효한 little-endian 주소 byte를 반환합니다. */
        [[nodiscard]] const std::uint8_t *data() const noexcept;

        /** @brief AA:BB:CC:DD:EE:FF 문자열을 기록합니다. */
        [[nodiscard]] bool format(char *output, std::size_t capacity) const noexcept;

        [[nodiscard]] bool operator==(const BLEAddress &other) const noexcept;
        [[nodiscard]] bool operator!=(const BLEAddress &other) const noexcept;

      private:
        Type type_ = Type::invalid;
        std::uint8_t bytes_[6] = {};
    };

    /** @brief 현재 LE PHY를 portable enum으로 노출합니다. */
    enum class BLEPhy : std::uint8_t
    {
        unknown,
        le_1m,
        le_2m,
        coded,
    };

    /** @brief callback 밖에서도 값 복사본이 유지되는 bounded scan 결과입니다. */
    struct BLEScanResult
    {
        static constexpr std::size_t maximum_name_length = 32U;
        static constexpr std::size_t maximum_payload_length = 255U;

        BLEAddress address;
        std::int8_t rssi = 0;
        bool connectable = false;
        bool scan_response = false;
        bool extended = false;
        bool truncated = false;
        std::uint8_t sid = 0xffU;
        std::int8_t tx_power = 127;
        std::uint16_t periodic_interval = 0U;
        BLEPhy primary_phy = BLEPhy::unknown;
        BLEPhy secondary_phy = BLEPhy::unknown;
        char name[maximum_name_length + 1U] = {};
        std::uint8_t payload[maximum_payload_length] = {};
        std::uint16_t payload_length = 0U;
    };

    /** @brief BLEDevice.poll() 문맥에서만 호출되는 scan 결과 callback입니다. */
    using BLEScanCallback = void (*)(const BLEScanResult &result, void *context);

    /** @brief callback 밖에서도 값 복사본이 유지되는 bounded periodic report입니다. */
    struct BLEPeriodicReport
    {
        static constexpr std::size_t maximum_payload_length = 255U;

        BLEPeriodicSyncHandle sync;
        BLEAddress address;
        std::uint8_t sid = 0xffU;
        std::int8_t tx_power = 127;
        std::int8_t rssi = 0;
        std::uint16_t periodic_event_counter = 0U;
        std::uint8_t subevent = 0U;
        bool truncated = false;
        std::uint8_t payload[maximum_payload_length] = {};
        std::uint16_t payload_length = 0U;
    };

    /** @brief BLEDevice.poll() 문맥에서만 호출되는 periodic report callback입니다. */
    using BLEPeriodicReportCallback = void (*)(const BLEPeriodicReport &report, void *context);

    /** @brief Bluetooth stack과 Arduino main-thread event 경계를 소유합니다. */
    class Device final
    {
      public:
        /** @brief stack을 한 번 초기화하고 local name을 적용합니다. */
        [[nodiscard]] bool begin(const char *local_name) noexcept;

        /** @brief queued GAP/GATT event를 Arduino main thread에서 전달합니다. */
        void poll() noexcept;

        /**
         * @brief library 소유 광고·검색·연결을 끝냅니다.
         *
         * controller stack은 image에서 한 번만 초기화되며 end()로 disable하지 않습니다.
         */
        void end() noexcept;

        /** @brief begin()이 성공했는지 반환합니다. */
        [[nodiscard]] bool initialized() const noexcept;

        /** @brief 현재 local name의 caller buffer 복사본을 반환합니다. */
        [[nodiscard]] const char *localName() const noexcept;

        /** @brief main-thread Core/GAP event callback을 등록합니다. */
        void onEvent(BLEEventCallback callback, void *context = nullptr) noexcept;

        /** @brief link handle을 포함하는 main-thread 상세 event callback을 등록합니다. */
        void onEventInfo(BLEEventInfoCallback callback, void *context = nullptr) noexcept;

        /** @brief Bluetooth 시작 전에 GATT service schema를 추가합니다. */
        [[nodiscard]] bool addService(BLEService &service) noexcept;

        /** @brief 마지막 공개 오류를 반환합니다. */
        [[nodiscard]] BLEError lastError() const noexcept;

        /** @brief 마지막 Zephyr/NCS 오류를 반환합니다. */
        [[nodiscard]] int lastDriverError() const noexcept;

        /** @brief 가득 찬 event queue가 버린 누적 event 수를 반환합니다. */
        [[nodiscard]] std::uint32_t droppedEvents() const noexcept;

        /** @brief central 1개와 peripheral 1개의 동시 peer 상한을 반환합니다. */
        [[nodiscard]] static constexpr std::size_t maximumConnections() noexcept
        {
            return 2U;
        }
    };

    /** @brief 31-byte legacy advertising payload를 고정 자원으로 구성합니다. */
    class Advertising final
    {
      public:
        static constexpr std::size_t maximum_payload_length = 31U;

        /** @brief 중지 상태에서 payload 구성을 기본값으로 초기화합니다. */
        [[nodiscard]] bool clear() noexcept;

        /** @brief connectable 또는 non-connectable 모드를 선택합니다. */
        [[nodiscard]] bool setConnectable(bool connectable) noexcept;

        /** @brief AD flags byte를 설정합니다. */
        [[nodiscard]] bool setFlags(std::uint8_t flags) noexcept;

        /** @brief 0.625 ms 단위 광고 최소·최대 interval을 설정합니다. */
        [[nodiscard]] bool setInterval(std::uint16_t minimum, std::uint16_t maximum) noexcept;

        /** @brief 16/32/128-bit service UUID를 광고 payload에 추가합니다. */
        [[nodiscard]] bool addServiceUuid(const BLEUuid &uuid) noexcept;

        /** @brief company ID와 bounded manufacturer payload를 설정합니다. */
        [[nodiscard]] bool setManufacturerData(std::uint16_t company_id, const void *data,
                                               std::size_t length) noexcept;

        /** @brief UUID와 bounded service data를 설정합니다. */
        [[nodiscard]] bool setServiceData(const BLEUuid &uuid, const void *data,
                                          std::size_t length) noexcept;

        /** @brief 6-byte Coordinated Set RSI를 표준 AD field로 설정합니다. */
        [[nodiscard]] bool setResolvableSetIdentifier(const std::uint8_t (&rsi)[6]) noexcept;

        /** @brief local name을 scan response에 포함할지 선택합니다. */
        [[nodiscard]] bool setScanResponseName(bool enabled) noexcept;

        /** @brief 검증된 payload로 advertising을 시작합니다. */
        [[nodiscard]] bool start() noexcept;

        /** @brief advertising을 중지합니다. */
        [[nodiscard]] bool stop() noexcept;

        /** @brief library가 시작한 advertising 상태를 반환합니다. */
        [[nodiscard]] bool running() const noexcept;
    };

    /** @brief active/passive scan과 bounded 결과 queue를 소유합니다. */
    class Scan final
    {
      public:
        /** @brief 중지 상태에서 모든 software filter를 지웁니다. */
        [[nodiscard]] bool clearFilters() noexcept;

        /** @brief 완전히 일치하는 UTF-8 local name filter를 설정합니다. */
        [[nodiscard]] bool filterName(const char *exact_name) noexcept;

        /** @brief advertising service UUID filter를 설정합니다. */
        [[nodiscard]] bool filterServiceUuid(const BLEUuid &uuid) noexcept;

        /** @brief exact peer address filter를 설정합니다. */
        [[nodiscard]] bool filterAddress(const BLEAddress &address) noexcept;

        /** @brief active 또는 passive scan을 시작합니다. */
        [[nodiscard]] bool start(bool active = true) noexcept;

        /** @brief extended report, coded PHY와 controller 중복 제거 선택을 포함해 scan을 시작합니다. */
        [[nodiscard]] bool startExtended(bool active = true, bool coded = false,
                                         bool filter_duplicates = true) noexcept;

        /** @brief scan을 중지합니다. */
        [[nodiscard]] bool stop() noexcept;

        /** @brief scan 중인지 반환합니다. */
        [[nodiscard]] bool running() const noexcept;

        /** @brief callback 미등록 시 읽을 수 있는 queued 결과 수를 반환합니다. */
        [[nodiscard]] int available() const noexcept;

        /** @brief 가장 오래된 bounded scan 결과를 복사합니다. */
        [[nodiscard]] bool read(BLEScanResult &result) noexcept;

        /** @brief BLEDevice.poll()에서 호출할 결과 callback을 등록합니다. */
        void onResult(BLEScanCallback callback, void *context = nullptr) noexcept;

        /** @brief queue가 가득 차 버린 누적 scan 결과 수를 반환합니다. */
        [[nodiscard]] std::uint32_t droppedResults() const noexcept;
    };

    /** @brief LE Coded PHY advertising의 controller coding 선택입니다. */
    enum class BLEAdvertisingCoding : std::uint8_t
    {
        automatic,
        s2,
        s8,
    };

    /** @brief extended advertising set 생성에 사용하는 portable 설정입니다. */
    struct BLEExtendedAdvertisingParameters
    {
        bool connectable = false;
        bool scannable = false;
        bool coded = false;
        bool secondary_1m = false;
        bool anonymous = false;
        bool include_tx_power = false;
        bool use_identity_address = false;
        bool filter_scan_requests = false;
        bool filter_connections = false;
        bool directed_low_duty = false;
        bool directed_peer_uses_rpa = false;
        std::uint8_t identity = 0U;
        std::uint8_t sid = 0U;
        std::uint16_t interval_min = 0x00a0U;
        std::uint16_t interval_max = 0x00f0U;
        BLEAdvertisingCoding coding = BLEAdvertisingCoding::automatic;
        BLEAddress directed_peer;
    };

    /** @brief build profile이 허용하는 여러 extended advertising set lifecycle을 소유합니다. */
    class ExtendedAdvertising final
    {
      public:
        static constexpr std::size_t maximum_payload_length = 255U;
        static constexpr std::size_t product_maximum_sets = 3U;

        /** @brief 설정을 검증하고 새 generation의 advertising set을 만듭니다. */
        [[nodiscard]] bool create(const BLEExtendedAdvertisingParameters &parameters,
                                  BLEAdvertisingSetHandle &advertising_set) noexcept;

        /** @brief AD structure로 인코딩된 raw payload와 scan response를 복사합니다. */
        [[nodiscard]] bool setData(BLEAdvertisingSetHandle advertising_set,
                                   const void *advertising_data,
                                   std::size_t advertising_length,
                                   const void *scan_response_data = nullptr,
                                   std::size_t scan_response_length = 0U) noexcept;

        /** @brief 10 ms duration과 최대 event 수를 제한해 advertising을 시작합니다. */
        [[nodiscard]] bool start(BLEAdvertisingSetHandle advertising_set,
                                 std::uint16_t duration = 0U,
                                 std::uint8_t maximum_events = 0U) noexcept;

        /** @brief 지정 generation의 advertising을 중지합니다. */
        [[nodiscard]] bool stop(BLEAdvertisingSetHandle advertising_set) noexcept;

        /** @brief 중지된 advertising set을 삭제하고 handle을 즉시 무효화합니다. */
        [[nodiscard]] bool remove(BLEAdvertisingSetHandle advertising_set) noexcept;

        /** @brief 지정 generation의 set이 생성되어 있는지 반환합니다. */
        [[nodiscard]] bool exists(BLEAdvertisingSetHandle advertising_set) const noexcept;

        /** @brief 지정 generation의 set이 advertising 중인지 반환합니다. */
        [[nodiscard]] bool running(BLEAdvertisingSetHandle advertising_set) const noexcept;
    };

    /** @brief periodic advertising interval과 ADI/TX power 옵션입니다. */
    struct BLEPeriodicAdvertisingParameters
    {
        std::uint16_t interval_min = 0x00a0U;
        std::uint16_t interval_max = 0x00f0U;
        bool include_tx_power = false;
        bool include_adi = false;
    };

    /** @brief 한 periodic advertiser와 profile 상한의 sync·PAST lifecycle을 소유합니다. */
    class PeriodicAdvertising final
    {
      public:
        static constexpr std::size_t maximum_payload_length = 255U;

        /** @brief 기존 extended set에 periodic interval과 option을 적용합니다. */
        [[nodiscard]] bool configure(
            BLEAdvertisingSetHandle advertising_set,
            const BLEPeriodicAdvertisingParameters &parameters = {}) noexcept;

        /** @brief AD structure로 인코딩된 periodic payload를 복사합니다. */
        [[nodiscard]] bool setData(BLEAdvertisingSetHandle advertising_set,
                                   const void *data, std::size_t length) noexcept;

        /** @brief 구성된 periodic advertising train을 시작합니다. */
        [[nodiscard]] bool start(BLEAdvertisingSetHandle advertising_set) noexcept;

        /** @brief periodic advertising train을 중지합니다. */
        [[nodiscard]] bool stop(BLEAdvertisingSetHandle advertising_set) noexcept;

        /** @brief 지정 set의 periodic advertising 상태를 반환합니다. */
        [[nodiscard]] bool running(BLEAdvertisingSetHandle advertising_set) const noexcept;

        /** @brief 주소·SID를 사용해 profile 상한 안에서 bounded periodic sync를 만듭니다. */
        [[nodiscard]] bool createSync(const BLEAddress &address, std::uint8_t sid,
                                      BLEPeriodicSyncHandle &sync, std::uint16_t skip = 0U,
                                      std::uint16_t timeout_10ms = 1000U,
                                      bool filter_duplicates = true) noexcept;

        /** @brief pending 또는 synchronized periodic sync를 삭제합니다. */
        [[nodiscard]] bool deleteSync(BLEPeriodicSyncHandle sync) noexcept;

        /** @brief 지정 generation의 sync object가 존재하는지 반환합니다. */
        [[nodiscard]] bool exists(BLEPeriodicSyncHandle sync) const noexcept;

        /** @brief 지정 generation의 sync가 동기화됐는지 반환합니다. */
        [[nodiscard]] bool synchronized(BLEPeriodicSyncHandle sync) const noexcept;

        /** @brief callback 미등록 시 읽을 수 있는 periodic report 수를 반환합니다. */
        [[nodiscard]] int available() const noexcept;

        /** @brief 가장 오래된 bounded periodic report를 복사합니다. */
        [[nodiscard]] bool read(BLEPeriodicReport &report) noexcept;

        /** @brief BLEDevice.poll()에서 호출할 periodic report callback을 등록합니다. */
        void onReport(BLEPeriodicReportCallback callback, void *context = nullptr) noexcept;

        /** @brief 가득 찬 report queue가 버린 누적 report 수를 반환합니다. */
        [[nodiscard]] std::uint32_t droppedReports() const noexcept;

        /** @brief 현재 sync 정보를 지정 connection peer에 PAST로 전달합니다. */
        [[nodiscard]] bool transferSync(BLEPeriodicSyncHandle sync,
                                        BLEConnectionHandle connection,
                                        std::uint16_t service_data = 0U) noexcept;

        /** @brief local periodic set 정보를 지정 connection peer에 PAST로 전달합니다. */
        [[nodiscard]] bool transferSet(BLEAdvertisingSetHandle advertising_set,
                                       BLEConnectionHandle connection,
                                       std::uint16_t service_data = 0U) noexcept;

        /** @brief 지정 connection에서 받을 PAST receiver parameter를 설정합니다. */
        [[nodiscard]] bool subscribeTransfers(BLEConnectionHandle connection,
                                              std::uint16_t skip = 0U,
                                              std::uint16_t timeout_10ms = 1000U,
                                              bool filter_duplicates = true) noexcept;

        /** @brief 지정 connection의 PAST receiver 구독을 해제합니다. */
        [[nodiscard]] bool unsubscribeTransfers(BLEConnectionHandle connection) noexcept;
    };

    /** @brief PAwR advertiser의 고정 subevent·response slot 구성입니다. */
    struct BLEPawrAdvertisingParameters
    {
        std::uint16_t interval_min = 0x0100U;
        std::uint16_t interval_max = 0x0100U;
        std::uint8_t subevents = 4U;
        std::uint8_t subevent_interval = 64U;
        std::uint8_t response_slot_delay = 24U;
        std::uint8_t response_slot_spacing = 64U;
        std::uint8_t response_slots = 4U;
        bool include_tx_power = false;
        bool include_adi = false;
    };

    /** @brief PAwR advertiser가 받은 bounded response 복사본입니다. */
    struct BLEPawrResponse
    {
        static constexpr std::size_t maximum_payload_length = 249U;

        BLEAdvertisingSetHandle advertising_set;
        std::uint8_t subevent = 0U;
        std::uint8_t response_slot = 0U;
        std::uint8_t transmit_status = 0U;
        std::int8_t tx_power = 127;
        std::int8_t rssi = 0;
        bool received = false;
        bool truncated = false;
        std::uint8_t payload[maximum_payload_length] = {};
        std::uint16_t payload_length = 0U;
    };

    /** @brief BLEDevice.poll() 문맥에서만 호출되는 PAwR response callback입니다. */
    using BLEPawrResponseCallback = void (*)(const BLEPawrResponse &response, void *context);

    /** @brief 4 subevent × 4 response slot PAwR advertiser/scanner를 소유합니다. */
    class Pawr final
    {
      public:
        static constexpr std::size_t maximum_subevents = 4U;
        static constexpr std::size_t maximum_response_slots = 4U;
        static constexpr std::size_t maximum_payload_length = 249U;

        /** @brief 기존 extended set을 bounded PAwR advertiser로 구성합니다. */
        [[nodiscard]] bool configureAdvertiser(
            BLEAdvertisingSetHandle advertising_set,
            const BLEPawrAdvertisingParameters &parameters = {}) noexcept;

        /** @brief controller request 때 사용할 한 subevent payload와 slot window를 복사합니다. */
        [[nodiscard]] bool setSubeventData(BLEAdvertisingSetHandle advertising_set,
                                           std::uint8_t subevent, const void *data,
                                           std::size_t length,
                                           std::uint8_t response_slot_start = 0U,
                                           std::uint8_t response_slot_count = 4U) noexcept;

        /** @brief synchronized PAwR에서 수신할 bounded subevent 목록을 설정합니다. */
        [[nodiscard]] bool configureScanner(BLEPeriodicSyncHandle sync,
                                            const std::uint8_t *subevents,
                                            std::size_t count) noexcept;

        /** @brief 수신 request에 한 번 사용할 이후 subevent response를 설정합니다. */
        [[nodiscard]] bool sendResponse(BLEPeriodicSyncHandle sync,
                                        std::uint16_t request_event,
                                        std::uint8_t request_subevent,
                                        std::uint8_t response_subevent,
                                        std::uint8_t response_slot,
                                        const void *data, std::size_t length) noexcept;

        /** @brief callback 미등록 시 읽을 수 있는 PAwR response 수를 반환합니다. */
        [[nodiscard]] int available() const noexcept;

        /** @brief 가장 오래된 bounded PAwR response를 복사합니다. */
        [[nodiscard]] bool read(BLEPawrResponse &response) noexcept;

        /** @brief BLEDevice.poll()에서 호출할 PAwR response callback을 등록합니다. */
        void onResponse(BLEPawrResponseCallback callback, void *context = nullptr) noexcept;

        /** @brief 가득 찬 response queue가 버린 누적 response 수를 반환합니다. */
        [[nodiscard]] std::uint32_t droppedResponses() const noexcept;
    };

    /** @brief 실제 link에서 확인한 connection parameter snapshot입니다. */
    struct BLEConnectionParameters
    {
        std::uint32_t interval_us = 0U;
        std::uint16_t latency = 0U;
        std::uint16_t supervision_timeout = 0U;
    };

    /** @brief 실제 controller가 확인한 link별 Data Length Extension 값입니다. */
    struct BLEDataLengthInfo
    {
        std::uint16_t transmit_octets = 0U;
        std::uint16_t transmit_time_us = 0U;
        std::uint16_t receive_octets = 0U;
        std::uint16_t receive_time_us = 0U;
    };

    /** @brief Host가 복사한 remote Link Layer version과 8-byte LE feature입니다. */
    struct BLERemoteInformation
    {
        std::uint8_t version = 0U;
        std::uint16_t manufacturer = 0U;
        std::uint16_t subversion = 0U;
        std::uint8_t features[8] = {};
    };

    /** @brief 한 PHY의 현재 local 송신 전력과 controller 상한입니다. */
    struct BLETransmitPowerLevel
    {
        BLETransmitPowerPhy phy = BLETransmitPowerPhy::unknown;
        std::int8_t current_dbm = 0;
        std::int8_t maximum_dbm = 0;
    };

    /** @brief 표준 Path Loss Monitoring threshold와 debounce 조건입니다. */
    struct BLEPathLossParameters
    {
        std::uint8_t high_threshold_db = 60U;
        std::uint8_t high_hysteresis_db = 5U;
        std::uint8_t low_threshold_db = 40U;
        std::uint8_t low_hysteresis_db = 5U;
        std::uint16_t minimum_connection_events = 5U;
    };

    /** @brief local RPA rotation 정책과 확장 advertising 만료 횟수를 관리합니다. */
    class Privacy final
    {
      public:
        static constexpr std::uint16_t minimum_rotation_timeout_seconds = 1U;
        static constexpr std::uint16_t maximum_rotation_timeout_seconds = 3600U;

        /** @brief production profile이 privacy와 runtime timeout을 지원하는지 반환합니다. */
        [[nodiscard]] bool supported() const noexcept;

        /** @brief 이후 local RPA 회전 timeout을 1~3600초 범위로 설정합니다. */
        [[nodiscard]] bool setRotationTimeout(std::uint16_t seconds) noexcept;

        /** @brief 현재 API가 적용한 RPA 회전 timeout을 반환합니다. */
        [[nodiscard]] std::uint16_t rotationTimeout() const noexcept;

        /** @brief 현재 Device session의 extended set RPA 만료 callback 수를 반환합니다. */
        [[nodiscard]] std::uint32_t expirationCount() const noexcept;
    };

    /** @brief build profile의 local identity slot을 생성·조회·재사용합니다. */
    class Identity final
    {
      public:
        static constexpr std::size_t product_maximum_identities = 3U;

        /** @brief 삭제되지 않은 local identity 수를 반환합니다. */
        [[nodiscard]] std::size_t count() const noexcept;

        /** @brief 지정 identity의 주소 복사본을 반환합니다. */
        [[nodiscard]] bool address(std::uint8_t identity,
                                   BLEAddress &address) const noexcept;

        /** @brief 새 random static identity와 IRK를 생성합니다. */
        [[nodiscard]] bool create(std::uint8_t &identity, BLEAddress &address) noexcept;

        /** @brief 삭제됐거나 사용 중인 non-default slot을 새 identity로 교체합니다. */
        [[nodiscard]] bool reset(std::uint8_t identity, BLEAddress &address) noexcept;

        /** @brief non-default identity와 해당 bond를 삭제합니다. */
        [[nodiscard]] bool remove(std::uint8_t identity) noexcept;
    };

    /** @brief controller Filter Accept List와 Periodic Advertiser List를 관리합니다. */
    class AdvertisingLists final
    {
      public:
        /** @brief build profile의 Filter Accept List 상한을 반환합니다. */
        [[nodiscard]] std::size_t filterAcceptCapacity() const noexcept;

        /** @brief controller resolving list 상한을 반환합니다. */
        [[nodiscard]] std::size_t resolvingCapacity() const noexcept;

        /** @brief build profile의 Periodic Advertiser List 상한을 반환합니다. */
        [[nodiscard]] std::size_t periodicAdvertiserCapacity() const noexcept;

        /** @brief Filter Accept List에 exact peer 주소를 추가합니다. */
        [[nodiscard]] bool addFilterAccept(const BLEAddress &address) noexcept;

        /** @brief Filter Accept List에서 exact peer 주소를 삭제합니다. */
        [[nodiscard]] bool removeFilterAccept(const BLEAddress &address) noexcept;

        /** @brief Filter Accept List를 비웁니다. */
        [[nodiscard]] bool clearFilterAccept() noexcept;

        /** @brief Periodic Advertiser List에 주소와 SID를 추가합니다. */
        [[nodiscard]] bool addPeriodicAdvertiser(const BLEAddress &address,
                                                 std::uint8_t sid) noexcept;

        /** @brief Periodic Advertiser List에서 주소와 SID를 삭제합니다. */
        [[nodiscard]] bool removePeriodicAdvertiser(const BLEAddress &address,
                                                    std::uint8_t sid) noexcept;

        /** @brief Periodic Advertiser List를 비웁니다. */
        [[nodiscard]] bool clearPeriodicAdvertisers() noexcept;
    };

    /** @brief 한 EAD key/IV와 bounded randomizer replay cache를 소유합니다. */
    class EncryptedAdvertisingData final
    {
      public:
        static constexpr std::size_t session_key_length = 16U;
        static constexpr std::size_t initialization_vector_length = 8U;
        static constexpr std::size_t randomizer_length = 5U;
        static constexpr std::size_t mic_length = 4U;
        static constexpr std::size_t maximum_encrypted_length = 255U;
        static constexpr std::size_t maximum_plaintext_length =
            maximum_encrypted_length - randomizer_length - mic_length;
        static constexpr std::size_t replay_cache_entries = 16U;

        EncryptedAdvertisingData() = default;
        ~EncryptedAdvertisingData() noexcept;
        EncryptedAdvertisingData(const EncryptedAdvertisingData &) = delete;
        EncryptedAdvertisingData &operator=(const EncryptedAdvertisingData &) = delete;

        /** @brief 16-byte session key와 8-byte IV를 복사하고 replay cache를 비웁니다. */
        [[nodiscard]] bool configure(const std::uint8_t session_key[session_key_length],
                                     const std::uint8_t iv[initialization_vector_length]) noexcept;

        /** @brief AD structure stream을 randomizer와 MIC가 포함된 EAD로 암호화합니다. */
        [[nodiscard]] bool encrypt(const void *plaintext, std::size_t plaintext_length,
                                   void *encrypted, std::size_t encrypted_capacity,
                                   std::size_t &encrypted_length) noexcept;

        /** @brief EAD 무결성과 bounded replay를 검사하고 payload를 복호화합니다. */
        [[nodiscard]] bool decrypt(const void *encrypted, std::size_t encrypted_length,
                                   void *plaintext, std::size_t plaintext_capacity,
                                   std::size_t &plaintext_length) noexcept;

        /** @brief key·IV·replay cache를 지우고 미설정 상태로 되돌립니다. */
        void clear() noexcept;

      private:
        std::uint8_t session_key_[session_key_length] = {};
        std::uint8_t iv_[initialization_vector_length] = {};
        std::uint8_t replay_cache_[replay_cache_entries][randomizer_length] = {};
        std::size_t replay_count_ = 0U;
        std::size_t replay_cursor_ = 0U;
        bool configured_ = false;
    };

    /** @brief Nordic SDC의 LLPM·QoS·시간·radio event 확장을 고정 queue로 제공합니다. */
    class NordicExtensions final
    {
      public:
        static constexpr std::uint32_t minimum_llpm_interval_us = 1000U;
        static constexpr std::uint32_t maximum_llpm_interval_us = 7000U;
        static constexpr std::uint32_t recommended_radio_prepare_distance_us = 3000U;

        /** @brief 연결이 없을 때 image-wide Nordic LLPM mode를 켜거나 끕니다. */
        [[nodiscard]] bool setLlpmMode(bool enabled) noexcept;

        /** @brief 2M PHY link에 1~7 ms Nordic LLPM connection update를 요청합니다. */
        [[nodiscard]] bool requestLlpmInterval(BLEConnectionHandle connection,
                                               std::uint32_t interval_us = 1000U,
                                               std::uint16_t latency = 0U,
                                               std::uint16_t supervision_timeout_10ms = 300U) noexcept;

        /** @brief image-wide QoS connection-event report 생성을 켜거나 끕니다. */
        [[nodiscard]] bool setConnectionEventReports(bool enabled) noexcept;

        /** @brief image-wide QoS channel survey와 0 또는 3,000~4,000,000 us 주기를 설정합니다. */
        [[nodiscard]] bool setChannelSurvey(bool enabled,
                                            std::uint32_t interval_us = 100000U) noexcept;

        /** @brief connection anchor-point 보고를 켜거나 끕니다. */
        [[nodiscard]] bool setAnchorPointReports(bool enabled) noexcept;

        /** @brief QoS connection-event queue 항목 수를 반환합니다. */
        [[nodiscard]] int availableConnectionEventReports() const noexcept;

        /** @brief 가장 오래된 QoS connection-event 보고를 복사합니다. */
        [[nodiscard]] bool readConnectionEventReport(
            BLENordicConnectionEventReport &report) noexcept;

        /** @brief channel-survey queue 항목 수를 반환합니다. */
        [[nodiscard]] int availableChannelSurveyReports() const noexcept;

        /** @brief 가장 오래된 channel-survey 보고를 복사합니다. */
        [[nodiscard]] bool readChannelSurveyReport(
            BLENordicChannelSurveyReport &report) noexcept;

        /** @brief anchor-point queue 항목 수를 반환합니다. */
        [[nodiscard]] int availableAnchorPointReports() const noexcept;

        /** @brief 가장 오래된 anchor-point 보고를 복사합니다. */
        [[nodiscard]] bool readAnchorPointReport(
            BLENordicAnchorPointReport &report) noexcept;

        /** @brief main-thread QoS connection-event callback을 등록합니다. */
        void onConnectionEvent(BLENordicConnectionEventCallback callback,
                               void *context = nullptr) noexcept;

        /** @brief main-thread channel-survey callback을 등록합니다. */
        void onChannelSurvey(BLENordicChannelSurveyCallback callback,
                             void *context = nullptr) noexcept;

        /** @brief main-thread anchor-point callback을 등록합니다. */
        void onAnchorPoint(BLENordicAnchorPointCallback callback,
                           void *context = nullptr) noexcept;

        /** @brief 기준 anchor에서 16-bit event counter 차이만큼 이동한 controller 시간을 계산합니다. */
        [[nodiscard]] bool projectAnchorPoint(
            const BLENordicAnchorPointReport &reference,
            std::uint16_t target_event_counter,
            std::uint32_t connection_interval_us,
            std::uint64_t &controller_clock_us) const noexcept;

        /** @brief connection event 시작에 caller 소유 peripheral task를 결합합니다. */
        [[nodiscard]] bool setConnectionEventTrigger(BLEConnectionHandle connection,
                                                     std::uint32_t task_address) noexcept;

        /** @brief advertising event 시작에 caller 소유 peripheral task를 결합합니다. */
        [[nodiscard]] bool setAdvertisingEventTrigger(BLEAdvertisingSetHandle advertising_set,
                                                      std::uint32_t task_address) noexcept;

        /** @brief scanner event 시작에 caller 소유 peripheral task를 결합합니다. */
        [[nodiscard]] bool setScannerEventTrigger(std::uint32_t task_address) noexcept;

        /** @brief initiator event 시작에 caller 소유 peripheral task를 결합합니다. */
        [[nodiscard]] bool setInitiatorEventTrigger(std::uint32_t task_address) noexcept;

        /** @brief radio event 전 system-workqueue prepare callback을 논리적으로 켜거나 끕니다. */
        [[nodiscard]] bool setRadioNotification(
            bool enabled,
            std::uint32_t prepare_distance_us = recommended_radio_prepare_distance_us) noexcept;

        /** @brief system-workqueue radio prepare callback을 등록합니다. */
        void onRadioPrepare(BLENordicRadioPrepareCallback callback,
                            void *context = nullptr) noexcept;

        /** @brief report queue가 가득 차 버린 누적 report 수를 반환합니다. */
        [[nodiscard]] std::uint32_t droppedReports() const noexcept;

        /** @brief experimental controller와 고정 Host TX 경로의 적용성을 분리해 반환합니다. */
        [[nodiscard]] BLEFlushableAclSupport flushableAclSupport() const noexcept;
    };

    /** @brief 고정 2-slot LE link와 실제 NCS link parameter를 제어합니다. */
    class Connection final
    {
      public:
        /** @brief exact scan 결과 주소에 비동기 연결을 시작합니다. */
        [[nodiscard]] bool connect(const BLEAddress &address) noexcept;

        /** @brief 비동기 central 연결을 시작하고 generation handle을 반환합니다. */
        [[nodiscard]] bool connect(const BLEAddress &address,
                                   BLEConnectionHandle &connection) noexcept;

        /** @brief 현재 연결을 비동기로 종료합니다. */
        [[nodiscard]] bool disconnect() noexcept;

        /** @brief 지정 generation의 link를 비동기로 종료합니다. */
        [[nodiscard]] bool disconnect(BLEConnectionHandle connection) noexcept;

        /** @brief 마지막 peer 주소에 새 연결을 시작합니다. */
        [[nodiscard]] bool reconnect() noexcept;

        /** @brief 마지막 central peer에 재연결하고 새 generation handle을 반환합니다. */
        [[nodiscard]] bool reconnect(BLEConnectionHandle &connection) noexcept;

        /** @brief 연결 시도 중인지 반환합니다. */
        [[nodiscard]] bool connecting() const noexcept;

        /** @brief 지정 generation의 central link가 연결 시도 중인지 반환합니다. */
        [[nodiscard]] bool connecting(BLEConnectionHandle connection) const noexcept;

        /** @brief link가 연결되어 있는지 반환합니다. */
        [[nodiscard]] bool connected() const noexcept;

        /** @brief 지정 generation의 link가 연결되어 있는지 반환합니다. */
        [[nodiscard]] bool connected(BLEConnectionHandle connection) const noexcept;

        /** @brief 현재 활성 link 수를 반환합니다. */
        [[nodiscard]] std::size_t count() const noexcept;

        /** @brief 지정 local 역할의 active 또는 pending generation handle을 반환합니다. */
        [[nodiscard]] BLEConnectionHandle handle(BLELinkRole role) const noexcept;

        /** @brief handle이 나타내는 local 역할을 반환합니다. */
        [[nodiscard]] BLELinkRole role(BLEConnectionHandle connection) const noexcept;

        /** @brief 마지막 또는 현재 peer 주소를 반환합니다. */
        [[nodiscard]] BLEAddress peerAddress() const noexcept;

        /** @brief 지정 generation의 현재 peer 주소를 반환합니다. */
        [[nodiscard]] BLEAddress peerAddress(BLEConnectionHandle connection) const noexcept;

        /** @brief 지정 link 설정에 실제 사용된 remote 주소를 반환합니다. */
        [[nodiscard]] BLEAddress connectionAddress(BLEConnectionHandle connection) const noexcept;

        /** @brief 지정 link의 peer identity가 확인되었는지 반환합니다. */
        [[nodiscard]] bool identityResolved(BLEConnectionHandle connection) const noexcept;

        /** @brief 현재 ATT MTU를 반환하며 미연결이면 0을 반환합니다. */
        [[nodiscard]] std::size_t mtu() const noexcept;

        /** @brief 지정 generation의 ATT MTU를 반환하며 미연결이면 0을 반환합니다. */
        [[nodiscard]] std::size_t mtu(BLEConnectionHandle connection) const noexcept;

        /** @brief 현재 연결에서 최대 ATT MTU 교환을 요청합니다. */
        [[nodiscard]] bool requestMtu() noexcept;

        /** @brief 지정 generation에서 최대 ATT MTU 교환을 요청합니다. */
        [[nodiscard]] bool requestMtu(BLEConnectionHandle connection) noexcept;

        /** @brief 실제 controller가 보고한 현재 PHY를 반환합니다. */
        [[nodiscard]] BLEPhy phy() const noexcept;

        /** @brief 지정 generation에서 실제 controller가 보고한 PHY를 반환합니다. */
        [[nodiscard]] BLEPhy phy(BLEConnectionHandle connection) const noexcept;

        /** @brief 지원 PHY mask로 link PHY 갱신을 요청합니다. */
        [[nodiscard]] bool requestPhy(bool allow_2m, bool allow_coded = false) noexcept;

        /** @brief 지정 generation에서 지원 PHY mask로 갱신을 요청합니다. */
        [[nodiscard]] bool requestPhy(BLEConnectionHandle connection, bool allow_2m,
                                      bool allow_coded = false) noexcept;

        /** @brief 실제 controller의 현재 local TX power를 읽습니다. */
        [[nodiscard]] bool txPower(std::int8_t &dbm) const noexcept;

        /** @brief 지정 generation에서 현재 local TX power를 읽습니다. */
        [[nodiscard]] bool txPower(BLEConnectionHandle connection, std::int8_t &dbm) const noexcept;

        /** @brief 지정 generation과 PHY의 local TX power와 최대값을 읽습니다. */
        [[nodiscard]] bool localTransmitPower(BLEConnectionHandle connection,
                                              BLETransmitPowerPhy phy,
                                              BLETransmitPowerLevel &level) const noexcept;

        /** @brief 지정 PHY의 remote TX power를 비동기로 요청합니다. */
        [[nodiscard]] bool requestRemoteTransmitPower(BLEConnectionHandle connection,
                                                      BLETransmitPowerPhy phy) noexcept;

        /** @brief peer에 -20~20 dB 범위의 표준 송신 전력 변경을 요청합니다. */
        [[nodiscard]] bool requestRemoteTransmitPowerChange(BLEConnectionHandle connection,
                                                            BLETransmitPowerPhy phy,
                                                            std::int8_t delta_db) noexcept;

        /** @brief 지정 link의 local/remote 송신 전력 보고를 독립적으로 켜거나 끕니다. */
        [[nodiscard]] bool setTransmitPowerReporting(BLEConnectionHandle connection,
                                                     bool local_enabled,
                                                     bool remote_enabled) noexcept;

        /** @brief 지정 link의 즉시 RSSI를 dBm 단위로 읽습니다. */
        [[nodiscard]] bool readRssi(BLEConnectionHandle connection,
                                    std::int8_t &rssi_dbm) const noexcept;

        /** @brief 지정 link에 검증된 Path Loss threshold 조건을 적용합니다. */
        [[nodiscard]] bool configurePathLossMonitoring(
            BLEConnectionHandle connection,
            const BLEPathLossParameters &parameters) noexcept;

        /** @brief 지정 link의 Path Loss 구간 보고를 켜거나 끕니다. */
        [[nodiscard]] bool setPathLossMonitoring(BLEConnectionHandle connection,
                                                 bool enabled) noexcept;

        /** @brief 이후 central 연결에 적용할 기본 Connection Subrating 범위를 설정합니다. */
        [[nodiscard]] bool setDefaultSubrate(
            const BLESubrateParameters &parameters) noexcept;

        /** @brief 지정 link에 Connection Subrating 변경을 요청합니다. */
        [[nodiscard]] bool requestSubrate(BLEConnectionHandle connection,
                                          const BLESubrateParameters &parameters) noexcept;

        /** @brief 지정 link가 마지막으로 보고한 Connection Subrating 결과를 읽습니다. */
        [[nodiscard]] bool subrate(BLEConnectionHandle connection,
                                   BLESubrateInfo &information) const noexcept;

        /** @brief 이후 central 연결에 적용할 표준 connection rate 범위를 설정합니다. */
        [[nodiscard]] bool setDefaultConnectionRate(
            const BLEConnectionRateParameters &parameters) noexcept;

        /** @brief 지정 link에 표준 Shorter Connection Interval 절차를 요청합니다. */
        [[nodiscard]] bool requestConnectionRate(
            BLEConnectionHandle connection,
            const BLEConnectionRateParameters &parameters) noexcept;

        /** @brief 지정 link가 마지막으로 보고한 실제 connection rate를 읽습니다. */
        [[nodiscard]] bool connectionRate(BLEConnectionHandle connection,
                                          BLEConnectionRateInfo &information) const noexcept;

        /** @brief controller가 지원하는 최소 connection interval을 us 단위로 읽습니다. */
        [[nodiscard]] bool minimumConnectionInterval(
            std::uint16_t &interval_us) const noexcept;

        /** @brief 지정 link의 PHY·spacing 종류에 Frame Space Update를 요청합니다. */
        [[nodiscard]] bool requestFrameSpace(
            BLEConnectionHandle connection,
            const BLEFrameSpaceParameters &parameters) noexcept;

        /** @brief 지정 link가 마지막으로 보고한 Frame Space 결과를 읽습니다. */
        [[nodiscard]] bool frameSpace(BLEConnectionHandle connection,
                                      BLEFrameSpaceInfo &information) const noexcept;

        /** @brief local controller의 전체 LE feature page 복사본을 읽습니다. */
        [[nodiscard]] bool localExtendedFeatures(
            BLEExtendedFeatureSet &features) const noexcept;

        /** @brief 지정 link에서 최대 0~10 page의 remote feature 교환을 요청합니다. */
        [[nodiscard]] bool requestRemoteExtendedFeatures(
            BLEConnectionHandle connection,
            std::uint8_t maximum_page = BLEExtendedFeatureSet::maximum_page) noexcept;

        /** @brief 지정 link에서 마지막으로 받은 remote feature page 복사본을 읽습니다. */
        [[nodiscard]] bool remoteExtendedFeatures(
            BLEConnectionHandle connection,
            BLEExtendedFeatureSet &features) const noexcept;

        /** @brief SCA controller 절차와 고정 Host 요청·보고 API 지원성을 분리해 반환합니다. */
        [[nodiscard]] BLESleepClockAccuracySupport sleepClockAccuracySupport() const noexcept;

        /** @brief 모든 LE link에 적용할 37-channel Host classification을 설정합니다. */
        [[nodiscard]] bool setChannelClassification(
            const std::uint8_t channel_map[5]) noexcept;

        /** @brief 1.25 ms/10 ms 단위 LE connection parameter를 요청합니다. */
        [[nodiscard]] bool requestParameters(std::uint16_t interval_min, std::uint16_t interval_max,
                                             std::uint16_t latency, std::uint16_t timeout) noexcept;

        /** @brief 지정 generation에서 LE connection parameter를 요청합니다. */
        [[nodiscard]] bool requestParameters(BLEConnectionHandle connection,
                                             std::uint16_t interval_min,
                                             std::uint16_t interval_max, std::uint16_t latency,
                                             std::uint16_t timeout) noexcept;

        /** @brief 지정 generation에서 실제 connection parameter를 읽습니다. */
        [[nodiscard]] bool parameters(BLEConnectionHandle connection,
                                      BLEConnectionParameters &information) const noexcept;

        /** @brief 지정 generation에서 DLE 최대 송신 octet·시간을 요청합니다. */
        [[nodiscard]] bool requestDataLength(BLEConnectionHandle connection,
                                             std::uint16_t transmit_octets = 251U,
                                             std::uint16_t transmit_time_us = 17040U) noexcept;

        /** @brief 지정 generation에서 실제 송수신 Data Length 값을 읽습니다. */
        [[nodiscard]] bool dataLength(BLEConnectionHandle connection,
                                      BLEDataLengthInfo &information) const noexcept;

        /** @brief 지정 generation에서 복사 가능한 remote version·feature를 읽습니다. */
        [[nodiscard]] bool remoteInformation(BLEConnectionHandle connection,
                                             BLERemoteInformation &information) const noexcept;
    };

} // namespace nucode::ble

/** @brief NU54DK의 단일 BLE Core lifecycle 객체입니다. */
extern nucode::ble::Device BLEDevice;

/** @brief NU54DK의 단일 legacy advertising 객체입니다. */
extern nucode::ble::Advertising BLEAdvertising;

/** @brief NU54DK의 단일 bounded scan 객체입니다. */
extern nucode::ble::Scan BLEScan;

/** @brief NU54DK의 bounded multiple extended advertising set 객체입니다. */
extern nucode::ble::ExtendedAdvertising BLEExtendedAdvertising;

/** @brief NU54DK의 한 개 periodic advertiser·sync·PAST 객체입니다. */
extern nucode::ble::PeriodicAdvertising BLEPeriodicAdvertising;

/** @brief NU54DK의 bounded PAwR advertiser·scanner 객체입니다. */
extern nucode::ble::Pawr BLEPawr;

/** @brief NU54DK local privacy와 RPA rotation 객체입니다. */
extern nucode::ble::Privacy BLEPrivacy;

/** @brief NU54DK local identity slot 객체입니다. */
extern nucode::ble::Identity BLEIdentity;

/** @brief NU54DK controller advertising list 객체입니다. */
extern nucode::ble::AdvertisingLists BLEAdvertisingLists;

/** @brief NU54DK Nordic SDC LLPM·QoS·시간·event 확장 객체입니다. */
extern nucode::ble::NordicExtensions BLENordic;

/** @brief NU54DK의 단일 LE connection 객체입니다. */
extern nucode::ble::Connection BLEConnection;

#endif
