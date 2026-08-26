# NU54DK Arduino GPIO와 시간 API 설계

| 항목 | 내용 |
| --- | --- |
| 문서 상태 | 설계·구현 동기화 — M6 조건부 완료 기준 |
| 작성자 | Quantum / NUCODE |
| 기준 SDK | nRF Connect SDK v3.4.0 |
| 기준 RTOS | Zephyr v4.4.0 |
| 기준 타깃 | `nrf54l15dk/nrf54l15/cpuapp/nu54dk` |
| GPIO 기반 | Zephyr GPIO API |
| 시간 기반 | Zephyr kernel uptime, cycle counter 및 busy wait |

---

## 1. 목적

이 문서는 Arduino digital GPIO, external interrupt 및 시간 API를 Zephyr 위에 구현하는 규칙을 정의한다. 대상 API는 다음과 같다.

- `pinMode()`
- `digitalWrite()`
- `digitalRead()`
- `attachInterrupt()`
- `detachInterrupt()`
- `millis()`
- `micros()`
- `delay()`
- `delayMicroseconds()`
- `yield()`

목표는 Arduino의 관례를 유지하면서도 Zephyr의 device, scheduler 및 ISR 규칙을
위반하지 않는 것이다. M3에서 구현한 digital GPIO·시간 API와 M6에서 구현한 external
edge interrupt를 현재 동작으로 명시한다. 전체 핀맵, 범용 pin ownership과 level
interrupt는 향후 목표로 구분한다.

---

## 2. 단일 원본 원칙

### 2.1 GPIO 자원

물리 GPIO 정보의 원본은 다음 경로다.

~~~text
board_package/NU54DK_Zephyr_DTS
~~~

이 보드 패키지가 다음을 소유한다.

- GPIO controller와 pin 번호
- LED와 버튼 polarity
- pull 설정
- peripheral pinctrl
- node status와 alias

Core는 Variant descriptor를 통해 생성된 `gpio_dt_spec` 또는 동등 정보를 소비한다. Core 소스에 `P0.x`, `P1.x`, `P2.x`를 직접 기록하지 않는다.

### 2.2 논리 핀

Arduino 논리 순서는 `variants/nu54dk`가 소유한다. M3 Variant는 다음 두 연결만 제공한다.

~~~text
LED_BUILTIN → DT_ALIAS(led0)
PIN_BUTTON0 → DT_ALIAS(sw0)
NUM_DIGITAL_PINS = 2
~~~

전체 논리 핀 정책은 [핀과 Variant 설계](../01_아두이노%20코어%20설계/03_핀과_Variant_설계.md)를 따른다.

### 2.3 시간

시간의 원본은 Zephyr kernel timebase다. Core가 별도 SysTick, GRTC 또는 TIMER register를 직접 구성하지 않는다.

| Arduino API | Zephyr 원본안 |
| --- | --- |
| `millis()` | `k_uptime_get_32()` |
| `micros()` | GRTC startup offset을 뺀 `k_cycle_get_64()`와 `k_cyc_to_us_floor64()` |
| `delay()` | `k_can_yield()` 검사와 deadline 기반 `k_msleep()` 반복 |
| `delayMicroseconds()` | ISR 검사와 안전한 크기로 나눈 `k_busy_wait()` |
| `yield()` | `k_can_yield()` 검사 후 `k_yield()` |

M3 구성의 `CONFIG_SYS_CLOCK_HW_CYCLES_PER_SEC`는 1 MHz다. 1,000 us 요청에 대한 내부
GRTC 계측은 1,026 us였지만, 실제 최소 resolution, 외부 시간 기준 오차와 저전력 상태의
연속성은 아직 확정하지 않았다.

---

## 3. 구성요소와 책임

### 3.1 `wiring_digital.cpp`

책임:

- logical pin lookup
- mode와 capability 검사
- Arduino GPIO mode를 Zephyr flag로 변환
- raw digital read/write
- pin runtime state 관리
- driver 오류를 Core 오류 정책으로 변환

### 3.2 `wiring_time.cpp`와 nRF54 backend

`wiring_time.cpp`는 ArduinoCore-API의 C linkage signature를 제공하고 비공개 backend로
전달한다. `internal/time_backend_nrf54.cpp`가 다음 실제 정책을 소유한다.

- kernel timebase를 32-bit Arduino 반환형으로 변환
- GRTC startup offset과 rollover 의미 처리
- millisecond sleep과 microsecond busy wait 구현
- yield 가능 문맥과 ISR 문맥 검사

### 3.3 `wiring_interrupt.cpp`

M6는 GPIO interrupt를 digital GPIO 구현과 분리한 이 파일에 구현한다.

책임:

- pin별 callback slot 관리
- Arduino interrupt mode를 Zephyr flag로 변환
- Zephyr `gpio_callback` 등록과 해제
- 공통 ISR trampoline에서 사용자 callback 호출

아래 raw edge interrupt 설계는 M6 현재 구현이다. level trigger와 전역 interrupt 제어는
아직 지원 상태가 아니다.

### 3.4 Variant와 내부 pin state

Variant descriptor는 물리 자원을 immutable data로 제공한다. Core는 별도의 runtime
state에 다음 정보를 유지한다.

- 현재 Arduino pin mode
- 성공한 output write의 마지막 raw 값
- 논리 핀별 고정 interrupt callback slot, callback 종류와 parameter
- callback 등록·활성 상태와 진행 중 callback 수

범용 peripheral pin ownership registry는 아직 구현하지 않았다. `pinMode()`가 핀 구성을
바꾸는 경우 같은 논리 핀의 Arduino interrupt는 자동 detach한다.

runtime state에 controller 이름과 물리 pin 번호를 다시 저장해 별도 원본으로 만들지 않는다.

---

## 4. GPIO 값 의미

### 4.1 Arduino `HIGH`와 `LOW`

Arduino digital API에서 다음 의미를 사용한다.

| 값 | 전기적 의미 |
| --- | --- |
| `LOW` | GPIO output 0 또는 읽힌 raw 0 |
| `HIGH` | GPIO output 1 또는 읽힌 raw 1 |

Zephyr `gpio_pin_set_dt()`와 `gpio_pin_get_dt()`는 Devicetree의 `GPIO_ACTIVE_LOW`에 따라 값을 반전할 수 있다. 일반 Arduino digital API는 전기적 High/Low를 요구하므로 다음 raw API를 기본으로 한다.

- `gpio_pin_set_raw()`
- `gpio_pin_get_raw()`

Devicetree polarity는 LED나 버튼이라는 device의 active 의미를 표현할 때 유효하지만, Sketch가 직접 다루는 `digitalWrite(HIGH)`를 “활성”이라는 뜻으로 바꾸지 않는다.

### 4.2 Built-in LED

NU54DK의 `led0`는 Active High이므로 다음 Sketch가 LED를 켠다.

~~~cpp
pinMode(LED_BUILTIN, OUTPUT);
digitalWrite(LED_BUILTIN, HIGH);
~~~

이 동작은 보드 패키지의 현재 회로 정의와 일치한다. 다른 보드에서 Active Low built-in LED를 지원할 때 Arduino `HIGH`의 전기적 의미를 유지할지, LED convenience macro를 추가할지는 별도 cross-board 정책으로 다룬다.

---

## 5. `pinMode()` 설계

### 5.1 Mode 변환

| Arduino mode | 현재 Zephyr 설정 | M3 상태 |
| --- | --- | --- |
| `INPUT` | `GPIO_INPUT` | 구현, 외부 신호 HIL 미완료 |
| `INPUT_PULLUP` | `GPIO_INPUT \| GPIO_PULL_UP` | 구현, 버튼 HIL 확인 |
| `INPUT_PULLDOWN` | `GPIO_INPUT \| GPIO_PULL_DOWN` | 구현, 외부 저항 HIL 미완료 |
| `OUTPUT` | `GPIO_OUTPUT_HIGH/LOW` | 구현, 저장된 output latch 적용 |
| `OUTPUT_OPENDRAIN` | 미구현, 요청 거부 | capability와 driver 지원 필요 |

지원하지 않는 mode는 임의의 다른 mode로 바꾸지 않는다.

### 5.2 Output latch

M3는 logical pin별 마지막으로 성공한 output 값을 유지한다.

~~~text
pinMode(pin, OUTPUT)
    ↓ 초기 output latch 0을 적용

digitalWrite(pin, HIGH)
    ↓ raw write 성공 후 output latch = 1
~~~

input 상태에서 `digitalWrite(HIGH)`로 latch를 미리 설정하는 Arduino 호환 동작은 M3에
없다. 현재는 output mode가 아니면 `wrong_mode`로 동작을 거부한다. 이 호환 동작을
추가하려면 input pull 전환 의미와 함께 별도 시험을 거쳐야 한다.

초기 latch 값은 `LOW`로 정의한다. application overlay가 boot-time pin state를 별도로
요구하면 application이 GPIO 전환 전 peripheral pinctrl을 해제해야 한다. M3 Core는 이
ownership 충돌을 자동 검출하지 않는다.

### 5.3 호출 흐름

~~~text
pinMode(logical_pin, mode)
        ↓
thread 문맥과 논리 핀 범위 검사
        ↓
GPIO device readiness와 Devicetree flag 검사
        ↓
mode와 digital capability 검사
        ↓
같은 논리 핀의 Arduino interrupt 자동 detach
        ↓
mode와 latch를 Zephyr flags로 변환
        ↓
gpio_pin_configure()
        ↓
성공 시 runtime mode 갱신
~~~

driver 호출이 실패하면 이전 mode 상태를 성공한 것으로 기록하지 않는다. M6 target
ztest에서 `pinMode()` 뒤 이전 callback이 실행되지 않는 auto-detach를 확인했다.

---

## 6. `digitalWrite()` 설계

### 6.1 Output pin

output으로 구성된 pin에서는 다음 순서를 사용한다.

1. thread 문맥, logical pin과 capability를 검사한다.
2. 현재 mode가 output인지 확인한다.
3. `gpio_pin_set_raw()`를 호출한다.
4. 성공한 경우에만 output latch를 raw 0 또는 1로 갱신한다.
5. 실패하면 driver 오류를 비공개 Core 상태에 보존한다.

### 6.2 Input pin

Arduino 관례에 따라 input pin에서 `digitalWrite(HIGH)`를 internal pull-up 활성화,
`LOW`를 pull 비활성으로 해석하는 Core도 있다. 아래 표는 향후 호환 목표 후보다.

| 현재 mode | `LOW` | `HIGH` |
| --- | --- | --- |
| `INPUT` | pull 없음 유지 | `INPUT_PULLUP`으로 재구성 |
| `INPUT_PULLUP` | `INPUT`으로 재구성 | 유지 |
| `INPUT_PULLDOWN` | pull-down 유지 | 잘못된 조합으로 진단 후 정책 결정 |

M3는 이 전환을 구현하지 않는다. input pin의 `digitalWrite()`는 `wrong_mode`로 거부하며,
모든 `digitalWrite()` 호출은 ISR에서 no-op된다.

### 6.3 Ownership

PWM, UART, SPI 또는 I2C가 소유한 pin에 `digitalWrite()`를 호출해 peripheral pinctrl을
자동 해제하지 않는다. M3에는 ownership registry와 충돌 진단도 없다. 현재 두 논리 핀은
M3 sample의 GPIO 용도만 검증했으며, 향후 전체 핀맵에서는 application overlay 또는
명시적인 peripheral lifecycle과 ownership 검사가 필요하다.

---

## 7. `digitalRead()` 설계

~~~text
digitalRead(logical_pin)
        ↓
thread 문맥, 범위와 digital input capability 검사
        ↓
구성되지 않은 pin인지 검사
        ↓
GPIO device readiness 검사
        ↓
gpio_pin_get_raw()
        ↓
raw 0 → LOW
raw 1 → HIGH
~~~

Driver가 음수 오류를 반환해도 Arduino API 반환형에는 `LOW`와 `HIGH`만 존재한다. 오류 시 기본 반환값은 `LOW`로 두되, Core 진단 상태에 driver 오류를 보존한다. 오류를 실제 LOW 입력과 구분해야 하는 application은 향후 제공할 상세 오류 API 또는 Zephyr GPIO API를 직접 사용한다.

digital input capability가 있는 Output pin에서 `digitalRead()`는 실제 pin input 값을 읽는다.
output latch를 그대로 돌려주는 방식은 물리 단락을 숨길 수 있으므로 사용하지 않는다.

---

## 8. External interrupt 구현

### 8.1 지원 mode

| Arduino mode | Zephyr flag | M6 상태 |
| --- | --- | --- |
| `RISING` | `GPIO_INT_EDGE_RISING` | 구현, target GPIO emulator PASS |
| `FALLING` | `GPIO_INT_EDGE_FALLING` | 구현, target GPIO emulator PASS |
| `CHANGE` | `GPIO_INT_EDGE_BOTH` | 구현, target GPIO emulator PASS |
| `LOW` | 해당 없음 | 미구현, 요청 거부 |
| `HIGH` | 해당 없음 | 미구현, 요청 거부 |

Level trigger 지원은 nRF54L15 Zephyr GPIO driver와 전력 정책을 HIL로 확인한 뒤 공개한다. 지원하지 않는 trigger를 edge trigger로 조용히 바꾸지 않는다.

### 8.2 Callback table

- pin마다 최대 하나의 Arduino callback을 등록한다.
- 정적 크기 table을 사용하고 ISR 등록 과정에서 heap을 사용하지 않는다.
- `attachInterrupt()`와 parameter를 받는 `attachInterruptParam()`을 제공한다.
- 재등록은 기존 callback을 disable·제거한 뒤 새 callback을 등록한다.
- `detachInterrupt()`는 hardware interrupt를 disable하고 driver callback을 제거한 뒤 slot을 비운다.
- interrupt를 붙이기 전에 해당 논리 핀을 input mode로 구성해야 한다.

### 8.3 호출 흐름

~~~text
GPIO hardware event
      ↓
Zephyr GPIO ISR
      ↓
Core gpio_callback trampoline
      ↓
logical pin callback lookup
      ↓
사용자 Arduino callback
~~~

사용자 callback은 ISR 문맥에서 실행된다. `delay()`, `Serial.write()`, mutex, heap 및 blocking Zephyr API를 호출하면 안 된다.

### 8.4 동시성

`attachInterrupt()`와 `detachInterrupt()`는 thread 문맥 전용이다. configuration mutex와
slot spinlock을 사용하고, detach는 in-flight callback이 끝난 뒤 slot을 비운다. M6 target
ztest에서 재등록, parameter callback, detach 후 무호출, invalid pin/mode/null callback과
`pinMode()` auto-detach를 통과했다.

실제 P1.13 active-low 버튼의 ISR edge는 사용자가 부재하여 아직 누르며 확인하지 못했다.
누름은 raw `FALLING`, 해제는 raw `RISING`으로 확인할 예정이다. 외부 계측 장비는 이
잔여 확인의 필수 조건이 아니다.

---

## 9. 시간 API 설계

### 9.1 `millis()`

현재 구현:

~~~text
return k_uptime_get_32()
~~~

Arduino와 같은 32-bit unsigned rollover 의미를 유지한다. 약 49.7일 후 wrap되는 것은 오류가 아니다. elapsed time 비교는 unsigned subtraction으로 수행해야 한다.

시간의 기준점은 Zephyr kernel uptime 시작 시점이다. 전원 인가 또는 reset edge와 몇 cycle 차이가 날 수 있으므로 절대 timestamp로 사용하지 않는다.

### 9.2 `micros()`

현재 nRF54L15 구현:

~~~text
k_cycle_get_64()
      ↓ GRTC startup value 차감
z_nrf_grtc_timer_startup_value_get()
      ↓
k_cyc_to_us_floor64()
      ↓
lower 32 bit 반환
~~~

현재 특성:

- 별도 heap, mutex 또는 sleep 없이 GRTC counter 조회
- thread와 ISR에서 조회 가능하며 M3 timer ISR에서 실기 확인
- 32-bit Arduino 반환형에 맞춰 약 71.6분마다 wrap
- clock frequency 변환은 Zephyr API에 위임

다음 항목은 아직 확정하지 않는다.

- 실제 최소 resolution
- system sleep 동안의 연속성
- dynamic clock 변경 시 정확도
- `millis()`와 장시간 drift 관계

GRTC는 system clock 초기화 전에 이미 진행할 수 있고 startup에서 0으로 지워지지 않으므로
startup offset 차감이 필요하다. Core 공통 진입점은 register를 직접 읽지 않고 nRF54 전용
backend에서 Zephyr timer API를 사용한다. 이때 사용하는
`z_nrf_grtc_timer_startup_value_get()`는 Zephyr의 internal symbol이므로 NCS/Zephyr를
업그레이드할 때 compile과 기준점 동작을 다시 검증해야 한다.

### 9.3 `delay(ms)`

| 입력/문맥 | 현재 동작 |
| --- | --- |
| `0`, yield 가능한 thread | guarded `k_yield()` |
| `1` 이상, block 가능한 thread | deadline까지 `k_msleep()` 반복 |
| ISR, pre-kernel, idle 또는 IRQ lock 문맥 | 안전한 no-op |

Arduino signature의 `unsigned long`은 target에서 32-bit지만 Zephyr `k_msleep()` 인자는
`int32_t`다. 따라서 최대 `INT32_MAX` ms 단위로 나누고, `k_wakeup()` 등으로 일찍
깨어나면 uptime deadline을 다시 계산해 남은 시간을 재시도한다.

`delay()`는 busy loop가 아니다. API를 호출한 current thread만 sleep하며 Zephyr의 다른
ready thread와 interrupt는 계속 실행된다. 일반 Sketch의 `loop()` 경로에서는 이 current
thread가 Zephyr main thread다.

Scheduler 지연 때문에 실제 복귀 시간이 요청값보다 길 수 있다. 요청 시간보다 일찍 복귀하지 않는 것을 기본 정확도 조건으로 한다.

### 9.4 `delayMicroseconds(us)`

현재 구현은 `k_busy_wait()`를 사용하되 한 번의 호출을 최대 1,000,000 us로 제한한다.
이는 nRF54L busy-wait 하위 구현의 32-bit cycle 계산 overflow를 피하기 위한 내부
분할이며 긴 요청도 sleep으로 자동 전환하지 않는다.

- `0`은 즉시 반환한다.
- scheduler에 CPU를 양보하지 않는다.
- 긴 대기는 전력과 latency를 악화하므로 `delay()` 사용을 권고한다.
- interrupt가 실행되면 실제 지연은 길어질 수 있다.
- Zephyr power management가 busy-wait용 clock을 정지시키는 구성에서는 동작하지 않을 수 있으므로 실제 PM profile마다 검증한다.
- ISR 사용은 v1 공개 계약에서 금지하며 M3 구현은 안전한 no-op로 반환한다.

M3 내부 계측에서 1,000 us 요청은 1,026 us였다. 최소 유효 값, 여러 구간의 오차와
외부 logic analyzer 기준은 아직 측정하지 않았다.

### 9.5 `yield()`

`yield()`는 `k_can_yield()`가 true일 때만 `k_yield()`를 호출한다. 이는 current thread를
같은 priority queue의 뒤로 보내는 동작이며, 낮은 priority thread 실행을 보장하는 sleep이
아니다. 금지 문맥에서는 no-op한다.

`yield()`를 power management 진입이나 1 ms sleep으로 몰래 바꾸지 않는다. loop 최소 sleep은 Runtime Kconfig의 별도 정책으로 다룬다.

### 9.6 M3 시간·scheduler 실측

`runtime_timing`의 최종 trace는 `PASS`, `failure=0`이었다.

| 항목 | 결과 |
| --- | ---: |
| `delay(20)`의 millisecond 경과 | 20 ms |
| `delay(20)`의 microsecond 경과 | 20,084 us |
| `delayMicroseconds(1000)` 경과 | 1,026 us |
| timer ISR의 `millis()`/`micros()` 읽기 | 1,582회 |

400 ms 단계별 공정성 실측에서는 spin과 `yield()`의 idle 비율이 0%, 한 tick sleep이
85.53%, `delay(1)`이 96.71%였다. 전체 loop/worker/timer/workqueue 수치는
[Arduino Runtime 설계](./01_Arduino_Runtime_설계.md#54-loop-공정성-정책)에 기록한다.

이 값은 한 보드·한 firmware 구성의 내부 시간원 측정이다. 외부 clock 정확도,
저전력 진입 전후 연속성과 장시간 drift를 검증한 결과로 확대 해석하지 않는다.

---

## 10. 스레드와 ISR 문맥

| API | Thread | ISR | Blocking | 비고 |
| --- | --- | --- | --- | --- |
| `pinMode` | 허용 | 금지 | driver 의존 | pin 재구성 |
| `digitalWrite` output | 허용 | 금지, no-op | driver 경로 | 사전 output configure 필요 |
| `digitalWrite` input | 현재 거부 | 금지, no-op | 아니요 | pull 전환 미구현 |
| `digitalRead` | 허용 | 금지, `LOW` 반환 | driver 경로 | raw input |
| `attachInterrupt` | 허용 | 금지 | driver 구성 동안 | input 구성 후 raw edge callback 등록 |
| `detachInterrupt` | 허용 | 금지 | in-flight callback 정리 동안 | interrupt disable과 slot 해제 |
| `millis` | 허용 | 허용 | 아니요 | timer ISR 실기 호출 확인 |
| `micros` | 허용 | 허용 | 아니요 | timer ISR 실기 호출 확인 |
| `delay` | 허용 | 금지, no-op | 예 | `k_can_yield()` 검사 |
| `delayMicroseconds` | 허용 | 공개 계약상 금지, no-op | busy wait | 1초 단위 내부 분할 |
| `yield` | 허용 | 금지, no-op | scheduler | `k_can_yield()` 검사 |

`delay()`와 `yield()`는 ISR뿐 아니라 pre-kernel, idle thread와 interrupt-locked 문맥처럼
`k_can_yield()`가 false인 곳에서도 no-op한다. `delayMicroseconds()`는 scheduler를
사용하지 않지만 M3 공개 계약과 구현 모두 ISR만 명시적으로 거부한다.

---

## 11. 오류 정책

### 11.1 오류 범주

| 오류 | 반환 가능한 API | `void` API |
| --- | --- | --- |
| invalid pin | `LOW` + private 오류 | no-op + private 오류 |
| capability 불일치 | `LOW` + private 오류 | no-op + private 오류 |
| device not ready | `LOW` + `device_not_ready` | no-op + `device_not_ready` |
| driver I/O 오류 | Core 상태에 보존 | Core 상태에 보존 |
| ISR 금지 GPIO 호출 | `LOW` 또는 해당 없음 | no-op, private GPIO 오류 기록 |
| ISR 금지 시간 호출 | 해당 없음 | no-op, M3 진단 기록 없음 |

### 11.2 진단

- GPIO는 `lastGpioError()`, `lastGpioDriverError()` 비공개 atomic 상태를 제공한다.
- 이 상태는 Sketch 공개 API가 아니며 현재 Zephyr log나 Kconfig diagnostics가 없다.
- 시간 API는 금지 문맥 no-op를 별도 상태에 기록하지 않는다.
- ISR에서는 문자열 formatting과 logging을 하지 않는다.
- release에서도 논리 핀 범위와 capability 검사를 제거하지 않는다.
- 고빈도 API인 `digitalWrite()`의 성공 경로에는 logging과 mutex를 넣지 않는다.

### 11.3 전역 interrupt API

Arduino의 `noInterrupts()`와 `interrupts()`는 token 없는 전역 API라 Zephyr의 nested `irq_lock()` 의미와 충돌할 수 있다. v0에서는 구현 완료로 간주하지 않는다.

선택지는 다음 검토 후 결정한다.

- thread-local nesting state
- arch IRQ lock key 보존 방법
- SMP 또는 향후 multicore 의미
- Zephyr subsystem interrupt를 장시간 막는 위험

잘못된 단순 wrapper를 제공하는 것보다 미지원 상태를 명확히 하는 편을 우선한다.

---

## 12. 설정 항목

현재 존재하는 Core 설정은 다음과 같다.

| 설정 | 기본값 | 목적 |
| --- | ---: | --- |
| `CONFIG_NUCODE_ARDUINO_GPIO` | Core 활성 시 `y` | digital GPIO API |
| `CONFIG_NUCODE_ARDUINO_INTERRUPTS` | Core 활성 시 `y` | GPIO raw edge interrupt API |
| `CONFIG_NUCODE_ARDUINO_TIME` | Core 활성 시 `y` | `millis/micros/delay/yield` API |

pin/time diagnostics와 별도 `CONFIG_NUCODE_ARDUINO_MICROS`는 현재 존재하지 않는 향후
검토안이다.

Zephyr 기본 의존성은 다음을 사용한다.

- `CONFIG_GPIO`
- `CONFIG_CPP`
- kernel timer와 system clock 설정

물리 pin 번호나 timer instance를 Kconfig에 다시 적는 옵션은 만들지 않는다.

---

## 13. 완료 기준

### 13.1 GPIO

- [x] `LED_BUILTIN`이 `DT_ALIAS(led0)`를 사용한다.
- [x] Core에 물리 pin 번호가 없다.
- [x] `HIGH`와 `LOW`가 raw 전기 값과 일치하며 Active High LED를 육안 확인했다.
- [x] `INPUT_PULLUP` 버튼과 `OUTPUT` LED가 실기에서 동작한다.
- [x] invalid pin self-check 뒤 버튼 연동 loop에 진입했다. 이 제어 흐름은 self-check
  PASS의 간접 oracle이며 세부 RAM trace 값은 미회수다.

`INPUT_PULLDOWN`의 추가 물리 조합과 GPIO/peripheral ownership은 전체 핀맵과 M7 이후
범위다. GPIO RAM trace와 외부 pulse 계측은 사용자 결정으로 필수 증거에서 제외했다.

### 13.2 Interrupt

- [x] target GPIO emulator에서 RISING, FALLING, CHANGE callback 횟수가 입력 edge와 일치한다.
- [x] detach 후 callback이 실행되지 않는다.
- [x] callback은 Zephyr GPIO ISR에서 직접 실행된다.
- [x] in-flight count와 slot 정리로 callback 실행 중 detach의 use-after-free를 방지한다.
- [x] 지원하지 않는 level trigger와 잘못된 mode가 조용히 다른 mode로 바뀌지 않는다.
- [ ] 실제 P1.13 active-low 버튼에서 누름 FALLING·해제 RISING·양 edge CHANGE를 수동 확인한다.

### 13.3 시간

- [x] `millis()`와 `micros()`가 M3 실행 구간에서 증가하고 unsigned elapsed 산술 검사를 통과한다.
- [x] production helper에 32-bit wrap 경계값을 주입해 rollover 산술을 검증한다.
- [x] `millis()`와 `micros()`를 timer ISR에서 1,582회 호출했다.
- [x] `delay(20)`이 20 ms보다 일찍 복귀하지 않았다.
- [x] `delay()` 중 worker thread, timer와 workqueue가 진행했다.
- [x] `delayMicroseconds(1000)`을 내부 시간원으로 계측해 1,026 us를 기록했다.
- [x] 긴 delay와 busy-wait chunk 경계를 자동 경계값 시험으로 검증한다.
- [ ] 저전력 진입 전후 `micros()` 정책은 사용자 결정으로 M3/M6 필수 범위에서 제외한다.

---

## 14. 테스트 계획

### 14.1 Host test

- logical pin 범위와 descriptor index
- Arduino mode에서 Zephyr flag 변환
- output latch 상태 전이
- invalid pin 오류 변환
- 32-bit millis/micros rollover 산술
- interrupt callback table 등록·교체·삭제

### 14.2 Zephyr test

- fake GPIO driver를 이용한 호출 인자 확인
- device not-ready 경로
- driver 음수 오류 경로
- thread/ISR 문맥 검사
- 동시 digital write와 detach race

### 14.3 NU54DK HIL

| 시험 | 측정 방법 |
| --- | --- |
| Blink | built-in LED 육안 확인 |
| Input pull | 사용자 버튼과 외부 저항 |
| Raw polarity | 온보드 active-low 버튼 상태와 API 반환 비교 |
| Edge interrupt | 온보드 P1.13 버튼 또는 자동 GPIO emulator |
| Delay | target 내부 counter와 경계값 주입 |
| Micros rollover | production helper 경계값 주입 |
| Scheduler 공존 | worker counter와 timer latency 기록 |

M3에서는 Blink와 pull-up/Active Low 버튼에 따른 LED 전환을 육안 확인하고
`runtime_timing` trace와 NU54DK Twister 9/9를 회수했다. M6는 GPIO emulator 기반 edge
interrupt 2/2와 Arduino CLI InterruptButton build를 통과했다. GPIO RAM trace, 외부
GPIO/time 계측과 저전력 profile은 사용자 결정으로 필수 증거에서 제외한다. 실제 P1.13
버튼 ISR edge 수동 확인만 M6 조건으로 남긴다.

### 14.4 Negative test

- `NUM_DIGITAL_PINS`와 같은 값의 pin 전달
- ADC-only pin에 output 요청
- PWM이 소유한 pin에 digital write 요청
- ISR에서 `delay()` 호출
- 준비되지 않은 GPIO controller 사용

---

## 15. 범위 제외

이 문서의 v0 범위에서 다음은 제외한다.

- `shiftIn()`과 `shiftOut()` 최적화
- `pulseIn()`과 timeout 정밀도
- `tone()`과 `noTone()`
- direct port register API
- cycle 정확도의 software bit-banging 보장
- peripheral pinctrl 자동 해제
- 전역 interrupt disable API의 성급한 wrapper
- 임의 물리 GPIO 번호 직접 입력
- USB GPIO 또는 USB timing API

nRF54L15에는 native USB peripheral이 없다. CMSIS-DAP USB 연결은 GPIO/시간 API 구현과 무관하다.

---

## 16. 핵심 결정 요약

~~~text
핀 위치는 Devicetree가 결정한다.
Arduino HIGH/LOW는 raw 전기 값을 뜻한다.
시간은 Zephyr kernel timebase를 사용한다.
sleep과 busy wait를 구분한다.
ISR-safe와 thread-safe를 구분한다.
~~~

이 원칙을 지키면 Arduino Sketch의 기본 동작을 제공하면서도 Zephyr scheduler, device lifecycle 및 전력 관리와 충돌하는 숨은 register 제어를 피할 수 있다.
