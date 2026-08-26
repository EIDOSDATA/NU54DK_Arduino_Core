/**
 * @file Arduino.h
 * @brief NU54DK용 Arduino Sketch 공개 API의 최소 계약입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#ifndef NUCODE_ARDUINO_CORE_ARDUINO_H_
#define NUCODE_ARDUINO_CORE_ARDUINO_H_

#include <stdint.h>

#ifdef __cplusplus
extern "C"
{
#endif

    /**
     * @brief Arduino 논리 핀 번호 형식입니다.
     *
     * 물리 nRF GPIO 번호가 아니라 Variant descriptor의 배열 index를 나타냅니다.
     */
    typedef uint8_t pin_size_t;

    /**
     * @brief 디지털 핀 값과 향후 interrupt trigger 값을 정의합니다.
     */
    typedef enum
    {
        LOW = 0,     /**< 전기적 Low 레벨입니다. */
        HIGH = 1,    /**< 전기적 High 레벨입니다. */
        CHANGE = 2,  /**< 양쪽 edge interrupt trigger입니다. */
        FALLING = 3, /**< 하강 edge interrupt trigger입니다. */
        RISING = 4,  /**< 상승 edge interrupt trigger입니다. */
    } PinStatus;

    /**
     * @brief Arduino 디지털 핀 동작 모드를 정의합니다.
     */
    typedef enum
    {
        INPUT = 0x0,            /**< 내부 pull 저항이 없는 입력입니다. */
        OUTPUT = 0x1,           /**< push-pull 출력입니다. */
        INPUT_PULLUP = 0x2,     /**< 내부 pull-up을 사용하는 입력입니다. */
        INPUT_PULLDOWN = 0x3,   /**< 내부 pull-down을 사용하는 입력입니다. */
        OUTPUT_OPENDRAIN = 0x4, /**< 향후 지원할 open-drain 출력입니다. */
    } PinMode;

    /**
     * @brief 논리 핀의 입출력 모드를 설정합니다.
     *
     * @note M3에서는 thread 문맥 전용이며 ISR에서는 안전한 no-op입니다.
     * @note 같은 핀을 여러 thread가 동시에 제어하는 것은 아직 지원하지 않습니다.
     *
     * @param pinNumber Variant가 정의한 논리 핀 번호입니다.
     * @param pinMode 적용할 Arduino 핀 모드입니다.
     */
    void pinMode(pin_size_t pinNumber, PinMode pinMode);

    /**
     * @brief 논리 핀에 전기적 High 또는 Low를 기록합니다.
     *
     * @note M3에서는 thread 문맥 전용이며 ISR에서는 안전한 no-op입니다.
     *
     * @param pinNumber Variant가 정의한 논리 핀 번호입니다.
     * @param status 기록할 전기적 레벨입니다.
     */
    void digitalWrite(pin_size_t pinNumber, PinStatus status);

    /**
     * @brief 논리 핀의 전기적 레벨을 읽습니다.
     *
     * @note M3에서는 thread 문맥 전용이며 ISR에서는 `LOW`를 반환합니다.
     *
     * @param pinNumber Variant가 정의한 논리 핀 번호입니다.
     * @return 전기적 High이면 `HIGH`, Low 또는 오류이면 `LOW`입니다.
     */
    PinStatus digitalRead(pin_size_t pinNumber);

    /**
     * @brief Zephyr system uptime의 하위 32-bit millisecond 값을 반환합니다.
     *
     * @return 약 49.7일마다 자연스럽게 순환하는 millisecond 값입니다.
     */
    unsigned long millis(void);

    /**
     * @brief 현재 firmware 실행 epoch의 하위 32-bit microsecond 값을 반환합니다.
     *
     * @return 약 71.6분마다 자연스럽게 순환하는 microsecond 값입니다.
     */
    unsigned long micros(void);

    /**
     * @brief 현재 thread를 지정한 millisecond 이상 재웁니다.
     *
     * @note 양보할 수 없는 문맥과 ISR에서는 안전한 no-op입니다.
     *
     * @param milliseconds 대기할 시간입니다.
     */
    void delay(unsigned long milliseconds);

    /**
     * @brief 현재 CPU에서 지정한 microsecond 동안 busy wait합니다.
     *
     * @note ISR에서는 안전한 no-op입니다.
     *
     * @param microseconds 대기할 시간입니다.
     */
    void delayMicroseconds(unsigned int microseconds);

    /**
     * @brief 현재 thread와 같은 priority의 다른 ready thread에 실행 기회를 줍니다.
     *
     * @note 양보할 수 없는 문맥과 ISR에서는 안전한 no-op입니다.
     */
    void yield(void);

#ifdef __cplusplus
}
#endif

#include <variant.h>

/**
 * @brief Sketch 초기화를 수행합니다.
 *
 * 애플리케이션이 반드시 정의해야 하며 Core 런타임이 정확히 한 번 호출합니다.
 */
void setup(void);

/**
 * @brief Sketch의 반복 작업을 수행합니다.
 *
 * 애플리케이션이 반드시 정의해야 하며 Core 런타임이 반환할 때마다 다시
 * 호출합니다.
 */
void loop(void);

#endif
