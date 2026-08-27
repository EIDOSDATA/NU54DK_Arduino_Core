# NU54DK Arduino 핀과 Variant 설계

| 항목 | 내용 |
| --- | --- |
| 문서 상태 | M3 digital Variant 완료, M7 A0·PWM 역할 조건부 완료 |
| 작성자 | Quantum / NUCODE |
| 기준 SDK | nRF Connect SDK v3.4.0 |
| 기준 RTOS | Zephyr v4.4.0 |
| 기준 타깃 | `nrf54l15dk/nrf54l15/cpuapp/nu54dk` |
| 보드 정의 원본 | `board_package/NU54DK_Zephyr_DTS` |
| 공개 역할 | digital 2개 + `A0` + `PIN_PWM0`; `NUM_PIN_ROLES=4` |

---

## 1. 목적

이 문서는 NU54DK Arduino Core에서 Arduino 논리 핀 번호와 Zephyr Devicetree의 물리 자원을 연결하는 방법을 정의한다. 목표는 다음과 같다.

- Arduino Sketch가 `LED_BUILTIN`, `D0`, `A0` 같은 논리 이름만 사용하도록 한다.
- GPIO controller, pin 번호, polarity, pinctrl 및 주변장치 route를 Core에 중복 기록하지 않는다.
- 보드 회로가 바뀌면 보드 패키지만 수정하고, Variant는 논리 순서가 바뀔 때만 수정한다.
- 잘못된 핀 조합과 필수 Devicetree 누락을 가능한 한 빌드 시점에 발견한다.
- GPIO, ADC, PWM, UART, SPI 및 I2C 구현이 같은 핀 해석 규칙을 사용하도록 한다.

이 문서는 장기 설계와 현재 구현 상태를 함께 관리한다. M3의 digital GPIO 범위는 논리 핀
2개이며, M7은 별도 논리 역할 `A0`와 `PIN_PWM0`을 추가했다. 두 역할의 target 의미 시험과
실제 driver 호출은 통과했지만 전체 D/A 핀, 일반 peripheral ownership과 임의 핀 전환은
여전히 구현 범위가 아니다.

---

## 2. 단일 원본 원칙

### 2.1 물리 정보의 단일 원본

NU54DK의 물리 정보는 다음 서브모듈이 단독으로 소유한다.

~~~text
board_package/NU54DK_Zephyr_DTS
~~~

이 저장소가 소유하는 정보는 다음과 같다.

- nRF54L15 GPIO controller와 실제 pin 번호
- LED와 버튼의 GPIO polarity 및 pull 설정
- UART, I2C, SPI, PWM, ADC 및 GRTC pinctrl
- peripheral node의 `status`
- `chosen`과 `aliases`
- 핀 충돌과 솔더브리지 관련 하드웨어 설명
- Flash/RAM partition과 Zephyr board metadata

관련 근거 문서는 다음과 같다.

- [NU54DK 핀 구성](../../board_package/NU54DK_Zephyr_DTS/00_Docs/03_PINOUT.md)
- [NU54DK 하드웨어 주의사항](../../board_package/NU54DK_Zephyr_DTS/00_Docs/04_HARDWARE_NOTES.md)
- [NU54DK 보드 개발 문서](../../board_package/NU54DK_Zephyr_DTS/00_Docs/01_BOARD_DEVELOPMENT.md)

Arduino Core 안에 `P2.9`, `P1.10` 같은 값을 별도의 진실로 복사하지 않는다. 문서 예시에서 물리 핀을 설명할 수는 있지만, 실행 코드가 그 문서의 숫자를 직접 소비해서는 안 된다.

### 2.2 Variant가 소유하는 정보

`variants/nu54dk`는 다음 Arduino 논리 정보만 소유한다.

- 논리 핀 배열의 순서
- `D0`, `D1`, `A0` 등 Arduino 이름과 배열 index의 관계
- `LED_BUILTIN`과 같은 Arduino 관례 이름
- 각 논리 핀에 허용할 Arduino API 범주
- Arduino library 호환을 위한 논리 상수

Variant는 물리 controller와 pin 번호를 직접 소유하지 않는다. 논리 index가 가리키는 실제 GPIO와 주변장치는 Devicetree macro를 통해 얻는다.

### 2.3 Core 공통 코드가 소유하는 정보

`cores/arduino`는 다음 동작 규칙을 소유한다.

- `pin_size_t`의 유효 범위 검사
- 논리 핀에서 Variant descriptor를 찾는 방법
- Arduino mode와 Zephyr GPIO flag의 변환
- 잘못된 핀과 준비되지 않은 device의 오류 처리
- ISR 및 thread 문맥별 허용 API

보드별 `switch` 문이나 물리 핀 상수를 Core 공통 코드에 넣지 않는다.

---

## 3. 설계 상태와 결정 범위

### 3.1 확정된 결정

1. 물리 핀 정보는 `NU54DK_Zephyr_DTS`가 단일 원본이다.
2. Core는 해당 저장소를 `BOARD_ROOT`로 전달해 실제 빌드에 사용한다.
3. 최초 PoC의 `LED_BUILTIN`은 반드시 `DT_ALIAS(led0)`에서 얻는다.
4. `digitalWrite(HIGH)`와 `digitalRead()`는 Arduino의 전기적 High/Low 의미를 보존하기 위해 raw GPIO 값으로 처리한다.
5. peripheral 충돌은 Variant가 런타임에 몰래 전환하지 않고, Devicetree overlay와 Kconfig에서 명시적으로 해결한다.
6. `NUM_DIGITAL_PINS`는 digital descriptor 수 2를 유지하고, A0와 PWM을 포함한 공개 역할 수는
   `NUM_PIN_ROLES=4`로 별도 표시한다.
7. `LED_BUILTIN` P2.9는 digital GPIO이며 PWM 역할이 아니다. `analogWrite()`는
   `PIN_PWM0`/`PIN_PWM_LED`만 받는다.

### 3.2 M3 구현 기준선

| 논리 index | 공개 이름 | Devicetree 원본 | M3 capability |
| ---: | --- | --- | --- |
| 0 | `LED_BUILTIN` | `DT_ALIAS(led0)` | digital input + output |
| 1 | `PIN_BUTTON0` | `DT_ALIAS(sw0)` | digital input only |

`NUM_DIGITAL_PINS`는 2다. descriptor는 `GPIO_DT_SPEC_GET()`으로 alias의 controller, pin과
flag를 얻으므로 Variant에 실제 nRF GPIO 번호를 복제하지 않는다. `led0`와 `sw0` alias가
없거나 활성 GPIO spec을 제공하지 않으면 compile 단계에서 실패한다.

M3 공개 GPIO API는 thread 문맥에서만 동작한다. ISR 호출은 수행하지 않고 `digitalRead()`는
`LOW`를 반환한다. pin mode, output latch, 마지막 오류와 driver 오류는 Core 내부 atomic
상태로 보존하지만 Sketch에 공개하는 진단 API는 아직 없다.

### 3.3 M7 논리 역할 기준선

| 논리 index | 공개 이름 | Devicetree 원본 | M7 계약 |
| ---: | --- | --- | --- |
| 2 | `PIN_A0`, `A0` | `nucode,arduino-adc` chosen의 `io-channels` | P1.12/SAADC channel 5, 고정 12-bit raw |
| 3 | `PIN_PWM0`, `PIN_PWM_LED` | `nucode,arduino-pwm` chosen | P1.10/pwm20, 고정 20 ms·8-bit |

물리 핀 표기는 회로와 최종 Devicetree를 사람이 대조하기 위한 설명이며 실행 코드의 pin
상수가 아니다. Core overlay는 ADC용 `nucode,arduino-adc-input` node와 PWM 역할을 chosen으로 선택한다.
PWM chosen은 보드의 `pwm_led1` node를 가리키며, 이 node는 `pwm-led0` alias의 대상과 같다.

`NUM_DIGITAL_PINS=2`, `NUM_ANALOG_INPUTS=1`, `NUM_ANALOG_OUTPUTS=1`,
`NUM_PIN_ROLES=4`다. index 2와 3은 `pinMode()`·`digitalRead()`·`digitalWrite()`의 digital
descriptor 범위가 아니다.

### 3.4 결정 대기 항목

다음 내용은 실제 보드 커넥터의 사용자 표기와 Arduino 호환성 검토 후 확정한다.

- 전체 `D0...Dn` 순서
- `A1...An` 추가 순서
- `SDA`, `SCL`, `MOSI`, `MISO`, `SCK`, `SS`의 논리 번호
- NU54DK 전용 connector node의 이름과 binding 방식
- 현재 A0/PWM 역할 밖의 동일 물리 핀을 digital, ADC 또는 PWM 논리 번호로 중복 노출할지 여부

따라서 최초 PoC 문서나 코드가 임의의 `D0` 전체 테이블을 확정해서는 안 된다.

---

## 4. 구성요소와 책임

### 4.1 `variant.h`

현재 경로:

~~~text
variants/nu54dk/variant.h
~~~

책임은 다음과 같다.

- Arduino Sketch에 노출할 논리 상수 선언
- `LED_BUILTIN`, `PIN_BUTTON0`, `PIN_A0`/`A0`, `PIN_PWM0`/`PIN_PWM_LED` 선언
- `NUM_DIGITAL_PINS=2`, `NUM_ANALOG_INPUTS=1`, `NUM_ANALOG_OUTPUTS=1`,
  `NUM_PIN_ROLES=4` 선언
- `AR_DEFAULT`와 같은 값의 설명용 별칭 `AR_INTERNAL` 선언
- Variant descriptor 조회 함수의 내부 선언 연결

물리 controller 이름과 pin 번호는 넣지 않는다.

### 4.2 `variant.cpp`

현재 경로:

~~~text
variants/nu54dk/variant.cpp
~~~

책임은 다음과 같다.

- 논리 순서에 맞춘 immutable descriptor table 생성
- Devicetree macro로 실제 device, pin 및 capability reference 생성
- 필수 alias와 node에 대한 compile-time assertion 제공
- Variant 초기화 hook가 필요할 때 최소한의 board-specific 동작 제공

M3 descriptor는 `DT_ALIAS(led0)`와 `DT_ALIAS(sw0)`를 사용한다. LED descriptor에는
digital input/output capability를, 버튼 descriptor에는 digital input capability만 둔다.
따라서 버튼을 `OUTPUT`으로 바꾸거나 `digitalWrite()`로 구동하려는 요청은 no-op으로
거부된다.

### 4.3 `pin_description.h`

현재 경로:

~~~text
cores/arduino/internal/pin_description.h
~~~

외부 Sketch에 노출하지 않는 내부 descriptor 계약을 정의한다. 개념 모델은 다음과 같다.

~~~text
PinDescription
├─ gpio_dt_spec 또는 동등한 Devicetree 생성 정보
├─ Arduino 논리 capability bit
├─ ADC/PWM 등 peripheral reference의 존재 여부
└─ 진단용 논리 이름 또는 index
~~~

구체적인 C++ layout은 ABI로 공개하지 않는다. Loader 없는 전체 정적 빌드이므로 내부 layout을 공개 ABI로 고정할 필요가 없다.

### 4.4 보드 패키지

보드 패키지는 다음 alias를 M3에 제공해야 한다.

~~~dts
/ {
    aliases {
        led0 = &led0;
        sw0 = &button0;
    };
};
~~~

위 DTS는 관계를 설명하는 축약 예시이며 실제 label은 보드 패키지가 소유한다. 현재 보드
정의에서 `led0`는 NU54DK 사용자 LED 1을, `sw0`는 사용자 버튼 1을 가리킨다. Core는 두
alias의 실제 GPIO 숫자를 알 필요가 없다.

### 4.5 Build Adapter

향후 Arduino CLI Build Adapter는 Variant를 직접 생성하지 않는다. 다음 정보만 전체 Zephyr 빌드에 전달한다.

- 선택된 board target
- `BOARD_ROOT`
- Core Zephyr module 경로
- Sketch별 `prj.conf`
- Sketch별 overlay

Variant와 보드 패키지의 관계는 west-native 빌드와 Arduino CLI 빌드에서 동일해야 한다.

---

## 5. 논리 핀 모델

### 5.1 논리 index

Sketch가 전달하는 `pin_size_t`는 nRF의 물리 pin 번호가 아니라 Variant 배열의 index다.

~~~text
Sketch pin_size_t
      ↓ 범위 검사
Variant descriptor[index]
      ↓ Devicetree 생성 정보
Zephyr device + GPIO pin
~~~

예를 들어 `LED_BUILTIN`이 논리 index 0이라고 하더라도 이것이 `P0.0`을 의미하지 않는다. 그 index의 descriptor가 `DT_ALIAS(led0)`에서 생성된 GPIO를 가리킨다는 뜻이다.

현재 공개한 index 0과 1은 `LED_BUILTIN`과 `PIN_BUTTON0`이라는 digital 역할 이름으로만
노출한다. index 2와 3은 각각 `A0`와 `PIN_PWM0`이라는 peripheral 역할이며 digital pin 수에
포함하지 않는다. 이 네 역할을 아직 승인되지 않은 `D0...Dn` 전체 번호표로 확대 해석하지
않는다.

### 5.2 `LED_BUILTIN`

M3 구현 규칙은 다음과 같다.

- `LED_BUILTIN`의 실제 자원은 `DT_ALIAS(led0)`에서 얻는다.
- alias가 없거나 GPIO node가 비활성이면 빌드를 실패시킨다.
- Core 또는 Variant에 `P2.9`를 직접 쓰지 않는다.
- Blink 예제는 `pinMode(LED_BUILTIN, OUTPUT)`과 `digitalWrite()`만 사용한다.

현재 NU54DK의 LED 1은 Active High다. 그러나 Core의 raw GPIO 규칙은 향후 Active Low 핀을 일반 digital pin으로 취급할 때도 `HIGH`가 실제 High 전압을 뜻하도록 유지한다.

`LED_BUILTIN`의 실제 핀 P2.9에는 M7 PWM 역할을 부여하지 않는다. 따라서
`analogWrite(LED_BUILTIN, ...)`는 지원 요청이 아니며 거부된다.

### 5.3 `PIN_BUTTON0`

- `PIN_BUTTON0`의 실제 자원은 `DT_ALIAS(sw0)`에서 얻는다.
- 논리 index는 1이며 digital input capability만 갖는다.
- `INPUT_PULLUP`의 raw 입력은 해제 `HIGH`, 누름 `LOW`다.
- `digitalWrite(PIN_BUTTON0, ...)`와 `pinMode(PIN_BUTTON0, OUTPUT)`은 다른 핀을 건드리지
  않고 거부된다.

실제 NU54DK 버튼 HIL에서 해제/누름 raw 값에 따라 LED가 꺼지고 켜지는 경로를 확인했다.
debounce, interrupt와 장시간 반복 입력은 이 결과에 포함하지 않는다.

### 5.4 `PIN_A0`/`A0`

- 논리 index는 2이며 `NUM_DIGITAL_PINS` 범위 밖이다.
- `nucode,arduino-adc` chosen의 단일 `io-channels` spec을 사용한다.
- NU54DK 기준 물리 경로는 P1.12/SAADC channel 5다.
- Core overlay가 보드의 미지원 gain 1/6을 nRF54L15용 `ADC_GAIN_1_4`로 override한다.
- `analogRead()`는 고정 12-bit raw 0..4095를 반환하고 오류는 `-1`이다.
- nominal full-scale 약 2.4 V는 saturation 기준이며 핀 절대최대 정격 안내가 아니다.
- `analogReference(AR_DEFAULT)`만 허용하며 `AR_INTERNAL`은 같은 값의 별칭이다.
- `analogReadResolution()`은 vendored API에 선언이 없어 구현하지 않는다.

### 5.5 `PIN_PWM0`/`PIN_PWM_LED`

- 두 이름은 같은 논리 index 3이다.
- `nucode,arduino-pwm` chosen이 가리키는 P1.10/pwm20 channel 0 역할을 사용한다.
- period는 20 ms, duty 입력은 고정 8-bit 0..255다.
- 이 역할은 digital descriptor가 아니므로 GPIO↔PWM 자동 ownership 전환이 없다.
- `analogWriteResolution()`과 임의 PWM frequency 변경은 구현하지 않는다.

### 5.6 전체 핀맵 확장

전체 핀맵을 추가할 때는 보드 패키지에 connector 또는 Arduino용 mapping node를 추가하는 방식을 우선 검토한다.

~~~text
NU54DK board Devicetree
└─ connector/gpio-map 또는 동등한 mapping node
       ↓
Variant의 논리 순서
       ↓
PinDescription table
~~~

NU54DK가 물리적으로 Arduino R3 header가 아니라면 `arduino-header-r3`라는 이름을 억지로 사용하지 않는다. 보드의 실제 connector 구조를 나타내는 전용 binding이나 일반 GPIO mapping node를 사용한다.

### 5.5 capability

논리 핀의 capability는 최소한 다음 범주를 표현할 수 있어야 한다.

| capability | 의미 |
| --- | --- |
| Digital input | `pinMode(INPUT...)`, `digitalRead` 가능 |
| Digital output | `pinMode(OUTPUT)`, `digitalWrite` 가능 |
| Interrupt | GPIO interrupt controller의 callback 가능; M6에서 index 1 edge 의미 구현 |
| ADC | M7의 `A0`처럼 chosen ADC input에 연결된 전용 논리 역할 |
| PWM | M7의 `PIN_PWM0`처럼 chosen PWM consumer에 연결된 전용 논리 역할 |
| Reserved | console, crystal, debug 등으로 기본 예약됨; 일반 ownership 전환은 미구현 |

capability bit는 Arduino API의 빠른 사전 검사용이다. 실제 활성 가능 여부는 최종 Devicetree와 device readiness가 결정한다. Variant의 bit만으로 비활성 peripheral을 활성화하지 않는다.

---

## 6. 데이터와 호출 흐름

### 6.1 `pinMode`

~~~text
Sketch pinMode(logical_pin, mode)
          ↓
논리 범위 및 capability 검사
          ↓
Variant descriptor 조회
          ↓
gpio_is_ready_dt() 검사
          ↓
Arduino mode → Zephyr gpio_flags_t 변환
          ↓
gpio_pin_configure()
~~~

M3는 `INPUT`, `INPUT_PULLUP`, `INPUT_PULLDOWN`, `OUTPUT`을 변환한다.
`OUTPUT_OPENDRAIN`은 공개 enum에 향후 값으로 존재하지만 구현되지 않았다. `OUTPUT`으로
전환할 때 마지막 output latch를 적용하며, LED처럼 input capability도 있는 output은 실제
핀 readback을 위해 input buffer도 연결한다.

### 6.2 `digitalWrite`

~~~text
Sketch digitalWrite(logical_pin, HIGH/LOW)
          ↓
논리 범위·output 상태 검사
          ↓
Variant descriptor 조회
          ↓
Arduino HIGH/LOW → raw 1/0
          ↓
gpio_pin_set_raw()
~~~

`gpio_pin_set_dt()`는 `GPIO_ACTIVE_LOW`를 논리적으로 반전할 수 있으므로 일반 Arduino digital API의 기본 구현으로 사용하지 않는다.

M3 `digitalWrite()`는 output capability가 있고 `OUTPUT`으로 성공적으로 구성된 핀에서만
동작한다. input 핀에서 `HIGH`/`LOW`로 pull-up을 켜고 끄는 Arduino 관례는 아직 구현하지
않았다. `digitalRead()`는 input capability와 성공한 pin 구성을 요구하며 raw 값을
`LOW`/`HIGH`로 반환한다. invalid pin, 잘못된 mode 또는 driver 오류는 panic하지 않는다.

### 6.3 ADC 또는 PWM

~~~text
Sketch analogRead/analogWrite(logical_pin)
          ↓
Variant capability 검사
          ↓
descriptor가 참조하는 Devicetree peripheral 확인
          ↓
활성 node와 pinctrl 확인
          ↓
Zephyr ADC/PWM API
~~~

Variant는 실행 중 pinctrl을 임의로 바꾸지 않는다. M7의 A0와 PWM 역할은 digital descriptor
table에 끼워 넣지 않고 각각 chosen peripheral을 직접 확인한다. 따라서 GPIO↔PWM 자동
ownership 전환은 없으며 P1.10을 다른 소비자와 함께 쓰려면 application overlay에서 명시적으로
구성을 바꿔야 한다. 일반 peripheral owner table과 lifecycle 전환은 아직 구현하지 않는다.

---

## 7. 핀 충돌 정책

NU54DK에는 다음과 같은 물리 충돌 가능성이 있다.

| 자원 | 충돌 예 | 정책 |
| --- | --- | --- |
| P1.10 | 사용자 LED 2와 PWM20 OUT0 | GPIO와 PWM을 동시에 소유하지 않음 |
| P1.8 | 사용자 버튼 3과 GRTC FAST 출력 | overlay와 실제 스위치 연결을 함께 검토 |
| P0.4 | 사용자 버튼 4와 GRTC 32 kHz 출력 | overlay와 실제 스위치 연결을 함께 검토 |
| P2.7 | 사용자 LED 3과 SWO | 솔더브리지 상태와 debug 용도를 확인 |
| P1.2/P1.3 | I2C22, NFC 및 SERIAL22 대체 모드 | 한 시점에 하나의 peripheral route만 활성화 |
| P2.1/P2.2/P2.4 | SPI00과 uart00 | Core overlay가 SPI00을 활성화할 때 uart00을 동시에 활성화하지 않음 |

Variant는 이러한 충돌을 다음 방법으로 숨기지 않는다.

- 첫 API 호출이 이전 소비자를 자동 해제하는 동작
- GPIO 호출이 PWM device를 자동 중단하는 동작
- 실제 솔더브리지 상태를 소프트웨어가 임의 추정하는 동작

필요한 전환은 overlay, Kconfig 및 명시적인 API lifecycle에서 수행한다. 빌드 가능한 구성이 전기적으로 안전하다는 보장은 없으므로 회로와 실물 검증이 별도로 필요하다.

---

## 8. 스레드와 ISR 문맥

Variant descriptor는 빌드 후 변경되지 않는 read-only data로 구현한다. descriptor 조회 자체는 thread와 ISR에서 안전해야 한다.

| 동작 | Thread | ISR | 비고 |
| --- | --- | --- | --- |
| 논리 핀 범위 검사 | 허용 | 허용 | 메모리 할당과 lock을 사용하지 않음 |
| descriptor 조회 | 허용 | 허용 | immutable table |
| device readiness 검사 | 허용 | 조건부 | 초기화 완료 후 값만 조회 |
| `pinMode()` | 허용 | 거부 | ISR에서는 no-op과 private 오류 기록 |
| `digitalWrite()` | 허용 | 거부 | ISR에서는 no-op과 private 오류 기록 |
| `digitalRead()` | 허용 | 거부 | ISR에서는 private 오류 기록 후 `LOW` |
| Variant 초기화 | 허용 | 금지 | Zephyr `main` 진입 후 한 번 수행 |
| 동적 핀맵 변경 | 지원하지 않음 | 지원하지 않음 | overlay 재빌드 대상 |

Variant lookup에서 heap, mutex 또는 logging을 사용하지 않는다. M3의 mode, output latch,
마지막 Core 오류와 원래 driver 오류는 `atomic_t`로 보존한다. 이 상태의 조회 함수는
`internal/pin_description.h`에만 있으며 Arduino Sketch 공개 API가 아니다. GPIO API의
동시 재구성을 직렬화하는 ownership lock은 아직 구현하지 않았다.

---

## 9. 오류 정책

### 9.1 빌드 시 오류

다음 조건은 compile-time failure로 처리한다.

- `DT_ALIAS(led0)`가 없음
- `led0`가 GPIO spec을 제공하지 않음
- `DT_ALIAS(sw0)`가 없거나 GPIO spec을 제공하지 않음
- 필수 Variant node가 `okay`가 아님
- 논리 핀 수와 descriptor 수가 다름
- 같은 논리 index가 상충하는 필수 capability로 정의됨

가능한 경우 `BUILD_ASSERT`, Devicetree macro 및 Kconfig dependency를 사용한다.

### 9.2 런타임 오류

다음 조건은 런타임 검사가 필요하다.

- GPIO device가 준비되지 않음
- 유효 범위 밖의 논리 핀
- 요청 API를 지원하지 않는 capability
- 이미 다른 peripheral이 소유한 pin
- driver가 반환한 I/O 오류

이 가운데 peripheral ownership 검사는 목표 정책이며 M3에는 구현되지 않았다. 현재는 논리
범위, digital capability, mode, device readiness, 지원하지 않는 Devicetree flag와 driver
오류만 검사한다.

Arduino 표준의 `void` API는 오류를 직접 반환할 수 없다. 기본 정책은 다음과 같다.

1. 메모리를 손상시키거나 다른 핀을 잘못 제어하지 않는다.
2. 해당 동작을 수행하지 않는다.
3. M3는 Zephyr log 대신 private atomic 오류와 원래 driver 오류를 기록한다.
4. ISR에서는 logging하지 않고 공개 GPIO 동작을 거부한다.
5. 공개 진단 API의 도입 여부는 이후 API 설계에서 결정한다.

유효하지 않은 pin을 배열 index로 그대로 사용하거나 modulo 연산으로 다른 pin에 매핑해서는 안 된다.

---

## 10. 설정 항목

M3 digital 설정과 M7 peripheral 설정을 구분한다. M7 설정은 module 수준에서 기본 `n`이고
Arduino builder의 기본 profile이 선택한 역할과 함께 `y`로 켠다.

| 설정 | 상태 | 기본값/용도 |
| --- | --- | --- |
| `CONFIG_NUCODE_ARDUINO_CORE` | 구현 | 기본 `n`; Arduino Core 정적 편입 |
| `CONFIG_NUCODE_ARDUINO_GPIO` | 구현 | Core 활성 시 기본 `y`; digital GPIO API와 Zephyr GPIO 선택 |
| `CONFIG_NUCODE_ARDUINO_WIRE` | M7 구현 | module 기본 `n`; I2C22 `Wire` |
| `CONFIG_NUCODE_ARDUINO_WIRE_BUFFER_SIZE` | M7 구현 | 기본 32 byte; TX/RX 각각 고정 buffer |
| `CONFIG_NUCODE_ARDUINO_SPI` | M7 구현 | module 기본 `n`; Core overlay의 SPI00 |
| `CONFIG_NUCODE_ARDUINO_ADC` | M7 구현 | module 기본 `n`; A0 고정 12-bit raw |
| `CONFIG_NUCODE_ARDUINO_PWM` | M7 구현 | module 기본 `n`; P1.10 고정 20 ms·8-bit |
| `CONFIG_NUCODE_ARDUINO_PIN_DIAGNOSTICS` | 미구현 후보 | invalid pin과 capability 오류 log |
| `CONFIG_NUCODE_ARDUINO_STRICT_PIN_CHECK` | 미구현 후보 | CI에서 가능한 오류를 assertion으로 강화 |

보드 물리 설정을 Kconfig 문자열로 다시 입력하는 옵션은 만들지 않는다. 예를 들어 `CONFIG_LED0_PIN=41` 같은 설정은 단일 원본 원칙에 위배된다.

---

## 11. 완료 기준

핀과 Variant v0가 완료되었다고 판단하려면 다음 조건을 모두 충족해야 한다.

- [x] `LED_BUILTIN`이 `DT_ALIAS(led0)`에서 생성된다.
- [x] `PIN_BUTTON0`이 `DT_ALIAS(sw0)`에서 생성된다.
- [x] Core와 Variant에 `P2.9` 같은 실제 GPIO pin 하드코딩이 없다.
- [x] `nrf54l15dk/nrf54l15/cpuapp/nu54dk` 전체 정적 빌드가 성공한다.
- [x] 최종 Devicetree alias에서 descriptor가 생성된다.
- [x] invalid pin self-check 후에만 도달하는 버튼 연동 loop를 육안 확인했다.
  세부 RAM trace 값은 미회수다.
- [x] LED Blink와 버튼 raw 입력/LED 연동이 NU54DK HIL에서 동작한다.
- [ ] 동일 source로 pristine build와 incremental build 결과가 일치한다.
- [ ] ISR 거부, 동시 호출과 오류 상태를 자동 회귀 시험으로 고정한다.
- [ ] input `digitalWrite()`, peripheral ownership와 interrupt 정책을 구현·검증한다.
- [ ] 전체 D/A 순서를 추가하기 전에 connector 및 중복 mapping 정책이 문서로 승인된다.

M7 역할의 확보된 실행 증거는 다음과 같다.

- [x] `PIN_A0`/`A0`와 `PIN_PWM0`/`PIN_PWM_LED`의 target compile과 emulator 의미 시험
- [x] A0 actual driver read와 P1.10 PWM 0·중간·255 실기 경로
- [x] PWM 전용 역할 이외의 pin을 거부하는 negative 의미 시험; `LED_BUILTIN` P2.9는 PWM 역할이 아님

---

## 12. 테스트 계획

### 12.1 정적 검사

- Core와 Variant에서 `P0.`, `P1.`, `P2.` 형태의 물리 상수 검색
- descriptor 개수와 공개 상수 개수 비교
- 필수 alias를 제거한 test overlay에서 빌드 실패 확인
- 비활성 GPIO node를 사용한 negative build 확인

### 12.2 Zephyr test

- mock descriptor를 이용한 논리 범위 검사
- capability 조합별 API 허용·거부 검사
- Active High/Active Low spec에서도 raw Arduino 값 변환 검사
- pin ownership 상태 전이 검사

### 12.3 NU54DK HIL

M3에서 통과한 범위는 다음과 같다.

1. `LED_BUILTIN`을 output으로 설정하고 Arduino API만으로 250 ms Blink를 실행했다.
2. `PIN_BUTTON0`을 `INPUT_PULLUP`으로 설정하고 해제 `HIGH`, 누름 `LOW` raw 의미를
   확인했다.
3. 버튼을 누르면 LED가 켜지고 해제하면 꺼지는 연동을 확인했다.
4. `NUM_DIGITAL_PINS`를 invalid pin으로 사용한 호출 전후에 LED 상태가 유지되는
   self-check를 포함했다.

M6는 GPIO emulator로 raw edge ISR 의미를 자동 검증하고, 실제 P1.13 active-low 버튼의
FALLING/RISING/CHANGE도 DAPLink sequence 25/COM10에서 확인했다. 외부 logic
analyzer/oscilloscope 계측은 사용자 결정으로 필수 증거에서 제외한다. pull-down, 입력
pin의 `digitalWrite()`, debounce, 장시간 반복, 동시 호출과 PWM/GPIO ownership은 해당 API
단계에서 별도 검증한다.

M7 target ztest에서 ADC 2/2와 PWM 2/2가 통과했다. 최종 실제 sequence 37에서는 gain 1/4의
A0 raw=3140과 PWM duty 0/128/255 driver 호출을 확인했다. 이 결과는 ADC 전압 정확도나 PWM
외부 파형을 증명하지 않으며 logic analyzer/oscilloscope와 정밀 전압 계측은 M7 필수 증거가
아니다.

### 12.4 회귀 검사

보드 패키지 서브모듈 commit을 갱신할 때 다음을 자동 비교한다.

- board target 존재 여부
- 필수 alias 존재 여부
- 최종 Devicetree status
- Variant가 참조하는 connector index 수
- Blink와 GPIO HIL 결과

---

## 13. 범위 제외

이 문서에서 다음 항목은 설계하거나 보장하지 않는다.

- LLEXT Loader용 고정 ABI 핀 테이블
- 런타임에 내려받는 동적 Variant
- 임의의 nRF 물리 pin 번호를 Arduino pin으로 직접 전달하는 API
- 솔더브리지 자동 감지
- overlay 없이 peripheral route를 자동 변경하는 기능
- 아직 승인되지 않은 전체 D0 및 A1 이후 번호표
- USB pin 또는 USB CDC Variant

nRF54L15 target에는 native USB peripheral이 없다. NU54DK의 USB connector와 CMSIS-DAP 인터페이스 MCU를 target의 Arduino USB pin이나 USB device 기능으로 표현하지 않는다.

---

## 14. 핵심 결정 요약

~~~text
물리 회로·GPIO·pinctrl
        = NU54DK_Zephyr_DTS 소유

Arduino 논리 이름과 순서
        = NU54DK Variant 소유

API 동작과 검증
        = Core 공통 코드 소유

LED_BUILTIN
        = DT_ALIAS(led0)

PIN_BUTTON0
        = DT_ALIAS(sw0)

M7 A0
        = nucode,arduino-adc chosen

M7 PWM
        = nucode,arduino-pwm chosen

digital 핀 수 / 전체 역할 수
        = 2 / 4
~~~

이 분리를 유지하면 보드 회로 변경과 Arduino API 변경을 서로 독립적으로 관리할 수 있으며,
Full Zephyr 빌드가 제공하는 Devicetree 검증을 그대로 활용할 수 있다. M3 결과는 두 digital
핀의 기준선이고 M7의 A0/PWM 역할은 승인된 target·실기 범위에서 검증됐다. 네 역할은 전체
Arduino 핀맵이나 일반 ownership 완료 판정이 아니다.
