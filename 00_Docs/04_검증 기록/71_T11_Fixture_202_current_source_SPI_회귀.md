# T11 Fixture 202 current-source SPI 회귀

| 항목 | 내용 |
| --- | --- |
| 기록일 | 2026-09-06 |
| 범위 | R00~R13 이후 current-source T11 중 Fixture 202 한 연속 cycle |
| Exact Core | `1349e208073d0fd7d3b020a5e9facf771b371237` |
| Board gitlink | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` |
| Build | `C:/u3e` DUT/peer 2/2 build-only PASS, failed/error/warning 0, 114.23초 |
| SWD | flash·mailbox·종료 확인 모두 **10,000,000 Hz**, 속도 하향 없음 |
| 실기 | 최종 실행 **9,084개 기능 PASS, 기능 실패 0개**, 1085.266초; 최초 peer flash 실패 별도 보존 |
| 다음 | Fixture 203 SPI 전원 OFF 결선 변경과 사용자 확인 |

## Exact 입력과 확인된 결선

사용자는 [70번 기록](70_T11_Fixture_201_current_source_SPI_회귀.md)의 다음 Fixture 202 안내 뒤
연결 완료·202 시작을 지시했다. [시작 기록](evidence/t11-fixture202-1349e20/checkpoint.json)과 [확인서](evidence/t11-fixture202-1349e20/confirmation.json)는
catalog revision 2, exact UID SHA·역할·source·image hash와 스위치·전압 조건을 연결한다.
원래 사용자 확인 시각부터 30분 안에 최종 연속 cycle을 시작했으며 확인 시각을 갱신하지 않았다.
이는 사용자 확인으로서 배선을 전기적으로 계측한 결과는 아니다.

| 신호 | A/DUT | B/peer |
| --- | --- | --- |
| SCK | P2-25 / P0.00 | P2-12 / P1.04 |
| MOSI | P2-26 / P0.01 | P2-11 / P1.05 |
| MISO | P4-4 / P0.02 | P2-10 / P1.06 |
| CSN | P4-5 / P0.03 | P2-9 / P1.07 |
| GND | P2-30 / GND | P2-30 / GND |

DAP UART 양쪽 분리, SWD 연결, 동일 I/O 전압, 각자 USB 전원 조건이다. 보드 사이 전원 rail·
외부 pull-up·다른 출력은 없다. Controller 역할을 바꾸어도 MOSI끼리·MISO끼리 연결하며
SCK·CSN 출력은 매 transaction의 controller 한 대가 소유한다. [USB 재식별](evidence/t11-fixture202-1349e20/usb-inventory.json)은
A D/COM5·COM6, B E/COM7·COM8과 두 exact UID SHA를 확인했다. UID 원문은 저장하지 않았다.
기존 peer P0 DAP CTS 진단 중단 지시는 유지하며 이번 외부 SPI로 그 실패를 해소 처리하지 않는다.

Clean main/origin에서 새 pair image를 만들었다. 직전 0f429e7과 컴파일 입력 hash·설정·source
membership·FLASH/RAM은 같고 embedded commit identity는 이번 source로 갱신됐다.
[입력 비교](evidence/t11-fixture202-1349e20/build-input-comparison.json)는 그 사이 변경이 문서·증거에 한정됨도 확인한다.
[산출물 색인](evidence/t11-fixture202-1349e20/target-artifact-index.json)과 [exact image](evidence/t11-fixture202-1349e20/exact-images.json)에 원본 hash·
mailbox 위치를 보존했다. 제품 코드·시험 앱·canonical runner는 이번 작업에서 변경하지 않았다.

## 최초 flash 실패와 한정 재개

[첫 실행](evidence/t11-fixture202-1349e20/fixture202-attempt1.json)은 A 기록·boot 뒤 B/peer sector flash 중 CMSIS-DAP
응답 시간 초과로 실패했다. `external_wiring_executed=false`, 기능 record 0개이며 SPI 시험은
시작하지 않았다. [실패 log](evidence/t11-fixture202-1349e20/fixture202-attempt1.log)를 보존했다.

[읽기 전용 진단](evidence/t11-fixture202-1349e20/probe-diagnostic.json)은 flash/reset/fixture 명령 없이 두 보드의 10 MHz
CPUID `0x411FD210`과 COM 포트 네 개를 확인했다. A SLEEPING·B HALTED였다. 근본 원인은
미확정이며 [69번](69_T11_Fixture_103_current_source_UART_회귀.md)의 유사 peer flash 실패와
함께 보존한다. 같은 원인이라고 단정하지 않는다.

응답 회복을 관측한 뒤 [한정 재개 결정](evidence/t11-fixture202-1349e20/retry-decision.json)에 따라 같은 image·10 MHz·
유효한 원래 사용자 확인으로 새 evidence에서 한 번만 다시 시작했다. 두 번째 실행은 두 flash와
전체 기능을 통과했다. 첫 실패를 최종 기능 결과와 합치거나 삭제하지 않았다.

## 실제 결과와 coverage

두 controller 역할 × A SPIM/SPIS30 × B SPIM/SPIS20·21·22의 6개 조합을 실행했다.

| 검사 | PASS |
| --- | ---: |
| 2·4·8 MHz, Mode 0~3, MSB/LSB, 1·2·31·32·255·256·1024 bytes, 세 전송 방향·세 buffer 스타일 | 9,072 |
| 진행 중 1024-byte 전송 cancel·bounded STOP | 6 |
| 각 cancel 직후 32-byte 정상 복구 | 6 |
| **기능 합계** | **9,084** |

Data 9,078개에는 recovery 6개가 포함되며 예상 cancel 오류는 별도 6개다. Sync 단일 buffer,
async 단일/이중 buffer·handover를 포함한다. Controller→peripheral, peripheral→controller,
full duplex의 전체 RX를 독립 패턴 또는 ORC `0x96`과 대조하고 nonce/sequence/role, DMA
count/amount, memory guard, STOP 반환도 검사했다. 각 controller 역할 종료에서 두 보드의
disarm `[0]`을 확인했다. Cleanup 2개·progress 1개·complete 1개는 기능 PASS에 포함하지 않으며
총 journal은 9,088개다. [독립 감사](evidence/t11-fixture202-1349e20/results-audit.json)는 6개 조합별 1,514개 계획 ID와 실제 ID의
완전 일치·고유성, 누락·범위 이탈 0개, 최종 JSON과 append-only journal 일치를 확인했다.

옵션은 `--fixture 202 --swd-frequency-hz 10000000 --repetitions 1 --execute-fixture`다.
Exact 역할 image·확인서와 probe lock, sector erase·`auto_unlock=false`를 사용했다.
Mass erase/recover·보드 대체·속도 하향은 없었다. 관측된 응답 회복 뒤 한 번만 새 실행했다.
Runner 마지막 범용 `forced-error modes remain NOT RUN` 문구와 별개로 위 cancel·recovery는
실제 record로 판정한다. Fixture 201의 SPIM00+TWIM22 동시성은 이번 Fixture 202에 포함하지 않는다.
과거 SPIM30의 RXDELAY 교정 이후 검증은 [48번](48_M24_Fixture_202_SPI_실기_검증.md)에 보존하며
이번 새 source에서도 8 MHz 전체 matrix를 통과했다. T13 전체 동시성·soak와 다른 오류 모드는 남는다.

## 증거와 종료 상태

- [최종 JSON](evidence/t11-fixture202-1349e20/fixture202-attempt2.json), [append-only journal](evidence/t11-fixture202-1349e20/fixture202-attempt2.json.jsonl), [최종 log](evidence/t11-fixture202-1349e20/fixture202-attempt2.log)
- [사전 확인](evidence/t11-fixture202-1349e20/preflight.log), [최종 실행 wrapper](evidence/t11-fixture202-1349e20/run-attempt2.py), [환경·UID 비공개 처리](evidence/t11-fixture202-1349e20/runtime.py)
- [종료 확인](evidence/t11-fixture202-1349e20/postflight.json), [원본 byte·hash·gzip 목록](evidence/t11-fixture202-1349e20/raw-files.json)

종료 후 flash/reset/fixture 명령 없이 양쪽 CPUID `0x411FD210`, full 40-byte commit과 role을
다시 읽어 통과했다. CPU snapshot은 A SLEEPING·B SLEEPING이며 별도 기능 PASS 조건으로 사용하지 않는다.
양쪽 1349e20 DUT/peer image와 Fixture 202 결선을 유지한다. SWD 10 MHz는 요청한 clock이며
파형 품질을 계측했다는 뜻은 아니다. PyOCD board ID 미등록 안내도 원본 log에 보존했다.
과거 실패·build/image·raw evidence·공개 자산은 유지하며 추가 제거할 불용 파일은 확인되지 않았다.

UART 101~103의 4,932개 기능 PASS와 SPI 201의 18,169개 기능 PASS는 [67번](67_T11_Fixture_101_current_source_UART_회귀.md)·
[68번](68_T11_Fixture_102_current_source_UART_회귀.md)·[69번](69_T11_Fixture_103_current_source_UART_회귀.md)·
[70번](70_T11_Fixture_201_current_source_SPI_회귀.md)의 exact 원본으로 유지한다. 서로 다른 embedded
commit을 하나의 frozen-source 전체 HIL로 합치지 않는다. SPI 203·TWI 301, T12~T15와 RC/공개는
남아 있으며 readiness physical gate를 부분 결과로 승격하지 않는다. 최종 GitHub Actions는 미확인이다.

## 문서와 증거 검증

활성 문서 9개에 결과와 다음 결선을 반영했다. Markdown UTF-8·내부 링크 180개, 계약 45개,
inventory 75개·Serial identity 23개·System capability 16개를 통과했다. Readiness는 필수 16개 중
blocker 8개를 유지한다. [software 검사 기록](evidence/t11-fixture202-1349e20/software-verification.json)에
canonical 명령과 log hash를 보존했다. 제품 코드 변경이 없어 이전 full Host·package·전체 target
결과는 해당 source의 역사 증거로 유지한다.

이번 실행·준비 입력 42개를 UTF-8/LF 사본과 원본 byte gzip으로 보존하고 hash·복원 일치·
UID 비공개를 검사했다. 실제 시험 source와 최종 문서 commit을 구분하며 commit·main push와
checkout·board·SDK·작업 프로세스 종료 점검은 최종 작업 산출물에 기록한다.

## 다음: Fixture 203 SPI

**두 USB 전원을 모두 분리하고 A의 신호선 네 개만 옮긴다. B와 GND는 그대로다.**
[다음 결선 감사](evidence/t11-fixture202-1349e20/next-wiring-audit.json)에서 catalog와 사용자 확정 connector pinmap을 대조했다.

| A의 현재 Fixture 202 핀 | A의 새 Fixture 203 핀 | 유지할 B 핀 | 신호 |
| --- | --- | --- | --- |
| P2-25 | P2-12 / P1.04 | P2-12 / P1.04 | SCK |
| P2-26 | P2-11 / P1.05 | P2-11 / P1.05 | MOSI |
| P4-4 | P2-10 / P1.06 | P2-10 / P1.06 | MISO |
| P4-5 | P2-9 / P1.07 | P2-9 / P1.07 | CSN |
| P2-30 GND | 그대로 유지 | P2-30 GND | GND |

DAP UART 양쪽 분리·SWD 연결·동일 I/O 전압·각자 USB 전원을 유지하고 전원선이나 외부 저항은
추가하지 않는다. USB 재연결과 사용자 결선 완료 확인 뒤 새 exact HEAD image·확인서로 시작한다.
Fixture 203은 이번 결선과 확인서로 실행하지 않았다.
