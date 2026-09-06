# T11 Fixture 201 current-source SPI 회귀

| 항목 | 내용 |
| --- | --- |
| 기록일 | 2026-09-06 |
| 범위 | R00~R13 이후 current-source T11 중 Fixture 201 한 연속 cycle |
| Exact Core | `0f429e7ab9b5b8e24f4ff19e47abe60014975547` |
| Board gitlink | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` |
| Build | `C:/u3d` DUT/peer 2/2 build-only PASS, failed/error/warning 0, 115.72초 |
| SWD | flash·mailbox·종료 확인 모두 **10,000,000 Hz**, 속도 하향 없음 |
| 실기 | 첫 실행 **18,169개 기능 PASS, 실패 0개**, 2175.312초 |
| 다음 | Fixture 202 SPI 전원 OFF 결선 변경과 사용자 확인 |

## Exact 입력과 사용자 결선 확인

사용자는 [69번 기록](69_T11_Fixture_103_current_source_UART_회귀.md)의 다음 Fixture 201 안내 뒤
연결 완료를 확인했다. [시작 기록](evidence/t11-fixture201-0f429e7/checkpoint.json)과 [새 확인서](evidence/t11-fixture201-0f429e7/confirmation.json)는
catalog revision 2, exact 두 UID SHA·역할·source·HEX hash와 스위치·전압 조건을 연결한다.
사용자 확인 시각부터 30분 안에 시작한 단일 연속 cycle이며 확인 시각을 중간에 갱신하지 않았다.
결선은 사용자 확인에 근거하며 전기적 계측 결과로 해석하지 않는다.

| 신호 | A/DUT | B/peer |
| --- | --- | --- |
| SCK | P4-20 / P2.01 | P2-12 / P1.04 |
| A MOSI / A SPIS MISO | P4-21 / P2.02 | P2-11 / P1.05 |
| A MISO / A SPIS MOSI | P2-17 / P2.04 | P2-10 / P1.06 |
| CSN | P2-19 / P2.05 | P2-9 / P1.07 |
| GND | P2-30 / GND | P2-30 / GND |

DAP UART 양쪽 분리, SWD 연결, 동일 I/O 전압, 각자 USB 전원 조건이다. 보드 사이 전원 rail·
외부 pull-up·다른 출력은 연결하지 않는다. P2 전용 SPIS 역할의 MOSI/MISO 교대는 firmware가
처리하며 SCK·CSN 출력은 매 transaction의 controller 한 대가 소유한다.
[USB 재식별](evidence/t11-fixture201-0f429e7/usb-inventory.json)에서 A D/COM5·COM6, B E/COM7·COM8과 두 exact UID SHA를
확인했다. UID 원문은 저장하지 않았다. 기존 peer P0 DAP CTS 진단 중단 지시는 유지한다.

Clean main/origin에서 새 pair image를 만들었다. 직전 7aece93과 컴파일 입력 hash·설정·source
membership·FLASH/RAM은 같고 embedded commit identity만 이번 source로 갱신됐다.
[입력 비교](evidence/t11-fixture201-0f429e7/build-input-comparison.json)는 그 사이 변경이 문서·증거에 한정됨도 확인한다.
[산출물 색인](evidence/t11-fixture201-0f429e7/target-artifact-index.json)과 [exact image](evidence/t11-fixture201-0f429e7/exact-images.json)에 원본 hash·
mailbox 위치를 보존했다. 제품 코드·시험 앱·canonical runner는 변경하지 않았다.

## 실제 결과와 독립 coverage 대조

양쪽 controller 역할 × A SPIM/SPIS00·20 × B SPIM/SPIS20·21·22의 12개 조합을 실행했다.

| 검사 | PASS |
| --- | ---: |
| 2·4·8 MHz, Mode 0~3, MSB/LSB, payload 1·2·31·32·255·256·1024 bytes, 세 전송 방향과 세 buffer 스타일 | 18,144 |
| 진행 중 1024-byte 전송 cancel·bounded STOP | 12 |
| 각 cancel 직후 32-byte 정상 복구 | 12 |
| SPIM00 1024-byte 비동기 전송과 TWIM22 온보드 PMIC 읽기 동시성 | 1 |
| **기능 합계** | **18,169** |

SPI data 18,157개에는 recovery 12개와 동시성 1개가 포함되며 예상 cancel 오류는 별도 12개다.
Sync 단일 buffer, async 단일/이중 buffer·handover를 포함한다. Controller→peripheral,
peripheral→controller, full duplex에서 RX 전체 byte를 독립 패턴 또는 ORC `0x96`과 대조했다.
Nonce/sequence/role, DMA count/amount, memory guard, STOP 반환도 canonical oracle이 검사했다.

양쪽 controller 역할 종료마다 두 보드의 disarm `[0]`을 확인했다. Cleanup 2개·campaign progress
1개·complete 1개는 기능 PASS와 별도이며 총 journal은 18,173개다. [독립 coverage 감사](evidence/t11-fixture201-0f429e7/results-audit.json)는
명시한 matrix의 계획 ID 18,169개와 실제 ID의 완전 일치·고유성, 누락 0개·범위 이탈 0개,
최종 JSON과 append-only journal 일치를 확인했다. Role 1/(0,20)은 동시성 포함 1,515개,
나머지 11개 조합은 각각 1,514개다.

실행 옵션은 `--fixture 201 --swd-frequency-hz 10000000 --repetitions 1 --execute-fixture`다.
새 확인서·evidence, exact role image와 OS probe lock을 사용했다. Flash는 sector erase·
`auto_unlock=false`이며 mass erase/recover·속도 하향·자동 재시도·보드 대체는 없었다.
Runner 마지막 범용 `forced-error modes remain NOT RUN` 문구와 별개로 위 cancel과 recovery는
실제 record로 판정한다. T13 전체 동시성·장시간 soak·다른 오류 모드는 이 결과에 포함하지 않는다.

과거 8 MHz RXDELAY 결함과 수정 결과는 [47번 기록](47_M24_Fixture_201_SPI_실기_검증.md)의
exact 원본을 유지한다. 이번 새 source 전체 실행은 해당 8 MHz matrix도 통과했다.
그 이전 PASS를 복사하거나 실패 원본을 소급 수정하지 않았다.

## 증거와 종료 상태

- [최종 JSON](evidence/t11-fixture201-0f429e7/fixture201-attempt1.json), [append-only journal](evidence/t11-fixture201-0f429e7/fixture201-attempt1.json.jsonl), [실행 log](evidence/t11-fixture201-0f429e7/fixture201-attempt1.log)
- [사전 확인](evidence/t11-fixture201-0f429e7/preflight.log), [실행 wrapper](evidence/t11-fixture201-0f429e7/run.py), [고정 환경·UID 비공개 처리](evidence/t11-fixture201-0f429e7/runtime.py)
- [종료 확인](evidence/t11-fixture201-0f429e7/postflight.json), [원본 byte·hash·gzip 목록](evidence/t11-fixture201-0f429e7/raw-files.json)

종료 뒤 flash/reset/fixture 명령 없이 양쪽 CPUID `0x411FD210`, full 40-byte commit과 role을
다시 읽어 통과했다. CPU snapshot은 A SLEEPING·B SLEEPING이며 별도 기능 PASS 조건으로 사용하지 않는다.
양쪽 0f429e7 DUT/peer image와 Fixture 201 결선을 유지한다. SWD 10 MHz는 요청한 clock 설정이며
계측한 파형 품질 보증은 아니다. PyOCD board ID 미등록 안내는 explicit `nrf54l` 선택과 함께
원본 log에 보존했다. 재개용 build/image·과거 실패·raw evidence와 공개 자산을 유지하며
이번 작업에서 추가 제거가 필요한 불용 파일은 확인되지 않았다.

Current-source UART 101~103의 4,932개 기능 PASS는 [67번](67_T11_Fixture_101_current_source_UART_회귀.md)·
[68번](68_T11_Fixture_102_current_source_UART_회귀.md)·[69번](69_T11_Fixture_103_current_source_UART_회귀.md)에
각 exact source로 보존한다. 이번 SPI 201은 별도 source 결과이며 하나의 frozen-source 전체 HIL로
합치지 않는다. SPI 202·203, TWI 301, T12~T15와 RC/공개는 남아 있다. Readiness 필수 physical
gate는 부분 결과만으로 승격하지 않는다. 최종 GitHub Actions 상태는 미확인이다.

## 문서와 증거 검증

활성 문서 9개에 결과와 다음 결선을 반영했다. Markdown UTF-8·내부 링크 179개, 계약 45개,
inventory 75개·Serial identity 23개·System capability 16개를 통과했다. Readiness는 필수 16개 중
blocker 8개를 유지한다. [software 검사 기록](evidence/t11-fixture201-0f429e7/software-verification.json)에
canonical 명령과 log hash를 보존했다. 제품 코드 변경이 없어 이전 full Host·package·전체 target
결과는 해당 source의 역사 증거로 유지한다.

이번 실행·준비 입력 32개를 UTF-8/LF 사본과 원본 byte gzip으로 보존하고 hash·복원 일치·
UID 비공개를 검사했다. 실제 시험 source와 최종 문서 commit을 구분하며 commit·main push와
checkout·board·SDK·작업 프로세스 종료 점검은 최종 작업 산출물에 기록한다.

## 다음: Fixture 202 SPI

**두 USB 전원을 모두 분리하고 A 쪽 신호선 네 개를 아래처럼 옮긴다. B와 GND는 그대로다.**
[다음 결선 감사](evidence/t11-fixture201-0f429e7/next-wiring-audit.json)는 catalog와 사용자 확정 connector pinmap을 대조했다.

| A의 현재 Fixture 201 핀 | A의 새 Fixture 202 핀 | 유지할 B 핀 | 신호 |
| --- | --- | --- | --- |
| P4-20 | P2-25 / P0.00 | P2-12 / P1.04 | SCK |
| P4-21 | P2-26 / P0.01 | P2-11 / P1.05 | MOSI |
| P2-17 | P4-4 / P0.02 | P2-10 / P1.06 | MISO |
| P2-19 | P4-5 / P0.03 | P2-9 / P1.07 | CSN |
| P2-30 GND | 그대로 유지 | P2-30 GND | GND |

DAP UART 양쪽 분리·SWD 연결·동일 I/O 전압·각자 USB 전원을 유지하고 전원선이나 외부 저항은
추가하지 않는다. USB 재연결과 사용자 결선 완료 확인 뒤 새 exact HEAD image·확인서로 시작한다.
Fixture 202는 이번 결선과 확인서로 실행하지 않았다.
