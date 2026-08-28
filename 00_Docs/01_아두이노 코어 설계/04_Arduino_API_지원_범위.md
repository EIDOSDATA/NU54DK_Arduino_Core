# NU54DK Arduino API 지원 범위

| 항목 | 내용 |
| --- | --- |
| 문서 상태 | v0.1.0 정식 공개 완료; v0.2.0 M14 Core API·Variant 무보드 구현 반영, 신규 pin HIL 대기 |
| 작성자 | Quantum / NUCODE |
| 기준 SDK | nRF Connect SDK v3.4.0 |
| 기준 Zephyr | Zephyr 4.4.0 |
| 기준 보드 | `nrf54l15dk/nrf54l15/cpuapp/nu54dk` |
| API 기준 | ArduinoCore-API 1.5.2, `cd91833d90b4fe50e428021ba5051e2b7ceafc84` |
| Core 자체 라이선스 목표 | MIT — third-party component에는 각각의 원 라이선스 적용 |

---

## 1. 문서 목적

이 문서는 NU54DK Arduino Core가 어떤 Arduino API를 어느 수준까지 제공할지 정의한다. API 이름이나 header가 존재한다는 이유만으로 `지원`이라고 선언하지 않는다. 실제 상태, v0.1.0 목표, 하드웨어 제약 및 검증 증거를 분리하여 관리한다.

현재 저장소에는 M3 Runtime·GPIO·시간 backend, M4에서 고정한 ArduinoCore-API source와
M6에서 생산 image에 연결한 `Common`, `String`, `Print`, `Stream`, `HardwareSerial` 및 GPIO
edge interrupt backend가 존재한다. M6는 target ztest 10/10, 실제 COM10 Serial READY·echo,
Arduino CLI staged package build와 실제 P1.13 active-low 버튼의 `FALLING`, `RISING`,
`CHANGE` HIL을 통과했다. interrupt 항목은 raw electrical edge와 ISR 호출 제약을 계속
명시한다. v0.1.0 목표 상태는 당시 계획을 보존한 것이며 현재 완료 보고와 구분한다.

M7의 `Wire`, `SPI`, `analogRead()`와 `analogWrite()` production source 및 builder profile은
NU54DK Twister target 11/11, Arduino CLI M7 4/4와 승인된 NU54DK driver HIL을 통과했다.
BQ25186 I2C repeated-start는 100/400 kHz에서 실기 통과했고 SPI00은 4 MHz에서 P2.2 MOSI와
P2.4 MISO 사이의 40-byte 물리 loopback이 전부 일치했다. 제약이 있는 공개 API는 아래 표에서
계속 `부분 지원` 또는 `의미 차이`로 표시하지만 M7 단계 자체는 **완료**다.

M14의 무보드 범위에서는 기존에 선언만 존재하던 `random()`/`randomSeed()`를 실제 생산
source에 연결하고, utility·bit·`F()`와 최소 공개 진단 API를 host compile/link·
native semantic·target cross-build로 검증했다. 임의 TEMP native executable을 Windows
Application Control이 차단한 최초 실행은 semantic SKIP으로 기록했고, repository
고정 staging에서 매번 재compile하도록 고친 시험은 의미 실행까지 3/3 PASS했다.
DTS `led0..3`/`sw0..3` alias로부터 sparse Variant 계약도 구현하고 host 대조와
NU54DK production target build-only를 통과했다. 다만 PWM이 소유한 `PIN_LED1`은 digital에서
명시적으로 거부하며, 신규 LED2/3과 BUTTON1..3의 실기 HIL은 보드 준비 후 남아 있다.
QEMU actual-runtime gate는 고정 Nordic container workflow에 등록했으나 이 문서 갱신
시점에서 원격 실행 증적은 아직 확정하지 않았다.

관련 문서는 다음과 같다.

- [구현 로드맵](02_구현_로드맵.md)
- [테스트와 검증](../03_펌웨어%20설계/04_테스트와_검증.md)
- [M6 기본 Arduino API, Serial과 인터럽트 기준선](<../04_검증 기록/06_M6_기본_Arduino_API_Serial과_인터럽트_기준선.md>)
- [M7 Wire·SPI·ADC·PWM 기준선](<../04_검증 기록/07_M7_Wire_SPI_ADC_PWM_기준선.md>)
- [M14 Core API와 Variant 기준선](<../04_검증 기록/16_M14_Core_API와_Variant_기준선.md>)

---

## 2. 지원 상태 vocabulary

지원 상태는 다음 다섯 값만 사용한다.

| 상태 | 정의 | 선언 조건 |
| --- | --- | --- |
| 지원 | 공식 또는 본 문서가 정한 API signature와 핵심 의미를 NU54DK에서 제공 | compile, semantic, Zephyr coexistence 및 HIL 검증을 모두 통과 |
| 부분 지원 | API는 사용할 수 있으나 pin, mode, resolution, frequency 또는 동시 사용에 명확한 제한이 있음 | 제한을 API 문서·예제·runtime/build diagnostic에 표시하고 제한 범위 시험 통과 |
| 의미 차이 | 동일 signature를 제공하지만 scheduler, interrupt context, timing, memory 또는 flush 같은 의미가 일반 Arduino 기대와 다름 | 차이를 문서화하고 해당 의미에 맞춘 시험 통과 |
| 하드웨어 미지원 | target MCU 또는 NU54DK 회로에 필요한 peripheral/전기 경로가 없어 Core만으로 구현할 수 없음 | 실제 하드웨어 근거를 기록하고 대체 경로가 정식 지원이 아님을 표시 |
| 미구현 | 구현과 검증이 완료되지 않음 | 계획에 있더라도 증거가 없으면 이 상태 유지 |

상태 선택 규칙은 다음과 같다.

- 아직 시험하지 않은 기능은 `지원 예정`이라고 쓰지 않고 `미구현`으로 둔다.
- 제약이 하드웨어 원인이라도 기능의 일부가 동작하면 `부분 지원`, 전체 경로가 없으면 `하드웨어 미지원`으로 구분한다.
- Zephyr/NCS API를 직접 사용해 같은 기능을 만들 수 있다는 사실은 Arduino API 지원 증거가 아니다.
- 외부 shield, 외장 USB bridge 또는 별도 firmware를 추가해야 하는 기능은 기본 NU54DK Core 지원으로 계산하지 않는다.
- architecture-specific library가 compile된다는 사실을 표준 API 전체 호환으로 확대 해석하지 않는다.

---

## 3. 우선순위

| 우선순위 | 의미 | 릴리스 관계 |
| --- | --- | --- |
| P0 | Core 사용과 기본 Sketch 실행에 필수 | v0.1.0 공개 후보의 필수 완료 항목 |
| P1 | 일반적인 센서·통신·아날로그 Sketch에 필요한 핵심 기능 | v0.1.0 목표. 부분 지원이나 의미 차이는 허용하되 미구현이면 release note에 명시하고 공개 범위를 재결정 |
| P2 | 유용하지만 초기 수직 경로를 막지 않는 기능 | v0.1.0 이후 순차 구현 |
| P3 | 별도 subsystem, 대규모 library 또는 제품 정책이 필요한 기능 | 별도 설계 승인 후 구현 |
| 제외 | 현재 하드웨어·아키텍처와 맞지 않거나 호환을 약속하지 않음 | 구현 계획 없음 또는 대체 API 안내 |

---

## 4. v0.1.0 지원 범위

### 4.1 v0.1.0 필수 범위

v0.1.0에서 반드시 끝까지 검증할 P0 범위는 다음과 같다.

- `Arduino.h`의 기본 정수형, 상수 및 utility
- `setup()`과 `loop()` runtime
- `pinMode()`, `digitalRead()`, `digitalWrite()`
- `millis()`, `micros()`, `delay()`, `delayMicroseconds()`, `yield()`
- ArduinoCore-API의 `String`, `Print`, `Printable`, `Stream`
- uart20/DAP UART 기반 기본 `Serial`
- `attachInterrupt()`, `detachInterrupt()` 및 interrupt mode
- Arduino CLI Full Zephyr compile 및 pyOCD/CMSIS-DAP upload

P0는 단순 Blink 한 개가 아니라 각 API의 signature, edge case, scheduler 공존 및 실기 결과를 포함한다.

### 4.2 v0.1.0 목표 범위

P1은 v0.1.0에서 구현을 목표로 했지만 하드웨어 특성상 `부분 지원`이나 `의미 차이`가 될 수 있다.

- `Wire`/I2C22
- `SPI`/SPI00
- `analogRead()`의 고정 12-bit A0
- `analogWrite()`와 PWM
- `random()`, `randomSeed()`, `map()`, `constrain()`, `min()`, `max()`
- `noInterrupts()`와 `interrupts()`의 Zephyr-safe 의미
- 대표 범용 Arduino library compile corpus

v0.1.0 release gate에서 P1이 미구현으로 남으면 기능명을 조용히 노출하지 않는다. `Arduino.h` 또는 전역 객체는 존재하지만 항상 실패하는 형태보다, compile-time diagnostic과 정확한 지원표를 우선한다.

### 4.3 v0.1.0 제외 범위

- LLEXT Loader와 runtime Sketch loading
- bootloader, MCUboot, UF2 및 OTA
- target native USB CDC/HID
- `SerialUSB`, `Keyboard`, `Mouse`, PluggableUSB backend
- Bluetooth, Thread, Matter 및 802.15.4 Arduino library
- Wi-Fi, Ethernet 및 network client/server backend
- filesystem, EEPROM emulation 및 external flash abstraction
- Servo, audio, tone 정식 지원
- AVR register, port macro 및 PROGMEM의 AVR memory model
- multi-board, 다른 nRF54L qualifier 및 다른 NCS version

---

## 5. API별 지원 계획

표의 `현재 상태`는 이 문서 작성 시점의 구현 증거를 나타낸다. `v0.1.0 목표`는 당시 완료 후 기대 상태다. 목표 상태가 `의미 차이` 또는 `부분 지원`이면 차이를 없애겠다는 뜻이 아니라 정확히 문서화하고 시험하겠다는 뜻이다.

### 5.0 M3·M6 기준선과 M14 Variant 확장 경계

현재 Variant는 일곱 digital-capable 논리 핀과 하나의 PWM-owned LED 역할을 제공한다.
v0.1 숫자 0..3을 보존하기 위해 A0와 PWM 역할이 digital descriptor 사이의 sparse slot을
차지한다.

| index | 이름 | Devicetree 원본 | capability |
| ---: | --- | --- | --- |
| 0 | `LED_BUILTIN`, `PIN_LED0`, `D0` | `DT_ALIAS(led0)` | input + output + interrupt |
| 1 | `PIN_BUTTON0`, `D1` | `DT_ALIAS(sw0)` | input + interrupt |
| 4 | `PIN_LED1` | `DT_ALIAS(led1)` | `PIN_PWM0` 소유, digital 미지원 |
| 5..6 | `PIN_LED2..3` | `DT_ALIAS(led2..3)` | input + output + interrupt |
| 7..9 | `PIN_BUTTON1..3` | `DT_ALIAS(sw1..3)` | input + interrupt |

`NUM_DIGITAL_PINS=10`은 0..9 sparse ID 순회의 상한이고 실제 descriptor 수는
`NUM_DIGITAL_CAPABLE_PINS=7`이다. `PIN_A0=2`, `PIN_PWM0=3`, `PIN_LED1=4`는 digital
API에서 `nullptr`/invalid pin으로 거부한다. GPIO controller, 실제 pin과 flag는 DTS에서 생성하며
Variant에 복제하지 않는다. 공개 digital GPIO API는 thread-only이고 ISR에서는 no-op 또는
`LOW`다. mode, output latch와 마지막 오류는 private atomic 상태로 관리한다. M6에서
interrupt capability와 고정 callback slot을 추가했으며 callback 자체는 Zephyr GPIO ISR에서
직접 실행한다.

M3 NU54DK HIL에서는 Arduino API만 사용하는 250 ms Blink와 `INPUT_PULLUP` 버튼의 raw
해제 `HIGH`/누름 `LOW`, 버튼-LED 연동을 확인했다. M6는 Arduino CLI에서 Serial/interrupt
예제를 빌드하고 NU54DK target ztest에서 raw 세 edge, detach, `pinMode()` auto-detach와
오류 경로를 검증했다. 실제 P1.13 버튼에서도 누름 `FALLING` 1회, 해제 `RISING` 1회와
`CHANGE` 누름·해제 누적 1·2회를 DAPLink sequence 25/COM10에서 확인했다. 외부 로직
애널라이저나 오실로스코프는 사용하지 않았다.

M14의 추가 다섯 digital pin과 PWM-owned LED1 예약은 고정 DTS alias 대조, host 계약과
NU54DK production target build-only를 통과했다. 실제 LED 출력, 버튼 pull/input과 interrupt
edge HIL은 보드가 준비된 뒤 완료한다.

M14 확장은 DTS alias가 있는 `led0..3`·`sw0..3`으로 제한한다. UART20, I2C22와 SPI00
pinctrl은 활성 peripheral ownership과 충돌하므로 digital ID로 중복 노출하지 않는다.
명시적인 connector mapping이 없는 일반 header도 회로의 물리 pin 번호를 Variant에 복사해
임의 공개하지 않는다.

### 5.1 Runtime과 기본 형식

| API/영역 | 우선순위 | 현재 상태 | v0.1.0 목표 | 설계·검증 메모 |
| --- | --- | --- | --- | --- |
| `Arduino.h` include | P0 | 지원 | 지원 | M6에서 `ArduinoAPI.h` 기반 생산 header 통합, C/C++ target 계약과 Arduino CLI M6 예제 build 통과 |
| `setup()` | P0 | 부분 지원 | 지원 | 전역 constructor 이후 한 번 실행하는 M2/M3 HIL과 M5 Arduino CLI compile/link 통과 |
| `loop()` | P0 | 의미 차이 | 의미 차이 | Zephyr main thread에서 반복하고 기본적으로 반환 뒤 한 tick sleep; scheduler HIL과 M5 Arduino CLI compile/link 통과, 실제 PM 회귀는 별도 범위 |
| `yield()` | P0 | 의미 차이 | 의미 차이 | guarded `k_yield()`이며 같은 priority worker는 진행했지만 낮은 priority와 idle은 진행하지 못함; yield 불가능 문맥에서는 no-op |
| `init()`/`initVariant()` 내부 hook | P0 | 부분 지원 | 부분 지원 | C linkage weak no-op과 override 계약 구현; NU54DK Variant는 별도 override가 필요하지 않음 |
| `HIGH`, `LOW`, `INPUT`, `OUTPUT` | P0 | 부분 지원 | 지원 | LED output과 raw HIGH/LOW HIL 통과; 전체 핀/mode 조합 미검증 |
| `INPUT_PULLUP`, `INPUT_PULLDOWN` | P0 | 부분 지원 | 지원 | 버튼 `INPUT_PULLUP` HIL 통과; pull-down과 전체 핀 조합 미검증 |
| `LSBFIRST`, `MSBFIRST`, interrupt mode 상수 | P0/P1 | 부분 지원 | 지원 | 생산 `Arduino.h`에 upstream 상수 노출; edge mode와 SPI mode·bit-order 변환 target ztest 통과 |
| `byte`, `word`, `boolean` 등 호환 type | P0 | 지원 | 지원 | M6 생산 header의 C/C++ target 계약과 `makeWord()` 회귀 통과 |
| C++ static object initialization | P0 | 지원 | 지원 | 전역 constructor 순서와 hardware를 constructor에서 켜지 않는 `Serial` 객체가 실제 HIL에서 동작 |
| C++ exception/RTTI | P1 | 미구현 | 의미 차이 | 기본 profile은 둘 다 비활성; fixed-staging host native semantic과 NCS QEMU cross-build 통과, QEMU·NU54 target runtime 지원 판정은 대기 |

기본 Sketch profile은 `CONFIG_CPP_EXCEPTIONS=n`, `CONFIG_CPP_RTTI=n`을 유지한다. 두 기능은
Core의 Arduino 호환 필수 계약이 아니라 expert opt-in이다. 사용할 때는
`CONFIG_REQUIRES_FULL_LIBCPP=y`, `CONFIG_CPP_EXCEPTIONS=y`, `CONFIG_CPP_RTTI=y`와 충분한
libc heap·thread stack을 함께 설계해야 한다. M14는 repository 고정 staging의 host native
semantic과 NCS 3.4.0 `qemu_cortex_m3` cross-build를 검증했다. 로컬 Windows에는 QEMU
실행기가 없어 Zephyr runtime을 실행하지 못했고, 고정 Nordic Linux container의 실시간
QEMU gate는 원격 증적을 기다린다. NU54DK에서 throw/unwind와 RTTI를 지원으로
선언하려면 별도 target runtime/HIL과 memory budget 승인이 필요하다.

### 5.2 Digital I/O

| API/영역 | 우선순위 | 현재 상태 | v0.1.0 목표 | 설계·검증 메모 |
| --- | --- | --- | --- | --- |
| `pinMode()` | P0 | 부분 지원 | 지원 | 7개 descriptor에서 capability 기반 input/pull/output을 thread에서 구현; 신규 5개 pin HIL, open-drain, ISR, ownership 미검증 |
| `digitalWrite()` | P0 | 부분 지원 | 지원 | `OUTPUT`으로 구성된 index 0에서 raw write HIL 통과; 추가 LED는 target build-only, input pull 전환·ISR·ownership 미구현 |
| `digitalRead()` | P0 | 부분 지원 | 지원 | v0.1 LED/button HIL 통과; 추가 LED/버튼은 target build-only, thread 문맥으로 제한 |
| `LED_BUILTIN` | P0 | 부분 지원 | 지원 | index 0, DTS `led0`, input+output; Blink HIL 통과, 정량 timing/voltage 미측정 |
| `PIN_BUTTON0` | P0 | 부분 지원 | 부분 지원 | index 1, DTS `sw0`, input-only·interrupt; pull-up raw 버튼과 ISR physical edge HIL 통과, Core debounce는 제공하지 않음 |
| `PIN_LED2..3`, `PIN_BUTTON1..3` | P1 | 부분 지원 | 부분 지원 | DTS `led2..3`/`sw1..3`에서 생성; host·target build-only 통과, 신규 pin HIL 대기 |
| `PIN_LED1` | P1 | 미구현 | 미구현 | DTS `led1` mapping은 검증하지만 P1.10을 `PIN_PWM0`이 소유하므로 명시적 ownership 전환 전 digital descriptor 없음 |
| 전체 `D0...Dn` 논리 pin map | P1 | 미구현 | 부분 지원 | `D0`/`D1`만 호환 별칭; 일반 connector의 D2 이후는 ownership 승인 전 미정 |
| `digitalPinToInterrupt()` | P0 | 지원 | 지원 | 유효 index와 `NOT_AN_INTERRUPT`, C++ 인수 1회 평가를 NU54DK target ztest로 검증 |
| direct port/register access | 제외 | 하드웨어 미지원 | 하드웨어 미지원 | AVR/SAMD register 호환을 제공하지 않음; Zephyr/nrfx 직접 API는 별도 영역 |

### 5.3 시간과 utility

| API/영역 | 우선순위 | 현재 상태 | v0.1.0 목표 | 설계·검증 메모 |
| --- | --- | --- | --- | --- |
| `millis()` | P0 | 부분 지원 | 지원 | uptime backend, `delay(20)`의 20 ms 경과와 timer ISR 반복 읽기 HIL 통과; 실제 wrap·PM 장기 연속성 미검증 |
| `micros()` | P0 | 부분 지원 | 부분 지원 | GRTC startup offset을 뺀 64-bit cycle backend와 timer ISR 반복 읽기 HIL 통과; 외부 resolution·실제 wrap·PM 미검증 |
| `delay()` | P0 | 의미 차이 | 의미 차이 | 64-bit deadline sleep, 20 ms/20,084 us 내부 계측과 worker 공존 HIL 통과; 긴 `INT32_MAX` chunk와 금지 문맥 진단 미검증 |
| `delayMicroseconds()` | P0 | 의미 차이 | 의미 차이 | 1초 chunk busy-wait의 1,000 us 요청을 내부에서 1,026 us로 측정; ISR에서는 no-op이며 외부 정확도·긴 chunk 경계 미검증 |
| `map()` | P1 | 부분 지원 | 지원 | ArduinoCore-API의 정수 구현과 정상·음수 범위 변환 검증; 입력 span 0과 signed 중간식 overflow는 지원하지 않음 |
| `constrain()`, `min()`, `max()`, `abs()` | P1 | 부분 지원 | 지원 | host C++ compile/link·fixed-staging 의미 시험과 NU54 target compile 통과; 아래 부수 효과·signed minimum 경계 적용, target runtime/HIL 대기 |
| `bitRead`, `bitWrite`, `bitSet`, `bitClear`, `bitToggle`, `bit()` | P1 | 부분 지원 | 지원 | host compile/link·constexpr·fixed-staging 의미 시험과 NU54 target compile 통과; 아래 bit 폭 경계 적용, target runtime/HIL 대기 |
| `random()`, `randomSeed()` | P1 | 부분 지원 | 의미 차이 | full-period 32-bit LCG·원자적 상태·bias 없는 반열린 범위 구현; host 의미 시험과 NU54/QEMU cross-build 통과, target runtime/HIL 대기, entropy/암호 용도 아님 |
| `pulseIn()`, `pulseInLong()` | P2 | 미구현 | 미구현 | timeout, scheduler 및 timing 오차 설계 후 추가 |
| `shiftIn()`, `shiftOut()` | P2 | 미구현 | 미구현 | software timing 기반 reference implementation 검토 |

`constrain(amt, low, high)`는 ArduinoCore-API 1.5.2의 매크로다. 선택 경로에 따라 `amt`를
최대 세 번 평가하고 `low` 또는 `high`도 조건과 반환식에서 반복 평가할 수 있으므로 `i++`,
함수 호출, volatile register read 같은 부수 효과 표현식을 전달하지 않는다. `low <= high`인
정상 범위만 지원하며 역전된 경계의 반환값을 별도 정책으로 보정하지 않는다. C++ `abs()`는
Core의 함수 template으로 인수를 한 번만 평가하고, `Arduino.h` 뒤의 `<cmath>`와
`std::abs()`를 가리지 않는다. C 호출부의 호환 매크로는 반복 평가할 수 있다. 두 경로 모두
signed 정수형 최솟값은 같은 형식의 양수로 나타낼 수 없으므로 지원 입력이 아니다.

`map()`은 입력을 clamp하지 않고 범위 밖 값을 선형 외삽한다. `in_min != in_max`여야 하며
`(x - in_min) * (out_max - out_min)`을 포함한 모든 `long` 중간식이 target의 signed 32-bit
범위에 들어와야 한다. 이 조건을 벗어난 divide-by-zero와 signed overflow는 Core가 별도
포화·오류 값으로 바꾸지 않는다.

bit helper에는 0 이상인 index만 전달한다. `bitRead(value, index)`는 unsigned로 해석한
`value` 형식의 bit 폭보다 index가 작아야 한다. `bitSet`, `bitClear`, `bitToggle`과
`bitWrite`는 upstream 구현이 `1UL << index`를 사용하므로 index가 destination 폭과
`unsigned long` 폭보다 모두 작아야 한다. `bit(index)`도 `unsigned long` 폭이 경계다.
NU54DK의 32-bit ABI에서는 뒤 다섯 helper의 유효 index가 0~31이며, 64-bit destination을
전달해도 32 이상 shift를 지원하지 않는다.

`random(howbig)`은 `howbig <= 0`이면 0, `random(howsmall, howbig)`은
`howsmall >= howbig`이면 `howsmall`을 반환한다. 정상 입력은 상한을 포함하지 않는다.
`randomSeed(0)`은 현재 수열을 변경하지 않으며 같은 nonzero seed는 같은 수열을 만든다.
상태 갱신은 Zephyr atomic CAS로 보호하지만 여러 thread의 호출 순서까지 재현 가능하다고
보장하지 않는다. hardware entropy를 자동으로 섞지 않으므로 security token, key, nonce
생성에는 사용하지 않는다.

### 5.4 Interrupt

| API/영역 | 우선순위 | 현재 상태 | v0.1.0 목표 | 설계·검증 메모 |
| --- | --- | --- | --- | --- |
| `attachInterrupt()`/`attachInterruptParam()` | P0 | 의미 차이 | 의미 차이 | 고정 pin slot의 GPIO ISR에서 callback 직접 실행; target GPIO emulator와 실제 P1.13 세 edge PASS |
| `detachInterrupt()` | P0 | 지원 | 지원 | callback 비활성화·제거와 진행 중 callback 정리, 재등록 및 `pinMode()` auto-detach target test 통과 |
| `RISING`, `FALLING`, `CHANGE` | P0 | 지원 | 지원 | raw electrical edge로 구현·target test 통과; P1.13 active-low에서 누름=FALLING, 해제=RISING, CHANGE 양 edge 실물 확인 완료 |
| `LOW`, `HIGH` level interrupt | P1 | 미구현 | 부분 지원 | Zephyr/nRF hardware와 driver가 안정적으로 제공하는 mode만 노출 |
| `noInterrupts()`/`interrupts()` | P1 | 미구현 | 의미 차이 | system 전체 IRQ 차단을 남용하지 않도록 nesting/context 정책 정의 |
| ISR 안의 Arduino API 호출 | P0 | 부분 지원 | 부분 지원 | callback은 volatile/atomic flag만 권장; digital GPIO·Serial·sleep·heap/blocking API 금지, Serial ISR 거부 target test 통과 |

### 5.5 String, Print와 Stream

| API/영역 | 우선순위 | 현재 상태 | v0.1.0 목표 | 설계·검증 메모 |
| --- | --- | --- | --- | --- |
| `String` | P0 | 부분 지원 | 지원 | 1.5.2 source 생산 link, 연결·16진·실수 변환과 8192-byte libc arena 경계/실패 보존 target test 통과 |
| `Print` | P0 | 지원 | 지원 | 문자열·16진·CRLF 출력과 partial write 오류 target test 통과 |
| `Printable` | P0 | 지원 | 지원 | custom `printTo()` dispatch, byte 수 합산과 `println()` CRLF 의미를 NU54DK target ztest로 검증 |
| `Stream` | P0 | 지원 | 지원 | 정수·실수 parsing, `find()`와 timeout target test 통과 |
| `F()`/`__FlashStringHelper` | P1 | 의미 차이 | 의미 차이 | `String`/`Print` compile·link와 fixed-staging 출력 의미 시험, 기존 Print target 회귀 확인; nRF54에서는 AVR식 SRAM 절약을 제공하지 않음 |
| `PROGMEM`, `PSTR` | 제외 | 하드웨어 미지원 | 하드웨어 미지원 | AVR Harvard memory model을 모사하지 않음; compile shim 여부는 별도 호환 정책 |

### 5.6 Serial

| API/영역 | 우선순위 | 현재 상태 | v0.1.0 목표 | 설계·검증 메모 |
| --- | --- | --- | --- | --- |
| `HardwareSerial` interface | P0 | 지원 | 지원 | 1.5.2 `Stream` interface의 Zephyr UART backend, target ztest와 실제 COM10 echo HIL 통과 |
| 기본 `Serial` | P0 | 의미 차이 | 의미 차이 | `DT_CHOSEN(zephyr_console)` non-owning wrapper; UART20 115200 8N1 READY·고유 echo HIL 통과 |
| `begin()`/`end()` | P0 | 의미 차이 | 의미 차이 | 실제 UART config를 읽기만 하며 Arduino RX queue/callback만 시작·종료; device·baud·pinctrl 불변 |
| `available()`/`read()`/`peek()` | P0 | 지원 | 지원 | 128-byte IRQ RX queue, peek/read와 실제 line echo 통과 |
| `write()`/`availableForWrite()` | P0 | 부분 지원 | 부분 지원 | mutex로 직렬화한 polling TX, write 1 byte 공간 보고, ISR 거부; COM10 실제 TX PASS |
| `flush()` | P0 | 의미 차이 | 의미 차이 | polling TX 호출 완료를 보장하고 RX는 버리지 않음 |
| 동일 UART의 Zephyr shell RX 병행 | 제외 | 미구현 | 미구현 | v0.1.0에서 Arduino Serial RX와 동시에 사용하지 않음 |
| Serial config `SERIAL_8N1` 등 | P1 | 부분 지원 | 부분 지원 | M6는 115200 `SERIAL_8N1`만 허용; 다른 요청은 UART 재구성 없이 명시적으로 거부 |
| `Serial1`/uart30 | P2 | 미구현 | 미구현 | solder bridge와 선택 pinctrl 확인 후 별도 지원 |
| `SerialUSB`/USB CDC | 제외 | 하드웨어 미지원 | 하드웨어 미지원 | nRF54L15 target에 native USB peripheral 경로가 없음 |

### 5.7 I2C/Wire

| API/영역 | 우선순위 | 현재 상태 | v0.1.0 목표 | 설계·검증 메모 |
| --- | --- | --- | --- | --- |
| 기본 `Wire` controller | P1 | 부분 지원 | 부분 지원 | I2C22 P1.2/P1.3의 blocking controller; Core overlay의 NFC→GPIO 패드 전환과 chosen 누락 negative 통과, 다른 Zephyr client는 application 직렬화 필요 |
| `beginTransmission()`/`endTransmission()` | P1 | 부분 지원 | 부분 지원 | 32-byte 고정 TX buffer와 Arduino 상태 번호; `endTransmission(false)`는 단독 전송하지 않고 보류; zero-byte `endTransmission(true)` address probe는 driver에 전달 |
| `requestFrom()` | P1 | 부분 지원 | 부분 지원 | 32-byte 고정 RX buffer; `requestFrom(..., false)`는 미지원이며 0과 진단을 반환 |
| repeated-start | P1 | 지원 | 지원 | 같은 주소의 보류 write와 `requestFrom(..., true)` 결합 ztest 및 BQ25186 `MASK_ID` 실기 통과 |
| `setClock()` | P1 | 부분 지원 | 부분 지원 | 100 kHz와 400 kHz만 허용하며 target ztest와 BQ25186 실기에서 두 속도 검증 |
| target/slave mode | P2 | 미구현 | 미구현 | Zephyr driver capability 검토 후 결정 |
| `Wire1` 또는 임의 bus instance | P2 | 미구현 | 미구현 | 보드 overlay와 pin conflict 정책 필요 |

M7 I2C HIL image와 host protocol은 주소나 register를 외부 입력으로 받지 않고 온보드
BQ25186의 `0x6A/0x0C` read-only transaction만 실행한다. register pointer 뒤 STOP을 내지 않고
repeated-start로 한 byte를 읽으며 `MASK_ID & 0x0F == 0x1`을 판정한다. register data write,
주소 scan과 fallback은 제공하지 않는다. 범용 `Wire` Core backend 자체는 모든 정상 7-bit
주소를 전달한다.

현재 `endTransmission()` public status는 TX overflow=1, `-ETIMEDOUT`=5이며 그 밖의
negative driver errno는 공개 status 4로 변환한다. NACK을 address/data status 2·3으로 나누지 않으며 원래 errno는 비공개
진단에 보존한다. target ztest는 overflow와 `-EIO`→4를 검증했다.

### 5.8 SPI

| API/영역 | 우선순위 | 현재 상태 | v0.1.0 목표 | 설계·검증 메모 |
| --- | --- | --- | --- | --- |
| 기본 `SPI` controller | P1 | 부분 지원 | 부분 지원 | `SPIClass`/`SPISettings`, 전역 `SPIClass &SPI`; Core overlay와 production compile check가 SPI00 P2.1/P2.2/P2.4를 강제, 4 MHz 물리 loopback 통과 |
| `begin()`/`end()` | P1 | 부분 지원 | 부분 지원 | Devicetree compile-time 활성화 필요; non-SPI00 chosen과 SPI00/uart00 동시 활성 expected-fail 진단 통과 |
| `beginTransaction()`/`endTransaction()` | P1 | 부분 지원 | 부분 지원 | nrfx runtime prescaler predicate 선검증과 Core caller owner/state; Zephyr bus-wide lock 없음, 다른 client 공존은 application 직렬화 필요 |
| `transfer()`/buffer transfer | P1 | 부분 지원 | 지원 | 8-bit, 16-bit와 in-place buffer full-duplex 의미는 ztest 통과; 실제 SPI00 4 MHz에서 40-byte data 일치 확인 |
| SPI modes 0~3 | P1 | 부분 지원 | 지원 | config 변환 target ztest 통과; 외부 로직 계측은 완료 조건이 아님 |
| LSBFIRST | P1 | 부분 지원 | 부분 지원 | Zephyr word-order 설정 변환 target ztest 통과 |
| automatic chip select | P1 | 의미 차이 | 의미 차이 | Core는 CS를 만들거나 추정하지 않으며 Sketch가 별도 digital GPIO로 직접 제어 |
| 다중 SPI bus | P2 | 미구현 | 미구현 | 추가 instance와 pin mapping 결정 후 지원 |

P2.2 MOSI와 P2.4 MISO를 직접 연결한 실제 SPI00 4 MHz loopback에서 40-byte 고정 패턴이
전부 일치했다. 센서, 자동 chip-select 또는 외부 로직 계측을 이 결과로 주장하지 않는다.

### 5.9 Analog와 PWM

| API/영역 | 우선순위 | 현재 상태 | v0.1.0 목표 | 설계·검증 메모 |
| --- | --- | --- | --- | --- |
| `PIN_A0`/`A0` | P1 | 부분 지원 | 부분 지원 | 논리 index 2, `nucode,arduino-adc` chosen의 P1.12/SAADC channel 5; digital pin이 아님 |
| `analogRead()` | P1 | 부분 지원 | 부분 지원 | A0 고정 12-bit raw 0..4095와 오류 `-1`; gain 1/4 최종 실기 raw=3176 범위 확인, 전압 정확도 미검증 |
| `analogReadResolution()` | P1 | 미구현 | 미구현 | vendored ArduinoCore-API 1.5.2에 선언이 없어 M7에서 추가하지 않음 |
| `analogReference()` | P2 | 의미 차이 | 의미 차이 | `AR_DEFAULT=0`만 허용하고 `AR_INTERNAL`은 같은 값의 설명용 별칭; DTS gain/reference는 runtime 불변 |
| `PIN_PWM0`/`PIN_PWM_LED` | P1 | 부분 지원 | 부분 지원 | 논리 index 3, `nucode,arduino-pwm` chosen의 P1.10/pwm20 역할; `LED_BUILTIN` P2.9는 PWM이 아님 |
| `analogWrite()` | P1 | 부분 지원 | 부분 지원 | P1.10의 20 ms·8-bit만 지원; driver duty 0/128/255 통과, 실제 파형 미검증 |
| `analogWriteResolution()` | P1 | 미구현 | 미구현 | 고정 8-bit 계약이며 setter를 구현하지 않음 |
| PWM frequency extension | P2 | 미구현 | 미구현 | 표준 Arduino API 밖의 NU54DK extension으로 분리 |
| DAC output | 제외 | 하드웨어 미지원 | 하드웨어 미지원 | `analogWrite()`를 true DAC로 표현하지 않음 |

A0의 internal 0.6 V reference와 gain 1/4 조합은 nominal full-scale 약 2.4 V지만 이는 핀의
절대최대 정격이 아니다. M7은 raw 0..4095만 계약하며 정확도·saturation·안전 입력 전압은
nRF54L15와 NU54DK 전기 사양을 따른다.

### 5.10 Tone, Servo와 storage

| API/영역 | 우선순위 | 현재 상태 | v0.1.0 목표 | 설계·검증 메모 |
| --- | --- | --- | --- | --- |
| `tone()`/`noTone()` | P2 | 미구현 | 미구현 | PWM/timer 자원 예약과 충돌 정책 필요 |
| Servo library | P2 | 미구현 | 미구현 | PWM channel 수, period와 pin conflict 검증 필요 |
| EEPROM API | P3 | 미구현 | 미구현 | flash wear, settings/NVS backend 및 partition 설계 필요 |
| filesystem | P3 | 미구현 | 미구현 | flash device, partition 및 Arduino FS API를 별도 설계 |
| external flash | P3 | 미구현 | 미구현 | NU54DK 실장 여부와 overlay를 기준으로 결정 |

### 5.11 USB, network와 wireless

| API/영역 | 우선순위 | 현재 상태 | v0.1.0 목표 | 설계·검증 메모 |
| --- | --- | --- | --- | --- |
| `PluggableUSB`, `USBAPI` backend | 제외 | 하드웨어 미지원 | 하드웨어 미지원 | ArduinoCore-API header 포함 여부와 실제 backend 지원을 구분 |
| `Keyboard`, `Mouse` | 제외 | 하드웨어 미지원 | 하드웨어 미지원 | target native USB device 경로 없음 |
| `Client`, `Server`, `UDP` base class | P3 | 미구현 | 미구현 | base interface compile과 실제 transport 구현을 구분 |
| Wi-Fi/Ethernet | 제외 | 하드웨어 미지원 | 하드웨어 미지원 | 별도 network hardware 없이 기본 Core에서 제공하지 않음 |
| BLE Arduino API | P3 | 미구현 | 미구현 | NCS Bluetooth 사용 가능성과 Arduino library 호환은 별개 |
| 802.15.4/Thread/Matter | P3 | 미구현 | 미구현 | Zephyr/NCS 직접 API는 사용할 수 있으나 Arduino wrapper는 별도 프로젝트 |

---

## 6. NU54DK/Zephyr 확장 API 정책

Full Zephyr 방식의 자유도를 유지하기 위해 사용자는 Sketch에서 Zephyr/NCS 공개 API를 직접 include할 수 있다. 그러나 다음을 구분한다.

| 영역 | 예시 | 호환성 약속 |
| --- | --- | --- |
| Portable Arduino API | `digitalWrite`, `Wire`, `SPI` | API 지원표와 semantic test 적용 |
| NU54DK Arduino extension | pin conflict query, Zephyr handle accessor 등 | `nucode/` 또는 명시적 namespace/header 아래 version 관리 |
| Zephyr public API | `k_thread`, `gpio_dt_spec`, sensor API | 고정 Zephyr 4.4.0 범위에서 upstream 문서 적용 |
| NCS public API | Nordic subsystem API | NCS v3.4.0 범위에서만 검증 |
| internal/private API | 내부 Zephyr/NCS symbol | Core에서 가능한 한 사용 금지; 불가피하면 adapter 한 곳에 격리 |

Arduino library가 이식성을 유지하려면 Portable Arduino API만 사용해야 한다. Zephyr/NCS 직접 API를 사용하는 Sketch는 NU54DK Core의 장점이지만 다른 Arduino Core로 그대로 이동할 수 있다고 보장하지 않는다.

M14에서 `<nucode/Diagnostics.h>` 아래에 `Diagnostic`, subsystem/code token,
`lastDiagnostic()`과 `formatDiagnostic()`을 추가했다. 이 API는 동적 할당이나 logging 없이
`NU54:<subsystem>:<code>:driver=<n>:detail=<n>` ASCII 문자열을 만드는 순수 공개 값·포맷
계약이다. GPIO, Serial, Wire, SPI와 Analog backend가 활성화된 build에서는 비공개 마지막
오류를 공통 code와 driver errno로 읽는 비파괴 projection을 제공한다. Serial RX overflow의
`detail`에는 누적 drop byte 수를 넣는다. 별도 오류 저장소가 없는 Time, 비활성 backend와
오류 이력·event queue는 제공하지 않으며 target runtime/HIL 완료로 해석하지 않는다.

---

## 7. ArduinoCore-API 고정 계약

### 7.1 역할

ArduinoCore-API는 hardware-independent Arduino API 정의와 `String`, `Print`, `Stream` 같은 공통 구현을 제공하는 upstream 후보다. 다음을 대신하지 않는다.

- NU54DK pin mapping
- Zephyr GPIO/UART/I2C/SPI/ADC/PWM backend
- `setup()/loop()` thread 정책
- Arduino CLI와 west Build Adapter
- pyOCD/J-Link upload
- board package와 Kconfig/Devicetree profile

### 7.2 고정 revision과 배치

M4에서 다음 계약을 확정했다.

- upstream: `https://github.com/arduino/ArduinoCore-API.git`
- version/tag: `1.5.2`
- commit: `cd91833d90b4fe50e428021ba5051e2b7ceafc84`
- `ARDUINO_API_VERSION`: `10502`
- 배치: `third_party/ArduinoCore-API`
- 포함: 원본 LF의 `LICENSE`, `README.md`, `api/**` 48개 파일
- local modification: 없음
- provenance: `third_party/ArduinoCore-API.provenance.yml`
- notice: `third_party/THIRD_PARTY_NOTICES.md`

개발 중에도 `master` 또는 최신 branch를 직접 따라가지 않는다. upgrade는 별도 pull request에서 API 차이와 회귀 결과를 검토한다.

### 7.3 선택한 통합 방식

Boards Manager 단일 package의 설치·배포 단순성을 위해 **고정 vendored source**를 선택했다.
별도 Git submodule 또는 west dependency로 만들지 않는다. 대신 다음 규칙을 적용한다.

- upstream 파일은 직접 수정하지 않는다.
- vendor 경로 전체를 LF로 강제하고, 48개 파일 manifest checksum으로 무결성을 확인한다.
- Zephyr에는 vendor root만 system include로 추가한다. `api` 자체를 include root로 추가해
  `api/String.h`가 C library의 `string.h`를 가리는 Windows 경로 충돌을 만들지 않는다.
- 생산 `Arduino.h`는 M4에서 일괄 교체하지 않는다. upstream `Common.h`와 기존 runtime의
  linkage·type 계약은 M6에서 backend와 함께 통합한다.
- snapshot 변경은 version, commit, tree, checksum, notice와 계약 시험을 한 변경에서
  갱신하는 명시적 review로만 수행한다.

---

## 8. 라이선스 주의사항

고정 snapshot의 주 라이선스는 `LGPL-2.1-or-later`이며 `api/Udp.h`와
`api/deprecated-avr-comp/avr/pgmspace.h`는 MIT 고지를 포함한다. 따라서 component
license 표현은 `LGPL-2.1-or-later AND MIT`로 기록한다. 원본 `LICENSE`와 각 파일 header를
그대로 보존했으며 자세한 범위는 third-party notice와 provenance가 단일 원본이다.

NU54DK Arduino Core의 자체 작성 code에 MIT를 적용하더라도 ArduinoCore-API source가 MIT로 바뀌는 것은 아니다.

필수 관리 원칙은 다음과 같다.

- third-party source의 copyright와 license header를 제거하지 않는다.
- top-level MIT 표시와 third-party LGPL component를 명확히 구분한다.
- package에 ArduinoCore-API license 원문, 출처, 고정 revision 및 변경 내역을 포함한다.
- source를 수정하면 수정 파일과 patch를 식별할 수 있게 한다.
- source build 방식이 라이선스 준수에 유리할 수 있어도 자동으로 모든 의무가 충족된다고 가정하지 않는다.
- 정적 링크된 firmware binary, 예제 binary 또는 prebuilt archive를 배포할 때 필요한 source 제공·재링크 조건을 release 전에 검토한다.
- SBOM에 component, version, license 및 checksum을 기록한다.
- 이 문서는 법률 자문이 아니며, 공개 배포 전 실제 배포 형태를 기준으로 별도 검토한다.

참고 upstream: [arduino/ArduinoCore-API](https://github.com/arduino/ArduinoCore-API)

---

## 9. 호환성 검증 기준

### 9.1 `지원` 선언에 필요한 증거

API를 `지원`으로 바꾸려면 다음을 모두 통과해야 한다.

1. **Signature:** ArduinoCore-API 또는 승인된 Arduino reference와 동일한 호출 형태로 compile된다.
2. **Link:** west-native와 Arduino CLI Full Zephyr build에서 unresolved symbol 없이 링크된다.
3. **Semantic:** 정상, 경계값, timeout, 오류 및 반복 호출 결과가 정의와 일치한다.
4. **Context:** thread와 ISR에서 허용된 호출이 문서대로 동작하고 금지된 호출은 진단된다.
5. **Zephyr 공존:** 다른 Zephyr thread, logger 또는 같은 subsystem 사용자와의 소유권이 정의된다.
6. **Configuration:** v0.1.0의 `prj.conf`/overlay 또는 M13 검증 profile 변경이 정확히 반영되고 잘못된 profile은 build에서 실패한다.
7. **Hardware:** NU54DK 실기 또는 적절한 계측 fixture에서 검증한다.
8. **Regression:** 고정 test가 CI 또는 HIL 절차에 등록되고 결과를 보관한다.
9. **Documentation:** pin, timing, buffer, resource 및 hardware 제한을 예제와 reference에 기록한다.

### 9.2 `부분 지원` 선언에 필요한 증거

- 지원하는 pin, instance, mode, frequency, resolution 및 동시 사용 조합을 열거한다.
- 지원 범위 안의 positive test와 범위 밖의 negative test를 모두 둔다.
- 지원하지 않는 입력이 조용히 성공하지 않게 한다.
- 가능하면 configure/build-time error를 사용하고 runtime error만 가능한 경우 반환값과 log를 정의한다.

### 9.3 `의미 차이` 선언에 필요한 증거

- Arduino 일반 의미와 NU54DK/Zephyr 의미를 같은 표에서 비교한다.
- scheduler, timeout, buffer, flush, ISR context 또는 memory 관련 차이를 측정한다.
- 차이가 실제 Sketch에 주는 영향을 최소 예제로 제공한다.
- 호환 library corpus에서 해당 차이 때문에 실패하는 library를 기록한다.

### 9.4 호환성 시험 묶음

| 묶음 | 목적 |
| --- | --- |
| ArduinoCore-API upstream test | 공통 C++ class의 기본 동작 회귀 |
| host unit test | pin 변환, buffer, parser 및 순수 C++ logic |
| Zephyr ztest/Twister | Kconfig, Devicetree, scheduler와 compile 조합 |
| NU54DK HIL | 실제 GPIO, UART, I2C, SPI, ADC, PWM 및 interrupt |
| Arduino CLI smoke | `.ino` 전처리, library discovery, compile/upload |
| library corpus | hardware 독립 library와 대표 sensor library의 compile/runtime 호환 |
| negative test | 잘못된 pin, 비활성 controller, resource conflict 및 timeout 진단 |

---

## 10. Library 호환성 등급

Arduino library는 다음 등급으로 별도 관리한다.

| 등급 | 정의 | 예시 특성 |
| --- | --- | --- |
| L0 | hardware-independent | `Print`, `Stream`, parsing, math만 사용 |
| L1 | 표준 Core API만 사용 | GPIO, Wire, SPI, Serial 기반 일반 sensor library |
| L2 | architecture conditional 지원 | `ARDUINO_ARCH_*` 분기와 일부 extension 필요 |
| L3 | 다른 MCU register 또는 SDK에 직접 의존 | AVR register, ESP-IDF, mbed 전용 API 등 |

v0.1.0은 L0과 선정한 L1 library의 호환성을 목표로 했다. L2는 library별 patch 없이 동작한 경우만 기록하며, L3는 일반 호환 대상으로 선언하지 않는다.

호환성 표에는 다음을 기록한다.

- library 이름과 version
- license
- 사용 API
- compile 결과
- HIL 결과
- 필요한 M13 profile 또는 expert `prj.conf`/overlay
- known issue와 workaround
- 검증 Core/NCS/board revision

M13 profile 도입 이후 일반 Arduino 사용자는 `prj.conf`와 overlay를 직접 편집하지 않는다.
Arduino IDE에서 검증된 profile을 선택하면 Build Adapter가 필요한 Kconfig와 Devicetree
구성을 적용한다. 직접 Zephyr/NCS API 또는 사용자 conf·overlay를 쓰는 expert escape hatch는
유지하되, 해당 조합은 기본 profile 지원과 구분하여 위 호환성 표와 시험 증거에 기록한다.

---

## 11. 상태 변경 절차

1. 구현 pull request에 API 표의 대상 행을 명시한다.
2. host/ztest/HIL/Arduino CLI 중 필요한 test를 추가한다.
3. test report에 Core, board submodule, NCS 및 Toolchain revision을 기록한다.
4. reviewer가 signature, 의미와 hardware 제한을 확인한다.
5. 증거가 병합된 뒤에만 `미구현`을 다른 상태로 변경한다.
6. regression으로 의미가 깨지면 상태를 즉시 `부분 지원` 또는 `미구현`으로 내리고 release note에 기록한다.

`지원` 상태는 영구 보장이 아니라 고정 compatibility matrix에서 검증된 사실이다. NCS, Zephyr, ArduinoCore-API 또는 board revision이 바뀌면 영향받는 상태를 다시 검증한다.
