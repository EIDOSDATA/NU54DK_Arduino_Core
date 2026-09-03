# NU54DK Arduino API 지원 범위

| 항목 | 내용 |
| --- | --- |
| 문서 ID | CORE-API-001 |
| 문서 개정 | 6.0 |
| 대상 | `v0.3.0` stable |
| 최종 갱신일 | 2026-09-03 |
| 상태 | **정식 공개 범위** |

## 판정 기준

이 문서는 `nucode:zephyr@0.3.0`이 약속하는 Arduino/NUCODE API 범위를 정리합니다. Header에
이름이 존재하는 것, target에서 compile되는 것과 실제 hardware 지원은 서로 다른 판정입니다.

| 상태 | 의미 |
| --- | --- |
| 지원 | 아래에 선언한 계약 전체를 구현하고 필요한 자동 시험 또는 HIL을 통과 |
| 지원된 범위 | API는 정식 지원하지만 공개 pin/channel/profile 범위가 hardware 전체보다 좁음 |
| 부분 지원 | Arduino의 해당 API군 중 명시한 하위 기능·instance만 지원 |
| 의미 차이 | 이름은 호환되지만 Zephyr/NU54DK에서 동작 의미가 다름 |
| 미지원 | 공개 backend 또는 mode를 제품 지원으로 제공하지 않음 |
| 전문가 opt-in | 기본 profile 밖의 직접 Zephyr/NCS 경로; portable Arduino 계약 아님 |
| build-only | 고정 환경에서 build만 확인했으며 runtime 지원이 아님 |

`v0.3.0`은 선언한 제품 범위를 완료했지만 모든 Arduino 보드의 API, 모든 pin/peripheral
instance와 제3자 library 전체를 지원한다는 뜻은 아닙니다.

## Runtime과 공통 API

| API/영역 | 상태 | 계약 |
| --- | --- | --- |
| `Arduino.h`, 공통 type·상수 | 지원 | ArduinoCore-API 1.5.2 기반 공개 형식과 C/C++ 계약 |
| `setup()` | 지원 | 정적 초기화와 `initVariant()` 뒤 main thread에서 한 번 호출 |
| `loop()` | 의미 차이 | Zephyr main thread에서 반복; 기본 post-loop는 한 kernel tick sleep |
| `serialEventRun()` | 지원 | Symbol이 있으면 각 `loop()` 뒤 호출 |
| `yield()` | 의미 차이 | 허용 thread 문맥에서 `k_yield()`, 금지 문맥은 no-op |
| `String`, `Print`, `Printable`, `Stream` | 지원 | 생산 backend와 bounded embedded heap 계약 |
| `F()`/`__FlashStringHelper` | 의미 차이 | Compile 호환만 제공하며 AVR식 SRAM 절약은 없음 |
| `PROGMEM`, `PSTR` | 미지원 | AVR Harvard memory model을 모사하지 않음 |
| C++ exception/RTTI | 전문가 opt-in | 기본 profile은 비활성; 별도 시험 구성에서만 검증 |

`IPAddress`, `Client`, `Server`, `Udp`, `PluggableUSB`와 USB backend는 vendored header 존재
여부와 무관하게 제품 지원 범위가 아닙니다.

## Pin, GPIO와 interrupt

| API/영역 | 상태 | 계약 |
| --- | --- | --- |
| `pinMode()`, `digitalWrite()`, `digitalRead()` | 지원된 범위 | Variant capability에 등록된 pin과 mode만 허용 |
| `OUTPUT_OPENDRAIN` | 지원된 범위 | 승인 connector pin; `HIGH`는 high-Z release |
| `digitalPinIsValid()` | 지원 | Sparse Arduino pin ID의 실제 capability 반환 |
| `digitalPinToInterrupt()` | 지원 | GPIOTE 가능 pin 또는 `NOT_AN_INTERRUPT` 반환 |
| Edge interrupt | 지원된 범위 | `RISING`, `FALLING`, `CHANGE`와 attach/detach |
| Level interrupt | 지원된 범위 | GPIOTE P0/P1의 `LOW`/`HIGH`, hold one-shot 뒤 재무장 |
| `noInterrupts()`/`interrupts()` | 의미 차이 | 중첩 가능한 Arduino GPIO callback mask; system/BLE/driver IRQ는 유지 |
| P2 interrupt | 미지원 | CPUAPP GPIOTE 경로가 없어 `NOT_AN_INTERRUPT` |

`PIN_GPIO0/D10` P2.5와 `PIN_GPIO1/D11` P2.6은 input/output/open-drain을 지원하지만 interrupt는
지원하지 않습니다. GPIO와 peripheral이 같은 pad를 동시에 소유하려 하면 고정 슬롯 manager가
충돌을 거부합니다. 물리 mapping은 [핀과 Variant 설계](./03_핀과_Variant_설계.md)를 따릅니다.

## 시간과 utility

| API/영역 | 상태 | 계약 |
| --- | --- | --- |
| `millis()` | 지원 | Zephyr uptime 기반 32-bit 반환 |
| `micros()` | 지원 | nRF54 GRTC cycle 기반 32-bit 반환 |
| `delay()` | 의미 차이 | 64-bit deadline으로 current thread sleep |
| `delayMicroseconds()` | 의미 차이 | Thread에서 busy wait, ISR에서는 no-op |
| `pulseIn()` | 지원 | Thread 전용 busy polling, timeout은 0 |
| `pulseInLong()` | 지원 | 주기적 `k_yield()`를 포함한 cooperative polling |
| `shiftIn()`/`shiftOut()` | 지원 | 8-bit GPIO sampling/clock과 두 bit order |
| `map()`, `constrain()`, min/max/abs, bit helper | 지원 | ArduinoCore-API 의미와 32-bit `long` 범위 |
| `random()`/`randomSeed()` | 지원 | 비암호 PRNG; key·nonce 생성 금지 |

32-bit 시간 rollover 차분은 자동 시험했지만 장시간 clock 정확도와 모든 PM/idle 전후 연속성을
제품 보증하지 않습니다. Pulse/shift는 고속 bus protocol 대체 API가 아닙니다.

## Serial

| API/영역 | 상태 | 계약 |
| --- | --- | --- |
| 기본 `Serial` | 지원·의미 차이 | Zephyr console를 빌려 쓰는 115200 8N1 non-owning wrapper |
| Serial RX/read/peek | 지원 | 고정 IRQ RX queue |
| Serial TX/flush | 의미 차이 | Polling TX, thread 문맥; `flush()`는 RX를 버리지 않음 |
| `Serial1` | 지원된 범위 | UART30, 기본 RX P0.1/TX P0.0, lifecycle과 runtime pins |
| `SerialUSB` | 미지원 | nRF54L15 target에 native USB device 경로 없음 |

`Serial1.setPins()`는 종료 상태에서 승인 route만 stage하며 `begin()` 때 적용합니다. 임의 UART
instance/pin 조합은 지원하지 않습니다.

## Wire/I2C와 SPI

| API/영역 | 상태 | 계약 |
| --- | --- | --- |
| `Wire` | 부분 지원 | I2C22 blocking controller, 32-byte TX/RX, 100/400 kHz |
| Wire repeated-start | 지원된 범위 | 같은 thread·주소의 `endTransmission(false)` 뒤 `requestFrom(..., true)` |
| `Wire.setPins()` | 지원된 범위 | 종료 상태에서 승인 P1 open-drain route 적용 |
| Wire target/slave/callback | 미지원 | `begin(address)`, `onReceive()`, `onRequest()` 없음 |
| `requestFrom(..., false)`, `Wire1` | 미지원 | No-STOP read와 추가 instance 없음 |
| `SPI` | 부분 지원 | SPI00 full-duplex controller, Sketch 소유 chip-select |
| SPI transaction/mode/bit order | 지원된 범위 | Mode 0~3, supported clock와 buffer transfer |
| `SPI.setPins()` | 지원된 범위 | 종료 상태에서 승인 SPI00 route 적용 |
| SPI interrupt mask | 부분 지원 | 등록한 Arduino GPIO callback만 transaction 중 mask |
| `SPI1`, peripheral mode | 미지원 | 추가 instance와 peripheral backend 없음 |

Wire의 실기 기준은 온보드 BQ25186 `0x6A` read-only 100/400 kHz repeated-start입니다. 이는 모든
외부 sensor 호환이나 자동 bus arbitration을 뜻하지 않습니다. SPI 실기 기준은 승인된 SPI00
route의 4 MHz local loopback입니다.

## ADC, PWM, Tone과 Servo

| API/영역 | 상태 | 계약 |
| --- | --- | --- |
| `analogRead()` | 지원된 채널 범위 | 공개 A0/AIN5, A6/AIN6, A7/AIN7 raw code |
| `analogReadResolution()` | 지원 | 8/10/12/14-bit 결과 scaling |
| `analogReference()` | 의미 차이 | `AR_DEFAULT`/동일 별칭 `AR_INTERNAL`; DTS 설정은 runtime 불변 |
| `analogWrite()` | 지원된 채널 범위 | PWM20 최대 4 channel, 공유 period |
| `analogWriteResolution()` | 지원 | 1~16-bit duty 변환 |
| `analogWriteFrequency()` | 지원된 범위 | 공유 hardware와 충돌하지 않는 frequency |
| `tone()`/`noTone()` | 지원된 범위 | PWM21 전용 1 channel, duration과 ownership 복구 |
| `Servo` | 지원된 범위 | PWM22 전용 최대 4 channel, 20 ms frame |
| DAC | 미지원 | `analogWrite()`는 PWM이며 DAC가 아님 |

ADC 핀별 경계:

| Arduino 이름 | 물리 핀 | 계약 |
| --- | --- | --- |
| `AIN0/A1`~`AIN3/A4` | P1.4~P1.7 | Console/system 소유로 읽기 거부 |
| `AIN4/A5` | P1.11 | PMIC/system 입력 소유로 읽기 거부 |
| `AIN5/A0` | P1.12 | 공개 ADC; GPIO/interrupt/ADC/PWM 사이 handover |
| `AIN6/A6` | P1.13 | 읽기 지원, SW0 pull 회로 부하 주의 |
| `AIN7/A7` | P1.14 | 읽기 지원, LED3 회로 부하 주의 |

ADC raw code의 전압 정확도·선형성 calibration을 제품 보증하지 않습니다. PWM/tone/Servo는
pin, period와 hardware ownership 충돌을 fail-closed로 거부합니다. Servo motor 전원은 GPIO가
아닌 적합한 외부 전원을 사용하십시오.

## Storage

| API/영역 | 상태 | 계약 |
| --- | --- | --- |
| `EEPROM` | 지원된 용량 범위 | 1,024-byte RAM mirror, 명시적 `commit()`, CRC record |
| `EEPROM.reset()` | 지원·파괴적 | 손상 record를 자동 초기화하지 않고 명시적으로 삭제 |
| `LittleFS` | 지원된 용량 범위 | 내부 전용 32 KiB, file open 최대 4개 |
| `LittleFS.begin(false)` | 지원 | 비파괴 mount, 손상 시 실패 |
| `LittleFS.begin(true)`/`format()` | 지원·파괴적 | 명시적으로 filesystem 초기화 |
| 외부 SD/QSPI FS | 미지원 | 이 Core의 bundled storage 범위가 아님 |

EEPROM과 LittleFS는 암호화, secure storage, 전원 차단 원자성 또는 flash 수명 보증을 제공하지
않습니다. Storage API는 ISR에서 사용하지 않습니다.

## NU54DK Board/System

`<NUCODE_NU54DK.h>`와 전역 `NU54DK`는 다음 범위를 지원합니다.

- Board/SoC/SDK identity, device ID, reset cause와 uptime
- Watchdog begin/feed/stop
- GRTC counter와 work-queue 문맥 one-shot alarm
- `nucode/` namespace의 Settings/ZMS
- Button 또는 GRTC 기반 System OFF 진입과 wake
- BQ25186 상태 read와 명시적 승인 뒤 제한된 설정

PMIC software API는 실제 배터리 충전·rail·ship mode의 전기 안전 인증이 아닙니다. 매 boot의
RAM-only 승인, register policy와 사용자 전원·배터리 조건의 별도 검증이 필요합니다.

## BLE

| API/영역 | 상태 | 계약 |
| --- | --- | --- |
| BLE NUS | 지원 | Peripheral/Central byte `Stream`, reconnect lifecycle |
| GAP | 지원된 범위 | Advertising, scanning, 단일 connection lifecycle |
| 범용 GATT | 지원된 범위 | Server/client read, write, notify, indicate |
| Pairing/bonding/SMP | 지원된 범위 | `NUCODE_BLE_Security`의 고정 lifecycle |
| BAS/DIS | 지원된 범위 | 표준 profile API와 예제 |
| BLE HID keyboard | 지원된 범위 | Windows 11 pairing, 입력과 bond 복원 HIL |
| Mesh/ISO/Channel Sounding | 미지원 | API, 예제와 runtime 검증 없음 |
| 802.15.4/OpenThread/Matter | 미지원 | 과거 build feasibility는 runtime 지원 아님 |

BLE 검증은 NU54DK 두 대와 Windows 11 범위이며 Bluetooth qualification, 보안 인증 또는 모든
OS interoperability를 뜻하지 않습니다.

## 공개 진단 API

`<nucode/Diagnostics.h>`는 반환값이 없는 Arduino API와 backend 오류의 마지막 atomic snapshot을
제공합니다.

```cpp
using namespace nucode::arduino;
Diagnostic diagnostic = lastDiagnostic(DiagnosticSubsystem::gpio);
```

GPIO, Serial, Wire, SPI와 Analog backend의 `invalid_context`, `invalid_argument`, `invalid_pin`,
`unsupported`, `device_not_ready`, `not_started`, `overflow`, `ownership_conflict`, `driver_error`
등을 조회합니다. Event queue나 전체 오류 이력이 아니며 ISR에서 문자열 formatting을 하지 않습니다.

## 직접 Zephyr/NCS와 제3자 library 경계

Full Zephyr 구조이므로 expert Sketch가 공개 Zephyr/NCS API를 직접 사용할 수 있지만 portable
Arduino 계약은 아닙니다. 외부 sensor library compile, crypto sample build와
802.15.4/OpenThread/Matter feasibility 결과도 runtime 지원으로 확대하지 않습니다.

## 명시적 미지원 범위

- Loader/LLEXT, native USB device, UF2와 OTA/DFU
- `Wire1`, Wire target/slave와 no-STOP read
- `SPI1`, SPI peripheral mode
- DAC, Wi-Fi와 Ethernet
- External filesystem과 일반 secure storage
- BLE Mesh, ISO, Channel Sounding과 multiprotocol
- IEEE 802.15.4, ESB, OpenThread와 Matter runtime
- AVR/SAMD direct register/port와 Harvard memory API

## 검증 증거

- [AC-01 GPIO 호환성](<../04_검증 기록/22_AC-01_GPIO_호환성_검증.md>)
- [AC-02A 핀·주변장치 소유권](<../04_검증 기록/26_AC-02A_핀과_주변장치_소유권_기준선.md>)
- [AC-02B Peripheral/Analog runtime](<../04_검증 기록/27_AC-02B_Peripheral_Analog_runtime_기준선.md>)
- [AC-03 Storage와 library](<../04_검증 기록/28_AC-03_Storage와_Library_호환성_기준선.md>)
- [M19 BLE Core/GAP](<../04_검증 기록/23_M19_BLE_Core_GAP_검증.md>)
- [M20 범용 GATT](<../04_검증 기록/24_M20_범용_GATT_검증.md>)
- [M21 BLE 보안·표준 profile](<../04_검증 기록/25_M21_BLE_보안과_표준_Profile_검증.md>)
- [M22 RC3 검증과 stable 인계](<../04_검증 기록/31_M22_v0.3.0_rc3_검증과_stable_인계.md>)
- [v0.3.0 정식 릴리스 공개](<../04_검증 기록/32_M22_v0.3.0_정식_릴리스_공개_기록.md>)

지원 상태를 올릴 때는 production source, host/target 계약, 설치 package compile과 필요한 HIL을
같이 갱신해야 합니다. 역사 검증 기록의 범위는 소급해서 바꾸지 않습니다.
