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
        rpa_expired,
        error,
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

    /** @brief 기존 event에 link handle과 local 역할을 결합한 상세 event입니다. */
    struct BLEEventInfo
    {
        BLEEvent event = BLEEvent::error;
        BLEConnectionHandle connection;
        BLEAdvertisingSetHandle advertising_set;
        BLEPeriodicSyncHandle periodic_sync;
        BLELinkRole role = BLELinkRole::none;
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

    /** @brief extended advertising set 생성에 사용하는 portable 설정입니다. */
    struct BLEExtendedAdvertisingParameters
    {
        bool connectable = false;
        bool scannable = false;
        bool coded = false;
        bool anonymous = false;
        bool include_tx_power = false;
        std::uint8_t sid = 0U;
        std::uint16_t interval_min = 0x00a0U;
        std::uint16_t interval_max = 0x00f0U;
    };

    /** @brief 한 개의 고정 extended advertising set lifecycle을 소유합니다. */
    class ExtendedAdvertising final
    {
      public:
        static constexpr std::size_t maximum_payload_length = 255U;

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

    /** @brief 한 periodic advertiser와 한 sync·PAST lifecycle을 고정 자원으로 소유합니다. */
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

        /** @brief 주소·SID를 사용해 한 개의 bounded periodic sync를 만듭니다. */
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
        std::uint8_t subevent_interval = 48U;
        std::uint8_t response_slot_delay = 8U;
        std::uint8_t response_slot_spacing = 80U;
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

/** @brief NU54DK의 한 개 고정 extended advertising set 객체입니다. */
extern nucode::ble::ExtendedAdvertising BLEExtendedAdvertising;

/** @brief NU54DK의 한 개 periodic advertiser·sync·PAST 객체입니다. */
extern nucode::ble::PeriodicAdvertising BLEPeriodicAdvertising;

/** @brief NU54DK의 bounded PAwR advertiser·scanner 객체입니다. */
extern nucode::ble::Pawr BLEPawr;

/** @brief NU54DK local privacy와 RPA rotation 객체입니다. */
extern nucode::ble::Privacy BLEPrivacy;

/** @brief NU54DK의 단일 LE connection 객체입니다. */
extern nucode::ble::Connection BLEConnection;

#endif
