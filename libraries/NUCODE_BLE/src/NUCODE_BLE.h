/**
 * @file NUCODE_BLE.h
 * @brief NCS Nordic UART Service를 Arduino Stream으로 노출합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#ifndef NUCODE_BLE_H_
#define NUCODE_BLE_H_

#include <Arduino.h>
#include <NUCODE_BLE_GAP.h>
#include <NUCODE_BLE_GATT.h>

#include <cstddef>
#include <cstdint>

namespace nucode::ble
{

    /** @brief BLE NUS 객체가 전달하는 사용자 문맥 event입니다. */
    enum class Event : std::uint8_t
    {
        advertising_started,
        scan_started,
        connected,
        ready,
        disconnected,
        received,
        error,
    };

    /** @brief 마지막 BLE NUS 동작의 공개 오류 분류입니다. */
    enum class Error : std::uint8_t
    {
        none,
        invalid_argument,
        invalid_context,
        already_started,
        not_started,
        wrong_role,
        not_connected,
        not_ready,
        busy,
        rx_overflow,
        event_overflow,
        timeout,
        driver_error,
    };

    /** @brief Sketch의 poll 문맥에서만 호출되는 event callback입니다. */
    using EventCallback = void (*)(Event event, void *context);

    /**
     * @brief Nordic UART Service Peripheral/Central을 제공하는 단일 Stream facade입니다.
     *
     * NCS callback은 사용자 함수를 직접 호출하지 않습니다. 수신 byte와 event는 고정
     * Zephyr queue에 복사되고 Sketch가 poll()을 호출할 때 callback으로 전달됩니다.
     */
    class NusSerial final : public Stream
    {
      public:
        NusSerial() = default;
        NusSerial(const NusSerial &) = delete;
        NusSerial &operator=(const NusSerial &) = delete;

        /** @brief NUS Peripheral 역할과 local name을 준비합니다. */
        [[nodiscard]] bool beginPeripheral(const char *local_name) noexcept;

        /** @brief 준비한 Peripheral의 connectable advertising을 시작합니다. */
        [[nodiscard]] bool startAdvertising() noexcept;

        /** @brief NUS Central 역할을 준비합니다. */
        [[nodiscard]] bool beginCentral() noexcept;

        /** @brief 완전히 일치하는 local name을 검색하고 NUS peer에 자동 연결합니다. */
        [[nodiscard]] bool scanForNus(const char *exact_name) noexcept;

        /** @brief queued event와 재광고·재검색 상태기를 Arduino main 문맥에서 진행합니다. */
        void poll() noexcept;

        /** @brief 현재 BLE link가 연결되어 있는지 반환합니다. */
        [[nodiscard]] bool connected() const noexcept;

        /** @brief NUS notify/write 경로가 실제 전송 가능한지 반환합니다. */
        [[nodiscard]] bool ready() const noexcept;

        /** @brief 현재 peer 연결을 비동기로 종료합니다. */
        [[nodiscard]] bool disconnect() noexcept;

        /** @brief 광고·검색·연결과 자동 재시작을 중지합니다. */
        void end() noexcept;

        /** @brief 사용자 event callback과 caller-owned context를 등록합니다. */
        void onEvent(EventCallback callback, void *context = nullptr) noexcept;

        /** @brief 현재 연결의 NUS payload 최대 길이를 반환합니다. */
        [[nodiscard]] std::size_t mtu() const noexcept;

        /** @brief 고정 RX queue가 가득 차 버린 누적 byte 수를 반환합니다. */
        [[nodiscard]] std::uint32_t droppedRxBytes() const noexcept;

        /** @brief 마지막 공개 오류를 반환합니다. */
        [[nodiscard]] Error lastError() const noexcept;

        /** @brief 마지막 Zephyr/NCS 음수 오류를 반환합니다. */
        [[nodiscard]] int lastDriverError() const noexcept;

        int available() override;
        int read() override;
        int peek() override;
        void flush() override;
        int availableForWrite() override;
        std::size_t write(std::uint8_t value) override;
        std::size_t write(const std::uint8_t *buffer, std::size_t size) override;

        using Print::write;
    };

} // namespace nucode::ble

/** @brief NU54DK의 단일 NUS Stream 객체입니다. */
extern nucode::ble::NusSerial BLESerial;

#endif
