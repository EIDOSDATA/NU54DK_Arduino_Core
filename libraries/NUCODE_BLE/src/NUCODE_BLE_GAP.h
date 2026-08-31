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
        error,
    };

    /** @brief BLEDevice.poll() 문맥에서만 호출되는 Core/GAP callback입니다. */
    using BLEEventCallback = void (*)(BLEEvent event, void *context);

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
        explicit BLEAddress(const char *text,
                            Type type = Type::public_address) noexcept;

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

    /** @brief callback 밖에서도 값 복사본이 유지되는 bounded scan 결과입니다. */
    struct BLEScanResult
    {
        static constexpr std::size_t maximum_name_length = 32U;
        static constexpr std::size_t maximum_payload_length = 31U;

        BLEAddress address;
        std::int8_t rssi = 0;
        bool connectable = false;
        bool scan_response = false;
        bool truncated = false;
        char name[maximum_name_length + 1U] = {};
        std::uint8_t payload[maximum_payload_length] = {};
        std::uint8_t payload_length = 0U;
    };

    /** @brief BLEDevice.poll() 문맥에서만 호출되는 scan 결과 callback입니다. */
    using BLEScanCallback = void (*)(const BLEScanResult &result, void *context);

    /** @brief 현재 LE PHY를 portable enum으로 노출합니다. */
    enum class BLEPhy : std::uint8_t
    {
        unknown,
        le_1m,
        le_2m,
        coded,
    };

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

        /** @brief Bluetooth 시작 전에 GATT service schema를 추가합니다. */
        [[nodiscard]] bool addService(BLEService &service) noexcept;

        /** @brief 마지막 공개 오류를 반환합니다. */
        [[nodiscard]] BLEError lastError() const noexcept;

        /** @brief 마지막 Zephyr/NCS 오류를 반환합니다. */
        [[nodiscard]] int lastDriverError() const noexcept;

        /** @brief 가득 찬 event queue가 버린 누적 event 수를 반환합니다. */
        [[nodiscard]] std::uint32_t droppedEvents() const noexcept;

        /** @brief 현재 profile의 동시 peer 수가 하나임을 고정합니다. */
        [[nodiscard]] static constexpr std::size_t maximumConnections() noexcept
        {
            return 1U;
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
        [[nodiscard]] bool setInterval(std::uint16_t minimum,
                                       std::uint16_t maximum) noexcept;

        /** @brief 16/32/128-bit service UUID를 광고 payload에 추가합니다. */
        [[nodiscard]] bool addServiceUuid(const BLEUuid &uuid) noexcept;

        /** @brief company ID와 bounded manufacturer payload를 설정합니다. */
        [[nodiscard]] bool setManufacturerData(std::uint16_t company_id,
                                               const void *data,
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

    /** @brief 단일 LE peer 연결과 실제 NCS link parameter를 소유합니다. */
    class Connection final
    {
    public:
        /** @brief exact scan 결과 주소에 비동기 연결을 시작합니다. */
        [[nodiscard]] bool connect(const BLEAddress &address) noexcept;

        /** @brief 현재 연결을 비동기로 종료합니다. */
        [[nodiscard]] bool disconnect() noexcept;

        /** @brief 마지막 peer 주소에 새 연결을 시작합니다. */
        [[nodiscard]] bool reconnect() noexcept;

        /** @brief 연결 시도 중인지 반환합니다. */
        [[nodiscard]] bool connecting() const noexcept;

        /** @brief link가 연결되어 있는지 반환합니다. */
        [[nodiscard]] bool connected() const noexcept;

        /** @brief 마지막 또는 현재 peer 주소를 반환합니다. */
        [[nodiscard]] BLEAddress peerAddress() const noexcept;

        /** @brief 현재 ATT MTU를 반환하며 미연결이면 0을 반환합니다. */
        [[nodiscard]] std::size_t mtu() const noexcept;

        /** @brief 현재 연결에서 최대 ATT MTU 교환을 요청합니다. */
        [[nodiscard]] bool requestMtu() noexcept;

        /** @brief 실제 controller가 보고한 현재 PHY를 반환합니다. */
        [[nodiscard]] BLEPhy phy() const noexcept;

        /** @brief 지원 PHY mask로 link PHY 갱신을 요청합니다. */
        [[nodiscard]] bool requestPhy(bool allow_2m, bool allow_coded = false) noexcept;

        /** @brief 실제 controller의 현재 local TX power를 읽습니다. */
        [[nodiscard]] bool txPower(std::int8_t &dbm) const noexcept;

        /** @brief 1.25 ms/10 ms 단위 LE connection parameter를 요청합니다. */
        [[nodiscard]] bool requestParameters(std::uint16_t interval_min,
                                             std::uint16_t interval_max,
                                             std::uint16_t latency,
                                             std::uint16_t timeout) noexcept;
    };

} // namespace nucode::ble

/** @brief NU54DK의 단일 BLE Core lifecycle 객체입니다. */
extern nucode::ble::Device BLEDevice;

/** @brief NU54DK의 단일 legacy advertising 객체입니다. */
extern nucode::ble::Advertising BLEAdvertising;

/** @brief NU54DK의 단일 bounded scan 객체입니다. */
extern nucode::ble::Scan BLEScan;

/** @brief NU54DK의 단일 LE connection 객체입니다. */
extern nucode::ble::Connection BLEConnection;

#endif
