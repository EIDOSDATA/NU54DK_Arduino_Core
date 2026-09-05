/** @file @brief PDM buffer callback과 STOP 지연을 주입하는 fake입니다. */
#pragma once
#include <cstdint>
#include <zephyr/irq.h>
struct NRF_PDM_Type
{
    bool enabled{false};
};
inline NRF_PDM_Type mock_pdm_regs[2];
#define NRF_PDM20 (&mock_pdm_regs[0])
#define NRF_PDM21 (&mock_pdm_regs[1])
enum
{
    NRF_PDM_MODE_STEREO,
    NRF_PDM_MODE_MONO,
    NRF_PDM_EDGE_LEFTRISING,
    NRF_PDM_EDGE_LEFTFALLING,
    NRF_PDM_TASK_START
};
enum
{
    NRFX_PDM_ERROR_OVERFLOW = 1
};
#define NRFX_PDM_MAX_BUFFER_SIZE 0x7FFFU
struct nrfx_pdm_evt_t
{
    bool buffer_requested;
    std::int16_t *buffer_released;
    int error;
};
struct nrfx_pdm_config_t
{
    unsigned clock_pin, data_pin, interrupt_priority;
    int mode, edge;
    unsigned prescalers;
};
#define NRFX_PDM_DEFAULT_CONFIG(clock, data) nrfx_pdm_config_t{clock, data, 0, 0, 0, 0}
struct nrfx_pdm_output_t
{
    unsigned input_clock, sample_rate, min_clock, max_clock;
};
struct nrfx_pdm_t
{
    NRF_PDM_Type *p_reg;
    bool initialized{false};
    void (*handler)(const nrfx_pdm_evt_t *){nullptr};
};
#define NRFX_PDM_INSTANCE(reg) {reg}
inline bool mock_pdm_stop_ready = true;
inline int mock_pdm_buffer_error = 0;
inline unsigned mock_pdm_uninits = 0;
inline nrfx_pdm_t *mock_pdm_drivers[2]{};
inline std::int16_t *mock_pdm_buffer{};
inline std::uint16_t mock_pdm_samples{};
inline int nrfx_pdm_prescalers_calc(const nrfx_pdm_output_t *, unsigned *)
{
    return 0;
}
inline int nrfx_pdm_init(nrfx_pdm_t *d, const nrfx_pdm_config_t *,
                         void (*handler)(const nrfx_pdm_evt_t *))
{
    d->initialized = true;
    d->handler = handler;
    mock_pdm_drivers[d->p_reg - mock_pdm_regs] = d;
    return 0;
}
inline bool nrfx_pdm_init_check(nrfx_pdm_t *d)
{
    return d->initialized;
}
inline bool nrfx_pdm_enable_check(nrfx_pdm_t *d)
{
    return d->p_reg->enabled;
}
inline int nrfx_pdm_start(nrfx_pdm_t *d)
{
    d->p_reg->enabled = true;
    return 0;
}
inline int nrfx_pdm_buffer_set(nrfx_pdm_t *, std::int16_t *buffer, std::uint16_t samples)
{
    mock_pdm_buffer = buffer;
    mock_pdm_samples = samples;
    return mock_pdm_buffer_error;
}
inline int nrfx_pdm_stop(nrfx_pdm_t *d)
{
    if (mock_pdm_stop_ready)
    {
        d->p_reg->enabled = false;
    }
    return 0;
}
inline void nrfx_pdm_uninit(nrfx_pdm_t *d)
{
    d->initialized = false;
    ++mock_pdm_uninits;
}
inline void nrfx_pdm_irq_handler(nrfx_pdm_t *)
{
}
inline std::uintptr_t nrfx_pdm_task_address_get(const nrfx_pdm_t *, int)
{
    return 0x40000000U;
}
inline void mock_pdm_event(nrfx_pdm_t *d, const nrfx_pdm_evt_t &event)
{
    const auto key = irq_lock();
    d->handler(&event);
    irq_unlock(key);
}
