// SPDX-License-Identifier: MIT
#include "serial_hil.h"
#include <nucode/SerialFabric.h>
#include <variant.h>
#include <cstddef>
#include <string.h>
namespace {
using namespace nucode::arduino;
constexpr unsigned capacity = 1024, guard = 16;
struct alignas(4) Guarded { std::uint8_t before[guard], data[capacity], after[guard]; };
Guarded receive[2]{};
alignas(4) std::uint8_t transmit[capacity * 2]{};
UarteHandle *handle = nullptr;
unsigned bytes = 0, buffers = 0, complete = 0, tx_complete = 0, error = 0, seen = 0;
std::uint32_t seed = 0;
std::uint8_t pattern(std::uint32_t value, unsigned index) {
    // Integer byte oracle also implemented independently by the Host.
    return static_cast<std::uint8_t>((value + 37U * index + (index >> 3U)) ^ (index >> 1U));
}
bool guardsIntact() {
    for (unsigned slot = 0; slot < 2; ++slot) {
        const auto &buffer = receive[slot];
        for (unsigned i = 0; i < guard; ++i)
            if (buffer.before[i] != 0xa5 || buffer.after[i] != 0x5a) return false;
        for (unsigned i = slot < buffers ? bytes : 0; i < capacity; ++i)
            if (buffer.data[i] != 0xcc) return false;
    }
    return true;
}
std::uint32_t start(const std::uint32_t *args, std::uint32_t *out, std::uint32_t &count) {
    if (handle || (args[0] != 20 && args[0] != 21 && args[0] != 22 && args[0] != 30) ||
        (args[1] != 115200 && args[1] != 1000000) || !args[2] || args[2] > capacity ||
        !args[3] || args[3] > 2 || args[5] > 1 || args[6] > 1) return 400;
    auto *candidate = serialFabric().uarte(args[0]);
    if (!candidate) return 600;
    bytes = args[2]; buffers = args[3]; seed = args[4];
    complete = tx_complete = error = seen = 0;
    for (auto &buffer : receive) {
        memset(buffer.before,0xa5,guard);
        memset(buffer.data,0xcc,capacity);
        memset(buffer.after,0x5a,guard);
    }
    for (unsigned i = 0; i < bytes * buffers; ++i) transmit[i] = pattern(seed ^ 0x5aU,i);
    const SerialSignal signals[] = {SerialSignal::txd,SerialSignal::rxd,SerialSignal::rts,SerialSignal::cts};
    const pin_size_t p1[] = {PIN_P1_04,PIN_P1_05,PIN_P1_06,PIN_P1_07};
    const pin_size_t p0[] = {PIN_P0_00,PIN_P0_01,PIN_P0_02,PIN_P0_03};
    SerialSignalPin pins[4]{};
    for (unsigned i = 0; i < 4; ++i) pins[i] = {signals[i],args[0] == 30 ? p0[i] : p1[i]};
    const SerialDmaWorkspace workspaces[] = {
        {receive[0].data,capacity},{receive[1].data,capacity},{transmit,sizeof(transmit)}};
    const SerialFabricConfiguration route{args[0] == 30 ? SerialRouteClass::p0_flexible : SerialRouteClass::p1_flexible,
        SerialElectricalProfile::dap_uart_bridge,pins,args[6] ? 4U : 2U,workspaces,3};
    auto result = candidate->configure({args[1],args[5] ? UarteParity::even : UarteParity::none,args[6] != 0});
    if (result == SerialFabricResult::success) result = candidate->stage(route);
    if (result == SerialFabricResult::success) result = candidate->activate();
    out[0] = static_cast<unsigned>(result); count = 1;
    if (result != SerialFabricResult::success) return 601;
    handle = candidate;
    result = handle->receiveAsync(receive[0].data,bytes,buffers == 2 ? receive[1].data : nullptr,buffers == 2 ? bytes : 0);
    out[0] = static_cast<unsigned>(result);
    return result == SerialFabricResult::success ? 0 : 602;
}
}

void serviceSerial() {
    if (!handle) return;
    UarteEvent event{};
    while (handle->takeEvent(event)) {
        if (event.type == UarteEventType::rx_complete) {
            unsigned slot = event.buffer == receive[0].data ? 0U : event.buffer == receive[1].data ? 1U : 2U;
            if (slot >= buffers || event.transferred != bytes || (seen & (1U << slot))) { error |= 1; continue; }
            seen |= 1U << slot;
            for (unsigned i = 0; i < bytes; ++i)
                if (receive[slot].data[i] != pattern(seed,slot * bytes + i)) error |= 2;
            ++complete;
            if (complete == buffers && !error) {
                if (handle->transmitAsync(transmit,bytes * buffers) != SerialFabricResult::success) error |= 4;
            }
        } else if (event.type == UarteEventType::tx_complete) {
            if (event.buffer != transmit || event.transferred != bytes * buffers || tx_complete) error |= 8;
            ++tx_complete;
        } else if (event.type == UarteEventType::error) error |= 16;
        else if (event.type != UarteEventType::rx_buffer_needed) error |= 32;
    }
    if (!guardsIntact()) error |= 64;
}

std::uint32_t serialOnboard(std::uint32_t opcode, const std::uint32_t *args,
                            std::uint32_t nargs, std::uint32_t *out, std::uint32_t &count) {
    if (opcode == 10 && nargs == 7) return start(args,out,count);
    if (opcode == 11 && nargs == 0 && handle) {
        serviceSerial();
        out[0]=complete; out[1]=tx_complete; out[2]=error; out[3]=seen;
        out[4]=static_cast<unsigned>(handle->bufferState(receive[0].data));
        out[5]=static_cast<unsigned>(handle->bufferState(receive[1].data)); count=6;
        return 0; // A status query reports errors as data; it never declares PASS.
    }
    if (opcode == 12 && nargs == 0 && handle) {
        const auto result=handle->deactivate(100000);
        out[0]=static_cast<unsigned>(result); out[1]=guardsIntact(); count=2;
        if (result != SerialFabricResult::success) return 603;
        handle=nullptr;
        return 0;
    }
    return 400;
}
