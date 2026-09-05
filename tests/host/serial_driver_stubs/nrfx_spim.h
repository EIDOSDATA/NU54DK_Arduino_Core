/** @file @brief 고정 nrfx의 descriptor·callback·STOP 경계를 재현하는 fake SPIM입니다. */
#pragma once
#include <cstddef>
#include <cstdint>
#include <functional>
#include <zephyr/irq.h>
struct NRF_SPIM_Type
{
    bool stopped{false};
    bool end{false};
};
inline NRF_SPIM_Type mock_spim_regs[5];
#define NRF_SPIM00 (&mock_spim_regs[0])
#define NRF_SPIM20 (&mock_spim_regs[1])
#define NRF_SPIM21 (&mock_spim_regs[2])
#define NRF_SPIM22 (&mock_spim_regs[3])
#define NRF_SPIM30 (&mock_spim_regs[4])
#define NRFX_SPIM_INSTANCE(reg)                                                                    \
    {                                                                                              \
        reg,                                                                                       \
        {                                                                                          \
        }                                                                                          \
    }
#define NRF_SPIM_PIN_NOT_CONNECTED UINT32_MAX
#define NRF_SPIM_HAS_RXDELAY 0
#define NRF_SPIM_HAS_HW_CSN 0
enum nrf_spim_mode_t
{
    NRF_SPIM_MODE_0,
    NRF_SPIM_MODE_1,
    NRF_SPIM_MODE_2,
    NRF_SPIM_MODE_3
};
enum
{
    NRF_SPIM_BIT_ORDER_LSB_FIRST,
    NRF_SPIM_BIT_ORDER_MSB_FIRST
};
enum
{
    NRF_SPIM_EVENT_STOPPED,
    NRF_SPIM_EVENT_END,
    NRF_SPIM_ALL_INTS_MASK = 0xFF
};
struct nrfx_spim_config_t
{
    std::uint32_t frequency;
    nrf_spim_mode_t mode;
    int bit_order;
    std::uint8_t orc;
};
#define NRFX_SPIM_DEFAULT_CONFIG(sck, mosi, miso, csn)                                             \
    nrfx_spim_config_t                                                                             \
    {                                                                                              \
    }
struct nrfx_spim_xfer_desc_t
{
    const std::uint8_t *p_tx_buffer;
    std::size_t tx_length;
    std::uint8_t *p_rx_buffer;
    std::size_t rx_length;
};
#define NRFX_SPIM_XFER_TRX(tx, txlen, rx, rxlen) {tx, txlen, rx, rxlen}
enum
{
    NRFX_SPIM_EVENT_DONE
};
struct nrfx_spim_event_t
{
    int type;
    nrfx_spim_xfer_desc_t xfer_desc;
};
struct nrfx_spim_control_block_t
{
    bool transfer_in_progress{false};
    void (*handler)(const nrfx_spim_event_t *, void *){nullptr};
    void *context{nullptr};
    nrfx_spim_xfer_desc_t descriptor{};
};
struct nrfx_spim_t
{
    NRF_SPIM_Type *p_reg;
    nrfx_spim_control_block_t cb;
};
inline bool mock_stop_ready = true;
inline int mock_submit_error = 0;
inline std::function<void()> mock_submit;
inline int nrfx_spim_init(nrfx_spim_t *driver, const nrfx_spim_config_t *,
                          void (*handler)(const nrfx_spim_event_t *, void *), void *context)
{
    driver->cb.handler = handler;
    driver->cb.context = context;
    return 0;
}
inline int nrfx_spim_xfer(nrfx_spim_t *driver, const nrfx_spim_xfer_desc_t *descriptor, unsigned)
{
    driver->cb.descriptor = *descriptor;
    driver->cb.transfer_in_progress = mock_submit_error == 0;
    driver->p_reg->stopped = false;
    if (mock_submit)
    {
        mock_submit();
    }
    return mock_submit_error;
}
inline void nrfy_spim_abort(NRF_SPIM_Type *reg, const void *)
{
    reg->stopped = mock_stop_ready;
}
inline bool nrfy_spim_event_check(NRF_SPIM_Type *reg, int event)
{
    return event == NRF_SPIM_EVENT_STOPPED ? reg->stopped : reg->end;
}
inline void nrfy_spim_event_clear(NRF_SPIM_Type *reg, int event)
{
    if (event == NRF_SPIM_EVENT_STOPPED)
    {
        reg->stopped = false;
    }
    else
    {
        reg->end = false;
    }
}
inline void nrfy_spim_int_disable(NRF_SPIM_Type *, unsigned)
{
}
inline void nrfx_spim_abort(nrfx_spim_t *driver)
{
    /** @brief 실제 pinned driver처럼 STOP 실패도 in_progress를 지우므로 안전한 증명이 아닙니다. */
    nrfy_spim_abort(driver->p_reg, nullptr);
    driver->cb.transfer_in_progress = false;
}
inline void nrfx_spim_uninit(nrfx_spim_t *driver)
{
    driver->cb.transfer_in_progress = false;
}
inline void nrfx_spim_irq_handler(nrfx_spim_t *)
{
}
inline void mock_complete(nrfx_spim_t &driver, int type = NRFX_SPIM_EVENT_DONE)
{
    const auto key = irq_lock();
    driver.cb.transfer_in_progress = false;
    const nrfx_spim_event_t event{type, driver.cb.descriptor};
    driver.cb.handler(&event, driver.cb.context);
    irq_unlock(key);
}
