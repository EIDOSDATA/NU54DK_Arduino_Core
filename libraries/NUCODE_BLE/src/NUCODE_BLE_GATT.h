/**
 * @file NUCODE_BLE_GATT.h
 * @brief NU54DK 범용 GATT server/client Arduino API를 선언합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#ifndef NUCODE_BLE_GATT_H_
#define NUCODE_BLE_GATT_H_

#include <NUCODE_BLE_GAP.h>

#include <cstddef>
#include <cstdint>

namespace nucode::ble
{

    namespace internal
    {
        struct GattAccess;
    }

    /** @brief GATT characteristic property bit입니다. */
    enum class BLEProperty : std::uint8_t
    {
        none = 0U,
        read = 1U << 0U,
        write = 1U << 1U,
        write_without_response = 1U << 2U,
        notify = 1U << 3U,
        indicate = 1U << 4U,
    };

    /** @brief BLEProperty bit 조합을 만듭니다. */
    [[nodiscard]] constexpr BLEProperty operator|(BLEProperty left, BLEProperty right) noexcept
    {
        return static_cast<BLEProperty>(static_cast<std::uint8_t>(left) |
                                        static_cast<std::uint8_t>(right));
    }

    /** @brief GATT characteristic 접근 권한 bit입니다. */
    enum class BLEPermission : std::uint8_t
    {
        none = 0U,
        read = 1U << 0U,
        write = 1U << 1U,
    };

    /** @brief BLEPermission bit 조합을 만듭니다. */
    [[nodiscard]] constexpr BLEPermission operator|(BLEPermission left,
                                                    BLEPermission right) noexcept
    {
        return static_cast<BLEPermission>(static_cast<std::uint8_t>(left) |
                                          static_cast<std::uint8_t>(right));
    }

    /** @brief server characteristic의 main-thread event입니다. */
    enum class BLECharacteristicEvent : std::uint8_t
    {
        written,
        subscribed,
        unsubscribed,
        notification_sent,
        indication_confirmed,
        indication_failed,
        descriptor_written,
        authorization_allowed,
        authorization_denied,
    };

    class BLECharacteristic;
    class BLEDescriptor;

    /** @brief server authorization callback이 판정할 접근 종류입니다. */
    enum class BLEGattAuthorizationOperation : std::uint8_t
    {
        read,
        write,
    };

    /** @brief Bluetooth callback 문맥에서만 유효한 bounded authorization 요청입니다. */
    struct BLEGattAuthorizationRequest
    {
        BLEConnectionHandle connection;
        BLECharacteristic *characteristic = nullptr;
        BLEDescriptor *descriptor = nullptr;
        BLEGattAuthorizationOperation operation = BLEGattAuthorizationOperation::read;
        const std::uint8_t *data = nullptr;
        std::size_t length = 0U;
        std::size_t offset = 0U;
        bool prepare = false;
        bool execute = false;
        bool without_response = false;
    };

    /**
     * @brief server read/write를 동기 판정하는 callback입니다.
     * @return 접근을 허용하면 true, ATT authorization 오류로 거부하면 false입니다.
     * @warning Bluetooth callback 문맥에서 실행되므로 bounded·non-blocking이어야 합니다.
     */
    using BLEGattAuthorizationCallback = bool (*)(const BLEGattAuthorizationRequest &request,
                                                   void *context);

    /** @brief server characteristic event의 callback 동안 유효한 상세 정보입니다. */
    struct BLECharacteristicEventInfo
    {
        BLECharacteristicEvent event;
        BLEConnectionHandle connection;
        const std::uint8_t *data;
        std::size_t length;
        std::size_t offset;
        bool without_response;
        int status;
        BLEDescriptor *descriptor = nullptr;
        BLEGattAuthorizationOperation authorization_operation =
            BLEGattAuthorizationOperation::read;
    };

    /** @brief BLEDevice.poll()에서만 호출되는 characteristic callback입니다. */
    using BLECharacteristicCallback = void (*)(BLECharacteristic &characteristic,
                                               const BLECharacteristicEventInfo &event,
                                               void *context);

    /**
     * @brief characteristic에 속하는 고정 value descriptor입니다.
     * @warning 등록한 객체와 caller-owned buffer는 image 수명 동안 유효해야 합니다.
     */
    class BLEDescriptor final
    {
      public:
        static constexpr std::size_t maximum_value_length = 512U;

        /** @brief 내부 고정 buffer를 사용하는 descriptor를 선언합니다. */
        BLEDescriptor(const BLEUuid &uuid, BLEPermission permissions,
                      std::size_t capacity = 20U) noexcept;

        /** @brief caller-owned 고정 buffer를 사용하는 descriptor를 선언합니다. */
        BLEDescriptor(const BLEUuid &uuid, BLEPermission permissions, std::uint8_t *buffer,
                      std::size_t capacity) noexcept;

        BLEDescriptor(const BLEDescriptor &) = delete;
        BLEDescriptor &operator=(const BLEDescriptor &) = delete;

        /** @brief descriptor UUID를 반환합니다. */
        [[nodiscard]] const BLEUuid &uuid() const noexcept;

        /** @brief descriptor permission bit를 반환합니다. */
        [[nodiscard]] BLEPermission permissions() const noexcept;

        /** @brief descriptor value 최대 길이를 반환합니다. */
        [[nodiscard]] std::size_t capacity() const noexcept;

        /** @brief descriptor value 현재 길이를 반환합니다. */
        [[nodiscard]] std::size_t valueLength() const noexcept;

        /** @brief descriptor value를 caller buffer로 복사하고 실제 길이를 반환합니다. */
        [[nodiscard]] std::size_t readValue(void *output, std::size_t capacity) const noexcept;

        /** @brief descriptor의 cached value를 갱신합니다. */
        [[nodiscard]] bool setValue(const void *data, std::size_t length) noexcept;

        /** @brief Bluetooth callback 문맥의 read/write authorization을 등록합니다. */
        void onAuthorize(BLEGattAuthorizationCallback callback,
                         void *context = nullptr) noexcept;

      private:
        friend struct internal::GattAccess;

        BLEUuid uuid_;
        BLEPermission permissions_ = BLEPermission::none;
        std::uint8_t *value_ = nullptr;
        std::size_t capacity_ = 0U;
        std::size_t value_length_ = 0U;
        std::uint8_t internal_value_[maximum_value_length] = {};
        BLEGattAuthorizationCallback authorization_callback_ = nullptr;
        void *authorization_context_ = nullptr;
        bool registered_ = false;
    };

    /**
     * @brief cached value와 고정 callback queue를 소유하는 GATT characteristic입니다.
     *
     * @warning 등록한 객체는 Bluetooth stack/image 수명보다 오래 유지되는 static 또는
     * global 객체여야 합니다. caller-owned buffer도 같은 수명을 가져야 하며, 등록 뒤에는
     * 직접 수정하지 말고 setValue()/readValue()로만 접근해야 합니다.
     */
    class BLECharacteristic final
    {
      public:
        static constexpr std::size_t maximum_value_length = 512U;
        static constexpr std::size_t maximum_descriptors = 4U;

        /** @brief 내부 고정 buffer를 사용하는 characteristic을 선언합니다. */
        BLECharacteristic(const BLEUuid &uuid, BLEProperty properties, BLEPermission permissions,
                          std::size_t capacity = 20U) noexcept;

        /**
         * @brief caller-owned 고정 buffer를 사용하는 characteristic을 선언합니다.
         * @warning buffer는 image 수명 동안 유효해야 하며 API 밖에서 직접 수정하면 안 됩니다.
         */
        BLECharacteristic(const BLEUuid &uuid, BLEProperty properties, BLEPermission permissions,
                          std::uint8_t *buffer, std::size_t capacity) noexcept;

        BLECharacteristic(const BLECharacteristic &) = delete;
        BLECharacteristic &operator=(const BLECharacteristic &) = delete;

        /** @brief characteristic UUID를 반환합니다. */
        [[nodiscard]] const BLEUuid &uuid() const noexcept;

        /** @brief characteristic property bit를 반환합니다. */
        [[nodiscard]] BLEProperty properties() const noexcept;

        /** @brief characteristic permission bit를 반환합니다. */
        [[nodiscard]] BLEPermission permissions() const noexcept;

        /** @brief cached value 최대 길이를 반환합니다. */
        [[nodiscard]] std::size_t capacity() const noexcept;

        /** @brief cached value 현재 길이를 반환합니다. */
        [[nodiscard]] std::size_t valueLength() const noexcept;

        /** @brief cached value를 caller buffer로 복사하고 실제 길이를 반환합니다. */
        [[nodiscard]] std::size_t readValue(void *output, std::size_t capacity) const noexcept;

        /** @brief server read 응답에 사용할 cached value를 갱신합니다. */
        [[nodiscard]] bool setValue(const void *data, std::size_t length) noexcept;

        /** @brief Bluetooth 시작 전 descriptor를 추가합니다. */
        [[nodiscard]] bool addDescriptor(BLEDescriptor &descriptor) noexcept;

        /** @brief 등록한 descriptor 수를 반환합니다. */
        [[nodiscard]] std::size_t descriptorCount() const noexcept;

        /** @brief 등록한 descriptor를 반환하며 범위를 벗어나면 nullptr입니다. */
        [[nodiscard]] BLEDescriptor *descriptor(std::size_t index) const noexcept;

        /** @brief Bluetooth callback 문맥의 read/write authorization을 등록합니다. */
        void onAuthorize(BLEGattAuthorizationCallback callback,
                         void *context = nullptr) noexcept;

        /** @brief 현재 peer가 notification CCC를 활성화했는지 반환합니다. */
        [[nodiscard]] bool notificationSubscribed() const noexcept;

        /** @brief 현재 peer가 indication CCC를 활성화했는지 반환합니다. */
        [[nodiscard]] bool indicationSubscribed() const noexcept;

        /** @brief cached value를 notification으로 전송합니다. */
        [[nodiscard]] bool notify() noexcept;

        /** @brief 지정 generation link로 cached value notification을 전송합니다. */
        [[nodiscard]] bool notify(BLEConnectionHandle connection) noexcept;

        /** @brief cached value를 confirmation이 있는 indication으로 전송합니다. */
        [[nodiscard]] bool indicate() noexcept;

        /** @brief 지정 generation link로 confirmation이 있는 indication을 전송합니다. */
        [[nodiscard]] bool indicate(BLEConnectionHandle connection) noexcept;

        /** @brief server write·CCC·전송 완료 callback을 등록합니다. */
        void onEvent(BLECharacteristicCallback callback, void *context = nullptr) noexcept;

      private:
        friend struct internal::GattAccess;

        BLEUuid uuid_;
        BLEProperty properties_ = BLEProperty::none;
        BLEPermission permissions_ = BLEPermission::none;
        std::uint8_t *value_ = nullptr;
        std::size_t capacity_ = 0U;
        std::size_t value_length_ = 0U;
        std::uint8_t internal_value_[maximum_value_length] = {};
        BLECharacteristicCallback callback_ = nullptr;
        void *callback_context_ = nullptr;
        BLEGattAuthorizationCallback authorization_callback_ = nullptr;
        void *authorization_context_ = nullptr;
        BLEDescriptor *descriptors_[maximum_descriptors] = {};
        std::size_t descriptor_count_ = 0U;
        bool registered_ = false;
    };

    /**
     * @brief Bluetooth 시작 전에 선언하는 primary GATT service입니다.
     * @warning 등록한 service와 characteristic 객체는 image 수명 동안 유효해야 합니다.
     */
    class BLEService final
    {
      public:
        static constexpr std::size_t maximum_characteristics = 8U;

        explicit BLEService(const BLEUuid &uuid) noexcept;
        BLEService(const BLEService &) = delete;
        BLEService &operator=(const BLEService &) = delete;

        /** @brief service UUID를 반환합니다. */
        [[nodiscard]] const BLEUuid &uuid() const noexcept;

        /** @brief Bluetooth 시작 전 characteristic을 추가합니다. */
        [[nodiscard]] bool addCharacteristic(BLECharacteristic &characteristic) noexcept;

        /** @brief 등록한 characteristic 수를 반환합니다. */
        [[nodiscard]] std::size_t characteristicCount() const noexcept;

      private:
        friend struct internal::GattAccess;

        BLEUuid uuid_;
        BLECharacteristic *characteristics_[maximum_characteristics] = {};
        std::size_t characteristic_count_ = 0U;
        bool registered_ = false;
    };

    /** @brief disconnect까지 유효한 discovered remote service handle입니다. */
    class BLERemoteService final
    {
      public:
        [[nodiscard]] bool valid() const noexcept;
        [[nodiscard]] const BLEUuid &uuid() const noexcept;
        [[nodiscard]] std::uint16_t startHandle() const noexcept;
        [[nodiscard]] std::uint16_t endHandle() const noexcept;

      private:
        friend struct internal::GattAccess;

        BLEUuid uuid_;
        std::uint16_t start_handle_ = 0U;
        std::uint16_t end_handle_ = 0U;
        bool valid_ = false;
    };

    /** @brief disconnect까지 유효한 discovered remote characteristic handle입니다. */
    class BLERemoteCharacteristic final
    {
      public:
        [[nodiscard]] bool valid() const noexcept;
        [[nodiscard]] const BLEUuid &uuid() const noexcept;
        [[nodiscard]] std::uint16_t valueHandle() const noexcept;
        [[nodiscard]] std::uint16_t cccHandle() const noexcept;
        [[nodiscard]] BLEProperty properties() const noexcept;

      private:
        friend struct internal::GattAccess;

        BLEUuid uuid_;
        std::uint16_t declaration_handle_ = 0U;
        std::uint16_t value_handle_ = 0U;
        std::uint16_t ccc_handle_ = 0U;
        BLEProperty properties_ = BLEProperty::none;
        bool valid_ = false;
    };

    /** @brief disconnect까지 유효한 discovered remote descriptor handle입니다. */
    class BLERemoteDescriptor final
    {
      public:
        [[nodiscard]] bool valid() const noexcept;
        [[nodiscard]] const BLEUuid &uuid() const noexcept;
        [[nodiscard]] std::uint16_t handle() const noexcept;

      private:
        friend struct internal::GattAccess;

        BLEUuid uuid_;
        std::uint16_t handle_ = 0U;
        bool valid_ = false;
    };

    /** @brief generic GATT client operation의 main-thread event입니다. */
    enum class BLEGattClientEvent : std::uint8_t
    {
        discovery_complete,
        read_complete,
        write_complete,
        write_without_response_complete,
        subscribed,
        unsubscribed,
        notification_received,
        indication_received,
        handles_invalidated,
        operation_failed,
        descriptor_discovery_complete,
        read_multiple_complete,
    };

    /** @brief GATT operation이 사용한 ATT bearer 종류입니다. */
    enum class BLEGattBearer : std::uint8_t
    {
        unenhanced,
        enhanced,
    };

    /** @brief client event의 link·오류·payload 상세 정보입니다. */
    struct BLEGattClientEventInfo
    {
        BLEGattClientEvent event = BLEGattClientEvent::operation_failed;
        BLEConnectionHandle connection;
        const std::uint8_t *data = nullptr;
        std::size_t length = 0U;
        std::size_t offset = 0U;
        std::uint8_t att_error = 0U;
        int status = 0;
        BLEGattBearer bearer = BLEGattBearer::unenhanced;
    };

    /** @brief BLEDevice.poll()에서만 호출되는 generic GATT client callback입니다. */
    using BLEGattClientCallback = void (*)(BLEGattClientEvent event, const std::uint8_t *data,
                                           std::size_t length, void *context);

    /** @brief BLEDevice.poll()에서만 호출되는 link 식별 가능 client callback입니다. */
    using BLEGattClientInfoCallback = void (*)(const BLEGattClientEventInfo &information,
                                               void *context);

    /** @brief 한 번에 한 service/characteristic operation을 수행하는 bounded GATT client입니다. */
    class GattClient final
    {
      public:
        /** @brief exact service와 characteristic UUID discovery를 시작합니다. */
        [[nodiscard]] bool discover(const BLEUuid &service_uuid,
                                    const BLEUuid &characteristic_uuid) noexcept;

        /** @brief 지정 link에서 exact service와 characteristic UUID discovery를 시작합니다. */
        [[nodiscard]] bool discover(BLEConnectionHandle connection, const BLEUuid &service_uuid,
                                    const BLEUuid &characteristic_uuid) noexcept;

        /** @brief remote service와 characteristic discovery가 완료됐는지 반환합니다. */
        [[nodiscard]] bool discovered() const noexcept;

        /** @brief 지정 link의 remote handle discovery가 완료됐는지 반환합니다. */
        [[nodiscard]] bool discovered(BLEConnectionHandle connection) const noexcept;

        /** @brief 현재 remote service handle의 동기화된 값 복사본을 반환합니다. */
        [[nodiscard]] BLERemoteService remoteService() const noexcept;

        /** @brief 지정 link의 remote service handle 복사본을 반환합니다. */
        [[nodiscard]] BLERemoteService remoteService(BLEConnectionHandle connection) const noexcept;

        /** @brief 현재 remote characteristic handle의 동기화된 값 복사본을 반환합니다. */
        [[nodiscard]] BLERemoteCharacteristic remoteCharacteristic() const noexcept;

        /** @brief 지정 link의 remote characteristic handle 복사본을 반환합니다. */
        [[nodiscard]] BLERemoteCharacteristic remoteCharacteristic(
            BLEConnectionHandle connection) const noexcept;

        /** @brief 현재 characteristic 뒤에서 exact descriptor UUID discovery를 시작합니다. */
        [[nodiscard]] bool discoverDescriptor(const BLEUuid &descriptor_uuid) noexcept;

        /** @brief 지정 link에서 exact descriptor UUID discovery를 시작합니다. */
        [[nodiscard]] bool discoverDescriptor(BLEConnectionHandle connection,
                                              const BLEUuid &descriptor_uuid) noexcept;

        /** @brief 현재 link에 저장한 remote descriptor 수를 반환합니다. */
        [[nodiscard]] std::size_t descriptorCount() const noexcept;

        /** @brief 지정 link에 저장한 remote descriptor 수를 반환합니다. */
        [[nodiscard]] std::size_t descriptorCount(BLEConnectionHandle connection) const noexcept;

        /** @brief 현재 link의 remote descriptor 복사본을 반환합니다. */
        [[nodiscard]] BLERemoteDescriptor remoteDescriptor(std::size_t index) const noexcept;

        /** @brief 지정 link의 remote descriptor 복사본을 반환합니다. */
        [[nodiscard]] BLERemoteDescriptor remoteDescriptor(BLEConnectionHandle connection,
                                                           std::size_t index) const noexcept;

        /** @brief remote cached value의 단일 bounded read를 시작합니다. */
        [[nodiscard]] bool read() noexcept;

        /** @brief 지정 link에서 최대 512 byte long read를 시작합니다. */
        [[nodiscard]] bool read(BLEConnectionHandle connection) noexcept;

        /** @brief 현재 link에서 최대 4개 attribute를 한 번에 읽습니다. */
        [[nodiscard]] bool readMultiple(const std::uint16_t *handles,
                                        std::size_t count) noexcept;

        /** @brief 지정 link에서 최대 4개 attribute를 한 번에 읽습니다. */
        [[nodiscard]] bool readMultiple(BLEConnectionHandle connection,
                                        const std::uint16_t *handles,
                                        std::size_t count) noexcept;

        /** @brief response가 있는 최대 512 byte long/reliable write를 시작합니다. */
        [[nodiscard]] bool write(const void *data, std::size_t length) noexcept;

        /** @brief 지정 link에서 최대 512 byte long/reliable write를 시작합니다. */
        [[nodiscard]] bool write(BLEConnectionHandle connection, const void *data,
                                 std::size_t length) noexcept;

        /** @brief response 없는 bounded write와 local TX 완료를 시작합니다. */
        [[nodiscard]] bool writeWithoutResponse(const void *data, std::size_t length) noexcept;

        /** @brief 지정 link에서 response 없는 bounded write를 시작합니다. */
        [[nodiscard]] bool writeWithoutResponse(BLEConnectionHandle connection, const void *data,
                                                std::size_t length) noexcept;

        /** @brief remote CCC notification 구독을 시작합니다. */
        [[nodiscard]] bool subscribeNotifications() noexcept;

        /** @brief 지정 link의 remote CCC notification 구독을 시작합니다. */
        [[nodiscard]] bool subscribeNotifications(BLEConnectionHandle connection) noexcept;

        /** @brief remote CCC indication 구독을 시작합니다. */
        [[nodiscard]] bool subscribeIndications() noexcept;

        /** @brief 지정 link의 remote CCC indication 구독을 시작합니다. */
        [[nodiscard]] bool subscribeIndications(BLEConnectionHandle connection) noexcept;

        /** @brief 현재 remote CCC 구독 해제를 시작합니다. */
        [[nodiscard]] bool unsubscribe() noexcept;

        /** @brief 지정 link의 현재 remote CCC 구독 해제를 시작합니다. */
        [[nodiscard]] bool unsubscribe(BLEConnectionHandle connection) noexcept;

        /** @brief 비동기 client operation이 진행 중인지 반환합니다. */
        [[nodiscard]] bool busy() const noexcept;

        /** @brief 지정 link에서 비동기 operation이 진행 중인지 반환합니다. */
        [[nodiscard]] bool busy(BLEConnectionHandle connection) const noexcept;

        /** @brief 마지막 remote ATT 오류 byte를 반환합니다. */
        [[nodiscard]] std::uint8_t lastAttError() const noexcept;

        /** @brief 지정 link의 마지막 remote ATT 오류 byte를 반환합니다. */
        [[nodiscard]] std::uint8_t lastAttError(BLEConnectionHandle connection) const noexcept;

        /** @brief main-thread generic client callback을 등록합니다. */
        void onEvent(BLEGattClientCallback callback, void *context = nullptr) noexcept;

        /** @brief link 식별 가능 main-thread client callback을 등록합니다. */
        void onDetailedEvent(BLEGattClientInfoCallback callback,
                             void *context = nullptr) noexcept;
    };

} // namespace nucode::ble

/** @brief NU54DK의 단일 bounded generic GATT client 객체입니다. */
extern nucode::ble::GattClient BLEClient;

#endif
