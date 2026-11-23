/** @file @brief Apple ANCS·AMS의 보안 연결과 사용자 데이터 API입니다.
 * SPDX-License-Identifier: MIT
 */
#pragma once
#include <NUCODE_BLE.h>
#include "NUCODE_BLE_CompanionCodec.h"

namespace nucode::ble::companion
{
    /** @brief 한 image에서 선택할 Apple service입니다. */
    enum class Service : uint8_t
    {
        notifications,
        media
    };
    /** @brief main thread에서 전달하는 event 종류입니다. */
    enum class Event : uint8_t
    {
        ready,
        notification,
        attribute,
        media_update,
        supported_commands,
        command_complete,
        disconnected,
        error
    };
    /** @brief callback 동안만 유효한 bounded event 데이터입니다. */
    struct EventInfo
    {
        Event event = Event::error;
        Error error = Error::none;
        int native_code = 0;
        Notification notification;
        uint8_t entity = 0;
        uint8_t attribute = 0;
        bool truncated = false;
        const uint8_t *data = nullptr;
        size_t length = 0;
        uint16_t command_mask = 0;
    };
    using Callback = void (*)(const EventInfo &event, void *context);

    /**
     * @brief 한 보안 link의 ANCS/AMS discovery·subscription·요청을 소유합니다.
     * @warning 객체는 static 수명이어야 합니다. BLEClient와 동시 discovery를 하지 않습니다.
     * 모든 메서드는 Sketch main thread에서 호출하고 poll()을 10ms 이내 간격으로 실행합니다.
     */
    class AppleClient final
    {
      public:
        AppleClient() = default;
        AppleClient(const AppleClient &) = delete;
        AppleClient &operator=(const AppleClient &) = delete;
        /** @brief Core가 발급한 link에 결합하고 L2 보안·service discovery를 시작합니다. */
        Error begin(BLEConnectionHandle connection, Service service) noexcept;
        /** @brief 알림 처리와 15초 discovery/5초 요청 timeout을 진행합니다. */
        void poll() noexcept;
        /** @brief 진행 중인 link를 disconnect하고 구독과 민감 buffer를 정리합니다. */
        void end() noexcept;
        bool ready() const noexcept;
        void onEvent(Callback callback, void *context = nullptr) noexcept;
        /** @brief 알림 UID의 단일 attribute를 요청합니다. 0..7, text 상한 128 byte입니다. */
        Error requestAttribute(uint32_t uid, uint8_t attribute) noexcept;
        /** @brief 사용자가 선택한 알림에만 positive/negative action을 전송합니다. */
        Error performAction(const Notification &notification, bool positive) noexcept;
        /** @brief AMS entity의 attribute 목록을 구독합니다. 빈 목록은 해당 entity 해제입니다. */
        Error selectMediaAttributes(uint8_t entity, const uint8_t *attributes,
                                    size_t count) noexcept;
        /** @brief peer가 허용했다고 통지한 AMS command(0..13)만 전송합니다. */
        Error sendMediaCommand(uint8_t command) noexcept;
        /** @brief truncated AMS attribute를 선택한 뒤 실제 GATT long read합니다. */
        Error readMediaAttribute(uint8_t entity, uint8_t attribute) noexcept;
        /** @brief Apple service solicitation UUID로 legacy connectable advertising을 시작합니다. */
        static Error advertise(Service service, const char *name) noexcept;
        static void stopAdvertising() noexcept;

      private:
        Callback callback_ = nullptr;
        void *context_ = nullptr;
    };
} // namespace nucode::ble::companion
