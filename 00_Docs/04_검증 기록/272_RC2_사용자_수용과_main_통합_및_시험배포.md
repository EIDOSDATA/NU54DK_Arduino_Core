# 272 — RC2 사용자 수용과 main 통합 및 시험 배포

작성일: 2026-09-27. [271번](271_v0.5.0-rc.2_사용자경험_교정과_검증.md)의 초기 공개 HOLD 이후 결정이다.
과거 성능 FAIL·GUI HOLD와 실패/재시도 원본을 보존하며 새 수용 결정으로 기술 결과를 덮어쓰지 않는다.

## 1. 사용자 결정과 범위

사용자는 최종 결과를 확인한 뒤 현재 결과가 충분하다고 수용하고 모든 문서를 읽어 갱신하며,
`0.5.0-RC2`를 main에 반영하고 README에 설치 링크를 제공하라고 요청했다.
Arduino GUI 시험은 사용자가 직접 수행한다. 따라서 RC2는 성능 목표 미달을 수용한 GUI 시험용 Pre-release다.
stable v0.5.0 공개·M32/M33 착수·보류 Host 재개·추가 실물 flash·squash/force-push·branch 삭제는 이번 범위 밖이다.

## 2. 불변 배포 입력

| 항목 | 값 |
| --- | --- |
| RC2 source/tag | `b2e7a587ba6fde31e033dc21008d7084bd6e631b` / `v0.5.0-rc.2` |
| 이전 main | `7b8692441f92c9d5b93d2613f6c8c50312992519` |
| Board gitlink | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` |
| Archive | `nucode-nu54dk-zephyr-0.5.0-rc.2.zip`, 8,717,905 bytes |
| Archive SHA-256 | `b2992bcab8c2e7cb322336a3be1a5101c69da5b63fa1676add0194ae181d43c4` |
| Index SHA-256 | `6324f0a2218fa38725e064d004c9eb062cdb743011af5a640743e8d675be8e0a` |
| Runtime payload SHA-256 | `61e3e30ee797bc019dd3d3c49479b706ed35a49bcc4e6f8114d85f1f3c24d5c8` |

배포 자산은 [Full RC run 36287748550](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/runs/36287748550)의
재현 package이며 문서 변경으로 재생성하지 않는다. 후속 문서/main HEAD와 tag의 source를 구분한다.
Archive 내부 문서는 b2e7 생성 당시 snapshot이며 최신 사용자 안내는 main의 RC2 문서 묶음이다.
기존 package plan/aggregate의 `publication_allowed=false`는 생성 당시 HOLD로 보존한다.
이후 사용자 수용 판단은 이 기록에 별도로 남기며 자동 validator를 모든 gate PASS로 속이지 않는다.
`stable_v0.5.0_publication`은 지금도 승인되지 않았다.
기존 `v0.5.0-release-readiness.json`의 RC1 공개 항목도 당시 완료 계약으로 보존한다.
이번 RC2 수용·공개 상태의 최신 원본은 이 기록이며 RC1 원장을 소급 재작성하지 않는다.

불변 증거: [원래 package plan](evidence/rc2-public-20260927/original-package-plan.json) ·
[최종 Full RC 집계](evidence/rc2-public-20260927/full-rc-ci-aggregate.json) ·
[최종 package M8 HIL](evidence/rc2-public-20260927/b2e7-m8-hil.json).

## 3. 검증 결과와 예외

- 최종 b2e7 M12 attempt 2: 9/9 job 성공, 대표 job 24분 20초로 20분 목표 FAIL.
- 최종 b2e7 Full RC attempt 2: 11/11 job 성공, 설치 예제 113/113, 실패/누락/중복 0.
  SDK 설치 정체 worker 0/3의 실패 job 재실행과 나머지6개 성공 재사용, compile bounded retry 1회는 보존한다.
  성공 shard 최장 54분으로 40분 목표 FAIL이며 전체 재시도 시간은 그보다 길다.
- 최종 package의 M8 sector flash/UART ready HIL PASS. 자동 unlock/recover/mass erase 없이 한 번 업로드했다.
  실제 다중 probe negative는 E_PROBE_AMBIGUOUS, exit1, flash false다. 이번 문서/공개 작업은 추가 flash하지 않는다.
- GUI는 native app 자동화 표면이 없어 초기 HOLD였고 이제 **사용자 후속 NOT RUN**이다.
  [GUI 확인 목록](<../05_릴리스/v0.5.0-rc.2/TESTING.md>)에서 새 결과를 추가한다.

## 4. 문서 전체 검토

현행 안내·계획·설계·도구·라이브러리·검증 기록·버전별 릴리스 Markdown **450개**를 분담해 전문 검토했다.
main 저장소 444개와 board submodule 6개이며, 기존 문서 63개 수정·RC2 문서 6개와 이 기록 1개 추가·380개 보존이다.
역사 증거와 upstream/board 문서는 사실이 그대로 유효하면 보존했고 문서를 일괄 덮어쓰지 않았다.
실제 수정한 문서, 보존한 문서, LF 정규화 SHA-256과 검증 결과는 [전수 감사 원장](../document-review.json)에 기록했다.
README/HANDOFF/TODO/설계/인덱스의 현재 버전·probe 메뉴·CI 계약을 동기화했다.

UTF-8/상대 링크 444개, 변경 문서로 들어오는 제목 anchor 65개, peripheral/coverage 생성 문서,
M31 contract, CI contract, release/readiness/example 경계 집중 Host 47개와 `git diff --check`가 통과했다.
회로도 PDF·라이선스 전문·원시 evidence TXT/JSON·빌드 입력은 편집 Markdown 분모가 아니며 기존 원본을 보존했다.

## 5. main 통합과 공개 확인

기존 main `7b869244...`에서 RC2 source `b2e7a587...`까지 16개 commit을 fast-forward로 통합하고 원격 main에 반영했다.
이후 문서 변경은 main의 별도 후속 commit으로 기록하며 squash/force-push는 하지 않는다.
RC1·RC2 branch, 기존 tag/Release/asset과 stable v0.4.1 index는 보존했다.
`v0.5.0-rc.2` annotated tag는 검증된 b2e7 source를 가리키며, 후속 문서 HEAD로 옮기지 않는다.

- GitHub Pre-release를 공개하고 검증된 자산 7개를 그대로 첨부했다. latest stable은 v0.4.1로 유지했다.
- 인증 없이 7개 공개 자산을 재다운로드해 원래 package plan의 크기·SHA-256과 전부 일치함을 확인했다.
  [공개 자산 검증 원장](evidence/rc2-public-20260927/public-assets.json)에 URL과 hash를 남겼다.
- 실제 공개 index로 새 Arduino data/download/user/cache/build root에 CLI 1.5.1 설치를 수행했다.
  설치 버전 0.5.0-rc.2, source b2e7, 설치 manifest의 payload 파일 633/633개의 byte 일치와 예제 113개를 확인했다.
  검증된 기존 NCS 3.4.0/toolchain은 재사용했으며 SDK까지 새로 설치한 시험은 아니다.
- 설치본 Standard Blink compile은 exit 0, 320/320 build target 완료다.
  FLASH 81,528/1,490,944 bytes, RAM 29,439/262,144 bytes이며 추가 실물 flash는 하지 않았다.
  [공개 설치·빌드 원장](evidence/rc2-public-20260927/public-install.json)에 산출물·로그 hash를 남겼다.
- 로컬 시험 보조 script는 Windows PowerShell 5.1의 BOM 없는 UTF-8 해석으로 최초 실행 전 parse 실패했고,
  명시적 UTF-8 로드로 재시작했다. 설치 후에는 정상 stderr 진행 메시지를 `Stop` 오류로 취급해 compile 시작이 중단되었다.
  같은 설치본을 PowerShell 7에서 직접 compile해 성공했으며 adapter의 `state-recovery=1`을 보존한다.
  이를 package compile 실패로 분류하거나 무중단 첫 시도 성공으로 기록하지 않는다.
- [RC2 Release CI 36299678313](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/runs/36299678313)는 성공했다.
  지정한 Full RC run의 exact b2e7 package/aggregate를 재사용·검증했고 재빌드하지 않았다.

tag push로 시작한 별도 M12 재현 matrix는 [36299830764](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/runs/36299830764)다.
문서 commit 자체의 exact main SHA CI는 commit 시점 `PENDING_AT_COMMIT`으로 구분하고 push 후 최종 인계에서 확인한다.
앞선 b2e7 9/9·11/11 성공을 새 문서 commit의 검사 결과로 대체하지 않는다.

- 공개 페이지: [v0.5.0-rc.2](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/releases/tag/v0.5.0-rc.2)
- 설치 URL: [RC2 Boards Manager index](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/releases/download/v0.5.0-rc.2/package_nucode_nu54dk_rc_index.json)
- 사용자 인계: [설치](<../05_릴리스/v0.5.0-rc.2/README.md>) · [시험](<../05_릴리스/v0.5.0-rc.2/TESTING.md>) · [제한](<../05_릴리스/v0.5.0-rc.2/KNOWN_ISSUES.md>)
