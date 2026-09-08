/** @file @brief parity와 UART 반환 뒤의 GPIO break 주입을 정상 전송과 분리합니다. */
#pragma once
#include "model.h"
#include <nucode/SerialFabric.h>

namespace t13
{
    bool uartFaultPolicy(unsigned mode);
    bool uartFaultPrepare(const Case &test, const Endpoint &endpoint);
    bool uartFaultArm();
    bool uartFaultTransmitAllowed();
    bool uartFaultReceiveAllowed();
    void uartFaultReceiveSuppressed(bool pending);
    nucode::arduino::UarteParity uartFaultParity();
    void uartFaultSubmitted(std::uint32_t cycle);
    void uartFaultEvent(const nucode::arduino::UarteEvent &event, bool guards);
    bool uartFaultStop(bool serial_stopped);
    bool uartFaultBreakReady();
    bool uartFaultBreakPrepare();
    bool uartFaultBreakPulse();
    bool serialBreakPrepare();
    void uartFaultSnapshot(std::uint32_t *out, std::uint32_t &count);
} // namespace t13
