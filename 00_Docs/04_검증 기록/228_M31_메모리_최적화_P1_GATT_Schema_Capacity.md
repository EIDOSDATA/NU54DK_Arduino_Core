# 228 — M31 메모리 최적화 P1 GATT Schema Capacity

## 1. 판정

2026-09-23 adaptive 공개 build declaration에 `ble.gatt-services`와
`ble.gatt-characteristics-per-service` capacity를 추가하고, 생성된 Kconfig가 범용 GATT server의
실제 고정 배열 크기를 결정하도록 연결했다. `ServiceSlot`의 characteristic UUID, descriptor UUID,
attribute, CCC, notification, indication과 index 배열은 모두 같은 검증값을 사용한다.

두 capacity는 각각 1~8 범위이고 aggregation은 `maximum`이다. 여러 선언이 합쳐질 때 가장 큰
요구를 보존한다. 선언이 없으면 Kconfig의 기존 4 services, service별 8 characteristics 기본값을
유지하므로 `standard`/`ble` full profile과 기존 공개 최대 범위를 축소하지 않는다. lean image에서
등록 수가 선언값을 넘으면 기존 schema 등록 경로가 명시적으로 실패한다.

## 2. 동일 GATT server fixture 전후 비교

P0의 역할 source 포함만 확인하던 fixture를 실제 1-service/1-characteristic 등록 fixture로 강화했다.
동일 Sketch를 기존 4×8 내부 배열과 새 1×1 배열로 각각 clean build해 비교했다.

| 항목 | 기존 4×8 | capacity 1×1 | 절감 |
| --- | ---: | ---: | ---: |
| 전체 정적 RAM | 113,218 B | 69,426 B | 43,792 B |
| GATT `slots` | 45,248 B | 1,468 B | 43,780 B |
| RAM headroom | 148,926 B | 192,718 B | +43,792 B |
| FLASH | 194,100 B | 193,988 B | 112 B |

나머지 12 B 차이는 동일 compile/link에서 배열 축소에 따라 달라진 정렬·보조 상태다. GATT event
queue 8,832 B와 두 client context 3,152 B는 유지했다. callback payload 수명과 2-link 동시 client
계약을 측정 없이 줄이지 않았다. 실제 server fixture의 RAM 상한은 71,000 B로 고정했다.

## 3. 공개 예제와 회귀

| 검증 | 결과 |
| --- | --- |
| capacity resolver Host 계약 | 42 PASS |
| M13 profile/sidecar 계약 | 15 PASS, 1 skip |
| M20 GATT API·수명 계약 | 6 PASS |
| 전체 Host gate | PASS |
| 초기 BLE 10역할 fresh clean build | 10/10 PASS, RAM ceiling·forbidden symbol PASS |
| 실제 `CustomGattPeripheral` adaptive clean compile | PASS, FLASH 200,336 B, RAM 69,607 B |
| 실제 `CustomGattCentral` adaptive clean compile | PASS, FLASH 200,872 B, RAM 68,854 B |
| 물리 HIL | NOT RUN — P1 정적 배열/capacity 연결 범위 |

Peripheral과 Central 예제의 sidecar에는 각각 1×1 schema capacity를 명시했다. Central은 local
server slot을 링크하지 않지만 같은 역할 선언의 상한을 결정적으로 유지한다. 최종 `.config`에는
두 Kconfig가 모두 1이고, resolved capability 문서에도 값과 생성 근거가 기록된다.

## 4. 남은 P1 경계

이번 변경은 service/characteristic 개수를 실제 배열에 연결한 것이며, 512-byte 최대 GATT payload,
16-depth event queue, 두 client context를 줄인 변경이 아니다. event record를 shared payload pool로
전환하려면 notification/indication 완료·취소, disconnect, stale callback, cross-link 데이터 격리,
고갈/backpressure와 해제 후 재시도를 먼저 검증해야 한다.

다음 단위는 GATT server-only/client-only 역할과 source/state 경계를 분리할 수 있는지 조사한다.
동적 queue/stack high-water에 의존하는 수치 조정은 P2로 유지한다.
