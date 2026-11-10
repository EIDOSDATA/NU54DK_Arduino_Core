# M33 개발 인계 — W06 수락 마감과 HOST-W04 진행

W06은 실제 PASS 46개와 사용자 승인 3개(#29·40·44)를 구분하여 수락 마감했다.
원형 strict 기술 완료는 미충족이며 #29 원인 분석은 유예했다.
[310번 수락 마감](<04_검증 기록/310_M33_W06_사용자_수락_마감_완료.md>)과
[공개 hash 참조](<04_검증 기록/evidence/m33-w06-b46ce570/closure-reference.json>)가 최종 결과다. 현행 범위는
[M33 TODO의 W06 절](TODO_M33.md#m33-w06--자원회귀상호운용)이 소유한다.
2026-11-10 사용자가 HOST-W04부터의 순차 진행과 모든 문서 갱신을 지시했다. 현재 HOST-W04 진행 중이며 Host는 3/8이다.
최신 상태는 [Host 원장](../variants/nu54dk/host-readiness.json)과 [311번 기록](<04_검증 기록/311_M33_W06_명시_수락_정정과_HOST_W04_착수.md>)을 따른다.
이 문서는 실제 재개 입력과 과거 증거의 위치를 안내한다.

## 현재 기준선

| 항목 | 확인 위치 |
| --- | --- |
| 기준 저장소·개발 브랜치 | `D:/w06/a/user/hardware/nucode/zephyr` · `Dev-0.6.0-M33` |
| 실제 작업본·source·단일 writer | `D:/w06/control/continuation.json`의 `active_workflow` |
| 진행 항목·source별 결과·native 종료 | 같은 `active_workflow`와 연결된 원본 terminal·tool completion·receipt |
| 현행 실행 순서·완료 분모 | [M33 TODO의 W06 절](TODO_M33.md#m33-w06--자원회귀상호운용) |
| 자동점검 | w06 PAUSED 유지·재활성화 금지 |

현재 source와 프로세스·보드 상태를 과거 인계에서 추정하지 않는다.
재개 시 실제 종료 증거와 공통3lock·COM·작업본 상태를 확인한다.

아래는 보존된 #29 재현 조건이며 현재 실행 지시가 아니다. 사용자 지시로 원인 분석과 추가 실기는 유예한다.
실패 후 현재 시험 peer의 bond가 남은 상태에서 #29 native-only campaign을 새 fresh attempt로
다시 시작할 때에는 원형 native scoped cleanup을 수행하고 실제 native·debug·OS·COM·공통3lock 종료를 확인한다.
검증된 현재 peer의 bond만 삭제하고 다른 bond의 보존을 확인한다.
STOP은 링크·대기 작업·스캔·광고·watchdog 종료 확인이며 bond 삭제를 대신하지 않는다.
정상 fresh→restored→second-peer 사이에는 이 준비 cleanup을 끼워 넣지 않는다.

실패 원본과 같은-source 유효 PASS는 보존한다. 이 cleanup은 campaign 실적에 더하지 않으며,
이를 위해 완료된 standard20을 반복하지 않는다. 새 attempt는 fresh passkey를 포함한 원형 분모와 조건으로 판정한다.
진단 trace 추가나 미재현을 인증 실패 원인 교정으로 기록하지 않는다.

## 판단 정정과 증거 경계

[304번](<04_검증 기록/304_M33_W06_실행_정리와_문서_전수_검토.md>)부터
[309번](<04_검증 기록/309_M33_W06_DFU_RRAM_초기화_교정과_증거_범위.md>)까지는 당시 source와 실행의 역사 기록으로 보존한다.

과거 개발49 완료는
[306번](<04_검증 기록/306_M33_W06_개발_49개_완료와_최종_빌드_중단_인계.md>),
연속 검증 판단과 J-Link 경로 혼동의 정정은
[307번](<04_검증 기록/307_M33_W06_연속검증_판단_정정과_마감_계획.md>),
READY 판정과 raw 보존 교정은
[308번](<04_검증 기록/308_M33_W06_READY_판정_불일치_교정과_독립_마감_재개.md>)에 있다.

S16의 #1~#17 PASS와 #18 FAIL, secondary RRAM 초기화 120초 timeout 및
87.13초 교정 진단은 [309번](<04_검증 기록/309_M33_W06_DFU_RRAM_초기화_교정과_증거_범위.md>)에 보존한다.
교정 진단을 정식 #18 PASS로 바꾸지 않는다. #18 실패를 J-Link reset 부재로 설명하지 않는다.
선두 READY 반복의 물리적 원인도 확정된 것으로 기록하지 않는다.

원본 PASS/FAIL은 해당 source·attempt의 기록이다.
현행 증거의 수락과 독립 조립은 M33 TODO의 W06 절 및 원형 계약에 따라 판정한다.

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
