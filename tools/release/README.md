# M11 release candidate 자동화

`nu54_release.py`는 `v0.1.0` 공개 직전까지 필요한 RC artifact와 검증 evidence를
로컬에서 준비한다. 이 도구는 Git tag 생성, push, GitHub Release 생성 및 stable 공개를
수행하지 않는다. 모든 기술 gate가 통과해도 결과는 `ready-for-human-approval`이며,
법률 검토와 최종 공개 승인은 항상 사람에게 남는다.

clean Windows Boards Manager 범위는 SHA-256까지 고정한 Arduino CLI `1.5.2-rc.1`
backend이다. Arduino IDE가 같은 package/index backend를 소비하더라도 GUI 조작 자체를
독립 자동 검증한 것으로 간주하지 않는다. plan과 최종 manifest는
`arduino_ide_gui.validated=false` 및 별도 known issue를 항상 기록한다.

현재 명시적으로 허용된 버전은 `0.1.0-rc.2`뿐이다. `0.1.0` stable이나 임의 RC 번호를
입력하면 fail-closed로 거부한다. M10 preview index와 RC index도 서로 다른 파일과 tag
규칙을 사용하므로 기존 공개 preview를 덮어쓰지 않는다.

## 1. RC artifact와 plan 준비

모든 구현·문서 변경을 먼저 commit하고 보드 submodule을 포함한 작업 트리를 깨끗하게
만든다. 출력은 Git에서 무시되는 `build/` 아래에 둔다.

```powershell
$Python = "python"
$ReleaseRoot = "build/m11/0.1.0-rc.2"

& $Python tools/release/nu54_release.py prepare `
  --repo-root . `
  --output-dir $ReleaseRoot `
  --version 0.1.0-rc.2 `
  --commit HEAD
```

생성 결과에는 RC ZIP, 별도 RC package index, checksum, SPDX SBOM, license inventory,
`m11-rc-plan.json`과 `package_integrity.evidence.json`이 포함된다. plan은 exact Core/보드
commit과 모든 artifact의 SHA-256·크기를 고정한다.

언제든 artifact byte를 다시 검증할 수 있다.

```powershell
& $Python tools/release/nu54_release.py validate-plan `
  --plan "$ReleaseRoot/m11-rc-plan.json"
```

## 2. 고정 gate 실행

`run-gate`는 사용자가 준 임의 명령을 실행하지 않는다. gate마다 RC commit에 들어 있는
`run_fixed_gate.py` 또는 `m8_upload.py`의 exact Git blob, command template와 시험 범위를
고정하고, package gate는 plan의 RC ZIP을 검증한 뒤 임시 Git-less platform으로 직접
해제한다. `--` 뒤에 임의 argv를 붙이면 인자 parser 단계에서 거부한다.

Arduino와 HIL gate에는 SHA-256이
`ba1890afcfc08524f76191b5cc801b0779cb25e81a5e6693eb0e26b50a3f3538`인 Arduino CLI
`1.5.2-rc.1` executable만 사용할 수 있다. Arduino·Zephyr·HIL gate는 M10이 준비한 고정
NCS/Toolchain과 prerequisite ready marker가 있는 PC에서 실행한다. gate 자체는 SDK를
다운로드하거나 `post_install.bat`을 실행하지 않는다.

Host 전체 회귀:

```powershell
& $Python tools/release/nu54_release.py run-gate `
  --repo-root . `
  --plan "$ReleaseRoot/m11-rc-plan.json" `
  --gate host_regression `
  --output "$ReleaseRoot/host_regression.evidence.json" `
  --timeout-seconds 3600
```

고정 RC ZIP에서 Arduino CLI 회귀:

```powershell
& $Python tools/release/nu54_release.py run-gate `
  --repo-root . `
  --plan "$ReleaseRoot/m11-rc-plan.json" `
  --gate arduino_cli_fixed_package `
  --output "$ReleaseRoot/arduino_cli_fixed_package.evidence.json" `
  --timeout-seconds 7200 `
  --arduino-cli "C:/Program Files/Arduino CLI/arduino-cli.exe"
```

고정 target ztest/Twister build-only 범위:

```powershell
& $Python tools/release/nu54_release.py run-gate `
  --repo-root . `
  --plan "$ReleaseRoot/m11-rc-plan.json" `
  --gate zephyr_regression `
  --output "$ReleaseRoot/zephyr_regression.evidence.json" `
  --timeout-seconds 7200
```

exact RC ZIP의 pyOCD 1회 flash와 UART `NUCODE_M8_UPLOAD_READY` 확인:

```powershell
& $Python tools/release/nu54_release.py run-gate `
  --repo-root . `
  --plan "$ReleaseRoot/m11-rc-plan.json" `
  --gate hil_rc_pyocd `
  --output "$ReleaseRoot/hil_rc_pyocd.evidence.json" `
  --timeout-seconds 1800 `
  --arduino-cli "C:/Program Files/Arduino CLI/arduino-cli.exe" `
  --serial-port auto
```

`auto`는 DAPLink VID:PID `0D28:0204`의 serial 후보를 제한 시간 동안 함께 열고 READY token이
나온 유일한 port를 선택한다. `--serial-port COMx`로 명시할 수도 있다. RC HIL은 pyOCD,
upload 1회, `smart_flash=false`, mass erase/recover 금지를 고정한다. M10의 pyOCD 10회는
safe preview의 내구 반복 증거로 별도 유지한다.

각 고정 명령에는 다음 환경 변수가 함께 전달된다.

- `NU54_RELEASE_VERSION`
- `NU54_RELEASE_CORE_REVISION`
- `NU54_RELEASE_RUNTIME_PAYLOAD_SHA256`
- `NU54_RELEASE_ARCHIVE`
- `NU54_RELEASE_INDEX`
- `NU54_RELEASE_PLATFORM_ROOT` (package gate에서만)

명령 종료 코드가 0이 아니거나 timeout이 발생하거나, 명령 실행 후 source checkout이
변경되면 PASS evidence가 생성되지 않는다. log는 자격 증명과 긴 장치 ID 후보를 제거한 뒤
별도 SHA-256으로 evidence에 묶는다.

### M10 대상 PC에서 원격 gate 자동 실행

M10이 PASS한 Windows 대상에 NCS/Toolchain과 `ready.json`이 남아 있으면 세 package/HIL
gate를 한 명령으로 실행할 수 있다. RC plan의 `core_revision`은 먼저 공개 저장소에 push되어
대상이 credential 없이 exact commit과 보드 submodule을 clone할 수 있어야 한다.

```powershell
$ReleaseRoot = "build/m11/0.1.0-rc.2"

powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File tools/release/invoke-m11-rc-windows.ps1 `
  -ReleaseRoot $ReleaseRoot `
  -TargetHost "192.168.1.10" `
  -RemoteUser "nu54ci" `
  -IdentityFile "$env:USERPROFILE/.ssh/nu54dk_m10_ed25519" `
  -KnownHostsFile "$env:USERPROFILE/.ssh/known_hosts"
```

원격 실행기는 `StrictHostKeyChecking=yes`, `IdentitiesOnly=yes`와 고정 private key를 사용하고,
`known_hosts`에 대상 key가 없으면 연결 전에 실패한다. plan의 전체 artifact byte를 로컬과
원격에서 각각 검증하고, 공개 `EIDOSDATA/NU54DK_Arduino_Core`의 exact detached commit만
checkout한다. 이 clone은 system/global Git config, credential helper와 대화형 인증을
비활성화하므로 공개 저장소 접근에 저장된 자격 증명을 사용하지 않는다. 대상의
`%LOCALAPPDATA%` 아래 M10 `ready.json`과 Toolchain bundle
`dcbdc366a1`의 Python/Git, SHA-256이 고정된 Arduino CLI만 사용한다.

결과는 기본적으로 `build/m11/remote/<RUN_ID>`에 기록한다. 다음 파일은 모두 있어야 하며,
하나라도 누락되거나 remote command가 timeout/non-zero로 끝나면 실행 전체가 실패한다.

- `arduino_cli_fixed_package.evidence.json`과 `.evidence.log`
- `zephyr_regression.evidence.json`과 `.evidence.log`
- `hil_rc_pyocd.evidence.json`, `.evidence.log`, `.evidence.result.json`
- endpoint 원문 없이 checksum만 기록한 `orchestrator.json`과 정제된 `orchestrator.log`

세 gate evidence와 companion log/result 7개는 byte를 다시 확인한 뒤 `ReleaseRoot`에도 자동으로
복사한다. 같은 이름의 파일이 이미 있으면 덮어쓰지 않고 실패하므로 새 RC attempt directory를
사용한다. `orchestrator.json`과 `orchestrator.log`는 원격 run 디렉터리에만 보존한다.

원격 실행이 실패해도 생성된 부분 evidence 회수는 시도하지만 PASS로 승격하지 않는다. 새
실행은 항상 새 run ID와 원격 directory를 사용하며 기존 원격 checkout이나 결과를 삭제·재사용하지
않는다.

## 3. clean Windows와 pyOCD 증거 가져오기

M10 원격 runner를 Windows-safe preview `0.0.96`→`0.0.97`로 실행한 결과의
`evidence.json`과 `orchestrator.json`을 가져온다. importer는 NCS가 없던 최초 상태,
전체 install/upgrade/downgrade/uninstall/reinstall lifecycle, 단일 CMSIS-DAP probe의
pyOCD upload 10회와 두 preview archive/index checksum을 확인한다. 두 preview는 같은 Core와
보드 revision 및 version 독립 `runtime_payload_sha256`을 가져야 한다. preview commit은 RC
commit의 ancestor여야 하며 그 사이에는 동결한 문서·시험·release automation 경로와 공개
preview index snapshot 변경만 허용한다. index byte는 M10 evidence의 SHA-256으로 별도
고정한다. package runtime source 또는 M10 runner가 바뀌면 import를 거부한다.

```powershell
& $Python tools/release/nu54_release.py import-m10 `
  --plan "$ReleaseRoot/m11-rc-plan.json" `
  --target-evidence "build/m10/remote/<RUN_ID>/evidence.json" `
  --orchestrator "build/m10/remote/<RUN_ID>/orchestrator.json" `
  --output-dir $ReleaseRoot
```

이 명령은 같은 원본 증거에 묶인 `clean_windows.evidence.json`과
`hil_pyocd.evidence.json`을 만든다. UTF-8 no-BOM BAT/CMD launcher 결함이 확인된
`0.0.90`~`0.0.93` 증거는 M11에서 인정하지 않는다. `0.0.94`와 `0.0.95`도 PowerShell 5.1
runner의 비동기 Task 반환값 누출로 Arduino CLI identity preflight에서 실패한 immutable
이력이므로 가져오지 않는다. clean Windows lifecycle과 pyOCD는
동일 runtime payload의 safe preview로 검증하며 RC ZIP을 clean PC에 직접 설치한 것으로
과장하지 않는다. exact RC ZIP 자체는 Arduino compile gate와 별도 1회 pyOCD+UART HIL에서
직접 검증한다. 최종 manifest는 두 범위를 구분해 기록한다.

importer는 입력한 두 raw JSON을 M11 output에 byte-for-byte 동결한다. M11 finalize 전에는
원본을 삭제하거나 수정하지 않는다. raw M10 JSON은 로컬 보존용이며 공개 GitHub Release
asset으로 올리지 않는다. 공개물에는 정제된 요약, gate evidence manifest와 checksum만
포함한다.

## 4. 문서 동결 evidence

최종 README, 설치, API 지원표, migration, troubleshooting, release notes, known issues,
license 문서를 `record-docs`에 모두 나열한다. 각 파일은 plan의 exact commit에 존재하고
현재 byte가 Git blob과 같아야 한다.

```powershell
& $Python tools/release/nu54_release.py record-docs `
  --repo-root . `
  --plan "$ReleaseRoot/m11-rc-plan.json" `
  --output "$ReleaseRoot/documentation.evidence.json" `
  --document "readme=README.md" `
  --document "license=LICENSE" `
  --document "installation=00_Docs/02_빌드 설계/06_Boards_Manager_설치와_패키징.md" `
  --document "api_matrix=00_Docs/01_아두이노 코어 설계/04_Arduino_API_지원_범위.md" `
  --document "migration=00_Docs/05_릴리스/05_v0.1.0_rc2_마이그레이션.md" `
  --document "troubleshooting=00_Docs/05_릴리스/06_v0.1.0_rc2_문제해결.md" `
  --document "release_notes=00_Docs/05_릴리스/07_v0.1.0_rc2_릴리스_노트.md" `
  --document "known_issues=00_Docs/05_릴리스/08_v0.1.0_rc2_알려진_제약.md" `
  --document "third_party_notices=third_party/THIRD_PARTY_NOTICES.md"
```

이 명령은 문서 내용의 법률적 타당성을 판정하지 않으며 byte provenance만 증명한다.

## 5. evidence 결합

필수 gate는 다음과 같다.

- `package_integrity`
- `host_regression`
- `arduino_cli_fixed_package`
- `zephyr_regression`
- `hil_rc_pyocd`
- `hil_pyocd`
- `clean_windows`
- `documentation`

```powershell
$Evidence = Get-ChildItem $ReleaseRoot -Filter "*.evidence.json" |
  ForEach-Object FullName

& $Python tools/release/nu54_release.py finalize `
  --plan "$ReleaseRoot/m11-rc-plan.json" `
  --evidence $Evidence `
  --output "$ReleaseRoot/m11-rc-evidence-manifest.json"
```

필수 evidence가 누락되거나 실패하면 manifest를 `hold`로 기록하고 종료 코드 3을 반환한다.
조사 중간에 HOLD manifest만 남길 때는 `--allow-incomplete`를 추가할 수 있다. 모든 기술
gate가 PASS면 `ready-for-human-approval`이 되지만 다음 항목은 계속 차단 상태다.

- third-party 및 Nordic 외부 prerequisite의 최종 법률 검토
- `v0.1.0` stable 공개 승인
- stable tag, GitHub Release 및 공개 package index 생성

따라서 이 도구의 출력만으로 stable 공개를 실행해서는 안 된다.
