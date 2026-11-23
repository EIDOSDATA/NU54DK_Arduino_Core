# Mac 검증 결과와 C11 전달 자료

macOS 26.7.3과 27.2.1의 C11 실기를 완료했습니다. C12에서는 macOS 27의 일반 IDE Upload와 Blink를 확인했습니다. 다음 단계는 최종 배포 후보 검토입니다. [336번 기록](<04_검증 기록/336_HOST_W07_C11_macOS_26_실기_검증과_재연결.md>), [337번 기록](<04_검증 기록/337_HOST_W07_C11_macOS_27_실기_검증과_마감.md>), [338번 기록](<04_검증 기록/338_HOST_W07_macOS_27_Arduino_IDE_Upload_교정.md>), [최종 후보 체크리스트](<05_릴리스/v0.6.0/RELEASE_CHECKLIST.md>)

아래 절차는 2026-11-16의 Windows 인계와 C11 검증을 재현하거나 원본을 복구할 때 사용합니다. 현재 작업을 재개할 때는 [새 작업 지시문](MAC_START_PROMPT.txt)과 최신 실제 writer 해제 기록을 확인하세요.

## 1. Mac에서 처음 할 일

1. 저장소 `EIDOSDATA/NU54DK_Arduino_Core`의 **`Dev-0.6.0-M33`** 최신 내용을 받는다.
2. 아래 읽기 순서로 문서를 확인하고 [복사용 작업지시문](MAC_START_PROMPT.txt)을 새 작업에 전달한다.
3. Windows에서 준비한 **`NU54DK-Mac-handoff-20261116.zip`**을 Mac으로 옮긴다.
4. 전달 묶음의 hash·writer 해제 기록과 실제 Mac 상태를 확인한 뒤 새 작업 폴더에서 시작한다.

새 checkout을 만들 때의 예시다. 이미 같은 저장소가 있으면 미커밋 변경을 먼저 확인하고 보존한다.
기존 폴더를 삭제하거나 강제로 reset하지 않는다.

```sh
set -eu
git clone --branch Dev-0.6.0-M33 --recurse-submodules https://github.com/EIDOSDATA/NU54DK_Arduino_Core.git "$HOME/nu54-src"
cd "$HOME/nu54-src"
git status --short
git rev-parse HEAD
git submodule status
```

Git 인증이나 OS 최초 개발 도구 설치가 필요하면 해당 Mac의 정상 로그인·설치 절차를 사용한다.
비밀번호·token·비밀키를 채팅에 보내거나 Windows의 credential 저장소를 복사하지 않는다.
문서의 최신 commit과 아래 **검증 제품 source C11**은 서로 다르다.

## 2. 먼저 읽을 문서

| 순서 | 파일 | 확인할 내용 |
| --- | --- | --- |
| 1 | [AGENTS](../AGENTS.md), 이 문서, [기계 판독 인계](mac-handoff.json) | 운영 경계·source·kit·재개 조건 |
| 2 | [HANDOFF](HANDOFF.md), [M33 인계](M33_HANDOFF.md) | 현재 단계와 보존된 W06/Host 결과 |
| 3 | [M33 TODO](TODO_M33.md)의 W07·W08, [v0.6.0 계획](TODO_v0.6.0.md) | 최종 마감·공개 경계 |
| 4 | [다중 Host 계약](<02_빌드 설계/10_v0.5.0_다중_Host_지원_착수_계약.md>), [고정 Nordic 설치](<02_빌드 설계/12_Host별_고정_Nordic_환경_설치.md>), [RC1 실기 절차](<02_빌드 설계/15_Host_RC1_실기_도구와_증거_절차.md>) | Mac 설치·USB·IDE의 배정 범위와 판정 |
| 5 | [331번 C11 결과](<04_검증 기록/331_HOST_W07_C11_macOS_26_27_호환성.md>), [332번 W08 문서 준비](<04_검증 기록/332_HOST_W08_문서_지원표_선행_정리.md>), [333번 Mac 인계](<04_검증 기록/333_Mac_재개_문서와_전달_자료.md>) | 인계 시점의 software PASS와 당시 Mac NOT_RUN 근거 |
| 6 | [Host 원장](../variants/nu54dk/host-readiness.json), [지원표](<05_릴리스/v0.6.0/SUPPORT_MATRIX.md>), [Testing](<05_릴리스/v0.6.0/TESTING.md>), [릴리스 체크리스트](<05_릴리스/v0.6.0/RELEASE_CHECKLIST.md>) | source별 근거·남은 순서 |

완료 TODO6개와 오래된 원형 기록 전체를 다시 읽을 필요는 없다. W06 수락 근거가 필요하면
[310번](<04_검증 기록/310_M33_W06_사용자_수락_마감_완료.md>)·[311번](<04_검증 기록/311_M33_W06_명시_수락_정정과_HOST_W04_착수.md>),
Windows/WSL 원인이 필요하면329·330번의 해당 부분만 확인한다. #29 원인 분석은 재개하지 않는다.

## 3. 고정 상태와 원본 kit

| 항목 | 값 |
| --- | --- |
| 현재 단계 | M33-W07, HOST-W08 문서 준비 완료·최종 gate 미완료 |
| 완료 수 | M33 수락6/8·기술5/8, Host7/8, 지원 목표 검증5/5 |
| Windows·Linux | C5 Windows11 기준선, C10 Ubuntu24.04/26.04 WSL2 완료 보존 |
| 제품 C11 | `d304f369c0d3ebbac35c3bf0ef3b7b2887f40dfa` |
| 문서 인계의 부모 | `09da4d740fb751904e939ca0f1ef944cdf1b720b`; 새 인계 문서 commit은 Git과 전달 receipt로 확인 |
| board submodule | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` |
| Mac SDK | NCS 3.4.0, bundle `ccc010f809`, SDK root `/opt/nordic/ncs` |
| 비공개 package | 현재 `0.6.0-rc.1`, 이전 `0.6.0-host.1`, **둘 다 같은 C11 source** |
| 원본 kit | `NU54DK-C11-d304f369-macOS-kit.tar.gz`, 201,857,017바이트 |
| kit SHA-256 | `c1792818979453ce3150d7b19abf960f3d14a31f970c4578f5f41afcf5cf8208` |
| C11 software CI | [43760678488/attempt1](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/runs/43760678488),5/5SUCCESS |
| Mac software 실적 | 실제26.7.2·27.0.1 ARM64, SDK 설치·lifecycle·대표4cold/4warm·관련 unit 통과 |

C11 kit의 source tree는 불변 입력이다. 최신 문서 checkout의 파일을 kit 안에 덮어쓰지 않는다.
제품 코드 수정이 필요한 실패는 원형을 보존하고 새 제품 source·새 kit·새 attempt로 구분한다.
권한·경로 등 환경 준비만 보완하면 원본 kit를 유지하고 fresh attempt에서 확인한다.
C5/C10/C11의 PASS를 C11 동일-source 전체 검증으로 합산하지 않는다.

## 4. Mac으로 옮길 자료

Windows 전달 파일은 `D:/w06/mac-transfer/NU54DK-Mac-handoff-20261116.zip`이다.
이 파일은 Git에 넣지 않는다. 별도 저장장치 등으로 원본 그대로 Mac에 복사한다.
옆의 `.sha256` 파일로 전체 ZIP을 확인한 뒤 새 폴더에 해제한다.
해제한 최상위 폴더에서 `shasum -a 256 -c SHA256SUMS`로 내부 파일도 확인한다.

묶음에는 다음이 들어 있다.

- 원본 C11 kit와 원형 producer/검증 근거, Mac26·27 원본 CI ZIP·job log.
- C10 Mac FAIL·진단 원형, C10 Ubuntu 완료 요약, C11/W08 완료·감사 결과.
- source/run/attempt·원본 경로→묶음 상대 경로·size·SHA-256을 담은 `transfer-manifest.json`과 `SHA256SUMS`.
- 최종 문서 SHA·CI와 Windows 실행 종료·writer 해제를 기록한 `windows-writer-release.json`.

기존 증거 내부의 Windows 경로는 당시 원형이므로 고치지 않는다. 현재 파일은 manifest의 상대 경로로 찾는다.
Windows/WSL `state.json`·SDK 설치본·runtime/cache·credential·private key·전체 continuation은 현재 실행 입력으로 옮기지 않는다.
묶음 안 CI ZIP의 `state.json`도 **역사 증거**이며 Mac work root에 복원하지 않는다.
W06·C5의 대규모 원본 전체 복제본은 아니며 그 보존 위치와 Git 증거 색인은 그대로 유지한다.

### 전달 파일을 놓친 경우

먼저 Windows의 보존 파일을 확보한다. GitHub artifact는 영구 저장소가 아니다.
C11 kit artifact `14180370671`은 보존 당시 API에 `2026-11-29T20:57:20Z` 만료 예정으로 기록됐다.
현재 다운로드 가능 여부는 재개 시 다시 확인한다. 유효하면 아래처럼 인증된 GitHub CLI로 원본 ZIP을 받을 수 있다.

```sh
set -eu
gh api repos/EIDOSDATA/NU54DK_Arduino_Core/actions/artifacts/14180370671 > artifact-metadata.json
gh api repos/EIDOSDATA/NU54DK_Arduino_Core/actions/artifacts/14180370671/zip > original-kit-artifact.zip
printf '%s  %s\n' '6112f3bbe55e061715ce7ca5d2107b61bef611fdea9835ea9c47327b6e24038f' 'original-kit-artifact.zip' | shasum -a 256 -c -
```

metadata의 id·source·run과 ZIP hash를 확인한 뒤 안의 `kit.tar.gz`를 추출하고 위 kit hash도 확인한다.
원본이 만료·유실됐으면 임의 재생성을 동일 artifact로 취급하지 않는다. 먼저 보존본을 찾고,
정말 재생성이 필요할 때 exact source와 새 생성 결과를 별도로 기록한다. 이전 CI PASS를 새 결과로 복사하지 않는다.
writer 해제 기록도 없으면 읽기 전용 준비를 계속하면서 이전 writer 종료 여부를 확인한다.

## 5. 단일 writer와 Mac의 새 상태

전달 묶음의 `windows-writer-release.json`에서 `writer_released=true`, `native_running=false`,
`local_heavy=false`, 최종 문서 SHA와 CI 결과를 먼저 확인한다. Mac에 Windows process가 없다는 이유만으로
이전 writer 해제를 추정하지 않는다. Windows writer는 이 문서 push·CI와 전달 준비를 끝낸 뒤 해제한다.
receipt의 최종 문서 SHA를 현재 checkout HEAD와 원격 branch에 대조한다. 다르면 문서 후속인지
제품 변경인지, 더 새 writer가 있는지 확인하기 전 옛 receipt를 현행 소유권 해제 근거로 사용하지 않는다.

Mac에서는 실제 checkout HEAD·dirty 상태·submodule, OS·architecture·장치·process·lock을 다시 확인한다.
Apple Silicon native ARM64와 실제 macOS major26 또는27을 기록한다. 다른 major나 Intel/Rosetta를
시험 대상26/27로 가장하지 않으며 기존 kit의 Host 판별만으로 실제 major를 확인한 것으로 세지 않는다.

```sh
sw_vers
uname -m
df -h "$HOME" /opt
```

새 로컬 `control/continuation.json`과 writer claim에는 현재 작업 ID·checkout/document SHA·제품 SHA·
OS/version/arch·kit hash·work root·실행 PID·현재 단계·원본 결과 경로를 남긴다.
단일 writer·단일 heavy job과 실행기의 SDK/build/probe lock 정책을 유지한다. Windows COM명·named mutex나
Windows 경로를 Mac에 만들어 충족시키지 않는다. 실제 Mac의 lock 구현·probe/port를 사용한다.
자동점검 w06은 PAUSED 유지, 새 예약작업·자동 재개 작업은 만들지 않는다.

## 6. 새 Mac 작업 폴더와 준비 단계

현재 Mac major를 확인한 뒤 아래26 예시를 해당 major와 새 실행 번호로 바꾼다.
기존 폴더가 있으면 다른 번호를 사용하고 삭제·덮어쓰기하지 않는다. `HOME` 자체를 재정의하지 않는다.
kit는 `plan`에서도 관리 runtime을 추출하므로 쓰기 가능한 로컬 폴더에 둔다.

```sh
set -eu
NU54_ARCHIVE="$HOME/Downloads/NU54DK-Mac-handoff-20261116/kit/NU54DK-C11-d304f369-macOS-kit.tar.gz"
printf '%s  %s\n' 'c1792818979453ce3150d7b19abf960f3d14a31f970c4578f5f41afcf5cf8208' "$NU54_ARCHIVE" | shasum -a 256 -c -
NU54_CASE="$HOME/nu54-mac26-a001"
mkdir "$NU54_CASE"
mkdir "$NU54_CASE/input" "$NU54_CASE/work" "$NU54_CASE/control" "$NU54_CASE/tmp"
export TMPDIR="$NU54_CASE/tmp"
tar -xzf "$NU54_ARCHIVE" -C "$NU54_CASE/input"
NU54_KIT="$NU54_CASE/input/kit"
sh "$NU54_KIT/START.sh" --work-root "$NU54_CASE/work" plan > "$NU54_CASE/control/plan.json"
```

위 명령은 **단계별로 exit code와 결과를 확인하며** 실행한다. Hash 실패 뒤 추출을 계속하지 않는다.
plan의 source·version·Mac descriptor·SDK root·kit hash를 확인한다. 시스템 Python/Homebrew·Rosetta를
무조건 먼저 설치하지 않는다. kit의 관리 runtime과 고정 SDK를 사용한다.

SDK root는 `/opt/nordic/ncs`다. 기존 SDK·소유권·여유 공간을 조사하고 설치기의 실제 필요량과
운영 최소 여유4GiB를 모두 충족한다. 경로가 없어서 생성 권한이 필요할 때만 사용자 OS 승인을 받아
다음과 같이 준비한다. 기존 경로를 무조건 chown하거나 kit 전체를 sudo로 실행하지 않는다.

```sh
sudo install -d -o "$(id -un)" -g "$(id -gn)" /opt/nordic/ncs
```

새 Mac의 설치/경로와 실기에 사용할 로컬 image·manifest를 만드는 최소 준비다.
CI의 절대경로 state/build manifest를 재사용하지 않는다.

```sh
set -eu
sh "$NU54_KIT/START.sh" --work-root "$NU54_CASE/work" install-sdk
sh "$NU54_KIT/START.sh" --work-root "$NU54_CASE/work" lifecycle
sh "$NU54_KIT/START.sh" --work-root "$NU54_CASE/work" build
sh "$NU54_KIT/START.sh" --work-root "$NU54_CASE/work" inventory
```

`build`는 대표4개 cold/warm8회다. **`--all-examples`를 추가하지 않는다.** 새 Mac의 환경 준비이며
보존된 전체204 기준선을 새로 실행하거나 동일-source 실적을 합치는 작업이 아니다.
source·OS major·attempt가 달라지면 새 work root를 사용한다. 고정 SDK 위치를 공유할 때도 실제 ready 검증·lock을 따른다.

## 7. 실제 NU54DK 검증

NU54DK의 CMSIS-DAP USB를 Mac에 직접 연결한다. nRF54L15DK로 임의 대체하지 않는다.
기존 COM17·18·25·26이나 Windows/WSL의 UID/path hash는 새 장치 선택 근거가 아니다.
새 inventory로 해당 probe·두 VCOM·serial/path hash를 대조하고, 열거 성공과 실제 port open을 구분한다.
`A`, `SA`, `PA`를 실제 Mac inventory에서 선택한 hash로 치환한 뒤 단계별 실행한다.

```sh
set -eu
sh "$NU54_KIT/START.sh" --work-root "$NU54_CASE/work" upload --example blink --probe-sha256 A
sh "$NU54_KIT/START.sh" --work-root "$NU54_CASE/work" blink --example blink --probe-sha256 A
sh "$NU54_KIT/START.sh" --work-root "$NU54_CASE/work" debug --example blink --probe-sha256 A
sh "$NU54_KIT/START.sh" --work-root "$NU54_CASE/work" upload --example serial --probe-sha256 A
sh "$NU54_KIT/START.sh" --work-root "$NU54_CASE/work" serial --example serial --probe-sha256 A --serial-sha256 SA --path-sha256 PA
```

정상 sector program·software reset·halt/resume·읽기 진단 범위로 진행한다.
자동 J-Link fallback·DAP/J-Link firmware 변경·mass erase·unlock·recover·보안 보호 우회는 하지 않는다.
실패는 원형 그대로 남기고 원인과 수정 범위를 좁힌 뒤 fresh attempt에서 확인한다.

물리 재연결은 **관찰 시작 안내 → 사용자가 케이블을 빼고10초 뒤 같은 포트에 연결 → 재열거와 첫 UART 응답 기록**으로
별도 검증한다. 재연결 첫 통신을 기록하기 전에 재flash/reset해 상태를 지우지 않는다.
serial의 두 번 open/close는 물리 재연결 PASS가 아니다. `--synchronize-line`은 C11에 있으나
기존 근거는 CMSIS-DAP/WSL2다. Mac의 기본 필수 정책으로 가정하지 말고 적용 이유와 실제 옵션을 기록한다.

한 보드로 Blink·serial·debug·재연결을 먼저 진행한다. 첫 Mac 기준선에 BLE 두 보드 검증을 배정하면
두 번째 NU54DK를 준비하고 RC1 절차의 `ble-pair`를 사용한다. 준비되지 않은 BLE 행은 별도로 남기며
한 보드 결과로 대체하지 않는다. 두 번째 Mac major는 기존 기준선과 변경 영향에 따라 호환성 범위를 정하고
동일 시험 전체를 자동 반복하지 않는다.

Arduino IDE는 실제 Mac용 설치본으로 후보의 격리 데이터·설정·cache를 사용해 board/example 발견과 Blink Verify를 확인한다.
후보 kit/lifecycle의 index·archive를 사용하고 공개 stable URL의0.5.0을 RC1 검증으로 착각하지 않는다.
Windows `.cmd`·`.arduinoIDE` 경로를 그대로 이식하지 않는다. Mac의 실제 IDE 설정·backend·build log로 설치 source를 확인한다.
화면 제어 수단이 없거나 OS 승인이 필요한 조작은 사용자가 수행할 항목을 명확히 안내하고,
CLI PASS를 IDE GUI PASS로 바꾸지 않는다.

## 8. 저장·보고·다음 단계

각 단계의 raw log·exit code·manifest·hash·STOP/cleanup과 source/run/attempt·OS를 기록한다.
`UNCONFIRMED` cleanup이나 `physical_recovery_pending=true`는 PASS가 아니다. 장치 소유권을 정리하고
다음 장치 작업 전에 실제 상태를 확인한다. Windows의 종료 receipt를 Mac 실행의 cleanup 증거로 재사용하지 않는다.

Mac26/27은 **각각 실제 완료한 범위만** 지원표에 반영한다. 하나만 확보했으면 나머지 행은 NOT_RUN이다.
문서·원장을 갱신하고 변경 범위에 맞는 검사·commit/push·exact CI를 확인한다. 코드 변경이 있으면 새 source로 분리한다.
이후 최종 배포 후보 정합화 → HOST-W08·M33-W07 마감 → 별도 공개 승인 → 게시·공개 설치 검증으로 진행한다.
공개 tag·Release·asset·stable index와 main 통합은 현재 승인 범위가 아니다.
