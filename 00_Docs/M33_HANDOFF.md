# M33 개발 인계 — W06 재설계 구현

최종 갱신: **2026-10-07**. 사용자가 현재 M33 브랜치에서 새 검증 파이프라인을 구현하고
W06 완료까지 진행하도록 요청했다. R1·R2 구현과 보드 없는 회귀를 통과했으며, 보존·동기화 기준은
아래 이력 보관 절을 따른다.
구체적인 설계·수락 조건은 [W06 재설계](<02_빌드 설계/11_M33_W06_검증_파이프라인_재설계.md>)가 소유한다.

## 1. 지금의 정본

| 항목 | 상태 |
| --- | --- |
| 작업 저장소 | `D:\w06\src` |
| 브랜치 | `Dev-0.6.0-M33`, origin의 같은 브랜치 추적; 사용자 요청으로 main 이후 87개 commit을 하나로 정리 |
| squash 전 구현 source | `f9f1cd283ee39bcf0609e047473e0e8c5c9930c1`; 원본 시험의 identity, 현재 HEAD와 구분 |
| board gitlink | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` |
| SDK·toolchain | NCS 3.4.0 / `dcbdc366a1`; C 설치본은 읽기 입력 전용 |
| 완료 상태 | M32 12/12, M33 W01~W05 **5/8**, HOST **3/8** |
| W06 | 미완료; R1·R2 완료, R3 실제 수직 연결부터 진행 |
| 현재 제품 | Windows stable/source version 0.5.0; v0.6.0 미공개 |

현재 HEAD는 위 구현 내용과 문서 정비를 포함한 squash 결과다. 기존 결과의 source를 새 SHA로 바꾸지 않는다.
재개 시 HEAD·원격·미커밋 변경·submodule을 실제 확인한다.
이전 미커밋 idle-fixture 4개 변경은 이미 이력에 반영됐으며 현재 다시 적용할 미커밋 패치가 아니다.

## 2. 정리한 실행과 남은 검증

| source/root | 실제 결과 | 사용 경계 |
| --- | --- | --- |
| `846f2993…` / e10 | build 141, Host 62/547, runtime 9, stage 150, matrix 11/49 뒤 signed-write FAIL | 과거 source의 결과; 새 source에 승계 금지 |
| dirty focused 진단 / e10 | orphan GATT 삭제·재부팅 지속성·sign/replay/EATT와 cache 재개 handshake 확인 | 개발 진단; 최종 W06 PASS 아님 |
| `f9f1cd28…` / e11 | clean Host **63 suite / 564 test / skip 0**, ecosystem 역할 build 2개, inventory·debugger 확인 | local aggregate/runtime/matrix/soak/closure 미실행 |
| Actions `37581357663` attempt 1 | 사용자 전환 요청으로 **CANCELLED**. plan·shard 1/3 성공, shard 0/2 취소, aggregate는 미완성 upstream 거부 | 전체 build PASS 아님; 취소로 인한 aggregate 실패를 제품 결함으로 단정하지 않음 |

2026-10-07 16:08 KST에 세 보드 모두 HALTED 유지·RADIO 유휴·상태 복원을 실제 확인했다.
이는 프로그램의 STOP 완료나 f9 firmware 실행 PASS가 아니다. 이후 장치 상태는 다시 확인해야 한다.
정리·자료 가용성·검사 원본은 [304번](<04_검증 기록/304_M33_W06_실행_정리와_문서_전수_검토.md>)을 따른다.

## 3. 재개할 때의 순서

1. [AGENTS](../AGENTS.md), [W06 재설계](<02_빌드 설계/11_M33_W06_검증_파이프라인_재설계.md>),
   [M33 TODO](TODO_M33.md)의 W06 절을 읽는다. 먼저 새 구현 작업의 재개 지시를 확인한다.
2. 실제 D 저장소와 source/board/SDK/toolchain, Python/CLI·symlink·디스크 여유를 확인한다.
3. 기존 registry·runner·oracle·artifact 소비 파일과 비용을 매핑하는 **R1**부터 시작한다.
4. 보드 없는 planner/schema/중단·재개 주입 시험 **R2**를 통과시킨다.
5. 한 그룹의 end-to-end **R3** → 전체 short pass **R4** → 영향 선택/보존/계측 **R5**를 구현·검증한다.
6. 결함 수정 후 clean S를 고정하고 **R6**에서 기존 W06 필수 전체 검증·closure를 수행한다.

현재 `D:\w06\tools\Continue-W06.ps1` 등을 그대로 실행하는 것은 위 재설계 순서가 아니다.
기존 도구는 역사 evidence 검증·비교용으로 보존하며 새 파이프라인이 구현됐다고 가정하지 않는다.
[기존 artifact 안내](../tools/ci/m33_w06_artifacts.md)는 현재 구현의 reference다.

## 4. D 자료와 보존

- 새 checkout/build/artifact/log/cache/temp는 모두 `D:\w06` 아래에 둔다.
- `e1`~`e11`, `artifacts`, `archive`는 서로 다른 source·attempt의 자료다. 이름만 바꿔 합치지 않는다.
- e2/e4/e7/e10의 중복 shard extraction과 e2~e10의 재생성 가능한 clean Arduino clone은 검증 후 정리했다.
  원본 ZIP·receipt·실패 진단·local runtime은 보존했다. 삭제한 extraction의 절대경로를 바로 실행하지 않는다.
- 사용자가 추가 ZIP 삭제를 취소했으므로 이 문서 정비에서 원본 artifact ZIP을 추가 삭제하지 않는다.
- GitHub artifact는 만료될 수 있다. 재사용 시 같은 source/run/attempt의 가용성·권한·hash를 확인한다.
  기존 4-shard 계약은 byte-bearing shard를 각각 받아 aggregate-shards로 결합해야 한다.
- private RRAM backup·signing key·credential·firmware/raw bundle은 공개 문서나 GitHub에 올리지 않는다.
  closure 공개 export는 허용된 metadata만 사용한다.
- 삭제된 옛 C/D 자료는 Git/원격에 없는 local Host·runtime·cleanup까지 복구된다고 가정하지 않는다.

## M33 원본 이력 보관 — 2026-10-07 squash

사용자 요청 범위는 **현재 M33 브랜치만**이다. 분기 기준 `main`과 공개 release/tag는 바꾸지 않는다.
기존 코드·설정·board gitlink는 유지하고, 이력 정리·복구 안내만 문서에 추가한다. W06 완료나 새 구현 승인이 아니다.

| 항목 | 고정값 |
| --- | --- |
| squash parent | `314c04f2b3e342df5aafa7ba8d950643e9124fe6` — 기존 main |
| 원본 tip | `84c5f4d85c08312d7ce0ff12e2e70b31bdf6564c` — 문서 정비 commit, push 확인 |
| 원본 tree / 대상 수 | `f7013e13afb0c372c37df03b1ac257a20fcc8f02` / main 이후 87 commit |
| 독립 원본 bundle | `D:\w06\archive\git-history-20261007\M33-presquash-84c5f4d8.bundle` |
| bundle SHA-256 | `b95cbd07520c080c76c0a15bd03b480668a1ed79add8e13bbd300c7d25e7b6c5` |
| bundle 크기·검사 | 152,774,333 byte; `git bundle verify` PASS, complete history·선행 bundle 불필요 |

원격 변경은 원본 tip을 기대값으로 한 `--force-with-lease`로 현재 M33 ref에만 적용한다.
새 HEAD의 parent·변경 범위·원격 일치를 검증하며, 새 exact build/HIL은 실행하거나 PASS로 승계하지 않는다.
문서/이력 정리 commit은 `[skip ci]`로 저장하여 중단한 긴 build를 자동 재시작하지 않는다.

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

## 5. 변하지 않는 경계

- 주 에이전트 하나, 하위 에이전트·다중 채팅/작업 트리 없음. 로컬 무거운 build/HIL은 하나씩.
- NCS 3.4.0 유지. 3.4.1은 v0.7.0 전용. SDK·board·공개 API를 문서 정비로 바꾸지 않는다.
- 승인된 정상 sector program·software reset·halt/resume는 재개 범위에서 수행할 수 있다.
  erase/unlock/recover 허용 이력은 일반 자동 retry 허가가 아니며 필요성을 먼저 진단한다.
- 현재 보드 연결·결선·firmware·STOP은 과거 기록으로 추정하지 않는다. symlink 권한 우회·임의 승격 금지.
- 완료 TODO 6개·과거 PASS/FAIL/HOLD/NOT_RUN과 공개 자산은 보존한다.
- 외부 Apple/Google·장치 실기는 사용자 후속 NOT_RUN. Linux SSH/Mac 접근을 가정하지 않는다.
  Ubuntu/macOS 실제 지원 검증은 RC 단계다.
- W06 실제 완료 후 다음 범위를 확인한다. HOST → RC/실제 OS → M33-W07 완료 → 별도 공개 승인 순서를 유지한다.

## 6. 원본을 찾는 곳

W01~W05 완료 결과는 [M33 TODO](TODO_M33.md)의 해당 절과 296·298~301번 기록에서 찾는다.
W06의 삭제 전/후 경계는 [302번](<04_검증 기록/302_M33_W06_빌드_통과와_runtime_중단_인계.md>),
D 재개와 개별 실패·교정은 [303번](<04_검증 기록/303_M33_W06_재실행_최소화와_checkpoint_개선_계획.md>),
이번 중단·정비는 [304번](<04_검증 기록/304_M33_W06_실행_정리와_문서_전수_검토.md>)이 소유한다.
축약 전 인계·TODO 전체 문장은 위 M33 bundle에 보존한 Git commit
`f9f1cd283ee39bcf0609e047473e0e8c5c9930c1`에서 복원할 수 있다. 새 원격 clone에 원본 중간 SHA가 있다고 가정하지 않는다.
