# NU54DK Arduino 주변장치 API 설계

| 항목 | 내용 |
| --- | --- |
| 문서 ID | FW-PERIPHERAL-001 |
| 문서 개정 | 4.0 |
| 문서 상태 | `v0.3.0` 정식 계약 |
| 최종 갱신일 | 2026-09-03 |
| 기준 | NCS v3.4.0 / Zephyr 4.4.0 |

## 1. 목적

이 문서는 `Serial`, `Wire`, `SPI`, `analogRead()`와 `analogWrite()`의 현재 구성, 소유권,
동시성 및 오류 계약을 정의한다. 과거 milestone의 byte 수, 측정값, UART transcript와 실행
commit은 `04_검증 기록`으로 이동하고 여기에는 제품 동작만 남긴다.

## 2. 단일 원본

| 정보 | 단일 원본 |
| --- | --- |
| UART/I2C/SPI/ADC/PWM 장치와 pinctrl | `board_package/NU54DK_Zephyr_DTS` |
| Arduino object·backend | `cores/arduino` |
| Arduino 논리 역할 | `variants/nu54dk` |
| runtime owner/resource 상태 | `cores/arduino/internal/IoResourceManager.h` |
| runtime pinctrl/PM route | `cores/arduino/internal/RuntimePeripheralRoute.*`, `variants/nu54dk/peripheral_routes.*` |
| 부팅 고정 자원 registry | `variants/nu54dk/io_resource_registry.cpp` — UART20 console만 고정 |
| 일반 사용자 subsystem 선택 | `standard`/`ble` profile과 library feature manifest |
| Sketch별 custom 구성 | expert `prj.conf`/overlay |

Core에 `uart20`, `i2c22`, `spi00`과 실제 pin 번호를 별도 board truth로 복제하지 않는다.
Production backend는 Devicetree chosen, alias와 profile overlay를 소비한다.

## 3. 현재 자원과 ownership

| 공개 객체/역할 | Devicetree source | `v0.3.0` stable ownership |
| --- | --- | --- |
| `Serial` | `DT_CHOSEN(zephyr_console)` | 기존 console UART의 non-owning wrapper |
| `Serial1` | UART30 runtime node | `begin/end`가 P0 RX/TX pad·UART30 block과 runtime PM을 소유 |
| `Wire` | `nucode,arduino-wire` = I2C22 | `begin/end`가 같은 P1 SDA/SCL pad와 I2C22 block을 소유 |
| `SPI` | `nucode,arduino-spi` = SPI00 | `begin/end`가 전용 P2.1/P2.2/P2.4와 SPI00 block을 소유; CS는 Sketch 책임 |
| `AIN0..7`, `A0..A7` | `nucode,arduino-adc` | SAADC channel metadata는 모두 존재하되 system owner와 전기 부하를 보존 |
| `analogWrite()` | PWM20 | 최대 4 channel과 한 shared period |
| `tone()` | PWM21 | 한 channel 전용 |
| `Servo` | PWM22 | 최대 4 channel, 20 ms frame |

### 3.1 AC-02A 내부 소유권 기준선

AC-02A는 공개 주변장치 객체를 늘리기 전에 pad와 peripheral block의 충돌을 fail-closed로 검출하는
공통 기반을 추가했다.

| 항목 | 현재 내부 계약 |
| --- | --- |
| 저장 구조 | heap 없는 고정 슬롯, 설정 가능한 최대 slot 수 |
| 자원 key | GPIO `controller + pin`, 또는 `serial/pwm/adc/power` block의 domain·instance |
| owner | `gpio`, `adc`, `pwm`, `wire`, `spi`, `serial`, `system` + instance |
| 전환 | 최대 8개 자원의 원자적 `reserve/commit/rollback/release` lease |
| 수명 보호 | 64-bit generation과 manager epoch로 stale lease 거부 |
| 문맥 | thread 전용 변경·조회; ISR 요청은 `invalid_context`로 거부 |
| 부팅 고정 owner | UART20 console의 pad와 block만 고정 |

Registry는 DTS pinctrl을 읽어 UART20 console을 `active`로 표시하며 GPIO가 이를 덮어쓰지 못하게
한다. I2C22, SPI00, UART30과 PWM20/21/22는 부팅 고정 owner가 아니라 AC-02B runtime lifecycle이
동적으로 소유한다.

AC-02B는 `PinHandover`와 `RuntimePeripheralRoute`를 연결해 기존 GPIO mode/latch/interrupt를
snapshot하고, peripheral pinctrl default/sleep 상태와 runtime PM을 적용한 뒤 종료 시 복원한다.
전환 실패는 rollback하거나 복구 불능 latch로 fail-closed한다. 이 코드는 host/target build와
exact commit `0b7f89283cd82a68a7f3f0910f4fc59b8dd01bfb`의 3-wire 물리 HIL을 통과했다.

## 4. 공통 lifecycle과 문맥

- 전역 object constructor는 hardware를 활성화하지 않는다.
- 실제 device 사용은 `begin()` 또는 첫 명시적 작업 뒤에 시작한다.
- `setPins()`는 종료 상태에서 다음 `begin()` route만 stage한다. 실행 중 변경은 거부한다.
- `begin()`은 route 검증, GPIO handover, dynamic pinctrl과 runtime PM을 하나의 lifecycle로 묶는다.
- `end()`는 driver를 중지하고 route를 deactivate한 뒤 이전 GPIO 상태 또는 free 상태를 복원한다.
- 실패 중간 상태는 rollback하며 복원 자체가 실패하면 fatal latch로 다음 재사용을 거부한다.
- 다른 Zephyr client의 bus-wide synchronization까지 제공하지 않는다.
- Peripheral I/O와 lifecycle은 thread 문맥 전용이다.
- ISR 호출은 `invalid_context`와 안전한 실패로 거부한다.
- Driver의 negative errno는 subsystem 내부 상태에 보존하고 공개 진단으로 projection한다.

## 5. `Serial`

### 5.1 소유권

기본 `Serial`은 DAP UART로 연결된 chosen console device를 사용한다. Core가 baud, parity,
pinctrl과 console ownership을 독점하지 않는다. 현재 production 계약은 console의 115200 8N1을
검증해 빌리고, `begin()`/`end()`가 Core RX lifecycle만 시작·중지하는 것이다.

### 5.2 공개 동작

| API | 계약 |
| --- | --- |
| `begin()` | 현재 chosen UART가 지원되는 설정인지 확인; hardware 재구성 안 함 |
| `end()` | Arduino RX callback·queue lifecycle 종료 |
| `available/read/peek` | 고정 RX queue 소비 |
| `write` | Core mutex로 직렬화한 polling TX; 실제 성공 byte 수 반환 |
| `availableForWrite` | 현재 구현이 즉시 받을 수 있는 최소 공간 보고 |
| `flush` | 호출한 TX 완료를 보장; RX queue를 버리지 않음 |

RX queue가 가득 차면 새 byte를 버리고 overflow 진단을 기록한다. TX는 ISR에서 허용하지 않는다.
동일 UART의 Arduino RX와 Zephyr shell RX를 동시에 활성화하는 구성을 지원하지 않는다.

`Serial1`은 UART30을 독립 소유한다. 기본 RX는 P0.1, TX는 P0.0이며 종료 상태에서
`Serial1.setPins(rx, tx)`로 기술 route가 있는 P0 핀을 다음 `begin()`에 배치할 수 있다. P0의
`conditional_dap_uart` 정책은 일반 GPIO 노출과 UART30 route를 구분한다. `begin/end/rebegin`,
고정 IRQ RX queue와 polling TX를 제공하며 bounded TX queue 확장은 구현하지 않는다.
`SerialUSB`는 nRF54L15 target에 native USB device 경로가 없어 제공하지 않는다.

## 6. `Wire`

### 6.1 Controller 계약

`Wire`는 7-bit controller/master transaction을 제공한다. TX/RX는 각각 고정 buffer이며 기본
크기는 `CONFIG_NUCODE_ARDUINO_WIRE_BUFFER_SIZE`가 정한다.

| API | 계약 |
| --- | --- |
| `setPins(sda, scl)` | 종료 상태에서 같은 P1의 open-drain I2C22 route를 stage |
| `begin()`/`end()` | I2C22 route·runtime PM·ownership 활성/복원 |
| `beginTransmission()` | address와 새 TX transaction 준비 |
| `write()` | TX buffer에 추가; overflow는 명시적 오류 |
| `endTransmission(true)` | write 또는 zero-byte address probe 실행 |
| `endTransmission(false)` | 같은 주소의 다음 read를 위한 write 보류 |
| `requestFrom(..., true)` | 보류 write와 repeated-start read 또는 단독 read |
| `requestFrom(..., false)` | 현재 미지원, 0과 진단 반환 |
| `setClock()` | 검증된 bus rate만 허용 |

NACK과 driver 오류는 Arduino 상태 값으로 변환하되 원래 errno를 보존한다. Address/data NACK을
항상 서로 다른 상태로 판별할 수 있다고 보증하지 않는다.

보류 repeated-start는 같은 thread, 같은 address와 바로 이어지는 `requestFrom(..., true)`에만
유효하다. 다른 Zephyr I2C client와 bus-wide lock을 공유하지 않으므로 여러 client는 application이
transaction을 직렬화해야 한다. Stock NCS v3.4 controller backend 경계에 따라 target/slave
`begin(address)`, `onReceive()`/`onRequest()`, read `requestFrom(..., false)`와 `Wire1`은
capability에 포함하지 않고 fail-closed한다. Cross-board P1.2/P1.3 continuity 불연속을 확인했기
때문에 HIL은 peer TWIS를 사용하지 않는다. DUT 온보드 BQ25186 `0x6A`의 read-only register
`0x0C == 0x41`을 100/400 kHz repeated-start와 end/rebegin으로 검증한다. 이는 Arduino target
지원 또는 임의 PMIC write를 뜻하지 않는다.

### 6.2 BQ25186 사용 경계

기본 `WirePmicId`와 Board/System adapter는 온보드 BQ25186의 제한된 read 경로를 사용한다.
일반 `Wire` backend 자체는 정상 7-bit address를 전달하지만 example/HIL protocol에 arbitrary
scan, register write와 fallback을 추가하지 않는다. PMIC write 안전 계약은
[NU54DK Board/System API](./05_NU54DK_Board_System_API.md)가 소유한다.

## 7. `SPI`

### 7.1 Controller와 chip-select

`SPI`는 chosen SPI controller의 8-bit full-duplex transfer를 제공한다. Core는 chip-select를
추정하거나 자동 생성하지 않는다. Sketch가 별도 digital GPIO를 선택해 assertion/deassertion을
소유한다.

| API | 계약 |
| --- | --- |
| `setPins(sck, miso, mosi)` | 종료 상태에서 SPI00 전용 route를 검증·stage |
| `begin()`/`end()` | SPI00 route·runtime PM·ownership 활성/복원 |
| `beginTransaction(settings)` | 지원 frequency, mode와 bit order 검증; Core caller ownership 획득 |
| `transfer(byte/word/buffer)` | active transaction에서 full-duplex 전송 |
| `endTransaction()` | Core ownership과 transaction 상태 해제 |
| `usingInterrupt()`/`notUsingInterrupt()` | 등록된 Arduino GPIO callback만 transaction 동안 mask/restore |

Core mutex는 Arduino `SPI` caller끼리만 직렬화한다. Zephyr bus-wide lock이나 다른 driver client의
동기화를 제공하지 않는다. Sketch 소유 CS를 오류 복구 과정에서 임의 변경하지 않는다.

SPI00 signal route는 SoC 전용 matrix에 따라 SCK P2.1, MOSI P2.2, MISO P2.4로 정확히 고정된다.
따라서 `setPins()`가 존재해도 임의 GPIO remap을 뜻하지 않는다. SPI00과 같은 hardware instance를
공유하는 `uart00`을 동시에 활성화하는 구성, chosen 누락과 다른 SPI instance 선택은
configure/build에서 명시적으로 실패시킨다. `attachInterrupt()`/`detachInterrupt()`는 SPIM
controller 의미를 합성하지 않고 unsupported, `SPI1`과 automatic chip-select도 미지원이다.

## 8. ADC와 `analogRead()`

- `AIN0..7`과 `A0..A7` 이름은 SAADC channel 0..7에 일대일 대응한다.
- `analogReadResolution()`은 8/10/12/14 bit만 허용하며 결과 범위를 software scaling한다.
- 오류는 `-1`과 Analog subsystem 진단으로 보고한다.
- `analogReference()`는 `AR_DEFAULT`와 같은 의미의 `AR_INTERNAL`만 허용한다.
- Reference/gain/channel은 Devicetree 계약이며 runtime에서 바꾸지 않는다.

| Channel/Arduino 이름 | 물리 핀 | 소유권·전기 경계 |
| --- | --- | --- |
| AIN0/A1~AIN3/A4 | P1.4~P1.7 | UART20 console/system 소유, 읽기 거부 |
| AIN4/A5 | P1.11 | PMIC/system 입력 소유, 읽기 거부 |
| AIN5/A0 | P1.12 | 공개 A0; GPIO input/output/open-drain·interrupt와 ADC/PWM 사이 transferable |
| AIN6/A6 | P1.13 | 읽기 지원; SW0와 pull 회로의 부하를 사용자가 고려 |
| AIN7/A7 | P1.14 | 읽기 지원; LED3 회로의 부하를 사용자가 고려 |

Nominal reference/gain을 pin의 절대최대 정격이나 측정 정확도로 해석하지 않는다. 전기적 입력
범위는 nRF54L15와 NU54DK hardware 사양을 따른다.

## 9. PWM과 `analogWrite()`

- `analogWriteResolution()`은 1~16 bit를 허용한다.
- `analogWriteFrequency(pin, hz)`는 다음 `analogWrite()`에서 사용할 period를 설정한다.
- PWM20은 P1의 `digital_output + pwm_output` capability 핀을 최대 4 channel까지 사용한다.
- 같은 PWM20 block의 active channel은 period를 공유하므로 다른 frequency 요청은 명확히 거부한다.
- `tone()`/`noTone()`은 PWM21 한 channel을 독립 사용한다.
- `Servo` library는 PWM22 최대 4 channel과 20 ms frame을 사용해 analogWrite/tone과 block을 분리한다.
- GPIO↔PWM 전환은 route 전체를 재구성하고 실패 시 이전 active channel 집합을 복원한다.
- PWM을 true DAC 출력으로 표현하지 않는다.

Servo signal과 공통 GND만 NU54DK에 연결한다. Servo motor 전원을 GPIO 또는 보드 3.3 V에서
공급하지 말고 부하에 적합한 외부 전원을 사용한다.

## 10. 공개 진단

`<nucode/Diagnostics.h>`의 `lastDiagnostic()`은 `serial`, `wire`, `spi`, `analog` subsystem의
마지막 backend 상태를 공개 `Diagnostic`으로 변환한다.

| 공개 code | 대표 의미 |
| --- | --- |
| `invalid-context` | ISR 등 금지 문맥 |
| `invalid-argument` / `invalid-pin` | 설정·address·pin 범위 오류 |
| `unsupported` | 지원하지 않는 mode/configuration |
| `device-not-ready` | Devicetree device 준비 실패 |
| `not-started` | `begin()` 또는 transaction 전 호출 |
| `overflow` | 고정 queue/buffer 부족 |
| `ownership-conflict` | pin/bus/transaction 소유권 충돌 |
| `driver-error` | Zephyr driver의 원래 오류 보존 |

진단 조회는 상태를 지우지 않으며 error history가 아니다. Release build에서도 범위와 ownership
검사를 제거하지 않는다. ISR에서는 문자열 format이나 log를 만들지 않는다.

## 11. 설정과 profile

| 설정 | 기본 profile 의미 |
| --- | --- |
| `CONFIG_NUCODE_ARDUINO_IO_OWNERSHIP` | 고정 슬롯 소유권 manager와 NU54DK 부팅 registry |
| `CONFIG_NUCODE_ARDUINO_SERIAL` | chosen console `Serial` |
| `CONFIG_NUCODE_ARDUINO_SERIAL1` | UART30 runtime `Serial1` |
| `CONFIG_NUCODE_ARDUINO_SERIAL_RX_BUFFER_SIZE` | Serial RX 고정 queue |
| `CONFIG_NUCODE_ARDUINO_WIRE` | chosen I2C `Wire` |
| `CONFIG_NUCODE_ARDUINO_WIRE_BUFFER_SIZE` | Wire TX/RX buffer |
| `CONFIG_NUCODE_ARDUINO_SPI` | chosen SPI controller |
| `CONFIG_NUCODE_ARDUINO_ADC` | AIN0~AIN7 metadata와 SAADC backend |
| `CONFIG_NUCODE_ARDUINO_PWM` | PWM20 analogWrite와 PWM21 tone runtime backend |
| `CONFIG_NUCODE_ARDUINO_SERVO` | Servo library용 PWM22 backend |

Module 자체의 최소 Kconfig와 Arduino `standard`/`ble` profile 기본값은 구분한다. 일반 사용자는
Arduino IDE feature set을 선택하고 raw conf/overlay는 expert escape hatch로만 사용한다.

## 12. Radio와 USB 경계

- `v0.2.0`의 BLE wrapper는 NUS Peripheral/Central `Stream`만 제공한다.
- 802.15.4, ESB, OpenThread와 Matter는 현재 runtime 미지원이다.
- BLE와 다른 radio stack의 multiprotocol 동시 운용을 임의로 활성화하지 않는다.
- nRF54L15 target의 native USB device API, CDC, Keyboard와 Mouse를 제공하지 않는다.
- 온보드 CMSIS-DAP USB는 target MCU의 Arduino USB peripheral이 아니다.

## 13. 검증과 증거

- [M6 기본 Arduino API·Serial·interrupt 기준선](<../04_검증 기록/06_M6_기본_Arduino_API_Serial과_인터럽트_기준선.md>)
- [M7 Wire·SPI·ADC·PWM 기준선](<../04_검증 기록/07_M7_Wire_SPI_ADC_PWM_기준선.md>)
- [M14 Core API와 Variant 기준선](<../04_검증 기록/16_M14_Core_API와_Variant_기준선.md>)
- [M15 NU54DK Board/System 기준선](<../04_검증 기록/17_M15_NU54DK_Board_System_기준선.md>)
- [M16 BLE NUS 기준선](<../04_검증 기록/18_M16_BLE_NUS_기준선.md>)
- [AC-02A 핀과 주변장치 소유권 기준선](<../04_검증 기록/26_AC-02A_핀과_주변장치_소유권_기준선.md>)
- [AC-02B Peripheral/Analog runtime 기준선](<../04_검증 기록/27_AC-02B_Peripheral_Analog_runtime_기준선.md>)

정식 `v0.2.0`의 기존 Serial/Wire/SPI/ADC/PWM 수직 경로 HIL은 완료됐다. AC-02B 개발 경로도
exact 3-wire fixture에서 Serial1, BQ25186 Wire, local SPI, ADC raw 0/3757과 A0 PWM
25%·75% polling capture를 통과했다. Exact transaction 수, frequency, payload, raw 측정값과
commit은 검증 문서가 소유한다.

## 14. 명시적 범위 밖

- 기본 console `Serial`의 baud·pin·hardware runtime 재구성 또는 bounded TX queue
- I2C target/slave·callback, read no-STOP `requestFrom(..., false)`, `Wire1`과 bus-wide arbitration
- `SPI1`, SPI peripheral `attachInterrupt()`/`detachInterrupt()`와 Core 소유 automatic chip-select
- system-reserved AIN0~AIN4의 강제 claim, analog 절대 정확도 보증과 runtime reference/gain 변경
- PWM block의 channel별 서로 다른 period와 DAC
- peripheral I/O의 ISR-safe 호환층
- P2 GPIO interrupt — CPUAPP GPIOTE 경로가 없어 `NOT_AN_INTERRUPT`
