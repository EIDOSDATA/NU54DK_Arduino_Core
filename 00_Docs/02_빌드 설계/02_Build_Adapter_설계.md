# NU54DK Build Adapter 설계 — v0.1.0 기준선 / v0.2.0 확장

| 항목 | 내용 |
| --- | --- |
| 문서 상태 | `v0.1.0` build·upload·Boards Manager 실증 완료 — `v0.2.0` M13 profile UX 예정 |
| 현재 정식 버전 | `v0.1.0` |
| 다음 목표 버전 | `v0.2.0` |
| 작성자 | Quantum / NUCODE |
| 기준 SDK | nRF Connect SDK v3.4.0 |
| 기준 Zephyr | Zephyr 4.4.0 |
| 대상 호스트 | `v0.1.0`: Windows 10/11 x64 / `v0.2.0`: CI·지원 범위 확장 검토 |
| 최종 이미지 | Loader 없는 Native Full Zephyr 정적 이미지 |

---

## 1. 목적

Build Adapter는 Arduino의 build lifecycle과 NCS/Zephyr의 CMake·west build lifecycle을 연결하는 단일 중계 도구다.

Adapter의 목표는 Arduino를 별도의 firmware loader용 sketch compiler로 사용하는 것이 아니다. Arduino가 제공하는 다음 기능을 보존하면서 최종 산출물의 소유권을 Zephyr에 두는 것이다.

- `.ino` 전처리
- Arduino library discovery
- Arduino CLI 및 IDE의 표준 Build/Upload 동작
- sketch와 library source에 대한 증분 컴파일
- Boards Manager tool 호출 구조

최종 firmware에는 다음이 하나의 ELF로 정적 링크된다.

- Zephyr kernel
- NCS 및 선택된 Zephyr subsystem
- NU54DK board configuration
- Arduino Core 구현
- Arduino variant
- sketch
- 사용된 Arduino libraries

Loader, LLEXT, EDK, export symbol table 및 별도 sketch partition은 사용하지 않는다.

---

## 2. 범위

### 2.1 포함 범위

- NCS/Zephyr 환경 진단
- 패키지 기본 구성과 고급 sketch별 `prj.conf`/`app.overlay` 입력 처리
- `v0.2.0` M13의 profile·feature resolver가 생성한 resolved config 입력 처리
- `BOARD_ROOT` 및 `EXTRA_ZEPHYR_MODULES` 고정
- prebuild 단계의 Zephyr configure
- Arduino library discovery용 전처리
- C, C++, ASM 개별 compiler wrapper
- Arduino object를 고정 경로의 payload archive로 변환
- Zephyr CMake의 imported library로 payload 연결
- `recipe.c.combine` 시점의 최종 west build
- ELF, HEX, BIN, map 및 provenance manifest 내보내기
- size 출력
- pyOCD/J-Link flash 명령 중계
- 진단 가능한 오류 코드와 로그
- Windows 경로, 공백, Unicode 및 command length 처리
- 최초 pristine 이후 증분 빌드

### 2.2 고정 입력

| 항목 | 값 |
| --- | --- |
| Board target | `nrf54l15dk/nrf54l15/cpuapp/nu54dk` |
| Board root | `<repo>/board_package/NU54DK_Zephyr_DTS` |
| Zephyr module root | `<repo>` |
| Zephyr module CMake 변수 | `EXTRA_ZEPHYR_MODULES=<repo>` |
| NCS | `v3.4.0` |
| Zephyr | `4.4.0` |
| PoC sysbuild | `false`, `--no-sysbuild` |
| 기본 runner | `pyocd` |

### 2.3 M5에서 확정한 방식

2026-08-27 M5 실증에서는 imported Arduino object 방식을 사용하지 않고 **source manifest
방식**을 확정했다. Arduino compile recipe는 source/object 일대일 record와 lifecycle용 빈
object만 만들며, `recipe.c.combine`이 실제 object 목록에 대응하는 Sketch/library source를
`sources.cmake`로 전달한다. Zephyr app target이 해당 source를 현재 `autoconf.h`, Devicetree,
compiler ABI로 다시 컴파일한다.

Arduino Core와 Variant source는 Zephyr module이 단독으로 소유한다. Arduino가 Core lifecycle
중 만든 placeholder `core.a`는 final link 입력이 아니며, 이 구조에서 Core 중복 symbol 없이
NU54DK Full Zephyr ELF가 생성되는 것을 확인했다. object import와 source manifest를 동시에
지원하지 않는다.

---

## 3. 설계 원칙

1. **Zephyr가 최종 linker다.** Arduino linker가 독립 firmware를 만들지 않는다.
2. **prebuild에서는 구성만 한다.** 아직 생성되지 않은 `.ino.cpp`와 아직 발견되지 않은 library source를 빌드하려 하지 않는다.
3. **최종 west build는 `recipe.c.combine`에서 실행한다.** Arduino build graph에서 모든 sketch/library compile이 끝난 시점이다.
4. **동적 property 변경을 전제로 하지 않는다.** 실행된 hook은 이미 해석된 `platform.txt` property를 되돌려 바꿀 수 없다.
5. **모든 후속 recipe는 context file을 읽는다.** compiler 경로와 Zephyr flags를 `platform.txt`에 동적으로 주입하지 않는다.
6. **Core와 sketch의 configuration은 동일해야 한다.** 동일한 `autoconf.h`, Devicetree 및 ABI flags를 사용한다.
7. **일반 build에서 pristine을 사용하지 않는다.** 최초 build directory 생성 또는 명시적 호환성 초기화에만 사용한다.
8. **일반 upload에서 mass erase를 사용하지 않는다.** 복구는 별도 명령과 사용자 의도로 분리한다.
9. **경로는 구조화된 인자로 전달한다.** shell 문자열 조립과 `cmd /c` 의존을 최소화한다.
10. **실패는 원인 단계에서 중단한다.** 환경, configure, compile, link, export, flash 오류를 구분한다.

---

## 4. 전체 구조

~~~text
Arduino IDE / Arduino CLI
        │
        │ platform.txt recipes
        ▼
tools/nu54-builder
  ├─ doctor
  ├─ prepare
  ├─ preprocess
  ├─ compile
  ├─ archive
  ├─ link
  ├─ export
  ├─ size
  └─ flash
        │
        ├──────────────► NCS v3.4.0 toolchain
        │                 ├─ west
        │                 ├─ CMake/Ninja
        │                 └─ target compiler/binutils
        │
        ├──────────────► NU54DK Zephyr board package
        │
        └──────────────► persistent/ephemeral build context
                          ├─ context.json
                          ├─ response files
                          ├─ arduino_payload.a
                          └─ zephyr-build/zephyr/zephyr.*
~~~

Adapter는 Arduino CLI 자체를 재귀 호출하지 않는다. 이미 실행 중인 Arduino build 안에서 recipe command로 동작한다.

---

## 5. 하위 명령 계약

### 5.1 `doctor`

목적은 build를 변경하지 않고 환경 사용 가능성을 진단하는 것이다.

입력:

- platform root
- 선택적 NCS root 또는 toolchain hint
- board target
- board root
- module root
- 선택 runner

출력:

- NCS version
- Zephyr version
- Python, west, CMake, Ninja 및 compiler 절대 경로
- board target 발견 여부
- Zephyr module 발견 여부
- pyOCD/J-Link 실행 파일과 runner 사용 가능성
- JSON 진단 결과와 사람이 읽는 요약

계약:

~~~text
nu54-builder doctor
  --platform-root <path>
  --board-root <path>
  --module-root <path>
  --board nrf54l15dk/nrf54l15/cpuapp/nu54dk
  [--ncs-root <path>]
  [--runner pyocd|jlink]
~~~

`doctor`는 package, NCS 설치 또는 사용자 환경을 수정하지 않는다.

### 5.2 `prepare`

목적은 Arduino library discovery보다 먼저 Zephyr configure를 완료하고 모든 compile recipe가 읽을 불변 context를 만드는 것이다.

입력:

- `{build.path}`
- `{build.source.path}`
- `{runtime.platform.path}`
- `{build.core.path}`
- `{build.variant.path}`
- `{build.fqbn}`
- board target
- platform version
- 선택된 Arduino menu options

처리:

1. 입력 경로 canonicalization
2. NCS v3.4.0 환경 탐색 및 검증
3. 패키지 기본 config와 sketch의 고급 선택 `prj.conf`/`app.overlay` 탐색
4. Adapter 기본 config와 sketch config의 결정적 병합 순서 확정; M13 이후는 resolved profile·feature fragment도 포함
5. cache key 계산
6. build lock 획득
7. 최초 build라면 placeholder payload archive 생성
8. Zephyr application template materialization
9. 최초에만 pristine configure
10. `west build --cmake-only --no-sysbuild` 실행
11. C/C++/ASM compiler와 flags 추출
12. `context.json`과 response file의 원자적 기록
13. lock 해제

출력:

~~~text
<context-root>/
├─ context.json
├─ c.rsp
├─ cxx.rsp
├─ asm.rsp
├─ preprocess.rsp
├─ input-manifest.json
├─ arduino_payload.a
├─ app/
│  ├─ CMakeLists.txt
│  ├─ prj.conf
│  ├─ app.overlay                 # 존재할 때
│  └─ src/arduino_entry.cpp
└─ zephyr-build/
   ├─ CMakeCache.txt
   ├─ build.ninja
   └─ zephyr/
      ├─ .config
      └─ zephyr.dts
~~~

`prepare`는 sketch compile, link, flash를 수행하지 않는다.

### 5.3 `preprocess`

목적은 Arduino library discovery와 prototype 처리에 필요한 전처리 결과를 생성하는 것이다.

입력:

- context file
- source file
- preprocessed output file
- Arduino `{includes}`
- library discovery phase 값

처리:

- context의 C++ compiler 사용
- Zephyr C++ compile ABI와 동일한 전처리 관련 flags 사용
- `-E -CC` 적용
- `ARDUINO`, `ARDUINO_ARCH_ZEPHYR`, board macro 적용
- `{includes}` 적용
- discovery phase macro 적용
- dependency 생성 전용 flags 중 전처리 output과 충돌하는 항목 제거

출력:

- `{preprocessed_file_path}`
- 전처리 오류의 compiler-compatible diagnostic

정상 동작에서 Adapter의 정보 로그를 stdout에 섞지 않는다. Arduino library discovery가 compiler output을 오해하지 않도록 진단 로그는 stderr 또는 별도 log file로 보낸다.

### 5.4 `compile`

목적은 Arduino가 선택한 sketch와 library source를 Zephyr와 ABI-compatible한 object로 만드는 것이다.

입력:

- `--lang c|cxx|asm`
- context file
- source file
- object file
- Arduino `{includes}`
- Arduino extra flags

처리:

1. context signature 검증
2. 언어별 compiler와 response file 선택
3. Arduino compile definitions 추가
4. source 및 output path 인용
5. `.o`와 `.d` 생성
6. child compiler exit code 전달

출력:

- `{object_file}`
- `{object_file}.d` 또는 Arduino CLI가 인식하는 dependency file

Adapter는 source file별 독립 프로세스로 병렬 실행될 수 있어야 한다. `compile`은 공용 context를 읽기만 하고 수정하지 않는다.

### 5.5 `archive`

목적은 Arduino build lifecycle이 요구하는 Core archive 단계를 충족하는 것이다.

첫 설계에서는 실제 Arduino Core 구현을 Zephyr module이 빌드한다. `cores/arduino`의 source가 Arduino CLI에도 보이면 Core가 중복 컴파일될 수 있으므로 다음 중 하나를 PoC에서 확정해야 한다.

1. Arduino core folder를 공개 header와 최소 stub로 제한하고 실제 구현은 Zephyr module에서만 등록
2. Arduino가 생성한 Core archive도 payload에 포함하되 전역 Core cache가 sketch별 Kconfig를 잘못 재사용하지 않도록 강제 무효화

우선 권장안은 1번이다. `archive`는 Arduino CLI가 요구하는 archive file을 올바른 target `ar`로 만들지만 최종 Zephyr link에 어떤 archive를 포함할지는 context 정책에 따른다.

### 5.6 `link`

목적은 Arduino의 개별 compile 결과를 Zephyr 전체 firmware에 포함하고 최종 산출물을 만드는 것이다.

호출 시점은 `recipe.c.combine.pattern`이다.

입력:

- context file
- `{object_files}`
- `{archive_file_path}`
- `{compiler.libraries.ldflags}`가 필요한 경우 그 구조화된 표현
- project name
- Arduino build output path

처리:

1. context와 현재 build input의 일치 확인
2. object list 정규화와 중복 제거
3. 지원하지 않는 precompiled library 발견 시 명시적 실패
4. target `ar`로 새 `arduino_payload.a` 작성
5. archive를 임시 파일에 쓴 후 원자적으로 교체
6. `west build -d <zephyr-build>` 실행
7. Zephyr link 결과 검사
8. `zephyr.elf`, HEX, BIN, map을 Arduino 이름으로 export
9. artifact manifest 기록

Zephyr application template은 payload의 고정 경로를 다음과 같은 방식으로 가져오는 것을 우선 검증한다.

~~~cmake
zephyr_library_import(
  arduino_payload
  "${ARDUINO_PAYLOAD_ARCHIVE}"
)
~~~

placeholder archive가 configure 전에 존재해야 하며, 최종 `link`에서 교체된 mtime을 Ninja가 감지해 link를 다시 수행해야 한다.

첫 PoC에서는 LTO와 사전 컴파일 Arduino library 지원을 비활성화하여 imported object 경계를 먼저 검증한다.

### 5.7 `export`

목적은 Zephyr 표준 산출물을 Arduino의 예상 이름과 export 위치로 복사하는 것이다.

입력:

- context
- project name
- output directory
- export format

출력:

~~~text
<arduino-build>/<project>.elf
<arduino-build>/<project>.hex
<arduino-build>/<project>.bin
<arduino-build>/<project>.map
<arduino-build>/<project>.nu54-build.json
~~~

복사는 임시 파일을 거쳐 원자적으로 완료한다. 부분 파일이 기존 정상 산출물을 덮어쓰지 않게 한다.

### 5.8 `size`

Arduino IDE가 파싱할 수 있는 안정적인 형식으로 크기를 출력한다.

예시 계약:

~~~text
NU54_FLASH_USED=30600
NU54_FLASH_TOTAL=1462272
NU54_RAM_USED=5952
NU54_RAM_TOTAL=192512
~~~

위 total 값은 현재 NU54DK board metadata의 기본 CPUAPP 가용량인 1428 KiB Flash와 188 KiB RAM을 byte로 표현한 예시다. 실제 release 값은 선택된 linker region과 기본 profile을 검증하여 확정하며, 물리 RRAM/SRAM 전체 크기를 그대로 사용하지 않는다. used 값은 Zephyr map, ELF section 또는 Zephyr memory report에서 얻는다. 문자열 regex 계약은 `platform.txt`와 함께 versioning한다.

### 5.9 `flash`

목적은 선택 runner로 이미 생성된 전체 Zephyr image를 플래시하는 것이다.

입력:

- context 또는 artifact manifest
- runner `pyocd|jlink`
- 선택적 probe id
- reset policy

일반 동작:

~~~text
west flash -d <zephyr-build> -r <runner>
~~~

일반 `flash`에 `--erase`, recover 또는 mass erase를 암묵적으로 추가하지 않는다.

---

## 6. 입력·출력 계약

### 6.1 sketch 입력 규칙

Adapter는 `{build.source.path}`에서 다음 선택 파일을 찾는다.

`v0.1.0`의 일반 Build/Upload는 아래 sidecar가 없어도 패키지 기본 구성으로 동작한다.
직접 `prj.conf`/`app.overlay`를 두는 방식은 고급 Zephyr 확장과 `v0.1.0` 검증 예제의
역사적 입력이다. `v0.2.0` M13은 일반 기능 선택을 Arduino Tools 메뉴와
profile·feature resolver로 이동하며, sidecar를 일반 사용자에게 필수로 요구하지 않는다.

| 파일 | 의미 | 없을 때 |
| --- | --- | --- |
| `prj.conf` | 고급 sketch 전용 Kconfig fragment | platform/profile 기본 config만 사용 |
| `app.overlay` | 고급 sketch 전용 Devicetree overlay | board DTS와 profile 기본 overlay 사용 |
| `boards/<target>.overlay` | 향후 복수 보드 overlay | 첫 버전에서는 지원하지 않음 |
| `sysbuild.conf` | sysbuild 입력 | 첫 버전에서는 오류 또는 무시가 아닌 명시적 비지원 |

설정 병합 순서는 결정적이어야 한다.

~~~text
Core 기본 prj.conf
  → NU54DK variant 기본 fragment
  → M13 resolved profile/feature fragment      # v0.2.0 이후
  → sketch/prj.conf                            # 고급 선택
~~~

Devicetree는 다음 순서를 사용한다.

~~~text
NU54DK board DTS
  → Core 기본 overlay가 있을 때
  → M13 resolved profile/feature overlay       # v0.2.0 이후
  → sketch/app.overlay                        # 고급 선택
~~~

### 6.2 `context.json`

최소 schema 예시는 다음과 같다.

~~~json
{
  "schema_version": 1,
  "adapter_version": "<platform-version>",
  "state": "configured",
  "fqbn": "nucode:zephyr:nu54dk",
  "board": "nrf54l15dk/nrf54l15/cpuapp/nu54dk",
  "sysbuild": false,
  "ncs_version": "v3.4.0",
  "zephyr_version": "4.4.0",
  "repo_root": "C:/path/NU54DK_Arduino_Core",
  "board_root": "C:/path/NU54DK_Arduino_Core/board_package/NU54DK_Zephyr_DTS",
  "module_root": "C:/path/NU54DK_Arduino_Core",
  "sketch_root": "C:/path/Blink",
  "zephyr_build_dir": "C:/cache/key/zephyr-build",
  "payload_archive": "C:/cache/key/arduino_payload.a",
  "compiler": {
    "c": "C:/ncs/toolchain/bin/arm-zephyr-eabi-gcc.exe",
    "cxx": "C:/ncs/toolchain/bin/arm-zephyr-eabi-g++.exe",
    "ar": "C:/ncs/toolchain/bin/arm-zephyr-eabi-ar.exe"
  },
  "response_files": {
    "c": "C:/cache/key/c.rsp",
    "cxx": "C:/cache/key/cxx.rsp",
    "asm": "C:/cache/key/asm.rsp",
    "preprocess": "C:/cache/key/preprocess.rsp"
  },
  "input_fingerprint": "sha256:...",
  "configured_at_utc": "2026-08-26T00:00:00Z"
}
~~~

JSON에는 secret을 기록하지 않는다. 경로는 Unicode를 보존하고 `/` 구분자로 canonicalize한다.

### 6.3 response file

- compiler 인자 하나를 손실 없이 표현해야 한다.
- 공백과 비ASCII 문자를 포함한 경로를 지원해야 한다.
- source와 output path는 공용 response file에 넣지 않는다.
- `-MMD`, `-MF`, `-o`, `-c`처럼 source별로 달라지는 인자는 `compile`이 추가한다.
- host shell용 quoting과 GCC response-file quoting을 혼동하지 않는다.
- context fingerprint가 다른 response file을 재사용하지 않는다.

### 6.4 artifact manifest

`<project>.nu54-build.json`에는 다음을 기록한다.

- artifact별 절대 경로, SHA-256 및 크기
- NCS, Zephyr, Core, board package 및 Adapter version
- board target과 FQBN
- config/overlay hash
- runner 기본값
- sysbuild 사용 여부
- build timestamp
- source repository commit이 확인 가능한 경우 commit id

---

## 7. 세부 처리 흐름

~~~text
Arduino build 시작
        │
        ▼
prebuild: prepare
  ├─ doctor subset
  ├─ cache key/lock
  ├─ placeholder archive
  └─ west --cmake-only --no-sysbuild
        │
        ▼
Arduino .ino 전처리 및 library discovery
  └─ recipe.preproc.macros → preprocess
        │
        ▼
Arduino sketch/library compile
  ├─ C → compile --lang c
  ├─ C++ → compile --lang cxx
  └─ ASM → compile --lang asm
        │
        ▼
Arduino core archive 단계
  └─ archive
        │
        ▼
recipe.c.combine → link
  ├─ arduino_payload.a 갱신
  ├─ west build -d <cache>
  ├─ Native Full Zephyr link
  └─ artifacts export
        │
        ▼
size → Arduino IDE 결과 표시
        │
        ▼
Upload 요청 시 flash
~~~

`recipe.hooks.linking.prelink`에서 west를 실행하고 별도의 정상 linker recipe까지 이어지는 구조는 사용하지 않는다. 최종 link 자체가 `recipe.c.combine`의 책임이다.

---

## 8. Core 소유권과 중복 방지

Arduino build system은 `cores/<core>` 아래의 source를 자동으로 컴파일하고 전역 Core cache를 사용할 수 있다. 그러나 Full Zephyr에서는 Core compile option이 sketch의 Kconfig와 Devicetree에 영향을 받는다.

전역 Core cache가 잘못 재사용되면 다음 문제가 발생한다.

- `CONFIG_*`가 다른 Core object 재사용
- generated header와 object ABI 불일치
- logging, C++ library, USB, BLE 설정 차이 누락
- Devicetree-dependent inline 또는 compile-time constant 불일치

따라서 첫 구현의 권장 소유권은 다음과 같다.

| 영역 | 빌드 주체 |
| --- | --- |
| Arduino 공개 header | Arduino core include path와 Zephyr module 모두에서 참조 |
| Arduino Core 구현 `.cpp` | Zephyr CMake module |
| Variant 구현 | Zephyr CMake module |
| 생성된 `.ino.cpp` | Adapter compiler wrapper |
| 발견된 Arduino library source | Adapter compiler wrapper |
| Zephyr kernel/NCS subsystem | Zephyr CMake/Ninja |
| 최종 link | Zephyr CMake/Ninja |

이 구조가 Arduino CLI에 빈 Core 또는 header-only Core로 허용되는지는 PoC 검증 항목이다. 필요하다면 기능 없는 최소 stub와 archive를 제공하되 최종 firmware에는 중복 구현을 넣지 않는다.

---

## 9. Windows 우선 구현 규칙

### 9.1 실행 환경

- Arduino IDE 프로세스가 NCS environment를 상속한다고 가정하지 않는다.
- 시스템 PATH의 `python`, `west`, CMake 또는 compiler를 무조건 사용하지 않는다.
- Adapter는 검증된 NCS toolchain의 절대 경로를 사용한다.
- PoC 단계에서만 NCS terminal 실행을 전제할 수 있다.
- 공개 배포 Adapter는 자체 launcher 또는 Boards Manager tool package 형태를 사용한다.

### 9.2 경로

- `Path` API로 결합하고 문자열 `\` 연결을 피한다.
- CMake cache 인자는 `/`로 정규화한다.
- 원본 path의 대소문자와 Unicode를 손실하지 않는다.
- 공백, 괄호, `&`, 한글이 포함된 경로를 시험한다.
- `cmd /c`, `&&`, 임시 batch file에 의존하지 않는다.

### 9.3 명령 길이

`{object_files}`와 `{includes}`는 길어질 수 있다. 첫 PoC에서는 Arduino가 일반 linker에도 전달하는 범위 안에서 직접 인자를 허용하되, production Adapter는 다음을 제공해야 한다.

- object list response file 또는 manifest
- compiler response file
- child process argument array 실행
- command string 재파싱 최소화

### 9.4 동시 실행

- context 작성은 lock 안에서 수행한다.
- compile은 context read-only다.
- payload archive는 임시 파일에 생성 후 replace한다.
- 같은 cache key의 link는 직렬화한다.
- 다른 sketch/cache key는 병렬 build 가능해야 한다.
- Windows named mutex 또는 POSIX `flock`을 lock 권위로 사용하고 process 종료 시 운영체제의
  자동 회수에 맡긴다. PID·host·timestamp JSON은 진단 정보로만 사용한다.

---

## 10. 오류 처리

### 10.1 오류 분류

| 코드 계열 | 의미 | 예시 |
| --- | --- | --- |
| `E_ENV_*` | NCS/도구 환경 오류 | west 없음, version 불일치 |
| `E_INPUT_*` | 입력·경로 오류 | sketch 없음, 잘못된 board root |
| `E_CONFIG_*` | CMake/Kconfig/DTS 오류 | configure 실패, overlay 오류 |
| `E_PREPROC_*` | Arduino 전처리·library discovery 오류 | header 탐색 실패 |
| `E_COMPILE_*` | source compile 오류 | C++ ABI flag 오류 |
| `E_ARCHIVE_*` | archive 오류 | object 누락, `ar` 실패 |
| `E_LINK_*` | Zephyr link 오류 | undefined symbol, payload 미반영 |
| `E_EXPORT_*` | 산출물 오류 | ELF/HEX 누락, copy 실패 |
| `E_CACHE_*` | cache/lock 오류 | signature 불일치, lock timeout |
| `E_RUNNER_*` | runner 오류 | pyOCD/J-Link 미등록 |
| `E_FLASH_*` | probe/flash 오류 | probe 없음, target 접근 실패 |

### 10.2 오류 출력 schema

사람이 읽는 메시지는 다음 정보를 포함한다.

~~~text
[NU54:E_CONFIG_BOARD_NOT_FOUND]
NU54DK board target을 찾지 못했습니다.
board: nrf54l15dk/nrf54l15/cpuapp/nu54dk
board_root: C:/.../board_package/NU54DK_Zephyr_DTS
next: 서브모듈과 BOARD_ROOT 경로를 확인하십시오.
log: C:/.../logs/prepare.log
~~~

JSON mode에서는 code, phase, message, detail, next_action, log_path 및 child_exit_code를 구조화한다.

### 10.3 실패 원칙

- version 불일치를 경고만 하고 계속하지 않는다.
- sysbuild가 의도치 않게 활성화되면 PoC 단계에서는 실패한다.
- 지원하지 않는 precompiled Arduino library를 조용히 누락하지 않는다.
- J-Link 미등록 시 pyOCD로 자동 fallback하지 않는다.
- flash 실패 시 자동 mass erase를 실행하지 않는다.
- 이전 성공 artifact를 실패한 partial output으로 덮어쓰지 않는다.

---

## 11. 완료 기준

Build Adapter v0의 전체 설계 기준은 다음과 같다. M5는 1~11의 build 경로를 검증하며,
12번 flash는 사용자의 단계 경계에 따라 M8에서 검증한다.

1. `doctor`가 NCS v3.4.0, Zephyr 4.4.0 및 board target을 검증한다.
2. `prepare`가 Arduino prebuild 시점에서 configure-only build를 생성한다.
3. Arduino library discovery가 Adapter preprocessor로 동작한다.
4. 최소 Blink `.ino.cpp`가 Adapter compiler로 object가 된다.
5. payload archive가 Zephyr CMake에 포함된다.
6. `recipe.c.combine`에서 Native Full Zephyr ELF/HEX를 생성한다.
7. ELF에 sketch, Core와 Zephyr kernel symbol이 함께 존재한다.
8. LLEXT와 loader artifact가 생성되지 않는다.
9. 첫 configure 이후 일반 sketch 변경에서 kernel 전체를 다시 빌드하지 않는다.
10. 공백과 한글이 포함된 Windows path에서 성공한다.
11. 오류 단계와 해결 방향이 IDE console에 표시된다.
12. **M8 범위:** 일반 `flash`가 mass erase 없이 pyOCD로 성공한다.

---

## 12. 검증 체크리스트 — 역사적 설계 수락 기준

아래 체크박스는 M5 설계 당시의 수락 기준을 보존한다. 현재 완료 판정은
`v0.1.0` 릴리스와 M5~M11 검증 기록이 소유하므로, 아래의 미체크 표기를
현재 미완료 상태로 해석하지 않는다.

### 12.1 명령과 context

- [ ] 모든 Adapter 하위 명령에 `--help`가 있다.
- [ ] `doctor --json` 결과가 machine-readable하다.
- [ ] `context.json` schema version이 검증된다.
- [ ] NCS/Zephyr version 불일치가 차단된다.
- [ ] `BOARD_ROOT`와 module root가 canonicalize된다.
- [ ] `sysbuild=false`가 context와 CMake cache에 일치한다.

### 12.2 전처리와 compile

- [ ] `.ino` prototype 생성 후 source가 정상 compile된다.
- [ ] library discovery phase에서 오류 없는 preprocessor output을 생성한다.
- [ ] C, C++ 및 ASM source가 각각 compile된다.
- [ ] `.d` dependency file이 Arduino 증분 판단에 사용된다.
- [ ] `autoconf.h` 변경이 관련 object 재빌드를 유도한다.
- [ ] 병렬 compile이 context를 손상시키지 않는다.

### 12.3 link와 산출물

- [ ] payload archive가 실제 final ELF에 포함된다.
- [ ] `setup()`과 `loop()` undefined symbol이 없다.
- [ ] Core 구현이 중복 링크되지 않는다.
- [ ] `zephyr.elf`, HEX, BIN 및 map을 내보낸다.
- [ ] artifact manifest의 hash가 실제 파일과 일치한다.
- [ ] Loader/LLEXT artifact가 없다.

### 12.4 Windows

- [ ] NCS terminal에서 동작한다.
- [ ] 일반 Arduino IDE process에서도 NCS environment를 찾는다.
- [ ] 공백 경로에서 동작한다.
- [ ] 한글 경로에서 동작한다.
- [ ] 긴 include/object list를 처리한다.
- [ ] 동일 cache key 동시 link가 직렬화된다.

---

## 13. 범위 제외

초기 Build Adapter에서는 다음을 지원하지 않는다.

- LLEXT 또는 Loader firmware 생성
- ArduinoCore-zephyr EDK 호환
- sysbuild/multi-image
- MCUboot, DFU, OTA 및 secure boot
- precompiled Arduino libraries
- LTO
- 분산 build 또는 remote cache
- Linux/macOS production package
- Arduino IDE 1.x
- PlatformIO 통합
- debugger UI 자동 구성
- mass erase 또는 recover 자동 실행
- 사용자 NCS 설치 자동 변경

---

## 14. 참고문헌

- [Arduino Platform Specification](https://docs.arduino.cc/arduino-cli/platform-specification/)
- [Arduino Sketch Build Process](https://docs.arduino.cc/arduino-cli/sketch-build-process)
- [ArduinoCore-zephyr platform.txt — 기준 commit](https://github.com/arduino/ArduinoCore-zephyr/blob/514a21feaa0fd62c3922243cba1a5a98f9f5fdf1/platform.txt)
- [ArduinoCore-zephyr README — 기준 commit](https://github.com/arduino/ArduinoCore-zephyr/tree/514a21feaa0fd62c3922243cba1a5a98f9f5fdf1)
- [nRF Connect SDK v3.4.0 Release Notes](https://github.com/nrfconnect/sdk-nrf/blob/v3.4.0/doc/nrf/releases_and_maturity/releases/release-notes-3.4.0.rst)
- [Zephyr 4.4.0 Build System](https://docs.zephyrproject.org/4.4.0/build/cmake/index.html)
- [Zephyr 4.4.0 west build, flash and debug](https://docs.zephyrproject.org/4.4.0/develop/west/build-flash-debug.html)
- [Zephyr 4.4.0 CMake extension source: `zephyr_library_import`](https://github.com/zephyrproject-rtos/zephyr/blob/v4.4.0/cmake/modules/extensions.cmake)
- [Zephyr 4.4.0 Modules](https://docs.zephyrproject.org/4.4.0/develop/modules.html)
- [Arduino Package Index Specification](https://arduino.github.io/arduino-cli/latest/package_index_json-specification/)
