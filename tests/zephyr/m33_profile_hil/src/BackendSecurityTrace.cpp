/** @file @brief 원형 보안 callback을 그대로 전달하며 첫 실패의 축약 전 인수를 기록합니다.
 * SPDX-License-Identifier: MIT
 */
#include "BackendSecurityTrace.h"

#include <zephyr/bluetooth/conn.h>
#include <zephyr/kernel.h>

namespace
{
    k_spinlock trace_lock;
    BackendSecurityTrace trace{};
} // namespace

BackendSecurityTrace backendSecurityTraceSnapshot() noexcept
{
    const k_spinlock_key_t key = k_spin_lock(&trace_lock);
    const BackendSecurityTrace snapshot = trace;
    k_spin_unlock(&trace_lock, key);
    return snapshot;
}

extern "C" void __real_bt_conn_security_changed(bt_conn *connection, uint8_t hci_reason,
                                                bt_security_err error);

/** @brief 같은 인수로 원형을 한 번 호출하며 보안 수준·retry·timeout을 변경하지 않습니다. */
extern "C" __attribute__((noinline)) void
__wrap_bt_conn_security_changed(bt_conn *connection, uint8_t hci_reason, bt_security_err error)
{
    const uintptr_t caller = reinterpret_cast<uintptr_t>(__builtin_return_address(0));
    const k_spinlock_key_t key = k_spin_lock(&trace_lock);
    ++trace.calls;
    if (hci_reason != 0U || error != BT_SECURITY_ERR_SUCCESS)
    {
        if (trace.failures == 0U)
        {
            trace.first_hci_reason = hci_reason;
            trace.first_security_error = static_cast<uint8_t>(error);
            trace.first_caller = caller;
        }
        ++trace.failures;
    }
    k_spin_unlock(&trace_lock, key);
    __real_bt_conn_security_changed(connection, hci_reason, error);
}
