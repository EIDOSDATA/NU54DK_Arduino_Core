/** @file @brief Analog 공개 factory와 기존 family 잠금·IRQ 초기화 진입점입니다.
 * SPDX-License-Identifier: MIT
 */
#include "internal/analog/AnalogFabricInternal.h"
namespace nucode::arduino
{
    using namespace internal::analog;
    namespace
    {
        K_MUTEX_DEFINE(analog_fabric_mutex);
        int connectAnalogFabricIrqs()
        {
            IRQ_CONNECT(SAADC_IRQn, IRQ_PRIO_LOWEST, saadcIrq, nullptr, 0);
            IRQ_CONNECT(PWM20_IRQn, IRQ_PRIO_LOWEST, pwm20Irq, nullptr, 0);
            IRQ_CONNECT(PWM21_IRQn, IRQ_PRIO_LOWEST, pwm21Irq, nullptr, 0);
            IRQ_CONNECT(PWM22_IRQn, IRQ_PRIO_LOWEST, pwm22Irq, nullptr, 0);
            return 0;
        }
        SYS_INIT(connectAnalogFabricIrqs, APPLICATION, CONFIG_APPLICATION_INIT_PRIORITY);
    } // namespace
    SaadcFabric &AnalogFabric::saadc() noexcept
    {
        static SaadcFabric handle;
        return handle;
    }

    PwmSequenceFabric *AnalogFabric::pwm(std::uint8_t instance) noexcept
    {
        static PwmSequenceFabric handles[3]{PwmSequenceFabric(20U), PwmSequenceFabric(21U),
                                            PwmSequenceFabric(22U)};
        switch (instance)
        {
        case 20U:
            return &handles[0];
        case 21U:
            return &handles[1];
        case 22U:
            return &handles[2];
        default:
            return nullptr;
        }
    }

    AnalogFabric &analogFabric() noexcept
    {
        static AnalogFabric fabric;
        return fabric;
    }

} // namespace nucode::arduino
namespace nucode::arduino::internal::analog
{
    void lockAnalog() noexcept
    {
        k_mutex_lock(&analog_fabric_mutex, K_FOREVER);
    }
    void unlockAnalog() noexcept
    {
        k_mutex_unlock(&analog_fabric_mutex);
    }
} // namespace nucode::arduino::internal::analog
