# NU54DK Arduino Runtime 설계

| 항목 | 내용 |
| --- | --- |
| 문서 상태 | 설계 기준선 — 구현 전 |
| 작성자 | Quantum / NUCODE |
| 실행 방식 | Loader 없는 Native Full Zephyr 정적 펌웨어 |
| 기준 SDK | nRF Connect SDK v3.4.0 |
| 기준 RTOS | Zephyr v4.4.0 |
| 기준 타깃 | `nrf54l15dk/nrf54l15/cpuapp/nu54dk` |
| 기본 실행 문맥 | PoC: Zephyr `main` thread |

---

## 1. 목적

이 문서는 Arduino Sketch의 `setup()`과 `loop()`를 NCS/Zephyr 애플리케이션 안에서 실행하는 runtime 구조를 정의한다. 다음 질문에 대한 기준을 제공한다.

- 리셋 후 어떤 코드가 어떤 순서로 실행되는가?
- Arduino Sketch와 Zephyr kernel은 어떤 관계인가?
- 누가 thread, stack, device 초기화 및 lifecycle을 소유하는가?
- `loop()`가 계속 실행되는 동안 Zephyr background 작업은 어떻게 동작하는가?
- ISR callback과 일반 Arduino API 사이의 경계는 무엇인가?
- 초기화 또는 실행 오류는 어떻게 처리하는가?

이 문서는 목표 설계를 정의하며 현재 runtime 구현이 완료되었다는 의미가 아니다.

---

## 2. 핵심 아키텍처 결정

NU54DK Arduino Core는 Sketch를 LLEXT extension으로 적재하지 않는다. Sketch, Core, Variant, Zephyr kernel, driver 및 선택한 NCS subsystem을 하나의 build graph에서 컴파일하고 하나의 실행 이미지로 정적 링크한다.

~~~text
Sketch source
    + Arduino Core
    + NU54DK Variant
    + Zephyr kernel/drivers
    + NCS subsystem
            ↓
        zephyr.elf
        zephyr.hex
            ↓
    CMSIS-DAP/pyOCD 또는 J-Link
~~~

이 구조에는 다음 요소가 없다.

- Arduino LLEXT Loader
- Loader EDK
- Sketch용 동적 ELF relocation
- Loader export symbol table
- Loader와 Sketch 사이의 별도 ABI 계약
- Sketch 전용 runtime partition

SoC Boot ROM, 선택적인 MCUboot, sysbuild 보조 image 또는 디버그 프로브 firmware는 LLEXT Loader와 다른 계층이다. 향후 필요에 따라 추가할 수 있지만 v0 Runtime의 필수 요소는 아니다.

---

## 3. 단일 원본 원칙

Runtime 구성의 원본은 다음과 같이 나눈다.

| 정보 | 단일 원본 |
| --- | --- |
| 보드의 물리 장치와 pinctrl | `board_package/NU54DK_Zephyr_DTS` |
| kernel과 driver 선택 | application `prj.conf` 및 Kconfig |
| Sketch별 장치 추가·변경 | application overlay |
| Arduino 실행 규칙 | `cores/arduino/main.cpp`와 Runtime 내부 코드 |
| Arduino 논리 핀 순서 | `variants/nu54dk` |
| 빌드 orchestration | west-native 명령과 향후 Build Adapter |

Runtime 코드에 UART 번호, GPIO 번호, Flash 주소 또는 partition 크기를 다시 하드코딩하지 않는다.

---

## 4. 부팅과 실행 흐름

### 4.1 기본 부팅 흐름

~~~text
nRF54L15 reset
      ↓
SoC Boot ROM
      ↓
Zephyr architecture/startup
      ↓
C/C++ runtime 및 정적 객체 초기화
      ↓
Zephyr init level별 kernel/device 초기화
      ↓
Core가 제공하는 main()
      ↓
Arduino Runtime 상태 초기화
      ↓
initVariant()
      ↓
setup() 1회
      ↓
loop() 반복
~~~

Zephyr가 `main()`을 호출할 때 kernel scheduler와 정상적인 init level의 device 초기화는 이미 완료되어 있어야 한다. Core는 `__libc_init_array()`를 다시 호출하거나 SoC startup을 중복 실행하지 않는다.

### 4.2 `setup()`

`setup()`은 다음 계약을 가진다.

- Runtime lifetime 동안 한 번만 호출한다.
- Zephyr `main` thread 문맥에서 실행한다.
- 호출 전에 Variant descriptor와 Core 내부 상태가 사용할 수 있어야 한다.
- `setup()`이 반환하면 Runtime은 반복 단계로 진입한다.
- Arduino 표준 signature를 유지하므로 오류 값을 반환하지 않는다.

초기화 실패를 알릴 필요가 있는 subsystem은 자체 상태 API, log 또는 명시적 begin 결과를 사용한다. Core가 임의로 `setup()`을 재호출하지 않는다.

### 4.3 `loop()`

기본 반복 구조는 다음과 같다.

~~~cpp
for (;;) {
    loop();
    runtimePostLoop();
}
~~~

`runtimePostLoop()`는 향후 다음 기능을 선택적으로 수행할 수 있는 내부 hook다.

- `serialEventRun()` 호환 hook
- cooperative yield
- optional minimum sleep
- 지연된 Core 진단 처리

PoC에서는 Blink의 `loop()`가 `delay()`를 호출하므로 scheduler에 자연스럽게 실행 기회를 반환한다.

---

## 5. Thread 모델

### 5.1 PoC 기본 결정

west-native PoC는 별도의 Arduino thread를 생성하지 않고 Zephyr가 제공하는 `main` thread에서 `setup()`과 `loop()`를 실행한다. v1에서도 이 모델을 유지할지는 loop 공정성, stack 및 priority 실측 후 결정한다.

선정 이유는 다음과 같다.

- 추가 stack과 thread object가 필요 없다.
- Zephyr 애플리케이션의 표준 진입점과 같다.
- debugger backtrace와 fault 위치가 단순하다.
- Full Zephyr 정적 링크 구조를 가장 적은 정책으로 검증할 수 있다.
- Sketch가 필요하면 표준 Zephyr API로 추가 thread를 만들 수 있다.

### 5.2 Stack과 priority

Runtime은 Zephyr 표준 설정을 사용한다.

| 항목 | 설정 |
| --- | --- |
| main stack | `CONFIG_MAIN_STACK_SIZE` |
| main priority | `CONFIG_MAIN_THREAD_PRIORITY` |
| scheduler | Zephyr kernel 설정 |
| system workqueue | Zephyr subsystem 설정 |

Core가 별도의 고정 숫자를 소스에 넣지 않는다. 첫 PoC는 작은 Blink에 필요한 값으로 시작하고, Serial·network·Bluetooth와 복잡한 C++ library를 추가하면서 stack watermark를 계측한다.

### 5.3 Background 실행

Arduino Runtime이 main thread에서 실행되어도 Zephyr의 다음 요소는 계속 존재한다.

- interrupt handler
- kernel timer
- system workqueue
- driver work item
- Bluetooth, radio 또는 network subsystem thread
- Sketch가 생성한 thread

다만 `loop()`가 영원히 block 또는 yield하지 않고 main thread보다 낮은 priority의 thread만 존재하면 해당 thread가 실행되지 못할 수 있다. Zephyr를 사용한다는 사실만으로 공정성이 자동 보장되는 것은 아니다.

### 5.4 Loop 공정성 정책

초기 설계는 다음과 같이 구분한다.

| 정책 | 상태 |
| --- | --- |
| `delay()`가 있는 loop | `k_msleep()`으로 main thread block |
| Sketch가 호출하는 `yield()` | `k_yield()`에 연결 |
| 매 loop 뒤의 강제 1 ms sleep | 기본 비활성 제안 |
| configurable minimum sleep | 도입 제안, 실측 후 기본값 확정 |

`k_yield()`는 같은 priority의 ready thread에 실행 기회를 주지만 더 낮은 priority의 thread까지 보장하지 않는다. 따라서 다음 실기 시험 전에 “yield를 넣었으니 안전하다”고 간주하지 않는다.

1. 빈 `loop()`를 최대 속도로 실행한다.
2. main보다 낮은 priority의 test worker를 생성한다.
3. system workqueue, timer 및 UART RX 진행 여부를 측정한다.
4. 필요하면 `CONFIG_NUCODE_ARDUINO_LOOP_MIN_SLEEP_MS`의 기본값 또는 main priority를 조정한다.

출시 기본값은 이 시험 결과를 기록한 후 확정한다. 이는 명시적인 결정 대기 항목이다.

---

## 6. 구성요소 책임

### 6.1 `cores/arduino/main.cpp`

책임:

- Zephyr 애플리케이션의 단일 `main()` 제공
- `initVariant()`, `setup()`, `loop()` 호출 순서 보장
- post-loop hook 실행
- Runtime의 최상위 비복구 오류 정책 적용

금지:

- SoC clock과 GPIO의 직접 초기화
- UART와 USB의 묵시적 초기화
- C++ constructor 수동 재호출
- Loader 또는 Sketch ELF 검색

### 6.2 Runtime 내부 상태

Core 내부 상태는 다음 범주만 유지한다.

- Runtime phase
- 마지막 Core 진단 코드
- pin mode와 output latch 같은 API 구현 상태
- 활성 peripheral wrapper의 lifecycle 상태

보드의 물리 설정을 상태로 복사해 두지 않는다.

### 6.3 `initVariant()`

`initVariant()`는 약한 기본 구현을 제공하고, NU54DK Variant가 필요할 때 재정의할 수 있다.

허용되는 동작:

- immutable descriptor의 일관성 확인
- board-specific 논리 객체 연결
- 필수 device readiness의 초기 진단

허용되지 않는 동작:

- Devicetree와 다른 pinctrl 강제 설정
- 사용자 동의 없는 peripheral 활성화
- 긴 blocking 작업
- `setup()` 대신 사용자 application을 초기화하는 동작

첫 PoC에서 별도 동작이 필요하지 않으면 빈 구현을 사용한다.

### 6.4 Sketch

Sketch는 다음을 소유한다.

- 사용자 application logic
- Sketch가 요청한 peripheral의 begin/end lifecycle
- 추가 Zephyr thread와 synchronization object
- project-specific `prj.conf`와 overlay

Sketch가 Zephyr API를 직접 포함하고 사용하는 것을 금지하지 않는다. 이것이 Loader 없는 Full Zephyr 방식을 선택한 이유 중 하나다.

---

## 7. 데이터와 호출 흐름

### 7.1 빌드 시

~~~text
Sketch .cpp 또는 전처리된 .ino
          +
Core sources
          +
Variant sources
          +
NU54DK BOARD_ROOT
          +
prj.conf / overlay
          ↓
Zephyr CMake + Kconfig + Devicetree
          ↓
단일 정적 ELF/HEX
~~~

### 7.2 실행 시

~~~text
main thread
   ├─ initVariant()
   ├─ setup()
   └─ loop()
        ├─ Arduino API
        │    └─ Zephyr driver/kernel API
        └─ 직접 Zephyr API 사용 가능

ISR / driver / workqueue
   └─ Zephyr scheduler와 동시 실행
~~~

Arduino API는 Zephyr를 감추기 위한 별도 운영체제가 아니다. Zephyr API 위에 Arduino 관례를 제공하는 compatibility layer다.

---

## 8. Thread와 ISR 문맥 규칙

| 기능 | Thread | ISR | 정책 |
| --- | --- | --- | --- |
| `setup()` | 허용 | 해당 없음 | main thread에서 1회 |
| `loop()` | 허용 | 해당 없음 | main thread에서 반복 |
| `delay()` | 허용 | 금지 | current thread를 sleep |
| `yield()` | 허용 | 금지 | scheduler yield |
| `millis()` | 허용 | 허용 목표 | lock 없는 uptime 조회 |
| `digitalWrite()` | 허용 | 사전 구성 pin에 한해 검증 후 허용 목표 | driver context 제약 준수 |
| `Serial.write()` | 허용 | 금지 | lock 또는 buffering 가능 |
| interrupt callback | 해당 없음 | 실행 | ISR-safe API만 호출 |

공통 규칙은 다음과 같다.

- ISR에서 heap allocation, mutex, sleep 및 일반 logging을 호출하지 않는다.
- ISR callback은 필요한 데이터를 atomic 또는 queue에 기록하고 thread에서 처리한다.
- Runtime 내부 API는 `k_is_in_isr()`로 문맥을 구분할 수 있지만, 잘못된 호출을 정상 동작으로 가장하지 않는다.
- thread-safe와 ISR-safe를 같은 의미로 사용하지 않는다.

---

## 9. C++ Runtime 정책

### 9.1 언어 버전

최초 구현안은 `CONFIG_CPP=y`와 C++17을 기준으로 한다. 최종 Arduino library 호환성 시험에서 필요한 경우 표준 버전을 조정한다.

### 9.2 Exception과 RTTI

초기 기본값은 다음과 같이 제안한다.

- C++ exception 비활성
- RTTI 비활성
- heap 사용 최소화
- static initialization은 허용하되 device 사용은 `main()` 이후로 제한

Exception 또는 full C++ standard library가 필요한 Sketch는 project `prj.conf`에서 명시적으로 활성화할 수 있어야 한다. Core가 이를 구조적으로 금지하지는 않지만 Flash/RAM 비용은 빌드 report로 확인한다.

### 9.3 정적 객체

정적 객체 constructor에서 Zephyr device가 완전히 준비되었다고 가정하지 않는다. `Serial`, `Wire`, `SPI` 같은 전역 객체는 constructor에서 hardware를 활성화하지 않고, `begin()` 또는 Runtime 초기화 이후에 실제 device를 사용한다.

---

## 10. 오류 정책

### 10.1 오류 등급

| 등급 | 예 | 처리 |
| --- | --- | --- |
| Build invariant | 필수 alias 없음, 지원하지 않는 board | 빌드 실패 |
| Startup fatal | Core 필수 상태 손상 | 명확한 log 후 `k_panic()` 검토 |
| Recoverable init | UART device 준비 실패 | 객체를 not-ready로 두고 Sketch가 확인 |
| API misuse | ISR에서 `delay()` 호출 | 동작 거부, 개발 진단 기록 |
| Driver I/O | UART/SPI/I2C 오류 | API별 반환값 또는 상태에 전달 |

`k_panic()`은 메모리 손상처럼 계속 실행할 수 없는 조건에만 사용한다. 사용자가 유효하지 않은 pin 하나를 전달했다고 전체 보드를 panic시키는 정책은 기본값으로 사용하지 않는다.

### 10.2 Arduino `void` API

Arduino API 중 반환값이 없는 함수는 다음 원칙을 따른다.

- 안전하지 않은 동작은 수행하지 않는다.
- 개발 build에서는 진단 log 또는 assertion을 선택적으로 제공한다.
- release build에서도 메모리 범위 검사를 제거하지 않는다.
- Core extension으로 마지막 오류를 조회하는 방안은 별도 API 문서에서 결정한다.

### 10.3 Fault

Zephyr fatal error handler와 coredump/debugger 정보를 우선 사용한다. Core가 Fault를 삼키거나 자동 reset loop를 만드는 기능은 v0 범위에 넣지 않는다.

---

## 11. 설정 항목

다음은 구현 예정안이다. 아직 존재하는 설정으로 간주하지 않는다.

| 설정안 | 기본값안 | 설명 |
| --- | ---: | --- |
| `CONFIG_NUCODE_ARDUINO_CORE` | `y` | Runtime과 Core 편입 |
| `CONFIG_NUCODE_ARDUINO_RUNTIME_LOG_LEVEL` | `WRN` | Runtime 진단 수준 |
| `CONFIG_NUCODE_ARDUINO_LOOP_MIN_SLEEP_MS` | 결정 대기 | loop 뒤 최소 sleep |
| `CONFIG_NUCODE_ARDUINO_SERIAL_EVENT` | `n` | post-loop serial event hook |
| `CONFIG_MAIN_STACK_SIZE` | PoC 측정 후 확정 | setup/loop stack |
| `CONFIG_MAIN_THREAD_PRIORITY` | Zephyr 기본에서 시작 | Arduino 실행 priority |
| `CONFIG_CPP` | `y` | C++ application 지원 |
| `CONFIG_STD_CPP17` | `y` 제안 | 초기 언어 기준 |

Sketch별 설정이 가능한 Full Zephyr 구조이므로 Core가 고정 profile만 허용해서는 안 된다.

---

## 12. 완료 기준

Runtime v0 완료 조건은 다음과 같다.

- [ ] `setup()`이 리셋당 정확히 한 번 호출된다.
- [ ] `setup()` 반환 후 `loop()`가 반복된다.
- [ ] Sketch, Core, Zephyr가 하나의 `zephyr.elf`에 정적 링크된다.
- [ ] Loader, LLEXT, EDK 또는 동적 Sketch partition이 필요하지 않다.
- [ ] C++ 정적 초기화가 한 번만 수행된다.
- [ ] `delay()`가 main thread만 block하고 kernel timer와 workqueue는 계속 진행한다.
- [ ] 빈 loop 공정성 시험 결과와 선택한 기본 정책이 기록된다.
- [ ] stack watermark를 Blink, Serial 및 복합 Sketch에서 측정한다.
- [ ] fault backtrace에서 Sketch와 Core symbol을 확인할 수 있다.
- [ ] 리셋 후 별도 Loader command 없이 Sketch가 즉시 시작한다.

---

## 13. 테스트 계획

### 13.1 Build test

- C Sketch가 아닌 C++ Sketch link
- `setup()` 누락 시 명확한 link error
- `loop()` 누락 시 명확한 link error
- Core module을 빼면 의도한 configuration error
- `--no-sysbuild` 단일 image와 필요 시 sysbuild image 비교

### 13.2 Runtime 순서 test

다음 event를 RAM buffer 또는 UART에 기록한다.

~~~text
static constructor
initVariant
setup begin
setup end
loop 1
loop 2
~~~

순서와 호출 횟수를 reset마다 확인한다.

### 13.3 Scheduler test

- Blink `delay()` 중 worker thread 진행
- 빈 loop 중 동일 priority worker 진행
- 빈 loop 중 낮은 priority worker 진행
- system workqueue 처리량
- timer callback jitter
- 선택적인 minimum sleep별 loop rate와 background latency 비교

### 13.4 Fault test

- stack overflow 보호 동작
- null access fault의 symbolized backtrace
- ISR에서 금지 API 호출 진단
- device not-ready의 recoverable 처리

### 13.5 Incremental build test

- 변경 없음: Ninja `no work to do`
- Sketch만 변경: Core와 Zephyr의 불필요한 전체 재컴파일 없음
- `prj.conf` 변경: 필요한 build graph만 재구성
- board package commit 변경: pristine이 필요한 조건을 Build Adapter가 감지

---

## 14. 범위 제외

Runtime v0에서 다음 항목은 제외한다.

- LLEXT Sketch Loader
- 실행 중 Sketch 교체
- Loader EDK와 export ABI
- MCUboot, DFU 및 FOTA 정책
- crash 후 자동 rollback
- USB CDC, HID 및 MSC
- multicore application orchestration
- Arduino scheduler를 Zephyr 위에 별도 구현하는 기능
- 모든 Arduino library의 호환성 보장

nRF54L15 target에는 native USB peripheral이 없다. 온보드 CMSIS-DAP의 USB 연결은 debug/flash 및 UART bridge 역할이며 target Runtime의 USB device subsystem이 아니다.

---

## 15. 결정 대기 목록

| 항목 | 결정 시점 | 필요한 근거 |
| --- | --- | --- |
| main thread 유지 또는 전용 Arduino thread 전환 | scheduler·stack HIL 후 | starvation, 격리 효과, 추가 RAM |
| loop 최소 sleep 기본값 | scheduler HIL 후 | worker latency, loop rate, power |
| main thread priority | 복합 subsystem 시험 후 | Bluetooth/UART/workqueue 공존 |
| 기본 stack 크기 | API 단계별 watermark 후 | 최대 관측값과 안전 여유 |
| `serialEventRun()` 기본 활성화 | Serial 구현 후 | Arduino library 호환성 및 비용 |
| exception/RTTI 공개 menu | library 호환 시험 후 | Flash/RAM 및 실제 사용 사례 |

---

## 16. 핵심 결정 요약

~~~text
Zephyr가 운영체제와 device lifecycle을 소유한다.
Core가 Arduino 실행 규칙을 소유한다.
Sketch는 main thread에서 setup()과 loop()로 실행된다.
모든 코드는 하나의 Full Zephyr image로 정적 링크된다.
~~~

Runtime은 Zephyr를 감추거나 대체하지 않는다. Arduino API와 Sketch 실행 관례를 Zephyr application model에 연결하는 얇고 검증 가능한 계층으로 유지한다.
