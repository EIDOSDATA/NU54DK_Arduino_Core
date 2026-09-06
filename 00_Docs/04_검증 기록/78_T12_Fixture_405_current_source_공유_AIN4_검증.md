# T12 Fixture 405 — 공유 AIN4 오픈드레인 실기 검증

2026-09-06, exact `9fc12bfbdafbb8a4450ed6cc61ca97b9c1efd220`에서 Fixture 405 **첫 실행 12개 PASS**, ADC **2,592 samples**,
양쪽 cleanup **12회 PASS**를 확인했다. 신호 시험 구간은 **6.906초**이며
업로드·준비 시간은 별도다. T12는 부분 완료이고 사용자 지정 후속 **406→407→408을 모두 수행**한다.

## 범위와 결선

| 보드 | 역할 | GPIO |
| --- | --- | --- |
| A, D:/COM5·6 | DUT role 1, SAADC 입력 | P1.11/AIN4 (P4-9) |
| B, E:/COM7·8 | peer role 2, LOW 또는 해제 신호원 | P1.14 (P4-12) |
| 양쪽 | 공통 기준 | GND (P2-30) |

사용자는 전원 OFF 변경 안내 뒤 “ㅇㅇ 했다. P1.11 했다”라고 확인했다. 확인 기록 시각은
2026-09-06T12:52:24Z이며 DAP UART 양쪽 분리·SWD 연결·각자 USB 재연결, SB1/PMIC 설정 유지 조건이다.
실행기는 30분 이내 확인서에 exact core/board revision·두 UID SHA-256·각 HEX SHA-256·catalog revision 3을
결합했다. [확인서](evidence/t12-fixture405-9fc12bf/confirmation.json)와 [USB inventory](evidence/t12-fixture405-9fc12bf/usb-inventory.json)를 보존했다.

[원본 회로도](<../../board_package/NU54DK_Zephyr_DTS/NU54-DK Schematic.pdf>) 1·3쪽에서
**P1.11→SB1→PMIC_INT→BQ25186 /INT pin 9**, R3 10kΩ→VDD_MOD를 확인했다. 이전 활성 문서의
“DAP 전원 감지” 설명은 교정했다. 별도 DAP MCU의 IF_VMOD_SENSE와 구별한다. /INT는 오픈드레인
출력이며 짧은 interrupt LOW가 가능하므로 B는 **S0D1·내부 pull-up의 LOW/해제만** 사용한다.
SB1 실제 개폐 상태를 측정하거나 PMIC 레지스터를 변경하지 않았다. 해제 시 HIGH를 관측한 사실만 판정한다.

## 구현과 사전 검증

T05/T10/T12 시험 경로에 405 전용 `(0, samples, phase, 0, 0, buffers, 0, 0)` 계약을 추가했다.
phase는 0 LOW-before, 1 released, 2 LOW-after이며 samples 32/256·buffers 1/2로 12개다.
PWM 인자와 다른 ID/role·예약 word·잘못된 경계는 핀 설정 전에 거부한다. 406·407은 후속 설계 전까지
실행 allowlist에 넣지 않고 계획의 필수 미완료 항목으로 남겼다. 408 PWM 경로는 유지한다.

신호원은 입력 해제→출력 latch 1→S0D1/pull-up 순서로 준비하고 start 때 LOW 또는 해제로 바뀐다.
종료·실패·lease 만료 시 입력으로 해제한다. 두 번째 보드 arm 실패 시에도 양쪽 cleanup을 수행하도록
기존 runner를 보완했다. ADC RAM은 INT16_MIN sentinel로 채워 stale/부분 DMA를 검출한다.
Host는 source 설정을 시작 전·샘플 완료 후 읽고, 종료 때 B를 먼저 해제한 뒤 다시 읽는다.

정착 10ms 뒤 2ms 간격의 수동 SAADC SAMPLE, 12-bit·gain 1/4·oversample 1을 사용했다.
LOW raw는 -256~256, released raw는 -256~4095 범위에서 **95% 이상 >256 및 median >256**을 요구했다.
독립 사후 감사는 LOW/해제/LOW 순서와 해제 중앙값이 두 LOW 중앙값보다 256 초과 높은지도 확인했다.
정밀 전압·ADC offset 보정·PMIC interrupt 생성 검증으로 확대하지 않는다.

전체 Host **648 tests/80 groups**, 계약 **45 tests**, Inventory 75·Serial 23·System 16,
C/C++ 정렬 **358 files**가 통과했다. Readiness는 필수 16개 중 blocker 8개를 유지한다.
초기 전체 Host에서 405를 invalid로 기대한 기존 assertion 1건과 추가 assertion의 정렬 실패를 발견·교정했다.
그 실패 log와 최종 성공 log를 모두 [software 검증](evidence/t12-fixture405-9fc12bf/software-verification.json)에 보존하며
물리 실패로 세지 않는다. [변경 범위 감사](evidence/t12-fixture405-9fc12bf/build-input-comparison.json)에서 제품 core·variant·
library·board·build tool 변경이 없고 pair application의 main/signal 소스만 바뀐 것을 확인했다.

새 C:/u3l pair DUT/peer **2/2 build PASS**, 경고·오류 없이 **118.36초**였다.
[artifact index](evidence/t12-fixture405-9fc12bf/target-artifact-index.json)와 [build 근거](evidence/t12-fixture405-9fc12bf/target-build-evidence.json)에
exact source·HEX/ELF·설정·실제 컴파일 입력 hash를 보존했다. 과거 T11/401~404 증거를 새 source의
실기 PASS로 복사하지 않았다.

## 실제 결과

| 버퍼당 samples | buffer 수 | LOW 전 중앙값 | 해제 중앙값 | LOW 후 중앙값 | 결과 |
| --- | --- | --- | --- | --- | --- |
| 32 | 1 | 68.0 | 3752.0 | 68.0 | PASS |
| 32 | 2 | 70.0 | 3752.0 | 72.0 | PASS |
| 256 | 1 | 68.0 | 3752.0 | 68.0 | PASS |
| 256 | 2 | 68.0 | 3752.0 | 68.0 | PASS |

LOW raw 전체 56~84, 해제 raw 3,740~3,760이었다. 네 DMA 조합 모두 LOW→HIGH→LOW를 구별했다.
GPIO 설정 readback 24개에서 고정 B P1.14·출력 방향·pull-up·S0D1·phase latch를 확인했고,
raw PIN_CNF의 DIR/INPUT/PULL/DRIVE0/DRIVE1을 독립 해석해 `(PIN_CNF & 0xF0F)==0x80D`를 대조했다.
해제 readback 12개는 입력·no-pull·출력 미소유와 해당 mask 0을 확인했다. 모든 DMA 길이·buffer 완료와
ADC 전체 samples의 SHA-256을 대조했다. raw samples 자체도 JSON/journal에 남겼다.

[최종 JSON](evidence/t12-fixture405-9fc12bf/fixture405-attempt1.json)과 [순차 journal](evidence/t12-fixture405-9fc12bf/fixture405-attempt1.json.jsonl)은
기능 12·cleanup 12·campaign 2의 **26 records**가 순서까지 일치했다.
[독립 감사](evidence/t12-fixture405-9fc12bf/results-audit.json)는 실행기에 의존하지 않는 12 vector 계획으로 누락·중복을 확인했다.

| 원본 | SHA-256 |
| --- | --- |
| JSON | `5c7d7d9a1d756693657fcc5b76aa9a49713a4149897afd4aa846de3a0700fffb` |
| journal | `33718b75e9ac95ec2abf49eabebf9ec4344e0bbacc36fc6ce1b3d351e07d7b7e` |

SWD는 양쪽 모두 **10,000,000 Hz**이며 sector erase·auto_unlock=false를 유지했다. mass erase·recover·
unlock·속도 하향·PMIC 쓰기 없이 첫 실행에 통과했다. 종료 후 [읽기 전용 검사](evidence/t12-fixture405-9fc12bf/postflight.json)는
2026-09-06T13:12:22.111518Z 양쪽 CPUID 0x411FD210·full source·role 일치를 확인했고 두 CPU는 SLEEPING이었다.

## 누적 범위와 다음 작업

| Fixture | 입력 | 상태 |
| --- | --- | --- |
| 401~404 | AIN0~3/P1.04~P1.07 | 각 exact source에서 PWM 기능 48개씩 PASS |
| 405 | AIN4/P1.11, PMIC_INT 공유 | exact 9fc12bf 오픈드레인 기능 12개 PASS |
| 406 | AIN5/P1.12, VBAT 분압기/SB4 공유 | 필수 후속 기능 시험, 별도 신호원 준비·결선 확인 대기 |
| 407 | AIN6/P1.13, 사용자 버튼 공유 | 필수 후속 기능 시험, 별도 신호원 준비·결선 확인 대기 |
| 408 | AIN7/P1.14, LED buffer 입력 공유 | 필수 후속 PWM 기능 시험, 결선 확인 대기 |

401~405의 서로 다른 exact source 합계는 기능 **204개**, cleanup **204회**, ADC **44,064 samples**다.
정적 오픈드레인 405를 PWM 48 vector와 같은 시험으로 세지 않는다. 406·407·408을 생략하지 않는다.
이후 420 QDEC·430 I2S·440 PDM 및 PWM period/duty capture·ADC calibration/채널 순서 등 T12 나머지 요구,
T13 동시성/장시간·T14/T15·T16~T18·R14·RC/공개 gate는 미완료다. 다음 결선은 개별 안내와 사용자 확인 뒤
변경하며 현재 A P1.11↔B P1.14를 임의로 변경하지 않는다.

## 증거 보존

준비·실행·실패·software 입력 42개를 UTF-8/LF 사본과 원본 byte gzip으로 보존했다.
[원본 manifest](evidence/t12-fixture405-9fc12bf/raw-files.json)는 모든 byte/hash와 gzip 복원 일치를 기록한다.
기존 공개 자산·역사 실기 원본은 보존했고 새 helper와 Host 검증 파일은 실제 참조가 있어 유지했다.
최종 문서 검사·commit·main push는 뒤의 검증 결과와 작업 산출물에 기록한다.

## 최종 문서 검증

활성 문서와 새 78번 기록 9개를 갱신했다. Markdown UTF-8·내부 링크 **187 files**, 계약 45개,
Inventory 75/23/16 및 readiness blocker 8개 유지 검사를 통과했다.
[문서 검증 기록](evidence/t12-fixture405-9fc12bf/documentation-verification.json)에 공개한 log의
정규화 byte hash를 보존했다. 사전 software 검증의 hash는 raw-files manifest와 gzip 원본 byte를 기준으로 한다.
문서 등록 뒤 링크 검사를 한 번 더 수행하고, staged 원본 gzip·hash·정확한 변경 경계를 대조한 뒤 commit·main push한다.
공개 release/tag는 생성하지 않는다. 최종 commit과 origin 일치·깨끗한 checkout·보드/SDK 불변·작업 프로세스 종료
결과는 저장소 밖 완료 보고서에 남겨 자기 commit hash를 소급 삽입하지 않는다.
