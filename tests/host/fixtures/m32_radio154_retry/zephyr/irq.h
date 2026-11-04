/** @file @brief 단일 스레드 회귀의 IRQ snapshot 경계입니다.
 * SPDX-License-Identifier: MIT
 */
#pragma once
inline unsigned int irq_lock()
{
    return 0U;
}
inline void irq_unlock(unsigned int key)
{
    static_cast<void>(key);
}
