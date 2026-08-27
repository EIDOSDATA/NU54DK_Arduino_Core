# NU54DK Arduino 주변장치 API 설계

| 항목 | 내용 |
| --- | --- |
| 문서 상태 | M6 완료; M7 Wire·SPI·ADC·PWM 조건부 완료 |
| 작성자 | Quantum / NUCODE |
| 기준 SDK | nRF Connect SDK v3.4.0 |
| 기준 RTOS | Zephyr v4.4.0 |
| 기준 타깃 | `nrf54l15dk/nrf54l15/cpuapp/nu54dk` |
| 보드 정의 원본 | `board_package/NU54DK_Zephyr_DTS` |
| v1 Serial 결정 | `zephyr,console` UART의 non-owning wrapper |

---

## 1. 목적

이 문서는 NU54DK Arduino Core에서 UART, I2C, SPI, ADC, PWM 및 무선 subsystem을 Arduino API와 Zephyr driver 사이에 연결하는 방법을 정의한다. 주요 목표는 다음과 같다.

- Arduino library가 기대하는 객체와 호출 순서를 제공한다.
- 물리 instance와 pinctrl을 Core에 하드코딩하지 않는다.
- Zephyr device lifecycle과 Arduino `begin()`/`end()` 의미를 구분한다.
- console, logging, shell 및 `Serial`의 UART 소유권 충돌을 명확히 한다.
- thread와 ISR에서 허용되는 호출을 구분한다.
- Devicetree에서 비활성인 장치를 API 호출만으로 몰래 활성화하지 않는다.

M6에서 `Serial`은 구현·target ztest·실제 COM10 HIL까지 완료했다. M7의 `Wire`, `SPI`, ADC와
PWM production source와 builder profile은 NU54DK Twister target 11/11, Arduino CLI 4/4 및 승인된
NU54DK driver HIL을 통과했다. BQ25186 I2C 응답도 확인했으며 물리 SPI data 경로만
미검증 경계로 기록하고 M7을 `조건부 완료`로 판정한다.

---

## 2. 단일 원본 원칙

### 2.1 물리 장치와 route

다음 정보는 `board_package/NU54DK_Zephyr_DTS`가 단독으로 소유한다.

- UART, I2C, SPI, ADC 및 PWM instance
- GPIO와 pinctrl route
- `current-speed`, `clock-frequency` 및 node status
- `chosen`과 `aliases`
- onboard device address와 interrupt GPIO
- 핀 충돌과 솔더브리지 조건

Core 안에 `uart20`, `i2c22`, `spi00`, `P1.4` 같은 이름이나 숫자를 별도의 board truth로 복제하지 않는다. 이 문서에서 현재 구성을 설명하기 위해 이름을 사용할 수 있지만 구현은 `DT_CHOSEN`, alias, node label 또는 Variant가 제공하는 Devicetree reference를 소비한다.

### 2.2 Arduino 논리 객체

Variant는 다음 논리 연결만 소유한다.

- `Serial`이 어떤 논리 UART 역할을 가리키는지
- `Serial1`의 존재 여부
- `Wire`, `SPI`의 기본 논리 bus
- analog와 PWM을 사용할 수 있는 논리 pin 순서

실제 device와 pin은 Devicetree가 결정한다.

### 2.3 Sketch별 변경

사용자가 baud, bus speed, peripheral node 또는 pin route를 바꾸려면 다음 구성 계층을 사용한다.

- `prj.conf`
- application overlay
- 필요 시 Zephyr snippet

Core source를 수정하거나 prebuilt profile을 새로 만들 필요가 없어야 한다. 이것이 Full Zephyr 정적 빌드의 핵심 자유도다.

---

## 3. 현재 NU54DK 보드 상태

현재 보드 패키지를 기준으로 한 설계 입력은 다음과 같다.

| 기능 | 현재 Devicetree 상태 | 설계 영향 |
| --- | --- | --- |
| 기본 UART | `zephyr,console`로 선택, 115200 bps | `Serial` 기본 후보 |
| 두 번째 UART | pinctrl과 속도 정의, 기본 비활성 | `Serial1`은 overlay 없이는 제공하지 않음 |
| I2C22 | 기본 활성, SDA P1.2/SCL P1.3, 100 kHz | Core chosen `nucode,arduino-wire`; 100/400 kHz controller |
| BQ25186 | I2C22의 0x6A child node 비활성 | Core가 Zephyr PMIC driver를 자동 활성화하지 않으며 M7 Wire HIL은 `MASK_ID`만 읽기 전용 접근 |
| SPI00 | P2.1/P2.2/P2.4 pinctrl만 정의, controller 기본 비활성 | Core overlay가 활성화; uart00과 동시 활성 금지 |
| PWM | pwm20 channel 0의 `pwm_led1` 역할 활성, P1.10 | Core chosen `nucode,arduino-pwm`; 20 ms·8-bit 전용 역할 |
| ADC | ADC와 channel 5 활성, P1.12 | Core chosen `nucode,arduino-adc`; A0 고정 12-bit raw |
| VBAT divider | consumer node 비활성 | 솔더브리지와 overlay 필요 |
| Radio/802.15.4 | 보드에서 활성 | Zephyr/NCS subsystem으로 사용 |
| Native USB | nRF54L15에 없음 | target USB CDC/HID/MSC 제공 불가 |

상세 물리 정보는 [NU54DK 핀 구성](../../board_package/NU54DK_Zephyr_DTS/00_Docs/03_PINOUT.md)을 따른다.

---

## 4. 공통 구성요소와 책임

### 4.1 Arduino wrapper 객체

`Serial`, `Wire`, `SPI`는 전역 C++ 객체를 제공하되 constructor에서 hardware를 활성화하지 않는다.

~~~text
정적 C++ constructor
      ↓
device reference와 초기 상태만 보관
      ↓
setup() 이후 begin()
      ↓
device readiness와 ownership 확인
      ↓
실제 API 사용
~~~

### 4.2 Zephyr device

Zephyr가 다음을 소유한다.

- driver instance 생성
- init priority에 따른 hardware 초기화
- pinctrl 적용
- interrupt 연결
- power management integration

Arduino `begin()`은 Zephyr device를 새로 생성하지 않는다. 준비된 device에 Arduino lifecycle을 연결하고 필요한 runtime 설정과 buffer를 시작한다.

### 4.3 Core 내부 adapter

Peripheral별 adapter는 다음 공통 규칙을 제공한다.

- logical object에서 Devicetree device 조회
- `device_is_ready()` 검사
- thread context와 ownership 검사
- Zephyr 오류에서 Arduino 반환값으로 변환
- 상세 오류 코드 보존
- 정적 buffer와 synchronization 관리

### 4.4 Build 구성

각 API는 필요한 Zephyr subsystem을 Kconfig dependency로 요구한다. API가 켜졌는데 필요한 node가 없으면 다음 중 하나로 처리한다.

- 필수 기본 객체라면 빌드 실패
- 선택 객체라면 공개 상수와 객체를 만들지 않음
- overlay로 활성화할 수 있다는 명확한 진단 제공

비활성 device를 source에서 register 제어로 우회하지 않는다.

---

## 5. Serial과 UART 설계

### 5.1 v1 소유권 결정

v1의 `Serial`은 `DT_CHOSEN(zephyr_console)`이 가리키는 UART에 연결하는 **non-owning wrapper**로 정의한다.

소유권은 다음과 같다.

| 자원 | 소유자 |
| --- | --- |
| UART device 생성과 초기화 | Zephyr |
| pinctrl과 기본 baud | 보드 Devicetree |
| device lifetime과 suspend 정책 | Zephyr driver/PM |
| Arduino RX/TX buffer | Arduino `Serial` wrapper |
| Arduino begin/end 상태 | Arduino `Serial` wrapper |
| console 출력 | Zephyr console |

이 결정의 결과는 다음과 같다.

- `Serial.begin()`은 console UART를 reset하거나 pinctrl을 다시 쓰지 않는다.
- `Serial.end()`은 Arduino buffer와 callback만 정리하고 UART device 자체를 끄지 않는다.
- `Serial`을 종료해도 Zephyr console 또는 fault output은 계속 사용할 수 있다.
- console과 Arduino TX가 같은 wire를 사용하므로 개발 log와 Sketch 출력이 섞일 수 있다.

### 5.2 Baud 정책

현재 보드 Devicetree의 기본 console baud는 115200 bps다.

v1 정책은 다음과 같다.

1. `Serial.begin(115200)`은 이미 구성된 UART에 attach한다.
2. 다른 baud를 요청하면 console이 활성인 상태에서 UART를 묵시적으로 재구성하지 않는다.
3. M6 기본 객체는 115200 8N1만 지원한다. overlay에서 다른 속도를 선택한 build에서는
   `Serial.begin(115200)`이 실제 설정 불일치로 실패한다.
4. 요청 baud/config와 실제 설정이 다르면 `Serial`을 ready로 표시하지 않고 진단을 남긴다.

Arduino `begin()`은 `void`라 오류를 직접 반환하지 않는다. `operator bool()`과 Core 진단 상태를 통해 준비 여부를 확인하는 방안을 사용한다.

향후 console이 아닌 전용 `Serial1`은 exclusive ownership을 얻은 경우 `uart_configure()`로 baud를 바꿀 수 있다.

### 5.3 Console, logging 및 shell

같은 UART의 역할을 다음과 같이 구분한다.

| 소비자 | TX | RX | v1 정책 |
| --- | --- | --- | --- |
| Zephyr console | 사용 | 일반적으로 직접 소비하지 않음 | 유지 |
| Zephyr logging | backend 설정 시 사용 | 사용 안 함 | 개발 build에서 허용 |
| Zephyr shell | 사용 | 소비 | 기본 Arduino 구성에서는 비활성 |
| Arduino `Serial` | 사용 | 소비 | 활성 |

RX는 두 소비자가 동시에 가져가면 byte ownership이 불명확해진다. 따라서 `Serial`과 같은 UART에서 Zephyr shell을 동시에 활성화하는 구성은 v1 지원 대상에서 제외한다. 필요하면 별도 UART나 RTT backend를 사용한다.

TX는 물리적으로 공유할 수 있지만 message가 byte 단위로 섞이지 않도록 Arduino 내부 TX lock을 사용한다. 이 lock은 Zephyr console 전체와 공유되지 않으므로 log line과 Sketch 출력의 완전한 원자성을 보장하지 않는다. release profile에서는 불필요한 logging을 끄는 것을 기본으로 한다.

### 5.4 M6 구현

- TX는 Core mutex로 직렬화한 `uart_poll_out()`을 사용한다.
- RX는 interrupt-driven 고정 `k_msgq`를 사용하며 기본 크기는 128 byte다.
- RX queue가 가득 차면 기존 byte를 보존하고 새 byte를 버리는 drop-newest 정책과 drop
  counter를 사용한다.
- `begin()`, `end()`, `available()`, `peek()`, `read()`, `write()`,
  `availableForWrite()`, `flush()`와 `operator bool()`을 구현했다.
- `begin()`은 `uart_config_get()`으로 115200 8N1 실제 설정을 확인할 뿐
  `uart_configure()`를 호출하지 않는다.
- `flush()`는 polling TX 호출이 반환한 상태를 보장하며 RX discard가 아니다.
- public `Serial` API는 ISR에서 거부한다.

TX ring buffer와 비동기 TX는 M6 계약에 포함하지 않는다. polling TX가 block될 수 있다는
의미를 문서화하고 이를 비동기 구현으로 표시하지 않는다.

### 5.5 데이터 흐름

~~~text
Sketch Serial.write(data)
          ↓
thread/ready/baud 검사
          ↓
Arduino TX buffer 또는 polling path
          ↓
Zephyr UART API
          ↓
console UART
          ↓
온보드 UART bridge
          ↓
CMSIS-DAP 인터페이스 MCU의 USB VCOM
~~~

CMSIS-DAP 인터페이스 MCU가 USB를 처리한다. nRF54L15 target이 USB CDC device로 동작하는 것이 아니다.

### 5.6 `Serial1`

현재 두 번째 UART는 기본 비활성이다. 따라서 v1 기본 Variant에서 동작하는 `Serial1`을 있다고 가정하지 않는다.

`Serial1`을 공개하려면 다음 조건이 필요하다.

- application overlay에서 UART node `okay`
- pinctrl 활성
- DAP 연결 솔더브리지 또는 외부 connector 경로 확인
- Variant의 logical UART mapping
- console과 독립된 ownership test

---

## 6. `Wire`와 I2C 설계

### 6.1 기본 역할

`TwoWire`는 `arduino::HardwareI2C`의 호환 이름이며 전역 `TwoWire &Wire`가
`nucode,arduino-wire` chosen의 I2C22를 사용한다. 현재 NU54DK 보드 정의에는 P1.2 SDA,
P1.3 SCL의 100 kHz I2C22가 활성화되어 있다.

P1.2/P1.3은 nRF54L15의 NFC 전용 패드이므로 controller 활성화만으로는 충분하지 않다.
Arduino Builder 기본 overlay와 Wire 실기 sample은 `&uicr { nfct-pins-as-gpios; };`를 설정해
부팅 초기에 NFCT PADCONFIG를 GPIO/TWIM 모드로 전환한다. 이 Core overlay 보완은 읽기 전용
보드 package를 수정하지 않는다.

v1 범위:

- controller/master mode
- `begin()`
- `beginTransmission()`
- `write()`
- `endTransmission()`
- `requestFrom()`
- `available()`, `read()`, `peek()`
- `setClock()`의 제한된 지원

Target/slave mode와 callback API는 별도 단계로 둔다.

### 6.2 Buffer

- 고정 크기 TX/RX buffer를 사용한다.
- heap을 기본으로 사용하지 않는다.
- 기본 32 byte이며 `CONFIG_NUCODE_ARDUINO_WIRE_BUFFER_SIZE`로 16..512 byte 범위에서 조정한다.
- overflow 시 추가 byte를 기록하지 않고 오류 상태를 설정한다.
- `endTransmission()` 전에 overflow가 발생하면 bus transaction을 보내지 않는 정책을 우선한다.

### 6.3 Clock ownership

Devicetree의 `clock-frequency`가 기본 원본이다. `Wire.setClock()`은 100 kHz와 400 kHz만
허용하고 Zephyr `i2c_configure()`로 적용한다. 다른 값은 조용히 근사하지 않고 진단한다.
같은 bus의 모든 client가 controller clock 변경의 영향을 받는다는 제약을 Sketch가 소유한다.

현재 BQ25186 child node는 비활성이므로 Core가 자동으로 enable하지 않는다. 이를 활성화한
application은 Zephyr BQ25186 driver 경로와 `Wire` 경로를 application 소유의 공통 mutex로
감싸야 한다. Core의 private `wire_mutex`는 다른 Zephyr I2C client를 직렬화하지 않는다.

### 6.4 호출 흐름

~~~text
beginTransmission(address)
      ↓ address와 state 저장
write(bytes)
      ↓ 고정 TX buffer
endTransmission(true)
      ↓ Zephyr i2c_write + STOP
endTransmission(false)
      ↓ address와 TX buffer만 보류, bus 전송 없음
requestFrom(same_address, length, true)
      ↓ i2c_write_read()의 WRITE + RESTART + READ + STOP
~~~

Zephyr 4.4 nRF TWIM의 단독 no-STOP write 제약 때문에 repeated-start는 deferred 방식으로
구현한다. 보류 중 새 transmission, 다른 address 또는 다른 thread가 개입하면 전송하지 않고
진단한다. 마지막 read 뒤 STOP을 생략하는 `requestFrom(..., false)`는 지원하지 않으며 0을
반환한다. TX byte 없이 `endTransmission(true)`를 호출하면 zero-byte write와 STOP을 실제
driver에 전달해 address-only probe를 수행한다. 이 범용 Core 기능과 달리 M7 PMIC HIL에서는
임의 주소 probe·scan을 허용하지 않는다. logic analyzer는 필수 완료 장비가 아니다.

### 6.5 M7 BQ25186 HIL 안전 경계

센서를 분리한 상태에서 온보드 BQ25186을 고정 target으로 사용한다. HIL은 address `0x6A`의
`MASK_ID(0x0C)` pointer를 no-STOP으로 보낸 뒤 repeated-start로 1 byte를 읽는다. 하위 nibble
Device ID가 `0x1`인지 확인하며 상위 interrupt-mask bit는 판정에서 제외한다. register data
write, address scan과 fallback을 실행하지 않는다.

HIL command line과 UART payload는 address·register·expected value·scan을 외부 입력으로
노출하지 않는다. 첫 I2C transaction이 BQ25186의 기본 160초 watchdog을 시작할 수 있으므로
시험은 ID를 한 번 읽고 종료한다. 기본 watchdog 만료 동작은 R/W register 기본값 복원이며,
HIL은 PMIC 설정 register를 쓰지 않는다.

### 6.6 오류 변환

Arduino `endTransmission()`의 호환 코드와 Zephyr errno를 연결하되 상세 errno를 내부 상태에 보존한다.

| Arduino 결과 | 의미 |
| ---: | --- |
| 0 | 성공 |
| 1 | TX buffer overflow |
| 2 | address NACK용 호환 코드; 현재 adapter는 반환하지 않음 |
| 3 | data NACK용 호환 코드; 현재 adapter는 반환하지 않음 |
| 4 | 기타 bus/driver 오류 |
| 5 | timeout |

현재 adapter는 TX buffer overflow를 1, `-ETIMEDOUT`을 5로 반환하며 그 밖의 negative driver
errno는 공개 status 4로 변환한다. 따라서 NACK도 address/data를 나눠 2 또는 3으로 반환하지 않는다. 원래 errno는
Core 비공개 진단에 보존한다. target ztest는 overflow와 `-EIO`→4·원본 errno 보존을 검증했으며
timeout 5와 실제 NACK 세분화는 검증하지 않았다.

---

## 7. `SPI` 설계

### 7.1 현재 상태

`SPIClass`와 `SPISettings`는 ArduinoCore-API 형식이며 전역 `SPIClass &SPI`가
`nucode,arduino-spi` chosen을 사용한다. NU54DK 보드 package는 SPI00의 P2.1 SCK, P2.2 MOSI,
P2.4 MISO pinctrl을 제공하지만 controller는 기본 비활성이다. Arduino builder의 Core overlay가
SPI00을 활성화한다. SPI00과 uart00은 같은 하드웨어 instance를 공유하므로 동시에 활성화할 수
없으며 충돌 profile은 configure/build 단계에서 실패해야 한다. NU54DK production Core는
chosen이 SPI00이 아닌 구성도 compile-time에 거부한다. fake driver를 쓰는 M7 target test만
명시적인 test 전용 compile definition으로 이 instance 검사를 우회한다.

### 7.2 API 범위

v1 목표:

- `SPI.begin()`과 `SPI.end()`
- `beginTransaction(SPISettings)`
- `transfer()`, `transfer16()`, buffer transfer
- `endTransaction()`
- mode 0~3
- MSB/LSB order의 driver 지원 범위
- transaction별 nrfx runtime prescaler 조건을 통과하는 frequency; shipped sample/HIL 기본은 4 MHz
- Core가 관리하지 않는 Sketch 소유 chip-select

SPI00은 128 MHz core clock에 4..126 범위의 짝수 prescaler를 사용한다. 1 MHz는 divider 128이
필요해 표현할 수 없고, 4 MHz는 divider 32로 정확히 표현할 수 있다. sequence 14에서는 1 MHz가
첫 transfer에서 driver `-EINVAL`로 드러났다. 최종 Core는 0 Hz·32 MHz 초과와 함께 nrfx
runtime predicate `(128 MHz % frequency) < prescaler` 및 prescaler 짝수·범위 조건을
`beginTransaction()`에서 동일하게 선검증한다. 이 runtime 조건은 나머지가 0인 값만 허용하는
exact-division 검사가 아니며 near-divisor도 허용할 수 있다. 실제 SCK는 128 MHz/prescaler로
양자화된다. Core는 별도의 가까운 frequency 탐색이나 임의 반올림을 하지 않으며 실제 driver
호출에서 발생한 errno는 진단에 보존한다. shipped sample/HIL 기본값은 4 MHz로 고쳤고 재시험
결과는 M7 기준선에 보존한다.

### 7.3 Transaction ownership

`beginTransaction()`은 다음을 수행한다.

1. thread 문맥을 확인한다.
2. 짧게 Core 내부 `spi_mutex`를 잡아 transaction owner와 상태를 갱신한다.
3. `SPISettings`를 Zephyr `spi_config`로 변환한다.
4. 지원하지 않는 mode·bit order와 nrfx runtime prescaler predicate가 거부하는 frequency를
   `invalid_frequency`로 거부한 뒤 mutex를 해제한다.

Core는 자동 CS, 기본 SS pin 또는 Zephyr child device를 만들지 않는다. Sketch가 사용할
digital GPIO를 직접 선택하고 `beginTransaction()` 전후가 아니라 실제 transfer 구간 앞뒤에서
CS를 제어한다. 각 `transfer()`도 Core 상태 검사와 해당 driver 호출 동안만 내부 mutex를 잡는다.
`SPI_LOCK_ON`이나 `spi_release()`를 사용하지 않으므로 `beginTransaction()`부터
`endTransaction()`까지 Zephyr bus 전체를 독점하지 않는다. 다른 Zephyr SPI client의 호출은
Arduino transaction 사이에 개입할 수 있으며, 해당 공존이 필요한 application이 별도 상위
직렬화 정책을 제공해야 한다. `endTransaction()`은 Core owner 상태만 정리한다.

### 7.4 호출 흐름

~~~text
SPI.beginTransaction(settings)
        ↓ Core owner/state 설정 후 mutex 해제
Sketch digitalWrite(CS, LOW)
        ↓
SPI.transfer(buffer)
        ↓ Core mutex + driver 호출 + mutex 해제
Zephyr spi_transceive()
        ↓
Sketch CS 해제 + endTransaction()
        ↓ Core owner/state 정리
~~~

v1 SPI API는 thread 문맥 전용이다. ISR transfer를 지원한다고 표시하지 않는다.

---

## 8. ADC와 `analogRead()` 설계

### 8.1 Mapping

`PIN_A0`/`A0`는 논리 index 2이며 `NUM_DIGITAL_PINS=2` 범위 밖의 analog 전용 역할이다.
Core overlay의 `nucode,arduino-adc` chosen node가 `io-channels = <&adc 5>`를 제공한다. 최종
Devicetree 기준 물리 입력은 P1.12/SAADC channel 5다.

### 8.2 API 범위

M7 계약은 다음과 같다.

- `analogRead(A0)`의 고정 12-bit raw 0..4095
- 잘못된 pin, ISR, 준비되지 않은 device, DTS 불일치와 driver 오류는 `-1`
- Core overlay가 정한 channel 5, `ADC_GAIN_1_4`, `ADC_REF_INTERNAL` 계약 검사
- `analogReference(AR_DEFAULT)`만 허용; `AR_INTERNAL`은 같은 값의 설명용 별칭
- `analogReadResolution()`은 vendored ArduinoCore-API 1.5.2에 선언이 없어 미구현

### 8.3 호출 흐름

~~~text
analogRead(logical_pin)
       ↓ ADC capability와 ownership 검사
       ↓ Devicetree channel spec
       ↓ ADC device readiness
       ↓ sequence 구성
       ↓ adc_read()
       ↓ 12-bit raw 0..4095 또는 오류 -1
~~~

ADC read는 thread 문맥 전용이며 synchronous conversion 동안 block될 수 있다.

보드 package의 channel 5는 `ADC_GAIN_1_6`을 선언하지만 nRF54L15에서 이 gain은
`-EINVAL`이다. 읽기 전용 서브모듈은 수정하지 않고 Core builder·sample·example overlay가
channel 5를 12-bit, internal reference, `ADC_GAIN_1_4`로 override한다. sequence 14에서
발견한 1/6 실패와 수정 후 재시험 결과는 M7 검증 기준선에 함께 보존한다.

internal 0.6 V reference와 gain 1/4의 nominal full-scale 입력은 약 2.4 V이므로 그 이상은
12-bit raw에서 saturation될 수 있다. 이는 절대최대 정격이나 안전 입력 전압 안내가 아니다.
정확도와 허용 전압은 SoC/보드 전기 사양을 따르며 `analogRead()` 계약은 raw 0..4095뿐이다.

### 8.4 VBAT

보드의 VBAT voltage-divider consumer는 기본 비활성이고 솔더브리지 상태가 필요하다. `analogRead()`이 이를 자동 활성화하거나 분압 비율을 적용하지 않는다.

배터리 전압 API가 필요하면 다음을 별도 library로 제공한다.

- voltage-divider node 활성화 overlay
- 실제 솔더브리지 조건
- ADC raw-to-mV 변환
- resistor tolerance와 calibration

---

## 9. PWM과 `analogWrite()` 설계

### 9.1 Mapping과 충돌

`PIN_PWM0`과 `PIN_PWM_LED`는 같은 논리 index 3이며 digital pin이 아니다. Core overlay의
`nucode,arduino-pwm` chosen은 보드 `pwm_led1` node를 가리키고, 이 node는 `pwm-led0` alias와
같은 P1.10/pwm20 channel 0 역할이다. `LED_BUILTIN`은 별도 P2.9 digital GPIO이며 PWM 핀이 아니다.

### 9.2 API 범위

M7 계약은 다음과 같다.

- `analogWrite(PIN_PWM0, value)` 또는 같은 역할 별칭 `PIN_PWM_LED`
- 고정 20 ms period와 고정 8-bit 0..255 duty
- 0은 pulse 0, 255는 full period, 중간값은 64-bit 연산으로 반올림
- 범위 밖의 값과 다른 pin은 clamp하지 않고 거부
- `analogWriteResolution()`과 PWM frequency setter는 미구현

### 9.3 Ownership 전환

M7은 P1.10을 digital descriptor로 추가하지 않으므로 GPIO↔PWM 자동 ownership 전환이 없다.
UART, SPI, I2C, debug 또는 다른 Zephyr device가 소유한 pin을 `analogWrite()`가 자동으로
빼앗지 않으며 ISR 호출은 거부한다. 다른 P1.10 소비자가 필요하면 Sketch overlay가 정적으로
구성을 바꾸고 충돌 책임을 진다.

### 9.4 값 변환

8-bit 최대값 255를 20 ms period에 비례해 pulse width로 변환한다. overflow를 피하기 위해
64-bit 중간 연산을 사용한다. DTS period가 정확히 20 ms가 아니면 조용히 다른 파형을
출력하지 않고 오류 상태를 남긴다.

---

## 10. Radio, Bluetooth 및 NCS 기능

NU54DK 보드 정의에는 radio와 IEEE 802.15.4 자원이 활성화되어 있다. 그러나 v1 기본 Arduino Core가 임의의 추상 `Radio` 객체를 만드는 것은 범위에 넣지 않는다.

초기 정책:

- Sketch는 Zephyr/NCS Bluetooth와 radio API를 직접 사용할 수 있다.
- 필요한 Kconfig와 overlay는 Sketch build에 포함한다.
- Arduino 호환 BLE library는 별도 library 계층으로 설계한다.
- Core runtime은 radio thread와 buffer를 항상 활성화하지 않는다.

이 정책은 사용하지 않는 subsystem을 빌드에서 제거하는 Zephyr의 장점을 보존한다.

---

## 11. USB 정책

nRF54L15 target MCU에는 native USB peripheral이 없다. 따라서 다음 Arduino target API는 NU54DK v1 Core에서 제공하지 않는다.

- `SerialUSB`
- target USB CDC ACM
- USB HID keyboard/mouse
- USB MSC
- target USB DFU

NU54DK의 USB connector는 온보드 CMSIS-DAP 인터페이스 MCU에 연결된다. target과의 관계는 다음과 같다.

~~~text
PC USB
  ↓
CMSIS-DAP interface MCU
  ├─ SWD → nRF54L15 flash/debug
  └─ VCOM ↔ nRF54L15 UART
~~~

따라서 PC에서 보이는 serial port는 UART bridge다. `Serial`은 target UART API이며 USB device API가 아니다.

---

## 12. Thread와 ISR 문맥

| API/동작 | Thread | ISR | Blocking 가능 | 비고 |
| --- | --- | --- | --- | --- |
| `Serial.begin/end` | 허용 | 금지 | 예 | lifecycle 변경 |
| `Serial.write` | 허용 | 금지 | polling TX 동안 | Core mutex로 호출 직렬화; ISR은 0과 진단 반환 |
| UART RX driver callback | 해당 없음 | 실행 | 금지 | 고정 RX queue와 drop counter만 조작 |
| `Wire` transaction | 허용 | 금지 | 예 | Core state mutex와 transfer; 다른 Zephyr client는 별도 직렬화 |
| `SPI` transaction | 허용 | 금지 | 예 | Core owner/state는 보호하지만 Zephyr bus 전체 lock은 아님 |
| `analogRead` | 허용 | 금지 | 예 | synchronous conversion |
| `analogWrite` | 허용 | 금지 | driver 호출 동안 | PIN_PWM0 전용; GPIO ownership 전환 없음 |
| peripheral event callback | API별 | 주로 ISR/workqueue | API별 | 문맥을 문서화 |

ISR callback은 다음 원칙을 따른다.

- heap allocation 금지
- mutex와 sleep 금지
- UART RX queue와 atomic flag 등 제한된 상태만 갱신
- 사용자 callback이 필요한 API는 ISR인지 workqueue인지 명시
- 긴 처리는 `k_work` 또는 message queue로 thread에 전달

---

## 13. 오류 정책

### 13.1 공통 상태

각 peripheral wrapper는 최소한 다음 상태를 구분한다.

~~~text
UNINITIALIZED
READY
BUSY
ERROR
ENDED
~~~

`begin()`이 실패했는데 READY로 전환해서는 안 된다.

### 13.2 오류 전달

| Arduino API 형태 | 정책 |
| --- | --- |
| `bool` 또는 byte 반환 | 호환 가능한 실패 값 반환 |
| byte count 반환 | 성공한 byte 수만 반환 |
| `void begin()` | ready 상태와 진단 코드로 확인 |
| stream read | data 없음과 오류를 구분할 내부 상태 보존 |

Zephyr의 원래 negative errno는 디버깅을 위해 보존한다. Arduino 호환 값으로 변환한 뒤 원인을 잃어버리지 않는다.

### 13.3 Timeout

- adapter가 제어할 수 있는 대기에는 무한 대기를 기본으로 두지 않는다.
- timeout Kconfig 또는 객체 API는 실제 구현과 시험이 추가된 뒤에만 지원으로 표시한다.
- 오류나 timeout 뒤에는 해당 adapter가 실제로 소유한 Core mutex와 transaction state만
  정리한다. M7 SPI는 bus-wide lock과 CS를 소유하지 않으므로 Sketch 소유 CS를 변경하지 않는다.
- UART buffer full, I2C bus hang 및 SPI driver stall의 추가 HIL은 후속 검증 범위다.

### 13.4 진단과 release

- 개발 build는 peripheral 이름, logical object, operation 및 errno를 log한다.
- ISR은 문자열 log를 직접 수행하지 않는다.
- release build에서도 상태와 범위 검사는 유지한다.
- 민감한 radio/network payload를 진단 log에 출력하지 않는다.

---

## 14. 설정 항목

Serial 항목은 M6 구현값이다. M7 항목은 module 수준 기본값과 Arduino builder 기본 profile을
구분한다.

| 설정 | 기본값 | 설명 |
| --- | ---: | --- |
| `CONFIG_NUCODE_ARDUINO_SERIAL` | `y` | 기본 `Serial` wrapper |
| `CONFIG_NUCODE_ARDUINO_SERIAL_RX_BUFFER_SIZE` | `128` | IRQ RX 고정 queue, overflow는 drop-newest |
| Serial TX buffer | 없음 | polling TX와 Core mutex 사용 |
| `CONFIG_NUCODE_ARDUINO_WIRE` | module `n`, builder `y` | I2C22 controller wrapper |
| `CONFIG_NUCODE_ARDUINO_WIRE_BUFFER_SIZE` | `32` | TX/RX 각각의 고정 buffer, 16..512 |
| `CONFIG_NUCODE_ARDUINO_SPI` | module `n`, builder `y` | Core overlay의 SPI00, CS 제외 |
| `CONFIG_NUCODE_ARDUINO_ADC` | module `n`, builder `y` | A0 고정 12-bit raw |
| `CONFIG_NUCODE_ARDUINO_PWM` | module `n`, builder `y` | P1.10 고정 20 ms·8-bit |

Zephyr dependency 예시는 다음과 같다.

- `CONFIG_SERIAL`
- `CONFIG_UART_INTERRUPT_DRIVEN`
- `CONFIG_I2C`
- `CONFIG_SPI`
- `CONFIG_ADC`
- `CONFIG_PWM`

필요하지 않은 peripheral은 build에서 제거할 수 있어야 한다.

---

## 15. 완료 기준

### 15.1 Serial

- [x] `Serial`이 `DT_CHOSEN(zephyr_console)`에서 device를 얻는다.
- [x] Core에 UART instance와 pin 번호를 별도 board truth로 하드코딩하지 않는다.
- [x] `Serial.begin(115200, SERIAL_8N1)`이 실제 설정을 읽기만 하고 console 설정을 바꾸지 않는다.
- [x] 다른 baud/config 요청이 묵시적으로 console을 재구성하지 않고 실패한다.
- [x] `Serial.end()`이 Arduino RX callback/queue만 정리하고 Zephyr UART lifetime을 유지한다.
- [x] 128-byte RX overflow가 drop-newest와 counter로 처리된다.
- [x] polling TX, `flush()`와 ISR 금지 의미가 문서화되어 있다.
- [x] shell·console input·UART mcumgr·async UART log/tracing 동시 사용 제한이 build에서 진단된다.
- [x] COM10에서 boot READY와 실행마다 고유한 echo payload가 실제로 왕복한다.

### 15.2 Wire

- [x] deferred write와 같은 주소 read가 repeated-start로 결합된다.
- [x] `requestFrom(..., false)`가 전송 없이 0과 미지원 진단을 반환한다.
- [x] zero-byte `endTransmission(true)` address probe와 driver 오류 변환을 검증한다.
- [x] TX overflow=1과 `-EIO` 등 generic driver 오류=4·원본 errno 보존을 검증한다.
- [ ] shared Zephyr client가 있을 때 bus lock과 clock 정책이 지켜진다.
- [x] 최종 generated Devicetree에서 BQ25186이 `status = "disabled"`로 유지된다.
- [x] Wire가 활성인데 `nucode,arduino-wire` chosen이 없으면 configure/build에서 실패한다.
- [x] HIL protocol이 BQ25186 `0x6A/0x0C` 읽기만 허용하고 Device ID 0x1을 실기 확인한다.
- [x] Core overlay가 P1.2/P1.3 NFC 패드를 GPIO/TWIM으로 전환하며 외부 pull-up만으로 통과한다.

### 15.3 SPI

- [x] overlay 없이 SPI가 준비된 것처럼 동작하지 않는다.
- [x] mode 0~3, frequency 및 buffer transfer를 target ztest로 검증한다.
- [x] 1 MHz/div128 실패를 보존하고 4 MHz/div32 실제 driver 경로를 재검증한다.
- [x] NU54DK production chosen이 SPI00이 아니면 stable diagnostic으로 실패한다.
- [x] SPI00과 uart00 동시 활성 구성이 configure/build 단계에서 실패한다.
- [x] Core가 CS를 만들지 않고 Sketch가 별도 GPIO CS를 소유한다.
- [x] transaction 오류 후 Core owner/state가 복구된다.

### 15.4 ADC/PWM

- [x] A0 및 PWM logical mapping이 Variant 문서와 일치한다.
- [x] ADC channel, gain, reference가 최종 Devicetree와 일치한다.
- [x] ADC 12-bit raw 0..4095와 오류 `-1`을 검증한다.
- [x] PWM 0·중간값·255 변환에 overflow가 없다.
- [x] PWM 전용 역할 이외의 pin이 PWM 역할로 오인되지 않는다.
- [ ] VBAT는 명시적 overlay 없이 배터리 전압 API로 노출되지 않는다.

---

## 16. 테스트 계획

### 16.1 Build test

- peripheral별 Kconfig on/off 조합
- device node가 disabled일 때 명확한 실패 또는 객체 제외
- overlay로 UART speed와 SPI/I2C 활성 상태 변경
- board package commit 변경 회귀

### 16.2 Host test

- Serial 고정 RX queue 경계와 drop-newest overflow
- I2C Arduino status 변환
- SPI settings 변환
- ADC/PWM scaling과 overflow
- lifecycle state machine
- timeout 후 resource cleanup

### 16.3 Zephyr test

- fake UART/I2C/SPI/ADC/PWM driver 오류 주입
- device not-ready
- concurrent thread 접근과 bus mutex
- ISR callback과 thread 전달
- power management suspend/resume 후 상태

### 16.4 NU54DK HIL

| 기능 | 시험 |
| --- | --- |
| Serial | **M6 PASS:** DAPLink sequence 7, COM10 boot READY·고유 echo; target ztest에서 RX/TX·overflow·end·ISR 거부 |
| Console 공유 | Zephyr log와 Sketch 출력의 관측 및 제한 확인 |
| I2C | **PASS:** seq33 100 kHz·seq34/42 400 kHz에서 BQ25186 `0x6A/0x0C=0x41`, Device ID 0x1과 repeated-start 확인 |
| SPI | **부분 통과:** 최종 seq37 4 MHz driver 호출 PASS, rx=0x00; physical data/loopback 미검증 |
| ADC | **PASS:** 최종 seq37 gain 1/4 A0 raw=3140; raw 범위만 검증, 전압 정확도 주장 없음 |
| PWM | **PASS:** 최종 seq37 P1.10 duty 0/128/255 driver 호출; 외부 파형 주장 없음 |
| Conflict | SPI00/uart00, 잘못된 analog pin과 LED_BUILTIN PWM negative test |

---

## 17. 범위 제외

v1 주변장치 API에서 다음은 제외한다.

- target native USB CDC/HID/MSC
- `SerialUSB`
- 같은 UART에서 Zephyr shell과 Arduino RX의 동시 소비
- API 호출만으로 비활성 SPI와 UART를 runtime에 활성화하는 기능
- I2C target/slave mode
- ISR에서 blocking Serial/Wire/SPI 호출
- 모든 sensor를 Core에 내장하는 기능
- BQ25186과 VBAT의 자동 board service
- 임의의 radio 추상 API
- LLEXT Loader용 peripheral export ABI

USB upload나 drag-and-drop firmware 기능이 필요하면 CMSIS-DAP 인터페이스 firmware 또는 별도 bootloader 프로젝트로 다룬다. Arduino Runtime의 target USB API로 가장하지 않는다.

---

## 18. 결정 대기 목록

| 항목 | 현재 상태 | 결정 근거 |
| --- | --- | --- |
| Serial RX queue 기본 크기 | M6 `128` byte | target overflow 시험과 RAM 비용 |
| Serial TX 방식 | M6 polling + mutex | COM10 실제 echo와 단순한 non-owning 소유권 |
| 다른 console baud/config 처리 | M6 거부 | 실제 설정은 읽기만 하고 Zephyr 소유 UART를 재구성하지 않음 |
| `Serial1` 공개 | 대기 | overlay와 physical route |
| I2C buffer 크기 | M7 `32` byte | Kconfig 16..512 범위의 고정 TX/RX buffer |
| I2C target mode | v1 제외 | 실제 사용 사례 |
| 기본 SPI 논리 bus | M7 SPI00 | Core overlay, P2.1/P2.2/P2.4와 uart00 충돌 |
| analog 논리 역할 | M7 A0만 | P1.12/SAADC channel 5, A1 이후는 대기 |
| PWM 기본 주기·해상도 | M7 20 ms·8-bit | 보드 pwm_led1 역할과 고정 API 계약 |
| 물리 SPI HIL | 미검증 | fixture가 없어 data/loopback 일치를 주장하지 않으며 M7 조건부 완료 사유로 유지 |

---

## 19. 핵심 결정 요약

~~~text
Devicetree가 물리 peripheral을 소유한다.
Zephyr가 device 초기화와 lifetime을 소유한다.
Arduino wrapper가 begin/end와 buffer를 소유한다.

Serial = zephyr,console UART의 non-owning wrapper
Wire = I2C22의 deferred repeated-start controller
SPI = Core overlay가 활성화한 CS 없는 SPI00 controller
A0 = P1.12/SAADC channel 5의 12-bit raw 역할
PIN_PWM0 = P1.10/pwm20의 20 ms·8-bit 역할
USB VCOM = CMSIS-DAP interface MCU의 UART bridge
Native USB = nRF54L15에 없음
~~~

이 경계를 유지하면 Arduino의 사용성을 제공하면서도 Zephyr console, driver, pinctrl 및 전력 관리가 Core의 숨은 register 제어로 손상되는 것을 방지할 수 있다.
