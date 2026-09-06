"""! @brief 검증된 Fixture 301 결과로 영구 기록 본문을 만듭니다. """
import json
import re

def make_record(work):
    audit = json.loads((work / 'results-audit.json').read_text(encoding='utf-8'))
    post = json.loads((work / 'postflight.json').read_text(encoding='utf-8'))
    coverage = json.loads((work / 't11-coverage-audit.json').read_text(encoding='utf-8'))
    assert audit['status'] == 'passed' and audit['successful_attempt'] == 1
    assert coverage['current_source_t11_complete'] and coverage['totals']['functional_pass'] == 61423
    assert all(row['status'] == 'passed' for row in post['devices']) and len(post['devices']) == 2
    states = '·'.join(f"{label} {row['state']}" for label, row in zip(('A', 'B'), post['devices']))
    elapsed = re.search(r'with no warnings in ([\d.]+) seconds', (work / 'build.log').read_text(encoding='utf-8-sig')).group(1)
    e = 'evidence/t11-fixture301-9a63251'
    return f'''# T11 Fixture 301 current-source TWI 회귀와 통신 단독 검증 완료

| 항목 | 내용 |
| --- | --- |
| 기록일 | 2026-09-06 |
| 범위 | R00~R13 이후 Fixture 301 전체 한 연속 cycle; current-source T11 단독 통신 회귀 완료 |
| Exact Core | `9a63251ed6f8b9916d8e49d8210414b21c5c7267` |
| Board gitlink | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` |
| Build | `C:/u3g` DUT/peer 2/2 build-only PASS, failed/error/warning 0, {elapsed}초 |
| SWD | flash·mailbox·종료 확인 모두 **10,000,000 Hz** |
| 결과 | 첫 실행 **1,986개 기능 PASS**, 실패 0개, 연속 {audit['continuous_elapsed_seconds']}초 |
| 다음 | T12 Fixture 401 PWM→AIN0 전원 OFF 결선 변경과 새 사용자 확인 |

## 입력과 사용자 확인

사용자는 [72번의 Fixture 301 안내](72_T11_Fixture_203_current_source_SPI_회귀.md) 뒤 준비 완료·시작을 지시했다.
[체크포인트]({e}/checkpoint.json)와 [확인서]({e}/confirmation.json)에 11:01:21 UTC의 원래 확인 시각,
catalog revision 2, 두 UID SHA·role·exact source·HEX hash와 스위치·전압·pull-up 조건을 연결했다.
30분 유효 시간 안에 실행했으며 확인 시각을 갱신하지 않았다. 배선은 사용자 확인이며 전기 계측 결과는 아니다.

| 신호 | A/DUT | B/peer |
| --- | --- | --- |
| SDA | P2-12 / P1.04 | P2-25 / P0.00 |
| SCL | P2-11 / P1.05 | P2-26 / P0.01 |
| GND | P2-30 / GND | P2-30 / GND |

이전 SPI MISO·CSN 점퍼는 양쪽 제거 조건이다. DAP UART 양쪽 분리·SWD 연결, 동일 I/O 전압,
각자 USB 전원, 공통 GND를 유지했다. Target TWIS 내부 pull-up을 사용하고 외부 저항·보드 간 전원 rail·
다른 출력은 연결하지 않았다. PMIC P1.02/P1.03 버스와 분리된 경로다.
[USB 재식별]({e}/usb-inventory.json)에서 A D/COM5·COM6, B E/COM7·COM8과 두 exact UID SHA를 확인했다.

[산출물 색인]({e}/target-artifact-index.json), [build evidence]({e}/target-build-evidence.json),
[exact image]({e}/exact-images.json)에 새 clean source의 두 역할 이미지와 hash·mailbox 위치를 보존했다.
제품 코드·시험 앱·canonical runner는 이번에 변경하지 않았다.

## 실제 실행과 독립 판정

두 controller 역할 × A TWIM/TWIS20·21·22 × B TWIM/TWIS30의 6개 조합을 실행했다.

| 검사 | PASS |
| --- | ---: |
| 100/400/1,000 kHz, 1·2·31·32·255·256 bytes, 주소 0x42/0x43, 세 방향·세 buffer 스타일 | 1,944 |
| 주소 NACK·진행 중 cancel와 bounded STOP | 12 |
| SDA stuck-low 실패·해제·recoverBus | 6 |
| NACK·cancel·stuck-SDA 각각 뒤 정상 32-byte 재전송 | 18 |
| TWIS buffer를 5 ms 늦게 제공한 clock stretch 뒤 정상 완료 | 6 |
| **기능 합계** | **1,986** |

Data 1,968개는 일반 1,944·복구 18·clock stretch 6을 포함한다. Sync 단일 buffer와 async 단일/이중
buffer, controller→target·target→controller·write-then-read를 검사했다. 실제 RX 전체를 독립 seed
패턴과 비교하고 DMA amount·completion count·guard·STOP 반환·role·nonce를 확인했다.
각 controller 역할 종료에서 두 보드 disarm `[0]`을 확인했다. Cleanup 2개와 campaign 2개는 기능
PASS에 포함하지 않으며 전체 journal은 1,990개다.

[독립 결과 감사]({e}/results-audit.json)는 조합당 331개, 전체 고유 ID 1,986개의 계획·실제 순서와
최종 JSON·append-only journal 일치를 확인했다. 누락·중복·범위 이탈은 없다. 과거 [50번](50_M24_Fixture_301_TWI_실기_검증.md)의
중복 recovery ID는 역사 원본 그대로 보존한다. 이번 source는 NACK·cancel·stuck-SDA 원인을
suffix로 구분한 고유 ID를 실제로 생성했다.

`--fixture 301 --swd-frequency-hz 10000000 --repetitions 1 --execute-fixture`로 첫 실행에서 완료했다.
두 exact probe lock, sector erase, `auto_unlock=false`를 유지했다. 속도 하향·mass erase·recover·unlock·
재시도는 없었다. Runner의 범용 종료 문구 `forced-error modes remain NOT RUN`과 별개로 위 오류·복구는
실제 record로 판정한다. 1 MHz는 이 결선의 기능 PASS이며 rise-time·신호 품질·외부 부품 호환성 보증이 아니다.

## current-source T11 완료 판정

[전체 묶음 감사]({e}/t11-coverage-audit.json)는 일곱 fixture의 원본 journal hash·실제 기능 수·고유 ID와
cleanup을 대조했다. 과거 원본은 보존 gzip에서 복원하여 검사했다.

| 회귀 | 기능 PASS | 근거 |
| --- | ---: | --- |
| UART 101~103 | 4,932 | [67번](67_T11_Fixture_101_current_source_UART_회귀.md)·[68번](68_T11_Fixture_102_current_source_UART_회귀.md)·[69번](69_T11_Fixture_103_current_source_UART_회귀.md) |
| SPI 201~203 | 54,505 | [70번](70_T11_Fixture_201_current_source_SPI_회귀.md)·[71번](71_T11_Fixture_202_current_source_SPI_회귀.md)·[72번](72_T11_Fixture_203_current_source_SPI_회귀.md) |
| TWI 301 | 1,986 | 이번 exact 9a63251 |
| **합계** | **61,423** | cleanup 14개 별도 |

[빌드 입력 대조]({e}/build-input-comparison.json)는 이전 여섯 fixture의 양쪽 image와 이번 image 사이
컴파일 source hash·resolved config·source membership·FLASH/RAM 일치를 확인했다. 최초 Fixture 101부터
이번 source까지의 Git 변경도 문서·증거에 한정된다. Embedded commit은 실행별 exact identity로 구분하며
하나의 frozen commit에서 동시에 실행한 전체 campaign이라고 하지 않는다.

이 근거로 **R00~R13 이후 current-source T11의 승인된 단독 통신 경로 회귀를 완료**한다.
T12 analog/stream, T13 동시성·soak, T14~T15 지원 확정, T16~T18·R14·RC/공개는 남는다.
M24 physical readiness를 단독 통신 PASS만으로 승격하지 않는다. 과거 probe flash timeout과
사용자가 중단시킨 peer P0 DAP CTS 진단은 보존하며 이번 첫 실행 PASS로 원인 해결을 주장하지 않는다.

## 증거와 종료 상태

- [전체 JSON]({e}/fixture301-attempt1.json)·[journal]({e}/fixture301-attempt1.json.jsonl)·[실행 log]({e}/fixture301-attempt1.log)
- [실행 wrapper]({e}/run.py)·[환경/UID 비공개]({e}/runtime.py)·[사전 확인]({e}/preflight.log)
- [종료 확인]({e}/postflight.json)·[원본 byte/hash 목록]({e}/raw-files.json)

종료 후 추가 flash/reset/fixture 명령 없이 양쪽 CPUID `0x411FD210`과 full 40-byte commit·role을 읽어
통과했다. CPU snapshot은 {states}다. 양쪽 9a63251 DUT/peer image와 Fixture 301 결선을 유지한다.
기존 실패·build/image·증거·공개 자산은 보존했으며 추가 제거할 불용 파일은 확인되지 않았다.
최종 GitHub Actions 상태는 미확인이다.

## 다음: Fixture 401 PWM→AIN0

**두 USB 전원을 모두 분리한 뒤 신호 한 선과 GND만 연결한다.**
[다음 결선 감사]({e}/next-wiring-audit.json)에서 catalog와 사용자 확정 connector pinmap을 대조했다.

| 신호 | A/DUT | B/peer |
| --- | --- | --- |
| B PWM → A AIN0 | P2-12 / P1.04 유지 | 현재 P2-25 끝을 **P4-12 / P1.14**로 이동 |
| GND | P2-30 유지 | P2-30 유지 |

기존 SCL A P2-11↔B P2-26 점퍼는 양쪽에서 제거한다. B만 PWM source이고 A는 ADC 입력이며
이번 401에서는 역할을 반대로 바꾸지 않는다. DAP UART 분리·SWD 연결·동일 I/O 전압·각자 USB 전원을
유지하고 외부 저항·보드 간 전원선은 추가하지 않는다. USB 재연결과 새 사용자 결선 완료 확인 뒤
Fixture 401용 exact image·확인서로 시작한다. 이번 작업에서는 T12를 실행하지 않았다.
'''
