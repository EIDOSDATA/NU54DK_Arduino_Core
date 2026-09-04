/**
 * @file SerialFabric.h
 * @brief nRF54L15 공유 serial block을 안전하게 선택하는 v0.4 후보 API입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#ifndef NUCODE_ARDUINO_CORE_NUCODE_SERIAL_FABRIC_H_
#define NUCODE_ARDUINO_CORE_NUCODE_SERIAL_FABRIC_H_

#include <api/Common.h>

#include <cstddef>
#include <cstdint>

namespace nucode::arduino
{
    /** @brief 한 serial block에서 선택할 hardware personality입니다. */
    enum class SerialPersonality : std::uint8_t
    {
        uarte = 0U,
        spim,
        spis,
        twim,
        twis,
    };

    /** @brief NU54DK가 승인한 serial pin bank입니다. */
    enum class SerialRouteClass : std::uint8_t
    {
        p2_dedicated20 = 0U,
        p1_flexible,
        p0_flexible,
    };

    /** @brief 회로 경로의 전기적 전제조건을 명시합니다. */
    enum class SerialElectricalProfile : std::uint8_t
    {
        connector_fixture = 0U,
        dap_uart_bridge,
        dap_uart_disabled,
        pmic_read_only,
    };

    /** @brief personality route의 신호 이름입니다. */
    enum class SerialSignal : std::uint8_t
    {
        invalid = 0U,
        txd,
        rxd,
        rts,
        cts,
        sck,
        mosi,
        miso,
        csn,
        dcx,
        sda,
        scl,
    };

    /** @brief public lifecycle 상태입니다. */
    enum class SerialFabricState : std::uint8_t
    {
        inactive = 0U,
        staged,
        activating,
        active,
        cancelling,
        faulted,
    };

    /** @brief EasyDMA buffer의 소유권 상태입니다. */
    enum class DmaBufferState : std::uint8_t
    {
        application_owned = 0U,
        queued,
        dma_owned,
        completed,
        cancelled,
        error,
    };

    /** @brief serial-fabric 연산의 안정된 결과입니다. */
    enum class SerialFabricResult : std::uint8_t
    {
        success = 0U,
        invalid_context,
        invalid_argument,
        unsupported_instance,
        unsupported_route,
        unsafe_electrical_profile,
        driver_unavailable,
        wrong_state,
        ownership_conflict,
        resource_exhausted,
        driver_error,
        stop_timeout,
        release_failed,
        faulted,
    };

    /** @brief UARTE parity 선택입니다. */
    enum class UarteParity : std::uint8_t
    {
        none = 0U,
        even,
    };

    /** @brief UARTE async event 종류입니다. ISR 밖에서 poll합니다. */
    enum class UarteEventType : std::uint8_t
    {
        tx_complete = 0U,
        tx_cancelled,
        rx_complete,
        rx_cancelled,
        rx_buffer_needed,
        error,
    };

    /** @brief UARTE 설정입니다. 기본값은 115200 8N1, flow control off입니다. */
    struct UarteConfiguration
    {
        std::uint32_t baud_rate{115200U};
        UarteParity parity{UarteParity::none};
        bool hardware_flow_control{false};
        /** Use ENDRX→STARTRX for two >=32-byte buffers. The application must
         * keep IRQ latency below one buffer duration; this is not an unbounded
         * receive queue. Short buffers use the default interrupt-linked mode. */
        bool continuous_receive{false};
    };

    /** @brief 완료 queue에서 읽는 UARTE async event입니다. */
    struct UarteEvent
    {
        UarteEventType type{UarteEventType::error};
        const void *buffer{nullptr};
        std::size_t transferred{0U};
        std::uint32_t error_mask{0U};
    };

    /** @brief SPI clock phase/polarity mode입니다. */
    enum class SpiFabricMode : std::uint8_t
    {
        mode0 = 0U,
        mode1,
        mode2,
        mode3,
    };

    /** @brief SPI wire bit order입니다. */
    enum class SpiFabricBitOrder : std::uint8_t
    {
        msb_first = 0U,
        lsb_first,
    };

    /** @brief SPIM/SPIS 공통 설정입니다. SPIS에서는 frequency를 무시합니다. */
    struct SpiFabricConfiguration
    {
        std::uint32_t frequency{4000000U};
        SpiFabricMode mode{SpiFabricMode::mode0};
        SpiFabricBitOrder bit_order{SpiFabricBitOrder::msb_first};
        std::uint8_t overrun_character{0xFFU};
    };

    /** @brief SPI EasyDMA 완료 queue의 event 종류입니다. */
    enum class SpiFabricEventType : std::uint8_t
    {
        transfer_complete = 0U,
        transfer_cancelled,
        buffers_armed,
        buffer_needed,
        error,
    };

    /** @brief SPI controller/peripheral의 비동기 완료 정보입니다. */
    struct SpiFabricEvent
    {
        SpiFabricEventType type{SpiFabricEventType::error};
        const void *tx_buffer{nullptr};
        void *rx_buffer{nullptr};
        std::size_t tx_transferred{0U};
        std::size_t rx_transferred{0U};
        std::uint32_t error_code{0U};
    };

    /** @brief TWIM controller bus speed입니다. */
    enum class TwiFabricFrequency : std::uint32_t
    {
        standard = 100000U,
        fast = 400000U,
        fast_plus = 1000000U,
    };

    /** @brief TWIM controller 설정입니다. */
    struct TwimConfiguration
    {
        TwiFabricFrequency frequency{TwiFabricFrequency::standard};
    };

    /** @brief TWIS target 주소와 pin pull 설정입니다. */
    struct TwisConfiguration
    {
        std::uint8_t primary_address{0x42U};
        std::uint8_t secondary_address{0U};
        bool internal_pullups{false};
    };

    /** @brief TWI EasyDMA event 종류입니다. */
    enum class TwiFabricEventType : std::uint8_t
    {
        transfer_complete = 0U,
        address_nack,
        data_nack,
        overrun,
        bus_error,
        read_request,
        read_complete,
        write_request,
        write_complete,
        buffer_needed,
        transfer_cancelled,
        error,
    };

    /** @brief TWIM/TWIS 비동기 완료와 오류 정보입니다. */
    struct TwiFabricEvent
    {
        TwiFabricEventType type{TwiFabricEventType::error};
        std::uint8_t address{0U};
        const void *tx_buffer{nullptr};
        void *rx_buffer{nullptr};
        std::size_t tx_transferred{0U};
        std::size_t rx_transferred{0U};
        std::uint32_t error_code{0U};
    };

    /** @brief 한 signal과 Arduino canonical pin을 연결합니다. */
    struct SerialSignalPin
    {
        SerialSignal signal{SerialSignal::invalid};
        pin_size_t pin{0U};
    };

    /** @brief activate와 함께 lease할 application RAM 범위입니다. */
    struct SerialDmaWorkspace
    {
        void *address{nullptr};
        std::size_t size{0U};
    };

    /** @brief allocation 없이 stage되는 완전한 route·DMA 설정입니다. */
    struct SerialFabricConfiguration
    {
        SerialRouteClass route{SerialRouteClass::p1_flexible};
        SerialElectricalProfile electrical_profile{SerialElectricalProfile::connector_fixture};
        const SerialSignalPin *pins{nullptr};
        std::size_t pin_count{0U};
        const SerialDmaWorkspace *dma_workspaces{nullptr};
        std::size_t dma_workspace_count{0U};
    };

    class SerialFabric;

    /** @brief 모든 typed handle이 공유하는 lifecycle 조회·제어 표면입니다. */
    class SerialFabricHandle
    {
      public:
        [[nodiscard]] SerialPersonality personality() const noexcept;
        [[nodiscard]] std::uint8_t instance() const noexcept;
        [[nodiscard]] SerialFabricState state() const noexcept;
        [[nodiscard]] SerialFabricResult lastResult() const noexcept;
        [[nodiscard]] int lastDriverError() const noexcept;

        [[nodiscard]] SerialFabricResult
        stage(const SerialFabricConfiguration &configuration) noexcept;
        [[nodiscard]] SerialFabricResult activate() noexcept;
        [[nodiscard]] SerialFabricResult deactivate(std::uint32_t timeout_us = 100000U) noexcept;

      protected:
        constexpr SerialFabricHandle(SerialPersonality personality, std::uint8_t instance,
                                     std::uint8_t handle_index) noexcept
            : personality_(personality), instance_(instance), handle_index_(handle_index)
        {
        }

      private:
        SerialPersonality personality_;
        std::uint8_t instance_;
        std::uint8_t handle_index_;
    };

    class UarteHandle final : public SerialFabricHandle
    {
        friend class SerialFabric;

      public:
        [[nodiscard]] SerialFabricResult
        configure(const UarteConfiguration &configuration) noexcept;
        [[nodiscard]] SerialFabricResult transmitAsync(const void *buffer,
                                                       std::size_t size) noexcept;
        [[nodiscard]] SerialFabricResult receiveAsync(void *first_buffer, std::size_t first_size,
                                                      void *second_buffer = nullptr,
                                                      std::size_t second_size = 0U) noexcept;
        [[nodiscard]] SerialFabricResult cancelTransmit() noexcept;
        [[nodiscard]] SerialFabricResult cancelReceive() noexcept;
        [[nodiscard]] bool takeEvent(UarteEvent &event) noexcept;
        [[nodiscard]] DmaBufferState bufferState(const void *buffer) const noexcept;

      private:
        constexpr UarteHandle(std::uint8_t instance, std::uint8_t index) noexcept
            : SerialFabricHandle(SerialPersonality::uarte, instance, index)
        {
        }
    };

    class SpimHandle final : public SerialFabricHandle
    {
        friend class SerialFabric;

      public:
        [[nodiscard]] SerialFabricResult
        configure(const SpiFabricConfiguration &configuration) noexcept;
        [[nodiscard]] SerialFabricResult transferAsync(const void *tx_buffer, std::size_t tx_size,
                                                       void *rx_buffer,
                                                       std::size_t rx_size) noexcept;
        [[nodiscard]] SerialFabricResult transfer(const void *tx_buffer, std::size_t tx_size,
                                                  void *rx_buffer, std::size_t rx_size,
                                                  std::uint32_t timeout_us = 100000U) noexcept;
        [[nodiscard]] SerialFabricResult cancelTransfer() noexcept;
        [[nodiscard]] bool takeEvent(SpiFabricEvent &event) noexcept;
        [[nodiscard]] DmaBufferState bufferState(const void *buffer) const noexcept;

      private:
        constexpr SpimHandle(std::uint8_t instance, std::uint8_t index) noexcept
            : SerialFabricHandle(SerialPersonality::spim, instance, index)
        {
        }
    };

    class SpisHandle final : public SerialFabricHandle
    {
        friend class SerialFabric;

      public:
        [[nodiscard]] SerialFabricResult
        configure(const SpiFabricConfiguration &configuration) noexcept;
        [[nodiscard]] SerialFabricResult queueBuffers(const void *tx_buffer, std::size_t tx_size,
                                                      void *rx_buffer, std::size_t rx_size,
                                                      const void *next_tx_buffer = nullptr,
                                                      std::size_t next_tx_size = 0U,
                                                      void *next_rx_buffer = nullptr,
                                                      std::size_t next_rx_size = 0U) noexcept;
        [[nodiscard]] SerialFabricResult cancelBuffers() noexcept;
        [[nodiscard]] bool takeEvent(SpiFabricEvent &event) noexcept;
        [[nodiscard]] DmaBufferState bufferState(const void *buffer) const noexcept;

      private:
        constexpr SpisHandle(std::uint8_t instance, std::uint8_t index) noexcept
            : SerialFabricHandle(SerialPersonality::spis, instance, index)
        {
        }
    };

    class TwimHandle final : public SerialFabricHandle
    {
        friend class SerialFabric;

      public:
        [[nodiscard]] SerialFabricResult configure(const TwimConfiguration &configuration) noexcept;
        [[nodiscard]] SerialFabricResult transferAsync(std::uint8_t address, const void *tx_buffer,
                                                       std::size_t tx_size, void *rx_buffer,
                                                       std::size_t rx_size) noexcept;
        [[nodiscard]] SerialFabricResult transfer(std::uint8_t address, const void *tx_buffer,
                                                  std::size_t tx_size, void *rx_buffer,
                                                  std::size_t rx_size,
                                                  std::uint32_t timeout_us = 100000U) noexcept;
        [[nodiscard]] SerialFabricResult cancelTransfer() noexcept;
        [[nodiscard]] SerialFabricResult recoverBus() noexcept;
        [[nodiscard]] bool takeEvent(TwiFabricEvent &event) noexcept;
        [[nodiscard]] DmaBufferState bufferState(const void *buffer) const noexcept;

      private:
        constexpr TwimHandle(std::uint8_t instance, std::uint8_t index) noexcept
            : SerialFabricHandle(SerialPersonality::twim, instance, index)
        {
        }
    };

    class TwisHandle final : public SerialFabricHandle
    {
        friend class SerialFabric;

      public:
        [[nodiscard]] SerialFabricResult configure(const TwisConfiguration &configuration) noexcept;
        [[nodiscard]] SerialFabricResult queueBuffers(const void *tx_buffer, std::size_t tx_size,
                                                      void *rx_buffer, std::size_t rx_size,
                                                      const void *next_tx_buffer = nullptr,
                                                      std::size_t next_tx_size = 0U,
                                                      void *next_rx_buffer = nullptr,
                                                      std::size_t next_rx_size = 0U) noexcept;
        [[nodiscard]] SerialFabricResult cancelBuffers() noexcept;
        [[nodiscard]] bool takeEvent(TwiFabricEvent &event) noexcept;
        [[nodiscard]] DmaBufferState bufferState(const void *buffer) const noexcept;

      private:
        constexpr TwisHandle(std::uint8_t instance, std::uint8_t index) noexcept
            : SerialFabricHandle(SerialPersonality::twis, instance, index)
        {
        }
    };

    /** @brief kind+instance selector만 허용하는 allocation-free factory입니다. */
    class SerialFabric final
    {
      public:
        [[nodiscard]] UarteHandle *uarte(std::uint8_t instance) noexcept;
        [[nodiscard]] SpimHandle *spim(std::uint8_t instance) noexcept;
        [[nodiscard]] SpisHandle *spis(std::uint8_t instance) noexcept;
        [[nodiscard]] TwimHandle *twim(std::uint8_t instance) noexcept;
        [[nodiscard]] TwisHandle *twis(std::uint8_t instance) noexcept;

      private:
        friend SerialFabric &serialFabric() noexcept;
        SerialFabric() = default;
    };

    /** @brief process-wide static factory를 반환하며 hardware를 활성화하지
     * 않습니다. */
    [[nodiscard]] SerialFabric &serialFabric() noexcept;
} // namespace nucode::arduino

#endif
