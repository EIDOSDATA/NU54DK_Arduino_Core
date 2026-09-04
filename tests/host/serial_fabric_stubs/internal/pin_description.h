#pragma once
#include <api/Common.h>
#include <zephyr/drivers/gpio.h>
namespace nucode::arduino::internal
{
    enum class PinPolicy { normal, input_only, system_reserved, conditional_lfxo, conditional_dap_uart };
    enum class PinCapability : unsigned { digital_input = 1, digital_output = 2, open_drain = 4 };
    struct PinDescription { gpio_dt_spec gpio{}; PinPolicy policy{}; unsigned capabilities{}; pin_size_t canonical_pin{}; };
    inline bool hasPinCapability(unsigned mask, PinCapability capability) { return (mask & static_cast<unsigned>(capability)) != 0; }
    const PinDescription *pinDescription(pin_size_t pin);
    inline pin_size_t canonicalPinId(pin_size_t pin) { return pin; }
}
