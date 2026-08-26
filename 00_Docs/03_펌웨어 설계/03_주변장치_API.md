# NU54DK Arduino 주변장치 API 설계

| 항목 | 내용 |
| --- | --- |
| 문서 상태 | M6 Serial 구현·HIL 완료; M7 Wire·SPI·ADC·PWM 구현 전 |
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

M6에서 `Serial`은 구현·target ztest·실제 COM10 HIL까지 완료했다. `Wire`, `SPI`, ADC와
PWM은 M7 구현 전 설계이며 이미 지원된다는 의미가 아니다.

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
| I2C | 기본 bus 활성, 100 kHz | `Wire` 후보 |
| BQ25186 | I2C child node 비활성 | Core가 자동 활성화하지 않음 |
| SPI | pinctrl만 정의, controller 기본 비활성 | `SPI`는 overlay가 필요 |
| PWM | PWM20 활성, 한 channel이 LED 2 pin과 공유 | GPIO/PWM ownership 필요 |
| ADC | ADC와 channel 5 활성 | 논리 analog mapping 승인 필요 |
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

`Wire`는 Variant가 지정한 기본 I2C bus의 Arduino master wrapper다. 현재 NU54DK 보드 정의에는 100 kHz I2C bus가 활성화되어 있다.

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
- buffer 크기는 Kconfig로 조정 가능하게 한다.
- overflow 시 추가 byte를 기록하지 않고 오류 상태를 설정한다.
- `endTransmission()` 전에 overflow가 발생하면 bus transaction을 보내지 않는 정책을 우선한다.

### 6.3 Clock ownership

Devicetree의 `clock-frequency`가 기본 원본이다. `Wire.setClock()`은 bus를 Arduino Core가 exclusive하게 소유하고 driver가 runtime configure를 지원할 때만 적용한다.

같은 bus에 Zephyr device driver가 붙어 있으면 clock 변경이 다른 client에 영향을 준다. 이런 구성에서는 overlay에서 bus speed를 결정하고 runtime 변경을 거부한다.

현재 BQ25186 child node는 비활성이므로 Core가 자동으로 enable하지 않는다. 이를 활성화한 application에서는 Zephyr BQ25186 driver와 `Wire` raw transaction의 동시 접근을 bus mutex로 보호해야 한다.

### 6.4 호출 흐름

~~~text
beginTransmission(address)
      ↓ address와 state 저장
write(bytes)
      ↓ 고정 TX buffer
endTransmission(stop)
      ↓ ownership + device readiness
      ↓ Zephyr i2c_write/i2c_transfer
      ↓ Arduino status code
~~~

Repeated start는 Zephyr message flag 조합으로 표현하고 transaction emulator와 연결된 known
I2C device의 register read로 검증한다. logic analyzer는 필수 완료 장비가 아니다.

### 6.5 오류 변환

Arduino `endTransmission()`의 호환 코드와 Zephyr errno를 연결하되 상세 errno를 내부 상태에 보존한다.

| Arduino 결과 | 의미 |
| ---: | --- |
| 0 | 성공 |
| 1 | TX buffer overflow |
| 2 | address NACK |
| 3 | data NACK |
| 4 | 기타 bus/driver 오류 |
| 5 | timeout을 구분할 때 사용 여부 결정 |

Zephyr driver가 address NACK과 data NACK을 구분하지 못하면 거짓으로 세분화하지 않고 기타 오류로 처리하며 제한을 문서화한다.

---

## 7. `SPI` 설계

### 7.1 현재 상태

NU54DK 보드 패키지는 SPI00 pinctrl을 정의하지만 controller를 기본 활성화하지 않는다. 따라서 overlay 없이 `SPI`가 준비되었다고 간주하지 않는다.

SPI 사용 application은 최소한 다음을 제공해야 한다.

- SPI controller `status = "okay"`
- pinctrl reference
- 필요하면 CS GPIO 또는 child device
- Variant의 기본 SPI mapping

### 7.2 API 범위

v1 목표:

- `SPI.begin()`과 `SPI.end()`
- `beginTransaction(SPISettings)`
- `transfer()`, `transfer16()`, buffer transfer
- `endTransaction()`
- mode 0~3
- MSB/LSB order의 driver 지원 범위
- transaction별 frequency

### 7.3 Transaction ownership

`beginTransaction()`은 다음을 수행한다.

1. thread 문맥을 확인한다.
2. bus mutex를 획득한다.
3. `SPISettings`를 Zephyr `spi_config`로 변환한다.
4. 지원하지 않는 bit order, word size 또는 frequency를 거부한다.

`endTransaction()`은 CS가 inactive인지 확인한 뒤 mutex를 해제한다.

Arduino 관례상 application이 digital GPIO로 CS를 제어할 수 있다. Zephyr child device의 `cs-gpios`를 사용하는 방식과 혼용할 때 이중 제어가 일어나지 않도록 한 transaction에서 한 소유 모델만 선택한다.

### 7.4 호출 흐름

~~~text
SPI.beginTransaction(settings)
        ↓ bus lock
        ↓ settings 변환
digitalWrite(CS, LOW) 또는 Zephyr CS spec
        ↓
SPI.transfer(buffer)
        ↓
Zephyr spi_transceive()
        ↓
CS 해제 + endTransaction()
        ↓ bus unlock
~~~

v1 SPI API는 thread 문맥 전용이다. ISR transfer를 지원한다고 표시하지 않는다.

---

## 8. ADC와 `analogRead()` 설계

### 8.1 Mapping

`A0...An`의 논리 순서가 확정되기 전에는 물리 AIN 번호를 Core에 하드코딩하지 않는다. Variant descriptor가 Devicetree ADC channel reference를 제공해야 한다.

현재 보드에는 ADC channel 5가 정의되어 있지만 이것만으로 `A0` 번호가 확정된 것은 아니다.

### 8.2 API 범위

v1 목표:

- `analogRead(pin)`
- `analogReadResolution(bits)`
- raw sample 반환
- acquisition time, gain 및 reference는 Devicetree 기본값 사용

`analogReference()`는 nRF ADC와 Zephyr channel configuration의 의미를 검토한 뒤 지원 범위를 정한다. AVR 이름을 받아 실제로 적용하지 않는 no-op 구현은 만들지 않는다.

### 8.3 호출 흐름

~~~text
analogRead(logical_pin)
       ↓ ADC capability와 ownership 검사
       ↓ Devicetree channel spec
       ↓ ADC device readiness
       ↓ sequence 구성
       ↓ adc_read()
       ↓ requested Arduino resolution로 정규화
~~~

ADC read는 thread 문맥 전용이며 synchronous conversion 동안 block될 수 있다.

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

현재 PWM channel 하나가 사용자 LED 2 GPIO와 같은 물리 핀을 공유한다. Variant와 Core는 이 사실을 Devicetree reference와 ownership 상태로 처리해야 한다.

### 9.2 API 범위

v1 목표:

- PWM capability가 있는 logical pin의 `analogWrite()`
- `analogWriteResolution()`
- 기본 frequency/period 정책
- duty 0과 최대값 처리
- Core가 소유한 GPIO와 PWM 사이의 안전한 전환

### 9.3 Ownership 전환

GPIO와 PWM이 모두 Arduino Core 관리 대상이고 Variant가 shareable로 표시한 pin에 한해 다음 전환을 허용한다.

~~~text
digital GPIO owner
       ↓ analogWrite()
GPIO output 비활성/상태 보존
       ↓
PWM owner
       ↓ digitalWrite()를 thread에서 호출
PWM stop
       ↓
GPIO owner로 명시적 복귀
~~~

UART, SPI, I2C, debug 또는 Zephyr device가 소유한 pin을 `analogWrite()`가 자동으로 빼앗지 않는다. ISR에서 ownership 전환을 수행하지 않는다.

### 9.4 값 변환

Arduino resolution의 최대값을 PWM period에 비례해 pulse width로 변환한다. overflow를 피하기 위해 64-bit 중간 연산을 사용한다.

실제 frequency와 resolution 조합은 PWM clock과 period 범위에 제한된다. 표현 불가능한 설정을 조용히 clamp할지 오류로 처리할지는 HIL과 Arduino library 호환 시험 후 확정하되, 실제 적용값을 조회할 진단 방법을 제공한다.

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
| `Wire` transaction | 허용 | 금지 | 예 | bus mutex와 transfer |
| `SPI` transaction | 허용 | 금지 | 예 | bus lock과 transfer |
| `analogRead` | 허용 | 금지 | 예 | synchronous conversion |
| `analogWrite` 동일 owner | 허용 | 제한적 | driver 검증 필요 | ownership 전환은 ISR 금지 |
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

- 무한 대기를 기본으로 사용하지 않는다.
- timeout은 Kconfig 또는 객체 API로 설정 가능하게 한다.
- timeout 발생 후 bus lock과 CS를 반드시 정리한다.
- UART buffer full, I2C bus hang 및 SPI driver stall을 HIL로 시험한다.

### 13.4 진단과 release

- 개발 build는 peripheral 이름, logical object, operation 및 errno를 log한다.
- ISR은 문자열 log를 직접 수행하지 않는다.
- release build에서도 상태와 범위 검사는 유지한다.
- 민감한 radio/network payload를 진단 log에 출력하지 않는다.

---

## 14. 설정 항목

Serial 항목은 M6 실제 구현값이고 나머지는 M7 이후 설계안이다.

| 설정 | 기본값 | 설명 |
| --- | ---: | --- |
| `CONFIG_NUCODE_ARDUINO_SERIAL` | `y` | 기본 `Serial` wrapper |
| `CONFIG_NUCODE_ARDUINO_SERIAL_RX_BUFFER_SIZE` | `128` | IRQ RX 고정 queue, overflow는 drop-newest |
| Serial TX buffer | 없음 | polling TX와 Core mutex 사용 |
| `CONFIG_NUCODE_ARDUINO_WIRE` | `y` | I2C master wrapper |
| `CONFIG_NUCODE_ARDUINO_WIRE_BUFFER_SIZE` | Arduino 호환 시험 후 | I2C static buffer |
| `CONFIG_NUCODE_ARDUINO_SPI` | overlay 조건부 | SPI wrapper |
| `CONFIG_NUCODE_ARDUINO_ADC` | logical mapping 후 | `analogRead` |
| `CONFIG_NUCODE_ARDUINO_PWM` | logical mapping 후 | `analogWrite` |
| `CONFIG_NUCODE_ARDUINO_PERIPHERAL_DIAGNOSTICS` | 개발 `y` | 오류 log와 counter |

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

- [ ] address scan, write, read와 repeated start가 동작한다.
- [ ] NACK, timeout, overflow와 bus 오류가 구분된다.
- [ ] shared Zephyr client가 있을 때 bus lock과 clock 정책이 지켜진다.
- [ ] 비활성 BQ25186을 Core가 자동 활성화하지 않는다.

### 15.3 SPI

- [ ] overlay 없이 SPI가 준비된 것처럼 동작하지 않는다.
- [ ] mode 0~3, frequency 및 buffer transfer를 검증한다.
- [ ] CS ownership이 중복되지 않는다.
- [ ] transaction 오류 후 lock과 CS가 복구된다.

### 15.4 ADC/PWM

- [ ] A0 및 PWM logical mapping이 Variant 문서와 일치한다.
- [ ] ADC channel, gain, reference가 최종 Devicetree와 일치한다.
- [ ] analog resolution 변환의 overflow가 없다.
- [ ] GPIO/PWM 공유 pin 전환이 glitch와 동시 구동을 만들지 않는다.
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
| I2C | 외부 known device, address NACK, repeated start |
| SPI | emulator config/transfer와 사용 가능한 경우 known peripheral |
| ADC | 활성 channel raw read와 resolution/range 변환; 외부 정밀 전압원은 선택 |
| PWM | driver duty 적용과 온보드 출력 상태; 외부 duty/frequency 계측은 선택 |
| Ownership | GPIO↔PWM 전환과 충돌 negative test |

---

## 17. 범위 제외

v1 주변장치 API에서 다음은 제외한다.

- target native USB CDC/HID/MSC
- `SerialUSB`
- 같은 UART에서 Zephyr shell과 Arduino RX의 동시 소비
- overlay 없이 비활성 SPI와 UART를 자동 활성화하는 기능
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
| I2C buffer 크기 | 대기 | library 호환성과 RAM |
| I2C target mode | v1 제외 | 실제 사용 사례 |
| 기본 SPI 논리 bus | 대기 | 전체 Variant 핀맵 승인 |
| A0...An 순서 | 대기 | Variant/connector 설계 승인 |
| PWM 기본 frequency | 대기 | Arduino 호환성과 nRF54 계측 |

---

## 19. 핵심 결정 요약

~~~text
Devicetree가 물리 peripheral을 소유한다.
Zephyr가 device 초기화와 lifetime을 소유한다.
Arduino wrapper가 begin/end와 buffer를 소유한다.

Serial = zephyr,console UART의 non-owning wrapper
USB VCOM = CMSIS-DAP interface MCU의 UART bridge
Native USB = nRF54L15에 없음
~~~

이 경계를 유지하면 Arduino의 사용성을 제공하면서도 Zephyr console, driver, pinctrl 및 전력 관리가 Core의 숨은 register 제어로 손상되는 것을 방지할 수 있다.
