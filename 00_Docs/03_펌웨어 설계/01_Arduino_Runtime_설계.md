# NU54DK Arduino Runtime 설계

| 항목 | 내용 |
| --- | --- |
| 문서 ID | FW-RUNTIME-001 |
| 문서 개정 | 4.0 |
| 문서 상태 | `v0.3.0` 정식 계약 |
| 최종 갱신일 | 2026-09-03 |
| 실행 방식 | Loader 없는 Native Full Zephyr 정적 firmware |
| 기준 | NCS v3.4.0 / Zephyr 4.4.0 |

## 1. 목적

이 문서는 Arduino Sketch의 `setup()`과 `loop()`가 Zephyr application 안에서 실행되는 현재
수명주기, thread 문맥과 오류 경계를 정의한다. 과거 milestone별 측정값과 실행 로그는
`04_검증 기록`에 보관하고 여기서는 제품 계약만 설명한다.

## 2. 아키텍처

Sketch, Arduino Core, NU54DK Variant, Zephyr kernel/driver와 선택한 NCS subsystem은 하나의
build graph에서 하나의 실행 image로 정적 링크된다.

```text
Sketch + Core + Variant + Zephyr/NCS
                 ↓
       zephyr.elf / zephyr.hex
                 ↓
       CMSIS-DAP/pyOCD 또는 J-Link
```

다음 요소는 사용하지 않는다.

- Arduino LLEXT Loader와 EDK
- Sketch용 동적 ELF relocation·export symbol 계약
- Loader와 Sketch 사이의 별도 ABI
- Sketch 전용 runtime partition

SoC Boot ROM, 선택적인 bootloader, sysbuild 보조 image와 probe firmware는 LLEXT Loader와 다른
계층이며 이 계약을 바꾸지 않는다.

## 3. 단일 원본

| 정보 | 단일 원본 |
| --- | --- |
| 물리 장치, pinctrl, memory, runner | `board_package/NU54DK_Zephyr_DTS` |
| Arduino 수명주기 | `cores/arduino/main.cpp` |
| post-loop scheduler 정책 | `cores/arduino/internal/runtime_scheduler.cpp` |
| 논리 핀 | `variants/nu54dk` |
| 일반 사용자 구성 | `variants/nu54dk/profiles/{standard,ble}`와 library feature manifest |
| expert 구성 | Sketch의 `prj.conf`, `app.overlay`, Zephyr/NCS 공개 API |

Runtime에 UART/GPIO 번호, Flash 주소와 partition 크기를 다시 하드코딩하지 않는다.

## 4. 부팅과 Sketch 수명주기

```text
nRF54L15 reset
  → Zephyr startup·kernel/device init
  → C/C++ 정적 객체 초기화
  → Core main()
  → init()
  → initVariant()
  → setup() 한 번
  → loop()
  → serialEventRun()이 있으면 호출
  → runtimePostLoop()
  → loop() 반복
```

Zephyr가 `main()`을 호출할 때 정상 init level의 kernel/device 초기화는 끝나 있다. Core는 C++
constructor나 SoC startup을 다시 실행하지 않는다.

### 4.1 `init()`과 `initVariant()`

Core는 두 함수를 weak no-op으로 제공한다. Board/Variant가 필요할 때 strong implementation으로
재정의할 수 있지만 다음 동작은 허용하지 않는다.

- Devicetree와 다른 pinctrl 강제 설정
- 사용자 선택 없이 peripheral 활성화
- 긴 blocking 초기화
- Sketch application logic 대행

현재 NU54DK Variant는 별도 `initVariant()` 구현을 요구하지 않는다.

### 4.2 `setup()`과 `loop()`

- `setup()`은 Zephyr main thread에서 정확히 한 번 실행된다.
- `setup()` 실패를 Core가 재호출로 복구하지 않는다. 실패 가능한 subsystem은 `begin()` 결과와
  자체 오류 API를 사용한다.
- `loop()`는 반환할 때마다 반복된다.
- ArduinoCore-API의 `serialEventRun()` symbol이 있으면 각 `loop()` 뒤 한 번 호출된다.
- `serialEventRun()` 뒤 `runtimePostLoop()`가 scheduler 정책을 적용한다.

## 5. Thread와 scheduler

Runtime은 별도 Arduino thread를 만들지 않고 Zephyr main thread를 사용한다.

| 항목 | 소유자 |
| --- | --- |
| main stack | `CONFIG_MAIN_STACK_SIZE` |
| main priority | `CONFIG_MAIN_THREAD_PRIORITY` |
| scheduler/workqueue | Zephyr kernel과 subsystem |
| 추가 thread | Sketch 또는 선택한 Zephyr/NCS subsystem |

Core는 stack/priority 숫자를 source에 고정하지 않는다. `loop()`가 block 또는 sleep 없이 계속
실행되면 낮은 priority thread와 idle 진행을 막을 수 있으므로 post-loop 정책을 제공한다.

| 정책 | Kconfig | 의미 |
| --- | --- | --- |
| 기본 | `CONFIG_NUCODE_ARDUINO_LOOP_SLEEP_ONE_TICK` | `k_sleep(K_TICKS(1))` |
| 선택 | `CONFIG_NUCODE_ARDUINO_LOOP_YIELD` | `k_yield()` |
| 선택 | `CONFIG_NUCODE_ARDUINO_LOOP_NONE` | Core scheduler 개입 없음 |

한 kernel tick을 1 ms로 가정하지 않는다. `YIELD`와 `NONE`을 선택한 application은 scheduler
공정성, idle과 power 정책을 직접 검증해야 한다.

## 6. Background 실행

Arduino Runtime과 함께 다음 Zephyr 실행 주체가 공존한다.

- interrupt handler와 kernel timer
- system workqueue와 driver work item
- Bluetooth, radio, network subsystem thread
- Sketch가 만든 thread·queue·timer

Arduino callback이 반드시 Sketch thread에서 실행되는 것은 아니다. GPIO interrupt callback은
ISR, BoardSystem alarm callback은 system workqueue, BLE NUS 사용자 event callback은
`BLESerial.poll()`을 호출한 Arduino 문맥에서 실행된다. 각 API 문서의 문맥 계약을 따른다.

## 7. Thread/ISR 호출 규칙

| API/영역 | Thread | ISR |
| --- | --- | --- |
| `setup()`, `loop()` | main thread | 해당 없음 |
| `millis()`, `micros()` | 허용 | 허용 |
| `delay()`, `yield()` | 허용 | no-op |
| `delayMicroseconds()` | 허용 | no-op |
| digital GPIO | 허용 | no-op 또는 안전한 실패 |
| `Serial`, `Wire`, `SPI`, ADC/PWM lifecycle·I/O | 허용 | 거부 |
| GPIO interrupt callback | 해당 없음 | ISR에서 실행 |
| BLE event callback | `poll()` 호출 문맥 | 직접 실행하지 않음 |

ISR에서는 heap, mutex, sleep, blocking driver API와 문자열 logging을 호출하지 않는다. 필요한
데이터만 atomic/queue에 기록하고 thread나 workqueue에서 처리한다.

## 8. C++ 정책

- Core는 C++17 이상을 요구한다.
- 기본 `standard`와 `ble` profile은 exception과 RTTI를 활성화하지 않는다.
- 정적 객체 constructor에서 hardware를 활성화하지 않는다. `Serial`, `Wire`, `SPI`와 library
  전역 객체는 `begin()` 또는 Runtime 시작 뒤 장치를 사용한다.
- `String`은 bounded libc heap을 사용하므로 allocation 실패 가능성을 보존한다.
- Exception/RTTI가 필요한 expert build는 별도 stack·heap·runtime 검증 없이는 제품 지원으로
  간주하지 않는다.

## 9. 오류와 공개 진단

Build invariant는 compile/configure 단계에서 실패시킨다. Runtime의 잘못된 인수나 금지 문맥은
가능하면 panic 대신 no-op, 실패 반환값과 backend 오류 상태로 처리한다. `k_panic()`은 계속
실행할 수 없는 Core invariant 손상에만 사용한다.

`<nucode/Diagnostics.h>`는 현재 다음 subsystem을 공개한다.

| Subsystem | `lastDiagnostic()` 동작 |
| --- | --- |
| `core` | 별도 오류 저장소가 없어 `none` |
| `time` | 별도 오류 저장소가 없어 `unsupported` |
| `gpio`, `serial`, `wire`, `spi`, `analog` | 활성 backend의 마지막 atomic 오류와 driver errno를 projection |

`formatDiagnostic()`은 할당 없이
`NU54:<subsystem>:<code>:driver=<signed>:detail=<unsigned>` 형식을 만든다. 조회는 오류 상태를
지우지 않으며 이 값은 오류 이력이나 event queue가 아니다.

## 10. 주요 Kconfig

| 설정 | 현재 역할 |
| --- | --- |
| `CONFIG_NUCODE_ARDUINO_CORE` | Core module 활성화 |
| `CONFIG_NUCODE_ARDUINO_RUNTIME` | Sketch 수명주기 |
| `CONFIG_NUCODE_ARDUINO_API` | 공통 ArduinoCore-API |
| `CONFIG_NUCODE_ARDUINO_GPIO` | sparse Variant GPIO |
| `CONFIG_NUCODE_ARDUINO_INTERRUPTS` | raw edge interrupt |
| `CONFIG_NUCODE_ARDUINO_TIME` | 시간 API |
| `CONFIG_NUCODE_ARDUINO_SERIAL` | chosen console Serial |
| loop choice 3종 | post-loop scheduler 정책 |

Wire, SPI, ADC, PWM, Board/System과 BLE는 선택 profile 및 library feature manifest가 추가한다.
일반 사용자는 raw Kconfig를 직접 편집하지 않고 Arduino IDE의 검증된 feature set을 사용한다.

## 11. 검증과 변경 조건

- [Runtime·module 기준선](<../04_검증 기록/02_M2_Zephyr_Module과_Runtime_기준선.md>)
- [GPIO·시간·Scheduler 기준선](<../04_검증 기록/03_M3_GPIO_시간과_Scheduler_기준선.md>)
- [M6 기본 Arduino API·Serial·interrupt 기준선](<../04_검증 기록/06_M6_기본_Arduino_API_Serial과_인터럽트_기준선.md>)
- [M14 Core API와 Variant 기준선](<../04_검증 기록/16_M14_Core_API와_Variant_기준선.md>)
- [M16 BLE NUS 기준선](<../04_검증 기록/18_M16_BLE_NUS_기준선.md>)

Thread 모델, 기본 post-loop choice, constructor 순서 또는 callback 문맥을 바꾸면 host 계약,
NU54DK target build와 관련 HIL을 다시 통과해야 한다. 설계 문서에는 실행별 exact 수치와 로그를
중복 보관하지 않는다.

## 12. 범위 밖

- 별도 Arduino 전용 thread와 고정 stack/priority
- runtime에서 Sketch ELF를 교체·unload하는 기능
- Core가 모든 Zephyr subsystem lifecycle을 대신 관리하는 기능
- 자동 fault 복구·reset loop와 일반 coredump 저장소
- ISR에서 일반 Arduino I/O를 허용하는 호환층
