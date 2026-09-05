# M24 Fixture 102 UART 실기 검증

| 항목 | 내용 |
| --- | --- |
| 기록 ID | VALIDATION-M24-UART-FIXTURE-045 |
| 실행일 | 2026-09-05 |
| 상태 | **Fixture 102 PASS — M24 전체는 진행 중** |
| exact core | `ff3423ea8b6e9a8419d72b493d02874deaac9dca` |
| board gitlink | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` |
| DUT / peer | D 드라이브 / E 드라이브로 사용자가 확정한 두 NU54DK |
| 검증 범위 | UARTE30의 P0 bank와 UARTE20·21·22의 P1 bank 사이 Fixture 102 양방향 통신 |
| 아직 아닌 것 | Fixture 103, SPI·TWI, analog·stream, 전체 동시성·soak, M24/M25 완료 또는 `v0.4.0` 공개 승인 |

## 1. 확정 결선과 실행 조건

사용자가 [수기 확정 핀맵](<../01_아두이노 코어 설계/13_NU54DK_P2_P4_커넥터_핀맵.md>)과
fixture catalog에 따라 다음 결선을 직접 확인했다. 보드 A는 DUT, 보드 B는 peer다.

| 신호 | 보드 A(DUT) | 방향 | 보드 B(peer) |
| --- | --- | --- | --- |
| TXD/RXD | P2-25 / P0.00 | → | P2-11 / P1.05 |
| RXD/TXD | P2-26 / P0.01 | ← | P2-12 / P1.04 |
| RTS/CTS | P4-4 / P0.02 | → | P2-9 / P1.07 |
| CTS/RTS | P4-5 / P0.03 | ← | P2-10 / P1.06 |
| 기준 전위 | P2-30 / GND | ↔ | P2-30 / GND |

두 보드의 `DISABLE_UART`는 DAP UART 분리 상태, `DISABLE_SWD`는 SWD 연결 상태로 두었다.
외부 pull-up과 보드 간 전원 rail은 연결하지 않았다. confirmation은 fixture catalog 개정,
두 UID hash, exact role image hash, 공통 GND·동일 I/O 전압·스위치·출력 충돌 조건에 묶었다.

## 2. 실행 전 build와 장치 식별

현재 clean `main`의 exact core에서 `v0.4.0` Zephyr group 20개를 새 `C:/r52`에 build해
**20/20 build-only PASS, 실패·오류·경고 0건**을 확인했다. 처음 연 셸은 Nordic
`environment.json` 변수가 적용되지 않아 Zephyr SDK 탐색 전에 중단됐고 target compile이나
flash는 시작하지 않았다. 고정 toolchain의 PATH, `PYTHONPATH`, `ZEPHYR_TOOLCHAIN_VARIANT`와
`ZEPHYR_SDK_INSTALL_DIR`를 적용한 새 출력 경로에서 전체 build를 다시 수행했다.

D 드라이브의 보드를 role 1 DUT, E 드라이브의 보드를 role 2 peer로 고정했다. Evidence에는
raw UID를 기록하지 않고 각 UID의 SHA-256만 보존한다. Preflight에서 source·board gitlink,
두 role의 HEX·ELF·build record hash, Fixture 102 catalog hash와 사용자 confirmation을 모두
대조한 뒤에만 외부 출력을 허용했다.

## 3. 전체 실행 결과

| 항목 | 결과 |
| --- | --- |
| campaign | 1회 연속 완료, 1,148.688초 |
| 정상 데이터 vector | **810 PASS** |
| 예상 오류·bounded STOP vector | **12 PASS** |
| fixture cleanup | **2 PASS** |
| campaign 기록 | progress 1건, complete 1건 |
| 총 evidence result | **826 PASS** |
| UART 속도 | 9,600 / 115,200 / 1,000,000 baud |
| 구성 | parity off/on, RTS/CTS off/on |
| payload | 1, 2, 31, 32, 255, 512, 1,024 byte |
| DMA | 비동기 단일·이중 RX buffer, deferred RX, 오류 뒤 재시작, 종료·정리 포함 |
| 역할/instance | controller role 1·2 × DUT UARTE30 × peer UARTE20·21·22 |

각 역할·instance 조합에서 정상 데이터 result 135건씩, 모두 810건을 기록했다. Payload는
SWD mailbox로 전부 회수해 독립 seed의 기대 hash와 비교했다. RTS/CTS 지연 RX,
parity/framing·break 유도, bounded STOP과 같은 lease에서의 정상 재시작도 각 조합에서
검사했다. 데이터 불일치, mailbox timeout, STOP 미증명 또는 장치 이탈은 없었다.

두 role image의 sector erase·flash는 각각 52.938초와 52.881초가 걸렸다. Fixture 101에서
안정성을 확인한 100 kHz SWD control clock을 그대로 사용했으며 mass erase·recover는 요청하지
않았다. UART bus는 계획한 1 Mbps까지 실행했으므로 이 설정을 UART baud 제한으로 해석하지 않는다.

Evidence 기록 뒤 저장소 전체 정렬 gate에서 이 fixture의 공통 header 들여쓰기 한 곳을 교정했다.
정렬 후 DUT/peer를 새 `C:/r53`에 다시 build해 2/2 PASS했고, 두 role의 runtime HEX SHA-256은
실기에서 사용한 image와 각각 동일했다. 소스 위치 정보가 포함된 ELF hash는 달라졌으므로 실기
evidence의 exact ELF와 core revision은 소급 변경하지 않는다. 정렬 뒤 M12 Host 전체도 PASS했다.

## 4. 증거

| 파일 | SHA-256 |
| --- | --- |
| [전체 JSON](evidence/ff3423e/fixture102-full-ff3423e-100khz.json) | `590dd5290d4054a4886cbeefded6ea6d59e4a7d6718f5904d186d287f4b1d1c6` |
| [append-only journal](evidence/ff3423e/fixture102-full-ff3423e-100khz.json.jsonl) | `3fa0a1181770cdce011176ec8513e9566526c9289b6efcfd8bb4367abd8f0f18` |

Evidence에는 role별 image identity, confirmation hash, fixture catalog hash, 100 kHz SWD와
sector erase·no recover 기록이 들어 있다. 결과 파일의 최종 `status`는 `passed`이며 원본은
사용자 Documents 증거 디렉터리에도 별도로 보존한다.

## 5. 판정과 다음 단계

Fixture 102에서 사용한 UARTE30 P0 route와 UARTE20·21·22 P1 route의 양방향 data path,
EasyDMA, parity, RTS/CTS, 오류 뒤 재시작은 기능 PASS다. 이 결과는 전기 파형 품질이나 모든
임의 핀 route의 보증이 아니다. M24 통신 인스턴스 기능 검증을 계속하려면 별도 confirmation으로
Fixture 103 UART와 Fixture 201~203 SPI, Fixture 301 TWI를 순서대로 검증해야 한다. 다음 물리
작업은 Fixture 103 P1↔P1 결선 변경과 사용자 확인이다.
