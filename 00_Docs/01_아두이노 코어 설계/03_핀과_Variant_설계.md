# NU54DK Arduino 핀과 Variant 설계

| 항목 | 내용 |
| --- | --- |
| 문서 ID | CORE-PIN-001 |
| 문서 개정 | 4.1 |
| 문서 상태 | `v0.2.0` 정식 계약 + `v0.3.0` AC-02B exact-commit HIL 완료 |
| 최종 갱신일 | 2026-09-01 |
| 대상 보드 | `nrf54l15dk/nrf54l15/cpuapp/nu54dk` |

## 1. 목적

이 문서는 NU54DK의 Devicetree 자원을 Arduino 논리 핀으로 노출하는 현재 계약을 정의한다.
물리 GPIO 번호, pinctrl과 전기적 특성은 보드 패키지가 소유한다. Core-owned DTS는 그 보드
자원을 Arduino용 capability·policy·route metadata로 투영하고 Variant는 공개 이름과 안정된 논리
ID를 제공한다.

정식 `v0.2.0` package의 10/7 sparse-pin 계약은 역사적 공개 계약으로 유지한다. 현재 `v0.3.0`
개발 트리는 기존 `0..11` ID를 보존하면서 module/header의 나머지 물리 pad에 canonical ID
`12..31`을 부여한다. 기본 `standard`/`ble` profile의 불변식은 32개 논리 역할, 31개 실제 pad,
20개 digital-capable canonical pad와 8개 analog channel이다. ID 4 `PIN_LED1`은 P1.10의 ID 3
`PIN_PWM0`으로 정규화되므로 논리 역할 수와 실제 pad 수가 하나 다르다.

P0.0~P0.3 DAP UART GPIO와 P1.0~P1.1 LFXO GPIO는 각각 opt-in Kconfig에서만 일반 digital
capability를 얻는다. 이름이나 `pin < NUM_DIGITAL_PINS`만으로 GPIO·interrupt·ADC·peripheral
사용 가능성을 판정하지 않고 DTS metadata와 현재 runtime owner를 함께 검사한다.

## 2. 단일 원본과 책임

| 정보 | 단일 원본 |
| --- | --- |
| 보드 기본 GPIO controller, 실제 pin, flag, pinctrl | `board_package/NU54DK_Zephyr_DTS` |
| Arduino physical pad와 capability·policy·route metadata | `dts/nucode/nu54dk-arduino-pins.dtsi` |
| Arduino 이름과 논리 ID | `variants/nu54dk/variant.h` |
| 31개 DTS node와 canonical ID 연결 | `variants/nu54dk/digital_pins.inc` |
| immutable pin descriptor 생성 | `variants/nu54dk/variant.cpp` |
| UART20 부팅 고정 자원 registry | `variants/nu54dk/io_resource_registry.cpp` |
| 공통 descriptor·오류 형식 | `cores/arduino/internal/pin_description.h` |
| 동적 핀·주변장치 소유권 상태 | `cores/arduino/internal/IoResourceManager.h` |
| runtime pinctrl·PM·GPIO handover | `RuntimePeripheralRoute`, `PinHandover` |
| GPIO·시간·interrupt 동작 | `cores/arduino/wiring_*.cpp` |

Variant C++에는 `P1.x`, `P2.x` 같은 물리 pin 번호를 복제하지 않는다. Board 기본 회로와 역할은
보드 패키지가 소유하고, Core DTS는 Arduino 관점의 31-pad metadata만 추가한다. Variant는 생성된
Devicetree node를 소비한다.

## 3. canonical 논리 핀 모델

| ID | 공개 이름 | 실제 pad | 현재 capability·정책 |
| ---: | --- | --- | --- |
| 0 | `LED_BUILTIN`, `PIN_LED0`, `D0` | P2.9 | input/output, interrupt 없음 |
| 1 | `PIN_BUTTON0`, `D1`, `A6` | P1.13 | input/interrupt/AIN6, 버튼 회로 부하 |
| 2 | `PIN_A0`, `A0` | P1.12 | input/output/interrupt/open-drain/AIN5/PWM, transferable |
| 3 | `PIN_PWM0`, `PIN_PWM_LED` | P1.10 | input/output/interrupt/open-drain/PWM, transferable |
| 4 | `PIN_LED1` | P1.10 | ID 3으로 정규화되는 legacy alias |
| 5 | `PIN_LED2` | P2.7 | input/output, interrupt 없음 |
| 6 | `PIN_LED3`, `A7` | P1.14 | input/output/interrupt/open-drain/AIN7/PWM, LED 부하 |
| 7 | `PIN_BUTTON1` | P1.9 | input/interrupt 전용 |
| 8 | `PIN_BUTTON2` | P1.8 | input/interrupt 전용 |
| 9 | `PIN_BUTTON3` | P0.4 | input/interrupt 전용 |
| 10 | `PIN_GPIO0`, `D10` | P2.5 | input/output/open-drain, interrupt 없음 |
| 11 | `PIN_GPIO1`, `D11` | P2.6 | input/output/open-drain, interrupt 없음 |

ID 12~31의 physical 이름과 기본 정책은 다음과 같다.

| Canonical 범위 | 기본 정책 |
| --- | --- |
| P0.0~P0.3 | UART30 route 사용 가능; 일반 GPIO는 DAP UART opt-in에서만 공개 |
| P1.0~P1.1 | LFXO 조건부 GPIO/PWM |
| P1.2~P1.3 | GPIO와 I2C22/PWM 사이 transferable |
| P1.4~P1.7 | AIN0~3 metadata는 존재하지만 UART20 system-reserved |
| P1.11 | AIN4/PMIC system input, output·peripheral 강제 claim 금지 |
| P2.0/P2.3 | 일반 input/output/open-drain GPIO |
| P2.1/P2.2/P2.4 | GPIO 또는 SPI00 exact signal route |
| P2.8 | system input-only |
| P2.10 | system-reserved, 공개 capability 없음 |

공개 상수는 다음 불변식을 유지한다.

```text
standard/ble 기본 profile:
NUM_PIN_ROLES             = 32
NUM_DIGITAL_PINS          = 32
NUM_PHYSICAL_PINS         = 31
NUM_DIGITAL_CAPABLE_PINS  = 20
NUM_ANALOG_INPUTS         = 8
NUM_ANALOG_OUTPUTS        = 1

조건부 GPIO:
CONFIG_NUCODE_ARDUINO_DAP_UART_GPIO_PINS=y  -> digital-capable +4
CONFIG_NUCODE_ARDUINO_LFXO_GPIO_PINS=y      -> digital-capable +2
```

`digitalPinIsValid()`는 legacy alias를 canonical ID로 정규화한 뒤 profile capability를 검사한다.
`digitalPinToInterrupt()`는 P0/P1의 interrupt-capable canonical pin만 같은 ID로 반환한다. 모든 P2
pin과 system-reserved·범위 밖 ID에는 `NOT_AN_INTERRUPT`를 반환한다. 내부
`pinDescriptionCount()`는 실제 pad descriptor 31개를 반환하며 digital-capable 수와 같지 않다.

## 4. Variant 구현 계약

### 4.1 `variant.h`

- 공개 핀 상수와 개수 상수를 제공한다.
- C와 C++에서 `A0`, `digitalPinIsValid()`와 `digitalPinToInterrupt()`를 사용할 수 있게 한다.
- 인수는 한 번만 평가한다.
- 실제 GPIO controller나 물리 pin 번호를 포함하지 않는다.

### 4.2 `digital_pins.inc`

X-macro 입력으로 Core-owned DTS의 31개 physical node와 canonical 논리 ID 관계를 선언한다.
ID 4 legacy alias는 별도 descriptor를 만들지 않고 ID 3으로 정규화한다.

### 4.3 `variant.cpp`

- DTS에서 `gpio_dt_spec`, capability, policy, ownership, route와 analog channel metadata를 생성한다.
- canonical ID와 descriptor를 함께 저장해 배열 index와 논리 ID를 혼동하지 않는다.
- 조건부 DAP UART/LFXO capability는 profile opt-in 전에는 fail-closed로 제거한다.
- DTS GPIO controller가 P0/P1일 때만 interrupt capability를 유지하고 GPIOTE가 없는 P2에는
  interrupt를 부여하지 않는다.
- lookup 범위를 벗어나거나 요청 capability가 없으면 안전한 실패를 반환한다.
- heap, runtime pin 번호 복제와 가변 mapping을 사용하지 않는다.

## 5. Digital API 의미

| 항목 | 계약 |
| --- | --- |
| `pinMode()` | capability·policy·owner 확인 뒤 `INPUT`, pull 입력, `OUTPUT` 또는 지원 pin의 `OUTPUT_OPENDRAIN` 적용 |
| `digitalWrite()` | output capability와 push-pull/open-drain output 상태가 있는 핀에 raw `HIGH`/`LOW` 기록 |
| `digitalRead()` | 실제 electrical level을 raw `HIGH`/`LOW`로 반환 |
| LED polarity | GPIO flag는 DTS가 소유하지만 `digitalWrite(HIGH)`는 raw high 의미를 유지 |
| 버튼 | Core debounce나 active-low 논리 반전을 제공하지 않음 |
| interrupt | GPIOTE가 있는 P0/P1 역할에서 raw edge와 one-shot/rearm level 지원; 모든 P2 pin은 미지원 |

`PIN_A0`는 digital input/output/open-drain과 ADC/PWM handover를, `PIN_PWM0`/`PIN_LED1`은 같은
P1.10 canonical pad의 digital/PWM handover를 지원한다. 버튼·system input은 output을 거부하고 P2.10과 UART20 system-reserved pad는
일반 digital API가 강제로 탈취하지 않는다.

## 6. 정적 역할과 동적 소유권

Variant의 capability는 어떤 기능이 가능한지를 설명하는 정적 metadata다. 현재 누가 pad나
peripheral block을 사용 중인지는 AC-02A의 내부 `IoResourceManager`가 별도로 관리한다. 둘을
합쳐서 해석하거나 Variant 배열을 runtime 상태 저장소로 사용하지 않는다.

관리자는 heap을 사용하지 않는 고정 슬롯 표이며 다음 계약을 가진다.

- 자원은 `kind + domain + index`로 식별한다. GPIO는 controller device와 controller 내부 pin을
  결합하므로 서로 다른 Arduino 별칭이 같은 pad를 가리키면 같은 자원으로 충돌한다.
- owner는 `gpio`, `adc`, `pwm`, `wire`, `spi`, `serial`, `system`과 instance로 식별한다.
- 최대 8개 자원을 한 lease에서 `reserve → commit`하거나 driver 실패 시 `rollback`한다. 확정한
  lease는 내부 `release`가 가능하고 batch 전체가 원자적으로 성공하거나 실패한다.
- 64-bit generation과 manager epoch로 복사되거나 오래된 lease가 새 소유권을 변경하지 못하게 한다.
- ISR에서는 조회·소유권 변경을 거부하고 heap·문자열 logging을 사용하지 않는다.

부팅 registry는 UART20 console pad와 serial block만 고정 active owner로 등록한다. UART30,
I2C22, SPI00과 PWM20/21/22는 boot-fixed owner가 아니다. Registry는 실제 driver나 pinctrl 상태를
바꾸지 않고 Core의 충돌 판정만 초기화한다.

`pinMode()`는 GPIO 자원을 먼저 reserve하고 driver 구성이 성공하면 commit한다. Driver 실패 시
rollback하며 `digitalRead()`와 `digitalWrite()`는 해당 pad의 active GPIO ownership을 확인한다.
다른 고정 owner의 pad에는 `ownership-conflict`를 기록하고 hardware를 변경하지 않는다.

### 6.1 Runtime handover와 제한

AC-02B의 `PinHandover`와 `RuntimePeripheralRoute`는 종료 상태에서 선택한 route를 검증하고,
`begin()`에서 기존 GPIO mode·latch·interrupt를 snapshot한 뒤 pad와 peripheral block을 원자적으로
peripheral owner로 전환한다. `end()`는 driver와 runtime PM을 정리하고 이전 GPIO 상태를 복원한다.
전환 또는 복원 실패는 rollback 또는 fault latch로 fail-closed한다.

- `Serial1`은 UART30의 승인된 P0 route, `Wire`는 I2C22의 승인된 P1 route를 사용한다.
- SPI00은 SoC signal matrix에 맞는 P2.1/P2.2/P2.4 exact route만 허용한다.
- `analogRead()`는 ADC block과 허용 pad를 한 번의 read 동안 transient 소유하고 GPIO input을 복원한다.
- `analogWrite()`, `tone()`과 `Servo`는 PWM20/21/22를 분리하고 GPIO↔PWM ownership을 전환한다.
- nRF54L15 CPUAPP의 GPIOTE20/30은 P1/P0에만 연결되므로 모든 P2 pin은 interrupt 미지원이다.
- P1.4~P1.7 UART20, P1.11 system input과 P2.10 system pad를 일반 API가 강제로 탈취하지 않는다.
- 전체 header를 연속 `Dn`으로 추정하지 않는다. Physical 이름은 `PIN_Px_yy`, 기존 Arduino 별칭은
  `D0`, `D1`, `D10`, `D11`, `A0..A7`처럼 명시적으로 제공한다.

Runtime pinctrl·PM lifecycle과 GPIO↔Serial1/Wire/SPI/ADC/PWM handover는 구현됐고 exact commit
`0b7f89283cd82a68a7f3f0910f4fc59b8dd01bfb`의 3-wire physical HIL을 통과했다. 이 결과는 승인된
route의 AC-02B 완료이며 SoC matrix 밖의 임의 peripheral 전환까지 지원한다는 뜻은 아니다.

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

현재 canonical mapping은 source/host 검사와 NU54DK target build를 통과했다. AC-01 GPIO HIL과
AC-02B 주변장치 handover의 exact 3-wire HIL도 완료됐다. Wire는 DUT 온보드 BQ25186 read-only
경로를 사용하며 cross-board P1.2/P1.3은 continuity 불연속으로 fixture에서 제외한다. 공유
P2.5↔P1.12 선은 ADC 구동 뒤 A0/P1.12 PWM polling capture에 재사용한다. 이 설계 문서에는 실행별
횟수와 로그를 복제하지 않는다.

- [M3 GPIO·시간·Scheduler 기준선](<../04_검증 기록/03_M3_GPIO_시간과_Scheduler_기준선.md>)
- [M6 기본 Arduino API·Serial·interrupt 기준선](<../04_검증 기록/06_M6_기본_Arduino_API_Serial과_인터럽트_기준선.md>)
- [M7 Wire·SPI·ADC·PWM 기준선](<../04_검증 기록/07_M7_Wire_SPI_ADC_PWM_기준선.md>)
- [M14 Core API와 Variant 기준선](<../04_검증 기록/16_M14_Core_API와_Variant_기준선.md>)
- [AC-01 GPIO 호환성 검증 절차와 구현 기록](<../04_검증 기록/22_AC-01_GPIO_호환성_검증.md>)
- [AC-02A 핀과 주변장치 소유권 기준선](<../04_검증 기록/26_AC-02A_핀과_주변장치_소유권_기준선.md>)
- [AC-02B Peripheral/Analog runtime 기준선](<../04_검증 기록/27_AC-02B_Peripheral_Analog_runtime_기준선.md>)

M14의 신규 LED/button 출력·입력·edge HIL은 완료 상태다. 향후 alias나 ownership을 바꾸면
M14 계약과 동일한 host, target, HIL 계층을 다시 통과해야 한다.

AC-01은 exact commit `ac10ba3b253bd6bf76bcf73aa2c79278304908a4`에서 P2.5↔P2.6 GPIO
loopback/open-drain/pulse HIL과 SW0 P1.13 GPIOTE level/mask HIL을 모두 통과했다. P2.5/P2.6은
digital GPIO로 검증됐지만 interrupt capability는 없으며, 이 차이를 지원 범위로 확대하지 않는다.

## 10. 명시적 범위 밖

- 승인되지 않은 모든 connector를 연속 `D0...Dn`으로 노출하는 범용 pin map
- SoC signal matrix와 DTS route를 무시하는 임의 peripheral remap
- Wire target/slave·`Wire1`, `SPI1`과 자동 chip-select
- Zephyr kernel과 모든 driver IRQ를 실제로 정지하는 전역 IRQ 호환층
- AVR/SAMD식 direct port/register API
