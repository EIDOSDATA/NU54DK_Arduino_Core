# M2 Zephyr module과 Arduino runtime 기준선

| 항목 | 내용 |
| --- | --- |
| 문서 상태 | 완료 |
| M2 상태 | **완료** — clean module·runtime·정책·negative build와 기존 runtime HIL 통과 |
| 검증일 | 2026-08-26 (Asia/Seoul) |
| 작성자 | Quantum / NUCODE |
| 대상 구조 | Loader/LLEXT 없는 Native Full Zephyr 정적 이미지 |
| 대상 보드 | NU54DK |
| Zephyr 보드 타깃 | `nrf54l15dk/nrf54l15/cpuapp/nu54dk` |
| Core 기준 revision | `a8d62ea75fef57cdf166738eb45ad4f61e0eaa9c` (clean) |
| 보드 package 기준 revision | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` (clean, 읽기 전용) |
| 기본 연결 | 온보드 CMSIS-DAP V2 + pyOCD |

> 상위 gitlink와 서브모듈 HEAD는 위 보드 revision으로 일치하며 두 작업 트리는 검증 시작
> 시점에 clean이었다. `NU54DK_Zephyr_DTS`는 읽기 전용 빌드 입력으로 사용했고 서브모듈
> 내부 파일은 수정하지 않았다. live build record에는 clean Core·보드 revision과 각 source
> SHA-256이 기록된다. 이번 갱신은 pristine build·link 회귀이며 target flash는 수행하지
> 않았다.

---

## 1. 목적과 판정 범위

M2는 Arduino GPIO나 주변장치를 구현하기 전에 다음 최소 runtime 구조가 성립하는지
검증한다.

1. Core 저장소를 Zephyr module로 발견하고 opt-in library로 링크한다.
2. Core가 소유하는 `main()`이 `initVariant()`, `setup()`, `loop()` 순서로 실행한다.
3. C++ 전역 생성자가 `setup()`보다 먼저 실행된다.
4. `setup()`은 정확히 한 번, `loop()`는 반복 실행된다.
5. Core를 활성화하지 않은 일반 Zephyr 앱에는 Core 코드가 편입되지 않는다.
6. Loader나 LLEXT 없이 하나의 완전한 Zephyr ELF/HEX를 생성한다.

M2의 LED 제어는 위 runtime을 육안으로 확인하기 위한 Zephyr 전용 시험 계측이다. 다음은
M2 구현 또는 지원 판정에 포함하지 않는다.

- Arduino `LED_BUILTIN`과 Variant 핀 매핑
- `pinMode()`, `digitalWrite()`, `digitalRead()`
- `millis()`, `micros()`, `delay()`, `yield()`
- Serial, Wire, SPI, ADC, PWM과 interrupt API
- `.ino` 전처리와 Arduino CLI Build Adapter

---

## 2. 구현 구조

### 2.1 Zephyr module

| 파일 | 책임 |
| --- | --- |
| `zephyr/module.yml` | module 이름과 CMake/Kconfig 진입점 등록 |
| `zephyr/Kconfig` | `CONFIG_NUCODE_ARDUINO_CORE` opt-in 설정과 C++ 정책 의존성 |
| `zephyr/CMakeLists.txt` | Core library, include 경로와 build provenance 연결 |
| `zephyr/cmake/write_build_record.cmake` | 매 build의 revision과 입력 SHA-256 갱신 |

`CONFIG_NUCODE_ARDUINO_CORE`의 기본값은 `n`이다. 애플리케이션이 C++17 이상의 표준을
선택한 뒤 명시적으로 활성화해야 한다. exception과 RTTI는 Core가 금지하지 않고 최종
애플리케이션이 선택한다. 따라서
`EXTRA_ZEPHYR_MODULES`에 이 저장소를 전달했다는 이유만으로 일반 Zephyr 앱에 Core가
주입되지 않는다.

### 2.2 Runtime과 symbol 소유권

| symbol | 소유자 | 연결 | M2 동작 |
| --- | --- | --- | --- |
| `main()` | Core | strong | `initVariant()`와 `setup()`을 한 번 호출한 뒤 `loop()` 반복 |
| `initVariant()` | Core 기본 구현 | weak | M2에서는 no-op, 이후 Variant가 strong symbol로 교체 가능 |
| `setup()` | 사용자 애플리케이션 | strong | Sketch 초기화 |
| `loop()` | 사용자 애플리케이션 | strong | 반환할 때마다 Core가 다시 호출 |

공개 `Arduino.h`에는 Sketch가 구현할 `setup()`과 `loop()` 계약만 둔다. Variant 초기화
확장점은 `internal/ArduinoRuntime.h`에 분리하여 Sketch 공개 API로 취급하지 않는다.

Zephyr가 C++ 정적 초기화를 끝낸 뒤 main thread에서 Core의 `main()`을 호출한다. M2에서는
전용 Arduino thread를 만들지 않는다. 빈 `loop()`의 CPU 점유, scheduler fairness와 전용
thread 전환 여부는 M3 계측 결과로 결정한다.

### 2.3 C++와 메모리 정책

| 항목 | M2 기준 sample | Core 허용 범위 |
| --- | --- | --- |
| C++ 표준 | C++17 | C++17 이상 |
| C++ library | Zephyr minimal C++ library | 애플리케이션 선택 |
| exception | 비활성 | 애플리케이션이 full C++ library와 함께 활성화 가능 |
| RTTI | 비활성 | 애플리케이션이 full C++ library와 함께 활성화 가능 |
| main stack | 2,048 B | 애플리케이션 Kconfig 소유 |
| Zephyr heap pool | 0 B | 애플리케이션 Kconfig 소유 |
| common libc malloc | 비활성 | 애플리케이션 Kconfig 소유 |
| LLEXT | 비활성 | v0.1 범위 제외 |

두 C++ compile unit에 실제 적용된 핵심 flag는 다음과 같다.

```text
-std=c++17 -fno-exceptions -fno-rtti
```

Core 자체는 M2에서 동적 메모리를 할당하지 않는다. 힙 정책은 Core가 모든 애플리케이션에
강제하지 않고 최종 애플리케이션 Kconfig가 소유한다. `runtime_smoke`만 무할당 기준을
검증하기 위해 heap과 common libc malloc을 끈다.

---

## 3. 재현 명령

아래 명령은 NCS v3.4.0 Toolchain 환경이 활성화된 PowerShell에서 Core 저장소 루트를 현재
디렉터리로 두고 실행한다. 개인 설치 경로와 probe UID는 환경에 맞게 바꾼다.

```powershell
$NcsRoot = "C:/ncs/v3.4.0"
$CoreRoot = (Resolve-Path ".").Path
$BoardRoot = Join-Path $CoreRoot "board_package/NU54DK_Zephyr_DTS"
$Board = "nrf54l15dk/nrf54l15/cpuapp/nu54dk"
$RuntimeBuild = Join-Path $CoreRoot "build/m2-runtime"

west -z "$NcsRoot/zephyr" build `
  --pristine always `
  --no-sysbuild `
  -b $Board `
  -s "$CoreRoot/samples/zephyr/runtime_smoke" `
  -d $RuntimeBuild `
  -- `
  "-DBOARD_ROOT=$BoardRoot" `
  "-DEXTRA_ZEPHYR_MODULES=$CoreRoot"

west -z "$NcsRoot/zephyr" flash `
  -d $RuntimeBuild `
  --dev-id <PROBE_UID>

west -z "$NcsRoot/zephyr" build -d $RuntimeBuild
```

Flash 명령은 `-r pyocd`를 지정하지 않아 생성된 보드의 기본 runner 선택까지 시험한다.
일반 Flash에는 `--erase`나 recover를 넣지 않는다.
위 flash 명령은 재현용이며 이번 clean 기준선 갱신에서는 실행하지 않았다.

Core 비활성 negative build는 다음과 같다.

```powershell
$OffBuild = Join-Path $CoreRoot "build/m2-module-off"

west -z "$NcsRoot/zephyr" build `
  --pristine always `
  --no-sysbuild `
  -b $Board `
  -s "$NcsRoot/zephyr/samples/hello_world" `
  -d $OffBuild `
  -- `
  "-DBOARD_ROOT=$BoardRoot" `
  "-DEXTRA_ZEPHYR_MODULES=$CoreRoot"
```

---

## 4. Build와 link 결과

### 4.1 Runtime clean build

| 항목 | 결과 |
| --- | --- |
| build | 성공 |
| FLASH | 30,568 B / 1,524 KB, 1.96% |
| RAM | 6,856 B / 256 KB, 2.62% |
| `zephyr.elf` | 1,120,504 B |
| `zephyr.hex` | 86,054 B |
| `zephyr.bin` | 30,568 B |
| 이번 기준선 생성 | `--pristine always --no-sysbuild`, 274/274 PASS |

| 산출물 | SHA-256 |
| --- | --- |
| `m2-runtime/zephyr/zephyr.elf` | `F30B9C28A5730561CD726833FAD7D26D1A068F7A74127CB32224A8A78087A80C` |
| `m2-runtime/zephyr/zephyr.hex` | `16394D224AFCD655BE06EAC0AD81BA68644B3A404A98BE7C4AE9ABCDA6C11D2B` |
| `m2-runtime/zephyr/zephyr.bin` | `3D174BB468AE243335FC3E5CAD89E92C89261A4564510B9592D2853548C1F4B8` |

### 4.2 Kconfig와 compiler

최종 `.config`의 핵심값은 다음과 같다.

```text
CONFIG_NUCODE_ARDUINO_CORE=y
CONFIG_ZEPHYR_NUCODE_ARDUINO_CORE_MODULE=y
CONFIG_CPP=y
CONFIG_STD_CPP_VERSION=201703
CONFIG_STD_CPP17=y
CONFIG_MINIMAL_LIBCPP=y
CONFIG_MAIN_STACK_SIZE=2048
CONFIG_HEAP_MEM_POOL_SIZE=0
# CONFIG_COMMON_LIBC_MALLOC is not set
# CONFIG_LLEXT is not set
```

`compile_commands.json`에서 Core `main.cpp`와 sample `runtime_smoke.cpp`가 각각 한 번씩
C++17, exception 비활성, RTTI 비활성 flag로 compile된 것을 확인했다.

현재 Core HEAD에는 M3 GPIO·시간 backend가 이미 포함되어 있으므로 이 M2 회귀 build의
`.config`에도 `CONFIG_NUCODE_ARDUINO_GPIO=y`와 `CONFIG_NUCODE_ARDUINO_TIME=y`가
나타난다. M2 판정은 module/runtime 계약과 opt-in 경계를 확인하며 이 artifact를 과거 M2
전용 image로 취급하지 않는다.

### 4.3 C++ 정책 확장 시험

Core Kconfig가 기준 sample의 정책을 모든 Sketch에 강제하지 않는지 두 clean build로
검증했다.

| 시험 | 결과 | 실제 compiler·link 증거 | FLASH / RAM |
| --- | --- | --- | --- |
| C++20 + minimal C++ | 성공 | 두 C++ TU 모두 `-std=c++20 -fno-exceptions -fno-rtti` | 30,568 B / 6,856 B |
| C++17 + full libstdc++ + exception + RTTI + common libc malloc | 성공 | `-fno-*` 제거, `CONFIG_COMMON_LIBC_MALLOC=y`, `libstdc++.a` link | 53,172 B / 7,032 B |

두 정책 build는 runtime 명령에 각각 다음 CMake/Kconfig 인자를 추가해 pristine으로
재현한다.

```text
C++20:   -DCONFIG_STD_CPP17=n -DCONFIG_STD_CPP20=y
full C++: -DCONFIG_REQUIRES_FULL_LIBCPP=y -DCONFIG_CPP_EXCEPTIONS=y
          -DCONFIG_CPP_RTTI=y -DCONFIG_COMMON_LIBC_MALLOC=y
```

따라서 `STD_CPP_VERSION >= 201703`은 C++20을 정상 허용하고 exception/RTTI도
애플리케이션이 선택할 수 있다. NCS v3.4.0의 full libstdc++ 링크에는 기준 sample의
`CONFIG_COMMON_LIBC_MALLOC=n`을 `y`로 함께 바꿔야 했다. 현재 image 비용은 기준
sample보다 FLASH 22,604 B, RAM 176 B 증가했다. 실제 `throw/catch`, `dynamic_cast`,
`typeid` 실행 의미와 malloc/heap 고갈 정책은 아직 검증하지 않았으므로 이번 결과는
설정·compile·link 호환성으로 한정한다.

### 4.4 ELF와 map

최종 ELF의 runtime symbol은 다음과 같다.

```text
W initVariant()
T loop()
T setup()
T main
B nu54_m2_runtime_trace
```

Map에는 사용자 앱과 Core가 서로 다른 archive에서 편입된 기록이 있다.

```text
app/libapp.a(runtime_smoke.cpp.obj)
modules/nucode_arduino_core/libnucode_arduino_core.a(main.cpp.obj)
```

`runtime_smoke.cpp`의 정적 초기화 함수와 `.init_array` 항목도 최종 ELF에 존재한다. 이는
전역 생성자 코드가 링크됐다는 증거이며, 실제 실행 순서는 다음 실기 시험에서 별도로
판정했다.

### 4.5 Build provenance

Zephyr 표준 `build_info.yml`의 `vendor-specific.nucode-arduino-core`에는 configure 시점
snapshot을 넣는다. Zephyr가 소유한 이 파일을 Core가 build-time에 다시 쓰지는 않는다.

매 build에서 새 파일과 삭제된 파일까지 다시 탐색하는 별도 target이 실행되고, build
root의 `nucode_arduino_core_build.yml`을 live source-state 보조 record로 관리한다. 값이 같으면
파일을 다시 쓰지 않아 timestamp가 유지된다. 신규 untracked 입력을 추가하고 삭제한 시험에서
Core source SHA-256이 각각 바뀌고 원래 값으로 복구되는 것도 확인했다.

최종 live record의 공개용 발췌는 다음과 같다. 실제 파일의 `toolchain_path`에는 로컬 설치
경로가 기록되므로 아래에서는 자리표시자로 바꿨다.

```yaml
nucode_arduino_core:
  core_revision: 'a8d62ea75fef'
  core_source_sha256: '60d6ef55aded0d13751517a05b955b24774c74606ee827916fceffe377fe1707'
  application_source_sha256: 'a7e5792e8d73641983bca0c8e13a32d4a8a9e009c9ece0f795b6f4e9748dcd44'
  board_revision: 'fe65f2f0880b'
  board_source_sha256: '00305e847d6844c401a78f0dbf449c1c37dda4fd707afaacb43ca6217bf9f72e'
  ncs_revision: '99553055607b'
  zephyr_revision: 'bf801e4e3d19'
  board: 'nrf54l15dk'
  board_qualifiers: 'nrf54l15/cpuapp/nu54dk'
  toolchain_variant: 'zephyr'
  toolchain_path: '<LOCAL_TOOLCHAIN_PATH>'
  cxx_compiler: 'GNU 14.3.0'
```

NCS와 Zephyr revision은 고정 설치본의 HEAD를 기록한다. Core와 보드 package는 실제 build
소유 경로의 변경 여부를 검사하여 dirty suffix를 붙이지만, 이번 record에는 suffix가 없다.
세 source SHA-256은 untracked 입력도 식별한다. 이 보조 record는 최종 ELF target과
원자적으로 결합되지 않고 입력 glob이 실제 compile 대상보다 넓으며 NCS·Zephyr dirty
state도 판정하지 않는다. 따라서 최종 image 식별은 위 산출물 SHA-256과 함께 사용한다.

---

## 5. Core 비활성 negative build

동일한 `BOARD_ROOT`와 `EXTRA_ZEPHYR_MODULES`를 Zephyr `hello_world`에 전달하되
`CONFIG_NUCODE_ARDUINO_CORE`를 켜지 않고 clean build했다.

| 확인 항목 | 결과 |
| --- | --- |
| module 발견 symbol | `CONFIG_ZEPHYR_NUCODE_ARDUINO_CORE_MODULE=y` |
| Core 활성 설정 | 없음 |
| Core archive | 생성되지 않음 |
| Core live build record | 생성되지 않음 |
| 표준 `build_info.yml`의 NUCODE vendor section | 생성되지 않음 |
| `setup()`, `loop()`, `initVariant()` | ELF symbol 0개 |
| no-change rebuild | `ninja: no work to do`, exit 0 |
| FLASH | 30,224 B / 1,524 KB |
| RAM | 5,800 B / 256 KB |

| 산출물 | 크기 | SHA-256 |
| --- | ---: | --- |
| `m2-module-off/zephyr/zephyr.elf` | 1,159,168 B | `BB1894BCA3E872300E0C37ABEF5CC008450728F2C08FF55185E3CDD1AE791806` |
| `m2-module-off/zephyr/zephyr.hex` | 85,096 B | `E700B202855D509911277594C844DFC2C4BD9F3589125328559FD5C95EF84C8A` |

이 결과는 Core가 opt-in이며 일반 Zephyr 애플리케이션의 링크 산출물과 ELF symbol 공간에
Core 코드·live record를 추가하지 않는다는 negative gate를 통과한다. Zephyr module 발견과
CMake configure footprint 자체는 존재한다.

---

## 6. NU54DK runtime 실기 시험

### 6.1 내부 판정

`runtime_smoke`는 다음 순서를 자체 검사한다.

1. 전역 `ConstructorProbe`가 호출 횟수를 증가시키고 나머지 필드를 쓴 뒤 signature를
   마지막 commit marker로 기록한다.
2. `setup()`이 호출 횟수를 증가시키고 constructor가 먼저 정확히 한 번 실행됐는지 검사한다.
3. `setup()` 호출 횟수가 1이 아니면 즉시 panic한다.
4. `loop()`는 매번 `setup()` 횟수를 확인하고 자체 호출 횟수를 증가시킨다.
5. 세 번째 `loop()`에서 호출 횟수를 먼저 쓴 뒤 추적 결과를 `PASS`로 기록한다.

실패 경로도 failure code를 먼저 기록하고 `FAIL` 결과를 마지막에 쓴다. 향후 debugger가
trace를 자동 수집할 때는 target을 halt하거나 result를 두 번 읽어 관측 중 marker가
바뀌지 않았는지 확인한다.

실패하면 LED 반복에 진입하지 않거나 점멸이 중단되고 `k_panic()`으로 정지한다. 추적 상태는
`nu54_m2_runtime_trace` C symbol로 ELF에 남겨 이후 debugger/HIL 자동화에서 사용할 수 있다.

### 6.2 육안 계측

기존 실기 시험에서는 runtime 판정을 육안으로 확인하기 위해 보드 package의
`DT_ALIAS(led0)`를 Zephyr GPIO API로 직접 토글하는 계측을 사용했다.

- `setup()`에서 LED GPIO device와 출력 설정을 검증한다.
- `loop()`마다 LED0를 토글하고 Zephyr `k_msleep(250)`으로 250 ms 대기한다.
- constructor, `setup()`, `loop()` 조건 또는 GPIO 동작이 실패하면 panic한다.
- 사용자가 실제 NU54DK에서 지속적인 빠른 LED0 점멸을 육안으로 확인했다.

따라서 exact image에서 전역 생성자 선행 실행, `setup()` 단일 호출, 반복 `loop()`와 Zephyr
kernel sleep이 함께 동작했다. 여기서 사용한 `gpio_pin_toggle_dt()`와 `k_msleep()`은 시험
계측이며 Arduino GPIO/time API의 구현 증거가 아니다.

### 6.3 Flash 결과와 이번 재검증 범위

사용자는 이전 M2 runtime image를 기본 pyOCD 경로로 실행해 250 ms LED0 점멸을 확인했다.
이번 clean revision 갱신은 요청 범위를 pristine build로 제한했으며 새
`16394D224AFCD655BE06EAC0AD81BA68644B3A404A98BE7C4AE9ABCDA6C11D2B`
HEX를 장치에 다시 기록하지 않았다.

| 항목 | 결과 |
| --- | --- |
| 이번 재검증 | build-only, flash 미수행 |
| 생성 runner | 기본 flash/debug `pyocd`; 인자 `--dt-flash=y`, `--target=nrf54l` |
| 기존 실행 확인 | 사용자가 250 ms 간격 LED0 점멸 확인 |

---

## 7. 알려진 제약과 후속 항목

| 항목 | 판정 및 후속 조치 |
| --- | --- |
| revision 기준 | Core `a8d62ea75fef`, 보드 `fe65f2f0880b` clean provenance를 확보했다. 보드 서브모듈은 읽기 전용이다. |
| UART/VCOM | M1과 마찬가지로 출력 byte를 확보하지 못했다. M2는 자체 판정과 LED HIL로 통과했으며 Serial 단계에서 VCOM을 추적한다. |
| runtime trace 자동 수집 | 실행 중 AP attach와 RAM trace 회수가 미완료다. M8 debug/HIL 자동화에서 다시 다룬다. |
| Windows CMake 재구성 | source 변경으로 CMake를 강제 재실행했을 때 NCS 생성 `extra_kconfig_options.conf`의 string quoting 경고가 Kconfig 오류로 승격됐다. 일반 C/C++ 변경은 provenance target과 Ninja 증분 compile만 사용한다. CMake/Kconfig를 바꾸면 현재 NCS v3.4.0 Windows 기준으로 pristine build한다. |
| 표준 `build_info.yml` | Zephyr 소유 canonical snapshot이며 configure 이후에는 Core가 수정하지 않는다. 최신 Core·애플리케이션·보드 source tree의 보조 판정은 별도 live record를 사용하되 최종 image SHA-256을 대체하지 않는다. |
| main thread fairness | M2는 구조를 단순화하기 위해 Zephyr main thread를 사용한다. 빠르게 반환하는 `loop()`의 CPU 점유와 전용 thread 필요성은 M3에서 측정한다. |
| Arduino API | M2의 최소 `Arduino.h`는 `setup()`과 `loop()` 계약만 제공한다. 기존 Arduino library 호환을 선언하지 않는다. |

---

## 8. M2 판정

| 완료 기준 | 결과 | 증거 |
| --- | --- | --- |
| Zephyr module 발견과 opt-in Core link | 통과 | module symbol, 별도 Core archive와 map |
| `setup()` 한 번, `loop()` 반복 | 통과 | 내부 횟수 검사와 지속적인 250 ms LED0 점멸 |
| 전역 C++ constructor 선행 실행 | 통과 | `.init_array`, runtime signature 검사와 LED HIL |
| Core 비활성 앱에 불필요한 symbol 없음 | 통과 | `hello_world` negative clean build |
| NCS, Toolchain, Core와 board revision 기록 | 통과 | live record에 clean revision과 source SHA 기록 |
| C++17 이상과 사용자 C++ 정책 | 통과 | C++20 및 common libc malloc을 포함한 full libstdc++ + exception/RTTI pristine link |
| 변경 없는 증분 build | 기존 회귀 통과 | 이번 기준선 갱신은 pristine build만 수행 |

**M2 완료.** M2의 module·runtime 구조, Core 비활성 회귀, C++20과 full C++
정책 build를 clean Core·보드 revision으로 다시 확인했다. 기존 NU54DK runtime 실기
증거와 이번 pristine build 증거를 구분해 기록했으며, 보드 서브모듈은 변경하지 않았다.
