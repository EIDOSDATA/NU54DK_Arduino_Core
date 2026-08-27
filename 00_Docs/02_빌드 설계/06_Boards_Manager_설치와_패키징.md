# Boards Manager 설치와 패키징 설계

| 항목 | 내용 |
| --- | --- |
| 문서 상태 | M10 설치·패키징 계약 및 clean Windows 실기 검증 완료 |
| 작성자 | Quantum / NUCODE |
| 초기 지원 운영체제 | Windows 10/11 x64 |
| Arduino package | `nucode:zephyr` |
| Board FQBN | `nucode:zephyr:nu54dk` |
| 현재 검증 preview | `0.0.96`, `0.0.97` — clean Windows 최종 run 통과 |
| 펌웨어 구조 | Loader/LLEXT 없는 Native Full Zephyr image |

---

## 1. 목적

이 문서는 NU54DK Arduino Core를 공개 Arduino Boards Manager package로 배포하고,
처음 사용하는 Windows PC에서 Nordic 개발 환경을 사용자 영역에 설치하는 계약을 정의한다.

핵심 목표는 다음과 같다.

- Arduino IDE의 Boards Manager URL 한 개로 NU54DK Core를 찾고 설치
- Arduino CLI에서도 같은 공개 index와 같은 package를 사용
- Core ZIP과 Nordic SDK/Toolchain의 배포 경계를 분리
- NCS, Zephyr, Toolchain 및 설치 완료 상태를 정확한 version과 revision으로 검증
- 중단된 대용량 설치를 같은 명령으로 재개
- 온보드 CMSIS-DAP V2와 pyOCD로 Full Zephyr image를 직접 Upload
- 고정 Git commit에서 재현 가능한 archive, checksum, SBOM과 license inventory 생성
- preview upgrade/downgrade/uninstall/reinstall 수명주기 검증

이 문서는 설치와 패키징의 **설계 및 사용 방법**을 설명한다. 실제 clean Windows PC의
PASS/FAIL, 실행 시각, 로그와 측정값은 M10 검증 기록에서만 확정한다. 따라서 이 문서가
존재한다는 사실만으로 M10 완료를 의미하지 않는다.

---

## 2. 전체 구조

~~~text
공개 package index
  package_nucode_nu54dk_preview_index.json
            │
            ▼
GitHub prerelease의 Core ZIP
  Core + NU54DK board definition + 설치/검증 script
            │
            ├── post_install.bat
            │       │
            │       ▼
            │   Nordic 공식 nRF Util / sdk-manager
            │       │
            │       ├── %USERPROFILE%\ncs\v3.4.0
            │       └── %USERPROFILE%\ncs\toolchains\dcbdc366a1
            │
            ▼
Arduino compile → Full Zephyr ELF/HEX → CMSIS-DAP V2/pyOCD Upload
~~~

Boards Manager ZIP에는 Arduino Core, Build Adapter, NU54DK board definition과 prerequisite
설치 script만 들어 있다. Nordic가 배포하는 NCS, Zephyr, Toolchain, nRF Util과 pyOCD binary는
Core ZIP이나 package index의 `tools` 항목에 포함하지 않는다.

---

## 3. 공식 preview index

Arduino IDE와 Arduino CLI에서 사용하는 공식 preview index URL은 다음과 같다.

~~~text
https://raw.githubusercontent.com/EIDOSDATA/NU54DK_Arduino_Core/main/package_nucode_nu54dk_preview_index.json
~~~

index의 package identity는 다음과 같다.

| 항목 | 값 |
| --- | --- |
| package name | `nucode` |
| architecture | `zephyr` |
| Core identity | `nucode:zephyr` |
| Board FQBN | `nucode:zephyr:nu54dk` |
| archive 제공 위치 | `EIDOSDATA/NU54DK_Arduino_Core` GitHub prerelease asset |
| 외부 tool dependency | 없음 — NCS/Toolchain은 `post_install.bat`이 별도 설치 |

이 URL은 preview용이다. 최종 stable release 전에는 버전과 공개 상태가 바뀔 수 있으므로
제품이나 교육 자료에서 영구 stable URL로 간주하지 않는다.

---

## 4. 고정 prerequisite

현재 package는 다음 identity를 정확히 요구한다.

| 구성 요소 | 고정 값 |
| --- | --- |
| nRF Util | `8.2.1` |
| nRF Util SHA-256 | `1d291d8a9d6bb5bec18454f8d95064aed7f62e8997ec1c4511f13bdf1124c037` |
| sdk-manager command | `1.16.1` |
| nRF Connect SDK | `v3.4.0` |
| NCS `sdk-nrf` revision | `99553055607b2e9885fbc80ccd11fa9da81c2df0` |
| Zephyr | `4.4.0` |
| Zephyr revision | `bf801e4e3d19e1ffa76164346480cb7734dd2800` |
| Nordic Toolchain bundle | `dcbdc366a1` |
| Toolchain 내 pyOCD | Nordic bundle 포함; 별도 binary 재배포·독립 version pin 없음 |

단일 원본은 package의 `tools/nu54-prerequisites/pins.json`과
`nrfutil-requirements.json`이다. release manifest, 완료 marker와 Build Adapter는 이 pin을
교차 검증하며 하나라도 다르면 build를 시작하지 않는다.

nRF Util 공식 download URL은 version 문자열이 없는 URL이다. 설치기는 내려받은 실행 파일의
SHA-256이 위 pin과 다르면 새 byte를 자동 신뢰하지 않고 중단한다. upstream 파일이 바뀐 경우
개발자가 새 binary를 검토하고, pin과 package version을 함께 갱신해야 한다.

---

## 5. 설치 전 조건

- Windows 10/11 x64 사용자 계정
- Arduino IDE 2.x 또는 Arduino CLI
- GitHub와 Nordic download server에 접근 가능한 인터넷 연결
- NCS와 Toolchain을 저장할 충분한 여유 공간
- build와 Upload를 실행할 때 NU54DK 및 data 통신 가능한 USB cable

관리자 권한, 시스템 PATH 변경과 별도 nRF Connect for VS Code 설치는 package 계약에 포함되지
않는다. prerequisite는 현재 사용자 profile에 설치한다.

보드가 없어도 package download와 Nordic prerequisite 설치까지는 가능하다. 실제 pyOCD
Upload 검증에는 NU54DK의 온보드 CMSIS-DAP V2가 연결돼 있어야 한다.

---

## 6. Arduino IDE 설치

1. Arduino IDE에서 `File > Preferences`를 연다.
2. `Additional boards manager URLs`에 공식 preview index URL을 추가한다.
3. `Tools > Board > Boards Manager`를 열고 `NUCODE NU54DK Zephyr Boards`를 찾는다.
4. 현재 최신 검증 대상인 `0.0.97`을 선택해 설치한다.
5. post-install script 실행 확인이 나타나면 승인하고 Nordic prerequisite 설치가 끝날 때까지
   기다린다. 첫 설치는 NCS와 Toolchain download 때문에 오래 걸릴 수 있다.
6. `Tools > Board`에서 `NU54DK (nRF54L15, Zephyr)`를 선택한다.
7. 기본 Upload probe가 `CMSIS-DAP (pyOCD)`인지 확인한다.

IDE 또는 설치 환경이 post-install을 실행하지 않았거나 설치가 중단됐다면 설치된 platform의
다음 파일을 일반 사용자 권한으로 다시 실행한다.

~~~text
%LOCALAPPDATA%\Arduino15\packages\nucode\hardware\zephyr\0.0.97\post_install.bat
~~~

Arduino data directory를 변경했다면 위 경로의 `%LOCALAPPDATA%\Arduino15` 대신 실제 Arduino
data directory를 사용한다. 같은 script를 다시 실행해도 이미 검증된 prerequisite는 재사용한다.

---

## 7. Arduino CLI 설치

PowerShell에서 다음 명령을 실행한다.

~~~powershell
$IndexUrl = 'https://raw.githubusercontent.com/EIDOSDATA/NU54DK_Arduino_Core/main/package_nucode_nu54dk_preview_index.json'

arduino-cli config add board_manager.additional_urls $IndexUrl
arduino-cli core update-index
arduino-cli core install nucode:zephyr@0.0.97 --run-post-install
arduino-cli board details --fqbn nucode:zephyr:nu54dk
~~~

`--run-post-install`은 Nordic prerequisite 설치를 허용하기 위해 명시한다. 자동 실행 여부와
무관하게 설치기가 멱등인지 확인하거나 중단 설치를 재개하려면 설치된 platform의
`post_install.bat`을 한 번 더 직접 실행할 수 있다.

기본 Arduino data directory를 사용한다면 다음과 같다.

~~~powershell
& "$env:LOCALAPPDATA\Arduino15\packages\nucode\hardware\zephyr\0.0.97\post_install.bat"
~~~

설치 검증은 platform root를 지정해 실행한다.

~~~powershell
$PlatformRoot = "$env:LOCALAPPDATA\Arduino15\packages\nucode\hardware\zephyr\0.0.97"

powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File "$PlatformRoot\tools\nu54-prerequisites\verify-nordic.ps1" `
  -PlatformRoot $PlatformRoot `
  -Json
~~~

성공 결과의 `status`는 `ready`여야 하며 NCS/Zephyr revision, Toolchain bundle, nRF Util
version·hash와 완료 marker가 모두 package pin과 일치해야 한다.

---

## 8. 사용자 영역 설치 경로

설치기는 관리자 권한이나 PATH 변경 없이 다음 경로를 사용한다.

| 경로 | 용도 |
| --- | --- |
| `%USERPROFILE%\ncs\v3.4.0` | NCS v3.4.0 workspace |
| `%USERPROFILE%\ncs\toolchains\dcbdc366a1` | 고정 Nordic Toolchain bundle |
| `%LOCALAPPDATA%\NUCODE\NU54DK_Arduino_Core\tools\nrfutil.exe` | SHA-256으로 고정한 nRF Util |
| `%LOCALAPPDATA%\NUCODE\NU54DK_Arduino_Core\nrfutil` | nRF Util command state |
| `%LOCALAPPDATA%\NUCODE\NU54DK_Arduino_Core\prerequisites\ready.json` | 검증 완료 marker |
| `%LOCALAPPDATA%\NUCODE\NU54DK_Arduino_Core\logs` | prerequisite 설치 log |

Core를 upgrade하거나 uninstall해도 공유 NCS와 Toolchain을 자동 삭제하지 않는다. 여러 Core
version에서 같은 고정 prerequisite를 재사용하기 위한 의도적인 정책이다. 디스크 정리가
필요하면 설치된 Core가 더 이상 이 경로를 사용하지 않는지 확인한 뒤 사용자가 별도로 관리한다.

---

## 9. Build와 pyOCD Upload

Arduino CLI의 기본 수직 경로는 다음과 같다.

~~~powershell
$Sketch = 'C:\path\to\Blink'
$Build = 'C:\path\to\build\Blink'

arduino-cli compile `
  --fqbn nucode:zephyr:nu54dk `
  --build-path $Build `
  --export-binaries `
  $Sketch

arduino-cli upload `
  --fqbn nucode:zephyr:nu54dk `
  --input-dir $Build `
  $Sketch
~~~

기본 runner는 Toolchain에 포함된 pyOCD와 NU54DK 온보드 CMSIS-DAP V2다. Upload는 Loader나
LLEXT image가 아니라 build한 Full Zephyr HEX를 SWD로 직접 기록하고 target을 reset한다.

안전 정책은 다음과 같다.

- 일반 Upload에서 mass erase와 recover를 요청하지 않는다.
- 연결된 CMSIS-DAP가 없으면 실패한다.
- CMSIS-DAP가 둘 이상이면 임의의 probe를 선택하지 않고 실패한다.
- artifact manifest, board, Full Zephyr HEX/ELF hash가 다르면 flash하지 않는다.
- pyOCD 기본 Upload는 `smart_flash=false`로 동일 page 비교의 USB timeout을 회피한다.

외장 J-Link는 선택 경로다. IDE에서 J-Link를 선택할 때는 probe serial을 명시해야 하며,
초기 Boards Manager clean Windows 기준선의 기본 HIL 경로는 CMSIS-DAP V2/pyOCD다.

---

## 10. 설치 중단과 재개

설치 상태는 다음 marker로 관리한다.

| marker | 의미 |
| --- | --- |
| `installing.json` | 현재 설치 단계가 실행 중 |
| `incomplete.json` | 실패 또는 중단된 단계와 오류·log 경로 |
| `ready.json` | 모든 byte와 revision을 검증한 완료 상태 |

설치가 중단되면 `post_install.bat`을 같은 사용자 계정에서 다시 실행한다. 설치기는
`sdk-manager`의 멱등 설치 명령을 다시 호출하고, 이미 올바르게 설치된 데이터는 재사용한다.
동시에 두 설치 process가 실행되면 사용자 영역 mutex가 두 번째 실행을 기다리게 하며 timeout
후에는 실패한다.

`ready.json`이 있어도 그대로 신뢰하지 않는다. installer와 Build Adapter는 pin SHA-256,
NCS/Zephyr Git revision, Toolchain manifest bundle, nRF Util byte와 version을 재검증한다.

---

## 11. 문제 해결

### 11.1 nRF Util SHA-256 불일치

공식 unversioned URL의 byte가 pin과 달라진 상태다. 보안 검증을 우회하거나 임의 hash로
바꾸지 않는다. 개발자가 새 nRF Util을 별도로 검증하고 새 preview version과 함께 pin을
갱신할 때까지 설치를 중단한다.

### 11.2 `incomplete.json`이 남아 있음

`%LOCALAPPDATA%\NUCODE\NU54DK_Arduino_Core\logs`의 최신 log와 `incomplete.json`의
`phase`, `error`를 확인한 뒤 같은 `post_install.bat`을 다시 실행한다. 단순히 marker만
삭제하면 실제 설치가 완전해지지 않는다.

### 11.3 Build Adapter가 prerequisite 불일치를 보고함

다음 검증기를 먼저 실행한다.

~~~powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File '<platform-root>\tools\nu54-prerequisites\verify-nordic.ps1' `
  -PlatformRoot '<platform-root>' `
  -Json
~~~

실패 항목이 pin, release manifest, ready marker 중 어느 경계인지 확인한다. 서로 다른 preview의
script나 marker를 섞지 않는다.

### 11.4 pyOCD probe가 없음

- NU54DK의 CMSIS-DAP USB port와 data cable 연결을 확인한다.
- 장치 관리자에서 CMSIS-DAP 장치가 인식되는지 확인한다.
- `ready.json`의 `toolchain_root` 아래
  `opt\bin\Scripts\pyocd.exe list --probes --no-header`를 실행한다.
- probe가 둘 이상이면 하나만 연결한 뒤 다시 Upload한다.

### 11.5 Core 재설치 후 NCS를 다시 내려받음

같은 사용자 계정과 기본 `%USERPROFILE%\ncs`를 사용했는지 확인한다. `ready.json`, package의
`pins.json` 또는 실제 NCS/Toolchain identity가 다르면 안전상 재사용하지 않는다.

---

## 12. Preview version 수명주기

M10의 clean Windows package lifecycle 검증 쌍은 다음과 같다.

| version | 용도 |
| --- | --- |
| `0.0.96` | 최초 설치와 downgrade 기준 |
| `0.0.97` | upgrade 및 최종 reinstall 기준 |

검증 순서는 다음과 같이 고정한다.

1. package가 없고 prerequisite가 없는 clean Windows baseline 확인
2. `0.0.96` 설치와 post-install 실행
3. 고정 prerequisite 검증
4. board details 확인
5. Blink cold build와 같은 build path의 warm build
6. 단일 CMSIS-DAP V2 확인과 pyOCD Upload 10회
7. `0.0.97` upgrade
8. `0.0.96` downgrade
9. Core uninstall 후 공유 NCS/Toolchain 및 `ready.json` 보존 확인
10. `0.0.97` reinstall, prerequisite 재검증과 Blink build

`0.0.90`~`0.0.93`은 Windows PowerShell 5.1 호환성, BAT/CMD 인코딩 또는 Windows build
경로 길이 결함이 확인돼 폐기한 preview다. 네 version은 공식 preview index에서 제외하며 신규 설치, downgrade 또는 회귀
기준으로 사용하지 않는다. 이미 공개된 artifact를 같은 tag에서 덮어쓰지 않고 후속 version으로
수정한 것은 release asset의 불변성을 보존하기 위해서다.

`0.0.94`와 `0.0.95`도 PowerShell 5.1 runner의 비동기 Task 반환값이 success stream에
섞여 Arduino CLI identity preflight에서 실패했다. 공개된 두 preview는 immutable 실패
이력으로 보존하며 현재 lifecycle이나 M11 계승 증거에 사용하지 않는다. 반환값 누출을
억제한 runner를 포함하는 새 검증 쌍이 `0.0.96`과 `0.0.97`이다.

---

## 13. Package 생성 계약

패키징 도구는 작업 트리의 임의 byte가 아니라 지정한 Git commit만 입력으로 사용한다.
상위 저장소가 기록한 `board_package/NU54DK_Zephyr_DTS` gitlink revision도 정확히 펼쳐 하나의
Arduino platform ZIP을 만든다.

~~~powershell
python .\packaging\boards-manager\nu54_package.py build `
  --repo-root . `
  --output-dir .\build\boards-manager `
  --version 0.0.97 `
  --commit HEAD `
  --update-index
~~~

동일한 commit, version과 입력으로 다시 만들면 다음 특성이 같아야 한다.

- archive 내부 단일 top-level directory
- 고정 timestamp와 file mode
- UTF-8 byte 순서로 정렬한 entry
- ZIP STORE 방식
- 전체 archive SHA-256과 size
- release manifest와 내부 `CHECKSUMS.sha256`

Archive 검증 예시는 다음과 같다.

~~~powershell
python .\packaging\boards-manager\nu54_package.py validate `
  --archive .\build\boards-manager\nucode-nu54dk-zephyr-0.0.97.zip `
  --expected-version 0.0.97

python .\packaging\boards-manager\nu54_package.py validate-index `
  --index .\build\boards-manager\package_nucode_nu54dk_preview_index.json `
  --artifact-dir .\build\boards-manager
~~~

---

## 14. 공개 prerelease artifact

각 preview는 `m10-preview-<version>` Git tag와 GitHub prerelease에 다음 파일을 제공한다.

| artifact | 내용 |
| --- | --- |
| `nucode-nu54dk-zephyr-<version>.zip` | Boards Manager가 설치하는 platform archive |
| `*.release-manifest.json` | Core/board/NCS/Zephyr/Toolchain identity와 file provenance |
| `*.spdx.json` | SPDX 2.3 SBOM |
| `*.license-inventory.json` | 포함·외부 구성 요소의 license inventory |
| `*.THIRD_PARTY_NOTICES.md` | 제3자 고지와 재배포 경계 |
| `*.CHECKSUMS.sha256` | archive와 sidecar의 SHA-256 목록 |

package index는 ZIP의 공개 release URL, 정확한 byte size와 SHA-256을 기록한다. 설치 전후
검증에서는 mutable한 raw index만 신뢰하지 않고 release archive와 manifest identity를 함께
고정한다.

Archive 내부 보드 파일의 license 범위는 다음처럼 분리한다.

- Core 저장소와 board package 최상위 저작물: 해당 저장소가 선언한 MIT 범위
- `boards/nucode/nu54dk/**`의 Zephyr 파생 board 정의: Apache-2.0 범위와 NOTICE

license inventory와 SPDX SBOM은 기술적인 목록과 provenance를 제공하지만 법률 자문이나
최종 라이선스 판단을 대신하지 않는다.

---

## 15. Nordic 구성 요소 비재배포 정책

다음 구성 요소는 NU54DK Core release asset에 포함하지 않는다.

- nRF Util
- sdk-manager command package
- nRF Connect SDK
- Zephyr source tree
- Nordic Toolchain bundle
- Toolchain에 포함된 pyOCD
- 선택적으로 사용하는 SEGGER J-Link software

`post_install.bat`은 Nordic 공식 배포 경로를 통해 이들을 설치하고 package pin과 실제 byte를
검증한다. package index의 `tools`와 `toolsDependencies`도 비어 있어 Arduino package로 Nordic
binary를 재배포하지 않는다.

외부 prerequisite의 종합 license는 확인되지 않은 내용을 추정하지 않고 inventory에서
`NOASSERTION`으로 유지한다. 최종 공개 stable release 전에 담당자가 Nordic/SEGGER 조건과
프로젝트 고지의 적절성을 별도로 검토해야 한다.

---

## 16. 법률 및 최종 공개 경계

자동화가 수행할 수 있는 범위는 다음과 같다.

- archive 내용과 출처 목록 생성
- SPDX 2.3 SBOM 생성
- license identifier와 원문 inventory 생성
- checksum, manifest와 NOTICE 생성·검증
- Nordic binary가 ZIP/index에 포함되지 않았는지 검증

자동화가 최종 판단할 수 없는 범위는 다음과 같다.

- 각 license 의무를 모두 충족했다는 법률적 결론
- Nordic와 SEGGER 배포 조건에 대한 법률 자문
- 상표, 특허 또는 수출 통제 판단
- stable `v0.1.0` 공개 승인

따라서 preview package의 기술 검증이 성공하더라도 최종 stable release는 라이선스 검토와
프로젝트 소유자의 명시적 공개 승인 전까지 HOLD한다.

---

## 17. M10 완료 판정과 문서 경계

M10 완료 여부는 이 설계 문서가 아니라 별도의 clean Windows 검증 기록으로 판정한다. 최소
증거는 다음을 포함해야 한다.

- 공개 index와 두 prerelease archive의 URL·size·SHA-256 일치
- 완전히 분리된 Windows 사용자 환경의 초기 상태
- `0.0.96` 최초 설치와 Nordic exact-pin 검증
- Blink cold/warm build 결과
- 실제 NU54DK CMSIS-DAP V2/pyOCD Upload 10회 결과
- `0.0.97` upgrade, `0.0.96` downgrade
- uninstall 후 공유 prerequisite 보존
- `0.0.97` reinstall와 최종 build 결과
- 비밀 값과 probe UID를 제거한 evidence와 log

probe 없이 실행한 조사 모드나 `-AllowMissingProbe` 결과는 최종 HIL PASS 근거가 될 수 없다.

---

## 18. 관련 문서와 구현

- [Arduino CLI 통합](<./03_Arduino_CLI_통합.md>)
- [빌드 캐시와 산출물](<./04_빌드_캐시와_산출물.md>)
- [업로드와 디버그](<./05_업로드와_디버그.md>)
- [M9 증분 빌드·캐시와 재현성 기준선](<../04_검증 기록/09_M9_증분_빌드_캐시와_재현성_기준선.md>)
- `packaging/boards-manager/nu54_package.py`
- `tools/nu54-prerequisites/install-nordic.ps1`
- `tools/nu54-prerequisites/verify-nordic.ps1`
- `tools/remote-windows/m10/invoke-m10-clean-windows.ps1`
