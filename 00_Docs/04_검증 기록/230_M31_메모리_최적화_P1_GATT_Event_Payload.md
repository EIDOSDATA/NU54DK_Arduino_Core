# 230 — M31 메모리 최적화 P1 GATT Event Payload

## 1. 판정

2026-09-23 adaptive build declaration에 `ble.gatt-event-payload` capacity를 추가하고,
`CONFIG_NUCODE_BLE_GATT_EVENT_PAYLOAD_SIZE`가 deferred GATT event record의 실제 data 배열 크기를
결정하도록 연결했다. 범위는 1~512 B, aggregation은 `maximum`이다. 선언이 없으면 기존 공개 최대
512 B를 유지하므로 `standard`/`ble` full profile과 기존 API 최대값을 축소하지 않는다.

이 capacity는 characteristic의 공개 cached value 최대값을 바꾸는 항목이 아니다. Zephyr callback에서
`BLEDevice.poll()`로 복사해 사용자 callback에 전달할 단일 event payload의 상한이다. 공개 예제와
P0 fixture는 실제 characteristic 용량에 맞춰 64 B를 선언했다.

## 2. 동일 1×1/1-link GATT fixture 비교

| 항목 | 512 B event payload | 64 B event payload | 절감 |
| --- | ---: | ---: | ---: |
| 전체 정적 RAM | 67,850 B | 60,682 B | 7,168 B |
| GATT event queue | 8,832 B | 1,664 B | 7,168 B |
| RAM headroom | 194,294 B | 201,462 B | +7,168 B |
| FLASH | 192,256 B | 192,252 B | 4 B |

queue depth 16은 유지했다. record 하나가 552 B에서 104 B로 줄어 448×16=7,168 B가 감소했다.
GATT role RAM 상한은 69,000 B에서 62,000 B로 낮췄고 resource audit에서 queue symbol 1,664 B를
정확히 검사한다.

## 3. 초과 입력 경계

- server characteristic/descriptor write가 선언 payload보다 크면 cached value를 바꾸기 전에
  `BT_ATT_ERR_INVALID_ATTRIBUTE_LEN`으로 거부한다.
- client long read 완료 payload가 선언값보다 크면 `value_overflow`와 operation-failed event로
  종료한다. silent truncation은 허용하지 않는다.
- client notification/indication enqueue가 용량 초과 또는 queue 포화로 실패하면 subscription
  token을 지우고 `BT_GATT_ITER_STOP`으로 중단한다.
- 512 B full/Host 경로의 두-link long read와 기존 callback 수명은 그대로 유지한다.

## 4. 회귀

| 검증 | 결과 |
| --- | --- |
| capacity resolver + M29 payload fail-closed 계약 | 49 PASS |
| R12 실제 512 B GATT lifecycle Host fixture | 24 scenario PASS |
| 전체 Host gate | PASS |
| 초기 BLE 10역할 fresh clean build | 10/10 PASS |
| adaptive GATT final Kconfig·RAM ceiling·queue symbol | PASS |
| 실제 `CustomGattPeripheral` adaptive clean compile | PASS, FLASH 198,600 B, RAM 60,863 B |
| 실제 `CustomGattCentral` adaptive clean compile | PASS, FLASH 199,124 B, RAM 60,110 B |
| 물리 HIL | NOT RUN — compile-time queue capacity와 초과 입력 경계 범위 |

## 5. 남은 P1 경계

이번 변경은 callback event queue의 복사 payload만 right-size했다. characteristic별 notification과
indication TX snapshot은 여전히 service slot 안에서 각각 공개 최대 512 B를 예약한다. 이를 shared
TX pool로 바꾸려면 전송 완료·취소·disconnect·stale callback·cross-link 격리와 고갈 후 재시도
계약을 먼저 갖춰야 한다. server-only/client-only source/state 분리 조사도 계속한다.
