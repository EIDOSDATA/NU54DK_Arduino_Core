# M33 개발 인계 — W06 현행 상태

최종 갱신: **2026-11-02**. 개발 집중 #1~#49 누적 PASS는 완료 기록으로 보존한다.
W06 마감은 미완료다. **전체49 연속 재시작을 필수로 전제하지 않고**, 기존 독립 증거·수정 회귀와
실제 남은 마감 입력을 확인한다. 최신 사용자 지시에 따라 문서 정리 후 아래 1~7을 자율 진행한다.

## 현재 기준선

| 항목 | 현재 상태 |
| --- | --- |
| 저장소 | `D:/w06/a/user/hardware/nucode/zephyr` |
| 브랜치·구현 source | `Dev-0.6.0-M33` · `93fc19f14ea54d8002b61fba81366d964a4071d7`(S14), push 확인 |
| 이번 변경 | HIL pre-program reset 기본값·안전한 flash 오류 기록·회귀시험·문서; 제품 C/C++·SDK·board 변경 없음 |
| 수정 검증 | S13의 reset 비교 진단과 S14 관련 Host242·skip0. 새 S14 실기 PASS로 합산하지 않음 |
| S14 exact CI | [41405732886/attempt1](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/runs/41405732886), 9 job success·job skip0 |
| S14 Actions | [41405696091/attempt1](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/runs/41405696091), 최신 API 관측은 진행 중; 전체141 수락 전 |
| 개발49 | source별 누적 PASS. [306번](<04_검증 기록/306_M33_W06_개발_49개_완료와_최종_빌드_중단_인계.md>)의 당시 기록 |
| 마지막 공식 cycle | S13 `D:/w06/final27bf`, #1 flash 단계 FAIL·완료0/49. 원본 보존·이어쓰기 금지 |
| 앞선 유효 실적 | S13 Host651·Actions141·ecosystem2·runtime9·stage150 PASS; S13 실적으로 보존 |
| 실제 종료 상태 | 11/02 새 OS·COM·공통3lock 확인. debug/flash/UART 실행0; 현재3보드 firmware·RAM·STOP 재검증을 뜻하지 않음 |
| 자동점검 | w06 PAUSED 유지 지시, 재활성화하지 않음 |
| 로컬 실행 정본 | `D:/w06/control/continuation.json`; 오래된 S8 새채팅 prompt는 역사로 보존 |

## 판단 정정과 증거 경계

상세 경위·J-Link 공식 자료·오류별 원인·회귀 범위는
[307번 기록](<04_검증 기록/307_M33_W06_연속검증_판단_정정과_마감_계획.md>)에 모았다.

- 정상 J-Link 업로드의 reset과 custom J-Link/pyOCD `attach`·`no_reset=True` 경로를 혼동했다.
  관측된 결함은 시험 도구의 program 전 reset 준비 누락이며, 일반 사용자의 업로드나 장비 한계가 아니다.
- 원형 `assemble --campaign-evidence`는 독립49 증거를 지원한다. matrix registry의 순서와
  동일 source·완전성 조건을 무중단 연속 실행 의무로 확대하지 않는다.
- 원래 #1 마지막 약11.5초 FlashFailure subtype과 진단 A의 MPU init 문제의 동일성은 미확인이다.
  원본 FAIL, 부분 PASS, 진단, 실제 새 실행을 구분한다.
- 개발 누적49와 일부 옛 raw 경로는 기록으로 남지만 모두 현재 존재하는 것은 아니다.
  과거 source의 결과를 최신 source로 바꿔 strict closure에 넣지 않는다.
- 별도 #1 재실기, #30~49 일괄, 전체49 재시작, 선행 #29 focused20은 기본 실행 목록에 없다.
  필요한 시험의 고유 cycles·negative·security·STOP·retry 조건은 줄이지 않는다.

## 다음 작업 1~7

1. **현재 상태 확인:** 소유권·프로세스·COM·3lock·마지막 종료 기록과 D 여유를 확인한다.
2. **기존 CI·Actions 확인:** 실행 중인 exact run의 실제 종료·artifact를 수집한다. 중복 dispatch하지 않는다.
3. **기존 실적 정리:** 개발49·진단B·회귀242·CI를 각 source와 범위에 결합한다.
4. **파이프라인 잔여 처리:** Host651·Actions141·ecosystem2·runtime9·stage150의 유효 입력과 미충족을 구분한다.
5. **남은 마감 처리:** 1800초 soak·자원/지원·risk7·qualification3의 실제 미완료 입력만 처리한다.
6. **원형 판정·export:** 독립 actual evidence를 원형 validator·strict closure/export로 검증한다.
   source 또는 원본 누락은 그대로 보고하고 완료를 합성하지 않는다.
7. **마감 기록:** 문서·증거·검사 결과를 commit/push하고 해당 commit CI를 확인한다.
   문서 마감과 W06 실제 완료 여부를 분리한다.

이 목록은 모두 새로 실행하라는 뜻이 아니다. 확인된 실패·누락·변경 영향에 필요한 범위만 진행한다.
원형이 요구하는 같은 source의 원본 증거가 없는데 재실행도 제외된 경우, 충돌하는 구체 입력과
가능한 마감 범위를 제시한다. 조건을 임의 완화하거나 전체 재실행으로 자동 되돌리지 않는다.

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
