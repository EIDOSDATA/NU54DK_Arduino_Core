/** @file @brief SAADC의 READY·buffer·STOP 경계를 주입하는 fake입니다. */
#pragma once
#include <cstddef>
#include <cstdint>
#include <zephyr/irq.h>
struct NRF_SAADC_Type
{
    bool enabled{false};
    bool stopped{false};
};
inline NRF_SAADC_Type mock_saadc_reg;
#define NRF_SAADC (&mock_saadc_reg)
#define SAADC_RESULT_MAXCNT_MAXCNT_Msk 0x7FFFU
enum nrf_saadc_resolution_t
{
    NRF_SAADC_RESOLUTION_8BIT,
    NRF_SAADC_RESOLUTION_10BIT,
    NRF_SAADC_RESOLUTION_12BIT,
    NRF_SAADC_RESOLUTION_14BIT
};
enum nrf_saadc_oversample_t
{
    NRF_SAADC_OVERSAMPLE_DISABLED,
    NRF_SAADC_OVERSAMPLE_2X,
    NRF_SAADC_OVERSAMPLE_4X,
    NRF_SAADC_OVERSAMPLE_8X,
    NRF_SAADC_OVERSAMPLE_16X,
    NRF_SAADC_OVERSAMPLE_32X,
    NRF_SAADC_OVERSAMPLE_64X,
    NRF_SAADC_OVERSAMPLE_128X,
    NRF_SAADC_OVERSAMPLE_256X
};
enum nrf_saadc_gain_t
{
    MOCK_SAADC_GAIN
};
enum
{
    SAADC_CH_CONFIG_GAIN_Gain2 = 0,
    SAADC_CH_CONFIG_GAIN_Gain1,
    SAADC_CH_CONFIG_GAIN_Gain2_3,
    SAADC_CH_CONFIG_GAIN_Gain2_4,
    SAADC_CH_CONFIG_GAIN_Gain2_5,
    SAADC_CH_CONFIG_GAIN_Gain2_6,
    SAADC_CH_CONFIG_GAIN_Gain2_7,
    SAADC_CH_CONFIG_GAIN_Gain2_8
};
enum nrfx_analog_input_t
{
    NRFX_ANALOG_INPUT_DISABLED = 0xFF,
    NRFX_ANALOG_INTERNAL_VDD = 8
};
enum
{
    NRF_SAADC_BURST_DISABLED,
    NRF_SAADC_BURST_ENABLED,
    NRF_SAADC_TASK_SAMPLE,
    NRF_SAADC_EVENT_STARTED,
    NRF_SAADC_EVENT_STOPPED
};
enum
{
    NRFX_SAADC_EVT_READY,
    NRFX_SAADC_EVT_DONE,
    NRFX_SAADC_EVT_BUF_REQ,
    NRFX_SAADC_EVT_CALIBRATEDONE,
    NRFX_SAADC_EVT_FINISHED,
    NRFX_SAADC_EVT_LIMIT
};
struct nrfx_saadc_evt_t
{
    int type;
    struct
    {
        struct
        {
            std::int16_t *p_buffer;
            std::size_t size;
        } done;
    } data;
};
struct nrfx_saadc_channel_t
{
    struct
    {
        nrf_saadc_gain_t gain;
    } channel_config;
};
#define NRFX_SAADC_DEFAULT_CHANNEL_SE(input, index)                                                \
    ((void)(input), (void)(index), nrfx_saadc_channel_t{})
#define NRFX_SAADC_DEFAULT_CHANNEL_DIFFERENTIAL(positive, negative, index)                         \
    ((void)(positive), (void)(negative), (void)(index), nrfx_saadc_channel_t{})
struct nrfx_saadc_adv_config_t
{
    nrf_saadc_oversample_t oversampling;
    int burst;
    unsigned internal_timer_cc;
    bool start_on_end;
};
#define NRFX_SAADC_DEFAULT_ADV_CONFIG                                                              \
    nrfx_saadc_adv_config_t                                                                        \
    {                                                                                              \
    }
#define NRFX_SAADC_INTERNAL_TIMER_INTERVAL_MAX_US 2047U
inline bool mock_saadc_stop_ready = true, mock_saadc_initialized = false;
inline unsigned mock_saadc_uninits = 0;
inline void (*mock_saadc_handler)(const nrfx_saadc_evt_t *) = nullptr;
inline void mock_saadc_event(int type)
{
    const auto key = irq_lock();
    if (type == NRFX_SAADC_EVT_FINISHED)
    {
        mock_saadc_reg.enabled = false;
        mock_saadc_reg.stopped = true;
    }
    const nrfx_saadc_evt_t event{type, {}};
    mock_saadc_handler(&event);
    irq_unlock(key);
}
inline int nrfx_saadc_init(unsigned)
{
    mock_saadc_initialized = true;
    return 0;
}
inline bool nrfx_saadc_init_check()
{
    return mock_saadc_initialized;
}
inline int nrfx_saadc_channels_config(const nrfx_saadc_channel_t *, std::size_t)
{
    return 0;
}
inline unsigned nrfx_saadc_interval_to_cc(unsigned value)
{
    return value;
}
inline int nrfx_saadc_advanced_mode_set(unsigned, nrf_saadc_resolution_t,
                                        const nrfx_saadc_adv_config_t *,
                                        void (*handler)(const nrfx_saadc_evt_t *))
{
    mock_saadc_handler = handler;
    return 0;
}
inline int nrfx_saadc_buffer_set(std::int16_t *, std::size_t)
{
    return 0;
}
inline int nrfx_saadc_mode_trigger()
{
    mock_saadc_reg.enabled = true;
    mock_saadc_reg.stopped = false;
    mock_saadc_event(NRFX_SAADC_EVT_READY);
    return 0;
}
inline int nrfx_saadc_offset_calibrate(void (*)(const nrfx_saadc_evt_t *))
{
    return 0;
}
inline void nrfx_saadc_abort()
{
    if (mock_saadc_stop_ready)
    {
        mock_saadc_event(NRFX_SAADC_EVT_FINISHED);
    }
}
inline void nrfx_saadc_uninit()
{
    mock_saadc_initialized = false;
    ++mock_saadc_uninits;
}
inline void nrfx_saadc_irq_handler()
{
}
inline bool nrf_saadc_enable_check(NRF_SAADC_Type *d)
{
    return d->enabled;
}
inline bool nrf_saadc_event_check(NRF_SAADC_Type *d, int)
{
    return d->stopped;
}
inline void nrf_saadc_event_clear(NRF_SAADC_Type *d, int)
{
    d->stopped = false;
}
inline std::uintptr_t nrf_saadc_task_address_get(NRF_SAADC_Type *, int)
{
    return 0x40000000U;
}
inline std::uintptr_t nrf_saadc_event_address_get(NRF_SAADC_Type *, int)
{
    return 0x40000004U;
}
inline void nrfy_saadc_sample_start(NRF_SAADC_Type *, const void *)
{
}
