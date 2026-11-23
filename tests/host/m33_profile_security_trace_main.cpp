/** @file @brief 보안 진단 wrapper의 원형 호출과 첫 실패 보존을 검사합니다.
 * SPDX-License-Identifier: MIT
 */
#include "BackendSecurityTrace.h"

#include <zephyr/bluetooth/conn.h>
#include <cassert>

namespace
{
    unsigned forwarded = 0U;
    bt_conn *expected_connection = nullptr;
    uint8_t expected_hci_reason = 0U;
    bt_security_err expected_error = BT_SECURITY_ERR_SUCCESS;
} // namespace

extern "C" void __wrap_bt_conn_security_changed(bt_conn *connection, uint8_t hci_reason,
                                                bt_security_err error);

/** @brief 원형 진입 시 정확한 인수와 진단 publication·잠금 해제를 검사합니다. */
extern "C" void __real_bt_conn_security_changed(bt_conn *connection, uint8_t hci_reason,
                                                bt_security_err error)
{
    ++forwarded;
    assert(connection == expected_connection);
    assert(hci_reason == expected_hci_reason);
    assert(error == expected_error);
    assert(backendSecurityTraceSnapshot().calls == forwarded);
}

int main()
{
    bt_conn connection{};
    expected_connection = &connection;
    const BackendSecurityTrace initial = backendSecurityTraceSnapshot();
    assert(initial.calls == 0U && initial.failures == 0U && initial.first_caller == 0U);
    __wrap_bt_conn_security_changed(&connection, expected_hci_reason, expected_error);
    assert(forwarded == 1U && backendSecurityTraceSnapshot().failures == 0U);

    expected_hci_reason = 0x3dU;
    expected_error = BT_SECURITY_ERR_AUTH_FAIL;
    __wrap_bt_conn_security_changed(&connection, expected_hci_reason, expected_error);
    const BackendSecurityTrace first = backendSecurityTraceSnapshot();
    assert(forwarded == 2U && first.calls == 2U && first.failures == 1U);
    assert(first.first_hci_reason == 0x3dU && first.first_security_error == 1U);
    assert(first.first_caller != 0U);

    expected_hci_reason = 0x1fU;
    expected_error = BT_SECURITY_ERR_SUCCESS;
    __wrap_bt_conn_security_changed(&connection, expected_hci_reason, expected_error);
    const BackendSecurityTrace second = backendSecurityTraceSnapshot();
    assert(forwarded == 3U && second.calls == 3U && second.failures == 2U);
    assert(second.first_hci_reason == first.first_hci_reason);
    assert(second.first_security_error == first.first_security_error);
    assert(second.first_caller == first.first_caller);

    expected_hci_reason = 0U;
    expected_error = BT_SECURITY_ERR_AUTH_FAIL;
    __wrap_bt_conn_security_changed(&connection, expected_hci_reason, expected_error);
    assert(forwarded == 4U && backendSecurityTraceSnapshot().failures == 3U);
    expected_error = BT_SECURITY_ERR_SUCCESS;
    expected_hci_reason = 0x1fU;
    __wrap_bt_conn_security_changed(&connection, expected_hci_reason, expected_error);
    assert(forwarded == 5U && backendSecurityTraceSnapshot().failures == 4U);
    return 0;
}
