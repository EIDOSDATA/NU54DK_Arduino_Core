# NU54DK Arduino 핀과 Variant 설계

| 항목 | 내용 |
| --- | --- |
| 문서 ID | CORE-PIN-001 |
| 문서 개정 | 3.2 |
| 문서 상태 | `v0.2.0` 정식 계약 + `v0.3.0` AC-01 자동 검증 완료 |
| 최종 갱신일 | 2026-08-31 |
| 대상 보드 | `nrf54l15dk/nrf54l15/cpuapp/nu54dk` |

## 1. 목적

이 문서는 NU54DK의 Devicetree 자원을 Arduino 논리 핀으로 노출하는 현재 계약을 정의한다.
물리 GPIO 번호, pinctrl과 전기적 특성은 보드 패키지가 소유하며 Variant는 공개 이름, sparse
논리 ID와 기능만 소유한다.

`v0.2.0` 기본 범위의 핵심은 다음 두 수치를 구분하는 것이다.

- `NUM_DIGITAL_PINS == 10`: `0..9`로 순회할 수 있는 공개 논리 ID 범위
- `NUM_DIGITAL_CAPABLE_PINS == 7`: 실제 digital GPIO descriptor를 가진 ID 개수

`PIN_A0`, `PIN_PWM0`과 PWM이 소유한 `PIN_LED1`도 `0..9` 범위에 있지만 digital 핀이 아니다.
따라서 `pin < NUM_DIGITAL_PINS`만으로 `pinMode()`, `digitalRead()` 또는 interrupt 사용 가능성을
판정하면 안 된다.

`v0.3.0`의 `standard`와 `ble` profile은 Core 소유 connector DTS를 합성해 `PIN_GPIO0/D10`
(P2.5)과 `PIN_GPIO1/D11`(P2.6)을 추가한다. 이때 공개 범위는 12, 실제 digital descriptor는
9가 된다. Connector DTS가 없는 expert/legacy build는 기존 10/7 계약을 그대로 유지한다.

## 2. 단일 원본과 책임

| 정보 | 단일 원본 |
| --- | --- |
| 보드 기본 GPIO controller, 실제 pin, flag, pinctrl | `board_package/NU54DK_Zephyr_DTS` |
| Arduino profile 전용 connector GPIO 역할 | `dts/nucode/nu54dk-arduino-connectors.dtsi` |
| Arduino 이름과 논리 ID | `variants/nu54dk/variant.h` |
| DTS alias와 digital capability 연결 | `variants/nu54dk/digital_pins.inc` |
| immutable GPIO descriptor 생성 | `variants/nu54dk/variant.cpp` |
| 공통 descriptor·오류 형식 | `cores/arduino/internal/pin_description.h` |
| GPIO·시간·interrupt 동작 | `cores/arduino/wiring_*.cpp` |

Variant C++에는 `P1.x`, `P2.x` 같은 물리 pin 번호를 복제하지 않는다. Board 기본 역할은 보드
패키지가, Arduino에서만 활성화하는 P2.5/P2.6 connector 역할은 Core profile DTS가 소유한다.
Variant는 두 원본을 합성한 `DT_ALIAS()`와 `DT_CHOSEN()`만 소비한다.

## 3. sparse 논리 핀 모델

| ID | 공개 이름 | DTS 역할 | digital descriptor | 현재 기능 |
| ---: | --- | --- | --- | --- |
| 0 | `LED_BUILTIN`, `PIN_LED0`, `D0` | `led0` | 있음 | input, output, interrupt |
| 1 | `PIN_BUTTON0`, `D1` | `sw0` | 있음 | input, interrupt |
| 2 | `PIN_A0`, `A0` | `nucode,arduino-adc` | 없음 | ADC 전용 |
| 3 | `PIN_PWM0`, `PIN_PWM_LED` | `nucode,arduino-pwm` | 없음 | PWM 전용 |
| 4 | `PIN_LED1` | `led1` | 없음 | `PIN_PWM0`과 같은 자원의 PWM-owned 역할 |
| 5 | `PIN_LED2` | `led2` | 있음 | input, output, interrupt |
| 6 | `PIN_LED3` | `led3` | 있음 | input, output, interrupt |
| 7 | `PIN_BUTTON1` | `sw1` | 있음 | input, interrupt |
| 8 | `PIN_BUTTON2` | `sw2` | 있음 | input, interrupt |
| 9 | `PIN_BUTTON3` | `sw3` | 있음 | input, interrupt |
| 10 | `PIN_GPIO0`, `D10` | `nucode-gpio0` | profile에서 있음 | input, output, open-drain |
| 11 | `PIN_GPIO1`, `D11` | `nucode-gpio1` | profile에서 있음 | input, output, open-drain |

공개 상수는 다음 불변식을 유지한다.

```text
standard/ble profile:
NUM_DIGITAL_PINS          = 12
NUM_DIGITAL_CAPABLE_PINS  = 9
NUM_PIN_ROLES             = 12

connector DTS 없는 expert/legacy build:
NUM_DIGITAL_PINS          = 10
NUM_DIGITAL_CAPABLE_PINS  = 7
NUM_PIN_ROLES             = 10

NUM_ANALOG_INPUTS         = 1
NUM_ANALOG_OUTPUTS        = 1
```

Profile에서는 `digitalPinIsValid(pin)`이 ID `0, 1, 5, 6, 7, 8, 9, 10, 11`에 참을 반환한다.
Connector DTS가 없으면 기존 일곱 ID만 유효하다. `digitalPinToInterrupt()`는 interrupt
capability가 있는 P0/P1 digital ID에는 같은 값을 반환하지만, P2 connector ID 10/11과 예약·범위
밖 ID에는 `NOT_AN_INTERRUPT`를 반환한다. 내부 `pinDescriptionCount()`는 각각 descriptor 개수
9 또는 7을 반환한다.

## 4. Variant 구현 계약

### 4.1 `variant.h`

- 공개 핀 상수와 개수 상수를 제공한다.
- C와 C++에서 `A0`, `digitalPinIsValid()`와 `digitalPinToInterrupt()`를 사용할 수 있게 한다.
- 인수는 한 번만 평가한다.
- 실제 GPIO controller나 물리 pin 번호를 포함하지 않는다.

### 4.2 `digital_pins.inc`

X-macro 입력으로 `led0..3`, `sw0..3`, 조건부 `nucode-gpio0..1`과 공개 ID의 관계를 선언한다.
`pwm_owned` 항목은 DTS mapping을 build에서 검증하지만 digital descriptor는 만들지 않는다.

### 4.3 `variant.cpp`

- DTS에서 `gpio_dt_spec`을 생성한다.
- LED와 버튼에 서로 다른 capability를 부여한다.
- sparse ID와 descriptor를 함께 저장해 배열 index와 논리 ID를 혼동하지 않는다.
- lookup 범위를 벗어나거나 예약 역할이면 `nullptr`을 반환한다.
- heap, runtime pin 번호 복제와 가변 mapping을 사용하지 않는다.

## 5. Digital API 의미

| 항목 | 계약 |
| --- | --- |
| `pinMode()` | capability 확인 뒤 `INPUT`, pull 입력, `OUTPUT` 또는 connector의 `OUTPUT_OPENDRAIN` 적용 |
| `digitalWrite()` | output capability와 push-pull/open-drain output 상태가 있는 핀에 raw `HIGH`/`LOW` 기록 |
| `digitalRead()` | 실제 electrical level을 raw `HIGH`/`LOW`로 반환 |
| LED polarity | GPIO flag는 DTS가 소유하지만 `digitalWrite(HIGH)`는 raw high 의미를 유지 |
| 버튼 | Core debounce나 active-low 논리 반전을 제공하지 않음 |
| interrupt | GPIOTE가 있는 P0/P1 역할에서 raw edge와 one-shot/rearm level 지원; P2 connector는 미지원 |

`PIN_A0`, `PIN_PWM0`, `PIN_LED1`에는 digital descriptor가 없으므로 digital API가
`invalid_pin`으로 거부한다. 이 sparse 거부는 의도된 계약이다.

## 6. Peripheral ownership과 충돌

- `PIN_A0`는 ADC backend가 소유한다.
- `PIN_PWM0`과 `PIN_LED1`은 같은 PWM 자원을 설명하며 동시에 별도 digital GPIO로 소유하지 않는다.
- `PIN_GPIO0`과 `PIN_GPIO1`은 `connector_gpio` ownership으로 고정하며 다른 peripheral 역할로
  자동 전환하지 않는다.
- nRF54L15 CPUAPP의 GPIOTE20/30은 P1/P0에만 연결된다. 따라서 P2.5/P2.6 connector에는
  `interrupt` capability가 없고 `digitalPinToInterrupt()`는 `NOT_AN_INTERRUPT`를 반환한다.
- UART, I2C와 SPI pinctrl 신호는 활성 peripheral이 소유하므로 connector 번호처럼 임의의 `Dn`으로
  중복 노출하지 않는다.
- 전체 header를 연속 `Dn`으로 추정하지 않는다. 승인된 connector 역할은 `D10`, `D11` 두 개만
  제공하며 `D0`, `D1`은 기존 호환 별칭이다.

## 7. 오류와 공개 진단

잘못된 ID, capability, mode, 문맥과 driver 실패는 panic 대신 안전한 실패로 처리한다.
반환값이 없는 Arduino API는 hardware를 변경하지 않고 오류를 기록한다.

GPIO backend의 내부 `GpioError`와 원래 driver errno는 공개
`<nucode/Diagnostics.h>`의 다음 호출로 조회할 수 있다.

```cpp
auto diagnostic = nucode::arduino::lastDiagnostic(
    nucode::arduino::DiagnosticSubsystem::gpio);
```

공개 진단은 `invalid-context`, `invalid-argument`, `invalid-pin`, `unsupported`,
`device-not-ready`, `not-started`, `overflow`, `ownership-conflict`, `driver-error`의 안정된
token을 사용한다. `formatDiagnostic()`의 한 줄 형식은
`NU54:<subsystem>:<code>:driver=<signed>:detail=<unsigned>`이다.

## 8. 실행 문맥

- Digital GPIO 구성과 read/write는 thread 문맥 전용이다.
- ISR에서 호출하면 no-op 또는 `LOW`를 반환하고 `invalid_context`를 기록한다.
- Interrupt callback은 GPIO ISR 문맥에서 실행되므로 blocking API, heap, mutex와 일반 logging을
  호출하지 않는다.
- Callback은 atomic flag나 queue로 데이터를 넘기고 긴 처리는 thread에서 수행한다.
- `noInterrupts()`/`interrupts()`는 호출 thread가 소유하는 중첩 계약으로 **Arduino GPIO
  callback 전달만** mask한다. Zephyr kernel tick, BLE, UART와 다른 driver IRQ는 중지하지 않는다.
- 마지막 `interrupts()`가 복원될 때 이미 assert된 level은 raw 상태 확인과 재무장을 거쳐 한 번
  전달한다. 짝이 없는 복원과 다른 thread의 복원은 진단 오류로 거부한다.

## 9. 검증과 증거

현재 계약은 source/host 검사, NU54DK target build와 실제 신규 pin HIL을 완료했다. 이 설계
문서에는 실행별 pin 번호, 횟수와 로그를 복제하지 않는다.

- [M3 GPIO·시간·Scheduler 기준선](<../04_검증 기록/03_M3_GPIO_시간과_Scheduler_기준선.md>)
- [M6 기본 Arduino API·Serial·interrupt 기준선](<../04_검증 기록/06_M6_기본_Arduino_API_Serial과_인터럽트_기준선.md>)
- [M7 Wire·SPI·ADC·PWM 기준선](<../04_검증 기록/07_M7_Wire_SPI_ADC_PWM_기준선.md>)
- [M14 Core API와 Variant 기준선](<../04_검증 기록/16_M14_Core_API와_Variant_기준선.md>)
- [AC-01 GPIO 호환성 검증 절차와 구현 기록](<../04_검증 기록/22_AC-01_GPIO_호환성_검증.md>)

M14의 신규 LED/button 출력·입력·edge HIL은 완료 상태다. 향후 alias나 ownership을 바꾸면
M14 계약과 동일한 host, target, HIL 계층을 다시 통과해야 한다.

AC-01은 exact commit `ac10ba3b253bd6bf76bcf73aa2c79278304908a4`에서 P2.5↔P2.6 GPIO
loopback/open-drain/pulse HIL과 SW0 P1.13 GPIOTE level/mask HIL을 모두 통과했다. P2.5/P2.6은
digital GPIO로 검증됐지만 interrupt capability는 없으며, 이 차이를 지원 범위로 확대하지 않는다.

## 10. 명시적 범위 밖

- 승인되지 않은 모든 connector를 연속 `D0...Dn`으로 노출하는 범용 pin map
- `PIN_LED1`의 runtime digital/PWM ownership 전환
- Zephyr kernel과 모든 driver IRQ를 실제로 정지하는 전역 IRQ 호환층
- AVR/SAMD식 direct port/register API
