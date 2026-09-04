/**
 * @file fixture_hil.cpp
 * @brief 고정 UART/SPI/TWI 결선의 비동기 기능 시험입니다.
 * @note 외부 신호 실기 PASS를 생성하지 않습니다. Host가 양쪽 결과를 별도로 판정합니다.
 * SPDX-License-Identifier: MIT
 */
#include "fixture_hil.h"
#include "fixture_gate.h"
#include "serial_hil.h"
#include <nucode/SerialFabric.h>
#include <variant.h>
#include <hal/nrf_gpio.h>
#include <zephyr/kernel.h>
#include <string.h>

namespace
{
    using namespace nucode::arduino;
    constexpr std::uint32_t role = CONFIG_NUCODE_V04_HIL_ROLE;
    constexpr std::uint32_t capacity = 1024;
    struct alignas(4) Buffer
    {
        std::uint8_t before[16];
        std::uint8_t data[capacity];
        std::uint8_t after[16];
    };
    Buffer receive{}, transmit{}, receive_next{}, transmit_next{};
    Buffer uart_receive[2]{};
    struct alignas(4) UartTransmitBuffer
    {
        std::uint8_t before[16];
        std::uint8_t data[capacity * 2];
        std::uint8_t after[16];
    } uart_transmit{};
    v04::FixtureGate gate;
    SerialFabricHandle *handle = nullptr;
    SpimHandle *spim = nullptr;
    SpisHandle *spis = nullptr;
    TwimHandle *twim = nullptr;
    TwimHandle *concurrent_twim = nullptr;
    TwisHandle *twis = nullptr;
    UarteHandle *uarte = nullptr;
    std::uint32_t length = 0, tx_length = 0, rx_length = 0;
    std::uint32_t tx_done = 0, rx_done = 0, errors = 0, ready = 0;
    std::uint32_t tx_amount = 0, rx_amount = 0, address = 0x42;
    std::uint32_t uart_buffers = 0, segments = 1, transfer_style = 0;
    bool kicked = false, second_kicked = false, synchronous = false;
    bool deferred_uart_receive = false, deferred_twis_buffers = false;
    bool gpio_line_generator = false;
    std::uint32_t generator_psel = 0, generator_configuration = 0, generator_output = 0;
    alignas(4) std::uint8_t concurrent_pmic_memory[2]{};
    SerialFabricResult concurrent_pmic_result = SerialFabricResult::wrong_state;

    /** @brief Host와 독립적으로 계산하는 역할별 바이트 패턴입니다. */
    std::uint8_t pattern(std::uint32_t seed, std::uint32_t index)
    {
        return static_cast<std::uint8_t>((seed + 37U * index + index / 8U) ^ (index / 2U));
    }

    void fill(Buffer &buffer)
    {
        memset(buffer.before, 0xa5, sizeof(buffer.before));
        memset(buffer.data, 0xcc, sizeof(buffer.data));
        memset(buffer.after, 0x5a, sizeof(buffer.after));
    }

    bool guards()
    {
        for (unsigned i = 0; i < 16; ++i)
        {
            if (receive.before[i] != 0xa5 || receive.after[i] != 0x5a ||
                transmit.before[i] != 0xa5 || transmit.after[i] != 0x5a ||
                receive_next.before[i] != 0xa5 || receive_next.after[i] != 0x5a ||
                transmit_next.before[i] != 0xa5 || transmit_next.after[i] != 0x5a)
            {
                return false;
            }
        }
        for (unsigned i = rx_length; i < capacity; ++i)
        {
            if (receive.data[i] != 0xcc)
            {
                return false;
            }
        }
        for (unsigned i = segments == 2 ? rx_length : 0; i < capacity; ++i)
        {
            if (receive_next.data[i] != 0xcc)
            {
                return false;
            }
        }
        return true;
    }

    /** @brief UART의 두 RX buffer와 연속 TX buffer guard를 검사합니다. */
    bool uartGuards()
    {
        for (unsigned slot = 0; slot < 2; ++slot)
        {
            for (unsigned i = 0; i < 16; ++i)
            {
                if (uart_receive[slot].before[i] != 0xa5 || uart_receive[slot].after[i] != 0x5a)
                {
                    return false;
                }
            }
            for (unsigned i = slot < uart_buffers ? length : 0; i < capacity; ++i)
            {
                if (uart_receive[slot].data[i] != 0xcc)
                {
                    return false;
                }
            }
        }
        for (unsigned i = 0; i < 16; ++i)
        {
            if (uart_transmit.before[i] != 0xa5 || uart_transmit.after[i] != 0x5a)
            {
                return false;
            }
        }
        return true;
    }

    /** @brief 오류 주입 GPIO의 OUT latch와 PIN_CNF를 원래 값으로 복원합니다. */
    void restoreGenerator()
    {
        if (!gpio_line_generator)
        {
            return;
        }
        auto pin = generator_psel;
        auto *const port = nrf_gpio_pin_port_decode(&pin);
        nrf_gpio_pin_write(generator_psel, generator_output);
        port->PIN_CNF[pin] = generator_configuration;
        gpio_line_generator = false;
    }

    /** @brief STOP이 실패하면 포인터와 lease를 보존하고 재사용을 거부합니다. */
    SerialFabricResult stop()
    {
        const auto concurrent_result =
            concurrent_twim != nullptr && concurrent_twim->state() == SerialFabricState::active
                ? concurrent_twim->deactivate(100000)
                : SerialFabricResult::success;
        const auto state = handle ? handle->state() : SerialFabricState::inactive;
        const auto result =
            handle && state != SerialFabricState::inactive && state != SerialFabricState::staged
                ? handle->deactivate(100000)
                : SerialFabricResult::success;
        if (result == SerialFabricResult::success &&
            concurrent_result == SerialFabricResult::success)
        {
            restoreGenerator();
            handle = nullptr;
            spim = nullptr;
            spis = nullptr;
            twim = nullptr;
            concurrent_twim = nullptr;
            twis = nullptr;
            uarte = nullptr;
        }
        return result != SerialFabricResult::success ? result : concurrent_result;
    }

    /** @brief SPIM00과 겹쳐 실행할 read-only PMIC TWIM22를 미리 활성화합니다. */
    SerialFabricResult prepareConcurrentPmic()
    {
        concurrent_twim = serialFabric().twim(22U);
        const SerialSignalPin pins[] = {{SerialSignal::sda, PIN_P1_02},
                                        {SerialSignal::scl, PIN_P1_03}};
        const SerialDmaWorkspace workspace{concurrent_pmic_memory, sizeof(concurrent_pmic_memory)};
        const SerialFabricConfiguration route{SerialRouteClass::p1_flexible,
                                              SerialElectricalProfile::pmic_read_only,
                                              pins,
                                              2U,
                                              &workspace,
                                              1U};
        if (concurrent_twim == nullptr)
        {
            return SerialFabricResult::unsupported_instance;
        }
        auto result = concurrent_twim->configure({TwiFabricFrequency::standard});
        if (result == SerialFabricResult::success)
        {
            result = concurrent_twim->stage(route);
        }
        if (result == SerialFabricResult::success)
        {
            result = concurrent_twim->activate();
        }
        return result;
    }

    /** @brief 고정 결선의 UART 교차 TX/RX·RTS/CTS 핀을 배정합니다. */
    void uartPins(v04::Bank bank, bool flow_control, SerialSignalPin *pins)
    {
        if (bank == v04::Bank::p2)
        {
            pins[0] = {SerialSignal::txd, PIN_P2_02};
            pins[1] = {SerialSignal::rxd, PIN_P2_00};
            pins[2] = {SerialSignal::rts, PIN_P2_05};
            pins[3] = {SerialSignal::cts, PIN_P2_04};
        }
        else if (bank == v04::Bank::p0)
        {
            pins[0] = {SerialSignal::txd, PIN_P0_00};
            pins[1] = {SerialSignal::rxd, PIN_P0_01};
            pins[2] = {SerialSignal::rts, PIN_P0_02};
            pins[3] = {SerialSignal::cts, PIN_P0_03};
        }
        else
        {
            pins[0] = {SerialSignal::txd, PIN_P1_04};
            pins[1] = {SerialSignal::rxd, PIN_P1_05};
            pins[2] = {SerialSignal::rts, PIN_P1_06};
            pins[3] = {SerialSignal::cts, PIN_P1_07};
        }
        if (!flow_control)
        {
            pins[2] = {};
            pins[3] = {};
        }
    }

    /** @brief 고정 결선의 양방향 데이터 선을 personality에 맞게 배정합니다. */
    void spiPins(v04::Bank bank, bool controller, SerialSignalPin *pins)
    {
        pin_size_t clock, mosi, miso, select;
        if (bank == v04::Bank::p2)
        {
            clock = PIN_P2_01;
            select = PIN_P2_05;
            mosi = controller ? PIN_P2_02 : PIN_P2_04;
            miso = controller ? PIN_P2_04 : PIN_P2_02;
        }
        else if (bank == v04::Bank::p0)
        {
            clock = PIN_P0_00;
            mosi = PIN_P0_01;
            miso = PIN_P0_02;
            select = PIN_P0_03;
        }
        else
        {
            clock = PIN_P1_04;
            select = PIN_P1_07;
            const bool swapped = gate.fixture() == 201 && gate.controller() == 2;
            mosi = swapped ? PIN_P1_06 : PIN_P1_05;
            miso = swapped ? PIN_P1_05 : PIN_P1_06;
        }
        pins[0] = {SerialSignal::sck, clock};
        pins[1] = {SerialSignal::mosi, mosi};
        pins[2] = {SerialSignal::miso, miso};
        pins[3] = {SerialSignal::csn, select};
    }

    /**
     * @brief 전송 전에 설정·DMA 버퍼를 준비합니다.
     * @param args instance, rate, mode, lsb, bytes, seed, direction, address 순서입니다.
     * direction은 controller 기준 write=1/read=2/duplex=3입니다.
     */
    std::uint32_t prepare(const std::uint32_t *args, std::uint32_t *out, std::uint32_t &count)
    {
        const auto family = v04::fixtureFamily(gate.fixture());
        const bool uart = family == v04::FixtureFamily::uarte;
        const bool i2c = family == v04::FixtureFamily::twi;
        const auto requested_address = args[7] & 0x7fU;
        const auto requested_style = i2c ? args[7] >> 8U : args[7];
        const bool controller = gate.controller() == role;
        const auto bank = v04::fixtureBank(gate.fixture(), role);
        if (handle || !v04::fixtureInstance(bank, args[0]) || !args[4] ||
            args[4] > (i2c ? 256U : capacity) || args[2] > (uart ? 1U : 3U) || args[3] > 1 ||
            args[6] < 1 || args[6] > (uart ? 4U : 3U) ||
            (i2c && (args[2] || args[3] ||
                     ((requested_address != 0x42 && requested_address != 0x43) &&
                      !(requested_address == 0x44 && requested_style == 3 && args[6] == 1)) ||
                     requested_style > 6)) ||
            (!i2c && !uart && args[7] > 4) ||
            (i2c && args[1] != 100000 && args[1] != 400000 && args[1] != 1000000) ||
            (!i2c && !uart && args[1] != 125000 && args[1] != 1000000 && args[1] != 4000000) ||
            (uart && args[1] != 9600 && args[1] != 115200 && args[1] != 1000000) ||
            (uart &&
             ((args[6] < 1 || args[6] > 4) || (args[6] == 2 && (!args[3] || args[7] != 1)) ||
              (args[6] == 3 && (args[3] || args[7] != 1)) ||
              (args[6] == 4 && (args[2] || args[3] || args[7] != 1)) ||
              (args[7] != 1 && args[7] != 2))))
        {
            return 400;
        }
        length = args[4];
        uart_buffers = uart ? args[7] : 0;
        transfer_style = requested_style;
        segments = !uart && transfer_style == 2 ? 2U : 1U;
        tx_length = uart ? (controller ? length * uart_buffers : 0U)
                         : ((args[6] & (controller ? 1U : 2U)) ? length : 0U);
        rx_length = uart ? (controller ? 0U : length * uart_buffers)
                         : ((args[6] & (controller ? 2U : 1U)) ? length : 0U);
        /** SPI의 반대 방향도 ORC를 수신하여 단방향 의미를 검사합니다. */
        if (!i2c && !uart)
        {
            rx_length = length;
        }
        fill(receive);
        fill(transmit);
        fill(receive_next);
        fill(transmit_next);
        if (uart)
        {
            fill(uart_receive[0]);
            fill(uart_receive[1]);
            memset(uart_transmit.before, 0xa5, sizeof(uart_transmit.before));
            memset(uart_transmit.data, 0xcc, sizeof(uart_transmit.data));
            memset(uart_transmit.after, 0x5a, sizeof(uart_transmit.after));
        }
        for (unsigned i = 0; i < length; ++i)
        {
            transmit.data[i] = pattern(args[5] ^ (role == 1 ? 0U : 0x5aU), i);
            transmit_next.data[i] = pattern(args[5] ^ (role == 1 ? 0U : 0x5aU), length + i);
        }
        for (unsigned i = 0; i < tx_length; ++i)
        {
            uart_transmit.data[i] = pattern(args[5] ^ (role == 1 ? 0U : 0x5aU), i);
        }
        tx_done = rx_done = errors = ready = tx_amount = rx_amount = 0;
        kicked = second_kicked = false;
        synchronous = !uart && transfer_style == 1;
        deferred_uart_receive = uart && args[6] == 2;
        deferred_twis_buffers = i2c && requested_style == 6 && !controller;
        gpio_line_generator = false;
        address = i2c ? requested_address : args[7];
        concurrent_twim = nullptr;
        concurrent_pmic_result = SerialFabricResult::wrong_state;
        SerialSignalPin pins[4]{};
        if (uart)
        {
            uartPins(bank, args[3] != 0, pins);
        }
        else if (i2c)
        {
            pins[0] = {SerialSignal::sda,
                       static_cast<pin_size_t>(bank == v04::Bank::p1 ? PIN_P1_04 : PIN_P0_00)};
            pins[1] = {SerialSignal::scl,
                       static_cast<pin_size_t>(bank == v04::Bank::p1 ? PIN_P1_05 : PIN_P0_01)};
        }
        else
        {
            spiPins(bank, controller, pins);
        }
        const SerialDmaWorkspace work[] = {{transmit.data, capacity},
                                           {receive.data, capacity},
                                           {transmit_next.data, capacity},
                                           {receive_next.data, capacity}};
        const SerialDmaWorkspace uart_work[] = {{uart_transmit.data, sizeof(uart_transmit.data)},
                                                {uart_receive[0].data, capacity},
                                                {uart_receive[1].data, capacity}};
        const auto route_class = bank == v04::Bank::p2   ? SerialRouteClass::p2_dedicated20
                                 : bank == v04::Bank::p1 ? SerialRouteClass::p1_flexible
                                                         : SerialRouteClass::p0_flexible;
        const auto profile = bank == v04::Bank::p2 ? SerialElectricalProfile::connector_fixture
                                                   : SerialElectricalProfile::dap_uart_disabled;
        const SerialFabricConfiguration route{route_class,
                                              profile,
                                              pins,
                                              uart ? (args[3] ? 4U : 2U) : (i2c ? 2U : 4U),
                                              uart ? uart_work : work,
                                              uart ? 3U : (segments == 2 ? 4U : 2U)};
        const SpiFabricConfiguration spi{args[1], static_cast<SpiFabricMode>(args[2]),
                                         static_cast<SpiFabricBitOrder>(args[3]), 0x96};
        SerialFabricResult result;
        if (uart && args[6] == 4 && controller)
        {
            generator_psel = bank == v04::Bank::p2   ? NRF_GPIO_PIN_MAP(2, 2)
                             : bank == v04::Bank::p0 ? NRF_GPIO_PIN_MAP(0, 0)
                                                     : NRF_GPIO_PIN_MAP(1, 4);
            auto pin = generator_psel;
            auto *const port = nrf_gpio_pin_port_decode(&pin);
            generator_configuration = port->PIN_CNF[pin];
            generator_output = nrf_gpio_pin_out_read(generator_psel);
            nrf_gpio_pin_set(generator_psel);
            nrf_gpio_cfg_output(generator_psel);
            gpio_line_generator = true;
            ready = 1;
            result = SerialFabricResult::success;
        }
        else if (i2c && requested_style == 5 && !controller)
        {
            generator_psel =
                bank == v04::Bank::p1 ? NRF_GPIO_PIN_MAP(1, 4) : NRF_GPIO_PIN_MAP(0, 0);
            auto pin = generator_psel;
            auto *const port = nrf_gpio_pin_port_decode(&pin);
            generator_configuration = port->PIN_CNF[pin];
            generator_output = nrf_gpio_pin_out_read(generator_psel);
            nrf_gpio_pin_clear(generator_psel);
            nrf_gpio_cfg_output(generator_psel);
            gpio_line_generator = true;
            ready = 1;
            result = SerialFabricResult::success;
        }
        else if (uart)
        {
            uarte = serialFabric().uarte(args[0]);
            handle = uarte;
            const auto parity = args[6] == 3 ? (controller ? UarteParity::none : UarteParity::even)
                                             : (args[2] ? UarteParity::even : UarteParity::none);
            result = uarte ? uarte->configure({args[1], parity, args[3] != 0, args[7] == 2})
                           : SerialFabricResult::unsupported_instance;
        }
        else if (!i2c && controller)
        {
            spim = serialFabric().spim(args[0]);
            handle = spim;
            result = spim ? spim->configure(spi) : SerialFabricResult::unsupported_instance;
        }
        else if (!i2c)
        {
            spis = serialFabric().spis(args[0]);
            handle = spis;
            result = spis ? spis->configure(spi) : SerialFabricResult::unsupported_instance;
        }
        else if (controller)
        {
            twim = serialFabric().twim(args[0]);
            handle = twim;
            result = twim ? twim->configure({static_cast<TwiFabricFrequency>(args[1])})
                          : SerialFabricResult::unsupported_instance;
        }
        else
        {
            twis = serialFabric().twis(args[0]);
            handle = twis;
            result = twis ? twis->configure({0x42, 0x43, false})
                          : SerialFabricResult::unsupported_instance;
        }
        if (result == SerialFabricResult::success && !gpio_line_generator)
        {
            result = handle->stage(route);
        }
        if (result == SerialFabricResult::success && !gpio_line_generator &&
            !(i2c && requested_style == 5 && controller))
        {
            result = handle->activate();
        }
        if (result == SerialFabricResult::success && !i2c && !uart && requested_style == 4U &&
            controller)
        {
            if (gate.fixture() != 201U || args[0] != 0U)
            {
                result = SerialFabricResult::unsupported_route;
            }
            else
            {
                result = prepareConcurrentPmic();
            }
        }
        if (result == SerialFabricResult::success && uart && !controller && !deferred_uart_receive)
        {
            result = uarte->receiveAsync(uart_receive[0].data, length,
                                         uart_buffers == 2 ? uart_receive[1].data : nullptr,
                                         uart_buffers == 2 ? length : 0U);
            if (result == SerialFabricResult::success)
            {
                ready = 1;
            }
        }
        else if (result == SerialFabricResult::success &&
                 v04::shouldQueueSerialPeripheralBuffers(uart, controller, gpio_line_generator,
                                                         deferred_twis_buffers))
        {
            const auto *tx = tx_length ? transmit.data : nullptr;
            auto *rx = rx_length ? receive.data : nullptr;
            const auto *next_tx = segments == 2 && tx_length ? transmit_next.data : nullptr;
            auto *next_rx = segments == 2 && rx_length ? receive_next.data : nullptr;
            result = i2c ? twis->queueBuffers(tx, tx_length, rx, rx_length, next_tx,
                                              segments == 2 ? tx_length : 0, next_rx,
                                              segments == 2 ? rx_length : 0)
                         : spis->queueBuffers(tx, tx_length, rx, rx_length, next_tx,
                                              segments == 2 ? tx_length : 0, next_rx,
                                              segments == 2 ? rx_length : 0);
            if (i2c && result == SerialFabricResult::success)
            {
                ready = 1;
            }
        }
        out[0] = static_cast<std::uint32_t>(result);
        count = 1;
        if (result != SerialFabricResult::success)
        {
            errors |= 1;
            /** @brief 활성화 이후 실패는 즉시 STOP을 요청하며 원래 실패를 숨기지 않습니다. */
            if (handle && handle->state() != SerialFabricState::inactive &&
                handle->state() != SerialFabricState::staged)
            {
                out[1] = static_cast<std::uint32_t>(stop());
                count = 2;
            }
            /** @brief 실패한 세션의 재사용은 STOP 성공 여부와 별개로 거부합니다. */
            gate.close(false);
            return 701;
        }
        return 0;
    }

    /** @brief UART 완료 event의 buffer·길이·중복 여부를 검사합니다. */
    void uartEvent(const UarteEvent &event)
    {
        if (event.type == UarteEventType::tx_complete)
        {
            ++tx_done;
            tx_amount = event.transferred;
            if (event.buffer != uart_transmit.data || event.transferred != tx_length)
            {
                errors |= 128;
            }
        }
        else if (event.type == UarteEventType::rx_complete)
        {
            unsigned slot = event.buffer == uart_receive[0].data   ? 0U
                            : event.buffer == uart_receive[1].data ? 1U
                                                                   : 2U;
            if (slot >= uart_buffers || event.transferred != length ||
                (rx_done & (1U << slot)) != 0)
            {
                errors |= 256;
            }
            else
            {
                rx_done |= 1U << slot;
                rx_amount += event.transferred;
            }
        }
        else if (event.type != UarteEventType::rx_buffer_needed)
        {
            errors |= 512;
        }
        if (!uartGuards())
        {
            errors |= 1024;
        }
    }

    void spiEvent(const SpiFabricEvent &event)
    {
        if (event.type == SpiFabricEventType::buffers_armed)
        {
            ready = 1;
        }
        else if (event.type == SpiFabricEventType::transfer_complete)
        {
            ++tx_done;
            ++rx_done;
            tx_amount += event.tx_transferred;
            rx_amount += event.rx_transferred;
            const bool first = event.tx_buffer == (tx_length ? transmit.data : nullptr) &&
                               event.rx_buffer == receive.data;
            const bool second = segments == 2 &&
                                event.tx_buffer == (tx_length ? transmit_next.data : nullptr) &&
                                event.rx_buffer == receive_next.data;
            if ((!first && !second) || event.tx_transferred != tx_length ||
                event.rx_transferred != rx_length)
            {
                errors |= 2;
            }
        }
        else if (event.type != SpiFabricEventType::buffer_needed)
        {
            errors |= 4;
        }
    }

    void twiEvent(const TwiFabricEvent &event)
    {
        if (event.type == TwiFabricEventType::transfer_complete ||
            event.type == TwiFabricEventType::read_complete)
        {
            ++tx_done;
            tx_amount += event.tx_transferred;
            const bool first = event.tx_buffer == (tx_length ? transmit.data : nullptr);
            const bool second =
                segments == 2 && event.tx_buffer == (tx_length ? transmit_next.data : nullptr);
            if ((!first && !second) || event.tx_transferred != tx_length)
            {
                errors |= 8;
            }
        }
        if (event.type == TwiFabricEventType::transfer_complete ||
            event.type == TwiFabricEventType::write_complete)
        {
            ++rx_done;
            rx_amount += event.rx_transferred;
            const bool first = event.rx_buffer == (rx_length ? receive.data : nullptr);
            const bool second =
                segments == 2 && event.rx_buffer == (rx_length ? receive_next.data : nullptr);
            if ((!first && !second) || event.rx_transferred != rx_length)
            {
                errors |= 16;
            }
        }
        if (event.type != TwiFabricEventType::transfer_complete &&
            event.type != TwiFabricEventType::read_complete &&
            event.type != TwiFabricEventType::write_complete &&
            event.type != TwiFabricEventType::read_request &&
            event.type != TwiFabricEventType::write_request &&
            event.type != TwiFabricEventType::buffer_needed)
        {
            errors |= 32;
        }
    }
} // namespace

bool fixtureClaimed()
{
    return gate.claimed();
}

void serviceFixture()
{
    if (gate.fixture() && !gate.live(k_uptime_get()))
    {
        errors |= 64;
        gate.close(stop() == SerialFabricResult::success);
    }
    if (!handle)
    {
        return;
    }
    SpiFabricEvent spi{};
    TwiFabricEvent twi{};
    UarteEvent uart{};
    while (uarte && uarte->takeEvent(uart))
    {
        uartEvent(uart);
    }
    while ((spim && spim->takeEvent(spi)) || (spis && spis->takeEvent(spi)))
    {
        spiEvent(spi);
    }
    while ((twim && twim->takeEvent(twi)) || (twis && twis->takeEvent(twi)))
    {
        twiEvent(twi);
    }
    if (handle && gate.controller() == role && segments == 2 && kicked && !second_kicked &&
        tx_done == 1 && rx_done == 1 && !errors)
    {
        second_kicked = true;
        const auto *tx = tx_length ? transmit_next.data : nullptr;
        auto *rx = rx_length ? receive_next.data : nullptr;
        const auto result = spim ? spim->transferAsync(tx, tx_length, rx, rx_length)
                                 : twim->transferAsync(address, tx, tx_length, rx, rx_length);
        if (result != SerialFabricResult::success)
        {
            errors |= 2048;
        }
    }
}

std::uint32_t fixtureCommand(std::uint32_t opcode, const std::uint32_t *args, std::uint32_t nargs,
                             std::uint32_t *out, std::uint32_t &count)
{
    serviceFixture();
    if (opcode == 16 && nargs == 4)
    {
        const auto family = v04::fixtureFamily(args[0]);
        const bool serial_family = family == v04::FixtureFamily::uarte ||
                                   family == v04::FixtureFamily::spi ||
                                   family == v04::FixtureFamily::twi;
        if (!serial_family || onboardSerialActive() || handle ||
            !gate.arm(args[0], args[1], args[2], args[3], role, k_uptime_get()))
        {
            return 403;
        }
        out[0] = gate.fixture();
        out[1] = v04::FixtureGate::lease_ms;
        count = 2;
        return 0;
    }
    if (opcode == 17 && nargs == 0)
    {
        const auto result = stop();
        gate.close(result == SerialFabricResult::success);
        out[0] = static_cast<std::uint32_t>(result);
        count = 1;
        return result == SerialFabricResult::success ? 0 : 702;
    }
    if (opcode == 22 && nargs == 0)
    {
        const bool uart = v04::fixtureFamily(gate.fixture()) == v04::FixtureFamily::uarte;
        out[0] = handle != nullptr || gpio_line_generator;
        out[1] = ready;
        out[2] = tx_done;
        out[3] = rx_done;
        out[4] = errors;
        out[5] = length && (uart ? uartGuards() : guards());
        out[6] = tx_amount;
        out[7] = rx_amount;
        count = 8;
        return 0;
    }
    if (!gate.live(k_uptime_get()))
    {
        return 403;
    }
    if (opcode == 18 && nargs == 0)
    {
        return gate.renew(k_uptime_get()) ? 0 : 403;
    }
    if (opcode == 19 && nargs == 0 && uarte && gate.controller() != role && deferred_uart_receive &&
        ready == 0)
    {
        const auto result = uarte->receiveAsync(uart_receive[0].data, length);
        out[0] = static_cast<std::uint32_t>(result);
        count = 1;
        if (result == SerialFabricResult::success)
        {
            ready = 1;
        }
        return result == SerialFabricResult::success ? 0 : 705;
    }
    if (opcode == 25 && nargs == 0 && gate.controller() != role)
    {
        if (gpio_line_generator && transfer_style == 5)
        {
            restoreGenerator();
            ready = 2;
            out[0] = static_cast<std::uint32_t>(SerialFabricResult::success);
            count = 1;
            return 0;
        }
        if (twis && deferred_twis_buffers && ready == 0)
        {
            const auto *tx = tx_length ? transmit.data : nullptr;
            auto *rx = rx_length ? receive.data : nullptr;
            const auto result = twis->queueBuffers(tx, tx_length, rx, rx_length);
            out[0] = static_cast<std::uint32_t>(result);
            count = 1;
            if (result == SerialFabricResult::success)
            {
                deferred_twis_buffers = false;
                ready = 1;
            }
            return result == SerialFabricResult::success ? 0 : 706;
        }
    }
    if (opcode == 20 && nargs == 8)
    {
        return prepare(args, out, count);
    }
    if (opcode == 21 && nargs == 0 && (handle || gpio_line_generator) && !kicked &&
        gate.controller() == role)
    {
        kicked = true;
        const auto *tx = tx_length ? transmit.data : nullptr;
        auto *rx = rx_length ? receive.data : nullptr;
        SerialFabricResult result;
        if (gpio_line_generator)
        {
            nrf_gpio_pin_clear(generator_psel);
            k_busy_wait(1000);
            nrf_gpio_pin_set(generator_psel);
            result = SerialFabricResult::success;
            tx_done = 1;
        }
        else if (uarte)
        {
            result = uarte->transmitAsync(uart_transmit.data, tx_length);
        }
        else if (spim && synchronous)
        {
            result = spim->transfer(tx, tx_length, rx, rx_length, 2000000);
        }
        else if (twim && synchronous)
        {
            result = twim->transfer(address, tx, tx_length, rx, rx_length, 2000000);
        }
        else
        {
            result = twim && transfer_style == 5 ? twim->recoverBus()
                     : spim ? spim->transferAsync(tx, tx_length, rx, rx_length)
                            : twim->transferAsync(address, tx, tx_length, rx, rx_length);
        }
        if (result == SerialFabricResult::success && spim != nullptr && transfer_style == 4U &&
            concurrent_twim != nullptr)
        {
            concurrent_pmic_memory[0] = 0x0cU;
            concurrent_pmic_memory[1] = 0U;
            concurrent_pmic_result = concurrent_twim->transfer(
                0x6aU, concurrent_pmic_memory, 1U, concurrent_pmic_memory + 1U, 1U, 100000U);
            if (concurrent_pmic_result != SerialFabricResult::success ||
                concurrent_pmic_memory[1] != 0x41U)
            {
                result = concurrent_pmic_result != SerialFabricResult::success
                             ? concurrent_pmic_result
                             : SerialFabricResult::driver_error;
            }
        }
        if (result == SerialFabricResult::success && synchronous)
        {
            tx_done = 1;
            rx_done = 1;
            tx_amount = tx_length;
            rx_amount = rx_length;
        }
        if (result == SerialFabricResult::success && spim && address == 3)
        {
            result = spim->cancelTransfer();
        }
        if (result == SerialFabricResult::success && twim && transfer_style == 4)
        {
            result = twim->cancelTransfer();
        }
        out[0] = static_cast<std::uint32_t>(result);
        count = 1;
        return twim && transfer_style == 5 ? 0 : (result == SerialFabricResult::success ? 0 : 703);
    }
    if (opcode == 26 && nargs == 0 && twim && transfer_style == 5 && gate.controller() == role &&
        handle->state() == SerialFabricState::staged)
    {
        const auto result = twim->recoverBus();
        out[0] = static_cast<std::uint32_t>(result);
        count = 1;
        return 0;
    }
    if (opcode == 27 && nargs == 0 && spim != nullptr && transfer_style == 4U &&
        gate.controller() == role && concurrent_twim != nullptr)
    {
        out[0] = static_cast<std::uint32_t>(concurrent_pmic_result);
        out[1] = concurrent_pmic_memory[1];
        out[2] = static_cast<std::uint32_t>(concurrent_twim->state());
        count = 3U;
        return concurrent_pmic_result == SerialFabricResult::success &&
                       concurrent_pmic_memory[1] == 0x41U &&
                       concurrent_twim->state() == SerialFabricState::active
                   ? 0U
                   : 707U;
    }
    if (opcode == 23 && nargs == 0)
    {
        const bool uart = v04::fixtureFamily(gate.fixture()) == v04::FixtureFamily::uarte;
        const auto result = stop();
        out[0] = static_cast<std::uint32_t>(result);
        out[1] = length && (uart ? uartGuards() : guards());
        count = 2;
        if (result != SerialFabricResult::success)
        {
            gate.close(false);
        }
        return result == SerialFabricResult::success ? 0 : 704;
    }
    /** @brief RX 완료 뒤에만 최대 64바이트를 읽어 Host의 전 바이트 대조에 사용합니다. */
    const bool uart = v04::fixtureFamily(gate.fixture()) == v04::FixtureFamily::uarte;
    const std::uint32_t expected_uart_done = (1U << uart_buffers) - 1U;
    if (opcode == 24 && nargs == 2 &&
        ((!uart && rx_done == segments) || (uart && rx_done == expected_uart_done)) && !errors &&
        args[1] && args[1] <= 64 && args[0] <= rx_length && args[1] <= rx_length - args[0])
    {
        count = (args[1] + 3U) / 4U;
        for (unsigned i = 0; i < args[1]; ++i)
        {
            const auto offset = args[0] + i;
            const auto value = uart ? uart_receive[offset / length].data[offset % length]
                               : offset < length ? receive.data[offset]
                                                 : receive_next.data[offset - length];
            out[i / 4U] |= static_cast<std::uint32_t>(value) << (8U * (i % 4U));
        }
        return 0;
    }
    return 400;
}
