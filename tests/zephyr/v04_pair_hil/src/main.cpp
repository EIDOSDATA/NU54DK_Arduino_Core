// SPDX-License-Identifier: MIT
// SWD controls the test even when both DAP UART level shifters are disconnected.
#include "protocol.h"
#include "serial_hil.h"
#include <nucode/AnalogFabric.h>
#include <nucode/EventFabric.h>
#include <nucode/SerialFabric.h>
#include <variant.h>
#include <zephyr/kernel.h>

extern "C" {
alignas(4) volatile std::uint32_t v04_request[v04::words]{};
alignas(4) volatile std::uint32_t v04_response[v04::words]{};
alignas(4) volatile std::uint32_t v04_identity[16]{};
}

namespace {
using namespace nucode::arduino;
constexpr std::uint32_t role = CONFIG_NUCODE_V04_HIL_ROLE;
constexpr char revision[] = NUCODE_HIL_CORE_REVISION;
static_assert(sizeof(revision) == 41);
alignas(4) std::uint8_t twi_memory[8]{};
alignas(4) std::int16_t adc_memory[32]{};

// All opcodes in this baseline use onboard resources only. External pin drivers
// must not be added without the matching fixture contract and host interlock.
std::uint32_t pmic(const std::uint32_t *args, std::uint32_t *out, std::uint32_t &count) {
    const auto instance = args[0];
    const auto repeats = args[1];
    if ((instance != 20U && instance != 21U && instance != 22U) || repeats == 0 || repeats > 100 ||
        (args[2] != 100000 && args[2] != 400000))
        return 400;
    auto *handle = serialFabric().twim(instance);
    const SerialSignalPin pins[] = {{SerialSignal::sda, PIN_P1_02}, {SerialSignal::scl, PIN_P1_03}};
    const SerialDmaWorkspace workspace{twi_memory, sizeof(twi_memory)};
    const SerialFabricConfiguration configuration{SerialRouteClass::p1_flexible,
        SerialElectricalProfile::pmic_read_only, pins, 2, &workspace, 1};
    if (handle == nullptr || handle->configure({static_cast<TwiFabricFrequency>(args[2])}) != SerialFabricResult::success ||
        handle->stage(configuration) != SerialFabricResult::success || handle->activate() != SerialFabricResult::success)
        return 501;
    out[0] = 0;
    for (std::uint32_t round = 0; round < repeats; ++round) {
        twi_memory[0] = 0x0c;
        twi_memory[1] = 0;
        const auto result = handle->transfer(0x6a, twi_memory, 1, twi_memory + 1, 1, 100000);
        out[3] = static_cast<std::uint32_t>(result);
        if (result != SerialFabricResult::success || twi_memory[1] != 0x41)
            break;
        ++out[0];
        TwiFabricEvent event{};
        while (handle->takeEvent(event)) {} // synchronous call already checked result
    }
    out[1] = twi_memory[1];
    out[2] = static_cast<std::uint32_t>(handle->deactivate(100000));
    count = 4;
    return out[0] == repeats && out[2] == 0 ? 0 : 502;
}

std::uint32_t timerTest(const std::uint32_t *args, std::uint32_t *out, std::uint32_t &count) {
    const auto instance = args[0];
    if (instance != 0 && instance != 10 && (instance < 20 || instance > 24)) return 400;
    auto *timer = eventFabric().timer(instance);
    if (!timer || args[1] >= timer->channelCount() || args[2] < 1000 || args[2] > 10000) return 400;
    if (timer->acquire(1000000) != EventFabricResult::success) return 510;
    const bool started = timer->clear() == EventFabricResult::success && timer->start() == EventFabricResult::success;
    if (started) k_busy_wait(args[2]);
    out[0] = timer->capture(args[1]);
    out[1] = static_cast<std::uint32_t>(timer->stop());
    out[2] = static_cast<std::uint32_t>(timer->release());
    count = 3;
    return started && out[1] == 0 && out[2] == 0 ? 0 : 511;
}

std::uint32_t adcTest(const std::uint32_t *args, std::uint32_t *out, std::uint32_t &count) {
    // Input allowlist: no external pad can be sampled or driven by this opcode.
    if ((args[0] != 0x80 && args[0] != 0x82) || args[1] == 0 || args[1] > 32) return 400;
    auto &adc = analogFabric().saadc();
    const SaadcChannelConfiguration channel{static_cast<SaadcInput>(args[0]), SaadcInput::disabled};
    if (adc.configure({&channel, 1, 12, 1, 0}) != AnalogFabricResult::success ||
        adc.start(adc_memory, args[1], nullptr, 0) != AnalogFabricResult::success) return 520;
    bool ready = false, complete = false, failed = false;
    std::uint32_t sampled = 0;
    const auto deadline = k_uptime_get() + 2000;
    while (!complete && !failed && k_uptime_get() < deadline) {
        SaadcEvent event{};
        while (adc.takeEvent(event)) {
            if (event.type == SaadcEventType::ready) ready = true;
            if (event.type == SaadcEventType::error) failed = true;
            if (event.type == SaadcEventType::buffer_complete) {
                complete = event.buffer == adc_memory && event.samples == args[1];
                failed |= !complete;
            }
        }
        if (ready && sampled < args[1]) {
            if (adc.sample() != AnalogFabricResult::success) failed = true;
            else ++sampled;
        }
        if (!complete) k_sleep(K_MSEC(1));
    }
    out[0] = sampled;
    out[1] = static_cast<std::uint32_t>(adc.stop(100000));
    out[2] = complete ? 1U : 0U;
    if (out[1] != 0) { count = 3; return 522; } // A failed STOP still owns DMA RAM.
    std::int16_t lowest = adc_memory[0], highest = adc_memory[0];
    for (std::size_t index = 0; index < args[1]; ++index) {
        if (adc_memory[index] < lowest) lowest = adc_memory[index];
        if (adc_memory[index] > highest) highest = adc_memory[index];
    }
    out[3] = static_cast<std::uint32_t>(static_cast<std::int32_t>(lowest));
    out[4] = static_cast<std::uint32_t>(static_cast<std::int32_t>(highest));
    count = 5;
    return complete && !failed && out[1] == 0 ? 0 : 521;
}

std::uint32_t dispatch(std::uint32_t opcode, const std::uint32_t *args,
                       std::uint32_t nargs, std::uint32_t *out, std::uint32_t &count) {
    if (opcode == 1 && nargs == 4) {
        count = 4;
        for (unsigned index = 0; index < count; ++index) out[index] = args[index] ^ (0xa5000000U | role);
        return 0;
    }
    if (opcode == 2 && nargs == 3) return pmic(args, out, count);
    if (opcode == 3 && nargs == 3) return timerTest(args, out, count);
    if (opcode == 4 && nargs == 2) return adcTest(args, out, count);
    if (opcode >= 10 && opcode <= 12) return serialOnboard(opcode,args,nargs,out,count);
    return 400;
}
} // namespace

int main() {
    v04_identity[1] = v04::version;
    v04_identity[2] = role;
    for (unsigned index = 0; index < 10; ++index) {
        std::uint32_t word = 0;
        for (unsigned byte = 0; byte < 4; ++byte)
            word |= static_cast<std::uint32_t>(revision[index * 4 + byte]) << (byte * 8);
        v04_identity[4 + index] = word;
    }
    __DMB();
    v04_identity[0] = v04::magic;
    std::uint32_t last_sequence = 0;
    std::uint32_t session_nonce[4]{};
    while (true) {
        serviceSerial();
        if (v04_request[0] != v04::magic) { k_sleep(K_MSEC(1)); continue; }
        __DMB();
        std::uint32_t request[v04::words]{}, response[v04::words]{};
        for (unsigned index = 0; index < v04::words; ++index) request[index] = v04_request[index];
        v04_request[0] = 0;
        for (unsigned index = 0; index < 9; ++index) response[index] = request[index];
        bool same_nonce = true;
        for (unsigned index = 0; index < 4; ++index)
            same_nonce &= request[5 + index] == session_nonce[index];
        if (!v04::valid(request, role) || request[2] != last_sequence + 1 || (last_sequence != 0 && !same_nonce)) {
            response[9] = 409;
        } else {
            for (unsigned index = 0; index < 4; ++index) session_nonce[index] = request[5 + index];
            last_sequence = request[2];
            response[9] = dispatch(request[4], request + 11, request[10], response + 11, response[10]);
        }
        response[31] = v04::checksum(response);
        v04_response[0] = 0;
        for (unsigned index = 1; index < v04::words; ++index) v04_response[index] = response[index];
        __DMB();
        v04_response[0] = v04::magic;
    }
}
