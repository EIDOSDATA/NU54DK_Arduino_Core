# T12 Fixture 403 current-source PWM→AIN2 실기 검증

| 항목 | 내용 |
| --- | --- |
| 기록일 | 2026-09-06 |
| 범위 | Fixture 403 단독 한 cycle; T12 전체 부분 완료 |
| Exact Core | `c95b9049a62e7c911e4b67104a8f36391ab7e168` |
| Board gitlink | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` |
| Build | `C:/u3j` DUT/peer 2/2 build-only PASS, failed/error/warning 0, 116.13초 |
| SWD | flash·mailbox·종료 read-only 확인 모두 **10,000,000 Hz** |
| 결과 | 첫 실행 **48개 기능 PASS**, 연속 26.407초 |
| 다음 | Fixture 404: A P1.06→P1.07/AIN3, 전원 OFF 결선 변경과 새 확인 |

## 결선 확인과 exact 입력

[75번 Fixture 402](75_T12_Fixture_402_current_source_PWM_ADC_검증.md) 완료 뒤 A 쪽 신호를
P1.05에서 P1.06/AIN2로 옮기는 403 안내를 제공했다. 사용자가 “403 시작해”라고 지시하여
직전 결선 안내 상태의 실행 지시로 기록했다. [체크포인트](evidence/t12-fixture403-c95b904/checkpoint.json)와
[확인서](evidence/t12-fixture403-c95b904/confirmation.json)에 12:04:31 UTC의 원래 기록 시각, catalog revision 2,
두 UID SHA·role·exact source·HEX hash와 조건을 연결했다. 시각 갱신 없이 30분 이내 실행했으며
사용자 지시 문맥에 따른 확인을 소프트웨어의 직접 전기 계측으로 확대하지 않는다.

| 연결 | A/DUT, role 1 | B/peer, role 2 |
| --- | --- | --- |
| B PWM → A AIN2 | **P1.06**, P2-10 | **P1.14**, P4-12 |
| 공통 GND | GND, P2-30 | GND, P2-30 |

양쪽 USB를 분리하고 A 쪽만 이동한 조건이다. B·GND는 유지하며 DAP UART 양쪽 분리·SWD 연결,
동일 I/O 전압·각자 USB 전원·외부 저항/보드 간 전원 rail/다른 출력 없음 조건이다.
Controller는 B/role 2만 사용했다. [USB 재식별](evidence/t12-fixture403-c95b904/usb-inventory.json)은
A D/COM5·COM6, B E/COM7·COM8과 기존 exact UID 두 개를 확인했다.

[build evidence](evidence/t12-fixture403-c95b904/target-build-evidence.json), [artifact 색인](evidence/t12-fixture403-c95b904/target-artifact-index.json),
[exact image](evidence/t12-fixture403-c95b904/exact-images.json)에 두 역할의 새 HEX/ELF·설정·빌드 기록·hash를 보존했다.
NCS v3.4.0·bundle dcbdc366a1·GNU Arm 14.3·bundled Python·pyOCD 0.42.0을 사용했다.
[402 대비 입력 대조](evidence/t12-fixture403-c95b904/build-input-comparison.json)는 두 역할의 컴파일 소스·설정·소속·메모리가
직전 ff483a1과 같음을 확인했다. Embedded commit identity는 별도 유지한다.
제품·시험 앱·canonical runner·SDK·board는 이번에 변경하지 않았다.

## 실기와 독립 감사

PWM20·21·22 × channel slot 0~3 × 32/256 samples × 단일/이중 DMA buffer = **48개**다.
B P1.14로 순차 route하며 top 1021·compare 512·individual load를 사용한다.
A SAADC는 AIN2·12-bit·gain 1/4이며 수동 SAMPLE로 수집한다. 준비·시작·완료·오류 0,
DMA 반환 pointer/길이·완료 mask, 요청/수집 sample 수와 HIGH 관측을 판정했다.

전체 **10,368 samples**를 읽고 vector별 sample hash·min/max를 기록했다.
LOW(raw <256)는 48개, HIGH(raw >256)는
48개 vector에서 관측했다. 전체 raw 범위는
-24~3784이며 교정 전압·ADC 정확도나 PWM 주기·듀티 측정값이 아니다.

매 vector 뒤 양쪽 disarm `[0]`을 확인했다. Cleanup 48개와 campaign 2개는 기능 PASS에서
제외했으며 journal은 총 98개다. 같은 cleanup 논리 ID는 바로 앞 기능 record와 순서로 대응한다.
[독립 감사](evidence/t12-fixture403-c95b904/results-audit.json)는 별도 48개 계획·고유 ID·전체 순서·상태·길이·해제,
JSON/journal 일치·image/UID·10 MHz를 대조했다.

| 원본 | SHA-256 |
| --- | --- |
| [결과 JSON](evidence/t12-fixture403-c95b904/fixture403-attempt1.json) | `a3050e2ec0c8d0172ef773e2c94d9b2f4c1db0a3ea216e2b17064d34067c5125` |
| [journal](evidence/t12-fixture403-c95b904/fixture403-attempt1.json.jsonl) | `0f4e87485d2ee08f138c1948a61337ced6c04db0696122911e2aa3b412356eae` |

양쪽 flash와 전체 cycle은 첫 실행에서 통과했다. Sector erase·`auto_unlock=false`를 사용했고
mass erase/recover·SWD 하향·재시도는 없었다. [종료 read-only 확인](evidence/t12-fixture403-c95b904/postflight.json)은
reset/flash 없이 CPUID `0x411fd210`, full 40-byte commit·role을 2/2 검증했다.
CPU snapshot은 A SLEEPING·B SLEEPING이다.

[부분 coverage 감사](evidence/t12-fixture403-c95b904/analog-coverage-audit.json)는 이전 401·402의 원본 gzip을 복원하고
각 SHA를 확인한 뒤 현재 403까지 별도 48개 고유 계획을 대조했다. 세 fixture 합계는 기능
**144개**, cleanup **144개**, samples **31,104개**다.
각 exact source는 구분하며 하나의 frozen-source 캠페인으로 합치지 않는다. T11의 61,423개
기능 결과와 과거 실패·공개 자산은 보존했다.

## T12의 남은 범위

401~403은 PWM route와 AIN0~2의 수집/DMA/정지 근거다. HIGH와 sample 수가 현재 oracle의
필수 판정이며 LOW는 min/max의 추가 관측이다. PWM period/duty capture, ADC calibration/
채널 순서, timer/event 등 T12 전체 요구는 별도로 검증해야 한다.
404·408·420·430·440과 T13 동시성·600/7,200초 soak, T14~T15 판정, 최종 통합·RC·공개는
미완료다. M24/M25 전체와 readiness gate를 승격하지 않았다. GitHub Actions는 미확인이다.

## 문서와 증거 검증

활성 문서 9개에 결과와 다음 결선을 반영했다. Markdown UTF-8·내부 링크 185개, 계약 45개,
inventory 75개·Serial identity 23개·System capability 16개를 통과했다. Readiness는 필수 16개 중
blocker 8개를 유지한다. [software 검사 기록](evidence/t12-fixture403-c95b904/software-verification.json)에
canonical 명령과 log hash를 보존했다. 제품 코드 변경이 없어 이전 full Host·package·전체 target
결과는 해당 source의 역사 증거로 유지한다.

이번 실행·준비 입력 32개를 UTF-8/LF 사본과 원본 byte gzip으로 보존하고 hash·복원 일치·
UID 비공개를 검사했다. 실제 시험 source와 최종 문서 commit을 구분하며 commit·main push와
checkout·board·SDK·작업 프로세스 종료 점검은 최종 작업 산출물에 기록한다.

## 다음: Fixture 404 PWM→AIN3

양쪽 USB를 분리하고 **A 쪽만 P1.06 → P1.07/AIN3**로 이동한다(P2-10 → P2-9).
**B P1.14와 공통 GND는 그대로** 유지한다. DAP UART 양쪽 분리·SWD 연결·동일 I/O 전압·
각자 USB 전원·다른 출력/전원선 없음 조건을 유지하고 USB 재연결 완료를 확인한다.
[다음 핀맵 감사](evidence/t12-fixture403-c95b904/next-wiring-audit.json)에 GPIO/connector 대응을 보존했다.
이번에는 404를 실행하지 않았으며 새 확인과 exact HEAD 이미지가 필요하다.
