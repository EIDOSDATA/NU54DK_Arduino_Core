/**
 * @file digital_pins.inc
 * @brief NU54DK의 공개 GPIO 역할과 Devicetree alias 관계를 선언합니다.
 *
 * 이 파일은 X-macro 입력입니다. 실제 GPIO controller, pin 번호와 flag는 기록하지 않고
 * 고정 보드 Devicetree의 alias만 참조합니다. `pwm_owned` class는 alias mapping을
 * 검증하되 digital descriptor를 생성하지 않습니다.
 *
 * SPDX-License-Identifier: MIT
 */

#ifndef NUCODE_NU54DK_DIGITAL_PIN
#error "digital_pins.inc를 포함하기 전에 NUCODE_NU54DK_DIGITAL_PIN을 정의해야 합니다."
#endif

NUCODE_NU54DK_DIGITAL_PIN(LED_BUILTIN, led0, led)
NUCODE_NU54DK_DIGITAL_PIN(PIN_BUTTON0, sw0, button)
NUCODE_NU54DK_DIGITAL_PIN(PIN_LED1, led1, pwm_owned)
NUCODE_NU54DK_DIGITAL_PIN(PIN_LED2, led2, led)
NUCODE_NU54DK_DIGITAL_PIN(PIN_LED3, led3, led)
NUCODE_NU54DK_DIGITAL_PIN(PIN_BUTTON1, sw1, button)
NUCODE_NU54DK_DIGITAL_PIN(PIN_BUTTON2, sw2, button)
NUCODE_NU54DK_DIGITAL_PIN(PIN_BUTTON3, sw3, button)
