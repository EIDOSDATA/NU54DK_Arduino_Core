# M28-W01 CI container revision 교정

| 항목 | 결과 |
| --- | --- |
| 작업일 | 2026-09-12 |
| 원인 분석 대상 | `eb16d0b057316fa07b85a7a324ee514a97b6c2f9` |
| CI 최초 결과 | Software Gates 7/7 PASS, Reproducible Builds의 `v0.5.0` CMake FAIL |
| 교정 범위 | Container Git revision 조회 |
| M28 상태 | **W01 완료 유지 / 1/8, 12.5% / W02 다음** |

## 1. CI 실패 분류와 수정

`eb16d0b0…`의 Linux Nordic container는 `tests/zephyr/m28_ble_capability/CMakeLists.txt`에서
Core revision을 읽을 때 checkout 소유자와 build 사용자가 달라 Git의 `dubious ownership`로
중단됐다. BLE compile·HCI 실패가 아니며 Node.js 20 annotation과도 관계없다.

전역 `safe.directory`를 변경하지 않고 각 `git rev-parse` 명령에 `-c safe.directory=<exact
repository>`를 적용했다. Host 회귀는 명령 단위 허용과 전역 설정 미사용을 검사한다.

| 검사 | 결과 |
| --- | --- |
| M28 capability + readiness Host | **20/20 PASS** |
| `v0.5.0` target build | **1/1 PASS**, 70.37초, warning 0 |
| CI contract / inventory / package | **46/46 / PASS / 21/21 PASS** |
| Markdown UTF-8·내부 링크 | 이 기록 추가 전 **267/267 PASS**, 최종 commit 전 재검사 |
| 로컬 full Host | R02 단독 PASS, 전체 실행의 임시 PE는 Application Control `4551` 환경 차단; 정확한 push CI로 최종 판정 |

## 2. 장비 경계

M28 실기 계약은 NU54DK 3대를 유지한다. 현재 보유·확인한 보드는 2대이므로, W02~W06의
구현·Host·target build와 2-node 전용 HIL을 먼저 진행한다. `M28-LINK-01`, `M28-PER-01`,
`M28-CTRL-01`, `M28-SOAK-01`의 3보드 실행 직전에서 정지한다. 3보드 시험 전에
완료한 2-node 기능시험 전체를 반복하지 않고 image·UID·UART·role preflight만 수행한다.

