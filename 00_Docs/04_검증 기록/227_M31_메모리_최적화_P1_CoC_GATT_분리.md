# 227 — M31 메모리 최적화 P1 CoC/GATT 분리

## 1. 판정

2026-09-22 `ble-l2cap-coc-dual-role`을 범용 NUCODE GATT facade와 분리했다. 이 역할은 BLE 연결과
CoC 운용에 필요한 Zephyr ATT/GATT 기반을 그대로 유지하지만, 사용하지 않는
`CONFIG_NUCODE_BLE_GATT`, `CONFIG_BT_GATT_DYNAMIC_DB`, 범용 GATT source와 event queue/state는
선택하지 않는다.

이는 GATT 자체를 끈 변경이 아니다. Audio profile이나 CS RAS처럼 upstream GATT/ATT를 직접 쓰는
역할과 범용 `NUCODE_BLE_GATT` facade를 구분한 것이다. 기존 `standard`/`ble` full profile과
GATT/NUS 역할의 공개 API·capacity는 바꾸지 않았다.

## 2. 정적 RAM 전후 비교

동일 `p0_ble_l2cap` adaptive clean image에서 P0 기준과 비교했다.

| 항목 | P0 기준 | P1 분리 뒤 | 절감 |
| --- | ---: | ---: | ---: |
| 전체 정적 RAM | 91,037 B | 70,081 B | 20,956 B |
| GATT event queue | 17,664 B | 0 B | 17,664 B |
| GATT session state | 3,152 B | 0 B | 3,152 B |
| FLASH | 199,884 B | 192,564 B | 7,320 B |
| RAM headroom | 171,107 B | 192,063 B | +20,956 B |

나머지 140 B는 GATT facade에 딸린 소규모 상태와 정렬 차이다. CoC의 512-byte TX MTU,
2 connections, L2CAP event queue와 controller/Host buffer는 유지했다. 역할 RAM 상한은
93,000 B에서 72,000 B로 낮췄다.

## 3. 검증

| 검증 | 결과 |
| --- | --- |
| capability Host 계약 | 41 PASS |
| 초기 BLE 10역할 fresh clean build | 10/10 PASS, forbidden symbol 0 |
| CoC 역할 final config | `CONFIG_NUCODE_BLE_L2CAP=y`, 범용 GATT/dynamic DB 없음 |
| CoC 역할 source graph | `NUCODE_BLE_L2CAP.cpp` 유지, `NUCODE_BLE_GATT.cpp`·GATT object 없음 |
| 실제 공개 `L2capCocClient` adaptive clean compile | PASS, FLASH 213,424 B, RAM 82,068 B |
| 물리 HIL | NOT RUN — P1 정적 source/config 분리 범위 |

실제 예제 RAM은 sketch 전역 상태와 Serial/GAP scan 코드가 포함되므로 합성 역할 image의 상한과
직접 비교하지 않는다. 두 build 모두 같은 역할 선언으로 범용 GATT facade가 제외되는 것은 확인했다.

## 4. 회귀 경계와 다음 작업

adaptive BLE smoke는 CoC-only 역할에 범용 GATT Kconfig나 source가 다시 들어오면 실패한다.
GATT를 사용하는 `ble-gatt-nus-dual-role`의 16-depth event queue와 server/client state는 그대로
유지했다. queue payload를 shared pool로 바꾸거나 depth를 줄이는 작업은 callback 완료·취소,
disconnect, stale completion, 고갈/backpressure의 실제 수명 검증 없이 적용하지 않는다.

다음 P1 단위는 범용 GATT를 실제 사용하는 역할에서 local server와 client/discovery 저장소가
역할·capacity에 맞게 분리 가능한지 확인하는 것이다. 동적 high-water에 의존하는 pool/stack 조정은
P2 경계로 유지한다.
