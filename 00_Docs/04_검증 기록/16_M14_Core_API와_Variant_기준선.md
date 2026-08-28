# M14 Core API와 Variant 기준선

| 항목 | 내용 |
| --- | --- |
| 상태 | Core API·DTS 기반 Variant 무보드 구현, host native semantic·NU54/QEMU cross-build 완료; 원격 QEMU runtime 증적과 신규 pin HIL 대기 |
| 기준일 | 2026-08-29 |
| 기준 Core | `4bbaa6143bf1ea182c32ac5d045858e4ffbcd031`(M13 완료)에서 시작한 M14 작업 tree |
| 기준 board package | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` — 변경 없음 |
| 기준 SDK | nRF Connect SDK v3.4.0 / Zephyr 4.4.0 |
| 기준 target | `nrf54l15dk/nrf54l15/cpuapp/nu54dk` |

---

## 1. 목적과 완료 경계

M14는 v0.2.0의 Core API 부채와 Variant 기준선을 다룬다. 이 기록은 보드 없이
구현·검증할 수 있는 Core API와 고정 DTS 기반 Variant 범위를 포함한다.

- Arduino utility, bit helper와 `F()`의 실제 지원 상태를 코드와 시험에 맞춘다.
- 선언만 존재하던 `random()`과 `randomSeed()`를 생산 image에 연결한다.
- 기존 backend를 바꾸지 않는 최소 공개 진단 값·포맷·비파괴 projection 계약을 만든다.
- C++ exception/RTTI의 기본 비활성·expert opt-in 정책을 검증 가능한 구성으로 고정한다.
- v0.1 논리 pin 번호를 보존하면서 DTS `led0..3`/`sw0..3` alias를 capability 기반
  sparse Variant로 확장한다.
- UART/I2C/SPI와 PWM이 소유한 pad를 일반 digital pin으로 중복 노출하지 않는다.

이 기준선은 M14 전체 완료 선언이 아니다. 물리 보드에서 신규 LED2/3과
BUTTON1..3의 GPIO·pull·interrupt를 검증해야 하며, 원격 QEMU runtime 결과도 실제
workflow 증적이 생성된 뒤에만 PASS로 기록한다.

---

## 2. 구현한 공통 Arduino 계약

### 2.1 Utility와 bit helper

ArduinoCore-API 1.5.2가 제공하는 `map()`, `constrain()`, `min()`, `max()`, `lowByte()`,
`highByte()`, `bitRead()`, `bitWrite()`, `bitSet()`, `bitClear()`, `bitToggle()`과 `bit()`를
실제 production include 경로에서 검증했다. Core는 C++용 generic `abs()`를 추가했다.

`abs()`는 인수를 한 번만 평가하며 `Arduino.h` 다음에 `<cmath>`를 include해도
`std::abs()`를 가리지 않는다. C 호출부에는 Arduino 호환 매크로를 제공한다. 다음 입력
경계는 지원하지 않는다.

- C의 `abs()` 매크로와 ArduinoCore-API의 `constrain()`에는 부수 효과 표현식을 넘기지 않는다.
- `constrain()`은 선택 경로에 따라 `amt`를 최대 세 번, `low`/`high`를 두 번 평가할 수 있다.
- `constrain()`의 정상 범위는 `low <= high`이며 역전된 경계를 Core가 보정하지 않는다.
- signed 정수형의 최솟값은 `abs()`의 같은 형식 결과로 표현할 수 없다.
- bit index는 0 이상이어야 하며 helper별 실제 shift 형식의 bit 폭보다 작아야 한다.

`map()`은 ArduinoCore-API의 정수식을 그대로 유지한다. 입력 범위 밖 값은 clamp하지 않고
외삽하며, `in_min != in_max`여야 한다. 모든 뺄셈·곱셈 중간식이 target의 signed 32-bit
`long` 범위 안에 있어야 한다. 0 span과 signed overflow를 포화값이나 오류값으로 바꾸지
않는다.

`bitRead(value, index)`는 unsigned로 해석한 value 형식의 폭을 경계로 한다. 나머지 변경
helper와 `bit()`는 upstream의 `1UL << index`를 사용하므로 destination 폭뿐 아니라
`unsigned long` 폭도 넘을 수 없다. NU54DK에서는 `unsigned long`이 32-bit이므로
`bitSet`/`bitClear`/`bitToggle`/`bitWrite`와 `bit()`의 유효 index는 0~31이다.

### 2.2 `F()` 계약

ArduinoCore-API의 `F()`와 `__FlashStringHelper`는 `String`과 `Print` 호출부에서 compile,
link된다. 임의 TEMP 경로의 최초 Windows gate는 실행이 SKIP됐지만, repository 고정
staging에서 매번 다시 compile한 executable은 실제 출력 비교를 PASS했다. 기존 Print target
회귀도 그대로 유효하다. nRF54는 AVR과 같은 Harvard memory model이 아니므로 이 호환 표기는
문자열을 별도 flash address space에 배치하거나 SRAM을 절약한다는 약속이 아니다. 이
차이는 `의미 차이`로 공개한다.

### 2.3 `random()`과 `randomSeed()`

생산 구현은 다음 계약을 가진다.

| 항목 | 계약 |
| --- | --- |
| 상태 | modulus 2^32의 full-period 32-bit LCG |
| 동시성 | Zephyr `atomic_cas()`로 전역 상태 갱신 |
| 범위 | rejection sampling을 사용한 bias 없는 반열린 범위 |
| `random(n)` | `n <= 0`이면 0, 아니면 `[0, n)` |
| `random(a, b)` | `a >= b`이면 `a`, 아니면 `[a, b)` |
| `randomSeed(0)` | 현재 상태를 변경하지 않음 |
| 동일 nonzero seed | 같은 단일 호출 순서에서 같은 수열 |
| entropy | 자동 hardware entropy 혼합 없음 |

이 PRNG는 Arduino sketch의 일반적인 모의·분산 값 용도다. key, nonce, session token처럼
예측 저항이 필요한 값에는 사용할 수 없다. atomic 갱신은 data race를 막지만 여러 thread의
호출 interleaving까지 재현 가능하게 만들지는 않는다.

multiplier `1664525`는 1 modulo 4이고 increment `1013904223`은 홀수다. 따라서 LCG 상태는
0을 포함한 uint32 전체 도메인을 한 주기에 정확히 한 번 순회한다. rejection threshold가
2^32개의 균등 후보를 가정하는 것과 실제 generator domain이 일치하므로 2의 거듭제곱
bound에서도 특정 remainder가 한 개 부족해지지 않는다.

---

## 3. 공개 Diagnostics 기준선

`<nucode/Diagnostics.h>`에는 다음 최소 계약만 추가했다.

- `DiagnosticSubsystem`과 `DiagnosticCode`
- `Diagnostic { subsystem, code, driver_error, detail }`
- 안정된 영문 token 변환
- 활성 backend의 마지막 오류를 읽는 비파괴 `lastDiagnostic()` projection
- 동적 할당과 logging이 없는 `formatDiagnostic()`
- `NU54:<subsystem>:<code>:driver=<signed>:detail=<unsigned>` ASCII 형식
- 필요한 전체 길이 반환, 0-byte 길이 질의, capacity가 1 이상일 때 NUL 종료 truncation

GPIO, Serial, Wire, SPI, Analog에는 이미 서로 다른 비공개 마지막 오류 상태가 있다.
이번 구현은 활성화된 GPIO, Serial, Wire, SPI와 Analog의 원자적 마지막 오류를 공통 code로
투영한다. driver errno는 `driver_error`일 때만 공개하고, Serial RX overflow의 `detail`에는
누적 drop byte 수를 넣는다. 조회는 상태를 지우지 않는다. Core는 오류 없음, 별도 오류
저장소가 없는 Time과 build에서 비활성화된 backend는 `unsupported`로 구분한다.

이 projection은 최신 원자 값의 비파괴 snapshot이며 이벤트 queue나 오류 이력이 아니다.
동시 갱신 중에는 다음 상태로 넘어가는 경계값을 볼 수 있다. 포맷·truncation과 synthetic
backend projection은 host semantic에서 검증했지만, 실제 driver 오류 직후의 target
projection은 후속 HIL 범위다.

---

## 4. C++ exception과 RTTI 정책

일반 Arduino profile은 계속 다음 값을 사용한다.

```text
CONFIG_CPP_EXCEPTIONS=n
CONFIG_CPP_RTTI=n
```

exception과 RTTI는 Arduino 호환 기본 계약이 아니라 expert opt-in이다. 활성화할 때는 최소한
다음을 함께 검토한다.

```text
CONFIG_REQUIRES_FULL_LIBCPP=y
CONFIG_CPP_EXCEPTIONS=y
CONFIG_CPP_RTTI=y
```

full libstdc++/libc, heap와 thread stack 증가를 제품 memory budget에 반영해야 한다. M14
host harness는 throw/catch, stack unwind 소멸자, `dynamic_cast`와 `typeid`를 실제 실행한다.
임의 TEMP executable은 Windows Application Control이 WinError 4551로 차단했지만,
repository 고정 staging에서 매번 재compile한 시험은 3/3 PASS했다. 이는 host
runtime 증거이며 Zephyr target runtime으로 확대하지 않는다. NCS 3.4.0의
`qemu_cortex_m3` cross-build는 같은 기능과 실제 `random`/Diagnostics source,
`Arduino.h` 뒤 `<cmath>`를 모두 통과했다. 로컬 Windows에는 `qemu-system-arm`이
없으므로 QEMU runtime PASS를 주장하지 않으며, 고정 Nordic Linux container의
원격 runtime gate 결과를 기다린다. NU54DK opt-in runtime/HIL도 아직 완료하지 않았다.

---

## 5. Variant/DTS 경계와 남은 HIL

board submodule과 DTS는 수정하지 않고 고정 revision을 유지했다. Variant는 물리
controller/pin/flag를 복제하지 않고 `digital_pins.inc`의 alias/class 목록과 고정 DTS에서
descriptor를 생성한다. v0.1 공개 번호는 그대로 보존했다.

| 논리 ID | 역할 | DTS 원본 | digital 판정 |
| ---: | --- | --- | --- |
| 0 | `LED_BUILTIN`, `PIN_LED0`, `D0` | `led0` | input + output + interrupt |
| 1 | `PIN_BUTTON0`, `D1` | `sw0` | input + interrupt |
| 2 | `PIN_A0`, `A0` | ADC chosen | 거부 |
| 3 | `PIN_PWM0`, `PIN_PWM_LED` | PWM chosen | 거부 |
| 4 | `PIN_LED1` | `led1` | P1.10을 PWM이 소유하므로 거부 |
| 5..6 | `PIN_LED2..3` | `led2..3` | input + output + interrupt |
| 7..9 | `PIN_BUTTON1..3` | `sw1..3` | input + interrupt |

`NUM_DIGITAL_PINS=10`은 sparse ID 상한, `NUM_DIGITAL_CAPABLE_PINS=7`은 실제 descriptor
개수, `NUM_PIN_ROLES=10`은 Core 상태 slot 범위다. `PIN_A0`, `PIN_PWM0`, `PIN_LED1`은
`pinDescription()==nullptr`, `digitalPinToInterrupt()==NOT_AN_INTERRUPT`로 fail-closed 거부한다.
UART20, I2C22, SPI00 pinctrl과 명시적 connector mapping이 없는 일반 header pin은
peripheral ownership이 확정되지 않아 이번 digital map에서 제외했다.

보드 준비 후 남은 HIL은 `PIN_LED2..3`의 output/readback, `PIN_BUTTON1..3`의
`INPUT_PULLUP` raw HIGH/LOW, `FALLING`/`RISING`/`CHANGE` edge다. `PIN_LED1`은 의도적
거부 계약이므로 digital HIL 대상이 아니며, 기존 `PIN_PWM0` HIL을 소유권 회귀로 사용한다.

---

## 6. 자동 검증 결과

### 6.1 Host semantic/link

```powershell
python -m unittest tests.host.test_m14_core_contract -v
```

최초 기준 Windows gate 결과는 **compile/link PASS 1건, source 등록 PASS 1건, native
semantic SKIP 1건**이었다. 임의 TEMP executable이 WinError 4551로 차단된 사실을 PASS로
숨기지 않았다. 이후 repository 아래 고정 staging을 매번 다시 compile하는 runner로 바꾼
단독 재실행은 **3/3 PASS**했고 생성 executable의 의미 시험도 실제 종료 코드 0으로
완료했다. 이는 로컬 실행 증거이며 독립 Ubuntu CI 증거로 확대하지 않는다. compile/link
단계는 실제 C++ production source와 constexpr 계약에서 다음을 확인했다.

- utility, bit helper와 full-period LCG/rejection 순수 연산의 compile·constexpr 계약
- C++ `abs()`, `<cmath>`/`std::abs()`, `F()`/`Print` 호출부 compile
- 실제 `wiring_random.cpp`, backend projection과 `diagnostics.cpp`의 host compile/link
- exception/RTTI 의미 시험 source의 compile/link
- production CMake source 등록

생성 executable에는 utility, `F()` 출력, public random 범위·seed, Diagnostics 포맷과
backend projection, throw/catch·unwind·RTTI runtime 검사가 모두 들어 있다. 고정 staging
재실행은 이 검사를 모두 수행했지만, GitHub Ubuntu host job 결과는 별도 원격 증거로
기록한다.

### 6.2 NU54DK production target compile

`tests/zephyr/m14_core_contract`를 production Zephyr module 경로로 pristine build-only
구성했다. test app이 Core source를 직접 등록하지 않고 `CONFIG_NUCODE_ARDUINO_CORE=y`와
`CONFIG_NUCODE_ARDUINO_API=y`를 통해 새 `wiring_random.cpp`와 `diagnostics.cpp`를 실제 Core
library에 포함한다. test 본문은 두 `random()` overload와 `randomSeed()`, invalid GPIO 오류의
`lastDiagnostic()` projection 및 `formatDiagnostic()`을 호출한다.

| 항목 | 결과 |
| --- | ---: |
| platform | `nrf54l15dk/nrf54l15/cpuapp/nu54dk` |
| Twister configuration | 1/1 build-only PASS |
| M14 test case | 1개 build됨; 실행/HIL은 이번 명령 범위 아님 |
| 최종 ELF 확인 | `random(long)`, `random(long,long)`, `randomSeed(unsigned long)`, `lastDiagnostic()`, `formatDiagnostic()` symbol 포함 |
| board submodule | 기준 revision 유지, 수정 없음 |

### 6.3 QEMU 정책 image

`tests/zephyr/m14_cpp_policy`는 `qemu_cortex_m3`용으로 다음 세 ztest를 정의한다.

1. throw/catch와 stack unwind
2. `dynamic_cast`와 `typeid`
3. 실제 Zephyr atomic random, Diagnostics, `Arduino.h`/`std::abs()` 공존

NCS 3.4.0 GNU Arm toolchain cross-build는 **1/1 PASS**했다. 로컬 QEMU runner가 없어 세
test case는 `Test was built only`이며 실행 PASS가 아니다. `run_m14_qemu.py`는
고정 NCS/Zephyr revision, `qemu-system-arm` identity, exact scenario·3 testcase, `runnable=true`와
각 PASS를 fail-closed로 검사하고 JSON 증적을 만든다. 고정 digest Nordic container의
GitHub workflow에 연결했지만 이 문서 기준에서 원격 실행 결과는 아직 대기 중이다.

### 6.4 Variant/DTS contract

host verifier는 board gitlink의 DTS alias 8개를 읽어 물리 GPIO 중복, 논리 ID,
capability class와 PWM ownership을 검사한다. alias 8개 중 `PIN_LED1` 역할은 mapping만
검증하고 digital descriptor에서 제외하여 descriptor 7개를 생성한다. duplicate physical
GPIO negative test도 포함한다. `tests/zephyr/m14_variant_contract`는 production module과
NU54DK DTS로 descriptor 7개, sparse 거부 slot과 LED/button capability를 3 testcase에서 build했다.

| 항목 | 결과 |
| --- | ---: |
| host DTS/verifier | 3 PASS; 로컬 구형 C++ compiler probe 1 SKIP |
| NU54DK Variant Twister | 1/1 build-only PASS, 3 testcase build |
| v0.1 pin 번호 | 0..3 보존 |
| board submodule | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3`, 수정 없음 |

### 6.5 실기 HIL 준비

`tests/zephyr/m14_pin_hil`은 production NU54DK target으로 sysbuild/link했다. 생성 image는
`PIN_LED2..3`의 LOW/HIGH output과 raw readback, `PIN_BUTTON1..3`의 `INPUT_PULLUP`
HIGH/LOW와 `FALLING`/`RISING`/`CHANGE` ISR을 안내형 UART protocol로 검증한다.

Host runner `tests/hil/nu54dk/m14_pin_hil.py`는 다음 경계를 fail-closed로 검사한다.

- 명시적 `--acknowledge-manual-actions`과 동작별 30초, 전체 520초 timeout
- Core commit, 부모 저장소 gitlink와 board checkout, NCS/Zephyr revision, target build record
- 현재 Core 범위·M14 application·board tree와 build record의 세 source SHA-256 exact 일치
- HEX, build record와 UART transcript의 SHA-256
- 정확한 핀 ID·동작·edge 순서와 최종 PASS token
- 기존 증적의 비의도적 덮어쓰기, 누락·중복 protocol, 불완전 FAIL line 차단

Parser·증적 host 시험은 11/11 PASS이고, HIL image의 production target build와
Twister build-only도 PASS했다. 이 결과는 실행 준비 증거이지 실기 PASS가 아니다.
M3/M4/M6/M7과 M14 Core·Variant·HIL을 같이 묶은 로컬 NCS v3.4.0 target gate는
7/7 build-only, failed/error/warning 0건으로 `M12_ZEPHYR_BUILD_PASS=7`을 출력했다.
HIL build record의 Core, application, board source SHA-256은 Python이 현재 tree에서
CMake와 같은 알고리즘으로 재계산한 값과 모두 byte-exact 일치했다.
LED 결과는 GPIO output/raw readback이며 사람의 시각적 점등 확인으로 확대해석하지
않는다. 보드 연결 후의 실제 flash·UART·버튼 동작과 PASS 증적 생성이 M14의 남은
완료 경계다.

---

## 7. 판정

M14의 무보드 Core API와 DTS 기반 Variant 구현은 완료했다. utility, bit helper,
`F()`, random과 Diagnostics는 host semantic·compile/link와 NU54 target compile을 통과했다.
`F()`는 nRF54에서 AVR식 SRAM 절약을 제공하지 않는 의미 차이로 남고,
exception/RTTI는 기본 비활성·expert opt-in 정책을 유지한다. QEMU actual-runtime은
원격 workflow 증적 전이므로 아직 PASS로 계산하지 않는다.

M14 전체의 물리 완료 경계는 `PIN_LED2..3`과 `PIN_BUTTON1..3`의 NU54DK HIL이다.
`PIN_LED1`은 `PIN_PWM0` 소유권 때문에 의도적으로 digital 거부하며, UART/I2C/SPI·
일반 connector pin은 이번 범위에서 공개하지 않는다. 기존 v0.1 HIL은 기존 pin
회귀로만 사용하고 신규 pin 증거로 확대하지 않는다.
