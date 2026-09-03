# NU54DK Arduino Core — Windows 개발환경 설정

| 항목 | 내용 |
| --- | --- |
| 문서 ID | BUILD-WINDOWS-DEV-001 |
| 문서 개정 | 1.1 |
| 문서 상태 | 현재 source 개발 기준 |
| 적용 제품 버전 | `v0.3.0` stable 이후 `main` |
| 지원 host | Windows 10/11 x64 |
| 최종 갱신일 | 2026-09-03 |
| 작성자 | Quantum / NUCODE |

이 문서는 새 Windows PC에서 NU54DK Arduino Core의 source를 수정하고 로컬 gate와 실물 보드
시험을 실행할 수 있는 환경을 준비하는 절차다. Arduino IDE에서 정식 Core를 설치해 Sketch만
작성하려는 사용자는 저장소 개발 도구를 모두 설치할 필요가 없으며, 최상위
[빠른 시작](../../README.md#빠른-시작)을 따르면 된다.

---

## 1. 어떤 환경이 필요한가

| 용도 | 필요한 항목 |
| --- | --- |
| 정식 Core로 Sketch 작성 | Arduino IDE 2.x, NU54DK, USB data cable |
| 문서·Python 계약 시험 | Git, Python 3.12.10 |
| 전체 host gate | 위 항목 + C++17 host compiler(권장: WinLibs MinGW-w64) |
| source Arduino 시험 | 위 항목 + Arduino CLI 1.5.1 + 고정 Nordic 환경 |
| 실물 build/upload/HIL | 위 항목 + NU54DK, CMSIS-DAP V2, 고정 Toolchain의 pyOCD |
| Release·Actions 관리 | GitHub CLI(선택), GitHub 인증과 해당 저장소 권한 |
| 외장 J-Link 사용 | SEGGER J-Link Software(선택), 외장 probe와 올바른 SWD/VTref 배선 |

`CMake`, `Ninja`, `west`, Arm Zephyr compiler, Python package와 pyOCD는 고정 Nordic
Toolchain에 포함된다. 이 프로젝트의 target build를 위해 이들을 임의의 전역 버전으로 따로
설치하지 않는다. MinGW-w64는 target firmware compiler가 아니라 host C++ 의미 시험용이다.
Visual Studio Code와 C/C++ extension은 선택 가능한 편집 도구다. nRF Connect for Desktop과
nRF Connect for VS Code도 이 저장소의 build·upload 필수 조건은 아니다.

## 2. 프로젝트가 고정하는 버전

다음 값은 source의 `tools/nu54-prerequisites/pins.json`과
`tools/ci/ncs-3.4.0.lock.json`이 단일 원본이다.

| 항목 | 기준 | 성격 |
| --- | --- | --- |
| Python | 3.12.10 | CI와 로컬 software gate 기준 |
| Arduino CLI | 1.5.1 | CI와 release 검증 기준 |
| nRF Connect SDK | v3.4.0, 고정 commit | target build 필수 |
| Zephyr | 4.4.0, 고정 commit | NCS workspace에 포함 |
| Nordic Toolchain | bundle `dcbdc366a1` | build 도구와 pyOCD 포함 |
| nRF Util | 8.2.1, 고정 SHA-256 | prerequisite 설치기에서 관리 |
| sdk-manager command | 1.16.1 | prerequisite 설치기에서 관리 |

Git과 GitHub CLI는 제품 산출물의 고정 입력이 아니다. 보안 수정이 반영된 최신 안정판을 쓰되,
release 증거에는 실제 사용 버전을 기록한다. WinLibs POSIX/UCRT GCC 16.1.0 r4는 Windows host
gate에서 검증한 권장 조합이며 target build identity에는 들어가지 않는다.

## 3. Windows 기본 도구 설치

관리자 또는 패키지 설치 권한이 있는 PowerShell에서 다음 명령을 실행한다. 이미 설치된 항목은
`winget list --id <ID>`로 확인한 뒤 생략할 수 있다.

```powershell
winget install --id Git.Git --exact --source winget `
  --accept-package-agreements --accept-source-agreements
winget install --id Python.Python.3.12 --exact --version 3.12.10 --source winget `
  --accept-package-agreements --accept-source-agreements
$WinLibsRoot = Join-Path $env:LOCALAPPDATA 'NUCODE\Toolchains\WinLibs-16.1.0-UCRT'
winget install --id BrechtSanders.WinLibs.POSIX.UCRT --exact `
  --version 16.1.0-14.0.0-r4 --source winget `
  --location $WinLibsRoot `
  --accept-package-agreements --accept-source-agreements
winget install --id ArduinoSA.CLI --exact --version 1.5.1 --source winget `
  --accept-package-agreements --accept-source-agreements
```

Release와 GitHub Actions를 명령행에서 관리할 개발자만 GitHub CLI를 추가한다.

```powershell
winget install --id GitHub.cli --exact --source winget `
  --accept-package-agreements --accept-source-agreements
```

설치가 끝나면 모든 PowerShell 창을 닫고 새 창을 연다. WinLibs portable package는 시스템
`PATH`를 바꾸지 않으므로 사용할 session에서 `mingw64\bin`을 앞에 추가한다. 다음 명령이 각각
실행 파일과 버전을 표시해야 한다.

```powershell
$WinLibsRoot = Join-Path $env:LOCALAPPDATA 'NUCODE\Toolchains\WinLibs-16.1.0-UCRT'
$WinLibsBin = Join-Path $WinLibsRoot 'mingw64\bin'
$env:Path = $WinLibsBin + ';' + $env:Path

git --version
py -3.12 --version
g++ --version
arduino-cli version
gh --version                 # GitHub CLI를 설치한 경우만
```

Git push 인증과 GitHub CLI 인증은 별도일 수 있다. `gh`가 필요한 작업을 하기 전에는 다음을
확인한다.

```powershell
gh auth login
gh auth status
```

## 4. 저장소와 submodule 준비

```powershell
Set-Location C:\Users\<사용자>\GitHub
git clone --recurse-submodules https://github.com/EIDOSDATA/NU54DK_Arduino_Core.git
Set-Location .\NU54DK_Arduino_Core
git submodule update --init --recursive
git submodule status --recursive
```

`board_package/NU54DK_Zephyr_DTS`는 별도 보드 저장소를 가리키는 고정 submodule이다. Core
작업 중에는 이 디렉터리를 임의로 수정하지 않는다. 출력이 `-`로 시작하면 submodule이 아직
초기화되지 않은 것이므로 `git submodule update --init --recursive`를 다시 실행한다.

## 5. Host Python 환경 준비

저장소 루트에서 독립 virtual environment를 만들고 hash가 고정된 host 의존성만 설치한다.
`.venv`는 저장소에 commit하지 않는다.

```powershell
py -3.12 -m venv .venv
$Python = (Resolve-Path .\.venv\Scripts\python.exe).Path
& $Python -m pip install --disable-pip-version-check --no-deps `
  --only-binary=:all: --require-hashes `
  -r .\tools\ci\requirements-host.txt
```

전역 Python에 무작정 package를 추가하지 않는다. 특히 별도의 `pip install pyocd`는 권장하지
않는다. Target build와 upload는 다음 절에서 설치하는 Toolchain의 Python과 pyOCD를 사용해야
같은 NCS 환경을 재현한다.

## 6. 고정 Nordic SDK와 Toolchain 설치

저장소가 제공하는 설치기는 공식 nRF Util을 내려받아 SHA-256을 확인하고, 고정
sdk-manager·NCS·Zephyr·Toolchain을 설치한다. 기본 설치 위치는 다음과 같다.

```text
%USERPROFILE%\ncs\v3.4.0
%USERPROFILE%\ncs\toolchains\dcbdc366a1
%LOCALAPPDATA%\NUCODE\NU54DK_Arduino_Core
```

저장소 루트에서 실행한다. 다운로드 용량이 크므로 충분한 디스크 공간과 안정적인 인터넷
연결이 필요하다. 중간에 중단돼도 같은 명령으로 재개할 수 있다.

```powershell
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass `
  -File .\tools\nu54-prerequisites\install-nordic.ps1 `
  -PlatformRoot .
```

설치 완료 뒤 exact pin과 완료 marker를 다시 검사한다.

```powershell
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass `
  -File .\tools\nu54-prerequisites\verify-nordic.ps1 `
  -PlatformRoot . `
  -Json
```

기본 위치 대신 `C:\ncs` 같은 경로를 선택하려면 설치와 검증에 항상 같은 base root를
넘긴다. Build Adapter에는 version 디렉터리와 Toolchain 디렉터리를 각각 지정한다.

```powershell
$NcsBase = 'C:\ncs'
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass `
  -File .\tools\nu54-prerequisites\install-nordic.ps1 `
  -PlatformRoot . -NcsRoot $NcsBase
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass `
  -File .\tools\nu54-prerequisites\verify-nordic.ps1 `
  -PlatformRoot . -NcsRoot $NcsBase -Json

$env:NUCODE_NCS_ROOT = Join-Path $NcsBase 'v3.4.0'
$env:NUCODE_TOOLCHAIN_ROOT = Join-Path $NcsBase 'toolchains\dcbdc366a1'
```

환경 변수는 필요한 PowerShell session에만 설정하는 편이 안전하다. 향후 pin이 바뀌었는데
사용자 전역 변수에 과거 경로가 남아 잘못된 Toolchain을 선택하는 일을 피할 수 있다.

## 7. pyOCD와 NU54DK 연결 확인

pyOCD는 Nordic Toolchain에 포함된 실행 파일을 직접 사용한다. 기본 설치 위치의 예는 다음과
같다.

```powershell
$NcsBase = Join-Path $env:USERPROFILE 'ncs'
$ToolchainRoot = Join-Path $NcsBase 'toolchains\dcbdc366a1'
$NcsPython = Join-Path $ToolchainRoot 'opt\bin\python.exe'
$PyOcd = Join-Path $ToolchainRoot 'opt\bin\Scripts\pyocd.exe'

& $NcsPython --version
& $PyOcd --version
& $PyOcd list
```

NU54DK의 debug USB connector를 **data 통신이 가능한 cable**로 연결한다. `pyocd list`에
온보드 CMSIS-DAP V2 probe가 하나 나타나고, Windows 장치 관리자에는 target UART용 COM port가
나타나야 한다. probe UID는 장치 선택 정보이므로 Issue, 공개 log 또는 화면 캡처에 그대로
노출하지 않는다.

장치가 보이지 않으면 다음을 순서대로 확인한다.

1. 충전 전용 cable이 아닌지 확인하고 다른 USB port에 직접 연결한다.
2. Arduino IDE, serial monitor, 다른 pyOCD/J-Link session처럼 probe나 COM port를 점유한
   프로그램을 닫는다.
3. 보드를 뺐다가 다시 연결하고 `& $PyOcd list`를 다시 실행한다.
4. `verify-nordic.ps1`로 Toolchain 손상 여부를 확인한다.

일반 upload에서 mass erase나 recover를 자동으로 실행하지 않는다. 보호 상태 복구나 전체
삭제는 데이터를 잃을 수 있으므로 원인이 확인된 별도 복구 절차에서만 수행한다.

## 8. Nordic Toolchain terminal이 필요한 경우

Build Adapter와 Arduino recipe는 `environment.json`을 자동 적용한다. `west`, CMake, Ninja를
직접 실행하는 HIL build는 고정 Toolchain terminal에서 해야 한다. 저장소 설치기가 배치한
nRF Util로 새 terminal을 열 수 있다.

```powershell
$RepoRoot = (Get-Location).Path
$NcsBase = Join-Path $env:USERPROFILE 'ncs'
$ApplicationRoot = Join-Path $env:LOCALAPPDATA 'NUCODE\NU54DK_Arduino_Core'
$env:NRFUTIL_HOME = Join-Path $ApplicationRoot 'nrfutil'
$NrfUtil = Join-Path $ApplicationRoot 'tools\nrfutil.exe'

& $NrfUtil sdk-manager toolchain launch `
  --toolchain-bundle-id dcbdc366a1 `
  --install-dir $NcsBase `
  --chdir $RepoRoot `
  --terminal
```

열린 terminal에서 `python --version`, `west --version`, `cmake --version`, `ninja --version`,
`pyocd --version`을 확인한다. HIL별 실제 build·배선·실행 명령은
[NU54DK HIL 시험](../../tests/hil/nu54dk/README.md)을 따른다.

## 9. 로컬 software gate 실행

Host C++ 시험이 compiler를 확실히 찾고, 생성된 실행 파일이 MinGW runtime DLL을 읽을 수
있도록 `CXX`와 `PATH`를 같은 session에 설정한다.

```powershell
$Python = (Resolve-Path .\.venv\Scripts\python.exe).Path
$WinLibsRoot = Join-Path $env:LOCALAPPDATA 'NUCODE\Toolchains\WinLibs-16.1.0-UCRT'
$WinLibsBin = Join-Path $WinLibsRoot 'mingw64\bin'
$env:Path = $WinLibsBin + ';' + $env:Path
$Gxx = (Get-Command g++.exe -ErrorAction Stop).Source
$env:CXX = $Gxx
$ArduinoCli = (Get-Command arduino-cli.exe -ErrorAction Stop).Source

& $Python .\tools\ci\run_m12_gate.py docs
& $Python .\tools\ci\run_m12_gate.py contract
& $Python .\tools\ci\run_m12_gate.py inventory
& $Python .\tools\ci\run_m12_gate.py host
& $Python .\tools\ci\run_m12_gate.py package
& $Python .\tools\ci\run_m12_gate.py examples --arduino-cli $ArduinoCli
```

각 명령은 `M12_GATE_PASS=<gate>`로 끝나야 한다. `host` 결과에 compiler 부재로 인한 skip이
있으면 전체 host 환경이 준비된 것으로 보지 않는다. Windows Application Control이 임시 native
실행 파일만 차단한 경우에는 시험 출력의 명시적 skip 사유와 target Zephyr 시험 결과를 함께
판정한다.

고정 NCS 설치본까지 포함해 M23 manifest의 DTS identity를 확인할 때는 다음 명령을 추가한다.

```powershell
& $Python .\tools\peripheral\verify_m23_inventory.py --ncs-root $NcsRoot
```

성공 표식은 `M23_INVENTORY_PASS=instances:75`다. Manifest를 의도적으로 바꾼 경우에만 먼저
`--write`로 C++ table과 Markdown matrix를 다시 생성하고, 생성 diff를 함께 검토한다.

Source 전체 Arduino compile은 고정 Nordic 설치가 끝난 뒤 다음처럼 격리된 임시 Arduino
hardware 경로에서 실행할 수 있다. 이 시험은 시간이 오래 걸리며 실제 build를 수행한다.

```powershell
& $Python .\tests\arduino-cli\run_smoke.py `
  --cli $ArduinoCli `
  --tests blink library config error parallel incremental m6 m7 m8 m9 m11 m15 m16 m21 ac02b ac03 examples
```

정식 설치본의 build/upload 수명주기를 확인하려면 source staging 시험으로 대체하지 말고
[v0.3.0 설치와 시험](../05_릴리스/v0.3.0/TESTING.md)의 stable Boards Manager 절차를 사용한다.

## 10. 실물 시험 준비물

- NU54DK 한 대: Blink, GPIO, 단일 보드 peripheral, upload/debug 시험
- NU54DK 두 대: BLE Central/Peripheral pair와 일부 peripheral 동시 시험
- 보드별 USB data cable과 독립 CMSIS-DAP V2/UART 연결
- HIL 문서가 지정한 jumper wire와 pin fixture
- 외장 J-Link 경로를 시험할 때만 SEGGER J-Link Software와 외장 probe

HIL PASS는 firmware가 한번 실행됐다는 사실만으로 선언하지 않는다. 시험 runner가 요구하는
exact Core/board revision, artifact hash, probe와 COM 선택, wiring 조건과 evidence 파일을 모두
충족해야 한다. 각 시험의 구체적인 조건은 [NU54DK HIL 시험](../../tests/hil/nu54dk/README.md)을
단일 원본으로 삼는다.

## 11. 자주 생기는 문제

| 증상 | 확인할 내용 |
| --- | --- |
| `g++`를 찾지 못함 | 3절의 `$WinLibsBin`이 실제 설치 경로인지 확인하고 session `PATH`에 추가 |
| Host EXE가 DLL을 찾지 못함 | 9절처럼 `g++.exe`의 디렉터리를 시험 session의 `PATH` 앞에 추가 |
| NCS를 찾지 못함 | 기본 경로를 쓰거나 `NUCODE_NCS_ROOT`를 `...\v3.4.0`으로 지정 |
| Toolchain을 찾지 못함 | `NUCODE_TOOLCHAIN_ROOT`를 `...\toolchains\dcbdc366a1`로 지정 |
| prerequisite hash/revision 실패 | 임의 파일 교체를 중단하고 설치기를 재실행한 뒤 log 확인 |
| pyOCD probe가 0개 | data cable, debug connector, USB port와 장치 점유 프로그램 확인 |
| pyOCD probe가 여러 개 | 자동 선택에 맡기지 말고 해당 HIL/upload 명령에서 UID 명시 |
| COM port를 열 수 없음 | Serial Monitor와 다른 runner를 닫고 보드를 다시 연결 |
| `gh auth status` 실패 | `gh auth login` 실행; Git push credential과 별도임에 유의 |

Prerequisite 설치 log는 `%LOCALAPPDATA%\NUCODE\NU54DK_Arduino_Core\logs`에 남는다. 정식
Core 설치·빌드 문제는 [v0.3.0 문제 해결](../05_릴리스/v0.3.0/TROUBLESHOOTING.md)도 함께
확인한다.

## 12. 완료 점검표

- [ ] `git`, Python 3.12.10, `g++`, Arduino CLI 1.5.1이 새 PowerShell에서 실행된다.
- [ ] 저장소와 `board_package/NU54DK_Zephyr_DTS` submodule이 초기화됐다.
- [ ] `.venv`에 hash 고정 host 요구사항을 설치했다.
- [ ] `verify-nordic.ps1 -Json` 결과가 `status: ready`다.
- [ ] 고정 Toolchain의 `pyocd list`가 연결한 NU54DK를 표시한다.
- [ ] docs, contract, host, package, examples software gate가 통과한다.
- [ ] 작업할 HIL의 보드 수, USB cable과 fixture 조건을 확인했다.
- [ ] GitHub 작업이 필요하면 `gh auth status`와 저장소 권한을 확인했다.

## 13. 관련 문서

- [Nordic prerequisite 설치 계약](../../tools/nu54-prerequisites/README.md)
- [Arduino CLI와 IDE 통합](./03_Arduino_CLI_통합.md)
- [Upload와 debug](./05_업로드와_디버그.md)
- [Boards Manager 설치와 package](./06_Boards_Manager_설치와_패키징.md)
- [CI/CD와 재현 build](./08_M12_CI_CD와_재현_빌드.md)
- [NU54DK HIL 시험](../../tests/hil/nu54dk/README.md)
- [v0.3.0 설치와 시험](../05_릴리스/v0.3.0/TESTING.md)
- [v0.3.0 문제 해결](../05_릴리스/v0.3.0/TROUBLESHOOTING.md)
