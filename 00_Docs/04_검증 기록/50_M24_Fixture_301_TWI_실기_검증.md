# M24 Fixture 301 TWI 실기 검증

| 항목 | 내용 |
| --- | --- |
| 기록 ID | VALIDATION-M24-TWI-FIXTURE-050 |
| 실행일 | 2026-09-06 |
| 상태 | **Fixture 301 PASS — T11 통신 인스턴스 단독 기능 검증 완료, M24 전체는 진행 중** |
| exact core | `e2f045c1b4272d986d17456c5af051fe8af74f19` |
| board gitlink | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` |
| DUT / peer | D 드라이브 / E 드라이브로 사용자가 확정한 두 NU54DK |
| 검증 범위 | P1↔P0 route의 TWIM/TWIS20·21·22·30 전 조합, 100/400/1,000 kHz, EasyDMA와 target 이중 buffer |
| 아직 아닌 것 | 더 넓은 최대 동시성·성능·soak, M25 analog·stream, M24/M25 전체 완료 또는 `v0.4.0` 공개 승인 |

## 1. 확정 결선과 실행 조건

사용자가 [수기 확정 핀맵](<../01_아두이노 코어 설계/13_NU54DK_P2_P4_커넥터_핀맵.md>)과
fixture catalog revision 2에 따라 다음 결선을 완료했다. 보드 A는 DUT, 보드 B는 peer다.

| 신호 | 보드 A(DUT) | 보드 B(peer) |
| --- | --- | --- |
| SDA | P2-12 / P1.04 | P2-25 / P0.00 |
| SCL | P2-11 / P1.05 | P2-26 / P0.01 |
| 기준 전위 | P2-30 / GND | P2-30 / GND |

두 보드의 `DISABLE_UART`는 DAP UART 분리 상태, `DISABLE_SWD`는 SWD 연결 상태로 두었다.
보드 사이에는 SDA·SCL·GND만 연결했다. 외부 pull-up 저항과 VDD_MOD를 포함한 전원 rail은
연결하지 않았으며 target 역할의 TWIS가 SDA/SCL 내부 pull-up을 활성화했다. Controller/target
역할은 자동으로 바뀌지만 두 보드가 동시에 SCL을 출력하는 transaction은 만들지 않았다.

Confirmation은 fixture catalog 개정, 두 UID hash, exact role image hash, 공통 GND·동일 I/O
전압·스위치·출력 충돌 금지와 내부 pull-up 조건에 묶었다. 실패한 이전 실행의 confirmation과
result는 재사용하지 않았고 USB 전원을 다시 인가한 뒤 exact `e2f045c`용 확인서를 새로 만들었다.

## 2. 선행 실패와 수정

첫 실행 exact `ddbe2aa`는 fixture catalog revision 1의 외부 2.2 kΩ pull-up 조건으로 승인됐지만
실제 결선에 해당 저항이 없었다. 330개 기능 record 뒤 clock-stretch에서 timeout이 발생했으므로
결선 계약 불일치로 무효화했으며 코어 FAIL이나 PASS로 사용하지 않았다.

Revision 2에서 target TWIS 내부 pull-up을 활성화한 exact `e25ebb0`은 같은 첫 instance 조합에서
regular 324건, NACK·cancel·stuck-SDA와 각 복구 6건을 통과했다. 그러나 buffer request 뒤
5 ms 지연 제공을 시험하는 clock-stretch에서 controller DMA가 완료되지 않았고 STOP도 증명하지
못했다. 자동 recover나 mass erase 없이 중단했다.

원인은 `TwisHandle::queueBuffers()`가 software buffer record만 채우고, 먼저 도착한
`NRFX_TWIS_EVT_READ_REQ`/`WRITE_REQ`가 clock을 stretch하는 동안 필요한
`nrfx_twis_tx_prepare()`/`nrfx_twis_rx_prepare()`를 호출하지 않은 것이었다. Exact `e2f045c`에서
pending request를 기록하고 같은 spinlock 아래 늦게 들어온 buffer를 nrfx에 제공해 DMA ownership으로
전환하도록 수정했다. 잘못된 방향, 취소·비활성화와 prepare 실패도 fail-closed로 처리하고 Host
회귀 시험과 clean role image 2/2 build를 통과시킨 뒤에만 실기를 재개했다.

## 3. 전체 실행 결과

| 항목 | 결과 |
| --- | --- |
| campaign | 1회 연속 완료, 158.953초 |
| TWI data 결과 | **1,968 PASS** |
| NACK·cancel와 bounded STOP 예상 오류 | **12 PASS** |
| stuck-SDA 실패·해제·bus recovery | **6 PASS** |
| fixture cleanup | **2/2 PASS**, 양쪽 disarm `[0]` |
| campaign 기록 | progress 1건, complete 1건 |
| 총 evidence result | **1,990**, 실패 0건 |
| plan 대조 | 계획 TWI record 1,986 / 실제 1,986 / 누락 0 / 범위 이탈 0 |
| TWI 속도 | 100/400/1,000 kHz |
| payload | 1, 2, 31, 32, 255, 256 byte |
| 전송 방향 | controller→target, target→controller, write-then-read |
| DMA | sync, async 단일·이중 buffer, target request/completion, clock-stretch 뒤 지연 buffer 제공 |
| 오류·복구 | 미등록 주소 NACK, 진행 중 cancel, SDA stuck-low 실패·해제·`recoverBus()`, 각 오류 뒤 정상 32-byte 재전송 |
| instance 조합 | role 1·2 controller × P1 TWIM/TWIS20·21·22 ↔ P0 TWIM/TWIS30, 총 6개 방향·instance 조합 |

각 instance 조합에는 328개 입력 vector가 있고 NACK·cancel·stuck-SDA 3개 vector가 복구 record를
하나씩 추가하므로 조합당 331개, 전체 1,986개 기능 record다. NACK와 cancel 뒤 정상 복구는 현재
runner에서 같은 논리 ID를 쓰므로 고유 문자열은 1,980개이고 의도된 반복 6건은 journal 순서와
서로 다른 seed로 구분된다. 이는 누락이나 실행 재시도가 아니며 전체 record 수와 순서를 계획과
대조했다. 같은 정리 변경에서 향후 실행의 recovery ID에 NACK·cancel 원인을 포함하도록 runner와
Host 회귀 시험을 교정했으며, 이미 생성된 exact evidence는 소급 수정하지 않는다.

최종 JSON의 `status`는 `passed`다. Payload/hash 불일치, DMA amount·guard 손상, event queue
overflow, mailbox timeout, STOP 미증명 또는 probe 이탈은 없었다. 1 MHz 결과는 이 결선에서의
기능 통과이며 rise-time, 신호 무결성이나 외부 I2C 부품 호환성 보증이 아니다.

## 4. 실행·증거 identity

CMSIS-DAP/SWD는 10 MHz로 설정했다. Role 1 flash는 4.453초, role 2는 4.078초였고
`mass_erase_requested=false`, `recover_requested=false`를 유지했다. Role image와 evidence에는
raw UID를 넣지 않고 SHA-256만 보존했다.

| 파일 | 크기 | SHA-256 |
| --- | ---: | --- |
| [전체 JSON](evidence/e2f045c/fixture301-full-10mhz-e2f045c.json) | 1,724,358 byte | `39a90ff35ff3287976d5623d0faa7af620675b4a7b789849315a8c15e64f2209` |
| [append-only journal](evidence/e2f045c/fixture301-full-10mhz-e2f045c.json.jsonl) | 925,411 byte | `f3902404de3f042f4d1774924df4bb8f83f922d9e225c19ee4fde03a8102e07a` |

## 5. 판정과 다음 단계

Fixture 301에서 TWIM/TWIS20·21·22·30의 양방향 data path, EasyDMA, 100/400/1,000 kHz,
단일·이중 buffer, target clock-stretch, NACK·cancel·stuck-SDA와 정상 복귀는 기능 PASS다.
Fixture 101~103 UART, 201~203 SPI와 합치면 T11이 요구한 23개 serial personality의 승인된
단독 통신 경로는 모두 actual HIL로 검증됐다.

이 판정은 고급 API의 stable 공개나 M24 전체 완료가 아니다. T13의 더 넓은 서로 다른 block
동시 실행, 충돌 negative 반복, 처리량·CPU·손실과 600/7,200초 soak가 남아 있다. 다음 순서는
T12 M25 합성 신호 기능 검증이며, 첫 결선은 Fixture 401의 PWM→AIN0 경로다.
