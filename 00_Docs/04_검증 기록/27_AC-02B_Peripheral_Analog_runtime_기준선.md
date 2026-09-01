# AC-02B Peripheral/Analog runtime 기준선

| 항목 | 내용 |
| --- | --- |
| 기록 ID | VALIDATION-AC02B-001 |
| 대상 | `v0.3.0` AC-02B |
| 판정 | **자동 구현·host/target build PASS, 물리 HIL 배선 대기** |
| 검증일 | 2026-09-01 |
| 기준 SDK | nRF Connect SDK v3.4.0 / Zephyr 4.4.0 |
| 기준 보드 | NU54DK / `nrf54l15dk/nrf54l15/cpuapp/nu54dk` |
| 기준 board package | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` |
| 기준 source | `731312c1dbec3c19a6073dddab7ad2c25d3b5a97` |
| 남은 gate | 두 NU54DK의 8선 fixture exact-commit HIL / M22 전체 27개 clean package compile |

## 1. 판정 요약

AC-02B는 AC-02A의 소유권 manager 위에 runtime pinctrl·PM lifecycle과 공개 Peripheral/Analog
API를 구현했다. Host 계약 시험과 NU54DK production target build는 통과했다. 두 역할의 실제
HIL image와 fail-closed runner도 준비했지만, 아직 8개 배선을 연결해 target protocol을 실행하지
않았다.

따라서 현재 판정은 다음과 같이 제한한다.

- production source 구현: 완료
- AC-02B host 계약: PASS
- AC-02B target·역할 image build/link: PASS
- 물리 Serial1/Wire/SPI/PWM/ADC HIL: **대기, PASS 아님**
- AC-02B 전체 완료: **아님**
- AC-02 전체 완료 및 `v0.3.0` stable 지원 선언: **아님**

`build-only`, parser PASS 또는 준비된 HIL token을 실제 전기·통신 PASS로 확대하지 않는다.

## 2. 자동 구현 기준선

### 2.1 Runtime route와 ownership

`RuntimePeripheralRoute`는 peripheral block과 signal별 GPIO pad를 하나의 lifecycle로 관리한다.
`setPins()`는 종료 상태에서 다음 `begin()`에 쓸 route만 stage한다. `begin()`은 route matrix와
소유권을 다시 검사하고 GPIO 상태를 snapshot한 뒤 peripheral owner로 handover하며, dynamic
pinctrl과 runtime PM을 활성화한다. `end()`는 driver를 정지하고 sleep/PM 경계를 거쳐 기존 GPIO
mode·latch·Arduino callback과 이전 pinctrl state를 복원한다.

다중 pad handover, pinctrl apply, PM get/put 또는 복원 중 하나라도 실패하면 중간 성공을 지원으로
남기지 않고 rollback 또는 faulted 상태로 닫는다. ISR에서 lifecycle을 변경하지 않으며, active
peripheral의 route를 즉시 바꾸지 않는다.

AC-02A 당시 부팅 registry에 고정했던 동적 주변장치 pad는 최종 runtime 구조에서 제거했다.
UART20 console만 boot-fixed owner이며, I2C22·SPI00·PWM20/21/22는 각 Arduino lifecycle이 필요한
시점에 pad와 block을 획득하고 종료 시 복원한다.

### 2.2 Serial

| 객체 | 현재 개발 계약 |
| --- | --- |
| `Serial` | `DT_CHOSEN(zephyr_console)`을 빌리는 non-owning wrapper. 115200 8N1과 현재 hardware 설정을 확인하고 RX lifecycle만 시작·종료한다. Console pinctrl·baud·전원 ownership은 바꾸지 않는다. |
| `Serial1` | 독립 `uart30`. 기본 RX P0.1/TX P0.0이며 `setPins(rx, tx)`는 종료 상태의 승인된 P0 route만 stage한다. `begin/end/rebegin`, 고정 IRQ RX queue와 polling TX를 제공한다. |

`Serial.begin()`을 임의 baud/pin 재구성 API로 사용하지 않는다. `Serial1`의 P0.0~P0.3은 NU54DK의
SB5~SB8/DAP UART 조립 조건과 관계가 있으므로 일반 GPIO capability와 uart30 route capability를
구분한다. `SerialUSB`는 target native USB device가 없어 제공하지 않는다.

### 2.3 Wire

`Wire`는 `i2c22` controller 한 개를 제공한다. 기본 SDA/SCL은 P1.2/P1.3이며 두 signal은 같은 P1
port의 open-drain 가능 route여야 한다. `setPins(sda, scl)`는 종료 상태에서만 다음 route를
stage하고, `begin/end/rebegin`, 100 kHz·400 kHz와 고정 TX/RX buffer를 제공한다.

지원하는 repeated-start는 같은 thread·같은 7-bit 주소에서
`endTransmission(false)`로 write를 보류한 뒤 `requestFrom(..., true)`가 한 번의
`i2c_write_read()`로 결합하는 형태다.

다음 기능은 구현하지 않았으며 capability에도 포함하지 않는다.

- `Wire.begin(address)`, target/slave mode와 `onReceive()`/`onRequest()`
- read를 no-STOP으로 끝내는 `requestFrom(..., false)`
- 두 번째 Arduino controller 객체 `Wire1`
- 다른 Zephyr client까지 포함하는 bus-wide arbitration

HIL peer가 사용하는 주소 `0x52`의 TWIS21은 DUT의 `Wire` controller를 검증하기 위한 direct
Zephyr fixture다. Arduino Wire target 지원을 가장하는 객체가 아니다.

### 2.4 SPI

`SPI`는 `spi00` controller 한 개다. nRF54L15의 전용 signal matrix에 따라 SCK P2.1, MOSI P2.2,
MISO P2.4만 승인한다. 따라서 `SPI.setPins()`는 임의 GPIO remap API가 아니라 종료 상태에서 이
정확한 route와 ownership을 검증·stage하는 API다.

`begin/end/rebegin`, mode 0~3, MSB/LSB, 8/16-bit와 buffer full-duplex transaction을 제공한다.
`usingInterrupt()`/`notUsingInterrupt()`는 등록한 Arduino GPIO callback만 transaction 동안
suspend/restore한다. SPI peripheral 자체 interrupt를 뜻하는 `attachInterrupt()`와
`detachInterrupt()`는 fail-closed `unsupported`이며, `SPI1`과 Core 소유 자동 chip-select는
제공하지 않는다.

### 2.5 ADC와 AIN0~AIN7 경계

`A0..A7`과 `PIN_AIN0..7` 이름은 실제 SAADC channel mapping을 보존한다. 그러나 이름의 존재가
모든 pad를 일반 계측 입력으로 허용한다는 뜻은 아니다.

| SAADC | Arduino 이름 | 실제 pad/보드 역할 | runtime 판정 |
| --- | --- | --- | --- |
| AIN0 | `A1`, `PIN_AIN0` | P1.4 / UART20 console TX | system-reserved, `analogRead()` 거부 |
| AIN1 | `A2`, `PIN_AIN1` | P1.5 / UART20 console RX | system-reserved, `analogRead()` 거부 |
| AIN2 | `A3`, `PIN_AIN2` | P1.6 / UART20 RTS | system-reserved, `analogRead()` 거부 |
| AIN3 | `A4`, `PIN_AIN3` | P1.7 / UART20 CTS | system-reserved, `analogRead()` 거부 |
| AIN4 | `A5`, `PIN_AIN4` | P1.11 / PMIC·system 입력 | system-reserved, `analogRead()` 거부 |
| AIN5 | `A0`, `PIN_AIN5` | P1.12 / 공개 A0 | 지원 대상 |
| AIN6 | `A6`, `PIN_AIN6` | P1.13 / SW0 | 읽기 가능하지만 버튼·pull 회로의 전기적 부하를 포함 |
| AIN7 | `A7`, `PIN_AIN7` | P1.14 / LED3 | 읽기 가능하지만 LED 회로의 전기적 부하를 포함 |

`analogReadResolution()`은 8/10/12/14 bit를 허용한다. ADC block과 pad는 한 read 동안만
transient 획득하고 기존 GPIO input 상태를 복원한다. Output으로 구성된 pad, system owner,
지원하지 않는 reference/channel은 fail-closed로 거부한다.

AIN6·AIN7의 software 지원은 보드 회로의 pull-up, switch, LED 저항과 누설을 제거하지 않는다.
입력 전압과 source impedance는 nRF54L15·NU54DK 전기 사양을 따라야 하며 이 기준선은 ADC 절대
정확도나 전압 허용 범위를 보증하지 않는다.

### 2.6 PWM, tone과 Servo

| 기능 | 전용 block | 현재 개발 계약 |
| --- | --- | --- |
| `analogWrite()` | PWM20 | 최대 4 channel, 같은 block의 active channel은 period 공유 |
| `tone()`/`noTone()` | PWM21 | 한 channel, 50% duty, 선택적 duration work |
| `Servo` | PWM22 | 최대 4 channel, 20 ms refresh, 고정 메모리 |

`analogWriteResolution()`은 1~16 bit, `analogWriteFrequency()`는 driver가 표현 가능한 nonzero
frequency를 허용한다. 같은 PWM20에서 여러 channel이 활성일 때 period가 다르면 변경을 거부한다.
출력과 PWM capability를 모두 가진 P1 route만 사용할 수 있으며 system/input-only pin은 거부한다.
P1.0/P1.1은 LFXO 조립 조건을 사용자가 승인한 전용 profile이 아니면 기본 profile에서 비활성이다.

`tone`과 `Servo`를 별도 PWM block에 배치해 `analogWrite`의 period와 분리했다. Servo motor 전원은
NU54DK GPIO에서 공급하지 않으며 signal과 공통 GND 외의 전원 설계는 사용자 책임이다.

## 3. 자동 시험 결과

### 3.1 Host 계약

| 시험 | 결과 | 확인 범위 |
| --- | --- | --- |
| `tests/host/test_ac02b_b2_contract.py` | 6/6 PASS | 공개 concrete type, route matrix, lifecycle와 미지원 기능 fail-closed |
| `tests/host/test_ac02b_analog_contract.py` | 7/7 PASS | ADC/PWM 계산, allocator, tone/Servo, fail-closed 복구와 예제 구조 |
| `tests/hil/nu54dk/test_ac02b_peripheral.py` | 8/8 PASS | nonce·순서·FAIL·ADC 범위·UID/MSD/COM·WIRING_REQUIRED gate |
| 전체 host fixed gate | 425 total / 423 PASS / 2 skipped | AC-02B를 포함한 전체 host 회귀, 실패 0 |
| CI contract | 34/34 PASS | Windows 짧은 outdir, workflow와 고정 도구 계약 |

Host parser PASS는 target 전기 동작을 뜻하지 않는다.

### 3.2 Target build

| Application | 결과 | 확인 범위 |
| --- | --- | --- |
| `tests/zephyr/ac02b_b2_contract` | PASS | Serial1/Wire/SPI production route와 PM lifecycle compile/link; FLASH 95,576 B/RAM 46,408 B |
| `tests/zephyr/ac02b_analog_contract` | PASS | ADC/PWM/tone/Servo target 계약 compile/link; FLASH 98,560 B/RAM 44,960 B |
| `tests/zephyr/ac02b_hil_dut` | PASS | Arduino production API를 직접 호출하는 DUT image; FLASH 80,188 B/RAM 49,280 B |
| `tests/zephyr/ac02b_hil_peer` | PASS | direct Zephyr uart30/TWIS21/GPIO peer image; FLASH 40,312 B/RAM 19,424 B |
| 전체 고정 target gate | 27/27 PASS | failed 0, error 0, filtered 0, warning 0 |

표의 크기는 최종 안전 회귀 시점의 contract build 관찰값이며 릴리스 용량 보증이 아니다. 전체
고정 target gate는 `C:\t\h`의 짧은 Windows outdir에서 실행했다. 두 HIL role의 Twister metadata는
`build_only: true`이므로 `READY` 한 줄로 물리 PASS를 만들지 않는다.

## 4. Arduino 예제 기준선

현재 source tree에는 public library 6개와 Arduino 예제 27개가 있다.

| Library | 예제 |
| --- | --- |
| `NUCODE_NU54DK` | AnalogChannels, AnalogReadA0, AnalogResolution, Blink, BoardInfo, CounterAlarm, DynamicPWM, InterruptButton, PWMFade, Serial1RuntimePins, SerialEcho, SettingsStorage, SPI00RuntimePins, SystemOffWake, ToneOutput, WatchdogBasic, WireRuntimePins |
| `Wire` | WirePmicId |
| `SPI` | SPITransaction |
| `Servo` | Sweep |
| `NUCODE_BLE` | CustomGattCentral, CustomGattPeripheral, GAPCentral, GAPPeripheral, NUSCentral, NUSPeripheral |
| `NUCODE_BLE_Security` | SecureKeyboard |

AC-02B에서 새로 추가된 8개 예제는 AnalogChannels, AnalogResolution, DynamicPWM,
Serial1RuntimePins, SPI00RuntimePins, ToneOutput, WireRuntimePins와 Servo/Sweep다. 고정 source
snapshot에서 신규 예제 8/8 Arduino CLI compile과 설치 예제 discovery 27/27을 통과했다. 이는 기존
19개와 신규 8개를 합친 27개 전체 clean package compile PASS를 뜻하지 않으며, 해당 통합 gate는
M22에서 다시 고정한다.

## 5. 물리 HIL 대기 fixture

Board A는 Arduino Core DUT, Board B는 direct Zephyr peer다. 두 보드 전원을 끈 뒤 다음 8가닥을
연결한다.

| 번호 | Board A(DUT) | 방향 | Board B(peer) | 목적 |
| --- | --- | --- | --- | --- |
| 1 | GND | ↔ | GND | 공통 기준 전압 |
| 2 | P0.0 / Serial1 TX | → | P0.1 / uart30 RX | Serial1 A→B |
| 3 | P0.1 / Serial1 RX | ← | P0.0 / uart30 TX | Serial1 B→A |
| 4 | P1.2 / Wire SDA | ↔ | P1.2 / TWIS21 SDA | I2C data |
| 5 | P1.3 / Wire SCL | ↔ | P1.3 / TWIS21 SCL | I2C clock |
| 6 | P1.10 / PWM20 | → | P1.14 / GPIO capture | 1 kHz, 25%·75% capture |
| 7 | P1.12 / A0 | ← | P2.5 / GPIO output | ADC LOW·HIGH |
| 8 | P2.2 / SPI00 MOSI | ↔ 같은 Board A의 P2.4 / SPI00 MISO | 해당 없음 | 4 MHz local loopback |

두 보드 기본 회로의 I2C pull-up을 사용하므로 별도 외부 저항은 요구하지 않는다. 시험 target은
`0x52`이며 BQ25186 주소 `0x6A`에는 접근하지 않는다. 두 보드 USB, 서로 다른 CMSIS-DAP UID·MSD·COM과
role별 exact HEX를 함께 사용한다.

Runner는 배선 승인 전 preflight까지만 수행하고 종료 코드 3의 `WIRING_REQUIRED`로 멈춘다.
`--acknowledge-wiring` 뒤에도 nonce, exact role image/build record, Core·board revision, source digest,
flash 전후 SHA-256과 양쪽 token 전체가 일치해야만 evidence를 기록한다.

## 6. 남은 완료 gate

1. 위 8가닥과 두 보드 identity를 확인한다.
2. clean exact commit에서 DUT·peer를 다시 pristine build한다.
3. `ac02b_peripheral.py`를 실행해 Serial1 end/rebegin, Wire 100/400 kHz repeated-start, SPI
   transaction/interrupt mask, PWM external edge와 ADC external LOW/HIGH를 검증한다.
4. DUT·peer transcript와 JSON evidence를 보존한다.
5. 기존 AC-01, M7, M14, M16과 BLE profile 회귀 및 27개 package example compile을 실행한다.
6. 제약을 API matrix에 고정한 뒤에만 AC-02B와 AC-02 완료 여부를 판정한다.

## 7. 관련 문서

- [v0.3.0 구현 마일스톤](<../01_아두이노 코어 설계/07_v0.3.0_구현_마일스톤.md>)
- [Arduino API 지원 범위](<../01_아두이노 코어 설계/04_Arduino_API_지원_범위.md>)
- [주변장치 API](<../03_펌웨어 설계/03_주변장치_API.md>)
- [테스트와 검증](<../03_펌웨어 설계/04_테스트와_검증.md>)
- [AC-02A 소유권 기준선](26_AC-02A_핀과_주변장치_소유권_기준선.md)
- [AC-02B HIL 실행 안내](<../../tests/hil/nu54dk/README.md>)
