# 235 — M31 메모리 최적화 P1 GATT client payload buffer

## 1. 범위와 계약

GATT client는 연결별 `read_data`와 `write_data`를 각각 공개 API 최대값인 512 B로
예약했다. adaptive image에서는 `ble.gatt-event-payload`와 `ble.gatt-tx-payload`를
선언해도 이 두 버퍼가 줄지 않았다. 이번 변경은 read 누적 버퍼를 event payload,
write snapshot을 TX payload 선언값에 연결한다. 선언하지 않은 full 호환 image의
두 기본값은 그대로 512 B다.

긴 read의 다음 fragment가 선언값을 넘으면 누적 버퍼에 복사하기 전에
`value_overflow`로 실패하고 완료 이벤트를 내지 않는다. write request, write command,
signed write도 전송 버퍼에 복사하기 전에 선언값 초과를 거부한다. ATT MTU, 서명
overhead, 기존 연결·bearer·비동기 완료 규칙은 별도로 유지한다.

## 2. 검증 진행

같은 `CustomGattCentral` adaptive image에서 RAM은 53,478→52,582 B로 896 B,
FLASH는 150,036→149,136 B로 900 B 줄었다. client `states` symbol은
1,576→680 B다. event queue는 1,536 B로 유지된다. 최종 설정은 두 payload 모두
64 B이며, server 전용 source와 slot은 포함하지 않는다.

| 검증 | 결과 |
| --- | --- |
| Host 64 B read·write 경계와 초과 거부 | PASS |
| Host signed write 64 B 경계와 초과 거부 | PASS |
| 실제 `CustomGattCentral` adaptive compile·ELF/map | PASS, FLASH 149,136 B, RAM 52,582 B, `states` 680 B |
| 기존 full 호환 `CustomGattCentral` compile | PASS, 기본 read/TX payload 각 512 B, FLASH 348,280 B, RAM 154,975 B |
| BLE 10역할 adaptive fresh build | 10/10 PASS |
| 전체 Host suite | PASS, 1,480건 실행(2 skip) |
| 문서 UTF-8·내부 link gate | PASS, 390개 문서 |
| 물리 HIL | NOT RUN — payload 저장소 크기와 Host 경계 검증 범위 |

## 3. 다음 경계

실제 RAM 차이는 같은 Central image 전후로 비교했다. 다른 고정 저장소는
역할·부하별 필요량과 기본 full 호환 계약을 확인한 다음 별도 묶음으로 판정한다.
현재 Central image의 scan result queue는 2,496 B, GATT event queue는 1,536 B,
Core/GAP event queue는 960 B다. scan/event depth를 더 낮추면 burst 중 결과를
잃을 수 있으므로, 정적 숫자만 보고 줄이지 않고 P2 실제 부하·overflow 계측과
연결해 판정한다. 8,192 B `malloc_arena`와 main stack, 4,164 B system heap,
controller·BT stack 역시 같은 P2 계측 경계다.
