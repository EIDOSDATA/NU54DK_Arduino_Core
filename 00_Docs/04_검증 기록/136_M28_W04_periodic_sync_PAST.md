# 136 — M28-W04 periodic sync·PAST

## 결론

M28-W04의 Host·target 범위를 완료했다. Extended advertising set 하나에 periodic advertiser를
결합하고, 수신 측은 generation 기반 고정 sync slot 하나와 255-byte report queue를 사용한다.
PAST 송·수신 API는 W02의 현재 connection handle을 요구한다.

이 PASS는 production source의 Host 수명 계약과 고정 NCS target compile/link에 적용한다. 실제
periodic RF report와 3-node PAST `M28-PER-01`은 W07 전까지 `NOT RUN`이다.

## 구현·검증 결과

| 항목 | 결과 |
| --- | --- |
| Advertiser | extended set 1개 결합, interval·TX power·ADI, raw AD 255 byte |
| Sync | generation handle 1개, pending/synchronized/delete/terminate/end 경계 |
| Report | 주소·SID·TX power·RSSI·255-byte payload, 고정 queue 8개 |
| PAST | current link별 sync/set transfer, subscribe/unsubscribe, 비구독 callback 거부 |
| Host | `advertiser`, `sync_report`, `past`, `end_cleanup` 4개 시나리오와 정적 계약 PASS |
| Target | `nucode.m28.ble_periodic_contract` 1/1 build-only PASS, warning 0, 61.65초 |
| 예제 | `PeriodicAdvertiser`, `PeriodicScanner` |

Target build는 NCS `99553055607b2e9885fbc80ccd11fa9da81c2df0`, Zephyr
`bf801e4e3d19e1ffa76164346480cb7734dd2800`, board
`fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3`, toolchain bundle `dcbdc366a1` 조건에서 수행했다.

Host 실행 중 Windows Application Control이 새 임시 실행 파일을 `WinError 4551`로 잠시 차단한
실패는 compile 또는 BLE assertion 실패가 아니다. 제한된 재실행에서 같은 source·scenario가
통과했으며, 이 환경 오류를 기능 PASS로 세거나 무한 재시도로 숨기지 않았다.

## 다음 작업

M28-W05 PAwR advertiser/scanner의 4 subevent × 4 response slot 고정 buffer, request/response window,
queue overflow와 stop/end 회수 경계를 Host → target 순서로 구현한다. 두 보드 RF는 W07의
`M28-PAWR-01`에서 한 번만 판정한다.
