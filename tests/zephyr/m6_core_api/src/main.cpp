/**
 * @file main.cpp
 * @brief M6 공통 API, Serial과 GPIO interrupt 계약을 자동 검증합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <Arduino.h>

#include <zephyr/device.h>
#include <zephyr/drivers/gpio/gpio_emul.h>
#include <zephyr/drivers/uart.h>
#include <zephyr/drivers/serial/uart_emul.h>
#include <zephyr/irq_offload.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/atomic.h>
#include <zephyr/ztest.h>

#include <stdint.h>
#include <string.h>

#include "internal/SerialBackend.h"
#include "internal/pin_description.h"

extern "C" int nucode_m6_c_header_contract(void);

namespace
{
    using nucode::arduino::internal::clearSerialDiagnostics;
    using nucode::arduino::internal::GpioError;
    using nucode::arduino::internal::lastGpioError;
    using nucode::arduino::internal::lastSerialError;
    using nucode::arduino::internal::serialDroppedRxBytes;
    using nucode::arduino::internal::SerialError;

    template <typename Left, typename Right> inline constexpr bool same_type = false;

    template <typename Value> inline constexpr bool same_type<Value, Value> = true;

    static_assert(same_type<String, arduino::String>);
    static_assert(same_type<Print, arduino::Print>);
    static_assert(same_type<Stream, arduino::Stream>);
    static_assert(same_type<HardwareSerial, arduino::HardwareSerial>);

    /** @brief M6 GPIO emulator 장치입니다. */
    const struct device *const test_gpio = DEVICE_DT_GET(DT_NODELABEL(m6_gpio));

    /** @brief M6 Serial 전용 UART emulator 장치입니다. */
    const struct device *const test_uart = DEVICE_DT_GET(DT_NODELABEL(m6_uart));

    /** @brief Print 출력을 고정 배열에 수집합니다. */
    class CapturePrint final : public Print
    {
      public:
        using Print::write;

        /** @brief 한 byte를 수집합니다. */
        size_t write(uint8_t value) override
        {
            if (length_ >= (sizeof(data_) - 1U))
            {
                setWriteError();
                return 0U;
            }
            data_[length_++] = static_cast<char>(value);
            data_[length_] = '\0';
            return 1U;
        }

        /** @brief 수집한 C 문자열을 반환합니다. */
        const char *data() const noexcept
        {
            return data_;
        }

      private:
        char data_[256] = {};
        size_t length_ = 0U;
    };

    /** @brief 지정한 byte 수 뒤 실패하는 Print 구현입니다. */
    class PartialPrint final : public Print
    {
      public:
        using Print::write;

        /** @brief 성공시킬 최대 byte 수를 지정합니다. */
        explicit PartialPrint(size_t limit) : limit_(limit)
        {
        }

        /** @brief 한 byte를 한도 안에서만 수락합니다. */
        size_t write(uint8_t value) override
        {
            ARG_UNUSED(value);
            if (written_ >= limit_)
            {
                setWriteError();
                return 0U;
            }

            ++written_;
            return 1U;
        }

      private:
        size_t limit_;
        size_t written_ = 0U;
    };

    /** @brief Printable 객체가 Print에 위임하는 byte 수와 호출 횟수를 기록합니다. */
    class PrintableToken final : public Printable
    {
      public:
        /** @brief 고정 문자열과 숫자를 전달받은 Print 구현에 기록합니다. */
        size_t printTo(Print &output) const override
        {
            ++invocation_count_;
            size_t written = output.print("NU54:");
            written += output.print(42U, HEX);
            return written;
        }

        /** @brief printTo가 호출된 누적 횟수를 반환합니다. */
        unsigned int invocationCount() const noexcept
        {
            return invocation_count_;
        }

      private:
        mutable unsigned int invocation_count_ = 0U;
    };

    /** @brief Stream 입력과 출력을 고정 배열로 모사합니다. */
    class MemoryStream final : public Stream
    {
      public:
        using Print::write;

        /** @brief 시험 입력 문자열을 선택합니다. */
        explicit MemoryStream(const char *input) : input_(input), length_(strlen(input))
        {
        }

        /** @brief 남은 입력 byte 수를 반환합니다. */
        int available() override
        {
            return static_cast<int>(length_ - cursor_);
        }

        /** @brief 다음 byte를 소비합니다. */
        int read() override
        {
            return (cursor_ < length_) ? static_cast<unsigned char>(input_[cursor_++]) : -1;
        }

        /** @brief 다음 byte를 소비하지 않고 반환합니다. */
        int peek() override
        {
            return (cursor_ < length_) ? static_cast<unsigned char>(input_[cursor_]) : -1;
        }

        /** @brief 시험 Stream에는 비동기 출력이 없으므로 아무 작업도 하지 않습니다. */
        void flush() override
        {
        }

        /** @brief 한 출력 byte를 버리고 성공을 반환합니다. */
        size_t write(uint8_t value) override
        {
            ARG_UNUSED(value);
            return 1U;
        }

      private:
        const char *input_;
        size_t length_;
        size_t cursor_ = 0U;
    };

    atomic_t simple_interrupt_count;
    atomic_t parameter_interrupt_count;
    atomic_t sentinel_uart_irq_count;
    volatile size_t isr_serial_write_result;

    /** @brief 단순 GPIO callback 실행 횟수를 증가시킵니다. */
    void simpleInterruptCallback()
    {
        atomic_inc(&simple_interrupt_count);
    }

    /** @brief 매개변수 GPIO callback 실행 횟수를 증가시킵니다. */
    void parameterInterruptCallback(void *parameter)
    {
        auto *counter = static_cast<atomic_t *>(parameter);
        atomic_inc(counter);
    }

    /** @brief 미시작 end() 보존 시험용 UART callback입니다. */
    void sentinelUartCallback(const struct device *device, void *user_data)
    {
        ARG_UNUSED(user_data);
        static_cast<void>(uart_irq_update(device));
        if (uart_irq_rx_ready(device) != 0)
        {
            uint8_t value = 0U;
            static_cast<void>(uart_fifo_read(device, &value, 1));
            atomic_inc(&sentinel_uart_irq_count);
        }
    }

    /** @brief IRQ 문맥에서 금지된 Serial write를 호출합니다. */
    void serialWriteFromIsr(const void *parameter)
    {
        ARG_UNUSED(parameter);
        isr_serial_write_result = Serial.write(static_cast<uint8_t>('X'));
    }

    /** @brief UART emulator RX가 Serial queue로 이동할 때까지 기다립니다. */
    bool waitForSerialBytes(int expected)
    {
        for (int attempt = 0; attempt < 100; ++attempt)
        {
            if (Serial.available() >= expected)
            {
                return true;
            }
            k_sleep(K_MSEC(1));
        }
        return false;
    }

    /** @brief 각 Serial 시험 전에 backend와 UART emulator를 초기화합니다. */
    void serialBefore(void *)
    {
        Serial.end();
        clearSerialDiagnostics();
        uart_emul_flush_rx_data(test_uart);
        uart_emul_flush_tx_data(test_uart);

        /**
		 * 실제 production Serial은 Zephyr 소유 UART를 재구성하지 않습니다.
		 * DTS 속성을 runtime 설정에 반영하지 않는 시험용 UART emulator에만
		 * Zephyr가 이미 적용한 것으로 간주할 115200 8N1 상태를 준비합니다.
		 */
        const struct uart_config config = {
            .baudrate = 115200U,
            .parity = UART_CFG_PARITY_NONE,
            .stop_bits = UART_CFG_STOP_BITS_1,
            .data_bits = UART_CFG_DATA_BITS_8,
            .flow_ctrl = UART_CFG_FLOW_CTRL_NONE,
        };
        zassert_ok(uart_configure(test_uart, &config),
                   "UART emulator의 Zephyr 소유 설정 적용에 실패했습니다.");
    }

} // namespace

ZTEST(m6_common, test_c_and_cpp_common_contract)
{
    zassert_equal(nucode_m6_c_header_contract(), 1, "Arduino.h C 계약이 깨졌습니다.");
    zassert_equal(map(25L, 0L, 100L, -100L, 100L), -50L, "map 결과가 다릅니다.");
    zassert_equal(makeWord(0x12U, 0x34U), 0x1234U, "makeWord 결과가 다릅니다.");

    pin_size_t pin = 0U;
    zassert_equal(digitalPinToInterrupt(pin++), 0U, "유효한 interrupt 매핑이 다릅니다.");
    zassert_equal(pin, 1U, "C++ interrupt 매핑이 인수를 두 번 평가했습니다.");
    zassert_equal(digitalPinToInterrupt(NUM_DIGITAL_PINS), NOT_AN_INTERRUPT,
                  "범위 밖 interrupt가 거부되지 않았습니다.");
}

ZTEST(m6_common, test_string_construction_and_conversion)
{
    String value("NU54");
    value += "DK";
    zassert_equal(strcmp(value.c_str(), "NU54DK"), 0, "String 연결 결과가 다릅니다.");

    String hexadecimal(255, HEX);
    zassert_equal(strcmp(hexadecimal.c_str(), "ff"), 0, "String 16진 변환이 다릅니다.");

    String floating(3.25, 2U);
    zassert_equal(strcmp(floating.c_str(), "3.25"), 0, "String 실수 변환이 다릅니다.");

    String bounded("stable");
    zassert_true(bounded.reserve(1024U), "String의 정상 heap 예약에 실패했습니다.");
    zassert_false(bounded.reserve(16384U), "String이 구성한 heap 경계를 넘어 예약했습니다.");
    zassert_equal(strcmp(bounded.c_str(), "stable"), 0,
                  "실패한 String 예약이 기존 내용을 손상했습니다.");
}

ZTEST(m6_common, test_print_and_stream_contract)
{
    CapturePrint output;
    zassert_equal(output.write("value="), 6U, "Print 문자열 write가 숨겨졌습니다.");
    output.println(255, HEX);
    zassert_equal(strcmp(output.data(), "value=FF\r\n"), 0, "Print 형식 출력이 다릅니다.");

    PartialPrint partial(3U);
    const uint8_t partial_input[] = {'A', 'B', 'C', 'D', 'E'};
    zassert_equal(partial.write(partial_input, sizeof(partial_input)), 3U,
                  "Print가 부분 write 지점에서 멈추지 않았습니다.");
    zassert_not_equal(partial.getWriteError(), 0, "Print 부분 write 오류가 기록되지 않았습니다.");

    MemoryStream stream("noise:-123,45.5!");
    stream.setTimeout(2U);
    zassert_equal(stream.parseInt(), -123L, "Stream 정수 parsing이 다릅니다.");
    zassert_within(stream.parseFloat(), 45.5F, 0.01F, "Stream 실수 parsing이 다릅니다.");

    MemoryStream searchable("prefix-token");
    searchable.setTimeout(2U);
    zassert_true(searchable.find("token"), "Stream find가 token을 찾지 못했습니다.");

    MemoryStream empty("");
    empty.setTimeout(2U);
    const unsigned long timeout_start = millis();
    zassert_false(empty.find("never"), "빈 Stream이 존재하지 않는 token을 찾았습니다.");
    const unsigned long timeout_elapsed = millis() - timeout_start;
    zassert_true(timeout_elapsed >= 2U, "Stream timeout이 요청한 시간보다 일찍 끝났습니다.");
    zassert_true(timeout_elapsed < 100U, "Stream timeout이 비정상적으로 오래 걸렸습니다.");
}

ZTEST(m6_common, test_printable_dispatch_and_count_contract)
{
    PrintableToken token;
    CapturePrint printed;
    zassert_equal(printed.print(token), 7U,
                  "Print::print가 Printable의 기록 byte 수를 반환하지 않았습니다.");
    zassert_equal(strcmp(printed.data(), "NU54:2A"), 0,
                  "Printable이 Print 구현에 기대한 내용을 기록하지 않았습니다.");
    zassert_equal(token.invocationCount(), 1U,
                  "Print::print가 Printable::printTo를 한 번만 호출하지 않았습니다.");

    CapturePrint line;
    zassert_equal(line.println(token), 9U,
                  "Print::println이 Printable 출력과 CRLF byte 수를 합산하지 않았습니다.");
    zassert_equal(strcmp(line.data(), "NU54:2A\r\n"), 0,
                  "Print::println이 Printable 출력 뒤 CRLF를 추가하지 않았습니다.");
    zassert_equal(token.invocationCount(), 2U,
                  "Print::println의 Printable dispatch 횟수가 다릅니다.");
}

ZTEST(m6_serial, test_begin_tx_and_non_destructive_rebegin)
{
    Serial.begin(9600U);
    zassert_equal(lastSerialError(), SerialError::unsupported_config,
                  "DTS와 다른 속도가 거부되지 않았습니다.");
    zassert_false(static_cast<bool>(Serial), "잘못된 begin 뒤 Serial이 시작되었습니다.");

    Serial.begin(115200U, SERIAL_8N1);
    zassert_true(static_cast<bool>(Serial), "유효한 Serial begin에 실패했습니다.");
    zassert_equal(Serial.write("M6"), 2U, "Serial.write 문자열 overload가 동작하지 않습니다.");
    Serial.println(" OK");

    uint8_t transmitted[16] = {};
    const size_t transmitted_size =
        uart_emul_get_tx_data(test_uart, transmitted, sizeof(transmitted));
    zassert_equal(transmitted_size, 7U, "Serial TX 길이가 다릅니다.");
    zassert_mem_equal(transmitted, "M6 OK\r\n", 7U, "Serial TX 내용이 다릅니다.");

    Serial.begin(9600U);
    zassert_equal(lastSerialError(), SerialError::unsupported_config,
                  "재-begin 오류가 기록되지 않았습니다.");
    zassert_true(static_cast<bool>(Serial), "잘못된 재-begin이 기존 세션을 중단했습니다.");
    zassert_equal(Serial.write(static_cast<uint8_t>('!')), 1U,
                  "재-begin 오류 뒤 기존 TX 세션이 유지되지 않았습니다.");
}

ZTEST(m6_serial, test_rx_peek_read_and_overflow)
{
    Serial.begin(115200U);
    const uint8_t received[] = {'A', 'B', 'C'};
    zassert_equal(uart_emul_put_rx_data(test_uart, received, sizeof(received)), sizeof(received),
                  "UART RX 주입에 실패했습니다.");
    zassert_true(waitForSerialBytes(3), "Serial RX queue가 채워지지 않았습니다.");
    zassert_equal(Serial.peek(), 'A', "Serial.peek 결과가 다릅니다.");
    zassert_equal(Serial.read(), 'A', "Serial.read 첫 byte가 다릅니다.");
    zassert_equal(Serial.read(), 'B', "Serial.read 두 번째 byte가 다릅니다.");
    zassert_equal(Serial.read(), 'C', "Serial.read 세 번째 byte가 다릅니다.");

    uint8_t overflow_data[160] = {};
    for (size_t index = 0U; index < sizeof(overflow_data); ++index)
    {
        overflow_data[index] = static_cast<uint8_t>(index);
    }
    zassert_equal(uart_emul_put_rx_data(test_uart, overflow_data, sizeof(overflow_data)),
                  sizeof(overflow_data), "overflow RX 주입에 실패했습니다.");
    zassert_true(waitForSerialBytes(128), "고정 Serial RX queue가 채워지지 않았습니다.");
    zassert_equal(Serial.available(), 128, "Serial RX queue 경계가 다릅니다.");
    zassert_equal(serialDroppedRxBytes(), 32U, "overflow drop 누적값이 다릅니다.");
    zassert_equal(Serial.read(), 0, "drop-newest 정책이 유지되지 않았습니다.");
}

ZTEST(m6_serial, test_started_end_stops_session_and_purges_rx)
{
    Serial.begin(115200U);
    const uint8_t received[] = {'E', 'N', 'D'};
    zassert_equal(uart_emul_put_rx_data(test_uart, received, sizeof(received)), sizeof(received),
                  "end 시험용 UART RX 주입에 실패했습니다.");
    zassert_true(waitForSerialBytes(3), "end 시험 전에 Serial RX queue가 채워지지 않았습니다.");

    Serial.end();
    zassert_false(static_cast<bool>(Serial), "end 뒤 Serial 세션이 계속 활성 상태입니다.");
    zassert_equal(Serial.available(), 0, "end 뒤 RX queue가 비워지지 않았습니다.");
    zassert_equal(lastSerialError(), SerialError::not_started,
                  "end 뒤 접근이 미시작 상태로 진단되지 않았습니다.");
}

ZTEST(m6_serial, test_end_without_session_preserves_existing_callback)
{
    atomic_clear(&sentinel_uart_irq_count);
    zassert_ok(uart_irq_callback_user_data_set(test_uart, sentinelUartCallback, nullptr),
               "시험 UART callback 등록에 실패했습니다.");
    uart_irq_rx_enable(test_uart);

    Serial.end();
    const uint8_t received = 'S';
    zassert_equal(uart_emul_put_rx_data(test_uart, &received, 1U), 1U,
                  "sentinel RX 주입에 실패했습니다.");
    for (int attempt = 0; (attempt < 100) && (atomic_get(&sentinel_uart_irq_count) == 0); ++attempt)
    {
        k_sleep(K_MSEC(1));
    }
    zassert_true(atomic_get(&sentinel_uart_irq_count) >= 1,
                 "미시작 end가 기존 UART callback을 제거했습니다.");

    uart_irq_rx_disable(test_uart);
    zassert_ok(uart_irq_callback_user_data_set(test_uart, nullptr, nullptr),
               "시험 UART callback 해제에 실패했습니다.");
}

ZTEST(m6_serial, test_isr_restriction)
{
    Serial.begin(115200U);
    isr_serial_write_result = 1U;
    irq_offload(serialWriteFromIsr, nullptr);
    zassert_equal(isr_serial_write_result, 0U, "ISR Serial.write가 거부되지 않았습니다.");
    zassert_equal(lastSerialError(), SerialError::invalid_context,
                  "ISR 문맥 오류가 기록되지 않았습니다.");
}

ZTEST(m6_interrupt, test_raw_edges_parameter_and_detach)
{
    atomic_clear(&simple_interrupt_count);
    atomic_clear(&parameter_interrupt_count);
    pinMode(PIN_BUTTON0, INPUT_PULLUP);
    zassert_ok(gpio_emul_input_set(test_gpio, 1U, 1), "button 초기 입력 설정에 실패했습니다.");

    attachInterrupt(digitalPinToInterrupt(PIN_BUTTON0), simpleInterruptCallback, FALLING);
    zassert_equal(lastGpioError(), GpioError::none, "FALLING callback 등록에 실패했습니다.");
    zassert_ok(gpio_emul_input_set(test_gpio, 1U, 0), "FALLING 입력 주입에 실패했습니다.");
    zassert_equal(atomic_get(&simple_interrupt_count), 1, "raw FALLING callback 횟수가 다릅니다.");
    zassert_ok(gpio_emul_input_set(test_gpio, 1U, 1), "RISING 입력 복구에 실패했습니다.");
    zassert_equal(atomic_get(&simple_interrupt_count), 1, "FALLING이 RISING에도 실행되었습니다.");

    attachInterrupt(digitalPinToInterrupt(PIN_BUTTON0), simpleInterruptCallback, RISING);
    zassert_ok(gpio_emul_input_set(test_gpio, 1U, 0), "RISING 시험용 LOW 설정에 실패했습니다.");
    zassert_equal(atomic_get(&simple_interrupt_count), 1, "RISING이 FALLING에도 실행되었습니다.");
    zassert_ok(gpio_emul_input_set(test_gpio, 1U, 1), "RISING 입력 주입에 실패했습니다.");
    zassert_equal(atomic_get(&simple_interrupt_count), 2, "raw RISING callback 횟수가 다릅니다.");

    attachInterruptParam(digitalPinToInterrupt(PIN_BUTTON0), parameterInterruptCallback, CHANGE,
                         &parameter_interrupt_count);
    zassert_ok(gpio_emul_input_set(test_gpio, 1U, 0), "CHANGE 하강 입력에 실패했습니다.");
    zassert_ok(gpio_emul_input_set(test_gpio, 1U, 1), "CHANGE 상승 입력에 실패했습니다.");
    zassert_equal(atomic_get(&parameter_interrupt_count), 2,
                  "매개변수 CHANGE callback 횟수가 다릅니다.");

    detachInterrupt(digitalPinToInterrupt(PIN_BUTTON0));
    zassert_ok(gpio_emul_input_set(test_gpio, 1U, 0), "detach 후 입력 주입에 실패했습니다.");
    zassert_equal(atomic_get(&parameter_interrupt_count), 2,
                  "detach 후 callback이 실행되었습니다.");
}

ZTEST(m6_interrupt, test_validation_and_pinmode_auto_detach)
{
    attachInterrupt(NOT_AN_INTERRUPT, simpleInterruptCallback, RISING);
    zassert_equal(lastGpioError(), GpioError::invalid_pin,
                  "범위 밖 interrupt 번호가 거부되지 않았습니다.");
    detachInterrupt(NOT_AN_INTERRUPT);
    zassert_equal(lastGpioError(), GpioError::invalid_pin,
                  "범위 밖 detach 번호가 거부되지 않았습니다.");

    attachInterrupt(digitalPinToInterrupt(LED_BUILTIN), simpleInterruptCallback, RISING);
    zassert_equal(lastGpioError(), GpioError::interrupt_not_configured,
                  "미설정 input interrupt가 거부되지 않았습니다.");

    pinMode(LED_BUILTIN, INPUT_PULLUP);
    attachInterrupt(digitalPinToInterrupt(LED_BUILTIN), nullptr, RISING);
    zassert_equal(lastGpioError(), GpioError::null_callback,
                  "null callback이 거부되지 않았습니다.");
    attachInterrupt(digitalPinToInterrupt(LED_BUILTIN), simpleInterruptCallback, HIGH);
    zassert_equal(lastGpioError(), GpioError::invalid_interrupt_mode,
                  "미지원 interrupt mode가 거부되지 않았습니다.");

    atomic_clear(&simple_interrupt_count);
    zassert_ok(gpio_emul_input_set(test_gpio, 0U, 0), "초기 LOW 설정에 실패했습니다.");
    attachInterrupt(digitalPinToInterrupt(LED_BUILTIN), simpleInterruptCallback, RISING);
    pinMode(LED_BUILTIN, INPUT_PULLUP);
    zassert_ok(gpio_emul_input_set(test_gpio, 0U, 1), "pinMode 후 RISING 입력에 실패했습니다.");
    zassert_equal(atomic_get(&simple_interrupt_count), 0,
                  "pinMode 변경 뒤 이전 callback이 남았습니다.");
}

ZTEST_SUITE(m6_common, nullptr, nullptr, nullptr, nullptr, nullptr);
ZTEST_SUITE(m6_serial, nullptr, nullptr, serialBefore, nullptr, nullptr);
ZTEST_SUITE(m6_interrupt, nullptr, nullptr, nullptr, nullptr, nullptr);
