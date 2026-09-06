# T12 Fixture 408 — current-source PWM→AIN7 검증

| 항목 | 내용 |
| --- | --- |
| 기록일 | 2026-09-07 Asia/Seoul, 원본 시각은 UTC |
| Exact Core | `87b987d9ed50855e0134f2c637c00706572719a5` |
| Board gitlink | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` |
| Fixture | revision 5, ID 408, controller B/role 2 |
| Build | C:/u3q pair 2/2 PASS, failed/error/warning 0, 116.06초 |
| SWD | flash·mailbox·읽기 전용 진단·postflight 모두 **10,000,000 Hz** |
| 실기 | attempt2에서 **48개 기능 PASS**, campaign **26.375초**; 첫 DUT flash 실패 구분 |
| 다음 | **420 QDEC** 별도 재결선·확인; 전체 T12는 부분 완료 |

## 결선과 실행 입력

사용자의 “연결 완료 408 진행해”를 **2026-09-06T15:35:46Z**에 기록했다.
직전 안내인 양쪽 USB 분리 → A 쪽 P1.13을 P1.14로 이동 → USB 재연결에 대한 완료 확인이다.
[checkpoint](evidence/t12-fixture408-87b987d/checkpoint.json)와 [confirmation](evidence/t12-fixture408-87b987d/confirmation.json)에 원래 시각·두 UID hash·source·image·조건을 연결했다.
이는 사용자 결선 확인이며 USB 열거만으로 전기적 결선을 계측한 것은 아니다.

| 연결 | A DUT / role 1 | B peer / role 2 |
| --- | --- | --- |
| PWM → AIN7 | **P1.14**, P4-12, SAADC 입력 | **P1.14**, P4-12, PWM 출력 |
| 공통 GND | P2-30 | P2-30 |

이전 A P1.13 선은 제거했다. DAP UART 양쪽 분리·SWD 연결, 같은 I/O 전압·각자 USB 전원,
기존 SB/PMIC 유지·다른 출력/전원선 없음 조건이다. P1.14는 양쪽 모두 LED4 buffer 입력과 공유하며
MCU 출력은 B만 켠다. [USB 재식별](evidence/t12-fixture408-87b987d/usb-inventory.json)은 A D/COM5·6, B E/COM7·8의 지정 두 probe를 확인했다.

Source 393e419의 전체 Host **655 PASS·1 조건부 SKIP(총 656)**·관련 113·계약 45·package 20·정렬 358·
Inventory·예제 발견·pair/BLE target 8/8은 [81번](81_T12_Fixture_407_Host_재개와_검증.md)에 유지한다.
[software 입력 비교](evidence/t12-fixture408-87b987d/software-input-comparison.json)는 87b987d까지 문서·역사 증거 외 변경이 없음을 확인했다.
이를 새 software 실행으로 세지 않았다. 새 exact pair는 NCS v3.4.0·bundle dcbdc366a1로 빌드했고,
각 역할의 repository translation unit 42개·정규화 설정·source 소속은 직전 407 pair와 동일하다.
[build 비교](evidence/t12-fixture408-87b987d/build-input-comparison.json), [build 기록](evidence/t12-fixture408-87b987d/target-build-evidence.json),
[artifact index](evidence/t12-fixture408-87b987d/target-artifact-index.json)에 SDK revision·설정·실제 image identity를 보존했다.

| 역할 | HEX SHA-256 | ELF SHA-256 |
| --- | --- | --- |
| 1 | `f91fcd69f19e9b1ec30fcf0f60190630ac28ac082fabeeee35c9395082ce240c` | `30443d6a6ad76e3f8383c5ffa675b408ec4c19896740b688fd1a8c77ca448f00` |
| 2 | `0eb819bd57df4b52440ab5597d28c0ca467a0841363db22ceeedf97da5ce95ea` | `a3cceb44d7c3fb699eba2fc48c1481965452285f4d98988ab004fa7a64e6eebb` |

## 최초 flash 실패와 제한된 재실행

[attempt1](evidence/t12-fixture408-87b987d/fixture408-attempt1.json)은 A/DUT sector flash 도중 CMSIS-DAP 응답 timeout으로
2026-09-06T15:40:08.004339Z에 실패했다. B flash 전이며 `external_wiring_executed=false`,
기능 record 0개다. 이 결과를 ADC 기능 실패나 PASS로 세지 않는다.

[읽기 전용 진단](evidence/t12-fixture408-87b987d/probe-diagnostic.json)은 flash/reset/fixture 명령 없이 두 보드의
10 MHz CPUID `0x411fd210`과 COM 포트 네 개를 확인했다. A HALTED·B SLEEPING이었다.
Timeout의 근본 원인은 미확정이다. 과거 비슷한 증상과 공통 원인이 있다고 단정하지 않는다.
[재실행 결정](evidence/t12-fixture408-87b987d/retry-decision.json)에 따라 같은 source·image·10 MHz와 유효한 원래 사용자 확인으로
**한 번만** 새 evidence에 전체 실행했다. 원래 확인 시각은 갱신하지 않았으며 실패한 결과·경과 시간을 다음 실행에 합산하지 않았다.
Sector erase·auto_unlock=false를 유지했고 mass erase/recover·unlock·속도 하향·보안 정책 변경은 없었다.

## 408 실기와 결과 감사

PWM20/21/22 × channel slot 0~3 × 32/256 samples × 단일/이중 DMA = **48개**다.
B P1.14로 순차 route하고 top 1021·compare 512·individual load를 사용했다.
A AIN7은 12-bit·gain 1/4·manual SAMPLE이다. 요청·수집 수, 완료·오류 상태,
DMA 반환 길이와 HIGH 관측을 검사했다. **10,368 samples**를 읽어 vector별 min/max·sample hash를 기록했다.
전체 raw 범위는 **-24~3780**, LOW(<256)와 HIGH(>256)는 각각 **48개 vector**에서 관측했다.
HIGH와 sample count가 필수 oracle이며 LOW는 추가 관측이다. 교정 전압이나 PWM 주기·듀티 측정값은 아니다.

기능마다 A→B disarm `[0]`을 확인해 **cleanup 48개**를 남겼다. Campaign 관리 2개를 더한
98개 journal record는 최종 JSON과 순서까지 같다. [독립 감사](evidence/t12-fixture408-87b987d/results-audit.json)는 별도 48개 계획,
고유 ID·순서·상태·DMA count·cleanup·확인서 hash·두 image/UID·SWD를 대조했다.
PWM 기록은 개별 sample 배열 대신 min/max·hash를 저장하므로 사후 감사에서 sample hash를 재계산했다고 주장하지 않는다.

| 원본 | 원본 byte SHA-256 |
| --- | --- |
| [fixture408-attempt2.json](evidence/t12-fixture408-87b987d/fixture408-attempt2.json) | `251f4e09de518365039204026c98b84653eb11d92c1199a7901fc4d26adcefb8` |
| [fixture408-attempt2.json.jsonl](evidence/t12-fixture408-87b987d/fixture408-attempt2.json.jsonl) | `c5609349fd1ec0669864c1db7c82fbb62dfb326717004db915f5f7a583913dd4` |

[최종 실행 log](evidence/t12-fixture408-87b987d/fixture408-attempt2.log)의 `V04_SIGNAL_PASS=two-board-synthetic-signal`과
[실행 wrapper](evidence/t12-fixture408-87b987d/run-attempt2.py)를 보존했다. 26.375초는 완료 campaign이며 build·flash 시간은 별도다.
2026-09-06T15:43:04.482525+00:00의 [postflight](evidence/t12-fixture408-87b987d/postflight.json)는 추가 flash/reset/fixture 명령 없이
full source·role·protocol·CPUID를 양쪽에서 확인했다. 당시 상태는 둘 다 SLEEPING이었다.

## 누계·남은 범위·보존

[누계 감사](evidence/t12-fixture408-87b987d/analog-coverage-audit.json)는 이전 401~407 원본 gzip의 hash·기능 수·cleanup·DMA count를 대조했다.
401~404·408 PWM 각 48개와 405 오픈드레인·406/407 입력 바이어스 각 12개를 합쳐
**276개 기능·59,616 samples·276개 cleanup**이다. AIN0~7 모두 각 exact source에서 개별 기능 근거를 확보했다.
공유 채널 시험을 PWM 시험과 같은 범위로 합치거나 한 frozen-source campaign으로 바꾸지 않는다.

**420 QDEC·430 I2S·440 PDM**, PWM period/duty capture·ADC calibration API/채널 순서·timer/event 등
전체 T12 요구와 T13 동시성·600/7,200초 soak·최종 통합·RC·공개는 남아 있다.
M24/M25 전체와 readiness 필수 16개 중 미해결 8개는 유지한다. 새 원격 GitHub Actions는 미확인이다.

[원본 manifest](evidence/t12-fixture408-87b987d/raw-files.json)의 **45개 입력**은 UTF-8 LF 사본과 원본 byte gzip으로 보존했다.
최초 실패·진단·재실행·build·postflight를 포함하며 UID 원문 부재·gzip 복원·SHA·Git stage byte를 검사한다.
기존 검증 기록·SDK·board·공개 자산과 현재 image·재현 입력은 유지했다. 새 불필요한 저장소 파일은 없다.
최종 [문서 검사](evidence/t12-fixture408-87b987d/docs-verification.json)는 Markdown **192개 PASS**다.
문서·증거를 commit·main push한 뒤 clean checkout·remote 일치·시험 프로세스 종료를 확인한다.

## 다음 결선: 420 QDEC

양쪽 USB를 분리하고 기존 A P1.14 신호 끝을 **P1.04**로 이동한다. B P1.14는 유지하며 두 번째 신호선을 추가한다.

| A DUT | B peer | 용도 |
| --- | --- | --- |
| **P1.04** (P2-12) | **P1.14** (P4-12) | QDEC A상 |
| **P1.06** (P2-10) | **P1.10** (P4-8) | QDEC B상 |
| GND (P2-30) | GND (P2-30) | 공통 GND |

[다음 결선 감사](evidence/t12-fixture408-87b987d/next-wiring-audit.json)는 현재 catalog와 사용자 확인 connector pinmap을 대조했다.
DAP UART 양쪽 분리·SWD 연결·기존 SB/PMIC를 유지하고 USB를 재연결한 뒤 별도 사용자 완료 확인을 받는다.
이번에는 420을 실행하지 않았다. 후속 문서 HEAD와 408 업로드 source를 구분하고 새 exact pair를 준비한다.
