/**
 * @file uart_trace.cpp
 * @brief 진단 image에서 원래 nrfx 호출·callback을 보존하며 DMA 전환 이력을 기록합니다.
 * @note 기본 빌드에서는 비활성이며 제품 API·SDK를 변경하지 않습니다. SWD 정지 뒤에 읽습니다.
 * SPDX-License-Identifier: MIT
 */
#include <nrfx_uarte.h>
#include <zephyr/irq.h>
#include <zephyr/kernel.h>
#include <cstddef>
#include <cstdint>
#include <cstring>

extern "C"
{
    /** @brief 역할별 exact ELF가 소유하는64건×24word 순환 이력과 게시 sequence입니다. */
    alignas(4) volatile std::uint32_t v04_uart_trace[5][64][24]{};
    alignas(4) volatile std::uint32_t v04_uart_trace_count[5]{};

    int __real_nrfx_uarte_init(nrfx_uarte_t *instance, const nrfx_uarte_config_t *configuration,
                               nrfx_uarte_event_handler_t handler);
    int __real_nrfx_uarte_rx_buffer_set(nrfx_uarte_t *instance, std::uint8_t *data,
                                        std::size_t length);
    int __real_nrfx_uarte_rx_enable(nrfx_uarte_t *instance, std::uint32_t flags);
}

namespace
{
    struct Callback
    {
        nrfx_uarte_t *instance = nullptr;
        nrfx_uarte_event_handler_t original = nullptr;
        void *context = nullptr;
        unsigned index = 0U;
    } callbacks[5];

    /** @brief 기존 다섯 UART 주소만 이력 slot으로 대응합니다. */
    unsigned indexFor(const NRF_UARTE_Type *registers)
    {
        const NRF_UARTE_Type *known[]{NRF_UARTE00, NRF_UARTE20, NRF_UARTE21, NRF_UARTE22,
                                      NRF_UARTE30};
        for (unsigned index = 0U; index < 5U; ++index)
        {
            if (registers == known[index])
            {
                return index;
            }
        }
        return 5U;
    }

    /** @brief RAM 이력만 쓰고 peripheral은 읽습니다. 게시 sequence는 마지막에 씁니다. */
    void record(nrfx_uarte_t *instance, unsigned operation, std::uint32_t argument,
                const void *buffer, std::size_t length, bool inspect_buffer)
    {
        if (instance == nullptr)
        {
            return;
        }
        const unsigned index = indexFor(instance->p_reg);
        if (index == 5U)
        {
            return;
        }
        const auto key = irq_lock();
        const std::uint32_t sequence = v04_uart_trace_count[index] + 1U;
        auto &out = v04_uart_trace[index][(sequence - 1U) % 64U];
        out[0] = 0U;
        out[1] = k_cycle_get_32();
        out[2] = operation;
        out[3] = argument;
        out[4] = reinterpret_cast<std::uintptr_t>(buffer);
        out[5] = length;
        std::uint32_t first_word = 0U;
        const auto address = reinterpret_cast<std::uintptr_t>(buffer);
        if (inspect_buffer && length >= sizeof(first_word) && address >= 0x20000000U &&
            address <= 0x20040000U - sizeof(first_word))
        {
            std::memcpy(&first_word, buffer, sizeof(first_word));
        }
        out[6] = first_word;
        const auto *registers = instance->p_reg;
        out[7] = registers->DMA.RX.PTR;
        out[8] = registers->DMA.RX.MAXCNT;
        out[9] = registers->DMA.RX.AMOUNT;
        out[10] = nrf_uarte_event_check(registers, NRF_UARTE_EVENT_RXSTARTED) ? 1U : 0U;
        out[11] = nrf_uarte_event_check(registers, NRF_UARTE_EVENT_ENDRX) ? 1U : 0U;
        out[12] = registers->ERRORSRC;
        out[13] = nrf_uarte_event_check(registers, NRF_UARTE_EVENT_ERROR) ? 1U : 0U;
        out[14] = registers->SHORTS;
        out[15] = instance->cb.flags;
        out[16] = reinterpret_cast<std::uintptr_t>(instance->cb.rx.curr.p_buffer);
        out[17] = reinterpret_cast<std::uintptr_t>(instance->cb.rx.next.p_buffer);
        out[18] = instance->cb.rx.curr.length;
        out[19] = instance->cb.rx.next.length;
        out[20] = registers->ENABLE;
        out[21] = registers->CONFIG;
        out[22] = __get_IPSR();
        out[23] = key;
        __DMB();
        out[0] = sequence;
        v04_uart_trace_count[index] = sequence;
        irq_unlock(key);
    }

    /** @brief 실제 callback 직전과 직후를 기록하며 event와 원래 context를 그대로 전달합니다. */
    void observedEvent(const nrfx_uarte_event_t *event, void *context)
    {
        auto &callback = *static_cast<Callback *>(context);
        const void *buffer = nullptr;
        std::size_t length = 0U;
        bool inspect_buffer = false;
        if (event->type == NRFX_UARTE_EVT_RX_DONE)
        {
            buffer = event->data.rx.p_buffer;
            length = event->data.rx.length;
            inspect_buffer = true;
        }
        else if (event->type == NRFX_UARTE_EVT_TX_DONE)
        {
            buffer = event->data.tx.p_buffer;
            length = event->data.tx.length;
            inspect_buffer = true;
        }
        const auto argument =
            static_cast<std::uint32_t>(event->type) |
            (event->type == NRFX_UARTE_EVT_ERROR ? event->data.error.error_mask << 8U : 0U);
        record(callback.instance, 6U, argument, buffer, length, inspect_buffer);
        callback.original(event, callback.context);
        record(callback.instance, 7U, argument, buffer, length, inspect_buffer);
    }
} // namespace

extern "C" int __wrap_nrfx_uarte_init(nrfx_uarte_t *instance,
                                      const nrfx_uarte_config_t *configuration,
                                      nrfx_uarte_event_handler_t handler)
{
    const unsigned index = instance == nullptr ? 5U : indexFor(instance->p_reg);
    if (index == 5U || configuration == nullptr || handler == nullptr ||
        nrfx_uarte_init_check(instance))
    {
        return __real_nrfx_uarte_init(instance, configuration, handler);
    }
    auto &callback = callbacks[index];
    callback = {instance, handler, configuration->p_context, index};
    auto observed = *configuration;
    observed.p_context = &callback;
    const int result = __real_nrfx_uarte_init(instance, &observed, observedEvent);
    record(instance, 1U, static_cast<std::uint32_t>(result), nullptr, 0U, false);
    return result;
}

extern "C" int __wrap_nrfx_uarte_rx_buffer_set(nrfx_uarte_t *instance, std::uint8_t *data,
                                               std::size_t length)
{
    record(instance, 2U, 0U, data, length, false);
    const int result = __real_nrfx_uarte_rx_buffer_set(instance, data, length);
    record(instance, 3U, static_cast<std::uint32_t>(result), data, length, false);
    return result;
}

extern "C" int __wrap_nrfx_uarte_rx_enable(nrfx_uarte_t *instance, std::uint32_t flags)
{
    record(instance, 4U, flags, nullptr, 0U, false);
    const int result = __real_nrfx_uarte_rx_enable(instance, flags);
    record(instance, 5U, static_cast<std::uint32_t>(result), nullptr, 0U, false);
    return result;
}
