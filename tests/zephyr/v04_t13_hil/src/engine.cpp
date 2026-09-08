/** @file @brief 고정 시험 ID·10초 lease·실제 측정 시각과 정지 판정을 관리합니다. */
#include "engine.h"
#include "measurement.h"
#include "cases.h"
#include "fixture_gate.h"
#include <zephyr/kernel.h>

namespace
{
    const t13::Case *selected = nullptr;
    v04::FixtureGate gate;
    bool started = false, quiesced = false, healthy = true;
    std::uint32_t expirations = 0U, max_gap_us = 0U;
    std::uint32_t previous_cycle = 0U;
    std::uint64_t start_ms = 0U, stop_ms = 0U, busy_cycles = 0U;
    t13::Timing service_timing;

    /** @brief 정지 증명에 실패하면 gate를 fault로 남기고 GPIO를 강제로 바꾸지 않습니다. */
    bool stop()
    {
        t13::serialQuiesce();
        healthy &= t13::serialHealthy() && t13::streamHealthy();
        const bool serial_stopped = t13::serialStop();
        const bool stream_stopped = t13::streamStop();
        const bool stopped = serial_stopped && stream_stopped;
        healthy &= stopped;
        if (started)
        {
            stop_ms = k_uptime_get();
        }
        started = false;
        gate.close(stopped);
        return stopped;
    }

    void snapshot(std::uint32_t *out, std::uint32_t &count)
    {
        const auto now = static_cast<std::uint64_t>(k_uptime_get());
        const auto elapsed = start_ms == 0U ? 0U : (started ? now : stop_ms) - start_ms;
        out[0] = selected == nullptr ? 0U : selected->id;
        out[1] = gate.claimed() ? 1U : 0U;
        out[2] = started ? 1U : 0U;
        out[3] = quiesced ? 1U : 0U;
        out[4] = healthy && t13::serialHealthy() && t13::streamHealthy() ? 1U : 0U;
        out[5] = expirations;
        out[6] = max_gap_us;
        const std::uint64_t fields[]{now, start_ms, elapsed, k_cyc_to_us_floor64(busy_cycles)};
        for (unsigned index = 0U; index < 4U; ++index)
        {
            out[7U + 2U * index] = static_cast<std::uint32_t>(fields[index]);
            out[8U + 2U * index] = static_cast<std::uint32_t>(fields[index] >> 32U);
        }
        out[15] = t13::serialDrained() ? 1U : 0U;
        count = 16U;
    }
} // namespace

bool t13::claimed()
{
    return gate.claimed();
}

bool t13::running()
{
    return gate.claimed();
}

void t13::service()
{
    if (!gate.fixture())
    {
        return;
    }
    const auto cycle = k_cycle_get_32();
    if (previous_cycle != 0U)
    {
        const auto gap = k_cyc_to_us_floor32(cycle - previous_cycle);
        if (gap > max_gap_us)
        {
            max_gap_us = gap;
        }
    }
    previous_cycle = cycle;
    if (!gate.live(k_uptime_get()))
    {
        ++expirations;
        healthy = false;
        stop();
        return;
    }
    serialService();
    streamService();
    healthy &= serialHealthy() && streamHealthy();
    if (!healthy)
    {
        stop();
    }
    const auto elapsed = static_cast<std::uint32_t>(k_cycle_get_32() - cycle);
    busy_cycles += elapsed;
    service_timing.add(k_cyc_to_us_floor32(elapsed));
}

std::uint32_t t13::command(std::uint32_t opcode, const std::uint32_t *args, std::uint32_t nargs,
                           std::uint32_t *out, std::uint32_t &count)
{
    if (opcode == 1U && nargs == 0U)
    {
        out[0] = CONFIG_NUCODE_V04_HIL_ROLE;
        count = 1U;
        return 0U;
    }
    if (opcode >= 48U && opcode <= 53U)
    {
        return wiringCommand(opcode, args, nargs, out, count);
    }
    if (opcode == 96U && nargs == 0U)
    {
        out[0] = 0x54313300U | CONFIG_NUCODE_T13_HARNESS;
        for (unsigned index = 0U; index < 8U; ++index)
        {
            out[index + 1U] = plan_hash[index];
        }
        /** @brief serial·stream·지연·고정 serial 취소/NACK를 구분하며 전체 복구 완료를 뜻하지 않습니다. */
        out[9] = 15U;
        count = 10U;
        return 0U;
    }
    if (opcode == 99U && nargs == 0U)
    {
        snapshot(out, count);
        return 0U;
    }
    if (opcode == 100U && nargs == 1U && selected != nullptr && args[0] < selected->serial_count)
    {
        serialSnapshot(args[0], out, count);
        return 0U;
    }
    if (opcode == 102U && nargs == 0U)
    {
        out[0] = stop() ? 1U : 0U;
        out[1] = healthy ? 1U : 0U;
        count = 2U;
        return 0U;
    }
    if (opcode == 105U && nargs == 2U && selected != nullptr && args[1] < 3U)
    {
        if (args[0] == UINT32_MAX)
        {
            service_timing.snapshot(out);
            count = 20U;
        }
        else if (args[0] >= 0x100U && args[0] < 0x104U)
        {
            streamTiming(args[0] - 0x100U, args[1], out, count);
        }
        else if (args[0] < selected->serial_count)
        {
            serialTiming(args[0], args[1], out, count);
        }
        return count == 20U ? 0U : 400U;
    }
    if (opcode == 104U && nargs == 1U && selected != nullptr && args[0] < 4U)
    {
        streamSnapshot(args[0], out, count);
        return 0U;
    }
    if (opcode == 106U && nargs == 1U && args[0] <= 1U && !gate.claimed() && !wiringClaimed())
    {
        out[0] = pwmClockPolicy(args[0] != 0U) ? 1U : 0U;
        count = 1U;
        return 0U;
    }
    if (opcode == 107U && nargs == 1U && args[0] <= 4U)
    {
        pwmTraceSnapshot(args[0], out, count);
        return 0U;
    }
    if (opcode == 108U && nargs == 1U && selected != nullptr && args[0] < selected->serial_count)
    {
        serialPinSnapshot(args[0], out, count);
        return count == 7U ? 0U : 400U;
    }
    if (opcode == 110U && nargs == 0U)
    {
        serialFaultSnapshot(out, count);
        return 0U;
    }
    if (opcode == 97U && nargs == 3U && !wiringClaimed() && !gate.claimed())
    {
        selected = nullptr;
        for (const auto &test : cases)
        {
            if (test.id == args[0] && test.harness == CONFIG_NUCODE_T13_HARNESS)
            {
                selected = &test;
                break;
            }
        }
        if (selected == nullptr ||
            !gate.arm(502U, 1U, args[2], 1U, CONFIG_NUCODE_V04_HIL_ROLE, k_uptime_get()))
        {
            return 403U;
        }
        started = quiesced = false;
        healthy = true;
        start_ms = stop_ms = busy_cycles = 0U;
        service_timing = {};
        previous_cycle = max_gap_us = 0U;
        healthy = streamPrepare(*selected, args[1]) && serialPrepare(*selected, args[1]);
        out[0] = healthy ? 1U : 0U;
        if (!healthy)
        {
            stop();
        }
        count = 1U;
        return 0U;
    }
    if (opcode == 103U && nargs == 0U)
    {
        /** @brief 자동 STOP 뒤 renew 거부도 진단 가능한 응답으로 반환합니다. */
        out[0] = gate.renew(k_uptime_get()) ? 1U : 0U;
        count = 1U;
        return 0U;
    }
    if (!gate.live(k_uptime_get()))
    {
        return 403U;
    }
    if (opcode == 109U && nargs == 1U && !started && selected != nullptr &&
        selected->serial_count == 1U && !selected->adc_channels && !selected->pwm_instance &&
        !selected->pdm_instance && !selected->i2s)
    {
        out[0] = serialArmFault(args[0]) ? 1U : 0U;
        count = 1U;
        return 0U;
    }
    if (opcode == 98U && nargs == 0U && !started)
    {
        start_ms = k_uptime_get();
        started = streamStart() && serialStart();
        healthy &= started;
        out[0] = started ? 1U : 0U;
        count = 1U;
        return 0U;
    }
    if (opcode == 101U && nargs == 0U && started)
    {
        serialQuiesce();
        streamQuiesce();
        quiesced = true;
        out[0] = 1U;
        count = 1U;
        return 0U;
    }
    return 400U;
}
