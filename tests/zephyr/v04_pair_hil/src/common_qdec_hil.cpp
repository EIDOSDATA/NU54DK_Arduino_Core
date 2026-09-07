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
    std::int32_t last_driver_acc = 0;
    v04::QdecObserver observer;
    std::uint32_t first_mismatch[20]{};
    bool mismatch_recorded = false, phase_checked = false;
    std::int32_t sampled_steps = 0, last_sample_value = 0;
    std::uint32_t sampled_doubles = 0U, sample_events = 0U, last_sample = 0U, max_sample_gap = 0U;
    std::uint32_t read_trace[16][10]{}, trace_next = 0U, trace_total = 0U;
    std::uint32_t first_sample_detail[8]{};
    std::uint32_t read_observation = 0U;
    std::uint32_t read_strategy = 0U;
    std::uint32_t read_period_us = 5000U;
    std::uint32_t read_sample_age_min = UINT32_MAX, read_sample_age_max = 0U, read_wait_max = 0U;
    std::uint32_t late_changes = 0U, late_wait_max = 0U, first_late_change[10]{};
    std::int32_t late_acc_difference = 0, late_double_difference = 0;
    std::uint32_t sample_poll_previous = 0U, sample_poll_max = 0U, sample_observe_max = 0U;
    std::uint32_t sample_poll_calls = 0U;
    std::int32_t irq_sample_steps = 0, irq_report_steps = 0;
    std::uint32_t irq_sample_count = 0U, irq_sample_doubles = 0U, irq_report_count = 0U;
    std::uint32_t irq_report_doubles = 0U, irq_event_errors = 0U, irq_service_last = 0U;
    std::uint32_t irq_service_max = 0U;
    std::uint32_t protected_read_max = 0U;

    /** @brief 비활성 IRQ의 SAMPLERDY를 관측하고 ACC와 별개인 SAMPLE 값을 합산합니다. */
    void observeSample(std::uint32_t now)
    {
        const auto started = k_cycle_get_32();
        if (sample_poll_calls != 0U && started - sample_poll_previous > sample_poll_max)
        {
            sample_poll_max = started - sample_poll_previous;
        }
        sample_poll_previous = started;
        ++sample_poll_calls;
        auto *const reg = instance == 20U ? NRF_QDEC20 : NRF_QDEC21;
        if (nrf_qdec_event_check(reg, NRF_QDEC_EVENT_SAMPLERDY))
        {
            last_sample_value = nrf_qdec_sample_get(reg);
            nrf_qdec_event_clear(reg, NRF_QDEC_EVENT_SAMPLERDY);
            const auto gap = now - last_sample;
            if (gap > max_sample_gap)
            {
                max_sample_gap = gap;
            }
            last_sample = now;
            ++sample_events;
            if (last_sample_value == 2)
            {
                ++sampled_doubles;
            }
            else
            {
                sampled_steps += last_sample_value;
            }
        }
        const auto duration = k_cycle_get_32() - started;
        if (duration > sample_observe_max)
        {
            sample_observe_max = duration;
        }
    }

    /** @brief 공개 IRQ 이벤트 큐에서 실제 SAMPLE 또는 자동 REPORT만 합산합니다. */
    void observeInterrupts(std::uint32_t now)
    {
        const auto gap = now - irq_service_last;
        if (gap > irq_service_max)
        {
            irq_service_max = gap;
        }
        irq_service_last = now;
        QdecEvent event{};
        while (qdec->takeEvent(event))
        {
            if (event.type == QdecEventType::sample && read_strategy == 7U)
            {
                ++irq_sample_count;
                if (event.accumulated == 2)
                {
                    ++irq_sample_doubles;
                }
                else
                {
                    irq_sample_steps += event.accumulated;
                }
            }
            else if (event.type == QdecEventType::report && read_strategy == 8U)
            {
                ++irq_report_count;
                irq_report_steps += event.accumulated;
                irq_report_doubles += event.double_transitions;
                accumulated += event.accumulated;
                doubles += event.double_transitions;
            }
            else
            {
                ++irq_event_errors;
            }
        }
        if (qdec->lastResult() != StreamFabricResult::success || irq_event_errors != 0U)
        {
            error = 5U;
        }
    }

    /** @brief SAMPLE 관측 품질과 최초 불일치까지 고정된 read ring 위치를 기록합니다. */
    void sampleDetail(std::uint32_t *out)
    {
        const std::uint32_t values[]{static_cast<std::uint32_t>(sampled_steps),
                                     sampled_doubles,
                                     sample_events,
                                     k_cyc_to_us_floor32(max_sample_gap),
                                     last_sample,
                                     static_cast<std::uint32_t>(last_sample_value),
                                     trace_total,
                                     trace_next};
        for (unsigned index = 0U; index < 8U; ++index)
        {
            out[index] = values[index];
        }
    }

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
                                     static_cast<std::uint32_t>(last_driver_acc),
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
        if (read_strategy != 8U && !phase_checked &&
            now - observer.last_edge >= k_us_to_cyc_ceil32(1024U))
        {
            phase_checked = true;
            const auto *const reg = instance == 20U ? NRF_QDEC20 : NRF_QDEC21;
            if (!mismatch_recorded && (accumulated + nrf_qdec_acc_get(reg) != observer.steps ||
                                       doubles + nrf_qdec_accdbl_get(reg) != observer.doubles))
            {
                diagnostic(first_mismatch);
                sampleDetail(first_sample_detail);
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
        if (read_strategy == 8U)
        {
            /** @brief 자동 REPORT 대비에서는 명시적 read/clear를 섞지 않습니다. */
            observeInterrupts(k_cycle_get_32());
            return error == 0U;
        }
        unsigned interrupt_key = 0U;
        if (read_strategy == 4U)
        {
            /** @brief 고정256us 진단에서 새 샘플 관측 후32~64us 구간으로 clear를 분리합니다. */
            interrupt_key = irq_lock();
            const auto origin = k_cycle_get_32();
            const auto initial_samples = sample_events;
            while (true)
            {
                const auto cycle = k_cycle_get_32();
                observeSample(cycle);
                observeInput(cycle);
                const auto age = k_cyc_to_us_floor32(cycle - last_sample);
                const auto waited = k_cyc_to_us_floor32(cycle - origin);
                if (waited > read_wait_max)
                {
                    read_wait_max = waited;
                }
                if (sample_events != initial_samples && age >= 32U && age <= 64U)
                {
                    break;
                }
                if (waited > 1024U)
                {
                    irq_unlock(interrupt_key);
                    error = 4U;
                    return false;
                }
                k_busy_wait(4U);
            }
        }
        if (read_strategy == 9U)
        {
            /** @brief 샘플 대기 없이 read 구간만 잠가 CPU 선점과 샘플 위상을 분리합니다. */
            interrupt_key = irq_lock();
        }
        const auto now = k_cycle_get_32();
        const auto gap = now - last_read;
        if (gap > max_read_gap)
        {
            max_read_gap = gap;
        }
        last_read = now;
        auto *const reg = instance == 20U ? NRF_QDEC20 : NRF_QDEC21;
        const auto before_acc = read_observation >= 2U
                                    ? static_cast<std::uint32_t>(nrf_qdec_acc_get(reg))
                                    : 0x80000000U;
        QdecEvent event{};
        auto result = StreamFabricResult::success;
        const auto sample_age = k_cyc_to_us_floor32(now - last_sample);
        if (sample_age < read_sample_age_min)
        {
            read_sample_age_min = sample_age;
        }
        if (sample_age > read_sample_age_max)
        {
            read_sample_age_max = sample_age;
        }
        if (read_strategy == 1U)
        {
            /** @brief 진단 전용으로 개별 task를 대비하며 공개 read의 PASS로 사용하지 않습니다. */
            nrf_qdec_task_trigger(reg, NRF_QDEC_TASK_RDCLRACC);
            event.accumulated = nrf_qdec_accread_get(reg);
            nrf_qdec_task_trigger(reg, NRF_QDEC_TASK_RDCLRDBL);
            event.double_transitions = nrf_qdec_accdblread_get(reg);
        }
        else if (read_strategy == 3U || read_strategy == 5U)
        {
            /** @brief 같은 동시 clear task 뒤 CPU write 완료 barrier를 추가한 대비입니다. */
            nrf_qdec_task_trigger(reg, NRF_QDEC_TASK_READCLRACC);
            __DSB();
            event.accumulated = nrf_qdec_accread_get(reg);
            event.double_transitions = nrf_qdec_accdblread_get(reg);
        }
        else
        {
            result = qdec->read(event);
        }
        if (read_strategy == 5U || read_strategy == 6U)
        {
            /** @brief 동일 task 결과의 지연 변화를 관측하며 방법6의 공개 반환값은 보정하지 않습니다. */
            const auto late_interrupt_key = irq_lock();
            const auto origin = k_cycle_get_32();
            k_busy_wait(5U);
            const auto late_acc = nrf_qdec_accread_get(reg);
            const auto late_double = nrf_qdec_accdblread_get(reg);
            const auto waited = k_cyc_to_us_floor32(k_cycle_get_32() - origin);
            irq_unlock(late_interrupt_key);
            if (waited > late_wait_max)
            {
                late_wait_max = waited;
            }
            if (late_acc != event.accumulated || late_double != event.double_transitions)
            {
                if (late_changes == 0U)
                {
                    const std::uint32_t values[]{now,
                                                 reads + 1U,
                                                 static_cast<std::uint32_t>(event.accumulated),
                                                 static_cast<std::uint32_t>(late_acc),
                                                 event.double_transitions,
                                                 late_double,
                                                 before_acc,
                                                 static_cast<std::uint32_t>(sampled_steps),
                                                 static_cast<std::uint32_t>(observer.steps),
                                                 waited};
                    for (unsigned index = 0U; index < 10U; ++index)
                    {
                        first_late_change[index] = values[index];
                    }
                }
                ++late_changes;
                late_acc_difference += late_acc - event.accumulated;
                late_double_difference += static_cast<std::int32_t>(late_double) -
                                          static_cast<std::int32_t>(event.double_transitions);
            }
            if (read_strategy == 5U)
            {
                event.accumulated = late_acc;
                event.double_transitions = late_double;
            }
        }
        if (read_strategy == 9U)
        {
            const auto elapsed = k_cycle_get_32() - now;
            if (elapsed > protected_read_max)
            {
                protected_read_max = elapsed;
            }
        }
        if (read_strategy == 4U || read_strategy == 9U)
        {
            irq_unlock(interrupt_key);
        }
        last_driver_acc = event.accumulated;
        if (!mismatch_recorded)
        {
            const std::uint32_t values[]{
                now,
                reads + 1U,
                static_cast<std::uint32_t>(last_driver_acc),
                static_cast<std::uint32_t>(before_acc),
                read_observation >= 2U ? static_cast<std::uint32_t>(reg->ACC) : 0x80000000U,
                read_observation >= 1U ? static_cast<std::uint32_t>(reg->ACCREAD) : 0x80000000U,
                static_cast<std::uint32_t>(sampled_steps),
                static_cast<std::uint32_t>(observer.steps),
                k_cyc_to_us_floor32(now - observer.last_edge),
                static_cast<std::uint32_t>(last_sample_value)};
            for (unsigned index = 0U; index < 10U; ++index)
            {
                read_trace[trace_next][index] = values[index];
            }
            trace_next = (trace_next + 1U) % 16U;
            ++trace_total;
        }
        if (result != StreamFabricResult::success || event.driver_error != 0 ||
            event.accumulated <= -1024 || event.accumulated >= 1023 ||
            event.double_transitions >= 15U ||
            k_cyc_to_us_floor32(gap) > (read_strategy == 2U ? 6000000U : 15000U))
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
        if (read_observation == 3U && read_strategy != 7U && read_strategy != 8U)
        {
            observeSample(now);
        }
        if (read_strategy == 7U || read_strategy == 8U)
        {
            observeInterrupts(now);
        }
        observeInput(now);
        if (error != 0U)
        {
            gate.close(stop());
            return;
        }
    }
    if (role == 1U && read_strategy == 2U)
    {
        /** @brief 지우지 않는 대비도 누산 포화·시간 초과 전에 출력 gate를 닫습니다. */
        const auto *const reg = instance == 20U ? NRF_QDEC20 : NRF_QDEC21;
        const auto acc = nrf_qdec_acc_get(reg);
        if (now - last_read > k_us_to_cyc_ceil32(6000000U) || acc <= -900 || acc >= 900 ||
            nrf_qdec_accdbl_get(reg) >= 14U)
        {
            error = 3U;
            gate.close(stop());
        }
    }
    if (role == 1U && read_strategy != 2U && read_strategy != 8U &&
        now - last_read >= k_us_to_cyc_ceil32(read_period_us))
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
        read_observation = 0U;
        read_strategy = 0U;
        read_period_us = 5000U;
        read_sample_age_min = UINT32_MAX;
        read_sample_age_max = read_wait_max = 0U;
        late_changes = late_wait_max = 0U;
        late_acc_difference = late_double_difference = 0;
        sample_poll_previous = sample_poll_max = sample_observe_max = sample_poll_calls = 0U;
        irq_sample_steps = irq_report_steps = 0;
        irq_sample_count = irq_sample_doubles = irq_report_count = irq_report_doubles = 0U;
        irq_event_errors = irq_service_max = protected_read_max = 0U;
        for (auto &word : first_late_change)
        {
            word = 0U;
        }
        sampled_steps = last_sample_value = 0;
        sampled_doubles = sample_events = max_sample_gap = trace_next = trace_total = 0U;
        mismatch_recorded = phase_checked = false;
        for (auto &word : first_mismatch)
        {
            word = 0U;
        }
        for (auto &word : first_sample_detail)
        {
            word = 0U;
        }
        for (auto &row : read_trace)
        {
            for (auto &word : row)
            {
                word = 0U;
            }
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
    if (opcode == 85U && nargs == 1U && args[0] == 2U && role == 1U)
    {
        sampleDetail(out);
        for (unsigned index = 0U; index < 8U; ++index)
        {
            out[8U + index] = first_sample_detail[index];
        }
        count = 16U;
        return 0U;
    }
    if (opcode == 85U && nargs == 1U && args[0] == 4U && role == 1U)
    {
        out[0] = read_observation;
        out[1] = read_observation == 3U;
        out[2] = read_observation >= 2U;
        out[3] = read_observation >= 1U;
        count = 4U;
        return 0U;
    }
    if (opcode == 85U && nargs == 1U && args[0] == 5U && role == 1U)
    {
        out[0] = read_strategy;
        out[1] = read_strategy != 1U && read_strategy != 3U && read_strategy != 5U &&
                 read_strategy != 8U;
        out[2] = read_strategy != 2U && read_strategy != 8U;
        out[3] = read_strategy == 2U ? 6000000U : 15000U;
        out[4] = read_period_us;
        count = 5U;
        return 0U;
    }
    if (opcode == 85U && nargs == 1U && args[0] == 6U && role == 1U)
    {
        out[0] = read_sample_age_min;
        out[1] = read_sample_age_max;
        out[2] = read_wait_max;
        count = 3U;
        return 0U;
    }
    if (opcode == 85U && nargs == 1U && args[0] == 7U && role == 1U)
    {
        out[0] = late_changes;
        out[1] = static_cast<std::uint32_t>(late_acc_difference);
        out[2] = static_cast<std::uint32_t>(late_double_difference);
        out[3] = late_wait_max;
        for (unsigned index = 0U; index < 10U; ++index)
        {
            out[4U + index] = first_late_change[index];
        }
        count = 14U;
        return 0U;
    }
    if (opcode == 85U && nargs == 1U && args[0] == 8U)
    {
        /** @brief GPIO pull·입력 buffer·drive와 실제 LEDPRE를 출력 변경 없이 기록합니다. */
        std::uint32_t pin = NRF_GPIO_PIN_MAP(1, 14);
        const auto *const port = nrf_gpio_pin_port_decode(&pin);
        const auto *const reg = instance == 20U ? NRF_QDEC20 : NRF_QDEC21;
        const std::uint32_t values[]{role,
                                     port->PIN_CNF[14],
                                     port->PIN_CNF[10],
                                     port->OUT & phase_mask,
                                     port->IN & phase_mask,
                                     reg->PSEL.A,
                                     reg->PSEL.B,
                                     reg->PSEL.LED,
                                     reg->LEDPRE,
                                     reg->SHORTS,
                                     reg->INTENSET,
                                     reg->DBFEN,
                                     reg->ENABLE};
        for (unsigned index = 0U; index < 13U; ++index)
        {
            out[index] = values[index];
        }
        count = 13U;
        return 0U;
    }
    if (opcode == 85U && nargs == 1U && args[0] == 9U && role == 1U)
    {
        /** @brief SAMPLE 처리 주기와 처리 중 선점을 직접 측정해 관측 누락 가능성을 판정합니다. */
        out[0] = k_cyc_to_us_floor32(sample_poll_max);
        out[1] = k_cyc_to_us_floor32(sample_observe_max);
        out[2] = sample_poll_calls;
        count = 3U;
        return 0U;
    }
    if (opcode == 85U && nargs == 1U && args[0] == 10U && role == 1U)
    {
        /** @brief IRQ 원본 합·이벤트 수·큐 오류와 서비스 간격을 기능 PASS와 구분합니다. */
        out[0] = static_cast<std::uint32_t>(irq_sample_steps);
        out[1] = irq_sample_doubles;
        out[2] = irq_sample_count;
        out[3] = static_cast<std::uint32_t>(irq_report_steps);
        out[4] = irq_report_doubles;
        out[5] = irq_report_count;
        out[6] = irq_event_errors;
        out[7] = k_cyc_to_us_floor32(irq_service_max);
        out[8] = qdec == nullptr ? 0U : static_cast<std::uint32_t>(qdec->lastDriverError());
        count = 9U;
        return 0U;
    }
    if (opcode == 85U && nargs == 1U && args[0] == 11U && role == 1U)
    {
        /** @brief 시험 중 실제 우선순위·IRQ 활성·짧은 read 보호 시간을 읽기만 합니다. */
        const auto irq = instance == 20U ? QDEC20_IRQn : QDEC21_IRQn;
        out[0] = NVIC_GetPriority(irq);
        out[1] = NVIC_GetEnableIRQ(irq);
        out[2] = k_cyc_to_us_floor32(protected_read_max);
        out[3] = __get_BASEPRI();
        out[4] = __get_PRIMASK();
        count = 5U;
        return 0U;
    }
    if (opcode == 85U && nargs == 2U && args[0] == 3U && args[1] < 16U && args[1] % 2U == 0U &&
        role == 1U)
    {
        for (unsigned index = 0U; index < 20U; ++index)
        {
            out[index] = read_trace[args[1] + index / 10U][index % 10U];
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
    if (opcode == 83U &&
        (nargs == 2U || (nargs == 3U && args[2] <= 3U) ||
         (nargs == 4U && args[2] == 3U && args[3] <= 9U)) &&
        (args[0] == 20U || args[0] == 21U) && args[1] <= 1U && !prepared && qdec == nullptr &&
        !generator_token.active)
    {
        instance = args[0];
        read_observation = nargs >= 3U ? args[2] : 0U;
        read_strategy = nargs == 4U ? args[3] : 0U;
        read_period_us = nargs == 4U ? 128U : 5000U;
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
                                                  read_strategy == 7U,
                                                  256U,
                                                  0U,
                                                  read_strategy == 8U,
                                                  StreamElectricalProfile::connector_fixture};
            prepared = qdec != nullptr &&
                       qdec->configure(configuration) == StreamFabricResult::success &&
                       qdec->start() == StreamFabricResult::success;
            last_read = k_cycle_get_32();
            irq_service_last = last_read;
            observer.start(last_read, inputPhase());
            last_sample = last_read;
            if (read_observation == 3U && read_strategy != 7U && read_strategy != 8U)
            {
                nrf_qdec_event_clear(instance == 20U ? NRF_QDEC20 : NRF_QDEC21,
                                     NRF_QDEC_EVENT_SAMPLERDY);
            }
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
            sampled_steps = 0;
            sampled_doubles = 0U;
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
        sampled_steps = 0;
        sampled_doubles = 0U;
        last_sample = last_read;
        if (read_observation == 3U)
        {
            nrf_qdec_event_clear(instance == 20U ? NRF_QDEC20 : NRF_QDEC21,
                                 NRF_QDEC_EVENT_SAMPLERDY);
        }
        out[0] = result ? 0U : 1U;
        count = 1U;
        return 0U;
    }
    return 400U;
}
