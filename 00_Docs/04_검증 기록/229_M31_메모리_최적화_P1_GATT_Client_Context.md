# 229 — M31 메모리 최적화 P1 GATT Client Context

## 1. 판정

2026-09-23 GATT client의 고정 `ClientState` 개수를 실제 `CONFIG_BT_MAX_CONN`과 공개 2-link
상한 중 작은 값으로 결정하도록 변경했다. adaptive `ble-gatt-nus-dual-role`은
`ble.connections=1`을 선언하므로 context 하나만 예약한다. `standard`/`ble` full profile의
`CONFIG_BT_MAX_CONN=2`와 Host의 2-link fixture는 기존 두 context를 유지한다.

이 변경은 connection slot, callback, handle generation, read/write/subscribe 수명을 공유하지 않는다.
동시에 존재할 수 없는 두 번째 client state만 제거한다. 연결 상한이 0인 잘못된 구성은 compile-time
`static_assert`로 거부한다.

## 2. 동일 1×1 GATT server fixture 비교

| 항목 | 기존 2 context | 연결 상한 기반 1 context | 절감 |
| --- | ---: | ---: | ---: |
| 전체 정적 RAM | 69,426 B | 67,850 B | 1,576 B |
| GATT `states` | 3,152 B | 1,576 B | 1,576 B |
| RAM headroom | 192,718 B | 194,294 B | +1,576 B |
| FLASH | 193,988 B | 192,256 B | 1,732 B |

FLASH 감소는 단일 배열 원소가 확정되면서 두 context 탐색 경로가 compile-time으로 단순화된 결과다.
GATT role RAM 상한은 71,000 B에서 69,000 B로 낮췄다. clean build의 resource audit에서
`CONFIG_BT_MAX_CONN=1`, 전체 RAM 67,850 B, `states` symbol 1,576 B를 함께 확인한다.

## 3. 회귀

| 검증 | 결과 |
| --- | --- |
| M29 2-link long-read 정적 계약 | 6 PASS |
| R12 실제 GATT lifecycle Host fixture | 24 scenario PASS |
| 전체 Host gate | PASS |
| 초기 BLE 10역할 fresh clean build | 10/10 PASS |
| adaptive GATT final Kconfig·RAM ceiling·ELF state symbol gate | PASS |
| 실제 `CustomGattPeripheral` adaptive clean compile | PASS, FLASH 198,604 B, RAM 68,031 B |
| 실제 `CustomGattCentral` adaptive clean compile | PASS, FLASH 199,088 B, RAM 67,278 B |
| 물리 HIL | NOT RUN — 연결 상한과 compile-time 배열 정합 범위 |

Host fixture는 `CONFIG_BT_MAX_CONN`을 별도로 정의하지 않아 공개 2-link 호환 기본값을 사용하고,
두 link의 long read를 교차 실행한다. 따라서 adaptive 1-link 절감이 2-link full 계약을 축소하지
않는다는 회귀를 함께 고정한다.

## 4. 남은 P1 경계

GATT event queue 8,832 B와 최대 512-byte payload 수명은 변경하지 않았다. 다음 단위에서는
server-only/client-only 역할 및 source/state 경계를 먼저 분리할 수 있는지 조사한다. payload를
shared pool로 바꾸는 작업은 완료·취소·disconnect·stale callback·cross-link 격리와 고갈 후 재시도
계약이 준비된 뒤에만 진행한다.
