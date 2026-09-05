/** @file @brief 경로 Host 검사의 pinctrl 경계입니다. */
#pragma once
#include <cstdint>
using pinctrl_soc_pin_t = std::uint32_t;
inline constexpr std::uint8_t PINCTRL_STATE_DEFAULT = 0;
inline constexpr std::uint8_t PINCTRL_STATE_SLEEP = 1;
struct pinctrl_state
{
    const pinctrl_soc_pin_t *pins;
    std::uint8_t pin_cnt;
    std::uint8_t id;
};
struct pinctrl_dev_config
{
    const pinctrl_state *states;
    std::uint8_t state_cnt;
};
int pinctrl_update_states(pinctrl_dev_config *, const pinctrl_state *, std::uint8_t);
