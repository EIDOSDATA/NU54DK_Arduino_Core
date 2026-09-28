# 개발과 기여 안내

사용자 설치는 [루트 README](README.md), 구현 변경은 이 안내와 [작업 지침](AGENTS.md)에서
시작합니다. 현재 개발 branch는 `main`, 정식 릴리스 백업은 `Release-0.5.0`입니다. RC1·RC2 branch는
정식 마감에서 삭제했고 공개 tag·Release·asset은 보존합니다. stable은 `v0.5.0`이며 버전별 지원 범위는
[릴리스 문서](<00_Docs/05_릴리스/README.md>)에 있습니다.

후속 개발 목표는 [v0.6.0의 M32·M33](00_Docs/TODO_v0.6.0.md)입니다. M34~M37은 v0.7.0,
M38~M41은 v0.8.0, M42~M45는 v0.9.0으로 배정하며 M 번호·기능 범위는 유지합니다.
`Release-0.5.0`은 `4790e3fa` 완료 기준선으로 보존하고 후속 변경은 `main`에서 진행합니다.
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
| Bluetooth 원장·예제 | `python tools/bluetooth/m31_contract.py --check`, 관련 Host·공개 예제 검사 |
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

2026-09-27의 첫 정리는 `0.5.0-RC1`의 당시 main 이후 83개 commit과 문서를 하나로 합치고
`M31-MEM-OPT` branch를 삭제한 작업입니다. 그 판단·복구 근거는
[269번 기록](<00_Docs/04_검증 기록/269_공개_RC_이력_Squash와_문서_전수_정비.md>)에 보존합니다.

후속 main 통합에서는 v0.4.1 마감 `1e0bf4a6`까지의 143개 commit을 유지하고,
그 이후 main 9개와 정리된 RC 1개를 하나로 합쳐 총 144개 이력으로 정리했습니다.
당시 `0.5.0-RC1` branch를 별도로 보존했으며 현재 개발 시작점은 `main`이었습니다.
범위·검증·복구 근거는 [270번 기록](<00_Docs/04_검증 기록/270_main_RC_통합_Squash와_문서_동기화.md>)을 따릅니다.
이는 당시 새 release가 아니었으며 stable v0.4.1의 catalog·공개 자산을 변경하지 않았습니다.
공개 tag `v0.5.0-rc.1`도 원래 source `7786984a186980f6220271cd506636e4564bc55d`를 계속 가리킵니다.

기존 checkout은 우선 변경을 commit 또는 별도 복사로 보관하고, submodule을 포함한 작업 트리가
깨끗한지 확인합니다. 정리 전 main/RC branch와 새 main을 일반 `pull`로 합치면 원래 이력이 다시
섞일 수 있습니다. 이전 local branch를 지우거나 강제 reset하지 말고, 원격 갱신 뒤 아래처럼
**사용하지 않는 새 local branch 이름**으로 새 main을 확인합니다.

```powershell
git fetch origin --prune
git switch --create main-after-squash --track origin/main
git submodule update --init --recursive
```

개인 변경은 새 branch에서 필요한 commit만 검토해 적용합니다. 새 이름이 이미 존재하면 다른
미사용 이름을 선택합니다. 별도 clone으로 시작해도 되며, 어느 방법이든 원본 작업을 먼저 보존합니다.
공개 RC 재현에는 main/RC branch HEAD 대신 해당 release tag를 사용합니다. 보존된 RC2는
`v0.5.0-rc.2` → `b2e7a587ba6fde31e033dc21008d7084bd6e631b`이며 RC1 tag는 그대로입니다.

## RC2 통합과 GUI 시험 인계 — 역사

RC2의 16개 구현·CI commit과 후속 문서 정비를 main에 반영한 당시에는 squash·force-push나
과거 branch 삭제를 하지 않았습니다. [272번 기록](<00_Docs/04_검증 기록/272_RC2_사용자_수용과_main_통합_및_시험배포.md>)과
[GUI 시험 목록](<00_Docs/05_릴리스/v0.5.0-rc.2/TESTING.md>)은 당시 결정입니다. 정식 v0.5.0의
이력 Squash·공개·backup branch·RC branch 삭제는 [274번 기록](<00_Docs/04_검증 기록/274_v0.5.0_정식_릴리스_승인과_공개.md>)을 따릅니다.
CI 시간 목표 미달은 수용한 제한으로 보존합니다. 후속 GUI Blink 연속 Upload는 PASS했지만 별도 기술
gate의 과거 FAIL/HOLD를 소급 변경하지 않습니다.
RC2 패키지는 검증된 b2e7 소스의 immutable 자산이고 최신 문서 commit과 구분합니다.
현재 지원되는 정식 패키지는 `v0.5.0` tag의 `0999b6a721b4579faa6a7a4d91d04da5e4960c07`을
기준으로 합니다. 공개 후 문서 교정은 [275번 기록](<00_Docs/04_검증 기록/275_v0.5.0_공개_후_문서_전수_재검토.md>)과
[감사 원장](00_Docs/document-review.json)에 남기며 기존 공개 자산을 덮어쓰지 않습니다.
