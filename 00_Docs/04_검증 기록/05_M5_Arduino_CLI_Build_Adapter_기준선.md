# M5 Arduino CLI Build Adapter 기준선

| 항목 | 값 |
| --- | --- |
| 상태 | 완료 |
| 기록 성격 | **v0.1.0 역사적 완료 기준선** — 검증 수치와 당시 단계 경계는 동결하고, 저장소 재구성으로 이동한 파일 경로만 현행 위치로 표기 |
| 검증일 | 2026-08-27 |
| 작성자 | Quantum / NUCODE |
| Core 기준 commit | `ba154305e3b0` + 본 M5 변경 |
| 보드 package | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` — 읽기 전용 |
| NCS / Zephyr | NCS v3.4.0 / Zephyr 4.4.0 |
| Arduino CLI | 1.5.1, commit `01f3d4f2b` |
| FQBN | `nucode:zephyr:nu54dk` |
| 실제 Zephyr 보드 | `nrf54l15dk/nrf54l15/cpuapp/nu54dk` |
| 이미지 구조 | Loader/LLEXT 없는 Native Full Zephyr 정적 이미지 |

---

## 1. 목적과 판정 범위

M5는 Arduino IDE/CLI의 `.ino` 전처리와 library discovery를 유지하면서 최종 compile과
link를 NCS/Zephyr가 소유할 수 있는지 확인하는 첫 수직 PoC다. 사용자에게 보이는 시작점은
일반 `arduino-cli compile`이지만 결과물은 별도 Sketch payload나 Loader가 아닌 완전한
Zephyr firmware다.

이번 단계의 완료 조건은 다음과 같다.

- `nucode:zephyr:nu54dk`가 Arduino board로 발견된다.
- `.ino` 결합, 자동 prototype과 원본 line directive가 보존된다.
- Arduino가 발견한 Sketch와 library source만 Zephyr build graph로 전달된다.
- `prj.conf`와 `app.overlay`가 최종 Kconfig와 Devicetree에 반영된다.
- 한 번의 CLI compile로 ELF, HEX, BIN, map과 manifest가 생성된다.
- 의도적 compile 오류가 CLI nonzero와 원본 `.ino` 행을 반환한다.
- 서로 다른 build가 context와 Zephyr workspace를 공유하지 않는다.
- 일반 수정에서 매번 pristine build를 수행하지 않는다.

Upload, Flash, Debug recipe는 M8 범위다. M5 완료는 Arduino IDE의 Upload 버튼이 준비됐다는
뜻이 아니다.

---

## 2. 구현된 수직 경로

~~~text
Arduino CLI
  │
  ├─ .ino 결합, #include 탐색, prototype 생성
  ├─ Arduino library dependency 선택
  │
  ▼
platform.txt recipe
  │
  ├─ prepare      Zephyr configure-only
  ├─ preprocess   NCS target preprocessor
  ├─ record       source/object 일대일 JSON record
  ├─ archive      Arduino lifecycle용 placeholder
  └─ link         선택된 record → sources.cmake
                         │
                         ▼
                 west/CMake/Ninja
                         │
                         ├─ Zephyr kernel
                         ├─ NCS subsystem
                         ├─ NU54DK board package
                         ├─ NU54DK Arduino Core/Variant
                         ├─ generated .ino.cpp
                         └─ 발견된 Arduino library source
                         │
                         ▼
                 Full Zephyr ELF/HEX/BIN/MAP
~~~

Arduino recipe가 만든 placeholder object나 `core.a`를 최종 linker에 넣지 않는다. 각 compile
recipe는 원자적인 source record를 만들고, `recipe.c.combine`이 실제로 전달한 object
목록에 대응하는 record만 선택한다. Core와 Variant source는 Zephyr module이 한 번만
컴파일하며, Sketch와 library source는 생성된 `sources.cmake`를 통해 Zephyr app target이
컴파일한다.

이 방식은 다음 문제를 피한다.

- Arduino object와 Zephyr app의 `autoconf.h`/Devicetree/ABI 불일치
- Core와 Variant의 중복 symbol
- build directory에 남은 과거 record의 우발적 포함
- Arduino linker와 Zephyr linker가 서로 다른 최종 image를 생성하는 문제

---

## 3. 주요 파일

| 경로 | 책임 |
| --- | --- |
| `boards.txt` | NU54DK board metadata와 Zephyr target 연결 |
| `platform.txt` | Arduino preprocess/compile/archive/link/export lifecycle 연결 |
| `tools/nu54-builder/nu54-builder.cmd` | 일반 Arduino IDE process에서 NCS Python을 찾는 Windows launcher |
| `tools/nu54-builder/src/nu54_builder.py` | 표준 라이브러리만 사용하는 Build Adapter |
| `tools/nu54-builder/templates/zephyr-app/` | configure-only와 final build가 공유하는 Zephyr app |
| `libraries/NUCODE_NU54DK/examples/Blink/Blink.ino` | prototype을 포함한 Arduino CLI 수직 예제이자 Arduino IDE 표준 예제 메뉴 배포 경로 |
| `tests/arduino-cli/run_smoke.py` | M5 CLI 자동 회귀 runner |
| `tests/arduino-cli/libraries/` | 직접 library와 `depends` library fixture |
| `tests/arduino-cli/config_overlay/` | Sketch별 Kconfig/Devicetree fixture |
| `tests/arduino-cli/compile_error/` | 원본 `.ino` diagnostic fixture |

공개 `boards.txt`와 `platform.txt`에는 개발 PC의 사용자 절대 경로를 넣지 않는다. 설치된
platform 위치는 `{runtime.platform.path}`, Arduino build와 Sketch 위치는 각각
`{build.path}`, `{build.source.path}`에서 받는다.

---

## 4. NCS 환경과 Windows 처리

Arduino IDE는 nRF Connect SDK terminal 환경을 상속하지 않을 수 있다. launcher와 Adapter는
다음 순서로 고정 환경을 찾는다.

1. `NUCODE_PYTHON`, `NUCODE_NCS_ROOT`, `NUCODE_TOOLCHAIN_ROOT` 명시값
2. NCS Toolchain Manager의 `toolchains.json`에서 v3.4.0 bundle 식별
3. `C:/ncs/v3.4.0`과 해당 `environment.json`

`environment.json`의 PATH, PYTHONPATH, `ZEPHYR_TOOLCHAIN_VARIANT`와
`ZEPHYR_SDK_INSTALL_DIR`를 child process 환경에 적용한다. 시스템 Python에 west나 Zephyr
package를 별도로 설치하지 않는다.

Windows에서 확인한 추가 조치는 다음과 같다.

- `.cmd`는 CRLF를 강제하고 child Python 종료 코드를 그대로 반환한다.
- Arduino/NCS의 긴 object path를 피하기 위해 실제 Zephyr workspace는
  `%TEMP%/n54/<build-path-hash>`를 사용한다.
- 영속 context와 source record는 Arduino `{build.path}/nu54-zephyr`에 둔다.
- path는 shell 문자열로 합치지 않고 subprocess argument 배열로 전달한다.
- 한글과 공백이 포함된 Arduino build path를 실제 compile로 검증한다.

---

## 5. Configure와 증분 정책

`prepare`는 source graph가 완성되기 전에 bootstrap source로 configure-only를 수행한다.
`--no-sysbuild`를 명시하며 `BOARD_ROOT`는 읽기 전용 보드 package,
`EXTRA_ZEPHYR_MODULES`는 Core platform root로 고정한다.

Sketch `prj.conf`는 template 설정 뒤에 병합하고 `app.overlay`는 생성 app에 전달한다.
Adapter version, board, platform root, template config, Sketch config와 overlay를 fingerprint로
관리한다. 유효한 CMake/Ninja graph와 같은 fingerprint가 있으면 다음 prebuild configure를
건너뛴다.

source manifest는 내용이 달라질 때만 timestamp를 바꾼다. 따라서 무변경 compile에서는
CMake를 다시 실행하지 않고, Sketch 한 줄 변경에서는 같은 Ninja tree에서 해당 source와
필요한 final link만 수행한다. `pristine_configure_count`는 context에 기록한다.

NCS security CMake가 string 형식 `CONFIG_*` cache를 다음 configure의 command-line override로
오인하는 문제는 configure 때 stale `CONFIG_*` cache를 제거하고 template에서 알려진 string
cache를 정리하여 차단했다.

---

## 6. 산출물 계약

Sketch 이름이 `Blink.ino`이면 Arduino build directory에 다음 파일을 내보낸다.

~~~text
Blink.ino.elf
Blink.ino.hex
Blink.ino.bin
Blink.ino.map
Blink.ino.nu54-build.json
~~~

JSON manifest에는 schema와 Adapter version, FQBN, 실제 Zephyr board, sysbuild 여부, 선택된
Sketch/library source, context, 각 artifact의 절대 경로·크기·SHA-256을 기록한다. `size`
recipe는 target ELF에 `arm-zephyr-eabi-size`를 실행하여 Arduino CLI가 표시할 FLASH/RAM 값을
제공한다.

`boards.txt`의 NU54DK 한도는 보드 DTS와 linker 결과에 맞춰 FLASH 1,560,576 B
(`0x17D000`, 1524 KiB), RAM 262,144 B (`0x40000`, 256 KiB)로 기록했다.

Loader image, LLEXT extension, EDK export table, 별도 Sketch partition 또는 merged Loader
artifact는 생성하지 않는다.

---

## 7. 자동 검증

기준 명령은 다음과 같다.

~~~powershell
$Python = "C:/ncs/toolchains/dcbdc366a1/opt/bin/python.exe"
& $Python tests/arduino-cli/run_smoke.py
~~~

| 시험 | 확인 항목 | 결과 |
| --- | --- | --- |
| board discovery | FQBN `nucode:zephyr:nu54dk` | PASS |
| Blink | prototype, Full Zephyr build, artifact 5종, source manifest | PASS |
| Windows path | 한글·공백 build path | PASS |
| local library | 직접 library와 `depends` library의 `.cpp` source | PASS |
| config/overlay | `CONFIG_THREAD_NAME=y`, DTS marker | PASS |
| compile error | CLI nonzero, 원본 `.ino` 행과 symbol | PASS |
| parallel | 두 build의 context/workspace/manifest 격리 | PASS |
| incremental | 동일 workspace, pristine count 1, 한 줄 수정 재빌드 | PASS |

최종 코드의 staged copy에서 Blink, compile error, library와 `depends`, config/overlay,
parallel, incremental 케이스를 각각 실행했고 6/6 PASS를 확인했다. 이 결과는 한 번의 전체
suite 실행이 아니라 동일한 최종 staged copy에 대한 케이스별 실행 결과의 합산이다. 별도로
board discovery와 한글·공백 build path를 실제 Arduino CLI compile로 확인했다.

Blink 기준 실제 Full Zephyr memory region은 FLASH 30,728 B, RAM 6,856 B였다. target
`size` tool을 사용하는 Arduino CLI 표시는 text/data/bss 기준 FLASH 30,724 B, RAM 6,859 B다.
두 값의 계산 기준이 다르므로 동일 숫자로 강제하지 않는다.

무변경 두 번째 Blink compile은 `configure_skipped=true`,
`pristine_configure_count=1`을 유지하고 약 7.04초에 종료됐다.

---

## 8. 발견하고 수정한 문제

| 문제 | 원인 | 조치 |
| --- | --- | --- |
| `.cmd`가 명령 일부를 별도 명령으로 해석 | LF-only Windows command file | CRLF 고정 및 `.gitattributes` 규칙 추가 |
| 실패한 Python child 뒤 CLI가 계속 진행 | 괄호 block 안 `%errorlevel%`의 parse-time 확장 | Python 경로 선택과 실행을 분리하고 실제 종료 코드 반환 |
| 최초 configure에서 `app` source 없음 | source manifest 생성 전 빈 app target | harmless bootstrap source 상시 포함 |
| 두 번째 configure에서 Kconfig warning abort | NCS security string cache가 따옴표 없는 override로 재생성 | stale `CONFIG_*` cache 제거와 template cache 정리 |
| 긴 Windows path 경고와 object 배치 위험 | Arduino build root 아래에 전체 NCS tree 배치 | 짧은 hash 기반 Zephyr workspace 분리 |
| 무변경 compile도 CMake 재실행 | template 파일 timestamp를 매번 교체 | 같은 byte면 timestamp를 보존하고 configure fingerprint 적용 |

---

## 9. M5 완료 당시 제한과 후속 경계

다음 목록은 **M5 완료 시점의 역사적 단계 경계**다. 이후 단계에서 해결된 항목이 있더라도
M5 자체의 검증 범위를 소급해서 넓히지 않는다.

- Arduino IDE 2.x GUI의 Verify 버튼 직접 조작 회귀
- Upload/Flash와 pyOCD/J-Link 선택
- Boards Manager package index와 release archive
- Linux/macOS launcher
- precompiled Arduino library
- 완전한 header dependency file과 compiler cache 최적화
- stale `%TEMP%/n54` workspace 정리 명령
- sysbuild/multi-image, MCUboot, DFU, OTA
- 일반 Arduino library corpus 호환성

후속 M6는 이 build 경로 위에서 ArduinoCore-API 공통 구현, `String`, `Print`, `Stream`, 기본
`Serial`과 GPIO interrupt를 연결했고, M8은 Upload recipe를 별도 검증했다. M5 당시에는
`platform.txt`에 upload recipe를 추가하지 않았고 자동 mass erase/recover도 실행하지 않았다.
