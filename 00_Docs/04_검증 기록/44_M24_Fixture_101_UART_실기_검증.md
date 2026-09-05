# M24 Fixture 101 UART 실기 검증

| 항목 | 내용 |
| --- | --- |
| 기록 ID | VALIDATION-M24-UART-FIXTURE-044 |
| 실행일 | 2026-09-05 |
| 상태 | **Fixture 101 PASS — M24 전체는 진행 중** |
| exact core | `2542a014c2f4dcf4309bd5372701291d1ace2f82` |
| board gitlink | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` |
| DUT / peer | D 드라이브 / E 드라이브로 사용자가 확정한 두 NU54DK |
| 검증 범위 | UARTE00·20의 P2 bank와 UARTE20·21·22의 P1 bank 사이 Fixture 101 양방향 통신 |
| 아직 아닌 것 | Fixture 102·103, SPI·TWI, analog·stream, 전체 동시성·soak, M24/M25 완료 또는 `v0.4.0` 공개 승인 |

## 1. 확정 결선과 실행 조건

사용자가 [수기 확정 핀맵](<../01_아두이노 코어 설계/13_NU54DK_P2_P4_커넥터_핀맵.md>)에 따라
다음 결선을 직접 확인했다. 보드 A는 DUT, 보드 B는 peer다.

| 신호 | 보드 A(DUT) | 방향 | 보드 B(peer) |
| --- | --- | --- | --- |
| TXD/RXD | P4-21 / P2.02 | → | P2-11 / P1.05 |
| RXD/TXD | P4-19 / P2.00 | ← | P2-12 / P1.04 |
| RTS/CTS | P2-19 / P2.05 | → | P2-9 / P1.07 |
| CTS/RTS | P2-17 / P2.04 | ← | P2-10 / P1.06 |
| 기준 전위 | P2-30 / GND | ↔ | P2-30 / GND |

두 보드의 `DISABLE_UART`는 DAP UART 분리 상태, `DISABLE_SWD`는 SWD 연결 상태로 두었다.
외부 pull-up과 보드 간 전원 rail은 연결하지 않았다. confirmation은 fixture catalog 개정,
두 UID hash, exact role image hash, 공통 GND·동일 I/O 전압·스위치·출력 충돌 조건에 묶었다.

## 2. 검증 중 발견한 문제와 교정

### DAP UART 충돌

처음에는 DAP UART가 P1.04~P1.07에 계속 연결돼 있어 Fixture 101의 peer 신호와 충돌했다.
두 보드의 `DISABLE_UART`를 분리 상태로 바꾸고 USB를 다시 연결한 뒤 최소
`UARTE00 → UARTE20`, 9,600 baud, 8N1, 1-byte 송수신·DMA·STOP·정리가 통과했다.
따라서 당시 무응답의 직접 원인은 잘못된 GPIO 기능 할당이 아니라 DAP UART가 물리적으로 함께
연결된 상태였다.

### 지연 RX fixture 분기 결함

`15565f7` image의 첫 인스턴스 조합에서 일반 UART vector 132개는 통과했지만, RTS/CTS sender를
먼저 시작하고 receiver RX를 100 ms 늦게 여는 vector가 peer `wrong_state`로 실패했다. 원인은
UART의 deferred RX 단계가 SPI/TWI peripheral buffer 준비 분기로 잘못 진입하는 fixture firmware
제어 흐름이었다. `2542a01`에서 UART를 해당 분기에서 명시적으로 제외하고 Host 회귀 truth table을
추가했다. 수정 image의 단일 재현 vector와 전체 Fixture 101에서 같은 실패가 재발하지 않았다.

### CMSIS-DAP 전송 속도

1 MHz SWD에서 A, 다음 재시도에서는 B의 sector erase/disconnect가 각각 timeout됐다. 자동
mass erase·recover는 실행하지 않았다. 두 UID를 100 kHz read-only로 다시 연결해 각각
`CPUID 0x411FD210`을 읽었고, 같은 100 kHz에서 두 exact image를 한 번씩 기록해 전체 시험을
완료했다. 이는 UART baud를 낮춘 것이 아니라 pyOCD와 CMSIS-DAP 사이의 SWD 제어 clock만 낮춘
것이다. UART vector는 계획한 1 Mbps까지 그대로 실행됐다.

Windows 보안 알림의 대상은 NCS GNU toolchain이 호출한 `arm-zephyr-eabi-gdb-py.exe`의
`iconv.exe`였다. 동일 build가 2/2 완료됐고 이번 pyOCD 실행 파일과도 다르므로, 그 알림을
CMSIS-DAP timeout의 원인으로 확정하지 않는다.

## 3. 전체 실행 결과

| 항목 | 결과 |
| --- | --- |
| campaign | 1회 연속 완료, 2,299.577초 |
| 정상 데이터 vector | **1,620 PASS** |
| 예상 오류·bounded STOP vector | **24 PASS** |
| fixture cleanup | **2 PASS** |
| campaign 기록 | progress 1건, complete 1건 |
| 총 evidence result | **1,648 PASS** |
| UART 속도 | 9,600 / 115,200 / 1,000,000 baud |
| 구성 | parity off/on, RTS/CTS off/on |
| payload | 1, 2, 31, 32, 255, 512, 1,024 byte |
| DMA | 비동기 단일·이중 RX buffer, deferred RX, 종료·정리 포함 |
| 역할/instance | controller role 1·2 × DUT 00·20 × peer 20·21·22 |

정상 vector의 payload는 SWD mailbox로 전부 회수해 독립 seed의 기대 hash와 비교했다.
RTS/CTS 지연 RX, parity/framing·break 유도와 bounded STOP도 각 instance/역할 조합에서
실행했다. Runner가 별도로 남긴 다른 fixture의 강제 오류 모드는 이번 PASS에 포함하지 않는다.

## 4. 증거

| 파일 | SHA-256 |
| --- | --- |
| [전체 JSON](evidence/2542a01/fixture101-full-2542a01-100khz.json) | `95a87a364c5b86cdc9b640faaa7d734ddd576dc300262189236f86b943c002eb` |
| [append-only journal](evidence/2542a01/fixture101-full-2542a01-100khz.json.jsonl) | `d95a792d8bc567a143be7b54fc3d2b5019e058c95dc8b926c376b66d75c64814` |

Evidence에는 raw UID 대신 SHA-256, role별 HEX·ELF·build record hash, fixture catalog와
confirmation hash, sector erase·no recover, 100 kHz SWD 기록이 들어 있다. 실패한 실행을 성공
파일로 덮어쓰지 않았으며 최종 `status`는 `passed`다.

## 5. 판정과 다음 단계

Fixture 101에서 사용한 UARTE instance·bank·양방향 data path·EasyDMA·RTS/CTS 경로는
기능 PASS다. 이 결과는 전기 파형 품질이나 모든 임의 핀 route의 보증이 아니다. M24 전체를
완료하려면 별도 confirmation으로 Fixture 102·103 UART route, Fixture 201~203 SPI,
Fixture 301 TWI를 순서대로 검증해야 한다. 다음 물리 작업은 Fixture 102 결선 변경과 사용자
확인이다.
