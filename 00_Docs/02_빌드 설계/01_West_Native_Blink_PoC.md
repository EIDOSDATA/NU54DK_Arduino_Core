# West Native Blink PoC — M3 역사적 기준선

| 항목 | 내용 |
| --- | --- |
| 문서 상태 | **역사적 설계 기준선** — M3 완료 뒤 회귀용으로 유지 |
| 적용 범위 | Arduino CLI 통합 전 west-native 최소 수직 경로 |
| 기준 SDK | nRF Connect SDK v3.4.0 / Zephyr 4.4.0 |
| 대상 보드 | `nrf54l15dk/nrf54l15/cpuapp/nu54dk` |
| 이미지 | Loader/LLEXT 없는 단일 Full Zephyr 이미지 |

이 문서는 M3 당시 Arduino Core의 최소 실행 경로를 분리 검증한 PoC 계약이다. 현재 Boards
Manager 사용자 절차나 Build Adapter의 상세 구현 설명이 아니다. 실제 실행 결과, 수치와 판정은
[M3 GPIO·시간·Scheduler 기준선](<../04_검증 기록/03_M3_GPIO_시간과_Scheduler_기준선.md>)을
단일 원본으로 사용한다.

## 1. PoC가 증명한 경계

PoC는 다음 항목을 Arduino recipe와 분리해 검증했다.

- 이 저장소를 Zephyr module로 인식할 수 있다.
- NU54DK 보드 서브모듈의 board target을 사용할 수 있다.
- Core runtime, Variant와 Blink가 하나의 정적 Zephyr 이미지에 링크된다.
- `setup()`은 한 번, `loop()`는 반복 실행된다.
- `LED_BUILTIN`은 NU54DK Devicetree의 `led0` alias를 따른다.
- 기본 pyOCD runner로 전체 이미지를 일반 플래시할 수 있다.
- 최초 구성 뒤에는 같은 build tree에서 Ninja 증분 빌드가 동작한다.

PoC에는 Loader, LLEXT, EDK, MCUboot, 별도 sketch partition 또는 Arduino `.ino` 전처리가 없다.

## 2. 고정 입력

| 입력 | 값 |
| --- | --- |
| NCS | `v3.4.0` |
| Zephyr | `4.4.0` |
| Board target | `nrf54l15dk/nrf54l15/cpuapp/nu54dk` |
| Board root | `<repo>/board_package/NU54DK_Zephyr_DTS` |
| Zephyr module root | `<repo>` |
| Sysbuild | 사용하지 않음 |
| 기본 flash runner | `pyocd` |

필수 저장소 입력은 다음과 같다.

```text
board_package/NU54DK_Zephyr_DTS/boards/nucode/nu54dk/
zephyr/module.yml
zephyr/CMakeLists.txt
zephyr/Kconfig
samples/zephyr/blink/
cores/arduino/
variants/nu54dk/
```

보드 패키지는 고정 Git submodule이다. 개발 checkout에서는 다음 상태를 먼저 확인한다.

```powershell
git submodule status --recursive
git submodule update --init --recursive
```

## 3. 재현 명령

NCS v3.4.0 Toolchain이 활성화된 PowerShell에서 저장소 루트를 현재 디렉터리로 두고 실행한다.

```powershell
$RepoRoot = (Resolve-Path '.').Path
$SourceDir = Join-Path $RepoRoot 'samples\zephyr\blink'
$BuildDir = Join-Path $RepoRoot 'build\west-native-blink'
$BoardRoot = Join-Path $RepoRoot 'board_package\NU54DK_Zephyr_DTS'

$RepoRootCMake = $RepoRoot.Replace('\', '/')
$BoardRootCMake = $BoardRoot.Replace('\', '/')

west build `
  --pristine always `
  --no-sysbuild `
  -b 'nrf54l15dk/nrf54l15/cpuapp/nu54dk' `
  -d $BuildDir `
  $SourceDir `
  -- `
  "-DBOARD_ROOT=$BoardRootCMake" `
  "-DEXTRA_ZEPHYR_MODULES=$RepoRootCMake"
```

`--pristine always`는 새 build directory의 최초 구성 또는 명시적인 호환성 초기화에만 사용한다.
일반 반복 빌드는 다음 명령으로 충분하다.

```powershell
west build -d $BuildDir
```

Kconfig, CMake 또는 overlay 입력이 바뀌어 재구성만 필요하면 다음을 사용한다.

```powershell
west build --cmake -d $BuildDir
```

일반 플래시는 destructive option 없이 실행한다.

```powershell
west flash -d $BuildDir -r pyocd
```

다중 probe 선택, Arduino Upload 및 J-Link 경계는
[업로드와 디버그](./05_업로드와_디버그.md)가 소유한다.

## 4. 산출물과 불변 조건

`--no-sysbuild` PoC의 canonical 산출물은 다음 경로에 있다.

```text
<build>/zephyr/zephyr.elf
<build>/zephyr/zephyr.hex
<build>/zephyr/zephyr.bin
<build>/zephyr/zephyr.map
<build>/zephyr/.config
<build>/zephyr/zephyr.dts
<build>/zephyr/runners.yaml
```

다음 조건을 유지한다.

- `EXTRA_ZEPHYR_MODULES`에는 `<repo>/zephyr`가 아니라 module root인 `<repo>`를 전달한다.
- `BOARD_ROOT`에는 `boards/nucode/nu54dk`가 아니라 보드 저장소 루트를 전달한다.
- 최종 `.config`에 `CONFIG_LLEXT=y`가 없어야 한다.
- Core와 Variant source를 sample CMake에서 중복 등록하지 않는다.
- `digitalWrite(HIGH/LOW)`는 raw 전기 High/Low 의미를 유지한다.
- 일반 flash 실패 뒤 mass erase나 recover를 자동 실행하지 않는다.

## 5. 현재 문서 체계에서의 역할

이 PoC의 상세 실행 로그와 당시 완료 판정은 M3 검증 기록에 보존한다. 현재 구현을 확인할 때는
다음 활성 문서를 함께 사용한다.

- [Build Adapter 설계](./02_Build_Adapter_설계.md)
- [Arduino CLI 및 IDE 통합](./03_Arduino_CLI_통합.md)
- [빌드 캐시와 산출물](./04_빌드_캐시와_산출물.md)
- [M3 GPIO·시간·Scheduler 기준선](<../04_검증 기록/03_M3_GPIO_시간과_Scheduler_기준선.md>)

PoC 당시의 개별 횟수, 메모리 수치와 장비 식별자는 이 활성 설계 문서에 복제하지 않는다.
