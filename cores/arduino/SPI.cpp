/**
 * @file SPI.cpp
 * @brief Arduino SPI transaction·반환값·interrupt mask를 구현합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <Arduino.h>
#include <NUCODEPeripheral.h>

#include <zephyr/kernel.h>
#include <zephyr/sys/atomic.h>

#include <errno.h>
#include <cstddef>
#include <cstdint>

#include "internal/SPIBackend.h"
#include "internal/spi/SpiBackendOperations.h"
#include "internal/SpiInterruptMask.h"

namespace
{

    using nucode::arduino::internal::recordSpiError;
    using nucode::arduino::internal::recordSpiSuccess;
    using nucode::arduino::internal::SpiError;
    namespace backend = nucode::arduino::internal::spi_backend;

    K_MUTEX_DEFINE(spi_mutex);

    atomic_t last_spi_error = ATOMIC_INIT(static_cast<atomic_val_t>(SpiError::none));
    atomic_t last_spi_driver_error = ATOMIC_INIT(0);
    atomic_t spi_transaction_active = ATOMIC_INIT(0);
    atomic_t spi_transaction_frequency = ATOMIC_INIT(0);

    BitOrder active_bit_order = MSBFIRST;
    k_tid_t spi_transaction_owner = nullptr;
    constexpr std::size_t interrupt_capacity = 8U;
    int spi_interrupts[interrupt_capacity]{};
    std::size_t spi_interrupt_count = 0U;
    nucode::arduino::internal::SpiInterruptMaskToken spi_interrupt_tokens[interrupt_capacity]{};
    nucode::arduino::internal::SpiInterruptMaskAdapter interrupt_adapter_storage{};
    const nucode::arduino::internal::SpiInterruptMaskAdapter *interrupt_adapter = nullptr;
    bool spi_interrupt_mask_faulted = false;

    /** @brief 복구되지 않은 interrupt token이 하나라도 남아 있는지 확인합니다. */
    [[nodiscard]] bool hasActiveSpiInterruptToken() noexcept
    {
        for (std::size_t index = 0U; index < spi_interrupt_count; ++index)
        {
            if (spi_interrupt_tokens[index].active)
            {
                return true;
            }
        }
        return false;
    }

    /** @brief 등록된 Arduino GPIO interrupt를 순서대로 suspend합니다. */
    [[nodiscard]] bool suspendSpiInterrupts() noexcept
    {
        if (spi_interrupt_mask_faulted || hasActiveSpiInterruptToken())
        {
            recordSpiError(SpiError::interrupt_mask_error, -EIO);
            return false;
        }
        if (spi_interrupt_count == 0U)
        {
            return true;
        }
        if ((interrupt_adapter == nullptr) || (interrupt_adapter->suspend == nullptr) ||
            (interrupt_adapter->restore == nullptr))
        {
            recordSpiError(SpiError::unsupported_operation);
            return false;
        }
        for (std::size_t index = 0U; index < spi_interrupt_count; ++index)
        {
            spi_interrupt_tokens[index] = {};
            const int result =
                interrupt_adapter->suspend(spi_interrupts[index], spi_interrupt_tokens[index]);
            if (result < 0)
            {
                int rollback_error = 0;
                for (std::size_t restore = index; restore > 0U; --restore)
                {
                    const int restore_result =
                        interrupt_adapter->restore(spi_interrupt_tokens[restore - 1U]);
                    if (restore_result == 0)
                    {
                        spi_interrupt_tokens[restore - 1U].active = false;
                    }
                    else if (rollback_error == 0)
                    {
                        rollback_error = restore_result;
                    }
                }
                if (spi_interrupt_tokens[index].active && rollback_error == 0)
                {
                    rollback_error = -EIO;
                }
                spi_interrupt_mask_faulted = rollback_error < 0;
                recordSpiError(SpiError::interrupt_mask_error,
                               rollback_error < 0 ? rollback_error : result);
                return false;
            }
            spi_interrupt_tokens[index].active = true;
        }
        return true;
    }

    /** @brief suspend된 Arduino GPIO interrupt를 역순으로 복원합니다. */
    [[nodiscard]] bool restoreSpiInterrupts() noexcept
    {
        int first_error = 0;
        if ((interrupt_adapter == nullptr) || (interrupt_adapter->restore == nullptr))
        {
            return spi_interrupt_count == 0U;
        }
        for (std::size_t index = spi_interrupt_count; index > 0U; --index)
        {
            if (!spi_interrupt_tokens[index - 1U].active)
            {
                continue;
            }
            const int result = interrupt_adapter->restore(spi_interrupt_tokens[index - 1U]);
            if (result == 0)
            {
                spi_interrupt_tokens[index - 1U].active = false;
            }
            if ((first_error == 0) && (result < 0))
            {
                first_error = result;
            }
        }
        if (first_error < 0)
        {
            spi_interrupt_mask_faulted = true;
            recordSpiError(SpiError::interrupt_mask_error, first_error);
            return false;
        }
        spi_interrupt_mask_faulted = false;
        return true;
    }

    /**
	 * @brief Arduino transaction 설정과 오류 우선순위를 검증합니다.
	 *
	 * @param settings Arduino transaction 설정입니다.
	 * @return v0.1 controller 계약과 맞으면 true입니다.
	 */
    [[nodiscard]] bool validateSpiSettings(const arduino::SPISettings &settings) noexcept
    {
        if (settings.getBusMode() != arduino::SPI_CONTROLLER)
        {
            recordSpiError(SpiError::unsupported_bus_mode);
            return false;
        }
        if (!backend::frequencySupported(settings.getClockFreq()))
        {
            recordSpiError(SpiError::invalid_frequency);
            return false;
        }
        if ((settings.getBitOrder() != MSBFIRST) && (settings.getBitOrder() != LSBFIRST))
        {
            recordSpiError(SpiError::invalid_bit_order);
            return false;
        }

        switch (settings.getDataMode())
        {
        case arduino::SPI_MODE0:
        case arduino::SPI_MODE1:
        case arduino::SPI_MODE2:
        case arduino::SPI_MODE3:
            return true;
        default:
            recordSpiError(SpiError::invalid_data_mode);
            return false;
        }
    }

    /** @brief ArduinoCore-API HardwareSPI의 CS 없는 controller 구현입니다. */
    class ZephyrSPI final : public nucode::arduino::Nu54SPIClass
    {
      public:
        /** @brief 종료 상태에서 다음 begin()의 SPI00 고정 route를 검증·선택합니다. */
        bool setPins(pin_size_t sck_pin, pin_size_t miso_pin, pin_size_t mosi_pin) noexcept override
        {
            if (k_is_in_isr())
            {
                recordSpiError(SpiError::invalid_context);
                return false;
            }
            static_cast<void>(k_mutex_lock(&spi_mutex, K_FOREVER));
            if (backend::started())
            {
                recordSpiError(SpiError::route_busy);
                static_cast<void>(k_mutex_unlock(&spi_mutex));
                return false;
            }
            const bool staged = backend::setPins(sck_pin, miso_pin, mosi_pin);
            static_cast<void>(k_mutex_unlock(&spi_mutex));
            return staged;
        }

        /** @brief controller·pin route와 현재 등록된 interrupt adapter capability를 반환합니다. */
        nucode::arduino::PeripheralCapability capabilities() const noexcept override
        {
            auto result = nucode::arduino::PeripheralCapability::controller |
                          nucode::arduino::PeripheralCapability::pin_remap;
            if (nucode::arduino::internal::spiInterruptMaskAvailable())
            {
                result = result | nucode::arduino::PeripheralCapability::interrupt_mask;
            }
            return result;
        }

        /** @brief Zephyr가 pinctrl을 적용한 SPI controller lifecycle을 시작합니다. */
        void begin() override
        {
            if (k_is_in_isr())
            {
                recordSpiError(SpiError::invalid_context);
                return;
            }

            static_cast<void>(k_mutex_lock(&spi_mutex, K_FOREVER));
            if (backend::started())
            {
                recordSpiSuccess();
                static_cast<void>(k_mutex_unlock(&spi_mutex));
                return;
            }
            backend::begin();
            static_cast<void>(k_mutex_unlock(&spi_mutex));
        }

        /** @brief Core 상태만 닫고 Zephyr가 소유한 SPI 장치는 유지합니다. */
        void end() override
        {
            if (k_is_in_isr())
            {
                recordSpiError(SpiError::invalid_context);
                return;
            }

            static_cast<void>(k_mutex_lock(&spi_mutex, K_FOREVER));
            const bool discarded_transaction = atomic_get(&spi_transaction_active) != 0;
            if (discarded_transaction && (spi_transaction_owner != k_current_get()))
            {
                recordSpiError(SpiError::transaction_owner_mismatch);
                static_cast<void>(k_mutex_unlock(&spi_mutex));
                return;
            }
            const bool interrupts_ok =
                (!discarded_transaction && !hasActiveSpiInterruptToken()) || restoreSpiInterrupts();
            if (!interrupts_ok)
            {
                /** @brief 복구 token과 transaction 소유권을 보존하여 새 사용을 차단합니다. */
                static_cast<void>(k_mutex_unlock(&spi_mutex));
                return;
            }
            atomic_clear(&spi_transaction_active);
            atomic_clear(&spi_transaction_frequency);
            backend::clearConfiguration();
            spi_transaction_owner = nullptr;
            if (backend::end())
            {
                recordSpiError(discarded_transaction ? SpiError::transaction_already_active
                                                     : SpiError::none);
            }
            static_cast<void>(k_mutex_unlock(&spi_mutex));
        }

        /** @brief 새 transaction의 frequency, mode와 bit order를 고정합니다. */
        void beginTransaction(arduino::SPISettings settings) override
        {
            if (k_is_in_isr())
            {
                recordSpiError(SpiError::invalid_context);
                return;
            }

            static_cast<void>(k_mutex_lock(&spi_mutex, K_FOREVER));
            if (!backend::started())
            {
                recordSpiError(SpiError::not_started);
            }
            else if (atomic_get(&spi_transaction_active) != 0)
            {
                recordSpiError((spi_transaction_owner == k_current_get())
                                   ? SpiError::transaction_already_active
                                   : SpiError::transaction_owner_mismatch);
            }
            else if (spi_interrupt_mask_faulted || hasActiveSpiInterruptToken())
            {
                recordSpiError(SpiError::interrupt_mask_error, -EIO);
            }
            else
            {
                backend::advanceConfiguration();
                if (validateSpiSettings(settings))
                {
                    backend::configureValidated(settings);
                    if (suspendSpiInterrupts())
                    {
                        backend::commitConfiguration();
                        active_bit_order = settings.getBitOrder();
                        atomic_set(&spi_transaction_frequency,
                                   static_cast<atomic_val_t>(settings.getClockFreq()));
                        atomic_set(&spi_transaction_active, 1);
                        spi_transaction_owner = k_current_get();
                        recordSpiSuccess();
                    }
                }
            }
            static_cast<void>(k_mutex_unlock(&spi_mutex));
        }

        /** @brief 현재 transaction을 닫으며 외부 CS는 변경하지 않습니다. */
        void endTransaction() override
        {
            if (k_is_in_isr())
            {
                recordSpiError(SpiError::invalid_context);
                return;
            }

            static_cast<void>(k_mutex_lock(&spi_mutex, K_FOREVER));
            if (atomic_get(&spi_transaction_active) == 0)
            {
                recordSpiError(SpiError::transaction_not_active);
            }
            else if (spi_transaction_owner != k_current_get())
            {
                recordSpiError(SpiError::transaction_owner_mismatch);
            }
            else
            {
                const bool interrupts_ok = restoreSpiInterrupts();
                if (interrupts_ok)
                {
                    atomic_clear(&spi_transaction_active);
                    atomic_clear(&spi_transaction_frequency);
                    backend::clearConfiguration();
                    spi_transaction_owner = nullptr;
                    recordSpiSuccess();
                }
            }
            static_cast<void>(k_mutex_unlock(&spi_mutex));
        }

        /** @brief 현재 transaction에서 한 byte를 full-duplex 전송합니다. */
        std::uint8_t transfer(std::uint8_t value) override
        {
            if (k_is_in_isr())
            {
                recordSpiError(SpiError::invalid_context);
                return 0U;
            }

            static_cast<void>(k_mutex_lock(&spi_mutex, K_FOREVER));
            if (!backend::started())
            {
                recordSpiError(SpiError::not_started);
                static_cast<void>(k_mutex_unlock(&spi_mutex));
                return 0U;
            }
            if ((atomic_get(&spi_transaction_active) == 0) || !backend::configurationReady())
            {
                recordSpiError(SpiError::transaction_not_active);
                static_cast<void>(k_mutex_unlock(&spi_mutex));
                return 0U;
            }
            if (spi_transaction_owner != k_current_get())
            {
                recordSpiError(SpiError::transaction_owner_mismatch);
                static_cast<void>(k_mutex_unlock(&spi_mutex));
                return 0U;
            }

            std::uint8_t received = 0U;
            static_cast<void>(backend::transferBlock(&value, &received, 1U));
            static_cast<void>(k_mutex_unlock(&spi_mutex));
            return received;
        }

        /** @brief 현재 bit order에 맞춰 16-bit 값을 full-duplex 전송합니다. */
        std::uint16_t transfer16(std::uint16_t value) override
        {
            if (k_is_in_isr())
            {
                recordSpiError(SpiError::invalid_context);
                return 0U;
            }

            static_cast<void>(k_mutex_lock(&spi_mutex, K_FOREVER));
            if (!backend::started() || (atomic_get(&spi_transaction_active) == 0) ||
                !backend::configurationReady())
            {
                recordSpiError(backend::started() ? SpiError::transaction_not_active
                                                  : SpiError::not_started);
                static_cast<void>(k_mutex_unlock(&spi_mutex));
                return 0U;
            }
            if (spi_transaction_owner != k_current_get())
            {
                recordSpiError(SpiError::transaction_owner_mismatch);
                static_cast<void>(k_mutex_unlock(&spi_mutex));
                return 0U;
            }

            std::uint8_t transmit[2] = {};
            std::uint8_t receive[2] = {};
            if (active_bit_order == LSBFIRST)
            {
                transmit[0] = static_cast<std::uint8_t>(value & 0xFFU);
                transmit[1] = static_cast<std::uint8_t>(value >> 8U);
            }
            else
            {
                transmit[0] = static_cast<std::uint8_t>(value >> 8U);
                transmit[1] = static_cast<std::uint8_t>(value & 0xFFU);
            }

            if (!backend::transferBlock(transmit, receive, sizeof(transmit)))
            {
                static_cast<void>(k_mutex_unlock(&spi_mutex));
                return 0U;
            }

            const std::uint16_t result =
                (active_bit_order == LSBFIRST)
                    ? static_cast<std::uint16_t>(receive[0] | (receive[1] << 8U))
                    : static_cast<std::uint16_t>((receive[0] << 8U) | receive[1]);
            static_cast<void>(k_mutex_unlock(&spi_mutex));
            return result;
        }

        /** @brief caller 소유 buffer를 고정 크기 chunk로 in-place 전송합니다. */
        void transfer(void *buffer, std::size_t count) override
        {
            if (k_is_in_isr())
            {
                recordSpiError(SpiError::invalid_context);
                return;
            }
            if ((buffer == nullptr) && (count != 0U))
            {
                recordSpiError(SpiError::invalid_buffer);
                return;
            }

            static_cast<void>(k_mutex_lock(&spi_mutex, K_FOREVER));
            if (!backend::started() || (atomic_get(&spi_transaction_active) == 0) ||
                !backend::configurationReady())
            {
                recordSpiError(backend::started() ? SpiError::transaction_not_active
                                                  : SpiError::not_started);
                static_cast<void>(k_mutex_unlock(&spi_mutex));
                return;
            }
            if (spi_transaction_owner != k_current_get())
            {
                recordSpiError(SpiError::transaction_owner_mismatch);
                static_cast<void>(k_mutex_unlock(&spi_mutex));
                return;
            }

            auto *bytes = static_cast<std::uint8_t *>(buffer);
            constexpr std::size_t chunk_capacity = 32U;
            std::uint8_t transmit[chunk_capacity] = {};
            std::uint8_t receive[chunk_capacity] = {};
            std::size_t offset = 0U;
            while (offset < count)
            {
                const std::size_t remaining = count - offset;
                const std::size_t chunk = (remaining < chunk_capacity) ? remaining : chunk_capacity;
                for (std::size_t index = 0U; index < chunk; ++index)
                {
                    transmit[index] = bytes[offset + index];
                }
                if (!backend::transferBlock(transmit, receive, chunk))
                {
                    break;
                }
                for (std::size_t index = 0U; index < chunk; ++index)
                {
                    bytes[offset + index] = receive[index];
                }
                offset += chunk;
            }
            static_cast<void>(k_mutex_unlock(&spi_mutex));
        }

        /** @brief transaction 동안 마스킹할 Arduino GPIO interrupt를 등록합니다. */
        void usingInterrupt(int interrupt_number) override
        {
            if (k_is_in_isr())
            {
                recordSpiError(SpiError::invalid_context);
                return;
            }
            static_cast<void>(k_mutex_lock(&spi_mutex, K_FOREVER));
            if (atomic_get(&spi_transaction_active) != 0)
            {
                recordSpiError(SpiError::transaction_already_active);
            }
            else if (spi_interrupt_mask_faulted || hasActiveSpiInterruptToken())
            {
                recordSpiError(SpiError::interrupt_mask_error, -EIO);
            }
            else if ((interrupt_adapter == nullptr) || (interrupt_adapter->valid == nullptr) ||
                     !interrupt_adapter->valid(interrupt_number))
            {
                recordSpiError(SpiError::unsupported_operation);
            }
            else
            {
                bool found = false;
                for (std::size_t index = 0U; index < spi_interrupt_count; ++index)
                {
                    found = found || (spi_interrupts[index] == interrupt_number);
                }
                if (found)
                {
                    recordSpiSuccess();
                }
                else if (spi_interrupt_count >= interrupt_capacity)
                {
                    recordSpiError(SpiError::unsupported_operation);
                }
                else
                {
                    spi_interrupts[spi_interrupt_count++] = interrupt_number;
                    recordSpiSuccess();
                }
            }
            static_cast<void>(k_mutex_unlock(&spi_mutex));
        }

        /** @brief transaction 마스킹 대상에서 Arduino GPIO interrupt를 제거합니다. */
        void notUsingInterrupt(int interrupt_number) override
        {
            if (k_is_in_isr())
            {
                recordSpiError(SpiError::invalid_context);
                return;
            }
            static_cast<void>(k_mutex_lock(&spi_mutex, K_FOREVER));
            if (atomic_get(&spi_transaction_active) != 0)
            {
                recordSpiError(SpiError::transaction_already_active);
            }
            else if (spi_interrupt_mask_faulted || hasActiveSpiInterruptToken())
            {
                recordSpiError(SpiError::interrupt_mask_error, -EIO);
            }
            else
            {
                std::size_t index = 0U;
                while ((index < spi_interrupt_count) && (spi_interrupts[index] != interrupt_number))
                {
                    ++index;
                }
                if (index == spi_interrupt_count)
                {
                    recordSpiError(SpiError::unsupported_operation);
                }
                else
                {
                    for (; index + 1U < spi_interrupt_count; ++index)
                    {
                        spi_interrupts[index] = spi_interrupts[index + 1U];
                    }
                    --spi_interrupt_count;
                    recordSpiSuccess();
                }
            }
            static_cast<void>(k_mutex_unlock(&spi_mutex));
        }

        /** @brief SPI peripheral interrupt 기능은 제공하지 않습니다. */
        void attachInterrupt() override
        {
            recordSpiError(SpiError::unsupported_operation);
        }

        /** @brief SPI peripheral interrupt 기능은 제공하지 않습니다. */
        void detachInterrupt() override
        {
            recordSpiError(SpiError::unsupported_operation);
        }
    };

    ZephyrSPI spi_backend;

} // namespace

SPIClass &SPI = spi_backend;

namespace nucode::arduino::internal
{
    void recordSpiError(SpiError error, int driver_error) noexcept
    {
        atomic_set(&last_spi_driver_error, static_cast<atomic_val_t>(driver_error));
        atomic_set(&last_spi_error, static_cast<atomic_val_t>(error));
    }
    void recordSpiSuccess() noexcept
    {
        recordSpiError(SpiError::none);
    }

    bool registerSpiInterruptMaskAdapter(const SpiInterruptMaskAdapter &adapter) noexcept
    {
        if (k_is_in_isr() || (adapter.valid == nullptr) || (adapter.suspend == nullptr) ||
            (adapter.restore == nullptr))
        {
            return false;
        }
        static_cast<void>(k_mutex_lock(&spi_mutex, K_FOREVER));
        if ((interrupt_adapter != nullptr) || (atomic_get(&spi_transaction_active) != 0))
        {
            static_cast<void>(k_mutex_unlock(&spi_mutex));
            return false;
        }
        interrupt_adapter_storage = adapter;
        interrupt_adapter = &interrupt_adapter_storage;
        static_cast<void>(k_mutex_unlock(&spi_mutex));
        return true;
    }

    bool spiInterruptMaskAvailable() noexcept
    {
        return interrupt_adapter != nullptr;
    }

    SpiError lastSpiError() noexcept
    {
        return static_cast<SpiError>(atomic_get(&last_spi_error));
    }

    int lastSpiDriverError() noexcept
    {
        return static_cast<int>(atomic_get(&last_spi_driver_error));
    }

    bool spiTransactionActive() noexcept
    {
        return atomic_get(&spi_transaction_active) != 0;
    }

    std::uint32_t spiTransactionFrequency() noexcept
    {
        return static_cast<std::uint32_t>(atomic_get(&spi_transaction_frequency));
    }

    void clearSpiDiagnostics() noexcept
    {
        recordSpiSuccess();
    }

} // namespace nucode::arduino::internal
