# Boards Manager 설치와 패키징 — stable v0.3.0

| 항목 | 값 |
| --- | --- |
| Package | `nucode:zephyr` |
| Board FQBN | `nucode:zephyr:nu54dk` |
| 현재 stable | `0.3.0` |
| 보존한 downgrade 버전 | `0.2.0`, `0.1.0` |
| 공식 사용자 OS | Windows 10/11 x64 |

## Stable index와 설치

Arduino IDE와 Arduino CLI의 일반 update channel은 다음 URL입니다.

```text
https://raw.githubusercontent.com/EIDOSDATA/NU54DK_Arduino_Core/main/package_nucode_nu54dk_index.json
```

Index는 최신순 `0.3.0`, `0.2.0`, `0.1.0`을 제공합니다. 이전 버전은 비지원 상태지만 재현성과
downgrade를 위해 항목을 보존합니다. RC/preview index는 신규 설치에 사용하지 않습니다.

Arduino CLI 설치 예시:

```powershell
$StableIndex = 'https://raw.githubusercontent.com/EIDOSDATA/NU54DK_Arduino_Core/main/package_nucode_nu54dk_index.json'
arduino-cli core update-index --additional-urls $StableIndex
arduino-cli core install nucode:zephyr@0.3.0 --run-post-install --additional-urls $StableIndex
arduino-cli core list
arduino-cli board listall nucode:zephyr
```

설치된 platform의 기본 위치는 다음과 같습니다.

```text
%LOCALAPPDATA%\Arduino15\packages\nucode\hardware\zephyr\0.3.0
```

## 고정 prerequisite

| 구성 요소 | 고정 값 |
| --- | --- |
| nRF Util | `8.2.1` |
| nRF Util SHA-256 | `1d291d8a9d6bb5bec18454f8d95064aed7f62e8997ec1c4511f13bdf1124c037` |
| `sdk-manager` | `1.16.1` |
| nRF Connect SDK | `v3.4.0` / `99553055607b2e9885fbc80ccd11fa9da81c2df0` |
| Zephyr | `4.4.0` / `bf801e4e3d19e1ffa76164346480cb7734dd2800` |
| Toolchain bundle | `dcbdc366a1` |

단일 원본은 [`pins.json`](../../tools/nu54-prerequisites/pins.json)과
[`nrfutil-requirements.json`](../../tools/nu54-prerequisites/nrfutil-requirements.json)입니다.
NCS/Toolchain은 Core ZIP에 넣지 않고 `post_install.bat`이 Nordic 공식 배포 경로에서
사용자 영역에 준비합니다. 같은 exact 설치는 Core version 간 공유하며 uninstall 때 자동
삭제하지 않습니다.

## Compile과 Upload

```powershell
$BuildPath = Join-Path $PWD 'build\blink'
$Sketch = "$env:LOCALAPPDATA\Arduino15\packages\nucode\hardware\zephyr\0.3.0\libraries\NUCODE_NU54DK\examples\Blink"
arduino-cli compile --fqbn nucode:zephyr:nu54dk --build-path $BuildPath $Sketch
arduino-cli upload --fqbn nucode:zephyr:nu54dk --build-path $BuildPath $Sketch
```

Upload에는 compile과 같은 FQBN, board options와 build path를 사용합니다. 여러 CMSIS-DAP,
BLE profile과 J-Link 경로는 [Arduino CLI 통합](03_Arduino_CLI_통합.md)과
[업로드와 디버그](05_업로드와_디버그.md)를 따릅니다.

## Package 생성 계약

재현 가능한 ZIP과 metadata 생성기는
[`nu54_package.py`](../../packaging/boards-manager/nu54_package.py)입니다. Exact release
commit의 깨끗한 worktree에서 `build-stable.ps1`을 실행합니다.

```powershell
.\packaging\boards-manager\build-stable.ps1 `
  -Version 0.3.0 `
  -Commit HEAD `
  -OutputDirectory C:\NU54DEV\stable\candidate `
  -VenvPath C:\NU54DEV\venv\host-3.12.10
```

Package gate는 archive root, allowlist, executable metadata, version, board submodule revision,
checksum, release manifest, SPDX와 license inventory를 검증합니다. Index는 검증한 archive만
최신순으로 기록합니다.

공개 stable은 exact source commit과 ZIP byte identity를 고정합니다. 같은 version으로 다른
source를 포장하거나 tag·asset을 이동·교체하지 않습니다. 이미 공개한 이전 stable은 해당 tag의
별도 worktree에서 감사하고 현재 도구로 재생성하지 않습니다.

## v0.3.0 공개 기준

- 두 독립 package build의 모든 산출물 byte 일치
- RC3와 stable의 version-independent runtime payload 일치
- Host, docs와 package validator PASS
- 격리 `0.2.0 → 0.3.0 → 0.2.0 → 0.3.0 → uninstall` lifecycle
- 설치된 package의 예제 29/29 compile과 Blink NU54DK pyOCD upload
- Annotated tag, 정확히 7개 Release asset과 공개 URL 재검증

정확한 자산과 실행 결과는
[v0.3.0 정식 공개 기록](<../04_검증 기록/32_M22_v0.3.0_정식_릴리스_공개_기록.md>)을
기준으로 합니다. 사용자 진단은 [v0.3.0 문제 해결](<../05_릴리스/v0.3.0/TROUBLESHOOTING.md>)을
확인하십시오.
