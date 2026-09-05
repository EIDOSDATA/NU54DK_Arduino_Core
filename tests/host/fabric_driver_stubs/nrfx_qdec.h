/** @file @brief QDEC snapshot·IRQ callback의 fake입니다. */
#pragma once
#include <cstdint>
#include <zephyr/irq.h>
struct NRF_QDEC_Type
{
};
inline NRF_QDEC_Type mock_qdec_regs[2];
#define NRF_QDEC20 (&mock_qdec_regs[0])
#define NRF_QDEC21 (&mock_qdec_regs[1])
#define NRF_QDEC_PIN_NOT_CONNECTED UINT32_MAX
enum nrf_qdec_sampleper_t
{
    NRF_QDEC_SAMPLEPER_128US = 0,
    NRF_QDEC_SAMPLEPER_256US = 1,
    NRF_QDEC_SAMPLEPER_16384US = 7,
    NRF_QDEC_SAMPLEPER_131MS = 10
};
enum
{
    NRF_QDEC_EVENT_SAMPLERDY,
    NRF_QDEC_EVENT_REPORTRDY,
    NRF_QDEC_EVENT_ACCOF
};
struct nrfx_qdec_event_t
{
    int type;
    struct
    {
        struct
        {
            int value;
        } sample;
        struct
        {
            std::int32_t acc;
            std::uint32_t accdbl;
        } report;
    } data;
};
struct nrfx_qdec_config_t
{
    unsigned a, b, led, interrupt_priority;
    bool dbfen, sample_inten;
    nrf_qdec_sampleper_t sampleper;
    unsigned ledpre;
    bool reportper_inten;
};
#define NRFX_QDEC_DEFAULT_CONFIG(a, b, led)                                                        \
    nrfx_qdec_config_t                                                                             \
    {                                                                                              \
        a, b, led, 0, false, false, NRF_QDEC_SAMPLEPER_128US, 0, false                             \
    }
struct nrfx_qdec_t
{
    NRF_QDEC_Type *p_reg;
};
#define NRFX_QDEC_INSTANCE(reg) {reg}
inline unsigned mock_qdec_reads = 0;
inline int nrfx_qdec_init(nrfx_qdec_t *, const nrfx_qdec_config_t *,
                          void (*)(nrfx_qdec_event_t, void *), void *)
{
    return 0;
}
inline void nrfx_qdec_enable(nrfx_qdec_t *)
{
}
inline void nrfx_qdec_disable(nrfx_qdec_t *)
{
}
inline void nrfx_qdec_uninit(nrfx_qdec_t *)
{
}
inline void nrfx_qdec_irq_handler(nrfx_qdec_t *)
{
}
inline void nrfx_qdec_accumulators_read(nrfx_qdec_t *, std::int32_t *acc, std::uint32_t *accdbl)
{
    *acc = 1;
    *accdbl = 0;
    ++mock_qdec_reads;
}
