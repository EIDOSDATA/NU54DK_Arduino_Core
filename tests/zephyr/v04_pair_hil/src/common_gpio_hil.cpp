/**
 * @file common_gpio_hil.cpp
 * @brief 공통 17신호에서 실제 Arduino GPIO와 GPIOTE API를 검사합니다.
 * @note 에지 발생은 CPU가 고정 GPIOTE task를 호출하는 진단 신호원입니다.
 * 정밀 주기나 IRQ latency를 보증하지 않으며 실제 count와 최대 poll 간격을 보고합니다.
 * SPDX-License-Identifier: MIT
 */
#include "common_gpio_hil.h"
#include "common_wiring.h"
#include "fixture_gate.h"
#include "fixture_hil.h"
#include "pwm_capture_hil.h"
#include "signal_hil.h"
#include "wiring_hil.h"
#include "serial_hil.h"
#include <Arduino.h>
#include <variant.h>
#include <internal/PinHandover.h>
#include <internal/pin_description.h>
#include <nucode/EventFabric.h>
#include <hal/nrf_gpio.h>
#include <hal/nrf_gpiote.h>
#include <zephyr/kernel.h>

namespace
{
    using namespace nucode::arduino;
    using namespace nucode::arduino::internal;
    constexpr std::uint32_t role = CONFIG_NUCODE_V04_HIL_ROLE;
    v04::FixtureGate gate;
    std::uint32_t net = v04::wiring_none;
    bool gpio_owned = false, gpiote_owned = false;
    bool output = false, generating = false;
    GpioteFabric *gpiote = nullptr;
    std::uint32_t channel = 0U, edge_count = 0U, emitted = 0U, error = 0U;
    std::uint32_t limit = 0U, interval_cycles = 0U, last_edge = 0U, last_poll = 0U;
    std::uint32_t max_poll_cycles = 0U, leakage = 0U, lease_expirations = 0U;

    /** @brief Arduino ID와 물리 net을 분리하고 I2S의 두 교차 선을 반영합니다. */
    pin_size_t logical(std::uint32_t selected)
    {
        constexpr pin_size_t pins[]{PIN_P1_14, PIN_P1_10, PIN_P1_04, PIN_P1_05, PIN_P1_06,
                                    PIN_P1_07, PIN_P0_00, PIN_P0_01, PIN_P0_02, PIN_P0_03,
                                    PIN_P2_00, PIN_P2_01, PIN_P2_02, PIN_P2_03, PIN_P2_04,
                                    PIN_P2_05, PIN_P2_06};
        if (selected >= v04::wiring_count)
        {
            return static_cast<pin_size_t>(UINT16_MAX);
        }
        return pins[role == 2U && (selected == 4U || selected == 5U) ? 9U - selected : selected];
    }

    /** @brief 현재 소유한 GPIOTE 레지스터만 진단 대상으로 선택합니다. */
    NRF_GPIOTE_Type *reg()
    {
        return gpiote != nullptr && gpiote->instance() == 30U ? NRF_GPIOTE30 : NRF_GPIOTE20;
    }

    /** @brief GPIO 입력 전환 뒤 내부 handover로 GPIO lease도 반환합니다. */
    bool releaseGpio()
    {
        if (!gpio_owned)
        {
            return true;
        }
        pinMode(logical(net), INPUT);
        if (lastGpioError() != GpioError::none)
        {
            return false;
        }
        GpioPinHandover handover{};
        if (beginGpioPinHandover(logical(net), {IoOwnerKind::application, 242U}, handover) !=
            PinHandoverResult::success)
        {
            return false;
        }
        if (commitGpioPinHandover(handover) != PinHandoverResult::success)
        {
            return false;
        }
        nrf_gpio_cfg_input(v04::wiringPin(role, net), NRF_GPIO_PIN_NOPULL);
        if (releasePeripheralPinHandover(handover) != PinHandoverResult::success)
        {
            return false;
        }
        gpio_owned = false;
        return true;
    }

    /** @brief 생성기를 먼저 중지한 뒤 검증 가능한 입력·free 상태로 돌립니다. */
    bool stop()
    {
        generating = false;
        if (gpiote_owned)
        {
            if (gpiote->release(static_cast<std::uint8_t>(channel)) != EventFabricResult::success)
            {
                return false;
            }
            gpiote_owned = false;
        }
        if (!releaseGpio())
        {
            return false;
        }
        if (net != v04::wiring_none &&
            nrf_gpio_pin_dir_get(v04::wiringPin(role, net)) != NRF_GPIO_PIN_DIR_INPUT)
        {
            return false;
        }
        net = v04::wiring_none;
        output = false;
        gpiote = nullptr;
        return true;
    }

    /** @brief 다른 신호를 구동하지 않았는지 전체 net의 방향을 원본으로 반환합니다. */
    std::uint32_t directionMask()
    {
        std::uint32_t mask = 0U;
        for (unsigned index = 0U; index < v04::wiring_count; ++index)
        {
            mask |=
                (nrf_gpio_pin_dir_get(v04::wiringPin(role, index)) == NRF_GPIO_PIN_DIR_OUTPUT ? 1U
                                                                                              : 0U)
                << index;
        }
        return mask;
    }

    /** @brief API 판정 전에 물리 level·설정·상태·누출을 그대로 제공합니다. */
    void snapshot(std::uint32_t *out, std::uint32_t &count)
    {
        out[0] = net;
        out[1] = net == v04::wiring_none ? 0U : nrf_gpio_pin_read(v04::wiringPin(role, net));
        out[2] = gpio_owned ? static_cast<std::uint32_t>(digitalRead(logical(net))) : UINT32_MAX;
        out[3] = directionMask();
        out[4] = 0U;
        if (net != v04::wiring_none)
        {
            auto physical = v04::wiringPin(role, net);
            auto *const port = nrf_gpio_pin_port_decode(&physical);
            out[4] = port->PIN_CNF[physical];
        }
        out[5] = edge_count;
        out[6] = emitted;
        out[7] = generating;
        out[8] = error;
        out[9] = leakage;
        out[10] = k_cyc_to_us_floor32(max_poll_cycles);
        out[11] = lease_expirations;
        out[12] = gpiote == nullptr ? 0U : gpiote->channelCount();
        out[13] = gpio_owned;
        out[14] = gpiote_owned;
        out[15] = gate.live(k_uptime_get());
        count = 16U;
    }
} // namespace

bool commonGpioClaimed()
{
    return gate.claimed();
}

bool commonGpioNeedsPolling()
{
    return gpiote_owned;
}

void serviceCommonGpio()
{
    if (gate.fixture() && !gate.live(k_uptime_get()))
    {
        ++lease_expirations;
        error = 1U;
        gate.close(stop());
    }
    if (!gpiote_owned)
    {
        return;
    }
    const auto now = k_cycle_get_32();
    const auto gap = now - last_poll;
    if (last_poll != 0U && gap > max_poll_cycles)
    {
        max_poll_cycles = gap;
    }
    last_poll = now;
    if (generating && now - last_edge >= interval_cycles)
    {
        last_edge = now;
        *reinterpret_cast<volatile std::uint32_t *>(gpiote->outTask(channel).address) = 1U;
        ++emitted;
        if (emitted == limit)
        {
            generating = false;
        }
    }
    for (unsigned index = 0U; index < gpiote->channelCount(); ++index)
    {
        const auto event = nrf_gpiote_in_event_get(index);
        if (nrf_gpiote_event_check(reg(), event))
        {
            nrf_gpiote_event_clear(reg(), event);
            if (index == channel && !output)
            {
                ++edge_count;
            }
            else
            {
                leakage |= 1U << index;
            }
        }
    }
}

std::uint32_t commonGpioCommand(std::uint32_t opcode, const std::uint32_t *args,
                                std::uint32_t nargs, std::uint32_t *out, std::uint32_t &count)
{
    serviceCommonGpio();
    if (opcode == 64U && nargs == 4U)
    {
        if (fixtureClaimed() || signalClaimed() || pwmCaptureClaimed() || wiringClaimed() ||
            onboardSerialActive() || args[0] != 502U ||
            !gate.arm(args[0], args[1], args[2], args[3], role, k_uptime_get()))
        {
            return 403U;
        }
        error = edge_count = emitted = leakage = max_poll_cycles = last_poll = 0U;
        out[0] = 502U;
        out[1] = 10000U;
        count = 2U;
        return 0U;
    }
    if (opcode == 65U && nargs == 0U)
    {
        const bool result = stop();
        gate.close(result);
        snapshot(out, count);
        return result ? 0U : 760U;
    }
    if (opcode == 68U && nargs == 0U)
    {
        snapshot(out, count);
        return 0U;
    }
    if (!gate.live(k_uptime_get()))
    {
        return 403U;
    }
    if (opcode == 69U && nargs == 0U)
    {
        out[0] = gate.renew(k_uptime_get()) ? 0U : 1U;
        count = 1U;
        return 0U;
    }
    if (opcode == 66U && nargs == 2U && args[0] < v04::wiring_count && args[1] < 5U &&
        !gpiote_owned && (net == v04::wiring_none || net == args[0]) &&
        (args[1] < 3U || gate.controller() == role))
    {
        constexpr PinMode modes[]{INPUT, INPUT_PULLUP, INPUT_PULLDOWN, OUTPUT, OUTPUT_OPENDRAIN};
        net = args[0];
        pinMode(logical(net), modes[args[1]]);
        out[0] = static_cast<std::uint32_t>(lastGpioError());
        gpio_owned |= out[0] == 0U;
        output = args[1] >= 3U && out[0] == 0U;
        count = 1U;
        return 0U;
    }
    if (opcode == 67U && nargs == 1U && args[0] <= 1U && gpio_owned && output &&
        gate.controller() == role)
    {
        digitalWrite(logical(net), args[0] ? HIGH : LOW);
        out[0] = static_cast<std::uint32_t>(lastGpioError());
        count = 1U;
        return 0U;
    }
    if (opcode == 70U && nargs == 4U && args[0] < 10U && args[1] < 8U && args[2] < 3U &&
        args[3] <= 1U && !gpio_owned && !gpiote_owned && net == v04::wiring_none &&
        (args[3] == 0U || gate.controller() == role))
    {
        net = args[0];
        channel = args[1];
        output = args[3] != 0U;
        gpiote = eventFabric().gpiote(net < 6U ? 20U : 30U);
        const auto polarity = static_cast<GpiotePolarity>(args[2]);
        const auto result = output ? gpiote->acquireOutput(channel, logical(net), polarity, false)
                                   : gpiote->acquireInput(channel, logical(net), polarity);
        gpiote_owned = result == EventFabricResult::success;
        out[0] = static_cast<std::uint32_t>(result);
        out[1] = gpiote->channelCount();
        count = 2U;
        if (gpiote_owned)
        {
            for (unsigned index = 0U; index < gpiote->channelCount(); ++index)
            {
                nrf_gpiote_event_clear(reg(), nrf_gpiote_in_event_get(index));
            }
        }
        return 0U;
    }
    if (opcode == 71U && nargs == 1U && args[0] < 3U && gpiote_owned && output && !generating)
    {
        const auto endpoint = args[0] == 0U   ? gpiote->outTask(channel)
                              : args[0] == 1U ? gpiote->setTask(channel)
                                              : gpiote->clearTask(channel);
        *reinterpret_cast<volatile std::uint32_t *>(endpoint.address) = 1U;
        out[0] = 0U;
        count = 1U;
        return 0U;
    }
    if (opcode == 72U && nargs == 2U && (args[0] == 100U || args[0] == 1000U) && args[1] == 1000U &&
        gpiote_owned && output && !generating && emitted == 0U)
    {
        interval_cycles = k_us_to_cyc_ceil32(1000000U / args[0]);
        limit = args[1];
        last_edge = k_cycle_get_32();
        generating = true;
        out[0] = 0U;
        count = 1U;
        return 0U;
    }
    if (opcode == 73U && nargs == 1U && args[0] < 3U && !gpio_owned && !gpiote_owned)
    {
        out[1] = directionMask();
        if (args[0] == 0U)
        {
            pinMode(static_cast<pin_size_t>(UINT16_MAX), OUTPUT);
            out[0] = static_cast<std::uint32_t>(lastGpioError());
        }
        else
        {
            auto *const handle = eventFabric().gpiote(args[0] == 1U ? 20U : 30U);
            const auto selected = args[0] == 1U ? handle->channelCount() : 0U;
            const auto result = handle->acquireInput(selected, PIN_P1_14, GpiotePolarity::toggle);
            out[0] = static_cast<std::uint32_t>(result);
            if (result == EventFabricResult::success)
            {
                /** @brief 예상 밖 성공도 입력만 획득했으며 즉시 반환하고 실패로 보고합니다. */
                (void)handle->release(selected);
            }
        }
        out[2] = directionMask();
        count = 3U;
        return 0U;
    }
    return 400U;
}
