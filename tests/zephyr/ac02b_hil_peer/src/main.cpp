/**
 * @file main.cpp
 * @brief AC-02B DUT와 물리 연결되는 direct Zephyr peer를 구현합니다.
 *
 * @details Arduino Wire target이 지원되지 않으므로 serial21을 TWIS target으로
 * 전환합니다. PWM capture와 ADC drive 명령은 host console에서만 받습니다.
 * uart30은 devicetree에서 비활성화하여 기존 P0 교차선이 남아 있어도 peer가
 * P0.0/P0.1을 구동하지 않습니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <zephyr/device.h>
#include <zephyr/devicetree.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/drivers/i2c.h>
#include <zephyr/drivers/uart.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/atomic.h>
#include <zephyr/sys/printk.h>
#include <zephyr/sys/time_units.h>

#include <errno.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include <cstddef>
#include <cstdint>

namespace
{
	/** @brief host nonce의 고정 ASCII 길이입니다. */
	constexpr std::size_t nonce_length = 32U;

	/** @brief bounded UART line 크기입니다. */
	constexpr std::size_t line_capacity = 160U;

	/** @brief PMIC 0x6A와 겹치지 않는 AC-02B target 주소입니다. */
	constexpr std::uint16_t i2c_target_address = 0x52U;

	/** @brief DUT P1.10 PWM이 연결되는 peer input입니다. */
	constexpr gpio_pin_t pwm_capture_pin = 14U;

	/** @brief DUT P1.12 ADC를 구동하는 peer output입니다. */
	constexpr gpio_pin_t adc_drive_pin = 5U;

	/** @brief host relay가 따라야 하는 고정 명령 순서입니다. */
	constexpr const char *relay_commands[]{
		"PWM:ARM:25", "PWM:CHECK:25", "PWM:ARM:75", "PWM:CHECK:75",
		"ADC:LOW", "ADC:HIGH", "ADC:LOW", "DONE"};

	/** @brief 각 relay 명령의 exact 응답입니다. */
	constexpr const char *relay_responses[]{
		"PWM:ARM:25:OK", "PWM:25:PASS", "PWM:ARM:75:OK", "PWM:75:PASS",
		"ADC:LOW:OK", "ADC:HIGH:OK", "ADC:LOW:OK", "DONE:PASS"};

	/** @brief peer P0 UART가 build에서 활성화되지 않았음을 보장합니다. */
	static_assert(!DT_NODE_HAS_STATUS(DT_NODELABEL(uart30), okay),
				  "AC-02B peer uart30은 반드시 disabled여야 합니다.");

	/** @brief DAPLink host console UART입니다. */
	const struct device *const console_uart = DEVICE_DT_GET(DT_CHOSEN(zephyr_console));

	/** @brief P1.2/P1.3을 사용하는 direct TWIS21 target입니다. */
	const struct device *const target_i2c = DEVICE_DT_GET(DT_NODELABEL(i2c21));

	/** @brief PWM capture port입니다. */
	const struct device *const capture_gpio = DEVICE_DT_GET(DT_NODELABEL(gpio1));

	/** @brief ADC drive port입니다. */
	const struct device *const drive_gpio = DEVICE_DT_GET(DT_NODELABEL(gpio2));

	/** @brief 현재 run과 결합한 nonce입니다. */
	char active_nonce[nonce_length + 1U]{};

	/** @brief DAPLink host RX byte를 보존하는 고정 queue입니다. */
	K_MSGQ_DEFINE(console_rx_queue, sizeof(std::uint8_t), 256U,
			  alignof(std::uint8_t));

	/** @brief IRQ UART 한 채널의 queue와 overflow 상태입니다. */
	struct UartRxContext
	{
		struct k_msgq *queue;
		atomic_t overflow;
	};

	/** @brief DAPLink console RX 상태입니다. */
	UartRxContext console_rx_context{&console_rx_queue, ATOMIC_INIT(0)};

	/** @brief nonce에서 파생한 I2C expected write입니다. */
	std::uint8_t expected_i2c_payload[16]{};

	/** @brief TWIS read request에 제공할 변환 응답입니다. */
	std::uint8_t i2c_response_payload[16]{};

	/** @brief 유효한 repeated-start write 횟수입니다. */
	atomic_t i2c_valid_write_count = ATOMIC_INIT(0);

	/** @brief I2C 길이·payload 불일치를 보존하는 fail-closed 표식입니다. */
	atomic_t i2c_invalid = ATOMIC_INIT(0);

	/** @brief host relay에서 다음에 받아야 하는 명령 index입니다. */
	std::size_t relay_step = 0U;

	/** @brief peer protocol 단계 관찰값입니다. */
	unsigned int pwm_pass_count = 0U;
	bool adc_low_seen = false;
	bool adc_high_seen = false;
	bool wire_reported = false;
	bool pwm_reported = false;
	bool adc_reported = false;

	/** @brief GPIO edge capture callback입니다. */
	struct gpio_callback capture_callback;

	/** @brief ISR과 main이 공유하는 PWM 측정값을 보호합니다. */
	struct k_spinlock capture_lock;

	/** @brief 현재 PWM edge 측정 누적값입니다. */
	std::uint64_t previous_rising_cycle = 0U;
	std::uint64_t period_cycle_sum = 0U;
	std::uint64_t high_cycle_sum = 0U;
	std::uint32_t period_count = 0U;
	std::uint32_t high_count = 0U;
	unsigned int armed_duty_percent = 0U;

	/** @brief I2C target callback table입니다. */
	struct i2c_target_callbacks target_callbacks{};

	/** @brief I2C target 등록 정보입니다. */
	struct i2c_target_config target_configuration{};

	/** @brief 문자가 소문자 hex인지 확인합니다. */
	[[nodiscard]] bool isLowerHex(char value)
	{
		return ((value >= '0') && (value <= '9')) ||
			   ((value >= 'a') && (value <= 'f'));
	}

	/** @brief exact 32자리 소문자 hex nonce만 허용합니다. */
	[[nodiscard]] bool validNonce(const char *nonce)
	{
		if ((nonce == nullptr) || (strlen(nonce) != nonce_length))
		{
			return false;
		}
		for (std::size_t index = 0U; index < nonce_length; ++index)
		{
			if (!isLowerHex(nonce[index]))
			{
				return false;
			}
		}
		return true;
	}

	/** @brief hex 문자 하나를 4-bit 값으로 변환합니다. */
	[[nodiscard]] std::uint8_t hexNibble(char value)
	{
		return static_cast<std::uint8_t>(
			(value <= '9') ? value - '0' : value - 'a' + 10);
	}

	/** @brief 현재 nonce에서 I2C expected write를 생성합니다. */
	void prepareI2cPayload(void)
	{
		for (std::size_t index = 0U; index < sizeof(expected_i2c_payload); ++index)
		{
			expected_i2c_payload[index] = static_cast<std::uint8_t>(
				(hexNibble(active_nonce[index * 2U]) << 4U) |
				hexNibble(active_nonce[(index * 2U) + 1U]));
			i2c_response_payload[index] =
				static_cast<std::uint8_t>(expected_i2c_payload[index] ^ 0xA5U);
		}
	}

	/** @brief UART IRQ byte를 console 고정 queue로 옮깁니다. */
	void uartRxHandler(const struct device *uart, void *user_data)
	{
		auto *const context = static_cast<UartRxContext *>(user_data);
		if ((context == nullptr) || (uart_irq_update(uart) == 0))
		{
			return;
		}
		while (uart_irq_rx_ready(uart) != 0)
		{
			std::uint8_t bytes[16]{};
			const int received = uart_fifo_read(uart, bytes, sizeof(bytes));
			if (received <= 0)
			{
				break;
			}
			for (int index = 0; index < received; ++index)
			{
				if (k_msgq_put(context->queue, &bytes[index], K_NO_WAIT) != 0)
				{
					atomic_set(&context->overflow, 1);
				}
			}
		}
	}

	/** @brief console UART 입력을 interrupt 기반으로 시작합니다. */
	[[nodiscard]] bool startUartRx(const struct device *uart,
								   UartRxContext &context)
	{
		k_msgq_purge(context.queue);
		atomic_clear(&context.overflow);
		if (uart_irq_callback_user_data_set(uart, uartRxHandler, &context) < 0)
		{
			return false;
		}
		uart_irq_rx_enable(uart);
		return true;
	}

	/** @brief interrupt queue에서 bounded UART 한 줄을 읽습니다. */
	[[nodiscard]] bool readQueuedLine(UartRxContext &context, char *output,
									 std::size_t capacity, std::int64_t timeout_ms)
	{
		if ((output == nullptr) || (capacity < 2U))
		{
			return false;
		}
		const std::int64_t deadline = k_uptime_get() + timeout_ms;
		std::size_t length = 0U;
		while (k_uptime_get() < deadline)
		{
			std::uint8_t value = 0U;
			if (k_msgq_get(context.queue, &value, K_MSEC(10)) != 0)
			{
				continue;
			}
			if (value == '\r')
			{
				continue;
			}
			if (value == '\n')
			{
				output[length] = '\0';
				return length > 0U;
			}
			if ((length + 1U) >= capacity)
			{
				return false;
			}
			output[length++] = static_cast<char>(value);
		}
		return false;
	}

	/** @brief peer console에 현재 nonce와 결합한 FAIL을 출력합니다. */
	void reportFailure(const char *stage)
	{
		printk("NUCODE_AC02B_FAIL:role=peer:stage=%s:nonce=%s\n", stage,
			   validNonce(active_nonce) ? active_nonce
									: "00000000000000000000000000000000");
	}

	/** @brief TWIS가 받은 buffer를 nonce와 exact 비교합니다. */
	void targetBufferWriteReceived(struct i2c_target_config *, std::uint8_t *data,
								   std::uint32_t size)
	{
		if ((data == nullptr) || (size != sizeof(expected_i2c_payload)) ||
			(memcmp(data, expected_i2c_payload, sizeof(expected_i2c_payload)) != 0))
		{
			atomic_set(&i2c_invalid, 1);
			return;
		}
		if ((atomic_inc(&i2c_valid_write_count) + 1) > 2)
		{
			atomic_set(&i2c_invalid, 1);
		}
	}

	/** @brief TWIS repeated-start read에 nonce 변환 buffer를 제공합니다. */
	int targetBufferReadRequested(struct i2c_target_config *, std::uint8_t **data,
								  std::uint32_t *size)
	{
		if ((data == nullptr) || (size == nullptr) ||
			(atomic_get(&i2c_invalid) != 0) ||
			(atomic_get(&i2c_valid_write_count) == 0))
		{
			return -EIO;
		}
		*data = i2c_response_payload;
		*size = sizeof(i2c_response_payload);
		return 0;
	}

	/** @brief P1.14 양 edge에서 period와 high 시간을 hardware cycle로 누적합니다. */
	void captureEdge(const struct device *port, struct gpio_callback *,
					 gpio_port_pins_t)
	{
		const int level = gpio_pin_get_raw(port, pwm_capture_pin);
		if (level < 0)
		{
			return;
		}
		const std::uint64_t now = k_cycle_get_64();
		const k_spinlock_key_t key = k_spin_lock(&capture_lock);
		if (level != 0)
		{
			if (previous_rising_cycle != 0U)
			{
				period_cycle_sum += now - previous_rising_cycle;
				++period_count;
			}
			previous_rising_cycle = now;
		}
		else if (previous_rising_cycle != 0U)
		{
			high_cycle_sum += now - previous_rising_cycle;
			++high_count;
		}
		k_spin_unlock(&capture_lock, key);
	}

	/** @brief PWM capture 누적값을 초기화하고 양 edge IRQ를 무장합니다. */
	[[nodiscard]] bool armCapture(unsigned int duty_percent)
	{
		if ((duty_percent != 25U) && (duty_percent != 75U))
		{
			return false;
		}
		if (gpio_pin_interrupt_configure(capture_gpio, pwm_capture_pin,
									 GPIO_INT_DISABLE) < 0)
		{
			return false;
		}
		const k_spinlock_key_t key = k_spin_lock(&capture_lock);
		previous_rising_cycle = 0U;
		period_cycle_sum = 0U;
		high_cycle_sum = 0U;
		period_count = 0U;
		high_count = 0U;
		armed_duty_percent = duty_percent;
		k_spin_unlock(&capture_lock, key);
		return gpio_pin_interrupt_configure(capture_gpio, pwm_capture_pin,
										GPIO_INT_EDGE_BOTH) == 0;
	}

	/** @brief 누적 edge에서 1 kHz와 요청 duty 허용 범위를 판정합니다. */
	[[nodiscard]] bool validateCapture(unsigned int expected_duty)
	{
		static_cast<void>(gpio_pin_interrupt_configure(
			capture_gpio, pwm_capture_pin, GPIO_INT_DISABLE));
		const k_spinlock_key_t key = k_spin_lock(&capture_lock);
		const std::uint64_t periods = period_cycle_sum;
		const std::uint64_t highs = high_cycle_sum;
		const std::uint32_t periods_observed = period_count;
		const std::uint32_t highs_observed = high_count;
		const unsigned int armed = armed_duty_percent;
		k_spin_unlock(&capture_lock, key);
		if ((armed != expected_duty) || (periods_observed < 8U) ||
			(highs_observed < 8U) || (periods == 0U))
		{
			return false;
		}
		const std::uint64_t average_period_cycles = periods / periods_observed;
		const std::uint64_t average_high_cycles = highs / highs_observed;
		const std::uint64_t period_us = k_cyc_to_us_floor64(average_period_cycles);
		if (period_us == 0U)
		{
			return false;
		}
		const std::uint64_t frequency_hz = 1000000ULL / period_us;
		const std::uint64_t duty_percent =
			(average_high_cycles * 100ULL) / average_period_cycles;
		return (frequency_hz >= 850U) && (frequency_hz <= 1150U) &&
			   (duty_percent >= (expected_duty - 8U)) &&
			   (duty_percent <= (expected_duty + 8U));
	}

	/** @brief Wire 두 round가 끝났으면 peer exact token을 한 번 출력합니다. */
	void reportWireIfReady(void)
	{
		if (!wire_reported && (atomic_get(&i2c_invalid) == 0) &&
			(atomic_get(&i2c_valid_write_count) == 2))
		{
			printk("NUCODE_AC02B_PEER:WIRE:PASS:address=0x52:clocks=100000,400000:bytes=32:nonce=%s\n",
				   active_nonce);
			wire_reported = true;
		}
	}

	/** @brief host relay에 nonce가 결합된 exact 응답을 출력합니다. */
	void reportRelayResponse(const char *response)
	{
		printk("NUCODE_AC02B_RELAY:RESPONSE:%s:nonce=%s\n", response,
			   active_nonce);
	}

	/** @brief 현재 순서의 PWM relay 명령을 실행합니다. */
	[[nodiscard]] bool handlePwmRelay(std::size_t step)
	{
		if ((step == 0U) || (step == 2U))
		{
			const unsigned int duty = (step == 0U) ? 25U : 75U;
			if (!armCapture(duty))
			{
				return false;
			}
			reportRelayResponse(relay_responses[step]);
			return true;
		}
		const unsigned int duty = (step == 1U) ? 25U : 75U;
		if (!validateCapture(duty))
		{
			return false;
		}
		reportRelayResponse(relay_responses[step]);
		++pwm_pass_count;
		if ((pwm_pass_count == 2U) && !pwm_reported)
		{
			printk("NUCODE_AC02B_PEER:PWM:PASS:frequency=1000:duty=25,75:nonce=%s\n",
				   active_nonce);
			pwm_reported = true;
		}
		return true;
	}

	/** @brief 현재 순서의 ADC relay 명령을 실행합니다. */
	[[nodiscard]] bool handleAdcRelay(std::size_t step)
	{
		const bool high = step == 5U;
		if (gpio_pin_set_raw(drive_gpio, adc_drive_pin, high ? 1 : 0) < 0)
		{
			return false;
		}
		adc_low_seen = adc_low_seen || !high;
		adc_high_seen = adc_high_seen || high;
		reportRelayResponse(relay_responses[step]);
		if (adc_low_seen && adc_high_seen && !adc_reported)
		{
			printk("NUCODE_AC02B_PEER:ADC:PASS:levels=0,1:nonce=%s\n",
				   active_nonce);
			adc_reported = true;
		}
		return true;
	}

	/** @brief host console의 nonce·순서 결합 relay 명령 하나를 처리합니다. */
	[[nodiscard]] bool handleRelayLine(const char *line, bool &finished)
	{
		if (relay_step >= (sizeof(relay_commands) / sizeof(relay_commands[0])))
		{
			return false;
		}
		char expected[line_capacity]{};
		const int count = snprintf(expected, sizeof(expected),
			"NUCODE_AC02B_RELAY:REQUEST:%s:nonce=%s",
			relay_commands[relay_step], active_nonce);
		if ((count <= 0) || (static_cast<std::size_t>(count) >= sizeof(expected)) ||
			(strcmp(line, expected) != 0))
		{
			return false;
		}

		reportWireIfReady();
		const std::size_t step = relay_step;
		bool success = false;
		if (step < 4U)
		{
			success = handlePwmRelay(step);
		}
		else if (step < 7U)
		{
			success = handleAdcRelay(step);
		}
		else
		{
			const bool complete = wire_reported && pwm_reported && adc_reported &&
							  (atomic_get(&i2c_invalid) == 0) &&
							  (atomic_get(&i2c_valid_write_count) == 2);
			if (complete)
			{
				static_cast<void>(gpio_pin_set_raw(drive_gpio, adc_drive_pin, 0));
				reportRelayResponse(relay_responses[step]);
				printk("NUCODE_AC02B_PEER:FINAL:PASS:nonce=%s\n", active_nonce);
				finished = true;
				success = true;
			}
		}
		if (success)
		{
			++relay_step;
		}
		return success;
	}

	/** @brief 물리 peer 장치와 callback을 host start 뒤에만 활성화합니다. */
	[[nodiscard]] bool initializePeer(void)
	{
		if (!device_is_ready(console_uart) || !device_is_ready(target_i2c) ||
			!device_is_ready(capture_gpio) || !device_is_ready(drive_gpio))
		{
			return false;
		}
		if (gpio_pin_configure(capture_gpio, pwm_capture_pin, GPIO_INPUT) < 0)
		{
			return false;
		}
		gpio_init_callback(&capture_callback, captureEdge, BIT(pwm_capture_pin));
		if (gpio_add_callback(capture_gpio, &capture_callback) < 0)
		{
			return false;
		}
		if (gpio_pin_configure(drive_gpio, adc_drive_pin, GPIO_OUTPUT_LOW) < 0)
		{
			return false;
		}
		target_callbacks.buf_write_received = targetBufferWriteReceived;
		target_callbacks.buf_read_requested = targetBufferReadRequested;
		target_configuration.address = i2c_target_address;
		target_configuration.callbacks = &target_callbacks;
		return i2c_target_register(target_i2c, &target_configuration) == 0;
	}
}

/** @brief host nonce를 받고 console relay 기반 direct Zephyr peer를 단발 실행합니다. */
int main(void)
{
	if (!device_is_ready(console_uart) ||
		!startUartRx(console_uart, console_rx_context))
	{
		return 1;
	}
	printk("NUCODE_AC02B_READY:role=peer\n");

	char command[line_capacity]{};
	while (true)
	{
		if (!readQueuedLine(console_rx_context, command, sizeof(command), 1000))
		{
			if (atomic_get(&console_rx_context.overflow) != 0)
			{
				reportFailure("host-rx-overflow");
				return 1;
			}
			continue;
		}
		constexpr char prefix[] = "NUCODE_AC02B_START:";
		if ((strncmp(command, prefix, sizeof(prefix) - 1U) == 0) &&
			validNonce(command + sizeof(prefix) - 1U))
		{
			memcpy(active_nonce, command + sizeof(prefix) - 1U,
				   nonce_length + 1U);
			break;
		}
	}

	prepareI2cPayload();
	if (!initializePeer())
	{
		reportFailure("initialize");
		return 1;
	}
	printk("NUCODE_AC02B_PEER:ARMED:PASS:address=0x52:control=host-console:nonce=%s\n",
		   active_nonce);
	printk("NUCODE_AC02B_PEER:UART30:PASS:status=disabled:pins=high-z:nonce=%s\n",
		   active_nonce);

	bool finished = false;
	while (!finished)
	{
		reportWireIfReady();
		char line[line_capacity]{};
		if (!readQueuedLine(console_rx_context, line, sizeof(line), 200))
		{
			if ((atomic_get(&i2c_invalid) != 0) ||
				(atomic_get(&console_rx_context.overflow) != 0))
			{
				reportFailure("console-or-wire");
				return 1;
			}
			continue;
		}
		if (!handleRelayLine(line, finished))
		{
			reportFailure("relay-command-order");
			return 1;
		}
	}
	return 0;
}
