# Arduino CLI 및 IDE 통합 설계 — v0.2.0

| 항목 | 내용 |
| --- | --- |
| 문서 상태 | **현재 구현 계약** |
| 대상 | Arduino CLI 1.5.1 / Arduino IDE 2.x |
| FQBN | `nucode:zephyr:nu54dk` |
| Zephyr target | `nrf54l15dk/nrf54l15/cpuapp/nu54dk` |
| 최종 이미지 | Loader/LLEXT 없는 단일 Full Zephyr 이미지 |

이 문서는 Arduino platform lifecycle과 NU54DK Build Adapter의 현재 연결을 설명한다. recipe의
단일 원본은 `boards.txt`와 `platform.txt`이며, 실행 구현은
`tools/nu54-builder/src/nu54_builder.py`다.

## 1. 사용자에게 보이는 흐름

Arduino 사용자는 일반 platform과 같은 순서로 작업한다.

```text
보드와 Feature set 선택
  → Verify / arduino-cli compile
  → Upload / arduino-cli upload
  → 필요한 경우 Serial Monitor
```

내부에서는 Arduino CLI가 `.ino` 전처리와 library discovery를 수행하고, Build Adapter가 선택된
source graph를 Zephyr CMake/Ninja에 전달한다. Arduino의 개별 compile recipe가 target object를
만드는 구조가 아니며, 최종 ELF를 Arduino linker가 만들지도 않는다.

## 2. Platform 구조와 설치 경계

정식 package의 핵심 구조는 다음과 같다.

```text
boards.txt
platform.txt
post_install.bat
cores/arduino/
variants/nu54dk/
libraries/
tools/nu54-builder/
tools/nu54-prerequisites/
board_package/NU54DK_Zephyr_DTS/
zephyr/
```

Build Adapter는 별도 Boards Manager tool dependency가 아니다. `platform.txt`가 설치된 platform
안의 CMD wrapper를 직접 호출한다.

```ini
nu54.builder="{runtime.platform.path}/tools/nu54-builder/nu54-builder.cmd"
```

Stable package index의 `toolsDependencies`는 비어 있다. NCS와 Toolchain은 Core ZIP에 포함하지
않고 `post_install.bat`이 Nordic 공식 배포 경로에서 사용자 영역에 exact pin으로 준비한다.

## 3. `boards.txt` 계약

현재 보드는 다음 build identity를 제공한다.

```ini
nu54dk.name=NU54DK (nRF54L15, Zephyr)
nu54dk.build.board=NUCODE_NU54DK
nu54dk.build.core=arduino
nu54dk.build.variant=nu54dk
nu54dk.build.zephyr_board=nrf54l15dk/nrf54l15/cpuapp/nu54dk
nu54dk.build.sysbuild=false
nu54dk.build.nu54_profile=standard
nu54dk.upload.tool.default=nu54_pyocd
```

Arduino Tools 메뉴는 두 독립 선택을 제공한다.

| 메뉴 | 값 | 전달되는 의미 |
| --- | --- | --- |
| `Feature set` | `Standard peripherals` | `build.nu54_profile=standard` |
| `Feature set` | `BLE NUS` | `build.nu54_profile=ble` |
| `Upload probe` | `CMSIS-DAP (pyOCD)` | 한 probe 자동 선택 |
| `Upload probe` | `CMSIS-DAP with UID (pyOCD)` | 필수 CMSIS-DAP UID field |
| `Upload probe` | `SEGGER J-Link` | 필수 J-Link serial field |

`upload.tool.default`는 full-image SWD upload에도 Arduino가 요구하는 표준 property 이름이다.
COM port, DAPLink volume과 probe UID는 서로 다른 식별자다.

## 4. Arduino lifecycle 연결

현재 `platform.txt`의 build 흐름은 다음과 같다.

| Arduino 단계 | Adapter 명령 | 실제 역할 |
| --- | --- | --- |
| prebuild | `prepare` | profile 기반 Zephyr configure-only와 context 준비 |
| include discovery | `preprocess --mode includes` | NCS compiler dependency 출력 |
| macro/prototype preprocess | `preprocess --mode macros` | Arduino discovery용 전처리 출력 |
| C/C++/ASM recipe | `record` | source/include record와 빈 lifecycle object 생성 |
| Core archive | `archive` | 빈 lifecycle archive 보장 |
| combine | `link` | source manifest 생성, west/Ninja build와 artifact publish |
| objcopy HEX/BIN | `verify-artifact` | 이미 publish된 artifact의 manifest/hash 확인 |
| size | `size` | Full Zephyr ELF의 FLASH/RAM 사용량 출력 |
| upload | `flash` | manifest와 probe를 검증한 west runner 호출 |

### 4.1 Prebuild

`prepare`는 Arduino가 library를 찾기 전에 실행된다. 따라서 최종 Sketch/library source를
요구하지 않으며 board/profile, 고급 sidecar와 prerequisite를 이용해 provisional cache만
구성한다.

### 4.2 Source graph 수집

Arduino CLI는 `.ino` 결합과 library 선택을 정상적으로 수행한다. 선택한 각 C/C++/ASM source에
대한 recipe는 `record`를 호출한다. 이 명령이 만드는 object와 depfile은 Arduino lifecycle용
placeholder이며 최종 firmware object가 아니다.

`recipe.c.combine`은 Arduino가 전달한 `{object_files}`를 `link --objects`에 넘긴다. Adapter는
각 object의 source record를 검증하고, 실제 선택 library feature를 해석한 뒤 결정적인
`sources.cmake`를 만든다. Sketch/library의 실제 컴파일과 링크는 Zephyr/Ninja가 수행한다.

### 4.3 Objcopy와 size

`link`가 이미 ELF, HEX, BIN과 map을 Arduino build path에 publish한다. 후속 objcopy recipe는
새 파일을 생성하지 않고 `verify-artifact`로 현재 manifest와 hash를 확인한다.

Size recipe는 다음 형식을 사용한다.

```text
NU54_FLASH_USED=<bytes>
NU54_RAM_USED=<bytes>
```

## 5. 입력과 출력

주요 Arduino property는 다음과 같다.

| Property | 용도 |
| --- | --- |
| `{runtime.platform.path}` | 설치된 platform root와 CMD wrapper 위치 |
| `{build.fqbn}` | board identity |
| `{build.nu54_profile}` | 선택 profile |
| `{build.source.path}` | Sketch source root |
| `{build.path}` | Arduino session과 export artifact 위치 |
| `{build.project_name}` | artifact basename |
| `{source_file}` / `{object_file}` | source record identity |
| `{includes}` | Arduino가 선택한 include root |
| `{object_files}` | 최종 link에서 검증할 source record 집합 |

일반 Sketch는 `.ino`만으로 build할 수 있다. 고급 사용자는 Sketch root에 `prj.conf`와
`app.overlay`를 선택적으로 둘 수 있지만, 표준 예제에는 필요하지 않다.

성공한 build는 `{build.path}`에 다음을 publish한다.

```text
<project>.elf
<project>.hex
<project>.bin
<project>.map
<project>.nu54-build.json
nu54-zephyr/context.json
```

ELF는 symbol을 포함한 Full Zephyr ELF이며 HEX/BIN도 별도 loader image가 아니다.

## 6. Arduino CLI 사용

### 6.1 Platform 확인

```powershell
arduino-cli board listall | Select-String 'NU54DK'
arduino-cli board details --fqbn 'nucode:zephyr:nu54dk'
```

### 6.2 Compile

```powershell
$RepoRoot = (Resolve-Path '.').Path
$SketchDir = Join-Path $RepoRoot 'libraries\NUCODE_NU54DK\examples\Blink'
$ArduinoBuild = Join-Path $RepoRoot 'build\arduino-cli\Blink'

arduino-cli compile `
  --fqbn 'nucode:zephyr:nu54dk' `
  --board-options feature_set=standard,upload_probe=pyocd `
  --build-path $ArduinoBuild `
  --verbose `
  $SketchDir
```

Verbose log의 Adapter 단계는 `prepare`, `preprocess`, `record`, `archive`, `link`,
`verify-artifact`, `size` 순서로 나타날 수 있다. 폐기된 `compile` 또는 `export` 하위 명령을
기대하지 않는다.

같은 build path로 다시 compile하면 같은 cache identity와 Ninja dependency를 재사용한다.

### 6.3 기본 pyOCD Upload

Compile과 Upload에는 같은 `upload_probe` option과 build path를 사용한다.

```powershell
arduino-cli upload `
  --fqbn 'nucode:zephyr:nu54dk' `
  --board-options feature_set=standard,upload_probe=pyocd `
  --build-path $ArduinoBuild `
  --verbose `
  $SketchDir
```

기본 경로는 CMSIS-DAP가 정확히 한 대일 때만 자동 선택한다.

### 6.4 명시 UID 또는 J-Link Upload

여러 CMSIS-DAP 중 하나를 선택할 때는 compile부터 `pyocd_uid`를 사용한다.

```powershell
arduino-cli compile `
  --fqbn 'nucode:zephyr:nu54dk' `
  --board-options feature_set=standard,upload_probe=pyocd_uid `
  --build-path $ArduinoBuild `
  $SketchDir

arduino-cli upload `
  --fqbn 'nucode:zephyr:nu54dk' `
  --board-options feature_set=standard,upload_probe=pyocd_uid `
  --upload-field probe_id=<CMSIS-DAP-UID> `
  --build-path $ArduinoBuild `
  --verbose `
  $SketchDir
```

J-Link는 `upload_probe=jlink`와
`--upload-field probe_id=<JLINK-SERIAL-NUMBER>`를 사용한다. 선택 runner가 없거나 ID가 비면
실패하며 pyOCD로 자동 fallback하지 않는다.

## 7. Arduino IDE 2.x 계약

### Verify

- CLI compile과 같은 recipes를 사용한다.
- 표준 예제는 sidecar 없이 선택 profile로 build된다.
- source 오류는 Arduino의 `#line` 정보를 가능한 한 보존한다.
- 성공 뒤 Full Zephyr FLASH/RAM 사용량을 표시한다.

### Upload

- 선택한 세 upload tool 중 하나를 사용한다.
- 다중 CMSIS-DAP 기본 경로는 임의 probe를 고르지 않고 실패한다.
- manifest, context와 artifact hash가 맞아야 flash한다.
- 일반 upload에서 mass erase/recover를 실행하지 않는다.

### Serial Monitor와 Debug

Serial Monitor는 target UART의 VCOM bridge이며 SWD probe ID와 별개다. Arduino IDE Debug 버튼의
자동 toolchain/debugserver 구성은 v0.2.0 정식 지원 범위가 아니다. Full Zephyr ELF를 이용한
수동 west debug 경계는 [업로드와 디버그](./05_업로드와_디버그.md)를 따른다.

## 8. Library와 구성 경계

Arduino library discovery의 우선순위와 architecture compatibility는 Arduino CLI가 소유한다.
Adapter는 넘겨받은 source/include record를 검증하고 package allowlist feature만 Zephyr 구성에
반영한다.

현재 제한은 다음과 같다.

- precompiled-only 또는 LTO-only Arduino library 미지원
- AVR register/libc와 architecture 전용 assembly 호환성 미보장
- 임의 linker script 주입 미지원
- sysbuild, MCUboot, DFU, OTA와 LLEXT 미지원
- Linux/macOS Boards Manager production 지원 미제공

## 9. 오류와 검증 기록

오류 해결을 위해 오래된 payload archive나 compiler response file을 찾지 않는다. 다음을 우선
확인한다.

- FQBN과 profile/upload menu option
- Boards Manager 설치본이면 exact prerequisite와 배포 board snapshot, Git 개발 체크아웃이면
  현재 NCS·Zephyr·board identity
- `{build.path}/nu54-zephyr/context.json`
- source record와 generated `sources.cmake`
- artifact manifest와 persistent cache state

실행 횟수, 개별 로그와 완료 판정은 다음 기록에 보존한다.

- [M5 Arduino CLI Build Adapter 기준선](<../04_검증 기록/05_M5_Arduino_CLI_Build_Adapter_기준선.md>)
- [M8 업로드와 디버그 기준선](<../04_검증 기록/08_M8_업로드와_디버그_기준선.md>)
- [M13 구성 profile 및 예제 배포 검증](<../04_검증 기록/15_M13_구성_프로필_검증.md>)
- [M18 v0.2.0 RC 검증과 교정](<../04_검증 기록/20_M18_v0.2.0_rc1_공개_검증과_rc2_교정.md>)
