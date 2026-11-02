# M33 개발 인계 — W06 현행 상태

최종 갱신: **2026-11-03**. W06은 미완료다. 기존 개발49의 source별 PASS는 보존한다.
최신 사용자 승인은 아래 **1~7의 온전한 독립 증거 마감**이다. 전체49 무중단 연속 합격은 요구하지 않는다.
같은 source의 유효한 개별 PASS를 유지하고, 실패한 항목은 원인을 고친 새 attempt로 판정한다.

## 현재 기준선

| 항목 | 현재 상태 |
| --- | --- |
| 저장소·브랜치 | `D:/w06/a/user/hardware/nucode/zephyr` · `Dev-0.6.0-M33` |
| 직전 검증 source | S15 `dcf7bafa446ecfc9b52bba28e85abe1f3c21551c`, push 완료 |
| S15 CI | [41411896808/attempt1](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/runs/41411896808) PASS |
| S15 준비 완료 | Host651/64 suite·skip0, Actions141, ecosystem2, runtime9, stage/validate150 PASS |
| S15 Actions | [41444695074/attempt1](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/runs/41444695074), 4 shard·141 build 수락 |
| 독립49 | `D:/w06/finaldcf7/attempt-001`의 #1 `gap_links` FAIL, 완료 **0/49**; 원본 봉인·이어쓰기 금지 |
| #1 원인·수정 | 수집기는 선두 동일 READY 반복을 허용하지만 최종 파서는 한 줄만 허용했다. 파서를 같은 경계에 맞추고 판정 전 UART 원본 저장을 보장 |
| 수정 검증 | 해당 suite18 PASS. 원본 보존 회귀 1개 추가로 공식 Host **652개/64 suite**; 새 source CI·정식 실기는 아직 별도 필요 |
| 실제 종료 상태 | 실패 capture·debug·OS·6 COM·공통3lock 종료 확인. 현재 세 보드 reset·halt·strict isolation PASS; application STOP으로 바꾸어 기록하지 않음 |
| 개발49 | 과거 source별 누적 PASS. [306번](<04_검증 기록/306_M33_W06_개발_49개_완료와_최종_빌드_중단_인계.md>)의 당시 실적 |
| 로컬 실행 정본 | `D:/w06/control/continuation.json`의 `active_workflow`; 자동점검 w06 PAUSED 유지·재활성화 금지 |

## 판단 정정과 증거 경계

[307번](<04_검증 기록/307_M33_W06_연속검증_판단_정정과_마감_계획.md>)은 연속 검증 판단 오류와
일반 J-Link 업로드/시험 도구 경로의 혼동을 기록한다. 이번 READY 불일치와 raw 보존 수정은
[308번](<04_검증 기록/308_M33_W06_READY_판정_불일치_교정과_독립_마감_재개.md>)에 기록한다.

- 원형 `assemble --campaign-evidence`로 독립49를 결합한다. 단일 writer·공통3lock 때문에 차례로
  실행하는 것과 전체49가 한 번에 끊김 없이 성공해야 한다는 요구를 혼동하지 않는다.
- 같은 source의 유효 PASS는 한 항목 실패 때문에 버리지 않는다. FAIL은 보존하고 새 attempt만 채택한다.
- 구현·시험·판정 코드 변경으로 source가 바뀌면 과거 PASS를 새 source 실적으로 고쳐 쓰지 않는다.
  이번 변경은 검증 코드 수정이며 S15와 새 source의 증거를 분리한다. 연속 실행을 위한 재시작이 아니다.
- 선두 READY의 물리적 반복 원인은 확정하지 않았다. reset 미실행이나 일반 J-Link 업로드 결함으로 단정하지 않는다.
- #29의 공식20회 fresh/restored 총40구간과 #30~#49는 독립49 범위에 포함한다. 별도 선행 focused20은 없다.
  각 시험의 cycles·negative·security·STOP/cleanup·retry 합격 조건은 유지한다.

## 다음 작업 1~7

1. **수정 검증·기준 고정:** 최소 수정과 관련 회귀·문서를 마감하고 commit/push·exact CI를 확인한다.
   소유권·프로세스·COM·3lock·SDK/도구/board·여유 공간과 clean source S를 고정한다.
2. **Host652:** S의 원형 Host652/64 suite·skip0, 원본 로그·시험 ID/hash·실제 process 종료를 확보한다.
3. **같은 S의 준비:** Actions 4 shard·build141 → ecosystem2 → runtime9 → stage/validate150.
   exact run 중복 dispatch는 하지 않으며 원형이 허용한 build/campaign 재사용만 적용한다.
4. **독립49:** 기능33+자원8+자동 peer8의 같은 S 원본 증거를 확보한다. 중간 실패는 원인부터 교정한다.
   실패 cycle에는 이어 쓰지 않고 유효 PASS는 원래 경로에 보존한다. 전체49 무중단 합격 조건은 없다.
5. **잔여 마감:** 별도 세 보드1800초 soak, 자원/지원 정합, risk7, qualification3을 완료한다.
   자원8·자동 peer8의 별도 중복 시험층은 만들지 않는다. 외부 제품/OS 실기와 제품 qualification은 실제 범위를 유지한다.
6. **원형 판정·export:** clean S에서 전체 actual evidence·원본 hash·receipt·종료 사슬을 검증하고
   독립 경로로 assemble → strict validate → export를 수행한다. 원본 누락이나 다른 source를 합성하지 않는다.
7. **최종 기록:** 허용된 완료 문서·readiness·증거 참조만 S의 직계 non-merge 기록 commit C 하나로 반영한다.
   원형 S→C 계약 검증 → push → C exact CI → 최종 기록을 완료한다. 이 조건 전에는 W06 완료로 처리하지 않는다.

## 운영·보존 경계

단일 writer·단일 heavy job·공통3lock, 출력/TMP `D:/w06`, 여유4GiB를 유지한다.
정상 sector program·software reset·halt/resume·읽기 진단은 기존 승인 범위다.
DAP/J-Link firmware 작업, Defender 보호 해제·예외·우회, mass erase·unlock·recover는 금지한다.
공개 tag/Release/main 변경과 외부 제품 interop PASS 승격은 이 작업 범위가 아니다.

현행 인계에서 삭제한 날짜별 중복 지시와 긴 source 일지는
[정리 전 고정 Git 버전](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/blob/93fc19f14ea54d8002b61fba81366d964a4071d7/00_Docs/M33_HANDOFF.md)에 남아 있다.
원본 실행·FAIL/PASS/HOLD/NOT_RUN·완료 TODO는 삭제하지 않는다. 과거 source와 경로는 현재 상태로 간주하지 않는다.

## M33 원본 이력 보관 — 2026-10-07 squash

아래는 **2026-10-07에 완료된 이력 정리의 역사 기록**이다. 당시 요청 범위는 M33 브랜치만이었다. 분기 기준 `main`과 공개 release/tag는 바꾸지 않는다.
기존 코드·설정·board gitlink는 유지하고, 이력 정리·복구 안내만 문서에 추가한다. W06 완료나 새 구현 승인이 아니다.

| 항목 | 고정값 |
| --- | --- |
| squash parent | `314c04f2b3e342df5aafa7ba8d950643e9124fe6` — 기존 main |
| 원본 tip | `84c5f4d85c08312d7ce0ff12e2e70b31bdf6564c` — 문서 정비 commit, push 확인 |
| 원본 tree / 대상 수 | `f7013e13afb0c372c37df03b1ac257a20fcc8f02` / main 이후 87 commit |
| 독립 원본 bundle | `D:\w06\archive\git-history-20261007\M33-presquash-84c5f4d8.bundle` |
| bundle SHA-256 | `b95cbd07520c080c76c0a15bd03b480668a1ed79add8e13bbd300c7d25e7b6c5` |
| bundle 크기·검사 | 152,774,333 byte; `git bundle verify` PASS, complete history·선행 bundle 불필요 |

당시 원격 변경은 원본 tip을 기대값으로 한 `--force-with-lease`로 M33 ref에만 적용했다. 현재 추가 이력 변경 지시가 아니다.
당시 parent·변경 범위·원격 일치를 검증했다. 새 build/HIL PASS로 승계하지 않았다.
당시 문서/이력 commit의 `[skip ci]` 사용은 과거 사실이며, 현재 마감 commit CI를 생략하는 지시가 아니다.

기존 checkout은 미커밋 작업과 별도 commit을 먼저 보존한다. squash 전 M33를 새 M33에 일반 merge하거나
그대로 `pull`해 원본 87개 이력을 다시 섞지 않는다. 원본 SHA 재현이 필요할 때는 이 bundle의 존재·hash를
확인한 뒤 별도 D 경로에 복원한다. bundle은 Git 이력만 보관하며 로컬 raw·runtime·SDK의 백업은 아니다.

## M32 원본 이력 보관

M32 브랜치는 삭제됐고 최종 내용은 M33 분기 기준 main에 남아 있다. 아래는 **과거 보관 기록**이며
현재 파일 존재 증명이 아니다. 이번 M33 squash에서 M32 branch 복원이나 추가 main 정리는 하지 않는다.

| 기록 | 당시 위치·identity |
| --- | --- |
| M32 원본 bundle | `C:\Users\eidos\Documents\Codex\2026-10-02\di-x20\outputs\M32-history-0c2af5bd.bundle` |
| 원본 tip / SHA-256 | `0c2af5bdd561c7d271dd21041e2294aba0ea6005` / `12e3f96ae50d30ac721bf43fdc217b7819ff7b388e046d622326d013ff99bdb1` |
| 문서 squash 전 bundle | `C:\Users\eidos\Documents\Codex\2026-10-03\m33-c-users-eidos-github-nu54dk\work\m33-docs-presquash-12637a30.bundle` |
| 문서 bundle SHA-256 | `cc75117047e8214fe440250891dfe95097cb56921a0f6b10e26f8885919f0e13`; 부모 6867 이력이 필요한 증분 백업 |
| 릴리스 백업 | 원격 `Release-0.5.0`의 `4790e3fa…` 기록; 공개 자산 보존 |

당시 감사는 [295번](<04_검증 기록/295_M32_문서_전수_정비와_main_Squash_통합.md>)과
[302번 §7](<04_검증 기록/302_M33_W06_빌드_통과와_runtime_중단_인계.md#7-로컬-자료-삭제-후-후속-인계--2026-10-05>)을 따른다.
실제 복구 필요 시 파일 존재·hash·bundle prerequisite를 다시 확인한다.
