# M24 Fixture 201 SPI 실기 검증

| 항목 | 내용 |
| --- | --- |
| 기록 ID | VALIDATION-M24-SPI-FIXTURE-047 |
| 실행일 | 2026-09-05 |
| 상태 | **Fixture 201 PASS — M24 전체는 진행 중** |
| exact core | `f21377ee9bbfee35a05748d4e5ba3ab1fd6b79b9` |
| board gitlink | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` |
| DUT / peer | D 드라이브 / E 드라이브로 사용자가 확정한 두 NU54DK |
| 검증 범위 | P2↔P1 route의 SPIM/SPIS 00·20·21·22, SPI 2/4/8 MHz, Mode 0~3, MSB/LSB, EasyDMA |
| 아직 아닌 것 | SPIM/SPIS30·P0/P1 추가 route, TWI, analog·stream, 전체 동시성·soak, M24/M25 완료 또는 `v0.4.0` 공개 승인 |

## 1. 확정 결선과 실행 조건

사용자가 [수기 확정 핀맵](<../01_아두이노 코어 설계/13_NU54DK_P2_P4_커넥터_핀맵.md>)과
fixture catalog에 따라 다음 결선을 직접 확인했다. 보드 A는 DUT, 보드 B는 peer다.

| 신호 | 보드 A(DUT) | 보드 B(peer) |
| --- | --- | --- |
| SCK | P4-20 / P2.01 | P2-12 / P1.04 |
| A MOSI / A SPIS MISO | P4-21 / P2.02 | P2-11 / P1.05 |
| A MISO / A SPIS MOSI | P2-17 / P2.04 | P2-10 / P1.06 |
| CSN | P2-19 / P2.05 | P2-9 / P1.07 |
| 기준 전위 | P2-30 / GND | P2-30 / GND |

두 보드의 `DISABLE_UART`는 DAP UART 분리 상태, `DISABLE_SWD`는 SWD 연결 상태로
두었다. 외부 pull-up과 보드 간 전원 rail은 연결하지 않았다. DUT가 peripheral로
바뀐 때 P2 전용 MOSI/MISO 핀을 firmware가 교대하고, 매 transaction의 SCK·CSN
출력은 controller 한 대만 소유했다.

Confirmation은 fixture catalog 개정, 두 UID hash, exact role image hash, 공통 GND·동일 I/O
전압·스위치·출력 충돌 금지 조건에 묶었다. 새 source/image마다 새 confirmation을
사용했으며 이전 source의 PASS를 최종 결과에 재사용하지 않았다.

## 2. 8 MHz 한 bit 수신 지연 진단과 교정

초기 전체 실행은 SPIM20↔SPIS20의 8 MHz, Mode 0, MSB first, 1-byte
controller→peripheral vector에서 controller가 SPIS ORC `0x96`대신 `0x2D`를 수신했다.
SWD control을 1 MHz에서 10 MHz로 바꾸어도 같은 값이 재현됐으므로 SWD 속도가
원인은 아니었다. 하드웨어 CSN setup/hold를 최대 cycle로 늘린 `2a219a9`도 같은
결과였다.

ORC 계약만의 문제인지 분리하기 위해 peripheral에 실제 `0xD2` TX buffer를
제공했다. 교정 전 controller는 `0xA5`를 수신했다. 두 값은 각각 원래 byte를
한 bit 왼쪽으로 이동한 값이므로, 무 TX일 때의 ORC oracle가 아니라 SPIM20 수신
sample 시점을 원인으로 확정했다.

nRF54L15 MDK의 인스턴스 정의는 SPIM00을 128 MHz core/RXDELAY 2,
SPIM20/21/22/30을 16 MHz core/RXDELAY 1로 지정한다. 기존 adapter는 공통
NRFX 기본값 2를 전 인스턴스에 적용했다. SPIM20 계열에서 2 cycle은 125 ns로
8 MHz의 한 bit 길이와 같다. `a254d01`에서 SPIM00은 2, serial SPIM은 1을
사용하도록 교정했다.

교정 image에서 문제의 8 MHz vector를 실제 TX buffer와 ORC로 각각 100회
반복해 모두 PASS했다. 이후 exact `f21377e`의 전체 matrix로 다시 검증했다.

## 3. 10 MHz SWD 최적화와 전체 실행 결과

CMSIS-DAP/SWD control과 sector erase/flash를 모두 10 MHz로 실행했다. 이것은 SPI
SCK 속도와 독립적이며 SPI matrix는 silicon 계약인 2/4/8 MHz를 그대로 사용했다.
Host mailbox의 고정 5 ms polling은 10 MHz SWD에서 대기 시간이 병목이었다.
`f21377e`에서 timeout·nonce·commit marker·poison 계약은 유지하고 최소 polling 간격만
1 ms로 줄였다. 관련 Host 시험 39건과 pair image 2/2 build를 먼저 통과했다.

| 항목 | 결과 |
| --- | --- |
| campaign | 1회 연속 완료, 2,180.983초 |
| SPI data 결과 | **18,157 PASS** |
| cancel·bounded STOP 예상 오류 | **12 PASS** |
| cancel 뒤 정상 재시작 | **12 PASS** — SPI data 18,157건에 포함 |
| SPIM00+TWIM22 동시성 | **1 PASS** — SPI data 18,157건에 포함 |
| fixture cleanup | **2 PASS** |
| campaign 기록 | progress 1건, complete 1건 |
| 총 evidence result | **18,173**, 실패 0건 |
| plan 대조 | 계획 ID 18,169 / 실제 고유 SPI ID 18,169 / 누락 0 / 범위 이탈 0 |
| SPI 속도·mode·order | 2/4/8 MHz, Mode 0~3, MSB/LSB first |
| payload | 1, 2, 31, 32, 255, 256, 1,024 byte |
| 전송 방향 | controller→peripheral, peripheral→controller, full duplex; 반대 방향 ORC도 전 byte 비교 |
| DMA | sync, async 단일 buffer, async 이중 buffer, buffer handover, cancel·STOP·recovery |
| instance 조합 | role 1·2 controller × P2 SPIM/SPIS00·20 × P1 SPIM/SPIS20·21·22, 양방향 12개 조합 |

두 role image의 10 MHz sector erase·flash는 각각 3.152초와 3.043초였다.
`auto_unlock=false`를 유지했고 mass erase·recover는 요청하지 않았다. 최종 전체 실행에
data 불일치, DMA amount·guard 손상, event queue overflow, mailbox timeout, STOP 미증명,
probe 이탈은 없었다.

## 4. 증거

### 4.1 전체 PASS

| 파일 | 크기 | SHA-256 |
| --- | ---: | --- |
| [전체 JSON](evidence/f21377e/fixture201-full-10mhz-f21377e.json) | 15,821,131 byte | `44aeb7c027abf8fdfca35c25f1420645f628bf80d60e3c6377631dca6efe0d32` |
| [append-only journal](evidence/f21377e/fixture201-full-10mhz-f21377e.json.jsonl) | 8,498,300 byte | `fdd21d2ad3d0475bc795be33140f3e483d394055dc9d41148ae60c8734d0195c` |

### 4.2 수신 지연 실패·교정 진단

| 파일 | 판정 | SHA-256 |
| --- | --- | --- |
| [CSN 교정 후 ORC 재현](evidence/2a219a9/fixture201-orc-stress100-10mhz-2a219a9.json) | `0x96 → 0x2D`, FAIL | `bd2ba32a75a1d1eca17c760a848c3d4a3fa0027b03022cf150698978315ee404` |
| [위 실패 journal](evidence/2a219a9/fixture201-orc-stress100-10mhz-2a219a9.json.jsonl) | cleanup만 보존 | `5d29e52703447bca894f971a3a7f5f33c7b7a2206a9e0acff9e8277862eff5aa` |
| [RXDELAY 교정 후 실제 TX 100회](evidence/a254d01/fixture201-buffered-rx-stress100-10mhz-a254d01.json) | PASS | `d0fc732b475bb2fe9290f126746b0cef16d1c0ad90e532345f78586baca1fb94` |
| [실제 TX journal](evidence/a254d01/fixture201-buffered-rx-stress100-10mhz-a254d01.json.jsonl) | 100건+cleanup | `42dddaa56ea4eaba2f017d9992241d5f821d6e1d0aa5eca38b2b0d62612a87d7` |
| [RXDELAY 교정 후 ORC 100회](evidence/a254d01/fixture201-orc-stress100-10mhz-a254d01.json) | PASS | `1952f40f7ea8f8e6b3e51151e7154dd245eab28dd854903d8e613384d75d5164` |
| [ORC journal](evidence/a254d01/fixture201-orc-stress100-10mhz-a254d01.json.jsonl) | 100건+cleanup | `060cd2d86f6acc38c04f6114ec16f6f145d3b9ecfb0035859e9603800c171581` |

Evidence에는 raw UID를 넣지 않고 role별 UID SHA-256, image identity, confirmation hash,
fixture catalog hash, SWD 설정과 flash 결과를 보존했다. 최종 JSON의 `status`는 `passed`다.

## 5. 판정과 다음 단계

Fixture 201의 P2↔P1 route에서 SPIM/SPIS00·20·21·22의 계획된 양방향 data path,
EasyDMA, SPI mode·bit order, ORC, 단일/이중 buffer handover, cancel 뒤 정상 재시작과
SPIM00+TWIM22 동시성은 기능 PASS다. 이 결과는 전기 파형 품질, 임의 핀 route,
외부 SPI 부품 호환성의 보증은 아니다.

M24 통신 인스턴스 기능 검증의 다음 물리 작업은 Fixture 202 SPI다. Fixture 201
점퍼를 그대로 사용하지 않는다. USB 전원을 분리하고 Fixture 202 결선으로 바꾼 뒤,
새 confirmation으로 실행해야 한다. Fixture 202·203과 TWI 301이 끝나기 전에는 T11
또는 M24 전체를 완료로 바꾸지 않는다.
