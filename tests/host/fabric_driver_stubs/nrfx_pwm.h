/** @file @brief PWM의 정지 실패·완료 callback·반복 시작을 주입하는 fake입니다. */
#pragma once
#include <cstdint>
#include <functional>
#include <zephyr/irq.h>
struct NRF_PWM_Type
{
    bool enabled{false};
    bool stopped{false};
    bool running{false};
    std::uint32_t EVENTS_SEQSTARTED[2]{};
    struct
    {
        struct
        {
            std::uint32_t READY{0U};
        } SEQ[2];
    } EVENTS_DMA;
    struct
    {
        struct
        {
            std::uint32_t START{0U};
        } SEQ[2];
    } SUBSCRIBE_DMA;
};
inline NRF_PWM_Type mock_pwm_regs[3];
#define NRF_PWM20 (&mock_pwm_regs[0])
#define NRF_PWM21 (&mock_pwm_regs[1])
#define NRF_PWM22 (&mock_pwm_regs[2])
enum nrfx_pwm_event_type_t
{
    NRFX_PWM_EVENT_END_SEQ0,
    NRFX_PWM_EVENT_END_SEQ1,
    NRFX_PWM_EVENT_FINISHED,
    NRFX_PWM_EVENT_STOPPED
};
enum nrf_pwm_dec_load_t
{
    NRF_PWM_LOAD_COMMON,
    NRF_PWM_LOAD_GROUPED,
    NRF_PWM_LOAD_INDIVIDUAL,
    NRF_PWM_LOAD_WAVE_FORM
};
enum
{
    NRF_PWM_CLK_1MHz,
    NRF_PWM_MODE_UP,
    NRF_PWM_STEP_TRIGGERED,
    NRF_PWM_STEP_AUTO
};
enum
{
    NRFX_PWM_FLAG_SIGNAL_END_SEQ0 = 1,
    NRFX_PWM_FLAG_SIGNAL_END_SEQ1 = 2,
    NRFX_PWM_FLAG_LOOP = 4,
    NRFX_PWM_FLAG_STOP = 8,
    NRFX_PWM_FLAG_START_VIA_TASK = 16
};
#define NRF_PWM_PIN_NOT_CONNECTED UINT32_MAX
#define PWM_DMA_SEQ_MAXCNT_MAXCNT_Msk 0x7FFFU
#define PWM_SUBSCRIBE_DMA_SEQ_START_EN_Msk (1UL << 31)
enum nrf_pwm_event_t
{
    NRF_PWM_EVENT_SEQSTARTED0,
    NRF_PWM_EVENT_SEQSTARTED1
};
inline std::function<void(NRF_PWM_Type *)> mock_pwm_on_disable;
inline unsigned mock_pwm_starts = 0, mock_pwm_stop_events = 0;
inline void mock_pwm_start(NRF_PWM_Type *reg, unsigned sequence = 1U)
{
    if (reg->enabled)
    {
        reg->running = true;
        reg->EVENTS_DMA.SEQ[sequence].READY = 1U;
        reg->EVENTS_SEQSTARTED[sequence] = 1U;
        ++mock_pwm_starts;
    }
}
inline bool nrf_pwm_event_check(const NRF_PWM_Type *reg, nrf_pwm_event_t event)
{
    return reg->EVENTS_SEQSTARTED[event] != 0U;
}
inline void nrf_pwm_event_clear(NRF_PWM_Type *reg, nrf_pwm_event_t event)
{
    reg->EVENTS_SEQSTARTED[event] = 0U;
}
inline void nrf_pwm_disable(NRF_PWM_Type *reg)
{
    if (mock_pwm_on_disable)
    {
        mock_pwm_on_disable(reg);
    }
    reg->enabled = false;
}
inline void nrf_pwm_enable(NRF_PWM_Type *reg)
{
    reg->enabled = true;
}
inline void nrf_barrier_rw()
{
}
struct nrfx_pwm_config_t
{
    std::uint32_t output_pins[4];
    bool pin_inverted[4];
    unsigned irq_priority;
    int base_clock;
    int count_mode;
    std::uint16_t top_value;
    nrf_pwm_dec_load_t load_mode;
    int step_mode;
};
#define NRFX_PWM_DEFAULT_CONFIG(a, b, c, d)                                                        \
    nrfx_pwm_config_t{{a, b, c, d}, {}, 0, 0, 0, 0, NRF_PWM_LOAD_COMMON, 0}
struct nrf_pwm_sequence_t
{
    union
    {
        const std::uint16_t *p_raw;
    } values;
    std::uint16_t length;
    std::uint32_t repeats;
    std::uint32_t end_delay;
};
struct nrfx_pwm_t
{
    NRF_PWM_Type *p_reg;
    bool initialized{false};
    void (*handler)(nrfx_pwm_event_type_t, void *){nullptr};
    void *context{nullptr};
};
#define NRFX_PWM_INSTANCE(reg) {reg}
inline bool mock_pwm_stop_ready = true;
inline unsigned mock_pwm_uninits = 0, mock_pwm_steps = 0;
inline nrfx_pwm_t *mock_pwm_drivers[3]{};
inline nrf_pwm_sequence_t mock_pwm_sequences[2]{};
inline int nrfx_pwm_init(nrfx_pwm_t *d, const nrfx_pwm_config_t *,
                         void (*handler)(nrfx_pwm_event_type_t, void *), void *context)
{
    d->initialized = true;
    d->handler = handler;
    d->context = context;
    mock_pwm_drivers[d->p_reg - mock_pwm_regs] = d;
    return 0;
}
inline bool nrfx_pwm_init_check(nrfx_pwm_t *d)
{
    return d->initialized;
}
inline void mock_pwm_event(nrfx_pwm_t *d, nrfx_pwm_event_type_t event)
{
    const auto key = irq_lock();
    if (event == NRFX_PWM_EVENT_STOPPED)
    {
        ++mock_pwm_stop_events;
        d->p_reg->enabled = false;
        d->p_reg->stopped = true;
        d->p_reg->running = false;
    }
    d->handler(event, d->context);
    irq_unlock(key);
}
inline std::uintptr_t nrfx_pwm_simple_playback(nrfx_pwm_t *d, const nrf_pwm_sequence_t *sequence,
                                               unsigned, unsigned flags)
{
    d->p_reg->enabled = true;
    mock_pwm_sequences[0] = *sequence;
    d->p_reg->stopped = false;
    if ((flags & NRFX_PWM_FLAG_START_VIA_TASK) != 0U)
    {
        return 0x40000000U;
    }
    mock_pwm_start(d->p_reg);
    return 0U;
}
inline std::uintptr_t nrfx_pwm_complex_playback(nrfx_pwm_t *d, const nrf_pwm_sequence_t *s,
                                                const nrf_pwm_sequence_t *next, unsigned count,
                                                unsigned flags)
{
    mock_pwm_sequences[1] = *next;
    return nrfx_pwm_simple_playback(d, s, count, flags);
}
inline void nrfx_pwm_step(nrfx_pwm_t *)
{
    ++mock_pwm_steps;
}
inline bool nrfx_pwm_stop(nrfx_pwm_t *d, bool)
{
    if (mock_pwm_stop_ready && d->p_reg->running)
    {
        mock_pwm_event(d, NRFX_PWM_EVENT_STOPPED);
    }
    return d->p_reg->stopped;
}
inline bool nrfx_pwm_stopped_check(nrfx_pwm_t *d)
{
    return d->p_reg->stopped;
}
inline void nrfx_pwm_uninit(nrfx_pwm_t *d)
{
    d->p_reg->enabled = false;
    d->initialized = false;
    ++mock_pwm_uninits;
}
inline void nrfx_pwm_irq_handler(nrfx_pwm_t *)
{
}
