# West Native Blink PoC

| 항목 | 내용 |
| --- | --- |
| 문서 상태 | M3 완료 — west-native와 자동 HIL 기준선 통과 |
| M3 상태 | **완료** |
| 작성자 | Quantum / NUCODE |
| 기준 SDK | nRF Connect SDK v3.4.0 |
| 기준 Zephyr | Zephyr 4.4.0 |
| 대상 보드 | `nrf54l15dk/nrf54l15/cpuapp/nu54dk` |
| 호스트 우선순위 | Windows 우선 |
| 빌드 방식 | Loader 없는 Native Full Zephyr, 단일 이미지 |

---

## 1. 목적

이 문서는 Arduino CLI 또는 Arduino IDE를 연결하기 전에 수행할 가장 작은 수직 검증인 west-native Blink PoC의 계약을 정의한다.

이 PoC가 증명해야 하는 것은 다음과 같다.

1. 이 저장소를 Zephyr module로 인식할 수 있다.
2. 별도 보드 패키지의 NU54DK board target을 실제 빌드에 사용할 수 있다.
3. Arduino Core의 최소 runtime과 `setup()`·`loop()` 호출 구조가 하나의 Zephyr 정적 이미지에 들어간다.
4. `LED_BUILTIN`이 NU54DK Devicetree의 `led0` alias를 통해 동작한다.
5. Loader, LLEXT, EDK 또는 별도 sketch partition 없이 리셋 직후 애플리케이션이 실행된다.
6. CMSIS-DAP와 pyOCD를 사용해 전체 Zephyr 이미지를 플래시할 수 있다.

이 결과는 이후 Build Adapter와 Arduino CLI 통합의 기준선이다. west-native PoC가 통과하기 전에는 Arduino recipe 문제와 Core 자체 문제를 섞어서 디버깅하지 않는다.

실제 실행 명령과 증거 경계는
[M3 GPIO·시간·Scheduler 기준선](<../04_검증 기록/03_M3_GPIO_시간과_Scheduler_기준선.md>)에
보관한다.

---

## 2. 범위

### 2.1 포함 범위

- NCS v3.4.0 환경 확인
- Zephyr 4.4.0 확인
- NU54DK board root 연결
- 이 저장소의 Zephyr module 연결
- `--no-sysbuild` 단일 이미지 빌드
- 최소 Arduino runtime 진입
- `setup()` 1회 호출과 `loop()` 반복 호출
- Devicetree 기반 내장 LED 점멸
- ELF, HEX, BIN, map, Kconfig 및 Devicetree 산출물 확인
- pyOCD를 이용한 일반 플래시
- J-Link runner 선택 가능성의 별도 확인
- 무변경 증분 빌드 확인

### 2.2 고정 조건

| 조건 | 고정값 |
| --- | --- |
| NCS | `v3.4.0` |
| Zephyr | `4.4.0` |
| Board target | `nrf54l15dk/nrf54l15/cpuapp/nu54dk` |
| Board root | `<repo>/board_package/NU54DK_Zephyr_DTS` |
| Zephyr module root | `<repo>` |
| Sysbuild | 사용하지 않음 |
| Loader/LLEXT | 사용하지 않음 |
| 기본 flash runner | `pyocd` |
| 일반 업로드 erase | 사용하지 않음 |

`<repo>`는 `NU54DK_Arduino_Core` 저장소의 절대 경로다. PowerShell에서는 현재 checkout을
기준으로 계산하고, CMake에 전달할 때 Windows 경로도 `/` 구분자로 정규화한다.

~~~powershell
$CoreRoot = (Resolve-Path ".").Path.Replace('\', '/')
~~~

### 2.3 현재 M3 실행 결과

2026-08-27 기준 west-native 수직 경로와 M3 자동 회귀를 완료했다.

| 검증 | 결과 | 비고 |
| --- | --- | --- |
| `blink` clean/warm build | PASS | 무변경 rebuild에서 Core compile과 link는 발생하지 않음 |
| `gpio_input_smoke` clean build와 버튼 육안 | PASS | 버튼에 따른 LED 동작 확인 |
| GPIO 입력 RAM trace | 범위 제외 | 사용자 결정에 따라 M3 필수 증거에서 제외 |
| `runtime_timing` clean build와 trace | PASS | 내부 시간·scheduler 판정 PASS |
| Core 비활성 negative | PASS | Core archive와 runtime의 비의도 주입 없음 |
| `led0` 누락 negative | PASS | 의도한 configure 실패 확인 |
| Blink와 버튼 실기 | PASS | 사용자 육안 판정 |
| ztest/Twister NU54DK HIL | PASS | DAPLink MSD flash, COM console, 9/9 test case |

기본 loop 반환 정책은 `CONFIG_NUCODE_ARDUINO_LOOP_SLEEP_ONE_TICK=y`다. 계측용
`runtime_timing` sample만 자동 loop 정책을 끄고 spin, `yield()`, 한 tick sleep 및
`delay(1)`을 직접 비교한다.

생성된 `runners.yaml`에는 `nrfutil`, `jlink`, `pyocd`가 available runner로 나타나며
flash/debug 기본값은 `pyocd`다. J-Link device와 speed metadata는 생성되지만 외장
J-Link flash/debug HIL은 실행하지 않았다. 외부 계측과 실제 system PM 시험은 사용자
결정에 따라 M3 필수 증거에서 제외했다. 32-bit rollover와 긴 delay 경계는 production
helper에 값을 주입하는 ztest로 검증했다.

---

## 3. 사전 조건

### 3.1 저장소 조건

다음 경로가 존재해야 한다.

~~~text
<repo>/board_package/NU54DK_Zephyr_DTS/boards/nucode/nu54dk
<repo>/zephyr/module.yml
<repo>/zephyr/CMakeLists.txt
<repo>/zephyr/Kconfig
<repo>/samples/zephyr/blink/CMakeLists.txt
<repo>/samples/zephyr/blink/prj.conf
<repo>/samples/zephyr/blink/src/Blink.cpp
~~~

Git submodule을 사용한 개발 checkout이라면 다음 명령이 성공해야 한다.

~~~powershell
git submodule status --recursive
~~~

출력 앞에 `-`가 표시되면 보드 패키지가 초기화되지 않은 것이다.

~~~powershell
git submodule update --init --recursive
~~~

### 3.2 도구 조건

NCS v3.4.0 Toolchain 환경에서 다음 명령이 모두 성공해야 한다.

~~~powershell
west --version
cmake --version
ninja --version
python --version
pyocd --version
~~~

Windows의 일반 PowerShell에서 `west`가 보이지 않는다고 해서 임의의 시스템 Python에 설치하지 않는다. 첫 PoC는 nRF Connect SDK Toolchain이 활성화된 터미널에서 실행한다. 이후 Build Adapter가 IDE 외부에서도 같은 환경을 찾는 방법은 [Build Adapter 설계](./02_Build_Adapter_설계.md)에서 정의한다.

### 3.3 보드 연결 조건

- NU54DK의 CMSIS-DAP USB가 연결되어 있어야 한다.
- 첫 검증에서는 한 대의 CMSIS-DAP probe만 연결하는 것을 권장한다.
- pyOCD가 probe를 열 수 있어야 한다.
- SWD 전원 및 target 전압이 정상이어야 한다.
- 일반 플래시에서 mass erase 또는 recover를 요구하지 않는 정상 보드 상태여야 한다.

---

## 4. 입력과 출력

### 4.1 입력

| 입력 | 경로 또는 값 | 책임 |
| --- | --- | --- |
| 애플리케이션 소스 | `<repo>/samples/zephyr/blink` | PoC의 `setup()`·`loop()` 및 LED 동작 |
| 기본 Kconfig | `<repo>/samples/zephyr/blink/prj.conf` | C++ 및 최소 Core 기능 활성화 |
| Core module | `<repo>/zephyr` 및 `<repo>/cores/arduino` | Arduino runtime과 API 구현 등록 |
| Variant | `<repo>/variants/nu54dk` | 논리 핀과 보드 상수 |
| Board package | `<repo>/board_package/NU54DK_Zephyr_DTS` | 실제 DTS, pinctrl, Kconfig, runner |
| Board target | `nrf54l15dk/nrf54l15/cpuapp/nu54dk` | NU54DK CPUAPP 선택 |

### 4.2 출력

PoC build directory를 `<repo>/build/west-native-blink`로 사용할 때 주요 산출물은 다음과 같다.

~~~text
<repo>/build/west-native-blink/
├─ build.ninja
├─ CMakeCache.txt
└─ zephyr/
   ├─ .config
   ├─ runners.yaml
   ├─ zephyr.dts
   ├─ zephyr.elf
   ├─ zephyr.hex
   ├─ zephyr.bin
   └─ zephyr.map
~~~

`--no-sysbuild`가 적용됐으므로 애플리케이션 산출물이 `build/<domain>/zephyr`와 같은 하위 domain 경로로 들어가면 안 된다. 이 PoC에서 `merged.hex`는 필수 산출물이 아니다.

---

## 5. 처리 흐름

~~~text
NCS v3.4.0 Toolchain 활성화
        │
        ▼
저장소·서브모듈·도구 사전 검사
        │
        ▼
BOARD_ROOT로 NU54DK 보드 패키지 등록
        │
        ▼
EXTRA_ZEPHYR_MODULES로 Arduino Core 저장소 등록
        │
        ▼
최초 1회 pristine + --no-sysbuild CMake 구성
        │
        ▼
Core + Variant + Blink를 Native Zephyr 정적 링크
        │
        ▼
ELF/HEX/Kconfig/DTS/runner 검사
        │
        ▼
erase 없는 pyOCD flash
        │
        ▼
LED 동작 및 무변경 증분 빌드 확인
~~~

PoC는 빌드와 플래시를 분리해서 실행한다. 빌드 실패와 probe 문제를 한 번에 진단하지 않는다.

---

## 6. 명령 계약

### 6.1 경로 준비

NCS v3.4.0 Toolchain이 활성화된 PowerShell에서 실행한다.

~~~powershell
$RepoRoot = (Resolve-Path '.').Path
$SourceDir = Join-Path $RepoRoot 'samples\zephyr\blink'
$BuildDir = Join-Path $RepoRoot 'build\west-native-blink'
$BoardRoot = Join-Path $RepoRoot 'board_package\NU54DK_Zephyr_DTS'

$RepoRootCMake = $RepoRoot.Replace('\', '/')
$BoardRootCMake = $BoardRoot.Replace('\', '/')
~~~

경로 변수는 사용자 홈이나 시스템 공용 환경 변수를 덮어쓰지 않는다.

### 6.2 최초 구성과 빌드

새 build directory를 만드는 최초 1회에만 pristine을 명시한다.

~~~powershell
west build `
  --pristine always `
  --no-sysbuild `
  -b 'nrf54l15dk/nrf54l15/cpuapp/nu54dk' `
  -d $BuildDir `
  $SourceDir `
  -- `
  "-DBOARD_ROOT=$BoardRootCMake" `
  "-DEXTRA_ZEPHYR_MODULES=$RepoRootCMake"
~~~

이 명령의 계약은 다음과 같다.

- `--pristine always`는 이 최초 명령 또는 명시적인 호환성 초기화에만 사용한다.
- `--no-sysbuild`는 보드 메타데이터의 sysbuild 기본값과 무관하게 단일 이미지를 강제한다.
- `BOARD_ROOT`는 보드 저장소 루트이며 `boards/nucode/nu54dk` 자체가 아니다.
- `EXTRA_ZEPHYR_MODULES`는 `zephyr/module.yml`이 들어 있는 저장소 루트다.
- Zephyr 4.4의 정식 변수인 `EXTRA_ZEPHYR_MODULES`를 사용하며 이전 이름인 `ZEPHYR_EXTRA_MODULES`를 새 설계에 사용하지 않는다.
- 명령에 Loader, LLEXT, MCUboot 또는 별도 child image 인자를 추가하지 않는다.

### 6.3 일반 증분 빌드

최초 빌드 후에는 다음 명령만 사용한다.

~~~powershell
west build -d $BuildDir
~~~

소스 변경만 있는 일반 개발 루프에서 `--pristine always`, `-p always` 또는 build directory 삭제를 사용하지 않는다.

### 6.4 CMake 재구성이 필요한 변경

`prj.conf`, Devicetree overlay, module CMake 또는 Kconfig가 변경된 경우 다음 명령을 사용할 수 있다.

~~~powershell
west build --cmake -d $BuildDir
~~~

board target, NCS 버전 또는 toolchain이 바뀌었다면 기존 build directory를 억지로 재사용하지 않는다. 새 key의 build directory를 만들거나 명시적인 pristine 초기화를 수행한다.

### 6.5 산출물 확인

~~~powershell
Get-Item (Join-Path $BuildDir 'zephyr\zephyr.elf')
Get-Item (Join-Path $BuildDir 'zephyr\zephyr.hex')
Get-Item (Join-Path $BuildDir 'zephyr\zephyr.map')

Select-String `
  -LiteralPath (Join-Path $BuildDir 'CMakeCache.txt') `
  -Pattern '^BOARD:|^BOARD_ROOT:|^EXTRA_ZEPHYR_MODULES:'
~~~

최종 Devicetree에서 `led0` alias와 연결된 node를 확인한다.

~~~powershell
Select-String `
  -LiteralPath (Join-Path $BuildDir 'zephyr\zephyr.dts') `
  -Pattern 'led0|gpio-leds'
~~~

최종 Kconfig에서 LLEXT가 활성화되지 않았는지 확인한다.

~~~powershell
Select-String `
  -LiteralPath (Join-Path $BuildDir 'zephyr\.config') `
  -Pattern 'CONFIG_LLEXT'
~~~

`# CONFIG_LLEXT is not set`은 허용한다. `CONFIG_LLEXT=y`는 PoC 실패다.

### 6.6 기본 플래시

일반 플래시는 erase 옵션 없이 수행한다.

~~~powershell
west flash -d $BuildDir -r pyocd
~~~

다음 옵션은 일반 Blink 업로드 계약에 포함하지 않는다.

~~~text
--erase
--recover
mass erase
~~~

J-Link 검증은 [업로드와 디버그](./05_업로드와_디버그.md)의 runner 등록 조건을 만족한 뒤 별도로 수행한다.

---

## 7. 소스와 파일 계약

### 7.1 애플리케이션 CMake

`samples/zephyr/blink/CMakeLists.txt`는 다음 책임만 가진다.

- Zephyr package 검색
- PoC project 선언
- Blink 소스를 `app` target에 등록
- 보드 또는 Core의 물리 핀을 직접 복제하지 않음

`BOARD_ROOT`와 `EXTRA_ZEPHYR_MODULES`의 절대 경로를 CMakeLists에 하드코딩하지 않는다.

### 7.2 `prj.conf`

PoC에 꼭 필요한 최소 설정만 둔다.

- C++ 애플리케이션 빌드에 필요한 설정
- GPIO 사용에 필요한 설정
- 최소 logging 또는 console 설정
- PoC에서 검증하려는 Arduino time/runtime 설정

LLEXT, shell 기반 sketch loader, MCUboot 또는 firmware update 기능은 활성화하지 않는다.

### 7.3 Blink 소스

Blink 소스는 다음 동작 계약을 가진다.

1. Zephyr `main()` 또는 Core runtime 진입점이 초기화된다.
2. `setup()`은 정확히 한 번 호출된다.
3. `loop()`는 반환할 때마다 다시 호출된다.
4. `LED_BUILTIN`의 GPIO controller와 pin은 Devicetree의 `led0` alias에서 얻는다.
5. Arduino `HIGH`와 `LOW`는 각각 raw 전기 High와 raw 전기 Low를 뜻한다.
6. Core의 `digitalWrite()`와 `digitalRead()` 구현은 `gpio_pin_set_raw()`와 `gpio_pin_get_raw()` 계열을 사용하며 DTS polarity flag로 Arduino 값을 반전하지 않는다.
7. 현재 NU54DK `LED0`는 Active High이므로 `HIGH`에서 켜지고 `LOW`에서 꺼지는지 확인한다.
8. 반복 대기에서 무한 busy loop를 만들지 않는다.

PoC 소스에 `P0.xx`와 같은 물리 핀 번호를 직접 쓰지 않는다.

### 7.4 Zephyr module

저장소 root를 `EXTRA_ZEPHYR_MODULES`로 넘겼을 때 다음이 등록돼야 한다.

- Arduino Core 구현 소스
- 공개 include directory
- NU54DK variant 소스
- 필요한 Kconfig symbol

동일 소스를 애플리케이션 CMake와 module CMake에서 중복 등록하지 않는다.

---

## 8. 오류 처리

| 증상 | 가능한 원인 | 처리 |
| --- | --- | --- |
| `No board named ...` | `BOARD_ROOT` 누락, 잘못된 root, 서브모듈 미초기화 | 보드 파일 존재와 CMake 경로 정규화 확인 |
| board target이 Nordic 기본 DK로 해석됨 | `/nu54dk` qualifier 누락 | 전체 target 문자열을 그대로 사용 |
| build output이 domain 하위에 생성됨 | sysbuild가 활성화됨 | configure 명령에 `--no-sysbuild` 확인 |
| module을 찾지 못함 | `EXTRA_ZEPHYR_MODULES`가 `<repo>/zephyr`로 잘못 지정됨 | module root인 `<repo>`를 전달 |
| `Arduino.h`를 찾지 못함 | module include 등록 누락 | `zephyr/CMakeLists.txt`의 공개 include 경로 확인 |
| `led0`가 없음 | 보드 DTS alias 누락 또는 잘못된 board 선택 | `zephyr.dts`와 보드 패키지 확인 |
| `HIGH/LOW` 전기값이 반전됨 | raw API 대신 logical GPIO API를 사용함 | `gpio_pin_set_raw/get_raw` 계약과 NU54DK LED0 Active High 연결 확인 |
| `CONFIG_LLEXT=y` | 잘못된 기본 config 또는 기존 loader 설정 유입 | LLEXT config 제거 후 CMake 재구성 |
| pyOCD가 probe를 찾지 못함 | USB, driver, 권한, 다중 probe 문제 | `pyocd list`로 probe 확인 |
| pyOCD target 미지원 | pyOCD 버전 또는 target pack 문제 | `nrf54l` target 지원 여부를 확인하고 도구 버전 고정 |
| flash가 erase를 요구함 | 보호 상태 또는 이미지/주소 문제 | 일반 업로드에서 자동 erase하지 말고 별도 복구 절차로 분리 |
| 매 빌드가 전체 재컴파일됨 | 매번 pristine 사용 또는 CMake 인자를 반복 변경 | 일반 명령을 `west build -d`로 축소 |

오류를 해결하기 위해 NCS 설치 내부 또는 보드 서브모듈의 파일을 임시로 직접 수정하지 않는다. 필요한 변경은 해당 원본 저장소에서 관리한다.

---

## 9. 완료 기준

다음 조건과 합의된 자동 시험 기준을 만족해 west-native Blink PoC와 M3를 완료했다.

1. 고정 board target과 두 root 인자로 clean configure가 성공한다.
2. build가 `--no-sysbuild` 단일 이미지로 완료된다.
3. `zephyr.elf`, `zephyr.hex`, `zephyr.bin`, `zephyr.map`이 생성된다.
4. 최종 `.config`에 `CONFIG_LLEXT=y`가 없다.
5. 최종 ELF 안에 Core runtime, `setup()` 및 `loop()`가 함께 링크된다.
6. pyOCD로 erase 없이 플래시된다.
7. 리셋 직후 별도 loader 명령 없이 Blink가 시작된다.
8. NU54DK LED0가 raw `HIGH`에서 켜지고 raw `LOW`에서 꺼지며 주기가 의도대로다.
9. 무변경 두 번째 빌드가 전체 pristine rebuild를 수행하지 않는다.
10. `.ino`, Arduino CLI 또는 IDE가 없어도 이 기준선 시험을 반복할 수 있다.

완료 판정의 상세 근거와 범위 제외 항목은
[M3 GPIO·시간·Scheduler 기준선](<../04_검증 기록/03_M3_GPIO_시간과_Scheduler_기준선.md>)을
따른다. GPIO RAM trace, 외부 계측, 실제 system PM과 외장 J-Link HIL은 M3 필수 증거에서
제외했다. Twister 9/9와 runtime rollover·긴 delay 경계 자동 시험은 통과했다.

---

## 10. 검증 체크리스트

아래 목록은 반복 실행용 전체 체크리스트다. 현재 실행 결과를 표시한 목록이 아니며,
실제 PASS/미회수/미실행 상태는 위 M3 검증 기록을 기준으로 판단한다.

### 10.1 환경

- [ ] NCS v3.4.0 Toolchain에서 실행했다.
- [ ] Zephyr version 출력이 4.4.0이다.
- [ ] `west`, CMake, Ninja 및 Python 경로가 같은 NCS 환경에 속한다.
- [ ] 보드 서브모듈이 지정 commit으로 초기화됐다.

### 10.2 구성

- [ ] board target이 `nrf54l15dk/nrf54l15/cpuapp/nu54dk`다.
- [ ] `BOARD_ROOT=<repo>/board_package/NU54DK_Zephyr_DTS`다.
- [ ] `EXTRA_ZEPHYR_MODULES=<repo>`다.
- [ ] `--no-sysbuild`가 적용됐다.
- [ ] 최초 구성 외에는 pristine을 사용하지 않았다.

### 10.3 산출물

- [ ] `zephyr.elf`가 존재한다.
- [ ] `zephyr.hex`가 존재한다.
- [ ] `zephyr.map`이 존재한다.
- [ ] `zephyr.dts`에서 `led0`를 확인했다.
- [ ] `.config`에서 LLEXT 비활성화를 확인했다.
- [ ] `runners.yaml`에서 pyOCD 사용 가능 여부를 확인했다.

### 10.4 실기

- [ ] CMSIS-DAP가 pyOCD에서 열거된다.
- [ ] `west flash -r pyocd`가 erase 옵션 없이 성공한다.
- [ ] 리셋 직후 Blink가 시작된다.
- [ ] `HIGH/LOW`가 DTS polarity와 무관한 raw 전기값으로 동작한다.
- [ ] 현재 Active High LED0가 `HIGH`에서 켜지고 `LOW`에서 꺼진다.
- [ ] USB를 다시 연결해도 같은 동작을 반복한다.
- [ ] 무변경 증분 빌드가 성공한다.

---

## 11. 범위 제외

이 PoC에서는 다음을 구현하거나 검증하지 않는다.

- Arduino `.ino` 전처리
- Arduino library discovery
- Arduino CLI 및 Arduino IDE 버튼 통합
- 영구 Build Adapter cache
- sysbuild 또는 multi-image
- MCUboot, DFU, OTA, secure boot
- LLEXT 또는 runtime loader
- BLE, USB device, Wi-Fi 및 고급 주변장치 API
- 전체 Arduino pin map
- J-Link runner 수정 자체
- mass erase, recover 또는 보안 provisioning 자동화
- Boards Manager 배포 패키지

---

## 12. 참고문헌

- [nRF Connect SDK v3.4.0 Release Notes](https://github.com/nrfconnect/sdk-nrf/blob/v3.4.0/doc/nrf/releases_and_maturity/releases/release-notes-3.4.0.rst)
- [Zephyr 4.4.0: Building, Flashing and Debugging](https://docs.zephyrproject.org/4.4.0/develop/west/build-flash-debug.html)
- [Zephyr 4.4.0: Application Development](https://docs.zephyrproject.org/4.4.0/develop/application/index.html)
- [Zephyr 4.4.0: Modules](https://docs.zephyrproject.org/4.4.0/develop/modules.html)
- [Zephyr 4.4.0: Devicetree HOWTOs](https://docs.zephyrproject.org/4.4.0/build/dts/howtos.html)
- [Zephyr 4.4.0: Kconfig](https://docs.zephyrproject.org/4.4.0/build/kconfig/index.html)
- [pyOCD Documentation](https://pyocd.io/docs/)
