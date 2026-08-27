# NU54DK Arduino Runtime 설계

| 항목 | 내용 |
| --- | --- |
| 문서 상태 | 설계·구현 동기화 — M6 완료 기준 |
| 작성자 | Quantum / NUCODE |
| 실행 방식 | Loader 없는 Native Full Zephyr 정적 펌웨어 |
| 기준 SDK | nRF Connect SDK v3.4.0 |
| 기준 RTOS | Zephyr v4.4.0 |
| 기준 타깃 | `nrf54l15dk/nrf54l15/cpuapp/nu54dk` |
| 기본 실행 문맥 | Zephyr `main` thread, loop 후 기본 한 kernel tick sleep |

---

## 1. 목적

이 문서는 Arduino Sketch의 `setup()`과 `loop()`를 NCS/Zephyr 애플리케이션 안에서 실행하는 runtime 구조를 정의한다. 다음 질문에 대한 기준을 제공한다.

- 리셋 후 어떤 코드가 어떤 순서로 실행되는가?
- Arduino Sketch와 Zephyr kernel은 어떤 관계인가?
- 누가 thread, stack, device 초기화 및 lifecycle을 소유하는가?
- `loop()`가 계속 실행되는 동안 Zephyr background 작업은 어떻게 동작하는가?
- ISR callback과 일반 Arduino API 사이의 경계는 무엇인가?
- 초기화 또는 실행 오류는 어떻게 처리하는가?

현재 구현은 Zephyr `main` thread 기반 runtime, 선택 가능한 post-loop 정책과 M6의
`serialEventRun()` hook까지 포함한다. 이 문서에서 “현재 구현”이라고 명시한 내용은
M3~M6 source와 실측에 대응한다. 복합 subsystem stack 정책과 전용 Arduino thread 같은
항목은 향후 목표로 구분한다.

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
init()
      ↓
initVariant()
      ↓
setup() 1회
      ↓
loop()
      ↓
serialEventRun()이 존재하면 호출
      ↓
post-loop 정책 뒤 loop() 반복
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
    if (serialEventRun exists) {
        serialEventRun();
    }
    runtimePostLoop();
}
~~~

현재 `runtimePostLoop()`는 Kconfig choice에 따라 다음 중 하나를 수행한다.

- 기본값: `k_sleep(K_TICKS(1))`
- 선택값: `k_yield()`
- 선택값: Core scheduler 개입 없음

ArduinoCore-API의 weak `serialEventRun()` symbol이 실제로 존재하면 각 `loop()` 직후,
`runtimePostLoop()` 전에 한 번 호출한다. M6 runtime smoke의 ELF에서 hook과 probe가 모두
strong `T` symbol임을 확인했고, DAPLink sequence 10/COM10 HIL에서 loop 1·2·3 뒤
`serial_event=3 PASS`를 회수했다. Blink는 Sketch 내부의 `delay()`로도 실행 기회를
반환하지만, 빠르게 반환하는 일반 `loop()`의 공정성은 post-loop 정책이 별도로 책임진다.

---

## 5. Thread 모델

### 5.1 PoC 기본 결정

M3 west-native 구현은 별도의 Arduino thread를 생성하지 않고 Zephyr가 제공하는 `main`
thread에서 `setup()`과 `loop()`를 실행한다. M3 공정성 실측 결과에 따라 현재는 이 모델과
기본 one-tick 정책을 유지한다. Serial, Bluetooth 또는 복합 Sketch의 stack·priority
실측에서 격리가 필요하다고 확인되면 전용 Arduino thread를 다시 검토한다.

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

Core가 별도의 고정 숫자를 소스에 넣지 않는다. M3 Blink와 `runtime_timing`은 각 sample의
`prj.conf`가 정한 값을 사용했다. Serial·network·Bluetooth와 복잡한 C++ library를
추가한 stack watermark는 아직 측정하지 않았다.

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

현재 구현은 다음 정책을 제공한다.

| 정책 | Kconfig | 현재 상태 |
| --- | --- | --- |
| 한 kernel tick sleep | `CONFIG_NUCODE_ARDUINO_LOOP_SLEEP_ONE_TICK` | 기본값 |
| scheduler yield | `CONFIG_NUCODE_ARDUINO_LOOP_YIELD` | 선택 가능 |
| Core 개입 없음 | `CONFIG_NUCODE_ARDUINO_LOOP_NONE` | 선택 가능 |
| Sketch의 `delay()` | API 호출 시 `k_msleep()` | 현재 main thread block |
| Sketch의 `yield()` | API 호출 시 `k_yield()` | 같은 priority 중심 |

one-tick은 1 ms 고정 지연이 아니다. M3 기준
`CONFIG_SYS_CLOCK_TICKS_PER_SEC=31250`이므로 명목상 한 tick은 약 32 us이며, 실제 한 번의
loop 주기는 scheduler와 다른 ready thread 실행 시간까지 포함한다.

`runtime_timing` sample은 Core post-loop 개입을 `NONE`으로 둔 뒤 400 ms씩 네 정책을 직접
적용해 다음 결과를 얻었다. `하위순위`는 main보다 수치상 priority가 1 큰 worker다.

| 단계 | loop 호출 | 동순위 worker | 하위순위 worker | timer | workqueue | idle 비율 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| spin | 177,986 | 0 | 0 | 390 | 40 | 0% |
| `yield()` | 66,937 | 371 | 0 | 391 | 40 | 0% |
| 한 tick sleep | 4,048 | 368 | 368 | 390 | 40 | 85.53% |
| `delay(1)` | 368 | 367 | 367 | 391 | 39 | 96.71% |

최종 trace는 `PASS`, `failure=0`이었다. spin에서도 interrupt와 system workqueue는
진행했지만 동순위·하위순위 worker와 idle은 진행하지 않았다. `yield()`는
동순위 worker를 진행시켰으나 하위순위와 idle을 보장하지 않았다. 한 tick sleep과
`delay(1)`은 하위순위와 idle을 모두 진행시켰다.

따라서 M3 기본 정책은 한 kernel tick sleep으로 확정한다. 최대 loop rate가 필요한
application은 `YIELD` 또는 `NONE`을 명시적으로 선택하고 Zephyr 공존 책임을 함께 진다.

---

## 6. 구성요소 책임

### 6.1 `cores/arduino/main.cpp`

현재 책임:

- Zephyr 애플리케이션의 단일 `main()` 제공
- `initVariant()`, `setup()`, `loop()` 호출 순서 보장
- post-loop hook 실행

최상위 비복구 오류를 분류해 별도 Core 진단으로 남기는 계층은 아직 없다. M3 sample의
실패 판정은 sample 자체의 trace와 LED 표시를 사용하며, 해당하는 경우에만 `k_panic()`으로
정지한다.

금지:

- SoC clock과 GPIO의 직접 초기화
- UART와 USB의 묵시적 초기화
- C++ constructor 수동 재호출
- Loader 또는 Sketch ELF 검색

### 6.2 Runtime 내부 상태

M3 runtime entry 자체는 phase나 lifecycle 상태를 저장하지 않는다. 현재 Core의 가변
상태는 digital GPIO 구현이 보유한 다음 항목뿐이다.

- 논리 핀별 현재 mode와 output latch
- 마지막 비공개 GPIO 오류와 driver 오류

Runtime phase, 공통 Core 진단 코드와 peripheral wrapper lifecycle은 향후 subsystem이
필요로 할 때 추가할 설계 범위다. 추가하더라도 보드의 물리 설정을 가변 상태에 복사해
별도 원본으로 만들지 않는다.

### 6.3 `initVariant()`

현재 `initVariant()`는 Core가 제공하는 weak no-op이며 `main()`이 `setup()`보다 먼저 한 번
호출한다. NU54DK Variant가 초기화를 요구하게 되면 strong 구현으로 재정의할 수 있다.

허용되는 동작:

- immutable descriptor의 일관성 확인
- board-specific 논리 객체 연결
- 필수 device readiness의 초기 진단

허용되지 않는 동작:

- Devicetree와 다른 pinctrl 강제 설정
- 사용자 동의 없는 peripheral 활성화
- 긴 blocking 작업
- `setup()` 대신 사용자 application을 초기화하는 동작

M3 NU54DK Variant는 별도 초기화가 필요하지 않아 현재 weak no-op을 그대로 사용한다.

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
| `delay()` | 허용 | 금지, no-op | `k_can_yield()`가 허용할 때 current thread를 sleep |
| `yield()` | 허용 | 금지, no-op | `k_can_yield()`가 허용할 때 scheduler yield |
| `millis()` | 허용 | 허용 | Zephyr uptime 조회, timer ISR 실기 호출 확인 |
| `micros()` | 허용 | 허용 | GRTC cycle 조회, timer ISR 실기 호출 확인 |
| `delayMicroseconds()` | 허용 | 공개 계약상 금지, no-op | thread에서 busy wait |
| `digitalWrite()` | 허용 | 금지, no-op | M3 GPIO 공개 API는 thread 전용 |
| `Serial.write()` | 허용 | 금지 | polling TX와 Core mutex; ISR 호출은 오류와 0 반환 |
| interrupt callback | 해당 없음 | 실행 | ISR-safe API만 호출 |

공통 규칙은 다음과 같다.

- ISR에서 heap allocation, mutex, sleep 및 일반 logging을 호출하지 않는다.
- ISR callback은 필요한 데이터를 atomic 또는 queue에 기록하고 thread에서 처리한다.
- Runtime 내부 API는 `k_can_yield()`와 `k_is_in_isr()`로 문맥을 구분한다.
- M3 시간 진단 계층은 아직 없으므로 금지 문맥의 `delay()`, `yield()`와
  `delayMicroseconds()`는 안전하게 no-op하고 오류 상태를 기록하지 않는다.
- thread-safe와 ISR-safe를 같은 의미로 사용하지 않는다.

---

## 9. C++ Runtime 정책

### 9.1 언어 버전

M3 기준은 `CONFIG_CPP=y`와 C++17이다. Core Kconfig는 C++17 이상을 허용하며 M2에서
C++20 clean build도 통과했다. 최종 Arduino library 호환성 시험에서 기본 표준 변경이
필요한지는 별도로 판단한다.

### 9.2 Exception과 RTTI

현재 기본 검증값은 다음과 같다.

- C++ exception 비활성
- RTTI 비활성
- ArduinoCore-API `String`용 common libc malloc arena 기본 8192 byte
- static initialization은 허용하되 device 사용은 `main()` 이후로 제한

Exception 또는 full C++ standard library가 필요한 Sketch는 project `prj.conf`에서
명시적으로 활성화할 수 있다. M2에서 full libstdc++ + exception + RTTI clean link를
통과했으며, Flash/RAM 비용은 각 빌드 report로 확인한다.

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
| API misuse | ISR에서 `delay()` 호출 | M3는 안전한 no-op, 진단 기록은 미구현 |
| Driver I/O | UART/SPI/I2C 오류 | API별 반환값 또는 상태에 전달 |

`k_panic()`은 메모리 손상처럼 계속 실행할 수 없는 조건에만 사용한다. 사용자가 유효하지 않은 pin 하나를 전달했다고 전체 보드를 panic시키는 정책은 기본값으로 사용하지 않는다.

### 10.2 Arduino `void` API

Arduino API 중 반환값이 없는 함수는 다음 원칙을 따른다.

- 안전하지 않은 동작은 수행하지 않는다.
- GPIO는 비공개 atomic 오류 상태를 제공하지만 Runtime/time용 log와 assertion은 아직 없다.
- release build에서도 메모리 범위 검사를 제거하지 않는다.
- Core extension으로 마지막 오류를 조회하는 방안은 별도 API 문서에서 결정한다.

### 10.3 Fault

Zephyr fatal error handler와 coredump/debugger 정보를 우선 사용한다. Core가 Fault를 삼키거나 자동 reset loop를 만드는 기능은 v0 범위에 넣지 않는다.

---

## 11. 설정 항목

현재 존재하는 설정은 다음과 같다.

| 설정 | 기본값/소유자 | 설명 |
| --- | --- | --- |
| `CONFIG_NUCODE_ARDUINO_CORE` | application이 활성화 | Runtime과 Core 편입 |
| `CONFIG_NUCODE_ARDUINO_RUNTIME` | 기본 `y` | `init()`/`initVariant()`/`setup()`/`loop()`와 `serialEventRun()` lifecycle |
| `CONFIG_NUCODE_ARDUINO_API` | 기본 `y` | `Common`, `String`, `Print`, `Stream`; common libc malloc과 float printf 선택 |
| `CONFIG_NUCODE_ARDUINO_GPIO` | 기본 `y` | Variant/DTS 기반 digital GPIO |
| `CONFIG_NUCODE_ARDUINO_INTERRUPTS` | 기본 `y` | raw edge GPIO ISR callback |
| `CONFIG_NUCODE_ARDUINO_TIME` | 기본 `y` | Arduino 시간 API |
| `CONFIG_NUCODE_ARDUINO_SERIAL` | 기본 `y` | chosen console UART의 non-owning Serial |
| `CONFIG_NUCODE_ARDUINO_SERIAL_RX_BUFFER_SIZE` | 기본 `128` | drop-newest 고정 RX queue 크기 |
| `CONFIG_COMMON_LIBC_MALLOC_ARENA_SIZE` | Core API 기본 `8192` | `String`용 bounded heap |
| `CONFIG_NUCODE_ARDUINO_LOOP_SLEEP_ONE_TICK` | Core 기본값 | loop 뒤 한 kernel tick sleep |
| `CONFIG_NUCODE_ARDUINO_LOOP_YIELD` | application 선택 | loop 뒤 scheduler yield |
| `CONFIG_NUCODE_ARDUINO_LOOP_NONE` | application 선택 | loop 뒤 Core scheduler 개입 없음 |
| `CONFIG_MAIN_STACK_SIZE` | application 소유 | setup/loop stack |
| `CONFIG_MAIN_THREAD_PRIORITY` | Zephyr/application 소유 | Arduino 실행 priority |
| `CONFIG_CPP` | application이 활성화 | C++ application 지원 |
| C++ 표준 choice | application 선택 | `CONFIG_STD_CPP_VERSION >= 201703`; C++17 이상 필요 |

`CONFIG_NUCODE_ARDUINO_RUNTIME_LOG_LEVEL`, loop millisecond 최소 sleep과
`serialEventRun()`을 강제로 끄는 별도 option은 현재 존재하지 않는 향후 검토 항목이다.

Sketch별 설정이 가능한 Full Zephyr 구조이므로 Core가 고정 profile만 허용해서는 안 된다.

---

## 12. 완료 기준

Runtime v0 완료 조건은 다음과 같다.

- [x] `setup()`이 리셋당 정확히 한 번 호출된다.
- [x] `setup()` 반환 후 `loop()`가 반복된다.
- [x] Sketch, Core, Zephyr가 하나의 `zephyr.elf`에 정적 링크된다.
- [x] Loader, LLEXT, EDK 또는 동적 Sketch partition이 필요하지 않다.
- [x] C++ 정적 초기화가 한 번만 수행된다.
- [x] `delay()`가 main thread만 block하고 kernel timer와 workqueue는 계속 진행한다.
- [x] 빈 loop 공정성 시험 결과와 기본 one-tick 정책이 기록된다.
- [x] `serialEventRun()`이 존재하면 각 `loop()` 직후 post-loop 정책보다 먼저 호출된다.
- [ ] stack watermark를 Blink, Serial 및 복합 Sketch에서 측정한다.
- [ ] fault backtrace에서 Sketch와 Core symbol을 확인할 수 있다.
- [x] 리셋 후 별도 Loader command 없이 Sketch가 즉시 시작한다.

위 완료 표시는 M2 west-native runtime, M3 NU54DK HIL/Twister와 M5·M6 Arduino CLI/target
회귀에 한정한다. `serialEventRun()`은 M6 runtime smoke target HIL까지 통과했다.
Bluetooth 복합 subsystem, stack watermark, fault backtrace와 저전력 profile은 완료
범위에 포함하지 않는다.

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
- `NONE`, `YIELD`, 한 tick sleep과 `delay(1)`의 loop rate·background 진행 비교

### 13.4 Fault test

- stack overflow 보호 동작
- null access fault의 symbolized backtrace
- ISR에서 금지 GPIO 호출의 private 오류와 시간 API no-op 동작
- device not-ready의 recoverable 처리

### 13.5 Incremental build test

- 변경 없음: provenance target 외 C/C++ compile·archive·link 0건
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
| 복합 subsystem에서 main thread 유지 여부 재검토 | Serial/Bluetooth·stack HIL 후 | 격리 효과, 추가 RAM, stack watermark |
| one-tick 기본값의 장기 유지 여부 | 복합 subsystem과 전력 HIL 후 | worker latency, loop rate, power |
| main thread priority | 복합 subsystem 시험 후 | Bluetooth/UART/workqueue 공존 |
| 기본 stack 크기 | API 단계별 watermark 후 | 최대 관측값과 안전 여유 |
| `serialEventRun()` 세부 최적화 | 기본 hook HIL 완료 후 | 다양한 Arduino library 호환성과 symbol/link 비용 |
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
