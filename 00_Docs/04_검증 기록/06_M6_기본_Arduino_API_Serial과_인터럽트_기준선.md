# M6 기본 Arduino API, Serial과 인터럽트 기준선

| 항목 | 값 |
| --- | --- |
| 상태 | **조건부 완료** |
| 검증일 | 2026-08-27 |
| 작성자 | Quantum / NUCODE |
| Core 기준 commit | `8cabfc3` + 본 M6 변경 |
| 보드 package | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` — 읽기 전용 |
| NCS / Zephyr | NCS v3.4.0 / Zephyr 4.4.0 |
| ArduinoCore-API | 1.5.2, `cd91833d90b4fe50e428021ba5051e2b7ceafc84` |
| Arduino FQBN | `nucode:zephyr:nu54dk` |
| 실제 Zephyr 보드 | `nrf54l15dk/nrf54l15/cpuapp/nu54dk` |
| 이미지 구조 | Loader/LLEXT 없는 Native Full Zephyr 정적 이미지 |

---

## 1. 목적과 판정

M6는 M5의 Arduino CLI Full Zephyr 빌드 경로 위에 ArduinoCore-API 공통 구현, 기본
`Serial`과 GPIO edge interrupt를 연결하고 NU54DK target에서 동작 의미를 검증하는
단계다. 이번 기준선에서 다음 항목을 완료했다.

- ArduinoCore-API의 `Common`, `String`, `Print`, `Stream` source를 생산 image에 연결했다.
- NU54DK console UART를 재구성하지 않는 non-owning `Serial`을 구현했다.
- `attachInterrupt()`, `attachInterruptParam()`과 `detachInterrupt()`를 raw electrical
  edge 기준으로 구현했다.
- west-native target build, Arduino CLI staged package, expected-failure 구성과 NU54DK
  target ztest를 통과했다.
- 온보드 DAPLink와 COM10을 이용해 실제 `Serial` READY/echo를 자동 검증했다.

M6의 상태는 **조건부 완료**다. 유일하게 남은 조건은 사용자가 자리를 비운 동안 자동화할
수 없었던 실제 P1.13 active-low 버튼의 GPIO ISR edge 확인이다. 버튼을 직접 눌렀다 놓으며
다음을 확인하면 조건이 해소된다.

- 버튼 누름: raw `FALLING`
- 버튼 해제: raw `RISING`
- 누름과 해제 모두: raw `CHANGE`

이 확인에는 로직 애널라이저나 오실로스코프가 필요하지 않다. `InterruptButton` 예제의
callback 횟수 또는 버튼에 따른 LED 반응을 사람이 관찰하면 된다. GPIO emulator를 사용한
target ztest에서는 세 edge와 detach 의미가 이미 통과했으며, 남은 조건은 실제 보드 배선과
GPIO driver 경로의 물리 확인만을 뜻한다.

---

## 2. 구현 경계

### 2.1 ArduinoCore-API 공통 구현

생산 Core는 고정된 ArduinoCore-API 1.5.2의 다음 source를 직접 링크한다.

- `Common.cpp`
- `String.cpp`
- `Print.cpp`
- `Stream.cpp`

NU54DK adapter는 upstream source를 수정하지 않고 필요한 libc 변환 함수를
`api_compat.cpp`에서 제공한다. `String`의 동적 할당은 Zephyr common libc의 경계가 있는
arena를 사용한다.

| 설정 | M6 기준값 | 의미 |
| --- | ---: | --- |
| `CONFIG_COMMON_LIBC_MALLOC` | `y` | Arduino `String` 동적 할당 제공 |
| `CONFIG_COMMON_LIBC_MALLOC_ARENA_SIZE` | `8192` | Core 기본 heap 상한 |
| `CONFIG_REQUIRES_FLOAT_PRINTF` | `y` | 문자열·출력의 부동소수 변환 지원 |

`String.reserve(1024)` 성공, arena보다 큰 `String.reserve(16384)` 실패와 기존 문자열 보존을
target ztest에서 확인했다. 이는 임의 크기의 heap을 보장한다는 의미가 아니다. Sketch가
더 큰 arena를 요구하면 최종 `prj.conf`가 비용과 한도를 명시적으로 소유한다.

### 2.2 Runtime 순서

Runtime은 C linkage의 `init()`, `initVariant()`, `setup()`과 `loop()` 계약을 사용한다.
각 `loop()`가 반환하면 선택적인 ArduinoCore-API `serialEventRun()`을 호출한 뒤 기존
`runtimePostLoop()` 정책을 적용한다.

~~~text
init()
  → initVariant()
  → setup()
  → loop()
  → serialEventRun()이 존재하면 호출
  → runtimePostLoop()
  → loop() 반복
~~~

강한 `serialEventRun()` 구현이 없는 Sketch에서는 weak symbol 검사를 통해 비용 없이
건너뛴다. Runtime smoke에서 `loop()` 뒤, post-loop 정책 전에 hook이 실행되는 순서를
검증했다. ELF symbol table에서 `arduino::serialEventRun()`과 시험 probe가 모두 strong
text symbol `T`로 존재하는 것도 확인했다.

### 2.3 기본 Serial

기본 `Serial`은 `zephyr,console` chosen node가 가리키는 UART20의 non-owning wrapper다.
현재 보드 package 기준 route는 TX P1.4, RX P1.5이며 115200 8N1이다. 물리 instance와 pin의
단일 원본은 계속 보드 Devicetree이고 Core source에 별도 복사하지 않는다.

| 항목 | M6 동작 |
| --- | --- |
| `begin(115200, SERIAL_8N1)` | `uart_config_get()`으로 실제 설정이 일치하는지만 확인하고 RX lifecycle 시작 |
| 다른 baud/config | UART를 재설정하지 않고 `unsupported_config`로 거부 |
| TX | thread 문맥의 `uart_poll_out()`과 Core TX mutex |
| RX | UART IRQ가 고정 `k_msgq`에 byte 저장 |
| RX 기본 크기 | 128 byte |
| RX overflow | 기존 byte를 보존하고 새 byte를 버리는 drop-newest, drop counter 증가 |
| `flush()` | Core polling TX 호출이 끝난 상태를 확인; RX를 버리지 않음 |
| `end()` | Core RX IRQ와 queue만 해제하고 Zephyr UART device·pinctrl·baud는 유지 |
| ISR에서 public Serial API | 거부하고 `invalid_context` 진단 |

동일 UART callback을 소비하는 Zephyr shell RX, console input, UART mcumgr, asynchronous UART
log와 tracing backend는 함께 활성화하지 않는다. 충돌 설정은 configure/build 단계에서
명시적으로 실패한다. TX는 Core 내부 호출끼리 직렬화하지만 Zephyr console/log와 공유하는
물리 선 전체의 message 원자성까지 보장하지 않는다.

### 2.4 GPIO interrupt

Variant는 Arduino 논리 핀별 고정 callback slot을 가진다. callback은 Zephyr GPIO ISR에서
직접 실행되며 별도 workqueue로 이동하지 않는다.

- `RISING`, `FALLING`, `CHANGE`만 지원한다.
- mode는 active-low 논리값이 아니라 raw electrical edge다.
- interrupt를 붙이기 전에 해당 핀을 input mode로 구성해야 한다.
- callback 재등록은 기존 slot을 안전하게 제거한 뒤 새 callback으로 교체한다.
- `detachInterrupt()`는 진행 중 callback이 끝날 때까지 정리 순서를 보장한다.
- `pinMode()`로 핀 구성을 바꾸면 기존 interrupt를 자동 detach한다.
- callback에서는 `String`, `Serial`, `Wire`, `SPI`, `delay()`, log와 동적 할당 같은
  blocking 또는 heap API를 호출하지 않는다. volatile/atomic flag를 기록하고 thread에서
  실제 처리를 수행한다.

NU54DK의 `PIN_BUTTON0`은 P1.13 active-low다. 따라서 Arduino edge 이름을 버튼의
누름/해제 이름으로 뒤집지 않는다.

---

## 3. 예제와 자동 검증 구성

| 경로 | 목적 |
| --- | --- |
| `examples/04.Communication/SerialEcho/SerialEcho.ino` | Arduino CLI용 READY/line echo 예제 |
| `examples/02.Digital/InterruptButton/InterruptButton.ino` | ISR에서는 flag만 기록하고 loop에서 LED를 갱신하는 예제 |
| `samples/zephyr/serial_echo/` | 실제 DAP UART Serial HIL image |
| `samples/zephyr/interrupt_button/` | 실제 P1.13 버튼 수동 edge 확인 image |
| `tests/hil/m6_serial_echo.py` | DAPLink UID·MSD·COM 탐색, flash, READY와 고유 payload echo 자동 판정 |
| `tests/zephyr/m6_core_api/` | Common/String/Print/Stream, UART emulator와 GPIO emulator target ztest |
| `tests/zephyr/m6_config_contract/` | UART callback 소유권 충돌 expected-failure |
| `tests/arduino-cli/run_smoke.py` | staged package에서 M6 예제 compile 회귀 |

---

## 4. 검증 결과

### 4.1 Target build와 Arduino CLI

| 시험 | 결과 | FLASH / RAM |
| --- | --- | ---: |
| M4 ArduinoCore-API 계약 target 회귀 | PASS | 34,908 B / 15,032 B |
| `serial_echo` pristine target build | PASS | 38,408 B / 17,528 B |
| `interrupt_button` pristine target build | PASS | 36,712 B / 17,200 B |
| Arduino CLI staged package `SerialEcho` | PASS | Full Zephyr image 생성 |
| Arduino CLI staged package `InterruptButton` | PASS | Full Zephyr image 생성 |
| Serial callback conflict | PASS | 의도한 configure/build 실패와 진단 일치 |

Arduino CLI 검증은 저장소 작업 tree를 직접 참조하지 않는 staged package에서 실행했다.
따라서 개발 checkout에만 우연히 존재하는 파일에 의존하지 않음을 함께 확인했다. Upload와
Flash recipe는 M8 범위이므로 이 단계의 CLI 명령은 compile까지만 담당한다.

### 4.2 실제 Serial HIL

`tests/hil/m6_serial_echo.py`가 다음 전체 경로를 자동 수행했다.

1. UID가 `54153603000528402aae46c5e8e3712a`인 NU54DK DAPLink MSD 식별
2. target과 UID가 일치하는 COM10 선택
3. SerialEcho HEX 기록 및 DAPLink `Flash Sequence` 증가와 `SUCCESS` 확인
4. COM10 115200 8N1에서 `NUCODE_M6_SERIAL_READY` 수신
5. 실행마다 생성한 고유 payload 송신
6. 동일 payload가 `NUCODE_M6_ECHO:` prefix와 함께 돌아오는지 byte 단위 판정

결과는 DAPLink sequence 7, COM10 READY와 고유 echo **PASS**였다. 이 결과는 compile만의
증거가 아니라 UART20, 보드 route, 온보드 VCOM과 `Serial` RX/TX가 함께 동작한 실기
증거다.

### 4.3 NU54DK target ztest

`m6_core_api`를 pristine으로 295/295 build한 뒤 DAPLink sequence 9로 기록했다.
기록량은 249,856 byte였으며 COM10에서 전체 10/10 test case 통과를 회수했다.

| suite | 결과 | 검증 내용 |
| --- | ---: | --- |
| `m6_common` | 3/3 PASS | C/C++ header, `map()`/`makeWord()`, `String`, `Print`, `Stream` |
| `m6_interrupt` | 2/2 PASS | raw 세 edge, parameter callback, detach, 오류와 `pinMode()` auto-detach |
| `m6_serial` | 5/5 PASS | 실제 config 검증, TX/RX/peek, overflow, end, callback 보존, ISR 거부 |
| 합계 | **10/10 PASS** | target semantic 회귀 |

UART와 GPIO 동작 의미는 target에서 emulator driver로 결정적으로 주입했다. 따라서 edge
순서, overflow와 오류 경로를 자동 회귀할 수 있지만, 이 결과가 P1.13의 실제 물리 edge
확인을 대신하지는 않는다.

### 4.4 Runtime `serialEventRun()` HIL

`runtime_smoke` image의 ELF에서 `arduino::serialEventRun()`과 probe가 모두 strong `T`
symbol임을 확인한 뒤 DAPLink sequence 10으로 109,056 byte를 기록했다. COM10에서 다음
실행 순서를 실제로 회수했다.

~~~text
boot
setup
loop 1
loop 2
loop 3
M2_RUNTIME_SMOKE: serial_event=3 PASS
~~~

따라서 hook은 단순 link 가능 상태가 아니라 각 `loop()` 직후 실제로 한 번씩 호출되며,
세 번째 반복까지 누락이나 중복 없이 동작했다.

### 4.5 기존 단계 비회귀

M6 변경을 적용한 상태에서 기존 자동 회귀를 다시 실행했다.

| 기존 기준선 | 결과 | 확인 내용 |
| --- | ---: | --- |
| M3 NU54DK target ztest | **9/9 PASS** | DAPLink sequence 11, 166,400 byte, COM10 `PROJECT EXECUTION SUCCESSFUL` |
| M5 Arduino CLI staged-copy 회귀 | **6/6 PASS** | Blink, library, config/overlay, compile-error negative, parallel 격리, incremental 재빌드 |

따라서 M6의 공통 API·Serial·interrupt 추가가 기존 GPIO·시간·scheduler 의미 또는
Arduino CLI Full Zephyr 빌드 격리를 깨뜨리지 않았음을 확인했다.

---

## 5. 조건부 완료의 정확한 의미

| 항목 | 판정 |
| --- | --- |
| Common/String/Print/Stream 생산 link와 target semantics | 완료 |
| non-owning Serial 설계·구현·target ztest | 완료 |
| 실제 UART20/DAP VCOM READY·echo | 완료 |
| GPIO interrupt raw edge semantics와 detach 자동 회귀 | 완료 |
| `serialEventRun()` symbol과 loop 직후 실행 순서 HIL | 완료 |
| Arduino CLI staged package의 M6 예제 compile | 완료 |
| callback conflict expected-failure | 완료 |
| 실제 P1.13 버튼의 FALLING/RISING/CHANGE ISR edge | **미실행 — 유일한 잔여 조건** |

실제 버튼 edge 미실행은 사용자가 부재한 동안 물리 입력을 만들 수 없었기 때문이다.
빌드 실패, 알려진 firmware 결함, 보드 package 변경 또는 외부 계측 부재가 원인은 아니다.
M7의 독립적인 구현·자동 시험을 진행하는 데 이 조건이 보드 source 변경을 요구하지 않는다.

---

## 6. 보드 package와 단계 경계

- `board_package/NU54DK_Zephyr_DTS`는 commit
  `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` 그대로 사용했다.
- M6는 서브모듈 내부 파일이나 상위 gitlink를 수정하지 않았다.
- 물리 pin, UART route와 GPIO flag의 단일 원본은 보드 Devicetree다.
- M7의 Wire, SPI, ADC와 PWM은 아직 M6 완료 범위가 아니다.
- M8의 Arduino Upload/Flash recipe, pyOCD/J-Link 선택과 recovery 분리는 아직 미구현이다.
- 일반 M6 flash에서 mass erase나 recover를 수행하지 않았다.

---

## 7. 잔여 확인 절차

사용자가 보드 앞에 있을 때 `interrupt_button` image를 기록하고 다음만 확인한다.

1. 초기 LED 상태를 확인한다.
2. P1.13 active-low 버튼을 누르고 LED 또는 callback count가 한 번 갱신되는지 확인한다.
3. 버튼을 놓고 반대 edge가 한 번 갱신되는지 확인한다.
4. `FALLING`, `RISING`, `CHANGE` mode를 각각 실행해 예상하지 않은 반대 edge callback이
   없는지 확인한다.
5. 결과와 사용한 image commit을 이 문서에 추가하고 상태를 `완료`로 변경한다.

bounce가 있는 실제 버튼에서 `CHANGE` callback이 여러 번 발생할 수 있다. M6는 debounce를
자동 제공하지 않으므로, 전기적 bounce를 Core interrupt 결함과 혼동하지 않는다. 외부
신호발생기나 계측기는 이 잔여 확인의 필수 장비가 아니다.
