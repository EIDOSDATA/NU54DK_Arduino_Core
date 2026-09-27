# T12 내부 ADC·TIMER·이벤트 무점퍼 검증

> 과거 검증 이력입니다. 준비·다음 작업·실행 조건은 기록 당시 기준이며, 현재 진행 상태는 [v0.5.0 TODO](../TODO_v0.5.0.md)를 따릅니다.

2026-09-07. 결선을 해제한 두 NU54DK에서 exact **874658a16db18b283ab7f1b2835111aaf34b42fd**의
내부 시험을 실행했다. **보드별 904 개, 합계 1,808 개 명령 PASS**다. 이전 080d771 PWM 회귀는
[94번](94_T14_PWM_지연_시작_취소와_무점퍼_검증.md)에 별도 보존한다. 이 결과는 T12 전체 완료가 아니다.

## 실제 시험 범위

| 기능 | 보드별 조합 | 두 보드 관측 결과 |
| --- | --- | --- |
| 내부 SAADC | 12 × 100 회 | configure/sample/stop 2,400 회, 52,000 samples, calibration 완료 1,200 회 |
| TIMER00/10/20~24 | 44 CC × clear/stop 4조합 × 1000/10000 tick, 각 10 회 | compare/capture·정지·clear 7,040 회 |
| EGU10/20→DPPI10/20 | 모든 source 16/6 개 × 모든 채널 24/16 개, 480조합 | 9,600,000 event 수신 |
| PPIB 네 쌍 | 모든 bridge channel과 원격 DPPI00/10/30, 44조합 | 880,000 event 왕복 수신, 양쪽 overflow 0 |
| GRTC 기존 시간 함수 | 1/10 ms × busy/sleep, 각 100 회 | micros/millis/delay/delayMicroseconds 800 회, 별도 TIMER와 대조 |
| PWM 공존 후 회귀 | PWM20/21/22 × CPU/DPPI 시작·취소 4방식, 각 100 회 | 추가 2,400 configure/play/stop |

ADC는 VDD/AVDD 단독·2채널 역순 scan, 1/32 sample, READY/DONE/FINISHED·완료 buffer와
길이·calibration 완료를 검사했다. 모든 반복에서 전후 16-byte guard와 요청 길이 이후 tail을
확인하고, 마지막 반복의 96-byte 원본도 Host가 독립 해석했다. VSS 입력 거부와 block/DMA
lease 반환을 확인했다. 교정 전압·ENOB 같은 정밀도 평가나 진행 중 calibration 강제 취소는 아니다.

TIMER는 선택 CC의 compare를 관측하고 다른 CC에서 capture한다. 자동 clear/stop 조합,
명시적 stop 후 값 유지·clear 후 0·SHORTS 해제를 확인했다. 각 조합의 compare는 10 회이며
44 CC 각각 1000 회 비교로 표시하지 않는다. 시험용 system 예약 거부도 7,040 회 확인했다.

EGU/DPPI와 PPIB는 각 조합에서 1000 event × 10 회를 실행했다. CPU는 source EGU만 trigger하고
수신 event를 직접 관측했다. PPIB는 서로 다른 두 channel을 통한 왕복으로 되먹임을 방지했다.
채널 disable 뒤 미전달 10,480 회, group 수명주기·해제 61,280 회와
동일 수의 group 예약 거부를 대조했다. Group enable은 public API로 소유·구성한 group의
HAL task를 사용한다. 빈 자원에 설정한 시험용 예약이며 OS가 실제 소유한 GRTC 채널을 침범하지 않았다.

## 최초 실패와 판정 교정

첫 exact 35f30b2 실행은 A의 ADC·TIMER·EGU/DPPI·PPIB 888 개 PASS 후 첫 GRTC 명령에서
중단했다. 1000us busy-wait 요청에 micros 995us, TIMER와 차이 16us를 관측했다. 새 HIL이
1000us 미만을 무조건 거부한 것이 원인이었다. [첫 실패 감사](evidence/t12-internal-nojumper-35f30b2/hardware-partial-audit.json)에
A 888 PASS·1 FAIL·15 미실행, B 904 미실행과 controlled reset/halt를 그대로 보존한다.

고정 SDK의 [Zephyr busy-wait 계약](https://docs.zephyrproject.org/latest/doxygen/html/group__thread__apis.html)은
delay clock과 system clock의 차이를 명시한다. 기존 V04-EVENT 시험표의 ±5%를 busy-wait의
하한·상한 모두에 적용하고 5% 밖은 거부하는 Host 회귀를 추가했다. Sleep은 요청 이상·여유 3 ms,
두 경로의 TIMER 차이는 요청의 5% 이내를 요구한다.
제품 시간 구현을 변경하거나 최초 실패를 PASS로 재분류하지 않았다.

두 번째 fcf85c2 실행은 A의 904명령 PASS 뒤 B의 첫 시간 명령에서 66 회 반복 후 중단했다.
micros 997~1011us, millis 0~2 ms, TIMER 차이 최대 13us였다. 서로 다른 읽기 시점과
31250Hz kernel tick(32us)을 생략하고 micros를 밀리초로 내림한 판정이 원인이었다.
millis와 micros의 차이는 1 ms 양자화 + kernel tick 32us + 실제 TIMER 읽기 구간 차이로
제한하고 마지막 세 값·최대 오차를 원본에 추가했다. 3 ms 차이·잘못된 원본은 Host가 거부한다.
[두 번째 실패 감사](evidence/t12-internal-nojumper-fcf85c2/hardware-partial-audit.json)에
A 904 PASS, B 1 FAIL·903 미실행·66 회 부분 반복과 cleanup을 보존한다.

874658a의 canonical target 1/1을 새 C:/nj28에서 빌드하고 교정한 시간 명령부터 두 보드
전체 904 개씩 재실행했다. Source/ELF/HEX·nonce·sequence·원본 요청·32-word 응답·ADC RAM 사본을
독립 대조했으며 누락·중복·미실행은 없다. 처음부터 끝까지 SWD는 **10 MHz**였다.

## 종료 상태와 증거

두 보드는 874658a nojumper image의 명령 대기 상태다. ADC와 PWM20/21/22 off,
네 DPPI CHEN=0, P1.14 PIN_CNF=2 입력 복원과 실패 latch=0을 확인했다.
정확한 두 UID hash·sector flash·auto_unlock=false·controlled reset/start·배타 probe lock을 사용했다.
UART/console은 해당 image에서 비활성화했다. 보드 간 신호선은 연결하지 않았다.

- [최종 독립 감사](evidence/t12-internal-nojumper-874658a/hardware-internal-audit.json), [전체 원본 목록](evidence/t12-internal-nojumper-874658a/raw-files.json), [실기 기록](evidence/t12-internal-nojumper-874658a/hardware-attempt1.json).
- [최초 실패 원본 목록](evidence/t12-internal-nojumper-35f30b2/raw-files.json). 최초 preflight의 두 번째 EGU 주소 표기 오류는 94번 evidence의 internal-resource-preflight2에서 올바른 EGU20 주소 0x500C9000으로 다시 읽어 교정했다.
- [전용 HIL·명령 정의](../../tests/zephyr/m25_nojumper_hil/README.md). ELF/HEX·전체 compile DB는 기록된 로컬 build root에 유지하고 SHA와 설정·identity를 저장소에 보존했다.

## 남은 작업과 재개 조건

| 다음 범위 | 남은 확인 | 필요한 조건 |
| --- | --- | --- |
| T12 PWM | 12 slot의 실제 period/duty·극성·TOP/load/sequence/loop/DPPI/triggered-step capture | 승인된 peer GPIO 결선과 capture HIL 확장 |
| T12 GPIO/GPIOTE | 승인 pin과 가용 channel의 edge·level·task/set/clear·누출 | 시험별 peer 결선 |
| T12 I2S | 1024 word, 연속 100 buffer, TX-only/RX-only | 430 결선 재구성·HIL 확장 |
| T12 QDEC | 실행 중 역전·read/clear/restart·invalid transition·반복 조건 | 420 결선 재구성·HIL 확장 |
| T12 event의 범위 대조 | TIMER의 상세 반복 요구와 system 예약 경계를 전체 시험표에 최종 대응 | 이번 10 회 compare 결과의 범위를 유지하고 T12 전체로 확대하지 않음 |
| T13 | 오류 복구·handover·86 방향 충돌·600s 단독/7200s 동시 soak | 해당 T11/T12 단독 PASS와 승인 topology, 필요한 스위치·재연결 |
| T15~T18 | 지원 범위 확정·최종 사용자 통합 | T12~T14 실기 결과 |
| R14·T19~T25 | RC 동결·최종 package·승인·정식 공개·공개 URL 검증 | 선행 gate와 별도 공개 승인 |

440 PDM의 기본·연속 검증은 91·92번에서 완료했으며 이번에 반복 결선을 요구하지 않는다.
Readiness는 필수 16 개 중 미해결 8 개를 유지한다. 공용 자원 수정 뒤 필요한 최종-source T11 회귀는
후속 통합에서 수행한다. [93번](93_Host_재검증과_T12_이후_남은_작업.md)은 이번 실행 전 목록이며,
현재 재개 순서는 [현재 TODO](../TODO_v0.5.0.md)의 체크포인트를 따른다.
