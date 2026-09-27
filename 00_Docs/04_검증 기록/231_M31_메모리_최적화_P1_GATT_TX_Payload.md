# 231 — M31 메모리 최적화 P1 GATT TX Payload

## 1. 판정

2026-09-23 adaptive build declaration에 `ble.gatt-tx-payload` capacity를 추가하고,
`CONFIG_NUCODE_BLE_GATT_TX_PAYLOAD_SIZE`가 GATT server notification·indication의 비동기
snapshot 배열 크기를 결정하도록 연결했다. 범위는 1~512 B, aggregation은 `maximum`이다.
선언이 없으면 기존 512 B를 유지하므로 `standard`/`ble` full profile과 공개 API 최대값은 줄지 않는다.

P0 GATT fixture와 `CustomGattPeripheral`·`CustomGattCentral`은 실제 characteristic payload에 맞춰
64 B를 선언한다. 이 capacity는 characteristic cached value의 공개 최대값을 바꾸지 않으며,
server가 한 번의 notification 또는 indication으로 보낼 수 있는 snapshot 상한만 정한다.

## 2. 동일 1×1/1-link GATT fixture 비교

| 항목 | 512 B TX payload | 64 B TX payload | 절감 |
| --- | ---: | ---: | ---: |
| 전체 정적 RAM | 60,682 B | 59,786 B | 896 B |
| GATT service slot | 1,468 B | 572 B | 896 B |
| RAM headroom | 201,462 B | 202,358 B | +896 B |
| FLASH | 192,252 B | 192,248 B | 4 B |

characteristic 하나에 notification과 indication snapshot을 각각 하나씩 보존하므로
`(512-64)×2=896 B`가 감소했다. GATT role RAM 상한은 62,000 B에서 61,000 B로 낮췄고,
resource audit에서 service slot symbol 572 B를 정확히 검사한다.

## 3. 무절단 전송 경계

- cached value 길이 확인과 snapshot 복사를 같은 spinlock 임계구역에서 수행한다.
- 전체 길이가 선언 TX payload보다 크면 일부만 복사하거나 전송하지 않고 `value_overflow`와
  `-EMSGSIZE`로 notification/indication을 모두 거부한다.
- 실패 시 active token과 connection reference를 원복해 다음 정상 전송을 막지 않는다.
- 전송을 시작한 뒤에는 기존 snapshot·generation·completion/destroy 수명을 그대로 유지한다.
- 512 B 기본 Host build와 별도의 64 B bounded Host build를 모두 실행해 기본 호환과 초과 거부를
  각각 확인했다.

## 4. 회귀

| 검증 | 결과 |
| --- | --- |
| capacity resolver·정적 fail-closed 계약·GATT Host 대상 | 57 PASS |
| R12 기본 512 B GATT lifecycle | 24 scenario PASS |
| R12 64 B TX 초과 notification/indication | PASS |
| 전체 Host gate | 1,479 PASS, 2 skip |
| Markdown UTF-8·저장소 내부 link gate | 386 PASS |
| 초기 BLE 10역할 fresh clean build | 10/10 PASS |
| adaptive GATT final Kconfig·61,000 B ceiling·572 B slot symbol | PASS |
| 실제 `CustomGattPeripheral` adaptive clean compile | PASS, FLASH 198,648 B, RAM 59,967 B |
| 실제 `CustomGattCentral` adaptive clean compile | PASS, FLASH 199,116 B, RAM 59,214 B |
| 물리 HIL | NOT RUN — compile-time snapshot 용량과 Host 비동기 수명 경계 범위 |

## 5. 남은 P1 경계

이번 변경은 characteristic마다 존재하는 두 snapshot의 크기를 선언값에 맞췄다. 여러
characteristic이 같은 시점에 전송되지 않는다는 가정으로 배열 자체를 shared pool로 합치지는 않았다.
그 작업은 동시 notification/indication, pool 고갈 후 재시도, 완료·취소·disconnect·stale callback과
cross-link 격리 계약을 먼저 고정한 뒤 판단한다. server-only/client-only source/state 분리 조사도 계속한다.
