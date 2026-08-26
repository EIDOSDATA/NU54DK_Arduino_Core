# NU54DK Arduino GPIO와 시간 API 설계

| 항목 | 내용 |
| --- | --- |
| 문서 상태 | 설계 기준선 — 구현 전 |
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

목표는 Arduino의 관례를 유지하면서도 Zephyr의 device, scheduler 및 ISR 규칙을 위반하지 않는 것이다. 이 문서는 구현 완료 보고서가 아니다.

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

Arduino 논리 순서는 `variants/nu54dk`가 소유한다. 최초 PoC에서는 다음 연결만 필수다.

~~~text
LED_BUILTIN → DT_ALIAS(led0)
~~~

전체 논리 핀 정책은 [핀과 Variant 설계](../01_아두이노%20코어%20설계/03_핀과_Variant_설계.md)를 따른다.

### 2.3 시간

시간의 원본은 Zephyr kernel timebase다. Core가 별도 SysTick, GRTC 또는 TIMER register를 직접 구성하지 않는다.

| Arduino API | Zephyr 원본안 |
| --- | --- |
| `millis()` | `k_uptime_get_32()` |
| `micros()` | `k_cycle_get_64()`와 `k_cyc_to_us_floor64()` |
| `delay()` | `k_msleep()` |
| `delayMicroseconds()` | `k_busy_wait()` |
| `yield()` | `k_yield()` |

`micros()`의 실제 resolution과 저전력 상태에서의 연속성은 nRF54L15 HIL로 검증한 뒤 확정한다.

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

### 3.2 `wiring_time.cpp`

책임:

- kernel timebase를 Arduino 반환형으로 변환
- 32-bit rollover 의미 보존
- millisecond sleep과 microsecond busy wait 구현
- thread와 ISR 문맥 검사

### 3.3 `wiring_interrupts.cpp`

GPIO interrupt를 별도 파일로 나누는 방안을 기본으로 한다.

책임:

- pin별 callback slot 관리
- Arduino interrupt mode를 Zephyr flag로 변환
- Zephyr `gpio_callback` 등록과 해제
- 공통 ISR trampoline에서 사용자 callback 호출

첫 Blink PoC에는 포함하지 않고 GPIO input 단계에서 추가한다.

### 3.4 Variant와 내부 pin state

Variant descriptor는 물리 자원을 immutable data로 제공한다. Core는 별도의 runtime state에 다음 최소 정보만 유지한다.

- 현재 Arduino pin mode
- output latch의 마지막 raw 값
- interrupt callback과 trigger mode
- pin ownership 상태

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

| Arduino mode | Zephyr 설정안 | 비고 |
| --- | --- | --- |
| `INPUT` | `GPIO_INPUT` | pull 없음 |
| `INPUT_PULLUP` | `GPIO_INPUT | GPIO_PULL_UP` | nRF GPIO 지원 확인 |
| `INPUT_PULLDOWN` | `GPIO_INPUT | GPIO_PULL_DOWN` | 지원 대상으로 포함 |
| `OUTPUT` | `GPIO_OUTPUT_HIGH/LOW` | 저장된 output latch를 적용 |
| `OUTPUT_OPEN_DRAIN` | 구현 후 확장 | capability와 driver 지원 필요 |

지원하지 않는 mode는 임의의 다른 mode로 바꾸지 않는다.

### 5.2 Output latch

Arduino 호환성을 위해 logical pin별 마지막 output 값을 유지한다.

~~~text
digitalWrite(pin, HIGH)
    ↓ output latch = 1

pinMode(pin, OUTPUT)
    ↓ GPIO_OUTPUT_HIGH로 configure
~~~

이 방식은 input 상태에서 미리 `digitalWrite(HIGH)`를 호출한 뒤 output으로 바꾸는 기존 Sketch의 동작과 output 전환 glitch를 함께 고려한다.

초기 latch 값은 `LOW`로 정의한다. 단, application overlay가 boot-time pin state를 별도로 요구하는 경우에는 그 장치가 GPIO API에 넘겨지기 전에 pinctrl ownership을 해제해야 한다.

### 5.3 호출 흐름

~~~text
pinMode(logical_pin, mode)
        ↓
범위와 digital capability 검사
        ↓
pin ownership 검사
        ↓
GPIO device readiness 검사
        ↓
mode와 latch를 Zephyr flags로 변환
        ↓
gpio_pin_configure()
        ↓
성공 시 runtime mode 갱신
~~~

driver 호출이 실패하면 이전 mode 상태를 성공한 것으로 기록하지 않는다.

---

## 6. `digitalWrite()` 설계

### 6.1 Output pin

output으로 구성된 pin에서는 다음 순서를 사용한다.

1. logical pin과 capability를 검사한다.
2. output latch를 raw 0 또는 1로 갱신한다.
3. `gpio_pin_set_raw()`를 호출한다.
4. driver 오류를 기록한다.

### 6.2 Input pin

Arduino 관례에 따라 input pin에서 `digitalWrite(HIGH)`는 internal pull-up 활성화, `LOW`는 pull 비활성으로 해석할 수 있다. v1 목표 동작은 다음과 같다.

| 현재 mode | `LOW` | `HIGH` |
| --- | --- | --- |
| `INPUT` | pull 없음 유지 | `INPUT_PULLUP`으로 재구성 |
| `INPUT_PULLUP` | `INPUT`으로 재구성 | 유지 |
| `INPUT_PULLDOWN` | pull-down 유지 | 잘못된 조합으로 진단 후 정책 결정 |

Input 재구성은 `gpio_pin_configure()`를 호출하므로 ISR에서 허용하지 않는다. ISR에서 input pin에 `digitalWrite()`가 호출되면 동작을 거부하고 진단 상태만 기록한다.

### 6.3 Ownership

PWM, UART, SPI 또는 I2C가 소유한 pin에 `digitalWrite()`를 호출해 peripheral pinctrl을 자동 해제하지 않는다. 해당 pin을 GPIO로 사용하려면 application overlay 또는 명시적인 peripheral `end()` 정책에 따라 ownership을 전환해야 한다.

---

## 7. `digitalRead()` 설계

~~~text
digitalRead(logical_pin)
        ↓
범위와 digital capability 검사
        ↓
GPIO device readiness 검사
        ↓
gpio_pin_get_raw()
        ↓
raw 0 → LOW
raw 1 → HIGH
~~~

Driver가 음수 오류를 반환해도 Arduino API 반환형에는 `LOW`와 `HIGH`만 존재한다. 오류 시 기본 반환값은 `LOW`로 두되, Core 진단 상태에 driver 오류를 보존한다. 오류를 실제 LOW 입력과 구분해야 하는 application은 향후 제공할 상세 오류 API 또는 Zephyr GPIO API를 직접 사용한다.

Output pin에서 `digitalRead()`는 가능하면 실제 pin input 값을 읽는다. output latch를 그대로 돌려주는 방식은 물리 단락을 숨길 수 있으므로 기본으로 사용하지 않는다.

---

## 8. External interrupt 설계

### 8.1 지원 mode

| Arduino mode | Zephyr flag안 |
| --- | --- |
| `RISING` | `GPIO_INT_EDGE_RISING` |
| `FALLING` | `GPIO_INT_EDGE_FALLING` |
| `CHANGE` | `GPIO_INT_EDGE_BOTH` |
| `LOW` | `GPIO_INT_LEVEL_LOW` 지원 시 |
| `HIGH` | `GPIO_INT_LEVEL_HIGH` 지원 시 |

Level trigger 지원은 nRF54L15 Zephyr GPIO driver와 전력 정책을 HIL로 확인한 뒤 공개한다. 지원하지 않는 trigger를 edge trigger로 조용히 바꾸지 않는다.

### 8.2 Callback table

- pin마다 최대 하나의 Arduino callback을 등록한다.
- 정적 크기 table을 사용하고 ISR 등록 과정에서 heap을 사용하지 않는다.
- 재등록은 기존 callback을 원자적으로 교체하거나 먼저 disable한 뒤 교체한다.
- `detachInterrupt()`는 hardware interrupt를 disable한 뒤 callback slot을 비운다.

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

`attachInterrupt()`와 `detachInterrupt()`는 thread 문맥 전용이다. callback pointer 교체와 ISR lookup 사이에는 interrupt disable 또는 atomic pointer 규칙을 사용한다. callback 실행 중 detach가 호출되는 경쟁 조건도 시험한다.

---

## 9. 시간 API 설계

### 9.1 `millis()`

예정 구현:

~~~text
return lower_32_bits(k_uptime_get_32())
~~~

Arduino와 같은 32-bit unsigned rollover 의미를 유지한다. 약 49.7일 후 wrap되는 것은 오류가 아니다. elapsed time 비교는 unsigned subtraction으로 수행해야 한다.

시간의 기준점은 Zephyr kernel uptime 시작 시점이다. 전원 인가 또는 reset edge와 몇 cycle 차이가 날 수 있으므로 절대 timestamp로 사용하지 않는다.

### 9.2 `micros()`

초기 구현 후보:

~~~text
k_cycle_get_64()
      ↓
k_cyc_to_us_floor64()
      ↓
lower 32 bit 반환
~~~

목표 특성:

- lock 없이 단조 증가
- thread와 ISR에서 조회 가능
- 32-bit Arduino 반환형에 맞춰 약 71.6분마다 wrap
- clock frequency 변환은 Zephyr API에 위임

다음 항목은 실측 전 확정하지 않는다.

- 실제 최소 resolution
- system sleep 동안의 연속성
- dynamic clock 변경 시 정확도
- `millis()`와 장시간 drift 관계

조건을 만족하지 못하면 uptime tick 기반 구현과 SoC counter 기반 구현을 비교한다. nRF register를 Core 공통 코드에서 직접 읽는 방식은 최후 수단으로 두고 별도 HAL 계층과 검증을 요구한다.

### 9.3 `delay(ms)`

| 입력 | 동작안 |
| ---: | --- |
| `0` | `k_yield()` |
| `1` 이상 | `k_msleep(ms)` |

`delay()`는 busy loop가 아니다. 현재 Arduino main thread만 sleep하며 Zephyr의 다른 ready thread와 interrupt는 계속 실행된다.

Scheduler 지연 때문에 실제 복귀 시간이 요청값보다 길 수 있다. 요청 시간보다 일찍 복귀하지 않는 것을 기본 정확도 조건으로 한다.

### 9.4 `delayMicroseconds(us)`

초기 구현은 `k_busy_wait(us)`를 사용한다.

- `0`은 즉시 반환한다.
- scheduler에 CPU를 양보하지 않는다.
- 긴 대기는 전력과 latency를 악화하므로 `delay()` 사용을 권고한다.
- interrupt가 실행되면 실제 지연은 길어질 수 있다.
- Zephyr power management가 busy-wait용 clock을 정지시키는 구성에서는 동작하지 않을 수 있으므로 실제 PM profile마다 검증한다.
- ISR에서의 사용은 짧은 hardware timing에 한해 기술적으로 가능할 수 있지만 v1 공개 계약에서는 금지한다.

실측 후 busy wait의 최소 유효 값과 오차를 문서화한다.

### 9.5 `yield()`

`yield()`는 `k_yield()`에 연결한다. 이는 current thread를 같은 priority queue의 뒤로 보내는 동작이며, 낮은 priority thread 실행을 보장하는 sleep이 아니다.

`yield()`를 power management 진입이나 1 ms sleep으로 몰래 바꾸지 않는다. loop 최소 sleep은 Runtime Kconfig의 별도 정책으로 다룬다.

---

## 10. 스레드와 ISR 문맥

| API | Thread | ISR | Blocking | 비고 |
| --- | --- | --- | --- | --- |
| `pinMode` | 허용 | 금지 | driver 의존 | pin 재구성 |
| `digitalWrite` output | 허용 | 검증 후 허용 목표 | 비차단 목표 | 사전 configure 필요 |
| `digitalWrite` input | 허용 | 금지 | 재구성 | pull 전환 가능 |
| `digitalRead` | 허용 | 검증 후 허용 목표 | 비차단 목표 | raw input |
| `attachInterrupt` | 허용 | 금지 | 설정 작업 | callback 등록 |
| `detachInterrupt` | 허용 | 금지 | 설정 작업 | callback 해제 |
| `millis` | 허용 | 허용 목표 | 아니요 | uptime read |
| `micros` | 허용 | 허용 목표 | 아니요 | cycle read |
| `delay` | 허용 | 금지 | 예 | current thread sleep |
| `delayMicroseconds` | 허용 | 공개 계약상 금지 | busy wait | 짧은 지연 전용 |
| `yield` | 허용 | 금지 | scheduler | 같은 priority 중심 |

“허용 목표”는 nRF54L15의 Zephyr driver 경로를 HIL로 확인한 뒤 완료 상태로 바꾼다.

---

## 11. 오류 정책

### 11.1 오류 범주

| 오류 | 반환 가능한 API | `void` API |
| --- | --- | --- |
| invalid pin | sentinel + 진단 | no-op + 진단 |
| capability 불일치 | sentinel + 진단 | no-op + 진단 |
| device not ready | sentinel + driver 오류 보존 | no-op + 진단 |
| driver I/O 오류 | Core 상태에 보존 | Core 상태에 보존 |
| ISR 금지 호출 | 즉시 실패 | no-op, ISR-safe 상태 기록 |

### 11.2 진단

- 개발 build에서는 logical pin, API 및 오류 코드를 Zephyr log로 남긴다.
- ISR에서는 문자열 formatting과 logging을 하지 않는다.
- release에서도 범위 검사와 ownership 검사를 제거하지 않는다.
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

아래는 구현 예정안이다.

| 설정안 | 기본값안 | 목적 |
| --- | ---: | --- |
| `CONFIG_NUCODE_ARDUINO_GPIO` | `y` | digital GPIO API |
| `CONFIG_NUCODE_ARDUINO_GPIO_INTERRUPT` | `y` | external interrupt API |
| `CONFIG_NUCODE_ARDUINO_PIN_DIAGNOSTICS` | 개발 `y` | 잘못된 pin 진단 |
| `CONFIG_NUCODE_ARDUINO_MICROS` | `y` | high-resolution time API |
| `CONFIG_NUCODE_ARDUINO_TIME_DIAGNOSTICS` | 개발 `y` | 금지 문맥 호출 진단 |

Zephyr 기본 의존성은 다음을 사용한다.

- `CONFIG_GPIO`
- `CONFIG_CPP`
- kernel timer와 system clock 설정

물리 pin 번호나 timer instance를 Kconfig에 다시 적는 옵션은 만들지 않는다.

---

## 13. 완료 기준

### 13.1 GPIO

- [ ] `LED_BUILTIN`이 `DT_ALIAS(led0)`를 사용한다.
- [ ] Core에 물리 pin 번호가 없다.
- [ ] `HIGH`와 `LOW`가 raw 전기 값과 일치한다.
- [ ] `INPUT`, `INPUT_PULLUP`, `INPUT_PULLDOWN`, `OUTPUT`이 동작한다.
- [ ] invalid pin이 memory access나 다른 GPIO 변경을 만들지 않는다.
- [ ] output latch 전환에 의도하지 않은 pulse가 없는지 logic analyzer로 확인한다.
- [ ] GPIO/peripheral ownership 충돌이 명확히 실패한다.

### 13.2 Interrupt

- [ ] RISING, FALLING, CHANGE callback 횟수가 입력 edge와 일치한다.
- [ ] detach 후 callback이 실행되지 않는다.
- [ ] callback은 ISR 문맥임이 확인된다.
- [ ] attach/detach 경쟁 조건에 use-after-free가 없다.
- [ ] 지원하지 않는 level trigger가 조용히 다른 mode로 바뀌지 않는다.

### 13.3 시간

- [ ] `millis()`가 monotonic하고 32-bit rollover test를 통과한다.
- [ ] `micros()`가 thread와 ISR에서 monotonic하다.
- [ ] `delay()`가 요청 시간보다 일찍 복귀하지 않는다.
- [ ] `delay()` 중 worker thread와 timer가 진행한다.
- [ ] `delayMicroseconds()` 오차와 유효 범위를 계측해 기록한다.
- [ ] 저전력 진입 전후 `micros()` 정책을 확정한다.

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
| Blink | built-in LED와 oscilloscope/logic analyzer |
| Input pull | 사용자 버튼과 외부 저항 |
| Raw polarity | GPIO 전압과 API 반환 비교 |
| Edge interrupt | signal generator 또는 연결된 output pin |
| Delay | logic analyzer pulse width |
| Micros drift | 일정 주기의 toggle과 외부 시간 기준 비교 |
| Scheduler 공존 | worker counter와 timer latency 기록 |

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
