/**
 * @file main.cpp
 * @brief AC-02B DUT와 물리 연결되는 direct Zephyr peer를 구현합니다.
 *
 * @details Arduino Wire target이 지원되지 않으므로 serial21을 TWIS target으로
 * 전환합니다. uart30 echo, P1.14 edge capture와 P2.5 ADC 구동도 이 peer가 맡습니다.
 * host가 nonce를 주입하기 전에는 READY만 출력하며 PASS를 생성하지 않습니다.
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
	constexpr std::size_t line_capacity = 96U;

	/** @brief PMIC 0x6A와 겹치지 않는 AC-02B target 주소입니다. */
	constexpr std::uint16_t i2c_target_address = 0x52U;

	/** @brief DUT P1.10 PWM이 연결되는 peer input입니다. */
	constexpr gpio_pin_t pwm_capture_pin = 14U;

	/** @brief DUT P1.12 ADC를 구동하는 peer output입니다. */
	constexpr gpio_pin_t adc_drive_pin = 5U;

	/** @brief host console UART입니다. */
	const struct device *const console_uart = DEVICE_DT_GET(DT_CHOSEN(zephyr_console));

	/** @brief DUT와 교차 연결되는 uart30입니다. */
	const struct device *const peer_uart = DEVICE_DT_GET(DT_NODELABEL(uart30));

	/** @brief P1.2/P1.3을 사용하는 direct TWIS21 target입니다. */
	const struct device *const target_i2c = DEVICE_DT_GET(DT_NODELABEL(i2c21));

	/** @brief PWM capture port입니다. */
	const struct device *const capture_gpio = DEVICE_DT_GET(DT_NODELABEL(gpio1));

	/** @brief ADC drive port입니다. */
	const struct device *const drive_gpio = DEVICE_DT_GET(DT_NODELABEL(gpio2));

	/** @brief 현재 run과 결합한 nonce입니다. */
	char active_nonce[nonce_length + 1U]{};

	/** @brief nonce에서 파생한 I2C expected write입니다. */
	std::uint8_t expected_i2c_payload[16]{};

	/** @brief TWIS read request에 제공할 변환 응답입니다. */
	std::uint8_t i2c_response_payload[16]{};

	/** @brief 유효한 repeated-start write 횟수입니다. */
	atomic_t i2c_valid_write_count = ATOMIC_INIT(0);

	/** @brief I2C 길이·payload 불일치를 보존하는 fail-closed 표식입니다. */
	atomic_t i2c_invalid = ATOMIC_INIT(0);

	/** @brief peer protocol 단계 관찰값입니다. */
	unsigned int serial_cycle_count = 0U;
	unsigned int pwm_pass_count = 0U;
	bool adc_low_seen = false;
	bool adc_high_seen = false;
	bool wire_reported = false;
	bool serial_reported = false;
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

	/** @brief polling UART에 ASCII line을 기록합니다. */
	void writeUartLine(const struct device *uart, const char *line)
	{
		for (const char *cursor = line; *cursor != '\0'; ++cursor)
		{
			uart_poll_out(uart, static_cast<unsigned char>(*cursor));
		}
		uart_poll_out(uart, '\r');
		uart_poll_out(uart, '\n');
	}

	/** @brief polling UART에서 bounded line을 읽습니다. */
	[[nodiscard]] bool readUartLine(const struct device *uart, char *output,
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
			unsigned char value = 0U;
			if (uart_poll_in(uart, &value) != 0)
			{
				k_sleep(K_MSEC(1));
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
		const atomic_val_t count = atomic_inc(&i2c_valid_write_count) + 1;
		if (count > 2)
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
	void captureEdge(const struct device *port, struct gpio_callback *, gpio_port_pins_t)
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
		const std::uint64_t duty_min = expected_duty - 8U;
		const std::uint64_t duty_max = expected_duty + 8U;
		return (frequency_hz >= 850U) && (frequency_hz <= 1150U) &&
			   (duty_percent >= duty_min) && (duty_percent <= duty_max);
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

	/** @brief DUT Serial1 frame를 nonce와 cycle에 결합해 echo합니다. */
	[[nodiscard]] bool handleSerialFrame(const char *line)
	{
		char expected[line_capacity]{};
		const int count = snprintf(expected, sizeof(expected), "S1:%s:%u",
								   active_nonce, serial_cycle_count);
		if ((count <= 0) || (strcmp(line, expected) != 0))
		{
			return false;
		}
		char response[line_capacity]{};
		static_cast<void>(snprintf(response, sizeof(response), "E1:%s:%u",
								   active_nonce, serial_cycle_count));
		writeUartLine(peer_uart, response);
		++serial_cycle_count;
		if ((serial_cycle_count == 2U) && !serial_reported)
		{
			printk("NUCODE_AC02B_PEER:SERIAL1:PASS:baud=115200:cycles=2:bytes=64:nonce=%s\n",
				   active_nonce);
			serial_reported = true;
		}
		return true;
	}

	/** @brief PWM control command를 실행하고 DUT에 exact 응답을 보냅니다. */
	[[nodiscard]] bool handlePwmCommand(const char *line)
	{
		if ((strcmp(line, "PWM:ARM:25") == 0) ||
			(strcmp(line, "PWM:ARM:75") == 0))
		{
			const unsigned int duty = (line[8] == '2') ? 25U : 75U;
			if (!armCapture(duty))
			{
				return false;
			}
			writeUartLine(peer_uart,
						  duty == 25U ? "PWM:ARM:25:OK" : "PWM:ARM:75:OK");
			return true;
		}
		if ((strcmp(line, "PWM:CHECK:25") == 0) ||
			(strcmp(line, "PWM:CHECK:75") == 0))
		{
			const unsigned int duty = (line[10] == '2') ? 25U : 75U;
			if (!validateCapture(duty))
			{
				return false;
			}
			writeUartLine(peer_uart, duty == 25U ? "PWM:25:PASS" : "PWM:75:PASS");
			++pwm_pass_count;
			if ((pwm_pass_count == 2U) && !pwm_reported)
			{
				printk("NUCODE_AC02B_PEER:PWM:PASS:frequency=1000:duty=25,75:nonce=%s\n",
					   active_nonce);
				pwm_reported = true;
			}
			return true;
		}
		return false;
	}

	/** @brief ADC LOW/HIGH drive command를 실행합니다. */
	[[nodiscard]] bool handleAdcCommand(const char *line)
	{
		if (strcmp(line, "ADC:LOW") == 0)
		{
			if (gpio_pin_set_raw(drive_gpio, adc_drive_pin, 0) < 0)
			{
				return false;
			}
			adc_low_seen = true;
			writeUartLine(peer_uart, "ADC:LOW:OK");
		}
		else if (strcmp(line, "ADC:HIGH") == 0)
		{
			if (gpio_pin_set_raw(drive_gpio, adc_drive_pin, 1) < 0)
			{
				return false;
			}
			adc_high_seen = true;
			writeUartLine(peer_uart, "ADC:HIGH:OK");
		}
		else
		{
			return false;
		}
		if (adc_low_seen && adc_high_seen && !adc_reported)
		{
			printk("NUCODE_AC02B_PEER:ADC:PASS:levels=0,1:nonce=%s\n", active_nonce);
			adc_reported = true;
		}
		return true;
	}

	/** @brief physical peer 장치와 callback을 host start 뒤에만 활성화합니다. */
	[[nodiscard]] bool initializePeer(void)
	{
		if (!device_is_ready(console_uart) || !device_is_ready(peer_uart) ||
			!device_is_ready(target_i2c) || !device_is_ready(capture_gpio) ||
			!device_is_ready(drive_gpio))
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

	/** @brief DUT command 하나를 처리하고 모든 단계의 fail-closed 상태를 유지합니다. */
	[[nodiscard]] bool handlePeerLine(const char *line, bool &finished)
	{
		reportWireIfReady();
		if (strncmp(line, "S1:", 3U) == 0)
		{
			return handleSerialFrame(line);
		}
		if (strncmp(line, "PWM:", 4U) == 0)
		{
			return handlePwmCommand(line);
		}
		if (strncmp(line, "ADC:", 4U) == 0)
		{
			return handleAdcCommand(line);
		}
		if (strcmp(line, "DONE") == 0)
		{
			reportWireIfReady();
			const bool complete = serial_reported && wire_reported && pwm_reported &&
								  adc_reported && (atomic_get(&i2c_invalid) == 0) &&
								  (atomic_get(&i2c_valid_write_count) == 2);
			if (!complete)
			{
				return false;
			}
			static_cast<void>(gpio_pin_set_raw(drive_gpio, adc_drive_pin, 0));
			writeUartLine(peer_uart, "DONE:PASS");
			printk("NUCODE_AC02B_PEER:FINAL:PASS:nonce=%s\n", active_nonce);
			finished = true;
			return true;
		}
		return false;
	}
}

/** @brief host nonce를 받고 direct Zephyr peer를 단발 실행합니다. */
int main(void)
{
	if (!device_is_ready(console_uart))
	{
		return 1;
	}
	printk("NUCODE_AC02B_READY:role=peer\n");

	char command[line_capacity]{};
	while (true)
	{
		if (!readUartLine(console_uart, command, sizeof(command), 1000))
		{
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
	printk("NUCODE_AC02B_PEER:ARMED:PASS:address=0x52:nonce=%s\n", active_nonce);

	bool finished = false;
	while (!finished)
	{
		reportWireIfReady();
		char line[line_capacity]{};
		if (!readUartLine(peer_uart, line, sizeof(line), 200))
		{
			if (atomic_get(&i2c_invalid) != 0)
			{
				reportFailure("wire-payload");
				return 1;
			}
			continue;
		}
		if (!handlePeerLine(line, finished))
		{
			reportFailure("peer-command");
			return 1;
		}
	}
	return 0;
}
