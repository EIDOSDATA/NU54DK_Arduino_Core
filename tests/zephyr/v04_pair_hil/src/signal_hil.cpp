/**
 * @file signal_hil.cpp
 * @brief 두 NU54DK의 PWM/SPIS/I2S를 합성 신호원으로 쓰는 외부 HIL입니다.
 * @note 이 파일의 pin 출력은 만료되는 fixture gate와 고정 allowlist 안에서만 가능합니다.
 * SPDX-License-Identifier: MIT
 */
#include "signal_hil.h"
#include "fixture_gate.h"
#include "fixture_hil.h"
#include <nucode/AnalogFabric.h>
#include <nucode/SerialFabric.h>
#include <nucode/StreamFabric.h>
#include <variant.h>
#include <hal/nrf_gpio.h>
#include <zephyr/kernel.h>
#include <string.h>

namespace
{
    using namespace nucode::arduino;
    constexpr std::uint32_t role = CONFIG_NUCODE_V04_HIL_ROLE;
    constexpr std::size_t analog_capacity = 256U;
    constexpr std::size_t stream_capacity = 1024U;
    constexpr std::size_t pdm_source_capacity = 16384U;

    v04::FixtureGate gate;
    bool prepared = false, started = false, ready = false, complete = false;
    std::uint32_t error = 0U, amount = 0U, requested = 0U;
    bool controller = false;

    alignas(4) std::int16_t analog_samples[2][analog_capacity]{};
    alignas(4) std::int16_t pdm_samples[2][stream_capacity]{};
    alignas(4) std::uint16_t pwm_values[16]{};
    alignas(4) std::uint32_t i2s_rx[2][stream_capacity]{};
    alignas(4) std::uint32_t i2s_tx[2][stream_capacity]{};
    alignas(4) std::uint8_t pdm_source[pdm_source_capacity]{};

    SaadcFabric *saadc = nullptr;
    PwmSequenceFabric *pwm = nullptr;
    QdecFabric *qdec = nullptr;
    I2sFabric *i2s = nullptr;
    PdmFabric *pdm = nullptr;
    SpisHandle *pdm_spis = nullptr;
    std::uint32_t pwm_playbacks = 1U, analog_buffers = 1U;
    std::uint32_t i2s_buffers = 1U, pdm_buffers = 1U;
    std::uint32_t analog_completed_mask = 0U, i2s_completed_mask = 0U;
    std::uint32_t pdm_completed_mask = 0U;
    std::uint32_t analog_sampled = 0U;
    std::int64_t next_analog_sample_ms = 0;
    bool cs_owned = false;
    std::uint32_t cs_psel = 0U, cs_configuration = 0U, cs_output = 0U;

    /** @brief role별 교차 결선의 첫 번째 signal pin을 반환합니다. */
    pin_size_t firstPin()
    {
        return role == 1U ? PIN_P1_04 : PIN_P1_05;
    }

    /** @brief role별 교차 결선의 두 번째 signal pin을 반환합니다. */
    pin_size_t secondPin()
    {
        return role == 1U ? PIN_P1_06 : PIN_P1_07;
    }

    /** @brief role별 PDM source select pin을 반환합니다. */
    pin_size_t selectPin()
    {
        return role == 1U ? PIN_P1_05 : PIN_P1_04;
    }

    /** @brief signal payload에 쓰는 독립 32-bit 패턴입니다. */
    std::uint32_t streamPattern(std::uint32_t seed, std::uint32_t index)
    {
        return (seed + 0x9e3779b9U * (index + 1U)) ^ ((index << 16U) | (index >> 16U));
    }

    /** @brief 직접 구동한 PDM CS pin의 원래 상태를 복원합니다. */
    void restoreChipSelect()
    {
        if (!cs_owned)
        {
            return;
        }
        auto pin = cs_psel;
        auto *const port = nrf_gpio_pin_port_decode(&pin);
        nrf_gpio_pin_write(cs_psel, cs_output);
        port->PIN_CNF[pin] = cs_configuration;
        cs_owned = false;
    }

    /** @brief 모든 signal handle을 역순으로 정지·해제합니다. */
    bool stopAll()
    {
        bool stopped = true;
        if (pwm != nullptr && pwm->state() == AnalogFabricState::active)
        {
            stopped &= pwm->stop(100000U) == AnalogFabricResult::success;
        }
        if (saadc != nullptr && saadc->state() == AnalogFabricState::active)
        {
            stopped &= saadc->stop(100000U) == AnalogFabricResult::success;
        }
        if (qdec != nullptr && qdec->state() == StreamFabricState::active)
        {
            stopped &= qdec->stop() == StreamFabricResult::success;
        }
        if (i2s != nullptr && i2s->state() == StreamFabricState::active)
        {
            stopped &= i2s->stop(100000U) == StreamFabricResult::success;
        }
        if (pdm != nullptr && pdm->state() == StreamFabricState::active)
        {
            stopped &= pdm->stop(100000U) == StreamFabricResult::success;
        }
        restoreChipSelect();
        if (pdm_spis != nullptr && pdm_spis->state() == SerialFabricState::active)
        {
            stopped &= pdm_spis->deactivate(100000U) == SerialFabricResult::success;
        }
        if (stopped)
        {
            saadc = nullptr;
            pwm = nullptr;
            qdec = nullptr;
            i2s = nullptr;
            pdm = nullptr;
            pdm_spis = nullptr;
            prepared = started = ready = complete = false;
            error = amount = requested = 0U;
            analog_buffers = i2s_buffers = pdm_buffers = 1U;
            analog_completed_mask = i2s_completed_mask = pdm_completed_mask = 0U;
            analog_sampled = 0U;
        }
        return stopped;
    }

    /** @brief 안전한 LED buffer 입력 PWM과 격리 AIN0의 시험을 준비합니다. */
    bool prepareAnalog(const std::uint32_t *args)
    {
        if ((args[0] < 20U || args[0] > 22U) || args[1] == 0U || args[1] > analog_capacity ||
            args[2] < 100U || args[2] > 10000U || args[3] > args[2] || args[4] > 3U ||
            (args[5] != 1U && args[5] != 2U) ||
            !((gate.fixture() >= 401U && gate.fixture() <= 404U) || gate.fixture() == 408U))
        {
            return false;
        }
        requested = args[1];
        analog_buffers = args[5];
        if (controller)
        {
            pwm = analogFabric().pwm(static_cast<std::uint8_t>(args[0]));
            PwmSequenceConfiguration configuration{};
            configuration.output_pins[args[4]] = PIN_P1_14;
            configuration.top_value = static_cast<std::uint16_t>(args[2]);
            configuration.load = PwmSequenceLoad::individual;
            for (std::size_t index = 0U; index < 4U; ++index)
            {
                pwm_values[index] = 0U;
            }
            pwm_values[args[4]] = static_cast<std::uint16_t>(args[3]);
            ready = pwm != nullptr && pwm->configure(configuration) == AnalogFabricResult::success;
            return ready;
        }
        saadc = &analogFabric().saadc();
        const auto input =
            static_cast<SaadcInput>(gate.fixture() == 408U ? 7U : gate.fixture() - 401U);
        const SaadcChannelConfiguration channel{input, SaadcInput::disabled,
                                                SaadcGain::one_quarter};
        if (saadc->configure({&channel, 1U, 12U, 1U, 0U}) != AnalogFabricResult::success ||
            saadc->start(analog_samples[0], requested, nullptr, 0U) != AnalogFabricResult::success)
        {
            return false;
        }
        if (analog_buffers == 2U &&
            saadc->queueBuffer(analog_samples[1], requested) != AnalogFabricResult::success)
        {
            return false;
        }
        return true;
    }

    /** @brief PWM quadrature generator 또는 QDEC receiver를 준비합니다. */
    bool prepareQdec(const std::uint32_t *args)
    {
        if (args[0] < 20U || args[0] > 22U || (args[1] != 20U && args[1] != 21U) || args[2] == 0U ||
            args[2] > 1000U || (args[3] != 2000U && args[3] != 10000U) || args[4] > 1U ||
            args[5] > 1U)
        {
            return false;
        }
        requested = args[2] * 4U;
        if (controller)
        {
            pwm = analogFabric().pwm(static_cast<std::uint8_t>(args[0]));
            PwmSequenceConfiguration configuration{};
            configuration.output_pins[0] = PIN_P1_14;
            configuration.output_pins[1] = PIN_P1_10;
            configuration.top_value = static_cast<std::uint16_t>(args[3]);
            configuration.load = PwmSequenceLoad::individual;
            const std::uint8_t forward[4]{1U, 3U, 2U, 0U};
            const std::uint8_t reverse[4]{2U, 3U, 1U, 0U};
            const auto *const states = args[4] ? reverse : forward;
            for (std::size_t step = 0U; step < 4U; ++step)
            {
                pwm_values[step * 4U] =
                    (states[step] & 1U) ? static_cast<std::uint16_t>(args[3]) : 0U;
                pwm_values[step * 4U + 1U] =
                    (states[step] & 2U) ? static_cast<std::uint16_t>(args[3]) : 0U;
                pwm_values[step * 4U + 2U] = pwm_values[step * 4U + 3U] = 0U;
            }
            pwm_playbacks = args[2];
            ready = pwm != nullptr && pwm->configure(configuration) == AnalogFabricResult::success;
            return ready;
        }
        qdec = streamFabric().qdec(static_cast<std::uint8_t>(args[1]));
        const QdecConfiguration configuration{PIN_P1_04,
                                              PIN_P1_06,
                                              0xFFU,
                                              args[5] != 0U,
                                              false,
                                              256U,
                                              0U,
                                              false,
                                              StreamElectricalProfile::dap_uart_disabled};
        ready = qdec != nullptr && qdec->configure(configuration) == StreamFabricResult::success &&
                qdec->start() == StreamFabricResult::success;
        return ready;
    }

    /** @brief I2S20 master/slave 양쪽의 full-duplex DMA buffer를 준비합니다. */
    bool prepareI2s(const std::uint32_t *args)
    {
        if ((args[0] != 16000U && args[0] != 48000U) ||
            (args[1] != 8U && args[1] != 16U && args[1] != 24U && args[1] != 32U) || args[2] > 2U ||
            args[3] == 0U || args[3] > stream_capacity || (args[4] != 1U && args[4] != 2U))
        {
            return false;
        }
        requested = args[3];
        i2s_buffers = args[4];
        for (std::size_t slot = 0U; slot < 2U; ++slot)
        {
            for (std::size_t index = 0U; index < requested; ++index)
            {
                i2s_rx[slot][index] = 0xccccccccU;
                i2s_tx[slot][index] =
                    streamPattern(args[5] ^ (role == 1U ? 0U : 0x5a5a5a5aU),
                                  static_cast<std::uint32_t>(slot * requested + index));
            }
        }
        i2s = streamFabric().i2s(20U);
        const I2sConfiguration configuration{PIN_P1_04,
                                             PIN_P1_05,
                                             0xFFU,
                                             PIN_P1_06,
                                             PIN_P1_07,
                                             args[0],
                                             static_cast<I2sSampleWidth>(args[1]),
                                             static_cast<I2sChannels>(args[2]),
                                             controller,
                                             StreamElectricalProfile::dap_uart_disabled};
        ready = i2s != nullptr && i2s->configure(configuration) == StreamFabricResult::success;
        return ready;
    }

    /** @brief PDM receiver 또는 SPIS EasyDMA bitstream source를 준비합니다. */
    bool preparePdm(const std::uint32_t *args)
    {
        if ((args[0] != 20U && args[0] != 21U) || args[1] == 0U || args[1] > stream_capacity ||
            (args[2] != 25U && args[2] != 50U && args[2] != 75U) || args[3] > 1U || args[4] > 1U ||
            (args[5] != 1U && args[5] != 2U))
        {
            return false;
        }
        requested = args[1];
        pdm_buffers = args[5];
        if (!controller)
        {
            pdm = streamFabric().pdm(static_cast<std::uint8_t>(args[0]));
            const PdmConfiguration configuration{
                firstPin(),    secondPin(),   16000U,
                args[3] != 0U, args[4] != 0U, StreamElectricalProfile::dap_uart_disabled};
            if (pdm == nullptr || pdm->configure(configuration) != StreamFabricResult::success)
            {
                return false;
            }
            cs_psel = role == 1U ? NRF_GPIO_PIN_MAP(1, 5) : NRF_GPIO_PIN_MAP(1, 4);
            auto pin = cs_psel;
            auto *const port = nrf_gpio_pin_port_decode(&pin);
            cs_configuration = port->PIN_CNF[pin];
            cs_output = nrf_gpio_pin_out_read(cs_psel);
            nrf_gpio_pin_set(cs_psel);
            nrf_gpio_cfg_output(cs_psel);
            cs_owned = true;
            ready = true;
            return true;
        }
        const std::uint8_t byte = args[2] == 25U ? 0x11U : args[2] == 50U ? 0x55U : 0x77U;
        const std::size_t source_bytes = requested * pdm_buffers * 8U;
        memset(pdm_source, byte, source_bytes);
        const SerialSignalPin pins[]{{SerialSignal::sck, firstPin()},
                                     {SerialSignal::mosi, secondPin()},
                                     {SerialSignal::miso, secondPin()},
                                     {SerialSignal::csn, selectPin()}};
        /**
         * @brief MOSI는 물리적으로 연결하지 않지만 MISO와 중복할 수 없어 남은 P1 핀을 사용합니다.
         */
        SerialSignalPin routed[4]{pins[0], pins[1], pins[2], pins[3]};
        routed[1].pin = role == 1U ? PIN_P1_07 : PIN_P1_06;
        const SerialDmaWorkspace workspace{pdm_source, source_bytes};
        const SerialFabricConfiguration route{SerialRouteClass::p1_flexible,
                                              SerialElectricalProfile::dap_uart_disabled,
                                              routed,
                                              4U,
                                              &workspace,
                                              1U};
        pdm_spis = serialFabric().spis(21U);
        if (pdm_spis == nullptr ||
            pdm_spis->configure({1000000U, SpiFabricMode::mode0, SpiFabricBitOrder::msb_first,
                                 0U}) != SerialFabricResult::success ||
            pdm_spis->stage(route) != SerialFabricResult::success ||
            pdm_spis->activate() != SerialFabricResult::success ||
            pdm_spis->queueBuffers(pdm_source, source_bytes, nullptr, 0U) !=
                SerialFabricResult::success)
        {
            return false;
        }
        return true;
    }

    /** @brief 선택된 fixture의 인자를 검증하고 각 role을 준비합니다. */
    bool prepare(const std::uint32_t *args)
    {
        if (prepared)
        {
            return false;
        }
        controller = gate.controller() == role;
        bool result = false;
        switch (v04::fixtureFamily(gate.fixture()))
        {
        case v04::FixtureFamily::analog:
            result = prepareAnalog(args);
            break;
        case v04::FixtureFamily::qdec:
            result = prepareQdec(args);
            break;
        case v04::FixtureFamily::i2s:
            result = prepareI2s(args);
            break;
        case v04::FixtureFamily::pdm:
            result = preparePdm(args);
            break;
        default:
            break;
        }
        prepared = result;
        if (!result)
        {
            error |= 1U;
        }
        return result;
    }

    /** @brief 준비된 generator 또는 receiver를 시작합니다. */
    bool start()
    {
        if (!prepared || started)
        {
            return false;
        }
        bool result = false;
        switch (v04::fixtureFamily(gate.fixture()))
        {
        case v04::FixtureFamily::analog:
            if (controller && pwm != nullptr)
            {
                result = pwm->play({pwm_values, 4U, 0U, 0U}, nullptr, 1U, true) ==
                         AnalogFabricResult::success;
            }
            else if (!controller && saadc != nullptr && ready)
            {
                analog_sampled = 0U;
                next_analog_sample_ms = k_uptime_get();
                result = true;
            }
            break;
        case v04::FixtureFamily::qdec:
            result = controller && pwm != nullptr &&
                     pwm->play({pwm_values, 16U, 0U, 0U}, nullptr,
                               static_cast<std::uint16_t>(pwm_playbacks),
                               false) == AnalogFabricResult::success;
            break;
        case v04::FixtureFamily::i2s:
            if (i2s != nullptr)
            {
                result =
                    i2s->start({i2s_rx[0], i2s_tx[0], requested}) == StreamFabricResult::success;
                if (result && i2s_buffers == 2U)
                {
                    result = i2s->queueBuffers({i2s_rx[1], i2s_tx[1], requested}) ==
                             StreamFabricResult::success;
                }
            }
            break;
        case v04::FixtureFamily::pdm:
            if (!controller && pdm != nullptr && cs_owned)
            {
                nrf_gpio_pin_clear(cs_psel);
                result = pdm->start(pdm_samples[0], requested) == StreamFabricResult::success;
                if (result && pdm_buffers == 2U)
                {
                    result =
                        pdm->queueBuffer(pdm_samples[1], requested) == StreamFabricResult::success;
                }
            }
            break;
        default:
            break;
        }
        started = result;
        if (!result)
        {
            error |= 2U;
        }
        return result;
    }
} // namespace

bool signalClaimed()
{
    return gate.claimed();
}

void serviceSignal()
{
    if (gate.fixture() && !gate.live(k_uptime_get()))
    {
        error |= 4U;
        gate.close(stopAll());
    }
    if (saadc != nullptr)
    {
        SaadcEvent event{};
        while (saadc->takeEvent(event))
        {
            if (event.type == SaadcEventType::ready)
            {
                ready = true;
            }
            else if (event.type == SaadcEventType::buffer_complete)
            {
                const unsigned slot = event.buffer == analog_samples[0]   ? 0U
                                      : event.buffer == analog_samples[1] ? 1U
                                                                          : 2U;
                if (slot >= analog_buffers || event.samples != requested)
                {
                    error |= 8U;
                }
                else
                {
                    analog_completed_mask |= 1U << slot;
                    amount += static_cast<std::uint32_t>(event.samples);
                    complete = analog_completed_mask == ((1U << analog_buffers) - 1U);
                }
            }
            else if (event.type == SaadcEventType::error)
            {
                error |= 16U;
            }
        }
        if (started && ready && !complete && analog_sampled < requested * analog_buffers &&
            k_uptime_get() >= next_analog_sample_ms)
        {
            if (saadc->sample() != AnalogFabricResult::success)
            {
                error |= 4096U;
            }
            else
            {
                ++analog_sampled;
                next_analog_sample_ms += 2;
            }
        }
    }
    if (pwm != nullptr)
    {
        PwmSequenceEvent event{};
        while (pwm->takeEvent(event))
        {
            if (event.type == PwmSequenceEventType::playback_complete)
            {
                complete = true;
            }
            else if (event.type == PwmSequenceEventType::error)
            {
                error |= 32U;
            }
        }
    }
    if (i2s != nullptr)
    {
        I2sEvent event{};
        while (i2s->takeEvent(event))
        {
            if (event.type == I2sEventType::buffers_complete)
            {
                const unsigned slot = event.released.receive == i2s_rx[0]   ? 0U
                                      : event.released.receive == i2s_rx[1] ? 1U
                                                                            : 2U;
                if (slot >= i2s_buffers || event.released.transmit != i2s_tx[slot] ||
                    event.released.words != requested)
                {
                    error |= 64U;
                }
                else
                {
                    i2s_completed_mask |= 1U << slot;
                    amount += static_cast<std::uint32_t>(event.released.words);
                    complete = i2s_completed_mask == ((1U << i2s_buffers) - 1U);
                }
            }
            else if (event.type == I2sEventType::error ||
                     (event.type == I2sEventType::underrun && !complete))
            {
                error |= 128U;
            }
        }
    }
    if (pdm != nullptr)
    {
        PdmEvent event{};
        while (pdm->takeEvent(event))
        {
            if (event.type == PdmEventType::buffer_complete)
            {
                const unsigned slot = event.buffer == pdm_samples[0]   ? 0U
                                      : event.buffer == pdm_samples[1] ? 1U
                                                                       : 2U;
                if (slot >= pdm_buffers || event.samples != requested)
                {
                    error |= 256U;
                }
                else
                {
                    pdm_completed_mask |= 1U << slot;
                    amount += static_cast<std::uint32_t>(event.samples);
                    complete = pdm_completed_mask == ((1U << pdm_buffers) - 1U);
                }
            }
            else if (event.type == PdmEventType::overflow || event.type == PdmEventType::error)
            {
                error |= 512U;
            }
        }
    }
    if (pdm_spis != nullptr)
    {
        SpiFabricEvent event{};
        while (pdm_spis->takeEvent(event))
        {
            if (event.type == SpiFabricEventType::buffers_armed)
            {
                ready = true;
            }
            else if (event.type == SpiFabricEventType::transfer_complete)
            {
                complete = true;
                amount = static_cast<std::uint32_t>(event.tx_transferred);
            }
            else if (event.type != SpiFabricEventType::buffer_needed)
            {
                error |= 1024U;
            }
        }
    }
    if (qdec != nullptr)
    {
        QdecEvent event{};
        while (qdec->takeEvent(event))
        {
            if (event.type == QdecEventType::error)
            {
                error |= 2048U;
            }
        }
    }
}

std::uint32_t signalCommand(std::uint32_t opcode, const std::uint32_t *args, std::uint32_t nargs,
                            std::uint32_t *out, std::uint32_t &count)
{
    serviceSignal();
    if (opcode == 32U && nargs == 4U)
    {
        const auto family = v04::fixtureFamily(args[0]);
        if (fixtureClaimed() || prepared ||
            (family != v04::FixtureFamily::analog && family != v04::FixtureFamily::qdec &&
             family != v04::FixtureFamily::i2s && family != v04::FixtureFamily::pdm) ||
            !gate.arm(args[0], args[1], args[2], args[3], role, k_uptime_get()))
        {
            return 403U;
        }
        out[0] = gate.fixture();
        out[1] = static_cast<std::uint32_t>(v04::FixtureGate::lease_ms);
        count = 2U;
        return 0U;
    }
    if (opcode == 33U && nargs == 0U)
    {
        const bool stopped = stopAll();
        gate.close(stopped);
        out[0] = stopped ? 0U : 1U;
        count = 1U;
        return stopped ? 0U : 730U;
    }
    if (opcode == 36U && nargs == 0U)
    {
        out[0] = prepared;
        out[1] = started;
        out[2] = ready;
        out[3] = complete;
        out[4] = error;
        out[5] = amount;
        out[6] = requested;
        out[7] = i2s_completed_mask;
        count = 8U;
        return 0U;
    }
    if (!gate.live(k_uptime_get()))
    {
        return 403U;
    }
    if (opcode == 34U && nargs == 8U)
    {
        const bool result = prepare(args);
        out[0] = result ? 0U : 1U;
        count = 1U;
        return result ? 0U : 731U;
    }
    if (opcode == 35U && nargs == 0U)
    {
        const bool result = start();
        out[0] = result ? 0U : 1U;
        count = 1U;
        return result ? 0U : 732U;
    }
    if (opcode == 37U && v04::fixtureFamily(gate.fixture()) == v04::FixtureFamily::qdec &&
        nargs == 0U && qdec != nullptr)
    {
        QdecEvent event{};
        const auto result = qdec->read(event);
        out[0] = static_cast<std::uint32_t>(result);
        out[1] = static_cast<std::uint32_t>(event.accumulated);
        out[2] = event.double_transitions;
        count = 3U;
        return result == StreamFabricResult::success ? 0U : 733U;
    }
    const auto family = v04::fixtureFamily(gate.fixture());
    const std::uint32_t available = family == v04::FixtureFamily::analog
                                        ? requested * analog_buffers
                                    : family == v04::FixtureFamily::pdm ? requested * pdm_buffers
                                    : family == v04::FixtureFamily::i2s ? requested * i2s_buffers
                                                                        : requested;
    if (opcode == 37U && nargs == 2U && args[1] != 0U && args[1] <= 16U && args[0] <= available &&
        args[1] <= available - args[0])
    {
        if (family == v04::FixtureFamily::i2s && complete)
        {
            for (std::size_t index = 0U; index < args[1]; ++index)
            {
                const std::size_t linear = args[0] + index;
                out[index] = i2s_rx[linear / requested][linear % requested];
            }
            count = args[1];
            return 0U;
        }
        if ((family == v04::FixtureFamily::analog || family == v04::FixtureFamily::pdm) && complete)
        {
            count = (args[1] + 1U) / 2U;
            for (std::size_t index = 0U; index < args[1]; ++index)
            {
                const std::size_t linear = args[0] + index;
                const auto value = static_cast<std::uint16_t>(
                    family == v04::FixtureFamily::analog
                        ? analog_samples[linear / requested][linear % requested]
                        : pdm_samples[linear / requested][linear % requested]);
                out[index / 2U] |= static_cast<std::uint32_t>(value) << (16U * (index % 2U));
            }
            return 0U;
        }
    }
    return 400U;
}
