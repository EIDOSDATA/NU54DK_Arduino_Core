/** @file @brief Apple companion protocol의 고정 크기 wire codec입니다.
 * SPDX-License-Identifier: MIT
 */
#pragma once
#include <stddef.h>
#include <stdint.h>

namespace nucode::ble::companion
{
    /** @brief wire 검증과 비동기 세션의 오류입니다. */
    enum class Error : uint8_t
    {
        none,
        invalid_argument,
        malformed,
        overflow,
        not_ready,
        busy,
        unsupported,
        security,
        timeout,
        transport,
        stale_session
    };

    /** @brief ANCS notification source의 정확히 8 byte인 event입니다. */
    struct Notification
    {
        uint32_t uid = 0;
        uint8_t event = 0;
        uint8_t flags = 0;
        uint8_t category = 0;
        uint8_t count = 0;
    };

    /** @brief AMS entity·attribute·UTF-8 byte view이며 입력 수명 동안만 유효합니다. */
    struct MediaUpdate
    {
        uint8_t entity = 0;
        uint8_t attribute = 0;
        bool truncated = false;
        const uint8_t *text = nullptr;
        size_t length = 0;
    };

    /** @brief ANCS 8-byte event의 reserved/category/event 범위를 검사합니다. */
    Error decodeNotification(const uint8_t *data, size_t size, Notification &output) noexcept;
    /** @brief AMS entity update를 검증하며 UTF-8 내용을 실행하거나 포맷 문자열로 쓰지 않습니다. */
    Error decodeMediaUpdate(const uint8_t *data, size_t size, MediaUpdate &output) noexcept;
    /** @brief peer가 허용한 remote command를 bit mask로 변환합니다. */
    Error decodeMediaCommands(const uint8_t *data, size_t size, uint16_t &mask) noexcept;
    /** @brief 단일 ANCS attribute 요청을 생성합니다. 출력은 8 byte 이상이어야 합니다. */
    Error encodeAttributeRequest(uint32_t uid, uint8_t attribute, uint16_t maximum, uint8_t *output,
                                 size_t capacity, size_t &length) noexcept;
    /** @brief action flag를 확인한 뒤 ANCS 사용자 동작 명령을 만듭니다. */
    Error encodeNotificationAction(const Notification &notification, bool positive, uint8_t *output,
                                   size_t capacity) noexcept;
    /** @brief AMS entity에 유효한 attribute인지 검사합니다. */
    bool validMediaAttribute(uint8_t entity, uint8_t attribute) noexcept;

    /** @brief 한 ANCS 요청의 분할 응답을 UID·attribute와 대조하며 128 byte까지 모읍니다. */
    class AttributeAssembler final
    {
      public:
        static constexpr size_t maximum_text = 128;
        /** @brief 새 요청을 시작하고 이전 세션의 조각을 폐기합니다. */
        Error begin(uint32_t uid, uint8_t attribute) noexcept;
        /** @brief 다음 fragment를 수용합니다. 완성 뒤 추가 byte는 malformed입니다. */
        Error feed(const uint8_t *data, size_t size) noexcept;
        /** @brief 응답 수신 상태와 민감한 text buffer를 초기화합니다. */
        void reset() noexcept;
        bool complete() const noexcept;
        const uint8_t *text() const noexcept;
        size_t length() const noexcept;

      private:
        uint8_t buffer_[maximum_text + 8] = {};
        size_t used_ = 0;
        size_t expected_ = 0;
        uint32_t uid_ = 0;
        uint8_t attribute_ = 0;
        bool active_ = false;
    };
} // namespace nucode::ble::companion
