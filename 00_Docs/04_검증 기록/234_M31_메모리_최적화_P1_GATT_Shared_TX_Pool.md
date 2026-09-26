# 234 — M31 메모리 최적화 P1 GATT shared TX pool

## 1. 판정

2026-09-23 generic GATT server의 characteristic별 notification/indication 전송 저장소를
bounded shared TX pool로 옮겼다. `ble.gatt-tx-contexts` 선언은 1~128개를 허용하고
`CONFIG_NUCODE_BLE_GATT_TX_CONTEXT_COUNT`에 연결된다. 선언하지 않은 호환 구성은
기존 4 service × 8 characteristic × notification/indication 두 방향의 최대 동시 수인
64개를 기본값으로 유지한다. 적은 동시 전송만 필요한 adaptive image는 필요한 수를 직접
선언한다. `CustomGattPeripheral`과 P0 server fixture는 1개를 선언한다.

각 context는 characteristic·native connection·session generation·전송 종류,
indication parameter와 최대 payload snapshot을 함께 소유한다. 같은 characteristic의 같은
전송 종류를 중복 시작하거나 pool이 소진되면 `busy`로 거부한다. cached value가 선언
payload 또는 MTU를 넘으면 잘라 보내지 않고 `value_overflow`로 거부한다. 예약과 해제는
TX spinlock으로 보호하며 동적 할당은 없다.

## 2. 비동기 수명

| 경계 | context 반환 시점 | 이벤트 처리 |
| --- | --- | --- |
| notification | Zephyr 전송 완료 callback | 같은 native connection과 generation이 활성일 때만 `notification_sent` |
| indication | confirmation callback 이후 Zephyr `destroy` callback | 같은 native connection과 generation이 활성일 때만 confirmed/failed |
| 시작 전 오류·driver 오류 | 호출 실패 즉시 | 명시적 `not_connected`·`value_overflow`·`driver_error` |
| disconnect·session end | stack이 보유한 callback 수명이 끝난 뒤 | 오래된 connection/generation 이벤트는 버림 |

Zephyr v3.4.0 고정 SDK의 `gatt_indicate_rsp()`는 application `func`를 호출한 뒤
`_ref`를 감소시키고 마지막 참조에서 `destroy`를 호출한다. 그래서 confirmation만으로
snapshot을 재사용하지 않는다. callback 전의 disconnect나 session end에도 context를
즉시 덮어쓰지 않는다.

## 3. ELF/map 비교

| 대상 | 이전 RAM | shared pool RAM | RAM 절감 | 이전 FLASH | shared pool FLASH |
| --- | ---: | ---: | ---: | ---: | ---: |
| P0 1×1/1-link/64 B server fixture | 48,653 B | 48,581 B | 72 B | 131,048 B | 131,052 B |
| `CustomGattPeripheral` | 48,835 B | 48,763 B | 72 B | 137,672 B | 137,572 B |

fixture의 `ServiceSlot` symbol은 572→392 B가 됐다. 별도 server state symbol은
1개 TX context를 포함해 144 B다. event queue는 1,664 B로 유지한다. RAM 상한은
50,000 B를 유지한다. 동일 fixture가 characteristic 1개만 보유하므로 절감량은
72 B이며, 여러 characteristic에 비해 동시 전송 수가 적은 image에서 절감 폭이 커진다.

## 4. 검증

| 검증 | 결과 |
| --- | --- |
| Host R12 GATT 수명·1-context pool 고갈/해제 후 재시도 | PASS |
| Host R12 2-context 병렬 전송·서로 다른 characteristic snapshot 격리 | PASS |
| 1-context에서 indication confirmation 뒤 `destroy` 전 재사용 금지 | PASS |
| adaptive BLE 초기 10역할 fresh build·최종 Kconfig·source/ELF | 10/10 PASS |
| 실제 `CustomGattPeripheral` adaptive compile | PASS, FLASH 137,572 B, RAM 48,763 B |
| 기존 full 호환 `CustomGattPeripheral` compile | PASS, 기본 TX context 64개, FLASH 348,228 B, RAM 155,716 B |
| 전체 Host gate | PASS, 1,480건 실행(2 skip) |
| Markdown UTF-8·저장소 내부 link gate | PASS, 389개 문서 |
| 물리 HIL | NOT RUN — compile-time 저장소와 Host callback 수명 범위 |

## 5. 다음 경계

P1의 나머지 고정 저장소와 다른 full 호환 image를 검토한다. runtime high-water와 controller
pool·thread stack 조정은 P2의 실물 부하 계측을 거쳐 판정한다.
