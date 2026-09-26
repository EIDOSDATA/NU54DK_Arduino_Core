/**
 * @file NUCODE_BLE_L2CAP.h
 * @brief 고정 자원 Bluetooth LE Credit Based Channel Arduino API를 선언합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#ifndef NUCODE_BLE_L2CAP_H_
#define NUCODE_BLE_L2CAP_H_

#include <NUCODE_BLE_GAP.h>

#include <cstddef>
#include <cstdint>

namespace nucode::ble
{

    namespace internal
    {
        struct BLEL2capChannelHandleAccess;
    }

    /** @brief channel slot 재사용을 generation으로 구분하는 불투명 LE CoC handle입니다. */
    class BLEL2capChannelHandle final
    {
      public:
        BLEL2capChannelHandle() = default;

        /** @brief handle이 비영 token을 보유하는지 반환합니다. */
        [[nodiscard]] constexpr bool valid() const noexcept
        {
            return token_ != 0U;
        }

        [[nodiscard]] constexpr bool operator==(const BLEL2capChannelHandle &other) const noexcept
        {
            return token_ == other.token_;
        }

        [[nodiscard]] constexpr bool operator!=(const BLEL2capChannelHandle &other) const noexcept
        {
            return !(*this == other);
        }

      private:
        explicit constexpr BLEL2capChannelHandle(std::uint64_t token) noexcept : token_(token)
        {
        }

        std::uint64_t token_ = 0U;
        friend struct internal::BLEL2capChannelHandleAccess;
    };

    /** @brief BLEDevice.poll()에서 전달하는 LE CoC 상태 변화입니다. */
    enum class BLEL2capEvent : std::uint8_t
    {
        connected,
        disconnected,
        received,
        sent,
        reconfigured,
    };

    /** @brief callback 밖 stack 객체를 노출하지 않는 LE CoC event 복사본입니다. */
    struct BLEL2capEventInfo
    {
        BLEL2capEvent event = BLEL2capEvent::disconnected;
        BLEL2capChannelHandle channel;
        BLEConnectionHandle connection;
        const std::uint8_t *data = nullptr;
        std::size_t length = 0U;
        std::uint16_t local_mtu = 0U;
        std::uint16_t remote_mtu = 0U;
        int status = 0;
    };

    /** @brief BLEDevice.poll() 문맥에서만 호출되는 LE CoC callback입니다. */
    using BLEL2capEventCallback = void (*)(const BLEL2capEventInfo &information, void *context);

    /** @brief image 수명 동안 누적하는 고정 자원 LE CoC 진단값입니다. */
    struct BLEL2capStatistics
    {
        std::uint32_t accepted = 0U;
        std::uint32_t connected = 0U;
        std::uint32_t disconnected = 0U;
        std::uint32_t received = 0U;
        std::uint32_t sent = 0U;
        std::uint32_t backpressure = 0U;
        std::uint32_t rejected = 0U;
        std::uint32_t dropped_events = 0U;
    };

    /** @brief server 1개와 generation 기반 channel 2개를 소유하는 LE CoC facade입니다. */
    class L2capCoc final
    {
      public:
        static constexpr std::size_t maximum_channels = 2U;
        static constexpr std::size_t maximum_sdu_length = 512U;
        static constexpr std::size_t receive_records_per_channel = 4U;
        static constexpr std::size_t transmit_buffers = 4U;

        /**
         * @brief LE CoC server를 한 번 등록하고 현재 Device session에서 accept를 허용합니다.
         * @param psm 0이면 stack이 0x0080~0x00ff 범위에서 동적으로 할당합니다.
         */
        [[nodiscard]] bool startServer(std::uint16_t psm = 0U) noexcept;

        /** @brief 실제 등록된 server PSM을 반환하며 미등록이면 0을 반환합니다. */
        [[nodiscard]] std::uint16_t serverPsm() const noexcept;

        /** @brief 지정 BLE link와 동적 PSM에 새 channel 연결을 시작합니다. */
        [[nodiscard]] bool connect(BLEConnectionHandle connection, std::uint16_t psm,
                                   BLEL2capChannelHandle &channel) noexcept;

        /** @brief 최대 512-byte SDU를 고정 TX pool에서 비동기로 전송합니다. */
        [[nodiscard]] bool send(BLEL2capChannelHandle channel, const void *data,
                                std::size_t length) noexcept;

        /** @brief 연결 또는 연결 중인 지정 generation channel을 비동기로 종료합니다. */
        [[nodiscard]] bool disconnect(BLEL2capChannelHandle channel) noexcept;

        /** @brief 지정 generation channel이 현재 전송 가능한 연결 상태인지 반환합니다. */
        [[nodiscard]] bool connected(BLEL2capChannelHandle channel) const noexcept;

        /** @brief stack이 아직 소유하지 않은 전체 고정 TX buffer 수를 반환합니다. */
        [[nodiscard]] std::size_t availableForWrite() const noexcept;

        /** @brief image 수명 누적 진단값의 일관된 복사본을 반환합니다. */
        [[nodiscard]] BLEL2capStatistics statistics() const noexcept;

        /** @brief main-thread LE CoC callback과 caller-owned 문맥을 등록합니다. */
        void onEvent(BLEL2capEventCallback callback, void *context = nullptr) noexcept;
    };

} // namespace nucode::ble

/** @brief NU54DK의 단일 고정 자원 LE CoC facade입니다. */
extern nucode::ble::L2capCoc BLEL2cap;

#endif
