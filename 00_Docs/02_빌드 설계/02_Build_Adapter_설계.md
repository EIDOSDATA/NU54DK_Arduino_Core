# NU54DK Build Adapter 설계 — v0.3.0

| 항목 | 내용 |
| --- | --- |
| 문서 상태 | **현재 구현 계약** |
| 현재 정식 버전 | `v0.3.0` |
| 다음 목표 버전 | `v0.4.0` |
| 기준 SDK | nRF Connect SDK v3.4.0 / Zephyr 4.4.0 |
| 공식 호스트 | Windows 10/11 x64 |
| 최종 이미지 | Loader/LLEXT 없는 단일 Full Zephyr 이미지 |

Build Adapter는 Arduino의 전처리·library discovery lifecycle을 보존하면서 실제 컴파일과 최종
링크를 Zephyr CMake/Ninja에 맡기는 중계 도구다. 현재 구현의 단일 원본은 다음 파일이다.

- `platform.txt`
- `tools/nu54-builder/nu54-builder.cmd`
- `tools/nu54-builder/src/nu54_builder.py`
- `tools/nu54-builder/templates/zephyr-app/`

이 문서는 현재 **source manifest 방식**만 설명한다. 초기 설계의 imported object,
`arduino_payload.a`, compiler response file, `compile`, `export`, `doctor` 하위 명령은 현재
구현 계약이 아니므로 사용하지 않는다.

## 1. 설계 목표

Adapter는 다음 경계를 유지한다.

- Arduino CLI가 `.ino` 결합, prototype 생성과 library 선택을 수행한다.
- Arduino compile recipe는 source graph를 기록할 뿐 target object를 컴파일하지 않는다.
- Core와 Variant는 Zephyr module이 한 번만 컴파일한다.
- Sketch와 선택된 Arduino library source도 최종 Zephyr app target에서 컴파일한다.
- 모든 source는 같은 `autoconf.h`, Devicetree와 NCS compiler ABI를 사용한다.
- `recipe.c.combine`에서 west 최종 build와 산출물 publish를 한 번 수행한다.
- 최초 cache identity만 pristine configure하고 이후에는 Ninja 증분 build를 사용한다.
- 일반 Upload는 manifest를 검증하고 mass erase/recover 없이 실행한다.

최종 firmware에는 Zephyr kernel, 선택 subsystem, NU54DK board 설정, Core, Variant, Sketch와
선택 library가 하나의 ELF로 정적 링크된다.

## 2. 현재 처리 흐름

```text
Arduino CLI / Arduino IDE
        │
        ├─ prebuild → prepare
        │              ├─ prerequisite와 target identity 검증
        │              ├─ provisional profile cache 선택
        │              └─ Zephyr configure-only + context.json
        │
        ├─ preprocess includes/macros
        │              └─ NCS C++ preprocessor로 Arduino discovery 지원
        │
        ├─ C/C++/ASM recipe → record
        │              ├─ source/object/include record 작성
        │              └─ Arduino lifecycle용 빈 object와 depfile 작성
        │
        ├─ Core archive recipe → archive
        │              └─ Arduino lifecycle용 빈 archive 보장
        │
        └─ combine recipe → link
                       ├─ object 목록과 source record 대조
                       ├─ 선택 bundled library/feature 해석
                       ├─ 최종 cache identity로 이관
                       ├─ generated source mirror와 sources.cmake 갱신
                       ├─ 필요한 경우 non-pristine 재구성
                       ├─ west/Ninja build
                       └─ ELF/HEX/BIN/map/context/manifest 원자적 publish
```

Arduino가 보는 `.o`와 `core.a`는 lifecycle token이다. 최종 ELF의 target code가 아니며
Zephyr link에 imported archive로 들어가지 않는다. `sources.cmake`가 현재 build에 실제로 선택된
Sketch/library source와 include root를 Zephyr app target에 전달한다.

## 3. 하위 명령 계약

현재 parser가 제공하는 명령은 다음과 같다.

| 명령 | 역할 | 주요 쓰기 위치 |
| --- | --- | --- |
| `prepare` | profile 기반 configure-only와 session context 준비 | session 및 persistent cache |
| `preprocess` | Arduino includes/macros discovery 출력 생성 | 요청한 preprocess output |
| `record` | source graph record와 빈 object/depfile 작성 | Arduino build path |
| `archive` | 빈 lifecycle archive 보장 | Arduino build path |
| `link` | source manifest, Ninja build와 산출물 publish | cache 및 Arduino build path |
| `verify-artifact` | objcopy 이후 현재 manifest의 artifact 무결성 확인 | 없음 |
| `size` | ELF에서 Arduino가 파싱할 FLASH/RAM 사용량 출력 | 없음 |
| `flash` | manifest와 probe를 검증해 west runner 실행 | flash log |
| `clean-build` | 현재 session이 가리키는 cache entry 제거 | 해당 entry와 session manifest |
| `cache` | `list/inspect/prune/remove/clear` 관리 | 선택한 cache 범위 |

각 recipe 명령에는 `--platform-root`, `--build-path`, `--sketch-root`, `--fqbn`,
`--project-name`, `--board`, `--profile` 공통 인자가 전달된다. Arduino가 넘긴 추가 인자는
명령별 allowlist로 제한한다.

### 3.1 `prepare`

`prepare`는 library discovery 전에 실행되므로 최종 library 목록을 아직 알 수 없다. 이 단계는
선택한 board/profile과 Sketch sidecar를 기준으로 provisional cache를 준비한다.

주요 작업은 다음과 같다.

1. platform, sketch와 build path canonicalization
2. 실행 환경 identity 확인: Boards Manager 배포 패키지는 exact NCS, Zephyr, Toolchain과
   board package pin을 검증하고, Git 개발 체크아웃은 감지한 실제 identity를 cache fingerprint에 기록
3. profile 및 Sketch의 선택적 `prj.conf`/`app.overlay` 검증
4. cache input manifest와 key 계산
5. app template materialization
6. 새 identity일 때 pristine configure-only 실행
7. `{build.path}/nu54-zephyr/context.json` 원자적 기록
8. 이전 source record와 placeholder 무효화

`prepare`는 Sketch compile, final link 또는 flash를 수행하지 않는다.

### 3.2 `preprocess`

`preprocess --mode includes`는 Arduino library discovery용 dependency 출력을, `--mode macros`는
prototype 처리용 `-E -CC` 출력을 만든다. NCS C++ compiler와 다음 public include를 사용한다.

- `cores/arduino`
- `variants/nu54dk`
- `third_party/ArduinoCore-API`
- Arduino가 전달한 `{includes}`

정보 로그를 stdout에 섞지 않는다. Arduino prototype 단계에서 직접 Zephyr/NCS header가 문제를
일으키는 source는 줄 수를 보존한 staging 입력을 사용하고 실제 header 해석은 최종 컴파일까지
보류한다.

### 3.3 `record`와 `archive`

`record`는 source와 Arduino object 경로를 일대일로 묶은 schema-versioned JSON을 작성한다.
언어, include root, platform root와 현재 cache key도 함께 기록한다. object는 반드시 Arduino
build directory 안에 있어야 한다.

빈 object와 depfile은 Arduino가 다음 lifecycle 단계로 진행하기 위한 placeholder다. 실제 C/C++
컴파일과 dependency 판정은 이후 Zephyr/Ninja가 수행한다. `archive`도 같은 이유로 빈 Core
archive가 존재하도록 할 뿐 Core 구현을 다시 묶지 않는다.

### 3.4 `link`

`link`는 Arduino가 전달한 `{object_files}`만 권위로 사용한다. 각 object에 대응하는 현재
source record가 없거나 cache identity가 다르면 실패한다. build directory를 재귀 scan해 stale
source를 추측하지 않는다.

처리 순서는 다음과 같다.

1. object 목록과 record schema/context 검증
2. 실제 선택된 bundled library와 feature manifest 해석
3. profile·feature를 포함한 최종 cache key 계산 및 필요 시 workspace 이관
4. Core/Variant record 제외와 Sketch/library source deduplication
5. Arduino 생성 source만 안정적인 cache mirror로 복사
6. 결정적인 `sources.cmake`와 provenance 생성
7. source 집합이 바뀐 경우 non-pristine CMake 재구성
8. `west build -d <zephyr-build>` 실행
9. ELF/HEX/BIN/map, context와 manifest를 하나의 generation으로 publish
10. 현재 entry를 보호한 상태에서 quota 기반 cache prune 시도

precompiled archive는 현재 지원하지 않는다. record가 없는 `.a`/`.ar`을 발견하면 조용히
누락하지 않고 실패한다.

### 3.5 `verify-artifact`, `size`, `flash`

Arduino objcopy recipe는 이미 publish된 HEX/BIN을 다시 만들지 않는다. `verify-artifact`가 현재
manifest의 path와 hash를 확인한다.

`size`는 Full Zephyr ELF를 target size tool로 읽고 다음 형식만 stdout에 출력한다.

```text
NU54_FLASH_USED=<bytes>
NU54_RAM_USED=<bytes>
```

`flash`는 [업로드와 디버그](./05_업로드와_디버그.md)의 manifest, runner, probe와 안전 계약을
따른다.

## 4. 구성 profile과 feature 해석

`boards.txt`의 `build.nu54_profile`이 기본 profile을 선택한다.

- `standard`: 표준 GPIO/Serial/Wire/SPI/ADC/PWM 구성
- `ble`: 표준 주변장치에 BLE NUS 사용 경계를 추가

설정 병합 순서는 다음과 같다.

```text
platform template
  → 선택 profile
  → 실제 선택된 allowlist bundled library feature
  → Sketch의 선택적 prj.conf / app.overlay
```

Feature는 Arduino source/include record에서 실제로 선택된 bundled library에 대해서만 활성화한다.
외부 library가 임의 `feature.yml`을 설치했다고 신뢰하지 않는다. profile, manifest와 fragment
내용은 최종 cache identity와 artifact provenance에 포함한다.

RC3의 기본 메모리 계약은 loaderless 단일 application 1,490,944 byte와 끝단 영구 저장소
68 KiB다. Adapter와 release gate는 Devicetree code partition, linker FLASH 범위와
`boards.txt` maximum size가 모두 `0x000000..0x16c000`을 가리키는지 확인해야 한다. 전문가
`app.overlay`가 마지막에 병합되더라도 이 경계를 조용히 우회하거나 Arduino size 표시만 바꾸는
구성은 지원하지 않는다. MCUboot/DFU dual-slot과 검증된 memory-layout 선택은 `v0.6.0` M36에서
cache·package identity에 포함할 별도 입력으로 추가한다.

## 5. 경로와 상태

Arduino session 상태는 다음 위치에 둔다.

```text
{build.path}/nu54-zephyr/
├─ context.json
├─ records/
├─ artifact-staging/
├─ publish-transactions/
└─ logs/
```

Persistent cache는 기본적으로 `%LOCALAPPDATA%/NU54/c` 아래에 schema별로 저장한다. 정확한
layout, key, lock과 prune 계약은 [빌드 캐시와 산출물](./04_빌드_캐시와_산출물.md)이 소유한다.

Context와 artifact manifest에는 secret을 기록하지 않는다. path는 Unicode를 보존하고 비교
전에 canonicalize한다. cache와 platform/board source tree가 겹치거나 UNC/network cache이면
실패한다.

## 6. Source 소유권

| 영역 | 실제 빌드 주체 |
| --- | --- |
| Arduino 전처리와 library 선택 | Arduino CLI + Adapter preprocessor |
| Arduino source graph record | Adapter `record` |
| Core와 Variant 구현 | Zephyr module/CMake/Ninja |
| Sketch와 선택 library source | generated `sources.cmake` + Zephyr app target |
| Zephyr kernel/NCS subsystem | Zephyr CMake/Ninja |
| 최종 link | Zephyr CMake/Ninja |

Core와 Variant를 Arduino archive와 Zephyr module 양쪽에서 중복 링크하지 않는다. 외부 library
source의 원래 private include 의미를 보존하기 위해 일반 외부 source는 원래 경로에서 컴파일하고,
Arduino build path의 생성 source만 cache mirror로 옮긴다.

## 7. 안전과 실패 원칙

- Boards Manager 배포 패키지에서는 exact prerequisite나 target identity가 다르면 build를 시작하지
  않는다. Git 개발 체크아웃에서는 현재 NCS·Zephyr·board identity를 cache fingerprint에 포함해
  서로 다른 환경의 cache가 섞이지 않게 한다.
- source record, cache state 또는 manifest가 stale이면 실패한다.
- 실패한 generation으로 이전 성공 artifact를 덮어쓰지 않는다.
- 같은 session과 cache key의 변경 작업은 OS-backed lock으로 직렬화한다.
- child process exit code를 가능한 그대로 Arduino CLI에 반환한다.
- 일반 build에서 매번 pristine, Ninja clean 또는 build directory 삭제를 실행하지 않는다.
- 일반 Upload에서 mass erase, recover 또는 다른 runner fallback을 실행하지 않는다.
- `cmd /c`로 긴 shell 문자열을 다시 해석하지 않고 CMD wrapper가 고정 Python entry를 찾는다.

## 8. 현재 제한

현재 정식 범위에는 다음이 포함되지 않는다.

- precompiled Arduino library와 LTO object
- sysbuild/multi-image, MCUboot, DFU와 OTA
- LLEXT 또는 Loader ABI
- remote/distributed cache와 network cache
- Linux/macOS Boards Manager production 지원
- Arduino IDE Debug 버튼 자동 구성
- 자동 recover 또는 mass erase

## 9. 검증 기록

설계 문서에는 실행 횟수, 경로별 시간과 개별 hash를 복제하지 않는다. 완료 근거는 다음 기록을
사용한다.

- [M5 Arduino CLI Build Adapter 기준선](<../04_검증 기록/05_M5_Arduino_CLI_Build_Adapter_기준선.md>)
- [M9 증분 빌드·캐시·재현성 기준선](<../04_검증 기록/09_M9_증분_빌드_캐시와_재현성_기준선.md>)
- [M13 구성 profile 및 예제 배포 검증](<../04_검증 기록/15_M13_구성_프로필_검증.md>)
- [v0.2.0 정식 릴리스 공개 기록](<../04_검증 기록/21_v0.2.0_정식_릴리스_공개_기록.md>)
