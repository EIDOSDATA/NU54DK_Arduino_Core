# 개발문서 전수 검토와 README 개선

| 항목 | 기준 |
| --- | --- |
| 작업일 | 2026-09-14 |
| 시작 branch / HEAD | `main` / `fcfd3e2c22a90c1e842126c512362c0840a5fa45` |
| 시작 작업 트리 | clean |
| 요청 범위 | 문서 전수 검토·불필요한 내용 정리·README 개선·로컬 검증·commit/push |
| 개발 상태 | M28 8/8 완료, M29 6/8(75%)·시험 ID 8/10 PASS |
| 실기 경계 | W07-C 완료 후 중단, W07-D/E NOT RUN 유지 |
| 원격 CI | 사용자 요청으로 확인을 뒤로 미룸. 이 문서 변경의 CI PASS를 주장하지 않음 |

## 1. 검토 범위와 근거

시작 시 main 저장소의 Markdown **284개**, 고정 board submodule의 Markdown **6개**를
검토 대상으로 잡았다. 이번 기록을 추가한 main Markdown은 **285개**다.
본문 검토와 기계 검사를 완료한 전체 경로·시작 Git blob·수정/보존 판정은
[문서별 감사 원장](evidence/docs-audit-20260914/document-inventory.json)에 남긴다.

| 문서군 | 시작 파일 수 | 검토 기준 |
| --- | ---: | --- |
| Root·AGENTS·문서 목차·TODO·HANDOFF | 7 | 현재 지원·진행률·재개 지점·독자별 탐색 |
| 사전 리서치 | 2 | 아키텍처 결정·적용 범위·역사적 판단 보존 |
| 코어·빌드·펌웨어 설계 | 41 | 실제 구현·설정·API·예제·고정 SDK와 대조 |
| 검증 기록·Markdown 진단 증거 | 149 | 당시 source·판정·후속 해결·목차와 링크 |
| 릴리스 | 65 | v0.4.1 단독 지원 안내와 과거 공개 원본 구분 |
| Tests·tools·packaging | 17 | 명령·도구 동작·시험 역할·제약과 일치 |
| Coverage 생성 요약·third-party | 3 | 생성 원본·외부 소유권·고지 보존 |
| Board submodule | 6 | 읽기 전용 검토. Core 문서에서 따라야 할 결선 원본 구분 |

현행 정보는 `boards.txt`, 고정 CI lock, v0.4.1 tag와 stable index,
M28/M29 readiness, library 설정·예제, HIL 결과와 빌드 도구를 대조했다.
문서 검토가 새 target build나 실제 보드 시험을 대신하지는 않는다.

## 2. 주요 개선

| 발견한 문제 | 개선 내용 |
| --- | --- |
| README가 M29를 아직 계획으로 표시 | M28 완료, M29 W07-C 완료·D/E NOT RUN과 W08 잔여를 명시 |
| 배포판과 개발판 지원이 혼동될 수 있음 | v0.4.1 BLE 1-link와 main의 2-link, 배포 30개 예제와 개발 예제를 구분 |
| 프로젝트의 용도·구조·기여 방법 부족 | Arduino 시작 경로, Zephyr 전체 firmware 빌드, Fabric, 검증 방식, 문제 보고 항목 추가 |
| HANDOFF·TODO에 실패 시도별 장문이 반복 | 현재 체크포인트·작업표·다음 조건으로 축약하고 상세 실패는 147번으로 연결 |
| 구버전 문서의 후대 안내가 v0.3.0을 현재 지원으로 표시 | 현재 설치 링크를 v0.4.1로 교정하고 당시 릴리스 본문·판정은 보존 |
| M29 정책·예제·진행률이 여러 설계에서 오래됨 | Signed Write/EATT 기본 OFF·legacy/experimental 정책과 실제 역할 예제로 통일 |
| 검증 목차가 장황하고 완료 뒤 기록도 현재 작업처럼 보임 | 최신 기록·주제별 진입점과 후속 완료 안내를 추가 |
| 빌드 안내의 Windows 경로·그룹이 실제 도구와 다름 | 도구의 현재 제약과 실행 가능한 명령 예제로 교정 |

## 3. 삭제·보존 판정

삭제한 문서 파일은 **0개**다. 동일 byte의 중복 Markdown이나 빈 문서가 없고,
이전 TODO·릴리스 문서·검증 기록은 고유한 결정·제약·실패와 공개 자산의 근거를 보유한다.
중복은 HANDOFF/TODO의 반복 설명을 줄여 정리했다. 파일을 지우지 않아도 현행 진입점에서
과거 이력을 분리해 가독성을 개선할 수 있다.

원시 evidence JSON/log, 과거 source와 당시 PASS/FAIL/NOT RUN, SDK·third-party·board gitlink,
생성 계약·공개 package·Release 자산은 보존한다. 구버전의 현재 지원 안내만 수정한 경우에도
해당 버전의 실제 시험 수치·출시 결과를 최신 결과로 덮어쓰지 않는다.

## 4. 외부 문서와 도구의 확인된 경계

- Board submodule의 커넥터 설명 일부는 Core의 소유자 확정 전사와 다르다. 예를 들어
  Core의 `P1.04`는 `P2-12`, `P2.04`는 `P2-17`이다. 실기 결선은
  [확정 P2/P4 핀맵](<../01_아두이노 코어 설계/13_NU54DK_P2_P4_커넥터_핀맵.md>)과
  [기계 원본](../../tests/hil/nu54dk/nu54dk_connector_pinmap.json)을 따른다.
  Board submodule 문서와 gitlink는 이번 Core 문서 변경에 포함하지 않는다.
- Windows Zephyr 빌드는 현재 runner의 짧은 출력 경로 제약을 따른다. Matrix 도구의 하위
  경로를 Windows에서 지원한다고 확대하지 않으며, 직접 group별 실행을 안내한다.
- CI badge·예제 compile·Host PASS만으로 실기나 cross-vendor 상호운용을 PASS로 표시하지 않는다.
- [125번 기록](125_v0.4.0_정식_릴리스_공개와_T24_T25_마감.md)의 Runtime payload SHA-256
  표시는 61자리로, 유효한 64자리 checksum이 아니다. 원문은 보존하고 검증값으로 사용하지
  말라는 정오 주석을 추가했다. 저장소에서 올바른 원본을 재확인하지 못해 임의 복원하지 않았다.
  이는 해당 문서의 표기 한계이며 별도로 기록된 공개 ZIP checksum이나 당시 실기 판정을 바꾸지 않는다.

## 5. 로컬 검증과 인계

| 검사 | 실제 결과 |
| --- | --- |
| `python -B tools/ci/run_m12_gate.py docs` | Markdown 285/285 UTF-8·내부 경로 PASS |
| Markdown 제목 anchor 교차 점검 | 내부 제목 링크 60개 확인, 깨진 후보 0 |
| 빈 문서·동일 byte 중복 | 시작 main 284개 중 각각 0개 |
| `python -B tools/ci/run_m12_gate.py contract` | 46/46 PASS |
| `python -B tools/ci/run_m12_gate.py inventory` | 생성 계약 5개·생성기 4개, product identity·75개 inventory·serial/system·release 계약 PASS |
| `python -B -m unittest discover -s tests/host -p 'test_m2?_readiness.py' -v` | M28 8개 + M29 8개 = 16/16 PASS |
| `python -B tools/ci/run_m12_gate.py package` | 21/21 PASS |
| `git diff --check` | PASS |

이번 변경은 문서와 감사 원장에 한정한다. Runtime source·기존 readiness·원시 HIL evidence와
board submodule은 변경하지 않았으며, 새 전체 Host 실행·target build·보드 실기를 수행한 것으로
기록하지 않는다. 문서 내용 검토에서 확인한 source/API 사실과 위 로컬 검사의 범위를 구분한다.

문서 commit/push 뒤 해당 SHA의 원격 CI는 나중에 확인한다. 실기는 재개하지 않았고
M29는 계속 **6/8(75%)**, `M29-MULTI-01`·`M29-REG-01`은 **NOT RUN**이다.
