# Boards Manager 설치와 패키징 — stable v0.2.0 / RC v0.3.0-rc.2

| 항목 | 값 |
| --- | --- |
| package | `nucode:zephyr` |
| board FQBN | `nucode:zephyr:nu54dk` |
| 현재 stable | `0.2.0` |
| 현재 시험 후보 | `0.3.0-rc.2` — 별도 RC index |
| 보존한 downgrade 버전 | `0.1.0` |
| 초기 지원 OS | Windows 10/11 x64 |

신규 사용자는 stable `0.2.0`을 설치한다. `0.1.0`과 과거 RC 문서는 downgrade·감사 증거로
남아 있지만 현재 설치 안내가 아니다. 정확한 공개 자산, checksum과 수명주기 결과는
[v0.2.0 정식 릴리스 공개 기록](<../04_검증 기록/21_v0.2.0_정식_릴리스_공개_기록.md>)에서
관리한다.

---

## 1. Stable index

Arduino IDE와 Arduino CLI의 일반 update channel은 다음 URL이다.

~~~text
https://raw.githubusercontent.com/EIDOSDATA/NU54DK_Arduino_Core/main/package_nucode_nu54dk_index.json
~~~

현재 index는 최신순으로 `0.2.0`, `0.1.0`을 제공한다. 특정 버전을 재현해야 하면 해당 GitHub
Release의 불변 index snapshot을 사용한다. RC 전용 index와 preview index는 신규 설치에 쓰지
않는다.

공개 검증된 `v0.3.0-rc.2`를 명시적으로 시험할 때만 다음 별도 index를 추가한다. RC 공개가 stable index의
version 순서나 byte를 바꾸지 않는다.

~~~text
https://github.com/EIDOSDATA/NU54DK_Arduino_Core/releases/download/v0.3.0-rc.2/package_nucode_nu54dk_rc_index.json
~~~

Index의 `tools`와 platform의 `toolsDependencies`는 비어 있다. Nordic NCS/Toolchain은 Core
ZIP에 넣지 않고 설치 후 `post_install.bat`이 Nordic 공식 배포 경로에서 준비한다.

---

## 2. 고정 prerequisite

현재 package가 검증하는 identity는 다음과 같다.

| 구성 요소 | 고정 값 |
| --- | --- |
| nRF Util | `8.2.1` |
| nRF Util SHA-256 | `1d291d8a9d6bb5bec18454f8d95064aed7f62e8997ec1c4511f13bdf1124c037` |
| `sdk-manager` command | `1.16.1` |
| nRF Connect SDK | `v3.4.0` / `99553055607b2e9885fbc80ccd11fa9da81c2df0` |
| Zephyr | `4.4.0` / `bf801e4e3d19e1ffa76164346480cb7734dd2800` |
| Windows Toolchain bundle | `dcbdc366a1` |

단일 원본은
[`pins.json`](../../tools/nu54-prerequisites/pins.json)과
[`nrfutil-requirements.json`](../../tools/nu54-prerequisites/nrfutil-requirements.json)이다.
설치기는 version 문자열이 없는 nRF Util URL에서 받은 byte도 위 SHA-256과 다르면 거부한다.

기본 설치 위치는 `%USERPROFILE%\ncs\v3.4.0`과
`%USERPROFILE%\ncs\toolchains\dcbdc366a1`이다. 관리자 권한이나 시스템 PATH 변경은 요구하지
않는다. 같은 exact NCS/Toolchain은 Core version 간 공유하며 Core 제거 시 자동 삭제하지
않는다.

---

## 3. Arduino IDE 설치

1. Arduino IDE 2.x의 Additional Boards Manager URLs에 stable index를 추가한다.
2. Boards Manager에서 `NUCODE NU54DK Zephyr Boards`를 찾는다.
3. 버전 `0.2.0`을 명시적으로 선택해 설치한다.
4. 설치 후 `NU54DK (nRF54L15, Zephyr)` 보드를 선택한다.

설치된 platform과 재실행 가능한 post-install 경로는 다음과 같다.

~~~text
%LOCALAPPDATA%\Arduino15\packages\nucode\hardware\zephyr\0.2.0
%LOCALAPPDATA%\Arduino15\packages\nucode\hardware\zephyr\0.2.0\post_install.bat
~~~

중단된 prerequisite 설치는 같은 `post_install.bat`을 일반 사용자 권한으로 다시 실행해
재개한다. 완료 marker와 pin이 일치하지 않으면 Build Adapter는 build 전에 실패한다.

---

## 4. Arduino CLI 설치와 확인

~~~powershell
$StableIndex = 'https://raw.githubusercontent.com/EIDOSDATA/NU54DK_Arduino_Core/main/package_nucode_nu54dk_index.json'

arduino-cli core update-index --additional-urls $StableIndex
arduino-cli core install nucode:zephyr@0.2.0 --run-post-install `
  --additional-urls $StableIndex
arduino-cli core list
arduino-cli board listall nucode:zephyr
~~~

설치 확인이 필요하면 platform의 검증 script를 실행한다.

~~~powershell
$PlatformRoot = "$env:LOCALAPPDATA\Arduino15\packages\nucode\hardware\zephyr\0.2.0"
& "$PlatformRoot\tools\nu54-prerequisites\verify-nordic.ps1" -PlatformRoot $PlatformRoot
~~~

기본 compile/upload 예시는 다음과 같다.

~~~powershell
$BuildPath = Join-Path $PWD 'build\blink'
$Sketch = "$env:LOCALAPPDATA\Arduino15\packages\nucode\hardware\zephyr\0.2.0\libraries\NUCODE_NU54DK\examples\Blink"

arduino-cli compile --fqbn nucode:zephyr:nu54dk --build-path $BuildPath $Sketch
arduino-cli upload --fqbn nucode:zephyr:nu54dk --build-path $BuildPath $Sketch
~~~

upload에는 compile과 같은 build path가 필요하다. 여러 probe, BLE profile과 J-Link 선택은
[Arduino CLI 통합](03_Arduino_CLI_통합.md)과
[업로드와 디버그](05_업로드와_디버그.md)를 따른다.

---

## 5. Package 생성 계약

재현 가능한 ZIP과 metadata 생성기는
[`nu54_package.py`](../../packaging/boards-manager/nu54_package.py)다. exact commit의 깨끗한
source에서 다음처럼 실행한다.

~~~powershell
python .\packaging\boards-manager\nu54_package.py build `
  --repo-root . `
  --output-dir .\build\boards-manager `
  --version 0.2.0 `
  --commit <exact-git-commit>

python .\packaging\boards-manager\nu54_package.py validate `
  --archive .\build\boards-manager\nucode-nu54dk-zephyr-0.2.0.zip `
  --expected-version 0.2.0 `
  --expected-commit <exact-git-commit>
~~~

Package gate는 archive root, 허용 파일, executable metadata, `platform.txt` version, board
submodule revision, checksum, SBOM과 license inventory를 검증한다. Index 생성은 같은 배포
channel의 이미 검증한 archive만 대상으로 하며 최신 version 순서를 강제한다.

공개 자산을 덮어쓰거나 기존 tag를 이동하지 않는다. Release candidate와 stable은 별도 index,
tag, archive와 승인 기록을 가진다. 도구가 만든 package는 자동으로 공개하지 않으며 사람의
릴리스 승인 뒤 별도 절차로 게시한다.

M22 RC2는 RC1 clean-room 실행기 결함을 교정하고 두 독립 build의 byte를 대조해 7개 asset만
공개했다. Public URL에서 package를 다시 받아 동일 PC 격리 clean-room에 설치한 뒤 8개
library·29개 예제 compile, 지정 UID Upload, downgrade/upgrade, uninstall/reinstall과 exact run
leaf cleanup을 통과했다. Stable `v0.2.0` index는 전후 크기·SHA-256·Git blob이 불변이다.

---

## 6. 설치 수명주기와 지원 경계

현재 stable 공개 검증의 수명주기는 다음 순서다.

~~~text
0.1.0 설치 → 0.2.0 upgrade → 0.1.0 downgrade
→ 0.2.0 재설치 → uninstall
~~~

정확한 실행 증거는 설계 문서에 복제하지 않는다. 과거 preview/RC의 설치 문제와 hash는
[M10 기준선](<../04_검증 기록/10_M10_Boards_Manager_패키징과_Clean_Windows_기준선.md>),
현재 stable 수명주기는
[v0.2.0 공개 기록](<../04_검증 기록/21_v0.2.0_정식_릴리스_공개_기록.md>)을 따른다.

Core ZIP은 Nordic NCS, Zephyr, Toolchain, nRF Util 또는 pyOCD binary를 재배포하지 않는다.
각 외부 구성 요소의 이용 조건과 최종 공개 승인은 package의 license inventory와 release
기록에서 관리한다. 이 문서는 법률 판단을 대신하지 않는다.

---

## 7. 문제 해결과 릴리스 문서

- [v0.2.0 릴리스 문서](<../05_릴리스/v0.2.0/README.md>)
- [v0.2.0 마이그레이션](<../05_릴리스/v0.2.0/MIGRATION.md>)
- [v0.2.0 문제 해결](<../05_릴리스/v0.2.0/TROUBLESHOOTING.md>)
- [v0.2.0 알려진 제약](<../05_릴리스/v0.2.0/KNOWN_ISSUES.md>)
- [M18 RC 공개 검증과 교정](<../04_검증 기록/20_M18_v0.2.0_rc1_공개_검증과_rc2_교정.md>)
- [v0.2.0 정식 릴리스 공개 기록](<../04_검증 기록/21_v0.2.0_정식_릴리스_공개_기록.md>)
- [v0.3.0-rc.2 설치와 시험](<../05_릴리스/v0.3.0-rc.2/TESTING.md>)
- [M22 v0.3.0-rc.1 중단 기록](<../04_검증 기록/29_M22_v0.3.0_rc1_통합_릴리스_기준선.md>)
- [M22 v0.3.0-rc.2 기준선](<../04_검증 기록/30_M22_v0.3.0_rc2_통합_릴리스_기준선.md>)
