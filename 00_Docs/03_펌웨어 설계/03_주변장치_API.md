# NU54DK Arduino 주변장치 API 설계

| 항목 | 내용 |
| --- | --- |
| 문서 ID | FW-PERIPHERAL-001 |
| 문서 개정 | 3.1 |
| 문서 상태 | `v0.2.0` 정식 계약 + `v0.3.0` AC-02A 내부 소유권 기준선 |
| 최종 갱신일 | 2026-09-01 |
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
| 부팅 고정 자원 registry | `variants/nu54dk/io_resource_registry.cpp` |
| 일반 사용자 subsystem 선택 | `standard`/`ble` profile과 library feature manifest |
| Sketch별 custom 구성 | expert `prj.conf`/overlay |

Core에 `uart20`, `i2c22`, `spi00`과 실제 pin 번호를 별도 board truth로 복제하지 않는다.
Production backend는 Devicetree chosen, alias와 profile overlay를 소비한다.

## 3. 현재 자원과 ownership

| 공개 객체/역할 | Devicetree source | 현재 ownership |
| --- | --- | --- |
| `Serial` | `DT_CHOSEN(zephyr_console)` | 기존 console UART의 non-owning wrapper |
| `Wire` | `nucode,arduino-wire` | blocking I2C controller; 다른 client와의 직렬화는 application 책임 |
| `SPI` | `nucode,arduino-spi` | SPI controller; chip-select는 Sketch 책임 |
| `A0`/`PIN_A0` | `nucode,arduino-adc` | ADC 전용 sparse ID 2 |
| `PIN_PWM0`/`PIN_PWM_LED` | `nucode,arduino-pwm` | PWM 전용 sparse ID 3 |
| `PIN_LED1` | `led1` | PWM-owned sparse ID 4, digital descriptor 없음 |

`NUM_DIGITAL_PINS=10` 범위 안에 A0/PWM 역할이 있어도 digital GPIO로 사용하지 않는다. 실제
digital-capable descriptor는 7개다.

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
| 부팅 고정 owner | UART20·I2C22·PWM20, 그리고 DTS에서 활성화된 경우 SPI00의 pad와 block |

Registry는 DTS pinctrl을 읽어 현재 사용 중인 고정 자원을 `active`로 표시할 뿐 driver나 pinctrl을
재구성하지 않는다. 따라서 AC-02A는 기존 `Serial`, `Wire`, `SPI`, ADC/PWM 동작을 바꾸지 않고
GPIO가 같은 pad를 덮어쓰지 못하게 하는 기반이다.

실제 runtime pinctrl·PM lifecycle, 각 `begin()`/`end()`와 manager의 acquire/release 연결,
Wire/SPI/Serial/ADC/PWM 사이 handover, 공개 claim/remap API와 물리 HIL은 AC-02B에 남아 있다.

## 4. 공통 lifecycle과 문맥

- 전역 object constructor는 hardware를 활성화하지 않는다.
- 실제 device 사용은 `begin()` 또는 첫 명시적 작업 뒤에 시작한다.
- `end()`는 wrapper가 소유한 queue, callback과 transaction 상태만 정리한다.
- AC-02A의 부팅 고정 owner lease는 `end()`가 해제하지 않는다. Peripheral lifecycle과 소유권
  handover의 결합은 AC-02B 범위다.
- Zephyr device, pinctrl 또는 다른 client의 상태를 임의로 되돌리지 않는다.
- Peripheral I/O와 lifecycle은 thread 문맥 전용이다.
- ISR 호출은 `invalid_context`와 안전한 실패로 거부한다.
- Driver의 negative errno는 subsystem 내부 상태에 보존하고 공개 진단으로 projection한다.

## 5. `Serial`

### 5.1 소유권

기본 `Serial`은 DAP UART로 연결된 chosen console device를 사용한다. Core가 baud, parity,
pinctrl과 console ownership을 독점하지 않는다. `begin()`은 실제 UART 설정이 지원 계약과 맞는지
확인하고 Core RX queue/callback을 시작한다. `end()`는 Core RX lifecycle만 중지한다.

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

`Serial1`과 임의 UART mapping은 제공하지 않는다. `SerialUSB`도 nRF54L15 target에 native USB
device 경로가 없어 제공하지 않는다.

## 6. `Wire`

### 6.1 Controller 계약

`Wire`는 7-bit controller/master transaction을 제공한다. TX/RX는 각각 고정 buffer이며 기본
크기는 `CONFIG_NUCODE_ARDUINO_WIRE_BUFFER_SIZE`가 정한다.

| API | 계약 |
| --- | --- |
| `begin()` | chosen I2C device readiness 확인 |
| `beginTransmission()` | address와 새 TX transaction 준비 |
| `write()` | TX buffer에 추가; overflow는 명시적 오류 |
| `endTransmission(true)` | write 또는 zero-byte address probe 실행 |
| `endTransmission(false)` | 같은 주소의 다음 read를 위한 write 보류 |
| `requestFrom(..., true)` | 보류 write와 repeated-start read 또는 단독 read |
| `requestFrom(..., false)` | 현재 미지원, 0과 진단 반환 |
| `setClock()` | 검증된 bus rate만 허용 |

NACK과 driver 오류는 Arduino 상태 값으로 변환하되 원래 errno를 보존한다. Address/data NACK을
항상 서로 다른 상태로 판별할 수 있다고 보증하지 않는다.

다른 Zephyr I2C client와 bus-wide lock을 공유하지 않는다. 여러 client가 같은 bus를 쓰면
application이 transaction을 직렬화해야 한다. Target/slave mode와 `Wire1`은 미지원이다.

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
| `begin()`/`end()` | chosen device readiness와 Core state 관리 |
| `beginTransaction(settings)` | 지원 frequency, mode와 bit order 검증; Core caller ownership 획득 |
| `transfer(byte/word/buffer)` | active transaction에서 full-duplex 전송 |
| `endTransaction()` | Core ownership과 transaction 상태 해제 |

Core mutex는 Arduino `SPI` caller끼리만 직렬화한다. Zephyr bus-wide lock이나 다른 driver client의
동기화를 제공하지 않는다. Sketch 소유 CS를 오류 복구 과정에서 임의 변경하지 않는다.

SPI00과 같은 hardware instance를 공유하는 `uart00`을 동시에 활성화하는 구성, chosen 누락과
다른 SPI instance 선택은 configure/build에서 명시적으로 실패시킨다. 다중 SPI bus는 미지원이다.

## 8. ADC와 `analogRead()`

- 지원 pin은 sparse ID 2의 `PIN_A0`/`A0` 하나다.
- A0에는 digital descriptor가 없다.
- `analogRead(A0)`는 fixed Devicetree ADC channel을 읽어 12-bit raw `0..4095`를 반환한다.
- 오류는 `-1`과 Analog subsystem 진단으로 보고한다.
- `analogReference()`는 `AR_DEFAULT`와 같은 의미의 `AR_INTERNAL`만 허용한다.
- Reference/gain/channel은 Devicetree 계약이며 runtime에서 바꾸지 않는다.
- `analogReadResolution()`은 제공하지 않는다.

Nominal reference/gain을 pin의 절대최대 정격이나 측정 정확도로 해석하지 않는다. 전기적 입력
범위는 nRF54L15와 NU54DK hardware 사양을 따른다.

## 9. PWM과 `analogWrite()`

- 지원 역할은 sparse ID 3의 `PIN_PWM0`/`PIN_PWM_LED` 하나다.
- `PIN_LED1` ID 4는 같은 physical resource를 설명하는 PWM-owned alias이며 digital descriptor가
  없다.
- `analogWrite()`는 고정 8-bit input `0..255`를 **20 ms로 고정한 period**의 pulse width로 변환한다.
  backend period가 정확히 20 ms가 아니면 요청을 거부한다.
- 지원 역할 이외의 pin은 ownership 오류로 거부한다.
- `analogWriteResolution()`과 runtime frequency setter는 제공하지 않는다.
- PWM을 true DAC 출력으로 표현하지 않는다.

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
| `CONFIG_NUCODE_ARDUINO_SERIAL_RX_BUFFER_SIZE` | Serial RX 고정 queue |
| `CONFIG_NUCODE_ARDUINO_WIRE` | chosen I2C `Wire` |
| `CONFIG_NUCODE_ARDUINO_WIRE_BUFFER_SIZE` | Wire TX/RX buffer |
| `CONFIG_NUCODE_ARDUINO_SPI` | chosen SPI controller |
| `CONFIG_NUCODE_ARDUINO_ADC` | A0 backend |
| `CONFIG_NUCODE_ARDUINO_PWM` | PIN_PWM0 backend |

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

현재 Serial, Wire, SPI, ADC/PWM production 경로와 관련 HIL은 완료됐다. Exact transaction 수,
frequency, payload, raw 측정값과 commit은 위 검증 문서가 소유한다.

## 14. 명시적 범위 밖

- `Serial1`, 임의 UART와 runtime pin remap
- I2C target/slave, `Wire1`
- 다중 SPI bus와 Core 소유 automatic chip-select
- ADC channel 확장, resolution setter와 정확도 보증
- PWM pin 확장, runtime frequency/resolution setter와 DAC
- peripheral I/O의 ISR-safe 호환층
