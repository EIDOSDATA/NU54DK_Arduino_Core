#pragma once
#include <cstdint>
struct NRF_GPIO_Type
{
    std::uint32_t PIN_CNF[32]{};
    std::uint32_t out{};
};
extern NRF_GPIO_Type mock_gpio[3];
inline NRF_GPIO_Type *nrf_gpio_pin_port_decode(std::uint32_t *pin)
{
    auto *port = &mock_gpio[*pin / 32];
    *pin %= 32;
    return port;
}
inline std::uint32_t nrf_gpio_pin_out_read(std::uint32_t pin)
{
    return (mock_gpio[pin / 32].out >> (pin % 32)) & 1U;
}
inline void nrf_gpio_pin_write(std::uint32_t pin, std::uint32_t value)
{
    auto &output = mock_gpio[pin / 32].out;
    output = (output & ~(1U << (pin % 32))) | (value << (pin % 32));
}
