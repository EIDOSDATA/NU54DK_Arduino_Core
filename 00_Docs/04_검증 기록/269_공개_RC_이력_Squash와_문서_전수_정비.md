# 269. 공개 RC 이력 Squash와 문서 전수 정비

작성: 2026-09-27. 사용자 요청에 따라 종료한 `M31-MEM-OPT` branch를 제거하고,
`0.5.0-RC1`의 main 이후 개발 이력을 하나로 정리한다. 이번 작업은 문서·Git 관리이며
펌웨어 변경, 새 HIL, 정식 stable 공개가 아니다.

## 1. 이력 정리 범위와 원본 보존

| 항목 | 정리 전 기준 | 정리 범위 |
| --- | --- | --- |
| `main` / `origin/main` | `4b6afa7a097bdf32b1535a264e443233c3258bf8` | 변경하지 않음 |
| `0.5.0-RC1` / 원격 | `174713ffa7dd1fbe1e8d4cd614fb1678e89ff17b` | main 이후 83개 commit과 이번 문서 변경 → squash 1개 |
| local `M31-MEM-OPT` | `8691fd0db1893d1a4e9fe93b26453f039f83430c` | 원본 포함 여부 확인·backup 후 삭제 |
| remote `M31-MEM-OPT` | `dd6beea5fd7fff931e16be61723f483a64de7ade` | exact ref lease로 삭제 |
| 공개 RC tag | `v0.5.0-rc.1` → `7786984a186980f6220271cd506636e4564bc55d` | tag·Release·7개 자산 불변 |
| board submodule | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` | 변경하지 않음 |

시작 작업 트리는 깨끗했고 local/remote M31 branch 모두 공개 RC source의 조상임을 확인했다.
원격 갱신은 이전 SHA를 명시한 `--force-with-lease`와 atomic push로 제한한다. 다른 작업자가
ref를 갱신했다면 덮어쓰지 않는다. main 병합, tag 재작성, 배포 ZIP 교체는 하지 않는다.

83개 원본 commit 대응은 [이력 manifest](<evidence/rc1-history-docs-20260927/history-manifest.json>)에
보관한다. 새 SHA는 이 문서를 포함한 squash commit 자체다. 자기 자신의 SHA를 본문에 넣어
다시 commit하는 순환을 피하며 `git log -1`과 원격 branch로 확인한다.

복구 bundle은 저장소 밖의
`C:\Users\eidos\Documents\Codex\2026-09-25\x20\outputs\pre-rc1-squash-174713ff.bundle`에 있다.
`git bundle verify`를 통과한 complete-history backup이며 SHA-256은
`742cf1da2a8fdb14a8700425a9142a5843a70079eb58c543cde20ec9986aa1a5`다.
정리 전 RC branch·두 M31 ref·공개 RC tag를 포함한다. 공개 RC tag에서도 당시 개발 이력을
계속 조회할 수 있다. 따라서 GitHub의 **RC branch 이력**은 간결해지지만 보존한 release tag의
역사까지 사라지는 것은 아니다.

기존 checkout 갱신과 공개 RC 재현 방법은
[기여 안내](../../CONTRIBUTING.md#이력-정리-뒤-기존-checkout)를 따른다.

## 2. 문서 구조와 정리 원칙

- 루트 README는 제품 소개·stable/RC 선택·설치·첫 예제·지원 한계·도움말 순서로 정리한다.
- `00_Docs/README.md`는 독자별 진입점, 릴리스 목차는 version별 설치·이전 안내를 소유한다.
- 누락된 개발 진입점 `CONTRIBUTING.md`에 clone·환경·검사·문서 소유권·squash 후 동기화를 추가한다.
- TODO·HANDOFF·설계에서 남은 M31 6/8, DF/CS 미완료, RC 미공개 등 현행 상태의 모순을 교정한다.
- 검증 기록 목차의 중복 최신/과거 목록을 제거하고 현재 근거와 접을 수 있는 번호별 archive로 나눈다.
- 공개 library 안내는 stable 30개와 RC 113개 예제를 구분한다. 진단용 DF receiver를 제품 지원으로
  안내하지 않으며 제품 SDC IQ RX·AoD `UNSUPPORTED` 경계를 유지한다.

기존 번호별 기록과 version별 문서는 서로 다른 실행·출시 시점의 증거이므로 불필요한 복제본으로
취급하지 않는다. 같은 진행 상태를 여러 곳에 복사한 설명을 줄이고 원본으로 링크한다.
링크·감사 경로를 흔드는 일괄 폴더 이동이나 번호 재배열은 하지 않는다. 기존 206·207번 결번은
이번에 삭제한 문서가 아니다. third-party·board 원본과 자동 생성 문서는 직접 편집하지 않는다.

## 3. 검토와 검증 경계

파일별 분류·검토 깊이·변경 여부·UTF-8/LF hash는 [문서 감사 원장](../document-review.json)이
소유한다. 전체 Markdown의 inventory, UTF-8, 내부 링크, 동일 본문 중복과 hash를 확인하고,
현행 안내·계약을 상세 대조한다. 과거 기록의 기술 결과는 재시험으로 재판정하지 않는다.

| 검사 | 이번 작업의 판정 |
| --- | --- |
| 문서 UTF-8·상대 링크·감사 inventory/hash | 원장의 이번 검사 결과 참조 |
| 주변장치 생성 문서 | **PASS** — 4개 generator, 5개 출력 일치 |
| coverage 생성 문서 | **PASS** — 변경 없는 render check |
| M31 readiness 계약 | **PASS** — 완료/미지원 경계 유지 |
| release·shard·lifecycle·설치예제·공개경계 관련 Host | **PASS** — 60 tests, 28 subtests |
| 런타임·SDK·workflow·기계 readiness·기존 evidence | 문서 이전 기준과 Git blob 비교, 변경하지 않음 |
| 새 firmware build / 물리 HIL | **NOT RUN** — 이번 변경에 포함하지 않음 |
| push 이후 exact-SHA CI | 이 commit 작성 시 **NOT RUN**; push 후 해당 SHA의 Actions 결과를 확인하며 기존 run을 새 PASS로 대체하지 않음 |

공개 RC 준비·실물 결과는 [267번](267_M31_W08_Windows_RC_준비와_M31_완료.md), 공개 다운로드·설치
smoke는 [268번](268_v0.5.0-rc.1_공개와_다운로드_smoke.md)의 source와 조건에 한정한다.
이번 Git/document 정리를 새 물리 PASS로 세지 않는다.

## 4. 현재 지원과 다음 작업

stable은 `v0.4.1`, 공개 후보는 `v0.5.0-rc.1`이다. P0·P1·P2와 M31-W01~W08 **8/8**은 완료했다.
정식 `v0.5.0` 승격은 별도 결정이며 M32/M33, 보류한 HOST-W04~W08을 자동 착수하지 않는다.
현재 안내는 [HANDOFF](../HANDOFF.md), 세부 분모는 [M31 TODO](../TODO_M31.md)를 따른다.
