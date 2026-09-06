# T11 Fixture 103 current-source UART 회귀

| 항목 | 내용 |
| --- | --- |
| 기록일 | 2026-09-06 |
| 범위 | R00~R13 이후 current-source T11 중 Fixture 103 한 연속 cycle |
| Exact Core | `7aece93395f0d74272816894a18c2c5e3f1a2abe` |
| Board gitlink | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` |
| Build | `C:/u3c` DUT/peer 2/2 build-only PASS, failed/error/warning 0, 110.57초 |
| SWD | flash·mailbox·종료 확인 모두 **10,000,000 Hz**, 속도 하향 없음 |
| 실기 | 최종 실행 **2,466개 기능 PASS, 기능 실패 0개**, 708.0초; 최초 peer flash 실패 1개 별도 보존 |
| 다음 | Fixture 201 SPI 전원 OFF 결선 변경과 사용자 확인 |

## Exact 입력과 승인 결선

사용자는 [68번 기록](68_T11_Fixture_102_current_source_UART_회귀.md)의 다음 Fixture 103 결선표와
완료 보고를 받은 뒤 결선 완료·테스트 시작을 지시했다. [시작 기록](evidence/t11-fixture103-7aece93/checkpoint.json)과
[새 확인서](evidence/t11-fixture103-7aece93/confirmation.json)에 이 확인을 남겼다. Catalog revision 2, 두 exact UID SHA·
역할·source·image hash와 스위치·전압 조건을 묶고 확인서의 30분 유효기간 안에 시작했다.
이는 사용자 확인이며 배선을 전기적으로 계측했다는 뜻은 아니다.

| A/DUT | 방향 | B/peer |
| --- | --- | --- |
| P2-12 / P1.04 TX | → | P2-11 / P1.05 RX |
| P2-11 / P1.05 RX | ← | P2-12 / P1.04 TX |
| P2-10 / P1.06 RTS | → | P2-9 / P1.07 CTS |
| P2-9 / P1.07 CTS | ← | P2-10 / P1.06 RTS |
| P2-30 / GND | ↔ | P2-30 / GND |

DAP UART는 양쪽 분리, SWD 연결, 동일 I/O 전압, 각자 USB 전원 조건이다.
보드 사이 전원 rail·외부 pull-up·다른 출력은 연결하지 않는다. [USB 재식별](evidence/t11-fixture103-7aece93/usb-inventory.json)은
A D/COM5·COM6, B E/COM7·COM8과 exact 두 UID SHA를 확인했다. UID 원문은 저장하지 않았다.
기존 peer P0 DAP CTS 진단 중단 지시는 유지하며 이번 P1↔P1 외부 UART PASS로 과거 실패를 지우지 않는다.

Clean `main`/`origin/main`에서 DUT/peer를 새로 build했다. 직전 a49cc0d와 컴파일 입력 hash·
설정·source membership·FLASH/RAM은 같고 embedded commit identity는 새 source로 갱신됐다.
[입력 비교](evidence/t11-fixture103-7aece93/build-input-comparison.json), [산출물 hash](evidence/t11-fixture103-7aece93/target-artifact-index.json),
[exact image·mailbox](evidence/t11-fixture103-7aece93/exact-images.json)에 근거가 있다. 제품 코드·시험 앱·canonical runner는
이번 작업에서 변경하지 않았다. 원본 image의 실기 source와 최종 문서 commit을 구분한다.

## 최초 flash 실패와 한정 재개

첫 실행은 A exact image의 기록·boot 뒤 B/peer sector flash에서 CMSIS-DAP 응답 시간 초과로
실패했다. [최초 실패 JSON](evidence/t11-fixture103-7aece93/fixture103-attempt1.json)과 [log](evidence/t11-fixture103-7aece93/fixture103-attempt1.log)를
보존했다. `external_wiring_executed=false`, 기능 record 0개로 UART 시험은 시작하지 않았다.

[읽기 전용 진단](evidence/t11-fixture103-7aece93/probe-diagnostic.json)은 flash/reset/fixture 명령 없이 양쪽 10 MHz SWD
CPUID `0x411FD210` 응답과 COM5·6/COM7·8을 확인했다. A는 SLEEPING, B는 HALTED였다.
실패의 근본 원인은 미확정이다. 통신 응답 회복을 확인한 뒤 [한정 재개 결정](evidence/t11-fixture103-7aece93/retry-decision.json)에
따라 같은 source·image·10 MHz와 유효한 사용자 확인으로 새 evidence에서 한 번만 다시 시작했다.
이 최종 실행에서 두 flash와 전체 기능이 통과했다. 최초 실패를 최종 결과에 합치거나 지우지 않는다.

## 실제 결과

양쪽 UARTE20·21·22의 9개 instance 조합을 두 송신 역할로 검사했다. 총 18개 역할·instance
조합마다 137개 기능 결과를 통과했다.

| 검사 | PASS |
| --- | ---: |
| 9,600·115,200·1,000,000 baud, parity off/even, RTS/CTS off/on, 1·2·31·32·255·512·1024 bytes, 단일/이중 RX buffer | 2,376 |
| CTS 100ms 정지 후 deferred RX 재개 | 18 |
| parity mismatch·break 오류 검출과 bounded STOP | 36 |
| 각 오류 직후 정상 전송 복구 | 36 |
| **기능 합계** | **2,466** |

데이터 record 2,430개에는 복구 36개가 포함되며 예상 오류는 별도 36개다. 양쪽 송신 역할 종료마다
두 보드의 disarm `[0]`을 확인했다. Cleanup 2개, progress 1개, campaign 완료 1개를 포함한
전체 journal은 2,470개이며 이 네 개를 기능 PASS에 포함하지 않는다. 최대 수신량은
1024 bytes × buffer 2개다. Canonical oracle이 nonce/sequence/role, guard, DMA count/amount,
전체 RX payload와 독립 seed 패턴, STOP 반환을 대조했다. [coverage 감사](evidence/t11-fixture103-7aece93/results-audit.json)는
기능 ID 2,466개의 고유성과 최종 JSON·append-only journal 일치를 확인했다.

실행 옵션은 `--fixture 103 --swd-frequency-hz 10000000 --repetitions 1 --execute-fixture`다.
새 확인서·evidence 경로, 두 exact role image와 OS probe lock을 사용했다. Flash는 sector erase·
`auto_unlock=false`였고 mass erase/recover·보드 대체·속도 하향은 없었다. 진단 뒤 한 번의 새 실행만 수행했다.
Runner 마지막 범용 `forced-error modes remain NOT RUN` 문구와 별개로 이번 parity/break와
그 뒤 복구는 실제 record로 판정한다. T13 전체 동시성·soak·미실행 오류 모드는 포함하지 않는다.

## 누적 UART 범위와 원본

| Fixture | Exact source | Data | 예상 오류 | 기능 합계 |
| --- | --- | ---: | ---: | ---: |
| 101 P2↔P1 | `154324ce7a865522374066ca957ebc98909c7c19` | 1,620 | 24 | 1,644 |
| 102 P0↔P1 | `a49cc0dbc1ef8bf5f697106d873bdce55f5911df` | 810 | 12 | 822 |
| 103 P1↔P1 | `7aece93395f0d74272816894a18c2c5e3f1a2abe` | 2,430 | 36 | 2,466 |
| 합계 | 각 exact 원본 별도 보존 | 4,860 | 72 | 4,932 |

[67번](67_T11_Fixture_101_current_source_UART_회귀.md)·[68번](68_T11_Fixture_102_current_source_UART_회귀.md)과
이번 결과로 current-source T11의 승인 UART route 세 묶음을 완료했다. 서로 다른 embedded commit과
이미지를 하나의 source PASS로 합치지 않는다. SPI 201~203·TWI 301과 T12~T15·RC/공개는 남아 있다.
[누적 감사](evidence/t11-fixture103-7aece93/uart-route-aggregate.json)는 각 원본 hash, 기능 합계,
세 pair의 컴파일 입력·설정·source membership·메모리 일치와 그 사이 Git 변경의 문서·증거 범위를 확인했다.

- [최종 JSON](evidence/t11-fixture103-7aece93/fixture103-attempt2.json), [원시 journal](evidence/t11-fixture103-7aece93/fixture103-attempt2.json.jsonl), [실행 log](evidence/t11-fixture103-7aece93/fixture103-attempt2.log)
- [preflight](evidence/t11-fixture103-7aece93/preflight.log), [최종 실행 wrapper](evidence/t11-fixture103-7aece93/run-attempt2.py), [환경·UID 비공개 처리](evidence/t11-fixture103-7aece93/runtime.py)
- [종료 확인](evidence/t11-fixture103-7aece93/postflight.json), [원본 byte·hash·gzip 목록](evidence/t11-fixture103-7aece93/raw-files.json)

종료 후 flash/reset/fixture 명령 없이 양쪽 CPUID `0x411FD210`, full 40-byte commit·role을
다시 읽어 통과했다. 읽기 순간의 CPU state는 A SLEEPING·B RUNNING이며 7aece93 DUT/peer image와
Fixture 103 결선을 유지한다. CPU state snapshot을 별도의 기능 PASS 조건으로 사용하지 않는다.
SWD 10 MHz는 요청한 clock 설정이며 계측한 파형 품질 보증은 아니다. pyOCD board ID 미등록
안내는 explicit `nrf54l` 선택과 함께 원본 log에 남겼다. 이전 실패·이미지·공개 자산과 재개에
필요한 build/raw evidence는 보존한다. Readiness의 필수 physical gate는 부분 결과로 승격하지 않는다.

## 문서와 증거 검증

현재 상태와 다음 결선을 문서 9개에 반영했다. Markdown UTF-8·내부 링크 178개, 계약 45개,
inventory 75개·Serial identity 23개·System capability 16개를 통과했다. Readiness는
필수 16개 중 blocker 8개를 유지한다. [software 검사 기록](evidence/t11-fixture103-7aece93/software-verification.json)에
canonical 명령과 log hash를 남겼다. 제품 코드 변경이 없는 이번 작업에서 이전 full Host·
package·전체 target 결과를 새 source의 실행 결과로 복사하지 않는다.

실패·진단·최종 결과와 작성 입력 38개를 UTF-8/LF 사본 및 원본 byte gzip으로 보존하고 hash·복원
일치·UID 비공개를 검사했다. 실행 전 보고서 초안의 CPU 상태 가정은 별도로 보존하고 실제
종료 snapshot으로 교정했다. 실기 증거와 판정은 변경하지 않았다. 추가 삭제 대상은 없다.
최종 GitHub Actions 상태는 미확인이다. 최종 commit·main push와 checkout·board·SDK·작업
프로세스 점검은 작업 산출물에 기록하며 본문의 실기 source를 문서 commit으로 바꾸지 않는다.

## 다음: Fixture 201 SPI

**두 USB를 모두 분리한 뒤 A 쪽 신호선 네 개만 아래처럼 옮긴다. B와 공통 GND는 그대로다.**
현재 A 핀 순서가 앞선 UART 안내와 다르므로 유지할 B 핀을 함께 대조한다.

| A의 현재 Fixture 103 핀 | A의 새 Fixture 201 핀 | 유지할 B 핀 | SPI 신호 |
| --- | --- | --- | --- |
| P2-11 | P4-20 / P2.01 | P2-12 / P1.04 | SCK |
| P2-12 | P4-21 / P2.02 | P2-11 / P1.05 | A MOSI / A SPIS MISO |
| P2-9 | P2-17 / P2.04 | P2-10 / P1.06 | A MISO / A SPIS MOSI |
| P2-10 | P2-19 / P2.05 | P2-9 / P1.07 | CSN |
| P2-30 GND | 그대로 유지 | P2-30 GND | GND |

DAP UART 양쪽 분리·SWD 연결·동일 I/O 전압·각자 USB 전원 조건을 유지하며 전원선이나 외부
저항은 추가하지 않는다. 역할 교대 시 MOSI/MISO의 P2 전용 관계는 firmware가 처리한다.
사용자 결선 완료 확인 뒤 당시 clean HEAD의 exact image·새 확인서로 Fixture 201을 시작한다.
이번 UART 확인서와 결과로 SPI를 실행하거나 PASS 처리하지 않는다.
