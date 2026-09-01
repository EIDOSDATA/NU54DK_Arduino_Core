# NU54DK Arduino GPIO와 시간 API 설계

| 항목 | 내용 |
| --- | --- |
| 문서 ID | FW-GPIO-TIME-001 |
| 문서 개정 | 4.0 |
| 문서 상태 | `v0.2.0` 정식 계약 + `v0.3.0` AC-02B GPIO handover 자동 구현·host/target build PASS, 물리 HIL 배선 대기 |
| 최종 갱신일 | 2026-09-01 |
| 기준 | NCS v3.4.0 / Zephyr 4.4.0 |

## 1. 목적

이 문서는 digital GPIO, external interrupt와 Arduino 시간 API의 현재 동작을 정의한다. 논리
핀 이름과 sparse ID는 [핀과 Variant 설계](<../01_아두이노 코어 설계/03_핀과_Variant_설계.md>)가
소유하고, 실행별 측정값과 로그는 `04_검증 기록`이 소유한다.

## 2. 단일 원본과 구성요소

| 정보/기능 | 소유자 |
| --- | --- |
| 물리 GPIO, polarity, pull과 pinctrl | `board_package/NU54DK_Zephyr_DTS` |
| 논리 ID·capability | `variants/nu54dk` |
| 물리 pad·peripheral block의 동적 소유권 | `cores/arduino/internal/IoResourceManager.h` |
| `pinMode`, digital read/write | `cores/arduino/wiring_digital.cpp` |
| interrupt slot과 callback | `cores/arduino/wiring_interrupt.cpp` |
| Arduino 시간 API | `cores/arduino/wiring_time.cpp` |
| nRF54 high-resolution time backend | `cores/arduino/internal/time_backend_nrf54.cpp` |

Core는 물리 pin 번호, timer instance와 DTS flag를 별도 원본으로 복제하지 않는다.

## 3. Canonical digital 핀 계약

정식 `v0.2.0` package의 10/7 sparse-pin 계약은 역사적 공개 계약으로 유지한다. 현재
`v0.3.0` 개발 트리는 module/header의 31개 physical pad를 32개 안정된 논리 역할로 표현한다.
`PIN_LED1` ID 4는 P1.10의 canonical ID `PIN_PWM0`으로 정규화되므로 논리 역할 수와 실제 pad
수가 하나 다르다.

```text
NUM_PIN_ROLES             = 32
NUM_DIGITAL_PINS          = 32
NUM_PHYSICAL_PINS         = 31
NUM_DIGITAL_CAPABLE_PINS  = 20  # 기본 standard/ble profile의 canonical pad 수
NUM_ANALOG_INPUTS         = 8
NUM_ANALOG_OUTPUTS        = 1
```

P0.0~P0.3과 P1.0~P1.1은 각각 DAP UART와 LFXO opt-in 정책에 따라 digital capability가 4개와
2개씩 추가된다. System-reserved, input-only와 transferable pin은 이름 존재 여부가 아니라 DTS
metadata의 capability, policy, route와 현재 runtime owner를 함께 검사한다. A0/P1.12는 digital
input과 ADC, P1.10은 digital output과 PWM을 같은 canonical pad에서 안전하게 전환한다.

P2 pad는 capability가 허용하는 input/output/open-drain GPIO로 사용할 수 있지만 CPUAPP GPIOTE
경로가 없다. 따라서 P2의 `digitalPinToInterrupt()`는 항상 `NOT_AN_INTERRUPT`를 반환한다.

## 4. GPIO 값과 mode

Arduino `HIGH`와 `LOW`는 raw electrical level이다. LED의 DTS active flag가 존재하더라도 Core가
`digitalWrite(HIGH)`를 “LED 켜기” 의미로 반전하지 않는다. Sketch는 board 역할의 polarity를
알고 값을 선택해야 한다.

| Arduino mode | `v0.2.0` 정식 | `v0.3.0` 개발 트리 |
| --- | --- | --- |
| `INPUT` | input 구성 | 동일 |
| `INPUT_PULLUP` | input + pull-up | 동일 |
| `INPUT_PULLDOWN` | input + pull-down | 동일 |
| `OUTPUT` | 마지막 output latch를 초기값으로 사용해 output 구성 | 동일 |
| `OUTPUT_OPENDRAIN` | 미지원, hardware 변경 없이 오류 기록 | output과 open-drain capability를 모두 가진 공개 pin에서 지원; `HIGH`는 high-Z release |

버튼 역할은 input/interrupt capability만 가지므로 output mode를 거부한다. LED 역할은
input/output capability를 가지며, 그중 DTS controller가 P0/P1인 역할만 interrupt를 가진다.

## 5. `pinMode()`, `digitalWrite()`, `digitalRead()`

### 5.1 `pinMode()`

1. thread 문맥인지 확인하고 GPIO·interrupt 공통 전환 mutex를 획득한다.
2. sparse descriptor와 요청 capability를 확인한다.
3. Zephyr GPIO device readiness를 확인한다.
4. GPIO pad를 고정 슬롯 소유권 manager에서 reserve한다.
5. 기존 interrupt slot을 안전하게 해제한다.
6. Arduino mode를 Zephyr flag로 변환해 구성한다.
7. 성공하면 소유권 lease를 commit하고 mode·output latch를 atomic 상태에 기록한다.
8. Interrupt 해제 또는 driver 구성이 실패하면 lease를 rollback하고 논리 mode를
   `unconfigured`로 바꿔 callback과 mode가 어긋나지 않는 fail-closed 상태로 둔다.

### 5.2 `digitalWrite()`

- `OUTPUT` 또는 지원되는 `OUTPUT_OPENDRAIN`으로 구성된 output-capable 핀에서만 값을 기록한다.
- input pin의 pull-up/down을 `digitalWrite()`로 전환하는 AVR식 의미는 제공하지 않는다.
- 잘못된 값, 미구성 pin과 ownership 불일치는 no-op과 진단으로 처리한다.
- 성공 경로는 heap과 문자열 logging을 사용하지 않는다. 상태 전환은 고정 슬롯 manager와
  GPIO 전환 mutex로 직렬화한다.
- 현재 pad가 active GPIO owner인지 확인하며 dynamic peripheral 또는 system owner가 가진 pad를
  덮어쓰지 않는다.

### 5.3 `digitalRead()`

- digital-capable descriptor에서 raw level을 읽는다.
- 현재 pad가 active GPIO owner인지 확인한다.
- input과 output readback을 허용한다.
- 오류나 금지 문맥에서는 `LOW`를 반환하고 진단을 기록한다.
- active-low 버튼을 누름/해제 의미로 반전하지 않는다.

## 6. External interrupt

| 항목 | 계약 |
| --- | --- |
| 등록 | `attachInterrupt()` 또는 `attachInterruptParam()` |
| 해제 | `detachInterrupt()` |
| mode | raw `RISING`, `FALLING`, `CHANGE`; v0.3 개발 트리는 GPIOTE P0/P1에서 `LOW`, `HIGH` 추가 |
| slot | digital 논리 ID별 고정 slot |
| callback 문맥 | Zephyr GPIO ISR |
| level interrupt | `v0.2.0` 미지원; v0.3은 hold one-shot 후 deassert·work polling 재무장 |

등록 전에 input-capable descriptor, mode, callback과 device readiness를 검사한다. Callback을
바꾸거나 해제할 때 진행 중 ISR과 slot 상태를 안전하게 정리한다. `pinMode()`로 GPIO 구성을
바꾸면 기존 interrupt ownership을 해제한다. `pinMode()`, attach/detach와 전체 callback mask는
같은 전환 mutex를 먼저 획득한 뒤 소유권 snapshot과 interrupt 설정을 처리하므로, 다른 thread의
mode 전환 뒤 오래된 input 판정을 사용해 interrupt를 다시 등록할 수 없다.

Callback에서는 blocking I/O, heap, mutex, sleep과 일반 logging을 호출하지 않는다. Atomic
flag 또는 queue로 데이터를 넘겨 Sketch thread에서 처리한다.

`v0.3.0`의 `noInterrupts()`/`interrupts()`는 호출 thread가 소유하는 중첩 mask이며 Arduino GPIO
callback 전달만 지연한다. Zephyr kernel tick, BLE, UART와 다른 driver IRQ를 정지하지 않는다.
마지막 복원 때 이미 assert된 level은 raw 상태를 확인해 한 번 전달하고 다시 무장한다.

## 7. 시간 API

### 7.1 `millis()`

Zephyr uptime을 Arduino `unsigned long` millisecond 값으로 반환한다. Arduino type의 자연스러운
wrap 의미를 따르며 Core가 별도 epoch나 wall clock을 제공하지 않는다.

### 7.2 `micros()`

nRF54 GRTC cycle을 64-bit 정수 연산으로 microsecond로 변환하고, system clock 초기화 때 latch한
GRTC startup offset을 뺀다. Arduino Runtime 객체를 시작한 시점을 새 epoch로 만드는 방식은 아니다.
반환형은 Arduino `unsigned long`이므로 공개 값은 해당 형식의 wrap 의미를 따른다.

이 값은 정밀 계측기나 RTC가 아니다. External clock 정확도, 장기 drift와 모든 power state
전후의 연속성은 별도 hardware 검증 없이는 보증하지 않는다.

### 7.3 `delay(ms)`

- yield 가능한 thread 문맥에서만 동작한다.
- 64-bit deadline을 사용하고 Zephyr sleep으로 current thread만 block한다.
- interrupt, timer와 다른 ready thread는 scheduler 정책에 따라 계속 실행된다.
- ISR, pre-kernel, idle 또는 interrupt-locked 문맥에서는 no-op한다.

### 7.4 `delayMicroseconds(us)`

Thread 문맥의 busy wait다. 긴 요청은 backend가 안전한 단위로 나눠 처리하지만 CPU를 양보하는
API는 아니다. ISR에서는 공개 계약상 no-op한다.

### 7.5 `yield()`

Yield 가능한 thread 문맥에서 `k_yield()`를 호출한다. `yield()`는 power management 진입이나
고정 1 ms sleep을 뜻하지 않는다. `loop()`의 기본 한-tick sleep은 Runtime Kconfig의 별도
post-loop 정책이다.

### 7.6 `pulseIn*`와 `shiftIn/Out`

정식 `v0.2.0`에는 이 API가 없다. `v0.3.0` AC-01은 thread 전용 `pulseIn()`, cooperative
`pulseInLong()`과 8-bit `shiftIn()`/`shiftOut()`을 추가했다. Pulse API는 64-bit cycle deadline을
사용하고 timeout에서 `0`을 반환한다. 측정 전체에서 GPIO 전환 mutex를 유지하므로 다른 thread의
`pinMode()`가 검증을 마친 input을 중간에 바꾸지 못한다. Shift API는 `MSBFIRST`/`LSBFIRST`를
지원하지만 SPI 대체나 고속 timing을 보증하지 않는다.

## 8. 실행 문맥

| API | Thread | ISR |
| --- | --- | --- |
| `pinMode()` | 허용 | 거부/no-op |
| `digitalWrite()` | 허용 | 거부/no-op |
| `digitalRead()` | 허용 | `LOW`와 진단 |
| attach/detach interrupt | 허용 | 거부 |
| interrupt callback | 해당 없음 | 실행 |
| `millis()`, `micros()` | 허용 | 허용 |
| `delay()`, `yield()` | 허용 | no-op |
| `delayMicroseconds()` | 허용 | no-op |

## 9. 오류와 진단

GPIO backend는 invalid context/pin/mode/value, unsupported capability, device readiness,
configuration, interrupt와 driver 오류를 atomic 상태로 보존한다. 공개 Sketch는 다음 API로
안정된 projection을 조회한다.

```cpp
auto diagnostic = nucode::arduino::lastDiagnostic(
    nucode::arduino::DiagnosticSubsystem::gpio);
```

공개 code와 원래 driver errno는 `<nucode/Diagnostics.h>` 계약을 따른다. Internal
`lastGpioError()` 계열은 Core 구현용이며 Sketch 공개 API가 아니다.

Time backend에는 별도 마지막 오류 저장소가 없다. 따라서
`lastDiagnostic(DiagnosticSubsystem::time)`은 현재 `unsupported`를 반환한다. 금지 문맥의
`delay()`, `delayMicroseconds()`와 `yield()`는 안전하게 no-op하지만 시간 오류 이력을 만들지
않는다.

## 10. 설정

| 설정 | 역할 |
| --- | --- |
| `CONFIG_NUCODE_ARDUINO_GPIO` | digital GPIO backend |
| `CONFIG_NUCODE_ARDUINO_IO_OWNERSHIP` | 고정 슬롯 I/O 소유권 manager와 부팅 자원 registry |
| `CONFIG_NUCODE_ARDUINO_INTERRUPTS` | raw edge interrupt backend |
| `CONFIG_NUCODE_ARDUINO_TIME` | Arduino 시간 API |
| `CONFIG_NUCODE_ARDUINO_CONNECTOR_GPIO` | v0.2.x prj.conf 호환 표식; 현재 canonical map의 P2.5/P2.6 descriptor는 이 값과 관계없이 항상 존재 |
| `CONFIG_NUCODE_ARDUINO_DAP_UART_GPIO_PINS` | DAP UART 조립 경계를 승인하고 P0.0~P0.3 일반 GPIO capability 활성화 |
| `CONFIG_NUCODE_ARDUINO_LFXO_GPIO_PINS` | LFXO 조립 경계를 승인하고 P1.0~P1.1 일반 GPIO/PWM capability 활성화 |
| Runtime loop choice | `loop()` 뒤 sleep/yield/none 정책 |

별도 physical pin이나 timer 번호를 Kconfig로 다시 입력하지 않는다.

## 11. 검증과 증거

- [M3 GPIO·시간·Scheduler 기준선](<../04_검증 기록/03_M3_GPIO_시간과_Scheduler_기준선.md>)
- [M6 기본 Arduino API·Serial·interrupt 기준선](<../04_검증 기록/06_M6_기본_Arduino_API_Serial과_인터럽트_기준선.md>)
- [M14 Core API와 Variant 기준선](<../04_검증 기록/16_M14_Core_API와_Variant_기준선.md>)
- [AC-01 GPIO 호환성 검증](<../04_검증 기록/22_AC-01_GPIO_호환성_검증.md>)
- [AC-02A 핀과 주변장치 소유권 기준선](<../04_검증 기록/26_AC-02A_핀과_주변장치_소유권_기준선.md>)
- [AC-02B Peripheral/Analog runtime 기준선](<../04_검증 기록/27_AC-02B_Peripheral_Analog_runtime_기준선.md>)

M14의 추가 LED/button output/readback, pull-up과 edge HIL은 완료됐다. 실행별 횟수, 시간 수치,
trace와 commit은 위 검증 문서가 소유한다.

AC-01은 exact commit `ac10ba3b253bd6bf76bcf73aa2c79278304908a4`에서 P2.5↔P2.6
loopback/open-drain/pulse·shift와 SW0 level/mask 실기까지 통과했다.

## 12. 명시적 범위 밖

- input `digitalWrite()`에 의한 pull 전환
- 정식 `v0.2.0`의 open-drain, level interrupt, pulse/shift와 interrupt mask API
- P2.5/P2.6 connector interrupt
- open-drain 외부 pull-up의 전기 품질·상승시간 보증
- Core debounce
- Zephyr kernel과 모든 driver IRQ를 정지하는 실제 전역 IRQ API
- external time 정확도·장기 drift 보증
- wall clock, calendar와 alarm API
