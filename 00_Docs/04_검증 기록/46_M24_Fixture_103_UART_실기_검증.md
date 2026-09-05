# M24 Fixture 103 UART 실기 검증

| 항목 | 내용 |
| --- | --- |
| 기록 ID | VALIDATION-M24-UART-FIXTURE-046 |
| 실행일 | 2026-09-05 |
| 상태 | **Fixture 103 PASS — M24 전체는 진행 중** |
| exact core | `b3c689b07f1a23e479a78bd2f852a650fd4a86d5` |
| board gitlink | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` |
| DUT / peer | D 드라이브 / E 드라이브로 사용자가 확정한 두 NU54DK |
| 검증 범위 | UARTE20·21·22의 P1 bank 사이 Fixture 103 양방향 통신 |
| 아직 아닌 것 | SPI·TWI, analog·stream, 전체 동시성·soak, M24/M25 완료 또는 `v0.4.0` 공개 승인 |

## 1. 확정 결선과 실행 조건

사용자가 [수기 확정 핀맵](<../01_아두이노 코어 설계/13_NU54DK_P2_P4_커넥터_핀맵.md>)과
fixture catalog에 따라 다음 결선을 직접 확인했다. 보드 A는 DUT, 보드 B는 peer다.

| 신호 | 보드 A(DUT) | 방향 | 보드 B(peer) |
| --- | --- | --- | --- |
| TXD/RXD | P2-12 / P1.04 | → | P2-11 / P1.05 |
| RXD/TXD | P2-11 / P1.05 | ← | P2-12 / P1.04 |
| RTS/CTS | P2-10 / P1.06 | → | P2-9 / P1.07 |
| CTS/RTS | P2-9 / P1.07 | ← | P2-10 / P1.06 |
| 기준 전위 | P2-30 / GND | ↔ | P2-30 / GND |

두 보드의 `DISABLE_UART`는 DAP UART 분리 상태, `DISABLE_SWD`는 SWD 연결 상태로 두었다.
외부 pull-up과 보드 간 전원 rail은 연결하지 않았다. Confirmation은 fixture catalog 개정,
두 UID hash, exact role image hash, 공통 GND·동일 I/O 전압·스위치·출력 충돌 조건에 묶었다.

## 2. 오류 분리와 진단 보강

최초 `9602f9a` 전체 실행은 사용자가 시험 중 선을 건드린 뒤 807개 결과 부근에서 중단됐다.
같은 source의 재시도는 한 번은 peer flash 중 CMSIS-DAP timeout, 한 번은 95개 정상 vector 뒤
role 2의 비정상 UART event로 중단됐다. 당시 firmware의 상태 word는 모든 비정상 event를
`0x00000200` 하나로 합쳐 취소 event와 실제 UARTE 오류를 구분할 수 없었다.

시험 firmware가 하위 판정 비트를 유지하면서 상위 비트에 event 종류와 UARTE `ERRORSRC`를
보존하도록 `b3c689b`에서 보강했다. DUT/peer pair image 2개는 새 `C:/r57`에서 build-only
**2/2 PASS, 실패·오류·경고 0건**이었다. 관련 Host 시험 23개와 clang-format 22.1.8
dry-run도 통과했다.

보강 image의 첫 전체 실행은 148개 result에서 `0x04060200`을 기록했다. 이는 기존 비정상 bit
`0x0200`, event tag 6(`UarteEventType::error`에 1을 더한 값), UARTE error mask `0x04`
(`FRAMING`)의 결합이다. Role 2는 첫 1,024-byte RX buffer를 완료한 상태였고 guard 손상은 없었다.
따라서 이 실패는 취소 수명주기나 event ring overflow가 아니라 stop bit를 HIGH로 읽지 못한 실제
선로/접촉 오류로 분류했다.

결선을 움직이지 않은 상태에서 다음 두 진단을 수행했다.

| 진단 | 결과 | 해석 |
| --- | --- | --- |
| 9,600 baud, 1,024-byte 이중 RX buffer, 양방향 5 cycle | data 10건, cleanup 10건, progress 5건, complete 1건 — 총 26 PASS | 이중 버퍼가 항상 실패하는 결정적 결함은 재현되지 않음 |
| 9,600 단일→이중 1,024 byte와 1 Mbps 255→512 byte 전환, 양방향 5 cycle | data 40건, cleanup 10건, progress 5건, complete 1건 — 총 56 PASS | 앞선 실패 전환 순서의 결정적 결함은 재현되지 않음 |

진단 실행기는 전체 catalog를 의도적으로 축소한 일회성 판정이므로 자체 종료 문자열을 Fixture 103
전체 PASS로 사용하지 않았다. 전체 PASS는 아래의 비축소 실행 결과만을 근거로 한다.

## 3. 전체 실행 결과

| 항목 | 결과 |
| --- | --- |
| campaign | 1회 연속 완료, 3,444.172초 |
| 정상 데이터 vector | **2,430 PASS** |
| 예상 오류·bounded STOP vector | **36 PASS** |
| fixture cleanup | **2 PASS** |
| campaign 기록 | progress 1건, complete 1건 |
| 총 evidence result | **2,470 PASS** |
| UART 속도 | 9,600 / 115,200 / 1,000,000 baud |
| 구성 | parity off/on, RTS/CTS off/on |
| payload | 1, 2, 31, 32, 255, 512, 1,024 byte |
| DMA | 비동기 단일·이중 RX buffer, deferred RX, 오류 뒤 재시작, 종료·정리 포함 |
| 역할/instance | controller role 1·2 × DUT UARTE20·21·22 × peer UARTE20·21·22 |

각 역할·instance 조합에서 정상 데이터 result 135건씩, 모두 2,430건을 기록했다. Payload는
SWD mailbox로 전부 회수해 독립 seed의 기대 hash와 비교했다. RTS/CTS 지연 RX,
parity/framing·break 유도, bounded STOP과 같은 lease에서의 정상 재시작도 각 조합에서
검사했다. 데이터 불일치, event queue overflow, DMA guard 손상, mailbox timeout, STOP 미증명
또는 장치 이탈은 최종 실행에 없었다.

두 role image의 sector erase·flash는 각각 52.094초와 51.969초였다. 100 kHz SWD control을
사용했고 mass erase·recover는 요청하지 않았다. 최종 실행 전 동일 image 재플래시 중 DUT
CMSIS-DAP timeout 한 건이 있었으나 probe 열거가 회복된 뒤 새 evidence에서 다시 시작했다.
중단 결과를 최종 PASS에 합치거나 자동 재사용하지 않았다.

## 4. 증거

### 4.1 전체 PASS

| 파일 | SHA-256 |
| --- | --- |
| [전체 JSON](evidence/b3c689b/fixture103-full-b3c689b-100khz-retry2.json) | `3b454cd40fb56c1dcde9adfa984ad736a2f564c0b2e95859ad746706ea7045d0` |
| [append-only journal](evidence/b3c689b/fixture103-full-b3c689b-100khz-retry2.json.jsonl) | `9f50a02fc4666222c3225486ad4a87c2130f0fa6cf713717d783d053a035059a` |

### 4.2 실패 원인과 축소 진단

| 파일 | SHA-256 |
| --- | --- |
| [FRAMING 실패 JSON](evidence/b3c689b/fixture103-full-b3c689b-100khz.json) | `626c6e78503e9f50dc02fae421bf6735a2dff29bf8dbaa46ac6524b6ea27f900` |
| [FRAMING 실패 journal](evidence/b3c689b/fixture103-full-b3c689b-100khz.json.jsonl) | `cf8bc31025547a70796d9ba35e9286c6a678ad4f0aa08a722fb0a813705cc21f` |
| [이중 버퍼 5-cycle JSON](evidence/b3c689b/fixture103-targeted-9600-double-5cycles.json) | `d2d29c70aedd5309e2c0887a5dddcc335220b43f8e7edb25fa9a83c2a508e868` |
| [이중 버퍼 5-cycle journal](evidence/b3c689b/fixture103-targeted-9600-double-5cycles.json.jsonl) | `57e930f514746102c9fbd265a42582e3bc721435b58dd5fa003e8efd470f992e` |
| [전환 순서 5-cycle JSON](evidence/b3c689b/fixture103-targeted-transitions-5cycles.json) | `b6f064f5aa6cf231847ff45b4f858a569aae3d685617b058305a2f1b5cf629a2` |
| [전환 순서 5-cycle journal](evidence/b3c689b/fixture103-targeted-transitions-5cycles.json.jsonl) | `4c060fceb3dff455bc3a14cd900f97587cf725d7ccb1e333d22094dd9b607763` |

Evidence에는 raw UID를 넣지 않고 role별 UID SHA-256, image identity, confirmation hash,
fixture catalog hash, SWD 설정과 flash 결과를 보존했다. 최종 전체 파일의 `status`는 `passed`다.

## 5. 판정과 다음 단계

Fixture 103의 P1 route에서 UARTE20·21·22 전 조합의 양방향 data path, EasyDMA,
parity, RTS/CTS, 오류 뒤 재시작은 기능 PASS다. Fixture 101~103으로 계획한 UART 외부 fixture는
완료됐지만, 이 결과는 전기 파형 품질이나 임의 배선의 신호 무결성 보증이 아니다.

M24 통신 인스턴스 기능 검증의 다음 물리 작업은 Fixture 201 SPI다. 현재 UART 점퍼를 그대로
SPI로 사용하지 않는다. USB 전원을 분리하고 별도 Fixture 201 결선 안내에 따라 다시 연결한 뒤,
새 confirmation으로 실행해야 한다. SPI 201~203과 TWI 301이 끝나기 전에는 T11 또는 M24 전체를
완료로 바꾸지 않는다.
