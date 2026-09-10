/**
 * @file power.cpp
 * @brief S 결선의 UART21 중계와 제한 시간·retention을 갖춘 B System OFF 시험입니다.
 * @note A/B P1.06 TX·P1.07 RX 교차선과 P1.14 wake만 사용합니다.
 * SPDX-License-Identifier: MIT
 */
#include "power.h"
#include "engine.h"
#include "protocol.h"
#include <nucode/SerialFabric.h>
#include <internal/IoResourceManager.h>
#include <hal/nrf_gpio.h>
#include <hal/nrf_uarte.h>
#include <zephyr/device.h>
#include <zephyr/drivers/clock_control/nrf_clock_control.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/drivers/hwinfo.h>
#include <zephyr/drivers/retained_mem.h>
#include <zephyr/drivers/timer/nrf_grtc_timer.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/poweroff.h>
#include <zephyr/sys/onoff.h>
#include <string.h>

extern "C" volatile std::uint32_t v04_identity[16];

extern "C"
{
    /** @brief 최초 UART 오류를 STOP 이후에도 읽을 수 있는 전용 진단 원본입니다. */
    alignas(4) volatile std::uint32_t v04_power_fault[20]{};
    /** @brief 합성 큐 초과와 별도로 처음 전달된 하드웨어 오류를 보존합니다. */
    alignas(4) volatile std::uint32_t v04_power_hardware_fault[20]{};
    /** @brief UART RX 시작 전 내부 pull-up 적용과 실제 유휴 수준을 부팅별로 보존합니다. */
    alignas(4) volatile std::uint32_t v04_power_idle[20]{};
}

namespace
{
    using namespace nucode::arduino;
    using namespace nucode::arduino::internal;
    constexpr std::uint32_t role = CONFIG_NUCODE_V04_HIL_ROLE;
    constexpr std::uint32_t magic = 0x504F5731U;
    constexpr unsigned frame_bytes = 128U, wake_pin = 46U;
    constexpr char revision[] = NUCODE_HIL_CORE_REVISION;
    const auto *const retained_device = DEVICE_DT_GET(DT_NODELABEL(t13_retained));
    const gpio_dt_spec wake_gpio{DEVICE_DT_GET(DT_NODELABEL(gpio1)), 14U, 0U};

    /** @brief source·nonce·정확한 다음 reset 단계까지 checksum으로 묶어 보존합니다. */
    struct Retained
    {
        std::uint32_t magic_word = 0U;
        char source[40]{};
        std::uint32_t nonce[4]{};
        std::uint32_t sequence = 0U, pending = 0U, boots = 0U;
        std::uint32_t mode = 0U, round = 0U, seed = 0U, released = 0U;
        std::uint32_t poll_mode = 0U;
        std::uint32_t checksum = 0U;
    } retained;

    UarteHandle *uart = nullptr;
    t13::Buffer tx{}, rx{};
    SerialSignalPin pins[2]{{SerialSignal::txd, 0U}, {SerialSignal::rxd, 0U}};
    SerialDmaWorkspace workspaces[2]{};
    IoResourceToken wake_token{};
    std::uint32_t staged[v04::words]{}, received[v04::words]{};
    std::uint32_t pages = 0U, error = 0U, reset_cause = 0U;
    std::uint32_t tx_count = 0U, rx_count = 0U, retained_valid = 0U;
    std::uint64_t deadline = 0U, wake_at = 0U, wake_end = 0U, off_after = 0U;
    bool active = false, receiving = false, tx_pending = false, ready = false;
    bool stop_after_reply = false;
    bool stop_proven = true;
    onoff_manager *clock_manager = nullptr;
    onoff_client clock_client{};
    bool clock_held = false;

    /** @brief UART 응답을 잃어도 재접속 뒤 읽기만으로 STOP 증거를 확인하게 합니다. */
    void stamp()
    {
        v04_identity[15] = 0x53540000U | (wake_token.active ? 1U : 0U) | (active ? 2U : 0U) |
                           (stop_proven ? 4U : 0U) | (clock_held ? 8U : 0U) | (error << 8U);
    }

    /** @brief 최초 실제 UART event와 주변장치·신호 수준을 변경 없이 보존합니다. */
    void captureFault(const UarteEvent &event)
    {
        const bool first = v04_power_fault[0] == 0U;
        const bool hardware = event.type == UarteEventType::error && event.error_mask != 0U &&
                              (event.error_mask & ~0x0FU) == 0U &&
                              v04_power_hardware_fault[0] == 0U;
        if (!first && !hardware)
        {
            return;
        }
        const auto *registers = NRF_UARTE21;
        const auto tx_pin = nrf_uarte_tx_pin_get(registers);
        const auto rx_pin = nrf_uarte_rx_pin_get(registers);
        const std::uint32_t values[]{0U,
                                     role,
                                     static_cast<std::uint32_t>(k_uptime_get()),
                                     static_cast<std::uint32_t>(event.type),
                                     event.error_mask,
                                     reinterpret_cast<std::uintptr_t>(event.buffer),
                                     static_cast<std::uint32_t>(event.transferred),
                                     receiving ? 1U : 0U,
                                     tx_pending ? 1U : 0U,
                                     ready ? 1U : 0U,
                                     registers->BAUDRATE,
                                     registers->CONFIG,
                                     registers->ENABLE,
                                     tx_pin,
                                     rx_pin,
                                     tx_pin < 96U ? nrf_gpio_pin_read(tx_pin) : UINT32_MAX,
                                     rx_pin < 96U ? nrf_gpio_pin_read(rx_pin) : UINT32_MAX,
                                     NRF_CLOCK->XO.STAT,
                                     retained.boots,
                                     (active ? 1U : 0U) | (wake_token.active ? 2U : 0U) |
                                         (tx.guards(frame_bytes) ? 4U : 0U) |
                                         (rx.guards(frame_bytes) ? 8U : 0U)};
        for (unsigned index = 1U; index < 20U; ++index)
        {
            if (first)
            {
                v04_power_fault[index] = values[index];
            }
            if (hardware)
            {
                v04_power_hardware_fault[index] = values[index];
            }
        }
        __DMB();
        if (first)
        {
            v04_power_fault[0] = 0x50464531U;
        }
        if (hardware)
        {
            v04_power_hardware_fault[0] = 0x50464531U;
        }
    }

    std::uint32_t retainedChecksum()
    {
        std::uint32_t value = t13::hash_initial;
        const auto *bytes = reinterpret_cast<const std::uint8_t *>(&retained);
        for (unsigned index = 0U; index < offsetof(Retained, checksum); ++index)
        {
            value = t13::hashByte(value, bytes[index]);
        }
        return value;
    }

    bool save()
    {
        retained.checksum = retainedChecksum();
        return device_is_ready(retained_device) &&
               retained_mem_write(retained_device, 0U,
                                  reinterpret_cast<const std::uint8_t *>(&retained),
                                  sizeof(retained)) == 0;
    }

    bool failure(std::uint32_t value)
    {
        if (error == 0U)
        {
            error = value;
        }
        return false;
    }

    /** @brief 디버그 유무와 관계없이 UART 구간의 외부 크리스털 참조를 획득합니다. */
    bool requestClock()
    {
        clock_manager = z_nrf_clock_control_get_onoff(CLOCK_CONTROL_NRF_SUBSYS_HF);
        if (clock_manager == nullptr || clock_held)
        {
            return failure(50U);
        }
        sys_notify_init_spinwait(&clock_client.notify);
        if (onoff_request(clock_manager, &clock_client) < 0)
        {
            return failure(51U);
        }
        clock_held = true;
        const auto until = k_uptime_get() + 1000U;
        int completed = 0, notification = -EAGAIN;
        while ((notification = sys_notify_fetch_result(&clock_client.notify, &completed)) ==
               -EAGAIN)
        {
            if (k_uptime_get() >= until)
            {
                return failure(52U);
            }
            k_sleep(K_MSEC(1));
        }
        return (notification == 0 && completed == 0 &&
                (NRF_CLOCK->XO.STAT & CLOCK_XO_STAT_STATE_Msk) != 0U) ||
               failure(53U);
    }

    /** @brief 이 시험이 획득한 참조만 취소·반환하며 다른 사용자의 참조는 유지합니다. */
    bool releaseClock()
    {
        if (clock_held)
        {
            if (onoff_cancel_or_release(clock_manager, &clock_client) < 0)
            {
                return failure(54U);
            }
            clock_held = false;
        }
        return true;
    }

    /** @brief DMA STOP와 pin 입력 복귀를 모두 확인한 경우에만 active를 해제합니다. */
    bool stopUart()
    {
        if (uart == nullptr)
        {
            return true;
        }
        if (uart->state() == SerialFabricState::inactive ||
            uart->state() == SerialFabricState::staged)
        {
            uart = nullptr;
            active = receiving = tx_pending = false;
            return true;
        }
        if (uart->deactivate() != SerialFabricResult::success)
        {
            return failure(20U);
        }
        const bool guards = tx.guards(frame_bytes) && rx.guards(frame_bytes);
        const auto tx_state = uart->bufferState(tx.data());
        const auto rx_state = uart->bufferState(rx.data());
        const bool returned =
            tx_state != DmaBufferState::queued && tx_state != DmaBufferState::dma_owned &&
            rx_state != DmaBufferState::queued && rx_state != DmaBufferState::dma_owned;
        uart = nullptr;
        active = receiving = tx_pending = false;
        nrf_gpio_cfg_input(38U, NRF_GPIO_PIN_NOPULL);
        nrf_gpio_cfg_input(39U, NRF_GPIO_PIN_NOPULL);
        return (guards && returned) || failure(21U);
    }

    bool stop()
    {
        wake_at = wake_end = off_after = 0U;
        stop_after_reply = false;
        const bool stopped = stopUart();
        const bool clock_released = stopped && releaseClock();
        nrf_gpio_cfg_input(wake_pin, NRF_GPIO_PIN_NOPULL);
        bool released = true;
        if (wake_token.active)
        {
            released = releaseIoResources(wake_token) == IoResourceResult::success;
        }
        retained.magic_word = 0U;
        const bool saved = save();
        stop_proven = saved && stopped && released && clock_released;
        stamp();
        return stop_proven;
    }

    bool armReceive()
    {
        if (receiving)
        {
            return true;
        }
        if (!active || uart == nullptr || !rx.initialize(frame_bytes))
        {
            return failure(11U);
        }
        const auto result = uart->receiveAsync(rx.data(), frame_bytes);
        if (result != SerialFabricResult::success)
        {
            /** @brief 재준비 거부 원인을 UART event 오류와 분리해 보존합니다. */
            return failure(100U + static_cast<std::uint32_t>(result));
        }
        receiving = true;
        return true;
    }

    /** @brief 초기 양쪽 TX idle 설정 뒤 별도 START로 RX를 활성화합니다. */
    bool begin()
    {
        if (active || t13::claimed() || t13::wiringClaimed())
        {
            return false;
        }
        const auto resource = gpioIoResource(wake_gpio);
        if (acquireIoResources({IoOwnerKind::application, 243U}, &resource, 1U,
                               IoAcquirePolicy::exclusive, wake_token) != IoResourceResult::success)
        {
            return failure(12U);
        }
        nrf_gpio_cfg_input(wake_pin, NRF_GPIO_PIN_NOPULL);
        stop_proven = false;
        if (!requestClock())
        {
            return false;
        }
        uart = serialFabric().uarte(21U);
        pins[0].pin = static_cast<pin_size_t>(t13::pinId(38U));
        pins[1].pin = static_cast<pin_size_t>(t13::pinId(39U));
        if (uart == nullptr || !tx.initialize(frame_bytes) || !rx.initialize(frame_bytes))
        {
            return failure(13U);
        }
        workspaces[0] = {tx.data(), frame_bytes};
        workspaces[1] = {rx.data(), frame_bytes};
        const SerialFabricConfiguration config{SerialRouteClass::p1_flexible,
                                               SerialElectricalProfile::dap_uart_disabled,
                                               pins,
                                               2U,
                                               workspaces,
                                               2U};
        if (uart->configure({115200U, UarteParity::none, false, false}) !=
                SerialFabricResult::success ||
            uart->stage(config) != SerialFabricResult::success ||
            uart->activate() != SerialFabricResult::success)
        {
            return failure(14U);
        }
        active = true;
        /**
         * @brief 상대 보드 reset·OFF 동안 해제되는 UART 선을 내부 pull-up으로 유휴 HIGH에 둡니다.
         * @note 소유한 RX만 변경하며 STOP에서는 기존 input/no-pull로 반환합니다.
         */
        const auto before_rx_cnf = NRF_P1->PIN_CNF[7U];
        const auto before_rx_level = nrf_gpio_pin_read(39U);
        nrf_gpio_cfg_input(39U, NRF_GPIO_PIN_PULLUP);
        const std::uint32_t idle[]{0U,
                                   role,
                                   static_cast<std::uint32_t>(k_uptime_get()),
                                   21U,
                                   38U,
                                   39U,
                                   NRF_P1->PIN_CNF[6U],
                                   before_rx_cnf,
                                   before_rx_level,
                                   NRF_P1->PIN_CNF[7U],
                                   nrf_gpio_pin_read(39U),
                                   nrf_gpio_pin_read(38U),
                                   NRF_UARTE21->ENABLE,
                                   NRF_UARTE21->CONFIG,
                                   NRF_UARTE21->BAUDRATE,
                                   NRF_CLOCK->XO.STAT,
                                   retained.boots,
                                   1U,
                                   0U,
                                   0U};
        for (unsigned index = 1U; index < 20U; ++index)
        {
            v04_power_idle[index] = idle[index];
        }
        __DMB();
        v04_power_idle[0] = 0x50494431U;
        deadline = k_uptime_get() + 10000U;
        return true;
    }

    bool send(const std::uint32_t *frame)
    {
        if (!active || tx_pending || error != 0U || !tx.initialize(frame_bytes))
        {
            return failure(15U);
        }
        ::memcpy(tx.data(), frame, frame_bytes);
        if (uart->transmitAsync(tx.data(), frame_bytes) != SerialFabricResult::success)
        {
            return failure(16U);
        }
        tx_pending = true;
        return true;
    }

    bool debugFree()
    {
        return NRF_TAD->SYSPWRUPREQ == 0U && NRF_TAD->DBGPWRUPREQ == 0U &&
               (CoreDebug->DHCSR & CoreDebug_DHCSR_C_DEBUGEN_Msk) == 0U;
    }

    /** @brief 응답 DMA 종료 후 UART 소유권과 HFXO 정지를 먼저 증명하고 System OFF에 들어갑니다. */
    void enterOff()
    {
        off_after = 0U;
        if (!debugFree() || !stopUart() || !releaseClock())
        {
            failure(30U);
            return;
        }
        const auto until = k_uptime_get() + 200U;
        while ((NRF_CLOCK->XO.STAT & CLOCK_XO_STAT_STATE_Msk) != 0U && k_uptime_get() < until)
        {
            k_sleep(K_MSEC(1));
        }
        if ((NRF_CLOCK->XO.STAT & CLOCK_XO_STAT_STATE_Msk) != 0U)
        {
            failure(31U);
            return;
        }
        retained.released = 1U;
        if (retained.mode == 2U)
        {
            /**
             * @brief nRF54L15의 System OFF GPIO 기상은 Zephyr의 검증된 level 감지 경로로
             *        GPIOTE PORT 감지까지 구성합니다.
             */
            if (gpio_pin_configure(wake_gpio.port, wake_gpio.pin, GPIO_INPUT | GPIO_PULL_UP) != 0 ||
                gpio_pin_interrupt_configure(wake_gpio.port, wake_gpio.pin, GPIO_INT_LEVEL_LOW) !=
                    0 ||
                gpio_pin_get(wake_gpio.port, wake_gpio.pin) != 1)
            {
                failure(32U);
                return;
            }
        }
        if (!save() || hwinfo_clear_reset_cause() != 0 ||
            (retained.mode == 1U && z_nrf_grtc_wakeup_prepare(2000000U) != 0))
        {
            failure(33U);
            return;
        }
        sys_poweroff();
        __builtin_unreachable();
    }
} // namespace

void t13::power::initialize(std::uint32_t &sequence, std::uint32_t *nonce)
{
    static_cast<void>(hwinfo_get_reset_cause(&reset_cause));
    if (role != 2U || !device_is_ready(retained_device) ||
        retained_mem_read(retained_device, 0U, reinterpret_cast<std::uint8_t *>(&retained),
                          sizeof(retained)) != 0 ||
        retained.magic_word != magic || retained.checksum != retainedChecksum() ||
        ::memcmp(retained.source, revision, 40U) != 0 || retained.boots >= 1000U ||
        retained.poll_mode > 1U)
    {
        retained = {};
        return;
    }
    const auto pending = retained.pending;
    const bool expected =
        pending == 1U
            ? reset_cause == RESET_PIN
            : pending == 2U && retained.released == 1U &&
                  reset_cause == (retained.mode == 1U ? RESET_CLOCK : RESET_LOW_POWER_WAKE);
    if (!expected)
    {
        retained.magic_word = 0U;
        static_cast<void>(save());
        failure(34U);
        return;
    }
    sequence = retained.sequence;
    ::memcpy(nonce, retained.nonce, sizeof(retained.nonce));
    retained.pending = 0U;
    ++retained.boots;
    retained_valid = 1U;
    if (!save() || !begin() || !armReceive())
    {
        failure(35U);
    }
}

bool t13::power::claimed()
{
    return active || wake_token.active || clock_held;
}

/** @brief 단일 중계 진단에서만 main의 1ms 대기를 10us polling으로 비교합니다. */
bool t13::power::fastPolling()
{
    return claimed() && retained.poll_mode == 1U;
}

void t13::power::remember(std::uint32_t sequence, const std::uint32_t *nonce)
{
    if (role == 2U && retained.magic_word == magic)
    {
        retained.sequence = sequence;
        ::memcpy(retained.nonce, nonce, sizeof(retained.nonce));
        if (!save())
        {
            failure(36U);
        }
    }
}

void t13::power::service()
{
    stamp();
    const auto now = static_cast<std::uint64_t>(k_uptime_get());
    if (claimed() && now >= deadline)
    {
        failure(40U);
        static_cast<void>(stop());
        return;
    }
    if (role == 1U && wake_at != 0U && now >= wake_at)
    {
        wake_at = 0U;
        nrf_gpio_pin_set(wake_pin);
        nrf_gpio_cfg(wake_pin, NRF_GPIO_PIN_DIR_OUTPUT, NRF_GPIO_PIN_INPUT_CONNECT,
                     NRF_GPIO_PIN_NOPULL, NRF_GPIO_PIN_S0D1, NRF_GPIO_PIN_NOSENSE);
        nrf_gpio_pin_clear(wake_pin);
        wake_end = now + 100U;
    }
    if (wake_end != 0U && now >= wake_end)
    {
        nrf_gpio_cfg_input(wake_pin, NRF_GPIO_PIN_NOPULL);
        wake_end = 0U;
    }
    if (uart != nullptr && active)
    {
        UarteEvent event{};
        while (uart->takeEvent(event))
        {
            if (event.type == UarteEventType::tx_complete && tx_pending &&
                event.buffer == tx.data() && event.transferred == frame_bytes &&
                event.error_mask == 0U && tx.guards(frame_bytes))
            {
                tx_pending = false;
                ++tx_count;
            }
            else if (event.type == UarteEventType::rx_complete && receiving && !ready &&
                     event.buffer == rx.data() && event.transferred == frame_bytes &&
                     event.error_mask == 0U && rx.guards(frame_bytes))
            {
                receiving = false;
                ::memcpy(received, rx.data(), frame_bytes);
                ready = true;
                ++rx_count;
            }
            else if (event.type != UarteEventType::rx_buffer_needed)
            {
                captureFault(event);
                failure(41U + static_cast<std::uint32_t>(event.type));
            }
        }
    }
    if (error != 0U && claimed())
    {
        static_cast<void>(stop());
        return;
    }
    if (stop_after_reply && !tx_pending)
    {
        static_cast<void>(stop());
    }
    else if (off_after != 0U && !tx_pending && now >= off_after)
    {
        enterOff();
    }
}

bool t13::power::takeRequest(std::uint32_t *request)
{
    if (role != 2U || !ready || tx_pending)
    {
        return false;
    }
    ::memcpy(request, received, frame_bytes);
    ready = false;
    return true;
}

bool t13::power::respond(const std::uint32_t *response)
{
    /**
     * @brief 고정 115200 중계에서 RX 완료 뒤 2ms를 두고 수신 준비 후 응답합니다.
     * @note RX_DONE과 RX_DISABLED는 다른 시점입니다. 이 간격은 시험 프로토콜의
     *       turnaround이며 재준비 실패를 재시도하거나 정상 UART 오류를 숨기지 않습니다.
     */
    k_sleep(K_MSEC(2));
    if (off_after == 0U && !stop_after_reply && !armReceive())
    {
        return false;
    }
    return send(response);
}

std::uint32_t t13::power::command(std::uint32_t opcode, const std::uint32_t *args,
                                  std::uint32_t nargs, std::uint32_t *out, std::uint32_t &count,
                                  bool from_peer)
{
    count = 1U;
    out[0] = 0U;
    if (opcode == 130U && (nargs == 1U || (nargs == 2U && args[1] == 1U)) && args[0] == magic &&
        !claimed() && error == 0U)
    {
        retained = {};
        retained.magic_word = magic;
        retained.poll_mode = nargs == 2U ? 1U : 0U;
        ::memcpy(retained.source, revision, 40U);
        out[0] = begin() ? 1U : 0U;
        return 0U;
    }
    if (opcode == 134U && nargs == 1U && args[0] == 2U)
    {
        /** @brief polling 진단 정책을 읽기만 하며 lease나 실제 OFF 판정은 변경하지 않습니다. */
        const std::uint32_t values[]{0x50504F31U, role, retained.poll_mode, fastPolling() ? 1U : 0U,
                                     error};
        ::memcpy(out, values, sizeof(values));
        count = 5U;
        return 0U;
    }
    if (opcode == 134U && nargs == 0U)
    {
        const std::uint32_t values[]{magic,
                                     role,
                                     active,
                                     receiving,
                                     error,
                                     retained.boots,
                                     reset_cause,
                                     retained.pending,
                                     retained.mode,
                                     retained.round,
                                     NRF_TAD->SYSPWRUPREQ,
                                     NRF_TAD->DBGPWRUPREQ,
                                     CoreDebug->DHCSR & CoreDebug_DHCSR_C_DEBUGEN_Msk,
                                     NRF_CLOCK->XO.STAT,
                                     tx_count,
                                     rx_count,
                                     retained.released,
                                     retained_valid,
                                     retained.seed,
                                     static_cast<std::uint32_t>(k_uptime_get())};
        ::memcpy(out, values, sizeof(values));
        count = 20U;
        deadline = k_uptime_get() + 10000U;
        return 0U;
    }
    if (opcode == 134U && nargs == 1U && args[0] == 1U)
    {
        /** @brief reset 전후 소유 GPIO와 UART를 읽기만 하며 lease를 갱신하지 않습니다. */
        const std::uint32_t values[]{0x50504931U,
                                     role,
                                     static_cast<std::uint32_t>(k_uptime_get()),
                                     NRF_P1->OUT,
                                     NRF_P1->IN,
                                     NRF_P1->PIN_CNF[6U],
                                     NRF_P1->PIN_CNF[7U],
                                     NRF_UARTE21->ENABLE,
                                     nrf_uarte_tx_pin_get(NRF_UARTE21),
                                     nrf_uarte_rx_pin_get(NRF_UARTE21),
                                     NRF_CLOCK->XO.STAT,
                                     active,
                                     receiving,
                                     tx_pending,
                                     error,
                                     tx_count,
                                     rx_count,
                                     retained.boots,
                                     NRF_TAD->SYSPWRUPREQ,
                                     NRF_TAD->DBGPWRUPREQ};
        ::memcpy(out, values, sizeof(values));
        count = 20U;
        return 0U;
    }
    if (opcode == 139U && nargs == 0U)
    {
        if (from_peer && active)
        {
            stop_after_reply = true;
            out[0] = 1U;
        }
        else
        {
            out[0] = stop() ? 1U : 0U;
        }
        return 0U;
    }
    if (!active || error != 0U)
    {
        return 403U;
    }
    deadline = k_uptime_get() + 10000U;
    if (opcode == 131U && nargs == 0U && !from_peer)
    {
        out[0] = armReceive() ? 1U : 0U;
        return 0U;
    }
    if (role == 2U && opcode == 131U && nargs == 0U && from_peer)
    {
        ::memcpy(out, revision, 40U);
        out[10] = magic;
        count = 11U;
        return 0U;
    }
    if (role == 1U && opcode == 132U && nargs == 17U && args[0] <= 1U && !tx_pending)
    {
        if (args[0] == 0U)
        {
            pages = 0U;
        }
        ::memcpy(staged + args[0] * 16U, args + 1U, 64U);
        pages |= 1U << args[0];
        out[0] = 1U;
        return 0U;
    }
    if (role == 1U && opcode == 133U && nargs == 0U && pages == 3U && v04::valid(staged, 2U) &&
        !tx_pending)
    {
        ready = false;
        pages = 0U;
        out[0] = armReceive() && send(staged) ? 1U : 0U;
        return 0U;
    }
    if (role == 1U && opcode == 135U && nargs == 1U && args[0] <= 1U)
    {
        if (!ready)
        {
            count = 0U;
            return 0U;
        }
        ::memcpy(out, received + args[0] * 16U, 64U);
        count = 16U;
        return 0U;
    }
    if (role == 2U && opcode == 136U && nargs == 3U && from_peer &&
        (args[0] == 1U || args[0] == 2U) && args[1] >= 1U && args[1] <= 100U &&
        retained_valid == 1U && debugFree() && retained.pending == 0U && retained.poll_mode == 0U)
    {
        retained.pending = 2U;
        retained.mode = args[0];
        retained.round = args[1];
        retained.seed = args[2];
        retained.released = 0U;
        off_after = k_uptime_get() + 100U;
        out[0] = 1U;
        return 0U;
    }
    if (role == 2U && opcode == 137U && nargs == 0U && !from_peer && retained.pending == 0U &&
        retained.boots == 0U)
    {
        if (hwinfo_clear_reset_cause() != 0)
        {
            return 500U;
        }
        retained.pending = 1U;
        out[0] = 1U;
        return 0U;
    }
    if (role == 2U && opcode == 137U && nargs == 20U && from_peer)
    {
        for (unsigned index = 0U; index < 20U; ++index)
        {
            out[index] = args[index] ^ retained.seed ^ (0x9E3779B9U * (index + 1U));
        }
        count = 20U;
        return 0U;
    }
    if (role == 1U && opcode == 138U && nargs == 1U && args[0] == 2000U && wake_at == 0U &&
        wake_end == 0U)
    {
        wake_at = k_uptime_get() + 2000U;
        out[0] = 1U;
        return 0U;
    }
    return 400U;
}
