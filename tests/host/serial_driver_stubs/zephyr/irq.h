/** @file @brief 단일 CPU IRQ 배타성을 실제 recursive mutex로 모사합니다. */
#pragma once
#include <zephyr/kernel.h>
inline unsigned irq_lock()
{
    mock_irq_mutex.lock();
    return 0;
}
inline void irq_unlock(unsigned)
{
    mock_irq_mutex.unlock();
}
inline void irq_enable(unsigned)
{
}
inline void irq_disable(unsigned)
{
}
#define NRFX_IRQ_NUMBER_GET(reg) 0U
inline unsigned mock_pending_clears = 0;
enum IRQn_Type
{
    MockSerialIRQ = 0
};
inline void mock_pending_clear(IRQn_Type)
{
    ++mock_pending_clears;
}
#define NRFY_IRQ_PENDING_CLEAR(irq) mock_pending_clear(irq)
