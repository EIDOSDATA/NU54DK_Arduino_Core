# M24 Fixture 203 SPI 실기 검증

| 항목 | 내용 |
| --- | --- |
| 기록 ID | VALIDATION-M24-SPI-FIXTURE-049 |
| 실행일 | 2026-09-06 |
| 상태 | **Fixture 203 PASS — M24 전체는 진행 중** |
| exact core | `4af93daa542b4b84e39381317d4747b3df3ff5c8` |
| board gitlink | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` |
| DUT / peer | D 드라이브 / E 드라이브로 사용자가 확정한 두 NU54DK |
| 검증 범위 | P1↔P1 route의 SPIM/SPIS20·21·22 전 조합, SPI 2/4/8 MHz, Mode 0~3, MSB/LSB, EasyDMA |
| 아직 아닌 것 | TWI 301, analog·stream, 전체 동시성·soak, M24/M25 완료 또는 `v0.4.0` 공개 승인 |

## 1. 확정 결선과 실행 조건

사용자가 [수기 확정 핀맵](<../01_아두이노 코어 설계/13_NU54DK_P2_P4_커넥터_핀맵.md>)과
fixture catalog에 따라 다음 결선을 완료했다. 보드 A는 DUT, 보드 B는 peer다.

| 신호 | 보드 A(DUT) | 보드 B(peer) |
| --- | --- | --- |
| SCK | P2-12 / P1.04 | P2-12 / P1.04 |
| MOSI | P2-11 / P1.05 | P2-11 / P1.05 |
| MISO | P2-10 / P1.06 | P2-10 / P1.06 |
| CSN | P2-9 / P1.07 | P2-9 / P1.07 |
| 기준 전위 | P2-30 / GND | P2-30 / GND |

두 보드의 `DISABLE_UART`는 DAP UART 분리 상태, `DISABLE_SWD`는 SWD 연결 상태로
두었다. 외부 pull-up과 보드 간 전원 rail은 연결하지 않았다. Controller/peripheral 역할을
바꾸어도 MOSI끼리, MISO끼리 연결하며 각 transaction의 SCK·CSN 출력은 controller 한 대만
소유했다.

Confirmation은 fixture catalog 개정, 두 UID hash, exact role image hash, 공통 GND·동일 I/O
전압·스위치·출력 충돌 금지 조건에 묶었다. Fixture 202의 confirmation이나 image를 재사용하지
않고 exact `4af93da`에 새 confirmation을 만들었다.

## 2. 준비와 실행

고정 Nordic Toolchain Python과 `C:/ncs/toolchains/dcbdc366a1/opt/zephyr-sdk`를 명시해
role image 2/2를 warning 없이 84.80초에 build-only PASS했다. 두 role image는
CMSIS-DAP/SWD 10 MHz로 sector erase·flash했다. Role 1은 3.188초, role 2는 3.063초였고
`auto_unlock=false`를 유지했다. Mass erase와 recover는 요청하지 않았다.

Mailbox polling은 1 ms 간격을 사용했으며 timeout·nonce·commit marker·poison 계약은
바꾸지 않았다. 실행 중 source와 image를 변경하거나 중단된 결과를 재사용하지 않았다.

## 3. 전체 실행 결과

| 항목 | 결과 |
| --- | --- |
| campaign | 1회 연속 완료, 3,306.922초(55분 6.922초) |
| SPI data 결과 | **27,234 PASS** |
| cancel·bounded STOP 예상 오류 | **18 PASS** |
| fixture cleanup | **2 PASS** |
| campaign 기록 | progress 1건, complete 1건 |
| 총 evidence result | **27,256**, 실패 0건 |
| plan 대조 | 계획 ID 27,252 / 실제 고유 SPI ID 27,252 / 중복 0 / 누락 0 / 범위 이탈 0 |
| SPI 속도·mode·order | 2/4/8 MHz, Mode 0~3, MSB/LSB first |
| payload | 1, 2, 31, 32, 255, 256, 1,024 byte |
| 전송 방향 | controller→peripheral, peripheral→controller, full duplex; 반대 방향 ORC도 전 byte 비교 |
| DMA | sync, async 단일 buffer, async 이중 buffer, buffer handover, cancel·STOP·recovery |
| instance 조합 | role 1·2 controller × 양쪽 SPIM/SPIS20·21·22, 총 18개 방향·instance 조합 |

최종 JSON의 `status`는 `passed`다. SPI 계획 record 27,252건은 모두 `passed`이고 나머지는
cleanup·progress metadata다. Data 불일치, DMA amount·guard 손상, event queue overflow,
mailbox timeout, STOP 미증명 또는 probe 이탈은 없었다. 공통 runner의 종료 문자열에 남은
`forced-error modes remain NOT RUN` 문구는 고정된 과거 요약이다. 실제 cancel·bounded STOP
18건의 실행 여부와 PASS는 `V04-SPI-EXPECTED-ERROR` evidence ID로 판정했다.

## 4. 증거

| 파일 | 크기 | SHA-256 |
| --- | ---: | --- |
| [전체 JSON](evidence/4af93da/fixture203-full-10mhz-4af93da.json) | 23,742,060 byte | `b239cc82e35a43fe578ea457ad61def691aa9a412ec6288c66d1b87f2aec26a7` |
| [append-only journal](evidence/4af93da/fixture203-full-10mhz-4af93da.json.jsonl) | 12,759,935 byte | `32e5624e47094166d2a9cabfc514e807a3d417eab2b0d805dd342883e492d186` |

Evidence에는 raw UID를 넣지 않고 role별 UID SHA-256, image identity, confirmation hash,
fixture catalog hash, SWD 설정과 flash 결과를 보존했다.

## 5. 판정과 다음 단계

Fixture 203의 P1↔P1 route에서 SPIM/SPIS20·21·22 전 조합의 양방향 data path, EasyDMA,
SPI mode·bit order, ORC, 단일/이중 buffer handover와 cancel 뒤 정상 재시작은 기능 PASS다.
Fixture 201~203을 합쳐 계획된 세 SPI route fixture가 모두 통과했다. 이 결과는 전기 파형
품질, 임의 핀 route 또는 외부 SPI 부품 호환성의 보증은 아니다.

M24 통신 인스턴스 기능 검증의 다음 물리 작업은 Fixture 301 TWI다. Fixture 203 점퍼를
그대로 사용하지 않는다. USB 전원을 분리하고 TWI 301 결선과 VDD_MOD 기준 pull-up을 적용한
뒤 새 confirmation으로 실행해야 한다. TWI 301이 끝나기 전에는 T11 또는 M24 전체를 완료로
바꾸지 않는다.
