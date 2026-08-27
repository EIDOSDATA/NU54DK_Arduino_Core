# M7 Wire·SPI·ADC·PWM 기준선

| 항목 | 내용 |
| --- | --- |
| 상태 | **완료** |
| 작성자 | Quantum / NUCODE |
| 라이선스 | MIT |
| 기준 SDK | nRF Connect SDK v3.4.0 |
| 기준 Zephyr | Zephyr 4.4.0 |
| 기준 타깃 | `nrf54l15dk/nrf54l15/cpuapp/nu54dk` |
| 보드 package | `board_package/NU54DK_Zephyr_DTS`, `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` |
| 검증 상태 | 자동 회귀, BQ25186 I2C·ADC/PWM HIL과 SPI00 4 MHz 40-byte 물리 loopback 통과 |

---

## 1. 목적과 판정 원칙

이 문서는 M7에서 추가하는 Arduino `Wire`, `SPI`, `analogRead()`와 `analogWrite()`의
구현 계약, 하드웨어 안전 경계와 검증 결과를 한곳에 보관한다. 소스나 시험 코드가
존재한다는 사실만으로 기능을 지원 또는 완료로 판정하지 않는다.

현재 문서는 구현 명칭과 확정된 target·Arduino CLI·HIL 결과를 기록한 **완료 기준선**이다.
실제 BQ25186 `MASK_ID` repeated-start와 P2.2 MOSI→P2.4 MISO의 SPI00 4 MHz 40-byte
loopback이 모두 통과했다. 실제 명령의 exit code, case 수, 메모리와 NU54DK HIL 결과는 확보된
실행 증거만 기록한다.

M7 최초 판정 당시 M6는 실제 P1.13 버튼 ISR edge 확인만 남아 있었다. 이후 독립적인
단계형 물리 HIL에서 `FALLING`, `RISING`, `CHANGE`를 확인해 M6는 **완료**로 변경했다.
이후 M7도 I2C와 SPI 물리 HIL을 완료해 잔여 조건을 해소했다.

---

## 2. 범위와 단계 경계

### 2.1 M7 포함 범위

- ArduinoCore-API `HardwareI2C` 기반 전역 `Wire`
- ArduinoCore-API `HardwareSPI` 기반 전역 `SPI`
- I2C22의 controller/master 전송과 제한된 clock 변경
- SPI00의 controller transaction과 full-duplex 전송
- A0의 고정 12-bit raw ADC 읽기
- P1.10 PWM 역할의 고정 8-bit `analogWrite()`
- Devicetree/Kconfig 계약, 내부 진단과 target emulator 회귀 시험
- 안전한 경우에만 실제 NU54DK 주변장치 HIL

### 2.2 M7 제외 범위

- Arduino IDE/CLI Upload 또는 Flash recipe
- pyOCD/J-Link runner 선택, erase, recover와 debug 통합
- I2C target/slave mode와 `Wire1`
- SPI peripheral mode, 다중 SPI bus와 자동 chip-select
- `analogReadResolution()`과 `analogWriteResolution()`
- 임의 GPIO의 PWM 전환, DAC, Servo와 audio
- BQ25186 제어와 VBAT service

Upload/Flash recipe와 pyOCD/J-Link 선택은 M7 완료 당시 범위 밖이었다. 이후 M8에서 Arduino
Upload recipe와 pyOCD 기본·J-Link 선택 경로를 완료했다. M7 HIL의 기존 DAPLink MSD 기록은
M8 Arduino upload 증거로 소급 계산하지 않는다.

---

## 3. 보드 package와 물리 매핑

보드 package는 읽기 전용 단일 원본으로 사용한다. M7은 서브모듈 내부 파일이나 상위 gitlink를
변경하지 않는다.

| Arduino 역할 | Devicetree 원본 | NU54DK 물리 경로 | M7 계약 |
| --- | --- | --- | --- |
| `Wire` | `nucode,arduino-wire` chosen → I2C22 | SDA P1.2, SCL P1.3 | controller, 기본 100 kHz |
| `SPI` | `nucode,arduino-spi` chosen → SPI00 | SCK P2.1, MOSI P2.2, MISO P2.4 | Core overlay로 활성화, CS 제외 |
| `A0`/`PIN_A0` | `nucode,arduino-adc` chosen의 `io-channels` | SAADC channel 5, AIN5/P1.12 | 12-bit raw, gain 1/4, internal reference |
| `PIN_PWM0`/`PIN_PWM_LED` | `nucode,arduino-pwm` chosen → 보드 `pwm_led1` (`pwm-led0` alias 대상) | pwm20 channel 0, P1.10 | 20 ms period, 8-bit duty |
| `LED_BUILTIN` | `led0` alias | P2.9 | digital GPIO이며 PWM 핀이 아님 |

`LED_BUILTIN`을 `analogWrite()` 대상으로 해석하지 않는다. PWM 역할은 별도 논리 index 3인
`PIN_PWM0`/`PIN_PWM_LED`다. `A0`는 index 2이며 기존 `NUM_DIGITAL_PINS=2`의 digital
descriptor 범위에 포함되지 않는다.

읽기 전용 보드 package의 channel 5는 `ADC_GAIN_1_6`을 선언하지만 nRF54L15 SAADC driver가
이 gain을 지원하지 않아 실제 read에서 `-EINVAL`이 발생한다. 보드 서브모듈을 수정하지 않고
Core builder·sample·example overlay가 같은 channel 5를 internal reference, 12-bit,
`ADC_GAIN_1_4`로 override한다. 이 값은 NCS v3.4.0의
`boards/seeed/xiao_nrf54l15/xiao_nrf54l15_common.dtsi`와 같은 nRF54L15 계약이다.

SPI00은 보드 package에서 pinctrl만 정의되고 기본 비활성이다. Core 소유 application overlay가
SPI00을 활성화하고, Sketch overlay가 필요하면 그 뒤에서 명시적으로 재정의한다. SPI00과
`uart00`은 같은 하드웨어 영역을 공유하므로 동시 활성 구성을 허용하지 않는다. I2C22 대신
SPI22를 M7 기본 `SPI`로 사용하지 않는다. NU54DK production Core는
`nucode,arduino-spi` chosen이 반드시 SPI00을 가리키게 빌드 시 검사한다. fake driver로 의미를
검증하는 M7 target test만 명시적인 test 전용 compile definition으로 이 board-instance 검사를 우회한다.

---

## 4. 공개 API와 구성 명칭

| 영역 | 확정 명칭 |
| --- | --- |
| Wire 형식 | `TwoWire` = `arduino::HardwareI2C` |
| Wire 객체 | `TwoWire &Wire` |
| SPI 형식 | `SPIClass`, `SPISettings` |
| SPI 객체 | `SPIClass &SPI` |
| Analog 입력 | `PIN_A0`, `A0` = 2 |
| PWM 출력 | `PIN_PWM0`, `PIN_PWM_LED` = 3 |
| 전체 역할 수 | `NUM_PIN_ROLES` = 4 |
| ADC reference | `AR_DEFAULT` = 0, `AR_INTERNAL`은 같은 값의 설명용 별칭 |

`Wire`와 `SPI`의 Arduino library 진입점은 각각 `libraries/Wire/src/Wire.h`와
`libraries/SPI/src/SPI.h`다. 실제 Zephyr backend는 Core source에서 한 번만 컴파일해 Arduino
library discovery와 Core link가 같은 구현을 중복 편입하지 않게 한다.

M7 Kconfig 명칭은 다음과 같다.

- `CONFIG_NUCODE_ARDUINO_WIRE`
- `CONFIG_NUCODE_ARDUINO_WIRE_BUFFER_SIZE`
- `CONFIG_NUCODE_ARDUINO_SPI`
- `CONFIG_NUCODE_ARDUINO_ADC`
- `CONFIG_NUCODE_ARDUINO_PWM`

module 수준 기본값은 `n`으로 두고 Arduino builder template이 기본 Arduino profile에서 필요한
항목을 `y`로 활성화한다. 이렇게 해야 Core overlay를 사용하지 않는 기존 west sample과 ztest가
M7 기능 때문에 깨지지 않는다.

### 4.1 파일과 책임

| 경로 | 책임 |
| --- | --- |
| `cores/arduino/Wire.cpp` | Zephyr I2C controller와 ArduinoCore-API `HardwareI2C` 연결 |
| `cores/arduino/SPI.cpp` | CS 없는 Zephyr SPI controller와 `SPIClass` 연결 |
| `cores/arduino/wiring_analog.cpp` | chosen ADC/PWM spec과 `analogRead()`/`analogWrite()` 연결 |
| `cores/arduino/internal/{Wire,SPI,Analog}Backend.h` | Sketch에 공개하지 않는 상태·errno 진단 계약 |
| `libraries/Wire/src/Wire.h`, `libraries/SPI/src/SPI.h` | Arduino library discovery용 thin public header |
| `variants/nu54dk/variant.h` | A0/PWM 논리 역할, 역할 수와 고정 reference 상수 |
| `dts/bindings/misc/nucode,arduino-adc-input.yaml`, `zephyr/module.yml` | Core 소유 ADC 역할 holder의 binding과 module DTS root 등록 |
| `zephyr/Kconfig` | M7 backend의 opt-in 구성 |
| `zephyr/CMakeLists.txt`, `zephyr/cmake/write_build_record.cmake` | source 편입과 configure/live build record가 공유하는 Core provenance 입력 범위 |
| `tools/nu54-builder/templates/zephyr-app/{prj.conf,app.overlay}` | Arduino 기본 profile의 M7 Kconfig와 chosen/SPI00 활성화 |
| `tests/zephyr/m7_core_api` | NU54DK target emulator/fake-driver 의미 회귀 |
| `tests/zephyr/m7_config_contract` | chosen 누락·잘못된 SPI instance·SPI00/uart00 충돌 expected-fail 자동 fixture |
| `tests/hil/m7_i2c_pmic.py` | 고정 BQ25186 0x6A/0x0C 읽기 전용 I2C HIL host protocol |
| `examples/03.Analog`, `examples/04.Communication` | Arduino CLI discovery·compile과 사용자 계약 예제 |
| `samples/zephyr/{wire_pmic_id,spi_transaction,analog_read_a0,pwm_fade}` | west-native build 및 승인된 실기 경로 |

Core backend는 `cores/arduino`에서 한 번만 컴파일한다. `libraries/Wire`와 `libraries/SPI`는
`Arduino.h`를 포함하는 진입점일 뿐 구현 source를 복제하지 않는다. 보드 package에는 위
chosen이나 예제를 추가하지 않으며, builder의 Core overlay가 읽기 전용 보드 DTS 역할을
선택한다.

---

## 5. Wire 계약과 0x6A 안전 경계

### 5.1 지원 범위

- controller/master mode
- `begin()`, `end()`
- `beginTransmission()`, `write()`, `endTransmission()`
- `requestFrom()`, `available()`, `read()`, `peek()`
- 100 kHz와 400 kHz `setClock()`
- `endTransmission(true)`의 zero-byte address-only probe
- 기본 32-byte 고정 TX/RX buffer
- thread 문맥의 blocking transfer

`begin(address)`, `onReceive()`와 `onRequest()`의 target/slave 의미는 제공하지 않는다.
zero-byte probe는 `i2c_write(..., length=0)`로 controller에 실제 전달한다. 성공은 status 0이고
negative driver errno는 아래와 같은 공개 status로 변환하면서 원래 errno를 비공개 진단에
보존한다. 이 Core 계약을 HIL의 임의 주소 scan 허용으로 해석하지 않는다.
TX buffer overflow는 공개 status 1, `-ETIMEDOUT`은 5이며 그 밖의 negative driver errno는
공개 status 4로 변환한다. address/data NACK을 2와 3으로 세분화하지 않으며 원래 errno는 비공개 진단에
보존한다. target ztest는 overflow와 `-EIO`→4·원본 errno 보존을 검증했다.

### 5.2 deferred repeated-start

nRF TWIM을 사용하는 Zephyr 4.4에서는 마지막 단독 message의 no-STOP transaction을 사용할 수
없다. 따라서 `endTransmission(false)`는 write를 즉시 전송하지 않고 address와 TX buffer를
보류한다. 같은 주소의 다음 `requestFrom(address, length, true)`가 보류된 write와 read를
`i2c_write_read()` 한 transaction으로 결합한다.

~~~text
beginTransmission(address)
  → write(register)
  → endTransmission(false): bus 전송 없이 보류
  → requestFrom(same_address, length, true)
  → WRITE + RESTART + READ + STOP
~~~

보류 중 다른 주소를 요청하거나 새 transmission을 시작하면 예상하지 않은 write를 보내지 않고
오류로 처리한다. 마지막 read 뒤 STOP을 생략하는 `requestFrom(..., false)`는 M7에서
**미지원**이며 0과 `unsupported_no_stop_read` 진단을 반환한다.

### 5.3 BQ25186 읽기 전용 HIL 안전 경계

외장 Qwiic 센서를 분리한 뒤 NU54DK 온보드 BQ25186을 고정 target으로 사용한다. HIL
image·host runner·실행 절차는 7-bit address `0x6A`의 `MASK_ID(0x0C)` pointer write와
repeated-start 1-byte read만 실행한다. 반환 byte의 하위 nibble Device ID가 `0x1`인지
판정하며 상위 interrupt-mask bit는 허용한다.

다음 동작은 하지 않는다.

- register data write
- address-only probe와 I2C scan
- 다른 register 접근
- 다른 주소 fallback 재시도

HIL command line·UART protocol에는 address, register 또는 scan 옵션을 노출하지 않는다.
첫 transaction은 BQ25186 기본 watchdog을 시작할 수 있으므로 고정 ID read를 한 번 수행한 뒤
종료한다. 범용 Arduino `Wire` 객체 자체에는 주소 blacklist를 두지 않는다.

P1.2/P1.3은 nRF54L15 NFC 전용 패드다. 초기 실패에서 두 line이 LOW이고 Zephyr driver가
`-ETIMEDOUT(-116)`을 반환했다. `nfct`를 disabled로 둔 것만으로는 패드가 GPIO/TWIM으로
전환되지 않았으며, Core의 Builder·Wire sample overlay에
`&uicr { nfct-pins-as-gpios; };`를 추가한 뒤 통신이 정상화됐다. 내부 pull-up을 제거한
상태에서도 통과했으므로 회로의 외부 pull-up 경로가 동작함을 확인했다. 보드 서브모듈은
수정하지 않았다.

---

## 6. SPI 계약

SPI00은 Core overlay가 P2.1/P2.2/P2.4 pinctrl과 함께 활성화한다. 전역 `SPI`는 controller
mode와 thread 문맥에서만 동작한다.

- `begin()`/`end()`
- `beginTransaction(SPISettings)`/`endTransaction()`
- mode 0~3
- MSB-first와 LSB-first
- transaction별 frequency; shipped sample/HIL 기본은 4 MHz
- `transfer(uint8_t)`, `transfer16()`와 in-place buffer transfer
- Zephyr `spi_transceive()` 기반 8-bit full-duplex

SPI00의 자동 CS는 제공하지 않는다. CS가 필요한 장치는 Sketch가 별도 digital GPIO를 선택해
실제 transfer 구간 앞뒤에서 직접 제어한다. Core가 임의의 SS 핀이나 sensor child node를 만들지
않는다. `usingInterrupt()`, `notUsingInterrupt()`, `attachInterrupt()`와
`detachInterrupt()`의 interrupt 연동은 M7에서 미지원 진단 대상이다.

`beginTransaction()`은 Arduino caller의 Core owner/state만 설정한다. 내부 `spi_mutex`는 각
API와 driver 호출 동안만 유지하며 `SPI_LOCK_ON`/`spi_release()`로 Zephyr bus를 transaction
전체에 걸쳐 독점하지 않는다. 따라서 다른 Zephyr SPI client와 함께 쓰려면 application 수준의
별도 직렬화가 필요하다.

NU54DK SPI00의 128 MHz core clock은 4..126 범위의 짝수 prescaler를 사용한다. 따라서
1 MHz는 divider 128이 필요해 표현할 수 없고, 4 MHz는 divider 32로 표현할 수 있다.
sequence 14에서는 1 MHz가 첫 transfer에서 driver `-EINVAL`로 드러났다. 최종 Core는
nrfx runtime predicate `(128 MHz % frequency) < prescaler`와 prescaler 짝수·4..126 범위를
`beginTransaction()`에서 동일하게 선검증한다. 이 조건은 exact-division만 허용하지 않으므로
near-divisor가 통과할 수 있고 실제 SCK는 128 MHz/prescaler로 양자화된다. Core가 별도의
가까운 frequency를 탐색하거나 선택하지는 않으며 실제 driver 호출의 원래 errno는 비공개
진단에 보존한다. shipped sample/HIL 기본값은 정확한 div32의 4 MHz로 바꾸었고 sequence 17에서
수정 image를 재시험했다.

P2.2 MOSI와 P2.4 MISO를 직접 연결한 실제 SPI00 4 MHz loopback은 40-byte 고정 패턴으로
검증한다. 외부 로직 애널라이저와 오실로스코프는 완료 조건이 아니다.

---

## 7. ADC와 PWM 계약

### 7.1 A0

`analogRead(A0)`는 P1.12의 SAADC channel 5를 동기식으로 읽는다. 최종 Devicetree의 12-bit,
`ADC_GAIN_1_4`, `ADC_REF_INTERNAL` 계약이 다르면 조용히 다른 설정으로 읽지 않고 진단한다.
성공 결과는 0~4095 raw 값으로 제한하고, 잘못된 pin·문맥·DTS 또는 driver 오류는 `-1`을
반환하면서 비공개 진단 상태를 남긴다.

`analogReference()`는 `AR_DEFAULT`만 허용하고 `AR_INTERNAL`은 같은 값의 설명용 별칭이다.
Devicetree 설정을 runtime에 바꾸지 않는다.
Vendored ArduinoCore-API 1.5.2에는 `analogReadResolution()` 선언이 없으므로 M7에서 추가하지
않는다. VBAT voltage-divider consumer도 자동 활성화하지 않는다.

internal 0.6 V reference와 gain 1/4 조합의 nominal full-scale 입력은 약 2.4 V다. 이보다
높은 입력은 12-bit raw에서 saturation될 수 있지만, 2.4 V는 핀의 절대최대 정격 안내가
아니다. 정확도와 허용 입력 전압은 nRF54L15 및 NU54DK 전기 사양을 따라야 하며 M7 API는
전압 환산이나 안전 정격이 아니라 raw 0..4095만 계약한다.

### 7.2 PWM

`analogWrite(PIN_PWM0, value)`와 `analogWrite(PIN_PWM_LED, value)`는 같은 논리 역할이다.
값 범위는 0~255이며 다른 값은 clamp하지 않고 거부한다. Core overlay의
`nucode,arduino-pwm` chosen이 보드 `pwm_led1` 역할을 선택하며, 이 node는 `pwm-led0` alias와
같은 20 ms normal-polarity PWM이다. pulse 계산은 64-bit 중간 연산으로 overflow를 피한다.

P1.10 PWM 역할을 digital pin으로 추가하지 않으므로 M7에는 GPIO↔PWM 자동 ownership 전환이
없다. `analogWrite(LED_BUILTIN, ...)`과 임의 digital pin은 거부한다. Vendored API에 없는
`analogWriteResolution()`도 구현하지 않는다.

---

## 8. 검증 행렬

현재 결과는 확보한 최종 실행 증거를 기준으로 한다. 실제 장치나 fixture가 없어 입증하지 못한
범위는 `미확정` 또는 `미검증`으로 구분한다.

| 시험 | 현재 결과 | 통과 기준 |
| --- | --- | --- |
| Wire production pristine build | **PASS** | FLASH 44,628 B, RAM 17,720 B; NFC 패드 전환 overlay 포함 |
| SPI 4 MHz production pristine build | **PASS** | FLASH 44,372 B, RAM 17,728 B |
| ADC gain 1/4 production pristine build | **PASS** | FLASH 43,256 B, RAM 17,688 B |
| PWM production pristine build | **PASS** | FLASH 37,096 B, RAM 17,160 B |
| M7 Core target build | **PASS** | pristine 310/310, FLASH 100,548 B, RAM 28,376 B |
| Wire repeated-start emulator | **PASS** | target ztest Wire suite 4/4에 포함 |
| Wire zero-byte address probe | **PASS** | `endTransmission(true)`의 0-byte write·STOP과 driver 오류 변환을 target ztest로 검증 |
| Wire overflow/generic error/clock | **PASS** | overflow와 `-EIO`→4·원본 errno, 100/400 kHz를 Wire 4/4에서 검증 |
| BQ25186 HIL 안전 경계 | **PASS** | host protocol을 0x6A/0x0C read-only로 고정; register data write·scan·fallback 없음 |
| BQ25186 비활성 유지 | **PASS** | 최종 generated Devicetree에서 `status = "disabled"` 확인 |
| SPI mode·bit order·transfer | **PASS** | target ztest SPI suite 3/3에 포함 |
| SPI lifecycle/error recovery | **PASS** | target ztest SPI suite 3/3에 포함 |
| ADC emulator | **PASS** | target ztest ADC suite 2/2, gain 1/4 최종 계약 |
| PWM fake driver | **PASS** | target ztest PWM suite 2/2 |
| HIL host protocol unittest | **PASS** | 고정 BQ25186 PMIC 5/5 + loopback 강화 peripheral parser 7/7, 합계 12/12 |
| Arduino CLI M7 smoke | **PASS** | fresh isolated `--tests m7`, exit 0; 4/4 compile/artifact와 전체 Kconfig y/n matrix·chosen·Sketch overlay 원문 병합 |
| live build record provenance | **PASS** | public header·`library.properties`·DTS binding 독립 mutation마다 `core_source_sha256` 변경, `core_revision` dirty와 복원 확인 |
| Builder incremental invalidation | **PASS** | `module.yml`과 DTS binding을 순서대로 독립 변경; 같은 workspace, 각각 재configure, pristine configure 누계 1 |
| 전체 staged Builder 회귀 | **PASS** | session 87999, exit 0; blink·library·config·error·parallel·incremental·m6·m7 named group 8/8 |
| Wire chosen 누락 negative | **PASS** | expected-fail; `NUCODE_M7_WIRE_CHOSEN_REQUIRED` 일치 |
| non-SPI00 chosen negative | **PASS** | expected-fail; `NUCODE_M7_SPI_CHOSEN_MUST_BE_SPI00` 일치 |
| SPI00/uart00 충돌 negative | **PASS** | expected-fail; `NUCODE_M7_SPI_UART00_CONFLICT` 또는 Zephyr mutual-exclusion 진단 일치 |
| NU54DK BQ25186 I2C | **PASS** | seq33 100 kHz·seq34/42 400 kHz에서 `MASK_ID(0x0C)=0x41`, Device ID 0x1과 repeated-start 확인 |
| NU54DK ADC raw | **PASS** | 최종 loopback seq2에서 gain 1/4 A0 raw=3176; 0..4095 범위만 검증, 전압 정확도 주장 없음 |
| NU54DK PWM | **PASS** | 최종 loopback seq2에서 driver duty 0/128/255 실행; 실제 파형 주장 없음 |
| NU54DK SPI 4 MHz driver 경로 | **PASS** | 최종 loopback seq2에서 4 MHz/div32 40-byte transfer 성공 |
| NU54DK 물리 SPI data 경로 | **PASS** | P2.2 MOSI→P2.4 MISO, 40-byte `MUL37_ADD5A` 고정 패턴 전부 일치 |

HIL host protocol은 주소나 register를 command-line 또는 UART payload로 임의 변경할 수 없게
고정한다. 허용 요청은 BQ25186 `0x6A/0x0C` 읽기 하나뿐이다.

live build record는 configure fingerprint와 같은 `cores`, `dts`, `libraries`, `third_party`,
`variants`, `zephyr` 범위를 사용한다. M7 CLI 회귀는 public header, SPI library metadata와 ADC
binding을 각각 따로 변경해 hash와 dirty 표기가 바뀌는지 확인하고, 각 변경을 복원한 뒤 clean
revision과 기준 hash가 돌아오는지도 검증했다.

별도 incremental 회귀는 같은 staged package에서 `zephyr/module.yml`을 변경한 뒤 한 번,
DTS binding을 변경한 뒤 다시 한 번 configuration fingerprint가 바뀌고 configure가 생략되지
않는지 독립적으로 확인했다. 두 경우 모두 기존 Zephyr workspace를 유지했으며 pristine configure
누계는 1에서 늘지 않았다.

최종 target ztest image는 gain 1/4, SPI frequency 선검증과 zero-byte address probe 보강 뒤
pristine 310/310으로 빌드되었고 FLASH 100,548 B, RAM 28,376 B를 사용했다. 최초 승인
sequence 20에서는 283,136-byte image를 기록한 뒤 COM10에서 1/1 configuration,
Wire 4, SPI 3, ADC 2, PWM 2의 합계 11/11과 `PROJECT EXECUTION SUCCESSFUL`을 확인했다.
2026-08-27 최종 source 재검증은 DAPLink sequence 41로 같은 283,136-byte image를 기록하고
pyOCD로 11개 `ztest_unit_test_stats`를 회수했다. 모든 case가 `run=1`, `skip=0`, `fail=0`,
`pass=1`이었다. 이 실행에서는 DAPLink 재열거 중 일회성 COM10 출력은 회수하지 못했으므로,
판정은 target RAM의 Zephyr ztest 통계로 독립 확인했다.

negative 구성 3건도 실제 NCS expected-fail build로 판정했다. Wire chosen 누락은
`NUCODE_M7_WIRE_CHOSEN_REQUIRED`, SPI chosen이 SPI00이 아닌 구성은
`NUCODE_M7_SPI_CHOSEN_MUST_BE_SPI00`, SPI00과 uart00 동시 활성은
`NUCODE_M7_SPI_UART00_CONFLICT` 또는 Zephyr peripheral mutual-exclusion 진단을 확인했다.

초기 실제 I2C HIL은 P1.2/P1.3 NFC 패드가 GPIO/TWIM으로 전환되지 않아 두 line이 LOW였고
Zephyr driver가 `-ETIMEDOUT(-116)`을 반환했다. Wire Core의 deferred repeated-start는
`i2c_write_read()` 한 호출로 정상 구성되어 있었으며 문제는 transaction 분할이 아니었다.
Core 소유 overlay에 `nfct-pins-as-gpios`를 추가한 뒤 내부 pull-up을 제거하고 다시 시험했다.

최종 실제 I2C HIL은 COM10에서 BQ25186 고정 요청만 실행했다. DAPLink sequence 33은
125,952-byte 100 kHz image, sequence 34는 같은 크기의 400 kHz image를 기록했다. 두 실행 모두
`NUCODE_M7_I2C_RESULT:6A:0C:41:RS`를 반환해 Device ID 하위 nibble `0x1`과
repeated-start를 확인했다. 최종 source와 외부 pull-up만 사용한 400 kHz 재검증도 sequence 42에서
동일하게 PASS했다. register data write, scan 또는 fallback은 실행하지 않았다.

첫 ADC 실기 HIL은 DAPLink sequence 14에서 `ADC_GAIN_1_6` 구성 때문에 Zephyr driver
`-EINVAL`로 실패했다. 이 실패는 숨기지 않는다. 원인은 nRF54L15가 해당 gain을 지원하지 않는
것으로 확인했으며, Core 소유 overlay의 channel 5를 `ADC_GAIN_1_4`로 override하도록 수정했다.
같은 sequence 14에서 SPI 1 MHz/div128도 실제 SPI00 prescaler 범위 밖이라 `-EINVAL`로
실패했다. shipped sample/HIL을 4 MHz/div32로 수정했다.

수정 후 최초 통합 peripheral HIL은 DAPLink sequence 17로 166,400-byte image를 기록하고
COM10에서 SPI 4 MHz driver 성공(`rx=0x00`), A0 raw=3176, PWM duty 0/128/255 실행을 확인했다.
sequence 37에서는 166,912-byte image를 기록해 SPI 4 MHz driver 성공(`rx=0x00`), A0 raw=3140,
PWM duty 0/128/255 실행을 다시 확인했다. P2.2와 P2.4를 직접 연결한 최종 sequence 2에서는
167,424-byte image로 SPI00 4 MHz의 40-byte `MUL37_ADD5A` 패턴이 전부 일치했고 A0 raw=3176,
PWM duty 0/128/255도 다시 통과했다. 강화된 peripheral parser unittest는 7/7 PASS다. 이 결과는
ADC 전압 정확도와 PWM 실제 파형을 증명하지 않는다.

---

## 9. M7 판정 조건

M7은 다음 조건을 기준으로 판정했다.

1. production source와 public header가 target에서 빌드된다.
2. emulator ztest가 Wire/SPI/ADC/PWM의 positive·negative 의미를 검증한다.
3. Core overlay와 Kconfig가 Arduino builder 및 기존 west 회귀에서 일관되게 동작한다.
4. BQ25186 0x6A/0x0C 읽기 전용 repeated-start HIL을 안전하게 실행한다.
5. ADC/PWM의 실제 driver 경로와 미검증 범위를 기록한다.
6. API 지원표, Variant, 주변장치와 시험 문서를 실제 결과와 동기화한다.

production target build와 NU54DK Twister target 11/11, Arduino CLI M7 4/4, 전체 Builder 회귀 8/8,
host protocol unittest 12/12, BQ25186 I2C와 ADC/PWM 실제 driver 경로를 통과했다. 마지막으로
SPI00 4 MHz의 40-byte 물리 loopback data까지 일치했으므로 M7의 최종 상태는 **완료**다.

---

## 10. 기록 갱신 규칙

검증 기록을 갱신할 때 다음 정보를 보존한다.

- 명령과 working directory
- Core·board package revision과 dirty 여부
- 실행 시각과 연결 보드 UID
- build exit code, case 수와 memory report
- DAPLink flash sequence와 UART port
- 각 미검증 항목의 원인과 재시험 조건

시험을 실행하지 않았거나 log를 잃은 항목을 PASS로 바꾸지 않는다. 후속 M8 상태는 별도의
M8 기준선에서 관리하며 M7 당시 결과와 섞지 않는다.
