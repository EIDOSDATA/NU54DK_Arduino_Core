# NU54DK Arduino API 지원 범위

| 항목 | 내용 |
| --- | --- |
| 문서 상태 | M3 최소 Runtime/GPIO/시간 구현 — 제한적 NU54DK HIL 통과 |
| 작성자 | Quantum / NUCODE |
| 기준 SDK | nRF Connect SDK v3.4.0 |
| 기준 Zephyr | Zephyr 4.4.0 |
| 기준 보드 | `nrf54l15dk/nrf54l15/cpuapp/nu54dk` |
| API 기준 후보 | ArduinoCore-API 고정 revision — M4에서 확정 |
| Core 자체 라이선스 목표 | MIT — third-party component에는 각각의 원 라이선스 적용 |

---

## 1. 문서 목적

이 문서는 NU54DK Arduino Core가 어떤 Arduino API를 어느 수준까지 제공할지 정의한다. API 이름이나 header가 존재한다는 이유만으로 `지원`이라고 선언하지 않는다. 실제 상태, v0.1 목표, 하드웨어 제약 및 검증 증거를 분리하여 관리한다.

현재 저장소에는 M3 최소 Runtime, GPIO와 시간 backend가 존재한다. 그러나 source와 symbol이
존재한다는 사실만으로 `지원`이라고 선언하지 않는다. 아래 표에서 M3 build/HIL 증거가
있는 제한 범위만 `부분 지원` 또는 `의미 차이`로 표시하고, 구현됐어도 의미·문맥 검증이
끝나지 않은 API는 `미구현` 상태를 유지한다. v0.1 목표 상태는 완료 보고가 아니다.

관련 문서는 다음과 같다.

- [구현 로드맵](02_구현_로드맵.md)
- [테스트와 검증](../03_펌웨어%20설계/04_테스트와_검증.md)

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
| P0 | Core 사용과 기본 Sketch 실행에 필수 | v0.1 공개 후보의 필수 완료 항목 |
| P1 | 일반적인 센서·통신·아날로그 Sketch에 필요한 핵심 기능 | v0.1 목표. 부분 지원이나 의미 차이는 허용하되 미구현이면 release note에 명시하고 공개 범위를 재결정 |
| P2 | 유용하지만 초기 수직 경로를 막지 않는 기능 | v0.1 이후 순차 구현 |
| P3 | 별도 subsystem, 대규모 library 또는 제품 정책이 필요한 기능 | 별도 설계 승인 후 구현 |
| 제외 | 현재 하드웨어·아키텍처와 맞지 않거나 호환을 약속하지 않음 | 구현 계획 없음 또는 대체 API 안내 |

---

## 4. v0.1 지원 범위

### 4.1 v0.1 필수 범위

v0.1에서 반드시 끝까지 검증할 P0 범위는 다음과 같다.

- `Arduino.h`의 기본 정수형, 상수 및 utility
- `setup()`과 `loop()` runtime
- `pinMode()`, `digitalRead()`, `digitalWrite()`
- `millis()`, `micros()`, `delay()`, `delayMicroseconds()`, `yield()`
- ArduinoCore-API의 `String`, `Print`, `Printable`, `Stream`
- uart20/DAP UART 기반 기본 `Serial`
- `attachInterrupt()`, `detachInterrupt()` 및 interrupt mode
- Arduino CLI Full Zephyr compile 및 pyOCD/CMSIS-DAP upload

P0는 단순 Blink 한 개가 아니라 각 API의 signature, edge case, scheduler 공존 및 실기 결과를 포함한다.

### 4.2 v0.1 목표 범위

P1은 v0.1에서 구현을 목표로 하지만 하드웨어 특성상 `부분 지원`이나 `의미 차이`가 될 수 있다.

- `Wire`/I2C22
- `SPI`/SPI00
- `analogRead()`와 ADC resolution
- `analogWrite()`와 PWM
- `random()`, `randomSeed()`, `map()`, `constrain()`, `min()`, `max()`
- `noInterrupts()`와 `interrupts()`의 Zephyr-safe 의미
- 대표 범용 Arduino library compile corpus

v0.1 release gate에서 P1이 미구현으로 남으면 기능명을 조용히 노출하지 않는다. `Arduino.h` 또는 전역 객체는 존재하지만 항상 실패하는 형태보다, compile-time diagnostic과 정확한 지원표를 우선한다.

### 4.3 v0.1 제외 범위

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

표의 `현재 상태`는 이 문서 작성 시점의 구현 증거를 나타낸다. `v0.1 목표`는 완료 후 기대 상태다. 목표 상태가 `의미 차이` 또는 `부분 지원`이면 차이를 없애겠다는 뜻이 아니라 정확히 문서화하고 시험하겠다는 뜻이다.

### 5.0 M3 검증 경계

현재 Variant는 다음 두 논리 핀만 제공한다.

| index | 이름 | Devicetree 원본 | capability |
| ---: | --- | --- | --- |
| 0 | `LED_BUILTIN` | `DT_ALIAS(led0)` | digital input + output |
| 1 | `PIN_BUTTON0` | `DT_ALIAS(sw0)` | digital input only |

`NUM_DIGITAL_PINS`는 2다. GPIO controller, 실제 pin과 flag는 DTS에서 생성하며 Variant에
복제하지 않는다. 공개 GPIO API는 thread-only이고 ISR에서는 no-op 또는 `LOW`다. mode,
output latch와 마지막 오류는 private atomic 상태로 관리하며 공개 진단 API는 없다.

M3 NU54DK HIL에서는 Arduino API만 사용하는 250 ms Blink와 `INPUT_PULLUP` 버튼의 raw
해제 `HIGH`/누름 `LOW`, 버튼-LED 연동을 확인했다. invalid pin 호출이 LED 상태를 바꾸지
않는 sample self-check도 포함한다. logic analyzer 정량 측정, ztest/Twister, Arduino CLI,
ISR, 동시 호출, input `digitalWrite()`, ownership와 interrupt는 아직 검증 또는 구현되지
않았다.

### 5.1 Runtime과 기본 형식

| API/영역 | 우선순위 | 현재 상태 | v0.1 목표 | 설계·검증 메모 |
| --- | --- | --- | --- | --- |
| `Arduino.h` include | P0 | 부분 지원 | 지원 | M3 Runtime/GPIO/시간 최소 계약만 제공; ArduinoCore-API 통합과 일반 library compile 미검증 |
| `setup()` | P0 | 부분 지원 | 지원 | 전역 constructor 이후 한 번 실행하는 M2/M3 HIL 통과; Arduino CLI 회귀 미검증 |
| `loop()` | P0 | 의미 차이 | 의미 차이 | Zephyr main thread에서 반복하고 기본적으로 반환 뒤 한 tick sleep; 네 scheduler 단계의 fairness/idle 정량 HIL 통과, Arduino CLI·PM 회귀 미검증 |
| `yield()` | P0 | 의미 차이 | 의미 차이 | guarded `k_yield()`이며 같은 priority worker는 진행했지만 낮은 priority와 idle은 진행하지 못함; yield 불가능 문맥에서는 no-op |
| `init()`/`initVariant()` 내부 hook | P0 | 부분 지원 | 부분 지원 | weak no-op `initVariant()`와 override 계약만 구현; 실제 Variant override 없음 |
| `HIGH`, `LOW`, `INPUT`, `OUTPUT` | P0 | 부분 지원 | 지원 | LED output과 raw HIGH/LOW HIL 통과; 전체 핀/mode 조합 미검증 |
| `INPUT_PULLUP`, `INPUT_PULLDOWN` | P0 | 부분 지원 | 지원 | 버튼 `INPUT_PULLUP` HIL 통과; pull-down과 전체 핀 조합 미검증 |
| `LSBFIRST`, `MSBFIRST`, interrupt mode 상수 | P0/P1 | 미구현 | 지원 | `RISING`/`FALLING`/`CHANGE` 값만 존재; interrupt backend와 bit-order 상수 미구현 |
| `byte`, `word`, `boolean` 등 호환 type | P0 | 미구현 | 지원 | fixed-width type와 overload compile test |
| C++ static object initialization | P0 | 부분 지원 | 지원 | 시험용 전역 constructor 선행 실행 HIL 통과; `Serial`, `Wire`, `SPI` 객체는 미구현 |
| C++ exception/RTTI | P1 | 미구현 | 의미 차이 | enable 구성의 compile/link만 확인; 실제 throw/RTTI/heap 의미는 미검증 |

### 5.2 Digital I/O

| API/영역 | 우선순위 | 현재 상태 | v0.1 목표 | 설계·검증 메모 |
| --- | --- | --- | --- | --- |
| `pinMode()` | P0 | 부분 지원 | 지원 | index 0/1에서 capability가 허용하는 input/pull/output만 thread에서 구현; open-drain, ISR, ownership 미구현 |
| `digitalWrite()` | P0 | 부분 지원 | 지원 | `OUTPUT`으로 구성된 index 0에서 raw write HIL 통과; input pull 전환, ISR, ownership 미구현 |
| `digitalRead()` | P0 | 부분 지원 | 지원 | LED readback self-check 후 버튼 loop 진입을 육안 확인; 정확한 RAM trace는 미회수, index 0/1 및 thread 문맥으로 제한 |
| `LED_BUILTIN` | P0 | 부분 지원 | 지원 | index 0, DTS `led0`, input+output; Blink HIL 통과, 정량 timing/voltage 미측정 |
| `PIN_BUTTON0` | P0 | 부분 지원 | 부분 지원 | index 1, DTS `sw0`, input-only; pull-up raw 버튼 HIL 통과, debounce/interrupt 미구현 |
| 전체 `D0...Dn` 논리 pin map | P1 | 미구현 | 부분 지원 | 회로에 노출되고 안전하게 사용할 수 있는 pin만 정의 |
| `digitalPinToInterrupt()` | P0 | 미구현 | 지원 | pin mapping과 interrupt capability 검증 |
| direct port/register access | 제외 | 하드웨어 미지원 | 하드웨어 미지원 | AVR/SAMD register 호환을 제공하지 않음; Zephyr/nrfx 직접 API는 별도 영역 |

### 5.3 시간과 utility

| API/영역 | 우선순위 | 현재 상태 | v0.1 목표 | 설계·검증 메모 |
| --- | --- | --- | --- | --- |
| `millis()` | P0 | 부분 지원 | 지원 | uptime backend, `delay(20)`의 20 ms 경과와 timer ISR 반복 읽기 HIL 통과; 실제 wrap·PM 장기 연속성 미검증 |
| `micros()` | P0 | 부분 지원 | 부분 지원 | GRTC startup offset을 뺀 64-bit cycle backend와 timer ISR 반복 읽기 HIL 통과; 외부 resolution·실제 wrap·PM 미검증 |
| `delay()` | P0 | 의미 차이 | 의미 차이 | 64-bit deadline sleep, 20 ms/20,084 us 내부 계측과 worker 공존 HIL 통과; 긴 `INT32_MAX` chunk와 금지 문맥 진단 미검증 |
| `delayMicroseconds()` | P0 | 의미 차이 | 의미 차이 | 1초 chunk busy-wait의 1,000 us 요청을 내부에서 1,026 us로 측정; ISR에서는 no-op이며 외부 정확도·긴 chunk 경계 미검증 |
| `map()` | P1 | 미구현 | 지원 | ArduinoCore-API 구현 재사용 후보, overflow 특성 포함 |
| `constrain()`, `min()`, `max()`, `abs()` | P1 | 미구현 | 지원 | macro/template 충돌 및 type test |
| `bitRead`, `bitWrite`, `bitSet`, `bitClear` | P1 | 미구현 | 지원 | compile 및 정수 폭 test |
| `random()`, `randomSeed()` | P1 | 미구현 | 의미 차이 | PRNG 선택과 hardware entropy 사용 여부를 공개 |
| `pulseIn()`, `pulseInLong()` | P2 | 미구현 | 미구현 | timeout, scheduler 및 timing 오차 설계 후 추가 |
| `shiftIn()`, `shiftOut()` | P2 | 미구현 | 미구현 | software timing 기반 reference implementation 검토 |

### 5.4 Interrupt

| API/영역 | 우선순위 | 현재 상태 | v0.1 목표 | 설계·검증 메모 |
| --- | --- | --- | --- | --- |
| `attachInterrupt()` | P0 | 미구현 | 의미 차이 | M3 pin descriptor에는 interrupt capability/backend가 없음; callback 문맥과 lifetime 설계 필요 |
| `detachInterrupt()` | P0 | 미구현 | 지원 | pending callback과 detach 경쟁 상태 시험 |
| `RISING`, `FALLING`, `CHANGE` | P0 | 미구현 | 지원 | enum 값만 존재하며 실제 interrupt 동작은 없음; 신호 발생기/버튼 edge 검증 필요 |
| `LOW`, `HIGH` level interrupt | P1 | 미구현 | 부분 지원 | Zephyr/nRF hardware와 driver가 안정적으로 제공하는 mode만 노출 |
| `noInterrupts()`/`interrupts()` | P1 | 미구현 | 의미 차이 | system 전체 IRQ 차단을 남용하지 않도록 nesting/context 정책 정의 |
| ISR 안의 Arduino API 호출 | P0 | 미구현 | 부분 지원 | M3 GPIO 세 API는 ISR에서 모두 거부; ISR-safe API 목록과 자동 negative test 미구현 |

### 5.5 String, Print와 Stream

| API/영역 | 우선순위 | 현재 상태 | v0.1 목표 | 설계·검증 메모 |
| --- | --- | --- | --- | --- |
| `String` | P0 | 미구현 | 지원 | ArduinoCore-API source와 upstream test 재사용 후보, heap failure 시험 |
| `Print` | P0 | 미구현 | 지원 | 정수/부동소수/진법/부분 write 동작 시험 |
| `Printable` | P0 | 미구현 | 지원 | custom printable compile/runtime test |
| `Stream` | P0 | 미구현 | 지원 | timeout, parse, find 및 partial input 시험 |
| `F()`/`__FlashStringHelper` | P1 | 미구현 | 의미 차이 | nRF54의 통합 address space에서 AVR flash 절약 의미가 동일하지 않음 |
| `PROGMEM`, `PSTR` | 제외 | 하드웨어 미지원 | 하드웨어 미지원 | AVR Harvard memory model을 모사하지 않음; compile shim 여부는 별도 호환 정책 |

### 5.6 Serial

| API/영역 | 우선순위 | 현재 상태 | v0.1 목표 | 설계·검증 메모 |
| --- | --- | --- | --- | --- |
| `HardwareSerial` interface | P0 | 미구현 | 지원 | ArduinoCore-API signature와 Zephyr UART backend 연결 |
| 기본 `Serial` | P0 | 미구현 | 의미 차이 | `DT_CHOSEN(zephyr_console)`의 non-owning wrapper; device init/pinctrl/baud/lifetime은 Zephyr 소유 |
| `begin()`/`end()` | P0 | 미구현 | 의미 차이 | Arduino buffer/lifecycle만 다루며 Zephyr console device를 재초기화하거나 baud/pinctrl을 소유하지 않음 |
| `available()`/`read()`/`peek()` | P0 | 미구현 | 지원 | RX buffer overflow, timeout 및 동시 access 시험 |
| `write()`/`availableForWrite()` | P0 | 미구현 | 부분 지원 | backend buffer 크기와 ISR 호출 제한 공개 |
| `flush()` | P0 | 미구현 | 의미 차이 | TX 완료 의미를 명확히 하고 RX discard로 해석하지 않음 |
| 동일 UART의 Zephyr shell RX 병행 | 제외 | 미구현 | 미구현 | v1에서 Arduino Serial RX와 동시에 사용하지 않음 |
| Serial config `SERIAL_8N1` 등 | P1 | 미구현 | 부분 지원 | Zephyr UART가 허용하는 data/parity/stop 조합만 제공 |
| `Serial1`/uart30 | P2 | 미구현 | 미구현 | solder bridge와 선택 pinctrl 확인 후 별도 지원 |
| `SerialUSB`/USB CDC | 제외 | 하드웨어 미지원 | 하드웨어 미지원 | nRF54L15 target에 native USB peripheral 경로가 없음 |

### 5.7 I2C/Wire

| API/영역 | 우선순위 | 현재 상태 | v0.1 목표 | 설계·검증 메모 |
| --- | --- | --- | --- | --- |
| 기본 `Wire` master | P1 | 미구현 | 지원 | i2c22와 canonical SDA/SCL 사용 |
| `beginTransmission()`/`endTransmission()` | P1 | 미구현 | 지원 | Arduino error code와 Zephyr errno mapping 시험 |
| `requestFrom()` | P1 | 미구현 | 지원 | partial read, zero length 및 timeout 시험 |
| repeated-start | P1 | 미구현 | 지원 | `endTransmission(false)` 뒤 read를 HIL로 검증 |
| `setClock()` | P1 | 미구현 | 부분 지원 | controller와 bus가 지원하는 표준 속도만 보장 |
| target/slave mode | P2 | 미구현 | 미구현 | Zephyr driver capability 검토 후 결정 |
| `Wire1` 또는 임의 bus instance | P2 | 미구현 | 미구현 | 보드 overlay와 pin conflict 정책 필요 |

### 5.8 SPI

| API/영역 | 우선순위 | 현재 상태 | v0.1 목표 | 설계·검증 메모 |
| --- | --- | --- | --- | --- |
| 기본 `SPI` controller | P1 | 미구현 | 부분 지원 | spi00은 기본 DTS에서 비활성이므로 Core profile overlay 필요 |
| `begin()`/`end()` | P1 | 미구현 | 부분 지원 | Devicetree compile-time 활성화와 runtime API의 경계 공개 |
| `beginTransaction()`/`endTransaction()` | P1 | 미구현 | 지원 | mode, bit order, frequency 설정의 원자성과 lock 시험 |
| `transfer()`/buffer transfer | P1 | 미구현 | 지원 | full-duplex와 in-place buffer 시험 |
| SPI modes 0~3 | P1 | 미구현 | 지원 | logic analyzer로 CPOL/CPHA 검증 |
| LSBFIRST | P1 | 미구현 | 부분 지원 | hardware 지원 또는 software conversion 비용 측정 후 결정 |
| automatic chip select | P1 | 미구현 | 의미 차이 | Arduino Sketch가 관리하는 GPIO CS와 Zephyr DT CS 정책을 구분 |
| 다중 SPI bus | P2 | 미구현 | 미구현 | 추가 instance와 pin mapping 결정 후 지원 |

### 5.9 Analog와 PWM

| API/영역 | 우선순위 | 현재 상태 | v0.1 목표 | 설계·검증 메모 |
| --- | --- | --- | --- | --- |
| `analogRead()` | P1 | 미구현 | 부분 지원 | 실제 ADC channel로 매핑된 Arduino analog pin만 지원 |
| `analogReadResolution()` | P1 | 미구현 | 부분 지원 | nRF SAADC/Zephyr가 제공하는 resolution 집합만 허용 |
| `analogReference()` | P2 | 미구현 | 의미 차이 | nRF reference/gain 모델을 Arduino 의미로 매핑할지 별도 결정 |
| `analogWrite()` | P1 | 미구현 | 부분 지원 | PWM이 연결된 pin만 지원; DAC 의미를 제공하지 않음 |
| `analogWriteResolution()` | P1 | 미구현 | 부분 지원 | period와 duty 계산 가능 범위 및 rounding 공개 |
| PWM frequency extension | P2 | 미구현 | 미구현 | 표준 Arduino API 밖의 NU54DK extension으로 분리 |
| DAC output | 제외 | 하드웨어 미지원 | 하드웨어 미지원 | `analogWrite()`를 true DAC로 표현하지 않음 |

### 5.10 Tone, Servo와 storage

| API/영역 | 우선순위 | 현재 상태 | v0.1 목표 | 설계·검증 메모 |
| --- | --- | --- | --- | --- |
| `tone()`/`noTone()` | P2 | 미구현 | 미구현 | PWM/timer 자원 예약과 충돌 정책 필요 |
| Servo library | P2 | 미구현 | 미구현 | PWM channel 수, period와 pin conflict 검증 필요 |
| EEPROM API | P3 | 미구현 | 미구현 | flash wear, settings/NVS backend 및 partition 설계 필요 |
| filesystem | P3 | 미구현 | 미구현 | flash device, partition 및 Arduino FS API를 별도 설계 |
| external flash | P3 | 미구현 | 미구현 | NU54DK 실장 여부와 overlay를 기준으로 결정 |

### 5.11 USB, network와 wireless

| API/영역 | 우선순위 | 현재 상태 | v0.1 목표 | 설계·검증 메모 |
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

---

## 7. ArduinoCore-API 검토 계획

### 7.1 역할

ArduinoCore-API는 hardware-independent Arduino API 정의와 `String`, `Print`, `Stream` 같은 공통 구현을 제공하는 upstream 후보다. 다음을 대신하지 않는다.

- NU54DK pin mapping
- Zephyr GPIO/UART/I2C/SPI/ADC/PWM backend
- `setup()/loop()` thread 정책
- Arduino CLI와 west Build Adapter
- pyOCD/J-Link upload
- board package와 Kconfig/Devicetree profile

### 7.2 revision 고정

M4에서 다음 정보를 dependency manifest에 기록한다.

- upstream URL
- tag와 정확한 commit SHA
- Arduino API version macro
- 가져온 파일 목록 또는 dependency 배치 방식
- local patch 유무와 patch 출처
- upstream test revision과 실행 결과
- license 원문 checksum

개발 중에도 `master` 또는 최신 branch를 직접 따라가지 않는다. upgrade는 별도 pull request에서 API 차이와 회귀 결과를 검토한다.

### 7.3 통합 선택지

| 방식 | 장점 | 주의사항 |
| --- | --- | --- |
| Git submodule | 출처와 revision이 분명함 | release archive staging과 사용자 clone 절차 필요 |
| west module/dependency | NCS workspace와 잘 결합 | Arduino Boards Manager package에 실제 source를 포함하는 별도 단계 필요 |
| vendored source | 단일 package 배포가 단순함 | upstream 추적, local patch, 라이선스와 source 변경 고지를 엄격히 관리 |

어떤 방식을 선택해도 공개 package에는 빌드에 필요한 실제 source와 해당 license/notice가 포함되어야 한다.

---

## 8. 라이선스 주의사항

ArduinoCore-API upstream은 이 문서의 확인 시점에 GNU LGPL 2.1 계열 라이선스로 공개되어 있으며, 여러 source header는 `version 2.1 or later` 문구를 포함한다. 최종 적용 조건은 **M4에서 고정한 revision의 `LICENSE`와 개별 파일 header**를 기준으로 다시 확인한다.

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
6. **Configuration:** `prj.conf`와 overlay 변경이 정확히 반영되고 잘못된 profile은 build에서 실패한다.
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

v0.1은 L0과 선정한 L1 library의 호환성을 목표로 한다. L2는 library별 patch 없이 동작한 경우만 기록하며, L3는 일반 호환 대상으로 선언하지 않는다.

호환성 표에는 다음을 기록한다.

- library 이름과 version
- license
- 사용 API
- compile 결과
- HIL 결과
- 필요한 `prj.conf`/overlay
- known issue와 workaround
- 검증 Core/NCS/board revision

---

## 11. 상태 변경 절차

1. 구현 pull request에 API 표의 대상 행을 명시한다.
2. host/ztest/HIL/Arduino CLI 중 필요한 test를 추가한다.
3. test report에 Core, board submodule, NCS 및 Toolchain revision을 기록한다.
4. reviewer가 signature, 의미와 hardware 제한을 확인한다.
5. 증거가 병합된 뒤에만 `미구현`을 다른 상태로 변경한다.
6. regression으로 의미가 깨지면 상태를 즉시 `부분 지원` 또는 `미구현`으로 내리고 release note에 기록한다.

`지원` 상태는 영구 보장이 아니라 고정 compatibility matrix에서 검증된 사실이다. NCS, Zephyr, ArduinoCore-API 또는 board revision이 바뀌면 영향받는 상태를 다시 검증한다.
