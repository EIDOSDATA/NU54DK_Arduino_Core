# 137 — M28-W05 PAwR advertiser·scanner

## 결론

M28-W05의 Host·target 범위를 완료했다. PAwR advertiser와 scanner는 고정 4 subevent × 4 response
slot, 249-byte payload와 8-entry response queue를 사용한다. 잘못된 subevent·slot·offset·길이는
controller에 전달하기 전에 거부하고, stop·delete·end 뒤의 이전 callback은 새 generation에 전달하지
않는다.

이 PASS는 production source의 Host 수명 계약과 고정 NCS target compile/link에 적용한다. 실제
PAwR RF `M28-PAWR-01`은 W07 전까지 `NOT RUN`이다.

## 구현·검증 결과

| 항목 | 결과 |
| --- | --- |
| Advertiser | 4 subevent, 4 response slot, request event와 subevent data 249 byte |
| Scanner | 현재 periodic sync generation에 response 결합, 범위 밖 window 거부 |
| Response | advertiser 수신 payload 249 byte, 고정 queue 8개, overflow 계수 |
| Host | `advertiser_request`, `advertiser_response`, `scanner_response`, `invalid_window_end` 4개 시나리오와 정적 계약 PASS |
| Target | `nucode.m28.ble_pawr_contract` 1/1 build-only PASS, warning 0, 61.26초 |
| 예제 | `PawrAdvertiser`, `PawrScanner` |

Target build는 NCS `99553055607b2e9885fbc80ccd11fa9da81c2df0`, Zephyr
`bf801e4e3d19e1ffa76164346480cb7734dd2800`, board
`fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3`, toolchain bundle `dcbdc366a1` 조건에서 수행했다.

## 다음 작업

M28-W06 privacy·RPA와 DLE·remote-info를 포함한 link별 제어를 Host → target 순서로 구현한다.
두 보드 RF는 W07의 `M28-PAWR-01`에서 한 번만 판정하고 3보드 mixed-role 시험에서는 같은 PAwR
수신률을 반복하지 않는다.
