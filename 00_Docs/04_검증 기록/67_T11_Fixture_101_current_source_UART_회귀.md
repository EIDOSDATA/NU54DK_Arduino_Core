# T11 Fixture 101 current-source UART 회귀

| 항목 | 내용 |
| --- | --- |
| 기록일 | 2026-09-06 |
| 범위 | R00~R13 이후 current-source T11 중 Fixture 101 한 연속 cycle |
| Exact Core source | `154324ce7a865522374066ca957ebc98909c7c19` |
| Board gitlink | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` |
| Build root | `C:/u3a`, DUT/peer 2/2 build-only PASS; failed/error/warning 0, 116.12초 |
| SWD 설정 | flash·attach·mailbox·종료 identity 확인 모두 **10,000,000 Hz**; 속도 하향·재시도 없음 |
| 실제 결과 | 기능 **1,644 PASS**, 실패 0; cleanup 2개와 campaign 2개는 기능 PASS 수에서 제외 |
| 연속 cycle 시간 | 476.25초; 장시간 soak 판정 아님 |
| 다음 작업 | Fixture 102 전원 OFF 결선 변경과 사용자 완료 확인 |

## 사용자 확인과 exact 입력

사용자는 직전 Fixture 101 결선표·스위치·전압 조건 안내에 대해 결선 완료와 최대 SWD 속도를
요청했다. 이를 [체크포인트](evidence/t11-fixture101-154324c/checkpoint.json)에 기록하고 30분 유효기간 안에
exact 이미지·catalog·두 UID SHA에 묶인 [확인서](evidence/t11-fixture101-154324c/confirmation.json)를 검증했다.
이는 사용자 결선 확인이며 전기적 계측으로 배선을 증명했다는 뜻은 아니다.

두 보드는 D/COM5·COM6의 A/DUT와 E/COM7·COM8의 B/peer이며
[USB 식별 결과](evidence/t11-fixture101-154324c/usb-inventory.json)에 UID SHA만 보존한다. DAP UART는 양쪽
분리, SWD는 연결 상태다. 각각 자기 USB 전원, 공통 GND, 동일 I/O 전압이며 전원 rail 직접
연결·외부 pull-up·다른 출력 장치는 사용하지 않는다.

| A/DUT 핀 | 방향 | B/peer 핀 |
| --- | --- | --- |
| P4-21 / P2.02 TX | → | P2-11 / P1.05 RX |
| P4-19 / P2.00 RX | ← | P2-12 / P1.04 TX |
| P2-19 / P2.05 RTS | → | P2-9 / P1.07 CTS |
| P2-17 / P2.04 CTS | ← | P2-10 / P1.06 RTS |
| P2-30 / GND | ↔ | P2-30 / GND |

Clean `main`/`origin/main`의 exact source를 새로 빌드했다. 이전 373d98d pair와 비교한
컴파일 입력 hash·설정·source membership·FLASH/RAM은 같으며, embedded commit identity는
154324c로 갱신됐다. [build 비교](evidence/t11-fixture101-154324c/build-input-comparison.json),
[ELF/HEX·build record hash](evidence/t11-fixture101-154324c/target-artifact-index.json),
[exact image와 mailbox 주소](evidence/t11-fixture101-154324c/exact-images.json)에 근거를 보존한다.
최종 문서 commit과 검증한 firmware source는 구분한다. 제품 runtime·시험 앱·canonical runner는
이번 작업에서 변경하지 않았다.

## 실제 기능 결과

A의 UARTE00/20과 B의 UARTE20/21/22를 조합하고 송신 역할을 양쪽으로 바꿨다.
총 12개 역할·instance 조합에서 각각 137개 기능 결과를 통과했다.

| 검사 | PASS |
| --- | ---: |
| 9,600·115,200·1,000,000 baud, parity off/even, RTS/CTS off/on, 1·2·31·32·255·512·1024 bytes, 단일/이중 buffer | 1,584 |
| 수신 준비 전 CTS가 TX를 100ms 정지시킨 뒤 재개 | 12 |
| parity mismatch와 break 오류 검출·bounded STOP | 24 |
| 각 오류 직후 독립 패턴 정상 전송 복구 | 24 |
| **기능 합계** | **1,644** |

최대 RX는 1024-byte buffer 두 개, 총 2048 bytes다. Canonical runner가 nonce/sequence/role,
guard·DMA 완료 수와 길이, seed 기반 독립 기대 payload, STOP 반환을 검사했다. 데이터 record는
복구를 포함해 1,620개, 예상 오류 record는 24개다. 최종 JSON과 append-only JSONL이 같고
기능 ID 1,644개가 모두 고유함을 [coverage 감사](evidence/t11-fixture101-154324c/results-audit.json)로 확인했다.
두 송신 역할 종료마다 두 보드 모두 disarm `[0]`을 반환했다. cleanup 두 개, progress 하나,
campaign 완료 하나를 포함한 전체 journal은 1,648개다.

Runner의 마지막 출력에 남아 있는 `forced-error modes remain NOT RUN` 문구는 범용 문구다.
이번 UART의 실제 parity/break 오류 및 각 복구 판정은 위 원시 record를 기준으로 한다.
그 밖의 미실행 오류 모드나 T13 전체 동시성·soak까지 통과했다고 해석하지 않는다.
기존 peer P0 DAP CTS 납땜 의심 경로는 재시험하지 않았고 이번 외부 P2↔P1 PASS로 지우지 않는다.

## 원본과 재현

- [최종 JSON](evidence/t11-fixture101-154324c/fixture101-attempt1.json), [append-only JSONL](evidence/t11-fixture101-154324c/fixture101-attempt1.json.jsonl), [실행 log](evidence/t11-fixture101-154324c/fixture101-attempt1.log)
- [읽기 전용 preflight](evidence/t11-fixture101-154324c/preflight.log), [canonical 실행 wrapper](evidence/t11-fixture101-154324c/run.py), [환경·UID 비공개 wrapper](evidence/t11-fixture101-154324c/runtime.py)
- [종료 identity](evidence/t11-fixture101-154324c/postflight.json), [원본 byte/hash·gzip 목록](evidence/t11-fixture101-154324c/raw-files.json)

실행 옵션은 `--fixture 101 --swd-frequency-hz 10000000 --repetitions 1 --execute-fixture`이며,
exact DUT/peer UID는 SHA로 메모리에서 선택했다. confirmation과 새 evidence 경로를 명시하고
OS probe lock을 유지했다. Flash는 sector erase·`auto_unlock=false`였으며 mass erase/recover와
보드 자동 대체를 하지 않았다. 공개 tag/Release/index도 변경하지 않았다.

SWD 10 MHz는 요청한 clock 설정이며 계측한 파형 품질이나 모든 probe의 상한 보증 수치가 아니다.
pyOCD의 board ID 미등록 안내는 explicit `nrf54l` target 선택과 함께 남겼다. 실제 CPUID는
두 보드 모두 `0x411FD210`이며, 종료 시 flash/reset 없이 full 40-byte commit과 role을 다시 읽어
확인했다. 두 보드에는 154324c DUT/peer image가 남아 있고 Fixture 101 결선은 유지한다.

## 문서와 증거 검증

문서 9개에 현재 상태와 다음 결선을 반영했다. Markdown UTF-8·내부 링크 176개, CI 계약
45개, inventory 75개·Serial identity 23개·System capability 16개가 통과했다. Readiness는
필수 16개 중 blocker 8개를 유지한다. [software 검사 기록](evidence/t11-fixture101-154324c/software-verification.json)에
canonical 명령·log hash를 연결한다. 이번 변경은 문서·증거뿐이므로 기존 full Host·package·
전체 target 결과를 새 결과로 복사하지 않으며 64~66번의 exact source 이력을 유지한다.

원본 24개를 UTF-8/LF 사본과 원본 byte gzip으로 보존하고 SHA-256·복원 일치·UID 비공개를
검사했다. 재개에 필요한 이미지·build 입력·원시 기록을 보존했으며 추가 삭제 대상은 없다.
최종 GitHub Actions 상태는 미확인이다. 최종 commit/push와 checkout·SDK·작업 프로세스 점검은
작업 산출물에 기록하고, 이 문서의 source hash를 자기 문서 commit으로 소급 변경하지 않는다.

## 다음 결선과 남은 범위

이번 PASS는 Fixture 101만이다. Current-source T11 전체 완료 표시는 보류하며 다음은
Fixture 102, 이어서 103·201·202·203·301이다. T12~T15와 RC/공개 gate는 계속 대기한다.
Readiness의 필수 physical gate를 이번 부분 결과만으로 PASS로 바꾸지 않는다.

Fixture 102는 **두 USB를 모두 분리한 뒤 A 쪽 신호선 네 개만 옮긴다. B 쪽과 GND는 그대로다.**

| A의 기존 Fixture 101 핀 | A의 새 Fixture 102 핀 | 유지할 B 핀 |
| --- | --- | --- |
| P4-21 | P2-25 / P0.00 TX | P2-11 / P1.05 RX |
| P4-19 | P2-26 / P0.01 RX | P2-12 / P1.04 TX |
| P2-19 | P4-4 / P0.02 RTS | P2-9 / P1.07 CTS |
| P2-17 | P4-5 / P0.03 CTS | P2-10 / P1.06 RTS |
| P2-30 GND | P2-30 GND 유지 | P2-30 GND |

DAP UART 양쪽 분리·SWD 연결·동일 전압·각자 USB 전원 조건을 유지한다. 외부 저항과 전원선은
추가하지 않는다. 새 결선 완료 확인 뒤 당시 clean HEAD의 exact image와 새 confirmation으로
Fixture 102를 시작한다. 이전 101 확인서·부분 결과를 재사용하지 않는다.
