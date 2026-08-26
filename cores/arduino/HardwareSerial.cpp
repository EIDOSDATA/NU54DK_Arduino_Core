/**
 * @file HardwareSerial.cpp
 * @brief Zephyr console UART를 빌려 쓰는 기본 Arduino Serial을 구현합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <Arduino.h>

#include <zephyr/device.h>
#include <zephyr/devicetree.h>
#include <zephyr/drivers/uart.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/atomic.h>

#include <cstddef>
#include <cstdint>

#include "internal/SerialBackend.h"

#if DT_HAS_CHOSEN(nucode_arduino_serial)
#define NUCODE_ARDUINO_SERIAL_NODE DT_CHOSEN(nucode_arduino_serial)
#elif DT_HAS_CHOSEN(zephyr_console)
#define NUCODE_ARDUINO_SERIAL_NODE DT_CHOSEN(zephyr_console)
#else
#error "기본 Serial에는 nucode,arduino-serial 또는 zephyr,console chosen이 필요합니다."
#endif

#if !DT_NODE_HAS_STATUS_OKAY(NUCODE_ARDUINO_SERIAL_NODE)
#error "기본 Serial chosen UART가 활성화되어 있지 않습니다."
#endif

namespace
{

    using nucode::arduino::internal::SerialError;

    /** @brief Devicetree가 선언한 Zephyr 소유 UART 속도입니다. */
    constexpr unsigned long configured_baud =
        DT_PROP(NUCODE_ARDUINO_SERIAL_NODE, current_speed);

    K_MSGQ_DEFINE(serial_rx_queue, sizeof(std::uint8_t),
                  CONFIG_NUCODE_ARDUINO_SERIAL_RX_BUFFER_SIZE, alignof(std::uint8_t));
    K_MUTEX_DEFINE(serial_lifecycle_mutex);
    K_MUTEX_DEFINE(serial_tx_mutex);

    atomic_t serial_started = ATOMIC_INIT(0);
    atomic_t last_serial_error = ATOMIC_INIT(static_cast<atomic_val_t>(SerialError::none));
    atomic_t last_serial_driver_error = ATOMIC_INIT(0);
    atomic_t dropped_rx_bytes = ATOMIC_INIT(0);

    /** @brief 기본 Serial이 참조하는 Zephyr UART 장치입니다. */
    const struct device *const serial_device = DEVICE_DT_GET(NUCODE_ARDUINO_SERIAL_NODE);

    /**
     * @brief Serial 진단 상태를 원자적으로 기록합니다.
     *
     * @param error Core 내부 오류입니다.
     * @param driver_error Zephyr UART가 반환한 오류입니다.
     */
    void recordSerialError(SerialError error, int driver_error = 0) noexcept
    {
        atomic_set(&last_serial_driver_error, static_cast<atomic_val_t>(driver_error));
        atomic_set(&last_serial_error, static_cast<atomic_val_t>(error));
    }

    /** @brief 성공한 Serial API 뒤 이전 오류를 제거합니다. */
    void recordSerialSuccess() noexcept
    {
        recordSerialError(SerialError::none);
    }

    /**
     * @brief Arduino가 요청한 설정이 Zephyr 소유 설정과 같은지 확인합니다.
     *
     * @param baudrate 요청한 통신 속도입니다.
     * @param config 요청한 data/parity/stop 설정입니다.
     * @return 재설정 없이 사용할 수 있으면 true입니다.
     */
    [[nodiscard]] bool isSupportedRequest(unsigned long baudrate, std::uint16_t config) noexcept
    {
        return (baudrate == configured_baud) &&
               (config == static_cast<std::uint16_t>(SERIAL_8N1));
    }

    /**
     * @brief Zephyr driver의 실제 UART 설정이 M6 Serial 계약과 같은지 확인합니다.
     *
     * @param config 읽어 온 Zephyr UART 설정입니다.
     * @param baudrate Arduino Sketch가 요청한 통신 속도입니다.
     * @return 장치를 재설정하지 않고 사용할 수 있으면 true입니다.
     */
    [[nodiscard]] bool matchesActiveConfig(const struct uart_config &config,
                                           unsigned long baudrate) noexcept
    {
        return (config.baudrate == baudrate) &&
               (config.parity == UART_CFG_PARITY_NONE) &&
               (config.stop_bits == UART_CFG_STOP_BITS_1) &&
               (config.data_bits == UART_CFG_DATA_BITS_8) &&
               (config.flow_ctrl == UART_CFG_FLOW_CTRL_NONE);
    }

    /**
     * @brief UART RX IRQ에서 수신 byte를 고정 queue로 옮깁니다.
     *
     * @param device callback을 발생시킨 UART입니다.
     * @param user_data 사용하지 않습니다.
     */
    void serialIrqHandler(const struct device *device, void *user_data)
    {
        ARG_UNUSED(user_data);

        if ((atomic_get(&serial_started) == 0) || (uart_irq_update(device) == 0))
        {
            return;
        }

        while (uart_irq_rx_ready(device) != 0)
        {
            std::uint8_t bytes[16] = {};
            const int received = uart_fifo_read(device, bytes, sizeof(bytes));
            if (received <= 0)
            {
                break;
            }

            for (int index = 0; index < received; ++index)
            {
                if (k_msgq_put(&serial_rx_queue, &bytes[index], K_NO_WAIT) != 0)
                {
                    atomic_inc(&dropped_rx_bytes);
                    recordSerialError(SerialError::rx_overflow);
                }
            }
        }
    }

    /** @brief ArduinoCore-API HardwareSerial의 Zephyr 구현입니다. */
    class ZephyrHardwareSerial final : public arduino::HardwareSerial
    {
    public:
        /** @brief Zephyr가 구성한 기본 속도로 RX lifecycle을 시작합니다. */
        void begin(unsigned long baudrate) override
        {
            begin(baudrate, static_cast<std::uint16_t>(SERIAL_8N1));
        }

        /**
         * @brief Zephyr 소유 속성을 바꾸지 않고 Arduino RX lifecycle을 시작합니다.
         *
         * @param baudrate DTS와 같아야 하는 통신 속도입니다.
         * @param config M6에서는 SERIAL_8N1만 허용합니다.
         */
        void begin(unsigned long baudrate, std::uint16_t config) override
        {
            if (k_is_in_isr())
            {
                recordSerialError(SerialError::invalid_context);
                return;
            }

            if (!isSupportedRequest(baudrate, config))
            {
                recordSerialError(SerialError::unsupported_config);
                return;
            }

            if (!device_is_ready(serial_device))
            {
                recordSerialError(SerialError::device_not_ready);
                return;
            }

            struct uart_config active_config = {};
            const int config_result = uart_config_get(serial_device, &active_config);
            if (config_result < 0)
            {
                recordSerialError(SerialError::driver_error, config_result);
                return;
            }
            if (!matchesActiveConfig(active_config, baudrate))
            {
                recordSerialError(SerialError::unsupported_config);
                return;
            }

            static_cast<void>(k_mutex_lock(&serial_lifecycle_mutex, K_FOREVER));
            if (atomic_get(&serial_started) != 0)
            {
                recordSerialSuccess();
                static_cast<void>(k_mutex_unlock(&serial_lifecycle_mutex));
                return;
            }

            k_msgq_purge(&serial_rx_queue);
            const int result = uart_irq_callback_user_data_set(serial_device, serialIrqHandler,
                                                               nullptr);
            if (result < 0)
            {
                recordSerialError(SerialError::driver_error, result);
                static_cast<void>(k_mutex_unlock(&serial_lifecycle_mutex));
                return;
            }

            atomic_set(&serial_started, 1);
            uart_irq_rx_enable(serial_device);
            recordSerialSuccess();
            static_cast<void>(k_mutex_unlock(&serial_lifecycle_mutex));
        }

        /** @brief Arduino RX IRQ와 queue만 해제하고 UART 장치는 유지합니다. */
        void end() override
        {
            if (k_is_in_isr())
            {
                recordSerialError(SerialError::invalid_context);
                return;
            }

            static_cast<void>(k_mutex_lock(&serial_lifecycle_mutex, K_FOREVER));
            if (atomic_get(&serial_started) == 0)
            {
                recordSerialSuccess();
                static_cast<void>(k_mutex_unlock(&serial_lifecycle_mutex));
                return;
            }

            atomic_clear(&serial_started);
            uart_irq_rx_disable(serial_device);
            const int result = uart_irq_callback_user_data_set(serial_device, nullptr, nullptr);
            k_msgq_purge(&serial_rx_queue);

            if (result < 0)
            {
                recordSerialError(SerialError::driver_error, result);
            }
            else
            {
                recordSerialSuccess();
            }
            static_cast<void>(k_mutex_unlock(&serial_lifecycle_mutex));
        }

        /** @brief RX queue에서 읽을 수 있는 byte 수를 반환합니다. */
        int available() override
        {
            if (k_is_in_isr())
            {
                recordSerialError(SerialError::invalid_context);
                return 0;
            }
            if (atomic_get(&serial_started) == 0)
            {
                recordSerialError(SerialError::not_started);
                return 0;
            }

            recordSerialSuccess();
            return static_cast<int>(k_msgq_num_used_get(&serial_rx_queue));
        }

        /** @brief 다음 RX byte를 소비하지 않고 반환합니다. */
        int peek() override
        {
            if (k_is_in_isr())
            {
                recordSerialError(SerialError::invalid_context);
                return -1;
            }
            if (atomic_get(&serial_started) == 0)
            {
                recordSerialError(SerialError::not_started);
                return -1;
            }

            std::uint8_t value = 0U;
            if (k_msgq_peek(&serial_rx_queue, &value) != 0)
            {
                recordSerialSuccess();
                return -1;
            }

            recordSerialSuccess();
            return value;
        }

        /** @brief 다음 RX byte를 소비하여 반환합니다. */
        int read() override
        {
            if (k_is_in_isr())
            {
                recordSerialError(SerialError::invalid_context);
                return -1;
            }
            if (atomic_get(&serial_started) == 0)
            {
                recordSerialError(SerialError::not_started);
                return -1;
            }

            std::uint8_t value = 0U;
            if (k_msgq_get(&serial_rx_queue, &value, K_NO_WAIT) != 0)
            {
                recordSerialSuccess();
                return -1;
            }

            recordSerialSuccess();
            return value;
        }

        /** @brief blocking TX 호출이 완료될 때까지 기다립니다. */
        void flush() override
        {
            if (k_is_in_isr())
            {
                recordSerialError(SerialError::invalid_context);
                return;
            }
            if (atomic_get(&serial_started) == 0)
            {
                recordSerialError(SerialError::not_started);
                return;
            }

            static_cast<void>(k_mutex_lock(&serial_tx_mutex, K_FOREVER));
            static_cast<void>(k_mutex_unlock(&serial_tx_mutex));
            recordSerialSuccess();
        }

        /**
         * @brief 한 byte를 Zephyr polling TX로 기록합니다.
         *
         * @param value 기록할 byte입니다.
         * @return 성공하면 1, 금지 문맥 또는 미시작 상태이면 0입니다.
         */
        std::size_t write(std::uint8_t value) override
        {
            if (k_is_in_isr())
            {
                setWriteError();
                recordSerialError(SerialError::invalid_context);
                return 0U;
            }
            if (atomic_get(&serial_started) == 0)
            {
                setWriteError();
                recordSerialError(SerialError::not_started);
                return 0U;
            }

            static_cast<void>(k_mutex_lock(&serial_tx_mutex, K_FOREVER));
            uart_poll_out(serial_device, value);
            static_cast<void>(k_mutex_unlock(&serial_tx_mutex));
            recordSerialSuccess();
            return 1U;
        }

        /** @brief polling TX가 가능한 상태이면 한 byte 공간을 보고합니다. */
        int availableForWrite() override
        {
            return (!k_is_in_isr() && (atomic_get(&serial_started) != 0)) ? 1 : 0;
        }

        /** @brief Arduino RX lifecycle이 시작되었고 장치가 준비되었는지 반환합니다. */
        operator bool() override
        {
            return (atomic_get(&serial_started) != 0) && device_is_ready(serial_device);
        }
    };

    ZephyrHardwareSerial serial_backend;

}

HardwareSerial &Serial = serial_backend;

namespace nucode::arduino::internal
{

    SerialError lastSerialError() noexcept
    {
        return static_cast<SerialError>(atomic_get(&last_serial_error));
    }

    int lastSerialDriverError() noexcept
    {
        return static_cast<int>(atomic_get(&last_serial_driver_error));
    }

    std::uint32_t serialDroppedRxBytes() noexcept
    {
        return static_cast<std::uint32_t>(atomic_get(&dropped_rx_bytes));
    }

    void clearSerialDiagnostics() noexcept
    {
        atomic_clear(&dropped_rx_bytes);
        recordSerialSuccess();
    }

}

#undef NUCODE_ARDUINO_SERIAL_NODE
