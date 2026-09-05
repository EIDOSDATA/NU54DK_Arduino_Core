/** @file @brief PWM의 정지 실패·완료 callback·반복 시작을 주입하는 fake입니다. */
#pragma once
#include <cstdint>
#include <zephyr/irq.h>
struct NRF_PWM_Type
{
    bool enabled{false};
    bool stopped{false};
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
inline int nrfx_pwm_init(nrfx_pwm_t *d, const nrfx_pwm_config_t *,
                         void (*handler)(nrfx_pwm_event_type_t, void *), void *context)
{
    d->initialized = true;
    d->handler = handler;
    d->context = context;
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
        d->p_reg->enabled = false;
        d->p_reg->stopped = true;
    }
    d->handler(event, d->context);
    irq_unlock(key);
}
inline std::uintptr_t nrfx_pwm_simple_playback(nrfx_pwm_t *d, const nrf_pwm_sequence_t *, unsigned,
                                               unsigned)
{
    d->p_reg->enabled = true;
    d->p_reg->stopped = false;
    return 0x40000000U;
}
inline std::uintptr_t nrfx_pwm_complex_playback(nrfx_pwm_t *d, const nrf_pwm_sequence_t *s,
                                                const nrf_pwm_sequence_t *, unsigned count,
                                                unsigned flags)
{
    return nrfx_pwm_simple_playback(d, s, count, flags);
}
inline void nrfx_pwm_step(nrfx_pwm_t *)
{
    ++mock_pwm_steps;
}
inline bool nrfx_pwm_stop(nrfx_pwm_t *d, bool)
{
    if (mock_pwm_stop_ready)
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
    d->initialized = false;
    ++mock_pwm_uninits;
}
inline void nrfx_pwm_irq_handler(nrfx_pwm_t *)
{
}
