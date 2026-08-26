# NU54DK Arduino 핀과 Variant 설계

| 항목 | 내용 |
| --- | --- |
| 문서 상태 | 설계 기준선 — 구현 전 |
| 작성자 | Quantum / NUCODE |
| 기준 SDK | nRF Connect SDK v3.4.0 |
| 기준 RTOS | Zephyr v4.4.0 |
| 기준 타깃 | `nrf54l15dk/nrf54l15/cpuapp/nu54dk` |
| 보드 정의 원본 | `board_package/NU54DK_Zephyr_DTS` |
| 최초 PoC 범위 | `LED_BUILTIN`과 `DT_ALIAS(led0)` |

---

## 1. 목적

이 문서는 NU54DK Arduino Core에서 Arduino 논리 핀 번호와 Zephyr Devicetree의 물리 자원을 연결하는 방법을 정의한다. 목표는 다음과 같다.

- Arduino Sketch가 `LED_BUILTIN`, `D0`, `A0` 같은 논리 이름만 사용하도록 한다.
- GPIO controller, pin 번호, polarity, pinctrl 및 주변장치 route를 Core에 중복 기록하지 않는다.
- 보드 회로가 바뀌면 보드 패키지만 수정하고, Variant는 논리 순서가 바뀔 때만 수정한다.
- 잘못된 핀 조합과 필수 Devicetree 누락을 가능한 한 빌드 시점에 발견한다.
- GPIO, ADC, PWM, UART, SPI 및 I2C 구현이 같은 핀 해석 규칙을 사용하도록 한다.

이 문서는 설계 문서다. 아래에 정의된 전체 핀 테이블과 API가 현재 구현되어 있다는 뜻은 아니다.

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

### 3.2 결정 대기 항목

다음 내용은 실제 보드 커넥터의 사용자 표기와 Arduino 호환성 검토 후 확정한다.

- 전체 `D0...Dn` 순서
- 전체 `A0...An` 순서
- `SDA`, `SCL`, `MOSI`, `MISO`, `SCK`, `SS`의 논리 번호
- NU54DK 전용 connector node의 이름과 binding 방식
- 동일 물리 핀을 digital, ADC 또는 PWM 논리 번호로 중복 노출할지 여부

따라서 최초 PoC 문서나 코드가 임의의 `D0` 전체 테이블을 확정해서는 안 된다.

---

## 4. 구성요소와 책임

### 4.1 `variant.h`

예정 경로:

~~~text
variants/nu54dk/variant.h
~~~

책임은 다음과 같다.

- Arduino Sketch에 노출할 논리 상수 선언
- `LED_BUILTIN` 선언
- `NUM_DIGITAL_PINS`, `NUM_ANALOG_INPUTS` 등 확정된 개수 선언
- Variant descriptor 조회 함수의 내부 선언 연결

물리 controller 이름과 pin 번호는 넣지 않는다.

### 4.2 `variant.cpp`

예정 경로:

~~~text
variants/nu54dk/variant.cpp
~~~

책임은 다음과 같다.

- 논리 순서에 맞춘 immutable descriptor table 생성
- Devicetree macro로 실제 device, pin 및 capability reference 생성
- 필수 alias와 node에 대한 compile-time assertion 제공
- Variant 초기화 hook가 필요할 때 최소한의 board-specific 동작 제공

첫 PoC의 descriptor는 `DT_ALIAS(led0)` 하나만 사용한다.

### 4.3 `pin_description.h`

예정 경로:

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

보드 패키지는 다음 alias를 첫 PoC에 제공해야 한다.

~~~dts
/ {
    aliases {
        led0 = &led0;
    };
};
~~~

현재 보드 정의에서 `led0`는 NU54DK 사용자 LED 1을 가리킨다. Core는 `led0`의 실제 GPIO 숫자를 알 필요가 없다.

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

### 5.2 `LED_BUILTIN`

최초 PoC의 필수 규칙은 다음과 같다.

- `LED_BUILTIN`의 실제 자원은 `DT_ALIAS(led0)`에서 얻는다.
- alias가 없거나 GPIO node가 비활성이면 빌드를 실패시킨다.
- Core 또는 Variant에 `P2.9`를 직접 쓰지 않는다.
- Blink 예제는 `pinMode(LED_BUILTIN, OUTPUT)`과 `digitalWrite()`만 사용한다.

현재 NU54DK의 LED 1은 Active High다. 그러나 Core의 raw GPIO 규칙은 향후 Active Low 핀을 일반 digital pin으로 취급할 때도 `HIGH`가 실제 High 전압을 뜻하도록 유지한다.

### 5.3 전체 핀맵 확장

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

### 5.4 capability

논리 핀의 capability는 최소한 다음 범주를 표현할 수 있어야 한다.

| capability | 의미 |
| --- | --- |
| Digital input | `pinMode(INPUT...)`, `digitalRead` 가능 |
| Digital output | `pinMode(OUTPUT)`, `digitalWrite` 가능 |
| Interrupt | GPIO interrupt controller를 통한 callback 가능 |
| ADC | 해당 logical pin에 연결된 ADC input 존재 |
| PWM | 해당 logical pin으로 route 가능한 활성 PWM channel 존재 |
| Reserved | console, crystal, debug 등으로 기본 예약됨 |

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
device_is_ready() 검사
          ↓
Arduino mode → Zephyr gpio_flags_t 변환
          ↓
gpio_pin_configure()
~~~

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

Variant는 실행 중 pinctrl을 임의로 바꾸지 않는다. GPIO와 PWM처럼 같은 물리 핀을 공유하는 기능은 application overlay와 API ownership 정책에 따라 한 소비자만 선택해야 한다.

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
| Variant 초기화 | 허용 | 금지 | Zephyr `main` 진입 후 한 번 수행 |
| 동적 핀맵 변경 | 지원하지 않음 | 지원하지 않음 | overlay 재빌드 대상 |

Variant lookup에서 heap, mutex 또는 logging을 필수로 요구하면 안 된다. ISR에서 발생한 오류의 문자열 logging은 즉시 수행하지 않고, 정수 상태를 기록하거나 조용히 실패하는 정책을 사용한다.

---

## 9. 오류 정책

### 9.1 빌드 시 오류

다음 조건은 compile-time failure로 처리한다.

- `DT_ALIAS(led0)`가 없음
- `led0`가 GPIO spec을 제공하지 않음
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

Arduino 표준의 `void` API는 오류를 직접 반환할 수 없다. 기본 정책은 다음과 같다.

1. 메모리를 손상시키거나 다른 핀을 잘못 제어하지 않는다.
2. 해당 동작을 수행하지 않는다.
3. thread 문맥이고 진단 기능이 켜져 있으면 Zephyr log를 남긴다.
4. ISR에서는 logging하지 않는다.
5. 디버그용 Core 상태 조회 API의 도입 여부는 API 설계 단계에서 결정한다.

유효하지 않은 pin을 배열 index로 그대로 사용하거나 modulo 연산으로 다른 pin에 매핑해서는 안 된다.

---

## 10. 설정 항목

아래 이름은 구현 예정안이며 현재 존재하는 Kconfig로 간주하면 안 된다.

| 설정안 | 기본값안 | 목적 |
| --- | ---: | --- |
| `CONFIG_NUCODE_ARDUINO_CORE` | `y` | Arduino Core 정적 편입 |
| `CONFIG_NUCODE_ARDUINO_GPIO` | `y` | digital GPIO API 활성화 |
| `CONFIG_NUCODE_ARDUINO_PIN_DIAGNOSTICS` | 개발 `y` | invalid pin과 capability 오류 log |
| `CONFIG_NUCODE_ARDUINO_STRICT_PIN_CHECK` | CI `y` | 가능한 오류를 assertion으로 강화 |

보드 물리 설정을 Kconfig 문자열로 다시 입력하는 옵션은 만들지 않는다. 예를 들어 `CONFIG_LED0_PIN=41` 같은 설정은 단일 원본 원칙에 위배된다.

---

## 11. 완료 기준

핀과 Variant v0가 완료되었다고 판단하려면 다음 조건을 모두 충족해야 한다.

- [ ] `LED_BUILTIN`이 `DT_ALIAS(led0)`에서 생성된다.
- [ ] Core와 Variant에 `P2.9` 하드코딩이 없다.
- [ ] `nrf54l15dk/nrf54l15/cpuapp/nu54dk` 전체 정적 빌드가 성공한다.
- [ ] 최종 `zephyr.dts`와 descriptor가 같은 GPIO를 가리킨다.
- [ ] invalid pin이 out-of-bounds access를 만들지 않는다.
- [ ] LED Blink가 pyOCD 플래시 후 리셋부터 즉시 동작한다.
- [ ] 동일 source로 pristine build와 incremental build 결과가 일치한다.
- [ ] 전체 D/A 순서를 추가하기 전에 connector 및 중복 mapping 정책이 문서로 승인된다.

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

1. `LED_BUILTIN`을 output으로 설정한다.
2. `HIGH`와 `LOW`를 번갈아 기록한다.
3. LED 상태와 GPIO 전압을 확인한다.
4. 사용자 버튼 alias를 추가한 뒤 pull-up과 Active Low 입력을 확인한다.
5. PWM/GPIO 공유 핀은 각기 다른 overlay로 빌드해 단독 동작을 확인한다.

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
- 아직 승인되지 않은 전체 D0/A0 번호표
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
~~~

이 분리를 유지하면 보드 회로 변경과 Arduino API 변경을 서로 독립적으로 관리할 수 있으며, Full Zephyr 빌드가 제공하는 Devicetree 검증을 그대로 활용할 수 있다.
