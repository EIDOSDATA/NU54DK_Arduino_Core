# M32-W03·W04 software/build와 exact HIL blocker

> **과거 blocker 기록:** 아래 판정은 software/build 완료 뒤 실기를 기다리던 시점의 원본이다.
> W03은 [288번](288_M32_W03_연결_timing_feature_exact_HIL_완료.md), W04는
> [290번](290_M32_W04_광고_identity_privacy_exact_HIL_완료.md)에서 exact HIL을 완료했다.
> 현재 전체 완료 상태는 [M32 TODO](../TODO_M32.md)를 따른다.

## 1. 판정

| 항목 | 결과 |
| --- | --- |
| 대상 branch | `Dev-0.6.0-M32` |
| W03 구현 commit | `30258a57…` |
| W04 구현 commit | `b8d0c0c1e46eeb119c61d40b4042ac319fda9dc9` |
| 고정 NCS | `v3.4.0` / `99553055607b2e9885fbc80ccd11fa9da81c2df0` |
| W03 상태 | **진행 — software/build 완료, exact HIL 대기** |
| W04 상태 | **진행 — software/build 완료, exact HIL 대기** |
| M32 완료 수 | **2/12 유지** |

구현과 자동 build 결과는 PASS다. 그러나 반복 sector flash 뒤 개발에 사용하던 두 probe의
CMSIS-DAP debug 인터페이스가 DP/AP에 응답하지 않는다. USB mass-storage·UART·RF가 보인 사실은
exact debug identity와 sector flash 성공을 대체하지 않는다. 자동 unlock·recover·mass erase는
안전 계약상 실행하지 않았으며 W03·W04 기능 HIL을 PASS로 올리지 않았다.

## 2. W03 software 결과

- 공개 timing·feature API와 Arduino 예제 11개를 구현했다.
- M32 Arduino smoke 17/17, Host 38 test·1 skip·17 subtest, timing contract target build가 PASS했다.
- 장비 중단 전 개발용 RF에서 2,000/2,000 packet, Subrating·Shorter Interval 역할별 20/20,
  Frame Space local 20회·peer 변경 2회, feature getter 20회를 관측했다.
- 위 RF 관측은 exact identity·sector flash·STOP을 같은 attempt에 묶지 못했으므로 개발 참고이며
  `M32-SUB-01`·`M32-SCA-01`·`M32-TIME-01`·`M32-FEAT-01` PASS가 아니다.

## 3. W04 software와 build 결과

구현 commit에서 Multiple Advertising Sets, multiple periodic sync, identity/list, directed advertising,
EAD, coding selection, scan while initiating와 ARF-01 자원 preset을 추가했다.

| 검증 | 결과 |
| --- | --- |
| Host 회귀 | **21 test PASS** |
| 공개 Arduino W04 예제 | **12/12 PASS** |
| 광고 contract | PASS — RAM 62,388 B / RRAM 230,544 B |
| scan/initiate contract | PASS — RAM 46,636 B / RRAM 139,240 B |
| `ble_c1p1` | PASS — RAM 65,280 B / RRAM 226,048 B |
| `ble_c2p0` | PASS — RAM 60,344 B / RRAM 218,716 B |
| `ble_c0p2` | PASS — RAM 61,248 B / RRAM 207,276 B |
| M28 extended/periodic/PAwR 회귀 build | PASS — 3/3 |

EAD Host negative는 변조 tag·잘못된 key/IV·randomizer replay를 거부하고 임시 key/plaintext 제거 경로를
검사한다. Generation handle과 자원 초과·잘못된 identity/SID·중복 자원 수명주기도 Host에서 검사했다.
Build 성공은 수신 packet, identity 격리, directed 재연결 또는 EAD RF 교환을 증명하지 않는다.

## 4. Readiness 반영

- W03·W04 작업 상태는 `in_progress`, `exact_evidence`는 `null`이다.
- W04의 여덟 capability는 `nu54dk_native_build`와 `arduino_build`만 구현 commit에 대해 PASS다.
- `runtime_capability`, `functional_hil`, `external_peer_interop`는 `NOT_RUN`을 유지한다.
- W04 build matrix 5개와 세 자원 profile 실측값만 갱신한다.
- `M32-ADV-01`, `M32-PRIV-01`, `M32-EAD-01`은 exact HIL 재개 전까지 `NOT_RUN`이다.

## 5. 재개 조건

DP/AP access가 복구된 probe에서 SHA-256 identity와 serial role을 다시 고정하고,
`auto_unlock=false` sector flash, image/source hash, bounded UART transcript와 역할별 STOP을 같은 attempt에
수집한다. 복구 과정에서도 자동 unlock·recover·mass erase는 사용하지 않는다. 이 조건을 만족하기 전에는
W03 또는 W04를 완료 처리하지 않으며, 독립적인 W05 이후 software/build 작업은 계속 진행할 수 있다.
