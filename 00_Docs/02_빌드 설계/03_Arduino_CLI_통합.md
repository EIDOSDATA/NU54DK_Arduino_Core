# Arduino CLI 및 IDE 통합 설계 — v0.1.0 기준선 / v0.2.0 확장

| 항목 | 내용 |
| --- | --- |
| 문서 상태 | `v0.1.0` Arduino CLI·IDE Build/Upload·clean Windows 실증 완료 |
| 현재 정식 버전 | `v0.1.0` |
| 다음 목표 버전 | `v0.2.0` — M13 예제 노출·구성 profile UX |
| 작성자 | Quantum / NUCODE |
| 대상 | Arduino CLI 및 Arduino IDE 2.x |
| 제안 FQBN | `nucode:zephyr:nu54dk` |
| 실제 Zephyr target | `nrf54l15dk/nrf54l15/cpuapp/nu54dk` |
| 최종 빌드 | Loader 없는 Native Full Zephyr |

---

## 1. 목적

이 문서는 사용자가 Arduino CLI 또는 Arduino IDE의 일반 Build/Upload 동작으로 NU54DK용 Full Zephyr firmware를 만들 수 있도록 Arduino platform과 Build Adapter의 경계를 정의한다.

사용자에게 보이는 흐름은 일반 Arduino platform과 같아야 한다.

~~~text
보드 선택
  → Verify/Build
  → Upload
  → Serial Monitor 또는 Debug
~~~

내부에서는 Arduino가 최종 firmware를 직접 링크하지 않는다. Arduino는 `.ino` 전처리와 library dependency resolution을 수행하고, Build Adapter가 그 결과를 NCS/Zephyr 전체 빌드에 연결한다.

M5에서 `boards.txt`, `platform.txt`와 Build Adapter를 구현했고 M8에서 Upload/Flash를
실증했다. M10~M11에서 Boards Manager를 통한 clean Windows Arduino IDE 2.3.10
설치·compile·NU54DK upload·실행을 검증한 뒤 `v0.1.0`을 정식 공개했다.
현재 후속 과제는 `v0.2.0` M13의 표준 library 예제 노출과 zero-config profile UX다.

---

## 2. 범위

### 2.1 포함 범위

- Arduino platform 폴더 구성
- `boards.txt`의 NU54DK 정의
- `platform.txt`의 compiler/build/upload recipe 설계
- `.ino` 전처리와 library discovery
- prebuild hook의 역할과 한계
- `recipe.c.combine`과 Build Adapter link 모델
- Arduino CLI의 compile, upload 및 export 흐름
- Arduino IDE 2.x Build/Upload 버튼 동작
- board menu를 통한 pyOCD/J-Link 선택 설계
- Arduino가 기대하는 ELF/HEX/BIN 및 size 출력
- Windows path와 NCS environment 오류 전달
- CLI 회귀 시험

### 2.2 고정 빌드 기준

| 항목 | 값 |
| --- | --- |
| NCS | v3.4.0 |
| Zephyr | 4.4.0 |
| Board target | `nrf54l15dk/nrf54l15/cpuapp/nu54dk` |
| `BOARD_ROOT` | `<repo>/board_package/NU54DK_Zephyr_DTS` |
| `EXTRA_ZEPHYR_MODULES` | `<repo>` |
| PoC sysbuild | 사용하지 않음 |
| Loader/LLEXT | 사용하지 않음 |
| 기본 upload runner | pyOCD |
| 일반 upload erase | 사용하지 않음 |

---

## 3. Arduino platform 파일 구조

개발 저장소에서 다음 구조를 사용한다.

~~~text
NU54DK_Arduino_Core/
├─ boards.txt
├─ platform.txt
├─ programmers.txt                    # programmer/debug 메뉴가 필요할 때
├─ cores/
│  └─ arduino/
│     ├─ Arduino.h
│     └─ ...
├─ variants/
│  └─ nu54dk/
├─ libraries/
├─ tools/
│  └─ nu54-builder/
├─ board_package/
│  └─ NU54DK_Zephyr_DTS/
└─ zephyr/
   └─ module.yml
~~~

Arduino architecture ID는 `zephyr`를 우선 사용한다. 이 경우 개발 설치 FQBN은 다음 형식이다.

~~~text
nucode:zephyr:nu54dk
~~~

vendor가 다르므로 공식 `arduino:zephyr:*` platform과 함께 설치할 수 있다. architecture 이름을 `zephyr`로 유지하면 `library.properties`에서 `architectures=zephyr`로 선언된 library의 호환성 판단에도 유리하다. 다만 최종 package vendor와 architecture 이름은 최초 CLI PoC 전에 확정한다.

---

## 4. Arduino build lifecycle과 연결 지점

### 4.1 Arduino가 수행하는 순서

Arduino CLI의 일반 build는 개념적으로 다음 순서로 진행된다.

1. platform과 board property 해석
2. prebuild hook 실행
3. `.ino` 파일 결합, `Arduino.h` 삽입 및 prototype 생성
4. preprocessor를 이용한 library discovery
5. sketch source compile
6. 발견된 library source compile
7. Core와 variant source compile
8. Core archive 생성
9. `recipe.c.combine` 링크
10. objcopy 및 post-objcopy hook
11. size 계산
12. export 또는 upload

### 4.2 prebuild 시점의 한계

`recipe.hooks.prebuild.*`는 sketch 전처리와 library discovery보다 먼저 실행된다. 이 시점에는 다음 정보가 아직 완성되지 않았다.

- 생성된 `<sketch>.ino.cpp`
- 실제 선택된 Arduino library 목록
- 각 library의 source 목록
- 최종 `{object_files}`

따라서 prebuild에서 전체 `west build`를 완료하는 설계는 사용하지 않는다. prebuild의 책임은 다음으로 제한한다.

- 환경 진단
- 패키지 기본 Kconfig/overlay와 고급 sketch sidecar 확인
- M13 이후 selected profile/feature의 resolved fragment 확인
- Zephyr configure-only 실행
- generated header와 compile flags 생성
- 이후 recipe가 읽을 context 작성

Arduino 공식 명세에 따르면 compilation database만 생성할 때도 `pre*` hook은 실행될 수 있고 compile 및 `post*` 단계는 생략된다. 그러므로 prebuild는 다음 특성을 가져야 한다.

- 반복 실행 가능
- flash 또는 erase를 수행하지 않음
- 부분 link를 수행하지 않음
- 동일 입력에서 같은 context를 재사용
- configure 외에 외부 상태를 변경하지 않음

### 4.3 최종 link 시점

`recipe.c.combine.pattern`은 sketch와 library object가 모두 준비된 뒤 실행되며 `{object_files}`와 Core archive 경로를 받을 수 있다.

따라서 이 recipe가 Build Adapter의 `link`를 호출한다.

~~~text
recipe.c.combine
  → object 목록 검증
  → arduino_payload.a 작성
  → west build -d <zephyr-build>
  → zephyr.elf/hex/bin export
~~~

`recipe.hooks.linking.prelink`에서 west를 실행한 뒤 별도 compiler linker recipe까지 실행하는 구조는 피한다. 최종 link가 두 번 실행되거나 Arduino linker가 Zephyr 결과를 덮어쓸 수 있기 때문이다.

---

## 5. 입력과 출력

### 5.1 Arduino 자동 입력 property

| Property | 용도 |
| --- | --- |
| `{runtime.platform.path}` | 설치된 NU54DK Arduino platform root |
| `{runtime.tools.nu54-builder.path}` | Boards Manager tool로 설치된 Adapter root |
| `{build.fqbn}` | 선택 board와 menu option을 포함한 FQBN |
| `{build.source.path}` | sketch source directory |
| `{build.path}` | Arduino build output directory |
| `{build.project_name}` | sketch project name |
| `{build.core.path}` | 선택 Core directory |
| `{build.variant.path}` | NU54DK variant directory |
| `{source_file}` | 현재 compile/preprocess source |
| `{object_file}` | 현재 object output |
| `{includes}` | library discovery가 만든 include path 목록 |
| `{object_files}` | 최종 link 대상 sketch/library object 목록 |
| `{archive_file_path}` | Arduino Core archive 경로 |

### 5.2 사용자 sketch 입력

일반 사용자의 표준 sketch는 `.ino`만으로 빌드된다.

~~~text
Blink/
└─ Blink.ino
~~~

`.ino`, 일반 sketch `.c/.cpp/.S`, Arduino library source는 Arduino CLI가 탐색한다. 고급
Zephyr 사용자는 sketch root에 `prj.conf`/`app.overlay`를 선택적으로 둘 수 있지만,
이는 일반 Arduino 사용자의 필수 작업이 아니다. `v0.2.0` M13은 표준 예제의
구성 선택을 profile·feature resolver와 Tools 메뉴로 소유하고, 직접 sidecar는 고급
escape hatch로 유지한다.

### 5.3 출력

Arduino build directory에는 최소 다음 파일이 있어야 한다.

~~~text
{build.path}/
├─ {build.project_name}.elf
├─ {build.project_name}.hex
├─ {build.project_name}.bin
├─ {build.project_name}.map
└─ {build.project_name}.nu54-build.json
~~~

이 파일들은 Zephyr build directory의 산출물을 export한 것이다. 별도의 LLEXT sketch ELF나 loader image가 아니다.

---

## 6. `boards.txt` 계약

다음은 설계 예시이며 실제 property 이름은 CLI PoC에서 검증 후 확정한다.

~~~ini
menu.upload_runner=Upload probe

nu54dk.name=NUCODE NU54DK (nRF54L15, Zephyr)
nu54dk.build.board=NU54DK_NRF54L15
nu54dk.build.core=arduino
nu54dk.build.variant=nu54dk
nu54dk.build.zephyr_board=nrf54l15dk/nrf54l15/cpuapp/nu54dk
nu54dk.build.sysbuild=false
nu54dk.upload.maximum_size=1462272
nu54dk.upload.maximum_data_size=192512
nu54dk.upload.use_1200bps_touch=false
nu54dk.upload.wait_for_upload_port=false
nu54dk.upload.native_usb=false

nu54dk.menu.upload_runner.pyocd=CMSIS-DAP (pyOCD)
nu54dk.menu.upload_runner.pyocd.upload.tool=nu54_pyocd
nu54dk.menu.upload_runner.pyocd.build.upload_runner=pyocd

nu54dk.menu.upload_runner.jlink=J-Link
nu54dk.menu.upload_runner.jlink.upload.tool=nu54_jlink
nu54dk.menu.upload_runner.jlink.build.upload_runner=jlink
~~~

주의 사항:

- flash/RAM 최대치는 보드 YAML 숫자를 기계적으로 복사하지 않고 실제 linkable region과 최종 linker configuration에 맞춰 검증한다.
- 일반 Upload 버튼이 SWD full-image flash를 실행하더라도 Arduino property 이름은 `upload.tool`을 사용할 수 있다.
- pyOCD가 기본 선택이다.
- J-Link 선택은 Zephyr build의 `runners.yaml`에 jlink가 실제 등록된 경우에만 성공해야 한다.
- J-Link가 불가능한 상황에서 pyOCD로 자동 fallback하지 않는다.

---

## 7. `platform.txt` recipe 계약

### 7.1 Adapter tool path

Boards Manager 배포에서는 package index의 tool dependency를 사용한다.

~~~ini
tools.nu54_builder.path={runtime.tools.nu54-builder.path}
tools.nu54_builder.cmd=nu54-builder
tools.nu54_builder.cmd.windows=nu54-builder.exe
~~~

개발 checkout에서는 `platform.local.txt` 또는 개발용 tool wrapper로 위치를 override할 수 있다. 사용자별 절대 경로를 공개 `platform.txt`에 넣지 않는다.

### 7.2 prebuild

~~~ini
recipe.hooks.prebuild.1.pattern="{tools.nu54_builder.path}/{tools.nu54_builder.cmd}" prepare --platform-root "{runtime.platform.path}" --sketch-root "{build.source.path}" --arduino-build "{build.path}" --core-root "{build.core.path}" --variant-root "{build.variant.path}" --fqbn "{build.fqbn}" --board "{build.zephyr_board}" --sysbuild false
~~~

이 command는 context만 준비한다. `.ino` source나 발견된 library를 요구하지 않는다.

### 7.3 library discovery preprocessor

~~~ini
recipe.preproc.macros="{tools.nu54_builder.path}/{tools.nu54_builder.cmd}" preprocess --context "{build.path}/nu54/context.json" --source "{source_file}" --output "{preprocessed_file_path}" --discovery-phase "{build.library_discovery_phase}" {includes}
~~~

`recipe.preproc.macros`를 생략하지 않는다. Arduino CLI가 compiler wrapper recipe에서 자동 생성한 전처리 command는 Adapter의 하위 명령 계약과 맞지 않을 수 있다.

### 7.4 source compile

~~~ini
recipe.c.o.pattern="{tools.nu54_builder.path}/{tools.nu54_builder.cmd}" compile --lang c --context "{build.path}/nu54/context.json" --source "{source_file}" --object "{object_file}" --arduino-version "{runtime.ide.version}" --board-macro "{build.board}" {includes}

recipe.cpp.o.pattern="{tools.nu54_builder.path}/{tools.nu54_builder.cmd}" compile --lang cxx --context "{build.path}/nu54/context.json" --source "{source_file}" --object "{object_file}" --arduino-version "{runtime.ide.version}" --board-macro "{build.board}" {includes}

recipe.S.o.pattern="{tools.nu54_builder.path}/{tools.nu54_builder.cmd}" compile --lang asm --context "{build.path}/nu54/context.json" --source "{source_file}" --object "{object_file}" --arduino-version "{runtime.ide.version}" --board-macro "{build.board}" {includes}
~~~

실제 recipe에는 사용자 `compiler.*.extra_flags`와 Arduino CLI가 기대하는 override property를 포함해야 한다. Arduino Lint 요구 사항도 최종 platform에 반영한다.

### 7.5 Core archive

~~~ini
recipe.ar.pattern="{tools.nu54_builder.path}/{tools.nu54_builder.cmd}" archive --context "{build.path}/nu54/context.json" --archive "{archive_file_path}" --object "{object_file}"
~~~

실제 Core 구현의 빌드 소유권은 [Build Adapter 설계](./02_Build_Adapter_설계.md)의 중복 방지 정책을 따른다.

### 7.6 최종 combine

~~~ini
recipe.c.combine.pattern="{tools.nu54_builder.path}/{tools.nu54_builder.cmd}" link --context "{build.path}/nu54/context.json" --project "{build.project_name}" --output-dir "{build.path}" --core-archive "{archive_file_path}" {object_files}
~~~

`{object_files}`가 Windows command length 제한에 접근하면 production 구현에서 response file 또는 Adapter manifest 방식으로 전환한다. object 누락을 피하기 위해 단순 build directory 전체 scan만으로 대체하지 않는다.

### 7.7 objcopy와 export

최종 link가 Zephyr HEX/BIN까지 export한다면 objcopy recipe는 존재만 하는 no-op이 아니라 산출물 존재를 검증하는 Adapter command로 둔다.

~~~ini
recipe.objcopy.hex.pattern="{tools.nu54_builder.path}/{tools.nu54_builder.cmd}" export --context "{build.path}/nu54/context.json" --format hex --output "{build.path}/{build.project_name}.hex"

recipe.objcopy.bin.pattern="{tools.nu54_builder.path}/{tools.nu54_builder.cmd}" export --context "{build.path}/nu54/context.json" --format bin --output "{build.path}/{build.project_name}.bin"
~~~

### 7.8 size

~~~ini
recipe.size.pattern="{tools.nu54_builder.path}/{tools.nu54_builder.cmd}" size --manifest "{build.path}/{build.project_name}.nu54-build.json"
recipe.size.regex=^NU54_FLASH_USED=([0-9]+)$
recipe.size.regex.data=^NU54_RAM_USED=([0-9]+)$
~~~

정확한 regex 동작과 최대 메모리 검사는 Arduino CLI 버전별 시험이 필요하다.

### 7.9 output export 이름

~~~ini
recipe.output.tmp_file={build.project_name}.hex
recipe.output.save_file={build.project_name}.nu54dk.hex
~~~

Arduino의 Export Compiled Binary가 전체 Zephyr HEX를 저장하는지 확인한다.

---

## 8. Build Adapter 처리 흐름

~~~text
arduino-cli compile / IDE Verify
        │
        ▼
boards.txt로 FQBN·Zephyr target·runner 결정
        │
        ▼
prebuild → nu54-builder prepare
  └─ Zephyr configure-only, context/flags 생성
        │
        ▼
Arduino .ino preprocessing
        │
        ▼
recipe.preproc.macros → library discovery
        │
        ▼
compile recipes → sketch/library objects
        │
        ▼
recipe.ar → Arduino lifecycle용 archive
        │
        ▼
recipe.c.combine → nu54-builder link
  ├─ arduino_payload.a
  ├─ west build --no-sysbuild
  └─ full zephyr.elf/hex/bin
        │
        ▼
size 및 export
        │
        ▼
Upload 요청 시 선택 runner로 full image flash
~~~

---

## 9. Arduino CLI 명령 계약

### 9.1 platform 인식

개발 설치가 완료된 뒤 다음 명령이 NU54DK를 표시해야 한다.

~~~powershell
arduino-cli board listall | Select-String 'NU54DK'
~~~

제안 FQBN 상세 확인:

~~~powershell
arduino-cli board details --fqbn 'nucode:zephyr:nu54dk'
~~~

### 9.2 최초 compile

~~~powershell
$RepoRoot = (Resolve-Path '.').Path
$SketchDir = Join-Path $RepoRoot 'libraries\NUCODE_NU54DK\examples\Blink'
$ArduinoBuild = Join-Path $RepoRoot 'build\arduino-cli\Blink'

arduino-cli compile `
  --fqbn 'nucode:zephyr:nu54dk' `
  --build-path $ArduinoBuild `
  --verbose `
  $SketchDir
~~~

성공 조건:

- verbose log에서 `prepare`, `preprocess`, `compile`, `link`, `size` 단계가 순서대로 보인다.
- NCS v3.4.0과 Zephyr 4.4.0이 표시된다.
- final output이 Loader용 extension이 아니라 Full Zephyr ELF/HEX다.
- LLEXT/EDK 관련 파일을 요구하지 않는다.

### 9.3 무변경 compile

같은 `--build-path`로 다시 실행한다.

~~~powershell
arduino-cli compile `
  --fqbn 'nucode:zephyr:nu54dk' `
  --build-path $ArduinoBuild `
  --verbose `
  $SketchDir
~~~

무변경 build에서 west pristine 또는 Zephyr 전체 rebuild가 발생하면 cache 계약 실패다.

### 9.4 upload

pyOCD 기본 선택:

~~~powershell
arduino-cli upload `
  --fqbn 'nucode:zephyr:nu54dk:upload_runner=pyocd' `
  --input-dir $ArduinoBuild `
  --verbose `
  $SketchDir
~~~

Arduino CLI의 `--input-dir` upload가 persistent Zephyr build directory 없이 export HEX만으로 가능한지는 별도 검증한다. 첫 PoC에서 Adapter가 `west flash -d`를 요구한다면 compile+upload가 같은 context를 공유해야 한다.

J-Link 선택:

~~~powershell
arduino-cli upload `
  --fqbn 'nucode:zephyr:nu54dk:upload_runner=jlink' `
  --input-dir $ArduinoBuild `
  --verbose `
  $SketchDir
~~~

J-Link runner가 미등록된 경우 명시적인 오류로 끝나야 한다.

---

## 10. Arduino library 처리 계약

### 10.1 library discovery 보존

Arduino CLI가 다음 우선순위와 compatibility 규칙을 적용하도록 discovery 자체를 재구현하지 않는다.

- sketch가 직접 지정한 custom library
- sketchbook library
- platform bundled library
- built-in library
- `library.properties`의 architecture compatibility

Adapter는 Arduino가 넘긴 `{includes}`와 source compile 요청을 정확히 수행한다.

### 10.2 Core bundled library

Zephyr 구현이 필요한 `Wire`, `SPI`, `Serial` 관련 library는 platform의 `libraries/`에 배치할 수 있다. generic Arduino library보다 이 platform 전용 구현이 선택되는지 회귀 시험한다.

### 10.3 첫 버전 제약

첫 통합에서는 다음 library를 명시적으로 비지원할 수 있다.

- `precompiled=true` archive가 포함된 library
- architecture-specific assembly가 NCS compiler와 호환되지 않는 library
- linker script를 직접 주입하는 library
- AVR register 또는 AVR libc에 의존하는 library
- LTO object만 제공하는 library

비지원 library를 발견했을 때 source를 조용히 누락하지 않고 library 이름과 이유를 출력한다.

---

## 11. Arduino IDE 2.x 동작 계약

### 11.1 Verify/Build 버튼

- 선택 FQBN으로 CLI compile과 동일한 recipe가 실행된다.
- Adapter의 단계별 로그가 Output console에 표시된다.
- 오류 위치는 가능하면 원본 `.ino`의 `#line` 정보로 표시된다.
- build 성공 후 Zephyr flash/RAM usage가 표시된다.

### 11.2 Upload 버튼

- 선택된 `Upload probe` menu에 따라 pyOCD 또는 J-Link를 사용한다.
- full Zephyr HEX 또는 해당 build context를 플래시한다.
- loader version 검사나 loader update를 하지 않는다.
- 일반 upload에서 mass erase를 하지 않는다.
- flash 후 reset policy는 runner가 지원하는 정상 reset을 사용한다.

### 11.3 Serial Monitor

Serial Monitor는 CMSIS-DAP의 SWD 기능과 별개다. onboard debugger가 VCOM을 제공하거나 firmware USB CDC/UART가 활성화된 경우에만 사용한다. Upload 성공을 Serial port 재열거에 의존시키지 않는다.

### 11.4 Debug 버튼

Arduino IDE debug integration은 첫 CLI build/upload PoC 이후 별도 단계다. `debug.executable`은 stripped sketch ELF가 아니라 symbol이 있는 Full Zephyr ELF를 가리켜야 한다.

---

## 12. 오류 처리

| 증상 | 원인 | 처리 |
| --- | --- | --- |
| FQBN unknown | platform 설치 경로 또는 architecture 이름 오류 | `board listall`, folder layout 확인 |
| prebuild에서 `.ino.cpp` 없음 | 정상 lifecycle을 잘못 가정 | prebuild는 configure-only로 제한 |
| library를 찾지 못함 | `recipe.preproc.macros`, `{includes}`, architecture 불일치 | verbose preprocess command 검사 |
| compiler path 없음 | IDE가 NCS environment를 상속하지 않음 | Adapter `doctor`와 절대 toolchain 경로 사용 |
| Core symbol 중복 | Arduino Core compile과 Zephyr module compile 중복 | Core 빌드 소유권 한 곳으로 제한 |
| undefined `setup`/`loop` | payload archive가 final Zephyr link에 누락 | payload 및 map 검사 |
| undefined Zephyr symbol | LLEXT export 문제가 아님 | Kconfig subsystem, include 또는 static link order 확인 |
| command line too long | `{object_files}` 또는 `{includes}` 과다 | response file/manifest로 전환 |
| 매번 full rebuild | 매번 pristine, cache key 불안정 | [빌드 캐시와 산출물](./04_빌드_캐시와_산출물.md) 점검 |
| Upload에서 nrfutil 선택 | 잘못된 `upload.tool` 또는 Nordic DK 설정 유입 | pyOCD/J-Link tool property 확인 |
| pyOCD 실패 후 erase 실행 | 잘못된 자동 복구 정책 | 즉시 중단하고 별도 recover로 분리 |

Adapter child process의 실제 exit code를 Arduino CLI에 반환한다. 실패를 성공으로 표시한 뒤 후속 objcopy/size 단계로 진행하지 않는다.

---

## 13. 완료 기준

Arduino CLI 통합 v0의 아래 수락 기준은 M5/M8 구현과 M10~M11 clean Windows
검증을 거쳐 `v0.1.0`에서 완료됐다. 항목의 M5/M8 표기는 당시 단계별 소유권을
보존하는 역사 기록이다. M13은 실행 가능한 예제를 `libraries/*/examples`에 노출하고
일반 사용자의 구성 profile UX를 소유한다.

1. `nucode:zephyr:nu54dk`가 board 목록과 IDE에 표시된다.
2. 표준 Blink `.ino`가 prototype 처리와 함께 compile된다.
3. 외부 Arduino library 하나 이상이 discovery되고 final ELF에 포함된다.
4. prebuild가 configure-only 역할만 수행한다.
5. `recipe.c.combine`에서 west 최종 link가 한 번 실행된다.
6. final ELF/HEX가 Native Full Zephyr image다.
7. 패키지 기본 구성이 자동 반영되고, 고급 sketch의 `prj.conf`/`app.overlay`도 반영된다.
8. **M8 범위:** pyOCD 선택으로 Upload 버튼이 erase 없이 성공한다.
9. **M8 범위:** J-Link 선택은 runner 등록 후 성공하고, 미등록 시 명확히 실패한다.
10. Windows의 공백/한글 경로에서 compile된다.
11. 무변경 두 번째 compile이 전체 pristine rebuild가 아니다.
12. **package/GUI 후속 범위:** Arduino IDE 2.x와 Arduino CLI의 산출물이 기능적으로 동일하다.

---

## 14. 검증 체크리스트 — 역사적 설계 수락 기준

아래 미체크 표기는 문서 초안의 검증 항목을 보존한 것이며 현재 릴리스 상태표가
아니다. `v0.1.0` 완료 판정은 M5~M11 검증 및 정식 릴리스 기록을 따른다.

### 14.1 platform metadata

- [ ] `boards.txt`가 Arduino Lint를 통과한다.
- [ ] `platform.txt`가 Arduino Lint를 통과한다.
- [ ] FQBN이 CLI와 IDE에서 동일하다.
- [ ] architecture ID와 bundled library compatibility를 확인했다.
- [ ] pyOCD가 기본 menu option이다.

### 14.2 build lifecycle

- [ ] prebuild가 `.ino.cpp`를 요구하지 않는다.
- [ ] compilation database 생성에서도 prebuild가 안전하다.
- [ ] `recipe.preproc.macros`가 명시적으로 정의됐다.
- [ ] C, C++, ASM recipe가 Adapter를 호출한다.
- [ ] `recipe.c.combine`만 최종 west link를 소유한다.
- [ ] objcopy/export가 Zephyr 산출물을 검증한다.

### 14.3 sketch와 library

- [ ] 단일 `.ino` Blink가 빌드된다.
- [ ] 여러 `.ino` tab 순서가 정상이다.
- [ ] sketch의 `.c`와 `.cpp`가 함께 빌드된다.
- [ ] platform bundled library가 선택된다.
- [ ] sketchbook library가 선택된다.
- [ ] 비호환 library가 명확한 오류를 낸다.

### 14.4 IDE/CLI

- [ ] CLI compile이 성공한다.
- [ ] CLI upload가 성공한다.
- [ ] IDE Verify가 성공한다.
- [ ] IDE Upload가 성공한다.
- [ ] source error가 원본 `.ino` line으로 표시된다.
- [ ] Export Compiled Binary가 Full Zephyr HEX를 저장한다.

---

## 15. 범위 제외

초기 Arduino CLI 통합에서는 다음을 제외한다.

- Arduino IDE 1.x
- Arduino App Lab
- Arduino Cloud build
- PlatformIO
- LLEXT dynamic 또는 prelinked sketch mode
- Loader 자동 설치와 version sync
- sysbuild/multi-image
- MCUboot, OTA 및 DFU
- precompiled Arduino library
- LTO
- IDE Debug 버튼의 완전한 UX
- custom pluggable discovery 구현
- Boards Manager 공개 release 자동화
- mass erase/recover 자동화

---

## 16. 참고문헌

- [Arduino Platform Specification](https://docs.arduino.cc/arduino-cli/platform-specification/)
- [Arduino Sketch Build Process](https://docs.arduino.cc/arduino-cli/sketch-build-process)
- [Arduino Library Specification](https://docs.arduino.cc/arduino-cli/library-specification/)
- [Arduino Package Index Specification](https://arduino.github.io/arduino-cli/latest/package_index_json-specification/)
- [Arduino Sketch Project File](https://arduino.github.io/arduino-cli/latest/sketch-project-file/)
- [ArduinoCore-zephyr platform.txt — 기준 commit](https://github.com/arduino/ArduinoCore-zephyr/blob/514a21feaa0fd62c3922243cba1a5a98f9f5fdf1/platform.txt)
- [ArduinoCore-zephyr boards.txt — 기준 commit](https://github.com/arduino/ArduinoCore-zephyr/blob/514a21feaa0fd62c3922243cba1a5a98f9f5fdf1/boards.txt)
- [nRF Connect SDK v3.4.0 Release Notes](https://github.com/nrfconnect/sdk-nrf/blob/v3.4.0/doc/nrf/releases_and_maturity/releases/release-notes-3.4.0.rst)
- [Zephyr 4.4.0: Building, Flashing and Debugging](https://docs.zephyrproject.org/4.4.0/develop/west/build-flash-debug.html)
- [Zephyr 4.4.0 Build System](https://docs.zephyrproject.org/4.4.0/build/cmake/index.html)
