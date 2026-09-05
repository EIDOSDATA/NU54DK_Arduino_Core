/** @file @brief STOP 뒤 callback을 발행하는 pinned nrfx TWIM 경계의 fake입니다. */
#pragma once
#include <cstddef>
#include <cstdint>
#include <functional>
#include <zephyr/irq.h>
struct NRF_TWIM_Type
{
};
inline NRF_TWIM_Type mock_twim_regs[4];
#define NRF_TWIM20 (&mock_twim_regs[0])
#define NRF_TWIM21 (&mock_twim_regs[1])
#define NRF_TWIM22 (&mock_twim_regs[2])
#define NRF_TWIM30 (&mock_twim_regs[3])
#define NRFX_TWIM_INSTANCE(reg)                                                                    \
    {                                                                                              \
        reg, false, nullptr, nullptr,                                                              \
        {                                                                                          \
        }                                                                                          \
    }
enum nrf_twim_frequency_t
{
    NRF_TWIM_FREQ_100K,
    NRF_TWIM_FREQ_400K,
    NRF_TWIM_FREQ_1000K
};
enum
{
    NRF_TWIM_TASK_STOP
};
enum nrfx_twim_event_type_t
{
    NRFX_TWIM_EVT_DONE,
    NRFX_TWIM_EVT_ADDRESS_NACK,
    NRFX_TWIM_EVT_DATA_NACK,
    NRFX_TWIM_EVT_OVERRUN,
    NRFX_TWIM_EVT_BUS_ERROR
};
enum
{
    NRFX_TWIM_XFER_TXRX,
    NRFX_TWIM_XFER_TX,
    NRFX_TWIM_XFER_RX,
    NRFX_TWIM_XFER_TXTX
};
struct nrfx_twim_config_t
{
    nrf_twim_frequency_t frequency;
};
#define NRFX_TWIM_DEFAULT_CONFIG(scl, sda)                                                         \
    nrfx_twim_config_t                                                                             \
    {                                                                                              \
    }
struct nrfx_twim_xfer_desc_t
{
    std::uint8_t address;
    std::uint8_t *p_primary_buf;
    std::size_t primary_length;
    std::uint8_t *p_secondary_buf;
    std::size_t secondary_length;
    int type;
};
struct nrfx_twim_event_t
{
    nrfx_twim_event_type_t type;
    nrfx_twim_xfer_desc_t xfer_desc;
};
struct nrfx_twim_t
{
    NRF_TWIM_Type *p_twim;
    bool busy;
    void (*handler)(const nrfx_twim_event_t *, void *);
    void *context;
    nrfx_twim_xfer_desc_t descriptor;
};
inline bool mock_stop_ready = true;
inline int mock_submit_error = 0;
inline std::function<void()> mock_submit;
inline std::function<void()> mock_stop;
inline int nrfx_twim_init(nrfx_twim_t *driver, const nrfx_twim_config_t *,
                          void (*handler)(const nrfx_twim_event_t *, void *), void *context)
{
    driver->handler = handler;
    driver->context = context;
    return 0;
}
inline void nrfx_twim_enable(nrfx_twim_t *)
{
}
inline int nrfx_twim_xfer(nrfx_twim_t *driver, const nrfx_twim_xfer_desc_t *descriptor, unsigned)
{
    driver->descriptor = *descriptor;
    driver->busy = mock_submit_error == 0;
    if (mock_submit)
    {
        mock_submit();
    }
    return mock_submit_error;
}
inline bool nrfx_twim_is_busy(nrfx_twim_t *driver)
{
    return driver->busy;
}
inline void nrfx_twim_uninit(nrfx_twim_t *driver)
{
    driver->busy = false;
}
inline void nrfx_twim_irq_handler(nrfx_twim_t *)
{
}
inline int nrfx_twim_bus_recover(unsigned, unsigned)
{
    return 0;
}
inline void nrfy_twim_task_trigger(NRF_TWIM_Type *, int)
{
    if (mock_stop_ready && mock_stop)
    {
        mock_stop();
    }
}
inline void mock_complete(nrfx_twim_t &driver, nrfx_twim_event_type_t type = NRFX_TWIM_EVT_DONE)
{
    const auto key = irq_lock();
    driver.busy = false;
    ++mock_pending_clears;
    const nrfx_twim_event_t event{type, driver.descriptor};
    driver.handler(&event, driver.context);
    irq_unlock(key);
}
