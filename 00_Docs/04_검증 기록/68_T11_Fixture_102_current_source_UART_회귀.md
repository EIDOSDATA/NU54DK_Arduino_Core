# T11 Fixture 102 current-source UART 회귀

| 항목 | 내용 |
| --- | --- |
| 기록일 | 2026-09-06 |
| 범위 | R00~R13 이후 current-source T11 중 Fixture 102 한 연속 cycle |
| Exact Core | `a49cc0dbc1ef8bf5f697106d873bdce55f5911df` |
| Board gitlink | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` |
| Build | `C:/u3b` DUT/peer 2/2 build-only PASS, failed/error/warning 0, 115.21초 |
| SWD | flash·mailbox·종료 확인 모두 **10,000,000 Hz**, 하향·재시도 없음 |
| 실기 결과 | **822개 기능 PASS, 실패 0개**, 239.5초 |
| 다음 | Fixture 103 전원 OFF 결선 변경과 사용자 확인 |

## 확인한 입력과 결선

사용자는 [67번 기록](67_T11_Fixture_101_current_source_UART_회귀.md)의 다음 결선표와 완료 보고를
받은 뒤 연결 완료·시작을 지시했다. [시작 체크포인트](evidence/t11-fixture102-a49cc0d/checkpoint.json)와
[새 확인서](evidence/t11-fixture102-a49cc0d/confirmation.json)는 해당 사용자 확인을 기록한다. 확인서는 catalog revision 2,
exact source·두 image·UID SHA·역할·스위치·전압 조건에 묶이고 30분 유효기간 안에 검증했다.
이는 사용자 확인에 근거하며 배선의 전기적 계측 증명은 아니다.

| A/DUT | 방향 | B/peer |
| --- | --- | --- |
| P2-25 / P0.00 TX | → | P2-11 / P1.05 RX |
| P2-26 / P0.01 RX | ← | P2-12 / P1.04 TX |
| P4-4 / P0.02 RTS | → | P2-9 / P1.07 CTS |
| P4-5 / P0.03 CTS | ← | P2-10 / P1.06 RTS |
| P2-30 / GND | ↔ | P2-30 / GND |

DAP UART는 양쪽 분리, SWD는 연결, 동일 I/O 전압과 각자 USB 전원을 사용한다.
보드 사이 전원 rail·외부 pull-up·다른 출력은 연결하지 않는다. [USB 재식별](evidence/t11-fixture102-a49cc0d/usb-inventory.json)은
A D/COM5·COM6, B E/COM7·COM8과 exact 두 UID SHA를 확인했다. UID 원문은 저장하지 않았다.
기존 peer P0 DAP CTS 납땜 의심 경로의 재시험 중단은 유지한다. 이번 경로는 A P0↔B P1 외부
MCU UART이며 그 역사적 DAP CTS 실패를 이번 결과로 지우지 않는다.

Clean `main`/`origin/main`에서 새 exact pair를 build했다. 직전 154324c pair와 비교한
컴파일 입력 hash·설정·source membership·FLASH/RAM은 같고 embedded commit identity만 새
source를 가리킨다. [입력 비교](evidence/t11-fixture102-a49cc0d/build-input-comparison.json),
[build·ELF·HEX hash](evidence/t11-fixture102-a49cc0d/target-artifact-index.json), [exact image](evidence/t11-fixture102-a49cc0d/exact-images.json)에
근거를 보존한다. 이번 작업에서 제품 코드·시험 앱·canonical runner를 변경하지 않았다.

## 실기 결과

A UARTE30 × B UARTE20/21/22 × 송신 역할 2개, 총 6개 조합에서 각각 137개 기능 결과를 통과했다.

| 검사 | PASS |
| --- | ---: |
| 9,600·115,200·1,000,000 baud, parity off/even, RTS/CTS off/on, 1·2·31·32·255·512·1024 bytes, 단일/이중 RX buffer | 792 |
| CTS 100ms 정지 후 deferred RX 재개 | 6 |
| parity mismatch·break 오류 검출과 bounded STOP | 12 |
| 각 오류 직후 정상 전송 복구 | 12 |
| **기능 합계** | **822** |

데이터 record는 복구를 포함해 810개, 예상 오류는 12개다. 양쪽 송신 역할 종료마다 두 보드
disarm `[0]`을 확인했다. cleanup 2개·progress 1개·campaign 완료 1개를 포함하면 826개다.
Cleanup과 campaign을 기능 PASS 수에 포함하지 않는다. 최대 수신량은 1024 bytes × buffer 2개다.
Canonical oracle이 nonce/sequence/role, guard·DMA count/amount, 전체 RX payload와 seed 기반
독립 기대 패턴, STOP을 검사했다. [coverage 감사](evidence/t11-fixture102-a49cc0d/results-audit.json)는 기능 ID 822개가
고유하고 최종 JSON과 append-only journal이 일치함을 확인했다.

실행 옵션은 `--fixture 102 --swd-frequency-hz 10000000 --repetitions 1 --execute-fixture`다.
확인서·새 evidence 경로·두 exact role image와 OS probe lock을 사용했다. Flash는 sector erase·
`auto_unlock=false`이며 mass erase/recover·보드 대체·무작정 재시도를 하지 않았다.
Runner 마지막 범용 `forced-error modes remain NOT RUN` 문구와 별개로 이번 parity/break 오류와
그 뒤 복구는 실제 record로 판정한다. 다른 미실행 오류 모드·T13 동시성·soak를 포함하지 않는다.

## 원본과 종료 상태

- [최종 JSON](evidence/t11-fixture102-a49cc0d/fixture102-attempt1.json), [원시 journal](evidence/t11-fixture102-a49cc0d/fixture102-attempt1.json.jsonl), [실행 log](evidence/t11-fixture102-a49cc0d/fixture102-attempt1.log)
- [preflight](evidence/t11-fixture102-a49cc0d/preflight.log), [실행 wrapper](evidence/t11-fixture102-a49cc0d/run.py), [환경·UID 비공개 처리](evidence/t11-fixture102-a49cc0d/runtime.py)
- [종료 확인](evidence/t11-fixture102-a49cc0d/postflight.json), [원본 byte·hash·gzip 목록](evidence/t11-fixture102-a49cc0d/raw-files.json)

종료 후 flash/reset/fixture 명령 없이 CPUID `0x411FD210`과 full 40-byte commit·role을 양쪽에서
다시 읽어 통과했다. 두 CPU는 SLEEPING이며 a49cc0d DUT/peer image와 Fixture 102 결선이 남는다.
SWD 10 MHz는 요청한 clock 설정이며 계측한 파형 품질 보증은 아니다. pyOCD의 board ID 미등록
안내는 explicit `nrf54l` target 선택과 함께 원본 log에 보존했다.

제품 source 변경이 없으므로 이번 pair 실제 결과를 67번의 Fixture 101 exact 154324c 결과와
구분해 누적한다. 전체 current-source T11은 부분 완료이며 Fixture 103·201~203·301과
T12~T15·RC/공개 gate는 남아 있다. Readiness의 필수 physical gate를 이번 부분 결과로 바꾸지 않는다.
이전 이미지·실패·공개 자산과 재개에 필요한 build/raw evidence는 보존하고 추가 삭제 대상은 없다.

## 문서와 증거 검증

현재 상태와 다음 결선을 문서 9개에 반영했다. Markdown UTF-8·내부 링크 177개, 계약 45개,
inventory 75개·Serial identity 23개·System capability 16개를 통과했다. Readiness는
필수 16개 중 blocker 8개를 유지한다. [software 검사 기록](evidence/t11-fixture102-a49cc0d/software-verification.json)에
canonical 명령과 log hash를 남겼다. 제품 코드 변경이 없는 이번 문서·증거 작업에서 이전
full Host·package·전체 target 결과를 새 source의 실행 결과로 복사하지 않는다.

원본 27개는 UTF-8/LF 사본과 원본 byte gzip으로 보존하고 hash·복원 일치·UID 비공개를
검사했다. 최종 GitHub Actions 상태는 미확인이다. 최종 commit·main push와 checkout·board·
SDK·작업 프로세스 점검은 작업 산출물에 기록하며, 본문의 실기 source를 문서 commit으로 바꾸지 않는다.

## 다음 결선: Fixture 103

**두 USB를 모두 분리한 뒤 A 쪽 신호선 네 개만 아래처럼 옮긴다. B와 공통 GND는 그대로다.**

| A의 현재 Fixture 102 핀 | A의 새 Fixture 103 핀 | 유지할 B 핀 |
| --- | --- | --- |
| P2-25 | P2-12 / P1.04 TX | P2-11 / P1.05 RX |
| P2-26 | P2-11 / P1.05 RX | P2-12 / P1.04 TX |
| P4-4 | P2-10 / P1.06 RTS | P2-9 / P1.07 CTS |
| P4-5 | P2-9 / P1.07 CTS | P2-10 / P1.06 RTS |
| P2-30 GND | 그대로 유지 | P2-30 GND |

DAP UART 양쪽 분리·SWD 연결·동일 전압·각자 USB 전원 조건을 유지하며 전원선이나 외부 저항은
추가하지 않는다. 사용자 결선 완료 확인 뒤 당시 clean HEAD의 새 exact image·확인서로
Fixture 103을 시작한다. 이전 102 확인서를 재사용하지 않는다.
