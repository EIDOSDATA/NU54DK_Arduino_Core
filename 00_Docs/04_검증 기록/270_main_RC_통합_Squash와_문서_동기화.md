# 270. main RC 통합 Squash와 문서 동기화

작성: 2026-09-27. [269번 RC branch 정리](269_공개_RC_이력_Squash와_문서_전수_정비.md) 뒤 사용자가
main에도 같은 정리를 요청했다. 완료한 RC source와 사용자 문서를 main에 반영하고, v0.4.1 공개
마감 이후 개발 이력을 하나로 정리한다. **정식 v0.5.0 stable 공개나 공개 RC 재배포는 아니다.**

## 이력 범위

| 대상 | 고정 기준과 처리 |
| --- | --- |
| 변경 전 local/remote main | `4b6afa7a097bdf32b1535a264e443233c3258bf8` |
| 가져온 RC source / 보존 branch | `0.5.0-RC1` → `a99623636c01aae87fcba4f72322d83d7d6078f8`; RC ref는 변경하지 않음 |
| 보존 parent | `1e0bf4a636e1799b890b51ea7da00bca31e48b03` — v0.4.1 source·catalog 게시·마감까지 143개 commit |
| squash | parent 이후 원래 main 9개 + RC 1개 + 이번 문서 변경 → 1개; 최종 main 전체 144개 |
| 공개 v0.4.1 source | `bbc2dc1fc5823ca465fc1d1ff2170512282b9313`; tag 불변 |
| 공개 v0.5.0-rc.1 source | `7786984a186980f6220271cd506636e4564bc55d`; tag·Release·자산 불변 |

v0.4.1 tag 직후가 아니라 catalog 공개와 마감까지 보존하는 기준은
[221번](221_main_마일스톤별_이력_정리.md)과 같다. 이후 개발 10개는 현재 RC의 완성된 상태로 통합하며
이전 중간 기능·실패 기록을 지우지 않는다. 원본 대응은
[main history manifest](<evidence/main-rc-sync-20260927/history-manifest.json>)에 있다.
새 SHA는 이 문서를 포함한 main squash commit 자체이며 `git log -1`과 원격에서 확인한다.

## 보존과 복구

시작 작업 트리는 깨끗했다. 먼저 complete-history bundle을 생성하고 `git bundle verify`를 통과했다.

- 파일: `C:\Users\eidos\Documents\Codex\2026-09-25\x20\outputs\pre-main-squash-4b6afa7a.bundle`
- SHA-256: `b531facc11902080b71a37c1dddcab1019fedb89f7a033b16b8770e8ae0b7332`
- 포함 ref: 변경 전 local/remote main, RC branch, `v0.4.1`, `v0.5.0-rc.1`

main 원격 갱신은 변경 전 SHA `4b6afa7a...`를 명시한 `--force-with-lease`로 제한한다.
다른 사용자가 먼저 원격을 변경했다면 덮어쓰지 않는다. RC branch·기존 archive·공개 tag를
추가 삭제하지 않는다. 269번에서 제거한 `M31-MEM-OPT`를 다시 만들지 않는다.

이전 main과 RC branch를 새 main에 일반 merge하면 정리 전 이력이 다시 섞일 수 있다.
개인 변경을 보존한 뒤 새 main 기준 checkout을 만들고 필요한 후속 변경만 검토해서 적용한다.
실제 명령은 [기여 안내](../../CONTRIBUTING.md#이력-정리-뒤-기존-checkout)를 따른다.

## 문서 동기화와 동일성

269번에서 정리한 README·문서 구조·RC 설치 안내·지원 경계를 그대로 main으로 가져왔다.
이번에는 개발 기준 branch와 clone·재동기화·인계 설명을 main에 맞추고 270번 근거를 추가한다.
이력 기록 속 당시 branch/source는 일괄 치환하지 않는다. 기존 번호 기록·생성 문서와 board·
third-party 원본을 유지하며 추가 삭제·폴더 이동은 하지 않는다.

전체 문서 inventory·UTF-8·상대 링크·hash는 [문서 감사 원장](../document-review.json)에서 다시 확인한다.
변하지 않은 본문은 269번 검토를 승계하고 이번 변경 본문을 대조한다. 모든 과거 실기를 다시
시험했다고 표현하지 않는다.

| 대상 | 검증 경계 |
| --- | --- |
| main runtime·도구·workflow·기존 evidence | RC `a9962363...`와 Git blob·mode·gitlink가 동일; 이번 별도 기능 변경 없음 |
| stable root catalog | 원래 main·보존 parent·RC와 같은 blob `8d5760da657154c057bee50f8332b21b5762274c`; v0.4.1 단독 유지 |
| SDK·board | NCS v3.4.0 lock과 board `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` 불변 |
| 문서·생성 계약·관련 Host | 이번 실행 결과는 감사 원장의 checks에 기록 |
| 새 firmware build·물리 HIL | **NOT RUN** — 기존 exact-source 결과를 새 실기 PASS로 바꾸지 않음 |
| push 후 exact-SHA CI | commit 작성 시 **NOT RUN**; 최종 push SHA의 실제 Actions 상태를 확인하고 이전 run과 구분 |

main은 최신 개발·안내 진입점이며 stable 설치 channel을 뜻하지 않는다. 지원 stable은 v0.4.1,
공개 후보는 v0.5.0-rc.1이다. 정식 stable 승격과 M32/M33·보류 Host 작업은
[HANDOFF](../HANDOFF.md)의 별도 후속 범위를 유지한다.
