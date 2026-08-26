# M2 Zephyr module과 Arduino runtime 기준선

| 항목 | 내용 |
| --- | --- |
| 검증 결과 | **CONDITIONAL GO** — 로컬 build·link·실기 통과, 기준 commit 고정 대기 |
| 검증일 | 2026-08-26 (Asia/Seoul) |
| 작성자 | Quantum / NUCODE |
| 대상 구조 | Loader/LLEXT 없는 Native Full Zephyr 정적 이미지 |
| 대상 보드 | NU54DK |
| Zephyr 보드 타깃 | `nrf54l15dk/nrf54l15/cpuapp/nu54dk` |
| Core 기준 revision | `618cb3d56041135130615896c45bb04e467611c8` + M2 작업 트리 |
| 보드 package 기준 revision | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` + M1 runner 작업 트리 |
| 기본 연결 | 온보드 CMSIS-DAP + pyOCD |

> 검증한 M2 source와 보드 runner는 아직 commit되지 않았다. live build record는 두
> revision을 `-dirty`로 표시하고 Core, 애플리케이션과 보드 입력의 SHA-256도 기록한다.
> 이 값은 build 실행 시점의 Core·애플리케이션·보드 source tree 상태를 보조 식별한다.
> ELF와의 원자적 결합, NCS·Zephyr 작업 트리 변경 또는 clean clone에서 동일 source를
> 내려받는 것까지 보장하지 않는다.
> 배포 기준선은 보드 package commit, 상위 submodule gitlink 갱신, Core commit과 clean
> rebuild를 마친 뒤 고정한다.

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
| FLASH | 30,552 B / 1,524 KB, 1.96% |
| RAM | 6,856 B / 256 KB, 2.62% |
| `zephyr.elf` | 1,119,364 B |
| `zephyr.hex` | 86,025 B |
| `zephyr.bin` | 30,552 B |
| no-change rebuild | provenance 확인 1개만 실행, C/C++ compile·link 0개, exit 0, 0.927초 |
| unchanged record | 내용과 timestamp 유지 |

| 산출물 | SHA-256 |
| --- | --- |
| `m2-runtime/zephyr/zephyr.elf` | `43409687BABED0EF38ACCA8AE397D9451A8029803C2CF321D6F499D12A728F7E` |
| `m2-runtime/zephyr/zephyr.hex` | `348D8FA69E01BEC82011E94996125BA4705E71A57E9801A0E24793B5F34BBCD7` |
| `m2-runtime/zephyr/zephyr.bin` | `0F8F3523562AB1EF71F889EF1244DCA81A9DE001D196F881CD9E7BE874DA946D` |

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

### 4.3 C++ 정책 확장 시험

Core Kconfig가 기준 sample의 정책을 모든 Sketch에 강제하지 않는지 두 clean build로
검증했다.

| 시험 | 결과 | 실제 compiler·link 증거 | FLASH / RAM |
| --- | --- | --- | --- |
| C++20 + minimal C++ | 성공 | 두 C++ TU 모두 `-std=c++20 -fno-exceptions -fno-rtti` | 30,552 B / 6,856 B |
| C++17 + full libstdc++ + exception + RTTI | 성공 | `-fno-*` 제거, `__EXCEPTIONS=1`, `__GXX_RTTI=1`, `libstdc++.a` link | 39,528 B / 6,896 B |

따라서 `STD_CPP_VERSION >= 201703`은 C++20을 정상 허용하고 exception/RTTI도
애플리케이션이 선택할 수 있다. full C++ 시험의 현재 image 비용은 기준 sample보다 FLASH
8,976 B, RAM 40 B 증가했다. 실제 `throw/catch`, `dynamic_cast`, `typeid` 실행 의미와 필요한
heap 정책은 아직 검증하지 않았으므로 이번 결과는 설정·compile·link 호환성으로 한정한다.

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
  core_revision: '618cb3d56041-dirty'
  core_source_sha256: '93bddb67a1d201127e32e6d4c5a2e263839ed2834c3db3c0ce042b7fcbac213b'
  application_source_sha256: 'a7e5792e8d73641983bca0c8e13a32d4a8a9e009c9ece0f795b6f4e9748dcd44'
  board_revision: 'fe65f2f0880b-dirty'
  board_source_sha256: '8267e572781e911fe3c7c77c4ff86b35648ea04b228cfa26e91bb6b44b463e41'
  ncs_revision: '99553055607b'
  zephyr_revision: 'bf801e4e3d19'
  board: 'nrf54l15dk'
  board_qualifiers: 'nrf54l15/cpuapp/nu54dk'
  toolchain_variant: 'zephyr'
  toolchain_path: '<LOCAL_TOOLCHAIN_PATH>'
  cxx_compiler: 'GNU 14.3.0'
```

NCS와 Zephyr revision은 고정 설치본의 HEAD를 기록한다. Core와 보드 package는 작업 트리
중 실제 build 소유 경로의 변경 여부를 검사하여 `-dirty`를 붙인다. 세 source SHA-256은
untracked 입력도 식별한다. 그러나 공개 사용자가 해당 내용을 받으려면 commit이 필요하므로
현재 판정을 CONDITIONAL GO로 유지한다. 이 보조 record는 최종 ELF target과 원자적으로
결합되지 않고 입력 glob이 실제 compile 대상보다 넓으며 NCS·Zephyr dirty state도 판정하지
않는다. 따라서 최종 image 식별은 아래의 산출물 SHA-256과 함께 사용해야 한다.

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

실행 중 nRF54L15의 application AP에 안정적으로 attach하여 RAM trace를 읽을 수 없었고,
`under-reset` 재연결은 관측하려는 RAM 상태를 초기화했다. M2에서는 runtime과 무관한
디버거 연결 문제로 판정을 막지 않기 위해 보드 package의 `DT_ALIAS(led0)`를 Zephyr GPIO
API로 직접 토글하는 계측을 추가했다.

- `setup()`에서 LED GPIO device와 출력 설정을 검증한다.
- `loop()`마다 LED0를 토글하고 Zephyr `k_msleep(250)`으로 250 ms 대기한다.
- constructor, `setup()`, `loop()` 조건 또는 GPIO 동작이 실패하면 panic한다.
- 사용자가 실제 NU54DK에서 지속적인 빠른 LED0 점멸을 육안으로 확인했다.

따라서 exact image에서 전역 생성자 선행 실행, `setup()` 단일 호출, 반복 `loop()`와 Zephyr
kernel sleep이 함께 동작했다. 여기서 사용한 `gpio_pin_toggle_dt()`와 `k_msleep()`은 시험
계측이며 Arduino GPIO/time API의 구현 증거가 아니다.

### 6.3 Flash 결과

변경된 M2 image의 최초 기록에서 8 sector, 32,768 B를 일반 sector erase하고 8 page,
32,768 B를 program한 뒤 실행했다. 현재 hash의 image를 다시 기본 runner로 flash했을 때는
동일한 8 page, 32,768 B를 비교 후 skip했고 exit 0으로 종료했다.

| 항목 | 결과 |
| --- | --- |
| runner | 생성된 기본 `pyocd` |
| rebuild | provenance 확인만 실행, C/C++ compile·link 없음 |
| 변경 image 기록 | 32,768 B, 8 sector erase 및 8 page program, exit 0, 11.082초 |
| 최종 비교 | 32,768 B, 8 page skip |
| 최종 비교 시간 | exit 0, 9.960초 |
| 명시적 전체 erase | 사용하지 않음 |
| recover | 사용하지 않음 |
| 실행 확인 | 사용자가 250 ms 간격 LED0 점멸 확인 |

일반 sector programming은 chip/mass erase와 다르다. M1에서 고정한
`auto_unlock=false`도 그대로 적용되어 잠긴 target을 일반 Flash가 자동으로 mass erase하지
않는다.

---

## 7. 알려진 제약과 후속 항목

| 항목 | 판정 및 후속 조치 |
| --- | --- |
| 작업 트리 revision | M2 신규 source와 보드 runner를 commit한 뒤 clean rebuild하여 manifest와 hash를 갱신한다. |
| UART/VCOM | M1과 마찬가지로 출력 byte를 확보하지 못했다. M2는 자체 판정과 LED HIL로 통과했으며 Serial 단계에서 VCOM을 추적한다. |
| runtime trace 자동 수집 | 실행 중 AP attach와 under-reset RAM 보존 문제가 있어 미완료다. M8 debug/HIL 자동화에서 다시 다룬다. |
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
| NCS, Toolchain, Core와 board revision 기록 | 조건부 통과 | canonical snapshot + live revision/source SHA, Core와 board는 `-dirty` |
| C++17 이상과 사용자 C++ 정책 | 통과 | C++20 및 full libstdc++ + exception/RTTI clean link |
| 변경 없는 증분 build | 통과 | runtime은 provenance 확인만, module-off는 `ninja: no work to do`; compile·link 0개 |

**결정 게이트: CONDITIONAL GO.** M2의 기술적 구조와 NU54DK 로컬 실기 경로는 모두
통과했으므로 M3 GPIO·시간 수직 PoC로 진행할 수 있다. 공개 재현 가능한 M2 GO로 닫으려면
다음 순서를 완료한다.

1. 보드 package의 M1 runner 변경을 commit한다.
2. 상위 Core 저장소의 submodule gitlink를 새 보드 commit으로 갱신한다.
3. M2 Core source와 문서를 commit한다.
4. clean checkout에서 runtime과 module-off를 다시 build·flash하고 revision과 hash를
   이 문서에 갱신한다.
