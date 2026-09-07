/**
 * @file common_i2s_hil.cpp
 * @brief 3개 DMA slot을 순환하며 초기 4개와 측정 100개 buffer를 보존합니다.
 * @note 이후 Host STOP까지 공급한 tail은 측정 100개에 더하지 않습니다.
 * SPDX-License-Identifier: MIT
 */
#include "common_i2s_hil.h"
#include "common_qdec_hil.h"
#include "common_gpio_hil.h"
#include "common_wiring.h"
#include "fixture_gate.h"
#include "fixture_hil.h"
#include "pwm_capture_hil.h"
#include "signal_hil.h"
#include "wiring_hil.h"
#include "serial_hil.h"
#include "i2s_stream_oracle.h"
#include <nucode/StreamFabric.h>
#include <variant.h>
#include <hal/nrf_gpio.h>
#include <zephyr/kernel.h>

namespace
{
    using namespace nucode::arduino;
    constexpr std::uint32_t role = CONFIG_NUCODE_V04_HIL_ROLE;
    constexpr std::uint32_t slots = 3U, measured_end = 104U, guard = 0xA55A9669U;
    struct alignas(4) Buffer
    {
        std::uint32_t memory[1032];
        /** @brief 요청 길이 직후에 16-byte guard를 두며 capacity 끝으로 미루지 않습니다. */
        std::uint32_t *data()
        {
            return memory + 4U;
        }
    } rx[slots]{}, tx[slots]{};
    v04::FixtureGate gate;
    I2sFabric *i2s = nullptr;
    v04::I2sStreamOracle oracle;
    bool prepared = false, started = false, receive = false, transmit = false;
    bool active_slots[slots]{};
    std::uint32_t completed = 0U, queued = 0U, error = 0U, rate = 0U, width = 0U;
    std::uint32_t channels = 0U, words = 0U, seed = 0U, origin = 0U, max_queue_us = 0U;
    std::uint32_t lease_expirations = 0U;
    std::uint32_t statistics[measured_end][5]{};

    /** @brief slot의 앞뒤 guard를 요청 길이에 맞추어 설정합니다. */
    void initialize(Buffer &buffer)
    {
        for (unsigned index = 0U; index < 4U; ++index)
        {
            buffer.memory[index] = buffer.memory[words + 4U + index] = guard;
        }
    }

    /** @brief 측정/대기/활성 slot 모두의 앞뒤 guard를 읽습니다. */
    bool guards()
    {
        for (unsigned slot = 0U; slot < slots; ++slot)
        {
            for (unsigned index = 0U; index < 4U; ++index)
            {
                if (rx[slot].memory[index] != guard ||
                    rx[slot].memory[words + 4U + index] != guard ||
                    tx[slot].memory[index] != guard || tx[slot].memory[words + 4U + index] != guard)
                {
                    return false;
                }
            }
        }
        return true;
    }

    /** @brief 순환 slot에 다음 고유 전역 word 위치를 채웁니다. */
    void fill(std::uint32_t slot, std::uint32_t index)
    {
        for (unsigned word = 0U; word < words; ++word)
        {
            tx[slot].data()[word] = v04::i2sStreamPattern(seed, index * words + word);
            rx[slot].data()[word] = 0xCCCCCCCCU;
        }
    }

    /** @brief 한쪽 DMA를 비활성화할 때는 실제 nullptr로 전달합니다. */
    I2sBuffers buffers(std::uint32_t slot)
    {
        return {receive ? rx[slot].data() : nullptr, transmit ? tx[slot].data() : nullptr, words};
    }

    /** @brief STOP이 증명된 뒤에만 stream과 pin을 반환합니다. */
    bool stop()
    {
        if (i2s != nullptr && i2s->state() == StreamFabricState::faulted)
        {
            return false;
        }
        if (i2s != nullptr && (i2s->state() == StreamFabricState::active ||
                               i2s->state() == StreamFabricState::stopping))
        {
            if (i2s->stop(100000U) != StreamFabricResult::success)
            {
                return false;
            }
            for (unsigned pin = 4U; pin <= 7U; ++pin)
            {
                nrf_gpio_cfg_input(NRF_GPIO_PIN_MAP(1, pin), NRF_GPIO_PIN_NOPULL);
            }
        }
        started = prepared = false;
        i2s = nullptr;
        return true;
    }

    /** @brief 완료와 재사용 전에 반환 pointer·크기·guard를 검증합니다. */
    void released(const I2sBuffers &result)
    {
        const auto slot = completed % slots;
        const auto expected = buffers(slot);
        if (!active_slots[slot] || result.receive != expected.receive ||
            result.transmit != expected.transmit || result.words != words || !guards())
        {
            error = 2U;
            return;
        }
        active_slots[slot] = false;
        if (completed < measured_end)
        {
            const auto mask = width == 24U ? 0xFFFFFFU : UINT32_MAX;
            auto crc = UINT32_MAX;
            for (unsigned index = 0U; index < words; ++index)
            {
                if (receive)
                {
                    const auto raw = result.receive[index];
                    oracle.consume(raw);
                    crc = v04::i2sCrcWord(crc, raw & mask);
                }
            }
            statistics[completed][0] = completed;
            statistics[completed][1] = k_cyc_to_us_floor32(k_cycle_get_32() - origin);
            statistics[completed][2] = receive ? crc ^ UINT32_MAX : 0U;
            statistics[completed][3] = receive ? result.receive[0] & mask : 0U;
            statistics[completed][4] = receive ? result.receive[words - 1U] & mask : 0U;
            if (oracle.mismatches != 0U)
            {
                error = 3U;
            }
        }
        ++completed;
    }

    /** @brief 측정과 tail, 실제 단방향 설정 및 출력 방향을 구분하여 반환합니다. */
    void snapshot(std::uint32_t *out, std::uint32_t &count)
    {
        std::uint32_t direction = 0U;
        for (unsigned net = 0U; net < v04::wiring_count; ++net)
        {
            direction |=
                (nrf_gpio_pin_dir_get(v04::wiringPin(role, net)) == NRF_GPIO_PIN_DIR_OUTPUT ? 1U
                                                                                            : 0U)
                << net;
        }
        const std::uint32_t values[]{prepared,
                                     started,
                                     completed,
                                     queued,
                                     completed < measured_end ? completed : measured_end,
                                     error,
                                     guards(),
                                     oracle.padding,
                                     receive,
                                     transmit,
                                     oracle.samples,
                                     oracle.mismatches,
                                     max_queue_us,
                                     rate,
                                     width,
                                     channels,
                                     words,
                                     direction,
                                     lease_expirations,
                                     gate.live(k_uptime_get())};
        for (unsigned index = 0U; index < 20U; ++index)
        {
            out[index] = values[index];
        }
        count = 20U;
    }
} // namespace

bool commonI2sClaimed()
{
    return gate.claimed();
}

bool commonI2sNeedsPolling()
{
    return started;
}

void serviceCommonI2s()
{
    if (gate.fixture() && !gate.live(k_uptime_get()))
    {
        ++lease_expirations;
        error = 1U;
        gate.close(stop());
    }
    if (!started || i2s == nullptr)
    {
        return;
    }
    I2sEvent event{};
    while (i2s->takeEvent(event))
    {
        if (event.type == I2sEventType::buffers_complete)
        {
            released(event.released);
        }
        else if (event.type == I2sEventType::buffers_needed && error == 0U)
        {
            const auto slot = queued % slots;
            if (active_slots[slot])
            {
                error = 4U;
                break;
            }
            const auto before = k_cycle_get_32();
            fill(slot, queued);
            const auto result = i2s->queueBuffers(buffers(slot));
            const auto elapsed = k_cyc_to_us_floor32(k_cycle_get_32() - before);
            if (elapsed > max_queue_us)
            {
                max_queue_us = elapsed;
            }
            if (result != StreamFabricResult::success)
            {
                error = 5U;
                break;
            }
            active_slots[slot] = true;
            ++queued;
        }
        else if (event.type == I2sEventType::underrun || event.type == I2sEventType::error ||
                 event.type == I2sEventType::stopped)
        {
            error = 6U;
        }
        if (error != 0U)
        {
            break;
        }
    }
    if (error != 0U)
    {
        gate.close(stop());
    }
}

std::uint32_t commonI2sCommand(std::uint32_t opcode, const std::uint32_t *args, std::uint32_t nargs,
                               std::uint32_t *out, std::uint32_t &count)
{
    serviceCommonI2s();
    if (opcode == 88U && nargs == 4U)
    {
        if (fixtureClaimed() || signalClaimed() || pwmCaptureClaimed() || wiringClaimed() ||
            commonGpioClaimed() || commonQdecClaimed() || onboardSerialActive() ||
            args[0] != 530U || !gate.arm(args[0], args[1], args[2], args[3], role, k_uptime_get()))
        {
            return 403U;
        }
        error = completed = queued = max_queue_us = 0U;
        out[0] = 530U;
        out[1] = 10000U;
        count = 2U;
        return 0U;
    }
    if (opcode == 89U && nargs == 0U)
    {
        const bool result = stop();
        gate.close(result);
        snapshot(out, count);
        return result ? 0U : 780U;
    }
    if (opcode == 92U && nargs == 0U)
    {
        snapshot(out, count);
        return 0U;
    }
    if (opcode == 93U && nargs == 2U && args[1] > 0U && args[1] <= 4U && args[0] < measured_end &&
        args[1] <= measured_end - args[0] && args[0] + args[1] <= completed)
    {
        for (unsigned index = 0U; index < args[1]; ++index)
        {
            for (unsigned field = 0U; field < 5U; ++field)
            {
                out[index * 5U + field] = statistics[args[0] + index][field];
            }
        }
        count = args[1] * 5U;
        return 0U;
    }
    if (opcode == 95U && nargs == 0U)
    {
        out[0] = oracle.first_index;
        out[1] = oracle.first_expected;
        out[2] = oracle.first_actual;
        out[3] = error;
        count = 4U;
        return 0U;
    }
    if (!gate.live(k_uptime_get()))
    {
        return 403U;
    }
    if (opcode == 94U && nargs == 0U)
    {
        out[0] = gate.renew(k_uptime_get()) ? 0U : 1U;
        count = 1U;
        return 0U;
    }
    if (opcode == 90U && nargs == 6U && !prepared && !started &&
        (args[0] == 16000U || args[0] == 48000U) &&
        (args[1] == 8U || args[1] == 16U || args[1] == 24U || args[1] == 32U) && args[2] <= 2U &&
        (args[3] == 32U || args[3] == 256U || args[3] == 1024U) && args[4] >= 1U && args[4] <= 3U)
    {
        rate = args[0];
        width = args[1];
        channels = args[2];
        words = args[3];
        transmit = (args[4] & (role == 1U ? 1U : 2U)) != 0U;
        receive = (args[4] & (role == 1U ? 2U : 1U)) != 0U;
        seed = args[5] ^ (role == 1U ? 0U : 0x5A5A5A5AU);
        oracle.reset(args[5] ^ (role == 1U ? 0x5A5A5A5AU : 0U), width, channels);
        for (unsigned slot = 0U; slot < slots; ++slot)
        {
            initialize(rx[slot]);
            initialize(tx[slot]);
            active_slots[slot] = false;
        }
        i2s = streamFabric().i2s(20U);
        const I2sConfiguration configuration{PIN_P1_04,
                                             PIN_P1_05,
                                             0xFFU,
                                             static_cast<pin_size_t>(transmit ? PIN_P1_06 : 0xFFU),
                                             static_cast<pin_size_t>(receive ? PIN_P1_07 : 0xFFU),
                                             rate,
                                             static_cast<I2sSampleWidth>(width),
                                             static_cast<I2sChannels>(channels),
                                             gate.controller() == role,
                                             StreamElectricalProfile::dap_uart_disabled};
        prepared = i2s != nullptr && i2s->configure(configuration) == StreamFabricResult::success;
        out[0] = prepared ? 0U : 1U;
        count = 1U;
        return 0U;
    }
    if (opcode == 91U && nargs == 0U && prepared && !started)
    {
        fill(0U, 0U);
        origin = k_cycle_get_32();
        started = i2s->start(buffers(0U)) == StreamFabricResult::success;
        active_slots[0] = started;
        queued = started ? 1U : 0U;
        out[0] = started ? 0U : 1U;
        count = 1U;
        return 0U;
    }
    return 400U;
}
