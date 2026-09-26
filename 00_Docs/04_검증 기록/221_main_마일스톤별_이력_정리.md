# 221 — main 마일스톤별 이력 정리

## 1. 요청과 정리 범위

2026-09-21 사용자가 main에서 squash 가능한 불필요한 세부 이력을 정리하도록 요청했다.
직전 [220번 문서 정비](220_M31_릴리스_전환과_문서_전수_정비.md)와 별도 승인된 작업이며,
이전의 이력 재작성 금지를 이번 한정 범위에서 변경한다. 최적화·기능 구현·HIL·Host 작업이나
릴리스 공개 승인이 아니다.

공개 v0.4.1 source·catalog 게시·마감을 포함한
`1e0bf4a636e1799b890b51ea7da00bca31e48b03`까지 **143개 커밋은 그대로 보존**한다.
그 이후 미공개 개발 **189개를 7개 의미 단위**로 정리했다. 전체 main은 **332개 → 150개**이며,
이 기록과 현재 인계 갱신을 담은 문서 커밋까지 포함하면 **151개**다.

공개 버전 사이의 이력은 재배포·재현 경계이므로 이번 정리에서 건드리지 않는다.
기존 W03 squash는 다른 기능과 다시 합치지 않고 독립 단위로 유지한다. 다만 M28~M30의
부모 이력이 바뀌었으므로 W03와 이후 커밋의 SHA는 바뀐다. 원본 SHA와 증거는 아래 archive에 남긴다.

## 2. 복구 가능한 원본과 대응표

원격 main을 바꾸기 **전에** 다음 annotated archive 태그를 생성·푸시하고 대상 SHA를 확인했다.

| 항목 | 값 |
| --- | --- |
| 정리 전 main | `4dce513ee135512f66a36e936fde1baca2017115` |
| 전체 원본 보존 태그 | `archive/main-before-milestone-squash-4dce513e` |
| 보존 tag object | `fa3b4752665eaaae3ad1d08c776cd5781f15c997` |
| 새 7묶음의 끝 | `ab0a54c536de560648b34dd7ec647ad6b774d149` |
| 정리 전후 동일 tree | `bb0dc9a100874e75c823603dabc90a23ea42d254` |

| 묶음 | 원본 → 정리 | 원본 끝 | 새 커밋 |
| --- | ---: | --- | --- |
| M28 | 56 → 1 | `a834dccf` | `f865f5f819858ab3b6a6eeb983f74ce78ce7f19d` |
| M29 | 42 → 1 | `19522fb1` | `e4cf269f0b33b07229c8f37d6b1e7c6c66b97ce5` |
| M30 | 72 → 1 | `eff575da` | `f282b3b5261fc4edcbd9214c001bc39b0a5e2e58` |
| M31-W01-W03 | 1 → 1 | `d18309a1` | `96be7f3a0fecd0546b65794ddbe0c7448c58a5d5` |
| M31-W03-docs | 1 → 1 | `8b20157d` | `357ec900b52486aaa9a58ef07d014c0fc14abead` |
| M31-W04-W05-diagnostics | 15 → 1 | `22ff349c` | `ea6a6917f6f27477868a7d72c06af4f178becc66` |
| M31-memory-release-plan | 2 → 1 | `4dce513e` | `ab0a54c536de560648b34dd7ec647ad6b774d149` |

M28·M29·M30은 각각 완료된 기능·검증 묶음이다. M30에는 HOST-W01~W03 공통 기반이 포함되며
HOST-W04 이후는 계속 보류다. W04/W05 진단 묶음은 **미완료 기능의 조사·실패·회복 근거**이지
완료 커밋이 아니다. 메모리 최적화도 계약만 있고 구현은 시작하지 않았다.

원본 189개 전체 SHA, 각 구간의 old/new 부모·끝·tree는
[history-map.json](evidence/main-history-squash-20260921/history-map.json)에 기록한다.
원본 commit을 archive에서 조회할 수 있으므로 과거 HIL/build provenance의 SHA는 치환하지 않는다.

## 3. 보존·동일성 검증

- 7개 경계마다 원본 끝의 Git tree를 새 부모 위에 사용했다. 각 tree SHA가 정확히 같고
  `git diff --quiet <old-tip> <new-commit>`도 모두 통과했다. Patch 재적용이나 임의 파일 선택을 하지 않았다.
- 인계 문서 추가 전 마지막 새 commit과 원래 main의 **전체 파일·mode·gitlink가 동일**하다.
  그 뒤 변경은 이력 매핑·문서 감사·AGENTS/HANDOFF/색인뿐이며 runtime·기존 evidence는 바꾸지 않는다.
- 보존 cutoff가 새 main의 조상임을 확인했다. 원본 189개 전부 `git cat-file` 조회 가능하며
  접근 실패는 0개다.
- 공개 `v0.3.0`·`v0.4.0`·`v0.4.1`과 기존 M31 archive 두 태그의 object/target을 보존했다.
  v0.3.0과 이전 M31 archive가 원래 main 조상이 아니었던 상태도 바꾸지 않았다.
- Board gitlink `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3`, SDK lock SHA-256
  `8c5ab4deaf0bb21dc83957330c49531d011e142959c6f93f7b47052bba5146f3`를 유지한다.
- 문서 UTF-8/local-link·문서 감사 hash와 M31 readiness 계약을 로컬에서 확인한다.
  실제 검사 결과는 [문서 감사 원장](../document-review.json)의 이력 유지보수 검사에 기록한다.
- 새 firmware build·물리 HIL·전체 Host 회귀는 **NOT RUN**이다. Tree 동일성은 내용 보존 증거이며
  새 SHA로 실기했다는 뜻이 아니다. CI/CD 실행 요청·조회·완료 대기는 사용자 지시대로 생략한다.

## 4. 원격 갱신과 다른 PC 인계

main push에는 기대 원격 SHA
`4dce513ee135512f66a36e936fde1baca2017115`를 명시한 **force-with-lease**만 사용한다.
원격 main이 달라졌으면 덮어쓰지 않고 중단한다. 공개 tag/Release/asset/catalog는 변경하지 않는다.

다른 PC에서는 다음 원칙을 따른다.

1. `git fetch origin --tags` 후 원격 main과 위 archive를 확인한다.
2. 이전 main은 새 main으로 fast-forward할 수 없다. 로컬 수정·독자 커밋을 먼저 보존하고,
   새 main 기준 checkout을 사용한다. 무조건 reset하거나 오래된 main을 다시 merge하지 않는다.
3. 과거 source를 확인할 때는 archive와 기록의 exact SHA를 사용한다. 기존 image의 결과를
   새 SHA로 재기록하지 않는다.
4. 다음 개발 순서는 메모리 최적화 → W04·W05 → W06~W08로 동일하다.

이번 시작 시 로컬·원격 branch는 main과 기존 archive branch뿐이었다. 이전에 생성됐던
`M31-MEM-OPT`는 존재하지 않아, 이번 이력 정리에서 임의로 재생성하거나 다른 branch를
삭제하지 않았다. **현재 main에서 종료**하며 후속 요청에서 최신 main 기준으로 분기한다.
