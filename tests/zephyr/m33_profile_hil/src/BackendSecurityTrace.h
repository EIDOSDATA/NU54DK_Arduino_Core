/** @file @brief 보안 실패의 원형 backend 인수와 호출 위치를 보존합니다.
 * SPDX-License-Identifier: MIT
 */
#pragma once

#include <stdint.h>

/** @brief 판정에 사용하지 않는 부팅 이후 보안 callback 진단입니다. */
struct BackendSecurityTrace
{
    uint32_t calls;
    uint32_t failures;
    uint8_t first_hci_reason;
    uint8_t first_security_error;
    uintptr_t first_caller;
};

/** @brief UART 출력 없이 잠금 아래 일관된 진단 사본을 반환합니다. */
BackendSecurityTrace backendSecurityTraceSnapshot() noexcept;
