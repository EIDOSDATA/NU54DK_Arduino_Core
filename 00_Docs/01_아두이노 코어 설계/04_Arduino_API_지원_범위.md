# NU54DK Arduino API 지원 범위

| 항목 | 내용 |
| --- | --- |
| 문서 ID | CORE-API-001 |
| 문서 개정 | 4.2 |
| 문서 상태 | `v0.2.0` 정식 공개 범위 + `v0.3.0` 개발 상태 |
| 최종 갱신일 | 2026-08-31 |
| 다음 확장 | `v0.3.0` AC-01~AC-03 Arduino Compatibility / M19~M21 BLE |

## 1. 목적

이 문서는 설치된 `v0.2.0` package가 약속하는 Arduino API와 다음 `v0.3.0` working tree의
구현 상태를 구분한다. 실행 횟수, 메모리 크기, UART transcript와 commit 같은 증거는
`04_검증 기록`이 소유하며 이 문서에는 현재 계약과 결과 링크만 둔다.

Arduino 호환 header에 이름이 존재하는 것, target에서 compile되는 것, 실제 hardware에서
지원되는 것은 서로 다른 판정이다. 특히 Zephyr/NCS sample의 build 성공을 Arduino wrapper의
runtime 지원으로 확대하지 않는다.

## 2. 지원 상태

| 상태 | 의미 |
| --- | --- |
| 지원 | 공개 계약 전체를 구현하고 필요한 자동 시험 또는 HIL을 통과 |
| 부분 지원 | 명시한 하위 범위만 구현·검증 |
| 의미 차이 | 이름은 호환되지만 Zephyr/NU54DK에서 동작 의미가 다름 |
| 미구현 | 공개 이름 또는 backend를 제품 지원으로 제공하지 않음 |
| 하드웨어 미지원 | target hardware에 필요한 peripheral 경로가 없음 |
| 전문가 opt-in | 기본 profile 밖에서 build·semantic 검증은 했지만 정식 제품 profile은 아님 |
| build-only | 고정 환경에서 compile/build만 확인; runtime 지원 아님 |

미구현 기능을 `지원 예정`으로 표시하지 않는다. 확정된 다음 단계도 현재 상태 열에서는 계속
`미구현`이다.

### 2.1 제품 완료와 전체 호환 폭

`v0.2.0`은 RC가 아닌 정식 제품 릴리스이며, 설치·빌드·업로드, `setup()`/`loop()`, 공개한
14개 예제와 아래에 `지원`으로 선언한 수직 기능은 완료·검증됐다. 다만 Arduino는 보드마다
물리 peripheral과 Core 확장 범위가 다르므로, 다음 두 판정을 같은 말로 취급하지 않는다.

| 판정 축 | `v0.2.0` 판정 | 의미 |
| --- | --- | --- |
| 선언한 제품 범위 | 완료 | 공개 API·예제·package와 필요한 자동 시험/HIL을 보유 |
| Arduino 전체 API 호환 폭 | 부분 | 일부 Common API, 추가 bus, USB·storage와 범용 BLE 계층은 미구현 또는 하드웨어 미지원 |
| 제3자 library 생태계 | 제한 검증 | 고정한 대표 library만 compile 검증; 전체 library 호환 보증 아님 |

따라서 `부분 지원`은 Core 전체가 불안정하다는 뜻이 아니라, 특정 API 행에서 보증하는 pin, mode,
bus instance 또는 검증 범위가 Arduino 생태계 전체보다 좁다는 뜻이다.

## 3. Runtime과 공통 API

| API/영역 | `v0.2.0` 상태 | 계약 |
| --- | --- | --- |
| `Arduino.h`, 공통 type·상수 | 지원 | ArduinoCore-API 1.5.2 기반 공개 형식과 C/C++ 계약 |
| `setup()` | 지원 | 정적 초기화와 `initVariant()` 뒤 main thread에서 한 번 호출 |
| `loop()` | 의미 차이 | Zephyr main thread에서 반복; 기본 post-loop는 한 kernel tick sleep |
| `serialEventRun()` | 지원 | symbol이 있으면 각 `loop()` 뒤 post-loop 정책보다 먼저 호출 |
| `yield()` | 의미 차이 | yield 가능한 thread 문맥에서 `k_yield()`; 금지 문맥은 no-op |
| `String` | 지원 | bounded libc heap을 사용하는 upstream 구현; embedded heap 한계상 allocation 실패 가능 |
| `Print`, `Printable`, `Stream` | 지원 | 생산 backend와 target 계약 제공 |
| `F()`/`__FlashStringHelper` | 의미 차이 | compile 호환은 제공하지만 AVR식 SRAM 절약은 없음 |
| `PROGMEM`, `PSTR` | 하드웨어 미지원 | AVR Harvard memory model을 모사하지 않음 |
| C++ exception/RTTI | 전문가 opt-in | 기본 profile에서는 비활성; 별도 시험 구성에서 unwind와 RTTI semantic 검증 |

Vendored ArduinoCore-API가 type/header를 제공한다는 사실만으로 production backend까지 지원한다고
판정하지 않는다. 현재 공통 구현으로 연결한 것은 `Common`, `Print`, `Stream`, `String` 계열이며,
`IPAddress`, `Client`, `Server`, `Udp`, `PluggableUSB`와 USB backend는 제품 지원 범위가 아니다.

## 4. 핀, GPIO와 interrupt

| API/영역 | `v0.2.0` 상태 | 계약 |
| --- | --- | --- |
| `pinMode()` | 부분 지원 | sparse digital descriptor 7개의 지원 mode·capability만 허용 |
| `digitalWrite()` | 부분 지원 | output capability와 `OUTPUT` 상태가 있는 LED 역할만 raw write |
| `digitalRead()` | 부분 지원 | digital descriptor의 raw electrical level 반환; thread 문맥 전용 |
| `digitalPinIsValid()` | 지원 | ID `0,1,5,6,7,8,9`만 참 |
| `digitalPinToInterrupt()` | 지원 | digital-capable ID 또는 `NOT_AN_INTERRUPT` 반환 |
| `attachInterrupt()`/`attachInterruptParam()` | 의미 차이 | 고정 slot의 GPIO ISR에서 callback 실행 |
| `detachInterrupt()` | 지원 | 등록 해제와 진행 중 callback 정리 |
| `RISING`, `FALLING`, `CHANGE` | 지원 | raw electrical edge |
| `OUTPUT_OPENDRAIN` | 미구현 | type에는 존재하지만 현재 GPIO backend가 mode를 받지 않음 |
| level `LOW`/`HIGH` interrupt | 미구현 | 공개 지원하지 않음 |
| `noInterrupts()`/`interrupts()` | 미구현 | Zephyr nested IRQ 의미를 불완전하게 모사하지 않음 |

핀 번호는 연속 digital descriptor 배열이 아니다. `NUM_DIGITAL_PINS=10`은 공개 ID 범위이고
실제 digital-capable 핀은 7개다. `PIN_A0=2`, `PIN_PWM0=3`, `PIN_LED1=4`는 이 범위 안의
예약 역할이며 digital descriptor가 없다. 자세한 계약은
[핀과 Variant 설계](./03_핀과_Variant_설계.md)를 따른다.

### 4.1 `v0.3.0` AC-01 working tree

아래 항목은 source 구현, host 계약과 NU54DK production target build를 통과했다. 정식 `지원`
선언은 P2.5↔P2.6 loopback HIL과 릴리스 gate가 끝난 뒤 적용한다. Level IRQ는 P2 connector가 아니라
GPIOTE가 있는 P0/P1 역할에만 적용하며 SW0 P1.13 자기구동 실기는 통과했다.

| API/영역 | 개발 상태 | AC-01 계약 |
| --- | --- | --- |
| `PIN_GPIO0/D10`, `PIN_GPIO1/D11` | 구현·target build | P2.5/P2.6 input/output/open-drain; GPIOTE가 없어 interrupt는 `NOT_AN_INTERRUPT` |
| `OUTPUT_OPENDRAIN` | 구현·target build | connector 두 핀만 허용; `HIGH`는 high-Z release, pull-up은 fixture/회로 책임 |
| level `LOW`/`HIGH` interrupt | 구현·target·SW0 HIL | GPIOTE P0/P1에서 hold one-shot, deassert 뒤 1 ms work polling 재무장 |
| `noInterrupts()`/`interrupts()` | 구현·target build | 같은 thread의 중첩 계약; Arduino GPIO callback만 mask하고 system/BLE/driver IRQ는 유지 |

Mask 중 assert된 level은 마지막 복원 뒤 raw 상태를 다시 확인해 재무장한다. 짝이 없는
`interrupts()`, 다른 thread의 복원, 중첩 overflow는 hardware를 임의 변경하지 않고 공개 GPIO
진단으로 보고한다.

## 5. 시간과 utility

| API/영역 | `v0.2.0` 상태 | 계약 |
| --- | --- | --- |
| `millis()` | 지원 | Zephyr uptime 기반 32-bit 반환; rollover 차분과 긴 delay 경계 자동 시험 |
| `micros()` | 지원 | nRF54 GRTC cycle 기반 32-bit 반환; 외부 clock 계측기 정확도는 보증하지 않음 |
| `delay()` | 의미 차이 | 64-bit deadline을 사용해 current thread를 sleep |
| `delayMicroseconds()` | 의미 차이 | thread에서 busy wait; ISR에서는 no-op |
| `map()` | 지원 | Arduino와 같은 clamp 없는 32-bit `long` 선형 변환; 0 span과 signed overflow는 호출자 전제 |
| `constrain()`, `min()`, `max()`, `abs()` | 지원 | upstream C/C++ 의미와 부수 효과 경계를 따름 |
| bit helper | 지원 | target의 32-bit `unsigned long` 범위에서 동작 |
| `random()`, `randomSeed()` | 지원 | Arduino 용도의 비암호 PRNG; entropy, key, nonce 생성에는 사용 금지 |
| `pulseIn*`, `shiftIn`, `shiftOut` | 미구현 | timing·timeout 계약이 없음 |

### 5.1 `v0.3.0` AC-01 pulse/shift working tree

| API | 개발 상태 | AC-01 계약 |
| --- | --- | --- |
| `pulseIn()` | 구현·target build | thread 전용 busy polling, 64-bit cycle deadline, timeout은 `0` 반환 |
| `pulseInLong()` | 구현·target build | 같은 deadline에 주기적 `k_yield()`를 추가한 cooperative polling |
| `shiftOut()` | 구현·target build | 구성된 output data/clock, `MSBFIRST`/`LSBFIRST`, 8-bit GPIO clock |
| `shiftIn()` | 구현·target build | 구성된 input data/output clock, 두 bit order의 8-bit GPIO sampling |

Pulse 폭의 외부 계측 정확도, 고속 shift 성능과 bus protocol 대체 사용은 보증하지 않는다.
AC-01 HIL은 P2.5↔P2.6 한 가닥 loopback으로 timeout, 짧은/긴 pulse 범위, shift 최종 상태·고정
low/high 수신을 검증한다.

## 6. Serial, Wire, SPI, ADC와 PWM

| API/영역 | `v0.2.0` 상태 | 계약 |
| --- | --- | --- |
| 기본 `Serial` | 의미 차이 | `DT_CHOSEN(zephyr_console)`의 non-owning `HardwareSerial` wrapper |
| Serial `begin()`/`end()` | 의미 차이 | UART hardware를 재구성하지 않고 Core RX lifecycle만 제어 |
| Serial read/peek | 지원 | 고정 IRQ RX queue |
| Serial write/flush | 부분 지원 | polling TX, thread 문맥; `flush()`는 RX를 버리지 않음 |
| `Serial1` | 미구현 | 추가 UART instance의 Arduino mapping과 ownership 계약 없음 |
| `SerialUSB` | 하드웨어 미지원 | nRF54L15 target에 native USB device 경로 없음 |
| 기본 `Wire` | 부분 지원 | I2C22 blocking controller, 고정 TX/RX buffer |
| Wire repeated-start | 지원 | 같은 주소의 보류 write와 `requestFrom(..., true)` 조합 |
| Wire target/slave, `Wire1` | 미구현 | 추가 instance와 ownership 계약 없음 |
| 기본 `SPI` | 부분 지원 | SPI00 full-duplex controller, Sketch 소유 chip-select |
| SPI transaction·mode·bit order | 부분 지원 | 지원 설정만 변환; 다른 Zephyr client와의 직렬화는 application 책임 |
| 다중 SPI bus | 미구현 | 추가 instance mapping 없음 |
| `analogRead(A0)` | 부분 지원 | `PIN_A0` 전용 12-bit raw 값, 실패 시 `-1` |
| `analogReference()` | 의미 차이 | `AR_DEFAULT`/동일 별칭 `AR_INTERNAL`만 허용; DTS 설정은 runtime 불변 |
| `analogWrite(PIN_PWM0)` | 부분 지원 | 전용 PWM 역할의 20 ms 고정 period·8-bit duty 계약 |
| analog resolution setter·PWM frequency extension | 미구현 | 현재 고정 계약 밖 |
| DAC | 하드웨어 미지원 | `analogWrite()`를 DAC로 표현하지 않음 |

`Wire`, `SPI`, ADC와 PWM은 `standard`와 `ble` profile에서 제공된다. Peripheral pinctrl과
chosen 장치는 Devicetree가 소유하고, Sketch가 임의 pin 번호로 bus를 재배치하지 않는다.

## 7. 공개 진단 API

`<nucode/Diagnostics.h>`는 반환값이 없는 Arduino API와 backend 오류를 조회하는 최소 공개
계약이다.

```cpp
using namespace nucode::arduino;
Diagnostic diagnostic = lastDiagnostic(DiagnosticSubsystem::gpio);
```

| 항목 | 현재 계약 |
| --- | --- |
| Subsystem | `core`, `gpio`, `time`, `serial`, `wire`, `spi`, `analog` |
| Code | `none`, `invalid_context`, `invalid_argument`, `invalid_pin`, `unsupported`, `device_not_ready`, `not_started`, `overflow`, `ownership_conflict`, `driver_error` |
| 활성 backend projection | GPIO, Serial, Wire, SPI, Analog의 마지막 atomic 오류와 driver errno |
| 별도 저장소 없음 | `core`는 `none`, `time`은 `unsupported` |
| format | `NU54:<subsystem>:<code>:driver=<signed>:detail=<unsigned>` |

조회는 backend 상태를 지우지 않는다. 공개 진단은 최신 원자 snapshot이며 event queue나 오류
이력이 아니다. ISR에서 문자열 formatting을 수행하지 않는다.

## 8. NU54DK 확장 API

### 8.1 `NUCODE_NU54DK`

`<NUCODE_NU54DK.h>`와 전역 `NU54DK`는 다음 보드 종속 기능을 제공한다.

- board/SoC/SDK identity, device ID, reset cause, uptime
- watchdog begin/feed/stop
- GRTC counter와 work-queue 문맥 one-shot alarm
- `nucode/` namespace의 Settings/ZMS 저장소
- 버튼 또는 GRTC 기반 System OFF 진입과 wake
- BQ25186 상태 read와 명시적 승인 뒤 제한된 설정

Board/System software 계약과 System OFF wake는 검증됐다. PMIC write API의 software 의미가
실제 배터리 충전·rail·ship mode의 전기적 안전을 보증하지는 않는다. 배터리 전기 HIL은 공개
지원 증거에서 제외하며 사용자가 자신의 전원 조건에서 검증해야 한다.

### 8.2 `NUCODE_BLE`

`<NUCODE_BLE.h>`의 `BLESerial`은 NUS Peripheral/Central을 Arduino `Stream`으로 제공한다.
광고·exact-name scan, 연결, RX write, TX notification, 재광고·재검색과 `poll()` event가
`v0.2.0`의 지원 범위다.

범용 GAP/GATT builder, GATT read/indication, pairing·bonding·SMP와 HID는 미구현이다. 다음
구현 단계는 M19 BLE Core/GAP이며, 계획이 현재 지원 판정을 바꾸지 않는다.

## 9. Zephyr/NCS 직접 사용과 build-only 경계

Full Zephyr 구조이므로 expert Sketch는 공개 Zephyr/NCS API를 직접 사용할 수 있다. 다만 다음
표현을 구분한다.

| 표현 | 의미 |
| --- | --- |
| Arduino/NUCODE 지원 | wrapper, 예제, 자동 시험과 필요한 HIL을 모두 보유 |
| Direct | Zephyr/NCS API를 Sketch가 직접 사용; portable Arduino 계약 아님 |
| Build-only | 고정 sample 또는 외부 library가 compile/build됨; runtime·hardware 지원 아님 |
| Deferred | 현재 제품에서는 광고·예제·지원하지 않음 |

외부 sensor library compile, crypto sample build, 802.15.4/OpenThread/Matter feasibility 결과는
이 경계를 넘어 지원으로 해석하지 않는다.

## 10. `v0.2.0` 정식 package의 명시적 미지원 범위

- `pulseIn()`, `pulseInLong()`, `shiftIn()`, `shiftOut()`
- `tone()`, `noTone()`, Servo
- Arduino EEPROM/FS 호환 API와 external flash
- native USB device, Keyboard, Mouse
- Wi-Fi/Ethernet
- 범용 BLE GAP/GATT·보안·HID
- BLE Mesh, Channel Sounding, ISO
- 802.15.4, ESB, OpenThread, Matter runtime
- AVR/SAMD direct register/port API

이 가운데 pulse/shift, tone/Servo, open-drain, 추가 connector pin·bus와 EEPROM facade는 기술적으로
구현할 수 있지만, 현재는 resource ownership·오류 의미·예제·HIL 계약이 없다. 반대로 native USB,
DAC, AVR Harvard memory와 Wi-Fi는 NU54DK/nRF54L15 hardware에서 동일한 방식으로 제공할 수 없다.

`v0.3.0`은 이 가운데 구현 가능한 호환성을 BLE 작업선과 병렬로 다음과 같이 다룬다.

- AC-01: 승인된 connector GPIO, open-drain, level interrupt, pulse/shift와 전역 IRQ 안전성 gate
- AC-02: `Serial1`, Wire/SPI 확장, ADC/PWM resolution·frequency, `tone()`/Servo와 자원 소유권
- AC-03: 기존 Settings/ZMS/RRAM 위의 EEPROM·internal filesystem facade와 고정된 대표 제3자
  library matrix
- M19~M21: 범용 BLE GAP/GATT, security와 표준 profile

계획이 현재 `v0.2.0` 지원 판정을 바꾸지는 않는다. 각 항목은 자동 계약, target build,
필요한 HIL과 예제를 통과해야만 지원으로 승격한다. 물리 경로나 driver 의미를 확정할 수
없는 항목은 feasibility 결과에 따라 하드웨어 비적용 또는 별도 scope 개정 대상으로 판정하며
성공으로 가장하지 않는다. 구현 목표로 확정한 항목은 그 결정 전까지 M22를 차단한다.

## 11. 검증 증거

- [M6 기본 Arduino API·Serial·interrupt 기준선](<../04_검증 기록/06_M6_기본_Arduino_API_Serial과_인터럽트_기준선.md>)
- [M7 Wire·SPI·ADC·PWM 기준선](<../04_검증 기록/07_M7_Wire_SPI_ADC_PWM_기준선.md>)
- [M14 Core API와 Variant 기준선](<../04_검증 기록/16_M14_Core_API와_Variant_기준선.md>)
- [M15 NU54DK Board/System 기준선](<../04_검증 기록/17_M15_NU54DK_Board_System_기준선.md>)
- [M16 BLE NUS 기준선](<../04_검증 기록/18_M16_BLE_NUS_기준선.md>)
- [M17 NCS 기능과 예제 Coverage 기준선](<../04_검증 기록/19_M17_NCS_기능과_예제_Coverage_기준선.md>)
- [v0.2.0 정식 릴리스 공개 기록](<../04_검증 기록/21_v0.2.0_정식_릴리스_공개_기록.md>)
- [AC-01 GPIO 호환성 검증](<../04_검증 기록/22_AC-01_GPIO_호환성_검증.md>)

지원 상태를 올리려면 production source, host/target 계약, Arduino package compile과 필요한 HIL을
함께 갱신하고 해당 검증 기록을 추가해야 한다.
