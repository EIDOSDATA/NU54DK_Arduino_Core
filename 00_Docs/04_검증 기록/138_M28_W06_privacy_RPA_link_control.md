# 138 — M28-W06 privacy·RPA·link control

## 결론

M28-W06의 Host·target 범위를 완료했다. RPA timeout·만료 event, 연결 설정 주소와 해석된 identity,
link별 actual parameter·DLE·remote-info를 generation handle에 결합했다. 이전 connection pointer의
늦은 callback은 재사용된 slot이나 현재 link에 전달하지 않는다.

이 PASS는 production source의 Host 수명 계약과 고정 NCS target compile/link에 적용한다. 실제
RPA 회전·bond reconnect와 동시 2-link control은 W07 전까지 `NOT RUN`이다.

## 구현·검증 결과

| 항목 | 결과 |
| --- | --- |
| Privacy | runtime RPA timeout 1~3600초, extended set별 만료 event·session count |
| Identity | 실제 connection remote 주소와 해석된 peer identity 분리, stale callback 거부 |
| Link control | handle별 actual parameter, PHY, DLE 요청·송수신 값, TX power |
| Remote info | LL version·manufacturer·subversion·8-byte LE feature 값 복사 |
| Host | `per_link_control`, `identity_resolution`, `stale_callback`, `privacy_rotation`, `extended_incoming` 5개와 정적 계약 PASS |
| Target | `nucode.m28.privacy_control` 1/1 build-only PASS, warning 0, 68.58초 |
| 예제 | `PrivacyPeripheral`, `PerLinkControl` |

Target build는 NCS `99553055607b2e9885fbc80ccd11fa9da81c2df0`, Zephyr
`bf801e4e3d19e1ffa76164346480cb7734dd2800`, board
`fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3`, toolchain bundle `dcbdc366a1` 조건에서 수행했다.

첫 두 target 시도는 같은 CRACEN object가 archive 직전에 없는 Windows 경로 길이 오류로 실패했다.
기능 source를 바꾸지 않고 suite·CMake project 식별자만 줄인 뒤 새 짧은 output에서 동일 조건 1/1이
PASS했다. 이 환경 오류를 기능 PASS에 포함하거나 이유 없는 재시도로 숨기지 않는다.

## 다음 작업

M28-W07에서 2보드 `REG/ADV/PAWR/PRIV`를 먼저 실행한다. 3보드 확보 뒤에는 이 네 기능시험을
반복하지 않고 `LINK/PER/CTRL/SOAK`의 2-link 동시성·PAST·장시간 회수 조건만 실행한다.
