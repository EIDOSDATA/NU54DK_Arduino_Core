/**
 * @file NUCODE_BLE_Profiles.h
 * @brief 사용자 값을 보존하는 표준 GATT 서비스 facade입니다.
 * SPDX-License-Identifier: MIT
 */
#ifndef NUCODE_BLE_PROFILES_H_
#define NUCODE_BLE_PROFILES_H_

#include <NUCODE_BLE.h>
#include <NUCODE_BLE_ProfileCodec.h>
#include <NUCODE_BLE_Security.h>

namespace nucode::ble::profiles
{
    /**
     * @brief CTS/HTS/CSC/RSCS/ETS의 최소 mandatory 구성을 등록합니다.
     * @note CSC는 crank-only, RSCS는 speed/cadence/running/stride를 제공합니다.
     * 선택적 wheel·누적 거리·writable clock은 이 facade에서 광고하지 않습니다.
     * 객체는 image 수명의 static/global이어야 하며 begin은 BLEDevice.begin 전에 호출합니다.
     */
    class SensorService final
    {
      public:
        explicit SensorService(Kind kind) noexcept;
        [[nodiscard]] bool begin() noexcept;
        /** @brief codec 검증 뒤 cached 값만 갱신합니다. 자연 시간 경과는 notify하지 않습니다. */
        [[nodiscard]] bool setValue(const Packet &packet) noexcept;
        /** @brief 현재 값을 지정한 generation link에 notify/indicate합니다. */
        [[nodiscard]] bool send(BLEConnectionHandle peer) noexcept;
        [[nodiscard]] Kind kind() const noexcept;
        [[nodiscard]] BLECharacteristic &measurement() noexcept;

      private:
        Kind kind_;
        BLEService service_;
        BLECharacteristic measurement_;
        BLECharacteristic feature_;
        bool ready_ = false;
    };

    /** @brief ANS 두 link의 control 상태와 마지막 category별 값을 고정 저장합니다. */
    class AlertService final
    {
      public:
        AlertService() noexcept;
        [[nodiscard]] bool begin() noexcept;
        /** @brief 마지막 알림을 저장하고 허용된 지정 link에 전달합니다. */
        [[nodiscard]] bool send(BLEConnectionHandle peer, const Alert &value) noexcept;
        [[nodiscard]] bool unread(BLEConnectionHandle peer, std::uint8_t category,
                                  std::uint8_t count) noexcept;
        /** @brief disconnect 시 generation 상태를 제거하고 immediate 요청을 처리합니다. */
        void poll() noexcept;

      private:
        struct Link
        {
            BLEConnectionHandle handle;
            AlertControl control;
        };
        static bool authorize(const BLEGattAuthorizationRequest &request, void *context) noexcept;
        static void event(BLECharacteristic &value, const BLECharacteristicEventInfo &event,
                          void *context) noexcept;
        Link *link(BLEConnectionHandle peer, bool create) noexcept;
        BLEService service_;
        BLECharacteristic supported_new_;
        BLECharacteristic new_alert_;
        BLECharacteristic supported_unread_;
        BLECharacteristic unread_;
        BLECharacteristic control_;
        Link links_[2] = {};
        Alert latest_[10] = {};
        std::uint8_t unread_count_[10] = {};
        bool have_alert_[10] = {};
        bool ready_ = false;
    };

    /** @brief 암호화·bond와 application 허가를 모두 요구하는 BMS 삭제 요청입니다. */
    struct BondDeleteRequest
    {
        BLEConnectionHandle peer;
        const std::uint8_t *authorization_code = nullptr;
        std::size_t length = 0U;
    };
    /** @brief Bluetooth callback 문맥에서 짧고 non-blocking하게 판정해야 합니다. */
    using BondDeleteAuthorization = bool (*)(const BondDeleteRequest &request, void *context);

    /**
     * @brief requesting LE peer 하나의 bond 삭제만 제공하는 BMS입니다.
     * @warning 전체 bond 삭제 opcode는 광고하거나 수락하지 않습니다. callback은 기본 거부입니다.
     */
    class BondManagementService final
    {
      public:
        BondManagementService() noexcept;
        [[nodiscard]] bool begin(BondDeleteAuthorization authorize,
                                 void *context = nullptr) noexcept;
        /** @brief 다음 한 건의 삭제 요청을 허가하거나 취소합니다. 초기 상태는 취소입니다. */
        void setArmed(bool armed) noexcept;
        [[nodiscard]] bool armed() const noexcept;
        [[nodiscard]] std::uint32_t acceptedCount() const noexcept;
        [[nodiscard]] std::uint32_t failureCount() const noexcept;

      private:
        static bool authorize(const BLEGattAuthorizationRequest &request, void *context) noexcept;
        static void event(BLECharacteristic &value, const BLECharacteristicEventInfo &event,
                          void *context) noexcept;
        BLEService service_;
        BLECharacteristic feature_;
        BLECharacteristic control_;
        BondDeleteAuthorization authorize_ = nullptr;
        void *context_ = nullptr;
        std::uint32_t accepted_ = 0U;
        std::uint32_t failed_ = 0U;
        bool ready_ = false;
        bool armed_ = false;
    };
} // namespace nucode::ble::profiles
#endif
