/** @file @brief I2S NEXT/STOP callback과 DMA 수명을 제어하는 fake입니다. */
#pragma once
#include <cstdint>
#include <zephyr/irq.h>
struct NRF_I2S_Type
{
    bool enabled{false};
};
inline NRF_I2S_Type mock_i2s_reg;
#define NRF_I2S20 (&mock_i2s_reg)
#define NRF_I2S_PIN_NOT_CONNECTED UINT32_MAX
#define I2S_RXTXD_MAXCNT_MAXCNT_Msk 0x3FFFU
enum nrf_i2s_channels_t
{
    NRF_I2S_CHANNELS_LEFT,
    NRF_I2S_CHANNELS_RIGHT,
    NRF_I2S_CHANNELS_STEREO
};
enum nrf_i2s_swidth_t
{
    NRF_I2S_SWIDTH_8BIT,
    NRF_I2S_SWIDTH_16BIT,
    NRF_I2S_SWIDTH_24BIT,
    NRF_I2S_SWIDTH_32BIT
};
enum
{
    NRF_I2S_MODE_MASTER,
    NRF_I2S_MODE_SLAVE,
    NRF_I2S_MCK_DISABLED
};
enum
{
    NRFX_I2S_STATUS_NEXT_BUFFERS_NEEDED = 1,
    NRFX_I2S_STATUS_TRANSFER_STOPPED = 2
};
struct nrfx_i2s_prescalers_t
{
    int mck_setup;
};
struct nrfx_i2s_config_t
{
    unsigned sck, lrck, mck, sdout, sdin, irq_priority;
    int mode;
    nrf_i2s_swidth_t sample_width;
    nrf_i2s_channels_t channels;
    nrfx_i2s_prescalers_t prescalers;
};
#define NRFX_I2S_DEFAULT_CONFIG(a, b, c, d, e)                                                     \
    nrfx_i2s_config_t                                                                              \
    {                                                                                              \
        a, b, c, d, e, 0, 0, NRF_I2S_SWIDTH_16BIT, NRF_I2S_CHANNELS_STEREO,                        \
        {                                                                                          \
        }                                                                                          \
    }
struct nrfx_i2s_clk_params_t
{
    unsigned input_clock, sample_rate;
    nrf_i2s_swidth_t sample_width;
    bool bypass;
};
struct nrfx_i2s_buffers_t
{
    std::uint32_t *p_rx_buffer;
    const std::uint32_t *p_tx_buffer;
    std::uint16_t buffer_size;
};
struct nrfx_i2s_t
{
    NRF_I2S_Type *p_reg;
    bool initialized{false};
    void (*handler)(const nrfx_i2s_buffers_t *, std::uint32_t){nullptr};
};
#define NRFX_I2S_INSTANCE(reg) {reg}
inline bool mock_i2s_stop_ready = true;
inline unsigned mock_i2s_uninits = 0;
inline int nrfx_i2s_prescalers_calc(const nrfx_i2s_clk_params_t *, nrfx_i2s_prescalers_t *)
{
    return 0;
}
inline int nrfx_i2s_init(nrfx_i2s_t *d, const nrfx_i2s_config_t *,
                         void (*handler)(const nrfx_i2s_buffers_t *, std::uint32_t))
{
    d->initialized = true;
    d->handler = handler;
    return 0;
}
inline bool nrfx_i2s_init_check(nrfx_i2s_t *d)
{
    return d->initialized;
}
inline int nrfx_i2s_start(nrfx_i2s_t *d, const nrfx_i2s_buffers_t *, unsigned)
{
    d->p_reg->enabled = true;
    return 0;
}
inline int nrfx_i2s_next_buffers_set(nrfx_i2s_t *, const nrfx_i2s_buffers_t *)
{
    return 0;
}
inline void mock_i2s_event(nrfx_i2s_t *d, const nrfx_i2s_buffers_t *buffers, std::uint32_t status)
{
    const auto key = irq_lock();
    if (status & NRFX_I2S_STATUS_TRANSFER_STOPPED)
    {
        d->p_reg->enabled = false;
    }
    d->handler(buffers, status);
    irq_unlock(key);
}
inline void nrfx_i2s_stop(nrfx_i2s_t *d)
{
    if (mock_i2s_stop_ready)
    {
        mock_i2s_event(d, nullptr, NRFX_I2S_STATUS_TRANSFER_STOPPED);
    }
}
inline void nrfx_i2s_uninit(nrfx_i2s_t *d)
{
    d->initialized = false;
    ++mock_i2s_uninits;
}
inline void nrfx_i2s_irq_handler(nrfx_i2s_t *)
{
}
