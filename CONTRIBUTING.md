# 개발과 기여 안내

사용자 설치는 [루트 README](README.md), 구현 변경은 이 안내와 [작업 지침](AGENTS.md)에서
시작합니다. 후속 개발은 `main`에서 시작합니다. M32 원본 이력은 `Dev-0.6.0-M32`,
정식 릴리스 백업은 `Release-0.5.0`에 보존합니다. M32는 12/12 완료, M33은 0/8 미착수입니다. stable은 `v0.5.0`이며 버전별 지원 범위는
[릴리스 문서](<00_Docs/05_릴리스/README.md>)에 있습니다.

후속 개발 목표는 [v0.6.0의 M32·M33](00_Docs/TODO_v0.6.0.md)입니다.
[v0.7.0](00_Docs/TODO_v0.7.0.md)은 NCS 3.4.0→3.4.1 전체 전환만 수행하며 신규 기능을 넣지 않습니다.
M34~M37은 v0.8.0, M38~M41은 v0.9.0, M42~M45는 v0.10.0으로 옮기고 M 번호·기능 범위는 유지합니다.
`Release-0.5.0`은 `4790e3fa` 완료 기준선입니다. 새 기능 작업은 최신 `main`에서 분기합니다.
버전 배정은 구현 완료·Host 보류 해제·릴리스 공개 승인이 아니며 실제 제품 버전은 아직 0.5.0입니다.

## 소스와 환경 준비

```powershell
git clone --branch main --recurse-submodules https://github.com/EIDOSDATA/NU54DK_Arduino_Core.git
cd NU54DK_Arduino_Core
git status --short --branch
git submodule status --recursive
```

[Windows 개발환경](<00_Docs/02_빌드 설계/09_Windows_개발환경_설정.md>)의 prerequisite 절차로
NCS v3.4.0과 고정 toolchain을 준비합니다. revision은
[SDK lock](tools/ci/ncs-3.4.0.lock.json)이 소유합니다. 보드 정의는
`board_package/NU54DK_Zephyr_DTS` submodule이며 Core 변경과 별도로 관리합니다.

NCS v3.4.1 전체 전환은 제품 v0.7.0의 유일한 목표입니다. 현재 v0.6.0 개발의 SDK·toolchain pin은
유지하고 [수정 내역·적용 조건·전환 검사](<00_Docs/00_사전 리서치/03_NCS_3.4.1_변경과_개발_영향.md>)를 먼저 확인합니다.
최신 웹 문서의 기능이나 버그 수정을 고정 v3.4.0의 지원·해결 결과로 소급하지 않습니다.

작업 전에 [HANDOFF](00_Docs/HANDOFF.md)와 해당 TODO를 읽고 변경 전 branch·commit·작업 트리·
submodule 상태를 기록합니다. 기능/API 변경은 담당 계약·예제·검사와 함께 수정합니다.

## 변경에 맞는 검사

아래 `python`은 개발환경에 준비한 Python을 뜻합니다. 다른 Python에 시험 의존성이 없다면
고정 toolchain의 Python 절대 경로를 사용합니다.

```powershell
python tools/ci/run_m12_gate.py docs
python tools/peripheral/verify_generated.py
python tools/coverage/m17_coverage.py render --check
git diff --check
```

| 변경 | 추가 검사 |
| --- | --- |
| 문서·링크 | 영향받은 계약/예제와 내용 대조, 문서 감사 원장 hash 갱신 |
| builder·공개 API·자원 | 관련 Host suite, 영향받은 profile/예제 target build |
| Bluetooth 원장·예제 | 해당 M31/M32 contract `--check`, 관련 Host·공개 예제 검사 |
| package·release | version별 계약·재현성·격리 설치·수명주기 검사 |
| hardware 동작 | 지정 fixture의 안전 확인과 필요한 범위의 HIL |

전체 Host 회귀가 필요한 경우 `python tools/ci/run_m12_gate.py host`를 사용합니다. GitHub Actions의
실행 범위는 [CI 안내](<00_Docs/02_빌드 설계/08_M12_CI_CD와_재현_빌드.md>)를 따릅니다.
Host·compile·실물 검증 결과를 각각 기록하고 실행하지 않은 항목은 `NOT RUN`으로 남깁니다.

## 코드와 문서 작성

- C/C++은 한국어 Doxygen, BSD/Allman, 4칸 들여쓰기를 사용합니다. 한 줄 제어문도 중괄호를 둡니다.
- 공개 Arduino 예제는 `.ino`에서 `NUCODE_*` API 사용 흐름을 보여 줍니다. backend와 시험 전용
  protocol 경계는 [AGENTS](AGENTS.md)의 공개 예제 규칙을 따릅니다.
- 현행 상태는 TODO/HANDOFF, 사용자 지원은 version별 릴리스 문서, 실행 당시 결과는 번호별 검증
  기록이 소유합니다. 같은 수치를 여러 진입점에 복사하기보다 원본에 링크합니다.
- 생성 문서는 원본 JSON·생성기를 수정하고 재생성합니다. 경로를 바꾸면 들어오는 링크도 고칩니다.
- 과거 실패·판정과 공개 자산을 보존하고 후속 교정은 새 기록에 남깁니다.

## 이력 정리 뒤 기존 checkout

2026-10-03 M32 통합은 기존 `main` `1049caf7…` 뒤에 완료 상태를 한 커밋으로 추가하는
**squash merge**입니다. `main`의 이전 이력은 유지하며 원격은 일반 fast-forward push로 갱신합니다.
`Dev-0.6.0-M32`에는 단계별 원본 커밋과 이번 문서 정비를 보존합니다. 범위와 검증은
[295번 기록](<00_Docs/04_검증 기록/295_M32_문서_전수_정비와_main_Squash_통합.md>)을 따릅니다.

기존 `main` checkout은 작업 트리가 깨끗한 상태에서 다음 명령으로 갱신할 수 있습니다.

```powershell
git fetch origin
git switch main
git pull --ff-only origin main
git submodule update --init --recursive
```

로컬 `main`이 원격과 갈라졌거나 이전 이력 정리 전 checkout이라면 강제 reset하지 않습니다.
개인 변경을 먼저 commit 또는 별도 복사로 보관한 뒤, 사용하지 않는 새 branch 이름으로
최신 원격을 확인합니다.

```powershell
git fetch origin
git switch --create main-after-squash --track origin/main
git submodule update --init --recursive
```

M32 개발 branch를 최신 `main`에 다시 일반 merge하면 squash 전 중간 이력이 합쳐집니다.
후속 개발은 최신 `main`에서 새 branch를 만들고 필요한 추가 변경만 검토해 가져옵니다.
M32 실기 재현은 각 검증 기록의 원본 SHA, 공개 제품 재현은 해당 release tag를 사용합니다.

## 이전 이력·공개 근거

| 기록 | 보존 내용 |
| --- | --- |
| [269번](<00_Docs/04_검증 기록/269_공개_RC_이력_Squash와_문서_전수_정비.md>) · [270번](<00_Docs/04_검증 기록/270_main_RC_통합_Squash와_문서_동기화.md>) | RC1 개발 이력과 당시 main 통합·복구 방법 |
| [272번](<00_Docs/04_검증 기록/272_RC2_사용자_수용과_main_통합_및_시험배포.md>) | RC2 사용자 수용·통합·시험 배포 |
| [274번](<00_Docs/04_검증 기록/274_v0.5.0_정식_릴리스_승인과_공개.md>) | 정식 v0.5.0 공개·이력 정리·백업과 RC branch 삭제 |
| [275번](<00_Docs/04_검증 기록/275_v0.5.0_공개_후_문서_전수_재검토.md>) | 정식 공개 후 문서 정비 |

현재 지원 패키지는 `v0.5.0` tag의 `0999b6a721b4579faa6a7a4d91d04da5e4960c07`에 고정돼 있습니다.
공개 tag·Release·asset과 당시 FAIL/HOLD/NOT RUN은 보존합니다. 최신 문서의 검토 범위·hash는
[문서 감사 원장](00_Docs/document-review.json)에서 확인합니다.
