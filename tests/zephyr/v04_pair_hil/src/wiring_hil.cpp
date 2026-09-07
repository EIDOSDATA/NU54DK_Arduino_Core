/**
 * @file wiring_hil.cpp
 * @brief 핀 소유권을 획득한 뒤 입력 pull-up과 제한된 단일 LOW만 사용합니다.
 * @note 물리 결선 진단이며 Arduino GPIO API 기능이나 전압 품질의 검증이 아닙니다.
 * SPDX-License-Identifier: MIT
 */
#include "wiring_hil.h"
#include "common_wiring.h"
#include "fixture_gate.h"
#include "fixture_hil.h"
#include "signal_hil.h"
#include "pwm_capture_hil.h"
#include "serial_hil.h"
#include <internal/IoResourceManager.h>
#include <hal/nrf_gpio.h>
#include <zephyr/device.h>
#include <zephyr/devicetree.h>
#include <zephyr/kernel.h>

namespace
{
    using namespace nucode::arduino::internal;
    constexpr std::uint32_t role = CONFIG_NUCODE_V04_HIL_ROLE;
    v04::FixtureGate gate;
    v04::WiringPulse pulse;
    IoResourceToken tokens[v04::wiring_count]{};
    std::uint32_t pulse_expirations = 0U, lease_expirations = 0U;

    /** @brief 고정 GPIO descriptor를 공용 소유권 key로 변환합니다. */
    IoResourceId resource(std::uint32_t net)
    {
        const struct device *const ports[]{DEVICE_DT_GET(DT_NODELABEL(gpio0)),
                                           DEVICE_DT_GET(DT_NODELABEL(gpio1)),
                                           DEVICE_DT_GET(DT_NODELABEL(gpio2))};
        const auto pin = v04::wiringPin(role, net);
        const gpio_dt_spec gpio{ports[pin / 32U], static_cast<gpio_pin_t>(pin % 32U), 0U};
        return gpioIoResource(gpio);
    }

    /** @brief 진행 중인 LOW를 먼저 입력으로 바꾸고 모든 소유 핀을 반환합니다. */
    bool stop()
    {
        bool stopped = true;
        pulse.clear();
        for (unsigned net = 0U; net < v04::wiring_count; ++net)
        {
            if (tokens[net].active)
            {
                const auto pin = v04::wiringPin(role, net);
                nrf_gpio_cfg_input(pin, NRF_GPIO_PIN_NOPULL);
                if (nrf_gpio_pin_dir_get(pin) != NRF_GPIO_PIN_DIR_INPUT ||
                    releaseIoResources(tokens[net]) != IoResourceResult::success)
                {
                    stopped = false;
                }
            }
        }
        return stopped;
    }

    /** @brief 모든 소유권을 확보하기 전에는 GPIO 설정을 바꾸지 않습니다. */
    bool prepare()
    {
        for (unsigned net = 0U; net < v04::wiring_count; ++net)
        {
            const auto id = resource(net);
            if (acquireIoResources({IoOwnerKind::application, 241U}, &id, 1U,
                                   IoAcquirePolicy::exclusive,
                                   tokens[net]) != IoResourceResult::success)
            {
                gate.close(stop());
                return false;
            }
        }
        for (unsigned net = 0U; net < v04::wiring_count; ++net)
        {
            nrf_gpio_cfg_input(v04::wiringPin(role, net), NRF_GPIO_PIN_PULLUP);
        }
        return true;
    }

    /** @brief net 순서의 실제 입력·방향·pull과 소유권을 원본으로 반환합니다. */
    void snapshot(std::uint32_t *out, std::uint32_t &count)
    {
        for (unsigned field = 0U; field < 8U; ++field)
        {
            out[field] = 0U;
        }
        for (unsigned net = 0U; net < v04::wiring_count; ++net)
        {
            const auto pin = v04::wiringPin(role, net);
            out[0] |= nrf_gpio_pin_read(pin) << net;
            out[1] |= (nrf_gpio_pin_dir_get(pin) == NRF_GPIO_PIN_DIR_OUTPUT ? 1U : 0U) << net;
            out[2] |= (nrf_gpio_pin_pull_get(pin) == NRF_GPIO_PIN_PULLUP ? 1U : 0U) << net;
            out[3] |= (tokens[net].active ? 1U : 0U) << net;
        }
        out[4] = pulse.net();
        out[5] = pulse_expirations;
        out[6] = lease_expirations;
        out[7] = gate.live(k_uptime_get()) ? 1U : 0U;
        count = 8U;
    }
} // namespace

void initializeWiringIdle()
{
    for (unsigned net = 0U; net < v04::wiring_count; ++net)
    {
        nrf_gpio_cfg_input(v04::wiringPin(role, net), NRF_GPIO_PIN_NOPULL);
    }
}

bool wiringClaimed()
{
    return gate.claimed();
}

void serviceWiring()
{
    const auto now = static_cast<std::uint64_t>(k_uptime_get());
    if (pulse.expired(now))
    {
        nrf_gpio_cfg_input(v04::wiringPin(role, pulse.net()), NRF_GPIO_PIN_PULLUP);
        pulse.clear();
        ++pulse_expirations;
    }
    if (gate.fixture() && !gate.live(now))
    {
        ++lease_expirations;
        gate.close(stop());
    }
}

std::uint32_t wiringCommand(std::uint32_t opcode, const std::uint32_t *args, std::uint32_t nargs,
                            std::uint32_t *out, std::uint32_t &count)
{
    serviceWiring();
    if (opcode == 48U && nargs == 4U)
    {
        if (fixtureClaimed() || signalClaimed() || pwmCaptureClaimed() || onboardSerialActive() ||
            args[0] != 501U ||
            !gate.arm(args[0], args[1], args[2], args[3], role, k_uptime_get()) || !prepare())
        {
            return 403U;
        }
        out[0] = 501U;
        out[1] = v04::FixtureGate::lease_ms;
        out[2] = v04::wiring_count;
        count = 3U;
        return 0U;
    }
    if (opcode == 49U && nargs == 0U)
    {
        const bool stopped = stop();
        gate.close(stopped);
        snapshot(out, count);
        return stopped ? 0U : 760U;
    }
    if (opcode == 51U && nargs == 0U)
    {
        snapshot(out, count);
        return 0U;
    }
    if (!gate.live(k_uptime_get()))
    {
        return 403U;
    }
    if (opcode == 50U && nargs == 1U && gate.controller() == role)
    {
        if (!pulse.start(args[0], k_uptime_get()))
        {
            return 400U;
        }
        const auto pin = v04::wiringPin(role, args[0]);
        nrf_gpio_pin_clear(pin);
        nrf_gpio_cfg(pin, NRF_GPIO_PIN_DIR_OUTPUT, NRF_GPIO_PIN_INPUT_CONNECT, NRF_GPIO_PIN_PULLUP,
                     NRF_GPIO_PIN_S0D1, NRF_GPIO_PIN_NOSENSE);
        out[0] = args[0];
        out[1] = v04::WiringPulse::limit_ms;
        count = 2U;
        return 0U;
    }
    if (opcode == 52U && nargs == 0U && gate.controller() == role)
    {
        if (pulse.net() != v04::wiring_none)
        {
            nrf_gpio_cfg_input(v04::wiringPin(role, pulse.net()), NRF_GPIO_PIN_PULLUP);
            pulse.clear();
        }
        out[0] = 0U;
        count = 1U;
        return 0U;
    }
    if (opcode == 53U && nargs == 0U && gate.renew(k_uptime_get()))
    {
        out[0] = 0U;
        count = 1U;
        return 0U;
    }
    return 400U;
}
