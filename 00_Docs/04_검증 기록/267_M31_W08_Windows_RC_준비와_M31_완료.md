# 267 — M31-W08 Windows RC 준비와 M31 완료

## 1. 판정

M31-W08은 **PASS**이며 M31은 **W01~W08 8/8 완료**다. 고정 NCS v3.4.0,
board gitlink `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3`와 Windows 10/11 x64 범위에서
`0.5.0-rc.1` 비공개 package를 독립적으로 두 번 생성해 byte 재현성을 확인했다. 그 package를
GitHub Actions의 격리 설치 환경에서 설치하고 공개 예제 **113/113**을 8개 shard로 정확히 한 번씩
build했으며, v0.4.1에서 RC로의 upgrade·uninstall·reinstall·cache 수명주기를 확인했다.

같은 Actions RC의 runtime payload를 한 NU54DK에 exact sector 방식으로 올려 UART ready와
`setup()` breakpoint를 확인했다. 시험 뒤에는 W07 CS reflector image로 복구해 advertising 중이고
ACL과 진행 중 CS 절차가 없는 상태를 확인했다. 따라서 W08의 package·Windows 설치·대표 실물·
원장·문서 gate는 닫힌다.

다만 현재 설치·지원 버전은 계속 **v0.4.1**이다. v0.5.0 공개 승인, tag, GitHub Release,
catalog 게시와 공개 URL download smoke는 이 작업에서 수행하지 않았고 각각 `HOLD` 또는
`NOT RUN`이다. RC 준비 완료를 공개 릴리스 완료로 읽지 않는다.

## 2. 비공개 RC와 Windows Actions

최종 기능 source `6c3c9ec59c4dd96ad5b4bc81bc013e30dc52b2d8`에서 GitHub Actions run
`36248923341`을 실행했다. prepare job은 package를 서로 독립된 두 경로에서 만들고 archive,
manifest, SBOM, license, checksums, index와 notices의 byte 동일성을 검증했다. plan은 끝까지
`publication_allowed=false`와 공개 승인 blocker를 유지했다.

| 항목 | 결과 |
| --- | --- |
| exact private RC 재현 | **PASS**, 독립 생성 2회 |
| 공개 Arduino 예제 | **113/113 PASS**, 8 shard, 누락·중복·실패 0 |
| 이전 설치본 | v0.4.1 |
| 수명주기 | install → RC upgrade → uninstall → reinstall/cache **PASS** |
| 전체 Host 회귀 | **1,537 passed, 2 skipped, 3,219 subtests passed**, 실패 0 |
| NCS / board lock | v3.4.0 / `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` |
| 공개 상태 | owner approval `HOLD`, public assets/download smoke `NOT RUN` |

8개 shard는 source의 113개 예제를 고정 index modulo 분할하며 aggregate가 각 예제의 정확히 한 번
등장과 모든 개별 PASS를 fail-closed로 검사한다. 0.4.1 공개 때의 Windows 30/30 로컬 설치 build를
그대로 늘여 직렬 실행하지 않고, 이번 확대된 113개 분모는 GitHub Actions Windows runner에서
병렬 처리했다. lifecycle job은 113개 전체 build를 중복하지 않고 대표 예제로 설치 상태 전이와
cache 경계를 별도로 판정한다.

## 3. 대표 실물 upload·UART·debug와 복구

실물 시험 직전에 probe SHA-256 identity, COM, 역할과 image hash를 다시 결합했다. 배타 probe lock,
watchdog와 명령 lease를 유지하고 exact 대상 sector만 flash했다. `auto_unlock=false`였으며 mass
erase·unlock·recover는 요청하지 않았다. 원시 probe UID도 evidence에 저장하지 않았다.

Actions RC의 대표 upload 뒤 `NUCODE_M8_UPLOAD_READY`를 UART에서 확인했고 GDB가 `setup()`
breakpoint에 정지해 source line을 표시했다. 이 실물은 source `a2257170...`에서 생성한 RC였지만,
최종 `6c3c9ec5...`의 runtime payload SHA-256도
`4eb04d8ad071c6a163e354046ff1a5e801aa75a4789b32277a347613c1c7a6bb`로 동일하다. 후속 변경은
lifecycle·Host test·CI 집계 계약 교정이며 실물에 올린 runtime byte와 최종 검증 runtime byte가 일치한다.

시험 뒤 보드를 W07 CS reflector image
`81e3025ce5b60247cab8d196bbdc62de8e856c0e789cab542222f922c71f59c6`로 sector-only 복구했다.
advertising은 동작하고 ACL 연결과 활성 CS 절차는 없다. 임의 배선·전원·USB 변경은 하지 않았다.

## 4. 실패 원본과 수정

최종 PASS 전의 실패·취소를 지우지 않았다.

| source / run | 원인 | 처리 |
| --- | --- | --- |
| `5a75fd85...` / `36238302917` | `post_install`이 고정 설치 root를 따르지 않았고 서로 다른 절대 artifact root를 한 upload 입력으로 전달 | 설치 root 전달과 단일 staging root로 수정, 실패 run 보존 |
| `2c2bf0b...` / `36239764407` | lifecycle 대표 build 경로 해석 오류와 일부 예제 profile 오분류 | 선언 profile routing과 경로 계산 교정, 실패 run 보존 |
| `a2257170...` / `36241541445` | `ready.json`을 `post_install` 전 hash로 비교해 정상 갱신을 uninstall 손상으로 오판 | uninstall 직전 상태를 기준점으로 고정, 실패 run 보존 |
| `fb669f50...` / `36242627303` | secure DFU sysbuild의 application·MCUboot HEX 두 개를 일반 build의 단일 HEX 계약으로 검사 | manifest가 지정한 primary application HEX를 root·hash와 함께 검증하도록 수정, 다른 7개 shard PASS와 실패 aggregate 보존 |
| `065b026a...` / `36245646295` | 8개 shard 113/113와 lifecycle은 모두 PASS했으나 aggregate PowerShell 임시 script의 한국어 문자열이 잘못 decode되어 parse error | aggregate 실행 block을 ASCII-only로 고정하고 workflow ASCII unit test 추가, 실패 run 보존 |
| system Python | `pyocd` 미설치 수집 오류 4건 | Nordic 고정 toolchain Python으로 실행, 환경 실패 보존 |
| Nordic Python 최초 process-lock | child가 `-I` 없이 system stdlib를 상속 | child도 격리 실행하도록 수정, 실패 원본 보존 |

원인 없는 무한 재시도는 사용하지 않았다. 각 실패는 원인을 특정해 수정한 뒤 새 source/run으로
검증했다. Actions build와 Host test는 물리 HIL PASS로 기록하지 않고 §3의 대표 실물만 물리
upload/UART/debug PASS로 구분한다.

## 5. 증거

- [W08 closure audit](evidence/m31-w08-close-20260926/closure-audit.json)
- [GitHub Actions aggregate](evidence/m31-w08-close-20260926/ci-aggregate.json)
- [Windows lifecycle](evidence/m31-w08-close-20260926/lifecycle.json)
- [비공개 RC plan 요약](evidence/m31-w08-close-20260926/rc-plan-summary.json)
- [대표 실물 upload/UART/debug](evidence/m31-w08-close-20260926/physical-upload-debug.json)
- [실물 시험 뒤 image 복구](evidence/m31-w08-close-20260926/post-hil-restore.json)
- [실패·수정 이력](evidence/m31-w08-close-20260926/diagnostic-history.json)
- [최종 Host 회귀](evidence/m31-w08-close-20260926/host-regression.json)
- [증거 manifest](evidence/m31-w08-close-20260926/manifest.json)

## 6. 완료 경계와 다음 작업

- M31 원장은 W01~W08 **8/8 완료**, test family **9/10 PASS**다. 남은 한 family의 제품 SDC
  raw IQ RX는 고정 SDK 지원 근거에 따른 `UNSUPPORTED`이며 누락된 PASS가 아니다.
- M31-W03 11/11, W04, W05, W06, W07과 메모리 최적화 P0~P2의 기존 판정은 유지한다.
- 외장 audio·angle/control, 일부 CS 외부 실물 후속은 기존대로 `NOT RUN`·비차단이다.
- `M31-MEM-OPT` 브랜치는 삭제하거나 이력을 재작성하지 않고 보존했다. W08 마감은
  `0.5.0-RC1` 브랜치에서 수행했다.
- 다음 단계는 v0.5.0 RC 검토와 사용자의 별도 공개 승인이다. 승인 전 tag·Release·catalog 게시와
  공개 download smoke를 수행하지 않는다.
- HOST-W04~W08, M32와 M33은 후속 작업으로 남기며 자동 착수하지 않는다.
