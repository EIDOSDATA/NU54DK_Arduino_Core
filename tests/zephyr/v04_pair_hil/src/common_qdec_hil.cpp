/**
 * @file common_qdec_hil.cpp
 * @brief 고정 두 선의 유한 파형과 QDEC read/clear/restart를 검사합니다.
 * @note ACC는 -1024..1023, ACCDBL은 0..15이므로 5ms마다 읽어 별도 합산합니다.
 * SPDX-License-Identifier: MIT
 */
#include "common_qdec_hil.h"
#include "common_gpio_hil.h"
#include "common_wiring.h"
#include "fixture_gate.h"
#include "fixture_hil.h"
#include "pwm_capture_hil.h"
#include "signal_hil.h"
#include "wiring_hil.h"
#include "serial_hil.h"
#include "qdec_waveform.h"
#include "qdec_observer.h"
#include <internal/IoResourceManager.h>
#include <internal/pin_description.h>
#include <nucode/StreamFabric.h>
#include <variant.h>
#include <hal/nrf_gpio.h>
#include <hal/nrf_qdec.h>
#include <zephyr/kernel.h>

namespace
{
    using namespace nucode::arduino;
    using namespace nucode::arduino::internal;
    constexpr std::uint32_t role = CONFIG_NUCODE_V04_HIL_ROLE;
    constexpr std::uint32_t phase_mask = (1U << 14U) | (1U << 10U);
    v04::FixtureGate gate;
    QdecFabric *qdec = nullptr;
    IoResourceToken generator_token{};
    bool prepared = false, generating = false;
    std::uint32_t instance = 0U, emitted = 0U, target_steps = 0U, mode = 0U;
    std::uint32_t interval_cycles = 0U, last_step = 0U, last_read = 0U;
    std::uint32_t doubles = 0U, reads = 0U, max_read_gap = 0U, error = 0U;
    std::uint32_t lease_expirations = 0U;
    std::int32_t accumulated = 0;
    v04::QdecObserver observer;
    std::uint32_t first_mismatch[20]{};
    bool mismatch_recorded = false, phase_checked = false;

    /** @brief 두 입력을 같은 port IN 값에서 읽어 순차 GPIO 읽기 사이 전이를 피합니다. */
    std::uint32_t inputPhase()
    {
        std::uint32_t pin = NRF_GPIO_PIN_MAP(1, 14);
        const auto value = nrf_gpio_pin_port_decode(&pin)->IN;
        return ((value >> 13U) & 2U) | ((value >> 10U) & 1U);
    }

    /** @brief 읽기 전용 register와 독립 GPIO 누산을 보존하며 hardware 값은 보정하지 않습니다. */
    void diagnostic(std::uint32_t *out)
    {
        const auto *const reg = instance == 20U ? NRF_QDEC20 : NRF_QDEC21;
        const auto now = k_cycle_get_32();
        const std::uint32_t values[]{now,
                                     static_cast<std::uint32_t>(observer.steps),
                                     observer.doubles,
                                     observer.transitions,
                                     k_cyc_to_us_floor32(observer.max_gap),
                                     observer.phase,
                                     k_cyc_to_us_floor32(now - observer.last_edge),
                                     static_cast<std::uint32_t>(accumulated),
                                     static_cast<std::uint32_t>(reg->ACC),
                                     static_cast<std::uint32_t>(reg->ACCREAD),
                                     reg->ACCDBL,
                                     reg->ACCDBLREAD,
                                     reads,
                                     k_cyc_to_us_floor32(now - last_read),
                                     static_cast<std::uint32_t>(reg->SAMPLE),
                                     reg->SAMPLEPER,
                                     reg->SHORTS,
                                     reg->ENABLE,
                                     reg->INTENSET,
                                     reg->DBFEN};
        for (unsigned index = 0U; index < 20U; ++index)
        {
            out[index] = values[index];
        }
    }

    /** @brief 안정된 phase에서 최초 불일치 원본만 고정해 후속 상태가 덮어쓰지 못하게 합니다. */
    void observeInput(std::uint32_t now)
    {
        const auto before = observer.transitions;
        observer.sample(now, inputPhase());
        if (before != observer.transitions)
        {
            phase_checked = false;
        }
        if (!phase_checked && now - observer.last_edge >= k_us_to_cyc_ceil32(1024U))
        {
            phase_checked = true;
            const auto *const reg = instance == 20U ? NRF_QDEC20 : NRF_QDEC21;
            if (!mismatch_recorded && (accumulated + nrf_qdec_acc_get(reg) != observer.steps ||
                                       doubles + nrf_qdec_accdbl_get(reg) != observer.doubles))
            {
                diagnostic(first_mismatch);
                mismatch_recorded = true;
            }
        }
    }

    /** @brief 다른 port 출력 latch를 보존하며 두 phase를 한 번의 OUT 쓰기로 바꿉니다. */
    void phase(std::uint32_t state)
    {
        const std::uint32_t bits =
            ((state & 2U) ? 1U << 14U : 0U) | ((state & 1U) ? 1U << 10U : 0U);
        std::uint32_t pin = NRF_GPIO_PIN_MAP(1, 14);
        auto *const port = nrf_gpio_pin_port_decode(&pin);
        port->OUT = (port->OUT & ~phase_mask) | bits;
        __DMB();
    }

    /** @brief hardware read가 반환한 두 누산기만 별도 합산하며 double overflow를 방지합니다. */
    bool drain()
    {
        if (qdec == nullptr || qdec->state() != StreamFabricState::active)
        {
            return false;
        }
        const auto now = k_cycle_get_32();
        const auto gap = now - last_read;
        if (gap > max_read_gap)
        {
            max_read_gap = gap;
        }
        last_read = now;
        QdecEvent event{};
        const auto result = qdec->read(event);
        if (result != StreamFabricResult::success || event.driver_error != 0 ||
            event.accumulated <= -1024 || event.accumulated >= 1023 ||
            event.double_transitions >= 15U || k_cyc_to_us_floor32(gap) > 15000U)
        {
            error = 2U;
            return false;
        }
        accumulated += event.accumulated;
        doubles += event.double_transitions;
        ++reads;
        return true;
    }

    /** @brief 파형을 멈추고 QDEC와 generator의 소유권을 입력 상태로 반환합니다. */
    bool stop()
    {
        generating = false;
        if (qdec != nullptr && qdec->state() == StreamFabricState::faulted)
        {
            return false;
        }
        if (qdec != nullptr && qdec->state() == StreamFabricState::active)
        {
            if (qdec->stop() != StreamFabricResult::success)
            {
                return false;
            }
            nrf_gpio_cfg_input(NRF_GPIO_PIN_MAP(1, 14), NRF_GPIO_PIN_NOPULL);
            nrf_gpio_cfg_input(NRF_GPIO_PIN_MAP(1, 10), NRF_GPIO_PIN_NOPULL);
        }
        if (generator_token.active)
        {
            phase(0U);
            nrf_gpio_cfg_input(NRF_GPIO_PIN_MAP(1, 14), NRF_GPIO_PIN_NOPULL);
            nrf_gpio_cfg_input(NRF_GPIO_PIN_MAP(1, 10), NRF_GPIO_PIN_NOPULL);
            if (releaseIoResources(generator_token) != IoResourceResult::success)
            {
                return false;
            }
        }
        prepared = false;
        qdec = nullptr;
        return true;
    }

    /** @brief 두 역할의 실제 준비/생성/누산 상태와 전체 net 방향을 반환합니다. */
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
        const std::uint32_t values[]{instance,
                                     prepared,
                                     generating,
                                     emitted,
                                     target_steps,
                                     static_cast<std::uint32_t>(accumulated),
                                     doubles,
                                     reads,
                                     k_cyc_to_us_floor32(max_read_gap),
                                     error,
                                     lease_expirations,
                                     direction,
                                     gate.live(k_uptime_get()),
                                     nrf_gpio_pin_read(NRF_GPIO_PIN_MAP(1, 14)),
                                     nrf_gpio_pin_read(NRF_GPIO_PIN_MAP(1, 10)),
                                     qdec != nullptr && qdec->state() == StreamFabricState::active};
        for (unsigned index = 0U; index < 16U; ++index)
        {
            out[index] = values[index];
        }
        count = 16U;
    }
} // namespace

bool commonQdecClaimed()
{
    return gate.claimed();
}

bool commonQdecNeedsPolling()
{
    return prepared;
}

void serviceCommonQdec()
{
    if (gate.fixture() && !gate.live(k_uptime_get()))
    {
        ++lease_expirations;
        error = 1U;
        gate.close(stop());
    }
    if (!prepared || error != 0U)
    {
        return;
    }
    const auto now = k_cycle_get_32();
    if (role == 1U)
    {
        observeInput(now);
    }
    if (role == 1U && now - last_read >= k_us_to_cyc_ceil32(5000U))
    {
        if (!drain())
        {
            gate.close(stop());
        }
    }
    if (role == 2U && generating && now - last_step >= interval_cycles)
    {
        last_step = now;
        phase(mode == 2U ? (emitted % 2U == 0U ? 3U : 0U) : v04::qdecState(emitted, mode == 1U));
        ++emitted;
        if (emitted == target_steps)
        {
            generating = false;
        }
    }
}

std::uint32_t commonQdecCommand(std::uint32_t opcode, const std::uint32_t *args,
                                std::uint32_t nargs, std::uint32_t *out, std::uint32_t &count)
{
    serviceCommonQdec();
    if (opcode == 80U && nargs == 4U)
    {
        if (fixtureClaimed() || signalClaimed() || pwmCaptureClaimed() || wiringClaimed() ||
            commonGpioClaimed() || onboardSerialActive() || args[0] != 520U || args[3] != 2U ||
            !gate.arm(args[0], args[1], args[2], args[3], role, k_uptime_get()))
        {
            return 403U;
        }
        error = reads = doubles = emitted = target_steps = max_read_gap = 0U;
        accumulated = 0;
        mismatch_recorded = phase_checked = false;
        for (auto &word : first_mismatch)
        {
            word = 0U;
        }
        out[0] = 520U;
        out[1] = 10000U;
        count = 2U;
        return 0U;
    }
    if (opcode == 81U && nargs == 0U)
    {
        const bool result = stop();
        gate.close(result);
        snapshot(out, count);
        return result ? 0U : 770U;
    }
    if (opcode == 85U && nargs == 0U)
    {
        snapshot(out, count);
        return 0U;
    }
    if (opcode == 85U && nargs == 1U && args[0] <= 1U && role == 1U)
    {
        if (args[0] == 0U)
        {
            diagnostic(out);
        }
        else
        {
            for (unsigned index = 0U; index < 20U; ++index)
            {
                out[index] = first_mismatch[index];
            }
        }
        count = 20U;
        return 0U;
    }
    if (!gate.live(k_uptime_get()))
    {
        return 403U;
    }
    if (opcode == 82U && nargs == 0U)
    {
        out[0] = gate.renew(k_uptime_get()) ? 0U : 1U;
        count = 1U;
        return 0U;
    }
    if (opcode == 83U && nargs == 2U && (args[0] == 20U || args[0] == 21U) && args[1] <= 1U &&
        !prepared && qdec == nullptr && !generator_token.active)
    {
        instance = args[0];
        if (role == 2U)
        {
            const IoResourceId resources[]{gpioIoResource(pinDescription(PIN_P1_14)->gpio),
                                           gpioIoResource(pinDescription(PIN_P1_10)->gpio)};
            prepared = acquireIoResources({IoOwnerKind::application, 243U}, resources, 2U,
                                          IoAcquirePolicy::exclusive,
                                          generator_token) == IoResourceResult::success;
            if (prepared)
            {
                phase(0U);
                nrf_gpio_cfg_output(NRF_GPIO_PIN_MAP(1, 14));
                nrf_gpio_cfg_output(NRF_GPIO_PIN_MAP(1, 10));
            }
        }
        else
        {
            qdec = streamFabric().qdec(instance);
            const QdecConfiguration configuration{PIN_P1_14,
                                                  PIN_P1_10,
                                                  0xFFU,
                                                  args[1] != 0U,
                                                  false,
                                                  256U,
                                                  0U,
                                                  false,
                                                  StreamElectricalProfile::connector_fixture};
            prepared = qdec != nullptr &&
                       qdec->configure(configuration) == StreamFabricResult::success &&
                       qdec->start() == StreamFabricResult::success;
            last_read = k_cycle_get_32();
            observer.start(last_read, inputPhase());
        }
        out[0] = prepared ? 0U : 1U;
        count = 1U;
        return 0U;
    }
    if (opcode == 84U && nargs == 3U && role == 2U && prepared && !generating &&
        (args[0] == 1U || args[0] == 100U || args[0] == 1000U) &&
        (args[1] == 2000U || args[1] == 10000U) && args[2] <= 2U)
    {
        emitted = 0U;
        mode = args[2];
        target_steps = args[0] * (mode == 2U ? 2U : 4U);
        interval_cycles = k_us_to_cyc_ceil32(args[1]);
        last_step = k_cycle_get_32();
        generating = true;
        out[0] = 0U;
        count = 1U;
        return 0U;
    }
    if (opcode == 86U && nargs == 1U && args[0] <= 1U && role == 1U && prepared)
    {
        (void)drain();
        snapshot(out, count);
        if (args[0] != 0U)
        {
            accumulated = 0;
            doubles = 0U;
            observer.clearCounts();
        }
        return 0U;
    }
    if (opcode == 87U && nargs == 0U && role == 1U && prepared)
    {
        const bool result = qdec->stop() == StreamFabricResult::success &&
                            qdec->start() == StreamFabricResult::success;
        accumulated = 0;
        doubles = 0U;
        last_read = k_cycle_get_32();
        observer.start(last_read, inputPhase());
        out[0] = result ? 0U : 1U;
        count = 1U;
        return 0U;
    }
    return 400U;
}
