/** @file @brief SPIS semaphore 선행 예약과 완료 순서를 재현하는 fake nrfx입니다. */
#pragma once

#include <cstddef>
#include <cstdint>
#include <vector>

#include <hal/nrf_gpio.h>

struct NRF_SPIS_Type
{
    bool rx_started{false};
    bool tx_started{false};
    std::uint32_t interrupt_mask{0U};
};

enum nrf_spis_event_t
{
    NRF_SPIS_EVENT_RXSTARTED,
    NRF_SPIS_EVENT_TXSTARTED,
};

inline constexpr std::uint32_t NRF_SPIS_INT_RXREADY_MASK = 1U;
inline constexpr std::uint32_t NRF_SPIS_INT_TXREADY_MASK = 2U;

inline bool nrf_spis_event_check(const NRF_SPIS_Type *registers, nrf_spis_event_t event)
{
    return event == NRF_SPIS_EVENT_RXSTARTED ? registers->rx_started : registers->tx_started;
}

inline void nrf_spis_event_clear(NRF_SPIS_Type *registers, nrf_spis_event_t event)
{
    if (event == NRF_SPIS_EVENT_RXSTARTED)
    {
        registers->rx_started = false;
    }
    else
    {
        registers->tx_started = false;
    }
}

inline void nrf_spis_int_enable(NRF_SPIS_Type *registers, std::uint32_t mask)
{
    registers->interrupt_mask |= mask;
}

inline NRF_SPIS_Type mock_spis_regs[5];

#define NRF_SPIS00 (&mock_spis_regs[0])
#define NRF_SPIS20 (&mock_spis_regs[1])
#define NRF_SPIS21 (&mock_spis_regs[2])
#define NRF_SPIS22 (&mock_spis_regs[3])
#define NRF_SPIS30 (&mock_spis_regs[4])
#define NRFX_SPIS_INSTANCE(reg)                                                                    \
    {                                                                                              \
        reg,                                                                                       \
        {                                                                                          \
        }                                                                                          \
    }

enum nrf_spis_mode_t
{
    NRF_SPIS_MODE_0,
    NRF_SPIS_MODE_1,
    NRF_SPIS_MODE_2,
    NRF_SPIS_MODE_3,
};

enum
{
    NRF_SPIS_BIT_ORDER_LSB_FIRST,
    NRF_SPIS_BIT_ORDER_MSB_FIRST,
};

struct nrfx_spis_config_t
{
    nrf_spis_mode_t mode{NRF_SPIS_MODE_0};
    int bit_order{NRF_SPIS_BIT_ORDER_MSB_FIRST};
    std::uint8_t orc{0U};
    nrf_gpio_pin_pull_t csn_pullup{NRF_GPIO_PIN_NOPULL};
};

#define NRFX_SPIS_DEFAULT_CONFIG(sck, mosi, miso, csn)                                             \
    nrfx_spis_config_t                                                                             \
    {                                                                                              \
    }

enum
{
    NRFX_SPIS_BUFFERS_SET_DONE,
    NRFX_SPIS_XFER_DONE,
};

struct nrfx_spis_event_t
{
    int evt_type;
    std::size_t tx_amount;
    std::size_t rx_amount;
};

struct MockSpisBufferSet
{
    const std::uint8_t *tx;
    std::size_t tx_size;
    std::uint8_t *rx;
    std::size_t rx_size;
};

struct nrfx_spis_control_block_t
{
    void (*handler)(const nrfx_spis_event_t *, void *){nullptr};
    void *context{nullptr};
    bool initialized{false};
};

struct nrfx_spis_t
{
    NRF_SPIS_Type *p_reg;
    nrfx_spis_control_block_t cb;
};

inline std::vector<MockSpisBufferSet> mock_spis_buffer_sets;
inline int mock_spis_set_result = 0;

inline int nrfx_spis_init(nrfx_spis_t *driver, const nrfx_spis_config_t *,
                          void (*handler)(const nrfx_spis_event_t *, void *), void *context)
{
    driver->cb.handler = handler;
    driver->cb.context = context;
    driver->cb.initialized = true;
    return 0;
}

inline void nrfx_spis_uninit(nrfx_spis_t *driver)
{
    driver->cb.initialized = false;
}

inline int nrfx_spis_buffers_set(nrfx_spis_t *, const std::uint8_t *tx, std::size_t tx_size,
                                 std::uint8_t *rx, std::size_t rx_size)
{
    mock_spis_buffer_sets.push_back({tx, tx_size, rx, rx_size});
    return mock_spis_set_result;
}

inline void nrfx_spis_irq_handler(nrfx_spis_t *)
{
}

inline void mock_spis_buffers_armed(nrfx_spis_t &driver)
{
    const nrfx_spis_event_t event{NRFX_SPIS_BUFFERS_SET_DONE, 0U, 0U};
    driver.cb.handler(&event, driver.cb.context);
}

inline void mock_spis_transfer_done(nrfx_spis_t &driver, std::size_t tx_amount,
                                    std::size_t rx_amount)
{
    const nrfx_spis_event_t event{NRFX_SPIS_XFER_DONE, tx_amount, rx_amount};
    driver.cb.handler(&event, driver.cb.context);
}

inline void mock_spis_rx_started(nrfx_spis_t &driver)
{
    driver.p_reg->rx_started = true;
}

inline void mock_spis_tx_started(nrfx_spis_t &driver)
{
    driver.p_reg->tx_started = true;
}
